import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import download


class PipelineTests(unittest.TestCase):
    def test_batch_deduplicates_and_ignores_comments(self):
        with tempfile.TemporaryDirectory() as folder:
            batch = Path(folder) / "urls.txt"
            batch.write_text("# comment\nhttps://youtu.be/abc\n\nhttps://youtu.be/def\n", encoding="utf-8")
            args = download.parser().parse_args(["https://youtu.be/abc", "--file", str(batch)])
            self.assertEqual(download.collect_urls(args), ["https://youtu.be/abc", "https://youtu.be/def"])

    def test_rejects_unrelated_hosts_and_playlist_without_opt_in(self):
        for url in ("https://youtube.com.evil.test/watch?v=abc", "file:///tmp/video", "https://youtube.com/playlist?list=abc"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                download.collect_urls(download.parser().parse_args([url]))

    def test_history_isolated_and_simulation_does_not_record(self):
        args = download.parser().parse_args(["https://youtu.be/abc", "--max-height", "720"])
        video = download.build_options(args, "video")
        audio = download.build_options(args, "audio")
        self.assertNotEqual(video["download_archive"], audio["download_archive"])
        self.assertEqual(video["format"], "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]")
        args.simulate = True
        self.assertNotIn("download_archive", download.build_options(args, "video"))

    def test_failure_does_not_stop_other_urls_or_audio_pass(self):
        calls = []

        class DownloadError(Exception):
            pass

        class FakeDownloader:
            def __init__(self, options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def download(self, urls):
                calls.extend(urls)
                if len(calls) == 1:
                    raise DownloadError("simulated failure")
                return 0

        fake = SimpleNamespace(YoutubeDL=FakeDownloader, utils=SimpleNamespace(DownloadError=DownloadError))
        with patch.dict(sys.modules, {"yt_dlp": fake}):
            result = download.main(["https://youtu.be/abc", "https://youtu.be/def", "--mode", "both", "--simulate"])
        self.assertEqual(result, 1)
        self.assertEqual(calls, ["https://youtu.be/abc", "https://youtu.be/def"] * 2)


if __name__ == "__main__":
    unittest.main()
