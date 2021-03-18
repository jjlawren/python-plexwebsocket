# python-plexwebsocket
Async library to react to events issued over Plex websockets.


## Sample usage
```python
import asyncio
import threading
import time

import plexwebsocket
from plexapi.server import PlexServer


def _print(signal, data, error):
    print(signal, data, error)


def plex_websocket_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    plexWebSocket = plexwebsocket.PlexWebsocket(plex, _print)
    loop.run_until_complete(plexWebSocket.listen())
    loop.close()


if __name__ == '__main__':
    plex = PlexServer()

    plex_thread = threading.Thread(target=plex_websocket_thread)
    plex_thread.start()

    while True:
        time.sleep(1)
```
