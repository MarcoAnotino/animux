import concurrent.futures
import os
import re
import urllib.parse

from .base import BaseAnimeExtractor, _clean_text, _source_id, _split_source_id


class MonoschinoExtractor(BaseAnimeExtractor):
    site_name = "monoschino"
    supports_dub = True
    _VALID_URL = r'https?://(?:www\.)?monoschino2\.com/ver/(?P<anime_id>[a-zA-Z0-9_-]+)-(?P<ep_no>\d+)/?'

    base_url = "https://monoschino2.com"

    def _series_url(self, title_or_id):
        source, identifier = _split_source_id(title_or_id)
        if source and source != self.site_name:
            raise ValueError(f"El identificador pertenece a {source}.")
        identifier = identifier or ""
        if identifier.startswith("http"):
            return identifier.rstrip("/") + "/"
        if re.fullmatch(r"[a-zA-Z0-9_-]+", identifier):
            return f"{self.base_url}/anime/{identifier}/"
        results = self.search(identifier)
        if not results:
            raise RuntimeError(f"MonosChino no encontró {identifier!r}.")
        return _split_source_id(results[0]["id"])[1]

    def search(self, title, dub=False):
        query = urllib.parse.quote_plus(title).replace("+", "%20")
        page = self._download_webpage(f"{self.base_url}/buscar?q={query}")
        if not page:
            return []

        candidates = []
        seen = set()
        
        # Estructura típica de tarjetas de series de MonosChino (/anime/slug)
        anchor_pattern = re.compile(
            r'<a[^>]+href=["\'](?P<href>(?:https?://(?:www\.)?monoschino2\.com)?/'
            r'anime/(?P<slug>[a-zA-Z0-9_-]+)/?)["\'][^>]*>(?P<body>.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        
        for match in anchor_pattern.finditer(page):
            slug = match.group("slug")
            body = match.group("body")
            
            # Limpiamos tags HTML internos que puedan venir dentro del contenedor de la tarjeta
            clean_body = re.sub(r'<[^>]+>', '', body)
            name = _clean_text(clean_body)
            url = urllib.parse.urljoin(self.base_url, match.group("href"))
            
            if not name or url in seen:
                continue
            seen.add(url)
            candidates.append((url, name))

        limit = max(1, int(os.getenv("ANIMUX_SPANISH_SEARCH_LIMIT", "12")))
        candidates = candidates[:limit]

        def enrich(candidate):
            url, name = candidate
            episodes = self.list_episodes(
                _source_id(self.site_name, url)
            )
            return {
                "id": _source_id(self.site_name, url),
                "title": name,
                "total_episodes": len(episodes),
                "extractor": self.site_name,
            }

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(candidates) or 1)) as executor:
            futures = [executor.submit(enrich, candidate) for candidate in candidates]
            for future in futures:
                try:
                    result = future.result()
                    if result["total_episodes"]:
                        results.append(result)
                except Exception as exc:
                    self._log(f"[monoschino][Aviso] No se pudo contar un resultado: {exc}")
        return results

    def list_episodes(self, title_or_id, dub=False):
        series_url = self._series_url(title_or_id)
        page = self._download_webpage(series_url)
        if not page:
            return []

        # Captura los números de los episodios directamente mapeados en las URLs del contenedor
        numbers = {
            match.group("ep_no")
            for match in re.finditer(
                r'href=["\'][^"\']*/ver/[a-zA-Z0-9_-]+-(?P<ep_no>\d+(?:\.\d+)?)["\']',
                page
            )
        }
        return sorted(numbers, key=float)

    def get_episode(self, title_or_id, episode, dub=False):
        series_url = self._series_url(title_or_id)
        
        # Reconstruye la URL de reproducción a partir del slug de la serie
        anime_id = series_url.rstrip("/").split("/")[-1]
        episode_url = f"{self.base_url}/ver/{anime_id}-{episode}"
        return self._stream_result(self.extract(episode_url))

    def extract(self, url, match=None):
        match = match or re.match(self._VALID_URL, url)
        if not match:
            raise ValueError("La URL proporcionada no es válida para MonosChino.")

        anime_id = match.group('anime_id')
        ep_no = match.group('ep_no')
        self._log(f"[monoschino] Analizando anime: {anime_id} (Episodio {ep_no})")

        html = self._download_webpage(url)
        if not html:
            raise RuntimeError("No se pudo obtener el HTML de la página del episodio.")

        iframe_urls = []
        ironhentai_urls = []

        # 1. Extracción y clasificación de IFrames
        other_iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        for iframe in other_iframes:
            if iframe.startswith('/'):
                iframe = f"{self.base_url}{iframe}"
            
            # Desarmamos el redireccionador de animepelix si existe
            if "animepelix.net" in iframe:
                parsed = urllib.parse.urlparse(iframe)
                params = urllib.parse.parse_qs(parsed.query)
                target_url = params.get('id', [iframe])[0]
            else:
                target_url = iframe

            # SEPARACIÓN CRÍTICA: Protegemos a IronHentai de las expresiones regulares base
            if "ironhentai.com" in target_url:
                if target_url not in ironhentai_urls:
                    ironhentai_urls.append(target_url)
            else:
                if target_url not in iframe_urls:
                    iframe_urls.append(target_url)

        video_url = None
        chosen_iframe = None

        # 2. PRIORIDAD: Procesar IronHentai de forma segura
        if ironhentai_urls:
            self._log(f"[monoschino] Detectados {len(ironhentai_urls)} servidores de IronHentai. Evitando trampa de regex...")
            for iron_url in ironhentai_urls:
                # Intentamos extraer el flujo directo usando el subproceso de yt-dlp interno de tu app
                resolved = self._get_url_via_ytdlp(iron_url, referer=url)
                if resolved:
                    video_url = resolved
                    chosen_iframe = iron_url
                    self._log("[monoschino] ¡URL directa obtenida de IronHentai mediante yt-dlp!")
                    break
            
            # Si yt-dlp no extrajo un stream crudo pero la URL es la buena para tu reproductor,
            # la usamos directamente como dictaminaste en tu prueba.
            if not video_url:
                self._log("[monoschino] Pasando URL de IronHentai directamente al formato de salida.")
                video_url = ironhentai_urls[0]
                chosen_iframe = url

        # 3. FALLBACK 1: Si no hay IronHentai, usamos el método multihilo tradicional con los otros servidores
        if not video_url and iframe_urls:
            self._log(f"[monoschino] No se usó IronHentai. Probando los otros {len(iframe_urls)} servidores...")
            video_url, chosen_iframe = self._extract_video_from_iframes(iframe_urls, url)

        # 4. FALLBACK 2: Último recurso, yt-dlp directo a la página web
        if not video_url:
            self._log("[monoschino] Intentando yt-dlp en URL base...")
            video_url = self._get_url_via_ytdlp(url, referer=self.base_url)
            chosen_iframe = url

        if not video_url:
            raise RuntimeError("Ninguno de los servidores disponibles devolvió un flujo de video válido.")

        return {
            'id': f"{anime_id}-{ep_no}",
            'title': f"{anime_id.replace('-', ' ').title()} - Episodio {ep_no}",
            'extractor': 'monoschino',
            'formats': [
                {
                    'format_id': 'monoschino-best',
                    'url': video_url,
                    'ext': 'mp4',
                    'protocol': 'm3u8_native' if '.m3u8' in video_url else 'https',
                    'http_headers': {
                        'User-Agent': self.user_agent,
                        'Referer': chosen_iframe
                    }
                }
            ]
        }
