import csv
import http.client
import os
import queue
import random
import re
import socket
import ssl
import statistics
import struct
import sys
import threading
import time

TARGET = "gemini.google.com"
DEFAULT_SERVERS_TEXT = """
dns.yandex one.one.one.one xbox-dns.ru dns.comss.one router.comss.one
dns.geohide.ru eu.geohide.ru us.geohide.ru
dns.geohide.ru:444 eu.geohide.ru:444 us.geohide.ru:444
dns.magicdns.ru dns.bezmezhau.com dns.wlrus.cfd dns.dagami.ru
dns.astracat.network dns.dns-ai.ru dns.mafioznik.xyz dns.malw.link
d.webshiftvpn.ru free.shecan.ir dns.zapret.moe dns.commonnet.work
freedns.controld.com common.dot.dns.yandex.net dns.ghost.pm doh.pub
5u35p8m9i7.cloudflare-gateway.com dns.switch.ch alidns.com
"""
SERVERS_FILE = "servers.txt"

BOOTSTRAP = ("1.1.1.1", "8.8.8.8")
BOOTSTRAP_TIMEOUT = 2.0
PROTOS = ("udp", "tls", "https")
PROTO_NAMES = {"udp": "UDP", "tls": "DoT", "https": "DoH"}

WORKERS = 8
REPEATS = 3
DNS_TIMEOUT = 4.0
HTTP_TIMEOUT = 8.0
HTTP_TOTAL = 15.0
MAX_BYTES = 1_500_000
TOP_N = 5
RUS_IS_BAD = True

COUNTRY_RE = re.compile(rb',2,1,200,"([A-Za-z]{3})"')
STATUS_RE = re.compile(rb"HTTP/\d(?:\.\d)? (\d{3})")
IP4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
REQ = (f"GET / HTTP/1.1\r\nHost: {TARGET}\r\nUser-Agent: Mozilla/5.0\r\n"
       "Accept: text/html\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n").encode()


class DnsFail(Exception):
    pass


# ---------- разбор записи сервера ----------

def parse_entry(entry):
    e = {"raw": entry, "proto": None, "host": "", "port": None,
         "path": "/dns-query", "ip": None}
    s = entry
    m = re.match(r"^(udp|tls|https)://", s)
    if m:
        e["proto"] = m.group(1)
        s = s[m.end():]
    if "@" in s:
        s, e["ip"] = s.rsplit("@", 1)
    if "/" in s:
        s, path = s.split("/", 1)
        e["path"] = "/" + path
    host, _, port = s.partition(":")
    e["host"] = host
    e["port"] = int(port) if port.isdigit() else None
    return e


def parse_server_text(text):
    out = []
    for line in text.splitlines():
        out += line.split("#", 1)[0].split()
    return list(dict.fromkeys(out))


def app_dir():
    p = sys.executable if getattr(sys, "frozen", False) else __file__
    return os.path.dirname(os.path.abspath(p))


# ---------- DNS wire format ----------

def build_query(name, qtype=1, pid=None):
    if pid is None:
        pid = random.randint(1, 0xFFFF)
    header = struct.pack(">HHHHHH", pid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0"
    return pid, header + qname + struct.pack(">HH", qtype, 1)


def skip_name(data, off):
    while True:
        ln = data[off]
        if ln == 0:
            return off + 1
        if ln & 0xC0 == 0xC0:
            return off + 2
        off += ln + 1


def is_truncated(data):
    return len(data) >= 4 and bool(struct.unpack(">H", data[2:4])[0] & 0x0200)


def parse_answer(data, pid, qtype):
    try:
        rid, flags, qd, an, _, _ = struct.unpack(">HHHHHH", data[:12])
        if rid != pid or not flags & 0x8000 or flags & 0xF:
            return None
        off = 12
        for _ in range(qd):
            off = skip_name(data, off) + 4
        ips = []
        for _ in range(an):
            off = skip_name(data, off)
            rtype, _, _, rdlen = struct.unpack(">HHIH", data[off:off + 10])
            off += 10
            if rtype == qtype == 1 and rdlen == 4:
                ips.append(socket.inet_ntoa(data[off:off + 4]))
            elif rtype == qtype == 28 and rdlen == 16:
                ips.append(socket.inet_ntop(socket.AF_INET6, data[off:off + 16]))
            off += rdlen
        return ips
    except (struct.error, IndexError):
        return None


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("соединение закрыто")
        buf += chunk
    return buf


def tcp_exchange(addr, pkt, timeout):
    with socket.create_connection(addr, timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(struct.pack(">H", len(pkt)) + pkt)
        ln = struct.unpack(">H", recv_exact(s, 2))[0]
        return recv_exact(s, ln)


# ---------- транспорты ----------

class UdpTransport:
    def __init__(self, ip, port, timeout):
        self.addr, self.timeout = (ip, port), timeout

    def open(self):
        pass

    def close(self):
        pass

    def exchange(self, pkt):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            deadline = time.perf_counter() + self.timeout
            s.sendto(pkt, self.addr)
            while True:
                left = deadline - time.perf_counter()
                if left <= 0:
                    raise socket.timeout
                s.settimeout(left)
                data, _ = s.recvfrom(4096)
                if data[:2] == pkt[:2]:
                    break
        if is_truncated(data):
            data = tcp_exchange(self.addr, pkt, self.timeout)
        return data


class DotTransport:
    def __init__(self, host, ip, port, timeout):
        self.host, self.addr, self.timeout, self.sock = host, (ip, port), timeout, None

    def open(self):
        raw = socket.create_connection(self.addr, timeout=self.timeout)
        try:
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise
        self.sock.settimeout(self.timeout)

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def exchange(self, pkt):
        self.sock.sendall(struct.pack(">H", len(pkt)) + pkt)
        ln = struct.unpack(">H", recv_exact(self.sock, 2))[0]
        return recv_exact(self.sock, ln)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, port, timeout):
        self._ctx = ssl.create_default_context()
        super().__init__(host, port, timeout=timeout, context=self._ctx)
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        try:
            self.sock = self._ctx.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


class DohTransport:
    def __init__(self, host, ip, port, path, timeout):
        self.args, self.path, self.conn = (host, ip, port, timeout), path, None

    def open(self):
        self.conn = _PinnedHTTPS(*self.args)
        self.conn.connect()

    def close(self):
        if self.conn:
            self.conn.close()

    def exchange(self, pkt):
        self.conn.request("POST", self.path, body=pkt, headers={
            "Content-Type": "application/dns-message",
            "Accept": "application/dns-message"})
        resp = self.conn.getresponse()
        body = resp.read()
        if resp.status != 200:
            raise ValueError(f"HTTP {resp.status}")
        return body


def make_transport(proto, e, srv_ip):
    if proto == "udp":
        return UdpTransport(srv_ip, e["port"] or 53, DNS_TIMEOUT)
    if proto == "tls":
        return DotTransport(e["host"], srv_ip, e["port"] or 853, DNS_TIMEOUT)
    return DohTransport(e["host"], srv_ip, e["port"] or 443, e["path"], DNS_TIMEOUT)


def short_err(e):
    if isinstance(e, (socket.timeout, TimeoutError)):
        return "таймаут"
    if isinstance(e, ssl.SSLError):
        return "TLS"
    if isinstance(e, ConnectionRefusedError):
        return "отказ"
    if isinstance(e, ValueError):
        return str(e)
    return e.__class__.__name__


# ---------- DNS-проба ----------

def bootstrap_lookup(server, name):
    pid, pkt = build_query(name, 1)
    data = UdpTransport(server, 53, BOOTSTRAP_TIMEOUT).exchange(pkt)
    return parse_answer(data, pid, 1) or []


def resolve_server(e):
    if e["ip"]:
        return e["ip"]
    if IP4_RE.match(e["host"]):
        return e["host"]
    for b in BOOTSTRAP:
        try:
            ips = bootstrap_lookup(b, e["host"])
            if ips:
                return ips[0]
        except OSError:
            continue
    try:
        return socket.getaddrinfo(e["host"], None, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    except OSError:
        raise DnsFail("имя DNS-сервера не резолвится")


def measure_dns(tr, name, qtype, doh):
    times, ip = [], None
    tr.open()
    try:
        for _ in range(REPEATS):
            pid, pkt = build_query(name, qtype, pid=0 if doh else None)
            try:
                t0 = time.perf_counter()
                data = tr.exchange(pkt)
                ms = (time.perf_counter() - t0) * 1000
                ips = parse_answer(data, pid, qtype)
                if ips is None:
                    raise ValueError("ошибочный ответ")
            except Exception:
                if not times:
                    raise
                continue
            times.append(ms)
            if ip is None and ips:
                ip = ips[0]
    finally:
        tr.close()
    return ip, statistics.median(times)


def dns_probe(e, cfg):
    srv_ip = resolve_server(e)
    qtype = 28 if cfg.get("ipv6") else 1
    errors = []
    for proto in ([e["proto"]] if e["proto"] else PROTOS):
        try:
            tr = make_transport(proto, e, srv_ip)
            ip, ms = measure_dns(tr, TARGET, qtype, proto == "https")
            return {"srv_ip": srv_ip, "proto": proto, "ip": ip, "ms": ms}
        except Exception as ex:
            errors.append(f"{PROTO_NAMES[proto]} {short_err(ex)}")
    raise DnsFail("dns не ответил (" + ", ".join(errors) + ")")


# ---------- HTTPS-проба ----------

def http_probe(ip, read_body=True):
    ctx = ssl.create_default_context()
    t0 = time.perf_counter()
    with socket.create_connection((ip, 443), timeout=HTTP_TIMEOUT) as raw:
        with ctx.wrap_socket(raw, server_hostname=TARGET) as s:
            s.settimeout(HTTP_TIMEOUT)
            s.sendall(REQ)
            buf = s.recv(65536)
            ttfb = (time.perf_counter() - t0) * 1000
            m = STATUS_RE.match(buf)
            status = int(m.group(1)) if m else None
            if not read_body:
                return ttfb, status, None
            while (buf and len(buf) < MAX_BYTES and not COUNTRY_RE.search(buf)
                   and time.perf_counter() - t0 < HTTP_TOTAL):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
    c = COUNTRY_RE.search(buf)
    return ttfb, status, (c.group(1).decode().upper() if c else None)


def blank(entry):
    return {"server": entry, "srv_ip": "-", "proto": "-", "ip": "-", "dns": None,
            "ttfb": None, "total": None, "http": None, "geo": "-", "avail": "", "ok": False}


def check(entry, cfg):
    r = blank(entry)
    try:
        d = dns_probe(parse_entry(entry), cfg)
    except DnsFail as ex:
        r["avail"] = f"недоступен: {ex}"
        return r
    r.update(srv_ip=d["srv_ip"], proto=PROTO_NAMES[d["proto"]], dns=d["ms"])
    if not d["ip"]:
        r["avail"] = "недоступен: dns вернул пустой ответ"
        return r
    r["ip"] = d["ip"]
    try:
        first, status, geo = http_probe(d["ip"])
    except ssl.SSLError:
        r["avail"] = "недоступен: TLS ошибка (подмена IP?)"
        return r
    except (socket.timeout, TimeoutError):
        r["avail"] = "недоступен: сайт не ответил"
        return r
    except OSError as ex:
        r["avail"] = f"недоступен: сайт {ex.__class__.__name__}"
        return r
    times = [first]
    for _ in range(REPEATS - 1):
        try:
            times.append(http_probe(d["ip"], read_body=False)[0])
        except Exception:
            break
    r["ttfb"] = statistics.median(times)
    r["total"] = r["dns"] + r["ttfb"]
    r["http"] = status
    r["geo"] = geo or "?"
    if status is not None and status >= 400:
        r["avail"] = f"недоступен: HTTP {status}"
    elif RUS_IS_BAD and r["geo"] == "RUS":
        r["avail"] = "недоступен: регион RUS"
    else:
        r["ok"] = True
        r["avail"] = "доступен" if r["geo"] != "?" else "доступен (гео не определено)"
    return r


def worker(jobs, out, stop, cfg):
    while not stop.is_set():
        try:
            s = jobs.get_nowait()
        except queue.Empty:
            return
        try:
            out.put(check(s, cfg))
        except Exception as e:
            r = blank(s)
            r["avail"] = f"недоступен: ошибка {e.__class__.__name__}: {e}"
            out.put(r)


def load_server_list(defaults):
    path = os.path.join(app_dir(), SERVERS_FILE)
    try:
        with open(path, encoding="utf-8-sig") as f:
            lst = parse_server_text(f.read())
        if lst:
            return lst
    except OSError:
        pass
    return parse_server_text(defaults)