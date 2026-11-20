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
and this chapter is the module `wallet.py`, which keeps keys in one.

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

A wallet is named as `--keys` names it: `github:OWNER/REPO`, or `command`,
whose commands are given by the configuration. The configuration of the
archive, `osheaf.json`, may name the wallet the owner uses, under `keys`;
the environment variable `OPENSHEAF_WALLET` overrides it, with the same
value as text (`github:OWNER/REPO`, `offline`) or as JSON (an object like
that of `osheaf.json`), for a user who keeps the name of its wallet out of
a public archive, or uses another wallet on another machine.

```json
"keys": {"wallet": "github:mgubi/opensheaf-keys"}
"keys": {"wallet": "command",
         "read": "op read 'op://Private/opensheaf-{owner}-{k}/notesPlain'",
         "write": "op item create --vault Private --category 'Secure Note' --title 'opensheaf-{owner}-{k}' \"notesPlain=$(cat)\""}
```

`forbidden` lists the repositories of the archive itself, which the GitHub
wallet refuses (below).

    # in wallet: choosing a wallet:
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
removes one, which only `osheaf key forget --wallet` asks for. A request
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
`pass`) configures the commands that read and write a key, in
`osheaf.json` or in `OPENSHEAF_WALLET`. Each is a shell command in which
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

Keys in and out of a wallet
---------------------------

Whatever the wallet, a key goes in as the file of [chapter 7](07-keys.md),
and is read back at once: a wallet that accepts and forgets, or changes
the text, is found before the key log commits a key kept only there.

    # in wallet: keys in and out of a wallet:
    def put_key(wallet, owner, key, kind, version, passphrase):
        """Keep KEY of OWNER, of KIND, committed in VERSION (or None), in WALLET, encrypted under PASSPHRASE
        (None: in clear, for a current key only)."""
        if passphrase is None and kind == keys.ROTATION:
            raise WalletError("a rotation key is kept in a wallet only encrypted under a passphrase")
        text = keys.key_file_text(key, owner, kind, version, passphrase)
        wallet.write(owner, key.id, kind, text)
        if (wallet.read(owner, key.id, kind) or "").strip() != text.strip():
            raise WalletError(f"{wallet.name} did not keep the {kind} key {key.did}")

A key read from a wallet is checked as any key read back: its seed gives
the key its file names, the owner and the kind are those asked for, and
its name is the one it is filed under. `passphrase` is a function, called
only when an encrypted key is met, so that a command asks for the
passphrase once, and not at all if nothing is encrypted.

    # in wallet: keys in and out of a wallet:
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
