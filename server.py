
import os
import ssl
import json
import socket
import struct
import hashlib
import secrets
import threading
from pathlib import Path

HOST = "0.0.0.0"
PORT = 8091

ROOT = Path("files").resolve()
CERT = "cert/server.crt"
KEY = "cert/server.key"
CONFIG = Path("config.json")

MAX_SIZE = 100 * 1024 * 1024

ROOT.mkdir(exist_ok=True)


def load_config():
    if not CONFIG.exists():
        data = {
            "username": "sun",
            "password": secrets.token_urlsafe(24)
        }

        CONFIG.write_text(json.dumps(data, indent=4))
        print("SUN kullanıcı:", data["username"])
        print("SUN parola:", data["password"])

    return json.loads(CONFIG.read_text())


AUTH = load_config()


def recv_exact(sock, size):
    data = bytearray()

    while len(data) < size:
        chunk = sock.recv(min(65536, size - len(data)))

        if not chunk:
            raise ConnectionError("Bağlantı kesildi.")

        data.extend(chunk)

    return bytes(data)


def recv_json(sock):
    size = struct.unpack("!I", recv_exact(sock, 4))[0]

    if size > 1024 * 1024:
        raise ValueError("Mesaj çok büyük.")

    return json.loads(recv_exact(sock, size))


def send_json(sock, data):
    raw = json.dumps(data).encode()
    sock.sendall(struct.pack("!I", len(raw)))
    sock.sendall(raw)


def safe_path(name):
    name = str(name).replace("\\", "/").lstrip("/")
    target = (ROOT / name).resolve()

    if target != ROOT and ROOT not in target.parents:
        raise ValueError("Geçersiz dosya yolu.")

    return target


def handle_client(sock, address):
    print("Bağlandı:", address)

    try:
        data = recv_json(sock)

        if (
            data.get("username") != AUTH["username"]
            or data.get("password") != AUTH["password"]
        ):
            send_json(sock, {"status": 401, "message": "Yetkisiz."})
            return

        command = data.get("command", "").upper()
        path = data.get("path", "")

        if command == "PING":
            send_json(sock, {
                "status": 200,
                "message": "SUN online"
            })

        elif command == "INFO":
            send_json(sock, {
                "status": 200,
                "name": "YUNIX CO SUN",
                "version": "2.0",
                "port": PORT,
                "tls": "TLS 1.3"
            })

        elif command == "LIST":
            folder = safe_path(path)

            if not folder.is_dir():
                send_json(sock, {"status": 404})
                return

            items = []

            for item in folder.iterdir():
                items.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0
                })

            send_json(sock, {
                "status": 200,
                "items": items
            })

        elif command == "MKDIR":
            safe_path(path).mkdir(parents=True, exist_ok=True)
            send_json(sock, {"status": 200})

        elif command == "DELETE":
            target = safe_path(path)

            if target == ROOT:
                raise ValueError("Ana klasör silinemez.")

            if target.is_dir():
                target.rmdir()
            elif target.is_file():
                target.unlink()
            else:
                send_json(sock, {"status": 404})
                return

            send_json(sock, {"status": 200})

        elif command == "GET":
            target = safe_path(path)

            if not target.is_file():
                send_json(sock, {"status": 404})
                return

            digest = hashlib.sha256()

            with open(target, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    digest.update(chunk)

            size = target.stat().st_size

            send_json(sock, {
                "status": 200,
                "size": size,
                "sha256": digest.hexdigest()
            })

            with open(target, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sock.sendall(chunk)

        elif command == "PUT":
            target = safe_path(data.get("name", ""))
            size = int(data.get("size", -1))
            expected = data.get("sha256", "")

            if target == ROOT or not target.name:
                raise ValueError("Dosya adı geçersiz.")

            if not 0 <= size <= MAX_SIZE:
                raise ValueError("Dosya boyutu geçersiz.")

            if len(expected) != 64:
                raise ValueError("SHA256 geçersiz.")

            send_json(sock, {"status": 100})

            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + ".uploading")
            digest = hashlib.sha256()

            try:
                with open(temp, "wb") as f:
                    remaining = size

                    while remaining:
                        chunk = recv_exact(sock, min(65536, remaining))
                        f.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)

                if digest.hexdigest() != expected:
                    raise ValueError("SHA256 doğrulaması başarısız.")

                os.replace(temp, target)

            except Exception:
                if temp.exists():
                    temp.unlink()
                raise

            send_json(sock, {"status": 200, "message": "Yüklendi."})

        else:
            send_json(sock, {"status": 400, "message": "Bilinmeyen komut."})

    except Exception as error:
        try:
            send_json(sock, {
                "status": 500,
                "message": str(error)
            })
        except Exception:
            pass

        print("Hata:", error)

    finally:
        sock.close()


def main():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3

    context.load_cert_chain(CERT, KEY)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(20)

    print("YUNIX CO SUN PRO 2.0")
    print("Port:", PORT)
    print("TLS 1.3 aktif")

    while True:
        raw, address = server.accept()

        try:
            secure = context.wrap_socket(raw, server_side=True)

            threading.Thread(
                target=handle_client,
                args=(secure, address),
                daemon=True
            ).start()

        except Exception as error:
            print("TLS hatası:", error)
            raw.close()


if __name__ == "__main__":
    main()
                      
