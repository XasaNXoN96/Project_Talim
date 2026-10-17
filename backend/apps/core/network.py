"""Client address and scheme behind a reverse proxy — trusting forwarded headers ONLY from configured proxies.

Rules
-----
* settings.TRUSTED_PROXIES (parsed from DJANGO_TRUSTED_PROXIES) lists the addresses/networks of OUR reverse proxies.
  Empty (the default) = direct connections only: every forwarded header is ignored.
* If the TCP peer (REMOTE_ADDR) is not a trusted proxy, X-Forwarded-For / X-Forwarded-Proto are attacker-controlled
  and are ignored.
* If it is, X-Forwarded-For is read from the RIGHT: trusted proxies are skipped, the first untrusted address is the
  client. Entries to its left were supplied by the client (or earlier, untrusted hops) and are never used.
* A malformed header is ignored entirely (the proxy's own address is used) and a warning is logged.
* IPv4-mapped IPv6 addresses are normalised to IPv4. Rate limiting uses the /64 network of an IPv6 client, because one
  subscriber normally owns a whole /64 and could otherwise rotate addresses for free.
"""
import ipaddress
import logging

from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


def parse_trusted_proxies(entries):
    """['10.0.0.5', '192.168.0.0/24', '::1'] -> list of ip_network. Invalid values stop the server at startup."""
    networks = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry.strip(), strict=False))
        except ValueError as exc:
            raise ImproperlyConfigured(f"DJANGO_TRUSTED_PROXIES contains an invalid address or network: {entry!r}") from exc
    return networks


def _normalise(text):
    address = ipaddress.ip_address(str(text).strip())
    if address.version == 6 and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def _trusted(address, networks):
    return any(address in network for network in networks if network.version == address.version)


def _peer(request):
    try:
        return _normalise(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return None


def _networks():
    from django.conf import settings

    return getattr(settings, "TRUSTED_PROXY_NETWORKS", [])


def is_from_trusted_proxy(request):
    peer = _peer(request)
    return peer is not None and _trusted(peer, _networks())


def client_ip(request):
    """The client's address as a string, or None if it cannot be determined."""
    peer = _peer(request)
    if peer is None:
        return None
    networks = _networks()
    if not networks or not _trusted(peer, networks):
        return str(peer)  # direct connection (or an untrusted peer pretending to be a proxy): headers are ignored
    header = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not header.strip():
        return str(peer)
    try:
        hops = [_normalise(part) for part in header.split(",")]
    except ValueError:
        logger.warning("Malformed X-Forwarded-For from a trusted proxy; using the proxy address")
        return str(peer)
    for hop in reversed(hops):
        if not _trusted(hop, networks):
            return str(hop)
    return str(hops[0])  # every hop is one of our proxies: the leftmost is the best available answer


def throttle_ip_key(ip):
    """Rate-limit identity: the address itself for IPv4, the /64 network for IPv6."""
    if not ip:
        return "unknown"
    try:
        address = _normalise(ip)
    except ValueError:
        return "unknown"
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


class TrustedProxyMiddleware:
    """Marks the request as HTTPS when a TRUSTED proxy says so (X-Forwarded-Proto: https).

    This replaces SECURE_PROXY_SSL_HEADER, which would believe the header from any client. Must be the first middleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_from_trusted_proxy(request) and request.META.get("HTTP_X_FORWARDED_PROTO", "").strip().lower() == "https":
            request.META["wsgi.url_scheme"] = "https"
        return self.get_response(request)
