-- ext_kickreason.lua -- KickReason (extension 194, packetless; aosprotocol
-- extensions.md): a client that takes it shows the system chat line (type 2,
-- from player 255) sent just before a disconnect as the reason it was let go.
--
--   aosext.disconnect_with(pid, code, reason)
--                                  the reason (to the client that takes it,
--                                  88 bytes at most), then lsd's disconnect
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

X.EXT_KICKREASON = 194;

function X.disconnect_with(pid, code, reason)
	if (reason and X.has(pid, X.EXT_KICKREASON)) then
		send_chat(pid, string.sub(reason, 1, 88), 2, 255);
	end
	disconnect(pid, code or 0);
end

X.add(X.EXT_KICKREASON, 1);

return mod;
