# Flipper-IRDB → ESPHome codegen (Home Assistant add-on)

Turn a [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) `.ir` file into a
ready-to-use ESPHome `remote_transmitter` component **on demand**, by referencing
it from your ESPHome YAML as if it were a remote package source.

> **Status:** design + working transformer prototype
> ([`flipper_ir_to_esphome.py`](flipper_ir_to_esphome.py)). The serving layer
> (HA add-on) is not built yet — see [Roadmap](#roadmap).

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
| other parsed (Sony, Samsung, RC5/6, …) | `# TODO unsupported` comment | ⏳ next |

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

## Roadmap

- [ ] Parsed-protocol coverage: Sony (SIRC), Samsung32, RC5/RC6, Panasonic,
      Pioneer — each verified against a receiver capture.
- [ ] REST serving layer (MVP) + `Dockerfile` + HA add-on `config.yaml`.
- [ ] Local bare-git-repo cache mode (the `packages: url:` "repo" experience).
- [ ] Optional smart-HTTP git backend.
- [ ] Button-set selection / naming / dedup.
