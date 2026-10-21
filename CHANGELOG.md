# Changelog

## 0.2.0

- Three live log files per queue-mode run, in `~/.config/yt-dlp/yd-logs/`:
  `yd-queue.<tag>.txt`, `yd-downloaded.<tag>.txt` and `yd-failed.<tag>.txt`,
  all tagged with the launch time.
- The queue log lists only unfinished URLs and is rewritten whenever the queue
  changes, which makes it the list to re-paste after an interrupted run.
- The downloaded log gets a line as each URL completes; the failed log gets a
  line with the yt-dlp exit code as each URL fails.
- On exit the three files move to `yd-logs/archive/`. Leftovers from a run that
  died are archived on the next launch, so `yd-logs/` only ever holds the
  current run.
- `SIGTERM` and `SIGHUP` are handled, so closing the terminal still archives the
  logs.
- A download interrupted by Ctrl+C is recorded as `interrupted (aborted)`
  instead of a bare negative exit code.

## 0.1.0

- Initial public release.
- Persistent terminal UI.
- Sequential yt-dlp download queue.
- Paste URLs while another download is active.
- Queue status.
- One-shot yt-dlp compatibility.
