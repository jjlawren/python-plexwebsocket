"""Support for issuing callbacks for Plex client updates via websockets."""
import asyncio
from concurrent.futures._base import CancelledError
from datetime import datetime
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

STATE_CONNECTED = "connected"
STATE_DISCONNECTED = "disconnected"
STATE_STARTING = "starting"
STATE_STOPPED = "stopped"


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

    # pylint: disable=too-many-instance-attributes

    def __init__(self, plex_server, callback, session=None, verify_ssl=True):
        """Initialize a PlexWebsocket instance.

        Parameters:
            plex_server (plexapi.server.PlexServer):
                A connected PlexServer instance.
            callback (Runnable):
                Callback to issue when Plex player events occur.
            verify_ssl:
                Set to False to disable SSL certificate validation.
            session (aiohttp.ClientSession, optional):
                Provide an optional session object.

        """
        self.session = session or aiohttp.ClientSession()
        self.uri = self._get_uri(plex_server)
        self.players = {}
        self.callback = callback
        self._ssl = False if verify_ssl is False else None
        self._state = None
        self.failed_attempts = 0

    @property
    def state(self):
        """Return the current state."""
        return self._state

    @state.setter
    def state(self, value):
        """Set the state."""
        self._state = value
        _LOGGER.debug("Websocket %s", value)

    @staticmethod
    def _get_uri(plex_server):
        """Generate the websocket URI using the `plexapi` library."""
        return plex_server.url(
            "/:/websockets/notifications", includeToken=True
        ).replace("http", "ws")

    async def running(self):
        """Open a persistent websocket connection and act on events."""
        self.state = STATE_STARTING

        try:
            async with self.session.ws_connect(
                self.uri, heartbeat=15, ssl=self._ssl
            ) as ws_client:
                self.state = STATE_CONNECTED
                self.failed_attempts = 0
                self.callback()

                async for message in ws_client:
                    if self.state == STATE_STOPPED:
                        break

                    if message.type == aiohttp.WSMsgType.TEXT:
                        msg = message.json()["NotificationContainer"]
                        if self.player_event(msg):
                            self.callback()

                    elif message.type == aiohttp.WSMsgType.CLOSED:
                        _LOGGER.warning("AIOHTTP websocket connection closed")
                        break

                    elif message.type == aiohttp.WSMsgType.ERROR:
                        _LOGGER.error("AIOHTTP websocket error")
                        break

        except aiohttp.ClientConnectionError as error:
            if self.state != STATE_STOPPED:
                retry_delay = min(2 ** (self.failed_attempts - 1) * 30, 300)
                self.failed_attempts += 1
                _LOGGER.error(
                    "Websocket connection failed, retrying in %ds: %s",
                    retry_delay,
                    error,
                )
                self.state = STATE_DISCONNECTED
                await asyncio.sleep(retry_delay)
        except CancelledError:
            _LOGGER.debug("Websocket future cancelled")
            self.state = STATE_STOPPED
        except Exception as error:  # pylint: disable=broad-except
            if self.state != STATE_STOPPED:
                _LOGGER.exception("Unexpected exception occurred: %s", error)
                self.state = STATE_DISCONNECTED
                await asyncio.sleep(10)
        else:
            if self.state != STATE_STOPPED:
                self.state = STATE_DISCONNECTED

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

    async def listen(self):
        """Close the listening websocket."""
        self.failed_attempts = 0
        while self.state != STATE_STOPPED:
            await self.running()

    def close(self):
        """Close the listening websocket."""
        self.state = STATE_STOPPED
