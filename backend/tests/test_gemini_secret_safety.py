"""
The Gemini key travels as a "?key=..." query parameter (like the Vision key), so a network failure's exception text,
a chained traceback, an upstream error body that echoes it, or the HTTP library's debug log could all expose it.
These tests use a FAKE key and a local fake Gemini server (nothing leaves the machine) and check that the key never
appears in the exception text, the traceback, the log, or the explain endpoint's response - while the explainer keeps
behaving as before (a failed generation falls back to the record-based explanation, and never raises).
"""
import json
import logging
import socket
import threading
import traceback
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from tests import helpers

FAKE_KEY = "FAKE-GEMINI-KEY-0987654321zyxwvu"
GOOGLE_STYLE_KEY = "AIzaSyFAKE9876543210zyxwvutsrqponmlkj"
MEDICINE = {"medicine_name": "Dolo 650 Tablet", "composition": "Paracetamol (650mg)", "form": "Tablet", "strength": "650mg",
            "manufacturer": "Micro Labs Ltd", "pack_size": "strip of 15 tablets", "primary_salt": "Paracetamol", "secondary_salt": None,
            "price": 34.27, "is_discontinued": 0, "release_type": None}


class _Gemini(BaseHTTPRequestHandler):
    mode = "ok"

    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        status, body = 200, {"candidates": [{"content": {"parts": [{"text": "Paracetamol is a pain reliever and fever reducer."}]}}]}
        if self.mode == "http_error":      # an upstream that echoes the key back in its error body
            status, body = 400, {"error": {"message": f"API key not valid: {FAKE_KEY} (request {self.path})"}}
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class _Server:
    def __init__(self, mode):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), type("H", (_Gemini,), {"mode": mode}))
        self.endpoint = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1beta"

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def _closed_port_endpoint():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}/v1beta"


def _everything(records):
    fmt = logging.Formatter("%(name)s %(levelname)s %(message)s")
    return "\n".join(fmt.format(r) for r in records)


class _Base(unittest.TestCase):
    def setUp(self):
        self.app = helpers.get_app()
        from app.services import medicine_explainer_service as svc
        self.svc = svc
        for patcher in (mock.patch("app.config.Config.GEMINI_API_KEY", FAKE_KEY), mock.patch("app.config.Config.GEMINI_MODEL", "fake-model"),
                        mock.patch("app.config.Config.LLM_TIMEOUT_SECONDS", 2)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def endpoint(self, url):
        patcher = mock.patch("app.config.Config.GEMINI_ENDPOINT", url)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_no_key(self, text, where=""):
        for secret in (FAKE_KEY, "key=FAKE", GOOGLE_STYLE_KEY):
            self.assertNotIn(secret, text, f"{where}: leaked {secret!r}")


class ExceptionsAndTracebacks(_Base):
    def failure(self):
        with self.assertRaises(RuntimeError) as ctx:
            self.svc._ask_gemini(MEDICINE)
        return ctx.exception

    def test_a_network_failure_message_has_no_key_but_keeps_the_diagnosis(self):
        self.endpoint(_closed_port_endpoint())
        text = str(self.failure())
        self.assert_no_key(text, "message")
        self.assertIn("could not reach Gemini", text)
        self.assertIn("127.0.0.1", text)
        self.assertRegex(text, r"ConnectionError|ConnectTimeout|Timeout")

    def test_the_original_exception_is_not_chained_onto_it(self):
        self.endpoint(_closed_port_endpoint())
        exc = self.failure()
        self.assertIsNone(exc.__cause__)                       # "from None": a chained traceback printed the original, key included
        self.assert_no_key("".join(traceback.format_exception(exc)), "traceback")

    def test_an_upstream_error_body_that_echoes_the_key_is_redacted(self):
        with _Server("http_error") as server:
            self.endpoint(server.endpoint)
            text = str(self.failure())
        self.assert_no_key(text, "HTTP error")
        self.assertIn("Gemini HTTP 400", text)
        self.assertIn("***", text)

    def test_the_other_failure_messages_are_unchanged(self):
        with _Server("ok") as server:
            self.endpoint(server.endpoint)
            with mock.patch.object(self.svc.requests, "post") as post:
                post.return_value = mock.Mock(status_code=200, json=lambda: {"candidates": []})
                with self.assertRaisesRegex(RuntimeError, "Gemini returned no candidates"):
                    self.svc._ask_gemini(MEDICINE)
                post.return_value = mock.Mock(status_code=200, json=lambda: {"candidates": [{"content": {"parts": [{"text": "  "}]}}]})
                with self.assertRaisesRegex(RuntimeError, "Gemini returned an empty explanation"):
                    self.svc._ask_gemini(MEDICINE)


class RedactionHelper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.get_app()
        from app.services import medicine_explainer_service as svc
        cls.redact = staticmethod(svc._redact)

    def test_the_configured_gemini_key_in_any_form(self):
        with mock.patch("app.config.Config.GEMINI_API_KEY", "ab/cd+ef=gh"):
            self.assertNotIn("ab/cd+ef=gh", self.redact("failed for ab/cd+ef=gh here"))
            self.assertNotIn("ab%2Fcd%2Bef%3Dgh", self.redact("url /v1?x=1&k=ab%2Fcd%2Bef%3Dgh"))

    def test_key_parameters_and_google_style_keys_even_without_a_configured_key(self):
        with mock.patch("app.config.Config.GEMINI_API_KEY", ""):
            self.assertNotIn("abc123", self.redact("POST /v1beta/models/m:generateContent?key=abc123 HTTP/1.1"))
            self.assertNotIn(GOOGLE_STYLE_KEY, self.redact(f"oops {GOOGLE_STYLE_KEY}"))

    def test_ordinary_diagnostics_survive(self):
        text = "HTTPSConnectionPool(host='generativelanguage.googleapis.com', port=443): Read timed out. (read timeout=30)"
        self.assertEqual(self.redact(text), text)


class ExplainBehaviour(_Base):
    """explain() as the app uses it: it never raises, never exposes the key, and still explains the medicine."""

    def explain_with_failure(self, mode, closed_port=False):
        if closed_port:
            self.endpoint(_closed_port_endpoint())
            with self.assertLogs(self.svc.logger, level="ERROR") as captured:
                return self.svc.explain(MEDICINE), captured
        with _Server(mode) as server:
            self.endpoint(server.endpoint)
            with self.assertLogs(self.svc.logger, level="ERROR") as captured:
                return self.svc.explain(MEDICINE), captured

    def test_a_network_failure_falls_back_and_logs_without_the_key(self):
        result, captured = self.explain_with_failure("ok", closed_port=True)
        self.assertEqual(result["source"], "database")                       # fallback preserved
        self.assertIn("Dolo 650", result["text"])
        logged = _everything(captured.records)
        self.assertIn("Gemini explanation failed", logged)
        self.assertIn("could not reach Gemini", logged)                      # still diagnosable
        self.assertIn("Traceback", logged)
        self.assert_no_key(logged, "server log")
        self.assert_no_key(json.dumps(result), "returned result")

    def test_an_error_body_that_echoes_the_key_falls_back_and_logs_without_it(self):
        result, captured = self.explain_with_failure("http_error")
        self.assertEqual(result["source"], "database")
        logged = _everything(captured.records)
        self.assertIn("Gemini HTTP 400", logged)
        self.assert_no_key(logged, "server log")
        self.assert_no_key(json.dumps(result), "returned result")

    def test_an_unexpected_exception_containing_the_key_is_redacted_in_the_log(self):
        with mock.patch.object(self.svc, "_ask_gemini", side_effect=RuntimeError(f"surprise ?key={FAKE_KEY} {GOOGLE_STYLE_KEY}")), \
             self.assertLogs(self.svc.logger, level="ERROR") as captured:
            result = self.svc.explain(MEDICINE)
        self.assertEqual(result["source"], "database")
        logged = _everything(captured.records)
        self.assertIn("surprise", logged)
        self.assertIn("Traceback", logged)
        self.assert_no_key(logged, "server log")

    def test_the_fallback_text_is_identical_with_and_without_a_failing_key(self):
        failed, _ = self.explain_with_failure("http_error")
        with mock.patch("app.config.Config.GEMINI_API_KEY", ""):
            with mock.patch.object(self.svc.requests, "post", side_effect=AssertionError("no network call without a key")):
                plain = self.svc.explain(MEDICINE)
        self.assertEqual(failed, plain)                                       # same record-based explanation either way
        self.assertEqual(plain["source"], "database")

    def test_a_successful_generation_is_unchanged(self):
        with _Server("ok") as server:
            self.endpoint(server.endpoint)
            result = self.svc.explain(MEDICINE)
        self.assertEqual(result["source"], "gemini")
        self.assertEqual(result["text"], "Paracetamol is a pain reliever and fever reducer.")
        self.assertEqual(result["disclaimer"], self.svc.DISCLAIMER)

    def test_the_http_library_debug_log_never_prints_the_key(self):
        logger = logging.getLogger("urllib3.connectionpool")
        previous = logger.level
        logger.setLevel(logging.DEBUG)
        self.addCleanup(logger.setLevel, previous)
        with _Server("ok") as server:
            self.endpoint(server.endpoint)
            with self.assertLogs("urllib3.connectionpool", level="DEBUG") as captured:
                self.svc.explain(MEDICINE)
        text = _everything(captured.records)
        self.assertIn("POST /v1beta/models/fake-model:generateContent", text)   # the request line really was logged
        self.assert_no_key(text, "urllib3 debug log")


class ExplainEndpoint(_Base):
    def test_the_api_response_never_contains_the_key_when_generation_fails(self):
        from flask_jwt_extended import create_access_token
        from app.db import get_connection
        accounts = helpers.TempAccounts()
        self.addCleanup(accounts.cleanup)
        with self.app.app_context():
            uid = accounts.user(allergies=[])
            headers = {"Authorization": f"Bearer {create_access_token(identity=str(uid))}"}
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT medicine_id FROM Medicines WHERE medicine_name = 'Dolo 650 Tablet' LIMIT 1")
            medicine_id = cur.fetchone()[0]
            cur.close()
            conn.close()
        for mode, closed in (("http_error", False), ("ok", True)):
            with self.subTest(mode=mode, closed_port=closed):
                if closed:
                    self.endpoint(_closed_port_endpoint())
                    server = None
                else:
                    server = _Server(mode).__enter__()
                    self.endpoint(server.endpoint)
                try:
                    with self.assertLogs(self.svc.logger, level="ERROR") as captured:
                        response = self.app.test_client().get(f"/api/medicines/{medicine_id}/explain", headers=headers)
                finally:
                    if server:
                        server.__exit__(None, None, None)
                self.assertEqual(response.status_code, 200)
                body = response.get_data(as_text=True)
                self.assert_no_key(body, "API response")
                self.assertEqual(json.loads(body)["source"], "database")
                self.assert_no_key(_everything(captured.records), "server log")


if __name__ == "__main__":
    unittest.main()
