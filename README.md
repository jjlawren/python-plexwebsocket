# python-plexwebsocket
Async library to react to events issued over Plex websockets.

## Example use
```python
import asyncio
from plexapi.server import PlexServer
from plexwebsocket import PlexWebsocket

baseurl = 'http://<PLEX_SERVER_IP>:32400'
token = '<YOUR_TOKEN_HERE>'
plex = PlexServer(baseurl, token)

def print_info(signal, data, error):
    if signal == "data":
        print(f"Data: {data}")
    elif signal == "state":
        print(f"State: {data} / Error: {error}")

async def main():
    ws = PlexWebsocket(plex, print_info)
    await ws.listen()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
```
