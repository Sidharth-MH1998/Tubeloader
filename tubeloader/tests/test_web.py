import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import web_app


class WebTests(unittest.TestCase):
    def test_validation(self):
        for body in ({}, {"url": "https://example.com"}, {"url": "https://youtu.be/abc123def45", "mode": "invalid"}, {"url": "https://youtube.com/playlist?list=abc"}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                web_app.make_args(body, "test")

    def test_job_generates_download_links(self):
        class Downloader:
            def __init__(self, options):
                self.options = options
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def download(self, urls):
                destination = Path(self.options["paths"]["home"])
                (destination / "Example video.mp4").write_bytes(b"test")
                return 0
        with tempfile.TemporaryDirectory() as folder, patch.object(web_app.yt_dlp, "YoutubeDL", Downloader):
            args = web_app.make_args({"url": "https://youtu.be/abc123def45"}, "test")
            args.output = Path(folder)
            web_app.JOBS["test"] = {"files": []}
            try:
                web_app.run_job("test", args)
                job = web_app.JOBS["test"]
                self.assertEqual(job["status"], "done")
                self.assertEqual(job["files"][0]["url"], "/files/test/video/Example%20video.mp4")
            finally:
                del web_app.JOBS["test"]

    def test_worker_reports_failure(self):
        args = web_app.make_args({"url": "https://youtu.be/abc123def45"}, "failure")
        with tempfile.TemporaryDirectory() as folder, patch.object(web_app.yt_dlp, "YoutubeDL", side_effect=RuntimeError("Offline")):
            args.output = Path(folder)
            web_app.JOBS["failure"] = {"files": []}
            try:
                web_app.run_job("failure", args)
                self.assertEqual(web_app.JOBS["failure"]["status"], "error")
                self.assertIn("Offline", web_app.JOBS["failure"]["detail"])
            finally:
                del web_app.JOBS["failure"]
