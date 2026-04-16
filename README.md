# soomfon

Python driver for the **SOOMFON Stream Controller SE** and compatible devices (Mirabox N3/N4, Ajazz AKP03 and variants).

## Compatible devices

| Device | VID:PID |
|---|---|
| SOOMFON Stream Controller SE | `1500:3001` |
| Mirabox Stream Controller N3 rev.2, N4 | `1500:3001` |
| Ajazz AKP03E/R rev.2 | `1500:3001` |
| Mars Gaming MSD-TWO, TreasLin N3, Redragon SS-551 | `1500:3001` |

All share the same firmware (`V25.CN002.01.005`) and mirajazz v3 protocol.

## Hardware layout

```
┌─────────────────────────────────┐
│  [0]   [1]   [2]              │
│  [3]   [4]   [5]    ← LCD keys│
│  [6]   [7]   [8]              │
│  (◀9▶) (◀10▶) (◀11▶)  ← knobs│
└─────────────────────────────────┘
```

- **Keys 0–5** — LCD macro buttons with 60×60 pixel displays
- **Keys 6–8** — plain buttons (no display)
- **Keys 9–11** — encoder press events (knob 0 / 1 / 2)
- **Encoders 0–2** — rotary knobs, fire `on_encoder(enc, delta)` on twist

## Installation

```bash
pip install soomfon
```

### Device permissions (Linux)

Without a udev rule the device is only accessible as root. Run once after install:

```bash
soomfon udev | sudo tee /etc/udev/rules.d/99-soomfon.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Then re-plug the device. The rule file is also included at `udev/99-soomfon.rules` in the source tree.

## Quickstart

```python
from soomfon import Soomfon
from PIL import Image

with Soomfon() as deck:
    deck.set_brightness(70)
    deck.set_key_image(0, Image.open("icon.png"))
    deck.set_key_color(1, 255, 80, 0)          # solid orange

    @deck.on_key
    def on_key(key: int, pressed: bool):
        print(f"key {key} {'↓' if pressed else '↑'}")

    @deck.on_encoder
    def on_encoder(enc: int, delta: int):
        print(f"encoder {enc}  {'→' if delta > 0 else '←'}")

    deck.run_forever()                          # blocks; Ctrl-C exits cleanly
```

## API

### `Soomfon()`

Opens the first connected device and runs the initialization sequence. Raises `RuntimeError` if no device is found.

Use as a context manager (`with Soomfon() as deck`) for automatic cleanup, or call `deck.close()` manually.

### Display

| Method | Description |
|---|---|
| `set_brightness(pct)` | Screen brightness, 0–100 |
| `set_key_image(key, image)` | Upload a PIL `Image` to an LCD key (0–5). Images are resized to 60×60 and JPEG-encoded automatically. |
| `set_key_color(key, r, g, b)` | Fill an LCD key with a solid colour |
| `clear_key(key)` | Clear one key |
| `clear_all()` | Clear all keys at once |
| `sleep()` | Put the device into standby |

### Events

Register callbacks before calling `start()` or `run_forever()`.

```python
@deck.on_key
def handler(key: int, pressed: bool): ...
```

```python
@deck.on_encoder
def handler(enc: int, delta: int): ...   # delta is always ±1
```

Both decorators return the callback unchanged, so they compose with other decorators.

### Lifecycle

| Method | Description |
|---|---|
| `start()` | Start background reader + dispatcher threads (non-blocking) |
| `run_forever()` | `start()` then block until `KeyboardInterrupt` |
| `stop()` | Stop threads |
| `close()` | Stop threads and close the HID device |

## CLI

```
soomfon info              show device info and firmware version
soomfon brightness PCT    set brightness (0–100)
soomfon udev              print udev rules to stdout
soomfon --version
```

## Development

```bash
git clone ...
cd soomfon
uv sync
uv run python examples/demo.py
```

The two-thread architecture keeps the HID reader loop unblocked by user callbacks: a dedicated reader thread enqueues raw reports as fast as the OS delivers them; a dispatcher thread drains the queue and calls `on_key` / `on_encoder`. Slow callbacks (e.g. image uploads triggered by key presses) never cause encoder events to be dropped.

## Protocol notes

The device uses the **mirajazz v3** protocol ([reference](https://github.com/4ndv/mirajazz)):

- All OUT reports are 1025 bytes (`0x00` report-ID + 1024 data)
- Commands begin with the CRT magic: `00 43 52 54 00 00`
- Images are sent as: `BAT` header → JPEG chunks → `STP` commit
- IN reports are 512 bytes, prefixed with `ACK` (`41 43 4B`); byte 9 is the event code, byte 10 is the state

## Image rotation

The driver rotates images 270° before encoding. This was determined empirically on a SOOMFON Stream Controller SE — other hardware revisions or firmware versions may display images differently. If your keys appear rotated, change `_IMG_ROT` in `src/soomfon/_device.py` to `0`, `90`, or `180`.

## License

MIT
