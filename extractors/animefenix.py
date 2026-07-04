# extractors/animefenix.py
import concurrent.futures
import os
import re
import urllib.parse

from .base import BaseAnimeExtractor, _clean_text, _source_id, _split_source_id


class AnimeFenixExtractor(BaseAnimeExtractor):
    site_name = "animefenix"
    supports_dub = False
    _VALID_URL = r"https?://(?:www\.)?animefenix2\.tv/ver/(?P<anime_id>[a-zA-Z0-9_-]+)-(?P<ep_no>\d+)/?"

    base_url = "https://animefenix2.tv"

    def _series_url(self, title_or_id):
        source, identifier = _split_source_id(title_or_id)
        if source and source != self.site_name:
            raise ValueError(f"El identificador pertenece a {source}.")

        identifier = identifier or ""
        if identifier.startswith("http"):
            return identifier.rstrip("/")
        if re.fullmatch(r"[a-zA-Z0-9_-]+", identifier):
            return f"{self.base_url}/{identifier}"

        results = self.search(identifier)
        if not results:
            raise RuntimeError(f"AnimeFenix no encontró {identifier!r}.")

        return _split_source_id(results[0]["id"])[1].rstrip("/")

    def search(self, title, dub=False):
        if dub:
            return []
        query = urllib.parse.quote_plus(title)
        page = self._download_webpage(f"{self.base_url}/directorio/anime?q={query}")
        if not page:
            return []

        candidates = []
        seen = set()

        # Extracción elástica de las tarjetas de resultados
        links = re.findall(
            r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*?>([\s\S]*?)</a>',
            page,
            re.IGNORECASE,
        )

        for href, content in links:
            full_url = (
                self.base_url + href if href.startswith("/") else href
            )

            if not full_url.startswith(self.base_url) or any(
                x in full_url
                for x in [
                    "/ver/",
                    "/directorio",
                    "/login",
                    "/registro",
                    "/comentarios",
                    "/animes",
                ]
            ):
                continue

            slug = full_url.replace(self.base_url, "").strip("/")
            if not slug or "/" in slug or full_url in seen:
                continue

            seen.add(full_url)

            title_text = re.sub(r"<[^>]+>", "", content).strip()
            title_text = _clean_text(title_text)
            if not title_text or len(title_text) > 100:
                title_text = slug.replace("-", " ").title()

            candidates.append((full_url, title_text))

        limit = max(1, int(os.getenv("ANIMUX_SPANISH_SEARCH_LIMIT", "12")))
        candidates = candidates[:limit]

        def enrich(candidate):
            url, name = candidate
            episodes = self.list_episodes(_source_id(self.site_name, url))
            return {
                "id": _source_id(self.site_name, url),
                "title": name,
                "total_episodes": len(episodes),
                "extractor": self.site_name,
            }

        results = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(6, len(candidates) or 1)
        ) as executor:
            futures = [
                executor.submit(enrich, candidate) for candidate in candidates
            ]
            for future in futures:
                try:
                    result = future.result()
                    if result["total_episodes"]:
                        results.append(result)
                except Exception as exc:
                    self._log(
                        f"[animefenix][Aviso] No se pudo contar un resultado: {exc}"
                    )
        return results

    def list_episodes(self, title_or_id, dub=False):
        if dub:
            return []
        series_url = self._series_url(title_or_id)
        page = self._download_webpage(series_url)
        if not page:
            return []

        container_match = re.search(
            r'id=["\']episodes-container["\'][^>]*?>([\s\S]*?)</div>',
            page,
            re.IGNORECASE,
        )
        if not container_match:
            container_match = re.search(
                r'<div[^>]*?episodes-container[^>]*?>([\s\S]*?)</div>',
                page,
                re.IGNORECASE,
            )

        if not container_match:
            raise RuntimeError("No se encontraron episodios para AnimeFenix.")

        container_html = container_match.group(1)
        ep_matches = re.findall(
            r'<a\s+[^>]*?href=["\']([^"\']+)["\'][^>]*?>([\s\S]*?)<span[^>]*?class=["\']ep-title["\'][^>]*?>([^<]+)</span>',
            container_html,
            re.IGNORECASE,
        )

        episodes = []
        for href, _, text in ep_matches:
            text = text.strip()
            num_match = re.search(
                r"(?:Capítulo|Episode|Ep)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE
            )
            if num_match:
                episodes.append(num_match.group(1))
            else:
                href_num = re.search(r"-(\d+(?:\.\d+)?)$", href.strip("/"))
                if href_num:
                    episodes.append(href_num.group(1))

        return sorted(list(set(episodes)), key=float)

    def get_episode(self, title_or_id, episode, dub=False):
        if dub:
            raise RuntimeError("AnimeFenix no ofrece doblaje en este backend.")
        series_url = self._series_url(title_or_id)
        slug = series_url.rstrip("/").split("/")[-1]
        episode_url = f"{self.base_url}/ver/{slug}-{episode}"
        return self._stream_result(self.extract(episode_url))

    def extract(self, url, match=None):
        match = match or re.match(self._VALID_URL, url)
        if not match:
            raise ValueError("La URL proporcionada no es válida para AnimeFenix.")

        anime_id = match.group("anime_id")
        ep_no = match.group("ep_no")
        self._log(f"[animefenix] Analizando anime: {anime_id} (Episodio {ep_no})")

        html = self._download_webpage(url)
        if not html:
            raise RuntimeError("No se pudo obtener el HTML de la página del episodio.")

        # Helper local para desenrollar las redirecciones de animepelix (.redirect o .smart)
        def _unwrap_animepelix(target_url):
            if target_url.startswith("//"):
                target_url = "https:" + target_url
            if "animepelix.net" in target_url:
                try:
                    parsed = urllib.parse.urlparse(target_url)
                    params = urllib.parse.parse_qs(parsed.query)
                    if "id" in params:
                        return params["id"][0]
                    if "url" in params:
                        return params["url"][0]
                except Exception:
                    pass
            return target_url

        iframe_urls = []
        ironhentai_urls = []
        seen_urls = set()

        # 1. Recolección unificada (iframes estáticos + enlaces latentes embebidos en scripts JS)
        main_iframes = re.findall(
            r"<iframe[^>]+src=[\"\']([^\"\' ]+)[\"\']", html, flags=re.IGNORECASE
        )
        script_urls = re.findall(
            r"[\"\'](https?://(?:re\.animepelix\.net|re\.ironhentai\.com|www\.mp4upload\.com|voex\.sx|streamtape\.com)[^\"\' ]+)[\"\']",
            html,
            flags=re.IGNORECASE,
        )

        for raw_url in main_iframes + script_urls:
            cleaned_url = _unwrap_animepelix(raw_url.replace("\\/", "/"))
            if cleaned_url in seen_urls:
                continue
            seen_urls.add(cleaned_url)

            # Clasificación estratégica para mitigar el honeypot del regex base
            if "ironhentai.com" in cleaned_url:
                if cleaned_url not in ironhentai_urls:
                    ironhentai_urls.append(cleaned_url)
            else:
                if cleaned_url not in iframe_urls:
                    iframe_urls.append(cleaned_url)

        if not ironhentai_urls and not iframe_urls:
            raise RuntimeError("No se encontró el bloque de reproducción.")

        video_url = None
        chosen_iframe = None

        # 2. PRIORIDAD: Servidores IronHentai aislados
        if ironhentai_urls:
            self._log(
                f"[animefenix] Detectados {len(ironhentai_urls)} servidores de IronHentai. Evitando trampa de regex..."
            )
            for iron_url in ironhentai_urls:
                resolved = self._get_url_via_ytdlp(iron_url, referer=url)
                if resolved:
                    video_url = resolved
                    chosen_iframe = iron_url
                    self._log(
                        "[animefenix] ¡URL directa obtenida de IronHentai mediante yt-dlp!"
                    )
                    break

            if not video_url:
                self._log(
                    "[animefenix] Pasando URL de IronHentai directamente al formato de salida."
                )
                video_url = ironhentai_urls[0]
                chosen_iframe = url

        # 3. FALLBACK 1: Procesar concurrentemente los servidores tradicionales libres de trampas (Mp4Upload, Voex, etc.)
        if not video_url and iframe_urls:
            self._log(
                f"[animefenix] Iniciando resolución concurrente para otros {len(iframe_urls)} servidores..."
            )
            video_url, chosen_iframe = self._extract_video_from_iframes(
                iframe_urls, url
            )

        # 4. FALLBACK 2: Intentar yt-dlp sobre la URL principal de la página
        if not video_url:
            self._log("[animefenix] Intentando yt-dlp en la URL base...")
            video_url = self._get_url_via_ytdlp(url, referer=self.base_url)
            chosen_iframe = url

        if not video_url:
            raise RuntimeError(
                "Ninguno de los servidores disponibles devolvió un flujo de video válido."
            )

        return {
            "id": f"{anime_id}-{ep_no}",
            "title": f"{anime_id.replace('-', ' ').title()} - Episodio {ep_no}",
            "extractor": "animefenix",
            "formats": [
                {
                    "format_id": "animefenix-best",
                    "url": video_url,
                    "ext": "mp4",
                    "protocol": (
                        "m3u8_native" if ".m3u8" in video_url else "https"
                    ),
                    "http_headers": {
                        "User-Agent": self.user_agent,
                        "Referer": chosen_iframe,
                    },
                }
            ],
        }
