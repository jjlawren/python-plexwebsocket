"""Support for issuing callbacks for Plex client updates via websockets."""
import asyncio
from datetime import datetime
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)


class WebsocketPlayer:  # pylint: disable=too-few-public-methods
    """Represent an individual player state in the Plex websocket stream."""

    def __init__(self, session_id, state, media_key, position):
        """Initialize a WebsocketPlayer instance."""
        self.session_id = session_id
        self.state = state
        self.media_key = media_key
        self.position = position
        self.timestamp = datetime.now()

    def significant_position_change(self, timestamp, new_position):
        """Determine if position change indicates a seek."""
        timediff = (timestamp - self.timestamp).total_seconds()
        posdiff = (new_position - self.position) / 1000
        diffdiff = timediff - posdiff

        if abs(diffdiff) > 5:
            return True
        return False


class PlexWebsocket:
    """Represent a websocket connection to a Plex server."""

    def __init__(self, plex_server, callback, session=None):
        """Initialize a PlexWebsocket instance.

        Parameters:
            plex_server (plexapi.server.PlexServer):
                A connected PlexServer instance.
            callback (Runnable):
                Callback to issue when Plex player events occur.
            session (aiohttp.ClientSession, optional):
                Provide an optional session object.

        """
        self.session = session or aiohttp.ClientSession()
        self.uri = self._get_uri(plex_server)
        self.players = {}
        self.callback = callback
        self._active = True
        self._current_task = None

    @staticmethod
    def _get_uri(plex_server):
        """Generate the websocket URI using the `plexapi` library."""
        return plex_server.url(
            "/:/websockets/notifications", includeToken=True
        ).replace("http", "ws")

    async def listen(self):
        """Open a persistent websocket connection and act on events."""
        self._active = True
        while self._active:
            try:
                async with self.session.ws_connect(self.uri, heartbeat=15) as ws_client:
                    self._current_task = asyncio.Task.current_task()
                    _LOGGER.debug("Websocket connected")
                    self.callback()

                    async for message in ws_client:
                        msg = message.json()["NotificationContainer"]
                        if self.player_event(msg):
                            self.callback()

            except aiohttp.client_exceptions.ClientConnectorError:
                _LOGGER.debug("Websocket connection refused")
                await asyncio.sleep(10)
            else:
                _LOGGER.debug("Websocket disconnected")
                if self._active:
                    # Session IDs reset if Plex server has restarted, be safe
                    self.players.clear()
                    await asyncio.sleep(5)

    def player_event(self, msg):
        """Determine if messages relate to an interesting player event."""
        should_fire = False

        if msg["type"] == "update.statechange":
            # Fired when clients connects or disconnect
            _LOGGER.debug("New client device detected")
            return True
        if msg["type"] != "playing":
            # Only monitor events related to active sessions
            return False

        payload = msg["PlaySessionStateNotification"][0]

        session_id = payload["sessionKey"]
        state = payload["state"]
        media_key = payload["key"]
        position = payload["viewOffset"]

        if session_id not in self.players:
            self.players[session_id] = WebsocketPlayer(
                session_id, state, media_key, position
            )
            _LOGGER.debug("New session: %s", payload)
            return True

        if state == "stopped":
            # Sessions "end" when stopped
            self.players.pop(session_id)
            _LOGGER.debug("Session ended: %s", payload)
            return True

        player = self.players[session_id]
        now = datetime.now()

        # Ignore buffering states as transient
        if state != "buffering":
            if player.media_key != media_key or player.state != state:
                # State or playback item changed
                _LOGGER.debug("State/media changed: %s", payload)
                should_fire = True
            elif state == "playing" and player.significant_position_change(
                now, position
            ):
                # Client continues to play and a seek was detected
                _LOGGER.debug("Seek detected: %s", payload)
                should_fire = True

        player.state = state
        player.media_key = media_key
        player.position = position
        player.timestamp = now

        return should_fire

    def close(self):
        """Close the listening websocket."""
        self._active = False
        self._current_task.cancel()
