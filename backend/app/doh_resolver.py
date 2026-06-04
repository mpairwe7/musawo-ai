"""DNS-over-HTTPS resolver for environments where standard DNS is broken.

Patches `socket.getaddrinfo` so every httpx / OpenAI-SDK / requests call routes
external hostname resolution through `https://1.1.1.1/dns-query`. This is the
DNS half of the Crane Cloud / RENU egress fix (ported from AgriLink): the RENU
pod has no working upstream resolver, but can reach 1.1.1.1 directly on TCP/443.

`auto_activate_if_dns_broken()` is called on startup and is a no-op where
external DNS already works (local dev, NITA-U) — so it's safe to call always.

Split-horizon: cluster-internal hostnames (`.svc.cluster.local`, single-label
"localhost", IP literals) bypass DoH and use the original resolver.
"""

from __future__ import annotations

import logging
import socket
import threading
import time

import httpx

# dnspython parses/serializes DNS wire format; the transport is httpx (so we are
# not blocked by the broken UDP/53 resolver).
import dns.message
import dns.rdatatype
import dns.exception

logger = logging.getLogger("musawo.doh")

_DOH_URL = "https://1.1.1.1/dns-query"
_CACHE_TTL_S = 60.0
_DOH_TIMEOUT_S = 5.0

_cache: dict[str, tuple[str, float]] = {}
_cache_lock = threading.Lock()
_original_getaddrinfo = socket.getaddrinfo
_activated = False

_internal_cache: dict[tuple, tuple[object, float]] = {}
_INTERNAL_CACHE_TTL_S = 300.0


def _looks_like_ip(host: str) -> bool:
    parts = host.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or not (0 <= int(p) <= 255):
            return False
    return True


def _is_internal(host: str) -> bool:
    """Hostnames that should bypass DoH and use the system resolver."""
    if not host:
        return True
    h = host.lower()
    if h == "localhost" or h.endswith(".cluster.local") or "." not in h:
        return True
    if _looks_like_ip(h):
        return True
    return False


def _resolve_doh(host: str) -> str:
    """Return one A-record IP for `host` via DoH, or raise socket.gaierror."""
    with _cache_lock:
        cached = _cache.get(host)
        if cached and cached[1] > time.time():
            return cached[0]
    try:
        query = dns.message.make_query(host, dns.rdatatype.A)
        with httpx.Client(timeout=_DOH_TIMEOUT_S) as client:
            resp = client.post(
                _DOH_URL,
                content=query.to_wire(),
                headers={
                    "Content-Type": "application/dns-message",
                    "Accept": "application/dns-message",
                },
            )
            resp.raise_for_status()
            msg = dns.message.from_wire(resp.content)
    except (httpx.HTTPError, dns.exception.DNSException) as exc:
        raise socket.gaierror(socket.EAI_AGAIN, f"DoH lookup failed for {host}: {exc}") from exc

    for rrset in msg.answer:
        if rrset.rdtype != dns.rdatatype.A:
            continue
        for item in rrset:
            ip = item.address  # type: ignore[attr-defined]
            with _cache_lock:
                _cache[host] = (ip, time.time() + _CACHE_TTL_S)
            return ip
    raise socket.gaierror(socket.EAI_NONAME, f"No A record returned for {host}")


def _doh_getaddrinfo(host, port, *args, **kwargs):
    """Drop-in replacement for socket.getaddrinfo routing external hosts via DoH."""
    if _is_internal(host):
        key = (host, port, args, tuple(sorted(kwargs.items())))
        now = time.time()
        with _cache_lock:
            hit = _internal_cache.get(key)
            if hit and hit[1] > now:
                return hit[0]
        result = _original_getaddrinfo(host, port, *args, **kwargs)
        with _cache_lock:
            _internal_cache[key] = (result, now + _INTERNAL_CACHE_TTL_S)
        return result

    try:
        ip = _resolve_doh(host)
    except socket.gaierror as exc:
        logger.warning("DoH fallback to system resolver for %s: %s", host, exc)
        return _original_getaddrinfo(host, port, *args, **kwargs)

    if isinstance(port, int):
        port_num = port
    elif port is None:
        port_num = 0
    elif isinstance(port, str) and port.isdigit():
        port_num = int(port)
    elif isinstance(port, str):
        try:
            port_num = socket.getservbyname(port)
        except OSError:
            port_num = 0
    else:
        port_num = 0
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port_num))]


def activate() -> None:
    """Idempotently install the DoH resolver as socket.getaddrinfo."""
    global _activated
    if _activated:
        return
    socket.getaddrinfo = _doh_getaddrinfo  # type: ignore[assignment]
    _activated = True
    logger.info("DoH resolver activated (upstream=%s)", _DOH_URL)


def deactivate() -> None:
    """Restore the original socket.getaddrinfo (tests)."""
    global _activated
    socket.getaddrinfo = _original_getaddrinfo  # type: ignore[assignment]
    _activated = False
    _cache.clear()
    _internal_cache.clear()


_AUTODETECT_CANARY = "example.com"


def _system_resolves(host: str, timeout_s: float) -> bool:
    res = {"ok": False}

    def _probe() -> None:
        try:
            _original_getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            res["ok"] = True
        except OSError:
            pass

    t = threading.Thread(target=_probe, daemon=True)
    t.start()
    t.join(timeout_s)
    return res["ok"]


def auto_activate_if_dns_broken(timeout_s: float = 2.0) -> bool:
    """Activate DoH only when external DNS is broken but DoH works. No-op where
    external DNS is healthy, so safe to call unconditionally. Returns True if active."""
    if _activated:
        return True
    if _system_resolves(_AUTODETECT_CANARY, timeout_s):
        return False  # external DNS works
    try:
        _resolve_doh(_AUTODETECT_CANARY)  # confirm DoH path works
    except socket.gaierror as exc:
        logger.warning("DoH unreachable, not activating: %s", exc)
        return False
    logger.warning("External DNS broken — activating DoH resolver")
    activate()
    return True
