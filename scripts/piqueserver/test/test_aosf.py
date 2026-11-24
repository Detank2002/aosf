#!/usr/bin/env python3
"""
The AOSF piqueserver scripts on a real piqueserver, from fake clients that
speak just enough of AoS 0.75 to join (after XRSpades' test_vr_presence.py),
and their packets byte for byte against the lsd scripts in ../../lsd.

    python3 test/test_aosf.py      (from scripts/piqueserver, with piqueserver
                                    installed; luajit for the lsd comparison)

What it holds:
  - every extension is offered, and a client is told only what it took;
  - Teamplay's Config, the sky, the team outfits and the beam reach a client
    that took them as soon as its extensions are known;
  - a ping reaches the sender's team only, in the team's colour;
  - a flashlight switched on is relayed to every client that took it;
  - a client that took Compact World Update gets it, and the rest World Update;
  - pie menus, smoke, damage markers, outfits and compact entries are built
    exactly as the lsd scripts build them.
"""
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
LSD = os.path.join(os.path.dirname(SCRIPTS), 'lsd')
sys.path.insert(0, SCRIPTS)

import enet  # noqa: E402

import compact_world_update  # noqa: E402
import damage_markers  # noqa: E402
import pie_menu  # noqa: E402
import smoke  # noqa: E402

NAMES = ['teamplay', 'damage_markers', 'player_outfit', 'pie_menu', 'flashlight',
         'daytime', 'smoke', 'compact_world_update', 'vr_presence']
ALL = {48, 32, 53, 0x31, 0x32, 0x33, 0x3F, 0x3E, 58}


class FakeClient:
    def __init__(self, port, name, extensions):
        self.host = enet.Host(None, 1, 1)
        self.host.compress_with_range_coder()
        self.peer = self.host.connect(enet.Address(b'127.0.0.1', port), 1, 3)
        self.name = name
        self.extensions = extensions
        self.player_id = None
        self.map_done = False
        self.packets = []
        self.server_extensions = None

    def send(self, data, reliable=True):
        flags = enet.PACKET_FLAG_RELIABLE if reliable else enet.PACKET_FLAG_UNSEQUENCED
        self.peer.send(0, enet.Packet(bytes(data), flags))

    def pump(self, seconds=0.05):
        end = time.time() + seconds
        while True:
            event = self.host.service(5)
            while event is not None and event.type != enet.EVENT_TYPE_NONE:
                if event.type == enet.EVENT_TYPE_RECEIVE:
                    self.handle(bytes(event.packet.data))
                event = self.host.service(0)
            if time.time() >= end:
                return

    def handle(self, data):
        kind = data[0]
        self.packets.append(data)
        if kind == 31 and len(data) >= 5:
            self.send(bytes((32,)) + data[1:5])
        elif kind == 33:
            self.send(bytes((34,)) + b'o' + bytes((0, 1, 5)) + b'AOSF test\0')
        elif kind == 60:
            count = data[1]
            offered = {data[2 + 2 * i]: data[3 + 2 * i] for i in range(count)}
            self.server_extensions = offered
            reply = [(k, v) for k, v in offered.items() if k in self.extensions]
            self.send(bytes((60, len(reply))) + b''.join(bytes(e) for e in reply))
        elif kind == 15:
            self.player_id = data[1]
            self.map_done = True

    def join(self, team):
        self.send(bytes((9, 0, team & 0xFF, 0, 0)) + struct.pack('<I', 0) +
                  bytes((0, 0, 0)) + self.name.encode() + b'\0')

    def of(self, packet_id, sub=None):
        return [p for p in self.packets
                if p[0] == packet_id and (sub is None or (len(p) > 1 and p[1] == sub))]


def free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pyspades.vxl import VXLData

        cls.dir = tempfile.mkdtemp(prefix='aosf_')
        os.makedirs(os.path.join(cls.dir, 'maps'))
        os.makedirs(os.path.join(cls.dir, 'scripts'))
        with open(os.path.join(cls.dir, 'maps', 'flat.vxl'), 'wb') as f:
            f.write(VXLData().generate())
        for name in NAMES:
            shutil.copy(os.path.join(SCRIPTS, name + '.py'), os.path.join(cls.dir, 'scripts'))
        cls.port = free_udp_port()
        with open(os.path.join(cls.dir, 'config.toml'), 'w') as f:
            f.write(f'''name = "aosf test"
master = false
port = {cls.port}
max_connections_per_ip = 8
rotation = ["flat"]
scripts = {NAMES!r}
game_mode = "ctf"
respawn_time = "1sec"
respawn_waves = false
balanced_teams = 0
fall_damage = false
[player_outfit]
teams = {{ green = "zombie" }}
[flashlight]
beam = {{ reach = 110, cone = 150, color = [255, 235, 205], flicker = 0 }}
'''.replace("'", '"'))
        cls.server = subprocess.Popen([sys.executable, '-m', 'piqueserver', '-d', cls.dir],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        time.sleep(3.0)
        if cls.server.poll() is not None:
            raise RuntimeError(cls.server.stdout.read().decode())
        cls.a = FakeClient(cls.port, 'alpha', ALL)          # blue, takes everything
        cls.b = FakeClient(cls.port, 'bravo', ALL)          # blue too
        cls.g = FakeClient(cls.port, 'golf', ALL)           # green
        cls.stock = FakeClient(cls.port, 'stock', set())    # green, takes nothing
        cls.clients = [cls.a, cls.b, cls.g, cls.stock]
        deadline = time.time() + 20
        while not all(c.map_done for c in cls.clients):
            for c in cls.clients:
                c.pump(0.02)
            if time.time() > deadline:
                raise RuntimeError('clients never received the map')
        for c, team in ((cls.a, 0), (cls.b, 0), (cls.g, 1), (cls.stock, 1)):
            c.join(team)
        deadline = time.time() + 20
        while not all(any(p[0] == 12 and p[1] == c.player_id for p in cls.a.packets)
                      for c in cls.clients):
            cls.pump_all(0.1)
            if time.time() > deadline:
                raise RuntimeError('the players never spawned')
        cls.pump_all(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        try:
            out, _ = cls.server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            out, _ = cls.server.communicate()
        if os.environ.get('AOSF_TEST_SERVER_LOG'):
            print(out.decode(errors='replace'))
        shutil.rmtree(cls.dir, ignore_errors=True)

    @classmethod
    def pump_all(cls, seconds):
        end = time.time() + seconds
        while time.time() < end:
            for c in cls.clients:
                c.pump(0.01)

    def clear(self):
        for c in self.clients:
            c.packets.clear()

    def test_1_every_extension_is_offered(self):
        for ext in ALL | {193, 194}:
            self.assertIn(ext, self.a.server_extensions, ext)

    def test_2_start_of_connection(self):
        # Sent before the clear below: kept from setUpClass.
        cfg = self.a.of(112, 0)
        self.assertTrue(cfg, 'no Teamplay Config')
        self.assertEqual(cfg[0], bytes((112, 0, 7)) + struct.pack('<ff', 0.0, -1.0))
        self.assertIn(bytes((115, 0, 720 % 256, 720 // 256, 0, 0, 0, 0)), self.a.of(115, 0))
        self.assertIn(bytes((117, 1, 1, 64)), self.a.of(117, 1))
        self.assertIn(bytes((114, 2, 255, 110, 150, 255, 235, 205, 0)), self.a.of(114, 2))
        self.assertTrue(self.a.of(114, 1), 'no Light State on join')
        for pid in (112, 114, 115, 117):
            self.assertEqual(self.stock.of(pid), [], pid)

    def test_3_ping_reaches_the_team_only(self):
        deadline = time.time() + 10
        while True:
            self.clear()
            self.a.send(bytes((112, 1, self.a.player_id)) + struct.pack('<ffff', 100.0, 120.0, 30.0, 0.0)
                        + bytes((0, 0, 0, 0, 0)) + b'here')
            self.pump_all(0.5)
            got = self.b.of(112, 1)
            if got or time.time() > deadline:
                break
            time.sleep(1.1)
        self.assertEqual(len(got), 1)
        p = got[0]
        self.assertEqual(p[2], self.a.player_id)
        self.assertEqual(struct.unpack_from('<fff', p, 3), (100.0, 120.0, 30.0))
        self.assertEqual(p[20:23], bytes((0xFF, 0x70, 0x30)))   # blue, as B G R
        self.assertEqual(p[24:], b"here")
        self.assertEqual(len(self.a.of(112, 1)), 1)              # the sender too
        self.assertEqual(self.g.of(112, 1), [])                  # not the other team

    def test_4_flashlight_is_relayed(self):
        self.clear()
        self.g.send(bytes((114, 0, self.g.player_id, 1)))
        self.pump_all(0.6)
        want = bytes((114, 0, self.g.player_id, 1))
        for c in (self.a, self.b, self.g):
            self.assertIn(want, c.of(114, 0))
        self.assertEqual(self.stock.of(114), [])

    def test_5_compact_world_update(self):
        self.clear()
        self.pump_all(0.6)
        compact = self.a.of(126)
        self.assertTrue(compact, 'no Compact World Update')
        ids = {compact[-1][3 + 10 * i] for i in range((len(compact[-1]) - 3) // 10)}
        self.assertTrue({self.a.player_id, self.g.player_id} <= ids, ids)
        self.assertEqual(self.a.of(2), [])          # no World Update for it
        self.assertTrue(self.stock.of(2))           # World Update for the stock client
        self.assertEqual(self.stock.of(126), [])
        seqs = [struct.unpack_from('<H', p, 1)[0] for p in compact]
        self.assertEqual(seqs, sorted(seqs))


class LsdBytesTest(unittest.TestCase):
    """The same packets from the lsd scripts (run under luajit with lsd stubbed)."""

    LUA = r'''
package.path = "./?.lua;" .. package.path
MAX_PLAYERS, SPECTATOR, PID_BROADCAST = 32, 255, 0x20000000
function get_time() return 1000 end
function init_mod() local m = {} for _, k in ipairs{"impl", "late", "early", "xearly"} do m[k] = {before={}, after={}, next={}} end
  m.before, m.after, m.next = {}, {}, {} return m end
function getcfg(k, v) if _G[k] == nil then _G[k] = v end end
function log() end
function pid_connected_table() return {} end
function register_command() end
local sent = {}
function piditer() local done = false return function() if done then return nil end done = true return 1 end end
function send_packet(pid, d) sent[#sent + 1] = d end
function is_connected() return true end
function is_alive() return true end
function get_hp() return 55 end
dofile("ext_core.lua").on_load()
dofile("ext_pie_menu.lua").on_load()
dofile("ext_smoke.lua")
dofile("ext_damage_markers.lua")
aosext.has = function() return true end
local function hex(s) return (s:gsub(".", function(c) return string.format("%02x", c:byte()) end)) end
print("pie " .. hex(aosext.pie_menu_packet({{contexts=4, theme="Caf\195\169", slices={
  {text="/strike", label="Strike", tooltip="Shells"}, nil, {text="Hi", global=true}, nil,
  {text="/pingmark %h Here", label="Here"}, nil}}})))
aosext.smoke{x=100.5, y=200.25, z=30, style="column", radius=6, r=255, g=0, b=0, opacity=180, duration=7.5, fade=2, hiss=true, id=4}
print("smoke " .. hex(sent[#sent]))
print("dmg " .. hex(aosext.damage_marker_packet(7, 45)) .. " " .. hex(aosext.damage_marker_packet(7, -300)) .. " " .. hex(aosext.damage_marker_packet(7, 70000)))
'''

    def test_same_bytes_as_lsd(self):
        luajit = shutil.which('luajit')
        if luajit is None or not os.path.isdir(LSD):
            self.skipTest('luajit or the lsd scripts not here')
        out = subprocess.check_output([luajit, '-e', self.LUA], cwd=LSD).decode()
        lua = dict(line.split(' ', 1) for line in out.strip().splitlines())
        py_pie = pie_menu.pie_menu_packet([{'contexts': 4, 'theme': 'Café', 'slices': [
            {'text': '/strike', 'label': 'Strike', 'tooltip': 'Shells'}, None,
            {'text': 'Hi', 'global': True}, None, {'text': '/pingmark %h Here', 'label': 'Here'}, None]}])
        self.assertEqual(py_pie.hex(), lua['pie'])
        py_smoke = smoke.smoke_packet(4, dict(x=100.5, y=200.25, z=30.0, style='column', radius=6, r=255,
                                              g=0, b=0, opacity=180, fade=2, hiss=True), 7.5)
        self.assertEqual(py_smoke.hex(), lua['smoke'])
        py_dmg = ' '.join(damage_markers.damage_marker_packet(7, a).hex() for a in (45, -300, 70000))
        self.assertEqual(py_dmg, lua['dmg'])

    def test_compact_entry(self):
        # 100.5 -> 6432; z 36.749 + 128 rounded up the map (down): 10543; -0.5 -> -63 (0xc1).
        e = compact_world_update.entry(5, (100.5, 200.25, 36.749), (1.0, 0.0, -0.5))
        self.assertEqual(e, bytes((5,)) + struct.pack('<HHH', 6432, 12816, 10543) + bytes((127, 0, 193)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
