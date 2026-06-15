# ESPHome IR Codegen — Home Assistant add-on

Serves IR codes from [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) (or
a fork) to ESPHome as **on-demand git packages**. Your ESPHome device clones a
per-remote URL and the component is generated at request time — no IR codes in
your config, and nothing to configure here except the source repo.

## Install

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add:
   `https://github.com/HomeOps/esphome-ir-codegen`
2. Install **ESPHome IR Codegen** and **Start** it. (Optionally set `repo` to a
   fork; default is `Lucaslhm/Flipper-IRDB`.)

## Use from ESPHome

The URL path is the Flipper-IRDB path with `.git`; the file is the model name:

```yaml
remote_transmitter:
  id: ir_tx
  pin: GPIO12

packages:
  tv:
    url: http://<addon-host>:9418/TVs/Sony/Sony_Bravia.git
    files: [Sony_Bravia.yaml]
    refresh: 0s
```

`<addon-host>` is the add-on's hostname (e.g. `948146ed-esphome-ir-codegen` — the
hash-prefixed slug shown in the add-on page URL) or your HA host's IP. Then
reference the generated buttons, e.g. `button.press: ir_power`.

Swap the URL path for any remote in the database — `ACs/LG/LG_AKB.git`,
`Audio_Receivers/Denon/...` — no add-on change needed.

## Options

| Option | Default | Notes |
|--------|---------|-------|
| `repo` | `Lucaslhm/Flipper-IRDB` | Source database repo. Point it at a fork freely. |

## Notes

- "Valid firmware" ≠ "correct codes" — verify with a `remote_receiver` capture if
  a device doesn't respond.
- Uses the source repo's default branch (HEAD), so results track upstream.
