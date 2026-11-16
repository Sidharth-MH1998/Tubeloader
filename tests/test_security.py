import http.client
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import web_app


class SecurityTests(unittest.TestCase):
    def test_only_individual_canonical_videos(self):
        self.assertEqual(
            web_app.canonical_video_url("https://youtu.be/abc123def45?si=tracking"),
            "https://www.youtube.com/watch?v=abc123def45",
        )
        for url in ("https://youtube.com/@someone", "https://youtube.com/playlist?list=x",
                    "https://youtube.com.evil.test/watch?v=abc123def45",
                    "https://user:pass@youtube.com/watch?v=abc123def45",
                    "file:///etc/passwd", "https://youtu.be/invalid"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                web_app.canonical_video_url(url)

    def test_media_limits(self):
        self.assertIsNotNone(web_app.validate_media({"is_live": True}))
        self.assertIsNotNone(web_app.validate_media({"duration": web_app.MAX_DURATION + 1}))
        self.assertIsNotNone(web_app.validate_media({}))
        self.assertIsNone(web_app.validate_media({}, incomplete=True))
        self.assertIsNone(web_app.validate_media({"duration": 60}))

    def test_http_guards_and_health(self):
        server = web_app.ThreadingHTTPServer(("127.0.0.1", 0), web_app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        port = server.server_port
        thread.start()
        try:
            with patch.object(web_app, "ALLOWED_HOSTS", {f"127.0.0.1:{port}"}):
                for method, path, headers, expected in (
                    ("GET", "/healthz", {}, 200),
                    ("GET", "/", {"Host": "evil.example"}, 403),
                    ("GET", "/files/../../web_app.py", {}, 404),
                    ("POST", "/api/jobs", {"Content-Type": "application/json"}, 403),
                ):
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                    connection.request(method, path, body="{}" if method == "POST" else None, headers=headers)
                    response = connection.getresponse()
                    response.read()
                    self.assertEqual(response.status, expected)
                    self.assertEqual(response.getheader("X-Frame-Options"), "DENY")
                    connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

