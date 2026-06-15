#!/usr/bin/env python3
"""Flipper .ir -> ESPHome remote_transmitter YAML.

Two modes:
  * one-shot CLI : print the generated ESPHome YAML for a Flipper file.
  * --serve      : run a tiny **git service** — generate the component, commit it
                   into a bare repo, and serve it over the git:// protocol so an
                   ESPHome build pulls it with `packages: url: git://host/irdb.git`.
                   This is the add-on "posing as a repo": ESPHome clones from the
                   live container at compile time.

Given a *pinned Flipper-IRDB git ref* + a path, fetch the `.ir` file and emit one
ESPHome `button` per IR signal.

Design decisions (locked):
  * Reproducibility comes from the Flipper ref itself (--ref), not a local copy.
  * The generator runs at ESPHome *compile* time and may hit the network live.
  * Naming/dedup is intentionally minimal for now.

Protocol coverage:
  * type: raw                               -> transmit_raw   (always correct)
  * type: parsed NEC / NECext / NEC42(ext)  -> transmit_nec
  * type: parsed SIRC / SIRC15 / SIRC20     -> transmit_sony
  * everything else                         -> `# TODO unsupported` comment

VERIFY generated parsed codes against a live `remote_receiver` capture before
trusting them — compiling only proves the YAML is *valid*, not that the code is
the *correct* one for your device.
"""

import argparse
import os
import sys
import urllib.request

FLIPPER_REPO = "Lucaslhm/Flipper-IRDB"
RAW_BASE = "https://raw.githubusercontent.com"

SONY_NBITS = {"SIRC": 12, "SIRC15": 15, "SIRC20": 20}


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


def _le(field):
    """'04 03 00 00' -> integer 0x0304 (little-endian)."""
    out = 0
    for i, byte in enumerate(field.split()):
        out |= int(byte, 16) << (8 * i)
    return out


def emit_raw(entry):
    freq = int(entry.get("frequency", "38000"))
    nums = [int(x) for x in entry["data"].split()]
    # Flipper raw data is all-positive, alternating mark/space starting on a
    # mark. ESPHome wants signed: + = carrier on (mark), - = off (space).
    code = [n if i % 2 == 0 else -n for i, n in enumerate(nums)]
    return ("transmit_raw", {"carrier_frequency": freq, "code": code})


def emit_nec(entry, ext=False):
    addr = _le(entry["address"])
    cmd = _le(entry["command"]) & 0xFF
    if ext:
        address = addr & 0xFFFF              # NECext: full 16-bit address
    else:
        a = addr & 0xFF
        address = a | ((a ^ 0xFF) << 8)      # NEC: addr | (~addr << 8)
    command = cmd | ((cmd ^ 0xFF) << 8)
    return ("transmit_nec", {"address": f"0x{address:04X}", "command": f"0x{command:04X}"})


def emit_sony(entry):
    nbits = SONY_NBITS[entry["protocol"]]
    address = _le(entry["address"])
    command = _le(entry["command"]) & 0x7F   # SIRC command is 7 bits
    # ESPHome sends LSB-first: 7-bit command, then address.
    data = command | (address << 7)
    return ("transmit_sony", {"data": f"0x{data:X}", "nbits": nbits})


def _button_name(prefix, name):
    return f"{prefix} {name}".strip() if prefix else name


def _slug(text):
    """Stable, valid ESPHome id from a name ('Bravia Power' -> bravia_power)."""
    s = "".join(c if c.isalnum() else "_" for c in text.lower())
    while "__" in s:
        s = s.replace("__", "_")
    s = s.strip("_")
    if not s or not s[0].isalpha():
        s = "ir_" + s
    return s


def generate(entries, ref, src, tx_id, prefix):
    out = [
        f"# Generated from {FLIPPER_REPO}@{ref}",
        f"#   path: {src}",
        "# Prototype (flipper_ir_to_esphome.py) — raw + NEC/NECext + Sony SIRC.",
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
            elif typ == "parsed" and proto in SONY_NBITS:
                action, args = emit_sony(entry)
            else:
                skipped.append((name, proto or typ or "unknown"))
                continue
        except (KeyError, ValueError):
            skipped.append((name, f"{proto or typ} (parse error)"))
            continue

        bname = _button_name(prefix, name)
        out.append("  - platform: template")
        out.append(f"    id: {_slug(bname)}")
        out.append(f'    name: "{bname}"')
        out.append("    on_press:")
        out.append(f"      - remote_transmitter.{action}:")
        if tx_id:
            out.append(f"          transmitter_id: {tx_id}")
        if action == "transmit_raw":
            code = ", ".join(str(x) for x in args["code"])
            out.append(f"          carrier_frequency: {args['carrier_frequency']}")
            out.append(f"          code: [{code}]")
        elif action == "transmit_sony":
            out.append(f"          data: {args['data']}")
            out.append(f"          nbits: {args['nbits']}")
        else:  # transmit_nec
            out.append(f"          address: {args['address']}")
            out.append(f"          command: {args['command']}")

    for name, why in skipped:
        out.append(f"# TODO unsupported: {name} ({why})")
    return "\n".join(out) + "\n"


def serve(port=9418, ref="main", path=None, out="component.yaml", tx_id=None, prefix=""):
    """Generate the component, bake it into a bare git repo, and serve git://.

    An ESPHome build pulls it with:

        packages:
          x:
            url: "git://<host>:<port>/irdb.git"
            ref: main
            files: ["<out>"]

    The container listens for git clone requests — this is the add-on serving
    layer, exercised for real (no pre-generated files on disk in the consumer).
    """
    import subprocess
    import tempfile

    if not path:
        raise SystemExit("--serve requires --path")

    webroot = tempfile.mkdtemp(prefix="irdb-")
    work = tempfile.mkdtemp(prefix="irdb-work-")
    yaml = generate(parse_ir(fetch(ref, path)), ref, path, tx_id, prefix)
    out_path = os.path.join(work, out)
    os.makedirs(os.path.dirname(out_path) or work, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(yaml)

    def git(*args, cwd):
        subprocess.run(
            ["git", *args], cwd=cwd, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    git("init", "-q", "-b", "main", cwd=work)
    git("config", "user.email", "codegen@local", cwd=work)
    git("config", "user.name", "ir-codegen", cwd=work)
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", f"generated {out}", cwd=work)
    bare = os.path.join(webroot, "irdb.git")
    subprocess.run(
        ["git", "clone", "-q", "--bare", work, bare], check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    print(f"git daemon: git://0.0.0.0:{port}/irdb.git  (ref main, file {out})", flush=True)
    os.execvp("git", [
        "git", "daemon", "--reuseaddr", "--export-all", "--verbose",
        f"--base-path={webroot}", f"--port={port}", "--listen=0.0.0.0", webroot,
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--serve", action="store_true", help="run a git:// service ESPHome can pull from")
    parser.add_argument("--port", type=int, default=9418, help="git daemon port for --serve")
    parser.add_argument("--out", help="component filename served by --serve (default: derived from --path)")
    parser.add_argument("--file", help="local .ir file")
    parser.add_argument("--path", help="path within the Flipper-IRDB repo")
    parser.add_argument("--ref", default="main", help="Flipper-IRDB git ref — pin for reproducibility")
    parser.add_argument("--tx", dest="tx_id", help="remote_transmitter id (omit if you only have one)")
    parser.add_argument("--prefix", default="", help='button name prefix, e.g. "TV"')
    args = parser.parse_args(argv)

    if args.serve:
        if not args.path:
            parser.error("--serve requires --path")
        out = args.out or (os.path.splitext(os.path.basename(args.path))[0].lower() + ".yaml")
        serve(port=args.port, ref=args.ref, path=args.path, out=out, tx_id=args.tx_id, prefix=args.prefix)
        return 0

    if not args.file and not args.path:
        parser.error("one of --file / --path is required (or use --serve)")

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
