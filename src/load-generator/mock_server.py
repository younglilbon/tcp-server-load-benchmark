import json
import struct
from socketserver import BaseRequestHandler, ThreadingTCPServer

MAX_FRAME = 1024 * 1024


def recv_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise EOFError("Connection closed")
        data.extend(chunk)
    return bytes(data)


class EchoHandler(BaseRequestHandler):
    def handle(self):
        self.request.settimeout(30)
        try:
            while True:
                n = struct.unpack("!I", recv_exact(self.request, 4))[0]
                if not 0 < n <= MAX_FRAME:
                    return
                request = json.loads(recv_exact(self.request, n).decode("utf-8"))
                if not isinstance(request, dict) or not all(
                    key in request for key in ("requestId", "timestamp", "payload")
                ):
                    return
                response = {"requestId": request["requestId"], "status": "OK",
                            "payload": request["payload"]}
                body = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                if not 0 < len(body) <= MAX_FRAME:
                    return
                self.request.sendall(struct.pack("!I", len(body)) + body)
        except (EOFError, OSError, ValueError, UnicodeError):
            return


class EchoServer(ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 128


if __name__ == "__main__":
    with EchoServer(("127.0.0.1", 19000), EchoHandler) as server:
        print("Mock server listening on 127.0.0.1:19000", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
