# Changelog

## [Unreleased]

## [0.5.0] - 2026-11-06

### Added

- More website support for links yt-dlp does not handle on its own.
- Download a complete series from one episode link, preserving episode titles,
  unique IDs, uploader/channel folders and creator metadata where available.
  Use `yd --no-playlist "URL"` for only the pasted episode.
- Support for additional embedded players, current quality sources and HLS streams.
  Some web players use Deno for their signatures.

### Fixed

- Preserve episode metadata instead of using generic player names or missing
  uploader folders. Track each episode separately in download history.
- Use current player sources when page metadata points to obsolete files.

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
