# extractors/gogoanime.py
import concurrent.futures
import os
import re
import urllib.parse

from .base import BaseAnimeExtractor, _clean_text, _source_id, _split_source_id


class GogoanimeExtractor(BaseAnimeExtractor):
    site_name = "gogoanime"
    supports_dub = True
    _VALID_URL = r"https?://(?:www\.)?gogoanime\.by/(?P<anime_id>[a-zA-Z0-9_-]+)-episode-(?P<ep_no>\d+)/?"

    base_url = "https://gogoanime.by"

    def _series_url(self, title_or_id):
        source, identifier = _split_source_id(title_or_id)
        if source and source != self.site_name:
            raise ValueError(f"El identificador pertenece a {source}.")

        identifier = identifier or ""
        if identifier.startswith("http"):
            return identifier.rstrip("/")
        if "/series/" in identifier:
            slug = identifier.split("/series/")[-1].strip("/")
            return f"{self.base_url}/series/{slug}"
        if re.fullmatch(r"[a-zA-Z0-9_-]+", identifier):
            return f"{self.base_url}/series/{identifier}"

        results = self.search(identifier)
        if not results:
            raise RuntimeError(f"Gogoanime no encontró {identifier!r}.")

        return _split_source_id(results[0]["id"])[1].rstrip("/")

    def search(self, title, dub=False):
        query = urllib.parse.quote_plus(title)
        page = self._download_webpage(f"{self.base_url}/?s={query}")
        if not page:
            return []

        items_match = re.search(
            r'<div\s+class=["\']items["\']>([\s\S]*?)</div>',
            page,
            re.IGNORECASE,
        )
        search_html = items_match.group(1) if items_match else page

        candidates = []
        seen = set()

        for match in re.finditer(
            r'<a\s+(?P<attrs>[^>]*href=["\'][^"\']*/series/[^"\']+["\'][^>]*)>'
            r'(?P<content>[\s\S]*?)</a>',
            search_html,
            re.IGNORECASE,
        ):
            attrs = match.group("attrs")
            href_match = re.search(r'href=["\']([^"\']+)["\']', attrs, re.I)
            if not href_match:
                continue
            href = href_match.group(1)
            title_match = re.search(r'title=["\']([^"\']+)["\']', attrs, re.I)
            title_text = _clean_text(
                title_match.group(1) if title_match else match.group("content")
            )
            full_url = (
                self.base_url + href if not href.startswith("http") else href
            )

            if full_url in seen or not title_text:
                continue
            seen.add(full_url)
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
                        f"[gogoanime][Aviso] No se pudo contar un resultado: {exc}"
                    )
        return results

    def list_episodes(self, title_or_id, dub=False):
        series_url = self._series_url(title_or_id)
        page = self._download_webpage(series_url)
        if not page:
            return []

        data_numbers = re.findall(
            r'data-episode-number=["\']([0-9]+(?:\.[0-9]+)?)["\']', page, re.I
        )
        if data_numbers:
            return sorted(set(data_numbers), key=float)

        ep_list_match = re.search(
            r'<div\s+class=["\']episode-list["\']>([\s\S]*?)</div>',
            page,
            re.IGNORECASE,
        )
        if not ep_list_match:
            raise RuntimeError("No se encontraron episodios para Gogoanime.")

        ep_html = ep_list_match.group(1)
        links_text = re.findall(
            r'<a\s+href=["\'][^"\']+["\'][^>]*>([\s\S]*?)</a>',
            ep_html,
            re.IGNORECASE,
        )

        episodes = []
        for text in links_text:
            text = re.sub(r"<[^>]+>", "", text).strip()
            match = re.search(
                r"(?:Episode|Episodio)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE
            )
            if match:
                episodes.append(match.group(1))

        if not episodes:
            raise RuntimeError("No se encontraron episodios para Gogoanime.")
        return sorted(list(set(episodes)), key=float)

    def get_episode(self, title_or_id, episode, dub=False):
        series_url = self._series_url(title_or_id)
        slug = series_url.rstrip("/").split("/")[-1]
        page = self._download_webpage(series_url)
        episode_match = re.search(
            rf'href=["\']([^"\']*-episode-{re.escape(str(episode))}(?:-[^"\']*)?/?)["\']'
            rf'[^>]*>\s*Episode\s+{re.escape(str(episode))}\s*</a>',
            page,
            re.IGNORECASE,
        )
        episode_url = (
            urllib.parse.urljoin(series_url, episode_match.group(1))
            if episode_match
            else f"{self.base_url}/{slug}-episode-{episode}"
        )
        return self._stream_result(self.extract(episode_url))

    def extract(self, url, match=None):
        match = match or re.match(self._VALID_URL, url)
        if not match:
            raise ValueError("La URL proporcionada no es válida para Gogoanime.")

        anime_id = match.group("anime_id")
        ep_no = match.group("ep_no")
        self._log(f"[gogoanime] Analizando anime: {anime_id} (Episodio {ep_no})")

        html = self._download_webpage(url)
        if not html:
            raise RuntimeError("No se pudo obtener el HTML de la página del episodio.")

        if not re.search(r'class=["\']?servers["\']?', html, re.IGNORECASE):
            raise RuntimeError("No se encontró el bloque de servidores")

        post_id = ""
        script_match = re.search(
            r'(?:defaultPostId|postId)\s*=\s*["\'](\d+)["\']', html
        )
        if script_match:
            post_id = script_match.group(1)

        # Extracción elástica de contenedores de servidor tipo player-link
        li_matches = re.findall(
            r"<li\s+([^>]*?player-type-link[^>]*?)>([\s\S]*?)</li>",
            html,
            re.IGNORECASE,
        )

        iframe_urls = []
        seen_iframes = set()

        for attrs_str, _ in li_matches:
            def get_data_attr(attr_name):
                m = re.search(
                    r"data-"
                    + re.escape(attr_name)
                    + r"\s*=\s*[\"']([^\"']*)[\"']",
                    attrs_str,
                    re.IGNORECASE,
                )
                return m.group(1) if m else ""

            server_type = get_data_attr("type")
            if not server_type:
                continue

            iframe_url = ""
            if server_type in ["embed", "kiwi"]:
                plain_url = get_data_attr("plain-url")
                if plain_url:
                    iframe_url = plain_url
            else:
                enc1 = get_data_attr("encrypted-url1")
                enc2 = get_data_attr("encrypted-url2")
                enc3 = get_data_attr("encrypted-url3")
                ref = get_data_attr("ref") or "gogoanime.by"

                params = {
                    server_type: enc1,
                    "feature_image": "",
                    "user_agent": self.user_agent,
                    "ref": ref,
                }
                if enc2:
                    params["url2"] = enc2
                if enc3:
                    params["url3"] = enc3
                if post_id:
                    params["postId"] = post_id

                query_string = urllib.parse.urlencode(params)
                iframe_url = f"https://9animetv.be/wp-content/plugins/video-player/includes/player/player.php?{query_string}"

            if iframe_url and iframe_url not in seen_iframes:
                seen_iframes.add(iframe_url)
                iframe_urls.append(iframe_url)

        if not iframe_urls:
            raise RuntimeError(
                "No se encontraron servidores de video utilizables en este episodio."
            )

        self._log(
            f"[gogoanime] Se encontraron {len(iframe_urls)} servidores procesables. Iniciando resolución concurrente..."
        )
        video_url, chosen_iframe = self._extract_video_from_iframes(
            iframe_urls, url
        )

        # Fallback 1: Si falla la extracción de los iframes, delegar la URL base a yt-dlp
        if not video_url:
            self._log("[gogoanime] Intentando yt-dlp en la URL base...")
            video_url = self._get_url_via_ytdlp(url, referer=self.base_url)
            chosen_iframe = url

        # Fallback 2: Si todo falla pero computamos iframes, pasar el primero de manera directa para el reproductor
        if not video_url and iframe_urls:
            self._log(
                "[gogoanime] Pasando primer iframe construido por fallback directo de seguridad."
            )
            video_url = iframe_urls[0]
            chosen_iframe = url

        if not video_url:
            raise RuntimeError(
                "Ninguno de los servidores disponibles devolvió un flujo de video válido."
            )

        return {
            "id": f"{anime_id}-{ep_no}",
            "title": f"{anime_id.replace('-', ' ').title()} - Episodio {ep_no}",
            "extractor": "gogoanime",
            "formats": [
                {
                    "format_id": "gogoanime-best",
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
