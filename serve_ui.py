import http.server
import socketserver

class C(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="apex-ui/dist", **kwargs)
    def end_headers(self):
        self.send_header('Permissions-Policy', 'camera=(self), microphone=(self)')
        super().end_headers()

socketserver.TCPServer(("", 8081), C).serve_forever()
