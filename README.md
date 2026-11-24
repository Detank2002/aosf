# AOSF: Ace of Spades Forward

Protocol extensions for Ace of Spades 0.75, and the server scripts that
speak them: the specs in one place, and code a server can drop in. Free for
anyone to use, for any purpose, with credit.

| Folder | What |
|---|---|
| [`protocol/`](protocol/) | The community protocol docs, [zerospades/aosprotocol](https://github.com/zerospades/aosprotocol) (a git submodule, Apache 2.0): 0.75 itself, the extension handshake, and the extensions registered there. |
| [`specs/`](specs/) | Extensions of our own, written in aosprotocol's style, until they are registered there. |
| [`scripts/lsd/`](scripts/lsd/) | One lsd script per extension, no game mode in them. |
| [`scripts/piqueserver/`](scripts/piqueserver/) | The same for piqueserver. |

[`specs/README.md`](specs/README.md) lists every extension these scripts
speak, where it is specified and which clients take it.

    git clone --recurse-submodules <this repo>
    git submodule update --remote protocol     # the latest aosprotocol

## Licence

Free to use, for anything, with credit:

- **Scripts** (`scripts/`): [Mozilla Public License 2.0](LICENSE). Use them
  in any server, open or closed, alongside code under any licence. Keep the
  licence notice at the top of each file, and if you hand out a changed copy
  of one of these files, make that file's source available under the MPL
  too. Your own files stay yours.
- **Specs** (`specs/` and this README): [CC BY 4.0](specs/LICENSE). Use,
  copy, adapt and build on them, with credit.
- `protocol/` is aosprotocol's, under its own Apache 2.0 licence.

To credit: *"AOSF (Ace of Spades Forward), by Detank2002,
github.com/Detank2002/aosf"*, with a note if you changed anything.

## Still to come

- the Player Outfit spec, [awaiting](specs/player-outfit.md) aosprotocol's
  pull request #14.

Issues and pull requests are welcome.
