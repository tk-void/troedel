# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # pymatting (pulled in by the cut-out) compiles with numba and wants to
    # cache next to its sources, which a read-only container does not allow.
    NUMBA_CACHE_DIR=/tmp/numba \
    OMP_NUM_THREADS=2 \
    # The container may run as any user id, also one without a home directory.
    HOME=/tmp \
    TROEDEL_DATA_DIR=/data \
    TROEDEL_HOST=0.0.0.0

# "full" includes the local background removal (about 1 GB more).
# Build with --build-arg EXTRAS="" for a small image without it.
ARG EXTRAS="[cutout]"

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".${EXTRAS}"

# An unprivileged user. Mount the data directory writable for UID 10001, or
# run with --user to match the owner of an existing directory.
RUN useradd --uid 10001 --create-home troedel && mkdir -p /data && chown troedel /data
USER troedel
VOLUME /data
EXPOSE 8099

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=5).status == 200 else 1)"

CMD ["troedel"]
