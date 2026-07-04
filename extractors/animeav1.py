# extractors/animeav1.py
import concurrent.futures
import os
import re
import urllib.parse

from .base import BaseAnimeExtractor, _clean_text, _source_id, _split_source_id


class AnimeAV1Extractor(BaseAnimeExtractor):
    site_name = "animeav1"
    supports_dub = True
    base_url = "https://animeav1.com"
    _VALID_URL = r"https?://(?:www\.)?animeav1\.com/media/(?P<series>[a-zA-Z0-9_-]+)/(?P<ep_no>\d+)/?"

    def _series_url(self, title_or_id):
        source, identifier = _split_source_id(title_or_id)
        if source and source != self.site_name:
            raise ValueError(f"El identificador pertenece a {source}.")

        identifier = identifier or ""
        if identifier.startswith("http"):
            return identifier.rstrip("/")
        if re.fullmatch(r"[a-zA-Z0-9_-]+", identifier):
            return f"{self.base_url}/media/{identifier}"

        results = self.search(identifier)
        if not results:
            raise RuntimeError(f"AnimeAV1 no encontró {identifier!r}.")

        return _split_source_id(results[0]["id"])[1].rstrip("/")

    def search(self, title, dub=False):
        url = f"{self.base_url}/catalogo?search={urllib.parse.quote_plus(title)}"
        page = self._download_webpage(url)
        if not page:
            return []

        # Extracción elástica basada en la lógica espejo del servicio JS
        slugs = re.findall(r"/media/([a-zA-Z0-9_-]+)(?!/\d+)", page)

        candidates = []
        seen = set()
        for slug in slugs:
            if slug in seen or slug in ["catalogo", "media"]:
                continue
            seen.add(slug)
            full_url = f"{self.base_url}/media/{slug}"
            display_title = _clean_text(slug.replace("-", " ").title())
            candidates.append((full_url, display_title))

        limit = max(1, int(os.getenv("ANIMUX_SPANISH_SEARCH_LIMIT", "12")))
        candidates = candidates[:limit]

        def enrich(candidate):
            series_url, name = candidate
            episodes = self.list_episodes(
                _source_id(self.site_name, series_url), dub=dub
            )
            if dub and not self._has_dub(series_url, episodes):
                return None
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
                        f"[animeav1][Aviso] No se pudo contar un resultado: {exc}"
                    )
        return results

    def _has_dub(self, series_url, episodes):
        if not episodes:
            return False
        episode_url = f"{series_url.rstrip('/')}/{episodes[0]}"
        page = self._download_webpage(episode_url)
        return bool(self._iframe_urls_from_page(page, episode_url, dub=True))

    def list_episodes(self, title_or_id, dub=False):
        series_url = self._series_url(title_or_id)
        page = self._download_webpage(series_url)
        if not page:
            return []

        # Captura precisa de rutas de episodios mapeando el contenedor svelte
        href_numbers = re.findall(
            r'href=["\']/media/[a-zA-Z0-9_-]+/(\d+(?:\.\d+)?)/?["\']', page
        )
        if not href_numbers:
            for article in re.findall(
                r'<article[^>]+class=["\'][^"\']*group/item[^"\']*["\'][^>]*>(.*?)</article>',
                page,
                re.IGNORECASE | re.DOTALL,
            ):
                match = re.search(
                    r'<span[^>]*>\s*([0-9]+(?:\.[0-9]+)?)\s*</span>', article
                )
                if match:
                    href_numbers.append(match.group(1))
        if not href_numbers:
            return []

        return sorted(list(set(href_numbers)), key=float)

    def get_episode(self, title_or_id, episode, dub=False):
        series_url = self._series_url(title_or_id)
        slug = series_url.rstrip("/").split("/")[-1]
        episode_url = f"{self.base_url}/media/{slug}/{episode}"
        return self._stream_result(
            self._extract_matched(episode_url, match=None, dub=dub)
        )

    def extract(self, url, match=None):
        match = match or re.match(self._VALID_URL, url)
        if not match:
            raise ValueError("La URL proporcionada no es válida para AnimeAV1.")
        return self._extract_matched(url, match, dub=False)

    def _iframe_urls_from_page(self, page, url, dub=False):
        embeds_position = page.find("embeds:")
        if embeds_position >= 0:
            section = page[embeds_position:]
            language = "DUB" if dub else "SUB"
            language_match = re.search(
                rf'["\']?{language}["\']?\s*:\s*\[(.*?)\](?:\s*,\s*["\']?[A-Z]+["\']?\s*:|\s*\}})',
                section,
                re.DOTALL | re.IGNORECASE,
            )
            if not language_match:
                return []
            values = re.findall(
                r'(?:url\s*:\s*|["\']url["\']\s*:\s*)["\']([^"\']+)["\']',
                language_match.group(1),
            )
            return [
                urllib.parse.urljoin(url, value.replace("\\/", "/"))
                for value in values
            ]

        # Mapeo elástico emulando VIDEO_URL_REGEX de tu archivo js de referencia
        patterns = [
            r"https?://(?:www\.)?pixeldrain\.com/(?:embed/)?[a-zA-Z0-9_-]+",
            r"https?://mega\.nz/embed/[a-zA-Z0-9_-]+#[a-zA-Z0-9_-]+",
            r"https?://(?:www\.)?mp4upload\.com/embed-[a-zA-Z0-9]+\.html",
            r"https?://player\.[a-zA-Z0-9_-]+\.[a-z]+/play/[a-zA-Z0-9]+",
            r"https?://[a-zA-Z0-9_-]*zilla[a-zA-Z0-9._/:-]+",
            r"https?://[a-zA-Z0-9_-]*uns\.bio/[a-zA-Z0-9_#-]+",
        ]

        urls = []
        for pattern in patterns:
            for m in re.findall(pattern, page, re.IGNORECASE):
                cleaned = (
                    m.replace("\\/", "/").replace('\\"', "").replace("\\'", "")
                )
                if cleaned not in urls:
                    urls.append(cleaned)
        return urls

    def _extract_matched(self, url, match=None, dub=False):
        if not match:
            match = re.match(self._VALID_URL, url)
            if not match:
                raise ValueError("URL inválida.")

        series_slug = match.group("series")
        ep_no = match.group("ep_no")

        page = self._download_webpage(url)
        if not page:
            raise RuntimeError("No se pudo obtener el episodio de AnimeAV1.")

        iframe_urls = self._iframe_urls_from_page(page, url, dub=dub)
        if not iframe_urls:
            raise RuntimeError("AnimeAV1 no devolvió servidores de video.")

        video_url = None
        chosen_iframe = None

        # Separamos los servidores por orden de calidad y estabilidad
        zilla_iframes = [i for i in iframe_urls if "zilla" in i.lower() or "player." in i.lower()]
        other_iframes = [i for i in iframe_urls if i not in zilla_iframes and "mp4upload" not in i.lower()]
        mp4upload_iframes = [i for i in iframe_urls if "mp4upload" in i.lower()]

        # 1. INTENTO PRIORITARIO: Zilla Networks (HLS)
        if zilla_iframes:
            for iframe in zilla_iframes:
                self._log(f"[animeav1] Intentando desencriptar HLS de Zilla: {iframe}")
                # Intentamos regex rápido primero
                zilla_html = self._download_webpage(iframe, referer=url)
                if zilla_html:
                    m3u8_match = re.search(
                        r'["\']?(?:file|src|source|url)["\']?\s*:\s*["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
                        zilla_html,
                        re.IGNORECASE
                    )
                    if m3u8_match:
                        video_url = m3u8_match.group(1).replace("\\/", "/")
                        chosen_iframe = iframe
                        break
                
                # Si el regex rápido de Zilla falla, forzamos yt-dlp INMEDIATAMENTE sobre Zilla
                self._log(f"[animeav1] Regex rápido falló en Zilla. Extrayendo nativamente con yt-dlp...")
                resolved = self._get_url_via_ytdlp(iframe, referer=url)
                if resolved:
                    video_url = resolved
                    chosen_iframe = iframe
                    break

        # 2. FALLBACK 1: Otros servidores estables (Mega, Pixeldrain, Uns.bio...)
        if not video_url and other_iframes:
            self._log("[animeav1] Pasando a servidores secundarios estables...")
            video_url, chosen_iframe = self._extract_video_from_iframes(other_iframes, url)
            if not video_url:
                for iframe in other_iframes:
                    resolved = self._get_url_via_ytdlp(iframe, referer=url)
                    if resolved:
                        video_url = resolved
                        chosen_iframe = iframe
                        break

        # 3. FALLBACK 2: MP4Upload (Último recurso si todo lo demás falla)
        if not video_url and mp4upload_iframes:
            self._log("[animeav1] Alerta: Usando MP4Upload como último recurso.")
            resolved = self._get_url_via_ytdlp(mp4upload_iframes[0], referer=url)
            if resolved:
                video_url = resolved
                chosen_iframe = mp4upload_iframes[0]

        if not video_url:
            raise RuntimeError("Ningún servidor de AnimeAV1 devolvió un stream de video válido.")

        return {
            "id": f"media/{series_slug}-{ep_no}",
            "title": f"{series_slug.replace('-', ' ').title()} - Episodio {ep_no}",
            "extractor": self.site_name,
            "formats": [
                {
                    "format_id": "animeav1-best",
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
