# gauntletx hosted server, containerized.
#
# Stdlib-only app, so the image is just Python plus three files — nothing to
# compile, nothing to pip install. Same rule as promptx, for the same reason:
# a NAS you do not control is still good enough, and the image cannot drift
# from the repo.
#
# Build (tag with the VERSION file so the image IS the release):
#   docker build --build-arg VERSION="$(cat VERSION)" -t "gauntletx:$(cat VERSION)" .

FROM python:3.12-slim

ARG VERSION=unknown
LABEL org.opencontainers.image.title="gauntletx" \
      org.opencontainers.image.description="Generates ready-to-paste Gauntlet Loop prompts from a goal" \
      org.opencontainers.image.source="https://github.com/NathanMaine/gauntletx" \
      org.opencontainers.image.version="$VERSION"

RUN useradd --uid 1000 --user-group gauntletx
WORKDIR /app

# The whole app: the core file (server + CLI + embedded UI), the version
# shim, and the version itself.
COPY gauntletx.py gauntletx_version.py VERSION ./

# read_only rootfs in compose means no bytecode cache writes either.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER gauntletx
EXPOSE 7332

# /api/version is both the health probe and the "what is actually running"
# answer.
CMD ["python3", "gauntletx.py", "--port", "7332", "--host", "0.0.0.0"]
