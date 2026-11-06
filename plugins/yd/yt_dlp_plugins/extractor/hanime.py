"""Hanime's current web player and its explicit More from series lists."""

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp import aes
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    ExtractorError, extract_attributes, int_or_none, smuggle_url, unsmuggle_url,
    urljoin, url_or_none,
)


def _b64encode(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def _b64decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


# These are public web-player protocol constants, not user credentials.
_KEY = list(hashlib.sha256(b'htv-insecure-handshake-v1').digest())
_AAD = b'htv-insecure-v1'


def _gcm_tag(ciphertext, nonce):
    def pad(value):
        return value + b'\0' * (-len(value) % 16)

    data = pad(_AAD) + pad(ciphertext) + (len(_AAD) * 8).to_bytes(8, 'big') + (len(ciphertext) * 8).to_bytes(8, 'big')
    subkey = aes.aes_encrypt([0] * 16, aes.key_expansion(_KEY))
    digest = aes.ghash(subkey, list(data))
    return bytes(aes.aes_ctr_encrypt(digest, _KEY, list(nonce + b'\0\0\0\1')))


def _seal_payload(payload, nonce=None):
    nonce = nonce if nonce is not None else os.urandom(12)
    plaintext = json.dumps(payload, separators=(',', ':')).encode()
    ciphertext = bytes(aes.aes_ctr_encrypt(list(plaintext), _KEY, list(nonce + b'\0\0\0\2')))
    envelope = {'v': 1, 'alg': 'AES-256-GCM', 'iv': _b64encode(nonce),
                'tag': _b64encode(_gcm_tag(ciphertext, nonce)), 'data': _b64encode(ciphertext)}
    return _b64encode(json.dumps(envelope, separators=(',', ':')).encode())


def _open_payload(token):
    envelope = json.loads(_b64decode(token))
    nonce, ciphertext, tag = (_b64decode(envelope[key]) for key in ('iv', 'data', 'tag'))
    if (envelope.get('v') != 1 or envelope.get('alg') != 'AES-256-GCM'
            or len(nonce) != 12 or not hmac.compare_digest(tag, _gcm_tag(ciphertext, nonce))):
        raise ValueError('Invalid Hanime response authentication tag')
    return json.loads(bytes(aes.aes_ctr_decrypt(list(ciphertext), _KEY, list(nonce + b'\0\0\0\2'))))


class HanimeTVIE(InfoExtractor):
    IE_NAME = 'hanime.tv'
    _VALID_URL = r'https?://(?:www\.)?hanime\.tv/videos/hentai/(?P<id>[a-zA-Z0-9_-]+)'

    def _page_props(self, webpage, component):
        for tag in re.findall(r'<astro-island\b[^>]*>', webpage):
            attrs = extract_attributes(tag)
            options = self._parse_json(attrs.get('opts', '{}'), None, fatal=False) or {}
            if options.get('name') != component:
                continue
            props = self._parse_json(attrs.get('props', '{}'), None) or {}
            return {key: value[1] for key, value in props.items()
                    if isinstance(value, list) and len(value) == 2 and value[0] == 0}
        return {}

    def _series(self, webpage, url):
        for section in re.findall(r'(?is)<section\b[^>]*>(.*?)</section>', webpage):
            name = self._html_search_regex(
                r'(?is)<h2\b[^>]*>\s*More from\s+(.*?)</h2>', section, 'series name', default=None,
            )
            if not name:
                continue
            urls = []
            for tag in re.findall(r'<a\b[^>]*>', section):
                href = extract_attributes(tag).get('href')
                if not href:
                    continue
                parsed = urlparse(urljoin(url, href))
                if (parsed.hostname in ('hanime.tv', 'www.hanime.tv')
                        and parsed.scheme in ('http', 'https')
                        and re.fullmatch(r'/videos/hentai/[a-zA-Z0-9_-]+/?', parsed.path)):
                    entry = f'https://hanime.tv{parsed.path.rstrip("/")}'
                    if entry not in urls:
                        urls.append(entry)
            return name, urls
        return None, []

    def _signature(self, webpage, video_id):
        runtime = self.get_param('js_runtimes', {}).get('deno') or {}
        deno = (runtime.get('path') if isinstance(runtime, dict) else runtime) or shutil.which('deno')
        if not deno and (Path.home() / '.deno/bin/deno').is_file():
            deno = str(Path.home() / '.deno/bin/deno')
        if not deno:
            raise ExtractorError('Hanime requires Deno; configure --js-runtimes deno:/path/to/deno', expected=True)
        vendor_url = self._search_regex(
            r'''<script\b[^>]*\bsrc=["'](https://hanime-cdn\.com/js/vendor\.[a-zA-Z0-9]+\.min\.js)["']''',
            webpage, 'player signature script',
        )
        if getattr(self, '_vendor_url', None) != vendor_url:
            self._vendor_source = self._download_webpage(vendor_url, video_id, note='Downloading player signature script')
            self._vendor_url = vendor_url
        # Run the public signature module with Deno's permissions disabled. It
        # receives no cookies, tokens, files or environment access.
        bootstrap = '''var process = undefined;
const window = new EventTarget();
const document = {currentScript: {src: "https://hanime-cdn.com/js/vendor.js"}};
globalThis.window = window; globalThis.document = document;
window.top = window; window.self = window;
window.location = {hostname: "hanime.tv", host: "hanime.tv", href: "https://hanime.tv/", origin: "https://hanime.tv"};
window.addEventListener("wasm-ready", () => console.log(JSON.stringify({signature: window.ssignature, time: window.stime})));
'''
        try:
            result = subprocess.run([
                deno, 'run', '--no-config', '--no-lock', '--no-npm', '--no-remote', '--no-prompt',
                '--deny-read', '--deny-write', '--deny-net', '--deny-env', '--deny-run', '--deny-ffi', '--deny-sys', '-',
            ], input=bootstrap + self._vendor_source, capture_output=True, text=True, timeout=15, check=True)
            signature = json.loads(result.stdout.strip().splitlines()[-1])
            if not re.fullmatch(r'[a-f0-9]{64}', signature['signature']) or not int_or_none(signature.get('time')):
                raise ValueError('Invalid signature')
            return signature
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError) as exc:
            raise ExtractorError('Unable to generate Hanime player signature with Deno', expected=True, cause=exc)

    def _playback_formats(self, webpage, slug, video_id, url):
        signature = self._signature(webpage, video_id)
        headers = {'Referer': url, 'Origin': 'https://hanime.tv', 'Accept': 'application/json',
                   'x-signature-version': 'web2', 'x-signature': signature['signature'],
                   'x-time': str(signature['time'])}
        csrf = self._download_json('https://ct.hanime.tv/csrf-token', video_id,
                                   note='Getting player session token', headers=headers)
        headers['x-csrf-token'] = csrf['csrf_token']
        headers['Content-Type'] = 'application/json'
        payload = _seal_payload({'timestamp_unix': int(time.time()), 'directive': 'htv_player_handshake', 'slug': slug})
        _, response = self._download_webpage_handle(
            'https://auth.hanime.tv/api/v11/handshake', video_id, note='Getting playable sources',
            data=json.dumps({'token': payload}).encode(), headers=headers,
        )
        try:
            playback = _open_payload(response.headers.get('x-token', ''))
        except (ValueError, KeyError, TypeError) as exc:
            raise ExtractorError('Invalid Hanime player response', expected=True, cause=exc)
        formats = []
        media_headers = {'Referer': url, 'Origin': 'https://hanime.tv'}
        for source in playback.get('sources', []):
            if source.get('kind') == 'promotion' or not source.get('src'):
                continue
            # The site's same-origin /hls route serves the signed source too.
            media_url = urljoin('https://hanime.tv', source['src'])
            if not url_or_none(media_url):
                continue
            manifest = self._download_webpage(media_url, video_id,
                note=f'Downloading {source.get("label", "HLS")} playlist', headers=media_headers)
            manifest = manifest.strip()
            if manifest.startswith('"'):
                manifest = self._parse_json(manifest, video_id)
            manifest = manifest.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\r', '\n')
            if not manifest.startswith('#EXTM3U') or '#EXTINF:' not in manifest:
                raise ExtractorError('Invalid Hanime media playlist', expected=True)
            formats.append({
                'url': media_url, 'format_id': source.get('label'), 'ext': 'mp4', 'protocol': 'm3u8_native',
                'height': int_or_none(source.get('height')), 'width': int_or_none(source.get('width')),
                'hls_media_playlist_data': manifest, 'http_headers': media_headers,
            })
        if not formats:
            raise ExtractorError('No playable Hanime sources available to this session', expected=True)
        return formats

    def _real_extract(self, url):
        url, smuggled = unsmuggle_url(url, {})
        slug = self._match_id(url)
        url = f'https://hanime.tv/videos/hentai/{slug}'
        webpage = self._download_webpage(url, slug)
        props = self._page_props(webpage, 'VideoPageContentController')
        video_id = str(props.get('video_id') or '')
        if not video_id.isdigit():
            raise ExtractorError('Unable to identify the Hanime video; page layout may have changed', expected=True)
        info = self._search_json_ld(webpage, video_id, default={})
        title = props.get('video_name') or info.get('title')
        if not title:
            raise ExtractorError('No Hanime episode title found', expected=True)
        series, episode_urls = self._series(webpage, url)
        if (len(episode_urls) > 1 and not smuggled.get('force_noplaylist')
                and self._yes_playlist(series, video_id, playlist_label='series')):
            if url not in episode_urls:
                raise ExtractorError('Pasted Hanime episode is missing from the series list', expected=True)
            entries = [self.url_result(smuggle_url(entry, {'force_noplaylist': True}), ie=self.ie_key())
                       for entry in episode_urls]
            return self.playlist_result(entries, series, series)
        studio = self._html_search_regex(
            r'''(?is)<a\b[^>]*href=["']/browse/brands/[^"']+["'][^>]*>.*?<strong\b[^>]*>(.*?)</strong>''',
            webpage, 'studio', default=None,
        )
        info.update({
            'id': video_id, 'display_id': slug, 'title': title, 'webpage_url': url,
            'uploader': 'Hanime', 'uploader_id': 'hanime.tv', 'channel': 'Hanime', 'channel_id': 'hanime.tv',
            'creator': studio, 'series': series, 'age_limit': 18,
            'formats': self._playback_formats(webpage, slug, video_id, url),
        })
        info.pop('url', None)
        return info
