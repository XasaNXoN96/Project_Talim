#!/usr/bin/env python3
"""Black-box acceptance check of a deployed instance, run from ANOTHER machine (the operator's laptop or a CI host), over the public address.
Usage: smoke_remote.py https://staging-host [--admin-path gate-xyz/] [--insecure-self-signed]
--insecure-self-signed turns certificate verification OFF and exists only for the sandbox rehearsal; without it a certificate that does not
validate against the system trust store (wrong name, expired, unknown CA, missing intermediate) is a FAIL - that is the point of the check.
Reads nothing secret, sends no credentials, writes nothing. Exit 0 = all PASS."""
import argparse
import http.client
import re
import ssl
import sys
import urllib.parse

R = []


def check(name, ok, detail=""):
    R.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def request(base, path, insecure, method="GET", headers=None, plain_http_port=None):
    u = urllib.parse.urlsplit(base)
    if plain_http_port is not None:
        conn = http.client.HTTPConnection(u.hostname, plain_http_port, timeout=20)
    else:
        ctx = ssl.create_default_context()
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection(u.hostname, u.port or 443, context=ctx, timeout=20)
    conn.request(method, path, headers=headers or {})
    r = conn.getresponse()
    body = r.read()
    return r, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--admin-path", default="")
    ap.add_argument("--http-port", type=int, default=80)
    ap.add_argument("--insecure-self-signed", action="store_true")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    ins = a.insecure_self_signed
    check("address is https://", base.startswith("https://"))
    try:
        r, body = request(base, "/healthz/", ins)
        check("TLS handshake and certificate validate" if not ins else "TLS handshake (certificate NOT validated: rehearsal mode)", True)
    except ssl.SSLError as e:
        check("TLS handshake and certificate validate", False, type(e).__name__)
        return finish()
    except OSError as e:
        check("server reachable", False, type(e).__name__)
        return finish()
    check("/healthz/ is 200 and database ok", r.status == 200 and b'"database": "ok"' in body.replace(b'":"', b'": "'))
    try:
        rr, _ = request(base, "/", ins, plain_http_port=a.http_port)
        loc = rr.getheader("Location") or ""
        check("HTTP redirects permanently to HTTPS", rr.status == 301 and loc.startswith("https://"), f"{rr.status}")
    except OSError:
        check("HTTP port answers with a redirect", False, "no answer on the plain-HTTP port")
    r, _ = request(base, "/accounts/login/", ins)
    h = {k.lower(): v for k, v in r.getheaders()}
    csp = h.get("content-security-policy", "")
    check("CSP is enforcing (header present, not report-only)", bool(csp) and "content-security-policy-report-only" not in h)
    check("CSP forbids framing and external scripts", "frame-ancestors 'none'" in csp and "script-src 'self'" in csp and "'unsafe-inline'" not in re.sub(r"style-src-attr[^;]*", "", csp).split("script-src")[1].split(";")[0])
    check("no-sniff, referrer policy", h.get("x-content-type-options") == "nosniff" and bool(h.get("referrer-policy")))
    check("login page is not cached", "no-store" in h.get("cache-control", ""))
    check("server version is not disclosed", not re.search(r"\d+\.\d+", h.get("server", "")), h.get("server", "-"))
    cookies = [v for k, v in r.getheaders() if k.lower() == "set-cookie"]
    csrf = [c for c in cookies if c.startswith("__Host-csrftoken=")]
    check("CSRF cookie is __Host-, Secure, Path=/, no Domain", bool(csrf) and all("Secure" in c and "Path=/" in c and "Domain" not in c for c in csrf))
    check("no cookie without Secure", all("Secure" in c for c in cookies))
    r, _ = request(base, "/accounts/login/", ins, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://evil.invalid"})
    check("POST without CSRF token / from a foreign origin is refused (403)", r.status == 403, str(r.status))
    for path in ("/media/x", "/private_media/x"):
        r, _ = request(base, path, ins)
        check(f"{path} is not served", r.status == 404, str(r.status))
    r, _ = request(base, "/admin/", ins)
    check("default /admin/ path does not exist", r.status == 404, str(r.status))
    if a.admin_path:
        r, _ = request(base, "/" + a.admin_path.strip("/") + "/login/", ins)
        check("configured admin path exists and is not cached", r.status in (200, 302) and "no-store" in (r.getheader("Cache-Control") or ""), str(r.status))
    for path in ("/portal/", "/portal/documents/", "/portal/audit/", "/portal/jobs/"):
        r, _ = request(base, path, ins)
        check(f"{path} requires login (redirect, no content)", r.status in (301, 302) and "/accounts/login/" in (r.getheader("Location") or ""), str(r.status))
    r, _ = request(base, "/portal/", ins, headers={"X-Forwarded-Proto": "http", "X-Forwarded-For": "203.0.113.9"})
    check("forged forwarding headers do not downgrade the connection", r.status in (301, 302) and (r.getheader("Location") or "").startswith("/"), str(r.status))
    hsts = h.get("strict-transport-security")
    print(f"[INFO] HSTS header: {hsts or 'absent (acceptable until real HTTPS is verified; docs/DEPLOYMENT_READINESS.md §4.12)'}")
    return finish()


def finish():
    n = len(R)
    ok = sum(R)
    print(f"SMOKE {'OK' if ok == n else 'FAILED'}: {ok}/{n}")
    return 0 if ok == n else 1


if __name__ == "__main__":
    sys.exit(main())
