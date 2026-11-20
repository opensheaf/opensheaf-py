# Generated from literate/09-wallets.md by opensheaf-literate: edit the document, not this file.
"""Key wallets (opensheaf-py): where an owner who prefers convenience to the
maximum security keeps its keys, current and rotation keys, each encrypted
under a passphrase as a file <owner>/<k>.key.enc: a private GitHub
repository, read and written through the GitHub CLI (`gh api`), or a command
of the user's (1Password's op, Bitwarden's bw, pass, ...). Also the clipboard,
through which a key goes to and from a password manager such as the
Passwords app of macOS.

The wallet is chosen with --keys github:OWNER/REPO or --keys command, or
configured in osheaf.json, "keys": {"wallet": "github:OWNER/REPO"} or
{"wallet": "command", "read": "...", "write": "..."}, or by the environment
variable OPENSHEAF_WALLET (the same, as text or JSON), which wins."""

import base64
import json
import os
import re
import shutil
import subprocess
import sys

from . import keys, names


class WalletError(Exception):
    """A wallet that cannot be used, or that refuses a key."""


OFFLINE = "offline"


def risk(where, owner):
    """The risk of keeping the keys of OWNER in the wallet named WHERE (section 6.2)."""
    return (f"security level {where}: the rotation keys and the current keys of {owner} are kept in "
            f"{where}, encrypted under your passphrase. Whoever controls {where} and knows the passphrase "
            "controls the owner: they can sign in its name and change its keys (sections 6.2 and 15.1), and "
            "a current key pulled from the wallet is on every device that pulls it. The maximum level keeps "
            "the rotation keys offline, apart from each other. To move up later, run once "
            "`osheaf owner rotate --keys offline --export DIR`: the rotation keys in the wallet are then "
            "used up, and the new ones are kept offline only.")


WALLET = "OPENSHEAF_WALLET"
REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9._-]+")


def parse(spec, config=None, *, forbidden=()):
    """The wallet SPEC names (github:OWNER/REPO, command, or a JSON object), None for offline;
    CONFIG holds the commands of a command wallet."""
    spec = (spec or "").strip()
    if spec.startswith("{"):
        try:
            config = json.loads(spec)
        except ValueError:
            raise WalletError(f"{WALLET}: not JSON: {spec}") from None
        spec = str(config.get("wallet", ""))
    if spec in ("", OFFLINE):
        return None
    if spec.startswith("github:"):
        repo = spec[len("github:"):]
        if not REPO.fullmatch(repo):
            raise WalletError(f"a GitHub wallet is github:OWNER/REPO: {spec}")
        return GitHubWallet(repo, forbidden)
    if spec == "command":
        return CommandWallet(config or {})
    raise WalletError(f"a security level is offline, github:OWNER/REPO or command: {spec}")


def configured(config, *, forbidden=()):
    """The wallet of OPENSHEAF_WALLET, or else of CONFIG (the `keys` of osheaf.json), or None."""
    config = config if isinstance(config, dict) else {}
    env = os.environ.get(WALLET, "").strip()
    if env:
        return parse(env, config, forbidden=forbidden)
    return parse(config.get("wallet"), config, forbidden=forbidden)


GITHUB_REMOTE = re.compile(r"github\.com[:/]+([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?(?:\s|$)")
PAGES = re.compile(r"https?://([A-Za-z0-9-]+)\.github\.io(?:/([A-Za-z0-9._-]+))?/?")


def archive_repositories(root, base_url):
    """The GitHub repositories (owner/repo, in lowercase) of the archive in ROOT served at BASE_URL."""
    out = set()
    if root is not None and shutil.which("git"):
        r = subprocess.run(["git", "-C", str(root), "remote", "-v"], capture_output=True, text=True)
        if r.returncode == 0:
            out |= {f"{o}/{n}".lower() for o, n in GITHUB_REMOTE.findall(r.stdout + "\n")}
    m = PAGES.match(base_url or "")
    if m:
        out.add(f"{m.group(1)}/{m.group(2) or m.group(1) + '.github.io'}".lower())
    return out


GH = "gh"


def _gh_command():
    exe = GH if os.path.isabs(GH) else shutil.which(GH)
    if not exe or not os.path.exists(exe):
        raise WalletError("the GitHub wallet needs the GitHub CLI, gh (https://cli.github.com): install it, "
                          "then sign in with gh auth login")
    return exe


class GitHubWallet:
    """Keys kept as files <owner>/<k>.key.enc of a private GitHub repository, through gh api."""

    def __init__(self, repo, forbidden=()):
        self.repo = repo
        self.name = f"github:{repo}"
        self.forbidden = {f.lower() for f in forbidden}
        self._signed_in = self._checked = False

    def _api(self, *args, body=None):
        exe = _gh_command()
        if not self._signed_in:
            r = subprocess.run([exe, "auth", "status"], capture_output=True, text=True)
            if r.returncode != 0:
                raise WalletError("gh is not signed in to GitHub: run gh auth login")
            self._signed_in = True
        r = subprocess.run([exe, "api", "-H", "Accept: application/vnd.github+json", *args],
                           input=None if body is None else json.dumps(body), capture_output=True, text=True)
        if r.returncode != 0:
            if "HTTP 404" in r.stderr:
                return None
            raise WalletError(f"gh api {args[-1] if args else ''}: {r.stderr.strip() or r.stdout.strip()}")
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def _contents(self, path=""):
        return f"repos/{self.repo}/contents/{path}".rstrip("/")


    def check_writable(self):
        """Refuse a repository that is missing, public, or the archive's own."""
        self._check_name()
        if self._checked:
            return
        info = self._api(f"repos/{self.repo}")
        if info is None:
            raise WalletError(f"no repository {self.repo} that gh can reach: create it, private, with "
                              f"gh repo create {self.repo} --private")
        if info.get("private") is not True:
            raise WalletError(f"{self.repo} is not a private repository: a wallet must be private")
        if str(info.get("full_name", self.repo)).lower() in self.forbidden:
            raise WalletError(f"{self.repo} is a repository of the archive, which is public: a wallet is "
                              "a repository of its own")
        self._checked = True

    def _check_name(self):
        if self.repo.lower() in self.forbidden:
            raise WalletError(f"{self.repo} is a repository of the archive, which is public: a wallet is "
                              "a repository of its own")


    def read(self, owner, kid, kind):
        """The text of the file of key KID of OWNER, or None."""
        self._check_name()
        got = self._api(self._contents(entry_path(owner, kid)))
        if not isinstance(got, dict) or "content" not in got:
            return None
        return base64.b64decode(got["content"]).decode("utf-8")

    def write(self, owner, kid, kind, text):
        self.check_writable()
        path = entry_path(owner, kid)
        old = self._api(self._contents(path))
        body = {"message": f"opensheaf: {kind} key {kid} of {owner}",
                "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
        if isinstance(old, dict) and old.get("sha"):
            body["sha"] = old["sha"]
        if self._api("-X", "PUT", self._contents(path), "--input", "-", body=body) is None:
            raise WalletError(f"{self.repo} refused {path}")

    def entries(self, owner=None):
        """[(owner, kid)] of the keys the wallet holds, of OWNER or of all owners."""
        self._check_name()
        folders = [owner] if owner else [x["name"] for x in self._api(self._contents()) or []
                                         if x.get("type") == "dir" and names.OWNER_NAME.match(x["name"])]
        out = []
        for o in folders:
            for x in self._api(self._contents(o)) or []:
                if x.get("type") == "file" and x["name"].endswith(ENTRY_SUFFIX):
                    out.append((o, x["name"][:-len(ENTRY_SUFFIX)]))
        return out

    def forget(self, owner, kid, kind):
        self.check_writable()
        path = entry_path(owner, kid)
        old = self._api(self._contents(path))
        if isinstance(old, dict) and old.get("sha"):
            self._api("-X", "DELETE", self._contents(path), "--input", "-",
                      body={"message": f"opensheaf: forget {kind} key {kid} of {owner}", "sha": old["sha"]})


ENTRY_SUFFIX = ".key.enc"


def entry_path(owner, kid):
    """The path of the file of key KID of OWNER in a wallet."""
    if not names.OWNER_NAME.match(owner) or not re.fullmatch(r"[a-z2-7]{16}", kid):
        raise WalletError(f"not an owner name and a key: {owner} {kid}")
    return f"{owner}/{kid}{ENTRY_SUFFIX}"


class CommandWallet:
    """Keys kept by commands of the user's, configured with {owner}, {k} and {kind}."""

    name = "command"

    def __init__(self, config):
        self.config = config
        if not config.get("read") or not config.get("write"):
            raise WalletError('a command wallet needs "read" and "write" commands, in "keys" of '
                              f"osheaf.json or in {WALLET}")

    def _run(self, what, owner="", kid="", kind="", text=None):
        if owner or kid:
            entry_path(owner, kid)
        if kind and kind not in keys.KINDS:
            raise WalletError(f"unknown kind of key: {kind}")
        command = self.config[what].replace("{owner}", owner).replace("{k}", kid).replace("{kind}", kind)
        return subprocess.run(command, shell=True, input=text, capture_output=True, text=True)

    def check_writable(self):
        pass

    def read(self, owner, kid, kind):
        r = self._run("read", owner, kid, kind)
        return r.stdout if r.returncode == 0 and r.stdout.strip() else None

    def write(self, owner, kid, kind, text):
        r = self._run("write", owner, kid, kind, text)
        if r.returncode != 0:
            raise WalletError(f"the write command of the wallet failed: {r.stderr.strip()}")

    def entries(self, owner=None):
        if not self.config.get("list"):
            raise WalletError('this command wallet has no "list" command')
        r = self._run("list")
        if r.returncode != 0:
            raise WalletError(f"the list command of the wallet failed: {r.stderr.strip()}")
        out = []
        for line in r.stdout.splitlines():
            parts = line.replace("/", " ").split()
            if len(parts) >= 2 and names.OWNER_NAME.match(parts[0]) and (owner in (None, parts[0])):
                out.append((parts[0], parts[1].removesuffix(ENTRY_SUFFIX)))
        return out

    def forget(self, owner, kid, kind):
        if not self.config.get("forget"):
            raise WalletError('this command wallet has no "forget" command: remove the key with your '
                              "password manager")
        r = self._run("forget", owner, kid, kind)
        if r.returncode != 0:
            raise WalletError(f"the forget command of the wallet failed: {r.stderr.strip()}")


def put_key(wallet, owner, key, kind, version, passphrase):
    """Keep KEY of OWNER, of KIND, committed in VERSION (or None), in WALLET, encrypted under PASSPHRASE
    (None: in clear, for a current key only)."""
    if passphrase is None and kind == keys.ROTATION:
        raise WalletError("a rotation key is kept in a wallet only encrypted under a passphrase")
    text = keys.key_file_text(key, owner, kind, version, passphrase)
    wallet.write(owner, key.id, kind, text)
    if (wallet.read(owner, key.id, kind) or "").strip() != text.strip():
        raise WalletError(f"{wallet.name} did not keep the {kind} key {key.did}")


def get_key(wallet, owner, kid, kind, passphrase):
    """The key KID of OWNER, of KIND, from WALLET, or None if it holds none; PASSPHRASE() gives the
    passphrase when needed."""
    text = wallet.read(owner, kid, kind)
    if text is None:
        return None
    try:
        try:
            rk = keys.read_key(text)
        except keys.PassphraseNeeded:
            rk = keys.read_key(text, passphrase())
    except keys.KeyStoreError as e:
        raise WalletError(f"{wallet.name} {entry_path(owner, kid)}: {e}") from None
    if rk.owner != owner or rk.kind != kind or rk.key.id != kid:
        raise WalletError(f"{wallet.name} {entry_path(owner, kid)} holds another key: {rk.kind} key "
                          f"{rk.key.did} of {rk.owner}")
    return rk.key


def read_any(wallet, owner, kid):
    """The text of the key KID of OWNER in WALLET, of either kind, or ''."""
    return next((t for t in (wallet.read(owner, kid, kind) for kind in keys.KINDS) if t), "")


def describe(text):
    """{field: value} of the lines of a key file before its seed."""
    fields = {}
    for line in text.splitlines():
        name, _, value = line.strip().partition(" ")
        if name in ("encryption", "seed"):
            break
        fields.setdefault(name, value.strip())
    return fields


def listing(wallet, owner=None):
    """[(owner, kid, kind, did:key, version)] of the keys WALLET holds."""
    out = []
    for o, kid in wallet.entries(owner):
        f = describe(read_any(wallet, o, kid))
        out.append((o, kid, f.get("kind", "?"), f.get("key", "?"), f.get("version", "")))
    return out


COPY, PASTE = ["pbcopy"], ["pbpaste"]


def to_clipboard(text):
    """Copy TEXT to the clipboard."""
    if not shutil.which(COPY[0]):
        raise WalletError(f"no clipboard command {COPY[0]} on this system: use --stdout")
    if subprocess.run(COPY, input=text, text=True).returncode != 0:
        raise WalletError("the text could not be copied to the clipboard")


def from_clipboard():
    """The text of the clipboard."""
    if not shutil.which(PASTE[0]):
        raise WalletError(f"no clipboard command {PASTE[0]} on this system: use --stdin")
    r = subprocess.run(PASTE, capture_output=True, text=True)
    if r.returncode != 0:
        raise WalletError("the clipboard could not be read")
    return r.stdout
