# Generated from literate/09-wallets.md by opensheaf-literate: edit the document, not this file.
"""Key wallets (opensheaf-py): where an owner who prefers convenience to the
maximum security keeps its keys, current and rotation keys, each encrypted
under a passphrase as a file <owner>/<k>.key.enc: a private GitHub
repository, read and written through the GitHub CLI (`gh api`), or a command
of the user's (1Password's op, Bitwarden's bw, pass, ...); passkeys may
unlock them too (osheaf key enroll, module passkey). Also the clipboard,
through which a key goes to and from a password manager such as the
Passwords app of macOS.

The wallet is chosen with --keys (commands that make keys) or --wallet (the
key commands), github:OWNER/REPO or command; or configured: by the
environment variable OPENSHEAF_WALLET (text or JSON), which wins, then by
"keys" of the user's configuration file ~/.config/opensheaf/config.json
($XDG_CONFIG_HOME/opensheaf/config.json), {"wallet": "github:OWNER/REPO"}
or {"wallet": "command", "read": "...", "write": "..."}, then by "keys" of
osheaf.json, which may name a GitHub wallet only: the commands of a command
wallet run on the user's machine, and are never read from an archive."""

import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

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
COMMANDS = ("read", "write", "list", "forget")


def user_config_path():
    """The user's configuration file of opensheaf."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "opensheaf" / "config.json"


def user_config():
    """The `keys` of the user's configuration file, or {}."""
    path = user_config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise WalletError(f"{path}: {e}") from None
    found = data.get("keys") if isinstance(data, dict) else None
    return found if isinstance(found, dict) else {}


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
        return CommandWallet(config or user_config())
    raise WalletError(f"a security level is offline, github:OWNER/REPO or command: {spec}")


def configured(config, *, forbidden=()):
    """The wallet of OPENSHEAF_WALLET, or else of the user's configuration, or else of CONFIG (the `keys`
    of osheaf.json, a GitHub wallet only), or None."""
    config = config if isinstance(config, dict) else {}
    if config.get("wallet") == "command" or any(c in config for c in COMMANDS):
        raise WalletError(f'osheaf.json configures a command wallet ("keys"), whose commands would run on this '
                          f"machine: they are read only from your own configuration. Move \"keys\" to "
                          f"{user_config_path()} (or to {WALLET}), and leave osheaf.json without it")
    env = os.environ.get(WALLET, "").strip()
    if env:
        return parse(env, forbidden=forbidden)
    user = user_config()
    if user.get("wallet"):
        return parse(str(user["wallet"]), user, forbidden=forbidden)
    return parse(config.get("wallet"), forbidden=forbidden)


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
        if info.get("private") is not True or info.get("visibility") != "private":
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
        try:
            return base64.b64decode("".join(str(got["content"]).split()), validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise WalletError(f"{self.name}: {entry_path(owner, kid)} is not a key file") from None

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


CONFIG_HELP = """Your own configuration: ~/.config/opensheaf/config.json ($XDG_CONFIG_HOME/opensheaf/config.json)

{"keys": {"wallet": "github:OWNER/REPO"}}         a key wallet in a private GitHub repository, or
{"keys": {"wallet": "command",                      a key wallet in your password manager:
          "read":   "op read 'op://Private/opensheaf-{owner}-{k}/notesPlain'",
          "write":  "...",                          receives the key file on its standard input
          "list":   "...",                          optional: prints "<owner> <k>" per key
          "forget": "..."}}                         optional: removes a key

The commands run in the shell; {owner} is the owner name, {k} the 16 characters
that name the key, {kind} current or rotation. read prints the key file as it was
written, and fails or prints nothing for a key it does not hold. A command wallet is
read only from this file or from OPENSHEAF_WALLET (the same JSON, or text such as
github:OWNER/REPO), which wins; never from an archive's osheaf.json, which may name a
GitHub wallet only. Examples for 1Password, Bitwarden and pass: chapter 9 of the
literate program of opensheaf-py ("A command of the user's"), and its README,
section "Keys and security levels"."""


class CommandWallet:
    """Keys kept by commands of the user's, configured with {owner}, {k} and {kind}."""

    name = "command"

    def __init__(self, config):
        self.config = config
        if not config.get("read") or not config.get("write"):
            raise WalletError('a command wallet needs "read" and "write" commands, in "keys" of '
                              f"{user_config_path()} or in {WALLET}")

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


def put_key(wallet, owner, key, kind, version, passphrase, passkeys=()):
    """Keep KEY of OWNER, of KIND, committed in VERSION (or None), in WALLET, encrypted under PASSPHRASE
    (None: in clear, for a current key only) and the unlocked PASSKEYS."""
    if passphrase is None and kind == keys.ROTATION:
        raise WalletError("a rotation key is kept in a wallet only encrypted under a passphrase")
    text = keys.key_file_text(key, owner, kind, version, passphrase, passkeys=passkeys)
    wallet.write(owner, key.id, kind, text)
    if (wallet.read(owner, key.id, kind) or "").strip() != text.strip():
        raise WalletError(f"{wallet.name} did not keep the {kind} key {key.did}")


def get_key(wallet, owner, kid, kind, passphrase, passkey=None):
    """The key KID of OWNER, of KIND, from WALLET, or None if it holds none; PASSKEY(owner, passkeys)
    gives the keys of passkeys unlocked, PASSPHRASE() the passphrase, when needed."""
    text = wallet.read(owner, kid, kind)
    if text is None:
        return None
    try:
        try:
            rk = keys.read_key(text)
        except keys.PassphraseNeeded as e:
            keks = passkey(owner, e.passkeys) if passkey is not None and e.passkeys else None
            try:
                rk = keys.read_key(text, keks=keks) if keks else None
            except keys.PassphraseNeeded:
                rk = None
            if rk is None:
                rk = keys.read_key(text, passphrase())
    except keys.KeyStoreError as e:
        raise WalletError(f"{wallet.name} {entry_path(owner, kid)}: {e}") from None
    if rk.owner != owner or rk.kind != kind or rk.key.id != kid:
        raise WalletError(f"{wallet.name} {entry_path(owner, kid)} holds another key: {rk.kind} key "
                          f"{rk.key.did} of {rk.owner}")
    return rk.key


def add_passkey(wallet, owner, kid, passphrase, passkey):
    """Add the unlocked PASSKEY to the key KID of OWNER in WALLET, opened with PASSPHRASE; returns its
    (kind, did:key)."""
    text = read_any(wallet, owner, kid)
    where = f"{wallet.name} {entry_path(owner, kid)}"
    try:
        before = keys.read_key(text, passphrase)
        new = keys.add_passkey(text, passphrase, passkey)
        after = keys.read_key(new, keks={passkey.cred: passkey.kek})
    except keys.KeyStoreError as e:
        raise WalletError(f"{where}: {e}") from None
    if after.key.did != before.key.did or after.kind != before.kind:
        raise WalletError(f"{where}: the key changed when the passkey was added")
    wallet.write(owner, kid, before.kind, new)
    if (wallet.read(owner, kid, before.kind) or "").strip() != new.strip():
        raise WalletError(f"{wallet.name} did not keep the {before.kind} key {before.key.did}")
    return before.kind, before.key.did


def read_any(wallet, owner, kid):
    """The text of the key KID of OWNER in WALLET, of either kind, or ''."""
    return next((t for t in (wallet.read(owner, kid, kind) for kind in keys.KINDS) if t), "")


def describe(text):
    """{field: value} of the lines of a key file before its seed."""
    fields = {}
    for line in text.splitlines():
        name, _, value = line.strip().partition(" ")
        if name in ("encryption", "wrap", "seed"):
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
CLEAR_AFTER = 60.0
_CLEAR = """import hashlib, json, subprocess, sys, time
time.sleep(float(sys.argv[2]))
r = subprocess.run(json.loads(sys.argv[3]), capture_output=True)
if r.returncode == 0 and hashlib.sha256(r.stdout).hexdigest() == sys.argv[1]:
    subprocess.run(json.loads(sys.argv[4]), input=b"")
"""


def clear_later(text, seconds=None):
    """Empty the clipboard after SECONDS (CLEAR_AFTER) if it still holds TEXT."""
    import hashlib
    seconds = CLEAR_AFTER if seconds is None else seconds
    if not seconds:
        return
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    subprocess.Popen([sys.executable, "-c", _CLEAR, digest, str(seconds), json.dumps(PASTE), json.dumps(COPY)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


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
