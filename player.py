import library

import vlc

paused = False
now_playing_row: -1
now_playing: None  # type: library.Track
instance = vlc.Instance()
mediaplayer = instance.media_player_new()


def playPause(track=None, pos=0):
    global paused

    if now_playing:
        if paused:
            mediaplayer.play()
        else:
            mediaplayer.pause()
        paused = not paused
    return not paused


def play(index: int, track=None):
    global paused, now_playing, now_playing_row

    try:
        media = instance.media_new(track.full_path)
        mediaplayer.set_media(media)
        # media.parse()
        # setWindowTitle(media.get_meta(0))
    except:
        paused = True
        now_playing = None
        return False

    paused = False
    now_playing = track
    now_playing_row = index
    mediaplayer.play()

    return track


def getProgress():
    return round(mediaplayer.get_position() / 1000)


def setProgress(pos):
    mediaplayer.set_position(pos)


def setVolume(volume):
    mediaplayer.audio_set_volume(volume)


def getVolume():
    return mediaplayer.audio_get_volume()


def stop():
    global paused, now_playing
    paused = False
    now_playing = None
    mediaplayer.stop()


def isNoMusic():
    return paused or not now_playing


def getNowPlayingMsg():
    if isinstance(now_playing, library.Track):
        return f'{"Paused: " if paused else "Playing: "}{now_playing.artist} - {now_playing.title} [{now_playing.album}]'
    else:
        return 'Play stopped'
