# shortener.py
import http.server
import socketserver
import urllib.parse
import json
import os
import time
import threading

HOST = "0.0.0.0"  # escuta todas as interfaces
PORT = int(os.getenv("PORT", 8000))  # usa PORT do ambiente, default 8000

DB_FILE = "db.json"

# Base62 para gerar códigos curtos
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

def base62_encode(n: int) -> str:
    if n == 0:
        return ALPHABET[0]
    s = []
    base = len(ALPHABET)
    while n > 0:
        n, r = divmod(n, base)
        s.append(ALPHABET[r])
    return "".join(reversed(s))

def load_db():
    if not os.path.exists(DB_FILE):
        return {"counter": 1000, "urls": {}}  # começa em 1000 para evitar códigos muito curtos
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

DB_LOCK = threading.Lock()

class ShortenerHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.lstrip("/")
        params = urllib.parse.parse_qs(parsed.query)

        if path == "" or path == "help":
            return self.respond_text(
                "EncCurtador ativo!\n"
                "Uso:\n"
                "  /new?url=<URL>     -> cria link curto\n"
                "  /list              -> lista todos\n"
                "  /<code>            -> redireciona\n"
                "\nExemplo:\n"
                f"  http://{HOST}:{PORT}/new?url=https://wa.me/5541998694346?text=Ola,%20Quero%20Aproveitar%20o%20Desconto%20de%20Fim%20Ano\n"
            )

        if path == "new":
            url = params.get("url", [None])[0]
            if not url:
                return self.respond_text("Erro: parâmetro 'url' é obrigatório.", status=400)

            # normaliza e valida minimamente
            url = url.strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                return self.respond_text("Erro: a URL deve começar com http:// ou https://", status=400)

            with DB_LOCK:
                db = load_db()
                # evita duplicados: reaproveita código se já existir
                for code, entry in db["urls"].items():
                    if entry["url"] == url:
                        short = f"http://{HOST}:{PORT}/{code}"
                        return self.respond_text(short)

                db["counter"] += 1
                code = base62_encode(db["counter"])
                db["urls"][code] = {"url": url, "created_at": time.time(), "hits": 0}
                save_db(db)
                short = f"http://{HOST}:{PORT}/{code}"

            return self.respond_text(short)

        if path == "list":
            with DB_LOCK:
                db = load_db()
                lines = []
                for code, entry in db["urls"].items():
                    lines.append(f"{code} -> {entry['url']} (hits: {entry['hits']})")
                return self.respond_text("\n".join(lines) if lines else "Sem links ainda.")

        # tenta redirecionar
        with DB_LOCK:
            db = load_db()
            entry = db["urls"].get(path)

        if entry:
            # incrementa hits
            with DB_LOCK:
                db["urls"][path]["hits"] += 1
                save_db(db)
            self.send_response(301)
            self.send_header("Location", entry["url"])
            self.end_headers()
        else:
            self.respond_text("Código não encontrado.", status=404)

    def respond_text(self, text, status=200):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

def run():
    with socketserver.TCPServer((HOST, PORT), ShortenerHandler) as httpd:
        print(f"Servidor rodando em http://{HOST}:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    run()