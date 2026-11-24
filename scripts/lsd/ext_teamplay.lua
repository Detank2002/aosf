-- ext_teamplay.lua -- Teamplay (extension 48, ZeroSpades'): packet 112, a
-- sub-packet byte, little-endian.
--   sub 0 Config  : features, north x, north y
--   sub 1 Ping    : sender, x y z, duration, surfaces, B G R, msg id, reason
--   sub 2 EspMark : target, duration (inf = until cleared, 0 = clear),
--                   surfaces, flags, B G R, msg id, label
--
--   aosext.send_teamplay_config(pid)   the features on (team ESP, pings,
--                                      compass; north is -y)
--   aosext.mark(target, on, label, colour, flags, to, seconds)
--                                      an outline on a player, or cleared
--   aosext.request_ping(pid, x, y, z, reason)
--                                      a player's ping, checked and relayed
--                                      to its team; nil, or why not
--   aosext.ping_packet(...), aosext.server_ping(x, y, z, label, colour,
--                                      seconds, to)   the server's own
--   /pingmark x y z [reason]           a ping by chat (a key bind, a pie
--                                      slice's "/pingmark %h ...")
--   teamplay_ping_colours = {[1]={r=,g=,b=}, [2]=...}   a team's ping colour
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

X.EXT_TEAMPLAY = 48;
local PACKET_TEAMPLAY = 64 + X.EXT_TEAMPLAY;         -- 112

local TP_CONFIG, TP_PING, TP_MARK = 0, 1, 2;
X.TP_FEATURES = 1 + 2 + 4;      -- team ESP, pings, compass
X.MARK_SURFACES = 1 + 2;        -- the world and the minimap
X.MARK_CLEAR = 1;               -- cleared when it respawns
X.MARK_NAME = 2;                -- its name drawn with the mark
X.PING_ALL = 1 + 2 + 4;         -- world, minimap, compass
local PING_SECONDS = 10.0;
local PING_EVERY = 1.0;

getcfg("teamplay_ping_colours", {[1]={r=0x30, g=0x70, b=0xFF}, [2]={r=0x30, g=0xE0, b=0x40}});

function X.send_teamplay_config(pid)
	if (X.has(pid, X.EXT_TEAMPLAY)) then
		send_packet(pid, string.char(PACKET_TEAMPLAY, TP_CONFIG, X.TP_FEATURES)
			.. X.pack_f32(0.0) .. X.pack_f32(-1.0));
	end
end

-- An outline on `target` for `to` (a pid, a list of pids, or nil for
-- everybody), or cleared when `on` is false. It lasts `seconds`, or until it
-- is cleared when that is nil. Returns how many were sent to.
function X.mark(target, on, label, colour, flags, to, seconds)
	local packet = string.char(PACKET_TEAMPLAY, TP_MARK, target)
		.. X.pack_f32(on and (seconds or math.huge) or 0.0)
		.. string.char(X.MARK_SURFACES, flags or X.MARK_CLEAR)
		.. X.pack_color_bgr(colour) .. string.char(0)
		.. string.sub(label or "", 1, 64);
	local sent = 0;
	for _, pid in ipairs(X.to_list(to)) do
		if (X.has(pid, X.EXT_TEAMPLAY)) then
			send_packet(pid, packet);
			sent = sent + 1;
		end
	end
	return sent;
end

local last_ping;

local function ping_colour(team)
	local c = teamplay_ping_colours or {};
	return c[team] or c[1] or {r=0x30, g=0x70, b=0xFF};
end

-- A ping asked for by `pid`, from the Ping packet or /pingmark: checked
-- (alive, on a team, on the map, one a second) and relayed to its team, the
-- sender included, in the team's colour. Nil when sent, else why not.
function X.request_ping(pid, x, y, z, reason)
	if (not is_alive(pid) or X.is_bot(pid) or get_team(pid) == SPECTATOR) then
		return "Only the living can ping.";
	end
	for _, v in ipairs{x, y, z} do
		if (v ~= v or v == math.huge or v == -math.huge) then
			return "That is not a place.";
		end
	end
	if (x < 0 or x > 512 or y < 0 or y > 512 or z < 0 or z > 64) then
		return "That is off the map.";
	end
	local now = get_time();
	if (now - (last_ping[pid] or -1e9) < PING_EVERY) then
		return "One ping a second.";
	end
	last_ping[pid] = now;
	local team = get_team(pid);
	-- The Reason is UTF-8, which is checked, and cut to 64 bytes on a
	-- character boundary.
	reason = X.clean_text(reason, 64);
	local packet = string.char(PACKET_TEAMPLAY, TP_PING, pid)
		.. X.pack_f32(x) .. X.pack_f32(y) .. X.pack_f32(z) .. X.pack_f32(PING_SECONDS)
		.. string.char(0) .. X.pack_color_bgr(ping_colour(team))
		.. string.char(0) .. reason;
	for i in piditer(PID_BROADCAST) do
		if (is_joined(i) and get_team(i) == team and X.has(i, X.EXT_TEAMPLAY)) then
			send_packet(i, packet);
		end
	end
	return nil;
end

-- A Ping packet as the spec lays it out (24 bytes and the label): sender 255
-- is the server, seconds math.huge stays until cleared and 0 clears,
-- surfaces 1 world, 2 minimap, 4 compass.
function X.ping_packet(sender, x, y, z, seconds, surfaces, colour, label)
	label = X.clean_text(label, 64);
	return string.char(PACKET_TEAMPLAY, TP_PING, sender)
		.. X.pack_f32(x) .. X.pack_f32(y) .. X.pack_f32(z) .. X.pack_f32(seconds)
		.. string.char(surfaces) .. X.pack_color_bgr(colour) .. string.char(0) .. label;
end

-- The server's own ping to `to` (a pid, a list, or nil for everybody that
-- took Teamplay). One at a time: a new one replaces the last, and seconds 0
-- clears it. Returns how many were sent to.
function X.server_ping(x, y, z, label, colour, seconds, to)
	local packet = X.ping_packet(255, x, y, z, seconds, X.PING_ALL, colour, label);
	local sent = 0;
	for _, pid in ipairs(X.to_list(to)) do
		if (X.has(pid, X.EXT_TEAMPLAY)) then
			send_packet(pid, packet);
			sent = sent + 1;
		end
	end
	return sent;
end

-- A client's Ping packet: refused silently. The Reason is what follows the
-- Message ID (byte 24).
local function on_teamplay(pid, data)
	if (string.byte(data, 2) ~= TP_PING or #data < 24) then
		return;
	end
	X.request_ping(pid, X.unpack_f32(data, 4), X.unpack_f32(data, 8), X.unpack_f32(data, 12),
		string.sub(data, 25));
end

-- /pingmark x y z [reason...]: the same ping as a chat line. It is
-- Teamplay's, so a client that did not take Teamplay has no such command; a
-- refusal is answered in chat, as is a line that does not start with three
-- numbers (a %h that met nothing).
register_command({name="pingmark", desc="Mark a place for your team: /pingmark <x> <y> <z> [reason].",
	func=function(pid, argv)
		if (not X.has(pid, X.EXT_TEAMPLAY)) then
			server_msg(pid, "Unknown command");
			return;
		end
		local x, y, z = tonumber(argv[1] or ""), tonumber(argv[2] or ""), tonumber(argv[3] or "");
		if (x == nil or y == nil or z == nil) then
			server_msg(pid, "Nothing there to mark: /pingmark <x> <y> <z> [reason].");
			return;
		end
		local why = X.request_ping(pid, x, y, z, table.concat(argv, " ", 4));
		if (why ~= nil) then
			server_msg(pid, why);
		end
	end}, mod);

X.add(X.EXT_TEAMPLAY, 1, PACKET_TEAMPLAY, on_teamplay);

function mod.on_load()
	last_ping = pid_connected_table(nil);
end

return mod;
