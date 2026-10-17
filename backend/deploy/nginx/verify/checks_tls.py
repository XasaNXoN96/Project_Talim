"""Checks run by run_tls.sh against nginx (HTTP_PORT/HTTPS_PORT) and gunicorn (APP_PORT). Phase name = argv[1]."""
import http.client
import warnings
import os
import re
import socket
import ssl
import sys

HTTP, HTTPS, APP = int(os.environ["HTTP_PORT"]), int(os.environ["HTTPS_PORT"]), int(os.environ["APP_PORT"])
ADMIN = os.environ["ADMIN_URL"]
RESULTS = []
warnings.simplefilter("ignore", DeprecationWarning)  # TLS 1.0/1.1 constants are deprecated; they are used on purpose to prove refusal


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def ctx(minimum=None, maximum=None):
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE  # throw-away self-signed certificate: the chain is NOT being tested
    if minimum:
        c.minimum_version = minimum
    if maximum:
        c.maximum_version = maximum
    return c


def https(method, path, body=None, headers=None, cookies=None):
    conn = http.client.HTTPSConnection("127.0.0.1", HTTPS, context=ctx(), timeout=20)
    h = {"Host": "localhost", **(headers or {})}
    if cookies:
        h["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    conn.request(method, path, body=body, headers=h)
    r = conn.getresponse()
    data = r.read()
    return r, data


def plain(port, method, path, headers=None, source=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20, source_address=(source, 0) if source else None)
    conn.request(method, path, headers={"Host": "localhost", **(headers or {})})
    r = conn.getresponse()
    r.read()
    return r


def set_cookies(r):
    return [v for k, v in r.getheaders() if k.lower() == "set-cookie"]


def attrs(cookie):
    parts = [p.strip() for p in cookie.split(";")]
    return parts[0].split("=")[0], {p.split("=")[0].lower(): (p.split("=", 1)[1] if "=" in p else True) for p in parts[1:]}


def common():
    r = plain(HTTP, "GET", "/accounts/login/")
    check("plain HTTP is redirected to HTTPS (301) and nothing else is served", r.status == 301 and r.getheader("Location", "").startswith(f"https://localhost:{HTTPS}/accounts/login/"), f"{r.status} {r.getheader('Location')}")
    r, body = https("GET", "/accounts/login/")
    check("HTTPS login page answers 200", r.status == 200)
    h = {k.lower(): v for k, v in r.getheaders()}
    csp = h.get("content-security-policy", "")
    check("Content-Security-Policy is ENFORCED (not report-only) in production", bool(csp) and "content-security-policy-report-only" not in h, csp[:60])
    check("CSP has no unsafe-eval and no inline scripts/styles (only the documented style attributes)", "unsafe-eval" not in csp and "script-src 'self'" in csp and "style-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp)
    check("X-Frame-Options DENY, nosniff, Referrer-Policy same-origin, Permissions-Policy present", h.get("x-frame-options") == "DENY" and h.get("x-content-type-options") == "nosniff" and h.get("referrer-policy") == "same-origin" and "geolocation=()" in h.get("permissions-policy", ""))
    check("account pages are not cacheable (no-store)", "no-store" in h.get("cache-control", ""), h.get("cache-control", ""))
    check("server version is not disclosed", not re.search(r"\d", h.get("server", "")), h.get("server", ""))
    cookies = {}
    for c in set_cookies(r):
        name, a = attrs(c)
        cookies[name] = c.split(";")[0].split("=", 1)[1]
        check(f"cookie {name}: Secure, Path=/, no Domain, SameSite=Lax", "secure" in a and a.get("path") == "/" and "domain" not in a and str(a.get("samesite", "")).lower() == "lax", c.split(";")[0].split("=")[0])
    check("CSRF cookie uses the __Host- prefix", "__Host-csrftoken" in cookies, ",".join(cookies))
    token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', body).group(1).decode()
    r, _ = https("POST", "/accounts/login/", body=f"csrfmiddlewaretoken={token}&username=alice&password=Namuna-Parol-12345",
                 headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": f"https://localhost:{HTTPS}/accounts/login/", "Origin": f"https://localhost:{HTTPS}"}, cookies={"__Host-csrftoken": cookies["__Host-csrftoken"]})
    sess = [attrs(c) for c in set_cookies(r) if c.startswith("__Host-sessionid")]
    check("login succeeds over HTTPS (302) with the CSRF token", r.status == 302, str(r.status))
    check("session cookie __Host-sessionid: Secure, HttpOnly, SameSite=Lax, Path=/, no Domain", bool(sess) and "secure" in sess[0][1] and "httponly" in sess[0][1] and str(sess[0][1].get("samesite", "")).lower() == "lax" and "domain" not in sess[0][1])
    r, _ = https("POST", "/accounts/login/", body="username=alice&password=x", headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": f"https://localhost:{HTTPS}/", "Origin": f"https://localhost:{HTTPS}"})
    check("a POST without a CSRF token is refused (403)", r.status == 403, str(r.status))
    r, _ = https("POST", "/accounts/login/", body="username=alice&password=x", headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://evil.test"}, cookies={"__Host-csrftoken": cookies["__Host-csrftoken"]})
    check("a POST from a foreign origin is refused (403)", r.status == 403, str(r.status))
    r, _ = https("GET", "/admin/")
    check("the default /admin/ path does not exist (admin lives on a non-default path)", r.status == 404, str(r.status))
    r, _ = https("GET", "/" + ADMIN)
    check("the configured admin path exists but needs a login", r.status in (200, 302), str(r.status))
    for p in ("/private_media/x", "/media/x", "/private_media/"):
        r, _ = https("GET", p)
        check(f"{p} is never served by nginx", r.status == 404, str(r.status))
    r, _ = https("GET", "/healthz/")
    check("health check answers over HTTPS", r.status == 200)
    return h


def access_log():
    https("GET", "/accounts/reset/MQ/set-token-abc123/")
    https("GET", "/portal/search/?q=SECRETQUERYWORD&type=tasks")
    https("GET", "/accounts/login/?next=/portal/documents/%3Fq%3DCONFIDENTIALTERM")
    import time

    time.sleep(0.5)
    log = open(os.environ["ACCESS_LOG"]).read()
    check("the access log records requests", "GET /accounts/login/" in log)
    check("the access log holds no query strings (search words, filters, next=)", "SECRETQUERYWORD" not in log and "CONFIDENTIALTERM" not in log and "?" not in log, "")
    check("the access log holds no password-reset token", "set-token-abc123" not in log and "/accounts/reset/MQ/[redacted]" in log)


def tls_versions():
    for name, v in (("TLS 1.0", ssl.TLSVersion.TLSv1), ("TLS 1.1", ssl.TLSVersion.TLSv1_1)):
        try:
            c = ctx(v, v)
            with socket.create_connection(("127.0.0.1", HTTPS), timeout=10) as s:
                with c.wrap_socket(s, server_hostname="localhost") as t:
                    check(f"{name} is refused", False, f"negotiated {t.version()}")
        except (ssl.SSLError, OSError) as exc:
            check(f"{name} is refused", True, type(exc).__name__)
    for name, v in (("TLS 1.2", ssl.TLSVersion.TLSv1_2), ("TLS 1.3", ssl.TLSVersion.TLSv1_3)):
        c = ctx(v, v)
        with socket.create_connection(("127.0.0.1", HTTPS), timeout=10) as s:
            with c.wrap_socket(s, server_hostname="localhost") as t:
                check(f"{name} is accepted", t.version() is not None, t.version())


def proxy_trust():
    r = plain(APP, "GET", "/accounts/login/", source="127.0.0.2")
    check("direct to gunicorn over plain HTTP is redirected to HTTPS (not served)", r.status == 301, str(r.status))
    r = plain(APP, "GET", "/accounts/login/", headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.9"}, source="127.0.0.2")
    check("a forged X-Forwarded-Proto from an untrusted peer does NOT make the request 'secure'", r.status == 301, str(r.status))
    for p in ("/accounts/login/",):
        r, _ = https("GET", p, headers={"X-Forwarded-Proto": "http"})
        check("a client-supplied X-Forwarded-Proto is overwritten by nginx (still served over HTTPS)", r.status == 200, str(r.status))


def hsts(expected):
    r, _ = https("GET", "/accounts/login/")
    value = r.getheader("Strict-Transport-Security")
    if expected:
        check("HSTS is sent over HTTPS when enabled", value is not None and "max-age=60" in value and "includeSubDomains" in value, value or "")
        check("HSTS is NOT sent on the plain-HTTP redirect", plain(HTTP, "GET", "/").getheader("Strict-Transport-Security") is None)
    else:
        check("HSTS is not sent while DJANGO_HSTS_SECONDS=0 (deferred on purpose until HTTPS is verified)", value is None)


phase = sys.argv[1]
if phase == "hsts_off":
    common()
    tls_versions()
    proxy_trust()
    access_log()
    hsts(False)
else:
    hsts(True)
print(f"{sum(RESULTS)}/{len(RESULTS)} checks passed")
sys.exit(0 if all(RESULTS) else 1)
