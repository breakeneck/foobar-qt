import pylast
import time

# You have to have your own unique two values for API_KEY and API_SECRET
# Obtain yours from https://www.last.fm/api/account/create for Last.fm
API_KEY = "ad6ab7666c6d445fd6a65957d4ff823e"  # this is a sample key
API_SECRET = "c0b02d43ce286b7da4d54138bd0f75c0"


class LastFM:
    def __init__(self, config):
        self.config = config

    def scrobble(self, artist, title):
        # print('Scrobbling', artist, ': ', title)
        pylast.LastFMNetwork(
            api_key=API_KEY,
            api_secret=API_SECRET,
            username=self.config.getLastFmUsername(),
            password_hash=pylast.md5(self.config.getLastFmPassword()),
        ).scrobble(artist, title, time.time())

# Now you can use that object everywhere
# track = network.get_track("Iron Maiden", "The Nomad")
# track.love()
# track.add_tags(("awesome", "favorite"))
