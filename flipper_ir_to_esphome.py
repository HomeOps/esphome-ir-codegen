#!/usr/bin/env python3
"""IR code sets -> ESPHome remote_transmitter YAML, served as git repos.

Two modes:
  * one-shot CLI : print the generated ESPHome YAML for a Flipper file.
  * --serve      : run a smart-HTTP **git service**. The Flipper source repo *is*
                   the URL path and the ref *is* the device's `packages: ref:`, so
                   an ESPHome build pulls a component with
                   `url: http://host/<owner>/<name>.git, ref: <branch>,
                    files: [<path>]`. The matching repo@ref is cloned and
                   transformed *on demand* — cached, and rebuilt when the source
                   HEAD moves. `ha-ir.git` is a reserved path served from the
                   installed infrared-protocols library.

The shared infrared-protocols encoder turns every command into transmit_raw, so
the two sources differ only in path layout:
  * <owner>/<name>.git -> a Flipper-IRDB repo or fork; path mirrors the tree,
                          e.g. TVs/Sony/Sony_Bravia.yaml (the device picks the
                          source repo by URL and the ref by `ref:`).
  * ha-ir.git          -> infrared-protocols' own curated code sets (vizio/tv.yaml)

Design decisions (locked):
  * repo + ref are per-device (URL path + `ref:`), never add-on config.
  * Build on demand keyed by (repo, ref); refresh when the source HEAD moves, so
    new commits propagate without restarting the add-on.
  * `ha-ir.git` is a reserved, library-built repo; adding another reserved
    adapter is just one more prebuilt `<name>.git` under the cache dir.

Protocol coverage:
  * type: raw                            -> transmit_raw (direct passthrough)
  * type: parsed (NEC/NECext, SIRC/15/20,
    Samsung32, RC5/RC5X, Sharp)          -> transmit_raw, encoded by the
                                            infrared-protocols library
  * everything else                      -> `# TODO unsupported` comment

We keep no protocol math of our own: parsed signals are encoded by the
infrared-protocols library (NECCommand, SonyCommand, …) and emitted as the raw
timings it returns. VERIFY generated parsed codes against a live
`remote_receiver` capture before trusting them — compiling only proves the YAML
is *valid*, not that the code is the *correct* one for your device.
"""

import argparse
import os
import re
import sys
import threading
import urllib.request

FLIPPER_REPO = "Lucaslhm/Flipper-IRDB"
RAW_BASE = "https://raw.githubusercontent.com"

# Flipper SIRC variants -> SonyCommand address width (command is always 7-bit).
SONY_ADDRESS_BITS = {"SIRC": 5, "SIRC15": 8, "SIRC20": 13}

# The library returns ONE frame per command (by design — repetition is the
# transmit layer's job, exactly as HA's IR proxy repeats it). In the ESPHome
# compile path *we* are that layer, so library-encoded signals are sent with a
# repeat: Sony SIRC and several others need ~3 frames before a device acts.
PARSED_REPEAT_TIMES = 3
PARSED_REPEAT_WAIT = "40ms"


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


# Every parsed protocol is encoded by the infrared-protocols library — we keep no
# protocol math of our own. The library returns raw timings, so every parsed
# signal is emitted as transmit_raw. (Flipper `type: raw` is a direct passthrough;
# there is no protocol to reuse there.)
def _command_for(entry):
    """Build an infrared_protocols Command for a Flipper *parsed* entry.

    Returns a Command, or None if the protocol isn't one the library encodes.
    Field values pass straight through so the library's own range checks reject
    bad data (raising ValueError) rather than us emitting a wrong-but-plausible
    code. Imports are local so the core stays importable without the library.
    """
    proto = entry.get("protocol", "")
    addr = _le(entry["address"])
    cmd = _le(entry["command"])

    if proto in ("NEC", "NECext"):
        from infrared_protocols.commands.nec import NECCommand

        # NECCommand selects standard (<=0xFF, adds inversion) vs extended
        # (16-bit) from the address width — matching Flipper NEC vs NECext.
        return NECCommand(address=addr & 0xFFFF, command=cmd & 0xFF)
    if proto in SONY_ADDRESS_BITS:
        from infrared_protocols.commands.sony import SonyCommand

        return SonyCommand(address=addr, address_bits=SONY_ADDRESS_BITS[proto], command=cmd)
    if proto == "Samsung32":
        from infrared_protocols.commands.samsung import Samsung32Command

        return Samsung32Command(address=addr & 0xFFFF, command=cmd & 0xFF)
    if proto in ("RC5", "RC5X"):
        from infrared_protocols.commands.rc5 import RC5Command

        return RC5Command(address=addr, command=cmd)
    if proto == "Sharp":
        from infrared_protocols.commands.sharp import SharpCommand

        return SharpCommand(address=addr, command=cmd)
    return None


def emit_parsed(entry):
    """Encode a parsed protocol to transmit_raw via the library.

    Returns ('transmit_raw', {...}) or None if unmapped. May raise ValueError
    (bad fields) or ImportError (library absent); the caller falls back to a
    `# TODO unsupported` comment.
    """
    command = _command_for(entry)
    if command is None:
        return None
    return ("transmit_raw", {"carrier_frequency": command.modulation, "code": command.get_raw_timings()})


def _button_name(prefix, name):
    return f"{prefix} {name}".strip() if prefix else name


def _sanitize(text):
    """Lower-case, collapse non-alphanumerics to single underscores, trim."""
    s = "".join(c if c.isalnum() else "_" for c in text.lower())
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def _id_prefix(path):
    """Derive a button-id prefix '<category>_<brand>[_<model>]' from a path.

    'KVMs/Generic_8K_HDMI_DP_4Port_KVM.ir' -> 'kvm_generic'        (model dropped)
    'TVs/Sony/Sony_Bravia.ir'              -> 'tv_sony_bravia'     (model kept)
    'vizio/tv'                             -> 'vizio_tv'           (ha-ir layout)

    The category (first path segment) is singularized by dropping a trailing
    's'; the brand is the first underscore-token of the filename. Flipper's
    Category/Brand/Brand_Model layout repeats the brand in the file name, so when
    the filename's leading token matches the parent (brand) folder, the next word
    (the model) is kept — otherwise distinct models would collapse to one prefix.
    A single-segment path contributes only the brand; falls back to 'ir' when
    nothing usable remains, preserving the old leading-letter id guarantee.
    """
    parts = [p for p in path.replace("\\", "/").split("/") if p and p not in (".", "..")]
    if not parts:
        return "ir"
    tokens = [t for t in os.path.splitext(parts[-1])[0].split("_") if t]
    brand = tokens[0] if tokens else ""
    category = parts[0] if len(parts) >= 2 else ""
    if category.lower().endswith("s") and len(category) > 1:
        category = category[:-1]
    pieces = [category, brand]
    parent = parts[-2] if len(parts) >= 2 else ""
    if parent and brand and parent.lower() == brand.lower() and len(tokens) > 1:
        pieces.append(tokens[1])   # brand repeated in the file name -> keep the model
    prefix = _sanitize("_".join(p for p in pieces if p))
    return prefix or "ir"


def _slug(text, prefix="ir"):
    """Stable, valid, non-reserved ESPHome id ('Return' -> tv_sony_return).

    `prefix` (derived from the code-set path, e.g. 'tv_sony' / 'kvm_generic')
    namespaces ids so buttons from different remotes never collide, and it
    guarantees a leading letter that dodges ESPHome / C++ reserved words
    (return, switch, class, default, …) bare button names would collide with.
    """
    s = _sanitize(text)
    return f"{prefix}_{s}" if s else f"{prefix}_unnamed"


def _append_button(out, bname, carrier, code, tx_id, repeat, id_prefix="ir"):
    """Append one template button that fires a transmit_raw. Shared by every
    adapter — after encoding, all output is transmit_raw, so this is the only
    button renderer. `repeat` adds the transmit-layer repeat (library frames are
    single); a Flipper raw capture passes False (authoritative, sent as-is).
    `id_prefix` namespaces the button id (derived from the code-set path)."""
    code_str = ", ".join(str(x) for x in code)
    out.append("  - platform: template")
    out.append(f"    id: {_slug(bname, id_prefix)}")
    out.append(f'    name: "{bname}"')
    out.append("    on_press:")
    out.append("      - remote_transmitter.transmit_raw:")
    if tx_id:
        out.append(f"          transmitter_id: {tx_id}")
    out.append(f"          carrier_frequency: {carrier}")
    out.append(f"          code: [{code_str}]")
    if repeat:
        out.append("          repeat:")
        out.append(f"            times: {PARSED_REPEAT_TIMES}")
        out.append(f"            wait_time: {PARSED_REPEAT_WAIT}")


def generate(entries, ref, src, tx_id, prefix):
    """flipper adapter: render a component from parsed Flipper `.ir` entries."""
    id_prefix = _id_prefix(src)
    out = [
        f"# Generated from {FLIPPER_REPO}@{ref}",
        f"#   path: {src}",
        "# Parsed protocols encoded by infrared-protocols -> transmit_raw.",
        "# VERIFY parsed codes against a live remote_receiver capture.",
        "button:",
    ]
    skipped = []
    for entry in entries:
        name = entry.get("name", "unnamed")
        typ = entry.get("type")
        proto = entry.get("protocol", "")
        try:
            # raw is a passthrough; every parsed protocol is encoded by the
            # library. Both yield transmit_raw.
            result = emit_raw(entry) if typ == "raw" else emit_parsed(entry)
        except (KeyError, ValueError, ImportError):
            skipped.append((name, f"{proto or typ} (encode error)"))
            continue
        if result is None:
            skipped.append((name, proto or typ or "unknown"))
            continue
        _action, args = result
        # A raw capture is authoritative; library-encoded parsed frames are
        # single and need a transmit-layer repeat.
        _append_button(out, _button_name(prefix, name), args["carrier_frequency"],
                       args["code"], tx_id, repeat=(typ != "raw"), id_prefix=id_prefix)

    for name, why in skipped:
        out.append(f"# TODO unsupported: {name} ({why})")
    return "\n".join(out) + "\n"


def generate_from_commands(named_commands, src, tx_id=None):
    """ha-ir adapter: render a component from infrared-protocols `Command`s.

    `named_commands` is an iterable of (name, Command). Each is a single library
    frame -> transmit_raw with a transmit-layer repeat. Duplicate button ids are
    dropped (first wins)."""
    out = [
        f"# Generated from infrared-protocols code set: {src}",
        "# Curated codes encoded by infrared-protocols -> transmit_raw.",
        "# VERIFY codes against a live remote_receiver capture.",
        "button:",
    ]
    id_prefix = _id_prefix(src)
    seen = set()
    for name, command in named_commands:
        bid = _slug(name, id_prefix)
        if bid in seen:
            continue
        seen.add(bid)
        _append_button(out, name, command.modulation, command.get_raw_timings(),
                       tx_id, repeat=True, id_prefix=id_prefix)
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


def _make_bare_repo(cache, name, populate):
    """Build one adapter's bare repo `<name>.git` under `cache`.

    `populate(work)` writes the adapter's `.yaml` components into `work` and
    returns the count. git-http-backend serves any bare repo under the cache
    dir, so adding an adapter is just another `<name>.git`. Returns the count.
    """
    import subprocess
    import tempfile

    work = tempfile.mkdtemp(prefix=f"irdb-{name}-")
    count = populate(work)

    def git(*args):
        subprocess.run(["git", "-C", work, *args], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "codegen@local")
    git("config", "user.name", "ir-codegen")
    git("add", "-A")
    git("commit", "-q", "--allow-empty", "-m", f"generated {count} components")
    bare = os.path.join(cache, f"{name}.git")
    subprocess.run(["git", "clone", "-q", "--bare", work, bare], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return count


def _populate_flipper(work, repo, branch):
    """flipper adapter: clone Flipper-IRDB and mirror each `.ir` to a generated
    `.yaml` component, preserving the tree (TVs/Sony/Sony_Bravia.yaml)."""
    import re as _re
    import subprocess
    import tempfile

    src = tempfile.mkdtemp(prefix="irdb-src-")
    url = f"https://github.com/{repo}.git"

    def run(*args):
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if _re.fullmatch(r"[0-9a-f]{7,40}", branch or ""):
        run("git", "init", "-q", src)
        run("git", "-C", src, "fetch", "--depth", "1", url, branch)
        run("git", "-C", src, "checkout", "-q", "FETCH_HEAD")
    else:
        run("git", "clone", "-q", "--depth", "1", "--branch", branch, url, src)

    count = 0
    for root, _dirs, files in os.walk(src):
        if ".git" in root.split(os.sep):
            continue
        for filename in files:
            if not filename.endswith(".ir"):
                continue
            rel = os.path.relpath(os.path.join(root, filename), src)
            try:
                with open(os.path.join(root, filename), encoding="utf-8", errors="replace") as handle:
                    component = generate(parse_ir(handle.read()), branch, rel, None, "")
            except Exception:
                continue
            # ESPHome only accepts .yaml/.yml package files, so mirror the path
            # with a .yaml extension (TVs/Sony/Sony_Bravia.ir -> ....yaml).
            outpath = os.path.join(work, _mirror_out(rel))
            os.makedirs(os.path.dirname(outpath), exist_ok=True)
            with open(outpath, "w", encoding="utf-8") as handle:
                handle.write(component)
            count += 1
    return count


def _ha_ir_codesets():
    """Yield (relpath, [(name, Command), ...]) for every infrared-protocols code
    set — e.g. 'vizio/tv' -> [('POWER', NECCommand(...)), ...]. Each `codes`
    submodule exposes Enums with a `.to_command()`; we enumerate their members.

    The library's brand dirs (codes/vizio/…) have no __init__.py (namespace
    packages), which pkgutil.walk_packages won't descend into — so we walk the
    package directory on disk and import each module by name instead.
    """
    import enum
    import importlib

    import infrared_protocols.codes as codes_pkg
    from infrared_protocols.commands import Command

    base = codes_pkg.__name__
    for root in list(codes_pkg.__path__):
        for dirpath, _dirs, files in os.walk(root):
            for filename in sorted(files):
                if not filename.endswith(".py") or filename == "__init__.py":
                    continue
                relmod = os.path.relpath(os.path.join(dirpath, filename), root)[:-3]
                relmod = relmod.replace(os.sep, ".")
                modname = f"{base}.{relmod}"
                try:
                    mod = importlib.import_module(modname)
                except Exception:
                    continue
                named, seen = [], set()
                for attr in vars(mod).values():
                    if not (isinstance(attr, type) and issubclass(attr, enum.Enum)):
                        continue
                    if attr.__module__ != modname or not hasattr(attr, "to_command"):
                        continue
                    for member in attr:
                        if member.name in seen:
                            continue
                        try:
                            command = member.to_command()
                        except Exception:
                            continue
                        if not isinstance(command, Command):
                            continue
                        seen.add(member.name)
                        named.append((member.name, command))
                if named:
                    yield relmod.replace(".", "/"), named


def _populate_ha_ir(work):
    """ha-ir adapter: expose infrared-protocols' own curated code sets as
    components at `<brand>/<type>.yaml` (e.g. vizio/tv.yaml)."""
    count = 0
    for rel, named in _ha_ir_codesets():
        component = generate_from_commands(named, rel)
        outpath = os.path.join(work, rel + ".yaml")
        os.makedirs(os.path.dirname(outpath), exist_ok=True)
        with open(outpath, "w", encoding="utf-8") as handle:
            handle.write(component)
        count += 1
    return count


_REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def _repo_from_path(path):
    """'/Owner/Name.git/git-upload-pack' -> 'Owner/Name'; '/ha-ir.git/…' -> 'ha-ir'.

    Returns the repo segment up to (not including) the `.git` that ends a path
    segment, or None when the path has no repo. The flipper source repo is the
    URL path, so this is how a clone of `http://host/<owner>/<name>.git` names
    its source. The `(?:/|$)` anchor keeps names like `.github` from matching.
    """
    m = re.match(r"/?(.+?\.git)(?:/|$)", path)
    return m.group(1)[:-4] if m else None


def _valid_repo(repo):
    """A flipper source must be exactly owner/name (no traversal, one slash)."""
    return bool(_REPO_RE.fullmatch(repo)) and ".." not in repo


def _source_url(repo):
    name = repo[:-4] if repo.endswith(".git") else repo
    return f"https://github.com/{name}.git"


def _pkt_lines(body):
    """Yield each pkt-line payload from a git smart-protocol request body.

    pkt-line = 4 hex length bytes (covering themselves) + payload; lengths < 4
    are the flush/delim/response-end markers (0000/0001/0002).
    """
    i, n = 0, len(body)
    while i + 4 <= n:
        try:
            length = int(body[i : i + 4], 16)
        except ValueError:
            return
        if length < 4:
            i += 4
            continue
        yield body[i + 4 : i + length]
        i += length


def _v2_command(body):
    """The git protocol-v2 command (`ls-refs` / `fetch`) in a request, or None."""
    for line in _pkt_lines(body):
        if line.startswith(b"command="):
            return line[len(b"command=") :].strip().decode("utf-8", "replace")
    return None


def _wanted_refs(body):
    """Branch/tag names a protocol-v2 `ls-refs` request is resolving.

    To resolve `<ref>`, git sends several `ref-prefix` lines (refs/heads/<ref>,
    refs/tags/<ref>, <ref>, …). We return the candidate names (heads/tags tails
    first, then bare), so the on-demand builder knows which ref to materialize.
    """
    heads, bare = [], []
    for line in _pkt_lines(body):
        if not line.startswith(b"ref-prefix "):
            continue
        val = line[len(b"ref-prefix ") :].strip().decode("utf-8", "replace")
        if not val or val == "HEAD" or val == "refs/":
            continue
        if val.startswith("refs/heads/"):
            heads.append(val[len("refs/heads/") :])
        elif val.startswith("refs/tags/"):
            heads.append(val[len("refs/tags/") :])
        elif not val.startswith("refs/"):
            bare.append(val)
    out, seen = [], set()
    for name in heads + bare:
        if name and name != "HEAD" and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _ls_remote_sha(repo, ref):
    """Current sha of <ref> on the source repo, or None if unknown/unreachable."""
    import subprocess

    url = _source_url(repo)
    for spec in (f"refs/heads/{ref}", f"refs/tags/{ref}", ref):
        try:
            res = subprocess.run(
                ["git", "ls-remote", url, spec],
                capture_output=True, text=True, timeout=20,
            )
        except Exception:
            return None
        out = res.stdout.strip()
        if out:
            return out.split()[0]
    return None


def _ensure_repo_dir(cache, repo):
    """Make sure `<cache>/<repo>.git` exists as a bare repo so git-http-backend
    can answer a protocol-v2 capability advertisement before any ref is built."""
    import subprocess

    bare = os.path.join(cache, repo + ".git")
    if not os.path.isdir(bare):
        os.makedirs(os.path.dirname(bare), exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _ensure_flipper_branch(cache, repo, ref, built, locks, locks_guard):
    """On demand: build/refresh branch <ref> of <repo>'s transformed components in
    the per-repo bare repo `<cache>/<repo>.git`, rebuilding only when the source
    HEAD moved. The bare repo accumulates one branch per requested ref, so the
    fixed URL path serves any ref a device asks for. Serves the cached build if
    the source can't be reached.
    """
    import subprocess
    import tempfile

    bare = os.path.join(cache, repo + ".git")
    with locks_guard:
        lock = locks.setdefault(repo, threading.Lock())
    with lock:
        os.makedirs(os.path.dirname(bare), exist_ok=True)
        if not os.path.isdir(bare):
            subprocess.run(["git", "init", "-q", "--bare", bare], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sha = _ls_remote_sha(repo, ref)
        key = (repo, ref)
        has_branch = subprocess.run(
            ["git", "-C", bare, "rev-parse", "--verify", "-q", f"refs/heads/{ref}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0
        if has_branch and (sha is None or built.get(key) == sha):
            return  # cached and current (or source unreachable -> serve cache)

        print(f"building {repo}@{ref} on demand (a few minutes) …", flush=True)
        work = tempfile.mkdtemp(prefix="irdb-build-")
        try:
            count = _populate_flipper(work, repo, ref)
        except Exception as exc:
            print(f"build failed for {repo}@{ref}: {exc}", flush=True)
            return

        def git(*args):
            subprocess.run(["git", "-C", work, *args], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        git("init", "-q")
        git("config", "user.email", "codegen@local")
        git("config", "user.name", "ir-codegen")
        git("add", "-A")
        git("commit", "-q", "--allow-empty", "-m", f"{repo}@{ref}: {count} components")
        git("push", "-q", "--force", bare, f"HEAD:refs/heads/{ref}")
        # Point the served repo's HEAD at a built branch so a bare `git clone`
        # (no -b) checks out content instead of an unborn default.
        subprocess.run(["git", "-C", bare, "symbolic-ref", "HEAD", f"refs/heads/{ref}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        built[key] = sha
        print(f"served {repo}@{ref}: {count} components", flush=True)


def serve_http(port=9418, adapters=("flipper", "ha-ir")):
    """Smart-HTTP git service: source repo is the URL path, ref is the request.

    A device clones the Flipper source it wants and `files:` selects the remote:

        packages:
          x:
            url: http://<host>:<port>/<owner>/<name>.git   # any Flipper-IRDB repo/fork
            ref: <branch|tag>                              # built on demand
            files: [TVs/Sony/Sony_Bravia.yaml]

    The matching `<owner>/<name>` @ `ref` is cloned and transformed on the first
    request and cached, then rebuilt whenever the source branch HEAD moves. The
    reserved `ha-ir.git` path is prebuilt from the installed infrared-protocols
    library (it has no source repo). `adapters` selects which sources are served
    (`flipper` enables on-demand `<owner>/<name>.git`; `ha-ir` prebuilds the
    reserved repo).
    """
    import http.server
    import subprocess
    import tempfile
    from urllib.parse import urlsplit

    cache = tempfile.mkdtemp(prefix="irdb-http-")
    serve_flipper = "flipper" in adapters
    reserved = set()
    if "ha-ir" in adapters:
        print("building reserved ha-ir.git from the infrared-protocols code sets …", flush=True)
        _make_bare_repo(cache, "ha-ir", _populate_ha_ir)
        reserved.add("ha-ir")
    if not serve_flipper and not reserved:
        raise SystemExit(f"no known adapters in {adapters!r} (expected: flipper, ha-ir)")

    built = {}                       # (repo, ref) -> source sha last built
    locks, locks_guard = {}, threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self._serve()

        def do_POST(self):
            self._serve()

        def _serve(self):
            split = urlsplit(self.path)
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""

            repo = _repo_from_path(split.path)
            if repo and repo not in reserved:
                # Dynamic flipper source: build the requested ref on demand. The
                # ref only appears in a protocol-v2 `ls-refs` body; the following
                # `fetch` reuses the branch we just built (so we skip it there).
                if not serve_flipper or not _valid_repo(repo):
                    self.send_error(404, "unknown repo")
                    return
                if split.path.endswith("/git-upload-pack") and _v2_command(body) == "ls-refs":
                    for ref in (_wanted_refs(body) or [_default_branch(repo)]):
                        _ensure_flipper_branch(cache, repo, ref, built, locks, locks_guard)
                else:
                    _ensure_repo_dir(cache, repo)   # v2 caps advertisement needs the dir

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
            # `body` was already read once above (for ref parsing); reusing it
            # avoids a second drained read that would block. git-http-backend
            # reads the request from stdin until EOF, so CONTENT_LENGTH is moot.
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

    sources = []
    if serve_flipper:
        sources.append("<owner>/<name>.git (on demand)")
    sources.extend(f"{name}.git (reserved)" for name in sorted(reserved))
    print(f"git-http: http://0.0.0.0:{port}/  serving {', '.join(sources)}", flush=True)
    http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--serve", action="store_true", help="run a git:// service ESPHome can pull from")
    parser.add_argument("--from-options", dest="from_options", help="read --serve options from a JSON file (Home Assistant add-on)")
    parser.add_argument("--port", type=int, default=9418, help="listen port for --serve")
    parser.add_argument("--repo", default=FLIPPER_REPO, help="flipper adapter source repo or fork (path-less --serve)")
    parser.add_argument("--adapters", default="flipper,ha-ir", help="comma-separated adapters to serve (flipper, ha-ir)")
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
        # repo + ref are per-device (URL path + `ref:`), never add-on options.
        # `adapters` selects which sources are served (default: both).
        adapters = opts.get("adapters") or ["flipper", "ha-ir"]
        if isinstance(adapters, str):
            adapters = [a.strip() for a in adapters.split(",") if a.strip()]
        serve_http(port=int(opts.get("port", 9418)), adapters=tuple(adapters))
        return 0

    if args.serve:
        if args.path:
            # Single-component git:// service (CLI / one-off).
            out = args.out or _mirror_out(args.path)
            serve(port=args.port, ref=args.ref or "main", path=args.path, out=out, tx_id=args.tx_id, prefix=args.prefix)
        else:
            # Path-less smart-HTTP service (the add-on): source repo is the URL
            # path, ref is the device's `ref:` — both per-device, built on demand.
            adapters = tuple(a.strip() for a in args.adapters.split(",") if a.strip())
            serve_http(port=args.port, adapters=adapters)
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
