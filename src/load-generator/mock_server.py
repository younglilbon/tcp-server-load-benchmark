from socketserver import StreamRequestHandler, ThreadingTCPServer


class EchoHandler(StreamRequestHandler):
    def handle(self):
        try:
            for line in self.rfile:
                if not line.endswith(b"\n"):
                    return
                self.wfile.write(line)
        except (ConnectionResetError, BrokenPipeError):
            return


class EchoServer(ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with EchoServer(("127.0.0.1", 19000), EchoHandler) as server:
        print("Echo server đang nghe tại 127.0.0.1:19000", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass