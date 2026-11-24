import socket
import struct

HEADER_SIZE = 4
REQ_ID_SIZE = 8
MAX_BODY_SIZE = 65536


class ProtocolError(Exception):
    pass


def pack_message(request_id: int, payload: bytes) -> bytes:
    body_len = REQ_ID_SIZE + len(payload)
    if body_len < REQ_ID_SIZE or body_len > MAX_BODY_SIZE:
        raise ProtocolError(f"Invalid body length: {body_len}")

    header = struct.pack("!IQ", body_len, request_id)
    return header + payload


def read_exact(sock: socket.socket, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionResetError("Connection closed before receiving full frame")
        buf.extend(chunk)
    return bytes(buf)


def recv_message(sock: socket.socket) -> tuple[int, bytes]:
    raw_len = read_exact(sock, HEADER_SIZE)
    (body_len,) = struct.unpack("!I", raw_len)

    if body_len < REQ_ID_SIZE or body_len > MAX_BODY_SIZE:
        raise ProtocolError(f"Body length out of range: {body_len}")

    body = read_exact(sock, body_len)
    (request_id,) = struct.unpack("!Q", body[:REQ_ID_SIZE])
    payload = body[REQ_ID_SIZE:]
    return request_id, payload
