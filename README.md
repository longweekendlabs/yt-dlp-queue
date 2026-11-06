# yt-dlp Queue

A small terminal queue wrapper for yt-dlp.

It keeps a URL input field available while a download is running, so additional
URLs can be queued. Downloads run one at a time.

## Usage

Start queue mode:

```bash
yd
```

Paste a URL and press Enter. While that download is running, paste another URL
and it waits in the queue.

| Command | Effect |
| --- | --- |
| `status` | show active, waiting, finished and failed counts |
| `q` | stop accepting URLs and finish the queue |
| `Ctrl+C` | stop immediately |

One-shot mode accepts regular yt-dlp arguments and includes the same site support:

```bash
yd "https://example.com/video"
yd -x --audio-format mp3 "https://example.com/video"
```

## Additional website support

yd includes support for more websites that yt-dlp does not handle on its own.
Paste a normal episode link to download the site's series list in order, with
proper titles, unique IDs, uploader/channel folders and available creator metadata.
Series grouping follows the website and can include related sequels.

To download only the pasted episode, use one-shot mode:

```bash
yd --no-playlist "https://example.com/video"
```

A whole series is one queue item. The log keeps the original pasted link; if you
interrupt a series, paste it again and your configured download archive skips
completed episodes. Each episode has its own download-history ID.

Some additional websites require Deno for their web player. yd uses the configured
Deno runtime, one on `PATH`, or `~/.deno/bin/deno`. You can specify it with
`--js-runtimes deno:/path/to/deno`. No additional Python packages are needed.
Only video sources available to the current session are offered.

## Run logs

Every queue-mode launch writes three live log files into
`~/.config/yt-dlp/yd-logs/`, tagged with the launch time (`YYYYMMDD-HHMMSS`) so
all three files of one run share the same tag:

| File | Contents |
| --- | --- |
| `yd-queue.<tag>.txt` | URLs still unfinished, rewritten whenever the queue changes |
| `yd-downloaded.<tag>.txt` | one line per URL that downloaded successfully |
| `yd-failed.<tag>.txt` | one line per URL that failed, with the yt-dlp exit code |

When yd exits (`q`, Ctrl+C, closing the terminal) the three files move to
`yd-logs/archive/`. If a run dies without cleaning up, such as a crash, `kill -9`
or a power loss, its leftovers are archived on the next launch. So `yd-logs/`
always describes the current run, and `yd-logs/archive/` holds the finished ones.

Each line is the URL followed by a comment, so a log file can be pasted straight
back into yd:

```
https://www.youtube.com/watch?v=abc123  # 2026-10-21 08:51:34
https://example.com/video-4  # exit code 1  # 2026-10-21 08:51:36
```

The queue log keeps only what has not finished yet, which makes it the list to
re-paste after an interrupted run. A download interrupted by Ctrl+C is recorded
in the failure log as `interrupted (aborted)`. One-shot mode writes no logs,
because there is no queue.

## Requirements

- Linux
- Python 3
- yt-dlp on `PATH`
- Deno for some additional websites

## Install

```bash
cp yd ~/.local/bin/yd
chmod 755 ~/.local/bin/yd
mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/yd/plugins/yd/yt_dlp_plugins/extractor"
cp plugins/yd/yt_dlp_plugins/extractor/*.py \
  "${XDG_DATA_HOME:-$HOME/.local/share}/yd/plugins/yd/yt_dlp_plugins/extractor/"
```

`~/.local/bin` must be on your `PATH`. yt-dlp itself is expected at
`/usr/local/bin/yt-dlp` or anywhere else on `PATH`.
Copy both the script and plugins when updating. The plugins are loaded by yd;
running yd from this checkout uses the checkout's plugins automatically.

## License

MIT. See [LICENSE](LICENSE).
