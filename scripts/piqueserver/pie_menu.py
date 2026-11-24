# Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
# SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
# terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
# distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Pie Menu (extension 0x31): the server's own radial menu, for clients that
take it (ZeroSpades, XRSpades). Spec: protocol/extensions/pie-menu.md.

A menu is a list of pies; the client shows the pies whose contexts take what
the player aims at, the first one first:

    menu  = [pie, ...]                       (0-255 pies)
    pie   = {'contexts': PIE_WORLD, 'theme': "...", 'slices': [slice x6]}
    slice = {'text': "/cmd or chat", 'label': "...", 'tooltip': "...",
             'global': False}  or None (blank)

A text may use %p (the player aimed at, #id), %b (the block), %h (the point
aimed at), %r (the camera ray) and %%.

Other scripts
^^^^^^^^^^^^^

    connection.set_pie_menu(menu)   # sent when it differs from the last
    PIE_BLOCK, PIE_TEAMMATE, PIE_ENEMY, PIE_SPECTATOR, PIE_DEAD, PIE_SKY, PIE_WORLD
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

EXTENSION_ID = 0x31
PACKET_ID = 64 + EXTENSION_ID  # 113

PIE_BLOCK, PIE_TEAMMATE, PIE_ENEMY, PIE_SPECTATOR, PIE_DEAD, PIE_SKY = 1, 2, 4, 8, 16, 32
PIE_WORLD = PIE_BLOCK + PIE_SKY


def _pie_string(text, is_text=False):
    """No NUL; in a Text no control bytes either. Printable ASCII as it is
    (it is Code Page 437 too), anything else as UTF-8 behind 0xff."""
    text = str(text or '')
    if is_text:
        text = ''.join(ch for ch in text if ord(ch) >= 32 and ord(ch) != 127)
    else:
        text = text.replace('\0', '')
    if all(32 <= ord(ch) < 127 for ch in text):
        return text.encode('ascii') + b'\0'
    return b'\xff' + text.encode('utf-8') + b'\0'


def pie_menu_packet(menu):
    menu = list(menu or [])[:255]
    data = bytearray((PACKET_ID, 0, len(menu)))
    for pie in menu:
        data += bytes((int(pie.get('contexts', PIE_WORLD)) & 255, 0)) + _pie_string(pie.get('theme'))
        slices = list(pie.get('slices') or [])
        for k in range(6):
            sl = (slices[k] if k < len(slices) else None) or {}
            data += bytes((0, 1 if sl.get('global') else 0))
            data += _pie_string(sl.get('text'), True) + _pie_string(sl.get('label')) \
                + _pie_string(sl.get('tooltip'))
    return bytes(data)


def apply_script(protocol, connection, config):
    class PieMenuProtocol(protocol):
        def __init__(self, *args, **kwargs):
            protocol.__init__(self, *args, **kwargs)
            _offer(self, EXTENSION_ID)

    class PieMenuConnection(connection):
        _pie_sent = None

        def set_pie_menu(self, menu):
            if not _has(self, EXTENSION_ID):
                return
            data = pie_menu_packet(menu)
            if data != self._pie_sent:
                self._pie_sent = data
                self.send_contained(_Raw(data))

    return PieMenuProtocol, PieMenuConnection
