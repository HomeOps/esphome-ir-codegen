# Flipper-IRDB → ESPHome codegen (Home Assistant add-on)

Turn a [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) `.ir` file into a
ready-to-use ESPHome `remote_transmitter` component **on demand**, by referencing
it from your ESPHome YAML as if it were a remote package source.

> **Status:** working transformer, Dockerized, with an **end-to-end CI test that
> builds real firmware from a real Flipper file** (see
> [CI](#ci-the-sony-bravia-end-to-end-test)). The HA add-on serving layer is the
> next step — see [Roadmap](#roadmap).

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

```bash
docker build -t esphome-ir-codegen .
docker run --rm esphome-ir-codegen \
  --ref d126fb1b6f1e114c52b4a8c19839ea65e3a9c24d \
  --path TVs/Sony/Sony_Bravia.ir \
  --tx ir_tx --prefix "Bravia"
```

It prints ESPHome YAML to stdout — redirect it into a file your device config
`!include`s.

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

| Stage | Mechanism | Effort |
|-------|-----------|--------|
| **MVP** | REST endpoint (`GET /gen?ref=…&path=…&tx=…&prefix=…`) → returns YAML; `!include` or write into `/config/esphome/`. | low |
| **v2 (the vision)** | Back it with a **real local bare-git repo** in a shared volume; the add-on commits generated YAML, ESPHome clones via `packages: url: file:///share/irdb-cache.git`. "Feels like a repo," no git-protocol code. | medium |
| **v3** | Full **smart-HTTP git backend** that generates YAML at clone time. | high |

Target ESPHome usage (v2):

```yaml
packages:
  tv_codes:
    url: http://<addon>:8099/irdb.git    # the add-on, posing as a repo
    ref: main
    files: [Samsung_TV.yaml]             # <- generated from Samsung_TV.ir
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

## CI: the Sony Bravia end-to-end test

Every push and PR runs the real thing (`.github/workflows/ci.yaml`):

1. **Build** the codegen Docker image.
2. **Run** it to generate the **Sony Bravia** component from a pinned
   Flipper-IRDB ref.
3. **Compile** real ESP32 firmware (`firmware-test/device.yaml`) that `!include`s
   the generated component, using ESPHome.
4. **Upload** the resulting `firmware.bin` as a build artifact.

If the generated YAML were malformed, step 3 fails — so a green build means the
Sony Bravia codes produce **valid firmware**. (Validity ≠ correctness: that the
codes are the *right* ones for your TV is verified separately against a live
`remote_receiver` capture.) This Sony Bravia run is the regression test guarding
every future PR.

Releases use [release-please](https://github.com/googleapis/release-please);
a tagged release publishes the image to GHCR (`.github/workflows/publish.yaml`).

## Roadmap

- [x] Parsed-protocol coverage: Sony (SIRC/SIRC15/SIRC20). NEC/NECext + raw.
- [x] `Dockerfile` + end-to-end CI (Sony Bravia → firmware).
- [ ] More parsed protocols: Samsung32, RC5/RC6, Panasonic, Pioneer — each
      verified against a receiver capture.
- [ ] REST serving layer (MVP) + HA add-on `config.yaml`.
- [ ] Local bare-git-repo cache mode (the `packages: url:` "repo" experience).
- [ ] Optional smart-HTTP git backend.
- [ ] Button-set selection / naming / dedup.
