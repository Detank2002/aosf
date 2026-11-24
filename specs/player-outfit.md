# Player Outfit (awaiting spec)

| ------------: | ------------- |
| Extension ID: | `53` (`0x35`) |
| Packet ID:    | `117` (`0x75`)|
| Version:      | 1             |
| Type:         | `HAS_PACKETS` |

The outfit a team, or one player, wears: a model set the client already has,
named by number.

**Awaiting its spec.** It is proposed in aosprotocol as pull request #14,
not merged yet; until it is, that pull request is the reference, and this
page will hold the spec if it lands here instead. The lsd script
[`ext_outfit.lua`](../scripts/lsd/ext_outfit.lua) follows the pull request
as XRSpades implements it:

* sub 0 Set Outfit: player id, outfit, colour (the team whose colour it
  wears; 255 the player's own);
* sub 1 Team Outfits: (team, outfit) pairs; a team not listed wears 0.

The outfit numbers are in the script's header (`aosext.OUTFITS`).

---

Part of [AOSF](https://github.com/Detank2002/aosf), under [CC BY 4.0](LICENSE).
