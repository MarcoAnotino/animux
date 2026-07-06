#!/bin/sh

set -u
umask 022

say() {
    printf '%s\n' "$*"
}

fail() {
    printf 'animux installer: %s\n' "$*" >&2
    exit 1
}

default_prefix() {
    case "$(uname -s 2>/dev/null || printf unknown)" in
        Darwin)
            if [ -d /opt/homebrew ] && [ -w /opt/homebrew ]; then
                printf '%s\n' /opt/homebrew
            elif [ -d /usr/local ] && [ -w /usr/local ]; then
                printf '%s\n' /usr/local
            else
                printf '%s\n' "$HOME/.local"
            fi
            ;;
        *)
            if [ -d /usr/local ] && [ -w /usr/local ]; then
                printf '%s\n' /usr/local
            else
                printf '%s\n' "$HOME/.local"
            fi
            ;;
    esac
}

PREFIX="${PREFIX:-$(default_prefix)}"
[ -n "$PREFIX" ] || fail "PREFIX cannot be empty."

case "$PREFIX" in
    /) fail "Refusing to install with PREFIX=/." ;;
esac

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)" || script_dir=""
source_dir=""
temporary_dir=""

cleanup() {
    [ -n "$temporary_dir" ] && [ -d "$temporary_dir" ] && rm -rf "$temporary_dir"
}

trap cleanup 0
trap 'cleanup; exit 1' HUP INT TERM

if [ "${0##*/}" = "install.sh" ] && [ -n "$script_dir" ] && [ -f "$script_dir/animux" ]; then
    source_dir="$script_dir"
else
    command -v curl >/dev/null 2>&1 || fail "curl is required for a remote installation."
    command -v tar >/dev/null 2>&1 || fail "tar is required for a remote installation."

    temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/animux-install.XXXXXX")" ||
        fail "Could not create a temporary directory."

    repository_owner="${ANIMUX_REPOSITORY_OWNER:-MarcoAnotino}"
    repository_name="${ANIMUX_REPOSITORY_NAME:-animux}"
    repository_ref="${ANIMUX_REF:-main}"
    archive_url="https://codeload.github.com/${repository_owner}/${repository_name}/tar.gz/${repository_ref}"
    archive_file="$temporary_dir/animux.tar.gz"

    say "Downloading animux ${repository_ref}..."

    curl --fail --silent --show-error --location "$archive_url" -o "$archive_file" ||
        fail "Could not download animux archive."

    tar -xzf "$archive_file" -C "$temporary_dir" ||
        fail "Could not extract animux archive."

    source_dir="$(find "$temporary_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"

    [ -n "$source_dir" ] && [ -f "$source_dir/animux" ] ||
        fail "Could not locate animux source after extraction."
fi

for file in animux anime-extractor animux-library extractor.py menuPixelArt.txt asciiArt.txt animux.1; do
    [ -f "$source_dir/$file" ] && [ -r "$source_dir/$file" ] ||
        fail "Required file not found: $file"
done

[ -d "$source_dir/extractors" ] && [ -r "$source_dir/extractors/__init__.py" ] ||
    fail "Required extractor package not found: extractors"

bin_dir="$PREFIX/bin"
libexec_dir="$PREFIX/libexec/animux"
share_dir="$PREFIX/share/animux"
ascii_dir="$share_dir/ascii"
man_dir="$PREFIX/share/man/man1"

if ! mkdir -p "$bin_dir" "$libexec_dir" "$share_dir" "$ascii_dir" 2>/dev/null; then
    say ""
    say "Cannot write to $PREFIX."
    say "Install without sudo with:"
    say "  PREFIX=\"\$HOME/.local\" ./install.sh"
    say "Or rerun this installer with sudo and PREFIX=$PREFIX."
    exit 1
fi

say "Installing animux to $PREFIX..."

cp "$source_dir/animux" "$bin_dir/animux" ||
    fail "Could not install the animux command."

cp "$source_dir/anime-extractor" "$libexec_dir/anime-extractor" ||
    fail "Could not install anime-extractor."

cp "$source_dir/animux-library" "$libexec_dir/animux-library" ||
    fail "Could not install animux-library."

cp "$source_dir/extractor.py" "$libexec_dir/extractor.py" ||
    fail "Could not install extractor.py."

rm -rf "$libexec_dir/extractors" ||
    fail "Could not remove the previous extractor package."
cp -R "$source_dir/extractors" "$libexec_dir/extractors" ||
    fail "Could not install the extractor package."

cp "$source_dir/menuPixelArt.txt" "$share_dir/menuPixelArt.txt" ||
    fail "Could not install menuPixelArt.txt."

cp "$source_dir/asciiArt.txt" "$share_dir/asciiArt.txt" ||
    fail "Could not install asciiArt.txt."

chmod 755 "$bin_dir/animux" "$libexec_dir/anime-extractor" "$libexec_dir/animux-library" ||
    fail "Could not set executable permissions."

chmod 644 "$libexec_dir/extractor.py" "$share_dir/menuPixelArt.txt" "$share_dir/asciiArt.txt" ||
    fail "Could not set data file permissions."

find "$libexec_dir/extractors" -type d -exec chmod 755 {} + ||
    fail "Could not set extractor directory permissions."
find "$libexec_dir/extractors" -type f -name '*.py' -exec chmod 644 {} + ||
    fail "Could not set extractor module permissions."

if [ -d "$source_dir/assets/ascii" ]; then
    say "Installing random ASCII art collection..."
    for art_file in "$source_dir"/assets/ascii/*.txt; do
        [ -f "$art_file" ] || continue
        cp "$art_file" "$ascii_dir/" ||
            fail "Could not install ASCII art: $art_file"
    done
    chmod 755 "$ascii_dir" ||
        fail "Could not set ASCII art directory permissions."
    chmod 644 "$ascii_dir"/*.txt 2>/dev/null || true
fi

if mkdir -p "$man_dir" && cp "$source_dir/animux.1" "$man_dir/animux.1"; then
    chmod 644 "$man_dir/animux.1" ||
        fail "Could not set man page permissions."
    say "Installed man page: $man_dir/animux.1"
else
    fail "Could not install the animux man page."
fi

say "Installed command: $bin_dir/animux"
say "Installed helpers: $libexec_dir"
say "Installed assets: $share_dir"

if [ -d "$ascii_dir" ] && ls "$ascii_dir"/*.txt >/dev/null 2>&1; then
    say "Installed random ASCII arts: $ascii_dir"
fi

say ""
say "Installed animux successfully."
say "Run: animux"

case ":${PATH:-}:" in
    *":$bin_dir:"*) ;;
    *)
        if [ "$PREFIX" = "$HOME/.local" ]; then
            say "Add ~/.local/bin to your PATH if animux is not found."
            say '  export PATH="$HOME/.local/bin:$PATH"'
        else
            say "Add $bin_dir to your PATH if animux is not found."
        fi
        ;;
    esac

exit 0
