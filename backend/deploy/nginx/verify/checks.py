"""Checks run by run.sh against a real nginx (NGINX_PORT) and gunicorn (APP_PORT). Phase name = argv[1]."""
import http.client
import os
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import uuid

NGINX, APP = int(os.environ["NGINX_PORT"]), int(os.environ["APP_PORT"])
DB, PIDFILE = os.environ["CHECK_DB"], os.environ["GUNICORN_PID_FILE"]
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def psql(sql):
    out = subprocess.run(["psql", "-d", DB, "-Atc", sql], capture_output=True, text=True, check=True)
    return out.stdout.strip()


class Client:
    """Minimal browser: cookies, CSRF, a chosen SOURCE address (127.0.0.N), optional forged headers."""

    def __init__(self, source, port=NGINX, forged_xff=None):
        self.source, self.port, self.cookies, self.forged = source, port, {}, forged_xff

    def request(self, method, path, body=None, headers=None, timeout=20):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout, source_address=(self.source, 0))
        h = {"Host": f"127.0.0.1:{self.port}", "Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items())}
        if self.forged:
            h["X-Forwarded-For"] = self.forged
            h["X-Real-IP"] = self.forged
            h["Forwarded"] = f"for={self.forged}"
        h.update(headers or {})
        try:
            conn.request(method, path, body=body, headers=h)
            r = conn.getresponse()
            data = r.read()
        finally:
            conn.close()
        for c in r.headers.get_all("Set-Cookie") or []:
            k, _, rest = c.partition("=")
            self.cookies[k] = rest.split(";")[0]
        return r.status, r, data

    def csrf(self, path="/accounts/login/"):
        status, _, data = self.request("GET", path)
        return re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', data).group(1).decode()

    def login(self, user, password="Namuna-Parol-12345"):
        token = self.csrf()
        body = urllib.parse.urlencode({"username": user, "password": password, "csrfmiddlewaretoken": token})
        return self.request("POST", "/accounts/login/", body, {"Content-Type": "application/x-www-form-urlencoded"})[0]

    def upload(self, title, filename, content):
        token = self.csrf("/portal/documents/new/")
        cat = psql("select id from documents_documentcategory order by name limit 1")
        b = "----" + uuid.uuid4().hex
        parts = []
        for k, v in (("csrfmiddlewaretoken", token), ("title", title), ("category", cat), ("access_level", "general")):
            parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: text/plain\r\n\r\n'.encode() + content + b"\r\n")
        parts.append(f"--{b}--\r\n".encode())
        return self.request("POST", "/portal/documents/new/", b"".join(parts), {"Content-Type": f"multipart/form-data; boundary={b}"}, timeout=60)


def last_failed_login_ips(n):
    rows = psql(f"select coalesce(ip::text,'') from audit_auditlog where action='login_failed' order by at desc limit {n}")
    return [r.split("/")[0] for r in rows.splitlines()]


def failed_login(client, user="nobody"):
    return client.login(user, "definitely-wrong-password")


def reset_state():
    psql("delete from accounts_throttlestate")


def phase_correct():
    print("PHASE correct: DJANGO_TRUSTED_PROXIES=127.0.0.1, nginx overwrites X-Forwarded-For")
    reset_state()
    # 1. via nginx the recorded address is the real client, whatever the client claims
    for src, forged in (("127.0.0.2", None), ("127.0.0.2", "203.0.113.50, 198.51.100.7"), ("127.0.0.3", "10.9.8.7")):
        failed_login(Client(src, forged_xff=forged), user=f"u{src[-1]}")
        seen = last_failed_login_ips(1)[0]
        check(f"via nginx from {src} claiming {forged or 'nothing'}: recorded {seen}", seen == src)
    # 2. direct to the app from an UNTRUSTED address with forged headers: headers ignored
    failed_login(Client("127.0.0.2", port=APP, forged_xff="203.0.113.99"), user="direct")
    seen = last_failed_login_ips(1)[0]
    check("direct to gunicorn from untrusted 127.0.0.2 with forged X-Forwarded-For: forged value ignored", seen == "127.0.0.2", seen)
    # 3. throttling uses the real address: block .2 after 20 failures, .3 and a legitimate user are unaffected
    reset_state()
    attacker = Client("127.0.0.2", forged_xff="127.0.0.3")  # also tries to blame .3
    for i in range(20):
        failed_login(attacker, user=f"guess{i}")
    check("attacker (.2) is blocked after 20 failures even with correct credentials", attacker.login("alice") == 200)
    check("a different real address (.3) can still sign in (not blamed by the forged header)", Client("127.0.0.3").login("alice") == 302)
    check("two users behind the same address are counted together (shared-IP policy)", Client("127.0.0.2").login("bob") == 200)
    # 4. headers and paths
    c = Client("127.0.0.4")
    status, r, _ = c.request("GET", "/accounts/login/")
    check("Server header does not reveal the nginx version", "nginx/" not in (r.headers.get("Server") or ""), r.headers.get("Server"))
    check("/private_media/ and /media/ are refused by nginx", all(c.request("GET", p)[0] == 404 for p in ("/private_media/x", "/media/x", "/private_media/")))
    # 5. uploads up to 10 MB through the whole chain (nginx -> gunicorn -> [clamd] -> private storage)
    hr = Client("127.0.0.5")
    check("hr signs in through nginx", hr.login("hrista") == 302)
    ten_mb = (b"salom dunyo\n" * 1_000_000)[: 10 * 1024 * 1024]
    t0 = time.monotonic()
    status, _, _ = hr.upload("O'n megabayt", "big.txt", ten_mb)
    check(f"upload of exactly 10 MB succeeds ({'with real clamd' if os.environ['DOC_SCAN'] == 'clamav' else 'NO antivirus'}), {time.monotonic() - t0:.1f}s", status == 302 and psql("select count(*) from documents_document where title like 'O''n%'") == "1", str(status))
    status, _, data = hr.upload("Katta", "big2.txt", ten_mb + b"x")
    check("10 MB + 1 byte: passes nginx, refused by the application's own limit", status == 200 and b"oshmasligi kerak" in data, str(status))
    status, _, data = hr.upload("Juda katta", "huge.txt", b"a" * (12 * 1024 * 1024))
    check("12 MB: refused by nginx with 413 and the static page", status == 413 and b"Fayl juda katta" in data, str(status))
    check("no document was created by the refused uploads", psql("select count(*) from documents_document where title in ('Katta','Juda katta')") == "0")


def phase_no_trusted_proxy():
    print("PHASE negative control: DJANGO_TRUSTED_PROXIES empty (the misconfiguration B-1 warns about)")
    reset_state()
    failed_login(Client("127.0.0.2"), user="x1")
    a = last_failed_login_ips(1)[0]
    failed_login(Client("127.0.0.3"), user="x2")
    b = last_failed_login_ips(1)[0]
    check("through nginx every client looks like the proxy (127.0.0.1): expected defect is visible", a == b == "127.0.0.1", f"{a}, {b}")
    for i in range(20):
        failed_login(Client("127.0.0.2"), user=f"g{i}")
    check("...so one attacker locks out EVERYONE behind nginx (this is why the setting is mandatory)", Client("127.0.0.3").login("alice") == 200)


def phase_too_broad():
    print("PHASE negative control: DJANGO_TRUSTED_PROXIES=127.0.0.0/8 (too broad)")
    reset_state()
    failed_login(Client("127.0.0.2", port=APP, forged_xff="203.0.113.77"), user="forge")
    seen = last_failed_login_ips(1)[0]
    check("a forged header from an address inside the too-broad range IS believed: expected defect is visible", seen == "203.0.113.77", seen)


def _children(pid):
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()
    return [int(p) for p in out]


def phase_upstream_failures():
    print("PHASE upstream failures (nginx proxy_read_timeout is 3s in this run)")
    c = Client("127.0.0.6")
    master = int(open(PIDFILE).read())
    pids = [master, *_children(master)]
    for p in pids:
        os.kill(p, signal.SIGSTOP)
    try:
        t0 = time.monotonic()
        status, _, data = c.request("GET", "/accounts/login/", timeout=30)
        took = time.monotonic() - t0
        check(f"hung application: nginx answers 504 after the timeout ({took:.1f}s) with the static page", status == 504 and b"vaqtincha mavjud emas" in data and 2.5 < took < 8, str(status))
    finally:
        for p in pids:
            os.kill(p, signal.SIGCONT)
    time.sleep(0.5)
    check("application recovers after the hang", Client("127.0.0.6").request("GET", "/healthz/")[0] == 200)
    os.kill(master, signal.SIGTERM)
    time.sleep(2)
    status, r, data = c.request("GET", "/accounts/login/")
    check("application down: nginx answers 502 with the static page, no upstream details", status == 502 and b"vaqtincha mavjud emas" in data and b"127.0.0.1" not in data, str(status))


if __name__ == "__main__":
    {"correct": phase_correct, "no_trusted_proxy": phase_no_trusted_proxy, "too_broad": phase_too_broad, "upstream_failures": phase_upstream_failures}[sys.argv[1]]()
    if not all(RESULTS):
        print("SOME CHECKS FAILED")
        sys.exit(1)
