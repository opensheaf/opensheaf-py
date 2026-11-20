Key wallets: keys kept for convenience
======================================

The safest place for the rotation keys of an owner is offline: on paper,
on USB keys or hardware tokens kept apart from the devices and from each
other (section 6.2), and the safest place for a current key is the one
device that made it. [Chapter 7](07-keys.md) does that, and it is the
default of the tools. It is also demanding: a USB key to find for every
change of keys, a new current key, and a new version of the key log, for
every new laptop. An owner starting out, testing the tools, or working
alone on a few papers may prefer to keep its keys where its other secrets
are, at a known, lower level of security. A *key wallet* is such a place,
and this chapter is the module `wallet.py`, which keeps keys in one, and
the module `passkey.py`, through which a passkey, with Touch ID, opens
them instead of the passphrase (the last section).

    # in src/opensheaf/wallet.py:
    <<wallet: the docstring and the imports>>


    <<wallet: security levels and their risk>>


    <<wallet: choosing a wallet>>


    <<wallet: the archive's own repositories>>


    <<wallet: a private GitHub repository>>


    <<wallet: a command of the user's>>


    <<wallet: keys in and out of a wallet>>


    <<wallet: the clipboard>>

The module uses the keys of [chapter 7](07-keys.md), and nothing outside
the standard library: the wallets are reached through commands, `gh` or
the user's.

    # in wallet: the docstring and the imports:
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

Security levels
---------------

The commands that make keys, `owner init` and `owner rotate`, take a
*security level* with `--keys`:

- `offline`, the default and the maximum: the rotation keys are exported
  once, to files in a folder outside the archive (`--export DIR`) and to
  printed sheets, and never kept on a device; the current key stays on the
  device that made it ([chapter 7](07-keys.md)).
- `github:OWNER/REPO`: the rotation keys and the current keys are kept in a
  private GitHub repository, separate from the archive's, encrypted under a
  passphrase; the GitHub account, protected by its own sign-in (a passkey,
  two factors), guards the files, the passphrase their content.
- `command`: the same, in a password manager or a vault the user already
  has, through a command configured once.

At a wallet level the rotation keys are always encrypted; so are the
current keys, unless `--plain-current` (they are then protected by the
wallet alone, which some vaults encrypt themselves). `--export` may be
given as well, which keeps an offline copy of the rotation keys besides.

Section 6.2 asks rotation keys to be kept apart, and the tools to state
the risk of a weaker setup. A wallet keeps them together, with the current
keys, behind one account and one passphrase; and a current key in a wallet
reaches every device that pulls it, where section 6.2 has one key per
device. The statement says so, and says how to move up: one `owner rotate
--keys offline --export DIR`, signed with the rotation keys read from the
wallet, commits new rotation keys kept offline only, after which those of
the wallet are used up and sign nothing (section 6.2). It is printed on
the standard error whenever keys are put into a wallet.

    # in wallet: security levels and their risk:
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

Choosing a wallet
-----------------

A wallet is named as `--keys` (or `--wallet`) names it:
`github:OWNER/REPO`, or `command`, whose commands are given by the
configuration. Three places may configure it, the first that does wins:

1. the environment variable `OPENSHEAF_WALLET`, as text
   (`github:OWNER/REPO`, `offline`, `command`) or as JSON (an object like
   those below);
2. `keys` in the user's configuration file, `config.json` in the folder
   `opensheaf` of `$XDG_CONFIG_HOME` (by default `~/.config`), which
   holds nothing else for now;
3. `keys` in the configuration of the archive, `osheaf.json`, which may
   name a GitHub wallet, and nothing else.

```json
"keys": {"wallet": "github:mgubi/opensheaf-keys"}
"keys": {"wallet": "command",
         "read": "op read 'op://Private/opensheaf-{owner}-{k}/notesPlain'",
         "write": "op item create --vault Private --category 'Secure Note' --title 'opensheaf-{owner}-{k}' \"notesPlain=$(cat)\""}
```

The commands of a command wallet are run by the shell, on the user's
machine; an archive is a folder that anyone may have written, cloned
from anywhere. So they are read only from the user's own configuration,
the file or the environment, never from `osheaf.json`: an `osheaf.json`
that holds a command wallet is refused, with a message that says where to
move it, before anything is run. A GitHub wallet in `osheaf.json` runs
nothing but `gh`, on a repository that must be private and is not the
archive's.

`forbidden` lists the repositories of the archive itself, which the GitHub
wallet refuses (below).

    # in wallet: choosing a wallet:
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

The archive's own repositories
------------------------------

An archive is public, and so is everything in its repository, history
included (section 15.4); a wallet in the archive's repository, or in the
repository that serves its website, would publish the encrypted keys, left
to a guess of the passphrase. The repositories of the archive are those of
its git remotes on GitHub, and that of its GitHub Pages address, when its
`baseUrl` is one (`https://OWNER.github.io/REPO/`, or
`https://OWNER.github.io/` for the repository `OWNER.github.io`); an
archive served from a domain of its own names its repository in its git
remote, if it has one.

    # in wallet: the archive's own repositories:
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

A private GitHub repository
---------------------------

The GitHub wallet keeps each key as a file `<owner>/<k>.key.enc` of a
private repository, the file of [chapter 7](07-keys.md) with its `kind`,
and never anything else. It reads and writes them through the GitHub CLI,
`gh`, which holds the user's sign-in to GitHub (made once with `gh auth
login`, through the browser, with a passkey or two factors): the tools
never see a GitHub password or token. Every call is one of the REST API
of [repository contents](https://docs.github.com/en/rest/repos/contents),
through `gh api`: `GET repos/{owner}/{repo}/contents/{path}` reads a file
(its content in base64, and its `sha`), `PUT` writes one (its content in
base64, and the `sha` of the file it replaces, if any), and `DELETE`
removes one, which only `osheaf key forget --from-wallet` asks for. A request
body goes on the standard input of `gh` (`--input -`), never on its
command line. The variable `GH` names the command, so that the tests can
put a double of their own in its place.

    # in wallet: a private GitHub repository:
    GH = "gh"


    def _gh_command():
        exe = GH if os.path.isabs(GH) else shutil.which(GH)
        if not exe or not os.path.exists(exe):
            raise WalletError("the GitHub wallet needs the GitHub CLI, gh (https://cli.github.com): install it, "
                              "then sign in with gh auth login")
        return exe

Before its first call the wallet checks that `gh` is there and signed in,
so that the user is told what to do rather than shown an error of the API.
A file that is not there is a 404 of the API, which `gh` reports on its
standard error; any other failure is an error, with what `gh` said.

    # in wallet: a private GitHub repository:
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

Before anything is written, the repository is checked, once per command:
it must exist (the tools never create one: `gh repo create OWNER/REPO
--private` does), be private, and not be a repository of the archive.
Private means both fields of the API that say so: `private` true and
`visibility` `private`, not `internal`, which every member of an
enterprise can read.
The last is checked without a call too, by name, so that even reading
from the archive's repository is refused.

    # in wallet: a private GitHub repository:
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

Reading, writing, listing and forgetting are then a call or two each. A
file written again (the same key pushed with a new passphrase, say)
replaces the one there, whose `sha` the API requires; a key is never
removed but by `forget`.

    # in wallet: a private GitHub repository:
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

The files are named the same in every wallet that has files.

    # in wallet: a private GitHub repository:
    ENTRY_SUFFIX = ".key.enc"


    def entry_path(owner, kid):
        """The path of the file of key KID of OWNER in a wallet."""
        if not names.OWNER_NAME.match(owner) or not re.fullmatch(r"[a-z2-7]{16}", kid):
            raise WalletError(f"not an owner name and a key: {owner} {kid}")
        return f"{owner}/{kid}{ENTRY_SUFFIX}"

A command of the user's
-----------------------

A user who keeps its secrets in a password manager with a command line
(1Password's `op`, Bitwarden's `bw`, the standard Unix password manager
`pass`) configures the commands that read and write a key, in its
configuration file or in `OPENSHEAF_WALLET` (never in `osheaf.json`,
above). Each is a shell command in which
`{owner}`, `{k}` and `{kind}` stand for the owner name, the 16 characters
that name the key, and `current` or `rotation`. `read` prints the text of
the key, as written, on its standard output, and fails, or prints nothing,
for a key it does not hold; `write` receives the text on its standard
input. Two more are optional: `list`, which prints the keys held, one per
line, `<owner> <k>` (or `<owner>/<k>`), and `forget`, which removes one.
The text is always the file of [chapter 7](07-keys.md), its seed
encrypted under the passphrase for a rotation key, so that what the
command passes along, even on a command line, is never a key in clear.

```json
1Password:
  "read":  "op read 'op://Private/opensheaf-{owner}-{k}/notesPlain'",
  "write": "op item create --vault Private --category 'Secure Note' --title 'opensheaf-{owner}-{k}' \"notesPlain=$(cat)\"",
  "forget": "op item delete --vault Private 'opensheaf-{owner}-{k}'"
Bitwarden (signed in, BW_SESSION set):
  "read":  "bw get notes 'opensheaf-{owner}-{k}'",
  "write": "bw get template item | jq --arg n \"$(cat)\" '.type=2 | .secureNote.type=0 | .name=\"opensheaf-{owner}-{k}\" | .notes=$n' | bw encode | bw create item"
pass:
  "read":  "pass show opensheaf/{owner}/{k}",
  "write": "pass insert -m -f opensheaf/{owner}/{k}",
  "list":  "cd ~/.password-store/opensheaf && ls -d */*.gpg | sed 's/.gpg$//'",
  "forget": "pass rm -f opensheaf/{owner}/{k}"
```

The values substituted are base32 characters and the two kinds, never
anything the shell would read as syntax; they are checked anyway.

    # in wallet: a command of the user's:
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

Keys in and out of a wallet
---------------------------

Whatever the wallet, a key goes in as the file of [chapter 7](07-keys.md),
and is read back at once: a wallet that accepts and forgets, or changes
the text, is found before the key log commits a key kept only there.

    # in wallet: keys in and out of a wallet:
    def put_key(wallet, owner, key, kind, version, passphrase, passkeys=()):
        """Keep KEY of OWNER, of KIND, committed in VERSION (or None), in WALLET, encrypted under PASSPHRASE
        (None: in clear, for a current key only) and the unlocked PASSKEYS."""
        if passphrase is None and kind == keys.ROTATION:
            raise WalletError("a rotation key is kept in a wallet only encrypted under a passphrase")
        text = keys.key_file_text(key, owner, kind, version, passphrase, passkeys=passkeys)
        wallet.write(owner, key.id, kind, text)
        if (wallet.read(owner, key.id, kind) or "").strip() != text.strip():
            raise WalletError(f"{wallet.name} did not keep the {kind} key {key.did}")

A key read from a wallet is checked as any key read back: its seed gives
the key its file names, the owner and the kind are those asked for, and
its name is the one it is filed under. `passphrase` is a function, called
only when an encrypted key is met, so that a command asks for the
passphrase once, and not at all if nothing is encrypted. `passkey`, if
given, is called first, for a key that passkeys can unlock: with the
owner and these passkeys, it returns the key-encryption keys of those it
could unlock (by credential), or None; the passphrase is asked only if
none opens the key.

    # in wallet: keys in and out of a wallet:
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

`osheaf key enroll` adds a passkey to the keys a wallet holds: each file
is opened with the passphrase, given one more wrap (chapter 7), checked to
open with the passkey alone and to be the same key, written back in place
of the old file, and read back.

    # in wallet: keys in and out of a wallet:
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

Listing a wallet shows what each file says about itself, its kind, key and
version, without decrypting anything. A key whose kind is not known yet is
read as either kind: a command wallet may file the two apart.

    # in wallet: keys in and out of a wallet:
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

The clipboard
-------------

A key goes to a password manager, such as the Passwords app of macOS, as
the text of [chapter 7](07-keys.md), through the clipboard: `osheaf key
export --clipboard` copies it, the user pastes it into a note, and on
another device copies the note and runs `osheaf key import --clipboard`.
The clipboard is that of macOS, through `pbcopy` and `pbpaste`; `COPY` and
`PASTE` name the commands, which the tests replace.

    # in wallet: the clipboard:
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

Unlocking with a passkey
------------------------

A passphrase typed on every device that pulls a key is the price of a
wallet; a *passkey* can stand in for it (chapter 7): a credential of the
browser and the operating system, synchronised between the user's devices
(by iCloud Keychain on a Mac, or by another passkey provider), checked by
Touch ID or another check of the user. A command-line tool cannot reach a
passkey itself: only a web page of the passkey's relying party can, here
`https://unlock.opensheaf.org/`, an origin that serves this one page and
nothing else (its source is the repository
[opensheaf/unlock](https://github.com/opensheaf/unlock)). The module
`passkey.py` is the command line's side of it.

    # in src/opensheaf/passkey.py:
    <<passkey: the docstring and the imports>>


    <<passkey: the page>>


    <<passkey: the hand-off>>


    <<passkey: the listener>>


    <<passkey: asking the browser>>

The way there and back is this. The command starts a *listener*, a small
web server on `127.0.0.1` only, on a port chosen by the system, with a
`state`, 128 random bits, and a one-time X25519 key pair, which only this
command knows. It opens the browser at the page, with the mode, the port,
the state, the public key of the pair, the owner and the credentials of
the owner's passkeys, all in the *fragment* of the address (after `#`),
which the browser never sends to a server; the page reads it, and at once
takes it out of the address bar and of the history. The command prints a
*confirmation code* of six digits, derived from the state and the public
key; the page shows the same code, and does nothing until the user has
checked that the two agree and clicked. It then calls WebAuthn: to
enroll, it creates a passkey for `unlock.opensheaf.org` and derives its
PRF secret; to unlock, it derives the secret of one of the passkeys named.
The PRF salt is not sent: the page computes it from the owner, as chapter
7 does, so that an address cannot have the page derive a secret for
another salt. The page hands the secret back by going to
`http://127.0.0.1:<port>/callback`, a `GET` whose query holds the state,
the credential and the secret *encrypted and authenticated to the
listener* (the hand-off, below), or an error. The answer is a page of the
listener, shown in the tab, which says that the tab can be closed.

Why an address, and not `fetch` or a form. Browsers block a page of the
web from reading a local server, but let it navigate there. A form posted
there would carry the secret in the body of the request, out of the
browser's history; but `http://127.0.0.1` is not `https`, and Safari stops
a form of an `https` page that is sent to it with a warning that it is "a
non-secure form", which is right in general, and would teach the user to
dismiss it. A navigation is not a form, and draws no warning; but an
address stays in the browser's history. So the secret is never in it, only
a ciphertext that the one-time private key of the listener alone opens,
and that key is forgotten when the command ends: in the history, the
address is useless.

Why a code. The address of the page is public in all but its state, and
any program of the user's, or any page, could open the page with a key
pair of its own, or send the listener an answer of its own. The code ties
the page the user sees to this command (a page opened by someone else
shows another code), and the authenticated hand-off ties the answer to
the page that knew the state; the command line, besides, trusts a secret
only once it has opened a key of the wallet (chapter 19), and checks a new
passkey with a second unlock before it writes anything under it.

    # in passkey: the docstring and the imports:
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

### The page

The address of the page carries everything it needs in its fragment, and
nothing secret: the mode (`enroll` or `unlock`), the port, the state, the
public key of the listener, the owner, and the credentials, separated by
commas: to unlock, those the page may use; to enroll, those the owner
already has, which the page asks WebAuthn to exclude, so that enrolling
again on a provider that holds one of them fails rather than replacing
it. The page refuses anything else, and answers only `127.0.0.1` at that
port.

The page and the relying party are one origin, and one constant, here
`keys.PASSKEY_RP`, and `RP_ID` in the page; `UNLOCK_PAGE` is a variable,
which the tests replace.

    # in passkey: the page:
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

The confirmation code is the first four bytes of a SHA-256 digest, of
`opensheaf unlock code v1`, the state (in UTF-8) and the public key of
the listener, as a number, modulo a million: six digits, shown in two
groups of three.

    # in passkey: the page:
    CODE_LABEL = b"opensheaf unlock code v1"


    def confirmation_code(state, pk):
        """The six digits that the page shows for the listener with STATE and public key PK, as `123 456`."""
        n = int.from_bytes(hashlib.sha256(CODE_LABEL + state.encode("utf-8") + bytes(pk)).digest()[:4], "big")
        digits = f"{n % 1000000:06d}"
        return f"{digits[:3]} {digits[3:]}"

### The hand-off

The hand-off is an ephemeral Diffie-Hellman exchange, then a one-time pad
and a MAC (encrypt-then-MAC). The page makes its own one-time X25519 key
pair (WebCrypto, its private key not extractable), and derives the shared
secret of its private key and the public key of the listener;
HKDF-SHA256 (RFC 5869) of that shared secret, with the state (in UTF-8)
as the salt and `opensheaf unlock hand-off v2` as the info, gives 64
bytes: an encryption key, the first 32, and a MAC key, the last 32. The
ciphertext is the PRF secret XOR the encryption key; the tag is
HMAC-SHA256, under the MAC key, of the *associated data* followed by the
ciphertext. The associated data is `mode|owner|cred|pk|epk` in UTF-8: the
mode, the owner, the credential used, and the two public keys, in
base64url. The page sends its public key (`epk`), the ciphertext (`ct`),
the tag (`tag`) and the credential (`cred`), in base64url; the listener
derives the same keys from its private key and `epk`, checks the tag, in
constant time, and only then recovers the secret. A ciphertext, a
credential, a mode or a key changed on the way is refused, rather than
giving another secret.

Why this, and not AES-GCM, which WebCrypto has. The Python side has
PyNaCl, whose bindings have no AES-GCM (libsodium's needs hardware AES,
and PyNaCl does not expose it), and the `cryptography` package would be a
second cryptographic dependency for 32 bytes. HMAC-SHA256 and HKDF are in
WebCrypto and in the standard library of Python: the construction needs
no new dependency on either side, and each key is used once, for one
message of 32 bytes. Both sides of the hand-off are here: `seal` is what
the page does, which the tests play, and which a test vector, shared with
the tests of the page, fixes; `unseal` is what the listener does. HKDF is
written out, as in chapter 7: it is two lines of HMAC.

    # in passkey: the hand-off:
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

### The listener

The listener answers one request, `GET /callback`, whose query holds the
`state`, and either `epk`, `ct`, `tag` and `cred` or an `error`, and
nothing else (a few fields, a few kilobytes at most). A request with
another state is refused (403), and the listener keeps waiting, as it
does for any other path (404) or any other query (400). Once the state is
right, the answer is opened: a damaged or forged one (not base64url, not
32 bytes, a public key that X25519 refuses, a tag that does not match)
counts as an error of the page. The first right answer ends the wait; the
tab shows a short page. No `POST` is answered: the page never sends a
form.

The listener serves each connection in a thread of its own, which gives
up after five seconds of silence: another program on the computer that
opens a connection and says nothing cannot keep the browser's answer
waiting. The first answer is taken under a lock.

    # in passkey: the listener:
    DONE = "osheaf has the key. You can close this tab."
    FAILED = "osheaf did not get the key ({}): it asks for the passphrase instead. You can close this tab."
    NO_X25519 = ("this browser has no X25519 in WebCrypto, and cannot hand the key to osheaf securely (known to "
                 "work: Safari 17+, Chrome 133+, Firefox 130+); osheaf uses the passphrase")
    ANSWER = ({"state", "epk", "ct", "tag", "cred"}, {"state", "error"})


    class _Handler(http.server.BaseHTTPRequestHandler):
        timeout = 5

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            if url.path != "/callback":
                return self._answer(404, "not found")
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

### Asking the browser

`ask` runs the way there and back. It opens the address with `OPEN` (the
standard `webbrowser`, which the tests replace by a double that plays the
page), prints the confirmation code, and waits for the answer, two
minutes at most, or until the user presses Ctrl-C (to type the
passphrase instead, or to stop). It says what it does on the standard
error, and shows the address, which is long, only when it is needed: when
no browser opens (`--no-browser`, a remote shell), or after ten seconds
without an answer, in case the browser did not come up. The listener is
closed whatever happens, and its private key goes with it.

    # in passkey: asking the browser:
    OPEN = webbrowser.open


    def ask(mode, owner, creds=(), *, no_browser=False, timeout=None, ctrl_c="type the passphrase instead"):
        """The answer of the page ({cred, secret} or {error}), in MODE (enroll or unlock), for OWNER and
        CREDS (to unlock with, or to exclude when enrolling); UnlockFailed if none comes."""
        if not names.OWNER_NAME.fullmatch(owner) or mode not in ("enroll", "unlock"):
            raise UnlockFailed(f"not an owner name: {owner}")
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.daemon_threads = True
        server.state, server.result, server.done = secrets.token_urlsafe(16), None, threading.Event()
        server.mode, server.owner, server.lock = mode, owner, threading.Lock()
        server.key = public.PrivateKey.generate()
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        try:
            pk = bytes(server.key.public_key)
            url = page_url(mode, server.server_port, server.state, pk, owner, creds)
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

The answer is checked before it is used: a secret of 32 bytes, and a
credential, one of those asked for when unlocking, none of those excluded
when enrolling.

    # in passkey: asking the browser:
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
