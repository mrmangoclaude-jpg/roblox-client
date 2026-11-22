"""Opium network API parity using only local loopback transports."""
import base64
import hashlib
import socketserver
import struct
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import test_local_compat as compat


class NetworkOpiumTests(unittest.TestCase):
    run_script = compat.LocalCompatibilityTests.run_script

    def serve(self, server):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: (server.shutdown(), thread.join(3)))
        return server.server_address[1]

    def test_misuse_error_text_matches_real_client(self):
        self.run_script('''
local ok, e = pcall(request, nil)
assert(not ok and e == "attempt to index nil with 'Url'", tostring(e))
local ok2, e2 = pcall(request, {})
assert(not ok2 and e2 == "invalid url for http request", tostring(e2))
local ok3, e3 = pcall(httpget, nil)
assert(not ok3 and e3 == "invalid argument #1 (Instance expected, got nil)", tostring(e3))
''')

    def test_httpget_aliases_and_request_cookies_methods_and_response_shape(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.command, self.path, self.headers.get('Cookie')))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'\x00\xffHttpGet')

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                seen.append((self.command, self.headers.get('X-Test'),
                             self.headers.get('Cookie'), body))
                self.send_response(201)
                self.send_header('X-Reply', 'actual')
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        port = self.serve(ThreadingHTTPServer(('127.0.0.1', 0), Handler))
        self.run_script(f'''
local url="http://127.0.0.1:{port}"
local expected=string.char(0,255).."HttpGet"
assert(HttpGet(url)==expected)
assert(http.HttpGet(url,false)==expected)
assert(httpget(url,true)==expected)
assert(game:HttpGet(url)==expected)
local data=string.char(0,255).."payload"
local result=request({{
 Url=url,
 Method="post",
 Headers={{["X-Test"]="sent",Cookie="existing=1"}},
 Cookies={{theme="dark",session="abc"}},
 Body=data,
}})
assert(result.Success and result.StatusCode==201 and result.StatusMessage=="Created")
assert(result.Headers["x-reply"]=="actual" and result.Body==data)
assert(result.BodyBase64==nil and result.Cookies==nil)
assert(http_request==request and http.request==request)
assert(not pcall(request,{{Url=url,Method="TRACE"}}))
assert(not pcall(request,{{Url=url,Method=42}}))
''')
        self.assertEqual(seen[:4], [('GET', '/', None)] * 4)
        self.assertEqual(seen[4], ('POST', 'sent', 'existing=1; session=abc; theme=dark',
                                   b'\x00\xffpayload'))
        self.assertEqual(len(seen), 5)

    def test_websocket_connect_aliases_preserve_real_binary_echo(self):
        received = []
        errors = []
        finished = threading.Event()

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                try:
                    self.connection.settimeout(3)
                    self.rfile.readline()
                    headers = {}
                    while True:
                        line = self.rfile.readline()
                        if line == b'\r\n':
                            break
                        key, value = line.decode().split(':', 1)
                        headers[key.lower()] = value.strip()
                    accept = base64.b64encode(hashlib.sha1(
                        (headers['sec-websocket-key'] +
                         '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
                    self.wfile.write(
                        b'HTTP/1.1 101 Switching Protocols\r\n'
                        b'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                        b'Sec-WebSocket-Accept: ' + accept + b'\r\n\r\n')
                    self.wfile.flush()
                    head = self.rfile.read(2)
                    if len(head) != 2:
                        raise ValueError('missing frame')
                    size = head[1] & 127
                    if size == 126:
                        size = struct.unpack('!H', self.rfile.read(2))[0]
                    elif size == 127:
                        size = struct.unpack('!Q', self.rfile.read(8))[0]
                    if size > 131072 or not head[1] & 128:
                        raise ValueError('invalid client frame')
                    mask = self.rfile.read(4)
                    body = self.rfile.read(size)
                    body = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
                    received.append((head[0] & 15, body))
                    self.wfile.write(bytes([0x82, len(body)]) + body)
                    self.wfile.flush()
                    close = self.rfile.read(2)
                    received.append((close[0] & 15, b''))
                except Exception as error:
                    errors.append(str(error))
                finally:
                    finished.set()

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True

        port = self.serve(Server(('127.0.0.1', 0), Handler))
        self.run_script(f'''
assert(ws==WebSocket and Websocket==WebSocket and websocket==WebSocket)
assert(WebSocket.Connect==WebSocket.connect)
local socket=Websocket.Connect("ws://127.0.0.1:{port}/echo")
local got,closed
socket.OnMessage:Connect(function(data)got=data end)
socket.OnClose:Connect(function()closed=true end)
local data=string.char(0,255).."echo"
socket:Send(data,true)
for i=1,100 do if got then break end;task.wait(.005) end
assert(got==data)
socket:Close();task.wait();assert(closed)
assert(not pcall(socket.Send,socket,"after close"))
assert(not pcall(websocket.Connect,"http://127.0.0.1:{port}/not-websocket"))
''')
        self.assertTrue(finished.wait(3), 'server did not receive the close frame')
        self.assertFalse(errors)
        self.assertEqual(received[0], (2, b'\x00\xffecho'))
        self.assertEqual(received[1][0], 8)


if __name__ == '__main__':
    unittest.main()
