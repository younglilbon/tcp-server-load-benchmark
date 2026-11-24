import json
import socket
import threading
import unittest

from src.server.server import ThreadedEchoServer


class EchoServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadedEchoServer(("127.0.0.1", 0), client_timeout=1)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def connect(self) -> socket.socket:
        client = socket.create_connection(self.server.server_address, timeout=2)
        client.settimeout(2)
        return client

    @staticmethod
    def read_response(reader: socket.SocketIO) -> dict:
        response = reader.readline()
        if not response:
            raise AssertionError("Server closed the connection without a response")
        return json.loads(response.decode("utf-8"))

    def test_echoes_request_id_and_payload_without_changing_payload(self) -> None:
        request = {"requestId": "vn-1", "payload": {"text": "xin chào", "values": [1, True]}}

        with self.connect() as client:
            reader = client.makefile("rb")
            client.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n")
            self.assertEqual(self.read_response(reader), request)
            reader.close()

    def test_handles_multiple_requests_on_one_connection(self) -> None:
        requests = [
            {"requestId": 1, "payload": "first"},
            {"requestId": 2, "payload": "second"},
        ]

        with self.connect() as client:
            reader = client.makefile("rb")
            client.sendall(b"".join(json.dumps(item).encode("utf-8") + b"\n" for item in requests))
            self.assertEqual([self.read_response(reader), self.read_response(reader)], requests)
            reader.close()

    def test_reports_invalid_json_and_continues_serving_connection(self) -> None:
        with self.connect() as client:
            reader = client.makefile("rb")
            client.sendall(
                b"{not-json}\n"
                + json.dumps({"requestId": "next", "payload": "ok"}).encode("utf-8")
                + b"\n"
            )
            error = self.read_response(reader)
            self.assertEqual(error["error"]["code"], "invalid_json")
            self.assertEqual(self.read_response(reader), {"requestId": "next", "payload": "ok"})
            reader.close()

    def test_rejects_request_missing_required_fields(self) -> None:
        with self.connect() as client:
            reader = client.makefile("rb")
            client.sendall(b'{"requestId":"missing-payload"}\n')
            response = self.read_response(reader)
            self.assertEqual(response["error"]["code"], "invalid_request")
            reader.close()

    def test_rejects_oversized_request(self) -> None:
        self.server.max_request_bytes = 16
        with self.connect() as client:
            reader = client.makefile("rb")
            client.sendall(b'{"requestId":1,"payload":"too long"}\n')
            response = self.read_response(reader)
            self.assertEqual(response["error"]["code"], "request_too_large")
            reader.close()


if __name__ == "__main__":
    unittest.main()
