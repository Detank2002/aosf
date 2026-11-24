# Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
# SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
# terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
# distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Teamplay (extension 48): team ESP, pings and the compass, for clients that
take it (ZeroSpades, XRSpades). Spec: protocol/extensions/teamplay.md.

The Config goes to every client that takes it as soon as its extensions are
known, as the spec requires. A client's ping is a request: it is checked
(alive, on a team, on the map, one a second) and relayed to its team, the
sender included, in the team's colour.

Commands
^^^^^^^^

* ``/pingmark x y z [reason]`` a ping by chat (a key bind, or a pie slice's
  ``/pingmark %h ...``)

Options
^^^^^^^

.. code-block:: toml

    [teamplay]
    features = 7                # bit 0 team ESP, 1 pings, 2 compass
    north = [0.0, -1.0]         # the map-plane vector pointing north
    ping_seconds = 10.0
    ping_colours = { blue = [48, 112, 255], green = [48, 224, 64] }

Other scripts
^^^^^^^^^^^^^

    protocol.teamplay_mark(target, on, label="", colour=(255, 255, 255),
                           flags=1, to=None, seconds=None)
        an outline on a player (a connection), or cleared; `to` a connection,
        a list, or None for everybody; flags 1 cleared on respawn, 2 its name
    protocol.teamplay_server_ping(x, y, z, label="", colour=(255, 255, 255),
                                  seconds=10.0, to=None)
        the server's own ping (one at a time: a new one replaces the last)
    connection.send_teamplay_config()
"""
import math
import time

from piqueserver.commands import command
from piqueserver.config import config

# --- shared by every AOSF piqueserver script (each file stands alone) -------
import struct as _struct

from pyspades import contained as _loaders
from pyspades import packet as _packet
from pyspades.loaders import Loader as _Loader


class _Raw(object):
    """Bytes sent as they are, through send_contained or broadcast_contained."""
    def __init__(self, data):
        self.data = bytes(data)

    def write(self, writer):
        writer.write(self.data)


def _offer(protocol, ext_id, version=1):
    exts = protocol.available_proto_extensions
    if not any(e[0] == ext_id for e in exts):
        exts.append((ext_id, version))


def _has(conn, ext_id):
    return ext_id in (getattr(conn, 'proto_extensions', None) or {})


def _hook_extinfo():
    """After piqueserver reads a client's ExtInfo, call the connection's
    aosf_extensions_known() (each script chains it through super())."""
    key = _loaders.ProtocolExtensionInfo.id
    prev = _packet._packet_handlers.get(key)
    if prev is None or getattr(prev, '_aosf', False):
        return

    def handler(conn, contained):
        prev(conn, contained)
        hook = getattr(conn, 'aosf_extensions_known', None)
        if hook is not None:
            hook()
    handler._aosf = True
    _packet._packet_handlers[key] = handler


def _reader(packet_id, handler_name):
    """Client packets of `packet_id` go to conn.<handler_name>(data), data
    from the sub-packet id on. Registered once, whichever script is first."""
    if packet_id not in _packet._client_loaders:
        class _In(_Loader):
            id = packet_id

            def read(self, reader):
                self.data = reader.read()
        _packet.register_packet(_In, server=False)

    loader = _packet._client_loaders[packet_id]
    prev = _packet._packet_handlers.get(packet_id)

    def handler(conn, contained):
        fn = getattr(conn, handler_name, None)
        if fn is not None:
            fn(bytes(getattr(contained, 'data', b'')))
        elif prev is not None:
            prev(conn, contained)
    _packet._packet_handlers[packet_id] = handler


def _f32(v):
    return _struct.pack('<f', v)


def _bgr(c):
    """(r, g, b) or {'r':, 'g':, 'b':} as the B G R bytes the packets carry."""
    if isinstance(c, dict):
        r, g, b = c.get('r', 0), c.get('g', 0), c.get('b', 0)
    else:
        r, g, b = c
    return bytes((int(b) & 255, int(g) & 255, int(r) & 255))


def _clean(text, limit):
    """UTF-8, no control bytes, cut to `limit` bytes on a character boundary."""
    if isinstance(text, bytes):
        try:
            text = text.decode('utf-8')
        except UnicodeDecodeError:
            text = ''
    text = ''.join(ch for ch in str(text or '') if ord(ch) >= 32 and ord(ch) != 127)
    data = text.encode('utf-8')[:limit]
    return data.decode('utf-8', 'ignore').encode('utf-8')
# ---------------------------------------------------------------------------

EXTENSION_ID = 48
PACKET_ID = 64 + EXTENSION_ID  # 112
SUB_CONFIG, SUB_PING, SUB_MARK = 0, 1, 2
SURFACES_MARK = 1 + 2          # the world and the minimap
SURFACES_ALL = 1 + 2 + 4       # and the compass
PING_EVERY = 1.0

section = config.section('teamplay')
FEATURES = section.option('features', 7)
NORTH = section.option('north', [0.0, -1.0])
PING_SECONDS = section.option('ping_seconds', 10.0)
PING_COLOURS = section.option('ping_colours', {'blue': [48, 112, 255], 'green': [48, 224, 64]})


def _team_colour(team):
    colours = PING_COLOURS.get() or {}
    key = 'green' if getattr(team, 'id', 0) == 1 else 'blue'
    return tuple(colours.get(key) or (48, 112, 255))


def _targets(protocol, to):
    if to is None:
        return list(protocol.players.values())
    if isinstance(to, (list, tuple, set)):
        return list(to)
    return [to]


def ping_packet(sender, x, y, z, seconds, surfaces, colour, label):
    return (bytes((PACKET_ID, SUB_PING, sender)) + _f32(x) + _f32(y) + _f32(z)
            + _f32(seconds) + bytes((surfaces,)) + _bgr(colour) + b'\0'
            + _clean(label, 64))


@command('pingmark')
def pingmark(connection, *args):
    """
    Mark a place for your team
    /pingmark <x> <y> <z> [reason]
    """
    if not _has(connection, EXTENSION_ID):
        return 'Unknown command'
    try:
        x, y, z = (float(a) for a in args[:3])
    except (TypeError, ValueError):
        return 'Nothing there to mark: /pingmark <x> <y> <z> [reason].'
    if len(args) < 3:
        return 'Nothing there to mark: /pingmark <x> <y> <z> [reason].'
    return connection.teamplay_request_ping(x, y, z, ' '.join(args[3:]))


def apply_script(protocol, connection, config):
    _hook_extinfo()
    _reader(PACKET_ID, 'on_teamplay_packet')

    class TeamplayProtocol(protocol):
        def __init__(self, *args, **kwargs):
            protocol.__init__(self, *args, **kwargs)
            _offer(self, EXTENSION_ID)

        def teamplay_mark(self, target, on, label='', colour=(255, 255, 255),
                          flags=1, to=None, seconds=None):
            secs = (math.inf if seconds is None else float(seconds)) if on else 0.0
            data = (bytes((PACKET_ID, SUB_MARK, target.player_id)) + _f32(secs)
                    + bytes((SURFACES_MARK, flags)) + _bgr(colour) + b'\0'
                    + _clean(label, 64))
            sent = 0
            for conn in _targets(self, to):
                if _has(conn, EXTENSION_ID):
                    conn.send_contained(_Raw(data))
                    sent += 1
            return sent

        def teamplay_server_ping(self, x, y, z, label='', colour=(255, 255, 255),
                                 seconds=10.0, to=None):
            data = ping_packet(255, x, y, z, float(seconds), SURFACES_ALL, colour, label)
            sent = 0
            for conn in _targets(self, to):
                if _has(conn, EXTENSION_ID):
                    conn.send_contained(_Raw(data))
                    sent += 1
            return sent

    class TeamplayConnection(connection):
        _tp_last_ping = 0.0

        def aosf_extensions_known(self):
            parent = getattr(super(), 'aosf_extensions_known', None)
            if parent is not None:
                parent()
            self.send_teamplay_config()

        def send_teamplay_config(self):
            if not _has(self, EXTENSION_ID):
                return
            north = NORTH.get() or [0.0, -1.0]
            self.send_contained(_Raw(bytes((PACKET_ID, SUB_CONFIG, int(FEATURES.get()) & 255))
                                     + _f32(float(north[0])) + _f32(float(north[1]))))

        def teamplay_request_ping(self, x, y, z, reason=''):
            """A ping this player asked for: None when sent, else why not."""
            if (self.world_object is None or not self.hp or self.team is None
                    or self.team.spectator):
                return 'Only the living can ping.'
            if not all(math.isfinite(v) for v in (x, y, z)):
                return 'That is not a place.'
            if not (0 <= x <= 512 and 0 <= y <= 512 and 0 <= z <= 64):
                return 'That is off the map.'
            now = time.monotonic()
            if now - self._tp_last_ping < PING_EVERY:
                return 'One ping a second.'
            self._tp_last_ping = now
            data = (bytes((PACKET_ID, SUB_PING, self.player_id)) + _f32(x) + _f32(y) + _f32(z)
                    + _f32(float(PING_SECONDS.get())) + b'\0' + _bgr(_team_colour(self.team))
                    + b'\0' + _clean(reason, 64))
            for conn in list(self.protocol.players.values()):
                if conn.team is self.team and _has(conn, EXTENSION_ID):
                    conn.send_contained(_Raw(data))
            return None

        def on_teamplay_packet(self, data):
            # Only Ping comes from a client; it is refused silently. The
            # reason is what follows the message id (byte 23 of the packet).
            if not data or data[0] != SUB_PING or len(data) < 23 or not _has(self, EXTENSION_ID):
                return
            x, y, z = _struct.unpack_from('<fff', data, 2)
            self.teamplay_request_ping(x, y, z, data[23:])

    return TeamplayProtocol, TeamplayConnection
