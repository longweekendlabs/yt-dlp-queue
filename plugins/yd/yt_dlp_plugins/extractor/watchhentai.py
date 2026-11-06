"""WatchHentai episode pages, with metadata retained for filenames and archives."""

import base64
import re
from urllib.parse import urlparse

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    ExtractorError, determine_ext, extract_attributes, get_element_by_class,
    get_elements_by_class, smuggle_url, unsmuggle_url, url_or_none, urljoin,
)


class WatchHentaiIE(InfoExtractor):
    IE_NAME = 'watchhentai'
    _VALID_URL = r'https?://(?:www\.)?watchhentai\.net/(?P<kind>videos|series)/(?P<id>[^/?#]+)'

    def _page_title(self, webpage):
        title = self._html_search_regex(
            r'(?is)<h1\b[^>]*>(.*?)</h1>', webpage, 'episode title', default=None,
        ) or self._og_search_title(webpage, default=None) or self._html_extract_title(webpage) or ''
        if re.fullmatch(r'Player\s*[-|]\s*WatchHentai\.net', title, re.I):
            raise ExtractorError('No episode title found on the WatchHentai page', expected=True)
        title = re.sub(
            r'\s*[-|]\s*(?:Watch\s*Hentai(?:\.net)?)(?:\s*,.*)?$', '', title,
            flags=re.IGNORECASE,
        ).strip()
        if not title:
            raise ExtractorError('No episode title found on the WatchHentai page', expected=True)
        return title

    @staticmethod
    def _episode_url(base_url, href):
        if not href:
            return None
        parsed = urlparse(urljoin(base_url, href))
        if (parsed.scheme in ('http', 'https')
                and parsed.hostname in ('watchhentai.net', 'www.watchhentai.net')
                and re.fullmatch(r'/videos/[^/]+/?', parsed.path)):
            return f'https://watchhentai.net{parsed.path.rstrip("/")}/'

    def _episode_urls(self, webpage, base_url):
        # Only the series' Episode List, never Discovery or other recommendations.
        urls = []
        for episode_list in get_elements_by_class('episodios', webpage):
            for anchor in re.findall(r'(?is)<a\b[^>]*>', episode_list):
                url = self._episode_url(base_url, extract_attributes(anchor).get('href'))
                if url and url not in urls:
                    urls.append(url)
        return urls

    def _real_extract(self, url):
        url, smuggled = unsmuggle_url(url, {})
        match = self._match_valid_url(url)
        display_id, kind = match.group('id', 'kind')
        webpage = self._download_webpage(url, display_id)
        title = self._page_title(webpage)

        if kind == 'series' or not (smuggled.get('force_noplaylist') or self.get_param('noplaylist')):
            series_link = get_element_by_class('item-all', webpage) or ''
            series_path = self._search_regex(
                r'''href\s*=\s*["']([^"']+)''', series_link, 'series URL', default=None,
            )
            series_url = urljoin(url, series_path) if series_path else None
            if series_url and not re.fullmatch(
                r'https?://(?:www\.)?watchhentai\.net/series/[^/?#]+/?', series_url,
            ):
                series_url = None
            episode_urls = self._episode_urls(webpage, url)
            if not episode_urls and series_url and kind == 'videos':
                series_page = self._download_webpage(
                    series_url, display_id, note='Downloading series episode list',
                )
                episode_urls = self._episode_urls(series_page, series_url)
            if not episode_urls and (kind == 'series' or series_url):
                raise ExtractorError('No episodes found in the WatchHentai series list', expected=True)
            if episode_urls and kind == 'videos' and self._episode_url(url, url) not in episode_urls:
                raise ExtractorError('Pasted episode is missing from the series list', expected=True)
            if kind == 'series' or len(episode_urls) > 1:
                series_id = self._match_id(series_url or url)
                if kind == 'series' or self._yes_playlist(series_id, display_id, playlist_label='series'):
                    series_title = re.sub(r'\s*[-\u2013\u2014]\s*Episode\b.*$', '', title, flags=re.I)
                    entries = [self.url_result(
                        smuggle_url(episode_url, {'force_noplaylist': True}), ie=self.ie_key(),
                    ) for episode_url in episode_urls]
                    return self.playlist_result(entries, series_id, series_title)

        player_url = urljoin(url, self._search_regex(
            r'''data-primary-player-url\s*=\s*["']([^"']+)''',
            webpage, 'player URL',
        ))
        player_id = re.fullmatch(
            r'/player/(\d+)/(\d+)/[^/]+/?', urlparse(player_url).path,
        )
        if urlparse(player_url).hostname not in ('watchhentai.net', 'www.watchhentai.net') or not player_id:
            raise ExtractorError('Unrecognized WatchHentai player URL', expected=True)
        # Use the episode's numeric ID, never the player's generic "mp4" ID.
        video_id = player_id.group(1)
        player = self._download_webpage(player_url, video_id, note='Downloading episode player')
        info = self._search_json_ld(player, video_id, default={})
        # Some episodes' JSON-LD points at a retired file. Prefer the sources
        # actually passed to the browser player, including its quality variants.
        sources = self._search_json(
            r'\b(?:var|let|const)\s+whJwSources\s*=', player, 'player sources', video_id,
            contains_pattern=r'\[(?s:.*?)\]', default=[],
        )
        if not sources and info.get('url'):
            sources = [{'file': info['url']}]
        headers = {'Referer': player_url}
        formats = []
        for source in sources:
            media_url = source.get('file') if isinstance(source, dict) else None
            if not isinstance(media_url, str):
                continue
            if not url_or_none(media_url):
                try:
                    raw = base64.urlsafe_b64decode(media_url + '=' * (-len(media_url) % 4))
                    unmasked = bytes(byte ^ ((13 + index % 17) & 255) for index, byte in enumerate(raw))
                    media_url = base64.b64decode(unmasked[::-1], validate=True).decode('utf-8')
                except (ValueError, UnicodeError) as exc:
                    raise ExtractorError('Unable to decode WatchHentai player source', expected=True, cause=exc)
            if not url_or_none(media_url):
                raise ExtractorError('Invalid WatchHentai player source URL', expected=True)
            media_url = self._proto_relative_url(media_url)
            extension = determine_ext(media_url)
            if extension == 'm3u8':
                formats.extend(self._extract_m3u8_formats(media_url, video_id, 'mp4', headers=headers))
            elif extension == 'mpd':
                formats.extend(self._extract_mpd_formats(media_url, video_id, headers=headers))
            else:
                label = source.get('label') or ''
                height = re.fullmatch(r'(\d+)p', label)
                formats.append({
                    'url': media_url, 'http_headers': headers,
                    'format_id': label or None,
                    'height': int(height.group(1)) if height else None,
                })
        if not formats:
            raise ExtractorError('No video source found in the WatchHentai player', expected=True)

        # Return a final video result: transparent redirects discard the outer ID,
        # which would cause unrelated episodes to share an archive entry.
        info.pop('url', None)
        info.update({
            'id': video_id,
            'display_id': display_id,
            'title': title,
            'uploader': 'WatchHentai',
            'uploader_id': 'watchhentai',
            'webpage_url': url,
            'thumbnail': self._og_search_thumbnail(webpage, default=None),
            'age_limit': 18,
            'formats': formats,
            'http_headers': headers,
        })
        return info
