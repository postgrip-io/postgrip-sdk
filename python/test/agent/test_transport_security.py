from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest

from postgrip.agent import Client, Connection


@contextmanager
def serve(handler: type[BaseHTTPRequestHandler]):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


class TransportSecurityTests(unittest.TestCase):
    def test_http_requires_explicit_insecure_development(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            Connection("http://agent.example.test")

        connection = Connection("http://agent.example.test", insecure_development=True)
        self.assertEqual(connection.address, "http://agent.example.test")

    def test_management_token_is_not_forwarded_across_redirect_origins(self) -> None:
        source_authorizations: list[str | None] = []
        target_authorizations: list[str | None] = []

        class TargetHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                target_authorizations.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"[]")

            def do_POST(self) -> None:
                target_authorizations.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"id":"workspace-1"}')

            def log_message(self, _format: str, *_args: object) -> None:
                return

        with serve(TargetHandler) as target_url:
            class SourceHandler(BaseHTTPRequestHandler):
                def _redirect(self, status: int) -> None:
                    source_authorizations.append(self.headers.get("Authorization"))
                    self.send_response(status)
                    self.send_header("Location", target_url)
                    self.end_headers()

                def do_GET(self) -> None:
                    self._redirect(302)

                def do_POST(self) -> None:
                    self._redirect(307)

                def log_message(self, _format: str, *_args: object) -> None:
                    return

            with serve(SourceHandler) as source_url:
                connection = Connection(
                    source_url,
                    auth_token="opaque-management-token",
                    insecure_development=True,
                )
                with self.assertRaises(RuntimeError):
                    connection.list_namespaces()
                with self.assertRaises(RuntimeError):
                    Client(connection).sandbox.upload_workspace(b"archive")

        self.assertEqual(
            source_authorizations,
            ["Bearer opaque-management-token", "Bearer opaque-management-token"],
        )
        self.assertEqual(target_authorizations, [])

    def test_same_origin_redirect_remains_supported(self) -> None:
        authorizations: list[str | None] = []

        class SameOriginHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                authorizations.append(self.headers.get("Authorization"))
                if self.path == "/api/v1/namespaces":
                    self.send_response(302)
                    self.send_header("Location", "/redirected")
                    self.end_headers()
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"[]")

            def log_message(self, _format: str, *_args: object) -> None:
                return

        with serve(SameOriginHandler) as base_url:
            connection = Connection(
                base_url,
                auth_token="opaque-management-token",
                insecure_development=True,
            )
            self.assertEqual(connection.list_namespaces(), [])

        self.assertEqual(
            authorizations,
            ["Bearer opaque-management-token", "Bearer opaque-management-token"],
        )

    def test_response_body_is_bounded(self) -> None:
        class OversizedHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"x" * ((40 << 20) + 1))

            def log_message(self, _format: str, *_args: object) -> None:
                return

        with serve(OversizedHandler) as base_url:
            connection = Connection(base_url, insecure_development=True)
            with self.assertRaisesRegex(RuntimeError, "too large"):
                connection.list_namespaces()

    def test_workflow_history_follows_stable_pages(self) -> None:
        requests: list[str] = []

        class HistoryHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                requests.append(self.path)
                self.send_response(200)
                self.end_headers()
                if "cursor=next-page" in self.path:
                    self.wfile.write(b'{"items":[{"id":"event-2"}]}')
                else:
                    self.wfile.write(b'{"items":[{"id":"event-1"}],"nextCursor":"next-page"}')

            def log_message(self, _format: str, *_args: object) -> None:
                return

        with serve(HistoryHandler) as base_url:
            connection = Connection(base_url, insecure_development=True)
            self.assertEqual(len(connection.get_workflow_history("workflow-1")), 2)

        self.assertEqual(len(requests), 2)
        self.assertIn("limit=500", requests[0])
        self.assertIn("cursor=next-page", requests[1])


if __name__ == "__main__":
    unittest.main()
