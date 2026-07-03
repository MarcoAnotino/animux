# animux

Watch anime from your terminal with a polished TUI, English and Spanish subtitle modes, keyboard navigation, and HD cover previews.

animux lets you choose between English and Spanish subtitles. Internally, it selects the best available source for that language.

animux is a modified version of [pystardust/ani-cli](https://github.com/pystardust/ani-cli), used as the starting point for this project.

The original project is licensed under GPL-3.0, and animux keeps the same license.

## Features

- English subtitles
- Spanish subtitles with internal fallback support
- Internal source routing
- Terminal-first anime browser/player
- Interactive main menu
- Improved fzf TUI
- Back navigation with Esc
- Continue watching / history
- HD cover art previews
- macOS and Linux support
- POSIX shell

## Requirements

animux requires `curl`, `fzf`, `mpv`, `ffmpeg`, `perl`, and `openssl`. The extractor-backed Spanish flow also requires `python3`. `chafa` and `ani-skip` are optional.

On macOS, dependencies can be installed with Homebrew:

```sh
brew install curl fzf mpv ffmpeg perl openssl python chafa
```

## Install

One-command install:

```sh
curl -fsSL https://raw.githubusercontent.com/MarcoAnotino/animux/main/install.sh | sh
```

Install from a clone:

```sh
git clone https://github.com/MarcoAnotino/animux.git
cd animux
./install.sh
```

Local install without sudo:

```sh
PREFIX="$HOME/.local" ./install.sh
```

If necessary, add the local binary directory to your shell configuration:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

The default installer selects `/opt/homebrew` when appropriate on Apple Silicon, `/usr/local` when writable, and otherwise `$HOME/.local`. Any explicit `PREFIX` is respected.

## Usage

```sh
animux
animux -L es "one piece"
animux -L en "demon slayer"
animux -c
```

Legacy environment variables remain compatible:

```sh
ANI_CLI_PLAYER=debug animux -L es -S 1 -e 1 "one piece"
```

## Options

```text
-L, --language en|es                   subtitle language
-P, --provider PROVIDER                advanced internal provider override
-S, --select-nth INDEX                 select the nth menu entry
-e, --episode EPISODE                  select an episode or range
-q, --quality QUALITY                  preferred stream quality
-c, --continue                         continue from watch history
-d, --download                         download instead of playing
-l, --logview                          show logs
    --dub                              request dubbed media
    --rofi                             use rofi instead of fzf
    --dmenu                            use dmenu instead of fzf
    --skip                             enable intro skipping with mpv
    --no-detach                        keep the player attached
    --exit-after-play                  exit after playback
```

Run `animux --help` for the complete command reference.

### Advanced provider override

Most users should not need this. animux chooses a source automatically from the selected subtitle language.

```sh
animux -P allanime -L en "frieren"
animux -P jkanime -L es "one piece"
```

## Keyboard

```text
Enter  select
Esc    back
Ctrl+C quit
Tab    multi-select
```

## ASCII art

animux ships with a small collection of ASCII arts for the main menu. By default, one is selected randomly on each run and remains fixed for that process.

Disable random art:

```sh
ANIMUX_RANDOM_ASCII_ART=0 animux
```

Use a custom art file:

```sh
ANIMUX_ASCII_ART=/path/to/art.txt animux
```

Use a custom art directory:

```sh
ANIMUX_ASCII_ART_DIR=/path/to/ascii animux
```

## Configuration and data

New configuration uses the `ANIMUX_*` namespace. Equivalent `ANI_CLI_*` variables are accepted as fallbacks, including `ANI_CLI_PLAYER=debug`.

Common variables include `ANIMUX_PROVIDER`, `ANIMUX_PLAYER`, `ANIMUX_DOWNLOAD_DIR`, `ANIMUX_QUALITY`, `ANIMUX_LOG`, `ANIMUX_HIST_DIR`, `ANIMUX_LIBEXEC_DIR`, `ANIMUX_SHARE_DIR`, `ANIMUX_BUILTIN_ART`, `ANIMUX_ASCII_ART`, `ANIMUX_ASCII_ART_DIR`, `ANIMUX_RANDOM_ASCII_ART`, `ANIMUX_NO_HEADER`, and `ANIMUX_HEADER`.

History is stored at `${XDG_STATE_HOME:-$HOME/.local/state}/animux/ani-hsts`, and cached art is stored at `${XDG_CACHE_HOME:-$HOME/.cache}/animux`. On first use, animux copies an existing `ani-cli/ani-hsts` history file when the new history does not exist; the old file is not removed.

The installed layout is:

```text
$PREFIX/bin/animux
$PREFIX/libexec/animux/anime-extractor
$PREFIX/libexec/animux/extractor.py
$PREFIX/share/animux/menuPixelArt.txt
$PREFIX/share/animux/asciiArt.txt
$PREFIX/share/animux/ascii/*.txt
$PREFIX/share/man/man1/animux.1
```

In a source checkout, `assets/ascii/` contains the random main-menu ASCII art collection.

## Development

Run the source script directly and validate all POSIX shell entry points:

```sh
./animux --help
make check
```

No Bash-specific shell features are required.

## Uninstall

```sh
curl -fsSL https://raw.githubusercontent.com/MarcoAnotino/animux/main/uninstall.sh | sh
```

Or, from a clone:

```sh
./uninstall.sh
```

Use the same `PREFIX` supplied during installation for a custom-prefix uninstall. Cache and history are intentionally preserved.

## Credits

animux is based on [pystardust/ani-cli](https://github.com/pystardust/ani-cli), licensed under GPL-3.0.

Original project:

- pystardust/ani-cli

animux modifications:

- enhanced TUI/navigation
- language-first subtitle selection
- internal source routing and extractor-backed Spanish support
- HD cover art previews
- install/uninstall flow
- macOS/Linux packaging improvements

See [NOTICE](NOTICE) for attribution and [LICENSE](LICENSE) for the full GPL-3.0 license text.

## Legal disclaimer

animux does not host or distribute media files. It is a terminal interface for browsing and opening publicly available sources. Users are responsible for complying with applicable laws in their region.

animux is not an official client of any provider or website.
