# Flipper-IRDB → ESPHome codegen (Home Assistant add-on)

Turn the whole [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) into
ready-to-use ESPHome `remote_transmitter` components, served as one git repo your
ESPHome YAML clones like any other remote package source — no IR codes in your
config, just a path to a remote in the database.

> **Status:** working transformer + Dockerized **smart-HTTP git service** +
> Home Assistant add-on. An end-to-end CI test stands up the container and has
> **ESPHome clone the component from it** to build real firmware (see
> [CI](#ci-the-sony-bravia-end-to-end-test)), and it's been verified on real
> hardware against a live TV. Next: more protocols — see [Roadmap](#roadmap).

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
    url: http://<addon-host>:9418/flipper.git
    ref: main
    files: [TVs/Sony/Sony_Bravia.yaml]     # the Flipper path selects the remote
    refresh: 1d                            # clone once, then reuse (never 0s)

binary_sensor:
  - platform: gpio
    pin: { number: GPIO39, inverted: true, mode: { input: true } }
    on_press:
      - button.press: ir_power       # Sony "Power" toggle, pulled from the DB
```

The point: **there are no IR codes in your config** — just a reference to a device
in a community database. The add-on builds the whole DB into one `flipper.git`
repo (each `.ir` mirrored to a `.yaml` component); the `files:` path *is* the
selector: `TVs/Sony/Sony_Bravia.yaml` is the generated form of
`TVs/Sony/Sony_Bravia.ir`. Swap it for any of the thousands of remotes in
Flipper-IRDB and reflash — that one line is the only place a specific remote is
named, and the clone is shared across every device that points at it.

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
2. **The add-on has already translated the whole database** into one `flipper.git`
   repo; ESPHome clones it and `files:` selects your remote's component.
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
docker run -d -p 9418:9418 esphome-ir-codegen --serve   # whole DB; add --repo for a fork
```

```yaml
# in your ESPHome device config — clones the shared DB once, picks a remote by path:
packages:
  tv:
    url: http://localhost:9418/flipper.git
    ref: main
    files: [TVs/Sony/Sony_Bravia.yaml]
    refresh: 1d
```

**How the remote is resolved:** the service builds the entire Flipper-IRDB into
one `flipper.git` repo, mirroring each `TVs/Sony/Sony_Bravia.ir` to a generated
`TVs/Sony/Sony_Bravia.yaml`. ESPHome clones that single repo (smart HTTP, shallow)
and `files:` selects the component. The add-on is generic (its only knob is the
source `repo`); the device's `files:` path decides the *remote*.

## Adapters

An **adapter** is a *source* of device code sets. The add-on serves **one bare
git repo per adapter**, all from the same smart-HTTP service; the shared
[infrared-protocols](https://github.com/home-assistant-libs/infrared-protocols)
encoder turns every command into `transmit_raw`, so adapters differ only in
source and path layout:

| Adapter | Repo | Source | `files:` path |
|---------|------|--------|---------------|
| **flipper** | `flipper.git` | Flipper-IRDB (`repo`, or a fork) | mirrors the tree — `TVs/Sony/Sony_Bravia.yaml` |
| **ha-ir** | `ha-ir.git` | infrared-protocols' own curated code sets | `<brand>/<type>.yaml` — `vizio/tv.yaml` |

Point a device at whichever adapter has your remote:

```yaml
packages:
  tv:
    url: http://<addon-host>:9418/ha-ir.git   # or flipper.git
    ref: main
    files: [vizio/tv.yaml]
    refresh: 1d
```

`git http-backend` serves any repo under its root, so adding an adapter is just
another `<name>.git` — the encoder never changes.

## Design (locked decisions)

1. **The flipper adapter's only knob is the source `repo`.** Default
   `Lucaslhm/Flipper-IRDB`; point it at a fork if you maintain one. The *device*
   YAML pins `ref:` and selects the remote via `files:`, so one running add-on
   serves every device. (The ha-ir adapter needs no repo — its source is the
   installed infrared-protocols version.)
2. **One shared repo per adapter.** Each adapter builds its components into a
   single bare repo; ESPHome clones it once and reuses the cache across every
   device that points at it (with `refresh: 1d`, not `0s`).
3. **Live-service dependency is acceptable.** ESPHome clones from the add-on at
   compile time; if it's down, the build fails. Codes are pinned by the device's
   `ref:`, so a green build is reproducible.
4. **Naming / dedup / button-explosion handling is deferred.** Minimal naming for
   now (stable `ir_<key>` ids); curation comes later.

## Architecture

```
ESPHome build  ──packages: url/files──▶  HA add-on (flipper.git)  ──build once──▶  Flipper-IRDB
   (compile)         clone + select        smart-HTTP git service      from repo      (source repo)
        ◀──────── generated ESPHome YAML component (buttons) ─────────
```

**Transformer core** (done): parse `.ir` → emit ESPHome `button` entities, one
per signal, each calling `remote_transmitter.transmit_*`.

**Serving layer** (done): ESPHome remote `packages:` are git-based, so the add-on
builds **one bare repo per adapter** (`flipper.git`, `ha-ir.git`) and serves them
over smart HTTP (`git http-backend`, required because ESPHome does shallow clones,
which dumb HTTP can't serve):

| Stage | Mechanism | Status |
|-------|-----------|--------|
| **Now** | `--serve` builds each adapter into `<name>.git` and serves it over smart HTTP; ESPHome clones one repo, selecting `files: [<path>.yaml]`. Both `flipper` + `ha-ir` exercised end-to-end in CI; flipper verified on real hardware. | ✅ |
| Next | More protocols (RC6/Kaseikyo/Panasonic) + a receiver-based correctness check. | ⏳ |
| Later | A runtime adapter that pushes codes to HA's `ir_rf_proxy` (no recompile to switch remotes). | ⏳ |

ESPHome usage today:

```yaml
packages:
  tv_codes:
    url: http://<addon-host>:9418/flipper.git    # one repo, cloned once
    ref: main
    files: [TVs/Sony/Sony_Bravia.yaml]             # the Flipper path = the remote
    refresh: 1d
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
2. Install **ESPHome IR Codegen** and **Start** it. The only option is `repo`
   (default `Lucaslhm/Flipper-IRDB`; point it at a fork if you like). First start
   builds the whole DB (a few minutes), then it's cached.
3. Point ESPHome at the shared `flipper.git` and pick a remote by path:

   ```yaml
   packages:
     tv:
       url: http://<addon-host>:9418/flipper.git
       ref: main
       files: [TVs/Sony/Sony_Bravia.yaml]
       refresh: 1d
   ```

The add-on image is built FROM the published GHCR image and just adds an
options-reading entrypoint (no script duplication). Full usage: [`addon/DOCS.md`](addon/DOCS.md).

## CI: the Sony Bravia end-to-end test

Every push and PR runs the real thing (`.github/workflows/ci.yaml`), exercising
the add-on **as a live service** — not a pre-generated file:

1. **Build** the codegen Docker image.
2. **Start** it as a running container serving `http://localhost:9418/flipper.git`
   (the whole DB, generated from a pinned Flipper-IRDB ref via `--ref` so the
   build is deterministic).
3. **Compile** real ESP32 firmware (`firmware-test/device.yaml`) whose
   `packages:` block **clones the component from that running container** and
   selects `files: [TVs/Sony/Sony_Bravia.yaml]`. ESPHome pulls from the live
   service — nothing is pre-generated into the repo.
4. **Capture** the generated `Sony_Bravia.yaml` component and upload it as the
   build artifact (the `.bin` is intentionally *not* kept — the useful output is
   the generated YAML).

If the served YAML were malformed, step 3 fails — so a green build means the live
service produces **valid firmware**. (Validity ≠ correctness: that the codes are
the *right* ones for your TV is verified separately against a live
`remote_receiver` capture, and on real hardware.) This Sony Bravia run is the
regression test guarding every future PR.

Releases use [release-please](https://github.com/googleapis/release-please)
(changelog in [`CHANGES.md`](CHANGES.md)); a tagged release publishes the image
to GHCR from the release-please run itself
(`.github/workflows/release-please.yaml`).

## Roadmap

- [x] Parsed-protocol coverage: Sony (SIRC/SIRC15/SIRC20). NEC/NECext + raw.
- [x] `Dockerfile` + end-to-end CI (Sony Bravia → firmware).
- [x] Smart-HTTP git backend serving the whole DB as one `flipper.git`.
- [x] HA add-on packaging (`addon/config.yaml`, single `repo` option).
- [ ] More parsed protocols: Samsung32, RC5/RC6, Panasonic, Pioneer — each
      verified against a receiver capture.
- [ ] On-demand generation (vs. whole DB at container start) to cut first-boot.
- [ ] Button-set selection / naming / dedup.
