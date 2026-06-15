# ESPHome IR Codegen — Home Assistant add-on

Serves the entire [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) (or a
fork) to ESPHome as **one git repo, `default.git`**, where each `.ir` path holds
its generated ESPHome component. Your device clones it **once** (and all devices
share that clone) and selects a remote by path. No IR codes in your config.

## Install

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add:
   `https://github.com/HomeOps/esphome-ir-codegen`
2. Install **ESPHome IR Codegen** and **Start** it. The **first start** generates
   the whole database (~9k components — a few minutes); after that it's instant.
   Optionally set `repo` to a fork.

## Use from ESPHome

### Minimal snippet

```yaml
remote_transmitter:
  id: ir_tx
  pin: GPIO12

packages:
  tv:
    url: http://<addon-host>:9418/default.git
    ref: main
    files: [TVs/Sony/Sony_Bravia.yaml]      # the exact Flipper-IRDB path
    refresh: 1d                             # clone once, then reuse (see gotchas)
```

`<addon-host>` is the add-on hostname (e.g. `948146ed-esphome-ir-codegen` — the
hash-prefixed slug in the add-on page URL) or your HA host's IP. Reference the
generated buttons, e.g. `button.press: ir_power`. Swap the `files:` path for any
remote in the database.

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
    url: http://<addon-host>:9418/default.git
    ref: main
    files: [TVs/Sony/Sony_Bravia.yaml]
    refresh: 1d

binary_sensor:
  - platform: gpio
    name: "Atom Button"
    pin:
      number: GPIO39          # input-only; board has an external pull-up
      inverted: true
      mode: { input: true }
    on_press:
      - button.press: ir_power
```

## Options

| Option | Default | Notes |
|--------|---------|-------|
| `repo` | `Lucaslhm/Flipper-IRDB` | Source database repo. Point it at a fork freely. |

## Gotchas (learned on real hardware)

- **Use `refresh: 1d`, never `refresh: 0s`.** `0s` makes ESPHome re-clone on
  *every* validation — and because the dashboard auto-validates, overlapping
  shallow clones corrupt the package cache (`shallow.lock`/`ambiguous argument
  HEAD` errors). `1d` clones once and reuses it. If you already hit this, clear
  `/data/packages` in the ESPHome add-on and recompile.
- **After restarting this add-on, restart the ESPHome add-on too** (or use the
  host IP instead of the hostname). The add-on's container IP changes on restart;
  ESPHome caches the old DNS answer and fails with "couldn't connect". The host
  IP (`http://192.168.x.x:9418/default.git`) sidesteps stale DNS.
- **First start takes a few minutes** — it generates ~9k components into one
  `default.git` (~10 MB). Subsequent clones are instant and shared across devices.
- **"Valid firmware" ≠ "correct codes."** A green compile only proves the YAML is
  valid. If a device doesn't respond, verify the codes with a `remote_receiver`
  capture. Note Sony devices in particular often need the frame repeated (the
  generated component handles common cases; a stubborn TV may need a manual
  `repeat:`).
