-- ext_pie_menu.lua -- Pie Menu (extension 0x31): packet 113, aosprotocol
-- PR #11. The server's menu replaces the client's own: pies of exactly six
-- slices, each offered in contexts (what the player aims at).
--   menu  = {pie, ...}           (0-255 pies)
--   pie   = {contexts=bits, theme="...", slices={slice x6}}
--   slice = {text="...", label="...", tooltip="...", global=bool}
--           or nil (blank: drawn empty, cannot be chosen)
-- The client shows the pies whose contexts take the aim, the first first.
-- Choosing a slice sends its text as a chat line (a command when it starts
-- with /), on the channel `global` says; the label is what is drawn (empty:
-- the text), the tooltip what is shown while it is highlighted. A slice with
-- neither text nor label is blank. Strings are NUL-terminated and carried as
-- chat is: Code Page 437 when plain printable ASCII, otherwise UTF-8 behind
-- 0xff; the spec gives them no length limit. A text may use %p (the player
-- aimed at, as #id), %b (the block, x y z), %h (the point aimed at, x y z),
-- %r (the camera ray) and %%; "/pingmark %h ..." (ext_teamplay) marks a place.
--
--   aosext.PIE_BLOCK, PIE_TEAMMATE, PIE_ENEMY, PIE_SPECTATOR, PIE_DEAD, PIE_SKY
--   aosext.PIE_WORLD                      BLOCK + SKY (aimed at no player)
--   aosext.set_pie_menu(pid, menu)        sent when it differs from the last
--   aosext.pie_menu_packet(menu)
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

X.EXT_PIE_MENU = 0x31;
local PACKET_PIE_MENU = 64 + X.EXT_PIE_MENU;            -- 113

X.PIE_BLOCK, X.PIE_TEAMMATE, X.PIE_ENEMY, X.PIE_SPECTATOR, X.PIE_DEAD, X.PIE_SKY = 1, 2, 4, 8, 16, 32;
X.PIE_WORLD = X.PIE_BLOCK + X.PIE_SKY;

-- A string as the spec carries it: no NUL (it ends the string), and in a
-- Text no control bytes either (a client may re-encode a Text, and 0x01-0x1f
-- are symbols in Code Page 437 but colours in UTF-8). Printable ASCII goes as
-- it is (it is Code Page 437 too), anything else as UTF-8 behind 0xff.
local function pie_string(text, is_text)
	text = string.gsub(tostring(text or ""), is_text and "[%z\1-\31\127]" or "%z", "");
	if (not string.find(text, "[\1-\31\127-\255]")) then
		return text .. "\0";
	end
	if (not X.valid_utf8(text)) then
		text = string.gsub(text, "[\128-\255]", "?");   -- a client refuses a whole menu over it
	end
	return "\255" .. text .. "\0";
end

function X.pie_menu_packet(menu)
	local count = math.min(#menu, 255);
	local parts = {string.char(PACKET_PIE_MENU, 0, count)};
	for i = 1, count do
		local pie = menu[i];
		parts[#parts + 1] = string.char(pie.contexts or X.PIE_WORLD, 0) .. pie_string(pie.theme);
		for k = 1, 6 do
			local sl = pie.slices[k] or {};
			parts[#parts + 1] = string.char(0, sl.global and 1 or 0)
				.. pie_string(sl.text, true) .. pie_string(sl.label) .. pie_string(sl.tooltip);
		end
	end
	return table.concat(parts);
end

local sent_menus;     -- pid -> the last menu packet sent

function X.set_pie_menu(pid, menu)
	if (not X.has(pid, X.EXT_PIE_MENU)) then
		return;
	end
	local packet = X.pie_menu_packet(menu);
	if (sent_menus[pid] ~= packet) then
		sent_menus[pid] = packet;
		send_packet(pid, packet);
	end
end

X.add(X.EXT_PIE_MENU, 1);

function mod.on_load()
	sent_menus = pid_connected_table(nil);
end

return mod;
