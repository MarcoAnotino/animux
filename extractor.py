
import json
import os
import re
import sys
import urllib.request
import urllib.parse
from http.cookiejar import CookieJar
import subprocess
import shutil
import concurrent.futures
import html as html_module
from html.parser import HTMLParser


def _clean_text(value):
    """Return readable text from a small HTML fragment."""
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html_module.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _source_id(source, value):
    return f"{source}:{value}"


def _split_source_id(value):
    if not isinstance(value, str) or ":" not in value:
        return None, value
    source, identifier = value.split(":", 1)
    if source not in {"jkanime", "animeflv", "animeav1"}:
        return None, value
    return source, identifier


class _ArticleParser(HTMLParser):
    """Extract the first link and heading from every article element."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.article = None
        self.in_heading = False
        self.results = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article":
            if self.depth == 0:
                self.article = {"href": "", "title": []}
            self.depth += 1
        if not self.article:
            return
        if tag == "a" and not self.article["href"]:
            self.article["href"] = attrs.get("href", "")
        if tag in {"h2", "h3"}:
            self.in_heading = True

    def handle_endtag(self, tag):
        if tag in {"h2", "h3"}:
            self.in_heading = False
        if tag == "article" and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.article:
                title = _clean_text("".join(self.article["title"]))
                if self.article["href"] and title:
                    self.results.append((self.article["href"], title))
                self.article = None

    def handle_data(self, data):
        if self.article and self.in_heading:
            self.article["title"].append(data)

class BaseAnimeExtractor:
    site_name = "anime"
    supports_dub = False

    def __init__(self):
        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        self.opener.addheaders = [('User-Agent', self.user_agent)]

        self.request_timeout = float(os.getenv("ANI_CLI_JKANIME_EXTRACTOR_TIMEOUT", os.getenv("ANI_CLI_JKANIME_MAX_TIME", "5")))
        self.ytdlp_timeout = float(os.getenv("ANI_CLI_JKANIME_YTDLP_TIMEOUT", "8"))

    def _log(self, message):
        print(message, file=sys.stderr)

    def _download_webpage(self, url, referer=None):
        req = urllib.request.Request(url)
        if referer:
            req.add_header('Referer', referer)
        try:
            with self.opener.open(req, timeout=self.request_timeout) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception as e:
            self._log(f"[{self.site_name}][Aviso] No se pudo descargar {url}: {e}")
            return ""

    def _request_text(self, url, data=None, headers=None, referer=None):
        request_headers = dict(headers or {})
        request_headers.setdefault("User-Agent", self.user_agent)
        if referer:
            request_headers.setdefault("Referer", referer)
        request = urllib.request.Request(url, data=data, headers=request_headers)
        try:
            with self.opener.open(request, timeout=self.request_timeout) as response:
                return response.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            self._log(f"[{self.site_name}][Aviso] Falló la petición a {url}: {exc}")
            return ""

    def _article_results(self, page, base_url):
        parser = _ArticleParser()
        try:
            parser.feed(page)
        except Exception as exc:
            self._log(f"[{self.site_name}][Aviso] HTML de búsqueda incompleto: {exc}")
        return [
            (urllib.parse.urljoin(base_url, href), title)
            for href, title in parser.results
        ]

    def search(self, title, dub=False):
        raise NotImplementedError

    def list_episodes(self, title_or_id, dub=False):
        raise NotImplementedError

    def get_episode(self, title_or_id, episode, dub=False):
        raise NotImplementedError

    def _stream_result(self, extracted):
        formats = extracted.get("formats", []) if extracted else []
        if not formats or not formats[0].get("url"):
            raise RuntimeError("El extractor no devolvió un stream válido.")
        selected = formats[0]
        headers = selected.get("http_headers", {})
        return {
            "url": selected["url"],
            "referer": headers.get("Referer", ""),
            "extractor": extracted.get("extractor", self.site_name),
        }

    def _get_url_via_ytdlp(self, url, referer=None):
        if not shutil.which("yt-dlp"):
            return None

        # Cambiamos -g por -J para extraer el diccionario JSON completo
        cmd = ["yt-dlp", "-J", "--referer", referer or url, url]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.ytdlp_timeout)
            if result.returncode == 0 and result.stdout.strip():
                import json
                info = json.loads(result.stdout)

                # Prefer actual formats. Generic extraction can echo the embed
                # page in `url`, which is not a playable media stream.
                candidates = []
                candidates.extend(info.get("requested_downloads") or [])
                candidates.extend(reversed(info.get("formats") or []))
                candidates.append(info)
                for entry in info.get("entries") or []:
                    candidates.extend(entry.get("requested_downloads") or [])
                    candidates.extend(reversed(entry.get("formats") or []))
                    candidates.append(entry)
                for candidate in candidates:
                    media_url = candidate.get("url")
                    ext = str(candidate.get("ext") or "").lower()
                    if not media_url or media_url == url or "/embed" in media_url:
                        continue
                    if (
                        re.search(r"\.(?:m3u8|mp4|mkv|webm|ts)(?:[?#]|$)", media_url, re.I)
                        or ext in {"m3u8", "m3u8_native", "mp4", "mkv", "webm", "ts"}
                    ):
                        return media_url

        except subprocess.TimeoutExpired:
            self._log(f"[{self.site_name}][Aviso] yt-dlp (básico) tardó demasiado.")
        except Exception as e:
            self._log(f"[{self.site_name}][Aviso] yt-dlp falló: {e}")

        # Integración automática de tus métodos avanzados si existen en la clase hija
        if hasattr(self, '_get_url_via_ytdlp_impersonate'):
            self._log(f"[{self.site_name}] Escalando a yt-dlp con suplantación de Chrome...")
            return self._get_url_via_ytdlp_impersonate(url)

        return None

    def _process_single_iframe(self, iframe, base_url, index):
        """Tarea individual que ejecutará cada hilo."""
        self._log(f"[{self.site_name}] [Hilo {index}] Analizando: {iframe.split('?')[0]}")

        # 1. Intentar usar la API directa si la clase hija la tiene (ej. AnimeFLV q8y5z)
        if hasattr(self, '_fetch_stream_from_api') and 'q8y5z' in iframe:
            match = re.search(r'q8y5z\.com/b22/([a-z0-9]+)', iframe)
            if match:
                vid_url = self._fetch_stream_from_api(match.group(1), iframe, base_url)
                if vid_url:
                    self._log(f"[{self.site_name}] [Hilo {index}] ¡Extraído vía API interna!")
                    return vid_url, iframe

        # 2. Descargar el iframe para buscar Regex o flujos directos
        iframe_html = self._download_webpage(iframe, referer=base_url)
        if not iframe_html:
            return None, None

        if iframe_html.strip().startswith('#EXTM3U'):
            self._log(f"[{self.site_name}] [Hilo {index}] ¡Flujo m3u8 directo encontrado!")
            return iframe, iframe

        patterns = [
            r'(?:file|src|url)\s*:\s*["\']([^"\']+\.(?:m3u8|mp4)[^"\']*)["\']',
            r'<source[^>]+src=["\']([^"\']+)["\']',
            r'https?://[^"\' ]+\.(?:m3u8|mp4)[^"\' ]*'
        ]

        for pattern in patterns:
            m = re.search(pattern, iframe_html)
            if m:
                video_url = m.group(1) if m.groups() else m.group(0)
                self._log(f"[{self.site_name}] [Hilo {index}] ¡Extraído por Regex con éxito!")
                return video_url, iframe

        # 3. Fallback a yt-dlp (que ahora incluye impersonate automáticamente)
        self._log(f"[{self.site_name}] [Hilo {index}] Regex falló. Probando yt-dlp...")
        res_ytdl = self._get_url_via_ytdlp(iframe, referer=base_url)
        if res_ytdl:
            self._log(f"[{self.site_name}] [Hilo {index}] ¡Extraído mediante yt-dlp!")
            return res_ytdl, iframe

        return None, None

    def _extract_video_from_iframes(self, iframe_urls, base_url):
        """Bucle concurrente reutilizable por los extractores."""
        video_url = None
        chosen_iframe = None

        # max_workers define cuántos servidores probar a la vez (limitamos a 12 para no saturar la red)
        workers = min(len(iframe_urls), 12)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            # Mapear cada hilo a su resultado futuro
            future_to_iframe = {
                executor.submit(self._process_single_iframe, iframe, base_url, idx): idx
                for idx, iframe in enumerate(iframe_urls, start=1)
            }

            # as_completed produce los resultados a medida que los hilos terminan (el primero que acabe, gana)
            for future in concurrent.futures.as_completed(future_to_iframe):
                idx = future_to_iframe[future]
                try:
                    res_url, res_iframe = future.result()
                    if res_url:
                        video_url = res_url
                        chosen_iframe = res_iframe
                        self._log(f"[{self.site_name}] ¡Hilo {idx} fue el más rápido! Deteniendo los demás...")
                        # Al hacer break salimos del loop, y el context manager de ThreadPoolExecutor
                        # cancelará de inmediato cualquier tarea pendiente que no haya iniciado.
                        break
                except Exception as e:
                    self._log(f"[{self.site_name}] Error en el hilo {idx}: {e}")

        return video_url, chosen_iframe


class JkanimeExtractor(BaseAnimeExtractor):
    site_name = "jkanime"
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


class AnimeFLVExtractor(BaseAnimeExtractor):
    site_name = "animeflv"
    supports_dub = True
    _VALID_URL = (
        r'https?://(?:[a-z0-9]+\.)?animeflv\.(?:one|net)/ver/'
        r'(?P<slug>[a-zA-Z0-9_-]+)-(?P<ep_no>\d+)'
    )

    def __init__(self):
        super().__init__()
        self.base_url = os.getenv(
            "ANIMUX_ANIMEFLV_BASE", "https://www3.animeflv.net"
        ).rstrip("/")
        self.stream_base_url = os.getenv(
            "ANIMUX_ANIMEFLV_STREAM_BASE", "https://vww.animeflv.one"
        ).rstrip("/")

    def _series_url(self, title_or_id, dub=False):
        source, identifier = _split_source_id(title_or_id)
        if source and source != self.site_name:
            raise ValueError(f"El identificador pertenece a {source}.")
        identifier = identifier or ""
        if identifier.startswith("http"):
            return identifier.rstrip("/")
        if identifier.startswith("/anime/"):
            return urllib.parse.urljoin(self.base_url, identifier)
        if re.fullmatch(r"[a-zA-Z0-9_-]+", identifier):
            return f"{self.base_url}/anime/{identifier}"
        results = self.search(identifier, dub=dub)
        if not results:
            raise RuntimeError(f"AnimeFLV no encontró {identifier!r}.")
        return _split_source_id(results[0]["id"])[1]

    @staticmethod
    def _looks_dubbed(title):
        normalized = title.lower()
        return any(word in normalized for word in (
            "doblaje", "latino", "castellano", "español", "espanol"
        ))

    def search(self, title, dub=False):
        queries = [title]
        if dub and not self._looks_dubbed(title):
            queries.insert(0, f"{title} latino")

        candidates = []
        seen = set()
        for query in queries:
            url = f"{self.base_url}/browse?q={urllib.parse.quote_plus(query)}"
            page = self._download_webpage(url)
            for series_url, name in self._article_results(page, self.base_url):
                if "/anime/" not in series_url or series_url in seen:
                    continue
                if dub and not self._looks_dubbed(name):
                    continue
                if not dub and self._looks_dubbed(name):
                    continue
                seen.add(series_url)
                candidates.append((series_url, name))

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
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(candidates) or 1)) as executor:
            futures = [executor.submit(enrich, candidate) for candidate in candidates]
            for future in futures:
                try:
                    result = future.result()
                    if result["total_episodes"]:
                        results.append(result)
                except Exception as exc:
                    self._log(f"[animeflv][Aviso] No se pudo contar un resultado: {exc}")
        return results

    def list_episodes(self, title_or_id, dub=False):
        series_url = self._series_url(title_or_id, dub=dub)
        page = self._download_webpage(series_url)
        match = re.search(r"var\s+episodes\s*=\s*(\[.*?\])\s*;", page, re.DOTALL)
        if not match:
            raise RuntimeError("AnimeFLV no publicó la lista de episodios.")
        numbers = re.findall(
            r"\[\s*([0-9]+(?:\.[0-9]+)?)\s*,", match.group(1)
        )
        if not numbers:
            raise RuntimeError("AnimeFLV devolvió una lista de episodios vacía.")
        return sorted(set(numbers), key=float)

    def get_episode(self, title_or_id, episode, dub=False):
        series_url = self._series_url(title_or_id, dub=dub)
        slug = series_url.rstrip("/").rsplit("/", 1)[-1]
        episode_url = f"{self.base_url}/ver/{slug}-{episode}"
        match = re.match(self._VALID_URL, episode_url)
        if not match:
            raise RuntimeError("No se pudo construir la URL de AnimeFLV.")
        try:
            return self._stream_result(
                self._extract_matched(episode_url, match, dub=dub)
            )
        except Exception as official_error:
            # animeflv.net currently exposes metadata reliably but may return an
            # empty `videos` array. Keep the already-supported .one player as
            # the source-level fallback before moving to a different provider.
            fallback_url = f"{self.stream_base_url}/ver/{slug}-{episode}"
            fallback_match = re.match(self._VALID_URL, fallback_url)
            self._log(
                f"[animeflv][Aviso] Servidor oficial sin stream: {official_error}. "
                "Probando animeflv.one..."
            )
            if not fallback_match:
                raise official_error
            return self._stream_result(
                self._extract_matched(fallback_url, fallback_match, dub=dub)
            )

    def extract(self, url, match=None):
        match = match or re.match(self._VALID_URL, url)
        if not match:
            raise ValueError("La URL proporcionada no es válida para AnimeFLV.")

        return self._extract_matched(url, match, dub=False)

    def _extract_matched(self, url, match, dub=False):

        slug = match.group("slug")
        ep_no = match.group("ep_no")
        self._log(f"[{self.site_name}] {slug} (Ep {ep_no})")

        if "animeflv.net" in urllib.parse.urlparse(url).netloc:
            iframe_urls = self._get_iframes_from_official(url, dub=dub)
        else:
            # Compatibility with the animeflv.one backend used by animux.
            iframe_urls = self._get_iframes_from_ajax(url)
        if not iframe_urls:
            raise RuntimeError("No se pudieron obtener los iframes del episodio.")

        # Usar la lógica genérica para extraer el stream de los iframes
        video_url, chosen_iframe = self._extract_video_from_iframes(iframe_urls, url)
        if video_url:
            return self._build_result_dict(slug, ep_no, video_url, chosen_iframe)

        # Fallback con yt‑dlp
        self._log("[animeflv] Fallback con yt‑dlp sobre la URL del episodio...")
        video_url = self._get_url_via_ytdlp(url, referer=url)
        if video_url:
            return self._build_result_dict(slug, ep_no, video_url, url)

        raise RuntimeError("No se pudo extraer el stream de ningún iframe.")

    def _get_iframes_from_official(self, episode_url, dub=False):
        page = self._download_webpage(episode_url)
        if not page:
            return []

        language_keys = ("DUB", "LAT", "ESP", "CAST") if dub else ("SUB",)
        iframes = []
        videos_match = re.search(
            r"var\s+videos\s*=\s*(\{.*?\})\s*;", page, re.DOTALL
        )
        if videos_match:
            try:
                videos = json.loads(videos_match.group(1))
                for key in language_keys:
                    for server in videos.get(key, []) or []:
                        value = server.get("code") or server.get("url")
                        if value:
                            iframes.append(value)
            except (TypeError, ValueError) as exc:
                self._log(f"[animeflv][Aviso] No se pudo leer var videos: {exc}")

        if not iframes:
            # Keep a tolerant fallback for minor JavaScript formatting changes.
            for key in language_keys:
                section = re.search(
                    rf'["\']?{key}["\']?\s*:\s*\[(.*?)\](?:\s*,|\s*\}})',
                    page,
                    re.DOTALL | re.IGNORECASE,
                )
                if section:
                    iframes.extend(re.findall(
                        r'["\'](?:code|url)["\']\s*:\s*["\']([^"\']+)',
                        section.group(1),
                    ))

        normalized = []
        for value in iframes:
            value = html_module.unescape(value.replace("\\/", "/"))
            iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)', value)
            if iframe_match:
                value = iframe_match.group(1)
            value = urllib.parse.urljoin(episode_url, value)
            if value.startswith("http") and value not in normalized:
                normalized.append(value)
        self._log(f"[animeflv] Encontrados {len(normalized)} servidores oficiales.")
        return normalized

    # ------------------------------------------------------------------
    def _fetch_stream_from_api(self, video_id, iframe_url, episode_url):
        """
        Llama a la API de q8y5z que el reproductor usa internamente.
        """
        api_url = f"https://q8y5z.com/api/videos/{video_id}/embed/playback"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Referer': iframe_url,
            'Origin': 'https://q8y5z.com',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
        }
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with self.opener.open(req, timeout=self.request_timeout) as resp:
                data = resp.read().decode('utf-8')
                # a veces la respuesta es JSON, a veces es la URL directamente
                if data.startswith('https://') and '.m3u8' in data:
                    return data.strip()
                try:
                    import json
                    j = json.loads(data)
                    for key in ('url', 'file', 'src', 'hls', 'video'):
                        if key in j and isinstance(j[key], str) and '.m3u8' in j[key]:
                            return j[key]
                    # buscar en cualquier campo
                    for val in j.values():
                        if isinstance(val, str) and '.m3u8' in val:
                            return val
                except:
                    pass
        except Exception as e:
            self._log(f"[{self.site_name}] Error API playback: {e}")
        return None

    def _get_iframes_from_ajax(self, episode_url):
        html = self._download_webpage(episode_url)
        if not html:
            return []

        # Obtener la URL base desde la etiqueta <base>
        base_match = re.search(r'<base\s+href="([^"]+)"', html)
        base_url = base_match.group(1) if base_match else episode_url

        # Extraer el data-encrypt
        encrypt_match = re.search(r'data-encrypt="([a-fA-F0-9]+)"', html)
        if not encrypt_match:
            self._log("[animeflv] No se encontró data-encrypt en la página.")
            return []
        encrypt_val = encrypt_match.group(1)

        # Construir la URL de la petición AJAX usando la base correcta
        flv_url = urllib.parse.urljoin(base_url, "./flv")
        post_data = urllib.parse.urlencode({
            'acc': 'opt',
            'i': encrypt_val
        }).encode()

        req = urllib.request.Request(flv_url, data=post_data)
        req.add_header('User-Agent', self.user_agent)
        req.add_header('Referer', episode_url)
        req.add_header('X-Requested-With', 'XMLHttpRequest')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8')
        try:
            with self.opener.open(req, timeout=self.request_timeout) as resp:
                ajax_html = resp.read().decode('utf-8', errors='ignore')
        except Exception as e:
            self._log(f"[animeflv] Error en petición AJAX a {flv_url}: {e}")
            return []

        # Parsear las URLs de los iframes (atributo encrypt en hex)
        iframe_urls = []
        for m in re.finditer(r'encrypt="([a-fA-F0-9]+)"', ajax_html):
            hex_src = m.group(1)
            try:
                iframe_src = bytes.fromhex(hex_src).decode('utf-8')
                if not iframe_src.startswith('http'):
                    iframe_src = urllib.parse.urljoin(base_url, iframe_src)
                if iframe_src not in iframe_urls:
                    iframe_urls.append(iframe_src)
            except Exception:
                pass

        self._log(f"[animeflv] Encontrados {len(iframe_urls)} iframes.")
        return iframe_urls

    def _build_result_dict(self, slug, ep_no, video_url, chosen_iframe):
        return {
            'id': f"{slug}-{ep_no}",
            'title': f"{slug.replace('-', ' ').title()} - Episodio {ep_no}",
            'extractor': self.site_name,
            'formats': [{
                'format_id': 'animeflv-best',
                'url': video_url,
                'ext': 'mp4',
                'protocol': 'm3u8_native' if '.m3u8' in video_url else 'https',
                'http_headers': {
                    'User-Agent': self.user_agent,
                    'Referer': chosen_iframe,
                },
            }],
        }

    def _download_webpage_premium(self, url):
        """Descarga imitando exactamente un navegador Safari real."""
        if shutil.which("curl"):
            # Replicar todos los encabezados que Safari envía
            cmd = [
                "curl", "-s", "-L", "--max-time", "12",
                "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
                "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "-H", "Accept-Language: es-ES,es;q=0.9",
                "-H", "Sec-Fetch-Dest: document",
                "-H", "Sec-Fetch-Mode: navigate",
                "-H", "Sec-Fetch-Site: none",
                "-H", "Upgrade-Insecure-Requests: 1",
                url
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    return result.stdout
            except Exception:
                pass
        # Fallback con urllib
        return self._download_webpage(url)

    def _get_url_via_ytdlp_impersonate(self, url):
        """Usa yt-dlp con la opción --impersonate para emular Chrome sin cookies."""
        if not shutil.which("yt-dlp"):
            return None
        cmd = [
            "yt-dlp", "-g",
            "--impersonate", "chrome",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "--referer", url,
            "--no-warnings",
            url
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=self.ytdlp_timeout)
            if res.returncode == 0 and res.stdout.strip():
                lines = [l for l in res.stdout.strip().split('\n') if l.startswith('http')]
                for line in lines:
                    if line != url and "/embed" not in line:
                        return line
        except Exception:
            pass
        return None

    def _get_url_via_ytdlp_advanced(self, url, referer):
        """Usa las cookies reales de Safari/Chrome del usuario sin preguntar."""
        if not shutil.which("yt-dlp"):
            return None
        # Intenta con Safari (macOS) y Chrome (Windows/macOS)
        for browser in ["safari", "chrome"]:
            cmd = [
                "yt-dlp", "-g",
                "--cookies-from-browser", browser,
                "--user-agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "--referer", referer,
                "--no-warnings",
                url
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=self.ytdlp_timeout)
                if res.returncode == 0 and res.stdout.strip():
                    lines = [l for l in res.stdout.strip().split('\n') if l.startswith('http')]
                    if lines:
                        return lines[0]
            except Exception:
                continue
        return None

class AnimeAV1Extractor(BaseAnimeExtractor):
    site_name = "animeav1"
    supports_dub = True
    base_url = "https://animeav1.com"
    _VALID_URL = (
        r'https?://(?:www\.)?animeav1\.com/(?P<series>.+)/(?P<ep_no>\d+)/?'
    )

    def _series_url(self, title_or_id):
        source, identifier = _split_source_id(title_or_id)
        if source and source != self.site_name:
            raise ValueError(f"El identificador pertenece a {source}.")
        identifier = identifier or ""
        if identifier.startswith("http"):
            return identifier.rstrip("/")
        if identifier.startswith("/"):
            return urllib.parse.urljoin(self.base_url, identifier).rstrip("/")
        results = self.search(identifier)
        if not results:
            raise RuntimeError(f"AnimeAV1 no encontró {identifier!r}.")
        return _split_source_id(results[0]["id"])[1]

    def search(self, title, dub=False):
        url = f"{self.base_url}/catalogo?search={urllib.parse.quote_plus(title)}"
        page = self._download_webpage(url)
        candidates = []
        seen = set()
        for series_url, name in self._article_results(page, self.base_url):
            if series_url in seen:
                continue
            seen.add(series_url)
            candidates.append((series_url.rstrip("/"), name))

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
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(candidates) or 1)) as executor:
            futures = [executor.submit(enrich, candidate) for candidate in candidates]
            for future in futures:
                try:
                    result = future.result()
                    if result and result["total_episodes"]:
                        results.append(result)
                except Exception as exc:
                    self._log(f"[animeav1][Aviso] No se pudo contar un resultado: {exc}")
        return results

    def list_episodes(self, title_or_id, dub=False):
        page = self._download_webpage(self._series_url(title_or_id))
        numbers = []
        for article in re.findall(
            r'<article[^>]+class=["\'][^"\']*group/item[^"\']*["\'][^>]*>(.*?)</article>',
            page,
            re.IGNORECASE | re.DOTALL,
        ):
            match = re.search(r'<span[^>]*>\s*([0-9]+(?:\.[0-9]+)?)\s*</span>', article)
            if match:
                numbers.append(match.group(1))
        if not numbers:
            # The episode number is also present at the end of episode links.
            numbers = re.findall(
                r'href=["\'][^"\']+/([0-9]+(?:\.[0-9]+)?)/?["\']', page
            )
        if not numbers:
            raise RuntimeError("AnimeAV1 no publicó la lista de episodios.")
        return sorted(set(numbers), key=float)

    def get_episode(self, title_or_id, episode, dub=False):
        episode_url = f"{self._series_url(title_or_id)}/{episode}"
        match = re.match(self._VALID_URL, episode_url)
        if not match:
            raise RuntimeError("No se pudo construir la URL de AnimeAV1.")
        return self._stream_result(
            self._extract_matched(episode_url, match, dub=dub)
        )

    def extract(self, url, match=None):
        match = match or re.match(self._VALID_URL, url)
        if not match:
            raise ValueError("La URL proporcionada no es válida para AnimeAV1.")
        return self._extract_matched(url, match, dub=False)

    def _iframe_urls_from_page(self, page, url, dub=False):
        embeds_position = page.find("embeds:{")
        section = page[embeds_position:] if embeds_position >= 0 else page
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

    def _has_dub(self, series_url, episodes):
        if not episodes:
            return False
        episode_url = f"{series_url.rstrip('/')}/{episodes[0]}"
        page = self._download_webpage(episode_url)
        return bool(self._iframe_urls_from_page(page, episode_url, dub=True))

    def _extract_matched(self, url, match, dub=False):
        page = self._download_webpage(url)
        if not page:
            raise RuntimeError("No se pudo obtener el episodio de AnimeAV1.")

        iframe_urls = self._iframe_urls_from_page(page, url, dub=dub)
        if not iframe_urls:
            language = "DUB" if dub else "SUB"
            raise RuntimeError(f"AnimeAV1 no devolvió servidores {language}.")

        video_url, chosen_iframe = self._extract_video_from_iframes(iframe_urls, url)
        if not video_url:
            video_url = self._get_url_via_ytdlp(iframe_urls[0], referer=url)
            chosen_iframe = iframe_urls[0]
        if not video_url:
            raise RuntimeError("Ningún servidor de AnimeAV1 devolvió un stream.")
        return {
            "id": f"{match.group('series')}-{match.group('ep_no')}",
            "title": f"{match.group('series').rsplit('/', 1)[-1]} - Episodio {match.group('ep_no')}",
            "extractor": self.site_name,
            "formats": [{
                "format_id": "animeav1-best",
                "url": video_url,
                "ext": "mp4",
                "protocol": "m3u8_native" if ".m3u8" in video_url else "https",
                "http_headers": {
                    "User-Agent": self.user_agent,
                    "Referer": chosen_iframe,
                },
            }],
        }


EXTRACTOR_CLASSES = (
    JkanimeExtractor,
    AnimeFLVExtractor,
    AnimeAV1Extractor,
)


class AnimeExtractor:
    """Search Spanish sources and resolve streams with ordered fallback."""

    extractor_classes = EXTRACTOR_CLASSES

    def __init__(self, extractor_classes=None):
        classes = (
            self.extractor_classes
            if extractor_classes is None
            else extractor_classes
        )
        self._extractors = [extractor_class() for extractor_class in classes]

    def extract(self, url):
        for extractor in self._extractors:
            match = re.match(extractor._VALID_URL, url)
            if match:
                return extractor.extract(url, match)
        raise ValueError(f"Ningún extractor interno soporta la URL: {url}")

    def _ordered_extractors(self, dub=False):
        if dub:
            return [
                extractor for extractor in self._extractors
                if getattr(extractor, "supports_dub", False)
            ]
        return list(self._extractors)

    def search(self, title, dub=False):
        source_order = (
            ("animeflv", "animeav1", "jkanime")
            if dub
            else ("jkanime", "animeflv", "animeav1")
        )
        extractors_by_source = {
            extractor.site_name: extractor
            for extractor in self._extractors
        }
        ordered = [
            extractors_by_source[source]
            for source in source_order
            if source in extractors_by_source
        ]
        ordered.extend(
            extractor
            for extractor in self._extractors
            if extractor not in ordered
        )

        for extractor in ordered:
            try:
                results = extractor.search(title, dub=dub)
            except Exception as exc:
                log = getattr(extractor, "_log", None)
                if callable(log):
                    log(f"[{extractor.site_name}][Aviso] Búsqueda fallida: {exc}")
                continue
            if results:
                return results
        return []

    def list_episodes(self, title_or_id, dub=False):
        source, _ = _split_source_id(title_or_id)
        ordered = self._ordered_extractors(dub=dub)
        if source:
            ordered = sorted(
                ordered,
                key=lambda extractor: extractor.site_name != source,
            )
        errors = []
        for extractor in ordered:
            if source and extractor.site_name != source:
                continue
            try:
                episodes = extractor.list_episodes(title_or_id, dub=dub)
                if episodes:
                    return episodes
            except Exception as exc:
                errors.append(f"{extractor.site_name}: {exc}")
        if not source:
            for result in self.search(title_or_id, dub=dub):
                try:
                    extractor = next(
                        item for item in ordered
                        if item.site_name == result["extractor"]
                    )
                    episodes = extractor.list_episodes(result["id"], dub=dub)
                    if episodes:
                        return episodes
                except Exception as exc:
                    errors.append(f"{result.get('extractor')}: {exc}")
        raise RuntimeError(
            "No se pudo obtener la lista de episodios. " + "; ".join(errors)
        )

    def get_episode(self, title_or_id, episode, dub=False, title=None):
        source, identifier = _split_source_id(title_or_id)
        ordered = self._ordered_extractors(dub=dub)
        errors = []

        if source:
            selected = next(
                (item for item in ordered if item.site_name == source), None
            )
            if selected:
                try:
                    return selected.get_episode(title_or_id, episode, dub=dub)
                except Exception as exc:
                    errors.append(f"{source}: {exc}")

        fallback_title = title
        if not fallback_title and not source:
            fallback_title = identifier
        if not fallback_title and source:
            fallback_title = urllib.parse.unquote(identifier.rstrip("/").rsplit("/", 1)[-1])
            fallback_title = fallback_title.replace("-", " ")

        for extractor in ordered:
            if source and extractor.site_name == source:
                continue
            try:
                matches = extractor.search(fallback_title, dub=dub)
                if not matches:
                    raise RuntimeError("sin coincidencias")
                return extractor.get_episode(
                    matches[0]["id"], episode, dub=dub
                )
            except Exception as exc:
                errors.append(f"{extractor.site_name}: {exc}")

        raise RuntimeError(
            "Ninguna fuente devolvió el episodio. " + "; ".join(errors)
        )
