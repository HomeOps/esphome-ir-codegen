# Home Assistant add-on image. BUILD_FROM is the published codegen image (see
# build.yaml), which already contains python, git, and the transformer with its
# ENTRYPOINT ["python", "/app/flipper_ir_to_esphome.py"].
ARG BUILD_FROM
FROM ${BUILD_FROM}

# HA passes the add-on's user options as /data/options.json; the entrypoint
# (inherited from the base image) reads them and starts the git service.
CMD ["--from-options", "/data/options.json"]
