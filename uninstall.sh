#!/bin/sh

set -u

say() {
    printf '%s\n' "$*"
}

fail() {
    printf 'animux uninstaller: %s\n' "$*" >&2
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
    /) fail "Refusing to uninstall with PREFIX=/." ;;
esac

remove_file() {
    if [ -e "$1" ] || [ -L "$1" ]; then
        rm -f "$1" || fail "Could not remove $1. Check permissions or rerun with sudo."
        say "Removed $1"
    fi
}

remove_dir() {
    if [ -d "$1" ]; then
        rm -rf "$1" || fail "Could not remove $1. Check permissions or rerun with sudo."
        say "Removed $1"
    fi
}

remove_file "$PREFIX/bin/animux"
remove_dir "$PREFIX/libexec/animux"
remove_dir "$PREFIX/share/animux"
remove_file "$PREFIX/share/man/man1/animux.1"

say "Uninstalled animux from $PREFIX."
say "Cache, watch history, and personal library were left intact."
