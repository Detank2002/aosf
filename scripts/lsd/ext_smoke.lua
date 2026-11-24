-- ext_smoke.lua -- Smoke (extension 0x3F, XRSpades'; spec: docs/extensions/
-- smoke.md in github.com/Detank2002/xrspades): packet 127, smoke the server
-- puts in the world, drawn by XRSpades (ZeroSpades X 0.3.5 and later) and by
-- nothing else - so a marker or an effect, never cover the game depends on.
-- Sub 0 Smoke (25 bytes), sub 1 Clear Smoke (3 bytes). Map Start clears
-- every smoke on the client, and a joiner sees none already going unless
-- sent it again: the ones with an id are kept until they end, and a joiner
-- is sent them with what is left. 0x3F is past ZeroSpades' own range, as its
-- developers asked.
--
--   aosext.smoke{x=, y=, z=, style="cloud"|"column", radius=5, r=, g=, b=,
--                opacity=200, duration=10 (seconds it keeps coming), fade=3
--                (seconds), hiss=false, id=nil (one from the pool) | 0-254 |
--                false (255: fire and forget, not kept)}
--     returns the id (255 for fire and forget)
--   aosext.clear_smoke(id)   nil: all
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

X.EXT_SMOKE = 0x3F;
local PACKET_SMOKE = 64 + X.EXT_SMOKE;                  -- 127

local SMOKE_NONE = 255;
local smokes = {};      -- id -> {spec, ends (get_time())}

local function smoke_byte(v, lo, hi)
	return math.max(lo, math.min(hi, math.floor((tonumber(v) or lo) + 0.5)));
end

local function smoke_packet(id, sp, duration)
	local d = smoke_byte(duration * 10, 0, 65535);
	return string.char(PACKET_SMOKE, 0, id, sp.style == "column" and 1 or 0)
		.. X.pack_f32(sp.x) .. X.pack_f32(sp.y) .. X.pack_f32(sp.z)
		.. string.char(smoke_byte(sp.radius or 5, 1, 255),
			smoke_byte(sp.r or 210, 0, 255), smoke_byte(sp.g or 210, 0, 255), smoke_byte(sp.b or 210, 0, 255),
			smoke_byte(sp.opacity or 200, 0, 255), d % 256, math.floor(d / 256),
			smoke_byte((sp.fade or 3) * 10, 0, 255), sp.hiss and 1 or 0);
end

local function smoke_to_all(data)
	for i in piditer(PID_BROADCAST) do
		if (X.has(i, X.EXT_SMOKE)) then
			send_packet(i, data);
		end
	end
end

local function smoke_id_free()
	local now = get_time();
	for id = 0, 254 do
		local s = smokes[id];
		if (s == nil or now >= s.ends + (s.spec.fade or 3)) then
			return id;
		end
	end
	return SMOKE_NONE;      -- the pool is full: fire and forget
end

function X.smoke(spec)
	local id = spec.id;
	if (id == false) then
		id = SMOKE_NONE;
	elseif (id == nil) then
		id = smoke_id_free();
	end
	id = smoke_byte(id, 0, 255);
	local duration = math.max(0, tonumber(spec.duration) or 10);
	if (id ~= SMOKE_NONE) then
		smokes[id] = {spec=spec, ends=get_time() + duration};
	end
	smoke_to_all(smoke_packet(id, spec, duration));
	return id;
end

function X.clear_smoke(id)
	id = id == nil and SMOKE_NONE or smoke_byte(id, 0, 255);
	if (id == SMOKE_NONE) then
		smokes = {};
	else
		smokes[id] = nil;
	end
	smoke_to_all(string.char(PACKET_SMOKE, 1, id));
end

local function send_smokes(pid)
	if (not X.has(pid, X.EXT_SMOKE)) then
		return;
	end
	local now = get_time();
	for id, s in pairs(smokes) do
		if (now < s.ends) then
			send_packet(pid, smoke_packet(id, s.spec, s.ends - now));
		end
	end
end

-- A new map: every client has forgotten them (Map Start), and so do we.
function mod.after.finish_map_load()
	smokes = {};
end

function mod.after.on_extensions_known(pid)
	send_smokes(pid);
end

X.add(X.EXT_SMOKE, 1);

return mod;
