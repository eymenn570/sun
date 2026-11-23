
import ssl
import hashlib
import socket
import json
import struct
import os

PORT = 8091
CERT = "sun-server.crt"


class SUNClient:

    def __init__(self, host, username, password, port=PORT):
        self.host = host
        self.port = port
        self.username = username
        self.password = password

        self.context = ssl.create_default_context(cafile=CERT)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_3
        self.context.maximum_version = ssl.TLSVersion.TLSv1_3

    def connect(self):
        raw = socket.create_connection(
            (self.host, self.port),
            timeout=15
        )

        return self.context.wrap_socket(
            raw,
            server_hostname="sun-server"
        )

    def recv_exact(self, sock, size):
        data = bytearray()

        while len(data) < size:
            chunk = sock.recv(min(65536, size - len(data)))

            if not chunk:
                raise ConnectionError("Bağlantı kesildi.")

            data.extend(chunk)

        return bytes(data)

    def send_json(self, sock, data):
        data["username"] = self.username
        data["password"] = self.password

        raw = json.dumps(data).encode()
        sock.sendall(struct.pack("!I", len(raw)))
        sock.sendall(raw)

    def recv_json(self, sock):
        size = struct.unpack(
            "!I", self.recv_exact(sock, 4)
        )[0]

        if size > 1024 * 1024:
            raise ValueError("Mesaj çok büyük.")

        return json.loads(self.recv_exact(sock, size))

    def request(self, command, path=""):
        with self.connect() as sock:
            self.send_json(sock, {
                "command": command,
                "path": path
            })

            result = self.recv_json(sock)

            if result.get("status", 500) >= 400:
                raise Exception(result.get("message", "SUN hatası"))

            return result

    def ping(self):
        return self.request("PING")

    def info(self):
        return self.request("INFO")

    def list_files(self, path=""):
        return self.request("LIST", path)

    def mkdir(self, path):
        return self.request("MKDIR", path)

    def delete(self, path):
        return self.request("DELETE", path)

    def download(self, remote, local):
        with self.connect() as sock:
            self.send_json(sock, {
                "command": "GET",
                "path": remote
            })

            result = self.recv_json(sock)

            if result.get("status") != 200:
                raise Exception("Dosya bulunamadı.")

            digest = hashlib.sha256()
            remaining = result["size"]

            try:
                with open(local, "wb") as f:
                    while remaining:
                        chunk = self.recv_exact(
                            sock, min(65536, remaining)
                        )

                        f.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)

                if digest.hexdigest() != result["sha256"]:
                    raise Exception("SHA256 hatası.")

            except Exception:
                if os.path.exists(local):
                    os.remove(local)
                raise

        return {"status": 200, "message": "İndirildi."}

    def upload(self, local, remote):
        digest = hashlib.sha256()

        with open(local, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                digest.update(chunk)

        size = os.path.getsize(local)

        with self.connect() as sock:
            self.send_json(sock, {
                "command": "PUT",
                "name": remote,
                "size": size,
                "sha256": digest.hexdigest()
            })

            result = self.recv_json(sock)

            if result.get("status") != 100:
                raise Exception(str(result))

            with open(local, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sock.sendall(chunk)

            return self.recv_json(sock)
  
