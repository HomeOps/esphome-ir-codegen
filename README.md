# Flipper-IRDB → ESPHome codegen (Home Assistant add-on)

Turn a [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) `.ir` file into a
ready-to-use ESPHome `remote_transmitter` component **on demand**, by referencing
it from your ESPHome YAML as if it were a remote package source.

> **Status:** working transformer + Dockerized **git service**. An end-to-end CI
> test stands up the container and has **ESPHome clone the component from it** to
> build real firmware (see [CI](#ci-the-sony-bravia-end-to-end-test)). Next:
> HTTP/ingress serving + HA add-on packaging — see [Roadmap](#roadmap).

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
    url: git://localhost:9418/irdb.git
    ref: main
    files: [TVs/Sony/Sony_Bravia.yaml]   # mirrors TVs/Sony/Sony_Bravia.ir

binary_sensor:
  - platform: gpio
    pin: { number: GPIO39, inverted: true, mode: { input: true } }
    on_press:
      - button.press: ir_power       # Sony "Power" toggle, pulled from the DB
```

The point: **there are no IR codes in your config** — just a reference to a device
in a community database. The `files:` path *is* the selector:
`TVs/Sony/Sony_Bravia.yaml` is generated on the fly from `TVs/Sony/Sony_Bravia.ir`.
Swap it for any of the thousands of remotes in Flipper-IRDB and reflash — that one
line is the only place a specific remote is named.

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
   and find your device's `.ir` file — e.g. `TVs/Sony/Sony_Bravia.ir`. Note a
   commit (the *ref*) so the result can never change under you.
2. **The codegen fetches that file** from GitHub at the pinned ref.
3. **It translates each remote button** into the matching ESPHome transmit action:
   - a Sony `Power` (SIRC) key → `remote_transmitter.transmit_sony: {data, nbits}`
   - an NEC key → `transmit_nec: {address, command}`
   - a `raw` capture → `transmit_raw: {carrier_frequency, code}`
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

Real usage — run it as a **service** and let ESPHome pull from it (no files on
disk):

```bash
docker run -d -p 9418:9418 esphome-ir-codegen \
  --serve --ref d126fb1b6f1e114c52b4a8c19839ea65e3a9c24d \
  --path TVs/Sony/Sony_Bravia.ir --out TVs/Sony/Sony_Bravia.yaml
```

```yaml
# in your ESPHome device config — clones from the running container:
packages:
  sony_bravia:
    url: git://localhost:9418/irdb.git
    ref: main
    files: [TVs/Sony/Sony_Bravia.yaml]   # mirrors …/Sony_Bravia.ir
    refresh: 0s
```

**How the `.ir` is resolved:** the served `.yaml` path *mirrors* the Flipper-IRDB
path — `TVs/Sony/Sony_Bravia.yaml` ⇄ `TVs/Sony/Sony_Bravia.ir`. So the `files:`
entry both names the output and selects the source. The service is generic (it's
told only the pinned Flipper *ref*); the device config decides the *remote*.

## Design (locked decisions)

1. **Reproducibility = a valid Flipper ref.** The "source" is a pinned
   Flipper-IRDB git ref + path; the add-on fetches
   `raw.githubusercontent.com/Lucaslhm/Flipper-IRDB/<ref>/<path>`. Pinning is
   inherent and points at the upstream DB, not a fork/copy.
2. **Live-service dependency is acceptable.** The add-on may hit the network at
   compile time; if it's down, the build fails. No offline mirror in v1.
3. **Naming / dedup / button-explosion handling is deferred.** Minimal naming for
   now (optional `prefix`); curation comes later.

## Architecture

```
ESPHome build  ──packages: url──▶  HA add-on  ──fetch @ref──▶  Flipper-IRDB (GitHub)
   (compile)                       (transform)                  (pinned source)
        ◀───────── generated ESPHome YAML (buttons) ──────────
```

**Transformer core** (done): parse `.ir` → emit ESPHome `button` entities, one
per signal, each calling `remote_transmitter.transmit_*`.

**Serving layer** (planned), how ESPHome pulls it — ESPHome remote
`packages:` / `external_components:` are git-based, so the add-on presents itself
as a repo:

| Stage | Mechanism | Status |
|-------|-----------|--------|
| **Now** | `--serve` runs `git daemon`; ESPHome pulls via `packages: url: git://host:9418/irdb.git`. Exercised end-to-end in CI. | ✅ |
| Next | HTTP(S) / smart-HTTP serving so it works through reverse proxies and HA ingress. | ⏳ |
| Later | On-demand generation per clone (vs. baked once at container start). | ⏳ |

ESPHome usage today:

```yaml
packages:
  tv_codes:
    url: git://<addon-host>:9418/irdb.git       # the add-on, posing as a repo
    ref: main
    files: [TVs/Sony/Sony_Bravia.yaml]          # <- mirrors TVs/Sony/Sony_Bravia.ir
    refresh: 0s
```

## Transformer — current coverage (baby step)

| Flipper signal | ESPHome output | Status |
|----------------|----------------|--------|
| `type: raw` | `transmit_raw` (sign-alternated, carrier from `frequency`) | ✅ always correct |
| `type: parsed` NEC / NECext / NEC42(ext) | `transmit_nec` (16-bit words; NEC uses `addr \| (~addr<<8)`) | ✅ |
| `type: parsed` SIRC / SIRC15 / SIRC20 (Sony) | `transmit_sony` (`command \| address<<7`, nbits 12/15/20) | ✅ |
| other parsed (Samsung32, RC5/6, Panasonic, …) | `# TODO unsupported` comment | ⏳ next |

**Verify parsed codes** against a live `remote_receiver` capture — the receiver
dump prints the same 16-bit NEC words this emits, so they should match.

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
2. Install **ESPHome IR Codegen**, then in **Configuration** set `ref` (a pinned
   Flipper-IRDB commit) and `path` (e.g. `TVs/Sony/Sony_Bravia.ir`). Start it.
3. Point ESPHome at it — codes are pulled at compile time, nothing stored:

   ```yaml
   packages:
     tv:
       url: git://<your-ha-host>:9418/irdb.git
       ref: main
       files: [TVs/Sony/Sony_Bravia.yaml]
       refresh: 0s
   ```

The add-on image is built FROM the published GHCR image and just adds an
options-reading entrypoint (no script duplication). Full usage: [`addon/DOCS.md`](addon/DOCS.md).

## CI: the Sony Bravia end-to-end test

Every push and PR runs the real thing (`.github/workflows/ci.yaml`), exercising
the add-on **as a live service** — not a pre-generated file:

1. **Build** the codegen Docker image.
2. **Start** it as a running container serving `git://localhost:9418/irdb.git`
   (the Sony Bravia component, from a pinned Flipper-IRDB ref).
3. **Compile** real ESP32 firmware (`firmware-test/device.yaml`) whose
   `packages:` block **clones the component from that running container**. There
   are no generated files on disk — ESPHome pulls from the service.
4. **Upload** the resulting `firmware.bin` as a build artifact.

If the served YAML were malformed, step 3 fails — so a green build means the live
service produces **valid firmware**. (Validity ≠ correctness: that the codes are
the *right* ones for your TV is verified separately against a live
`remote_receiver` capture.) This Sony Bravia run is the regression test guarding
every future PR.

Releases use [release-please](https://github.com/googleapis/release-please)
(changelog in [`CHANGES.md`](CHANGES.md)); a tagged release publishes the image
to GHCR (`.github/workflows/publish.yaml`).

## Roadmap

- [x] Parsed-protocol coverage: Sony (SIRC/SIRC15/SIRC20). NEC/NECext + raw.
- [x] `Dockerfile` + end-to-end CI (Sony Bravia → firmware).
- [ ] More parsed protocols: Samsung32, RC5/RC6, Panasonic, Pioneer — each
      verified against a receiver capture.
- [ ] REST serving layer (MVP) + HA add-on `config.yaml`.
- [ ] Local bare-git-repo cache mode (the `packages: url:` "repo" experience).
- [ ] Optional smart-HTTP git backend.
- [ ] Button-set selection / naming / dedup.
