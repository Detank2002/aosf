# Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
# SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
# terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
# distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Player Outfit (extension 53): the outfit a team, or one player, wears, for
clients that take it (ZeroSpades, XRSpades). The spec is awaiting
(aosprotocol pull request #14); see specs/player-outfit.md.

    sub 0 Set Outfit  : player id, outfit, colour (255: the player's own team's)
    sub 1 Team Outfits: (team, outfit) pairs; a team not listed wears 0

A client is sent the team outfits and every player's own as soon as its
extensions are known, and again when it joins.

Options
^^^^^^^

.. code-block:: toml

    [player_outfit]
    teams = { green = "zombie" }    # blue, green or spectator -> a name or number

Other scripts
^^^^^^^^^^^^^

    protocol.set_team_outfit(team, outfit)    # a Team, or "blue"/"green"/"spectator"
    protocol.team_outfit(team)
    protocol.set_player_outfit(conn, outfit)  # OUTFIT_TEAM (255): back to the team's
"""
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

EXTENSION_ID = 53
PACKET_ID = 64 + EXTENSION_ID  # 117
SUB_SET, SUB_TEAMS = 0, 1
OUTFIT_TEAM = 255

OUTFITS = {
    'soldier': 0, 'scout': 1, 'ghillie': 2, 'bodyguard': 3, 'terrorist': 4, 'convict': 5,
    'brawler': 6, 'miner': 7, 'builder': 8, 'scientist': 9, 'butcher': 10, 'royal': 11,
    'robot': 12, 'vampire': 13, 'mummy': 14, 'demon': 15, 'god': 16, 'mascot': 17,
    'tiger': 18, 'penguin': 19, 'bear': 20, 'unicorn': 21, 'trex': 22, 'banana': 23,
    'blockstack': 24,
    'zombie': 64, 'spitter': 65, 'leaper': 66, 'caller': 67, 'breaker': 68, 'toppler': 69,
    'turret': 80, 'projector': 81, 'dishantenna': 82, 'mastantenna': 83,
    'undead': 64,
}

section = config.section('player_outfit')
TEAMS = section.option('teams', {})


def outfit_number(v):
    if isinstance(v, str):
        v = OUTFITS.get(v.lower(), v)
        try:
            v = int(v)
        except ValueError:
            return None
    if not isinstance(v, int) or not 0 <= v <= 255:
        return None
    return v


def wire_team(team):
    """A Team (or 'blue', 'green', 'spectator') as the packets carry it."""
    if isinstance(team, str):
        return {'blue': 0, 'green': 1, 'spectator': 255, 'spectators': 255}.get(team.lower())
    if getattr(team, 'spectator', False):
        return 255
    return getattr(team, 'id', None)


def apply_script(protocol, connection, config):
    _hook_extinfo()

    class OutfitProtocol(protocol):
        def __init__(self, *args, **kwargs):
            protocol.__init__(self, *args, **kwargs)
            _offer(self, EXTENSION_ID)
            self._outfit_teams = {}
            self._outfit_players = {}
            for k, v in (TEAMS.get() or {}).items():
                t, o = wire_team(str(k)), outfit_number(v)
                if t is None or o is None or o == OUTFIT_TEAM:
                    print('[player_outfit] ignoring %s = %s' % (k, v))
                elif o != 0:
                    self._outfit_teams[t] = o

        def _outfit_teams_packet(self):
            data = bytearray((PACKET_ID, SUB_TEAMS))
            for t, o in self._outfit_teams.items():
                data += bytes((t, o))
            return bytes(data)

        def _outfit_to_all(self, data):
            for conn in list(self.connections.values()):
                if _has(conn, EXTENSION_ID):
                    conn.send_contained(_Raw(data))

        def set_team_outfit(self, team, outfit):
            o = outfit_number(outfit)
            t = wire_team(team)
            if o is None or t is None:
                raise ValueError('unknown outfit or team: %r %r' % (outfit, team))
            if o == 0:
                self._outfit_teams.pop(t, None)
            else:
                self._outfit_teams[t] = o
            self._outfit_to_all(self._outfit_teams_packet())

        def team_outfit(self, team):
            return self._outfit_teams.get(wire_team(team), 0)

        def set_player_outfit(self, conn, outfit):
            o = outfit_number(outfit)
            if o is None:
                raise ValueError('unknown outfit: %r' % (outfit,))
            pid = conn.player_id
            if o == OUTFIT_TEAM and pid not in self._outfit_players:
                return
            if o == OUTFIT_TEAM:
                self._outfit_players.pop(pid, None)
            else:
                self._outfit_players[pid] = o
            self._outfit_to_all(bytes((PACKET_ID, SUB_SET, pid, o, 255)))

    class OutfitConnection(connection):
        def aosf_extensions_known(self):
            parent = getattr(super(), 'aosf_extensions_known', None)
            if parent is not None:
                parent()
            self.send_outfits()

        def send_outfits(self):
            if not _has(self, EXTENSION_ID):
                return
            self.send_contained(_Raw(self.protocol._outfit_teams_packet()))
            for pid, o in self.protocol._outfit_players.items():
                self.send_contained(_Raw(bytes((PACKET_ID, SUB_SET, pid, o, 255))))

        def on_join(self):
            connection.on_join(self)
            self.send_outfits()

        def on_disconnect(self):
            # A client forgets a player's outfit when they leave; so do we.
            if self.player_id is not None:
                self.protocol._outfit_players.pop(self.player_id, None)
            connection.on_disconnect(self)

    return OutfitProtocol, OutfitConnection
