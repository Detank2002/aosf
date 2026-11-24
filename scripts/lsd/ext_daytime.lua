-- ext_daytime.lua -- Daytime and Weather (extension 0x33): packet 115,
-- aosprotocol PR #13.
--   sub 0 Sky: time (UShort, 0 night, anything else day), reserved (UShort),
--              weather (2 bytes, 0)
-- A client that takes it draws nothing until its first Sky, so every one is
-- sent the sky in force as soon as its extensions are known.
--
--   aosext.set_night(on), aosext.is_night()   night or day for everybody
--   aosext.send_sky(pid)
--   aosext.all_take_daytime(pids)   whether all of them can be shown the night
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

X.EXT_DAYTIME = 0x33;
local PACKET_DAYTIME = 64 + X.EXT_DAYTIME;              -- 115

local night = false;

local function sky_packet()
	local t = night and 0 or 720;      -- midnight, or noon
	return string.char(PACKET_DAYTIME, 0, t % 256, math.floor(t / 256), 0, 0, 0, 0);
end

function X.send_sky(pid)
	if (X.has(pid, X.EXT_DAYTIME)) then
		send_packet(pid, sky_packet());
	end
end

function X.is_night()
	return night;
end

function X.set_night(on)
	on = on == true;
	if (on == night) then
		return;
	end
	night = on;
	for i in piditer(PID_BROADCAST) do
		X.send_sky(i);
	end
end

-- The protocol, not the client, decides whether night can be shown.
function X.all_take_daytime(pids)
	if (#pids == 0) then
		return false;
	end
	for _, pid in ipairs(pids) do
		if (not X.has(pid, X.EXT_DAYTIME)) then
			return false;
		end
	end
	return true;
end

function mod.after.on_extensions_known(pid)
	X.send_sky(pid);
end

X.add(X.EXT_DAYTIME, 1);

return mod;
