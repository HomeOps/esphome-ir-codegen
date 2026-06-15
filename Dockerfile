# Codegen image — IR code sets -> ESPHome components, served as git repos.
#
#   serve:  docker run -p 9418:9418 IMAGE --serve            (the add-on)
#           -> builds one bare repo per adapter (flipper.git + ha-ir.git) and
#              serves them over smart HTTP. A device clones
#              http://<host>:9418/<adapter>.git and picks files: [<path>.yaml].
#              Knobs: --repo (flipper source/fork), --adapters.
#   CLI:    docker run IMAGE --path <Cat>/<Brand>/<Model>.ir  (print one component)
# Python 3.14 is required by the infrared-protocols dependency.
FROM python:3.14-slim

# git is required for --serve (components are served as git repos).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first for layer caching (infrared-protocols: protocol encoders).
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY flipper_ir_to_esphome.py /app/

EXPOSE 9418

ENTRYPOINT ["python", "/app/flipper_ir_to_esphome.py"]
