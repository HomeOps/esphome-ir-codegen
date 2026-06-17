# IR code sets → ESPHome codegen (Home Assistant add-on)

Turn open IR code databases into ready-to-use ESPHome `remote_transmitter`
components. The add-on serves codes as a git repo your ESPHome YAML clones like
any other remote package — no IR codes in your config, just a path to a remote.
Two sources ship today: any
[Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) repo or fork, built on
demand from the `url:` path at your `ref:` (`…/<owner>/<name>.git`), and Home
Assistant's curated
[infrared-protocols](https://github.com/home-assistant-libs/infrared-protocols)
code sets (reserved `…/ha-ir.git`). See [Adapters](#adapters).

> **Status:** working transformer + Dockerized **smart-HTTP git service** +
> Home Assistant add-on, serving the `flipper` + `ha-ir` adapters. An end-to-end
> CI test stands up the container and has **ESPHome clone a component from each
> adapter** to build real firmware (see [CI](#ci-the-end-to-end-test)). The
> flipper Sony Bravia path is also verified on real hardware against a live TV;
> ha-ir is compile-verified only. Next: more protocols — see [Roadmap](#roadmap).

## Showcase: a ~$20 universal remote

Press the button on a **$20
[M5 Atom Lite](https://shop.m5stack.com/products/atom-lite-esp32-development-kit)**
and your TV toggles. The IR codes are never hand-typed — they're pulled, at build
time, straight from the open
[Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) by the codegen service.

This is the exact device that CI compiles on every PR
([`firmware-test/device.yaml`](firmware-test/device.yaml)):

```yaml
esp32:
  board: m5stack-atom              # M5 Atom Lite

remote_transmitter:
  id: ir_tx
  pin: GPIO12                      # the Atom's built-in IR LED

packages:                          # <- codes pulled LIVE from the codegen service
  sony_bravia:
    url: http://<addon-host>:9418/Lucaslhm/Flipper-IRDB.git  # source repo IS the path
    ref: main                                                # any branch/tag, built on demand
    files: [TVs/Sony/Sony_Bravia.yaml]     # the Flipper path selects the remote

binary_sensor:
  - platform: gpio
    pin: { number: GPIO39, inverted: true, mode: { input: true } }
    on_press:
      - button.press: tv_sony_power  # Sony "Power" toggle, pulled from the DB
```

The point: **there are no IR codes in your config** — just a reference to a device
in a community database. The `url:` path is the Flipper-IRDB repo (or fork) and
`ref:` the branch/tag; the add-on builds that repo@ref into a `.yaml`-per-`.ir`
mirror on demand and caches it. The `files:` path *is* the selector:
`TVs/Sony/Sony_Bravia.yaml` is the generated form of `TVs/Sony/Sony_Bravia.ir`.
Swap it for any of the thousands of remotes in Flipper-IRDB and reflash — that
one line is the only place a specific remote is named, and the clone is shared
across every device that points at it. (For curated codes, point `url:` at the
reserved `…/ha-ir.git` instead — see [Adapters](#adapters).)

### Why this matters

Logitech Harmony is discontinued; SofaBaton and similar universal remotes are
closed, cloud-tied, and cost real money. The goal here is a **fully open, local,
DIY Harmony-style universal remote** on commodity ESP hardware — codes sourced
from an open database, no vendor lock-in, for roughly the price of a sandwich. If
it lands, it's an order-of-magnitude cheaper, fully hackable alternative.

## Credits / prior art

This project stands on work that already proved the `.ir` → ESPHome mapping is
practical:

- **[balloob/flipper-ir-esphome](https://github.com/balloob/flipper-ir-esphome)**
  by **Paulus Schoutsen** (founder of Home Assistant) — a web converter that
  turns a Flipper `.ir` file into ESPHome YAML. This is the direct inspiration;
  the transformer here is the same idea wrapped as an on-demand, ref-pinned
  service. **Thank you, balloob.**
- **[home-assistant-libs/infrared-protocols](https://github.com/home-assistant-libs/infrared-protocols)**
  — Home Assistant's IR protocol encoder/decoder library. **This project depends
  on it**: every parsed protocol (NEC, Sony, Samsung32, RC5, Sharp…) is encoded
  by this library, not by code of our own. It's the same encoder stack HA's
  native infrared platform uses, so the codes we emit are protocol-correct by
  construction.
- **[READYWARE Signal Editor](https://readyware.net/signal-editor.html)** — a
  browser-based multi-format IR/RF converter (Flipper ↔ ESPHome/Pronto/LIRC…).
- **[Lucaslhm/Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB)** — the
  community IR code database this consumes.
- **[probonopd/irdb](https://github.com/probonopd/irdb)** — the classic
  protocol/hex IR database.

## Why this exists

Capturing or looking up IR codes and hand-pasting them into ESPHome is tedious,
and the existing converters are manual (paste in, copy out). The goal: reference
a code set **declaratively** from your device YAML and have it generated for you.

The key constraint that shapes everything: **ESPHome is static.** Entities are
fixed at *compile time* and baked into firmware — the device can't fetch a URL at
runtime and spawn commands. So this runs as **build-time codegen**, not an
on-device feature. Changing codes still means recompile + reflash; the add-on
just removes the copy-paste.

## How it works (for humans)

In one sentence: **you point it at a remote's code file in the Flipper database,
and it hands ESPHome the buttons that press those codes.**

Step by step:

1. **Pick a remote.** Browse [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB)
   and find your device's `.ir` file — e.g. `TVs/Sony/Sony_Bravia.ir`. Name it in
   your device's `files:` (as `…Sony_Bravia.yaml`); pin `ref:` so the result can
   never change under you.
2. **The add-on translates that repo@ref on demand** into a `.yaml`-per-`.ir`
   mirror (cached, rebuilt when the branch moves); ESPHome clones it and `files:`
   selects your remote's component.
3. **Each remote button becomes** a `remote_transmitter.transmit_raw` action.
   Parsed protocols (Sony, NEC, Samsung32, RC5, Sharp…) are encoded by the
   [infrared-protocols](https://github.com/home-assistant-libs/infrared-protocols)
   library into raw timings; a Flipper `raw` capture passes through directly.
4. **Out comes a block of ESPHome YAML** — one `button` per remote key, each
   wired to your IR transmitter.
5. **Include that YAML in your device config and flash.** Home Assistant now has
   a button for every key on the original remote.

Think of it as a **translator**: Flipper speaks "remote button," ESPHome speaks
"transmit action," and this sits in the middle. It runs while you *build* the
firmware (not on the device), so switching remotes means regenerate + reflash.

### Try it (Docker)

Quick peek — CLI prints the YAML:

```bash
docker build -t esphome-ir-codegen .
docker run --rm esphome-ir-codegen \
  --ref d126fb1b6f1e114c52b4a8c19839ea65e3a9c24d \
  --path TVs/Sony/Sony_Bravia.ir --tx ir_tx --prefix "Bravia"
```

Real usage — run it as a **service** and let ESPHome clone from it:

```bash
docker run -d -p 9418:9418 esphome-ir-codegen --serve   # prebuilds reserved ha-ir.git
#   --adapters flipper     serve only flipper (skip the ha-ir prebuild)
# The Flipper source repo + ref are per-device (URL path + ref:), not flags.
```

```yaml
# in your ESPHome device config — the url path is the source repo, ref: the branch:
packages:
  tv:
    url: http://localhost:9418/Lucaslhm/Flipper-IRDB.git   # or …/ha-ir.git (reserved)
    ref: main
    files: [TVs/Sony/Sony_Bravia.yaml]
```

**How the remote is resolved:** the `url:` path names the Flipper-IRDB repo (or
fork) and `ref:` the branch/tag; the add-on clones that repo@ref and mirrors each
`TVs/Sony/Sony_Bravia.ir` to a generated `TVs/Sony/Sony_Bravia.yaml`, on the first
request and cached after. ESPHome clones that repo (smart HTTP, shallow) and
`files:` selects the component. The *device* decides everything — source repo,
ref, and remote — so one running add-on serves every device.

## Adapters

There are two kinds of source, both served over the same smart-HTTP service; the
shared [infrared-protocols](https://github.com/home-assistant-libs/infrared-protocols)
encoder turns every command into `transmit_raw`, so they differ only in where the
codes come from and the path layout:

| Source | `url:` | From | `files:` path |
|--------|--------|------|---------------|
| **flipper** | `…/<owner>/<name>.git` (on demand) | any Flipper-IRDB repo/fork at `ref:` | mirrors the tree — `TVs/Sony/Sony_Bravia.yaml` |
| **ha-ir** | `…/ha-ir.git` (reserved, prebuilt) | infrared-protocols' own curated code sets | `<brand>/<type>.yaml` — `vizio/tv.yaml` |

Point a device at whichever source has your remote:

```yaml
packages:
  tv:
    url: http://<addon-host>:9418/ha-ir.git   # reserved; or …/<owner>/<name>.git
    ref: main
    files: [vizio/tv.yaml]
```

`git http-backend` serves any repo under its root, so the reserved `ha-ir.git`
and the on-demand `<owner>/<name>.git` repos all share one encoder.

## Design (locked decisions)

1. **No source config — repo + ref are per-device.** The `url:` path is the
   Flipper source repo (any fork) and `ref:` is the branch/tag; the add-on has no
   `repo`/`ref` option, only `adapters` (which sources to serve). The *device*
   selects the remote via `files:`, so one running add-on serves every device.
2. **Build on demand, keyed by `(repo, ref)`.** Each `(repo, ref)` is cloned and
   transformed on its first request, cached as a branch in a per-repo bare repo,
   and rebuilt automatically when the source branch HEAD moves (no add-on
   restart). ESPHome reuses its own clone cache too (default `refresh` `1d` —
   just don't set `0s`, which re-clones on every build).
3. **Live-service dependency is acceptable.** ESPHome clones from the add-on at
   compile time; if it's down, the build fails. The device's `ref:` selects the
   codes, so a green build is reproducible.
4. **Button ids are namespaced by path.** `<category>_<brand>_<key>` (e.g.
   `tv_sony_power`), so buttons from different remotes never collide; dedup /
   button-explosion curation is still deferred.

## Architecture

```
                                ┌─ <owner>/<name>.git ◀─ Flipper-IRDB repo@ref (.ir, on demand)
ESPHome build ─url(=repo)/ref/files─▶ HA add-on ┤        (smart-HTTP git service)
   (compile)     clone + select                 └─ ha-ir.git ◀─ infrared-protocols code sets (reserved)
        ◀──────── generated ESPHome YAML component (buttons) ─────────
```

**Transformer core** (done): turn each IR signal into an ESPHome `button` entity
calling `remote_transmitter.transmit_raw`. The flipper source parses `.ir` files;
the ha-ir source reads infrared-protocols `Command`s. Both encode through the
same library, so all output is `transmit_raw`.

**Serving layer** (done): ESPHome remote `packages:` are git-based, so the add-on
serves smart HTTP (`git http-backend`, required because ESPHome does shallow
clones, which dumb HTTP can't serve). The Flipper source repo is the URL path and
the ref is the request, so each `(repo, ref)` is built on demand:

| Stage | Mechanism | Status |
|-------|-----------|--------|
| **Now** | `--serve` builds the requested `<owner>/<name>.git@<ref>` on demand (cached, HEAD-refreshed) and prebuilds the reserved `ha-ir.git`; ESPHome clones one repo, selecting `files: [<path>.yaml]`. Both exercised end-to-end in CI; flipper verified on real hardware. | ✅ |
| Next | More protocols (RC6/Kaseikyo/Panasonic) + a receiver-based correctness check. | ⏳ |
| Later | A runtime adapter that pushes codes to HA's `ir_rf_proxy` (no recompile to switch remotes). | ⏳ |

ESPHome usage today:

```yaml
packages:
  tv_codes:
    url: http://<addon-host>:9418/Lucaslhm/Flipper-IRDB.git   # url path = source repo
    ref: main                                                 # branch/tag, built on demand
    files: [TVs/Sony/Sony_Bravia.yaml]             # the Flipper path = the remote
```

## Transformer — current coverage

Every parsed signal is encoded by the
[infrared-protocols](https://github.com/home-assistant-libs/infrared-protocols)
library and emitted as `transmit_raw` (the library returns raw timings). We keep
no protocol math of our own.

| Flipper signal | ESPHome output | Status |
|----------------|----------------|--------|
| `type: raw` | `transmit_raw` (sign-alternated, carrier from `frequency`) | ✅ direct passthrough |
| `type: parsed` NEC / NECext | `transmit_raw` via `NECCommand` | ✅ |
| `type: parsed` SIRC / SIRC15 / SIRC20 (Sony) | `transmit_raw` via `SonyCommand` | ✅ |
| `type: parsed` Samsung32 / RC5 / RC5X / Sharp | `transmit_raw` via the matching `*Command` | ✅ |
| other parsed (NEC42, RC6, Kaseikyo, …) | `# TODO unsupported` comment | ⏳ next |

**Single frame + transmit-layer repeat.** The library returns *one* frame per
command — by design, repetition is the transmit layer's job (the same split HA's
IR proxy uses). So parsed signals are emitted with a `repeat:` (Sony SIRC and
others need ~3 frames before a device acts); a `raw` capture is authoritative and
sent as-is. **Validity ≠ correctness:** a green compile proves the YAML is valid,
not that the code is right for your device — verify against a live
`remote_receiver` capture, or on the real hardware.

> **Requires Python ≥ 3.14** (the `infrared-protocols` dependency). The Docker
> image and CI use it; the esphome compile step is unaffected.

### CLI usage

```bash
# From a pinned Flipper-IRDB ref + path
python flipper_ir_to_esphome.py \
  --ref main --path TVs/Samsung/Samsung_TV.ir \
  --tx ir_tx --prefix TV

# From a local file
python flipper_ir_to_esphome.py --file Samsung_TV.ir --prefix TV
```

## Install as a Home Assistant add-on

The codegen ships as a Home Assistant add-on (this repo is also an add-on
repository — see [`addon/`](addon/) and [`repository.yaml`](repository.yaml)):

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add
   `https://github.com/HomeOps/esphome-ir-codegen`.
2. Install **ESPHome IR Codegen** and **Start** it. Nothing to configure — the
   source repo and ref are per-device; the only option is `adapters` (default
   `flipper,ha-ir`). The reserved ha-ir.git is prebuilt at startup; flipper repos
   build on first request (a few minutes), then cached.
3. Point ESPHome at your Flipper repo (or the reserved `ha-ir.git`) and pick a
   remote by path:

   ```yaml
   packages:
     tv:
       url: http://<addon-host>:9418/Lucaslhm/Flipper-IRDB.git
       ref: main
       files: [TVs/Sony/Sony_Bravia.yaml]
      ```

The add-on image is built FROM the published GHCR image and just adds an
options-reading entrypoint (no script duplication). Full usage: [`addon/DOCS.md`](addon/DOCS.md).

## CI: the end-to-end test

Every push and PR runs the real thing (`.github/workflows/ci.yaml`), exercising
the add-on **as a live service** — not a pre-generated file:

1. **Build** the codegen Docker image.
2. **Start** it as a running container, then warm `Lucaslhm/Flipper-IRDB.git @
   main` (on-demand build) and confirm the reserved `ha-ir.git`.
3. **Compile** real ESP32 firmware, one device per source, each **cloning its
   component from that running container**:
   - `firmware-test/device.yaml` → `Lucaslhm/Flipper-IRDB.git@main`, `files: [TVs/Sony/Sony_Bravia.yaml]`
   - `firmware-test/device-ha-ir.yaml` → `ha-ir.git`, `files: [vizio/tv.yaml]`
4. **Capture** both generated components and upload them as the build artifact
   (the `.bin` is intentionally *not* kept — the useful output is the YAML).

If a served component were malformed, step 3 fails — so a green build means each
adapter produces **valid firmware**. (Validity ≠ correctness: that the codes are
the *right* ones for your device is verified separately against a live
`remote_receiver` capture, and on real hardware.) These compiles are the
regression test guarding every future PR.

Releases use [release-please](https://github.com/googleapis/release-please)
(changelog in [`addon/CHANGELOG.md`](addon/CHANGELOG.md), where Home Assistant's
add-on update dialog reads it); a tagged release publishes the image to GHCR from
the release-please run itself (`.github/workflows/release-please.yaml`).

## Roadmap

- [x] Parsed-protocol coverage: NEC/NECext, Sony (SIRC/SIRC15/SIRC20),
      Samsung32, RC5/RC5X, Sharp — all via infrared-protocols. Plus raw.
- [x] `Dockerfile` + end-to-end CI (Sony Bravia + Vizio TV → firmware).
- [x] Smart-HTTP git backend: on-demand `<owner>/<name>.git@<ref>` + reserved `ha-ir.git`.
- [x] HA add-on packaging (`addon/config.yaml`, `adapters` option; repo+ref per-device).
- [ ] More parsed protocols: RC6, Panasonic/Kaseikyo, Pioneer, NEC42 — each
      verified against a receiver capture.
- [ ] A runtime adapter that pushes codes to HA's `ir_rf_proxy` (no recompile
      to switch remotes).
- [ ] On-demand generation (vs. whole DB at container start) to cut first-boot.
- [ ] Button-set selection / naming / dedup.
