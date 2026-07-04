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


SUPPORTED_SOURCES = (
    "jkanime",
    "animeflv",
    "animeav1",
    "tioanime",
    "animefenix",
    "monoschino",
    "gogoanime",
)


def _source_id(source, value):
    return f"{source}:{value}"


def _split_source_id(value):
    if not isinstance(value, str) or ":" not in value:
        return None, value
    source, identifier = value.split(":", 1)
    if source not in SUPPORTED_SOURCES:
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
