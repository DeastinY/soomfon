"""soomfon — command-line tool."""

from __future__ import annotations

import argparse
import sys

import hid

from . import VENDOR_ID, PRODUCT_ID, __version__

_UDEV = """\
# SOOMFON Stream Controller SE (and compatible Mirabox / Ajazz AKP03 devices)
# Install:
#   sudo cp 99-soomfon.rules /etc/udev/rules.d/
#   sudo udevadm control --reload-rules && sudo udevadm trigger
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1500", ATTRS{idProduct}=="3001", TAG+="uaccess"
"""


def _cmd_info(_args: argparse.Namespace) -> None:
    devs = hid.enumerate(VENDOR_ID, PRODUCT_ID)
    if not devs:
        sys.exit("No SOOMFON device found.")
    for d in devs:
        print(f"Interface {d['interface_number']}: {d['path'].decode()}")
        print(f"  Manufacturer : {d['manufacturer_string']}")
        print(f"  Product      : {d['product_string']}")
        if d["serial_number"]:
            print(f"  Serial       : {d['serial_number']}")
    dev = hid.Device(path=devs[0]["path"])
    try:
        fw = dev.get_feature_report(0x01, 20)
        print(f"  Firmware     : {bytes(fw[1:]).rstrip(b'\\x00').decode()}")
    except Exception:
        pass
    finally:
        dev.close()


def _cmd_brightness(args: argparse.Namespace) -> None:
    from . import Soomfon
    with Soomfon() as deck:
        deck.set_brightness(args.value)
    print(f"Brightness → {args.value}%")


def _cmd_udev(_args: argparse.Namespace) -> None:
    print(_UDEV, end="")


def main() -> None:
    p = argparse.ArgumentParser(
        prog="soomfon",
        description=f"SOOMFON Stream Controller SE  v{__version__}",
    )
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", metavar="COMMAND")

    sub.add_parser("info", help="show connected device information")

    bp = sub.add_parser("brightness", help="set display brightness (0–100)")
    bp.add_argument("value", type=int, metavar="PCT")

    sub.add_parser("udev", help="print udev rules to stdout")

    args = p.parse_args()
    dispatch = {"info": _cmd_info, "brightness": _cmd_brightness, "udev": _cmd_udev}
    fn = dispatch.get(args.cmd)
    if fn:
        fn(args)
    else:
        p.print_help()
