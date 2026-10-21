import re

import lyricsgenius
import lyricwikia
from PyLyrics import *
from PyQt6.QtCore import QObject, pyqtSignal


class Lyrics(QObject):
    finished = pyqtSignal(str)

    PROVIDER_GENIUS = "Genius.com"
    PROVIDER_LYRICSWIKIA = "LyricsWikia"
    PROVIDER_PYLYRICS = "PyLyrics"

    DEFAULT_PROVIDER = PROVIDER_GENIUS

    PROVIDERS = [PROVIDER_GENIUS, PROVIDER_PYLYRICS]

    provider: 0

    genius: lyricsgenius.Genius

    config: None
    player: None

    def setConfig(self, config, player):
        self.config = config
        self.player = player
        self.initProviders()
        self.setProvider(
            self.DEFAULT_PROVIDER
            if config.getLyricsProvider() == ""
            else config.getLyricsProvider()
        )

    # genius.com sits behind Cloudflare which rejects the library's default
    # User-Agent with 403; a browser-like one goes through
    BROWSER_UA = (
        "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"
    )

    def initProviders(self):
        # lyricsgenius raises TypeError('Invalid token') on an empty token;
        # if it propagates out of a Qt slot PyQt6 aborts the process, so the
        # provider is simply left unavailable and lookup falls back to others.
        token = self.config.getLyricsGeniusToken()
        self.genius = None
        if token:
            self.genius = lyricsgenius.Genius(token, verbose=False)
            self.genius._session.headers.update({"User-Agent": self.BROWSER_UA})

    def run(self):
        # Nothing may escape this slot: when a Python exception propagates
        # out of a slot invoked from C++, PyQt6 calls qFatal() and abort()s
        # the whole process.
        try:
            self.lookup()
        except Exception as e:
            self.finished.emit("Lyrics lookup failed: %s" % e)

    def lookup(self):
        # Capture the track: playback may stop while this runs.
        track = self.player.now_playing
        if not track:
            return
        # Tags can be NULL in the DB (rows load straight from SQLite),
        # and re.sub on None raises TypeError.
        artist = re.sub(r"\(.*?\)", "", str(track.artist or "")).strip()
        title = re.sub(r"\(.*?\)", "", str(track.title or "")).strip()

        # Try the selected provider first, then fall back to the others:
        # a song missing from one site's database is often found on another.
        providers = [self.provider] + [p for p in self.PROVIDERS if p != self.provider]
        errors = []
        for provider in providers:
            try:
                lyrics = self.getLyrics(provider, artist, title)
                if lyrics:
                    if provider != self.provider:
                        lyrics = "(%s)\n\n%s" % (provider, lyrics)
                    self.finished.emit(lyrics)
                    return
                errors.append("%s: no lyrics" % provider)
            except Exception as e:
                errors.append("%s: %s" % (provider, str(e)))

        self.finished.emit(
            str(track.artist or "")
            + ": "
            + str(track.title or "")
            + "\nLyrics not found (" + ", ".join(errors) + ")"
        )

    def getLyrics(self, provider, artist, title):
        if provider == self.PROVIDER_GENIUS:
            if self.genius is None:
                raise Exception("no genius token configured")
            song = self.genius.search_song(title, artist)
            return song.lyrics if song else None
        if provider == self.PROVIDER_LYRICSWIKIA:
            return lyricwikia.get_lyrics(artist, title)
        if provider == self.PROVIDER_PYLYRICS:
            lyrics = PyLyrics.getLyrics(artist, title)
            output = (
                str(lyrics)
                .encode("utf-8", errors="replace")[22:-6:]
                .decode("utf-8")
                .replace("\n", "")
                .replace("<br/>", "\n")
            )
            return output
        return None

    def setProvider(self, name):
        self.provider = name

    def onChangeTokens(self):
        self.initProviders()
