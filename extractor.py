#!/usr/bin/env python3
import sys

from extractors import (
    AnimeAV1Extractor,
    AnimeFenixExtractor,
    AnimeExtractor,
    AnimeFLVExtractor,
    GogoanimeExtractor,
    JkanimeExtractor,
    MonoschinoExtractor,
    TioAnimeExtractor,
)


def parse_command_options(args):
    """Parse shared command options without breaking legacy positional calls."""
    lang = "es"
    dub = False
    positional = []
    index = 0
    while index < len(args):
        value = args[index]
        if value == "--dub":
            dub = True
        elif value == "--lang":
            index += 1
            if index >= len(args) or args[index] not in {"es", "en"}:
                raise ValueError("--lang requiere 'es' o 'en'.")
            lang = args[index]
        else:
            positional.append(value)
        index += 1
    return lang, dub, positional


def main():
    if len(sys.argv) < 2:
        print("Usage: extractor.py <url> [fallback-url ...]", file=sys.stderr)
        print("       extractor.py search [--lang en|es] [--dub] <title>", file=sys.stderr)
        print("       extractor.py episodes [--lang en|es] [--dub] <id>", file=sys.stderr)
        print("       extractor.py episode [--lang en|es] [--dub] <id> <episode> [title]", file=sys.stderr)
        return 1

    extractor = AnimeExtractor()
    args = sys.argv[1:]

    if args[0] in {"search", "episodes", "episode"}:
        command = args.pop(0)

        try:
            lang, dub, args = parse_command_options(args)
            if command == "search":
                if not args:
                    raise ValueError("Falta el título para buscar.")

                query = " ".join(args)
                for result in extractor.search(query, dub=dub, lang=lang):
                    identifier = str(result["id"]).replace("\t", " ").replace("\n", " ")
                    title = str(result["title"]).replace("\t", " ").replace("\n", " ")
                    print(f"{identifier}\t{title} ({result['total_episodes']} episodes)")

            elif command == "episodes":
                if len(args) != 1:
                    raise ValueError("episodes requiere exactamente un identificador.")

                for number in extractor.list_episodes(
                    args[0], dub=dub, lang=lang
                ):
                    print(number)

            else:
                if len(args) < 2:
                    raise ValueError("episode requiere un identificador y un episodio.")

                identifier, number = args[:2]
                title = " ".join(args[2:]) if len(args) > 2 else None
                result = extractor.get_episode(
                    identifier,
                    number,
                    dub=dub,
                    title=title,
                    lang=lang,
                )
                print("best >" + result["url"])
                if result.get("referer"):
                    print("referer >" + result["referer"])
                print("extractor >" + result["extractor"], file=sys.stderr)

        except Exception as exc:
            print(f"[animux] {command} falló: {exc}", file=sys.stderr)
            return 1

        return 0

    for url in args:
        try:
            data = extractor.extract(url)
            formats = data.get("formats", []) if data else []
            if not formats:
                raise RuntimeError("No se encontraron formatos de video válidos.")
            print("best >" + formats[0]["url"])
            return 0
        except Exception as exc:
            print(f"[animux] Fallo en {url}: {exc}", file=sys.stderr)

    print("[animux] Ningún extractor interno devolvió un stream válido.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
