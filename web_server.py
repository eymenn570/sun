
from flask import Flask, request, jsonify, send_file
from sun_client import SUNClient
from pathlib import Path
from urllib.parse import urlparse
from werkzeug.utils import secure_filename
import tempfile
import os

app = Flask(__name__, static_folder="web", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

client = None
TEMP_DIR = Path(tempfile.mkdtemp(prefix="sun-browser-"))


@app.get("/")
def home():
    return app.send_static_file("index.html")


@app.errorhandler(Exception)
def handle_error(error):
    if isinstance(error, HTTPException):
        return jsonify({"error": str(error)}), error.code
    return jsonify({"error": str(error)}), 400


from werkzeug.exceptions import HTTPException


@app.post("/api/connect")
def connect():
    global client

    data = request.get_json()
    address = data.get("address", "")
    parsed = urlparse(address)

    if parsed.scheme != "sun" or not parsed.hostname:
        return jsonify({"error": "SUN adresi geçersiz."}), 400

    username = data.get("username", "")
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Kullanıcı adı ve parola gerekli."}), 400

    client = SUNClient(
        parsed.hostname,
        username,
        password,
        parsed.port or 8091
    )

    return jsonify(client.ping())


def get_client():
    if client is None:
        raise Exception("Önce SUN sunucusuna bağlan.")

    return client


@app.get("/api/list")
def list_files():
    path = request.args.get("path", "")
    result = get_client().list_files(path)
    return jsonify(result)


@app.post("/api/mkdir")
def mkdir():
    data = request.get_json()
    return jsonify(get_client().mkdir(data["path"]))


@app.post("/api/upload")
def upload():
    file = request.files.get("file")

    if not file:
        return jsonify({"error": "Dosya seçilmedi."}), 400

    folder = request.form.get("path", "")
    filename = secure_filename(file.filename)

    if not filename:
        return jsonify({"error": "Dosya adı geçersiz."}), 400

    temp_path = TEMP_DIR / filename

    try:
        file.save(temp_path)

        remote = "/".join(
            part for part in (folder, filename) if part
        )

        result = get_client().upload(str(temp_path), remote)
        return jsonify(result)

    finally:
        if temp_path.exists():
            temp_path.unlink()


@app.get("/api/download")
def download():
    remote = request.args.get("path", "")
    filename = Path(remote).name

    fd, local = tempfile.mkstemp(
        prefix="sun-download-",
        dir=TEMP_DIR
    )
    os.close(fd)

    try:
        get_client().download(remote, local)

        response = send_file(
            local,
            as_attachment=True,
            download_name=filename
        )

        response.call_on_close(
            lambda: os.path.exists(local) and os.remove(local)
        )

        return response

    except Exception:
        if os.path.exists(local):
            os.remove(local)
        raise


if __name__ == "__main__":
    print("SUN Browser 2.0")
    print("http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
      
