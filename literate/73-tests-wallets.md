The tests of key wallets
========================

These tests check the security levels, the key wallets of
[chapter 9](09-wallets.md) and the commands that move keys
([chapter 19](19-owner-commands.md)). They must never reach the user's
GitHub account, keychain or clipboard: GitHub is a double, a script that
plays `gh` on a folder of the test, the clipboard a file of the test, the
key store a folder of files, as in the [other tests](70-tests.md); the
browser and the page of passkey unlock are a double too, which never
opens a browser nor makes a passkey. They are in `tests/test_wallets.py`.

    # in tests/test_wallets.py:
    <<wallet tests: the imports and the doubles>>


    <<wallet tests: key files and texts>>


    <<wallet tests: the GitHub wallet refuses>>


    <<wallet tests: push, pull and list>>


    <<wallet tests: an owner in a wallet>>


    <<wallet tests: the clipboard>>


    <<wallet tests: a command wallet>>


    <<wallet tests: passkey unlock>>

The doubles
-----------

The double of `gh` is a Python script, written into the folder of the
test, whose path becomes `wallet.GH`. It answers `gh auth status` (signed
in unless `FAKE_GH_AUTH` is `0`) and the calls of `gh api` the wallet
makes: a repository's description, from `repos.json`, which says which
repositories exist and which are private; and the contents API, on the
folder `contents/<owner>/<repo>/`, with the `sha` of a file (here its
SHA-1) required to replace or delete it, and the 404 of the real API
(`gh: Not Found (HTTP 404)` on the standard error). Each call is logged in
`calls.log`, so that a test can check what was never asked for.

    # in wallet tests: the imports and the doubles:
    """Tests of key wallets, security levels and the commands that move keys (opensheaf-py),
    against doubles of gh and of the clipboard."""

    import base64
    import json
    import stat
    import sys
    import threading
    import urllib.error
    import urllib.parse
    import urllib.request
    from pathlib import Path

    import pytest
    from nacl import pwhash
    from nacl.public import PrivateKey

    from opensheaf import cli, core as P, keys, names, owners, passkey, wallet

    FAKE_GH = r'''
    import base64, hashlib, json, os, sys
    state = os.environ["FAKE_GH_DIR"]
    args = sys.argv[1:]
    with open(os.path.join(state, "calls.log"), "a") as log:
        log.write(" ".join(args) + "\n")
    if args[:2] == ["auth", "status"]:
        sys.exit(0 if os.environ.get("FAKE_GH_AUTH", "1") == "1" else 1)
    method, body, path, rest = "GET", None, None, args[1:]
    while rest:
        a = rest.pop(0)
        if a == "-H":
            rest.pop(0)
        elif a == "-X":
            method = rest.pop(0)
        elif a == "--input":
            rest.pop(0)
            body = json.loads(sys.stdin.read())
        else:
            path = a
    def not_found():
        print('{"message": "Not Found"}')
        print("gh: Not Found (HTTP 404)", file=sys.stderr)
        sys.exit(1)
    repos = json.load(open(os.path.join(state, "repos.json")))
    parts = path.split("/")
    repo = "/".join(parts[1:3])
    if repo not in repos:
        not_found()
    if len(parts) == 3:
        print(json.dumps({"full_name": repo, "private": repos[repo]}))
        sys.exit(0)
    full = os.path.join(state, "contents", repo, *parts[4:])
    sha = lambda f: hashlib.sha1(open(f, "rb").read()).hexdigest()
    if method == "GET":
        if os.path.isdir(full):
            print(json.dumps([{"name": n, "type": "dir" if os.path.isdir(os.path.join(full, n)) else "file"}
                              for n in sorted(os.listdir(full))]))
        elif os.path.isfile(full):
            print(json.dumps({"type": "file", "sha": sha(full),
                              "content": base64.encodebytes(open(full, "rb").read()).decode()}))
        else:
            not_found()
    elif method == "PUT":
        if os.path.exists(full) and body.get("sha") != sha(full):
            print("gh: sha does not match (HTTP 409)", file=sys.stderr)
            sys.exit(1)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "wb").write(base64.b64decode(body["content"]))
        print("{}")
    elif method == "DELETE":
        if not os.path.isfile(full) or body.get("sha") != sha(full):
            not_found()
        os.remove(full)
        print("{}")
    '''


    def script(path, text, interpreter):
        path.write_text(f"#!{interpreter}\n" + text)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return str(path)

The autouse fixture makes every test safe before it starts: the keys of
the tests, predictable, in files; no wallet, passphrase or signing key from
the environment; the double of `gh`, with three repositories, `me/keys`
(private), `me/open` (public) and `me/papers` (private, the archive's own
in some tests); the clipboard, a file; and the cheapest Argon2id. The
passphrase, for the tests that need one, comes from the environment, as in
a script. No test may open a browser: `passkey.OPEN` fails the test unless
a test puts the double of the browser in its place, and the wait for the
browser is two seconds.

    # in wallet tests: the imports and the doubles:
    FAST = dict(opslimit=pwhash.argon2id.OPSLIMIT_MIN, memlimit=pwhash.argon2id.MEMLIMIT_MIN)


    @pytest.fixture(autouse=True)
    def doubles(tmp_path, monkeypatch, request):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv(keys.KEY_STORE, "file")
        monkeypatch.delenv(keys.SIGNING_KEY, raising=False)
        monkeypatch.delenv(P.PASSPHRASE, raising=False)
        monkeypatch.delenv(wallet.WALLET, raising=False)
        monkeypatch.delenv(P.PASSPHRASE_COMMAND, raising=False)
        monkeypatch.delenv(passkey.UNLOCK, raising=False)
        monkeypatch.setattr(passkey, "OPEN", lambda url: pytest.fail(f"a browser was opened: {url}"))
        monkeypatch.setattr(passkey, "TIMEOUT", 2.0)
        monkeypatch.setenv(keys.TEST_KEYS, ",".join(f"{request.node.name} {i}" for i in range(80)))
        monkeypatch.setattr(keys, "OPSLIMIT", FAST["opslimit"])
        monkeypatch.setattr(keys, "MEMLIMIT", FAST["memlimit"])
        gh = tmp_path / "gh-state"
        gh.mkdir()
        (gh / "repos.json").write_text(json.dumps({"me/keys": True, "me/open": False, "me/papers": True}))
        monkeypatch.setenv("FAKE_GH_DIR", str(gh))
        monkeypatch.setenv("FAKE_GH_AUTH", "1")
        bin_ = tmp_path / "bin"
        bin_.mkdir()
        monkeypatch.setattr(wallet, "GH", script(bin_ / "gh", FAKE_GH, sys.executable))
        clip = tmp_path / "clipboard.txt"
        monkeypatch.setattr(wallet, "COPY", [script(bin_ / "pbcopy", f"cat > '{clip}'\n", "/bin/sh")])
        monkeypatch.setattr(wallet, "PASTE", [script(bin_ / "pbpaste", f"cat '{clip}'\n", "/bin/sh")])


    def gh_calls(tmp_path):
        log = tmp_path / "gh-state" / "calls.log"
        return log.read_text().splitlines() if log.exists() else []


    def in_repo(tmp_path, repo="me/keys"):
        """{path: text} of the files of the double's repository REPO."""
        root = tmp_path / "gh-state" / "contents" / repo
        return {str(f.relative_to(root)): f.read_text() for f in root.rglob("*") if f.is_file()} if root.exists() else {}


    def run(*argv):
        cli.main(list(argv))


    def make_archive(tmp_path, *extra, name="T"):
        root = tmp_path / name
        run("init", str(root), "--name", name, "--base-url", f"https://example.org/{name}/",
            "--curator", "Doe, Jane", "--new-owner", "--yes", *extra)
        return root


    def local_keys(tmp_path, owner):
        folder = tmp_path / "config" / "opensheaf" / "keys" / owner
        return sorted(f.name for f in folder.iterdir()) if folder.exists() else []


    def deposit(root, label, text, new=False):
        pdf = root.parent / f"{label}.pdf"
        pdf.write_bytes(b"%PDF-1.4 " + text.encode())
        run("--root", str(root), "deposit", label, "--pdf", str(pdf), "--no-source", "x", "--title", "T",
            "--author", "Doe, J", *(["--new"] if new else []))

Key files and texts
-------------------

A key file of a wallet says its kind, and is read back as that kind; a
current key is refused where a rotation key is needed. The text for a
password manager reads back, in clear or encrypted, also with lines
pasted around it, and a mistyped group is caught by its check.

    # in wallet tests: key files and texts:
    def test_key_files_and_texts():
        k = keys.example_key("wallet current")
        owner = "a" * 52
        text = keys.key_file_text(k, owner, keys.CURRENT, 2, "pass", **FAST)
        assert text.startswith(f"opensheaf-key/0.2\nkind current\nowner {owner}\nversion v2\nkey {k.did}\n")
        back = keys.read_key(text, "pass")
        assert (back.key.did, back.kind, back.version, back.owner) == (k.did, "current", 2, owner)
        with pytest.raises(keys.PassphraseNeeded):
            keys.read_key(text)
        with pytest.raises(keys.KeyStoreError, match="not a rotation key"):
            keys.read_rotation_key(text, "pass")
        plain = keys.key_text(k, owner)
        assert plain.startswith("opensheaf-key-text/0.2\nkind current\n") and "encryption" not in plain
        assert keys.read_key("Notes from the Passwords app\n\n" + plain + "\nmore\n").key.did == k.did
        secret = keys.key_text(k, owner, passphrase="pass", **FAST)
        assert "encryption argon2id-secretbox" in secret and keys.read_key(secret, "pass").key.did == k.did
        seed = next(x for x in plain.splitlines() if x.startswith("seed ")).split()[1]
        wrong = seed[:-1] + ("A" if seed[-1] != "A" else "B")
        with pytest.raises(keys.KeyStoreError, match="mistyped"):
            keys.read_key(plain.replace(seed, wrong, 1))
        with pytest.raises(wallet.WalletError, match="only encrypted"):
            wallet.put_key(None, owner, k, keys.ROTATION, 1, None)

The repositories of an archive are those of its git remotes on GitHub and
of its GitHub Pages address.

    # in wallet tests: key files and texts:
    def test_archive_repositories(tmp_path):
        assert wallet.archive_repositories(None, "https://Me.github.io/Papers/") == {"me/papers"}
        assert wallet.archive_repositories(None, "https://me.github.io/") == {"me/me.github.io"}
        assert wallet.archive_repositories(None, "https://example.org/papers/") == set()
        import subprocess
        subprocess.run(["git", "init", "-q", str(tmp_path / "a")], check=True)
        subprocess.run(["git", "-C", str(tmp_path / "a"), "remote", "add", "origin",
                        "git@github.com:me/papers.git"], check=True)
        assert wallet.archive_repositories(tmp_path / "a", None) == {"me/papers"}
        with pytest.raises(wallet.WalletError):
            wallet.parse("github:not a repo")
        assert wallet.parse("offline") is None and wallet.parse("github:me/keys").name == "github:me/keys"

The GitHub wallet refuses
-------------------------

Nothing is written to a public repository, nor to the archive's own (here
the repository of its git remote), nor to one that does not exist; a
missing or signed-out `gh` is said so. The log of the double shows that no
`PUT` was ever sent.

    # in wallet tests: the GitHub wallet refuses:
    def test_github_wallet_refuses(tmp_path, monkeypatch):
        import subprocess
        root = make_archive(tmp_path, "--export", str(tmp_path / "usb"), "--no-passphrase")
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "https://github.com/me/papers"], check=True)
        monkeypatch.setenv(P.PASSPHRASE, "correct horse")
        r = ["--root", str(root), "key", "push"]
        with pytest.raises(SystemExit, match="not a private repository"):
            run(*r, "--keys", "github:me/open")
        with pytest.raises(SystemExit, match="repository of the archive"):
            run(*r, "--keys", "github:me/papers")
        with pytest.raises(SystemExit, match="no repository me/missing"):
            run(*r, "--keys", "github:me/missing")
        monkeypatch.setenv("FAKE_GH_AUTH", "0")
        with pytest.raises(SystemExit, match="not signed in"):
            run(*r, "--keys", "github:me/keys")
        monkeypatch.setattr(wallet, "GH", str(tmp_path / "no-gh"))
        with pytest.raises(SystemExit, match="needs the GitHub CLI"):
            run(*r, "--keys", "github:me/keys")
        assert not [c for c in gh_calls(tmp_path) if "PUT" in c or "DELETE" in c]
        assert in_repo(tmp_path, "me/open") == {} and in_repo(tmp_path, "me/papers") == {}

Push, pull and list
-------------------

An owner kept offline pushes its current key to the wallet, encrypted; the
listing shows it, and never a secret; a machine without the key pulls it
back, and signs. A machine whose archive names the wallet (here through
`OPENSHEAF_WALLET`) pulls the key itself when it signs, once.

    # in wallet tests: push, pull and list:
    def test_push_pull_list(tmp_path, monkeypatch, capsys):
        root = make_archive(tmp_path, "--export", str(tmp_path / "usb"), "--no-passphrase")
        owner = P.ARCHIVE["owner"]
        current = P.key_log(owner).latest().keys["keys"][0]
        kid = names.key_id(current)
        monkeypatch.setenv(P.PASSPHRASE, "correct horse")
        r = ["--root", str(root)]
        capsys.readouterr()
        run(*r, "key", "push", "--keys", "github:me/keys")
        out, err = capsys.readouterr()
        assert wallet.risk("github:me/keys", owner) in err and "pushed to github:me/keys" in out
        files = in_repo(tmp_path)
        assert list(files) == [f"{owner}/{kid}.key.enc"]
        assert "kind current" in files[f"{owner}/{kid}.key.enc"] and "wrap passphrase argon2id" in files[f"{owner}/{kid}.key.enc"]
        run(*r, "key", "list", "--keys", "github:me/keys")
        out = capsys.readouterr().out
        assert out.split() == [owner, kid, "current", current, "v1"]
        seed = (tmp_path / "config" / "opensheaf" / "keys" / owner / f"{kid}.key").read_text().strip()
        run(*r, "key", "forget", current)
        assert local_keys(tmp_path, owner) == []
        run(*r, "key", "pull", "--keys", "github:me/keys")
        assert local_keys(tmp_path, owner) == [f"{kid}.key"]
        assert "Pulled 1 current key of" in capsys.readouterr().out
        run(*r, "key", "forget", current)
        with pytest.raises(SystemExit, match="holds 0 of the current keys"):
            deposit(root, "p", "one", new=True)
        monkeypatch.setenv(wallet.WALLET, "github:me/keys")
        deposit(root, "p", "one", new=True)
        assert "Pulling the current key of " in capsys.readouterr().err
        assert local_keys(tmp_path, owner) == [f"{kid}.key"] and P.verify_errors() == []
        assert seed not in capsys.readouterr().out

An owner in a wallet
--------------------

`init --keys github:me/keys` makes an owner whose rotation keys are in the
wallet, encrypted, and not on the device, which keeps only its current key
(also in the wallet); the configuration names the wallet, and the risk is
stated. A rotation reads the rotation keys from the wallet, asking no
files, and keeps the new ones there. Moving up, `owner rotate --keys
offline --export DIR`, signs with the keys of the wallet and exports the
new ones only: the wallet's are used up, which the command says, and
`key forget --wallet --used` removes them, keeping the current key. The
next rotation finds no rotation keys in the wallet, and needs the files.
No secret is ever printed on the standard output.

    # in wallet tests: an owner in a wallet:
    def test_owner_in_a_github_wallet(tmp_path, monkeypatch, capsys):
        monkeypatch.setenv(P.PASSPHRASE, "correct horse")
        root = make_archive(tmp_path, "--keys", "github:me/keys")
        out, err = capsys.readouterr()
        owner = P.ARCHIVE["owner"]
        assert json.loads((root / "osheaf.json").read_text())["keys"] == {"wallet": "github:me/keys"}
        assert wallet.risk("github:me/keys", owner) in err
        log = P.key_log(owner)
        v1 = log.latest().keys
        files = in_repo(tmp_path)
        kinds = sorted(t.splitlines()[1] for t in files.values())
        assert kinds == ["kind current"] + ["kind rotation"] * 3
        assert all("encryption envelope-secretbox\nwrap passphrase argon2id" in t for t in files.values())
        assert {f"{owner}/{d[:16]}.key.enc" for d in v1["next"]} < set(files)
        assert local_keys(tmp_path, owner) == [f"{names.key_id(v1['keys'][0])}.key"]
        assert not (tmp_path / "usb").exists()
        r = ["--root", str(root)]
        P.configure(root)
        laptop = P.key_new(P.argparse_namespace(owner=None)).did
        run(*r, "owner", "rotate", "--add", laptop, "--keys", "github:me/keys")
        out2, err2 = capsys.readouterr()
        assert "Read 2 rotation keys of v1 from github:me/keys." in err2
        v2 = P.key_log(owner).latest().keys
        assert laptop in v2["keys"] and {f"{owner}/{d[:16]}.key.enc" for d in v2["next"]} < set(in_repo(tmp_path))
        assert f"{owner}/{names.key_id(laptop)}.key.enc" in in_repo(tmp_path)
        run(*r, "owner", "rotate", "--keys", "offline", "--export", str(tmp_path / "usb"), "--yes")
        out3, err3 = capsys.readouterr()
        assert "moved up" in err3
        v3 = P.key_log(owner).latest().keys
        assert not {f"{owner}/{d[:16]}.key.enc" for d in v3["next"]} & set(in_repo(tmp_path))
        assert len(list((tmp_path / "usb").glob("rotation-*.txt"))) == 3
        run(*r, "key", "forget", "--wallet", "--used", "--yes")
        assert sorted(in_repo(tmp_path)) == sorted(f"{owner}/{names.key_id(d)}.key.enc" for d in v3["keys"])
        with pytest.raises(SystemExit, match="holds 0 of the rotation keys of v3"):
            run(*r, "owner", "rotate", "--export", str(tmp_path / "usb2"), "--yes")
        usb = sorted(str(f) for f in (tmp_path / "usb").glob("rotation-*.txt"))
        run(*r, "owner", "rotate", "--rotation-key", usb[0], "--rotation-key", usb[1],
            "--export", str(tmp_path / "usb2"), "--yes")
        assert len(P.key_log(owner).versions) == 4 and P.verify_errors() == []
        out4 = out + out2 + out3 + capsys.readouterr().out
        assert "seed" not in out4 and "correct horse" not in out4 + err + err2 + err3

A rotation key committed by the latest version is kept in the wallet unless
`--force`, and removing anything is confirmed; the passphrase is asked
once per command, here through `getpass`, though the command decrypts two
rotation keys and encrypts three.

    # in wallet tests: an owner in a wallet:
    def test_wallet_keeps_needed_rotation_keys(tmp_path, monkeypatch):
        monkeypatch.setenv(P.PASSPHRASE, "correct horse")
        root = make_archive(tmp_path, "--keys", "github:me/keys")
        owner = P.ARCHIVE["owner"]
        nxt = P.key_log(owner).latest().keys["next"]
        rotation = next(t for t in in_repo(tmp_path).values() if f"digest {nxt[0]}" in t)
        did = next(x.split()[1] for x in rotation.splitlines() if x.startswith("key "))
        r = ["--root", str(root)]
        with pytest.raises(SystemExit, match="--force removes them"):
            run(*r, "key", "forget", "--wallet", did, "--yes")
        monkeypatch.setattr("builtins.input", lambda prompt: "no")
        with pytest.raises(SystemExit, match="not confirmed"):
            run(*r, "key", "forget", "--wallet", did, "--force")
        assert len(in_repo(tmp_path)) == 4
        monkeypatch.delenv(P.PASSPHRASE)
        asked = []
        monkeypatch.setattr("getpass.getpass", lambda prompt: asked.append(prompt) or "correct horse")
        run(*r, "owner", "rotate", "--keys", "github:me/keys")
        assert len(asked) == 1 and len(P.key_log(owner).versions) == 2

The clipboard
-------------

A current key goes to the clipboard (the double's file) as text, and
nothing secret goes to the standard output; forgotten on the device, it
comes back from the clipboard. Encrypted, it needs the passphrase. With
`--stdout` the text is printed, as asked; a rotation key is never
imported.

    # in wallet tests: the clipboard:
    def test_clipboard_round_trip(tmp_path, monkeypatch, capsys):
        root = make_archive(tmp_path, "--export", str(tmp_path / "usb"), "--no-passphrase")
        owner = P.ARCHIVE["owner"]
        current = P.key_log(owner).latest().keys["keys"][0]
        r = ["--root", str(root)]
        capsys.readouterr()
        run(*r, "key", "export", "--clipboard")
        out, err = capsys.readouterr()
        clip = (tmp_path / "clipboard.txt").read_text()
        assert clip.startswith(f"opensheaf-key-text/0.2\nkind current\nowner {owner}\nkey {current}\n")
        assert out == "" and "on the clipboard" in err and "one key per device" in err
        run(*r, "key", "forget", current)
        run(*r, "key", "import", "--clipboard")
        assert local_keys(tmp_path, owner) == [f"{names.key_id(current)}.key"]
        monkeypatch.setenv(P.PASSPHRASE, "correct horse")
        run(*r, "key", "export", "--clipboard", "--encrypt")
        assert "encryption argon2id-secretbox" in (tmp_path / "clipboard.txt").read_text()
        run(*r, "key", "forget", current)
        monkeypatch.delenv(P.PASSPHRASE)
        monkeypatch.setattr("getpass.getpass", lambda prompt: "wrong horse")
        with pytest.raises(SystemExit, match="wrong passphrase"):
            run(*r, "key", "import", "--clipboard")
        monkeypatch.setattr("getpass.getpass", lambda prompt: "correct horse")
        run(*r, "key", "import", "--clipboard")
        assert local_keys(tmp_path, owner) == [f"{names.key_id(current)}.key"]
        capsys.readouterr()
        run(*r, "key", "export", "--stdout")
        assert capsys.readouterr().out.startswith("opensheaf-key-text/0.2\n")
        rotation = sorted((tmp_path / "usb").glob("rotation-*.txt"))[0]
        (tmp_path / "clipboard.txt").write_text(rotation.read_text())
        with pytest.raises(SystemExit, match="never kept on a device"):
            run(*r, "key", "import", "--clipboard")

A command wallet
----------------

A wallet of commands, configured in `osheaf.json`, here commands that keep
each key as a file `<owner>-<k>-<kind>.txt` of a folder of the test, as a
password manager would keep an item: an owner made offline moves to it with
a rotation, and the next rotation reads its rotation keys there. The
listing uses the `list` command. `OPENSHEAF_WALLET` overrides the
configuration: here, with a wallet of JSON, the same commands in another
folder, which holds nothing.

    # in wallet tests: a command wallet:
    def test_command_wallet(tmp_path, monkeypatch, capsys):
        root = make_archive(tmp_path, "--export", str(tmp_path / "usb"), "--no-passphrase")
        owner = P.ARCHIVE["owner"]
        vault = tmp_path / "vault"
        vault.mkdir()

        def commands(folder):
            return {"wallet": "command", "read": f"cat '{folder}/{{owner}}-{{k}}-{{kind}}.txt'",
                    "write": f"cat > '{folder}/{{owner}}-{{k}}-{{kind}}.txt'",
                    "list": f"ls '{folder}' | sed 's/-/ /g'"}

        cfg = json.loads((root / "osheaf.json").read_text())
        cfg["keys"] = commands(vault)
        (root / "osheaf.json").write_text(json.dumps(cfg))
        monkeypatch.setenv(P.PASSPHRASE, "correct horse")
        r = ["--root", str(root)]
        usb = sorted(str(f) for f in (tmp_path / "usb").glob("rotation-*.txt"))
        capsys.readouterr()
        run(*r, "owner", "rotate", "--keys", "command", "--rotation-key", usb[0], "--rotation-key", usb[1])
        assert wallet.risk("command", owner) in capsys.readouterr().err
        held = sorted(f.name.rsplit("-", 1)[1] for f in vault.iterdir())
        assert held == ["current.txt"] + ["rotation.txt"] * 3
        run(*r, "key", "list")
        rows = capsys.readouterr().out.splitlines()
        assert len(rows) == 4 and sorted(x.split()[2] for x in rows) == ["current"] + ["rotation"] * 3
        run(*r, "owner", "rotate", "--keys", "command")
        assert len(P.key_log(owner).versions) == 3 and len(list(vault.iterdir())) == 7
        other = tmp_path / "other"
        other.mkdir()
        monkeypatch.setenv(wallet.WALLET, json.dumps(commands(other)))
        with pytest.raises(SystemExit, match="command holds 0 of the rotation keys"):
            run(*r, "owner", "end")
        monkeypatch.setenv(wallet.WALLET, "command")
        run(*r, "owner", "end")
        assert P.key_log(owner).ended and P.verify_errors() == []

Passkey unlock
--------------

The key-encryption key of a passkey is HKDF-SHA256 of its PRF secret,
here checked against a value computed by OpenSSL (`openssl kdf -keylen 32
-kdfopt digest:SHA256 -kdfopt hexkey:000102...1f -kdfopt info:"opensheaf
wallet passkey v1" HKDF`); the salt is the digest of the owner name. A
file in the format written before envelopes, its seed encrypted directly
under the passphrase, is read as before, and becomes an envelope when a
passkey is added: then the passkey alone opens it, and so does the
passphrase; a wrong key-encryption key asks for the passphrase, naming the
passkeys that could open it.

    # in wallet tests: passkey unlock:
    def test_passkey_key_files():
        assert keys.passkey_kek(bytes(range(32))).hex() == \
            "c5d8a01a83eb8478a5020b465c6ba170410b4c44b14ad4e31c779251a88c5cc7"
        owner = "a" * 52
        assert keys.passkey_salt(owner) == names.sha256(("opensheaf wallet unlock v1 " + owner).encode())
        k = keys.example_key("wallet passkey")
        old = keys._file_text([keys.KEY_FORMAT, "kind current"], k, owner, 1, "pass", FAST["opslimit"], FAST["memlimit"])
        assert "encryption argon2id-secretbox" in old and keys.read_key(old, "pass").key.did == k.did
        pk = keys.Passkey("Y3JlZGVudGlhbC0x", keys.passkey_salt(owner), kek=keys.passkey_kek(b"\1" * 32))
        new = keys.add_passkey(old, "pass", pk, **FAST)
        assert "encryption envelope-secretbox\nwrap passphrase argon2id" in new and "wrap passkey prf rp=opensheaf.org " \
            "cred=Y3JlZGVudGlhbC0x" in new
        assert keys.read_key(new, keks={pk.cred: pk.kek}).key.did == k.did == keys.read_key(new, "pass").key.did
        with pytest.raises(keys.PassphraseNeeded) as e:
            keys.read_key(new, keks={pk.cred: keys.passkey_kek(b"\2" * 32)})
        assert [p.cred for p in e.value.passkeys] == [pk.cred]
        pk2 = keys.Passkey("Y3JlZGVudGlhbC0y", keys.passkey_salt(owner), kek=keys.passkey_kek(b"\3" * 32))
        both = keys.add_passkey(new, "pass", pk2)
        assert both.count("wrap passkey") == 2 and keys.read_key(both, keks={pk2.cred: pk2.kek}).key.did == k.did
        with pytest.raises(keys.KeyStoreError, match="wrong passphrase"):
            keys.add_passkey(new, "wrong", pk2)
        with pytest.raises(keys.KeyStoreError, match="nothing to unlock"):
            keys.add_passkey(keys.key_file_text(k, owner, keys.CURRENT), None, pk)

The hand-off is fixed by a test vector, which the tests of the page
(`tests/unlock.test.mjs` of the manager) check too, with WebCrypto: from
these two private keys, this state and this secret, the page sends this
public key and this ciphertext, and the listener opens it. Any other state
or key gives another secret.

    # in wallet tests: passkey unlock:
    HAND_OFF = {"sk": "3MnQ1WVJ9j-gIHW04onidnPAdXBkj8Ex38awjc_xIFU", "pk": "EDUGNAoWiXZye3oZT1uexqCDj6g-_pOiwL6N01HzQX0",
                "esk": "XsIioGnOBETGr9GuOkvzh0s9Mnee8lz8KkfLHClLxGc", "epk": "wz_hpV5NNJh92Eqb4TE6dA7IVbA2LrWBmV8GisGgjBE",
                "state": "Zaz8C5ywR4VKbNOX7dQHUg", "secret": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8",
                "ct": "zFOj0v4rRRRpaSyM_xRgRRWo-SH_pdvdYHDVc--it4k"}


    def test_hand_off_vector():
        v = {k: passkey.from_b64url(x) if k != "state" else x for k, x in HAND_OFF.items()}
        sk, esk = PrivateKey(v["sk"]), PrivateKey(v["esk"])
        assert bytes(sk.public_key) == v["pk"] and bytes(esk.public_key) == v["epk"]
        assert v["secret"] == bytes(range(32))
        assert passkey.seal(v["secret"], v["pk"], v["state"], esk) == (v["epk"], v["ct"])
        assert passkey.unseal(sk, v["epk"], v["ct"], v["state"]) == v["secret"]
        assert passkey.unseal(sk, v["epk"], v["ct"], "another state") != v["secret"]
        assert passkey.unseal(esk, v["pk"], v["ct"], v["state"]) == v["secret"]
        assert passkey.hkdf(b"\x0b" * 22, bytes(range(13)), bytes(range(0xf0, 0xfa)), 42).hex() == (
            "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865")
        with pytest.raises(ValueError):
            passkey.unseal(sk, v["epk"], v["ct"][:16], v["state"])

The double of the browser reads the address of the page as the page
does, checks the salt, and goes back to the listener as the page would,
from another thread: it encrypts a PRF secret of its own (a digest of the
credential and the salt, stable as a real one is) to the public key of
the listener, and sends it in the address of a `GET`; or it sends an
error, or a wrong state, or nothing at all. It records the queries of the
pages it opened, and the addresses it went to.

    # in wallet tests: passkey unlock:
    def fake_browser(opened, answer="secret", cred="ZmFrZS1wYXNza2V5LWNyZWRlbnRpYWw"):
        def opener(url):
            assert url.startswith(passkey.PAGE + "?")
            q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
            opened.append(q)
            if answer == "none":
                return True
            salt = passkey.from_b64url(q["salt"])
            assert salt == keys.passkey_salt(q["owner"])
            used = cred if q["mode"] == "enroll" else q["cred"].split(",")[0]
            fields = {"state": q["state"] if answer != "wrong state" else "W" * 22}
            if answer in ("error", "x25519-unavailable"):
                fields["error"] = "NotAllowedError: the user cancelled" if answer == "error" else answer
            else:
                prf = names.sha256(b"fake prf " + used.encode() + salt)
                epk, ct = passkey.seal(prf, passkey.from_b64url(q["pk"]), q["state"])
                fields.update(epk=passkey.b64url(epk), ct=passkey.b64url(ct), cred=used)
            to = f"http://127.0.0.1:{q['port']}/callback?" + urllib.parse.urlencode(fields)

            def go():
                opened.append({"went": to})
                try:
                    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(to, timeout=5).read()
                except urllib.error.HTTPError as e:
                    opened.append({"status": e.code})

            threading.Thread(target=go, daemon=True).start()
            return True
        return opener

`key enroll` asks the passphrase once, opens the page to create a
passkey, and adds a passkey wrap to every key of the owner in the wallet,
keeping the passphrase wrap; a key written before envelopes is converted.
Run again, it has nothing to do. On another machine, `key unlock` opens
the page to unlock, with the credential and the owner, and pulls the
current key without any passphrase. A rotation reads its rotation keys
with the passkey (one page for both) and gives the new keys a passkey
wrap; only the encryption of the new keys asks the passphrase. No secret
is printed.

    # in wallet tests: passkey unlock:
    def test_enroll_and_unlock(tmp_path, monkeypatch, capsys):
        monkeypatch.setenv(P.PASSPHRASE, "correct horse")
        root = make_archive(tmp_path, "--keys", "github:me/keys")
        owner = P.ARCHIVE["owner"]
        current = P.key_log(owner).latest().keys["keys"][0]
        repo = tmp_path / "gh-state" / "contents" / "me" / "keys" / owner
        a_rotation = next(f for f in sorted(repo.iterdir()) if "kind rotation" in f.read_text())
        rk = keys.read_key(a_rotation.read_text(), "correct horse")
        a_rotation.write_text(keys._file_text([keys.KEY_FORMAT, "kind rotation"], rk.key, owner, 1, "correct horse",
                                              FAST["opslimit"], FAST["memlimit"]))
        monkeypatch.delenv(P.PASSPHRASE)
        asked, opened = [], []
        monkeypatch.setattr("getpass.getpass", lambda prompt: asked.append(prompt) or "correct horse")
        monkeypatch.setattr(passkey, "OPEN", fake_browser(opened))
        r = ["--root", str(root)]
        capsys.readouterr()
        run(*r, "key", "enroll")
        assert len(asked) == 1 and [q["mode"] for q in opened if "mode" in q] == ["enroll"]
        assert opened[0]["owner"] == owner and len(passkey.from_b64url(opened[0]["pk"])) == 32
        assert asked == ["Passphrase of the keys in github:me/keys: "]
        out, err = capsys.readouterr()
        short = names.short(owner)
        assert out == f"Done: the 4 keys of {short} open with your passkey (Touch ID) and still with your passphrase.\n"
        assert f"Opening the 4 keys of {short} in github:me/keys with the passphrase…" in err
        assert "  1/4 " in err and "  4/4 " in err and "Saving the 4 keys to github:me/keys…" in err
        assert "Opening the browser to create a passkey for" in err and "Still waiting" not in err
        assert passkey.PAGE not in err and "(s)" not in out + err
        went = [q["went"] for q in opened if "went" in q]
        assert "secret" not in went[0] and "&ct=" in went[0]
        files = in_repo(tmp_path)
        assert len(files) == 4 and all("encryption envelope-secretbox\nwrap passphrase argon2id" in t
                                       and "wrap passkey prf rp=opensheaf.org cred=ZmFrZS1w" in t for t in files.values())
        run(*r, "key", "enroll")
        assert "already" in capsys.readouterr().out and len(opened) == 2 and len(asked) == 1
        run(*r, "key", "forget", current)
        monkeypatch.setattr("getpass.getpass", lambda prompt: pytest.fail("the passphrase was asked"))
        capsys.readouterr()
        run(*r, "key", "unlock")
        assert opened[-2]["mode"] == "unlock" and opened[-2]["cred"] == "ZmFrZS1wYXNza2V5LWNyZWRlbnRpYWw"
        assert local_keys(tmp_path, owner) == [f"{names.key_id(current)}.key"]
        out, err = capsys.readouterr()
        assert out == (f"All 4 keys of {short} opened with your passkey.\n"
                       f"Pulled 1 current key of {short} from github:me/keys into a file of this computer.\n")
        run(*r, "key", "pull")
        assert capsys.readouterr().out == f"The current key of {short} is already on this computer.\n"
        deposit(root, "p", "one", new=True)
        monkeypatch.setattr("getpass.getpass", lambda prompt: asked.append(prompt) or "correct horse")
        run(*r, "owner", "rotate", "--keys", "github:me/keys")
        assert len([q for q in opened if "mode" in q]) == 3 and len(asked) == 2
        v2 = P.key_log(owner).latest().keys
        new = [in_repo(tmp_path)[f"{owner}/{d[:16]}.key.enc"] for d in v2["next"]]
        assert all("wrap passkey" in t for t in new) and P.verify_errors() == []
        out2, err2 = capsys.readouterr()
        assert "correct horse" not in out + err + out2 + err2 and "secret=" not in err + err2

When the browser gives nothing, the passphrase is asked instead: the page
reports an error; it posts with another state, which the listener refuses
(403) and keeps waiting, until the time is up; it never answers. With
`OPENSHEAF_UNLOCK=passphrase` the browser is never opened. `key unlock`
itself does not fall back: it says the passkey failed.

    # in wallet tests: passkey unlock:
    def test_unlock_falls_back_to_the_passphrase(tmp_path, monkeypatch, capsys):
        monkeypatch.setenv(P.PASSPHRASE, "correct horse")
        root = make_archive(tmp_path, "--keys", "github:me/keys")
        owner = P.ARCHIVE["owner"]
        current = P.key_log(owner).latest().keys["keys"][0]
        opened = []
        monkeypatch.setattr(passkey, "OPEN", fake_browser(opened))
        r = ["--root", str(root)]
        run(*r, "key", "enroll")
        monkeypatch.delenv(P.PASSPHRASE)
        monkeypatch.setattr(passkey, "TIMEOUT", 1.0)
        asked = []
        monkeypatch.setattr("getpass.getpass", lambda prompt: asked.append(prompt) or "correct horse")
        capsys.readouterr()
        for answer, said in (("error", "the page says: NotAllowedError"), ("wrong state", "no answer"),
                             ("none", "no answer"), ("x25519-unavailable", "Safari 17+")):
            run(*r, "key", "forget", current)
            monkeypatch.setattr(passkey, "OPEN", fake_browser(opened, answer))
            run(*r, "key", "pull")
            assert said in capsys.readouterr().err and local_keys(tmp_path, owner) != []
        assert len(asked) == 4 and {"status": 403} in opened
        run(*r, "key", "forget", current)
        monkeypatch.setenv(passkey.UNLOCK, "passphrase")
        monkeypatch.setattr(passkey, "OPEN", lambda url: pytest.fail("a browser was opened"))
        run(*r, "key", "pull")
        assert len(asked) == 5 and local_keys(tmp_path, owner) != []
        monkeypatch.setattr(passkey, "OPEN", fake_browser(opened, "error"))
        with pytest.raises(SystemExit, match="did not unlock"):
            run(*r, "key", "unlock")

The listener answers only `GET /callback` with the fields of an answer:
another path, another query (a secret in clear, a field more, a field
missing), a form `POST` are refused, and it keeps waiting; a ciphertext
that is not 32 bytes counts as an error of the page. Without a browser
(`--no-browser`), the address is printed at once; when the browser does
not answer, it is printed after a while, in case no browser opened.

    # in wallet tests: passkey unlock:
    def test_listener():
        owner = "56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa"
        got = []

        def opener(url):
            q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
            o = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            base = f"http://127.0.0.1:{q['port']}"
            s, short = q["state"], passkey.b64url(b"short")
            for path in (f"/other?state={s}&error=x", f"/callback?state={s}&secret=AAAA&error=x",
                         f"/callback?state={s}&epk=AAAA", f"/callback?state={s}&error=x&error=y",
                         f"/callback?state={s}&epk={short}&ct={short}&cred=Y3JlZA&more=1", None,
                         f"/callback?state={s}&epk={short}&ct={short}&cred=Y3JlZA"):
                try:
                    data = b"state=" + s.encode() if path is None else None
                    got.append(o.open(base + (path or "/callback"), data=data, timeout=5).status)
                except urllib.error.HTTPError as e:
                    got.append(e.code)
            return True

        passkey.OPEN = opener
        try:
            with pytest.raises(passkey.UnlockFailed, match="damaged"):
                passkey.unlock(owner, ["Y3JlZA"])
        finally:
            passkey.OPEN = lambda url: pytest.fail("a browser was opened")
        assert got == [404, 400, 400, 400, 400, 501, 200]
        with pytest.raises(passkey.UnlockFailed, match="32 bytes"):
            passkey._answer({"secret": b"short", "cred": "Y3JlZA"})
        with pytest.raises(passkey.UnlockFailed, match="another passkey"):
            passkey._answer({"secret": bytes(32), "cred": "b3RoZXI"}, ["Y3JlZA"])


    def test_the_address_when_no_browser_opens(monkeypatch, capsys):
        owner = "56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa"
        monkeypatch.setattr(passkey, "STILL", 0.2)
        monkeypatch.setattr(passkey, "OPEN", lambda url: True)
        with pytest.raises(passkey.UnlockFailed, match="no answer"):
            passkey.unlock(owner, ["Y3JlZA"], timeout=0.5)
        err = capsys.readouterr().err
        assert err.index("Waiting for the browser") < err.index("Still waiting… if the browser did not open, go to:\n  "
                                                                 + passkey.PAGE + "?mode=unlock&")
        monkeypatch.setattr(passkey, "OPEN", lambda url: pytest.fail("a browser was opened"))
        with pytest.raises(passkey.UnlockFailed, match="no answer"):
            passkey.unlock(owner, ["Y3JlZA"], timeout=0.3, no_browser=True)
        err = capsys.readouterr().err
        assert "Go to this address in your browser" in err and "Opening the browser" not in err
        assert "Still waiting" not in err

`OPENSHEAF_PASSPHRASE_COMMAND` gives the passphrase, before it is asked,
also where it would be asked twice; a command that gives nothing is said
so, and the passphrase is asked.

    # in wallet tests: passkey unlock:
    def test_passphrase_command(tmp_path, monkeypatch, capsys):
        monkeypatch.setenv(P.PASSPHRASE_COMMAND, "printf 'correct horse\\n'")
        monkeypatch.setattr("getpass.getpass", lambda prompt: pytest.fail("the passphrase was asked"))
        root = make_archive(tmp_path, "--keys", "github:me/keys")
        owner = P.ARCHIVE["owner"]
        assert keys.read_key(next(iter(in_repo(tmp_path).values())), "correct horse").owner == owner
        current = P.key_log(owner).latest().keys["keys"][0]
        r = ["--root", str(root)]
        run(*r, "key", "forget", current)
        monkeypatch.setenv(P.PASSPHRASE_COMMAND, "false")
        asked = []
        monkeypatch.setattr("getpass.getpass", lambda prompt: asked.append(prompt) or "correct horse")
        run(*r, "key", "pull")
        assert len(asked) == 1 and "gave no passphrase" in capsys.readouterr().err
