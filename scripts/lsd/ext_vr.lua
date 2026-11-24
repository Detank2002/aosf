-- ext_vr.lua -- VR presence (extension 58, ZeroSpadesEx's; ZeroSpades VR, --vr): players in a headset
-- seen as such, their tracked head and hands, by everyone whose client takes
-- extension 58 - in a headset or on a monitor. A port of zerospadesex's
-- Server/vr_presence.py.
--
--   vr_max_rate = 30       -- poses relayed a second a VR player; more are dropped
--   vr_body_sync = true    -- a pose's position moves the body (room-scale walking)
--   vr_max_step = 0.6      -- the furthest one pose may move the body, in blocks
--   vr_max_reach = 4.0     -- head and hands further than this from the eye: refused
--
-- A VR client sends its head and hands up to 30 times a second as packet 122
-- (64 + 58); this checks each one and relays it to every other client that
-- took the extension. The rest never see a byte of it, and are drawn the VR
-- player with the ordinary animation.
--
-- Room-scale: one who walks in the room moves without a key down, which the
-- server's physics never hears of; PositionData comes about once a second, so
-- without body sync the others see them hop. With it, the position in each
-- pose moves the body sideways, a small step at a time and never into a wall.
--
-- The packet format is the client's Sources/Client/VRNetProtocol.h and VR.md.
--   client to server, a pose:   [122][0][payload]
--   server to client, a pose:   [122][0][player id][payload]
--   server to client, config:   [122][1][flags (1 body sync)][max rate]
-- payload, 56 bytes, little-endian: flags u8 (4 body), then head, left hand
-- and right hand each 3 x i16 position (1/512 block, from the eye) and 4 x i16
-- rotation, then body 3 x f32, then buttons u8.
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

getcfg("vr_max_rate", 30);
getcfg("vr_body_sync", true);
getcfg("vr_max_step", 0.6);
getcfg("vr_max_reach", 4.0);

X.EXT_VR = 58;
local PACKET_VR = 64 + X.EXT_VR;        -- 122
local SUB_POSE, SUB_CONFIG = 0, 1
local POSE_BYTES = 56
local POSE_FLAG_BODY = 4
local CONFIG_BODY_SYNC = 1
local POSITIONS = {1, 15, 29}           -- payload offsets of head, left, right
local BODY = 43
local KEY_CROUCH = 32
local ACTIVE_FOR = 1.0

-- The body box the client's own room-scale check uses (Player::VRPushBody):
-- 0.45 either side; heights under the eye from the top of the head to a block
-- above the feet (nearer the feet a sample can land in the ground's top block
-- and call open ground a wall). Crouched, the feet are 0.9 nearer the eye.
local HALF_WIDTH = 0.45
local LEVELS = {-0.35, 0.45, 1.2}
local LEVELS_CROUCHED = {-0.35, 0.3}

local vr;       -- pid -> {relayed=, seen=, told=}

-- Solid, with out-of-bounds handled (is_solid() is undefined out of bounds):
-- below the map (z >= 64) is solid, above it (z < 0) and off the edges is not.
-- A game mode that set its own first keeps it.
X.solid = X.solid or function(x, y, z)
	x, y, z = math.floor(x), math.floor(y), math.floor(z);
	if (z >= 64) then
		return true;
	end
	if (z < 0 or x < 0 or x >= 512 or y < 0 or y >= 512) then
		return false;
	end
	return is_solid{x=x, y=y, z=z};
end

local function i16(s, at)
	local lo, hi = string.byte(s, at, at + 1);
	local v = lo + hi * 256;
	return v >= 32768 and v - 65536 or v;
end

-- A little-endian f32, nil when not finite.
function X.vr_f32(s, at)
	local b1, b2, b3, b4 = string.byte(s, at, at + 3);
	local exp = (b4 % 128) * 2 + math.floor(b3 / 128);
	local mant = (b3 % 128) * 65536 + b2 * 256 + b1;
	if (exp == 255) then
		return nil;
	end
	local v = exp == 0 and mant * 2 ^ -149 or (1 + mant / 8388608) * 2 ^ (exp - 127);
	return b4 >= 128 and -v or v;
end

-- `payload` (56 bytes): head and hands within reach of the eye, and a body
-- position that is a number. Anything else is a broken or doctored client.
function X.vr_plausible(payload, reach)
	for _, at in ipairs(POSITIONS) do
		for k = 0, 2 do
			if (math.abs(i16(payload, at + 1 + 2 * k)) / 512 > reach) then
				return false;
			end
		end
	end
	for k = 0, 2 do
		if (X.vr_f32(payload, BODY + 1 + 4 * k) == nil) then
			return false;
		end
	end
	return true;
end

-- Whether the body fits at (x, y) with its eye at z.
function X.vr_body_clear(x, y, z, crouched)
	for _, dz in ipairs(crouched and LEVELS_CROUCHED or LEVELS) do
		for _, ox in ipairs({-HALF_WIDTH, HALF_WIDTH}) do
			for _, oy in ipairs({-HALF_WIDTH, HALF_WIDTH}) do
				local bx, by, bz = math.floor(x + ox), math.floor(y + oy), math.floor(z + dz);
				if (bx < 0 or bx >= 512 or by < 0 or by >= 512) then
					return false;
				end
				if (bz >= 0 and X.solid(bx, by, bz)) then     -- above the map is open air
					return false;
				end
			end
		end
	end
	return true;
end

-- Whether `pid` has sent a pose in the last second.
function X.vr_active(pid)
	local v = vr and vr[pid];
	return v ~= nil and v.seen ~= nil and get_time() - v.seen < ACTIVE_FOR;
end

local function rate()
	return math.max(1, math.min(255, math.floor(tonumber(vr_max_rate) or 30)));
end

local function send_config(pid)
	local v = vr[pid];
	if (v.told or not X.has(pid, X.EXT_VR)) then
		return;
	end
	v.told = true;
	send_packet(pid, string.char(PACKET_VR, SUB_CONFIG, vr_body_sync and CONFIG_BODY_SYNC or 0, rate()));
end

-- Sideways only: height is the server's physics (gravity, steps, jumps),
-- which the client agrees with anyway. on_position, as a PositionData from
-- the client would: the server's body moves, the client is not sent back.
local function sync_body(pid, payload)
	local x, y = X.vr_f32(payload, BODY + 1), X.vr_f32(payload, BODY + 5);
	local pos = get_position(pid);
	local step = math.sqrt((x - pos.x) ^ 2 + (y - pos.y) ^ 2);
	if (step < 0.005 or step > (tonumber(vr_max_step) or 0.6)) then
		return;
	end
	if (not X.vr_body_clear(x, y, pos.z, get_inputs(pid) % (2 * KEY_CROUCH) >= KEY_CROUCH)) then
		return;
	end
	on_position(pid, {x=x, y=y, z=pos.z});
end

local function on_vr(pid, data)
	-- Only from a client that took the extension, and only poses: a config
	-- is the server's to send.
	if (string.byte(data, 2) ~= SUB_POSE or not X.has(pid, X.EXT_VR)) then
		return;
	end
	if (not is_alive(pid) or get_team(pid) == SPECTATOR or #data < 2 + POSE_BYTES) then
		return;
	end
	local v = vr[pid];
	local now = get_time();
	-- A little slack, so a client pacing itself at exactly the limit does
	-- not lose every other pose to timer jitter.
	if (v.relayed ~= nil and now - v.relayed < 0.8 / rate()) then
		return;
	end
	local payload = string.sub(data, 3, 2 + POSE_BYTES);
	if (not X.vr_plausible(payload, tonumber(vr_max_reach) or 4.0)) then
		return;
	end
	if (v.seen == nil) then
		X.log("%s is in VR", get_name(pid));
	end
	v.relayed, v.seen = now, now;
	send_config(pid);
	if (vr_body_sync and string.byte(payload, 1) % (2 * POSE_FLAG_BODY) >= POSE_FLAG_BODY) then
		sync_body(pid, payload);
	end
	local relay = string.char(PACKET_VR, SUB_POSE, pid) .. payload;
	for i in piditer(PID_BROADCAST) do
		if (i ~= pid and X.has(i, X.EXT_VR)) then
			send_packet_unreliable(i, relay);
		end
	end
end

X.add(X.EXT_VR, 1, PACKET_VR, on_vr);

function mod.after.spawn_player(pid)
	if (pid >= 0 and pid < MAX_PLAYERS and vr[pid] ~= nil) then
		send_config(pid);
	end
end

local cmd = {name="vr", fakepid=true, desc="Who is in VR."};
function cmd.func(pid)
	local names = {};
	for i in piditer(PID_BROADCAST) do
		if (X.vr_active(i)) then
			names[#names + 1] = get_name(i);
		end
	end
	server_msg(pid, #names == 0 and "Nobody is in VR right now." or ("In VR: " .. table.concat(names, ", ")));
end
register_command(cmd, mod);

function mod.on_load()
	vr = pid_connected_table(function() return {} end);
end

return mod;
