"""A concurrent TCP server that echoes newline-delimited JSON requests."""

import argparse
import json
import logging
import socket
import socketserver
from typing import Any


LOGGER = logging.getLogger("tcp_server")
DEFAULT_MAX_REQUEST_BYTES = 1024 * 1024
DEFAULT_CLIENT_TIMEOUT = 30.0


class EchoRequestHandler(socketserver.StreamRequestHandler):
    """Handle newline-delimited JSON requests on one client connection."""

    def handle(self) -> None:
        self.request.settimeout(self.server.client_timeout)  # type: ignore[attr-defined]
        peer = self.client_address
        LOGGER.info("Client connected: %s:%s", *peer)

        try:
            while True:
                raw_request = self.rfile.readline(
                    self.server.max_request_bytes + 1  # type: ignore[attr-defined]
                )
                if not raw_request:
                    break

                if len(raw_request) > self.server.max_request_bytes:  # type: ignore[attr-defined]
                    self._send_error(None, "request_too_large", "Request exceeds the size limit")
                    LOGGER.warning("Rejected oversized request from %s:%s", *peer)
                    break

                if not raw_request.endswith(b"\n"):
                    LOGGER.warning("Rejected incomplete request from %s:%s", *peer)
                    break

                try:
                    request = json.loads(raw_request.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._send_error(None, "invalid_json", "Request must be valid UTF-8 JSON")
                    LOGGER.warning("Rejected invalid JSON from %s:%s", *peer)
                    continue

                if not isinstance(request, dict) or "requestId" not in request or "payload" not in request:
                    self._send_error(None, "invalid_request", "Request must contain requestId and payload")
                    LOGGER.warning("Rejected invalid request from %s:%s", *peer)
                    continue

                self._send_json(
                    {"requestId": request["requestId"], "payload": request["payload"]}
                )
        except socket.timeout:
            LOGGER.warning("Client timed out: %s:%s", *peer)
        except (BrokenPipeError, ConnectionResetError):
            LOGGER.info("Client disconnected unexpectedly: %s:%s", *peer)
        except OSError:
            LOGGER.exception("Socket error while handling client %s:%s", *peer)
        finally:
            LOGGER.info("Client disconnected: %s:%s", *peer)

    def _send_error(self, request_id: Any, code: str, message: str) -> None:
        self._send_json(
            {"requestId": request_id, "error": {"code": code, "message": message}}
        )

    def _send_json(self, response: dict[str, Any]) -> None:
        encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.wfile.write(encoded + b"\n")
        self.wfile.flush()


class ThreadedEchoServer(socketserver.ThreadingTCPServer):
    """TCP server that handles each client connection in a separate thread."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
        client_timeout: float = DEFAULT_CLIENT_TIMEOUT,
    ) -> None:
        if max_request_bytes < 1:
            raise ValueError("max_request_bytes must be positive")
        if client_timeout <= 0:
            raise ValueError("client_timeout must be positive")

        self.max_request_bytes = max_request_bytes
        self.client_timeout = client_timeout
        super().__init__(server_address, EchoRequestHandler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a newline-delimited JSON TCP echo server.")
    parser.add_argument("--host", default="127.0.0.1", help="IP address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9000, help="TCP port to bind (default: 9000)")
    parser.add_argument(
        "--max-request-bytes",
        type=int,
        default=DEFAULT_MAX_REQUEST_BYTES,
        help=f"Maximum request line size (default: {DEFAULT_MAX_REQUEST_BYTES})",
    )
    parser.add_argument(
        "--client-timeout",
        type=float,
        default=DEFAULT_CLIENT_TIMEOUT,
        help=f"Idle client timeout in seconds (default: {DEFAULT_CLIENT_TIMEOUT:g})",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args()

    try:
        with ThreadedEchoServer(
            (args.host, args.port),
            max_request_bytes=args.max_request_bytes,
            client_timeout=args.client_timeout,
        ) as server:
            LOGGER.info("TCP echo server listening on %s:%s", *server.server_address)
            server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Server stopped")
    except (OSError, ValueError) as error:
        LOGGER.error("Unable to start server: %s", error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
