# Codegen image — Flipper-IRDB -> ESPHome transformer.
#
#   serve:  docker run -p 9418:9418 IMAGE --serve           (path-less; the add-on)
#           -> lazy git-over-HTTP. A device clones
#              http://<host>:9418/<Flipper/path>.git and the component is
#              generated on demand. Only knob: --repo (a Flipper-IRDB fork).
#   CLI:    docker run IMAGE --path <Cat>/<Brand>/<Model>.ir  (print one component)
FROM python:3.12-slim

# git is required for --serve (components are served as git repos).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY flipper_ir_to_esphome.py /app/

EXPOSE 9418

# stdlib-only — no pip dependencies.
ENTRYPOINT ["python", "/app/flipper_ir_to_esphome.py"]
