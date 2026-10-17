import ipaddress

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts import throttle
from apps.accounts.models import ThrottleState
from apps.accounts.testing import PASSWORD, make_user
from apps.audit.models import AuditLog
from apps.core.network import client_ip, parse_trusted_proxies, throttle_ip_key

LOGIN = reverse("accounts:login")
WRONG = "Noto-g-ri-parol-0000"


def request(remote, **headers):
    meta = {"REMOTE_ADDR": remote}
    meta.update({"HTTP_" + k.upper().replace("-", "_"): v for k, v in headers.items()})
    return RequestFactory().get("/", **meta)


def trusting(*entries):
    return override_settings(TRUSTED_PROXY_NETWORKS=parse_trusted_proxies(entries))


class DirectConnectionTests(SimpleTestCase):
    def test_default_configuration_trusts_no_proxy(self):
        self.assertEqual(settings.TRUSTED_PROXIES, [])
        self.assertEqual(settings.TRUSTED_PROXY_NETWORKS, [])

    def test_peer_address_is_used(self):
        self.assertEqual(client_ip(request("203.0.113.7")), "203.0.113.7")

    def test_forwarded_headers_are_ignored_without_trusted_proxies(self):
        req = request("203.0.113.7", X_Forwarded_For="1.2.3.4", X_Real_IP="5.6.7.8", Forwarded="for=9.9.9.9")
        self.assertEqual(client_ip(req), "203.0.113.7")

    def test_unusable_peer_address(self):
        self.assertIsNone(client_ip(request("")))
        self.assertIsNone(client_ip(request("not-an-ip")))


class SpoofingTests(SimpleTestCase):
    @trusting("10.0.0.5")
    def test_untrusted_peer_cannot_use_forwarded_for_even_if_proxies_are_configured(self):
        self.assertEqual(client_ip(request("198.51.100.20", X_Forwarded_For="1.2.3.4")), "198.51.100.20")

    @trusting("10.0.0.5")
    def test_peer_in_a_different_subnet_is_not_trusted(self):
        self.assertEqual(client_ip(request("10.0.0.6", X_Forwarded_For="1.2.3.4")), "10.0.0.6")

    @trusting("10.0.0.5")
    def test_values_on_the_left_are_client_supplied_and_never_used(self):
        self.assertEqual(client_ip(request("10.0.0.5", X_Forwarded_For="1.2.3.4, 203.0.113.7")), "203.0.113.7")
        self.assertEqual(client_ip(request("10.0.0.5", X_Forwarded_For="6.6.6.6, 7.7.7.7, 203.0.113.7")), "203.0.113.7")

    @trusting("10.0.0.5")
    def test_client_cannot_pose_as_a_trusted_proxy_to_hide(self):
        # the client prepends the proxy's own address; the proxy appended the real one on the right
        self.assertEqual(client_ip(request("10.0.0.5", X_Forwarded_For="10.0.0.5, 203.0.113.7")), "203.0.113.7")

    @trusting("10.0.0.5")
    def test_other_forwarding_headers_are_never_used(self):
        self.assertEqual(client_ip(request("10.0.0.5", X_Real_IP="1.2.3.4", Forwarded="for=5.6.7.8", True_Client_IP="9.9.9.9")), "10.0.0.5")


class TrustedProxyTests(SimpleTestCase):
    @trusting("10.0.0.5")
    def test_single_proxy_hop(self):
        self.assertEqual(client_ip(request("10.0.0.5", X_Forwarded_For="203.0.113.7")), "203.0.113.7")

    @trusting("10.0.0.0/24")
    def test_chain_of_two_trusted_proxies(self):
        self.assertEqual(client_ip(request("10.0.0.5", X_Forwarded_For="203.0.113.7, 10.0.0.9")), "203.0.113.7")

    @trusting("10.0.0.5", "192.168.0.0/16")
    def test_multiple_entries_and_networks(self):
        self.assertEqual(client_ip(request("192.168.4.4", X_Forwarded_For="203.0.113.7")), "203.0.113.7")

    @trusting("10.0.0.5")
    def test_missing_header_falls_back_to_the_proxy(self):
        self.assertEqual(client_ip(request("10.0.0.5")), "10.0.0.5")
        self.assertEqual(client_ip(request("10.0.0.5", X_Forwarded_For="   ")), "10.0.0.5")

    @trusting("10.0.0.5")
    def test_malformed_header_is_ignored_as_a_whole(self):
        for bad in ("garbage", "203.0.113.7, not-an-ip", "203.0.113.7;evil", "999.1.1.1", "203.0.113.7, "):
            with self.assertLogs("apps.core.network", level="WARNING"):
                self.assertEqual(client_ip(request("10.0.0.5", X_Forwarded_For=bad)), "10.0.0.5", msg=bad)

    @trusting("10.0.0.5", "10.0.0.6")
    def test_all_hops_trusted_returns_the_leftmost(self):
        self.assertEqual(client_ip(request("10.0.0.5", X_Forwarded_For="10.0.0.6")), "10.0.0.6")

    @trusting("::1")
    def test_ipv6_proxy(self):
        self.assertEqual(client_ip(request("::1", X_Forwarded_For="2001:db8::7")), "2001:db8::7")

    @trusting("10.0.0.5")
    def test_ipv4_mapped_addresses_are_normalised(self):
        self.assertEqual(client_ip(request("::ffff:10.0.0.5", X_Forwarded_For="::ffff:203.0.113.7")), "203.0.113.7")
        self.assertEqual(client_ip(request("::ffff:203.0.113.7")), "203.0.113.7")

    @trusting("10.0.0.5")
    def test_ipv4_network_does_not_match_an_ipv6_peer(self):
        self.assertEqual(client_ip(request("::1", X_Forwarded_For="1.2.3.4")), "::1")


class ConfigurationTests(SimpleTestCase):
    def test_parsing(self):
        nets = parse_trusted_proxies(["10.0.0.5", " 192.168.0.0/24 ", "::1"])
        self.assertEqual([str(n) for n in nets], ["10.0.0.5/32", "192.168.0.0/24", "::1/128"])
        self.assertEqual(parse_trusted_proxies([]), [])

    def test_invalid_entries_stop_startup(self):
        for bad in ("not-an-ip", "10.0.0.0/99", "*", "0.0.0.0/0x"):
            with self.assertRaises(ImproperlyConfigured, msg=bad):
                parse_trusted_proxies([bad])

    def test_wildcard_networks_are_a_conscious_choice_not_a_default(self):
        self.assertEqual(settings.TRUSTED_PROXY_NETWORKS, [])  # nothing trusted unless the operator lists it


class ThrottleKeyTests(SimpleTestCase):
    def test_ipv4_is_per_address(self):
        self.assertEqual(throttle_ip_key("203.0.113.7"), "203.0.113.7")
        self.assertNotEqual(throttle_ip_key("203.0.113.7"), throttle_ip_key("203.0.113.8"))

    def test_ipv6_is_per_slash_64(self):
        self.assertEqual(throttle_ip_key("2001:db8:1:2::1"), throttle_ip_key("2001:db8:1:2:ffff:ffff:ffff:ffff"))
        self.assertNotEqual(throttle_ip_key("2001:db8:1:2::1"), throttle_ip_key("2001:db8:1:3::1"))
        self.assertEqual(throttle_ip_key("2001:db8:1:2::1"), "2001:db8:1:2::/64")

    def test_mapped_and_unknown(self):
        self.assertEqual(throttle_ip_key("::ffff:203.0.113.7"), "203.0.113.7")
        self.assertEqual(throttle_ip_key(None), "unknown")
        self.assertEqual(throttle_ip_key("garbage"), "unknown")


class SchemeTests(TestCase):
    def test_untrusted_peer_cannot_make_the_request_look_secure(self):
        response = Client().get("/", REMOTE_ADDR="203.0.113.7", HTTP_X_FORWARDED_PROTO="https")
        self.assertFalse(response.wsgi_request.is_secure())

    @trusting("10.0.0.5")
    def test_trusted_proxy_can_declare_https(self):
        secure = Client().get("/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_PROTO="https")
        self.assertTrue(secure.wsgi_request.is_secure())
        plain = Client().get("/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_PROTO="http")
        self.assertFalse(plain.wsgi_request.is_secure())

    def test_the_header_trusting_django_switch_is_not_used(self):
        self.assertIsNone(getattr(settings, "SECURE_PROXY_SSL_HEADER", None))


@trusting("10.0.0.5")
class BehindProxyIntegrationTests(TestCase):
    """The rate limiter and the audit trail see the real client, and clients sharing an address are handled correctly."""

    def attempt(self, client, user, password, client_addr, via="10.0.0.5"):
        return client.post(LOGIN, {"username": user, "password": password}, REMOTE_ADDR=via, HTTP_X_FORWARDED_FOR=client_addr)

    def test_audit_trail_records_the_real_client_address(self):
        make_user("alice")
        self.attempt(Client(), "alice", PASSWORD, "203.0.113.7")
        self.assertEqual(AuditLog.objects.get(action=AuditLog.Action.LOGIN).ip, "203.0.113.7")

    def test_different_clients_behind_one_proxy_are_counted_separately(self):
        for i in range(25):  # 25 different people each fail once: nobody reaches any limit
            self.attempt(Client(), f"nobody{i}", WRONG, f"203.0.113.{i + 10}")
        make_user("alice")
        self.assertEqual(self.attempt(Client(), "alice", PASSWORD, "203.0.113.99").status_code, 302)

    def test_proxy_address_is_not_what_gets_rate_limited(self):
        for i in range(25):
            self.attempt(Client(), f"nobody{i}", WRONG, f"203.0.113.{i + 10}")
        self.assertFalse(ThrottleState.objects.filter(kind="login:ip", key_hash=throttle.digest("login:ip", "10.0.0.5")).exists())

    def test_forged_forwarded_for_from_a_client_cannot_dodge_the_limit(self):
        # the attacker's real address is the rightmost one the proxy appends; the forged left part changes nothing
        make_user("alice")
        for i in range(20):
            self.attempt(Client(), f"x{i}", WRONG, f"{i}.{i}.{i}.{i}, 198.51.100.50")
        self.assertEqual(self.attempt(Client(), "alice", PASSWORD, f"8.8.8.8, 198.51.100.50").status_code, 200)  # still locked

    def test_users_sharing_one_public_address_can_all_sign_in(self):
        users = [make_user(f"staff{i}") for i in range(5)]
        for user in users:  # each mistypes three times, then succeeds (NAT'd office: one public IP)
            client = Client()
            for _ in range(3):
                self.attempt(client, user.username, WRONG, "198.51.100.77")
            self.assertEqual(self.attempt(client, user.username, PASSWORD, "198.51.100.77").status_code, 302, msg=user.username)

    def test_a_shared_address_is_limited_as_a_whole_when_it_misbehaves(self):
        # documented trade-off: 20 failures from ONE public address lock that address, innocent colleagues included
        make_user("alice")
        for i in range(20):
            self.attempt(Client(), f"x{i}", WRONG, "198.51.100.88")
        self.assertEqual(self.attempt(Client(), "alice", PASSWORD, "198.51.100.88").status_code, 200)
        self.assertEqual(self.attempt(Client(), "alice", PASSWORD, "198.51.100.89").status_code, 302)  # other address: fine

    def test_ipv6_clients_are_limited_per_slash_64(self):
        make_user("alice")
        for i in range(20):
            self.attempt(Client(), f"x{i}", WRONG, f"2001:db8:aaaa:bbbb::{i + 1:x}")  # rotating addresses inside one /64
        self.assertEqual(self.attempt(Client(), "alice", PASSWORD, "2001:db8:aaaa:bbbb::ffff").status_code, 200)
        self.assertEqual(self.attempt(Client(), "alice", PASSWORD, "2001:db8:aaaa:cccc::1").status_code, 302)


class WithoutProxyConfigurationTests(TestCase):
    """Production without DJANGO_TRUSTED_PROXIES must never be fooled by a header."""

    def test_forged_forwarded_for_is_useless_to_a_direct_attacker(self):
        make_user("alice")
        for i in range(20):
            Client().post(LOGIN, {"username": f"x{i}", "password": WRONG}, REMOTE_ADDR="198.51.100.60", HTTP_X_FORWARDED_FOR=f"1.1.1.{i}")
        locked = Client().post(LOGIN, {"username": "alice", "password": PASSWORD}, REMOTE_ADDR="198.51.100.60", HTTP_X_FORWARDED_FOR="9.9.9.9")
        self.assertEqual(locked.status_code, 200)
