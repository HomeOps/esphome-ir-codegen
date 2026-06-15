# Codegen image — Flipper-IRDB -> ESPHome transformer.
#
#   serve:  docker run -p 9418:9418 IMAGE --serve            (the add-on)
#           -> builds the whole DB into default.git and serves it over smart
#              HTTP. A device clones http://<host>:9418/default.git once and
#              picks files: [<Flipper/path>.ir]. Only knob: --repo (a fork).
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
