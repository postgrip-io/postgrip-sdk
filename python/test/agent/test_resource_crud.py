import json
import unittest
from unittest.mock import patch
from postgrip.agent import Connection


class ResourceCRUDTests(unittest.TestCase):
    def test_enrollment_auth_and_empty_label_serialization(self):
        requests = []

        class Response:
            def __init__(self):
                self._read = False

            def read(self, _size=-1):
                if self._read:
                    return b""
                self._read = True
                return b'{"id":"s/1","name":"renamed"}'

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

        def urlopen(request, timeout=None):
            requests.append((request.full_url, request.method, request.get_header("Authorization"), json.loads(request.data)))
            return Response()

        connection = Connection("http://agent.test", insecure_development=True, auth_token="pgt-management")
        with patch("postgrip.agent._connection.urlopen", urlopen):
            connection.openapi.enroll_agent({"enrollmentKey": "one-time", "agentId": "host", "signaturePublicKey": "public-key"})
            connection.openapi.update_sandbox("s/1", {"name": "renamed"})
            connection.openapi.update_sandbox("s/1", {"labels": {}})
        self.assertEqual(requests, [
            ("http://agent.test/api/v1/agent/enroll", "POST", None, {"enrollmentKey": "one-time", "agentId": "host", "signaturePublicKey": "public-key"}),
            ("http://agent.test/api/v1/sandboxes/s%2F1", "PATCH", "Bearer pgt-management", {"name": "renamed"}),
            ("http://agent.test/api/v1/sandboxes/s%2F1", "PATCH", "Bearer pgt-management", {"labels": {}}),
        ])
