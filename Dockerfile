FROM denoland/deno:bin-2.9.8 AS deno
FROM python:3.15-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TUBELOADER_HOST=0.0.0.0 \
    TUBELOADER_PORT=8765 \
    TUBELOADER_OUTPUT=/data/downloads \
    HOME=/tmp \
    DENO_DIR=/tmp/deno

COPY --from=deno /deno /usr/local/bin/deno
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 tubeloader \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin tubeloader \
    && mkdir -p /data/downloads \
    && chown -R 10001:10001 /data

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY download.py web_app.py container_check.py ./
COPY web/ ./web/
USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "container_check.py", "--health"]
CMD ["python", "container_check.py", "--serve"]

