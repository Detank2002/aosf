# piqueserver scripts

One piqueserver script per extension, no game mode in them. Copy the ones
you want into your server's `scripts/` folder and list them in
`config.toml`:

```toml
scripts = ["teamplay", "pie_menu", "player_outfit", "compact_world_update", ...]
```

Each file stands alone (no shared module to install) and its docstring lists
its options and what other scripts can call. They are written against
piqueserver 1.x (tested on 1.4.2) and send the same bytes as the
[lsd scripts](../lsd/).

| Script | Extension | Spec |
|---|---|---|
| `teamplay.py` | 48 Teamplay: the Config, pings, ESP marks; `/pingmark` | [protocol](../../protocol/extensions/teamplay.md) |
| `damage_markers.py` | 32 Damage Markers: the damage a hit did, to the attacker | [protocol](../../protocol/extensions/damage-markers.md) |
| `player_outfit.py` | 53 Player Outfit: a team's or a player's outfit | [awaiting](../../specs/player-outfit.md) |
| `pie_menu.py` | 0x31 Pie Menu: `connection.set_pie_menu(menu)` | [protocol](../../protocol/extensions/pie-menu.md) |
| `flashlight.py` | 0x32 Flashlight: lights relayed, beams | [protocol](../../protocol/extensions/flashlight.md) |
| `daytime.py` | 0x33 Daytime and Weather: `protocol.set_night(on)`; `/night` | [protocol](../../protocol/extensions/daytime-weather.md) |
| `compact_world_update.py` | 0x3E Compact World Update, in place of World Update | [here](../../specs/compact-world-update.md) |
| `smoke.py` | 0x3F Smoke: `protocol.smoke(x, y, z, ...)`; `/smoke` | [here](../../specs/smoke.md) |
| `vr_presence.py` | 58 VR Presence: heads and hands relayed; `/vr` | [here](../../specs/vr-presence.md) |

piqueserver itself already offers and handles **Message Types** (193) and
**Kick Reason** (194), so there is no script for them. **Player Limit** (192)
is not offered: piqueserver has 32 player slots.

## How they hook in

* Each one adds its extension to `protocol.available_proto_extensions`;
  piqueserver sends the list in ExtInfo and keeps what each client took in
  `connection.proto_extensions`.
* What a client should have from the start (the Teamplay Config, the sky,
  outfits, the flashlight beam) goes out as soon as its extensions are
  known, through `connection.aosf_extensions_known()`, which every script
  chains through `super()`; and again where it matters when the player joins.
* Client packets (a ping, a flashlight switched on) go to
  `connection.on_<extension>_packet(data)`.

## Tests

```sh
python3 test/test_aosf.py      # from this folder, with piqueserver installed
```

runs every script together on a real piqueserver against fake clients, and
compares their packets byte for byte with the lsd scripts (with `luajit`).
`vr_presence.py` has its own test in the XRSpades repo
(`Server/test/test_vr_presence.py`), which checks it against the client's
own C++ encoder.
