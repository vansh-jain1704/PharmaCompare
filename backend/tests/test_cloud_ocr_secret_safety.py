"""
The Google Vision API key travels as a "?key=..." query parameter, so anything that prints the request URL, an
exception that quotes it, or an upstream error body that echoes it can leak the key into logs or into an API
response. These tests use a FAKE key and a local fake Vision server (nothing leaves the machine) and check that the
key never appears - in the error text, the exception chain, the traceback, the OCR fallback log, the HTTP library's
debug log, or the upload route's JSON error response - while the diagnostics stay useful.
"""
import io
import json
import logging
import socket
import tempfile
import threading
import traceback
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from PIL import Image

from tests import helpers

FAKE_KEY = "FAKE-VISION-KEY-1234567890abcdef"
GOOGLE_STYLE_KEY = "AIzaSyFAKE0123456789abcdefghijklmnopqrs"


class _Vision(BaseHTTPRequestHandler):
    mode = "ok"

    def log_message(self, *args):   # keep the test output quiet
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        status, body = 200, {"responses": [{}]}
        if self.mode == "http_error":      # an upstream that echoes the key back in its error body
            status, body = 403, {"error": {"message": f"API key not valid: {FAKE_KEY} (request {self.path})"}}
        elif self.mode == "vision_error":
            body = {"responses": [{"error": {"message": f"bad credentials {FAKE_KEY}"}}]}
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class _Server:
    def __init__(self, mode):
        handler = type("H", (_Vision,), {"mode": mode})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1/images:annotate"

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def _closed_port_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}/v1/images:annotate"


def _everything(records):
    """Every log record the way a handler would print it, traceback included."""
    fmt = logging.Formatter("%(name)s %(levelname)s %(message)s")
    return "\n".join(fmt.format(r) for r in records)


class _Base(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.png = f"{self.tmp.name}/rx.png"
        Image.new("RGB", (40, 40), "white").save(self.png)
        for patcher in (mock.patch("app.config.Config.GOOGLE_VISION_API_KEY", FAKE_KEY), mock.patch("app.config.Config.CLOUD_OCR_TIMEOUT_SECONDS", 2)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def endpoint(self, url):
        patcher = mock.patch("app.config.Config.GOOGLE_VISION_ENDPOINT", url)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_no_key(self, text, where=""):
        for secret in (FAKE_KEY, "key=FAKE", GOOGLE_STYLE_KEY):
            self.assertNotIn(secret, text, f"{where}: leaked {secret!r}")


class ErrorMessagesAndTracebacks(_Base):
    def raise_error(self, url):
        from app.services import cloud_ocr_service as c
        self.endpoint(url)
        with self.assertRaises(c.CloudOcrError) as ctx:
            c.extract_words(self.png, "png")
        return ctx.exception

    def test_a_network_failure_message_has_no_key_but_keeps_the_diagnosis(self):
        exc = self.raise_error(_closed_port_url())
        text = str(exc)
        self.assert_no_key(text, "message")
        self.assertIn("could not reach Vision", text)
        self.assertIn("127.0.0.1", text)                                     # which host failed
        self.assertRegex(text, r"ConnectionError|ConnectTimeout|Timeout")   # what kind of failure

    def test_the_original_exception_is_not_chained_onto_it(self):
        exc = self.raise_error(_closed_port_url())
        # "raise ... from exc" printed the ORIGINAL exception (URL and key included) in every traceback
        self.assertIsNone(exc.__cause__)
        self.assertTrue(exc.__suppress_context__ or exc.__context__ is None)
        self.assert_no_key("".join(traceback.format_exception(exc)), "traceback")

    def test_an_upstream_error_body_that_echoes_the_key_is_redacted(self):
        with _Server("http_error") as server:
            exc = self.raise_error(server.url)
        text = str(exc)
        self.assert_no_key(text, "HTTP error")
        self.assertIn("Vision HTTP 403", text)       # status stays visible
        self.assertIn("***", text)                    # and the redaction is visible

    def test_a_vision_reported_error_that_echoes_the_key_is_redacted(self):
        with _Server("vision_error") as server:
            exc = self.raise_error(server.url)
        self.assert_no_key(str(exc), "Vision error")
        self.assertIn("Vision reported an error", str(exc))

    def test_the_success_path_is_unchanged(self):
        from app.services import cloud_ocr_service as c
        with _Server("ok") as server:
            self.endpoint(server.url)
            self.assertEqual(c.extract_words(self.png, "png"), [])


class RedactionHelper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.get_app()
        from app.services.cloud_ocr_service import redact_secrets
        cls.redact = staticmethod(redact_secrets)

    def test_the_configured_key_in_any_form(self):
        with mock.patch("app.config.Config.GOOGLE_VISION_API_KEY", "ab/cd+ef=gh"):
            self.assertNotIn("ab/cd+ef=gh", self.redact("failed for ab/cd+ef=gh here"))
            self.assertNotIn("ab%2Fcd%2Bef%3Dgh", self.redact("url /v1?key=ab%2Fcd%2Bef%3Dgh"))

    def test_key_query_parameters_whatever_the_key(self):
        for raw in ("/v1/images:annotate?key=abc123&alt=json", "https://x/y?alt=json&key=abc123", "GET /p?KEY=abc123 HTTP/1.1", "?key=abc123"):
            out = self.redact(raw)
            self.assertNotIn("abc123", out, raw)
            self.assertIn("key=***", out.lower(), raw)

    def test_google_style_keys_even_when_not_configured(self):
        with mock.patch("app.config.Config.GOOGLE_VISION_API_KEY", ""):
            self.assertNotIn(GOOGLE_STYLE_KEY, self.redact(f"oops {GOOGLE_STYLE_KEY} oops"))

    def test_ordinary_diagnostics_survive(self):
        text = "HTTPConnectionPool(host='127.0.0.1', port=9): Max retries exceeded with url: /v1/images:annotate (Caused by ConnectTimeoutError)"
        self.assertEqual(self.redact(text), text)
        self.assertEqual(self.redact(None), "None")
        self.assertIn("boom", self.redact(RuntimeError("boom")))


class LibraryDebugLogging(_Base):
    def test_the_http_library_debug_log_never_prints_the_key(self):
        from app.services import cloud_ocr_service as c
        logger = logging.getLogger("urllib3.connectionpool")
        previous = logger.level
        logger.setLevel(logging.DEBUG)
        self.addCleanup(logger.setLevel, previous)
        with _Server("ok") as server:
            self.endpoint(server.url)
            with self.assertLogs("urllib3.connectionpool", level="DEBUG") as captured:
                c.extract_words(self.png, "png")
        text = _everything(captured.records)
        self.assertIn("POST /v1/images:annotate", text)     # the request line really was logged (so this test means something)
        self.assert_no_key(text, "urllib3 debug log")


class FallbackAndRouteBehaviour(_Base):
    def test_the_fallback_still_happens_and_its_log_is_clean(self):
        from app.services import ocr_service
        self.endpoint(_closed_port_url())
        easy = {"text": "", "lines": [], "confidence": 0.0, "readable": False, "provider": "easyocr"}
        with mock.patch("app.config.Config.OCR_PROVIDER", "auto"), mock.patch.object(ocr_service, "extract_text_easyocr", return_value=dict(easy)), \
             self.assertLogs(ocr_service.logger, level="ERROR") as captured:
            result = ocr_service.extract_text(self.png, "png")
        self.assertEqual((result["provider"], result.get("fallback")), ("easyocr", True))      # fallback preserved
        text = _everything(captured.records)
        self.assertIn("Cloud OCR failed", text)
        self.assertIn("could not reach Vision", text)                                        # still diagnosable
        self.assert_no_key(text, "fallback log")

    def _upload(self, provider):
        from flask_jwt_extended import create_access_token
        accounts = helpers.TempAccounts()
        self.addCleanup(accounts.cleanup)
        with self.app.app_context():
            uid = accounts.user(allergies=[])
            headers = {"Authorization": f"Bearer {create_access_token(identity=str(uid))}"}
        buf = io.BytesIO()
        Image.new("RGB", (40, 40), "white").save(buf, "PNG")
        buf.seek(0)
        with mock.patch("app.config.Config.OCR_PROVIDER", provider), self.assertLogs(self.app.logger, level="ERROR") as captured:
            response = self.app.test_client().post("/api/prescriptions/upload", headers=headers, data={"file": (buf, "rx.png")}, content_type="multipart/form-data")
        return response, captured

    def test_a_pinned_cloud_failure_returns_no_key_and_logs_no_key(self):
        self.endpoint(_closed_port_url())
        response, captured = self._upload("cloud")
        self.assertEqual(response.status_code, 500)
        body = response.get_data(as_text=True)
        self.assert_no_key(body, "API error response")
        self.assertIn("could not reach Vision", json.loads(body)["details"])                  # still useful to the caller
        self.assert_no_key(_everything(captured.records), "server log")

    def test_the_error_response_redacts_even_an_unexpected_exception(self):
        # defence in depth: whatever raised, the route must not hand a key to the client
        with mock.patch("app.routes.prescriptions.extract_text", side_effect=RuntimeError(f"surprise ?key={FAKE_KEY} and {GOOGLE_STYLE_KEY}")):
            response, captured = self._upload("auto")
        self.assertEqual(response.status_code, 500)
        self.assert_no_key(response.get_data(as_text=True), "API error response")
        self.assertIn("surprise", json.loads(response.get_data(as_text=True))["details"])      # still informative
        logged = _everything(captured.records)
        self.assertIn("surprise", logged)                                                       # message and traceback are still logged
        self.assertIn("Traceback", logged)
        self.assert_no_key(logged, "server log")


if __name__ == "__main__":
    unittest.main()
