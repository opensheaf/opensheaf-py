# Generated from literate/09-wallets.md by opensheaf-literate: edit the document, not this file.
"""Passkey unlock (opensheaf-py): the command line's side of the page
https://opensheaf.org/manager/unlock.html, which creates a passkey for
opensheaf.org or derives the PRF secret of one (WebAuthn), and hands the
secret back to a one-time listener on 127.0.0.1, encrypted to a one-time
X25519 key of the listener (X25519, HKDF-SHA256, XOR).

OPENSHEAF_UNLOCK=passphrase never asks the browser."""

import base64
import hashlib
import hmac
import html
import http.server
import re
import secrets
import sys
import threading
import urllib.parse
import webbrowser

from nacl import bindings, public

from . import keys, names


class UnlockFailed(Exception):
    """The browser gave no secret: an error of the page, no answer in time, or the user gave up."""


PAGE = "https://opensheaf.org/manager/unlock.html"
UNLOCK = "OPENSHEAF_UNLOCK"
TIMEOUT = 120.0
STILL = 10.0
B64URL = re.compile(r"[A-Za-z0-9_-]+")


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def from_b64url(text):
    if not isinstance(text, str) or not B64URL.fullmatch(text):
        raise ValueError("not base64url")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def page_url(mode, port, state, pk, owner, creds=()):
    """The address of the page, in MODE, for the listener on PORT with STATE and public key PK."""
    query = {"mode": mode, "port": str(port), "state": state, "pk": b64url(pk), "owner": owner,
             "salt": b64url(keys.passkey_salt(owner))}
    if creds:
        query["cred"] = ",".join(creds)
    return PAGE + "?" + urllib.parse.urlencode(query)


HAND_OFF_INFO = b"opensheaf unlock hand-off v1"


def hkdf(ikm, salt, info, length):
    """HKDF-SHA256 (RFC 5869): LENGTH bytes from IKM, SALT and INFO."""
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    out, block = b"", b""
    for i in range(1, -(-length // 32) + 1):
        block = hmac.new(prk, block + info + bytes([i]), hashlib.sha256).digest()
        out += block
    return out[:length]


def _pad(private, other, state, length):
    shared = bindings.crypto_scalarmult(bytes(private), bytes(other))
    return hkdf(shared, state.encode("utf-8"), HAND_OFF_INFO, length)


def seal(secret, pk, state, ephemeral=None):
    """(epk, ct): SECRET encrypted to the X25519 public key PK, as the page does, with the one-time
    private key EPHEMERAL (a fresh one by default)."""
    ephemeral = ephemeral or public.PrivateKey.generate()
    pad = _pad(ephemeral, pk, state, len(secret))
    return bytes(ephemeral.public_key), bytes(a ^ b for a, b in zip(secret, pad))


def unseal(private, epk, ct, state):
    """The secret that the page encrypted as CT, with its public key EPK, to the key pair PRIVATE."""
    if len(epk) != 32 or len(ct) != 32:
        raise ValueError("not a hand-off of 32 bytes")
    pad = _pad(private, epk, state, len(ct))
    return bytes(a ^ b for a, b in zip(ct, pad))


DONE = "osheaf has the key. You can close this tab."
FAILED = "osheaf did not get the key ({}): it asks for the passphrase instead. You can close this tab."
NO_X25519 = ("this browser cannot hand the key to osheaf securely; use Safari 17+, Chrome 133+ "
             "or Firefox 130+, or the passphrase")
ANSWER = ({"state", "epk", "ct", "cred"}, {"state", "epk", "ct"}, {"state", "error"})


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path != "/callback":
            return self._answer(404, "not found")
        try:
            fields = urllib.parse.parse_qs(url.query, max_num_fields=6, strict_parsing=True)
        except ValueError:
            fields = {}
        if set(fields) not in ANSWER or any(len(v) != 1 for v in fields.values()) or len(url.query) > 8192:
            return self._answer(400, "this is not an answer of the page")
        fields = {k: v[0] for k, v in fields.items()}
        if not hmac.compare_digest(fields["state"].encode(), self.server.state.encode()):
            return self._answer(403, "this is not the answer osheaf is waiting for")
        if self.server.result is not None:
            return self._answer(409, "osheaf has its answer already")
        self.server.result = result = self._open(fields)
        if "error" in result:
            error = NO_X25519 if result["error"] == "x25519-unavailable" else result["error"][:200]
            self._answer(200, FAILED.format(error))
        else:
            self._answer(200, DONE)
        self.server.done.set()

    def _open(self, fields):
        if "error" in fields:
            return {"error": fields["error"][:200] or "an error"}
        try:
            epk, ct = from_b64url(fields["epk"]), from_b64url(fields["ct"])
            if "cred" in fields:
                from_b64url(fields["cred"])
            secret = unseal(self.server.key, epk, ct, self.server.state)
        except Exception:
            return {"error": "the page sent a damaged answer"}
        return {"cred": fields.get("cred"), "secret": secret}

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
    its credentials CREDS; UnlockFailed if none comes."""
    if not names.OWNER_NAME.match(owner) or mode not in ("enroll", "unlock"):
        raise UnlockFailed(f"not an owner name: {owner}")
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    server.state, server.result, server.done = secrets.token_urlsafe(16), None, threading.Event()
    server.key = public.PrivateKey.generate()
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    try:
        url = page_url(mode, server.server_port, server.state, bytes(server.key.public_key), owner, creds)
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
        print(f"Waiting for the browser (Ctrl-C to {ctrl_c})…", file=sys.stderr)
        limit = TIMEOUT if timeout is None else timeout
        try:
            if opened and limit > STILL and not server.done.wait(STILL):
                print(f"Still waiting… if the browser did not open, go to:\n  {url}", file=sys.stderr)
                limit -= STILL
            if not server.done.wait(limit):
                raise UnlockFailed("no answer from the browser in time")
        except KeyboardInterrupt:
            raise UnlockFailed("interrupted") from None
    finally:
        server.shutdown()
        server.server_close()
        server.key = None
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


def enroll(owner, **kw):
    """(the credential of a new passkey of OWNER, its PRF secret)."""
    cred, secret = _answer(ask("enroll", owner, **kw))
    if cred is None:
        raise UnlockFailed("the page sent no credential")
    return cred, secret


def unlock(owner, creds, **kw):
    """(the credential used, or None, and the PRF secret) of one of the passkeys CREDS of OWNER."""
    return _answer(ask("unlock", owner, creds, **kw), creds)
