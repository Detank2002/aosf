-- ext_compact.lua -- the Compact World Update (extension 0x3E, XRSpades';
-- packet 126) for clients that take it (XRSpades, ZeroSpades X): where
-- everybody is, in place of lsd's World Update. 0x3E is past ZeroSpades' own
-- range, as its developers asked.
--
--   compact_world_update = true     false: offered, but lsd's update for all
--
-- lsd's World Update is 24 bytes for every slot up to the highest live one:
-- with players in slots 36-135 it is 3.2 KB, which ENet splits into three
-- reliable pieces, and on a lossy line every lost piece holds up everything
-- behind it. The compact one is a u16 sequence number (little-endian, one
-- more for each packet built) and then only the living, 10 bytes each:
--   u8 player id;
--   u16 x * 64, u16 y * 64, u16 (z + 128) * 64 (little-endian, 1/64 block);
--   s8 front x * 127, s8 front y * 127, s8 front z * 127.
-- A hundred living players come to about 1 KB: one unfragmented packet,
-- and a lost one is simply replaced by the next. It goes unsequenced
-- (send_packet_unsequenced, lsd-unsequenced.patch) where lsd has it: ENet
-- ties a plain unreliable packet to the reliable ones before it, and one of
-- those lost held up or dropped every update behind it (test server, 100
-- bots, 2% loss: worse than lsd's own update until then). The client drops
-- one overtaken by a newer one by the sequence number. Past
-- COMPACT_PER_PACKET living players it goes as more than one packet, each
-- complete in itself.
--
-- Everybody else (other clients, the fleet, the demo camera, which never
-- takes it) gets lsd's own World Update as before. /ups still decides how
-- often: this sits in the late chain, under command_ups.
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

X.EXT_COMPACT_WU = 0x3E;     -- past ZeroSpades' range (to 0x33) by ten, as its developers asked
local PACKET_COMPACT_WU = 64 + X.EXT_COMPACT_WU;     -- 126
-- ENet's fragment size is 1364 bytes (MTU 1392 less its headers); 120
-- entries is 1203 bytes, well under it.
local COMPACT_PER_PACKET = 120;

getcfg("compact_world_update", true);

local floor, char, concat = math.floor, string.char, table.concat;

local function u16(v)
	local n = floor(v * 64 + 0.5);
	if (n < 0) then n = 0; elseif (n > 65535) then n = 65535; end
	return char(n % 256, floor(n / 256));
end

local function s8(v)
	local n = floor(v * 127 + 0.5);
	if (n < -127) then n = -127; elseif (n > 127) then n = 127; end
	return n < 0 and n + 256 or n;
end

-- The height is rounded UP the map (z down, so towards the smaller z), never
-- to the nearest: a body standing on a floor is a hair above it (lsd sends
-- 36.749 over a floor at 39), and rounded to the nearest it came out exactly
-- on the floor, where the client's collision box touches the ground; walking,
-- the client then took every step for a block in the way and climbed the
-- body a block, and every update pulled it back down - players jittering up
-- and down 30 times a second in the client, and shots missing them (traced
-- frame by frame on a test server, 11 Nov 2026).
local function u16_up(v)
	local n = floor(v * 64);
	if (n < 0) then n = 0; elseif (n > 65535) then n = 65535; end
	return char(n % 256, floor(n / 256));
end

local function entry(i)
	local p, o = get_position(i), get_orientation(i);
	return char(i) .. u16(p.x) .. u16(p.y) .. u16_up(p.z + 128) .. char(s8(o.x), s8(o.y), s8(o.z));
end

-- Built once a tick, whoever it goes to.
local tick_no, built_at, packets = 0, -1, {};
local seq = 0;

function mod.before.tick()
	tick_no = tick_no + 1;
end

local function build()
	if (built_at == tick_no) then
		return packets;
	end
	built_at = tick_no;
	packets = {};
	local function head()
		seq = (seq + 1) % 65536;
		return {char(PACKET_COMPACT_WU, seq % 256, floor(seq / 256))};
	end
	local parts, n = head(), 0;
	for i in piditer(PID_BROADCAST) do
		if (is_alive(i)) then
			parts[#parts + 1] = entry(i);
			n = n + 1;
			if (n == COMPACT_PER_PACKET) then
				packets[#packets + 1] = concat(parts);
				parts, n = head(), 0;
			end
		end
	end
	if (n > 0 or #packets == 0) then
		packets[#packets + 1] = concat(parts);
	end
	return packets;
end

local function takes_it(i)
	return compact_world_update and X.has(i, X.EXT_COMPACT_WU);
end

local function send_to(i)
	if (takes_it(i)) then
		local unseq = type(send_packet_unsequenced) == "function" and send_packet_unsequenced or nil;
		for _, pk in ipairs(build()) do
			if (not (unseq and unseq(i, pk))) then
				send_packet_unreliable(i, pk);
			end
		end
	else
		mod.late.next.send_player_update(i);
	end
end

function mod.late.send_player_update(pid)
	if (pid >= 0 and pid < MAX_PLAYERS) then
		local ok, err = pcall(send_to, pid);
		if (not ok) then
			X.log("compact world update to #%d: %s", pid, tostring(err));
			return mod.late.next.send_player_update(pid);
		end
		return;
	end
	for i in piditer(pid) do
		send_to(i);
	end
end

X.add(X.EXT_COMPACT_WU, 1);

return mod;
