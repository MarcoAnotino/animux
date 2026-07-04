# extractors/tioanime.py
import concurrent.futures
import os
import re
import urllib.parse

from .base import BaseAnimeExtractor, _clean_text, _source_id, _split_source_id


class TioAnimeExtractor(BaseAnimeExtractor):
    site_name = "tioanime"
    supports_dub = False
    base_url = "https://tioanime.com"
    _VALID_URL = r"https?://(?:www\.)?tioanime\.com/ver/(?P<ep_id>[a-zA-Z0-9_-]+)-(?P<ep_no>\d+)/?"

    def _series_url(self, title_or_id):
        source, identifier = _split_source_id(title_or_id)
        if source and source != self.site_name:
            raise ValueError(f"El identificador pertenece a {source}.")

        identifier = identifier or ""
        if identifier.startswith("http"):
            return identifier.rstrip("/")
        if re.fullmatch(r"[a-zA-Z0-9_-]+", identifier):
            return f"{self.base_url}/anime/{identifier}"

        results = self.search(identifier)
        if not results:
            raise RuntimeError(f"TioAnime no encontró resultados para {identifier!r}.")

        return _split_source_id(results[0]["id"])[1].rstrip("/")

    def search(self, title, dub=False):
        if dub:
            return []
        # TioAnime procesa las búsquedas usando el parámetro 'q'
        url = f"{self.base_url}/directorio?q={urllib.parse.quote_plus(title)}"
        page = self._download_webpage(url)
        if not page:
            return []

        # Captura los enlaces de animes del directorio: /anime/nombre-del-anime
        slugs = re.findall(r'href=["\']/anime/([a-zA-Z0-9_-]+)["\']', page)

        candidates = []
        seen = set()
        for slug in slugs:
            if slug in seen:
                continue
            seen.add(slug)
            full_url = f"{self.base_url}/anime/{slug}"
            display_title = _clean_text(slug.replace("-", " ").title())
            candidates.append((full_url, display_title))

        limit = max(1, int(os.getenv("ANIMUX_SPANISH_SEARCH_LIMIT", "12")))
        candidates = candidates[:limit]

        def enrich(candidate):
            series_url, name = candidate
            episodes = self.list_episodes(
                _source_id(self.site_name, series_url), dub=dub
            )
            return {
                "id": _source_id(self.site_name, series_url),
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
                    if result and result["total_episodes"]:
                        results.append(result)
                except Exception as exc:
                    self._log(
                        f"[{self.site_name}][Aviso] No se pudo procesar resultado: {exc}"
                    )
        return results

    def list_episodes(self, title_or_id, dub=False):
        if dub:
            return []
        series_url = self._series_url(title_or_id)
        page = self._download_webpage(series_url)
        if not page:
            return []

        # Extrae los números de episodios basándose en la lista .episodes-list proporcionada
        # Ejemplo de ruta: /ver/ore-dake-haireru-kakushi-dungeon-12
        slug = series_url.rstrip("/").split("/")[-1]
        href_numbers = re.findall(
            rf'href=["\']/ver/{slug}-(\d+(?:\.\d+)?)/?["\']', page
        )
        if not href_numbers:
            # Fallback en caso de que la estructura varíe sutilmente o use rutas genéricas
            href_numbers = re.findall(
                r'href=["\']/ver/[a-zA-Z0-9_-]+-(\d+(?:\.\d+)?)/?["\']', page
            )

        if not href_numbers:
            return []

        # Convertir a set para limpiar duplicados y ordenar ascendentemente
        return sorted(list(set(href_numbers)), key=float)

    def get_episode(self, title_or_id, episode, dub=False):
        if dub:
            raise RuntimeError("TioAnime no ofrece doblaje en este backend.")
        series_url = self._series_url(title_or_id)
        slug = series_url.rstrip("/").split("/")[-1]
        episode_url = f"{self.base_url}/ver/{slug}-{episode}"
        return self._stream_result(
            self._extract_matched(episode_url, match=None, dub=dub)
        )

    def extract(self, url, match=None):
        match = match or re.match(self._VALID_URL, url)
        if not match:
            raise ValueError(f"La URL proporcionada no es válida para {self.site_name}.")
        return self._extract_matched(url, match, dub=False)

    def _iframe_urls_from_page(self, page, url):
        urls = []
        # Replicamos la lógica del JS: buscamos "videos = [...]" con DOTALL para capturar todo el bloque
        video_js_match = re.search(r'videos\s*=\s*(\[[\s\S]*?\]);', page)
        
        if video_js_match:
            try:
                # Limpiamos los escapes de barra invertida igual que en tu ejemplo JS
                json_str = video_js_match.group(1).replace("\\/", "/").replace('\\"', '"')
                import json
                raw_data = json.loads(json_str)
                
                # raw_data es una lista de listas: [["NombreServidor", "url_del_iframe"], ...]
                for entry in raw_data:
                    if isinstance(entry, list) and len(entry) >= 2:
                        server_url = entry[1]
                        if server_url and server_url not in urls:
                            urls.append(server_url)
            except Exception as e:
                self._log(f"[{self.site_name}] Error parseando JSON de videos: {e}")
        
        return urls

    def _extract_matched(self, url, match=None, dub=False):
        if not match:
            match = re.match(self._VALID_URL, url)
            if not match:
                raise ValueError("URL de episodio inválida.")

        ep_id = match.group("ep_id")
        ep_no = match.group("ep_no")

        page = self._download_webpage(url)
        if not page:
            raise RuntimeError(f"No se pudo descargar la página del episodio en {self.site_name}.")

        iframe_urls = self._iframe_urls_from_page(page, url)
        if not iframe_urls:
            raise RuntimeError(f"{self.site_name} no expuso ningún servidor válido para este episodio.")

        # Filtrado inteligente de servidores prioritarios vs inestables
        # Excluimos de la primera pasada servidores pesados o bloqueados por CORS si existen mejores opciones
        priority_iframes = [i for i in iframe_urls if not any(x in i.lower() for x in ["mp4upload", "yourupload"])]
        fallback_iframes = [i for i in iframe_urls if i not in priority_iframes]

        video_url = None
        chosen_iframe = None

        # 1. Extracción multihilo rápida utilizando el módulo base en servidores estables (Voe, Okru, Mega, Mixdrop)
        if priority_iframes:
            video_url, chosen_iframe = self._extract_video_from_iframes(priority_iframes, url)

        # 2. Fallback de emergencia vía yt-dlp sobre todos los servidores disponibles
        if not video_url:
            for iframe in priority_iframes + fallback_iframes:
                self._log(f"[{self.site_name}] Intentando resolución nativa yt-dlp en: {iframe}")
                resolved = self._get_url_via_ytdlp(iframe, referer=url)
                if resolved:
                    video_url = resolved
                    chosen_iframe = iframe
                    break

        if not video_url:
            raise RuntimeError(f"Ningún servidor de {self.site_name} pudo resolver un flujo reproducible.")

        return {
            "id": f"ver/{ep_id}-{ep_no}",
            "title": f"{ep_id.replace('-', ' ').title()} - Episodio {ep_no}",
            "extractor": self.site_name,
            "formats": [
                {
                    "format_id": f"{self.site_name}-best",
                    "url": video_url,
                    "ext": "mp4" if ".mp4" in video_url else "ts",
                    "protocol": "m3u8_native" if ".m3u8" in video_url else "https",
                    "http_headers": {
                        "User-Agent": self.user_agent,
                        "Referer": chosen_iframe,
                    },
                }
            ],
        }
