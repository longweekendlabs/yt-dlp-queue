"""Offline extraction and queue integration checks using the installed yt-dlp.

Run: python3 -m unittest discover -s tests -v
"""

import base64
import importlib.util
import io
import json
import queue
import runpy
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
# yt-dlp's standalone Python release is also an importable zip archive.
try:
    import yt_dlp
except ImportError:
    sys.path.insert(0, shutil.which('yt-dlp'))
    import yt_dlp

from yt_dlp.utils import DownloadError

spec = importlib.util.spec_from_file_location(
    'watchhentai', ROOT / 'plugins/yd/yt_dlp_plugins/extractor/watchhentai.py',
)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
yd = runpy.run_path(str(ROOT / 'yd'))

EPISODE_URL = 'https://watchhentai.net/videos/example-series-episode-2/'
FIRST_EPISODE_URL = EPISODE_URL.replace('episode-2', 'episode-1')
SERIES_URL = 'https://watchhentai.net/series/example-series/'
PLAYER_URL = 'https://watchhentai.net/player/668/1/mp4/'
MEDIA_URL = 'https://media.example.test/episode-2.mp4'
EPISODE_HTML = '''
<h1 class="module-title">Example Series &#8211; Episode 2 &amp; More</h1>
<meta property="og:image" content="https://media.example.test/poster.jpg">
<iframe data-primary-player-url="/player/668/1/mp4/"
 data-alternate-player-url="/player-alt/668/1/mp4/"></iframe>
'''
EPISODE_LIST = f'''
<div class="item item-all"><a href="{SERIES_URL}">All Episodes</a></div>
<ul class="episodios">
<li><a href="{FIRST_EPISODE_URL}">Episode 1</a></li>
<li><a href="{EPISODE_URL}">Episode 2</a></li>
<li><a href="{EPISODE_URL}?tracking=duplicate">Episode 2 duplicate</a></li>
<li><a href="https://other.example/videos/unrelated/">External link</a></li>
</ul>
<div id="dt-episodes-discovery"><a href="/videos/recommendation/">Other series</a></div>
'''


def player_html(media_url=MEDIA_URL):
    return '<script type="application/ld+json">' + json.dumps({
        '@context': 'https://schema.org', '@type': 'VideoObject',
        'name': 'Player - WatchHentai.net', 'contentUrl': media_url,
        'duration': 'PT20M',
    }) + '</script>'


def encoded_source(media_url, label):
    value = base64.b64encode(media_url.encode())[::-1]
    masked = bytes(byte ^ ((13 + index % 17) & 255) for index, byte in enumerate(value))
    return {'file': base64.urlsafe_b64encode(masked).decode().rstrip('='), 'label': label}


class ExtractionTests(unittest.TestCase):
    def extract(self, episode=EPISODE_HTML, player=None, url=EPISODE_URL, extra_pages=None, **params):
        pages = {url: episode, PLAYER_URL: player if player is not None else player_html()}
        pages.update(extra_pages or {})
        with yt_dlp.YoutubeDL({
            'quiet': True, 'no_warnings': True, 'logger': Mock(), **params,
        }, auto_init=False) as dl:
            ie = plugin.WatchHentaiIE(dl)
            dl.add_info_extractor(ie)
            with patch.object(ie, '_download_webpage', side_effect=lambda u, *a, **k: pages[u]), \
                    patch.object(dl, 'urlopen', side_effect=AssertionError('Offline test attempted network access')):
                info = dl.extract_info(url, download=False)
            return info, dl.prepare_filename(info), dl._make_archive_id(info)

    def test_original_metadata_controls_filename_folder_and_archive(self):
        info, filename, archive_id = self.extract(
            outtmpl='%(uploader)s/%(title)s-%(id)s.%(ext)s',
        )
        self.assertEqual(info['title'], 'Example Series – Episode 2 & More')
        self.assertEqual(info['id'], '668')
        self.assertEqual(info['uploader'], 'WatchHentai')
        self.assertEqual(filename, 'WatchHentai/Example Series – Episode 2 & More-668.mp4')
        self.assertEqual(archive_id, 'watchhentai 668')
        self.assertEqual(info['webpage_url'], EPISODE_URL)
        self.assertEqual(info['url'], MEDIA_URL)
        self.assertEqual(info['http_headers']['Referer'], PLAYER_URL)
        self.assertEqual(info['duration'], 1200)

    def test_other_episodes_have_separate_archive_ids(self):
        first = self.extract()[2]
        other_player = PLAYER_URL.replace('668', '669')
        with patch.dict(globals(), PLAYER_URL=other_player):
            second = self.extract(episode=EPISODE_HTML.replace('668', '669'))[2]
        self.assertNotEqual(first, second)

    def test_og_title_fallback_removes_site_advertising(self):
        page = EPISODE_HTML.replace(
            '<h1 class="module-title">Example Series &#8211; Episode 2 &amp; More</h1>',
            '<meta property="og:title" content="Example Episode 2 - Watch Hentai, Stream Online English Subbed">',
        )
        self.assertEqual(self.extract(episode=page)[0]['title'], 'Example Episode 2')

    def test_missing_source_fails_clearly(self):
        with self.assertRaisesRegex(DownloadError, 'No video source found'):
            self.extract(player='<html>No source</html>')

    def test_missing_title_fails_instead_of_using_generic_player_title(self):
        page = '<iframe data-primary-player-url="/player/668/1/mp4/"></iframe>'
        with self.assertRaisesRegex(DownloadError, 'No episode title found'):
            self.extract(episode=page)

    def test_unexpected_player_host_is_rejected(self):
        with self.assertRaisesRegex(DownloadError, 'Unrecognized WatchHentai player URL'):
            self.extract(episode=EPISODE_HTML.replace(
                '"/player/668/1/mp4/"', '"https://unrelated.example/player/668/1/mp4/"',
            ))

    def test_hls_source_uses_manifest_formats_and_referer(self):
        manifest = 'https://media.example.test/master.m3u8'
        with patch.object(plugin.WatchHentaiIE, '_extract_m3u8_formats', return_value=[{
            'url': MEDIA_URL, 'ext': 'mp4', 'format_id': '720p',
        }]) as formats:
            info = self.extract(player=player_html(manifest))[0]
        formats.assert_called_once_with(manifest, '668', 'mp4', headers={'Referer': PLAYER_URL})
        self.assertEqual(info['format_id'], '720p')

    def test_uses_real_player_quality_variants_instead_of_stale_metadata(self):
        sources = [encoded_source(MEDIA_URL.replace('.mp4', f'_{height}p.mp4'), f'{height}p')
                   for height in (480, 1080, 720)]
        player = player_html('https://media.example.test/stale-404.mp4')
        player += '<script>var whJwSources = ' + json.dumps(sources) + ';</script>'
        info = self.extract(player=player)[0]
        self.assertEqual(info['url'], MEDIA_URL.replace('.mp4', '_1080p.mp4'))
        self.assertEqual(info['height'], 1080)
        self.assertEqual({fmt['height'] for fmt in info['formats']}, {480, 720, 1080})
        self.assertNotIn('stale-404', str(info['formats']))

    def test_plain_player_sources_work_without_decoding(self):
        player = player_html() + '<script>var whJwSources = ' + json.dumps([
            {'file': MEDIA_URL, 'label': '720p'},
        ]) + ';</script>'
        self.assertEqual(self.extract(player=player)[0]['height'], 720)

    def test_corrupt_encoded_source_fails_clearly(self):
        player = '<script>var whJwSources = [{"file":"broken"}];</script>'
        with self.assertRaisesRegex(DownloadError, 'Unable to decode WatchHentai'):
            self.extract(player=player)

    def test_plugin_only_claims_watchhentai_episode_pages(self):
        self.assertTrue(plugin.WatchHentaiIE.suitable(EPISODE_URL))
        self.assertTrue(plugin.WatchHentaiIE.suitable(SERIES_URL))
        for url in ('https://youtube.com/watch?v=example', PLAYER_URL,
                    'https://watchhentai.net.evil.test/videos/example/'):
            self.assertFalse(plugin.WatchHentaiIE.suitable(url))

    def series_pages(self):
        return {
            FIRST_EPISODE_URL: EPISODE_HTML.replace('668', '667') + EPISODE_LIST,
            PLAYER_URL.replace('668', '667'): player_html(MEDIA_URL.replace('2.mp4', '1.mp4')),
        }

    def test_pasted_second_episode_downloads_whole_series_once_in_site_order(self):
        info = self.extract(
            episode=EPISODE_HTML + EPISODE_LIST, extra_pages=self.series_pages(),
        )[0]
        self.assertEqual(info['_type'], 'playlist')
        self.assertEqual(info['title'], 'Example Series')
        self.assertEqual(info['id'], 'example-series')
        self.assertEqual([entry['id'] for entry in info['entries']], ['667', '668'])
        self.assertEqual([entry['webpage_url'] for entry in info['entries']],
                         [FIRST_EPISODE_URL, EPISODE_URL])
        self.assertTrue(all(entry['uploader'] == 'WatchHentai' for entry in info['entries']))

    def test_no_playlist_only_extracts_pasted_episode(self):
        info = self.extract(episode=EPISODE_HTML + EPISODE_LIST, noplaylist=True)[0]
        self.assertEqual(info['id'], '668')
        self.assertNotIn('entries', info)

    def test_direct_series_url_downloads_its_episode_list(self):
        pages = self.series_pages()
        pages[EPISODE_URL] = EPISODE_HTML + EPISODE_LIST
        info = self.extract(
            episode='<h1>Example Series</h1>' + EPISODE_LIST,
            url=SERIES_URL, extra_pages=pages,
        )[0]
        self.assertEqual([entry['id'] for entry in info['entries']], ['667', '668'])

    def test_falls_back_to_series_page_when_episode_has_no_list(self):
        series_link = f'<div class="item-all"><a href="{SERIES_URL}">All Episodes</a></div>'
        pages = self.series_pages()
        pages[SERIES_URL] = '<h1>Example Series</h1>' + EPISODE_LIST
        info = self.extract(episode=EPISODE_HTML + series_link, extra_pages=pages)[0]
        self.assertEqual(len(info['entries']), 2)

    def test_empty_series_list_fails_instead_of_silently_downloading_one(self):
        with self.assertRaisesRegex(DownloadError, 'No episodes found'):
            self.extract(episode='<h1>Example Series</h1>', url=SERIES_URL)

    def test_series_list_missing_pasted_episode_fails_clearly(self):
        page = EPISODE_HTML + EPISODE_LIST.replace(EPISODE_URL, FIRST_EPISODE_URL)
        with self.assertRaisesRegex(DownloadError, 'Pasted episode is missing'):
            self.extract(episode=page)


class QueueTests(unittest.TestCase):
    def test_queue_keeps_original_url_in_logs_and_passes_plugin_to_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = yd['RunLogs'](Path(tmp))
            logs.prepare()
            events = queue.Queue()
            process = Mock(stdout=io.StringIO('[download] Finished\n'))
            process.wait.return_value = 0
            with patch('subprocess.Popen', return_value=process) as popen:
                worker = yd['QueueWorker']('yt-dlp', events, logs)
                worker.add(EPISODE_URL)
                worker.stop_accepting()
                worker.shutdown_when_done()
                worker.thread.join(timeout=3)
                self.assertFalse(worker.thread.is_alive())
            command = popen.call_args.args[0]
            self.assertEqual(command[-3:], ['--newline', '--', EPISODE_URL])
            self.assertIn('--plugin-dirs', command)
            self.assertIn(EPISODE_URL, logs.paths['downloaded'].read_text())
            self.assertEqual(logs.paths['queue'].read_text(), '')
            self.assertEqual(worker.snapshot()['failed'], 0)

    def test_one_shot_keeps_user_arguments_and_loads_same_plugin(self):
        args = ['yd', '--simulate', '--output', '%(title)s.%(ext)s', EPISODE_URL]
        with patch('sys.argv', args), patch('subprocess.run') as run:
            run.return_value.returncode = 0
            self.assertEqual(yd['main'](), 0)
        self.assertEqual(run.call_args.args[0][-4:], args[1:])
        self.assertIn('--plugin-dirs', run.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
