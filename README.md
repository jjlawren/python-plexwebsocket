# python-plexwebsocket
Async library to react to events issued over Plex websockets.

## Example use
```python
import asyncio
import logging
from plexapi.server import PlexServer
from plexwebsocket import PlexWebsocket, SIGNAL_CONNECTION_STATE

logging.basicConfig(level=logging.DEBUG)

baseurl = 'http://<PLEX_SERVER_IP>:32400'
token = '<YOUR_TOKEN_HERE>'
plex = PlexServer(baseurl, token)

def print_info(msgtype, data, error):
    if msgtype == SIGNAL_CONNECTION_STATE:
        print(f"State: {data} / Error: {error}")
    else:
        print(f"Data: {data}")

async def main():
    ws = PlexWebsocket(plex, print_info, subscriptions=["playing", "state"])
    await ws.listen()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
```
