-- ext_outfit.lua -- Player Outfit (extension 53): packet 117, aosprotocol
-- PR #14.
--   sub 0 Set Outfit  : player, outfit, colour (the team whose colour it
--                       wears; 255 = the player's own, which is all we send)
--   sub 1 Team Outfits: (team, outfit) pairs; a team not listed wears 0
-- Team Outfits goes first, as soon as the extension is agreed; Set Outfit
-- may come before the player is introduced and any time after. The client
-- forgets a player's outfit when they leave. Outfit art ships with the
-- client.
--
--   outfit_teams = {green="zombie"}     the outfit a team wears from the start
--   aosext.OUTFITS                      the numbers by name
--   aosext.set_team_outfit(team, outfit), aosext.team_outfit(team)
--   aosext.set_player_outfit(pid, outfit)   aosext.OUTFIT_TEAM: back to the team's
--   aosext.wire_team(team)              lsd's team (1, 2, SPECTATOR) as packets carry it
--   aosext.outfit_old_numbering(pid)    TRANSITION, for the game mode to answer:
--                                       whether pid's client numbers outfits as
--                                       PR #14's first draft did and takes a Set
--                                       Outfit without the colour byte (default no)
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local X = aosext;

X.EXT_OUTFIT = 53;
local PACKET_OUTFIT = 64 + X.EXT_OUTFIT;                -- 117

X.OUTFITS = {
	soldier=0, scout=1, ghillie=2, bodyguard=3, terrorist=4, convict=5, brawler=6, miner=7,
	builder=8, scientist=9, butcher=10, royal=11, robot=12, vampire=13, mummy=14, demon=15,
	god=16, mascot=17, tiger=18, penguin=19, bear=20, unicorn=21, trex=22, banana=23,
	blockstack=24,
	zombie=64, spitter=65, leaper=66, caller=67, breaker=68, toppler=69,
	turret=80, projector=81, dishantenna=82, mastantenna=83,
	undead=64,      -- the old name of zombie, still in configs
};
X.OUTFIT_TEAM = 255;

getcfg("outfit_teams", {});

local team_outfits = {};      -- wire team byte -> outfit
local player_outfits;         -- pid -> outfit (nil: the team's)

function X.wire_team(team)
	if (team == SPECTATOR) then
		return 255;
	end
	return team - 1;
end
local wire_team = X.wire_team;

function X.outfit_number(v)
	if (type(v) == "string") then
		v = X.OUTFITS[string.lower(v)] or tonumber(v);
	end
	if (type(v) ~= "number" or v ~= math.floor(v) or v < 0 or v > 255) then
		return nil;
	end
	return v;
end
local outfit_number = X.outfit_number;

function X.outfit_old_numbering(pid)
	return false;
end

-- TRANSITION: the first draft's numbers. Delete with the OLD branches below
-- once no client numbers outfits this way.
local OLD_OUTFITS = {
	[0]=0, [1]=2, [2]=6, [3]=15, [4]=16, [5]=10, [6]=7, [7]=5, [8]=11, [9]=8,
	[10]=9, [11]=3, [12]=12, [13]=4, [15]=14, [16]=13,
};

local function wire_outfit(o, new)
	if (new or o == X.OUTFIT_TEAM) then
		return o;
	end
	if (o >= 64 and o <= 79) then
		return 1;
	end
	return OLD_OUTFITS[o] or 0;
end

local function team_outfits_packet(new)
	local parts = {string.char(PACKET_OUTFIT, 1)};
	for t, o in pairs(team_outfits) do
		parts[#parts + 1] = string.char(t, wire_outfit(o, new));
	end
	return table.concat(parts);
end

local function set_outfit_packet(p, o, new)
	if (new) then
		return string.char(PACKET_OUTFIT, 0, p, o, 255);
	end
	return string.char(PACKET_OUTFIT, 0, p, wire_outfit(o, false));
end

local function is_new(pid)
	return not X.outfit_old_numbering(pid);
end

-- `make(new)` builds the packet for a client on the current numbering (true)
-- or the first draft's (false).
local function send_all(make)
	for i in piditer(PID_BROADCAST) do
		if (X.has(i, X.EXT_OUTFIT)) then
			send_packet(i, make(is_new(i)));
		end
	end
end

local function send_outfits(pid)
	if (not X.has(pid, X.EXT_OUTFIT)) then
		return;
	end
	local new = is_new(pid);
	send_packet(pid, team_outfits_packet(new));
	for p, o in pairs(player_outfits) do
		send_packet(pid, set_outfit_packet(p, o, new));
	end
end

-- The outfit a team (1, 2 or SPECTATOR) wears: a number or a name from OUTFITS.
function X.set_team_outfit(team, outfit)
	local o = assert(outfit_number(outfit), "unknown outfit " .. tostring(outfit));
	team_outfits[wire_team(team)] = (o ~= 0 and o) or nil;
	send_all(team_outfits_packet);
end

function X.team_outfit(team)
	return team_outfits[wire_team(team)] or 0;
end

-- One player's, over their team's; OUTFIT_TEAM (255) to go back to the team's.
function X.set_player_outfit(pid, outfit)
	local o = assert(outfit_number(outfit), "unknown outfit " .. tostring(outfit));
	if (o == X.OUTFIT_TEAM and player_outfits[pid] == nil) then
		return;
	end
	player_outfits[pid] = (o ~= X.OUTFIT_TEAM and o) or nil;
	send_all(function (new)
		return set_outfit_packet(pid, o, new);
	end);
end

function mod.after.on_extensions_known(pid)
	send_outfits(pid);
end

X.add(X.EXT_OUTFIT, 1);

function mod.on_load()
	player_outfits = pid_connected_table(nil);
	team_outfits = {};
	local keys = {blue=1, green=2, spectator=SPECTATOR, spectators=SPECTATOR};
	for k, v in pairs(outfit_teams or {}) do
		local team = keys[string.lower(tostring(k))];
		local o = outfit_number(v);
		if (team == nil or o == nil or o == X.OUTFIT_TEAM) then
			X.log("outfits: ignoring %s = %s", tostring(k), tostring(v));
		elseif (o ~= 0) then
			team_outfits[wire_team(team)] = o;
		end
	end
	local said = {};
	for t, o in pairs(team_outfits) do
		said[#said + 1] = t .. "=" .. o;
	end
	X.log("team outfits: %s", #said > 0 and table.concat(said, ", ") or "none");
end

return mod;
