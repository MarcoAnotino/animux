import concurrent.futures
import os
import re
import urllib.parse

from .base import BaseAnimeExtractor, _clean_text, _source_id, _split_source_id

class JkanimeExtractor(BaseAnimeExtractor):
    site_name = "jkanime"
    supports_dub = False
    _VALID_URL = r'https?://(?:www\.)?jkanime\.net/(?P<anime_id>[a-zA-Z0-9_-]+)/(?P<ep_no>\d+)/?'

    base_url = "https://jkanime.net"

    def _series_url(self, title_or_id):
        source, identifier = _split_source_id(title_or_id)
        if source and source != self.site_name:
            raise ValueError(f"El identificador pertenece a {source}.")
        identifier = identifier or ""
        if identifier.startswith("http"):
            return identifier.rstrip("/") + "/"
        if re.fullmatch(r"[a-zA-Z0-9_-]+", identifier):
            return f"{self.base_url}/{identifier}/"
        results = self.search(identifier)
        if not results:
            raise RuntimeError(f"JKanime no encontró {identifier!r}.")
        return _split_source_id(results[0]["id"])[1]

    def search(self, title, dub=False):
        if dub:
            return []
        query = urllib.parse.quote_plus(title).replace("+", "%20")
        page = self._download_webpage(f"{self.base_url}/buscar/{query}/")
        if not page:
            return []

        candidates = []
        seen = set()
        anchor_pattern = re.compile(
            r'<a[^>]+href=["\'](?P<href>(?:https?://(?:www\.)?jkanime\.net)?/'
            r'(?P<slug>[a-zA-Z0-9_-]+)/)["\'][^>]*>(?P<body>.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        ignored = {"buscar", "directorio", "horario", "ultimos", "genero"}
        for match in anchor_pattern.finditer(page):
            slug = match.group("slug")
            body = match.group("body")
            # The first link in each card wraps the image and HTML comments;
            # the later h5 link contains the actual series title.
            if "<" in body:
                continue
            name = _clean_text(body)
            url = urllib.parse.urljoin(self.base_url, match.group("href"))
            if slug in ignored or not name or url in seen:
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
                    self._log(f"[jkanime][Aviso] No se pudo contar un resultado: {exc}")
        return results

    def list_episodes(self, title_or_id, dub=False):
        if dub:
            return []
        series_url = self._series_url(title_or_id)
        page = self._download_webpage(series_url)
        anime_match = re.search(r'data-anime=["\'](\d+)["\']', page)
        token_match = re.search(
            r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)',
            page,
            re.IGNORECASE,
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']csrf-token',
            page,
            re.IGNORECASE,
        )
        if not anime_match or not token_match:
            raise RuntimeError("JKanime no expuso el ID del anime o el token CSRF.")

        anime_id = anime_match.group(1)
        token = token_match.group(1)
        data = urllib.parse.urlencode({"_token": token}).encode()
        headers = {"X-Requested-With": "XMLHttpRequest"}

        first = self._request_text(
            f"{self.base_url}/ajax/episodes/{anime_id}/1",
            data=data,
            headers=headers,
            referer=series_url,
        )
        total_match = re.search(r'"total"\s*:\s*(\d+)', first)
        if not total_match:
            raise RuntimeError("JKanime no devolvió el total de episodios.")
        total = int(total_match.group(1))
        pages = max(1, (total + 15) // 16)
        payloads = [first]
        for page_number in range(2, pages + 1):
            payloads.append(self._request_text(
                f"{self.base_url}/ajax/episodes/{anime_id}/{page_number}",
                data=data,
                headers=headers,
                referer=series_url,
            ))
        numbers = {
            match.group(1)
            for payload in payloads
            for match in re.finditer(r'"number"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)', payload)
        }
        if not numbers and total:
            numbers = {str(number) for number in range(1, total + 1)}
        return sorted(numbers, key=float)

    def get_episode(self, title_or_id, episode, dub=False):
        if dub:
            raise RuntimeError("JKanime no ofrece doblaje en español en este backend.")
        series_url = self._series_url(title_or_id)
        episode_url = urllib.parse.urljoin(series_url, f"{episode}/")
        return self._stream_result(self.extract(episode_url))

    def extract(self, url, match=None):
        match = match or re.match(self._VALID_URL, url)
        if not match:
            raise ValueError("La URL proporcionada no es válida para JKanime.")

        anime_id = match.group('anime_id')
        ep_no = match.group('ep_no')
        self._log(f"[jkanime] Analizando anime: {anime_id} (Episodio {ep_no})")

        html = self._download_webpage(url)
        if not html:
            raise RuntimeError("No se pudo obtener el HTML de la página del episodio.")

        iframe_urls = []

        jk_players = re.findall(r'src=["\'](https://jkanime\.net/jkplayer/[^"\']+)["\']', html)
        iframe_urls.extend(jk_players)

        other_iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        for iframe in other_iframes:
            if iframe not in iframe_urls:
                if iframe.startswith('/'):
                    iframe = f"https://jkanime.net{iframe}"
                iframe_urls.append(iframe)

        if not iframe_urls:
            raise RuntimeError("No se encontraron servidores de video en este episodio.")

        self._log(f"[jkanime] Se encontraron {len(iframe_urls)} servidores. Iniciando búsqueda...")
        video_url, chosen_iframe = self._extract_video_from_iframes(iframe_urls, url)

        if not video_url:
            self._log("[jkanime] Intentando yt-dlp en URL base...")
            video_url = self._get_url_via_ytdlp(url, referer="https://jkanime.net")
            chosen_iframe = url

        if not video_url:
            raise RuntimeError("Ninguno de los servidores disponibles devolvió un flujo de video válido.")

        return {
            'id': f"{anime_id}-{ep_no}",
            'title': f"{anime_id.replace('-', ' ').title()} - Episodio {ep_no}",
            'extractor': 'jkanime',
            'formats': [
                {
                    'format_id': 'jkplayer-best',
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
