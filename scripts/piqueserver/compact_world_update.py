# Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
# SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
# terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
# distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Compact World Update (extension 0x3E): where every living player is, in 10
bytes a player, in place of World Update for clients that take it (XRSpades,
ZeroSpades X 0.3.4+). Spec: specs/compact-world-update.md.

World Update carries 24 bytes for every slot up to the highest in use; the
compact one carries only the living, and goes unsequenced like piqueserver's
own World Update, so a lost one is simply replaced by the next. Everybody
else is sent World Update as before.

Options
^^^^^^^

.. code-block:: toml

    [compact_world_update]
    enabled = true     # false: offered, but World Update for everybody
"""
import math

from piqueserver.config import config
from pyspades import contained as loaders

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

EXTENSION_ID = 0x3E
PACKET_ID = 64 + EXTENSION_ID  # 126
PER_PACKET = 120               # 1203 bytes: under ENet's fragment size

section = config.section('compact_world_update')
ENABLED = section.option('enabled', True)


def _u16(v):
    return max(0, min(65535, int(math.floor(v * 64 + 0.5))))


def _u16_up(v):
    # Rounded up the map (towards the smaller z), never to the nearest: a body
    # on a floor rounded to the nearest can land exactly on it and climb.
    return max(0, min(65535, int(math.floor(v * 64))))


def _s8(v):
    n = max(-127, min(127, int(math.floor(v * 127 + 0.5))))
    return n & 255


def entry(pid, position, front):
    x, y, z = position
    fx, fy, fz = front
    return (bytes((pid,)) + _struct.pack('<HHH', _u16(x), _u16(y), _u16_up(z + 128))
            + bytes((_s8(fx), _s8(fy), _s8(fz))))


def apply_script(protocol, connection, config):
    class CompactProtocol(protocol):
        _compact_seq = 0

        def __init__(self, *args, **kwargs):
            protocol.__init__(self, *args, **kwargs)
            _offer(self, EXTENSION_ID)

        def _takes_compact(self, conn):
            return bool(ENABLED.get()) and _has(conn, EXTENSION_ID)

        def _compact_packets(self):
            entries = []
            for pid, player in sorted(self.players.items()):
                wo = getattr(player, 'world_object', None)
                if (wo is None or not player.hp or player.team is None or player.team.spectator
                        or getattr(player, 'filter_visibility_data', False)):
                    continue
                entries.append(entry(pid, wo.position.get(), wo.orientation.get()))
            packets = []
            for i in range(0, max(1, len(entries)), PER_PACKET):
                self._compact_seq = (self._compact_seq + 1) % 65536
                packets.append(bytes((PACKET_ID,)) + _struct.pack('<H', self._compact_seq)
                               + b''.join(entries[i:i + PER_PACKET]))
            return packets

        def update_network(self):
            if not len(self.players):
                return
            takers = [c for c in self.connections.values() if self._takes_compact(c)]
            if not takers:
                return protocol.update_network(self)
            for data in self._compact_packets():
                for conn in takers:
                    conn.send_contained(_Raw(data), sequence=True)   # True: unsequenced
            # World Update for everybody else, as pyspades builds it.
            items = []
            highest = max(self.players)
            for i in range(highest + 1):
                position = orientation = None
                try:
                    player = self.players[i]
                    if not player.filter_visibility_data and not player.team.spectator:
                        position = player.world_object.position.get()
                        orientation = player.world_object.orientation.get()
                except (KeyError, TypeError, AttributeError):
                    pass
                if position is None:
                    position = (0.0, 0.0, 0.0)
                    orientation = (0.0, 0.0, 0.0)
                items.append((position, orientation))
            world_update = loaders.WorldUpdate()
            world_update.items = items[:highest + 1]
            self.broadcast_contained(world_update, unsequenced=True,
                                     rule=lambda p: not self._takes_compact(p))

    return CompactProtocol, connection
