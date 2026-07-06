# Changelog

## [Unreleased] - animux

Upstream base: pystardust/ani-cli

### Added
- **Personal anime library** — Watching, Watch later, Completed, Favorites,
  Dropped, and All anime views backed by a separate atomic `library.json` file.
- **Episode progress tracking** — successful playback/download records watched
  episodes, last episode, known totals, and automatically completes the last
  known episode without modifying the existing `ani-hsts` format.
- **Library cover previews** — highlighted library entries reuse the existing
  cover cache and terminal renderer, with textual metadata fallback.
- **Search-result quick actions** — save or classify an anime before fetching
  episodes; `-S`/`-e` non-interactive paths remain direct.
- **Two-column episode browser** — episodes on the left, cover art on the right (50/50 fzf split)
- **Two-column main menu** — menu options on the left, ASCII art on the right
- **HD cover art** via Kitty graphics protocol using `chafa` (Ghostty, Kitty, WezTerm, iTerm2)
- **Floyd-Steinberg dithered fallback** — smooth 256-color ANSI block art for legacy terminals
- **Lanczos downscaling** in ffmpeg for sharper cover art at any size
- **Dynamic terminal sizing** — cover art auto-scales using `stty size`
- **JKanime support** — Spanish subtitles source added to main menu
- **Provider fallback expansion** — Spanish subtitles now use JKanime →
  AnimeFLV → AnimeFenix → TioAnime → AnimeAV1; Spanish dub uses MonosChinos →
  AnimeFLV → AnimeAV1.
- **English Python fallback** — AllAnime remains primary and falls back to
  Gogoanime for empty searches and unresolved episodes.
- **Language-aware extractor CLI** — `search`, `episodes`, and `episode` accept
  `--lang en|es` while defaulting to Spanish for compatibility.
- **Graphics cleanup** — cover images are cleared instantly on Esc or episode selection (no lingering)
- **Custom start screen** — `menuPixelArt.txt` logo (box-drawing) + `asciiArt.txt` side panel
- **Search text visibility fix** — migrated fzf colors to 256-color palette indexes; explicit `query:253`

### Changed
- `ui_render_cover` rewrote renderer from simple quantizer to full dithered pipeline
- `fzf_command` preview now cascades: chafa → wezterm imgcat → kitty icat → imgcat → ANSI dither
- `ui_builtin_art` split into logo-only mode (for fzf header) and full mode (logo + braille art)
- `ui_main_header` now uses logo-only to keep fzf header compact and menu items visible
- `ui_scale_braille_art` regex now accepts any variable name before `"""` (not just `logo`)
- The installer now deploys and permissions the complete `extractors/` package.

### Attribution

- Based on [pystardust/ani-cli](https://github.com/pystardust/ani-cli), licensed under GPL-3.0.
