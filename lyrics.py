import lyricwikia
from PyLyrics import *
import lyricsgenius

from PyQt5.QtCore import QObject, pyqtSignal


class Lyrics(QObject):
    finished = pyqtSignal(str)

    PROVIDER_GENIUS = 'Genius.com'
    PROVIDER_LYRICSWIKIA = 'LyricsWikia'
    PROVIDER_PYLYRICS = 'PyLyrics'

    DEFAULT_PROVIDER = PROVIDER_LYRICSWIKIA

    PROVIDERS = [PROVIDER_GENIUS, PROVIDER_LYRICSWIKIA, PROVIDER_PYLYRICS]

    provider: 0

    genius: lyricsgenius.Genius

    config: None
    player: None

    def setConfig(self, config, player):
        self.config = config
        self.player = player
        self.initProviders()
        self.setProvider(self.DEFAULT_PROVIDER if config.getLyricsProvider() == '' else config.getLyricsProvider())

    def initProviders(self):
        self.genius = lyricsgenius.Genius(self.config.getLyricsGeniusToken())

    def run(self):
        try:
            if self.provider == self.PROVIDER_GENIUS:
                song = self.genius.search_song(self.player.now_playing.title, self.player.now_playing.artist)
                self.finished.emit(song.lyrics)
            elif self.provider == self.PROVIDER_LYRICSWIKIA:
                self.finished.emit(lyricwikia.get_lyrics(self.player.now_playing.artist, self.player.now_playing.title))
            elif self.provider == self.PROVIDER_PYLYRICS:
                self.finished.emit(PyLyrics.getLyrics(self.player.now_playing.artist, self.player.now_playing.title))

        except Exception as e:
            self.finished.emit(self.player.now_playing.artist + ': ' + self.player.now_playing.title + '\n' \
                   + self.provider + ' server error: ' + str(e))

    def setProvider(self, name):
        self.provider = name

    def onChangeTokens(self):
        self.initProviders()
