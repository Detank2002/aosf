# Compact World Update

Where every living player is and which way they face, in 10 bytes a player
instead of World Update's 24, and only for the players that are alive. Small
enough for one unfragmented packet with a hundred players, and sent
unreliably, so a lost one is replaced by the next instead of holding up
everything behind it.

| ------------: | ------------- |
| Extension ID: | `0x3E`        |
| Packet ID:    | `0x7E`        |
| Version:      | 1             |
| Type:         | `HAS_PACKETS` |

Written in the style of [aosprotocol](../protocol/extensions/extension.md)'s
extensions, for XRSpades; not registered there (yet). `0x3E` is past the
range ZeroSpades uses (up to `0x33`), as its developers asked, and clear of
every id registered or proposed in aosprotocol as of 24 November 2026.

## Why

[World Update](../protocol/protocol075.md#world-update-075) carries 24 bytes for
every player slot up to the highest one in use, living or not. With players
in high slots ([Player Limit](../protocol/extensions/player-limit.md)), a
server with a hundred players sends 3 KB or more, thirty times a second.
That is over the network's MTU, so ENet splits it into reliable fragments,
and on a line that loses packets every lost fragment holds up every packet
behind it until it is sent again. Players freeze, then jump.

Compact World Update says the same thing for the living only, in about 1 KB
for a hundred of them: one packet, sent unreliably. A lost one does not
matter, because the next one, a thirtieth of a second later, says it all
again.

## The packet

Server to client only. Unlike the other extensions' packets, it has **no
sub-packet id**: the sequence number follows the packet id directly (see
[Version 1's layout](#version-1s-layout)).

| Field Name      | Field Type | Example | Notes                                   |
|-----------------|------------|---------|-----------------------------------------|
| Packet ID       | UByte      | `0x7E`  | Always `0x7E` (126).                    |
| Sequence number | LE UShort  | `513`   | One more for each packet sent, wrapping |
| Entries         | Entry[]    |         | 0 or more, 10 bytes each                |

Each entry:

| Field Name | Field Type | Example | Notes                                        |
|------------|------------|---------|----------------------------------------------|
| Player ID  | UByte      | `7`     |                                              |
| X          | LE UShort  | `16032` | `x * 64`: 1/64 of a block                     |
| Y          | LE UShort  | `24000` | `y * 64`                                     |
| Z          | LE UShort  | `10400` | `(z + 128) * 64`                             |
| Front X    | Byte       | `127`   | the orientation's x, times 127               |
| Front Y    | Byte       | `0`     | the orientation's y, times 127               |
| Front Z    | Byte       | `0`     | the orientation's z, times 127               |

All multi-byte fields are little-endian. The packet is `3 + 10 * n` bytes for
`n` players. Bytes after the last whole entry are ignored.

### Position

X and Y cover the map, 0 to 512. Z is offset by 128 so that a player above
the map (z below 0, up to 128 blocks above it) can still be sent; the field
covers z from -128 to 896. A value outside the field is clamped to 0 or
65535.

The server rounds X and Y to the nearest 1/64. It should round Z **down**,
towards the smaller z (up the map), never to the nearest: a player standing
on a floor is a hair above it, and rounded to the nearest the client may put
them exactly on the floor, where its collision box touches the ground. The
client then takes the floor for a block in the way, lifts the player a block
when they walk, and every update pulls them back down: the player jitters up
and down, and shots miss them.

### Orientation

Front is the direction the player faces, each component times 127 and
rounded, from -127 to 127. The client divides by 127 and normalises the
result. A front of (0, 0, 0), or one too short to normalise (squared length
0.01 or under), means "no direction": the client keeps the orientation it
had.

## Sending it

* A server sends Compact World Update **in place of** World Update to a
  client that took the extension, at the rate it sends World Update, and
  World Update to every other client.
* It lists the players that are alive. A player it leaves out keeps where it
  was on the client (as a dead player does with World Update).
* It goes unreliable. Where the network library allows it, it should also go
  **unsequenced** (in ENet, `ENET_PACKET_FLAG_UNSEQUENCED` on channel 0): an
  unreliable packet that is still sequenced is tied to the reliable packets
  sent before it on the channel, and a lost one of those holds it up or drops
  it. The sequence number is there because unsequenced packets can arrive out
  of order.
* It should fit one unfragmented packet. In ENet the fragment size is about
  1364 bytes, so 120 entries (1203 bytes) is a safe limit; with more living
  players than that, the server sends more than one packet, each complete in
  itself with its own sequence number (but see
  [More than one packet](#more-than-one-packet)).

## Receiving it

* The client keeps the last sequence number it applied, none at first and
  none again after every [Map Start](../protocol/protocol075.md#map-start-075).
* A packet is applied only if its sequence number is newer than the last,
  allowing for wrapping: newer when `(seq - last) mod 65536` is between 1 and
  32767. An older one, overtaken by a newer one, is dropped whole.
* For each entry, as World Update does for that player:
  * an id the client has no slot for is skipped;
  * the position and front are kept for the player whatever their state;
  * a player who is alive, not a spectator and not the local player is moved
    there and turned that way.
* A demo plays packets back in the order they were recorded, so its player
  ignores the sequence number.

## More than one packet

Each packet carries its own sequence number, and the client drops any packet
older than the last it applied. When a server splits one update over two
packets and the second arrives first, the client drops the first, and the
players in it stay where they were until the next update. With up to 120
living players this never happens; a server with more should expect the
occasional stale player, or (in a later version) the packets of one update
could share a sequence number.

## Version 1's layout

Every other extension packet has a sub-packet id after its packet id
([Extensions](../protocol/extensions/extension.md#extension-packets)). Version
1 of this one does not: it was written and shipped before it was put beside
them. Clients and servers that implement version 1 must read and write it as
above. A later version that adds the sub-packet id (sub 0, then the sequence
number) would be negotiated as version 2 in [ExtInfo](../protocol/extensions/extension.md#extinfo-packet).

## Implementations

* Client: XRSpades (ZeroSpades X 0.3.4 and later), `Sources/Client/NetClient.cpp`
  and `NetProtocol.h` (`ReadCompactWorldEntry`).
* Server: lsd, [`scripts/lsd/ext_compact.lua`](../scripts/lsd/ext_compact.lua).

See [Extensions](../protocol/extensions/extension.md) for how the extension is negotiated.

---

Part of [AOSF](https://github.com/Detank2002/aosf), under [CC BY 4.0](LICENSE).
