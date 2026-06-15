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


def fetch(ref, path, repo=FLIPPER_REPO):
    """Fetch a .ir file from a Flipper-IRDB repo (or fork) at a ref."""
    url = f"{RAW_BASE}/{repo}/{ref}/{path.lstrip('/')}"
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
    """Stable, valid, non-reserved ESPHome id ('Return' -> ir_return).

    Always `ir_`-prefixed: it guarantees a leading letter and dodges ESPHome /
    C++ reserved words (return, switch, class, default, …) that arbitrary remote
    button names would otherwise collide with.
    """
    s = "".join(c if c.isalnum() else "_" for c in text.lower())
    while "__" in s:
        s = s.replace("__", "_")
    s = s.strip("_")
    return f"ir_{s}" if s else "ir_unnamed"


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


def _mirror_out(path):
    """Map an .ir path to its .yaml mirror, preserving directory and case.

    'TVs/Sony/Sony_Bravia.ir' -> 'TVs/Sony/Sony_Bravia.yaml'. This is what a
    device's `files:` entry references, so a bare `path` "just works".
    """
    base = path[:-3] if path.endswith(".ir") else os.path.splitext(path)[0]
    return base + ".yaml"


def _default_branch(repo):
    import json
    try:
        with urllib.request.urlopen(f"https://api.github.com/repos/{repo}", timeout=15) as resp:
            return json.load(resp).get("default_branch") or "main"
    except Exception:
        return "main"


def _ensure_repo(cache, repo, branch, flipper_path):
    """Generate (once) a bare git repo for <flipper_path> from <flipper_path>.ir."""
    import subprocess
    import tempfile

    repodir = os.path.join(cache, flipper_path + ".git")
    if os.path.isdir(repodir):
        return
    text = fetch(branch, flipper_path + ".ir", repo=repo)
    yaml = generate(parse_ir(text), branch, flipper_path + ".ir", None, "")
    work = tempfile.mkdtemp()
    name = os.path.basename(flipper_path) + ".yaml"
    with open(os.path.join(work, name), "w", encoding="utf-8") as handle:
        handle.write(yaml)

    def git(*args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    git("init", "-q", "-b", "main", cwd=work)
    git("config", "user.email", "codegen@local", cwd=work)
    git("config", "user.name", "ir-codegen", cwd=work)
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", name, cwd=work)
    os.makedirs(os.path.dirname(repodir), exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--bare", work, repodir], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    git("update-server-info", cwd=repodir)


def serve_http(port=9418, repo=FLIPPER_REPO, ref=None):
    """Lazy git-over-HTTP — the path-less add-on mode.

    A device clones `http://<host>:<port>/<Flipper/path>.git`; the component is
    generated on first request from `<path>.ir` in `repo`. The only knob is the
    source repo, so pointing at a fork is trivial. `ref` is optional (defaults to
    the repo's default branch); CI pins it for determinism.
    """
    import http.server
    import re as _re
    import subprocess
    import tempfile
    import threading
    from urllib.parse import urlsplit

    branch = ref or _default_branch(repo)
    cache = tempfile.mkdtemp(prefix="irdb-http-")
    lock = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self._serve()

        def do_POST(self):
            self._serve()

        def _serve(self):
            split = urlsplit(self.path)
            match = _re.match(r"^/(.+?\.git)(/.*)$", split.path)
            if not match:
                self.send_error(404)
                return
            try:
                with lock:
                    _ensure_repo(cache, repo, branch, match.group(1)[:-4])
            except Exception as err:
                self.send_error(404, f"cannot generate: {err}")
                return

            # Smart HTTP via git-http-backend (supports shallow clones).
            env = {
                **os.environ,
                "GIT_PROJECT_ROOT": cache,
                "GIT_HTTP_EXPORT_ALL": "1",
                "PATH_INFO": split.path,
                "QUERY_STRING": split.query,
                "REQUEST_METHOD": self.command,
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "GIT_PROTOCOL": self.headers.get("Git-Protocol", ""),
                "REMOTE_ADDR": self.client_address[0],
            }
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            proc = subprocess.run(["git", "http-backend"], input=body, env=env, capture_output=True)

            out = proc.stdout
            sep = b"\r\n\r\n" if b"\r\n\r\n" in out else b"\n\n"
            head, _, payload = out.partition(sep)
            status = 200
            headers = []
            for line in head.splitlines():
                if not line.strip():
                    continue
                key, _, val = line.partition(b":")
                key, val = key.strip(), val.strip()
                if key.lower() == b"status":
                    status = int(val.split(b" ")[0])
                else:
                    headers.append((key.decode("latin-1"), val.decode("latin-1")))
            self.send_response(status)
            for key, val in headers:
                self.send_header(key, val)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    print(f"git-http: http://0.0.0.0:{port}/<Flipper/path>.git  (source {repo}@{branch})", flush=True)
    http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--serve", action="store_true", help="run a git:// service ESPHome can pull from")
    parser.add_argument("--from-options", dest="from_options", help="read --serve options from a JSON file (Home Assistant add-on)")
    parser.add_argument("--port", type=int, default=9418, help="listen port for --serve")
    parser.add_argument("--repo", default=FLIPPER_REPO, help="source Flipper-IRDB repo or fork (path-less --serve)")
    parser.add_argument("--out", help="served component path (default: the --path with .yaml, dirs preserved)")
    parser.add_argument("--file", help="local .ir file")
    parser.add_argument("--path", help="path within the Flipper-IRDB repo")
    parser.add_argument("--ref", default=None, help="Flipper-IRDB ref to pin (default: the repo's default branch)")
    parser.add_argument("--tx", dest="tx_id", help="remote_transmitter id (omit if you only have one)")
    parser.add_argument("--prefix", default="", help='button name prefix, e.g. "TV"')
    args = parser.parse_args(argv)

    if args.from_options:
        import json

        with open(args.from_options, encoding="utf-8") as handle:
            opts = json.load(handle)
        # Path-less: the only knob is the source repo (a fork works as-is).
        serve_http(
            port=int(opts.get("port", 9418)),
            repo=opts.get("repo") or FLIPPER_REPO,
            ref=opts.get("ref"),
        )
        return 0

    if args.serve:
        if args.path:
            # Single-component git:// service (CLI / one-off).
            out = args.out or _mirror_out(args.path)
            serve(port=args.port, ref=args.ref or "main", path=args.path, out=out, tx_id=args.tx_id, prefix=args.prefix)
        else:
            # Path-less lazy git-over-HTTP service (the add-on).
            serve_http(port=args.port, repo=args.repo, ref=args.ref)
        return 0

    if not args.file and not args.path:
        parser.error("one of --file / --path is required (or use --serve)")

    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            text = handle.read()
        ref, src = "(local)", args.file
    else:
        text = fetch(args.ref or "main", args.path, repo=args.repo)
        ref, src = args.ref or "main", args.path

    sys.stdout.write(generate(parse_ir(text), ref, src, args.tx_id, args.prefix))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
