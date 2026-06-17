# ESPHome IR Codegen — Home Assistant add-on

Serves IR code sets to ESPHome as git repos. Your device clones a source and
selects a remote by path — the **source repo is the URL** and the **ref is your
`ref:`**, both per-device, built on demand. No IR codes in your config.

| Source | `url:` | From | `files:` path |
|--------|--------|------|---------------|
| **flipper** | `…/<owner>/<name>.git` | any [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) repo or fork (the URL path) at `ref:` | mirrors the tree — `TVs/Sony/Sony_Bravia.yaml` |
| **ha-ir** | `…/ha-ir.git` (reserved) | [infrared-protocols](https://github.com/home-assistant-libs/infrared-protocols) curated code sets | `<brand>/<type>.yaml` — `vizio/tv.yaml` |

## Install

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add:
   `https://github.com/HomeOps/esphome-ir-codegen`
2. Install **ESPHome IR Codegen** and **Start** it. There's nothing to configure:
   the source repo and ref are per-device. The **first clone** of any
   `(repo, ref)` generates that whole Flipper database (~9k components — a few
   minutes), then it's cached and shared; the cache is rebuilt automatically when
   the source branch gets new commits. `adapters` (default `flipper,ha-ir`) can
   drop the reserved ha-ir build if you only want flipper.

## Use from ESPHome

### Minimal snippet

```yaml
remote_transmitter:
  id: ir_tx
  pin: GPIO12

packages:
  tv:
    url: http://<addon-host>:9418/Lucaslhm/Flipper-IRDB.git   # source repo IS the path
    ref: main                                                 # any branch/tag — built on demand
    files: [TVs/Sony/Sony_Bravia.yaml]      # flipper path (ha-ir: url …/ha-ir.git, vizio/tv.yaml)
```

`<addon-host>` is the add-on hostname (e.g. `948146ed-esphome-ir-codegen` — the
hash-prefixed slug in the add-on page URL) or your HA host's IP. The `url:` path
is the Flipper source repo (point it at any fork) and `ref:` is any branch/tag
(pin an unmerged PR branch freely); the reserved `…/ha-ir.git` serves the curated
HA code sets. Reference the generated buttons, e.g. `button.press: tv_sony_bravia_power`
— ids are namespaced by the code-set path (see [Button ids](#button-ids)). Swap
the `files:` path for any remote in the repo.

### Complete, runnable device (copy-paste)

A full M5 Atom Lite config — Wi-Fi, API, OTA, logger — whose front button toggles
a Sony Bravia. Drop your secrets in `secrets.yaml` and flash:

```yaml
esphome:
  name: ir-blaster

esp32:
  board: m5stack-atom        # M5 Atom Lite (ESP32-PICO)
  framework:
    type: arduino

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

api:
  encryption:
    key: !secret api_key

ota:
  - platform: esphome
    password: !secret ota_password

logger:

remote_transmitter:
  id: ir_tx
  pin:
    number: GPIO12            # the Atom's built-in IR LED (strapping pin)
    ignore_strapping_warning: true
  carrier_duty_percent: 50%
  non_blocking: true          # explicit (default changed in ESPHome 2025.11.0)

packages:
  tv:
    url: http://<addon-host>:9418/Lucaslhm/Flipper-IRDB.git
    ref: main
    files: [TVs/Sony/Sony_Bravia.yaml]

binary_sensor:
  - platform: gpio
    name: "Atom Button"
    pin:
      number: GPIO39          # input-only; board has an external pull-up
      inverted: true
      mode: { input: true }
    on_press:
      - button.press: tv_sony_bravia_power
```

## Button ids

Generated button ids are **namespaced by the code-set path** so buttons from
different remotes never collide when you include more than one package:
`<category>_<brand>[_<model>]_<key>`. The category (first path segment) drops its
trailing `s`; the brand is the filename's first token. When the file sits in a
brand folder that repeats the brand (Flipper's `Category/Brand/Brand_Model`
layout), the model word is kept so distinct models stay distinct:

| `files:` path | Sub-device | Button (key `Power`) |
|---------------|------------|----------------------|
| `TVs/Sony/Sony_Bravia.yaml` | Sony Bravia | `tv_sony_bravia_power` |
| `KVMs/Generic_8K_HDMI_DP_4Port_KVM.yaml` | Generic | `kvm_generic_power` |
| `vizio/tv.yaml` (ha-ir) | tv | `vizio_tv_power` |

Each included component also **auto-creates a Home Assistant sub-device** (via
`esphome: devices:`) named after the remote — so every button from one `files:`
entry is grouped under its own device in HA, no manual wiring. Requires an
ESPHome version with sub-device support (2025.x+).

## Source repo & ref are per-device

There is **no `repo` or `ref` add-on option** — they belong on each device:

- **Repo** is the `url:` path: `…/<owner>/<name>.git` is the Flipper-IRDB repo or
  fork to build from. Different devices can use different forks against one add-on.
- **Ref** is `ref:`: any branch or tag. The add-on clones that repo @ ref,
  transforms it on the first request, caches it, and rebuilds automatically when
  the source branch HEAD moves (no add-on restart needed). Pin an unmerged PR
  branch to consume codes before they're upstreamed.

> Refs must be branch/tag **names**, not commit shas (the served repo has its own
> transformed commits, so a source sha can't be fetched directly).

## Options

| Option | Default | Notes |
|--------|---------|-------|
| `adapters` | `flipper,ha-ir` | Comma-separated. `flipper` enables on-demand `…/<owner>/<name>.git`; `ha-ir` prebuilds the reserved `…/ha-ir.git`. Drop `ha-ir` for flipper-only. |

## Gotchas (learned on real hardware)

- **Never set `refresh: 0s`.** ESPHome's default `refresh` (`1d`) is what you
  want — leave it off. `0s` makes ESPHome re-clone on *every* validation, and
  because the dashboard auto-validates, overlapping shallow clones corrupt the
  package cache (`shallow.lock`/`ambiguous argument HEAD` errors). If you already
  hit this, clear `/data/packages` in the ESPHome add-on and recompile.
- **After restarting this add-on, restart the ESPHome add-on too** (or use the
  host IP instead of the hostname). The add-on's container IP changes on restart;
  ESPHome caches the old DNS answer and fails with "couldn't connect". The host
  IP (`http://192.168.x.x:9418/Lucaslhm/Flipper-IRDB.git`) sidesteps stale DNS.
- **The first clone of a new `(repo, ref)` takes a few minutes** — it generates
  ~9k flipper components (~10 MB) on demand. Subsequent clones are instant and
  shared across devices; a new commit on the source branch triggers one rebuild.
- **"Valid firmware" ≠ "correct codes."** A green compile only proves the YAML is
  valid. If a device doesn't respond, verify the codes with a `remote_receiver`
  capture. Every parsed (library-encoded) signal already ships with a built-in
  `repeat:` (×3) — Sony SIRC and others need it; only `raw` captures are sent
  as-is.
