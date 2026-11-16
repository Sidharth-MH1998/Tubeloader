"""Container startup and health checks. No downloads during startup."""
import argparse
import http.client
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if args.health:
        connection = http.client.HTTPConnection("127.0.0.1", 8765, timeout=3)
        try:
            connection.request("GET", "/healthz")
            response = connection.getresponse()
            response.read()
            return 0 if response.status == 200 else 1
        finally:
            connection.close()
    if not args.serve:
        parser.error("Use --serve or --health")
    for executable in ("ffmpeg", "ffprobe", "deno"):
        if not shutil.which(executable):
            raise RuntimeError(f"Missing required tool: {executable}")
    subprocess.run(["deno", "--version"], check=True, timeout=10)
    destination = Path(os.environ.get("TUBELOADER_OUTPUT", "/data/downloads"))
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=destination):
        pass
    runpy.run_path(str(Path(__file__).with_name("web_app.py")), run_name="__main__")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Tubeloader startup/health check failed: {exc}", file=sys.stderr)
        sys.exit(1)

