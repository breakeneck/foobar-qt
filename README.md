# foobar-qt

Foobar-like music player for linux (alpha version)

![screenshot](https://imgur.com/c7DieFW.png)

Main features:
- Directory structure navigation by click (immediate Playlist update)
- "Stop After Current Track" button
- "Next Random Track" button
- Select currently playing track by status bar click
- Group by directory in Playlist view
- Instant search
- Autoload lyrics from inet (currently supports Lyrics Wikia)


To enable insensitive case search for non ascii symbols compile
```
cd apsw-master
../venv/bin/python setup.py fetch --sqlite
../venv/bin/python setup.py build --enable-all-extensions
../venv/bin/python setup.py build install
```