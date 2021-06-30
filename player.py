from library import Track
import vlc
from operating_system import LinuxStandbyLock


class Player:
    paused: bool
    now_playing_row: int
    now_playing: Track
    instance: vlc.Instance
    mediaplayer: vlc.MediaPlayer

    def __init__(self):
        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()
        self.paused = False
        self.now_playing_row = -1
        self.now_playing = None

    def onPlayStart(self):
        pass
        # LinuxStandbyLock.inhibit()

    def onPlayEnd(self):
        pass
        # LinuxStandbyLock.release()

    def playPause(self, track=None, pos=0):
        global paused

        if self.now_playing:
            if paused:
                self.mediaplayer.play()
                self.onPlayStart()
            else:
                self.mediaplayer.pause()
                self.onPlayEnd()
            paused = not paused
        return not paused

    def play(self, index: int, track=None):
        try:
            media = self.instance.media_new(track.full_path)
            self.mediaplayer.set_media(media)
            # media.parse()
            # setWindowTitle(media.get_meta(0))
        except:
            self.paused = True
            self.now_playing = None
            return False

        self.paused = False
        self.now_playing = track
        self.now_playing_row = index
        self.mediaplayer.play()
        self.onPlayStart()

        return track

    def getProgress(self):
        return round(self.mediaplayer.get_position() / 1000)

    def setProgress(self, pos):
        self.mediaplayer.set_position(pos)

    def setVolume(self, volume):
        self.mediaplayer.audio_set_volume(volume)

    def getVolume(self):
        return self.mediaplayer.audio_get_volume()

    def stop(self):
        self.paused = False
        self.now_playing = None
        self.mediaplayer.stop()
        self.onPlayEnd()

    def isNoMusic(self):
        return paused or not self.now_playing

    def getNowPlayingMsg(self):
        if isinstance(self.now_playing, library.Track):
            return f'{"Paused: " if paused else "Playing: "}{self.now_playing.artist} - {self.now_playing.title} [{self.now_playing.album}]'
        else:
            return 'Play stopped'