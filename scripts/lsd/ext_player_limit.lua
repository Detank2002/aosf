-- ext_player_limit.lua -- PlayerLimit (extension 192, packetless; aosprotocol
-- extensions.md): a client that takes it reads player ids up to 255. Offered
-- only while the server hands out slots past 31; keeping a client that did
-- not take it away from those players is the game mode's business (lsd's
-- own 32-entry clients crash on the first packet naming a player past 31).
--
--   player_limit_offer = false     offer it
--   aosext.player_limit_wanted()   or the game mode's answer, asked at each
--                                  handshake (default: player_limit_offer)
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

X.EXT_PLAYER_LIMIT = 192;

getcfg("player_limit_offer", false);

function X.player_limit_wanted()
	return player_limit_offer == true;
end

X.add(X.EXT_PLAYER_LIMIT, 1, nil, nil, function() return X.player_limit_wanted() end);

return mod;
