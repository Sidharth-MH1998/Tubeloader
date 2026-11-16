"""Local web interface. Run: python web_app.py"""

import json
import os
import secrets
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, quote, parse_qs
import re

import yt_dlp
import download


ROOT = Path(__file__).resolve().parent

OUTPUT = Path(
    os.environ.get(
        "TUBELOADER_OUTPUT",
        str(ROOT / "downloads" / "web"),
    )
).resolve()

PORT = int(os.environ.get("TUBELOADER_PORT", "8765"))

# Address the web server listens on.
# Default is localhost only.
HOST = os.environ.get("TUBELOADER_HOST", "127.0.0.1")

# Hosts that are allowed to access the application.
ALLOWED_HOSTS = {
    f"127.0.0.1:{PORT}",
    f"localhost:{PORT}",
}

# Additional hosts can be supplied through systemd/environment variables.
#
# Example:
# TUBELOADER_ALLOWED_HOSTS=server.example:8765
#
for host in os.environ.get("TUBELOADER_ALLOWED_HOSTS", "").split(","):
    host = host.strip()
    if host:
        ALLOWED_HOSTS.add(host)


TOKEN = secrets.token_urlsafe(32)

JOBS = {}

LOCK = threading.Lock()

POOL = ThreadPoolExecutor(max_workers=1)
MAX_DURATION = int(os.environ.get("TUBELOADER_MAX_DURATION", "7200"))
MAX_BYTES = int(os.environ.get("TUBELOADER_MAX_DOWNLOAD_MB", "2048")) * 1024 * 1024
MIN_FREE = int(os.environ.get("TUBELOADER_MIN_FREE_MB", "1024")) * 1024 * 1024
if min(MAX_DURATION, MAX_BYTES, MIN_FREE) <= 0:
    raise ValueError("Download limits must be positive.")


def validate_media(info, *, incomplete=False):
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
        return "Live and upcoming streams are not supported."
    duration = info.get("duration")
    if duration is None and not incomplete:
        return "Cannot verify video duration."
    if duration is not None and duration > MAX_DURATION:
        return f"Video exceeds the {MAX_DURATION}-second duration limit."
    return None


def canonical_video_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        raise ValueError("Enter a normal YouTube video link.")
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        video_id = parsed.path.strip("/")
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        parts = parsed.path.strip("/").split("/")
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in ("shorts", "embed", "live"):
            video_id = parts[1]
        else:
            raise ValueError("Use an individual video link, not a channel or playlist.")
    else:
        raise ValueError("Only YouTube video links are supported.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("The YouTube video ID is invalid.")
    return "https://www.youtube.com/watch?v=" + video_id



def update(job_id, **values):
    with LOCK:
        JOBS[job_id].update(values)


def run_job(job_id, args):
    errors = []

    class Logger:
        def debug(self, message):
            pass

        def warning(self, message):
            update(job_id, warning=message)

        def error(self, message):
            pass

    def progress(data):
        if data.get("downloaded_bytes", 0) > MAX_BYTES:
            raise yt_dlp.utils.DownloadError("Stream exceeds the download size limit.")
        if shutil.disk_usage(args.output).free < MIN_FREE:
            raise yt_dlp.utils.DownloadError("Download stopped: not enough free disk space.")
        total = (
            data.get("total_bytes")
            or data.get("total_bytes_estimate")
        )

        percent = (
            min(
                100,
                100 * data.get("downloaded_bytes", 0) / total,
            )
            if total
            else None
        )

        update(
            job_id,
            progress=percent,
            detail=(
                "Processing media…"
                if data["status"] == "finished"
                else "Downloading stream…"
            ),
            title=data.get(
                "info_dict", {}
            ).get(
                "title",
                "YouTube download",
            ),
        )

    update(
        job_id,
        status="running",
        detail="Connecting to YouTube…",
    )

    try:
        modes = (
            ("video", "audio")
            if args.mode == "both"
            else (args.mode,)
        )

        for mode in modes:
            update(
                job_id,
                stage=mode,
                progress=None,
            )

            options = download.build_options(
                args,
                mode,
            )

            options.update(
                logger=Logger(),
                progress_hooks=[progress],
                quiet=True,
                socket_timeout=20,
                match_filter=validate_media,
                max_filesize=MAX_BYTES,
                postprocessor_hooks=[
                    lambda data: update(
                        job_id,
                        detail="Preparing your file…",
                        progress=None,
                    )
                ],
            )

            Path(
                options["paths"]["home"]
            ).mkdir(
                parents=True,
                exist_ok=True,
            )

            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    if ydl.download(args.urls):
                        errors.append(
                            f"The {mode} download did not complete."
                        )

            except Exception as exc:
                errors.append(str(exc))

        files = []

        for path in args.output.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower()
                in (
                    ".mp4",
                    ".mp3",
                    ".m4a",
                    ".wav",
                    ".flac",
                    ".opus",
                )
            ):
                relative = (
                    path.relative_to(
                        args.output
                    ).as_posix()
                )

                files.append(
                    {
                        "name": path.name,
                        "size": path.stat().st_size,
                        "url": (
                            f"/files/{job_id}/"
                            f"{quote(relative)}"
                        ),
                    }
                )

        if not files and not errors:
            errors.append(
                "No media files were produced."
            )

        update(
            job_id,
            status=(
                "error"
                if errors
                else "done"
            ),
            detail=(
                " · ".join(errors)
                if errors
                else "Your files are ready."
            ),
            progress=(
                100
                if not errors
                else None
            ),
            files=files,
        )

    except Exception as exc:
        update(
            job_id,
            status="error",
            detail=str(exc),
        )


def make_args(body, job_id):
    if (
        not isinstance(body, dict)
        or not isinstance(
            body.get("url"),
            str,
        )
    ):
        raise ValueError(
            "Paste a YouTube link to get started."
        )

    mode = body.get(
        "mode",
        "video",
    )

    audio = body.get(
        "audio_format",
        "mp3",
    )

    height = body.get(
        "height",
        "best",
    )

    quality = body.get(
        "audio_quality",
        "192",
    )

    if (
        mode
        not in (
            "video",
            "audio",
            "both",
        )
        or audio
        not in (
            "mp3",
            "m4a",
            "wav",
            "flac",
            "opus",
        )
        or height
        not in (
            "best",
            "2160",
            "1440",
            "1080",
            "720",
            "480",
            "360",
        )
        or quality
        not in (
            "64",
            "96",
            "128",
            "192",
            "256",
            "320",
        )
    ):
        raise ValueError(
            "Invalid download options."
        )

    args = (
        download.parser()
        .parse_args([])
    )

    args.urls = [canonical_video_url(body["url"].strip())]

    args.mode = mode
    args.audio_format = audio
    args.audio_quality = quality

    args.max_height = (
        None
        if height == "best"
        else int(height)
    )

    args.output = (
        OUTPUT / job_id
    )

    args.no_archive = True

    args.urls = (
        download.collect_urls(args)
    )

    return args


class Handler(BaseHTTPRequestHandler):

    def json_response(
        self,
        data,
        status=200,
    ):
        payload = json.dumps(
            data
        ).encode()

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json",
        )

        self.send_header(
            "Content-Length",
            str(len(payload)),
        )

        self.send_header(
            "Cache-Control",
            "no-store",
        )

        self.end_headers()

        self.wfile.write(payload)

    def valid_host(self):
        host = self.headers.get(
            "Host",
            "",
        )

        return host in ALLOWED_HOSTS

    def setup(self):
        super().setup()

        self.connection.settimeout(
            30
        )

    def end_headers(self):
        self.send_header(
            "X-Frame-Options",
            "DENY",
        )

        self.send_header(
            "X-Content-Type-Options",
            "nosniff",
        )

        self.send_header(
            "Referrer-Policy",
            "no-referrer",
        )

        super().end_headers()

    def do_GET(self):

        if not self.valid_host():
            return self.json_response(
                {
                    "error": "Invalid host",
                },
                403,
            )

        path = urlparse(
            self.path
        ).path

        if path == "/healthz":
            return self.json_response({"status": "ok"})

        if path == "/api/jobs":

            with LOCK:
                snapshot = [
                    dict(job)
                    for job
                    in JOBS.values()
                ]

            return self.json_response(
                {
                    "jobs": snapshot[::-1],
                }
            )

        if path == "/api/config":

            missing = [
                x
                for x
                in (
                    "ffmpeg",
                    "ffprobe",
                )
                if not shutil.which(x)
            ]

            return self.json_response(
                {
                    "token": TOKEN,
                    "missing": missing,
                }
            )

        if path.startswith(
            "/files/"
        ):

            from urllib.parse import unquote

            relative = unquote(
                path[len("/files/"):]
            )

            target = (
                OUTPUT / relative
            ).resolve()

            with LOCK:
                allowed = {
                    file["url"]
                    for job
                    in JOBS.values()
                    for file
                    in job["files"]
                }

            if (
                path not in allowed
                or not target.is_relative_to(
                    OUTPUT.resolve()
                )
                or not target.is_file()
            ):
                return self.json_response(
                    {
                        "error": "File not found",
                    },
                    404,
                )

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "application/octet-stream",
            )

            self.send_header(
                "Content-Disposition",
                (
                    "attachment; "
                    "filename*=UTF-8''"
                    + quote(target.name)
                ),
            )

            self.send_header(
                "Content-Length",
                str(
                    target.stat().st_size
                ),
            )

            self.end_headers()

            with target.open(
                "rb"
            ) as source:
                shutil.copyfileobj(
                    source,
                    self.wfile,
                )

            return

        if path != "/":
            return self.json_response(
                {
                    "error": "Not found",
                },
                404,
            )

        payload = (
            ROOT
            / "web"
            / "index.html"
        ).read_bytes()

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/html; charset=utf-8",
        )

        self.send_header(
            "Content-Length",
            str(len(payload)),
        )

        self.send_header(
            "X-Content-Type-Options",
            "nosniff",
        )

        self.end_headers()

        self.wfile.write(payload)

    def do_POST(self):

        if (
            not self.valid_host()
            or self.headers.get(
                "X-Local-Token"
            )
            != TOKEN
        ):
            return self.json_response(
                {
                    "error":
                    "Refresh the page and try again."
                },
                403,
            )

        if self.path != "/api/jobs":
            return self.json_response(
                {
                    "error": "Not found",
                },
                404,
            )

        try:

            length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )

            if not 0 < length <= 8192:
                raise ValueError(
                    "Request is too large or empty."
                )

            body = json.loads(
                self.rfile.read(length)
            )

            job_id = (
                secrets.token_hex(8)
            )

            args = make_args(
                body,
                job_id,
            )

            if any(
                not shutil.which(x)
                for x
                in (
                    "ffmpeg",
                    "ffprobe",
                )
            ):
                raise ValueError(
                    "Install FFmpeg and ffprobe "
                    "before downloading. "
                    "See README.md."
                )

            OUTPUT.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(OUTPUT).free < MIN_FREE:
                raise ValueError("Not enough free disk space to start a download.")

            with LOCK:

                active_jobs = sum(
                    j["status"]
                    in (
                        "queued",
                        "running",
                    )
                    for j
                    in JOBS.values()
                )

                if active_jobs >= 10:
                    raise ValueError(
                        "The queue is full. "
                        "Wait for a download "
                        "to finish."
                    )

                JOBS[job_id] = {
                    "id": job_id,
                    "title": args.urls[0],
                    "mode": args.mode,
                    "status": "queued",
                    "detail":
                        "Waiting in queue…",
                    "progress": None,
                    "files": [],
                }

            POOL.submit(
                run_job,
                job_id,
                args,
            )

            self.json_response(
                {
                    "id": job_id,
                },
                202,
            )

        except (
            ValueError,
            UnicodeError,
        ) as exc:

            self.json_response(
                {
                    "error": str(exc),
                },
                400,
            )


if __name__ == "__main__":

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"Allowed hosts: "
        f"{', '.join(sorted(ALLOWED_HOSTS))}",
        flush=True,
    )

    server = ThreadingHTTPServer(
        (
            HOST,
            PORT,
        ),
        Handler,
    )

    print(
        f"Tubeloader listening on "
        f"{HOST}:{PORT} — "
        f"press Ctrl+C to stop.",
        flush=True,
    )

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        server.server_close()