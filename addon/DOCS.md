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

```yaml
remote_transmitter:
  id: ir_tx
  pin: GPIO12

packages:
  tv:
    url: http://<addon-host>:9418/default.git
    ref: main
    files: [TVs/Sony/Sony_Bravia.ir]      # the exact Flipper-IRDB path
    refresh: 0s
```

`<addon-host>` is the add-on hostname (e.g. `948146ed-esphome-ir-codegen` — the
hash-prefixed slug in the add-on page URL) or your HA host's IP. Reference the
generated buttons, e.g. `button.press: ir_power`. Swap the `files:` path for any
remote in the database.

## Options

| Option | Default | Notes |
|--------|---------|-------|
| `repo` | `Lucaslhm/Flipper-IRDB` | Source database repo. Point it at a fork freely. |

## Notes

- First start pre-generates ~9k components (one `default.git`, ~10 MB); every
  device then shares one clone instead of one-per-remote.
- "Valid firmware" ≠ "correct codes" — verify with a `remote_receiver` capture if
  a device doesn't respond.
