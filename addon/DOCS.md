# ESPHome IR Codegen — Home Assistant add-on

Serves IR codes from [Flipper-IRDB](https://github.com/Lucaslhm/Flipper-IRDB) to
ESPHome as a `git://` package source. Your ESPHome device pulls a generated
component at compile time — no IR codes in your config.

## Install

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, add:
   `https://github.com/HomeOps/esphome-ir-codegen`
2. Install **ESPHome IR Codegen**.
3. In **Configuration**, set:
   - `ref` — a pinned Flipper-IRDB commit (reproducibility).
   - `path` — the `.ir` file, e.g. `TVs/Sony/Sony_Bravia.ir`.
   - `out` — optional output name; defaults to the path with `.yaml`
     (`TVs/Sony/Sony_Bravia.yaml`).
4. Start the add-on. It serves `git://<your-ha-host>:9418/irdb.git`.

## Use from ESPHome

```yaml
remote_transmitter:
  id: ir_tx
  pin: GPIO12

packages:
  tv:
    url: git://<your-ha-host>:9418/irdb.git
    ref: main
    files: [TVs/Sony/Sony_Bravia.yaml]   # mirrors the .ir path you configured
    refresh: 0s
```

Then reference the generated buttons, e.g. `button.press: ir_power`.

## Notes / limitations

- One configured remote per add-on instance for now; on-demand serving of any
  requested path is on the roadmap.
- "Valid firmware" ≠ "correct codes." Verify with a `remote_receiver` capture if
  a device doesn't respond.
