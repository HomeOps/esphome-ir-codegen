#!/usr/bin/env python3
"""Flipper .ir -> ESPHome remote_transmitter YAML (prototype / baby step).

The transformation core for the planned Home Assistant add-on: given a *pinned
Flipper-IRDB git ref* and a path within that repo, fetch the `.ir` file and emit
ESPHome `button` entities, one per IR signal.

Design decisions (locked):
  * Reproducibility comes from the Flipper ref itself (--ref), not a local copy.
  * The generator runs at ESPHome *compile* time and may hit the network live.
  * Naming/dedup is intentionally minimal for now.

Protocol coverage (baby step):
  * type: raw                       -> remote_transmitter.transmit_raw   (always correct)
  * type: parsed, NEC / NECext / NEC42(ext) -> remote_transmitter.transmit_nec
  * everything else                 -> emitted as a `# TODO unsupported` comment

VERIFY generated parsed codes against a live `remote_receiver` capture before
trusting them (the receiver dump prints the same 16-bit NEC words this emits).
"""

import argparse
import re
import sys
import urllib.request

FLIPPER_REPO = "Lucaslhm/Flipper-IRDB"
RAW_BASE = "https://raw.githubusercontent.com"


def fetch(ref, path):
    """Fetch a .ir file from Flipper-IRDB at a pinned ref."""
    url = f"{RAW_BASE}/{FLIPPER_REPO}/{ref}/{path.lstrip('/')}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read().decode("utf-8")


def parse_ir(text):
    """Parse a Flipper .ir file into a list of signal dicts (split on '#')."""
    entries, cur = [], {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("Filetype", "Version")):
            continue
        if line == "#":
            if cur:
                entries.append(cur)
                cur = {}
            continue
        key, sep, val = line.partition(":")
        if sep:
            cur[key.strip()] = val.strip()
    if cur:
        entries.append(cur)
    return entries


def _le_bytes(field):
    """'04 00 00 00' -> [0x04, 0x00, 0x00, 0x00]."""
    return [int(b, 16) for b in field.split()]


def emit_raw(entry):
    freq = int(entry.get("frequency", "38000"))
    nums = [int(x) for x in entry["data"].split()]
    # Flipper raw data is all-positive, alternating mark/space starting on a
    # mark. ESPHome wants signed: + = carrier on (mark), - = off (space).
    code = [n if i % 2 == 0 else -n for i, n in enumerate(nums)]
    return ("transmit_raw", {"carrier_frequency": freq, "code": code})


def emit_nec(entry, ext=False):
    addr = _le_bytes(entry["address"])
    cmd = _le_bytes(entry["command"])
    if ext:
        # NECext: full 16-bit address, no inversion check.
        address = addr[0] | (addr[1] << 8)
    else:
        # Standard NEC: ESPHome's 16-bit word is addr | (~addr << 8).
        address = addr[0] | ((addr[0] ^ 0xFF) << 8)
    command = cmd[0] | ((cmd[0] ^ 0xFF) << 8)
    return ("transmit_nec", {"address": f"0x{address:04X}", "command": f"0x{command:04X}"})


def _button_name(prefix, name):
    return f"{prefix} {name}".strip() if prefix else name


def generate(entries, ref, src, tx_id, prefix):
    out = [
        f"# Generated from {FLIPPER_REPO}@{ref}",
        f"#   path: {src}",
        "# Prototype (flipper_ir_to_esphome.py) — supports raw + NEC/NECext.",
        "# VERIFY parsed codes against a live remote_receiver capture.",
        "button:",
    ]
    skipped = []
    for entry in entries:
        name = entry.get("name", "unnamed")
        typ = entry.get("type")
        proto = entry.get("protocol", "")
        try:
            if typ == "raw":
                action, args = emit_raw(entry)
            elif typ == "parsed" and proto in ("NEC", "NECext", "NEC42", "NEC42ext"):
                action, args = emit_nec(entry, ext=proto.endswith("ext"))
            else:
                skipped.append((name, proto or typ or "unknown"))
                continue
        except (KeyError, ValueError):
            skipped.append((name, f"{proto or typ} (parse error)"))
            continue

        out.append("  - platform: template")
        out.append(f'    name: "{_button_name(prefix, name)}"')
        out.append("    on_press:")
        out.append(f"      - remote_transmitter.{action}:")
        if tx_id:
            out.append(f"          transmitter_id: {tx_id}")
        if action == "transmit_raw":
            code = ", ".join(str(x) for x in args["code"])
            out.append(f"          carrier_frequency: {args['carrier_frequency']}")
            out.append(f"          code: [{code}]")
        else:
            out.append(f"          address: {args['address']}")
            out.append(f"          command: {args['command']}")

    for name, why in skipped:
        out.append(f"# TODO unsupported: {name} ({why})")
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="local .ir file")
    source.add_argument("--path", help="path within the Flipper-IRDB repo")
    parser.add_argument("--ref", default="main", help="Flipper-IRDB git ref — pin for reproducibility")
    parser.add_argument("--tx", dest="tx_id", help="remote_transmitter id (omit if you only have one)")
    parser.add_argument("--prefix", default="", help='button name prefix, e.g. "TV"')
    args = parser.parse_args(argv)

    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            text = handle.read()
        ref, src = "(local)", args.file
    else:
        text = fetch(args.ref, args.path)
        ref, src = args.ref, args.path

    sys.stdout.write(generate(parse_ir(text), ref, src, args.tx_id, args.prefix))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
