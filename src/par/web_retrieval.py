"""Bounded unauthenticated public HTTP retrieval; no browser cookies or proxies.

Resolve/check every redirect and pin the TCP address while retaining TLS SNI and
certificate verification for the original hostname (prevents DNS rebinding).
"""
import http.client
import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urljoin, urlunsplit, parse_qs, quote

MAX_BYTES = 2*1024*1024

@dataclass
class Page:
    url: str
    body: str
    content_type: str
    status: int = 200


def public_target(url):
    p = urlsplit(url)
    if (p.scheme not in {'http', 'https'} or not p.hostname or p.username or p.password
            or p.port not in {None, 80 if p.scheme == 'http' else 443}
            or len(url) > 2000 or any(ord(c) < 33 for c in url) or '\\' in url):
        raise ValueError('Only public HTTP(S) URLs on standard ports without credentials are allowed')
    if any(k.casefold() in {'token', 'key', 'api_key', 'password', 'signature', 'access_token'} for k in parse_qs(p.query)):
        raise ValueError('Credential-bearing URLs are not accepted')
    host = p.hostname.encode('idna').decode()
    port = p.port or (443 if p.scheme == 'https' else 80)
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError('Public hostname could not be resolved') from None
    ips = {a[4][0] for a in addresses}
    def forbidden(value):
        ip = ipaddress.ip_address(value)
        return (not ip.is_global or ip.is_multicast or ip.is_reserved or getattr(ip, 'is_site_local', False)
                or bool(getattr(ip, 'ipv4_mapped', None)) or bool(getattr(ip, 'sixtofour', None)) or bool(getattr(ip, 'teredo', None)))
    if not ips or any(forbidden(ip) for ip in ips):
        raise ValueError('Private, loopback, link-local, reserved and mixed-public/private destinations are refused')
    authority = ('['+host+']' if ':' in host else host)+(':'+str(p.port) if p.port else '')
    normalized = urlunsplit((p.scheme, authority, quote(p.path or '/', safe="/%:@!$&'()*+,;=-._~"), quote(p.query, safe="%=&?/:@!$'()*+,;~-._"), ''))
    return normalized, host, port, sorted(ips)[0]


class PublicFetcher:
    def fetch(self, url):
        deadline = time.monotonic()+25
        for _ in range(4):
            url, host, port, ip = public_target(url)
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise ValueError('Public retrieval time limit exceeded')
            cls = http.client.HTTPSConnection if urlsplit(url).scheme == 'https' else http.client.HTTPConnection
            kwargs = {'context': ssl.create_default_context()} if cls is http.client.HTTPSConnection else {}
            conn = cls(host, port, timeout=min(10, remaining), **kwargs)
            conn._create_connection = lambda address, timeout, source_address=None: socket.create_connection((ip, port), timeout, source_address)
            try:
                p = urlsplit(url)
                conn.request('GET', p.path+('?' + p.query if p.query else ''), headers={'User-Agent': 'Omnibus/0.3 (explicit user-requested retrieval)', 'Accept': 'text/html,text/plain', 'Accept-Encoding': 'identity'})
                r = conn.getresponse()
                if r.status in {301, 302, 303, 307, 308}:
                    location = r.getheader('Location')
                    if not location:
                        raise ValueError('Redirect without destination')
                    url = urljoin(url, location)
                    continue
                if r.status != 200:
                    raise ValueError(f'Public resource returned HTTP {r.status}; no bypass attempted')
                mime = r.getheader('Content-Type', '').split(';')[0].strip().lower()
                if mime not in {'text/html', 'application/xhtml+xml', 'text/plain'}:
                    raise ValueError('Only HTML/plain-text snapshots are supported; no media download')
                if r.getheader('Content-Encoding', 'identity') != 'identity':
                    raise ValueError('Compressed response refused (bounded plain responses only)')
                size = r.getheader('Content-Length')
                expected = int(size) if size is not None else None
                if expected is not None and not 0 <= expected <= MAX_BYTES:
                    raise ValueError('Public response size exceeds limits')
                raw = bytearray()
                while True:
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        raise ValueError('Public retrieval time limit exceeded')
                    if conn.sock:
                        conn.sock.settimeout(min(10, remaining))
                    block = r.read1(min(65536, MAX_BYTES+1-len(raw)))
                    raw.extend(block)
                    if len(raw) > MAX_BYTES:
                        raise ValueError('Public response exceeds 2 MiB')
                    if not block:
                        break
                if expected is not None and len(raw) != expected:
                    raise ValueError('Incomplete public response; no metadata verified')
                return Page(url, raw.decode('utf-8', errors='replace'), mime)
            except (OSError, http.client.HTTPException):
                raise ValueError('Public retrieval failed (network/TLS/timeout); no resource verified') from None
            finally:
                conn.close()
        raise ValueError('Too many public resource redirects')
