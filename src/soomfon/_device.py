"""
SOOMFON Stream Controller SE — Python driver.

Protocol: mirajazz v3 (Ajazz AKP03 / Mirabox N3/N4 rev.2 compatible)
Reference: https://github.com/4ndv/mirajazz

OUT reports : 1025 bytes  (0x00 report-ID + 1024 data)
              every command starts with CRT magic: 00 43 52 54 00 00
IN  reports : 512 bytes, valid ones start with ACK: 41 43 4B
              byte 9  = event code  (which key / encoder)
              byte 10 = state       (1 pressed / down, 0 released / up)
Images      : 60×60 JPEG q90, rotated 270° before encoding
"""

from __future__ import annotations

import io
import queue
import threading
from typing import Callable

import hid
from PIL import Image

VENDOR_ID  = 0x1500
PRODUCT_ID = 0x3001

# ── Protocol ─────────────────────────────────────────────────────────────────

_PACK = 1024
_RPT  = _PACK + 1                              # total report bytes incl. report-ID

_CRT  = b"\x00\x43\x52\x54\x00\x00"           # command prefix
_ACK  = b"\x41\x43\x4b"                        # expected IN-report prefix

_IMG_SIZE    = (60, 60)
_IMG_QUALITY = 90
_IMG_ROT     = 270


def _cmd(tail: bytes) -> bytes:
    return (_CRT + tail).ljust(_RPT, b"\x00")

_DIS      = _cmd(b"\x44\x49\x53")
_LIG_INIT = _cmd(b"\x4c\x49\x47\x00\x00\x00\x00")
_STP      = _cmd(b"\x53\x54\x50")
_HAN      = _cmd(b"\x48\x41\x4e")

def _lig(pct: int) -> bytes:
    return _cmd(bytes([0x4c, 0x49, 0x47, 0x00, 0x00, max(0, min(100, pct))]))

def _cle(key: int) -> bytes:                   # key=-1 → clear all (0xFF on wire)
    wire = 0xFF if key < 0 else key + 1
    return _cmd(bytes([0x43, 0x4c, 0x45, 0x00, 0x00, 0x00, wire]))

def _bat(key: int, size: int) -> bytes:
    return _cmd(bytes([0x42, 0x41, 0x54, 0x00, 0x00,
                       (size >> 8) & 0xFF, size & 0xFF, key + 1]))

def _jpeg(image: Image.Image) -> bytes:
    img = image.convert("RGB").resize(_IMG_SIZE, Image.LANCZOS).rotate(_IMG_ROT)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_IMG_QUALITY)
    return buf.getvalue()

# ── Input maps ───────────────────────────────────────────────────────────────

# byte 9 → key index (0-based); LCD keys 0-5, plain buttons 6-8
_KEY_MAP: dict[int, int] = {
    1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5,
    0x25: 6, 0x30: 7, 0x31: 8,
}

# byte 9 → (encoder index, delta)
_ENC_TWIST: dict[int, tuple[int, int]] = {
    0x90: (0, -1), 0x91: (0, +1),
    0x50: (1, -1), 0x51: (1, +1),
    0x60: (2, -1), 0x61: (2, +1),
}

# byte 9 → encoder index (presses reported as key 9/10/11)
_ENC_PRESS: dict[int, int] = {0x33: 0, 0x35: 1, 0x34: 2}

# ── Device class ─────────────────────────────────────────────────────────────

class Soomfon:
    """
    Driver for the SOOMFON Stream Controller SE.

    Usage::

        with Soomfon() as deck:
            deck.set_brightness(70)
            deck.set_key_image(0, Image.open("icon.png"))

            @deck.on_key
            def on_key(key: int, pressed: bool): ...

            @deck.on_encoder
            def on_enc(enc: int, delta: int): ...   # delta is always ±1

            deck.run_forever()
    """

    def __init__(self) -> None:
        devs = hid.enumerate(VENDOR_ID, PRODUCT_ID)
        if not devs:
            raise RuntimeError(f"SOOMFON not found ({VENDOR_ID:#06x}:{PRODUCT_ID:#06x})")
        path = next(d["path"] for d in devs if d["interface_number"] == 0)
        self._dev  = hid.Device(path=path)
        self._lock = threading.Lock()
        self._q: queue.SimpleQueue[bytes] = queue.SimpleQueue()
        self._running = False
        self._threads: list[threading.Thread] = []
        self._key_cb: Callable[[int, bool], None] | None = None
        self._enc_cb: Callable[[int, int],  None] | None = None
        self._write(_DIS)
        self._write(_LIG_INIT)

    # ── context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> Soomfon:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── display ───────────────────────────────────────────────────────────────

    def set_brightness(self, pct: int) -> None:
        self._write(_lig(pct))

    def set_key_image(self, key: int, image: Image.Image) -> None:
        data = _jpeg(image)
        with self._lock:
            self._dev.write(_bat(key, len(data)))
            for off in range(0, len(data), _PACK):
                chunk = data[off:off + _PACK]
                self._dev.write(b"\x00" + chunk + bytes(_PACK - len(chunk)))
            self._dev.write(_STP)

    def set_key_color(self, key: int, r: int, g: int, b: int) -> None:
        self.set_key_image(key, Image.new("RGB", _IMG_SIZE, (r, g, b)))

    def clear_key(self, key: int) -> None:
        with self._lock:
            self._dev.write(_cle(key))
            self._dev.write(_STP)

    def clear_all(self) -> None:
        with self._lock:
            self._dev.write(_cle(-1))
            self._dev.write(_STP)

    def sleep(self) -> None:
        self._write(_HAN)

    # ── events ────────────────────────────────────────────────────────────────

    def on_key(self, cb: Callable[[int, bool], None]) -> Callable:
        """key 0-5: LCD buttons; 6-8: plain buttons; 9-11: encoder presses."""
        self._key_cb = cb
        return cb

    def on_encoder(self, cb: Callable[[int, int], None]) -> Callable:
        """encoder 0-2, delta ±1 per hardware detent."""
        self._enc_cb = cb
        return cb

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._dev.nonblocking = False
        for target, name in (
            (self._read_loop,     "soomfon-reader"),
            (self._dispatch_loop, "soomfon-dispatcher"),
        ):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._running = False
        self._q.put(b"")               # unblock dispatcher
        for t in self._threads:
            t.join(timeout=1)
        self._threads.clear()

    def close(self) -> None:
        self.stop()
        self._dev.close()

    def run_forever(self) -> None:
        self.start()
        try:
            self._threads[0].join()
        except KeyboardInterrupt:
            pass

    # ── internal ─────────────────────────────────────────────────────────────

    def _write(self, data: bytes) -> None:
        self._dev.write(data)

    def _read_loop(self) -> None:
        while self._running:
            data = self._dev.read(512, timeout=100)
            if data and len(data) >= 11:
                self._q.put(bytes(data))

    def _dispatch_loop(self) -> None:
        while self._running:
            try:
                data = self._q.get(timeout=0.1)
            except queue.Empty:
                continue
            if len(data) < 11 or data[:3] != _ACK:
                continue
            code  = data[9]
            state = data[10]
            if code == 0:
                continue
            if code in _KEY_MAP:
                if self._key_cb:
                    self._key_cb(_KEY_MAP[code], bool(state))
            elif code in _ENC_TWIST:
                enc, delta = _ENC_TWIST[code]
                if self._enc_cb:
                    self._enc_cb(enc, delta)
            elif code in _ENC_PRESS:
                if self._key_cb:
                    self._key_cb(9 + _ENC_PRESS[code], bool(state))
