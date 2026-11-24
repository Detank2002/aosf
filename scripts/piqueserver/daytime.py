# Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
# SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
# terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
# distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Daytime and Weather (extension 0x33): night or day, for clients that take it
(ZeroSpades, XRSpades). Spec: protocol/extensions/daytime-weather.md.

A client that takes it draws nothing until its first Sky, so every one is
sent the sky in force as soon as its extensions are known (and again when it
joins).

Commands
^^^^^^^^

* ``/night [on|off]`` (admin) night or day for everybody

Options
^^^^^^^

.. code-block:: toml

    [daytime]
    night = false      # how it starts

Other scripts
^^^^^^^^^^^^^

    protocol.set_night(on), protocol.is_night()
    protocol.all_take_daytime(conns)   # whether all of them can be shown the night
"""
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

EXTENSION_ID = 0x33
PACKET_ID = 64 + EXTENSION_ID  # 115

section = config.section('daytime')
NIGHT = section.option('night', False)


def sky_packet(night):
    t = 0 if night else 720        # midnight, or noon
    return bytes((PACKET_ID, 0, t % 256, t // 256, 0, 0, 0, 0))


@command('night', admin_only=True)
def night_command(connection, value=None):
    """
    Night or day for everybody
    /night [on|off]
    """
    proto = connection.protocol
    on = (not proto.is_night()) if value is None else value.lower() in ('on', '1', 'true', 'yes')
    proto.set_night(on)
    return 'Night.' if on else 'Day.'


def apply_script(protocol, connection, config):
    _hook_extinfo()

    class DaytimeProtocol(protocol):
        def __init__(self, *args, **kwargs):
            protocol.__init__(self, *args, **kwargs)
            _offer(self, EXTENSION_ID)
            self._night = bool(NIGHT.get())

        def is_night(self):
            return self._night

        def set_night(self, on):
            on = bool(on)
            if on == self._night:
                return
            self._night = on
            for conn in list(self.connections.values()):
                conn.send_sky()

        def all_take_daytime(self, conns):
            conns = list(conns)
            return bool(conns) and all(_has(c, EXTENSION_ID) for c in conns)

    class DaytimeConnection(connection):
        def send_sky(self):
            if _has(self, EXTENSION_ID):
                self.send_contained(_Raw(sky_packet(self.protocol.is_night())))

        def aosf_extensions_known(self):
            parent = getattr(super(), 'aosf_extensions_known', None)
            if parent is not None:
                parent()
            self.send_sky()

        def on_join(self):
            connection.on_join(self)
            self.send_sky()

    return DaytimeProtocol, DaytimeConnection
