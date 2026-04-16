#!/usr/bin/env python3
"""
SOOMFON Stream Controller SE — demo / entry point.

Run:  uv run python main.py

Key layout
  0-5  : six LCD macro keys (have displays)
  6-8  : three non-display buttons
  9-11 : three encoder *press* events (knob 0 / 1 / 2)

Encoders also fire on_encoder(enc_idx, delta) when twisted.
"""
from __future__ import annotations

import sys
from PIL import Image, ImageDraw, ImageFont

from soomfon import Soomfon

LCD_KEYS = range(6)   # only keys 0-5 have displays

# ── Image helpers ────────────────────────────────────────────────────────────

def make_label(
    line1: str,
    bg: tuple[int, int, int],
    line2: str = "",
    fg: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """60×60 image with up to two centred text lines."""
    img = Image.new("RGB", (60, 60), bg)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=13)
    except TypeError:
        font = ImageFont.load_default()

    lines = [l for l in [line1, line2] if l]
    total_h = sum(draw.textbbox((0, 0), l, font=font)[3] for l in lines) + (len(lines) - 1) * 3
    y = (60 - total_h) // 2
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font)
        w = bb[2] - bb[0]
        draw.text(((60 - w) // 2, y), line, fill=fg, font=font)
        y += bb[3] + 3
    return img


# ── Key definitions ──────────────────────────────────────────────────────────

KEY_COLORS = [
    (180,  40,  40),  # 0 — red
    (180, 110,  40),  # 1 — orange
    (160, 160,  40),  # 2 — yellow
    ( 40, 160,  40),  # 3 — green
    ( 40, 110, 180),  # 4 — blue
    (110,  40, 180),  # 5 — purple
]
KEY_LABELS = ["1", "2", "3", "4", "5", "6"]

# Knob names for terminal output
KNOB_NAMES = ["Left knob", "Mid knob", "Right knob"]


# ── Demo ─────────────────────────────────────────────────────────────────────

def demo() -> None:
    print("Connecting to SOOMFON Stream Controller SE…")

    # Track per-knob accumulated values for display
    knob_values = [0, 0, 0]

    with Soomfon() as deck:
        deck.set_brightness(70)

        # Paint the 6 LCD keys
        print("Setting LCD key images…")
        for i in LCD_KEYS:
            img = make_label(KEY_LABELS[i], KEY_COLORS[i])
            deck.set_key_image(i, img)
            print(f"  Key {i} → '{KEY_LABELS[i]}' {KEY_COLORS[i]}")

        # ── Key / button events ──────────────────────────────────────────────
        @deck.on_key
        def handle_key(key: int, pressed: bool) -> None:
            action = "↓" if pressed else "↑"

            if key in LCD_KEYS:
                print(f"  LCD key {key} {action}")
                if pressed:
                    deck.set_key_color(key, 255, 255, 255)
                else:
                    img = make_label(KEY_LABELS[key], KEY_COLORS[key])
                    deck.set_key_image(key, img)

            elif key in range(6, 9):
                print(f"  Button {key} {action}")

            elif key in range(9, 12):
                enc = key - 9
                print(f"  {KNOB_NAMES[enc]} press {action}  (val={knob_values[enc]})")

        # ── Encoder twist events ─────────────────────────────────────────────
        @deck.on_encoder
        def handle_encoder(enc: int, delta: int) -> None:
            knob_values[enc] += delta
            direction = "→" if delta > 0 else "←"
            print(f"  {KNOB_NAMES[enc]} {direction}  val={knob_values[enc]}")

        print("\nListening — press Ctrl-C to quit.\n")
        deck.run_forever()

        print("\nClearing keys before exit…")
        deck.clear_all()


if __name__ == "__main__":
    try:
        demo()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
