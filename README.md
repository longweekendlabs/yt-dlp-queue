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

One-shot mode passes its arguments straight to yt-dlp:

```bash
yd "https://example.com/video"
yd -x --audio-format mp3 "https://example.com/video"
```

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

## Install

```bash
cp yd ~/.local/bin/yd
chmod 755 ~/.local/bin/yd
```

`~/.local/bin` must be on your `PATH`. yt-dlp itself is expected at
`/usr/local/bin/yt-dlp` or anywhere else on `PATH`.

## License

MIT. See [LICENSE](LICENSE).
