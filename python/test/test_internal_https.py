from __future__ import annotations

import datetime
import ipaddress
import json
import ssl
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import HTTPSHandler, build_opener

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from postgrip._internal.http import CancellationAwareHTTPSHandler
from postgrip.worker import WorkerClient


def _self_signed_localhost(directory: Path) -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path = directory / "cert.pem"
    key_path = directory / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return cert_path, key_path


class _JSONHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({"status": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class CancellationAwareHTTPSTest(unittest.TestCase):
    """The cancellation-aware HTTPS handler must work on every supported Python.

    Python 3.12 removed ``HTTPSConnection``'s ``check_hostname`` argument; the
    handler once passed it unconditionally, so every HTTPS request failed.
    """

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        cert_path, key_path = _self_signed_localhost(Path(directory.name))
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(cert_path, key_path)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _JSONHandler)
        self.server.socket = server_context.wrap_socket(self.server.socket, server_side=True)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.client_context = ssl.create_default_context(cafile=str(cert_path))
        self.base_url = f"https://127.0.0.1:{self.server.server_address[1]}"

    def test_handler_completes_an_https_request(self) -> None:
        opener = build_opener(CancellationAwareHTTPSHandler(context=self.client_context))
        with opener.open(f"{self.base_url}/health", timeout=5) as response:
            self.assertEqual(json.loads(response.read()), {"status": "ok"})

    def test_handler_keeps_hostname_verification(self) -> None:
        opener = build_opener(CancellationAwareHTTPSHandler(context=ssl.create_default_context()))
        with self.assertRaises(Exception):
            opener.open(f"{self.base_url}/health", timeout=5)

    def test_worker_client_completes_an_https_request(self) -> None:
        client = WorkerClient(
            base_url=self.base_url,
            token="pgt_test-token",
            opener=build_opener(HTTPSHandler(context=self.client_context)),
        )
        self.assertEqual(client.health(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
