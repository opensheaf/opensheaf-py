# Generated from literate/73-tests-wallets.md by opensheaf-literate: edit the document, not this file.
"""Tests of key wallets, security levels and the commands that move keys (opensheaf-py),
against doubles of gh and of the clipboard."""

import base64
import json
import os
import re
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
    vis = repos[repo] if isinstance(repos[repo], str) else "private" if repos[repo] else "public"
    print(json.dumps({"full_name": repo, "private": vis != "public", "visibility": vis}))
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
    monkeypatch.setattr(wallet, "CLEAR_AFTER", 0)
    monkeypatch.setenv(keys.TEST_KEYS, ",".join(f"{request.node.name} {i}" for i in range(80)))
    monkeypatch.setattr(keys, "OPSLIMIT", FAST["opslimit"])
    monkeypatch.setattr(keys, "MEMLIMIT", FAST["memlimit"])
    keys.forget_seen()
    gh = tmp_path / "gh-state"
    gh.mkdir()
    (gh / "repos.json").write_text(json.dumps({"me/keys": True, "me/open": False, "me/papers": True,
                                                   "me/internal": "internal"}))
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
    with pytest.raises(wallet.WalletError, match="only locked with a passphrase"):
        wallet.put_key(None, owner, k, keys.ROTATION, 1, None)
    import unicodedata
    nfc, nfd = (unicodedata.normalize(f, "Élan café, crème brûlée") for f in ("NFC", "NFD"))
    assert nfc != nfd
    for one, other in ((nfc, nfd), (nfd, nfc)):
        for text in (keys.key_file_text(k, owner, keys.CURRENT, 2, one, **FAST),
                     keys.key_text(k, owner, passphrase=one, **FAST)):
            assert keys.read_key(text, other).key.did == k.did == keys.read_key(text, one).key.did
    with pytest.raises(keys.KeyStoreError, match="wrong passphrase"):
        keys.read_key(keys.key_text(k, owner, passphrase=nfc, **FAST), "Elan cafe, creme brulee")


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


def test_github_wallet_refuses(tmp_path, monkeypatch):
    import subprocess
    root = make_archive(tmp_path, "--export", str(tmp_path / "usb"), "--no-passphrase")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "https://github.com/me/papers"], check=True)
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    r = ["--root", str(root), "key", "push"]
    with pytest.raises(SystemExit, match="not a private repository"):
        run(*r, "--wallet", "github:me/open")
    with pytest.raises(SystemExit, match="not a private repository"):
        run(*r, "--wallet", "github:me/internal")
    with pytest.raises(SystemExit, match="repository of the archive"):
        run(*r, "--wallet", "github:me/papers")
    with pytest.raises(SystemExit, match="No repository me/missing"):
        run(*r, "--wallet", "github:me/missing")
    monkeypatch.setenv("FAKE_GH_AUTH", "0")
    with pytest.raises(SystemExit, match="not signed in"):
        run(*r, "--wallet", "github:me/keys")
    monkeypatch.setattr(wallet, "GH", str(tmp_path / "no-gh"))
    with pytest.raises(SystemExit, match="needs the GitHub CLI"):
        run(*r, "--wallet", "github:me/keys")
    assert not [c for c in gh_calls(tmp_path) if "PUT" in c or "DELETE" in c]
    assert in_repo(tmp_path, "me/open") == {} and in_repo(tmp_path, "me/papers") == {}


def test_forget_asks_and_reports(tmp_path, monkeypatch, capsys):
    import types
    root = make_archive(tmp_path, "--export", str(tmp_path / "usb"), "--no-passphrase")
    owner = P.ARCHIVE["owner"]
    current = P.key_log(owner).latest().keys["keys"][0]
    r = ["--root", str(root)]
    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(SystemExit, match="(?i)not confirmed"):
        run(*r, "key", "forget", current)
    assert local_keys(tmp_path, owner) != []
    assert "a current key of the latest version" in capsys.readouterr().err
    folder = tmp_path / "config" / "opensheaf" / "keys" / owner
    folder.chmod(0o500)
    try:
        with pytest.raises(SystemExit, match="(?i)not removed from this computer"):
            run(*r, "key", "forget", current, "--yes")
    finally:
        folder.chmod(0o700)
    monkeypatch.setenv(keys.KEY_STORE, "security")
    monkeypatch.setattr(keys.sys, "platform", "darwin")
    monkeypatch.setattr(keys.shutil, "which", lambda name: "/stub/" + name)
    answers = iter([types.SimpleNamespace(returncode=44, stderr=""),
                    types.SimpleNamespace(returncode=51, stderr="User interaction is not allowed.")])
    monkeypatch.setattr(keys.subprocess, "run", lambda cmd, **kw: next(answers))
    assert keys.forget_current_key(owner, current) == []
    assert keys.forget_current_key(owner, current) == [("security", "User interaction is not allowed.")]


def test_push_pull_list(tmp_path, monkeypatch, capsys):
    root = make_archive(tmp_path, "--export", str(tmp_path / "usb"), "--no-passphrase")
    owner = P.ARCHIVE["owner"]
    current = P.key_log(owner).latest().keys["keys"][0]
    kid = names.key_id(current)
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    r = ["--root", str(root)]
    capsys.readouterr()
    run(*r, "key", "push", "--wallet", "github:me/keys")
    out, err = capsys.readouterr()
    assert wallet.risk("github:me/keys", owner) in err and out == "Done: 1 current key of " \
        f"{names.short(owner)} saved to github:me/keys, locked with your passphrase.\n" \
        f"The key wallet github:me/keys is recorded in osheaf.json for {names.short(owner)} " \
        "(osheaf key wallet --remove github:me/keys removes it).\n"
    assert json.loads((root / "osheaf.json").read_text())["keys"] == {owner: {"wallets": ["github:me/keys"]}}
    files = in_repo(tmp_path)
    assert list(files) == [f"{owner}/{kid}.key.enc"]
    assert "kind current" in files[f"{owner}/{kid}.key.enc"] and "wrap passphrase argon2id" in files[f"{owner}/{kid}.key.enc"]
    run(*r, "key", "list", "--wallet", "github:me/keys")
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "The wallet github:me/keys holds 1 key:"
    assert out[1].split() == ["Owner", "Kind", "Key", "Version", "Locks"]
    assert out[2].split() == [names.short(owner), "current", names.short(current), "v1", "passphrase"]
    seed = (tmp_path / "config" / "opensheaf" / "keys" / owner / f"{kid}.key").read_text().strip()
    run(*r, "key", "forget", current, "--yes")
    assert local_keys(tmp_path, owner) == []
    run(*r, "key", "pull", "--wallet", "github:me/keys")
    assert local_keys(tmp_path, owner) == [f"{kid}.key"]
    assert "Pulled 1 current key of" in capsys.readouterr().out
    run(*r, "key", "forget", current, "--yes")
    run(*r, "key", "wallet", "--remove", "github:me/keys")
    with pytest.raises(SystemExit, match="holds 0 of the current keys"):
        deposit(root, "p", "one", new=True)
    monkeypatch.setenv(wallet.WALLET, "github:me/keys")
    deposit(root, "p", "one", new=True)
    assert "Pulling the current key of " in capsys.readouterr().err
    assert local_keys(tmp_path, owner) == [f"{kid}.key"] and P.verify_errors() == []
    assert seed not in capsys.readouterr().out


def test_owner_in_a_github_wallet(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    root = make_archive(tmp_path, "--keys", "github:me/keys")
    out, err = capsys.readouterr()
    owner = P.ARCHIVE["owner"]
    assert json.loads((root / "osheaf.json").read_text())["keys"] == {owner: {"wallets": ["github:me/keys"]}}
    assert f"The key wallet github:me/keys is recorded in osheaf.json for {names.short(owner)}" in out
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
    assert "Moved up to the maximum security level" in err3
    v3 = P.key_log(owner).latest().keys
    assert not {f"{owner}/{d[:16]}.key.enc" for d in v3["next"]} & set(in_repo(tmp_path))
    assert len(list((tmp_path / "usb").glob("rotation-*.txt"))) == 3
    run(*r, "key", "forget", "--from-wallet", "--used", "--yes")
    assert sorted(in_repo(tmp_path)) == sorted(f"{owner}/{names.key_id(d)}.key.enc" for d in v3["keys"])
    with pytest.raises(SystemExit, match="holds 0 of the rotation keys of v3"):
        run(*r, "owner", "rotate", "--export", str(tmp_path / "usb2"), "--yes")
    usb = sorted(str(f) for f in (tmp_path / "usb").glob("rotation-*.txt"))
    run(*r, "owner", "rotate", "--rotation-key", usb[0], "--rotation-key", usb[1],
        "--export", str(tmp_path / "usb2"), "--yes")
    assert len(P.key_log(owner).versions) == 4 and P.verify_errors() == []
    out4 = out + out2 + out3 + capsys.readouterr().out
    assert "seed" not in out4 and "correct horse" not in out4 + err + err2 + err3


def test_wallet_keeps_needed_rotation_keys(tmp_path, monkeypatch):
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    root = make_archive(tmp_path, "--keys", "github:me/keys")
    owner = P.ARCHIVE["owner"]
    nxt = P.key_log(owner).latest().keys["next"]
    rotation = next(t for t in in_repo(tmp_path).values() if f"digest {nxt[0]}" in t)
    did = next(x.split()[1] for x in rotation.splitlines() if x.startswith("key "))
    r = ["--root", str(root)]
    with pytest.raises(SystemExit, match="--force removes them"):
        run(*r, "key", "forget", "--from-wallet", did, "--yes")
    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(SystemExit, match="Not confirmed"):
        run(*r, "key", "forget", "--from-wallet", did, "--force")
    assert len(in_repo(tmp_path)) == 4
    monkeypatch.delenv(P.PASSPHRASE)
    asked = []
    monkeypatch.setattr("getpass.getpass", lambda prompt: asked.append(prompt) or "correct horse")
    run(*r, "owner", "rotate", "--keys", "github:me/keys")
    assert len(asked) == 1 and len(P.key_log(owner).versions) == 2


def test_wallets_of_each_owner(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    repos = json.loads((tmp_path / "gh-state" / "repos.json").read_text())
    (tmp_path / "gh-state" / "repos.json").write_text(json.dumps({**repos, "me/other": True}))
    root = make_archive(tmp_path, "--keys", "github:me/keys")
    first = P.ARCHIVE["owner"]
    r = ["--root", str(root)]
    run(*r, "owner", "init", "--keys", "github:me/other")
    cfg = json.loads((root / "osheaf.json").read_text())
    second = cfg["owners"][0]
    assert cfg["keys"] == {first: {"wallets": ["github:me/keys"]}, second: {"wallets": ["github:me/other"]}}
    assert any(f.startswith(f"{second}/") for f in in_repo(tmp_path, "me/other"))
    capsys.readouterr()
    run(*r, "key", "list", "--owner", second)
    assert capsys.readouterr().out.startswith("The wallet github:me/other holds 4 keys of")
    # one owner, two wallets: a hint added, the first holding its keys used
    run(*r, "key", "push", "--wallet", "github:me/other")
    assert json.loads((root / "osheaf.json").read_text())["keys"][first] == \
        {"wallets": ["github:me/keys", "github:me/other"]}
    P.configure(root)
    assert P.configured_wallet(first).name == "github:me/keys"
    run(*r, "key", "wallet", "--add", "github:me/missing")
    run(*r, "key", "wallet", "--remove", "github:me/keys")
    P.configure(root)
    assert P.ARCHIVE["keys"][first] == {"wallets": ["github:me/other", "github:me/missing"]}
    assert P.configured_wallet(first).name == "github:me/other"
    capsys.readouterr()
    run(*r, "key", "wallet")
    assert capsys.readouterr().out == f"The keys of {names.short(first)} are looked for in, in order:\n" \
        "  github:me/other    osheaf.json\n  github:me/missing  osheaf.json\n"
    run(*r, "key", "wallet", "--remove", "github:me/missing")
    with pytest.raises(SystemExit, match="GitHub wallets only"):
        run(*r, "key", "wallet", "--add", "command")
    with pytest.raises(SystemExit, match="not an owner of this archive"):
        run(*r, "key", "wallet", "--owner", "a" * 52, "--add", "github:me/keys")
    # the person's wallets, in the configuration file
    user = tmp_path / "config" / "opensheaf" / "config.json"
    user.parent.mkdir(parents=True, exist_ok=True)
    user.write_text(json.dumps({"other": 1}))
    run(*r, "key", "wallets", "--add", "github:me/keys")
    run(*r, "key", "wallets", "--add", "github:me/nothing")
    assert json.loads(user.read_text()) == {"other": 1, "wallets": ["github:me/keys", "github:me/nothing"]}
    capsys.readouterr()
    run(*r, "key", "wallets")
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "github:me/other (osheaf.json):"
    assert sorted(x.split() for x in out[1:3]) == sorted([[names.short(first), "1", "key", "passphrase"],
                                                          [names.short(second), "4", "keys", "passphrase"]])
    assert out[3] == f"github:me/keys ({user}):" and out[4].split() == [names.short(first), "4", "keys", "passphrase"]
    assert out[5] == f"github:me/nothing ({user}):" and out[6].startswith("  cannot be read") or out[6] == "  holds no key"
    run(*r, "key", "wallet", "--owner", first, "--remove", "github:me/other")
    P.configure(root)
    assert P.configured_wallet(first).name == "github:me/keys"
    run(*r, "key", "wallets", "--remove", "github:me/nothing")
    assert json.loads(user.read_text())["wallets"] == ["github:me/keys"]
    with pytest.raises(SystemExit, match="not one of your wallets"):
        run(*r, "key", "wallets", "--remove", "github:me/nothing")
    # the user's "keys", after the user's wallets; one wallet for the archive, no longer read
    user.write_text(json.dumps({"keys": {"wallet": "github:me/keys"}}))
    cfg = json.loads((root / "osheaf.json").read_text())
    cfg["keys"] = {second: {"wallets": ["github:me/other"]}}
    (root / "osheaf.json").write_text(json.dumps(cfg, indent=2) + "\n")
    P.configure(root)
    assert P.configured_wallet(second).name == "github:me/other"
    assert P.configured_wallet(first).name == "github:me/keys"      # the user's: none hinted for it
    cfg["keys"] = {"wallet": "github:me/other"}
    (root / "osheaf.json").write_text(json.dumps(cfg, indent=2) + "\n")
    P.configure(root)
    with pytest.raises(SystemExit, match="no longer read"):
        P.configured_wallet(first)
    cfg["keys"] = {second: {"wallets": ["github:me/other"]}}
    (root / "osheaf.json").write_text(json.dumps(cfg, indent=2) + "\n")
    P.configure(root)
    monkeypatch.setenv(wallet.WALLET, "github:me/env")
    assert P.configured_wallet(first).name == "github:me/env"
    monkeypatch.delenv(wallet.WALLET)
    # a command wallet: never in osheaf.json
    cfg["keys"] = {second: {"wallets": ["command"]}}
    (root / "osheaf.json").write_text(json.dumps(cfg, indent=2) + "\n")
    P.configure(root)
    with pytest.raises(SystemExit, match="configures a command wallet"):
        P.configured_wallet(first)


def test_a_hinted_wallet_is_confirmed(tmp_path, monkeypatch):
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    repos = json.loads((tmp_path / "gh-state" / "repos.json").read_text())
    (tmp_path / "gh-state" / "repos.json").write_text(json.dumps({**repos, "eve/keys": True}))
    root = make_archive(tmp_path, "--export", str(tmp_path / "usb"), "--no-passphrase")
    owner = P.ARCHIVE["owner"]
    r = ["--root", str(root)]
    cfg = json.loads((root / "osheaf.json").read_text())
    cfg["keys"] = {owner: {"wallets": ["github:eve/keys"]}}
    (root / "osheaf.json").write_text(json.dumps(cfg, indent=2) + "\n")
    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(SystemExit, match="(?i)not confirmed: nothing was put into github:eve/keys"):
        run(*r, "key", "push")
    assert in_repo(tmp_path, "eve/keys") == {}
    run(*r, "key", "push", "--wallet", "github:me/keys")
    user = tmp_path / "config" / "opensheaf" / "config.json"
    user.parent.mkdir(parents=True, exist_ok=True)
    user.write_text(json.dumps({"wallets": ["github:me/keys"]}))
    P.configure(root)
    assert P.configured_wallet(owner).name == "github:me/keys"
    run(*r, "key", "push")
    assert in_repo(tmp_path, "eve/keys") == {}
    user.write_text(json.dumps({}))
    (root / "osheaf.json").write_text(json.dumps(cfg, indent=2) + "\n")
    run(*r, "key", "push", "--yes")
    assert in_repo(tmp_path, "eve/keys") != {}


def test_an_explicit_wallet_wins(monkeypatch, capsys):
    import types
    given, configured = types.SimpleNamespace(name="github:me/given"), types.SimpleNamespace(name="github:me/conf")
    held = {"github:me/given": ["k"], "github:me/conf": ["k"]}
    monkeypatch.setattr(P, "level_wallet", lambda args, owner=None: given if args.keys else None)
    monkeypatch.setattr(P, "configured_wallet", lambda owner=None: configured)
    monkeypatch.setattr(P, "wallet_rotation_keys", lambda w, owner, prev: held[w.name])
    prev = types.SimpleNamespace(number=1, keys={"nextThreshold": 1, "next": []})
    args = lambda keys=None: types.SimpleNamespace(rotation_key=None, keys=keys)
    assert P.rotation_signers(args("github:me/given"), "o", prev)[1] is given
    assert P.rotation_signers(args(), "o", prev)[1] is configured
    held["github:me/given"] = []
    assert P.rotation_signers(args("github:me/given"), "o", prev)[1] is configured
    assert "reading from github:me/conf" in capsys.readouterr().err


def test_a_passphrase_per_place(monkeypatch):
    import getpass
    typed = iter(["for the files", "for the wallet"])
    monkeypatch.setattr(getpass, "getpass", lambda prompt: next(typed))
    P.forget_passphrase()
    assert P.passphrase(confirm=False) == "for the files"
    assert P.passphrase(confirm=False) == "for the files"
    assert P.passphrase(confirm=False, where="github:me/keys") == "for the wallet"
    assert P.passphrase(confirm=False, where="github:me/keys") == "for the wallet"
    P.forget_passphrase()


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
    run(*r, "key", "forget", current, "--yes")
    run(*r, "key", "import", "--clipboard")
    assert local_keys(tmp_path, owner) == [f"{names.key_id(current)}.key"]
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    run(*r, "key", "export", "--clipboard", "--encrypt")
    assert "encryption argon2id-secretbox" in (tmp_path / "clipboard.txt").read_text()
    run(*r, "key", "forget", current, "--yes")
    monkeypatch.delenv(P.PASSPHRASE)
    monkeypatch.setattr("getpass.getpass", lambda prompt: "wrong horse")
    with pytest.raises(SystemExit, match="Wrong passphrase"):
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
    import time
    clipboard = tmp_path / "clipboard.txt"
    monkeypatch.setattr(wallet, "CLEAR_AFTER", 0.3)
    run(*r, "key", "export", "--clipboard")
    assert "Universal Clipboard" in capsys.readouterr().err
    for _ in range(100):
        if clipboard.read_text() == "":
            break
        time.sleep(0.05)
    assert clipboard.read_text() == ""
    run(*r, "key", "export", "--clipboard")
    clipboard.write_text("something else")
    time.sleep(1.0)
    assert clipboard.read_text() == "something else"


def test_command_wallet(tmp_path, monkeypatch, capsys):
    root = make_archive(tmp_path, "--export", str(tmp_path / "usb"), "--no-passphrase")
    owner = P.ARCHIVE["owner"]
    vault = tmp_path / "vault"
    vault.mkdir()

    def commands(folder):
        return {"wallet": "command", "read": f"cat '{folder}/{{owner}}-{{k}}-{{kind}}.txt'",
                "write": f"cat > '{folder}/{{owner}}-{{k}}-{{kind}}.txt'",
                "list": f"ls '{folder}' | sed 's/-/ /g'"}

    user = wallet.user_config_path()
    user.parent.mkdir(parents=True, exist_ok=True)
    user.write_text(json.dumps({"keys": commands(vault)}))
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    r = ["--root", str(root)]
    usb = sorted(str(f) for f in (tmp_path / "usb").glob("rotation-*.txt"))
    capsys.readouterr()
    run(*r, "owner", "rotate", "--keys", "command", "--rotation-key", usb[0], "--rotation-key", usb[1])
    assert wallet.risk("command", owner) in capsys.readouterr().err
    held = sorted(f.name.rsplit("-", 1)[1] for f in vault.iterdir())
    assert held == ["current.txt"] + ["rotation.txt"] * 3
    run(*r, "key", "list")
    rows = capsys.readouterr().out.splitlines()[2:]
    assert len(rows) == 4 and sorted(x.split()[1] for x in rows) == ["current"] + ["rotation"] * 3
    assert all(x.endswith("  passphrase") for x in rows)
    run(*r, "owner", "rotate", "--keys", "command")
    assert len(P.key_log(owner).versions) == 3 and len(list(vault.iterdir())) == 7
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv(wallet.WALLET, json.dumps(commands(other)))
    with pytest.raises(SystemExit, match="The wallet command holds 0 of the rotation keys"):
        run(*r, "owner", "end", "--yes")
    monkeypatch.setenv(wallet.WALLET, "command")
    run(*r, "owner", "end", "--yes")
    assert P.key_log(owner).ended and P.verify_errors() == []
    monkeypatch.delenv(wallet.WALLET)
    cfg = json.loads((root / "osheaf.json").read_text())
    planted = tmp_path / "planted"
    cfg["keys"] = {"wallet": "command", "read": f"touch '{planted}'", "write": f"touch '{planted}'",
                   "list": f"touch '{planted}'"}
    (root / "osheaf.json").write_text(json.dumps(cfg))
    with pytest.raises(SystemExit, match="Move .keys. to .*config.json"):
        run(*r, "key", "list")
    assert not planted.exists()
    cfg["keys"] = {owner: {"wallets": ["github:me/keys"]}}
    (root / "osheaf.json").write_text(json.dumps(cfg))
    user.unlink()
    run(*r, "key", "list")


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
    assert "encryption envelope-secretbox\nwrap passphrase argon2id" in new and "wrap passkey prf rp=unlock.opensheaf.org " \
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


def test_passkey_wraps_old_and_removed():
    owner = "a" * 52
    k = keys.example_key("wallet passkey")
    old_rp = keys.Passkey("b2xkLWNyZWRlbnRpYWw", keys.passkey_salt(owner), rp="opensheaf.org",
                          kek=keys.passkey_kek(b"\4" * 32))
    new_rp = keys.Passkey("bmV3LWNyZWRlbnRpYWw", keys.passkey_salt(owner), kek=keys.passkey_kek(b"\5" * 32))
    text = keys.key_file_text(k, owner, keys.CURRENT, 1, "pass", passkeys=[old_rp, new_rp], **FAST)
    assert "wrap passkey prf rp=opensheaf.org cred=b2xkLWNyZWRlbnRpYWw" in text
    assert keys.read_key(text, keks={old_rp.cred: old_rp.kek}).key.did == k.did
    found = {p.cred: p for p in keys.passkeys_of(text)}
    assert found[old_rp.cred].rp == "opensheaf.org" and found[new_rp.cred].rp == "unlock.opensheaf.org"
    assert found[new_rp.cred].opens(new_rp.kek) and not found[new_rp.cred].opens(old_rp.kek)
    moved = keys.remove_passkeys(text, rp="opensheaf.org")
    assert "rp=opensheaf.org" not in moved and moved.count("wrap passkey") == 1
    assert keys.read_key(moved, "pass").key.did == keys.read_key(moved, keks={new_rp.cred: new_rp.kek}).key.did
    bare = keys.remove_passkeys(moved, cred=new_rp.cred)
    assert "wrap passkey" not in bare and keys.read_key(bare, "pass").key.did == k.did
    assert keys.remove_passkeys(bare, rp="opensheaf.org") == bare
    with pytest.raises(keys.KeyStoreError):
        keys.remove_passkeys(text)
    a = pwhash.argon2id
    for ops, mem in ((a.OPSLIMIT_SENSITIVE + 1, a.MEMLIMIT_MIN), (a.OPSLIMIT_MIN, a.MEMLIMIT_SENSITIVE * 4),
                     (0, a.MEMLIMIT_MIN)):
        costly = text.replace(f"opslimit={FAST['opslimit']} memlimit={FAST['memlimit']}",
                              f"opslimit={ops} memlimit={mem}")
        with pytest.raises(keys.KeyStoreError, match="out of bounds"):
            keys.read_key(costly, "pass")


HAND_OFF = {"sk": "3MnQ1WVJ9j-gIHW04onidnPAdXBkj8Ex38awjc_xIFU", "pk": "EDUGNAoWiXZye3oZT1uexqCDj6g-_pOiwL6N01HzQX0",
            "esk": "XsIioGnOBETGr9GuOkvzh0s9Mnee8lz8KkfLHClLxGc", "epk": "wz_hpV5NNJh92Eqb4TE6dA7IVbA2LrWBmV8GisGgjBE",
            "state": "Zaz8C5ywR4VKbNOX7dQHUg", "mode": "unlock",
            "owner": "em4v3kp5btra7jlggxhvl5y6uluymzk2ezcdjg4pnptnk5tygora", "cred": "ZmFrZS1wYXNza2V5LWNyZWRlbnRpYWw",
            "secret": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8",
            "ct": "715olE38lfUKZdHslhzg2vWDWtGo88nSvuZNo4v-Hrc", "tag": "2MlYwfCCb9AS4OVAMHXml-cxWi4HCPyd34BNYNVGeyU",
            "code": "371 704"}


def test_hand_off_vector():
    text = ("state", "mode", "owner", "cred", "code")
    v = {k: x if k in text else passkey.from_b64url(x) for k, x in HAND_OFF.items()}
    sk, esk = PrivateKey(v["sk"]), PrivateKey(v["esk"])
    assert bytes(sk.public_key) == v["pk"] and bytes(esk.public_key) == v["epk"]
    assert v["secret"] == bytes(range(32))
    context = (v["state"], v["mode"], v["owner"], v["cred"])
    assert passkey.seal(v["secret"], v["pk"], *context, esk) == (v["epk"], v["ct"], v["tag"])
    assert passkey.unseal(sk, v["epk"], v["ct"], v["tag"], *context) == v["secret"]
    assert passkey.confirmation_code(v["state"], v["pk"]) == v["code"]
    changed = [(v["epk"], v["ct"], v["tag"], "another state", *context[1:]),
               (v["epk"], v["ct"], v["tag"], v["state"], "enroll", *context[2:]),
               (v["epk"], v["ct"], v["tag"], *context[:2], "a" * 52, v["cred"]),
               (v["epk"], v["ct"], v["tag"], *context[:3], "b3RoZXI"),
               (v["epk"], bytes([v["ct"][0] ^ 1]) + v["ct"][1:], v["tag"], *context),
               (v["epk"], v["ct"], bytes(32), *context),
               (bytes(sk.public_key), v["ct"], v["tag"], *context)]
    for args in changed:
        with pytest.raises(ValueError):
            passkey.unseal(sk, *args)
    with pytest.raises(ValueError):
        passkey.unseal(sk, v["epk"], v["ct"][:16], v["tag"], *context)
    assert passkey.hkdf(b"\x0b" * 22, bytes(range(13)), bytes(range(0xf0, 0xfa)), 42).hex() == (
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kw):
        return None


def follow_start(url):
    """The address of the page that the listener at URL, its /start, sends the browser to."""
    assert re.fullmatch(r"http://127\.0\.0\.1:[0-9]+/start", url)
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect).open(url, timeout=5)
    h = e.value.headers
    assert e.value.code == 302 and h["Cache-Control"] == "no-store" and h["Referrer-Policy"] == "no-referrer"
    return h["Location"]


def fake_browser(opened, answer="secret", cred="ZmFrZS1wYXNza2V5LWNyZWRlbnRpYWw"):
    def opener(url):
        url = follow_start(url)
        assert url.startswith(passkey.UNLOCK_PAGE + "#") and "?" not in url
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).fragment).items()}
        assert "salt" not in q
        opened.append(q)
        if answer == "none":
            return True
        salt = keys.passkey_salt(q["owner"])
        if q["mode"] == "enroll":
            used = cred if cred not in q.get("cred", "").split(",") else None
        else:
            used = q["cred"].split(",")[0]
        fields = {"state": q["state"] if answer != "wrong state" else "W" * 22}
        if answer in ("error", "x25519-unavailable") or used is None:
            fields["error"] = ("InvalidStateError: a passkey of this owner is here already" if used is None
                               else "NotAllowedError: the user cancelled" if answer == "error" else answer)
        else:
            prf = names.sha256(b"fake prf " + used.encode() + salt)
            if answer == "forged":
                prf = names.sha256(b"forged")
            pk = passkey.from_b64url(q["pk"])
            epk, ct, tag = passkey.seal(prf, pk, q["state"], q["mode"], q["owner"], used)
            if answer == "tampered":
                ct = bytes(32)
            fields.update(epk=passkey.b64url(epk), ct=passkey.b64url(ct), tag=passkey.b64url(tag), cred=used)
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
    assert len(asked) == 1 and [q["mode"] for q in opened if "mode" in q] == ["enroll", "unlock"]
    assert "cred" not in opened[0] and opened[2]["cred"] == "ZmFrZS1wYXNza2V5LWNyZWRlbnRpYWw"
    assert opened[0]["owner"] == owner and len(passkey.from_b64url(opened[0]["pk"])) == 32
    assert asked == ["Passphrase of the keys in github:me/keys: "]
    out, err = capsys.readouterr()
    short = names.short(owner)
    assert out == f"Done: the 4 keys of {short} open with your passkey (Touch ID) and still with your passphrase.\n"
    assert f"Opening the 4 keys of {short} in github:me/keys with the passphrase…" in err
    assert "  1/4 " in err and "  4/4 " in err and f"Adding a passkey lock to the 4 keys of {short} in github:me/keys…" in err
    assert "Opening the browser to create a passkey for" in err and "Still waiting" not in err
    assert passkey.UNLOCK_PAGE not in err and "(s)" not in out + err
    assert err.count("Check that the browser shows the code ") == 2
    went = [q["went"] for q in opened if "went" in q]
    assert "secret" not in went[0] and "&ct=" in went[0] and "&tag=" in went[0]
    files = in_repo(tmp_path)
    assert len(files) == 4 and all("encryption envelope-secretbox\nwrap passphrase argon2id" in t
                                   and "wrap passkey prf rp=unlock.opensheaf.org cred=ZmFrZS1w" in t
                                   for t in files.values())
    run(*r, "key", "enroll")
    assert "already" in capsys.readouterr().out and len(opened) == 4 and len(asked) == 1
    run(*r, "key", "forget", current, "--yes")
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
    assert len([q for q in opened if "mode" in q]) == 4 and len(asked) == 2
    v2 = P.key_log(owner).latest().keys
    new = [in_repo(tmp_path)[f"{owner}/{d[:16]}.key.enc"] for d in v2["next"]]
    assert all("wrap passkey" in t for t in new) and P.verify_errors() == []
    out2, err2 = capsys.readouterr()
    assert "correct horse" not in out + err + out2 + err2 and "secret=" not in err + err2


def test_enroll_another_passkey(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    root = make_archive(tmp_path, "--keys", "github:me/keys")
    opened = []
    monkeypatch.setattr(passkey, "OPEN", fake_browser(opened))
    r = ["--root", str(root)]
    run(*r, "key", "enroll")
    before = in_repo(tmp_path)
    with pytest.raises(SystemExit, match="InvalidStateError"):
        run(*r, "key", "enroll", "--new-passkey")
    assert opened[-2]["mode"] == "enroll" and opened[-2]["cred"] == "ZmFrZS1wYXNza2V5LWNyZWRlbnRpYWw"
    assert in_repo(tmp_path) == before
    pages = [fake_browser(opened, "forged", cred="Zm9yZ2VkLWNyZWRlbnRpYWw"),
             fake_browser(opened, cred="Zm9yZ2VkLWNyZWRlbnRpYWw")]
    monkeypatch.setattr(passkey, "OPEN", lambda url: pages.pop(0)(url))
    with pytest.raises(SystemExit, match="did not give the same secret twice"):
        run(*r, "key", "enroll", "--new-passkey")
    assert in_repo(tmp_path) == before
    monkeypatch.setattr(passkey, "OPEN", fake_browser(opened, cred="YW5vdGhlci1wcm92aWRlcg"))
    run(*r, "key", "enroll", "--new-passkey")
    assert all(t.count("wrap passkey prf rp=unlock.opensheaf.org") == 2 for t in in_repo(tmp_path).values())
    capsys.readouterr()
    run(*r, "key", "wallets")
    assert capsys.readouterr().out.splitlines()[1].split()[1:] == ["4", "keys", "passphrase,", "2", "passkeys"]


def test_forged_answers_are_not_kept(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    root = make_archive(tmp_path, "--keys", "github:me/keys")
    owner = P.ARCHIVE["owner"]
    current = P.key_log(owner).latest().keys["keys"][0]
    opened = []
    monkeypatch.setattr(passkey, "OPEN", fake_browser(opened))
    r = ["--root", str(root)]
    run(*r, "key", "enroll")
    monkeypatch.delenv(P.PASSPHRASE)
    asked = []
    monkeypatch.setattr("getpass.getpass", lambda prompt: asked.append(prompt) or "correct horse")
    forged_kek = keys.passkey_kek(names.sha256(b"forged"))
    for answer, said in (("forged", "opens no key"), ("tampered", "damaged")):
        run(*r, "key", "forget", current, "--yes")
        monkeypatch.setattr(passkey, "OPEN", fake_browser(opened, answer))
        capsys.readouterr()
        run(*r, "key", "pull")
        assert said in capsys.readouterr().err and local_keys(tmp_path, owner) != []
    assert len(asked) == 2
    deposit(root, "p", "one", new=True)
    monkeypatch.setattr(passkey, "OPEN", fake_browser(opened, "forged"))
    run(*r, "owner", "rotate", "--keys", "github:me/keys")
    v2 = P.key_log(owner).latest().keys
    for d in v2["next"]:
        text = in_repo(tmp_path)[f"{owner}/{d[:16]}.key.enc"]
        assert not any(p.opens(forged_kek) for p in keys.passkeys_of(text))
    P.forget_passphrase()
    w = wallet.parse("github:me/keys")
    kid = names.key_id(current)
    monkeypatch.setattr(passkey, "unlock", lambda owner, creds, **kw: (creds[0], names.sha256(b"forged")))
    assert P.unlock_key(w, owner, kid, keys.CURRENT).did == current
    assert P.unlocked_passkeys(owner) == []
    P.forget_passphrase()
    monkeypatch.setattr(passkey, "unlock", lambda owner, creds, **kw: (None, names.sha256(b"forged")))
    assert P.unlock_key(w, owner, kid, keys.CURRENT).did == current and P.unlocked_passkeys(owner) == []
    P.forget_passphrase()


def test_move_from_the_first_relying_party(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    root = make_archive(tmp_path, "--keys", "github:me/keys")
    owner = P.ARCHIVE["owner"]
    current = P.key_log(owner).latest().keys["keys"][0]
    repo = tmp_path / "gh-state" / "contents" / "me" / "keys" / owner
    old = keys.Passkey("b2xkLWNyZWRlbnRpYWw", keys.passkey_salt(owner), rp="opensheaf.org",
                       kek=keys.passkey_kek(b"\4" * 32))
    for f in repo.iterdir():
        f.write_text(keys.add_passkey(f.read_text(), "correct horse", old))
    monkeypatch.delenv(P.PASSPHRASE)
    asked = []
    monkeypatch.setattr("getpass.getpass", lambda prompt: asked.append(prompt) or "correct horse")
    r = ["--root", str(root)]
    run(*r, "key", "forget", current, "--yes")
    capsys.readouterr()
    run(*r, "key", "pull")
    err = capsys.readouterr().err
    assert "was enrolled on opensheaf.org" in err and "osheaf key enroll --new-passkey" in err
    assert len(asked) == 1 and local_keys(tmp_path, owner) != []
    opened = []
    monkeypatch.setattr(passkey, "OPEN", fake_browser(opened))
    run(*r, "key", "enroll")
    assert [q["mode"] for q in opened if "mode" in q] == ["enroll", "unlock"] and "cred" not in opened[0]
    assert all("rp=opensheaf.org" in t and "rp=unlock.opensheaf.org" in t for t in in_repo(tmp_path).values())
    prompts = []
    with pytest.raises(SystemExit, match="Not confirmed: nothing was removed"):
        monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "no")
        run(*r, "key", "forget", "--rp", "opensheaf.org")
    assert prompts == ["Type forget to confirm: "]
    capsys.readouterr()
    run(*r, "key", "forget", "--rp", "opensheaf.org", "--yes")
    out, err = capsys.readouterr()
    short = names.short(owner)
    listed = err.splitlines()
    assert listed[0] == f"Removing the opensheaf.org passkey lock from 4 keys of {short} in github:me/keys:"
    assert sorted(x.split()[0] for x in listed[1:5]) == ["current"] + ["rotation"] * 3
    assert [x.split()[0] for x in listed[5:]] == ["1/4", "2/4", "3/4", "4/4"]
    assert all(x.endswith("  lock removed") for x in listed[5:])
    assert out == "Done: the 4 keys open with your passkey (unlock.opensheaf.org) and your passphrase.\n"
    files = in_repo(tmp_path).values()
    assert all("rp=opensheaf.org" not in t and "rp=unlock.opensheaf.org" in t for t in files)
    assert all(keys.read_key(t, "correct horse").owner == owner for t in files)
    run(*r, "key", "forget", "--passkey", "ZmFrZS1wYXNza2V5LWNyZWRlbnRpYWw", "--yes")
    assert all("wrap passkey" not in t for t in in_repo(tmp_path).values())
    run(*r, "key", "forget", "--rp", "opensheaf.org", "--yes")
    assert "No key of" in capsys.readouterr().out


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
        run(*r, "key", "forget", current, "--yes")
        monkeypatch.setattr(passkey, "OPEN", fake_browser(opened, answer))
        run(*r, "key", "pull")
        assert said in capsys.readouterr().err and local_keys(tmp_path, owner) != []
    assert len(asked) == 4 and {"status": 403} in opened
    run(*r, "key", "forget", current, "--yes")
    monkeypatch.setenv(passkey.UNLOCK, "passphrase")
    monkeypatch.setattr(passkey, "OPEN", lambda url: pytest.fail("a browser was opened"))
    run(*r, "key", "pull")
    assert len(asked) == 5 and local_keys(tmp_path, owner) != []
    monkeypatch.setattr(passkey, "OPEN", fake_browser(opened, "error"))
    with pytest.raises(SystemExit, match="did not unlock"):
        run(*r, "key", "unlock")


def test_listener():
    import socket
    import time
    owner = "56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa"
    got, idle = [], []

    def opener(url):
        url = follow_start(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).fragment).items()}
        idle.append(socket.create_connection(("127.0.0.1", int(q["port"]))))
        o = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base = f"http://127.0.0.1:{q['port']}"
        s, short = q["state"], passkey.b64url(b"short")
        v1 = f"epk={short}&ct={short}&cred=Y3JlZA"
        for path in (f"/other?state={s}&error=x", f"/callback?state={s}&secret=AAAA&error=x",
                     f"/callback?state={s}&epk=AAAA", f"/callback?state={s}&error=x&error=y",
                     f"/callback?state={s}&{v1}&tag={short}&more=1", f"/callback?state={s}&{v1}", None,
                     f"/callback?state={s}&{v1}&tag={short}"):
            try:
                data = b"state=" + s.encode() if path is None else None
                got.append(o.open(base + (path or "/callback"), data=data, timeout=5).status)
            except urllib.error.HTTPError as e:
                got.append(e.code)
        return True

    passkey.OPEN = opener
    started = time.monotonic()
    try:
        with pytest.raises(passkey.UnlockFailed, match="damaged"):
            passkey.unlock(owner, ["Y3JlZA"], no_browser=False)
    finally:
        passkey.OPEN = lambda url: pytest.fail("a browser was opened")
        for c in idle:
            c.close()
    assert got == [404, 400, 400, 400, 400, 400, 501, 200] and time.monotonic() - started < 1.5
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
                                                             "http://127.0.0.1:")
    assert re.search(r"go to:\n  http://127\.0\.0\.1:[0-9]+/start\n", err) and passkey.UNLOCK_PAGE not in err
    monkeypatch.setattr(passkey, "OPEN", lambda url: pytest.fail("a browser was opened"))
    with pytest.raises(passkey.UnlockFailed, match="no answer"):
        passkey.unlock(owner, ["Y3JlZA"], timeout=0.3, no_browser=True)
    err = capsys.readouterr().err
    assert "Go to this address in your browser" in err and "Opening the browser" not in err
    assert "Still waiting" not in err and "/start\n" in err and passkey.UNLOCK_PAGE not in err
    monkeypatch.setattr(passkey, "OPEN", lambda url: follow_start(url) and True)
    with pytest.raises(passkey.UnlockFailed, match="no answer"):
        passkey.unlock(owner, ["Y3JlZA"], timeout=0.5)
    assert "Still waiting" not in capsys.readouterr().err


def test_start_is_answered_once(monkeypatch, capsys):
    owner = "56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa"
    opened = []

    def twice(url):
        assert follow_start(url).startswith(passkey.UNLOCK_PAGE + "#mode=unlock&")
        try:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=5)
        except urllib.error.HTTPError as e:
            opened.append({"again": e.code})
        return True

    monkeypatch.setattr(passkey, "OPEN", twice)
    with pytest.raises(passkey.UnlockFailed, match="opened twice"):
        passkey.unlock(owner, ["Y3JlZA"], timeout=3)
    assert opened == [{"again": 409}]
    assert "Warning: the address of osheaf was opened twice" in capsys.readouterr().err


def test_another_user_is_refused(monkeypatch, capsys):
    owner = "56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa"
    who, got, opened = [os.getuid() + 1], [], []
    monkeypatch.setattr(passkey, "SAME_USER_ONLY", True)
    monkeypatch.setattr(passkey, "PEER_UID", lambda host, port, server_port: who[0])
    o = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)

    def status(url):
        try:
            return o.open(url, timeout=5).status
        except urllib.error.HTTPError as e:
            return e.code

    def opener(url):
        got.append(status(url))
        who[0] = os.getuid()
        page = follow_start(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(page).fragment).items()}
        epk, ct, tag = passkey.seal(bytes(32), passkey.from_b64url(q["pk"]), q["state"], q["mode"], q["owner"],
                                    "Y3JlZA")
        answer = url.replace("/start", "/callback?") + urllib.parse.urlencode(
            {"state": q["state"], "epk": passkey.b64url(epk), "ct": passkey.b64url(ct),
             "tag": passkey.b64url(tag), "cred": "Y3JlZA"})
        who[0] = os.getuid() + 1
        got.append(status(answer))
        who[0] = os.getuid()
        got.append(status(answer))
        return True

    monkeypatch.setattr(passkey, "OPEN", opener)
    assert passkey.unlock(owner, ["Y3JlZA"], timeout=3) == ("Y3JlZA", bytes(32))
    assert got == [403, 403, 200]
    err = capsys.readouterr().err
    assert err.count("Warning: another user of this computer asked osheaf for ") == 2


def test_peer_uid(tmp_path):
    import socket
    table = tmp_path / "tcp"
    table.write_text(
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 0100007F:D431 0100007F:0050 06 00000000:00000000 03:00000000 00000000     0        0 0\n"
        "   1: 0100007F:D431 0100007F:0050 01 00000000:00000000 00:00000000 00000000  1001        0 0\n"
        "   2: 0100007F:0050 0100007F:D431 01 00000000:00000000 00:00000000 00000000  1002        0 0\n")
    table6 = tmp_path / "tcp6"
    table6.write_text(
        "  sl  local_address                         remote_address                        st tx_queue rx_queue "
        "tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 0000000000000000FFFF00000100007F:D432 0000000000000000FFFF00000100007F:0050 01 00000000:00000000 "
        "00:00000000 00000000  1003        0 0\n")
    tables = (str(table), str(table6), str(tmp_path / "missing"))
    assert passkey.peer_uid("127.0.0.1", 0xD431, 0x50, tables) == 1001
    assert passkey.peer_uid("127.0.0.1", 0x50, 0xD431, tables) == 1002
    assert passkey.peer_uid("127.0.0.1", 0xD432, 0x50, tables) == 1003
    assert passkey.peer_uid("127.0.0.1", 0xD433, 0x50, tables) is None
    assert passkey.peer_uid("127.0.0.2", 0xD431, 0x50, tables) is None
    if sys.platform.startswith("linux"):
        with socket.create_server(("127.0.0.1", 0)) as server, \
                socket.create_connection(server.getsockname()) as client:
            accepted, (host, port) = server.accept()
            with accepted:
                assert passkey.peer_uid(host, port, server.getsockname()[1]) == os.getuid()


def test_passphrase_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(P.PASSPHRASE_COMMAND, "printf 'correct horse\\n'")
    monkeypatch.setattr("getpass.getpass", lambda prompt: pytest.fail("the passphrase was asked"))
    root = make_archive(tmp_path, "--keys", "github:me/keys")
    owner = P.ARCHIVE["owner"]
    assert keys.read_key(next(iter(in_repo(tmp_path).values())), "correct horse").owner == owner
    current = P.key_log(owner).latest().keys["keys"][0]
    r = ["--root", str(root)]
    run(*r, "key", "forget", current, "--yes")
    monkeypatch.setenv(P.PASSPHRASE_COMMAND, "false")
    asked = []
    monkeypatch.setattr("getpass.getpass", lambda prompt: asked.append(prompt) or "correct horse")
    run(*r, "key", "pull")
    assert len(asked) == 1 and "gave no passphrase" in capsys.readouterr().err


def counting_store(monkeypatch, held):
    """A double of keyring, HELD ({(owner, kid): seed text}), whose reads are counted."""
    reads = []
    read, write = keys._read, keys._write

    def fake_read(store, owner, kid):
        if store != "keyring":
            return read(store, owner, kid)
        reads.append((owner, kid))
        return held.get((owner, kid))

    def fake_write(store, owner, kid, text):
        if store != "keyring":
            return write(store, owner, kid, text)
        held[(owner, kid)] = text
        return True

    monkeypatch.setattr(keys, "_read", fake_read)
    monkeypatch.setattr(keys, "_write", fake_write)
    monkeypatch.setenv(keys.KEY_STORE, "keyring")
    return reads


def test_one_read_per_key_and_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    opened = []
    monkeypatch.setattr(passkey, "OPEN", fake_browser(opened))
    root = make_archive(tmp_path, "--keys", "github:me/keys")
    owner = P.ARCHIVE["owner"]
    current = P.key_log(owner).latest().keys["keys"][0]
    kid = names.key_id(current)
    r = ["--root", str(root)]
    run(*r, "key", "enroll")
    seed = (tmp_path / "config" / "opensheaf" / "keys" / owner / f"{kid}.key").read_text().strip()
    held = {(owner, kid): seed}
    reads = counting_store(monkeypatch, held)
    for command in (["key", "unlock"], ["key", "pull"], ["owner", "show"]):
        reads.clear()
        run(*r, *command)
        assert reads == [(owner, kid)], command
    reads.clear()
    deposit(root, "p", "one", new=True)
    deposit(root, "p", "two")
    assert reads == [(owner, kid)] * 2
    for command in (["key", "unlock"], ["key", "pull"]):
        del held[(owner, kid)]
        reads.clear()
        run(*r, *command)
        assert reads == [(owner, kid)] and (owner, kid) in held, command
    del held[(owner, kid)]
    reads.clear()
    deposit(root, "p", "three")
    assert reads == [(owner, kid)] and (owner, kid) in held
    reads.clear()
    run(*r, "key", "forget", current, "--yes")
    assert reads == []
    assert P.verify_errors() == []


def test_no_key_store(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    opened = []
    monkeypatch.setattr(passkey, "OPEN", fake_browser(opened))
    root = make_archive(tmp_path, "--keys", "github:me/keys")
    owner = P.ARCHIVE["owner"]
    current = P.key_log(owner).latest().keys["keys"][0]
    r = ["--root", str(root)]
    run(*r, "key", "enroll")
    run(*r, "key", "forget", current, "--yes")
    monkeypatch.delenv(P.PASSPHRASE)
    monkeypatch.setattr("getpass.getpass", lambda prompt: pytest.fail("the passphrase was asked"))
    reads = counting_store(monkeypatch, {})
    monkeypatch.setenv(keys.KEY_STORE, "none")
    capsys.readouterr()
    run(*r, "key", "pull")
    out = capsys.readouterr().out
    assert "not kept on this computer, by choice (OPENSHEAF_KEY_STORE=none)" in out
    run(*r, "key", "unlock")
    assert "not kept on this computer, by choice" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="OPENSHEAF_KEY_STORE=none"):
        run(*r, "key", "new")
    unlocks = len([q for q in opened if q.get("mode") == "unlock"])
    deposit(root, "p", "one", new=True)
    deposit(root, "p", "two")
    assert len([q for q in opened if q.get("mode") == "unlock"]) == unlocks + 2
    assert "memory, for this command only" in capsys.readouterr().err
    assert reads == [] and local_keys(tmp_path, owner) == [] and P.verify_errors() == []
    monkeypatch.setattr(P, "configured_wallet", lambda owner=None: None)
    with pytest.raises(SystemExit, match="configure a key wallet"):
        deposit(root, "p", "three")
