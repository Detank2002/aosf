# VR Presence

What a VR player's head and hands are doing, so every other client that
takes the extension can draw them, whether that client is in a headset or
on a monitor. It also lets a VR player's room-scale walking reach the
server faster than Position Data does.

| ------------: | ------------- |
| Extension ID: | `58` (`0x3A`) |
| Packet ID:    | `122` (`0x7A`)|
| Version:      | 1             |
| Type:         | `HAS_PACKETS` |

Written in the style of [aosprotocol](../protocol/extensions/extension.md)'s
extensions, from ZeroSpades VR (now in XRSpades) and its reference server
script; not registered in aosprotocol (yet).

### Sub Packets:

| Sub ID | Name   | Direction        | Size |
|--------|--------|------------------|------|
| 0      | Pose   | Client -> Server | 58   |
| 0      | Pose   | Server -> Client | 59   |
| 1      | Config | Server -> Client | 4    |

A client without the extension never sees these packets, and draws a VR
player with the ordinary animation.

## Sub ID 0: Pose

A VR client sends its pose while it is alive, at the rate the server
allows (20 a second until the server says otherwise). The server checks it
and relays it, with the sender's player id added, to every **other** client
that took the extension.

Client to server:

| Field Name    | Field Type | Example | Notes                     |
|---------------|------------|---------|---------------------------|
| Packet ID     | UByte      | `0x7A`  |                           |
| Sub Packet ID | UByte      | `0`     |                           |
| Payload       | 56 bytes   |         | see [Payload](#payload)   |

Server to client:

| Field Name    | Field Type | Example | Notes                     |
|---------------|------------|---------|---------------------------|
| Packet ID     | UByte      | `0x7A`  |                           |
| Sub Packet ID | UByte      | `0`     |                           |
| Player ID     | UByte      | `5`     | the VR player             |
| Payload       | 56 bytes   |         | as the sender sent it     |

### Payload

All fields little-endian.

| Field Name     | Field Type | Notes                                           |
|----------------|------------|-------------------------------------------------|
| Flags          | UByte      | see below                                       |
| Head position  | 3 x LE Short | offset from the sender's eye                  |
| Head rotation  | 4 x LE Short | unit quaternion x, y, z, w                    |
| Left position  | 3 x LE Short |                                               |
| Left rotation  | 4 x LE Short |                                               |
| Right position | 3 x LE Short |                                               |
| Right rotation | 4 x LE Short |                                               |
| Body           | 3 x LE Float | the sender's own position (eye), world blocks |
| Buttons        | UByte      | see below                                       |

That is `1 + 3 * 14 + 12 + 1 = 56` bytes.

**Positions** are offsets from the sender's eye, in world blocks, in units of
1/512: from -64 to +64 blocks. **Rotations** are unit quaternions in world
axes, each component times 32767. Both are rounded to the nearest and
clamped to -32767 to 32767. Everything is in the game's world frame, so a
receiver needs nothing but the sender's player position to place them. A
receiver normalises the quaternion it reads.

Flags:

| Bit | Meaning                                         |
|-----|-------------------------------------------------|
| 0   | the left hand is tracked (its fields are valid) |
| 1   | the right hand is tracked                       |
| 2   | Body holds the sender's position                |
| 3   | the sender holds its tools in the left hand     |

Buttons (the trigger or grip more than half way in):

| Bit | Meaning       |
|-----|---------------|
| 0   | right trigger |
| 1   | left trigger  |
| 2   | right grip    |
| 3   | left grip     |

### What a server checks

A server relays a pose only:

* from a client that took the extension;
* from a player who is alive and not a spectator;
* that is at least 56 bytes long (bytes past the payload are dropped);
* that is plausible: head and both hands within `max_reach` of the eye (4
  blocks: any component of the offset, divided by 512) and a body whose three
  floats are numbers, not NaN or infinite;
* no sooner than its rate allows. A little slack keeps a client pacing itself
  at exactly the limit from losing every other pose to timer jitter: the
  reference servers take one 0.8 of an interval after the last.

Anything else is dropped silently. It relays the pose unreliable and
unsequenced: a lost one is replaced by the next a fraction of a second later.

### What a client does with one

* It draws the head and hands at their offsets from that player's eye, in
  place of the ordinary animation.
* A pose shorter than 57 bytes (player id and payload) is dropped, never
  read past.
* A pose for a player id it has no player for is dropped.
* A player whose last pose is more than a second old is drawn with the
  ordinary animation again (they took the headset off, or stopped sending).

## Sub ID 1: Config

| Field Name    | Field Type | Example | Notes                              |
|---------------|------------|---------|------------------------------------|
| Packet ID     | UByte      | `0x7A`  |                                    |
| Sub Packet ID | UByte      | `1`     |                                    |
| Flags         | UByte      | `1`     | bit 0: body sync                   |
| Max rate      | UByte      | `30`    | poses a second the server relays   |

The server sends it once a connection, when the player spawns or with its
first pose, whichever comes first. The client paces its poses to the rate,
clamped to 5-60 a second. Body sync tells the client the server moves its
body to the position in its poses (see below); the client needs to do
nothing different for it.

## Room-scale walking (body sync)

A VR player who walks in their room moves without a key down, which the
server's physics never hears of; [Position Data](../protocol/protocol075.md#position-data)
comes about once a second, so without help the others see them hop.

With body sync on, a server moves the body to the Body position in each pose
that has flag 2, sideways only and a small step at a time:

* x and y from the pose; z stays the server's (gravity, steps, jumps);
* only a step between 0.005 and `max_step` (0.6) blocks; anything else is
  dropped, and Position Data catches up;
* never into a wall: the body (0.45 either side, from the top of the head to
  a block above the feet; less when crouched) must be clear at the new spot;
* handled as Position Data from the client would be: the body moves on the
  server, and the client is not sent its own position back.

## Settings the reference servers have

| Setting      | Default | |
|--------------|---------|---|
| `max_rate`   | 30      | poses a second relayed per VR player |
| `body_sync`  | true    | room-scale walking moves the body    |
| `max_step`   | 0.6     | furthest one pose may move the body, blocks |
| `max_reach`  | 4.0     | head and hands further from the eye are refused |

and a `/vr` command that lists who is in VR (a pose in the last second).

## Implementations

* Client: XRSpades (ZeroSpades VR builds), `Sources/Client/VRNetProtocol.h`
  (the encoder and decoder) and `Client_VR.cpp`.
* Server: piqueserver, `Server/vr_presence.py` in the XRSpades repo and
  [AoSTools](https://github.com/Detank2002/AoSTools/tree/main/tools/vr-presence);
  lsd, [`scripts/lsd/ext_vr.lua`](../scripts/lsd/ext_vr.lua).

See [Extensions](../protocol/extensions/extension.md) for how the extension is negotiated.

---

Part of [AOSF](https://github.com/Detank2002/aosf), under [CC BY 4.0](LICENSE).
