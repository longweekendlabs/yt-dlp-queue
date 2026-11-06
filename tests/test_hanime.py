"""Hanime metadata, series, authenticated transport and HLS regression checks."""

import importlib.util
import json
import shutil
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

try:
    import yt_dlp
except ImportError:
    sys.path.insert(0, shutil.which('yt-dlp'))
    import yt_dlp

from yt_dlp.utils import DownloadError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hanime', ROOT / 'plugins/yd/yt_dlp_plugins/extractor/hanime.py')
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

URL = 'https://hanime.tv/videos/hentai/example-2'
FIRST_URL = URL.replace('example-2', 'example-1')
FOLLOWUP_URL = URL.replace('example-2', 'example-followup-1')
VENDOR = 'https://hanime-cdn.com/js/vendor.abc123.min.js'
MANIFEST = '#EXTM3U\\n#EXT-X-VERSION:3\\n#EXT-X-TARGETDURATION:8\\n#EXTINF:8.0,\\nhttps://media.example.test/segment.ts\\n#EXT-X-ENDLIST\\n'
SOURCES = [
    {'src': '', 'label': '1080p', 'height': 1080, 'kind': 'promotion'},
    {'src': '/hls/42/720', 'label': '720p', 'height': 720, 'width': 1280, 'kind': 'normal'},
    {'src': '/hls/42/480', 'label': '480p', 'height': 480, 'width': 854, 'kind': 'normal'},
]


def page(video_id=42, title='Example 2', episode_urls=None):
    from html import escape
    props = {'video_id': [0, video_id], 'video_name': [0, title]}
    result = f'''<script src="{VENDOR}"></script>
<astro-island opts='{escape(json.dumps({'name': 'VideoPageContentController'}), quote=True)}'
 props='{escape(json.dumps(props), quote=True)}'></astro-island>
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"VideoObject","name":"{title}","duration":"PT10M"}}</script>
<a href="/browse/brands/example-studio">Studio <strong>Example Studio</strong></a>
'''
    if episode_urls is not None:
        result += '<section><h2>More from Example Series</h2>'
        result += ''.join(f'<a href="{url}">Episode</a>' for url in episode_urls)
        result += '</section>'
    result += '<section><h2>Related Playlists</h2><a href="/videos/hentai/unrelated">Unrelated</a></section>'
    return result


class ProtocolTests(unittest.TestCase):
    def test_matches_independent_aes_gcm_vector_with_associated_data(self):
        # Generated independently using AESGCM (the WebCrypto protocol's algorithm).
        envelope = {
            'v': 1, 'alg': 'AES-256-GCM', 'iv': 'AAECAwQFBgcICQoL',
            'tag': 'aec8eN6EhUGBSL0x80Qy1A',
            'data': 'HEste_1Vyj58Pyv0PfRWFPGBRrdjMJogG-Uma2c4Ig-nJjLnXxY0fgRjPqoygMdmBVeeLw',
        }
        payload = {'sources': [{'src': '/hls/42/example', 'height': 720}]}
        token = plugin._b64encode(json.dumps(envelope, separators=(',', ':')).encode())
        self.assertEqual(plugin._open_payload(token), payload)
        self.assertEqual(plugin._seal_payload(payload, bytes(range(12))), token)

    def test_tampering_is_rejected(self):
        envelope = json.loads(plugin._b64decode(plugin._seal_payload({'sources': []})))
        envelope['tag'] = plugin._b64encode(bytes(16))
        token = plugin._b64encode(json.dumps(envelope).encode())
        with self.assertRaisesRegex(ValueError, 'authentication tag'):
            plugin._open_payload(token)

    def test_signature_runtime_has_no_file_network_or_environment_permissions(self):
        deno = shutil.which('deno') or str(Path.home() / '.deno/bin/deno')
        if not Path(deno).is_file():
            self.skipTest('Deno not installed')
        vendor = '''
for (const attempt of [() => Deno.env.get("HOME"), () => Deno.readTextFileSync("/etc/hostname"),
                       () => Deno.writeTextFileSync("/tmp/yd-hanime-denied", "test")]) {
  try { attempt(); throw new Error("Permission unexpectedly granted"); }
  catch (error) { if (!(error instanceof Deno.errors.NotCapable)) throw error; }
}
window.ssignature = "a".repeat(64); window.stime = 123;
window.dispatchEvent(new Event("wasm-ready"));
'''
        with yt_dlp.YoutubeDL({'quiet': True, 'js_runtimes': {'deno': {'path': deno}}}, auto_init=False) as dl:
            ie = plugin.HanimeTVIE(dl)
            with patch.object(ie, '_download_webpage', return_value=vendor):
                result = ie._signature(page(), '42')
        self.assertEqual(result, {'signature': 'a' * 64, 'time': 123})


class ExtractionTests(unittest.TestCase):
    def extract(self, webpage=None, sources=None, extra_pages=None, **params):
        pages = {URL: webpage if webpage is not None else page(),
                 'https://hanime.tv/hls/42/720': MANIFEST,
                 'https://hanime.tv/hls/42/480': MANIFEST, **(extra_pages or {})}
        with yt_dlp.YoutubeDL({'quiet': True, 'logger': Mock(), **params}, auto_init=False) as dl:
            ie = plugin.HanimeTVIE(dl)
            dl.add_info_extractor(ie)
            response = SimpleNamespace(headers={'x-token': plugin._seal_payload({
                'sources': SOURCES if sources is None else sources,
            })})
            with patch.object(ie, '_download_webpage', side_effect=lambda u, *a, **k: pages[u]), \
                    patch.object(ie, '_signature', return_value={'signature': 'a' * 64, 'time': 123}), \
                    patch.object(ie, '_download_json', return_value={'csrf_token': 'fixture-token'}), \
                    patch.object(ie, '_download_webpage_handle', return_value=('', response)) as handshake, \
                    patch.object(dl, 'urlopen', side_effect=AssertionError('Offline test attempted network access')):
                info = dl.extract_info(URL, download=False)
            return info, dl.prepare_filename(info), dl._make_archive_id(info), handshake

    def test_metadata_filename_archive_and_available_quality(self):
        info, filename, archive_id, handshake = self.extract(
            outtmpl='%(uploader)s/%(title)s-%(id)s.%(ext)s',
        )
        self.assertEqual(filename, 'Hanime/Example 2-42.mp4')
        self.assertEqual(archive_id, 'hanimetv 42')
        self.assertEqual(info['channel'], 'Hanime')
        self.assertEqual(info['creator'], 'Example Studio')
        self.assertEqual(info['duration'], 600)
        self.assertEqual(info['height'], 720)
        self.assertEqual({f['height'] for f in info['formats']}, {480, 720})
        self.assertEqual(info['webpage_url'], URL)
        self.assertTrue(info['hls_media_playlist_data'].startswith('#EXTM3U\n'))
        self.assertNotIn('\\n', info['hls_media_playlist_data'])
        self.assertNotIn('x-csrf-token', info['http_headers'])
        request = json.loads(handshake.call_args.kwargs['data'])
        payload = plugin._open_payload(request['token'])
        self.assertEqual(payload['slug'], 'example-2')
        self.assertEqual(payload['directive'], 'htv_player_handshake')

    def test_official_series_keeps_order_deduplicates_and_avoids_recursion(self):
        episodes = [FIRST_URL, URL, URL + '?duplicate=1', FOLLOWUP_URL,
                    'https://unrelated.example/videos/hentai/other']
        series = page(episode_urls=episodes)
        info = self.extract(webpage=series, extra_pages={
            FIRST_URL: page(41, 'Example 1', episodes),
            FOLLOWUP_URL: page(43, 'Example Followup 1', episodes),
        })[0]
        self.assertEqual(info['_type'], 'playlist')
        self.assertEqual(info['title'], 'Example Series')
        self.assertEqual([e['id'] for e in info['entries']], ['41', '42', '43'])
        self.assertEqual([e['webpage_url'] for e in info['entries']], [FIRST_URL, URL, FOLLOWUP_URL])

    def test_no_playlist_downloads_only_pasted_episode(self):
        info = self.extract(webpage=page(episode_urls=[FIRST_URL, URL]), noplaylist=True)[0]
        self.assertEqual(info['id'], '42')
        self.assertNotIn('entries', info)

    def test_missing_selected_episode_fails_clearly(self):
        with self.assertRaisesRegex(DownloadError, 'missing from the series list'):
            self.extract(webpage=page(episode_urls=[FIRST_URL, FOLLOWUP_URL]))

    def test_premium_placeholder_is_not_a_playable_format(self):
        with self.assertRaisesRegex(DownloadError, 'No playable Hanime sources'):
            self.extract(sources=[SOURCES[0]])

    def test_missing_numeric_id_fails_clearly(self):
        with self.assertRaisesRegex(DownloadError, 'Unable to identify the Hanime video'):
            self.extract(webpage='<h1>Example 2</h1>')

    def test_does_not_claim_other_hosts_or_sites(self):
        self.assertTrue(plugin.HanimeTVIE.suitable(URL))
        for url in ('https://hanime.tv.evil.test/videos/hentai/example',
                    'https://watchhentai.net/videos/example/', 'https://hanime.tv/browse/brands/studio'):
            self.assertFalse(plugin.HanimeTVIE.suitable(url))


if __name__ == '__main__':
    unittest.main()
