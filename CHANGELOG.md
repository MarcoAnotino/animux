# Changelog

## [Unreleased] - animux

Upstream base: pystardust/ani-cli

### Added
- **Two-column episode browser** — episodes on the left, cover art on the right (50/50 fzf split)
- **Two-column main menu** — menu options on the left, ASCII art on the right
- **HD cover art** via Kitty graphics protocol using `chafa` (Ghostty, Kitty, WezTerm, iTerm2)
- **Floyd-Steinberg dithered fallback** — smooth 256-color ANSI block art for legacy terminals
- **Lanczos downscaling** in ffmpeg for sharper cover art at any size
- **Dynamic terminal sizing** — cover art auto-scales using `stty size`
- **JKanime support** — Spanish subtitles source added to main menu
- **Graphics cleanup** — cover images are cleared instantly on Esc or episode selection (no lingering)
- **Custom start screen** — `menuPixelArt.txt` logo (box-drawing) + `asciiArt.txt` side panel
- **Search text visibility fix** — migrated fzf colors to 256-color palette indexes; explicit `query:253`

### Changed
- `ui_render_cover` rewrote renderer from simple quantizer to full dithered pipeline
- `fzf_command` preview now cascades: chafa → wezterm imgcat → kitty icat → imgcat → ANSI dither
- `ui_builtin_art` split into logo-only mode (for fzf header) and full mode (logo + braille art)
- `ui_main_header` now uses logo-only to keep fzf header compact and menu items visible
- `ui_scale_braille_art` regex now accepts any variable name before `"""` (not just `logo`)

### Attribution

- Based on [pystardust/ani-cli](https://github.com/pystardust/ani-cli), licensed under GPL-3.0.
