-- ext_flashlight.lua -- Flashlight (extension 0x32): packet 114.
--   sub 0 Light       : player, state   (client asks for its own; relayed)
--   sub 1 Light State : a bit per player id, to a joining client
--   sub 2 Light Config: one player's beam (255: everyone's)
-- Every request is honoured and relayed to every client that takes it, the
-- sender included (its own light only comes on when the relay arrives).
--
--   flashlight_beam = {reach=, cone=, color={r=,g=,b=}, flicker=}
--     everybody's beam, sent as each client's extensions are known; {} (the
--     default) leaves the client's own. reach: blocks at which the light
--     reaches zero (1-255; the client takes it as the falloff radius, so a
--     longer one is brighter at every distance); cone: full angle in pi/256
--     (128 is 90 degrees, 255 about 179)
--   aosext.set_light(pid, on, beam)   the server puts a light on a player, with
--                                     a beam of its own if given; a client turns
--                                     a light off at death and respawn, so switch
--                                     it on after a spawn
--   aosext.send_beam(pid), aosext.beam_packet(beam, pid), aosext.send_light_state(pid)
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

X.EXT_FLASHLIGHT = 0x32;
local PACKET_FLASHLIGHT = 64 + X.EXT_FLASHLIGHT;        -- 114

getcfg("flashlight_beam", {});

local lights;      -- pid -> true when on
local own_beams;   -- pid -> beam, while it has one of its own

local function byte_of(v, default)
	v = math.floor(tonumber(v) or default);
	return string.char(math.max(0, math.min(255, v)));
end

function X.beam_packet(beam, pid)
	if (type(beam) ~= "table" or beam.reach == nil) then
		return nil;
	end
	local c = beam.color or {};
	return string.char(PACKET_FLASHLIGHT, 2, pid or 255) .. byte_of(beam.reach, 60) .. byte_of(beam.cone, 128)
		.. byte_of(c.r, 255) .. byte_of(c.g, 179) .. byte_of(c.b, 128) .. byte_of(beam.flicker, 0);
end

function X.send_beam(pid)
	local packet = X.beam_packet(flashlight_beam);
	if (packet ~= nil and X.has(pid, X.EXT_FLASHLIGHT)) then
		send_packet(pid, packet);
	end
end

local function light_packet(pid, on)
	return string.char(PACKET_FLASHLIGHT, 0, pid, on and 1 or 0);
end

local function relay_light(pid, on)
	for i in piditer(PID_BROADCAST) do
		if (X.has(i, X.EXT_FLASHLIGHT)) then
			send_packet(i, light_packet(pid, on));
		end
	end
end

local function on_flashlight(pid, data)
	if (string.byte(data, 2) ~= 0 or #data < 4 or not X.has(pid, X.EXT_FLASHLIGHT)) then
		return;
	end
	local on = string.byte(data, 4) ~= 0;
	if ((lights[pid] == true) == on) then
		relay_light(pid, on);       -- asked again: say so, nothing changed
		return;
	end
	lights[pid] = on or nil;
	relay_light(pid, on);
end

-- Also for a client that never joins (a demo camera).
function X.send_light_state(pid)
	if (not X.has(pid, X.EXT_FLASHLIGHT)) then
		return;
	end
	local bytes = {};
	for i = 0, 31 do
		bytes[i + 1] = 0;
	end
	for i in pairs(lights) do
		if (i >= 0 and i < 256) then
			local b = math.floor(i / 8) + 1;
			bytes[b] = bytes[b] + 2 ^ (i % 8);
		end
	end
	local parts = {string.char(PACKET_FLASHLIGHT, 1)};
	for i = 1, 32 do
		parts[#parts + 1] = string.char(bytes[i]);
	end
	send_packet(pid, table.concat(parts));
end

local function to_all(packet)
	for i in piditer(PID_BROADCAST) do
		if (is_joined(i) and X.has(i, X.EXT_FLASHLIGHT)) then
			send_packet(i, packet);
		end
	end
end

function X.set_light(pid, on, beam)
	if (lights == nil or not is_connected(pid)) then
		return;
	end
	if (on and type(beam) == "table") then
		own_beams[pid] = beam;
		to_all(X.beam_packet(beam, pid));
	elseif (not on and own_beams[pid] ~= nil) then
		own_beams[pid] = nil;
		local back = X.beam_packet(flashlight_beam, pid);
		if (back ~= nil) then
			to_all(back);
		end
	end
	lights[pid] = on or nil;
	relay_light(pid, on);
end

-- After State Data: the lights already on, for a client that has just joined,
-- with the beams of their own first.
function mod.after.on_join(pid)
	if (own_beams ~= nil and X.has(pid, X.EXT_FLASHLIGHT)) then
		for i, beam in pairs(own_beams) do
			send_packet(pid, X.beam_packet(beam, i));
		end
	end
	X.send_light_state(pid);
end

function mod.before.on_disconnect(pid)
	if (own_beams ~= nil) then
		own_beams[pid] = nil;      -- (a client forgets it on Player Left)
	end
	if (lights ~= nil and lights[pid]) then
		lights[pid] = nil;
		X.next_tick(function() relay_light(pid, false); end);
	end
end

function mod.after.on_extensions_known(pid)
	X.send_beam(pid);
end

X.add(X.EXT_FLASHLIGHT, 1, PACKET_FLASHLIGHT, on_flashlight);

function mod.on_load()
	lights = {};
	own_beams = {};
end

return mod;
