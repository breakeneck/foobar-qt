import lyricwikia
from PyLyrics import *
import lyricsgenius
import re

from PyQt5.QtCore import QObject, pyqtSignal


class Lyrics(QObject):
    finished = pyqtSignal(str)

    PROVIDER_GENIUS = 'Genius.com'
    PROVIDER_LYRICSWIKIA = 'LyricsWikia'
    PROVIDER_PYLYRICS = 'PyLyrics'

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
        self.setProvider(self.DEFAULT_PROVIDER if config.getLyricsProvider() == '' else config.getLyricsProvider())

    def initProviders(self):
        self.genius = lyricsgenius.Genius(self.config.getLyricsGeniusToken())

    def run(self):
        artist = re.sub(r"\(.*?\)", "", self.player.now_playing.artist)
        title = re.sub(r"\(.*?\)", "", self.player.now_playing.title)
        try:
            if self.provider == self.PROVIDER_GENIUS:
                song = self.genius.search_song(title, artist)
                self.finished.emit(song.lyrics)
            elif self.provider == self.PROVIDER_LYRICSWIKIA:
                self.finished.emit(lyricwikia.get_lyrics(artist, title))
            elif self.provider == self.PROVIDER_PYLYRICS:
                lyrics = PyLyrics.getLyrics(artist, title)
                output = str(lyrics).encode('utf-8', errors='replace')[22:-6:]. \
                    decode("utf-8").replace('\n', '').replace('<br/>', '\n')
                try:
                    text = output
                except:
                    text = output.encode('utf-8')
                self.finished.emit(text)


        except Exception as e:
            self.finished.emit(str(self.player.now_playing.artist) + ': ' + str(self.player.now_playing.title) + '\n' \
                               + self.provider + ' server error: ' + str(e))

    def setProvider(self, name):
        self.provider = name

    def onChangeTokens(self):
        self.initProviders()
