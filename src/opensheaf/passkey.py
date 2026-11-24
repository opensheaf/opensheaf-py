# Generated from literate/09-wallets.md by opensheaf-literate: edit the document, not this file.
"""Passkey unlock (opensheaf-py): the command line's side of the page
https://unlock.opensheaf.org/ (UNLOCK_PAGE), which creates a passkey for
unlock.opensheaf.org or derives the PRF secret of one (WebAuthn), and hands
the secret back to a one-time listener on 127.0.0.1, encrypted and
authenticated to a one-time X25519 key of the listener (X25519,
HKDF-SHA256, XOR and HMAC-SHA256).

OPENSHEAF_UNLOCK=passphrase never asks the browser."""

import base64
import hashlib
import hmac
import html
import http.server
import os
import re
import secrets
import socket
import sys
import threading
import urllib.parse
import webbrowser

from nacl import bindings, public

from . import keys, names


class UnlockFailed(Exception):
    """The browser gave no secret: an error of the page, no answer in time, or the user gave up."""


UNLOCK_PAGE = f"https://{keys.PASSKEY_RP}/"
UNLOCK = "OPENSHEAF_UNLOCK"
TIMEOUT = 120.0
STILL = 10.0
B64URL = re.compile(r"[A-Za-z0-9_-]+")


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def from_b64url(text):
    if not isinstance(text, str) or not B64URL.fullmatch(text) or len(text) % 4 == 1:
        raise ValueError("not base64url")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def page_url(mode, port, state, pk, owner, creds=()):
    """The address of the page, in MODE, for the listener on PORT with STATE and public key PK."""
    fragment = {"mode": mode, "port": str(port), "state": state, "pk": b64url(pk), "owner": owner}
    if creds:
        fragment["cred"] = ",".join(creds)
    return UNLOCK_PAGE + "#" + urllib.parse.urlencode(fragment)


def start_url(port):
    """The address that the command opens, and prints: the listener on PORT, which sends the browser on."""
    return f"http://127.0.0.1:{port}/start"


CODE_LABEL = b"opensheaf unlock code v1"


def confirmation_code(state, pk):
    """The six digits that the page shows for the listener with STATE and public key PK, as `123 456`."""
    n = int.from_bytes(hashlib.sha256(CODE_LABEL + state.encode("utf-8") + bytes(pk)).digest()[:4], "big")
    digits = f"{n % 1000000:06d}"
    return f"{digits[:3]} {digits[3:]}"


HAND_OFF_INFO = b"opensheaf unlock hand-off v2"


def hkdf(ikm, salt, info, length):
    """HKDF-SHA256 (RFC 5869): LENGTH bytes from IKM, SALT and INFO."""
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    out, block = b"", b""
    for i in range(1, -(-length // 32) + 1):
        block = hmac.new(prk, block + info + bytes([i]), hashlib.sha256).digest()
        out += block
    return out[:length]


def _hand_off_keys(private, other, state):
    shared = bindings.crypto_scalarmult(bytes(private), bytes(other))
    both = hkdf(shared, state.encode("utf-8"), HAND_OFF_INFO, 64)
    return both[:32], both[32:]


def associated_data(mode, owner, cred, pk, epk):
    """What the tag of the hand-off covers besides the ciphertext."""
    return f"{mode}|{owner}|{cred}|{b64url(pk)}|{b64url(epk)}".encode("utf-8")


def _tag(mac_key, aad, ct):
    return hmac.new(mac_key, aad + ct, hashlib.sha256).digest()


def seal(secret, pk, state, mode, owner, cred, ephemeral=None):
    """(epk, ct, tag): SECRET encrypted and authenticated to the X25519 public key PK, as the page does,
    with the one-time private key EPHEMERAL (a fresh one by default)."""
    ephemeral = ephemeral or public.PrivateKey.generate()
    epk = bytes(ephemeral.public_key)
    enc, mac = _hand_off_keys(ephemeral, pk, state)
    ct = bytes(a ^ b for a, b in zip(secret, enc))
    return epk, ct, _tag(mac, associated_data(mode, owner, cred, pk, epk), ct)


def unseal(private, epk, ct, tag, state, mode, owner, cred):
    """The secret that the page encrypted as CT, with its public key EPK and the tag TAG, to the key pair
    PRIVATE; ValueError if anything was changed."""
    if len(epk) != 32 or len(ct) != 32 or len(tag) != 32:
        raise ValueError("not a hand-off of 32 bytes")
    enc, mac = _hand_off_keys(private, epk, state)
    aad = associated_data(mode, owner, cred, bytes(private.public_key), epk)
    if not hmac.compare_digest(_tag(mac, aad, ct), tag):
        raise ValueError("the answer of the page is not authentic")
    return bytes(a ^ b for a, b in zip(ct, enc))


DONE = "osheaf has the key. You can close this tab."
FAILED = "osheaf did not get the key ({}): it asks for the passphrase instead. You can close this tab."
NO_X25519 = ("this browser has no X25519 in WebCrypto, and cannot hand the key to osheaf securely (known to "
             "work: Safari 17+, Chrome 133+, Firefox 130+); osheaf uses the passphrase")
ANSWER = ({"state", "epk", "ct", "tag", "cred"}, {"state", "error"})
TWICE = ("the address of osheaf was opened twice: another program may have read it, so osheaf does not "
         "wait for the browser (if it was you, try again, and open the address once)")
OTHER_USER = "another user of this computer"
SAME_USER_ONLY = sys.platform.startswith("linux")


def _hex_address(host):
    """The forms of the IPv4 address HOST in /proc/net/tcp and in /proc/net/tcp6 (as ::ffff:HOST)."""
    word = socket.inet_aton(host)[::-1].hex().upper()
    return {word, "0000000000000000FFFF0000" + word}


def peer_uid(host, port, server_port, tables=("/proc/net/tcp", "/proc/net/tcp6")):
    """The uid of the socket at HOST:PORT connected to HOST:SERVER_PORT, from the kernel's TCP TABLES;
    None if none is found."""
    here = _hex_address(host)
    for table in tables:
        try:
            with open(table, encoding="ascii") as f:
                lines = f.read().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            f = line.split()
            if len(f) < 8 or f[3] != "01":
                continue
            (local, lport), (remote, rport) = f[1].split(":"), f[2].split(":")
            if (local in here and remote in here and int(lport, 16) == port
                    and int(rport, 16) == server_port):
                return int(f[7])
    return None


PEER_UID = peer_uid


class _Handler(http.server.BaseHTTPRequestHandler):
    timeout = 5

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path not in ("/start", "/callback"):
            return self._answer(404, "not found")
        if SAME_USER_ONLY:
            host, port = self.client_address[:2]
            if PEER_UID(host, port, self.server.server_port) != os.getuid():
                print(f"Warning: {OTHER_USER} asked osheaf for {url.path}: refused.", file=sys.stderr)
                return self._answer(403, f"osheaf answers only the user who runs it, not {OTHER_USER}")
        if url.path == "/start":
            return self._start()
        try:
            fields = urllib.parse.parse_qs(url.query, max_num_fields=6, strict_parsing=True)
        except ValueError:
            fields = {}
        if set(fields) not in ANSWER or any(len(v) != 1 for v in fields.values()) or len(url.query) > 8192:
            return self._answer(400, "this is not an answer of the page (if osheaf or the page was just "
                                     "updated, update the other too)")
        fields = {k: v[0] for k, v in fields.items()}
        if not hmac.compare_digest(fields["state"].encode(), self.server.state.encode()):
            return self._answer(403, "this is not the answer osheaf is waiting for")
        with self.server.lock:
            if self.server.result is not None:
                return self._answer(409, "osheaf has its answer already")
            self.server.result = result = self._open(fields)
        if "error" in result:
            error = NO_X25519 if result["error"] == "x25519-unavailable" else result["error"][:200]
            self._answer(200, FAILED.format(error))
        else:
            self._answer(200, DONE)
        self.server.done.set()

    def _start(self):
        s = self.server
        with s.lock:
            s.started += 1
            if s.started > 1 and s.result is None:
                s.result = {"abort": TWICE}
                s.done.set()
        if s.started > 1:
            return self._answer(409, TWICE)
        self.send_response(302)
        self.send_header("Location", s.page)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _open(self, fields):
        if "error" in fields:
            return {"error": fields["error"][:200] or "an error"}
        s = self.server
        try:
            epk, ct, tag = from_b64url(fields["epk"]), from_b64url(fields["ct"]), from_b64url(fields["tag"])
            from_b64url(fields["cred"])
            secret = unseal(s.key, epk, ct, tag, s.state, s.mode, s.owner, fields["cred"])
        except Exception:
            return {"error": "the page sent a damaged answer"}
        return {"cred": fields["cred"], "secret": secret}

    def _answer(self, status, text):
        page = (f"<!DOCTYPE html><html lang=en><meta charset=utf-8><title>osheaf</title>"
                f"<p style='font-family:sans-serif'>{html.escape(text)}</p></html>").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *args):
        pass


OPEN = webbrowser.open


def ask(mode, owner, creds=(), *, no_browser=False, timeout=None, ctrl_c="type the passphrase instead"):
    """The answer of the page ({cred, secret} or {error}), in MODE (enroll or unlock), for OWNER and
    CREDS (to unlock with, or to exclude when enrolling); UnlockFailed if none comes."""
    if not names.OWNER_NAME.fullmatch(owner) or mode not in ("enroll", "unlock"):
        raise UnlockFailed(f"not an owner name: {owner}")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    server.state, server.result, server.done = secrets.token_urlsafe(16), None, threading.Event()
    server.mode, server.owner, server.lock, server.started = mode, owner, threading.Lock(), 0
    server.key = public.PrivateKey.generate()
    pk = bytes(server.key.public_key)
    server.page = page_url(mode, server.server_port, server.state, pk, owner, creds)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    try:
        url = start_url(server.server_port)
        what = (f"create a passkey for {names.short(owner)}" if mode == "enroll"
                else f"unlock the keys of {names.short(owner)} with your passkey")
        opened = False
        if not no_browser:
            print(f"Opening the browser to {what} (Touch ID)…", file=sys.stderr)
            try:
                opened = OPEN(url)
            except Exception:
                opened = False
        if not opened:
            print(f"Go to this address in your browser, to {what} (Touch ID):\n  {url}", file=sys.stderr)
        print(f"Check that the browser shows the code {confirmation_code(server.state, pk)}", file=sys.stderr)
        print(f"Waiting for the browser (Ctrl-C to {ctrl_c})…", file=sys.stderr)
        limit = TIMEOUT if timeout is None else timeout
        try:
            if opened and limit > STILL and not server.done.wait(STILL):
                if not server.started:
                    print(f"Still waiting… if the browser did not open, go to:\n  {url}", file=sys.stderr)
                limit -= STILL
            if not server.done.wait(limit):
                raise UnlockFailed("no answer from the browser in time")
        except KeyboardInterrupt:
            raise UnlockFailed("interrupted") from None
    finally:
        server.shutdown()
        server.server_close()
        server.key = server.page = None
    if "abort" in server.result:
        print(f"Warning: {server.result['abort']}.", file=sys.stderr)
        raise UnlockFailed(server.result["abort"])
    if "error" in server.result:
        error = server.result["error"]
        raise UnlockFailed(NO_X25519 if error == "x25519-unavailable" else f"the page says: {error[:200]}")
    return server.result


def _answer(result, creds=()):
    secret, cred = result.get("secret") or b"", result.get("cred")
    if len(secret) != 32:
        raise UnlockFailed("the page sent a secret that is not 32 bytes")
    if creds and cred is not None and cred not in creds:
        raise UnlockFailed("the page used another passkey than those asked for")
    return cred, secret


def enroll(owner, exclude=(), **kw):
    """(the credential of a new passkey of OWNER, its PRF secret); EXCLUDE, the credentials it has."""
    cred, secret = _answer(ask("enroll", owner, exclude, **kw))
    if cred is None or cred in exclude:
        raise UnlockFailed("the page sent no new credential")
    return cred, secret


def unlock(owner, creds, **kw):
    """(the credential used, or None, and the PRF secret) of one of the passkeys CREDS of OWNER."""
    return _answer(ask("unlock", owner, creds, **kw), creds)
