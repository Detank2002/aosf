-- ext_core.lua -- 0.75 protocol extensions for lsd: the handshake, and what
-- every ext_*.lua builds on. Load it before any of them; each extension is
-- its own file and a server loads only the ones it wants.
--
-- The handshake (aosprotocol extensions.md, "ExtInfo Packet"): once a client
-- has answered the version request, the server sends ExtInfo (packet 60)
-- with what it offers, and a client that knows the packet answers with what
-- it takes. lsd has no packet 60 of its own, nor any extension packet, so
-- this catches them before lsd's sanity checks see them.
--
-- The API is the global table `aosext`:
--   aosext.has(pid, id)              whether pid's client took extension id
--   aosext.add(id, version, packet, reader, when)
--                                    offer an extension; `reader(pid, data)`
--                                    gets its client packets (packet = 64 + id
--                                    for the ones that have packets, nil for
--                                    192-255); `when()`, if given, is asked at
--                                    each handshake whether to offer it
--   on_extensions_known(pid)         a hook (mod.after.on_extensions_known):
--                                    pid's extensions are known, send it what
--                                    it should have from the start
-- and the helpers the extension files share: pack_f32, unpack_f32,
-- pack_color_bgr, valid_utf8, cut_utf8, clean_text, to_list, next_tick, log.
--
-- What it asks of the game mode, which may replace any of these:
--   aosext.is_bot(pid)    a bot, never a person (default: nobody is)
--   aosext.people()       the players "everybody" means (default: joined,
--                         not bots)
--   ext_log_prefix = "[ext] "    the start of every log line
--
-- Part of AOSF (Ace of Spades Forward), github.com/Detank2002/aosf.
-- SPDX-License-Identifier: MPL-2.0. This Source Code Form is subject to the
-- terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
-- distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.
local mod = init_mod();
local ffi = require("ffi");

aosext = aosext or {};
local X = aosext;

getcfg("ext_log_prefix", "[ext] ");

function X.log(fmt, ...)
	log(tostring(ext_log_prefix) .. fmt, ...);
end

function X.is_bot(pid)
	return false;
end

function X.people()
	local out = {};
	for i in piditer(PID_BROADCAST) do
		if (is_joined(i) and not X.is_bot(i)) then
			out[#out + 1] = i;
		end
	end
	return out;
end

-- `to`: a pid, a list of pids, or nil for X.people().
function X.to_list(to)
	if (type(to) == "number") then
		return {to};
	elseif (to == nil) then
		return X.people();
	end
	return to;
end

---------------------------------------------------------------------------
-- Bytes lsd has no function for. Little-endian floats, as 0.75 sends them.

local f32 = ffi.new("float[1]");

function X.pack_f32(v)
	f32[0] = v;
	return ffi.string(f32, 4);
end

function X.unpack_f32(s, at)
	ffi.copy(f32, string.sub(s, at, at + 3), 4);
	return f32[0];
end

-- {r=, g=, b=} or {r, g, b} as the B G R bytes the packets carry.
function X.pack_color_bgr(c)
	return string.char(c.b or c[3], c.g or c[2], c.r or c[1]);
end

-- Whether `text` is well-formed UTF-8: no stray continuation bytes, no
-- overlong forms, no surrogates, nothing past U+10FFFF.
function X.valid_utf8(text)
	local i, n = 1, #text;
	while (i <= n) do
		local c = string.byte(text, i);
		local extra, cp, least;
		if (c < 0x80) then
			extra, cp, least = 0, c, 0;
		elseif (c >= 0xC2 and c <= 0xDF) then
			extra, cp, least = 1, c - 0xC0, 0x80;
		elseif (c >= 0xE0 and c <= 0xEF) then
			extra, cp, least = 2, c - 0xE0, 0x800;
		elseif (c >= 0xF0 and c <= 0xF4) then
			extra, cp, least = 3, c - 0xF0, 0x10000;
		else
			return false;
		end
		if (i + extra > n) then
			return false;
		end
		for k = 1, extra do
			local d = string.byte(text, i + k);
			if (d < 0x80 or d > 0xBF) then
				return false;
			end
			cp = cp * 64 + (d - 0x80);
		end
		if (cp < least or cp > 0x10FFFF or (cp >= 0xD800 and cp <= 0xDFFF)) then
			return false;
		end
		i = i + extra + 1;
	end
	return true;
end

-- `text` cut to `max` bytes on a character boundary, never inside a UTF-8
-- sequence.
function X.cut_utf8(text, max)
	if (#text <= max) then
		return text;
	end
	text = string.sub(text, 1, max);
	local i = #text;
	while (i > 0 and string.byte(text, i) >= 0x80 and string.byte(text, i) < 0xC0) do
		i = i - 1;
	end
	if (i > 0 and string.byte(text, i) >= 0xC0) then
		local c = string.byte(text, i);
		local len = c >= 0xF0 and 4 or (c >= 0xE0 and 3 or 2);
		if (i + len - 1 > #text) then
			text = string.sub(text, 1, i - 1);
		end
	end
	return text;
end

-- A label a client is sent: UTF-8 (anything else dropped), no control
-- bytes, at most `max` bytes.
function X.clean_text(text, max)
	text = text or "";
	if (not X.valid_utf8(text)) then
		text = "";
	end
	return X.cut_utf8((string.gsub(text, "[%z\1-\31\127]", "")), max);
end

-- `fn` on the next tick, after what is going on now is through (a relay
-- once a disconnect is done).
local soon = {};
function X.next_tick(fn)
	soon[#soon + 1] = fn;
end

function mod.after.tick()
	if (#soon == 0) then
		return;
	end
	local now = soon;
	soon = {};
	for _, fn in ipairs(now) do
		local ok, err = pcall(fn);
		if (not ok) then
			X.log("next tick: %s", tostring(err));
		end
	end
end

---------------------------------------------------------------------------
-- The handshake.

local PACKET_EXT_INFO = 60;

-- The order ExtInfo lists them in: the ones known here first, in this
-- order, then any other in the order it was added.
local ORDER = {193, 194, 48, 32, 53, 0x31, 0x32, 0x33, 0x3E, 0x3F, 58, 192};
local rank = {};
for i, id in ipairs(ORDER) do
	rank[id] = i;
end

local offered = {};    -- {id=, version=, when=, n=}
local readers = {};    -- packet id -> reader(pid, data)
local exts;            -- pid -> {[id]=version} the client took

function X.add(id, version, packet, reader, when)
	for _, e in ipairs(offered) do
		if (e.id == id) then
			return;
		end
	end
	offered[#offered + 1] = {id=id, version=version, when=when, n=#offered + 1};
	table.sort(offered, function(a, b)
		local ra, rb = rank[a.id] or (#ORDER + a.n), rank[b.id] or (#ORDER + b.n);
		return ra < rb;
	end);
	if (packet ~= nil and reader ~= nil) then
		readers[packet] = reader;
	end
end

-- A client packet for an extension added without a reader.
function X.reader(packet, reader)
	readers[packet] = reader;
end

function X.has(pid, id)
	return exts ~= nil and exts[pid] ~= nil and exts[pid][id] ~= nil;
end

-- What is offered now, {id, version} pairs.
function X.offer()
	local list = {};
	for _, e in ipairs(offered) do
		if (e.when == nil or e.when()) then
			list[#list + 1] = {e.id, e.version};
		end
	end
	return list;
end

-- Called once a client's extensions are known, for the extensions that send
-- it something as soon as it can take it (a sky, outfits, smoke).
function mod.impl.on_extensions_known(pid)
end

function mod.after.on_version(pid, idChar, major, minor, patch)
	-- OpenSpades 0.1.3 and older crash on it (piqueserver#504).
	if (idChar == string.byte("o") and (major == 0 and (minor < 1 or (minor == 1 and patch <= 3)))) then
		return;
	end
	local list = X.offer();
	local parts = {string.char(PACKET_EXT_INFO, #list)};
	for _, e in ipairs(list) do
		parts[#parts + 1] = string.char(e[1], e[2]);
	end
	send_packet(pid, table.concat(parts));
end

local function on_ext_info(pid, data)
	local n = string.byte(data, 2) or 0;
	local took = {};
	local names = {};
	local list = X.offer();
	for i = 0, n - 1 do
		local id, ver = string.byte(data, 3 + 2*i, 4 + 2*i);
		if (id == nil or ver == nil) then
			break;
		end
		for _, e in ipairs(list) do
			if (e[1] == id) then
				took[id] = math.min(ver, e[2]);
				names[#names + 1] = tostring(id);
			end
		end
	end
	exts[pid] = took;
	if (#names > 0 and not X.is_bot(pid)) then
		X.log("%s takes extensions %s", get_name(pid) or ("#" .. pid), table.concat(names, ", "));
	end
	on_extensions_known(pid);
end

function mod.xearly.on_any_packet(pid, data)
	if (pid < 0 or pid >= MAX_PLAYERS) then
		return mod.xearly.next.on_any_packet(pid, data);
	end
	local id = string.byte(data, 1);
	if (id == PACKET_EXT_INFO) then
		local ok, err = pcall(on_ext_info, pid, data);
		if (not ok) then
			X.log("bad extension info from #%d: %s", pid, tostring(err));
		end
		return 1;
	end
	local reader = readers[id];
	if (reader ~= nil) then
		if (is_alive(pid) or is_joined(pid)) then
			local ok, err = pcall(reader, pid, data);
			if (not ok) then
				X.log("bad packet %d from #%d: %s", id, pid, tostring(err));
			end
		end
		return 1;
	end
	return mod.xearly.next.on_any_packet(pid, data);
end

-- Ours, handled above: not crap, so not logged as such.
function mod.xearly.on_crap_packet(pid, data)
	if (pid < 0 or pid >= MAX_PLAYERS) then
		return mod.xearly.next.on_crap_packet(pid, data);
	end
	local id = string.byte(data, 1);
	if (id == PACKET_EXT_INFO or readers[id] ~= nil) then
		return;
	end
	return mod.xearly.next.on_crap_packet(pid, data);
end

function mod.on_load()
	exts = pid_connected_table(nil);
end

return mod;
