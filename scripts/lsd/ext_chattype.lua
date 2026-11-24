-- ext_chattype.lua -- MessageTypes (extension 193, packetless; aosprotocol
-- extensions.md): chat types 3 big (the centre of the screen), 4 info (a
-- banner), 5 warning (a banner with a beep), 6 error. A client without it
-- gets OpenSpades' magic prefixes instead, which OpenSpades-family clients
-- draw the same way.
--
--   aosext.CHAT_BIG, CHAT_INFO, CHAT_WARNING, CHAT_ERROR = 3, 4, 5, 6
--   aosext.CHAT_PREFIX[type]       the prefix for a client without it
--   aosext.send_typed(pid, line, type)
--                                  one line of that type (wrap it first)
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

X.EXT_CHATTYPE = 193;
X.CHAT_BIG, X.CHAT_INFO, X.CHAT_WARNING, X.CHAT_ERROR = 3, 4, 5, 6;
X.CHAT_PREFIX = {[3]="C% ", [4]="N% ", [5]="%% ", [6]="!% "};

function X.send_typed(pid, line, kind)
	if (X.has(pid, X.EXT_CHATTYPE)) then
		send_chat(pid, line, kind, 35);
	else
		server_msg(pid, (X.CHAT_PREFIX[kind] or "") .. line);
	end
end

X.add(X.EXT_CHATTYPE, 1);

return mod;
