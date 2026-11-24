# Specs

Every extension the scripts in this repo speak. The ones registered in
aosprotocol are specified there ([`../protocol/`](../protocol/)); the rest
are specified here, in the same style, until they are.

| ID | Extension | Spec | Clients that take it | lsd script |
|---|---|---|---|---|
| 32 (`0x20`) | Damage Markers | [protocol](../protocol/extensions/damage-markers.md) | ZeroSpades, XRSpades | `ext_damage_markers` |
| 48 (`0x30`) | Teamplay | [protocol](../protocol/extensions/teamplay.md) | ZeroSpades, XRSpades | `ext_teamplay` |
| 49 (`0x31`) | Pie Menu | [protocol](../protocol/extensions/pie-menu.md) | ZeroSpades, XRSpades | `ext_pie_menu` |
| 50 (`0x32`) | Flashlight | [protocol](../protocol/extensions/flashlight.md) | ZeroSpades, XRSpades | `ext_flashlight` |
| 51 (`0x33`) | Daytime and Weather | [protocol](../protocol/extensions/daytime-weather.md) | ZeroSpades, XRSpades | `ext_daytime` |
| 53 (`0x35`) | Player Outfit | [awaiting](player-outfit.md) (aosprotocol PR #14) | ZeroSpades, XRSpades | `ext_outfit` |
| 58 (`0x3A`) | VR presence | [here](vr-presence.md) | XRSpades | `ext_vr` |
| 62 (`0x3E`) | Compact World Update | [here](compact-world-update.md) | XRSpades (ZeroSpades X 0.3.4+) | `ext_compact` |
| 63 (`0x3F`) | Smoke | [here](smoke.md) | XRSpades (ZeroSpades X 0.3.5+) | `ext_smoke` |
| 192 | Player Limit | [protocol](../protocol/extensions/player-limit.md) | ZeroSpades, XRSpades, BetterSpades and its forks | `ext_player_limit` |
| 193 | Message Types | [protocol](../protocol/extensions/message-types.md) | ZeroSpades, XRSpades, BetterSpades and its forks | `ext_chattype` |
| 194 | Kick Reason | [protocol](../protocol/extensions/kick-reason.md) | ZeroSpades, XRSpades, BetterSpades and its forks | `ext_kickreason` |

"Clients that take it" is what our servers' logs show clients taking (November
2026), not a full list.

The handshake every one of them goes through is
[Extensions](../protocol/extensions/extension.md) (ExtInfo, packet 60).

Our own ids (`0x3E`, `0x3F`) are past the range ZeroSpades uses (up to
`0x33`, then `0x35` and `0x36`), as its developers asked.

These specs are under [CC BY 4.0](LICENSE): free to use, copy and adapt,
with credit to *AOSF (Ace of Spades Forward), by Detank2002,
github.com/Detank2002/aosf*.
