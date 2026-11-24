# Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
# SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
# terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
# distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Flashlight (extension 0x32): a light a player carries, seen by everyone whose
client takes it (ZeroSpades, XRSpades). Spec: protocol/extensions/flashlight.md.

    sub 0 Light       : player, state   (a client asks for its own; relayed)
    sub 1 Light State : a bit per player id, to a joining client
    sub 2 Light Config: one player's beam (255: everyone's)

Every request is honoured and relayed to every client that takes it, the
sender included (its own light only comes on when the relay arrives).

Options
^^^^^^^

.. code-block:: toml

    [flashlight]
    # Everybody's beam, sent as each client's extensions are known; leave it
    # out for the client's own. reach: blocks at which the light reaches zero
    # (1-255); cone: full angle in pi/256 (128 is 90 degrees).
    beam = { reach = 110, cone = 150, color = [255, 235, 205], flicker = 0 }

Other scripts
^^^^^^^^^^^^^

    protocol.set_light(conn, on, beam=None)   # the server puts a light on a player,
                                              # with a beam of its own if given
"""
from piqueserver.config import config
from twisted.internet import reactor

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

EXTENSION_ID = 0x32
PACKET_ID = 64 + EXTENSION_ID  # 114
SUB_LIGHT, SUB_STATE, SUB_BEAM = 0, 1, 2

section = config.section('flashlight')
BEAM = section.option('beam', {})


def _byte(v, default):
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = default
    return max(0, min(255, v))


def beam_packet(beam, pid=255):
    if not isinstance(beam, dict) or beam.get('reach') is None:
        return None
    c = beam.get('color') or [255, 179, 128]
    if isinstance(c, dict):
        c = [c.get('r', 255), c.get('g', 179), c.get('b', 128)]
    return bytes((PACKET_ID, SUB_BEAM, pid, _byte(beam.get('reach'), 60), _byte(beam.get('cone'), 128),
                  _byte(c[0], 255), _byte(c[1], 179), _byte(c[2], 128), _byte(beam.get('flicker'), 0)))


def apply_script(protocol, connection, config):
    _hook_extinfo()
    _reader(PACKET_ID, 'on_flashlight_packet')

    class FlashlightProtocol(protocol):
        def __init__(self, *args, **kwargs):
            protocol.__init__(self, *args, **kwargs)
            _offer(self, EXTENSION_ID)
            self._lights = set()
            self._own_beams = {}

        def _light_relay(self, pid, on):
            data = bytes((PACKET_ID, SUB_LIGHT, pid, 1 if on else 0))
            for conn in list(self.connections.values()):
                if _has(conn, EXTENSION_ID):
                    conn.send_contained(_Raw(data))

        def _light_to_joined(self, data):
            for conn in list(self.players.values()):
                if _has(conn, EXTENSION_ID):
                    conn.send_contained(_Raw(data))

        def set_light(self, conn, on, beam=None):
            pid = conn.player_id
            if on and isinstance(beam, dict):
                self._own_beams[pid] = beam
                data = beam_packet(beam, pid)
                if data:
                    self._light_to_joined(data)
            elif not on and pid in self._own_beams:
                del self._own_beams[pid]
                back = beam_packet(BEAM.get(), pid)
                if back:
                    self._light_to_joined(back)
            if on:
                self._lights.add(pid)
            else:
                self._lights.discard(pid)
            self._light_relay(pid, on)

    class FlashlightConnection(connection):
        def aosf_extensions_known(self):
            parent = getattr(super(), 'aosf_extensions_known', None)
            if parent is not None:
                parent()
            data = beam_packet(BEAM.get())
            if data and _has(self, EXTENSION_ID):
                self.send_contained(_Raw(data))

        def on_flashlight_packet(self, data):
            if len(data) < 3 or data[0] != SUB_LIGHT or not _has(self, EXTENSION_ID):
                return
            on = data[2] != 0
            lights = self.protocol._lights
            if on:
                lights.add(self.player_id)
            else:
                lights.discard(self.player_id)
            self.protocol._light_relay(self.player_id, on)   # asked again: said again

        def on_join(self):
            connection.on_join(self)
            if not _has(self, EXTENSION_ID):
                return
            # The lights already on, with the beams of their own first.
            for pid, beam in self.protocol._own_beams.items():
                data = beam_packet(beam, pid)
                if data:
                    self.send_contained(_Raw(data))
            bits = bytearray(32)
            for pid in self.protocol._lights:
                if 0 <= pid < 256:
                    bits[pid // 8] |= 1 << (pid % 8)
            self.send_contained(_Raw(bytes((PACKET_ID, SUB_STATE)) + bytes(bits)))

        def on_disconnect(self):
            pid = self.player_id
            proto = self.protocol
            if pid is not None:
                proto._own_beams.pop(pid, None)   # (a client forgets it on Player Left)
                if pid in proto._lights:
                    proto._lights.discard(pid)
                    reactor.callLater(0, proto._light_relay, pid, False)
            connection.on_disconnect(self)

    return FlashlightProtocol, FlashlightConnection
