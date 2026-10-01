"""Generuje samopodpisany certyfikat TLS dla lokalnego nginx.

    py deploy/generate_ssl.py            # tworzy, jeśli nie istnieje
    py deploy/generate_ssl.py --force    # nadpisuje istniejący

Pliki trafiają do deploy/nginx/ssl/ (wykluczone z gita i z obrazu Dockera).
Używa lokalnego openssl, a gdy go brak — kontenera alpine/openssl, więc na
Windowsie wystarczy Docker Desktop.

Certyfikat samopodpisany nadaje się wyłącznie do uruchomień lokalnych
i demonstracji — przeglądarka pokaże ostrzeżenie. Na produkcji certyfikat
powinien pochodzić z zaufanego urzędu (np. Let's Encrypt).
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SSL_DIR = os.path.join(ROOT, "deploy", "nginx", "ssl")

# Nowoczesne przeglądarki ignorują pole CN i wymagają subjectAltName.
ARGUMENTY = [
    "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "365",
    "-subj", "/C=PL/O=Helpdesk_AI/CN=localhost",
    "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
]


def polecenie():
    if shutil.which("openssl"):
        return ["openssl", *ARGUMENTY,
                "-keyout", os.path.join(SSL_DIR, "key.pem"),
                "-out", os.path.join(SSL_DIR, "cert.pem")]
    if shutil.which("docker"):
        return ["docker", "run", "--rm", "-v", f"{SSL_DIR}:/ssl", "alpine/openssl",
                *ARGUMENTY, "-keyout", "/ssl/key.pem", "-out", "/ssl/cert.pem"]
    return None


def main():
    os.makedirs(SSL_DIR, exist_ok=True)
    istnieje = all(os.path.exists(os.path.join(SSL_DIR, f)) for f in ("key.pem", "cert.pem"))
    if istnieje and "--force" not in sys.argv:
        print(f"Certyfikat już istnieje w {SSL_DIR} (--force, aby nadpisać).")
        return 0

    cmd = polecenie()
    if cmd is None:
        print("Brak openssl i dockera — zainstaluj jedno z nich.", file=sys.stderr)
        return 1

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        print("Nie udało się wygenerować certyfikatu.", file=sys.stderr)
        return 1

    print(f"Wygenerowano certyfikat w {SSL_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
