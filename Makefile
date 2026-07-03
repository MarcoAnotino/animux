PREFIX ?=

.PHONY: install uninstall check

install:
	PREFIX="$(PREFIX)" sh ./install.sh

uninstall:
	PREFIX="$(PREFIX)" sh ./uninstall.sh

check:
	sh -n animux
	sh -n anime-extractor
	@if [ -f play_jkanime.sh ]; then sh -n play_jkanime.sh; fi
	sh -n install.sh
	sh -n uninstall.sh
	python3 -m unittest
