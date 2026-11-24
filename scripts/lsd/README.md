# lsd scripts

One lsd Lua script per extension, with no game mode in
them. Copy the ones you want into lsd's `scripts/` and load them from your
config, `ext_core` first:

```lua
load "ext_core"
load "ext_chattype"
load "ext_teamplay"
load "ext_pie_menu"
-- ... any others
```

[`example-config.lua`](example-config.lua) is lsd's own CTF config with every
one of them loaded.

| Script | Extension | Spec |
|---|---|---|
| `ext_core.lua` | the handshake (ExtInfo, packet 60), packet routing, shared helpers | [Extensions](../../protocol/extensions/extension.md) |
| `ext_chattype.lua` | 193 Message Types | [protocol](../../protocol/extensions/message-types.md) |
| `ext_kickreason.lua` | 194 Kick Reason | [protocol](../../protocol/extensions/kick-reason.md) |
| `ext_teamplay.lua` | 48 Teamplay, and `/pingmark` | [protocol](../../protocol/extensions/teamplay.md) |
| `ext_damage_markers.lua` | 32 Damage Markers | [protocol](../../protocol/extensions/damage-markers.md) |
| `ext_outfit.lua` | 53 Player Outfit | [awaiting](../../specs/player-outfit.md) (aosprotocol PR #14) |
| `ext_pie_menu.lua` | 0x31 Pie Menu | [protocol](../../protocol/extensions/pie-menu.md) |
| `ext_flashlight.lua` | 0x32 Flashlight | [protocol](../../protocol/extensions/flashlight.md) |
| `ext_daytime.lua` | 0x33 Daytime and Weather | [protocol](../../protocol/extensions/daytime-weather.md) |
| `ext_compact.lua` | 0x3E Compact World Update | [here](../../specs/compact-world-update.md) |
| `ext_smoke.lua` | 0x3F Smoke | [here](../../specs/smoke.md) |
| `ext_vr.lua` | 58 VR presence | [here](../../specs/vr-presence.md) |
| `ext_player_limit.lua` | 192 Player Limit | [protocol](../../protocol/extensions/player-limit.md) |

The load order of the extensions does not matter for the handshake: ExtInfo
lists them in a fixed order. The ones that send a joining client something
(the sky, the beam, outfits, smoke) send it in the order they were loaded.
Load `ext_compact` after `command_ups`, since it sits in the late chain under
it.

## Using them

Everything is in the global table `aosext`; each script's header lists its
settings and functions. A few examples:

```lua
aosext.has(pid, aosext.EXT_TEAMPLAY)                 -- did pid's client take it?
aosext.mark(target, true, "Boss", {r=255, g=0, b=0})  -- an outline, for everybody
aosext.set_night(true)                                -- night, for every client that takes it
aosext.smoke{x=256, y=256, z=40, style="column"}      -- a column of smoke
aosext.set_pie_menu(pid, menu)                        -- the player's rings
aosext.damage_marker(attacker, victim, hp_before)     -- after a hit
```

## What a game mode answers

A few things only the game mode knows. Each has a default for a plain
server; a mode replaces it by assigning to `aosext` after `ext_core` loads.

| Asked | Default |
|---|---|
| `aosext.is_bot(pid)` | nobody is a bot |
| `aosext.people()`: whom "everybody" means | joined players that are not bots |
| `aosext.solid(x, y, z)` (VR body sync) | `is_solid`, out of bounds handled |
| `aosext.player_limit_wanted()` | the `player_limit_offer` setting |
| `aosext.outfit_old_numbering(pid)` | never (a transition for clients on PR #14's first draft) |
| `ext_log_prefix` (setting) | `"[ext] "` |

## lsd patches

`ext_compact` is at its best with lsd's `send_packet_unsequenced`, which
stock lsd does not have yet (a small patch, to be offered upstream). Without
it, the update goes unreliable but sequenced, which works but loses some of
the benefit on a lossy line.
