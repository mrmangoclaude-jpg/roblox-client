"""Unix sockets or authenticated Windows loopback sockets for local consoles."""
import json
import os
from pathlib import Path
import secrets
import socket
import stat
from platform_files import read_private, open_nofollow


def endpoint(path):
    value = json.loads(read_private(path, 1024))
    if (set(value) != {'port', 'token'} or type(value['port']) is not int
            or not 1 <= value['port'] <= 65535 or not isinstance(value['token'], str)
            or len(value['token']) != 64 or any(c not in '0123456789abcdef' for c in value['token'])):
        raise ValueError('Invalid local console endpoint')
    return value


def connect(path, timeout=8):
    if os.name == 'nt':
        value = endpoint(path)
        connection = socket.create_connection(('127.0.0.1', value['port']), timeout)
        return connection, value['token']
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout); connection.connect(str(path))
        return connection, None
    except BaseException:
        connection.close(); raise


def probe(path, timeout=.2):
    try:
        connection, _ = connect(path, timeout)
    except TimeoutError as error:
        if os.name == 'nt':
            raise ConnectionRefusedError('Windows loopback listener is not active') from error
        raise
    connection.close()


def listen(path):
    path = Path(path)
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if os.name != 'nt' and (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()):
            raise ValueError('Console path is not an owned socket')
        try: probe(path)
        except ConnectionRefusedError: path.unlink()
        else: raise ValueError('A client console is already running')
    token = secrets.token_hex(32) if os.name == 'nt' else None
    server = socket.socket(socket.AF_INET if token else socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(('127.0.0.1', 0) if token else str(path))
        server.listen(4)
        if token:
            fd = open_nofollow(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, 'w') as output:
                json.dump({'port':server.getsockname()[1], 'token':token}, output)
        else: path.chmod(0o600)
        server.setblocking(False)
        return server, token
    except BaseException:
        server.close(); raise
