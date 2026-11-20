The tests of key wallets
========================

These tests check the security levels, the key wallets of
[chapter 9](09-wallets.md) and the commands that move keys
([chapter 19](19-owner-commands.md)). They must never reach the user's
GitHub account, keychain or clipboard: GitHub is a double, a script that
plays `gh` on a folder of the test, the clipboard a file of the test, the
key store a folder of files, as in the [other tests](70-tests.md). They are
in `tests/test_wallets.py`.

    # in tests/test_wallets.py:
    <<wallet tests: the imports and the doubles>>


    <<wallet tests: key files and texts>>


    <<wallet tests: the GitHub wallet refuses>>


    <<wallet tests: push, pull and list>>


    <<wallet tests: an owner in a wallet>>


    <<wallet tests: the clipboard>>


    <<wallet tests: a command wallet>>

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
    from pathlib import Path

    import pytest
    from nacl import pwhash

    from opensheaf import cli, core as P, keys, names, owners, wallet

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
a script. `gh_calls` reads the log of the double.

    # in wallet tests: the imports and the doubles:
    FAST = dict(opslimit=pwhash.argon2id.OPSLIMIT_MIN, memlimit=pwhash.argon2id.MEMLIMIT_MIN)


    @pytest.fixture(autouse=True)
    def doubles(tmp_path, monkeypatch, request):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv(keys.KEY_STORE, "file")
        monkeypatch.delenv(keys.SIGNING_KEY, raising=False)
        monkeypatch.delenv(P.PASSPHRASE, raising=False)
        monkeypatch.delenv(wallet.WALLET, raising=False)
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
        assert "kind current" in files[f"{owner}/{kid}.key.enc"] and "encryption argon2id" in files[f"{owner}/{kid}.key.enc"]
        run(*r, "key", "list", "--keys", "github:me/keys")
        out = capsys.readouterr().out
        assert out.split() == [owner, kid, "current", current, "v1"]
        seed = (tmp_path / "config" / "opensheaf" / "keys" / owner / f"{kid}.key").read_text().strip()
        run(*r, "key", "forget", current)
        assert local_keys(tmp_path, owner) == []
        run(*r, "key", "pull", "--keys", "github:me/keys")
        assert local_keys(tmp_path, owner) == [f"{kid}.key"]
        assert "1 current key(s)" in capsys.readouterr().out
        run(*r, "key", "forget", current)
        with pytest.raises(SystemExit, match="holds 0 of the current keys"):
            deposit(root, "p", "one", new=True)
        monkeypatch.setenv(wallet.WALLET, "github:me/keys")
        deposit(root, "p", "one", new=True)
        assert "pulled from github:me/keys" in capsys.readouterr().err
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
        assert all("encryption argon2id-secretbox" in t for t in files.values())
        assert {f"{owner}/{d[:16]}.key.enc" for d in v1["next"]} < set(files)
        assert local_keys(tmp_path, owner) == [f"{names.key_id(v1['keys'][0])}.key"]
        assert not (tmp_path / "usb").exists()
        r = ["--root", str(root)]
        P.configure(root)
        laptop = P.key_new(P.argparse_namespace(owner=None)).did
        run(*r, "owner", "rotate", "--add", laptop, "--keys", "github:me/keys")
        out2, err2 = capsys.readouterr()
        assert "rotation key(s) of v1 read from github:me/keys" in err2
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
