-- ext_damage_markers.lua -- Damage Markers (extension 32): packet 96, one
-- per hit, to the attacker: the victim and what the hit did (negative a
-- heal), as a UByte, a signed short or a signed int by size.
--
--   aosext.damage_marker(attacker, victim, before)
--                         after a hit on `victim`, who had `before` health:
--                         the attacker is told what it did (call it from
--                         wherever the game mode applies damage)
--   aosext.damage_marker_packet(victim, amount)
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

X.EXT_DAMAGE_MARKERS = 32;
local PACKET_DAMAGE_MARKER = 64 + X.EXT_DAMAGE_MARKERS;  -- 96

function X.damage_marker_packet(victim, amount)
	if (amount >= 0 and amount <= 255) then
		return string.char(PACKET_DAMAGE_MARKER, victim, amount);
	end
	if (amount >= -32768 and amount <= 32767) then
		local u = amount % 65536;
		return string.char(PACKET_DAMAGE_MARKER, victim, u % 256, math.floor(u / 256));
	end
	local u = amount % 4294967296;
	return string.char(PACKET_DAMAGE_MARKER, victim, u % 256, math.floor(u / 256) % 256,
		math.floor(u / 65536) % 256, math.floor(u / 16777216));
end

function X.damage_marker(attacker, victim, before)
	if (attacker == nil or attacker == victim or attacker < 0 or attacker >= MAX_PLAYERS
			or not is_connected(attacker) or not X.has(attacker, X.EXT_DAMAGE_MARKERS)) then
		return;
	end
	local after = is_alive(victim) and get_hp(victim) or 0;
	local amount = before - after;
	if (amount ~= 0) then
		send_packet(attacker, X.damage_marker_packet(victim, amount));
	end
end

X.add(X.EXT_DAMAGE_MARKERS, 1);

return mod;
