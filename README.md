cat > README.md <<'EOF'
# yt-dlp Queue

A small terminal queue wrapper for yt-dlp.

It keeps a URL input field available while a download is running, allowing additional URLs to be queued.

Downloads run one at a time.

## Usage

Start queue mode:

```bash
yd
Paste a URL and press Enter.
While that download is running, paste another URL. It will wait in the queue.
Commands:
status — show queue status
q — stop accepting URLs and finish the queue
Ctrl+C — stop immediately
One-shot mode also works:
yd "https://example.com/video"
Requirements
Linux
Python 3
yt-dlp

