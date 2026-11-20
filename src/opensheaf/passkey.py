# Generated from literate/09-wallets.md by opensheaf-literate: edit the document, not this file.
"""Passkey unlock (opensheaf-py): the command line's side of the page
https://opensheaf.org/manager/unlock.html, which creates a passkey for
opensheaf.org or derives the PRF secret of one (WebAuthn), and hands the
secret back by a form POST to a one-time listener on 127.0.0.1.

OPENSHEAF_UNLOCK=passphrase never asks the browser."""

import base64
import hmac
import html
import http.server
import re
import secrets
import sys
import threading
import urllib.parse
import webbrowser

from . import keys, names


class UnlockFailed(Exception):
    """The browser gave no secret: an error of the page, no answer in time, or the user gave up."""


PAGE = "https://opensheaf.org/manager/unlock.html"
UNLOCK = "OPENSHEAF_UNLOCK"
TIMEOUT = 120.0
B64URL = re.compile(r"[A-Za-z0-9_-]+")


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def from_b64url(text):
    if not isinstance(text, str) or not B64URL.fullmatch(text):
        raise ValueError("not base64url")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def page_url(mode, port, state, owner, creds=()):
    """The address of the page, in MODE, for the listener on PORT with STATE."""
    query = {"mode": mode, "port": str(port), "state": state, "owner": owner,
             "salt": b64url(keys.passkey_salt(owner))}
    if creds:
        query["cred"] = ",".join(creds)
    return PAGE + "?" + urllib.parse.urlencode(query)


DONE = "osheaf has the key; you can close this tab."
FAILED = "osheaf received the answer: {}. It asks for the passphrase instead; you can close this tab."


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path != "/callback":
            return self._answer(404, "not found")
        if not self.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded"):
            return self._answer(415, "a form is expected")
        n = int(self.headers.get("Content-Length") or 0)
        if n > 16384:
            return self._answer(413, "too long")
        body = self.rfile.read(n).decode("ascii", "replace")
        self._receive(urllib.parse.parse_qs(body, max_num_fields=8))

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        fields = urllib.parse.parse_qs(url.query, max_num_fields=8)
        if url.path != "/callback" or "error" not in fields or "secret" in fields:
            return self._answer(404, "not found")
        self._receive(fields)

    def _receive(self, fields):
        fields = {k: v[0] for k, v in fields.items()}
        if not hmac.compare_digest(fields.get("state", "").encode(), self.server.state.encode()):
            return self._answer(403, "this is not the answer osheaf is waiting for")
        if self.server.result is not None:
            return self._answer(409, "osheaf has its answer already")
        self.server.result = fields
        self._answer(200, FAILED.format(fields["error"][:200]) if "error" in fields else DONE)
        self.server.done.set()

    def _answer(self, status, text):
        page = (f"<!DOCTYPE html><html lang=en><meta charset=utf-8><title>osheaf</title>"
                f"<p style='font-family:sans-serif'>{html.escape(text)}</p></html>").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *args):
        pass


OPEN = webbrowser.open


def ask(mode, owner, creds=(), *, no_browser=False, timeout=None):
    """The fields the page posts back, in MODE (enroll or unlock), for OWNER and its credentials
    CREDS; UnlockFailed if none come."""
    if not names.OWNER_NAME.match(owner) or mode not in ("enroll", "unlock"):
        raise UnlockFailed(f"not an owner name: {owner}")
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    server.state, server.result, server.done = secrets.token_urlsafe(16), None, threading.Event()
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    try:
        url = page_url(mode, server.server_port, server.state, owner, creds)
        what = "create a passkey for" if mode == "enroll" else "unlock with your passkey the keys of"
        print(f"osheaf asks the browser to {what} {owner}:\n  {url}", file=sys.stderr)
        opened = False
        if not no_browser:
            try:
                opened = OPEN(url)
            except Exception:
                opened = False
        if not opened:
            print("open this address in your browser", file=sys.stderr)
        print("waiting for the browser (Ctrl-C to type the passphrase instead)", file=sys.stderr)
        try:
            if not server.done.wait(TIMEOUT if timeout is None else timeout):
                raise UnlockFailed("no answer from the browser in time")
        except KeyboardInterrupt:
            raise UnlockFailed("interrupted") from None
    finally:
        server.shutdown()
        server.server_close()
    if "error" in server.result:
        raise UnlockFailed(f"the page says: {server.result['error'][:200]}")
    return server.result


def _answer(fields, creds=()):
    try:
        secret = from_b64url(fields.get("secret", ""))
        cred = fields.get("cred") or None
        if cred is not None:
            from_b64url(cred)
    except ValueError:
        raise UnlockFailed("the page sent a damaged answer") from None
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
