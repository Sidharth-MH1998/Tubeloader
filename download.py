"""Download YouTube videos and audio using yt-dlp."""

import argparse
from pathlib import Path
import shutil
import sys
from urllib.parse import urlparse


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("urls", nargs="*", help="YouTube video or playlist URLs")
    cli.add_argument("--file", type=Path, help="UTF-8 file containing one URL per line")
    cli.add_argument("--mode", choices=("video", "audio", "both"), default="video")
    cli.add_argument("--output", type=Path, default=Path("downloads"))
    cli.add_argument("--audio-format", choices=("mp3", "m4a", "wav", "flac", "opus"), default="mp3")
    cli.add_argument("--audio-quality", choices=("64", "96", "128", "192", "256", "320"), default="192", help="Audio conversion bitrate in kbps (lossy formats)")
    cli.add_argument("--max-height", type=positive_int, help="Maximum video height, e.g. 1080")
    cli.add_argument("--playlist", action="store_true", help="Allow downloading entire playlists")
    cli.add_argument("--simulate", action="store_true", help="Check extraction without saving media")
    cli.add_argument("--no-archive", action="store_true", help="Ignore previous download history")
    return cli


def collect_urls(args):
    urls = list(args.urls)
    if args.file:
        urls.extend(line.strip() for line in args.file.read_text(encoding="utf-8-sig").splitlines()
                    if line.strip() and not line.lstrip().startswith("#"))
    if not urls:
        raise ValueError("Provide a URL or --file urls.txt")
    for url in urls:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https") or not (
            host in ("youtube.com", "youtu.be", "youtube-nocookie.com")
            or host.endswith(".youtube.com")
        ):
            raise ValueError(f"Expected a YouTube URL, got: {url}")
        if not args.playlist and parsed.path.rstrip("/") == "/playlist":
            raise ValueError("Playlist URLs require --playlist")
    return list(dict.fromkeys(urls))


def build_options(args, mode):
    destination = args.output.resolve() / mode
    options = {
        "paths": {"home": str(destination)},
        "outtmpl": "%(title).180B [%(id)s].%(ext)s",
        "windowsfilenames": True,
        "noplaylist": not args.playlist,
        "retries": 5,
        "fragment_retries": 5,
        "skip_unavailable_fragments": False,
        "continuedl": True,
        "ignoreerrors": False,
        "simulate": args.simulate,
        "js_runtimes": {name: {} for name in ("deno", "node") if shutil.which(name)},
    }
    if not args.no_archive and not args.simulate:
        # Keep history separate for each requested output profile.
        profile = f"{args.audio_format}-{args.audio_quality}" if mode == "audio" else f"mp4-{args.max_height or 'best'}"
        options["download_archive"] = str(destination / f".archive-{profile}.txt")
    if mode == "audio":
        options["outtmpl"] = f"%(title).180B [%(id)s] [{args.audio_quality}k].%(ext)s" if args.audio_format not in ("wav", "flac") else "%(title).180B [%(id)s].%(ext)s"
        options.update({
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": args.audio_format,
                                "preferredquality": args.audio_quality}],
        })
    else:
        limit = f"[height<={args.max_height}]" if args.max_height else ""
        options.update({
            "format": f"bestvideo[ext=mp4]{limit}+bestaudio[ext=m4a]/best[ext=mp4]{limit}",
            "merge_output_format": "mp4",
            "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        })
        # Separate resolution profiles so a later higher quality request isn't skipped.
        options["outtmpl"] = f"%(title).180B [%(id)s] [{args.max_height or 'best'}].%(ext)s"
    return options


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    try:
        urls = collect_urls(args)
    except (ValueError, OSError) as exc:
        cli.error(str(exc))
    try:
        import yt_dlp
    except ImportError:
        print("Install dependencies: python -m pip install -r requirements.txt", file=sys.stderr)
        return 2
    if not args.simulate:
        missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
        if missing:
            print(f"Missing from PATH: {', '.join(missing)}. See README.md for setup.", file=sys.stderr)
            return 2
    modes = ("video", "audio") if args.mode == "both" else (args.mode,)
    failed = False
    try:
        for mode in modes:
            options = build_options(args, mode)
            if not args.simulate:
                Path(options["paths"]["home"]).mkdir(parents=True, exist_ok=True)
            print(f"\n=== {mode.upper()} ===", flush=True)
            # Continue other input URLs even if one URL or playlist fails.
            with yt_dlp.YoutubeDL(options) as ydl:
                for url in urls:
                    try:
                        failed = bool(ydl.download([url])) or failed
                    except yt_dlp.utils.DownloadError as exc:
                        print(f"Failed: {url}: {exc}", file=sys.stderr)
                        failed = True
    except KeyboardInterrupt:
        print("\nInterrupted. Run the same command to resume partial downloads.", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"File error: {exc}", file=sys.stderr)
        return 1
    print("\nCompleted with errors." if failed else "\nCompleted successfully.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
