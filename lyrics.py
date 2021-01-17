import lyricwikia
from PyLyrics import *
import lyricsgenius

import player


class Lyrics:
    PROVIDER_GENIUS = 'Genius.com'
    PROVIDER_LYRICSWIKIA = 'LyricsWikia'
    PROVIDER_PYLYRICS = 'PyLyrics'

    DEFAULT_PROVIDER = PROVIDER_LYRICSWIKIA

    PROVIDERS = [PROVIDER_GENIUS, PROVIDER_LYRICSWIKIA, PROVIDER_PYLYRICS]

    provider: 0

    genius: lyricsgenius.Genius
    config: None

    def __init__(self, config):
        self.config = config
        self.initProviders()
        self.setProvider(self.DEFAULT_PROVIDER if config.getLyricsProvider() == '' else config.getLyricsProvider())


    def initProviders(self):
        self.genius = lyricsgenius.Genius(self.config.getLyricsGeniusToken())


    def find(self):
        try:
            if self.provider == self.PROVIDER_GENIUS:
                song = self.genius.search_song(player.now_playing.title, player.now_playing.artist)
                return song.lyrics
            elif self.provider == self.PROVIDER_LYRICSWIKIA:
                return lyricwikia.get_lyrics(player.now_playing.artist, player.now_playing.title)
            elif self.provider == self.PROVIDER_PYLYRICS:
                return PyLyrics.getLyrics(player.now_playing.artist, player.now_playing.title)

        except Exception as e:
            return player.now_playing.artist + ': ' + player.now_playing.title + '\n' \
                   + self.provider + ' server error: ' + str(e)


    def setProvider(self, name):
        self.provider = name


    def onChangeTokens(self):
        self.initProviders()

