# Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
# SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
# terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
# distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Damage Markers (extension 32): after each hit, the attacker is told what it
did, for clients that take it (ZeroSpades, XRSpades). Spec:
protocol/extensions/damage-markers.md.

The amount is the health the victim lost (a kill counts what they had left),
and a heal is negative: whatever the server applied, whichever script changed
the damage on the way.
"""

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

EXTENSION_ID = 32
PACKET_ID = 64 + EXTENSION_ID  # 96


def damage_marker_packet(victim_id, amount):
    if 0 <= amount <= 255:
        return bytes((PACKET_ID, victim_id, amount))
    if -32768 <= amount <= 32767:
        return bytes((PACKET_ID, victim_id)) + _struct.pack('<h', amount)
    return bytes((PACKET_ID, victim_id)) + _struct.pack('<i', max(-2**31, min(2**31 - 1, amount)))


def apply_script(protocol, connection, config):
    class DamageMarkersProtocol(protocol):
        def __init__(self, *args, **kwargs):
            protocol.__init__(self, *args, **kwargs)
            _offer(self, EXTENSION_ID)

    class DamageMarkersConnection(connection):
        def set_hp(self, value, *args, **kwargs):
            hit_by = args[0] if args else kwargs.get('hit_by')
            before = self.hp
            connection.set_hp(self, value, *args, **kwargs)
            if (hit_by is None or hit_by is self or before is None
                    or getattr(hit_by, 'disconnected', False) or not _has(hit_by, EXTENSION_ID)):
                return
            amount = int(before) - int(self.hp or 0)
            if amount != 0:
                hit_by.send_contained(_Raw(damage_marker_packet(self.player_id, amount)))

    return DamageMarkersProtocol, DamageMarkersConnection
