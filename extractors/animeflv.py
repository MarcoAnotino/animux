import concurrent.futures
import html as html_module
import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request

from .base import BaseAnimeExtractor, _source_id, _split_source_id

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
