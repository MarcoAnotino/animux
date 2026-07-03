#!/bin/sh
# Uso: ./play_jkanime.sh <url_del_episodio>
# Ejemplo: ./play_jkanime.sh https://jkanime.net/one-piece/1168/

URL="$1"
# Suponiendo que el extractor está en extractor.py y tiene una clase JkanimeExtractor
# Necesitamos un pequeño script que imprima solo la URL del stream en formato "best >url"
STREAM=$(python3 -c "
from extractor import JkanimeExtractor
import sys
url = sys.argv[1]
ext = JkanimeExtractor()
data = ext.extract(url)
print('best >' + data['formats'][0]['url'])
" "$URL")

echo "Stream obtenido: $STREAM"
# Pasar al reproductor (ajusta si usas iina)
mpv --referrer="https://jkanime.net" "$(echo "$STREAM" | cut -d'>' -f2)"