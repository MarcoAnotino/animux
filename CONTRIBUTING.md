# Contributing to animux

animux is a personal fork — PRs and issues are welcome but this project is maintained at my own pace and doesn't follow a formal release cycle.

## Reporting bugs

Open an issue with:
- Your terminal emulator and OS
- The command you ran
- The full error output
- Output of `echo $TERM $TERM_PROGRAM $COLORTERM`

## Pull Requests

- Keep changes focused and small
- No new required dependencies without a very good reason
- Test on at least one POSIX shell (`sh`, `bash`, or `zsh`)
- `make check` must pass (POSIX shell syntax checks)
- Update the README if you add or change a feature

## Adding a new source

Read [hacking.md](hacking.md) first — it explains how the scraping pipeline works and how to add a new site.

## Note

For issues that also affect upstream [ani-cli](https://github.com/pystardust/ani-cli), consider checking the original project.
