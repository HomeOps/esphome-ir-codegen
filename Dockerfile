# Codegen image — Flipper-IRDB -> ESPHome transformer.
#
#   CLI:    docker run IMAGE --path <Category>/<Brand>/<Model>.ir --ref <sha>
#   serve:  docker run -p 9418:9418 IMAGE --serve --path <...> --out <...> --ref <sha>
#           -> serves git://<host>:9418/irdb.git, which ESPHome pulls via
#              `packages: { url: "git://<host>:9418/irdb.git", files: [...] }`
FROM python:3.12-slim

# git is required for --serve (the component is served by `git daemon`).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY flipper_ir_to_esphome.py /app/

EXPOSE 9418

# stdlib-only — no pip dependencies.
ENTRYPOINT ["python", "/app/flipper_ir_to_esphome.py"]
