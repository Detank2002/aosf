# Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
# SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
# terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
# distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Smoke (extension 0x3F): clouds and columns the server puts in the world, for
clients that take it (XRSpades). Spec: specs/smoke.md.

Smoke is only drawn, by the clients that take it, so use it for a marker or
an effect, never for cover the game depends on. Map Start clears it on every
client; a player who joins while one is still coming is sent it with what is
left of it.

Commands
^^^^^^^^

* ``/smoke [column]`` (admin) a smoke where you stand, to try it

Other scripts
^^^^^^^^^^^^^

    protocol.smoke(x, y, z, style="cloud"|"column", radius=5, r=210, g=210, b=210,
                   opacity=200, duration=10, fade=3, hiss=False, id=None)
        id None: one from the pool; 0-254; False: fire and forget (not kept).
        Returns the id (255 for fire and forget).
    protocol.clear_smoke(id=None)   # None: all
"""
import time

from piqueserver.commands import command

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

EXTENSION_ID = 0x3F
PACKET_ID = 64 + EXTENSION_ID  # 127
NONE = 255


def _b(v, lo, hi):
    try:
        v = int(float(v) + 0.5)
    except (TypeError, ValueError):
        v = lo
    return max(lo, min(hi, v))


def smoke_packet(sid, spec, duration):
    d = _b(duration * 10, 0, 65535)
    return (bytes((PACKET_ID, 0, sid, 1 if spec.get('style') == 'column' else 0))
            + _f32(spec['x']) + _f32(spec['y']) + _f32(spec['z'])
            + bytes((_b(spec.get('radius', 5), 1, 255),
                     _b(spec.get('r', 210), 0, 255), _b(spec.get('g', 210), 0, 255),
                     _b(spec.get('b', 210), 0, 255), _b(spec.get('opacity', 200), 0, 255),
                     d % 256, d // 256, _b(spec.get('fade', 3) * 10, 0, 255),
                     1 if spec.get('hiss') else 0)))


@command('smoke', admin_only=True)
def smoke_command(connection, style='cloud'):
    """
    A smoke where you stand, to try it
    /smoke [column]
    """
    if connection.world_object is None:
        return 'Spawn first.'
    x, y, z = connection.world_object.position.get()
    connection.protocol.smoke(x, y, z, style='column' if style == 'column' else 'cloud')


def apply_script(protocol, connection, config):
    class SmokeProtocol(protocol):
        def __init__(self, *args, **kwargs):
            protocol.__init__(self, *args, **kwargs)
            _offer(self, EXTENSION_ID)
            self._smokes = {}      # id -> (spec, ends)

        def _smoke_to_all(self, data):
            for conn in list(self.connections.values()):
                if _has(conn, EXTENSION_ID):
                    conn.send_contained(_Raw(data))

        def _smoke_free_id(self):
            now = time.monotonic()
            for sid in range(255):
                s = self._smokes.get(sid)
                if s is None or now >= s[1] + float(s[0].get('fade', 3)):
                    return sid
            return NONE

        def smoke(self, x, y, z, id=None, **spec):
            spec.update(x=float(x), y=float(y), z=float(z))
            if id is False:
                sid = NONE
            elif id is None:
                sid = self._smoke_free_id()
            else:
                sid = _b(id, 0, 255)
            duration = max(0.0, float(spec.get('duration', 10)))
            if sid != NONE:
                self._smokes[sid] = (spec, time.monotonic() + duration)
            self._smoke_to_all(smoke_packet(sid, spec, duration))
            return sid

        def clear_smoke(self, id=None):
            sid = NONE if id is None else _b(id, 0, 255)
            if sid == NONE:
                self._smokes = {}
            else:
                self._smokes.pop(sid, None)
            self._smoke_to_all(bytes((PACKET_ID, 1, sid)))

        def on_map_change(self, the_map):
            # A new map: every client has forgotten them (Map Start), and so do we.
            self._smokes = {}
            return protocol.on_map_change(self, the_map)

    class SmokeConnection(connection):
        def on_join(self):
            connection.on_join(self)
            if not _has(self, EXTENSION_ID):
                return
            now = time.monotonic()
            for sid, (spec, ends) in list(self.protocol._smokes.items()):
                if now < ends:
                    self.send_contained(_Raw(smoke_packet(sid, spec, ends - now)))

    return SmokeProtocol, SmokeConnection
