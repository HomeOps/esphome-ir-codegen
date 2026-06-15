# Codegen image — runs the Flipper-IRDB -> ESPHome transformer.
# Today the entrypoint is the CLI; a `serve` (REST) mode is on the roadmap so the
# same image can back the Home Assistant add-on.
FROM python:3.12-slim

WORKDIR /app
COPY flipper_ir_to_esphome.py /app/

# stdlib-only — no pip dependencies yet.
ENTRYPOINT ["python", "/app/flipper_ir_to_esphome.py"]
