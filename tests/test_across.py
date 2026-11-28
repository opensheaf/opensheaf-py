# Generated from literate/72-tests-across.md by opensheaf-literate: edit the document, not this file.
"""Tests across archives: resolution, collections, mirrors, key logs met, branches, drafts,
takedowns and indexes (specification 0.2)."""

import functools
import http.server
import json
import shutil
import socketserver
import threading
import urllib.parse
from pathlib import Path

import pytest

from opensheaf import cli, core as P, keys, names, owners, remote, sign, wallet


@pytest.fixture(autouse=True)
def keys_of_the_tests(tmp_path, monkeypatch, request):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv(keys.KEY_STORE, "file")
    monkeypatch.delenv(keys.SIGNING_KEY, raising=False)
    monkeypatch.delenv(P.PASSPHRASE, raising=False)
    monkeypatch.delenv(wallet.WALLET, raising=False)
    monkeypatch.setattr(wallet, "GH", "/nonexistent/gh")
    monkeypatch.setattr(wallet, "COPY", ["/nonexistent/pbcopy"])
    monkeypatch.setattr(wallet, "PASTE", ["/nonexistent/pbpaste"])
    monkeypatch.setattr(owners, "fetch_json", lambda url: pytest.fail(f"the network was read: {url}"))
    monkeypatch.setenv(keys.TEST_KEYS, ",".join(f"{request.node.name} {i}" for i in range(120)))
    monkeypatch.setenv(remote.LOCATIONS, f"https://example.org/={tmp_path}/")


def run(*argv):
    cli.main(list(argv))


def make(tmp_path, name, *extra):
    root = tmp_path / name
    run("init", str(root), "--name", name.title(), "--base-url", f"https://example.org/{name}/",
        "--curator", "Doe, Jane", "--new-owner", "--export", str(tmp_path / f"{name}-keys"),
        "--no-passphrase", "--yes", *extra)
    return root


def deposit(root, label, text, *extra, new=False, rights="cc-by-4.0"):
    pdf = root.parent / f"{label}.pdf"
    pdf.write_bytes(b"%PDF-1.4 " + text.encode())
    run("--root", str(root), "deposit", label, "--pdf", str(pdf), "--no-source", "x", "--title",
        label.title(), "--author", "Doe, J", "--issued", "2020-01-01", "--rights", rights, *extra,
        *(["--new"] if new else []))


def line(root, label):
    P.configure(root)
    return P.LABELS[label]


def uri(root, label, version=None, pin=None):
    _, nm, owner = line(root, label).split(":")
    base = json.loads((root / P.CONFIG_NAME).read_text())["baseUrl"]
    s = f"sheaf:{nm}:{owner}" + (f"/v{version}" if version else "")
    query = ([f"sha512={pin}"] if pin else []) + ["at=" + urllib.parse.quote(base, safe="")]
    return s + "?" + "&".join(query)


def head_digest(root, label, version):
    return P.digest(P.obj_dir(line(root, label)) / version / "inventory.json")


def errors(root):
    P.configure(root)
    return P.verify_errors()


def findings(root, remote_=False):
    P.configure(root)
    return P.verify_findings(remote=remote_)


def members(root, label):
    d = P.obj_dir(line(root, label))
    return P.read_json(d, P.load_inventory(d), "members.json")


def rotation_files(folder):
    return sorted(str(p) for p in Path(folder).glob("rotation-*.txt"))


def test_resolution_across_two_archives(tmp_path, capsys):
    a, c = make(tmp_path, "a"), make(tmp_path, "c")
    deposit(a, "paper", "one", new=True)
    deposit(a, "paper", "two")
    _, nm, owner = line(a, "paper").split(":")
    at = ["https://example.org/a/"]
    P.configure(c)
    with remote.Resolver() as r:
        lid, found = r.resolve(f"sheaf:{nm}", at)
        assert lid == f"sheaf:{nm}:{owner}" and (found.status, found.version) == ("verified", "v2")
        assert found.copy.where == "https://example.org/a/"
        _, f1 = r.resolve(f"sheaf:{nm}/v1", at)
        assert (f1.status, f1.version) == ("verified", "v1")
        d1 = head_digest(a, "paper", "v1")
        P.configure(c)
        _, fp = r.resolve(f"sheaf:{nm}/v1?sha512={d1}", at)
        assert (fp.status, fp.version) == ("verified", "v1")
        _, fm = r.resolve(f"sheaf:{nm}/v1?sha512={'0' * 128}", at)
        assert fm.status == "mismatch"
        _, fs = r.resolve(f"sheaf:{nm[:10]}:{owner[:10]}/v2", at)
        assert fs.version == "v2"
        _, fo = r.resolve(f"sheaf:{owner}", at)
        assert (fo.status, fo.version) == ("verified", "v1")
    with remote.Resolver() as r:
        assert r.resolve(f"sheaf:{nm}:{owner}", ["https://example.org/nowhere/"])[1].status == "unavailable"
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        run("--root", str(c), "resolve", uri(a, "paper", 2), "--json")
    assert e.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "verified" and out["pin"] == f"sheaf:{nm}:{owner}/v2?sha512={head_digest(a, 'paper', 'v2')}"
    shutil.rmtree(P.obj_dir(line(a, "paper")) / sign.WITNESSES / "v2")
    with pytest.raises(SystemExit):
        run("--root", str(c), "resolve", uri(a, "paper"))
    assert "latest signed v1; after it: v2 unsigned (section 7.4)" in capsys.readouterr().out


def test_what_another_archive_says_is_checked(tmp_path, monkeypatch):
    a = make(tmp_path, "a")
    deposit(a, "paper", "one", new=True)
    for good in ("v1/content/paper.tm", "v12/content/a/b"):
        assert owners.content_path(good, {}, 12)
    for bad in ("v1/content/../../x", "/v1/content/x", "v1/other/x", "v2/content/x", "x/content/y", "v1/content",
                "v1/content//x", "v1\\content\\x", None):
        assert not owners.content_path(bad, {}, 1), bad
    assert owners.content_path("v1/data/x", {"contentDirectory": "data"}, 1)
    for root in ("../x/", "/etc/", "//evil.example/", "https://evil.example/", "ocfl", "a/../../"):
        folder = tmp_path / ("root" + str(abs(hash(root))))
        folder.mkdir()
        (folder / "opensheaf.json").write_text(json.dumps({"specification": "0.2", "storageRoot": root}))
        with pytest.raises(remote.Unavailable, match="storage root"):
            remote.Source(str(folder)).object_path(line(a, "paper"))
    src = remote.Source(str(a))
    monkeypatch.setattr(remote, "MAX_FETCH_FILES", 3)
    with pytest.raises(remote.Unavailable, match="more than 3 files"):
        remote.fetch_object(src, line(a, "paper"), tmp_path / "copy1")
    monkeypatch.setattr(remote, "MAX_FETCH_FILES", 20000)
    tampered = tmp_path / "tampered"
    shutil.copytree(a, tampered)
    d = tampered / remote.Source(str(a)).object_path(line(a, "paper"))
    inv = json.loads((d / "v1" / "inventory.json").read_bytes())
    first = next(iter(inv["manifest"]))
    inv["manifest"][first] = ["v1/content/../../../../escaped"]
    data = json.dumps(inv).encode()
    for f in (d / "v1" / "inventory.json", d / "inventory.json"):
        f.write_bytes(data)
        f.with_name(f.name + ".sha512").write_bytes(owners.sidecar(data))
    with pytest.raises(remote.Unavailable, match="out of the object"):
        remote.fetch_object(remote.Source(str(tampered)), line(a, "paper"), tmp_path / "copy2")
    assert not (tmp_path / "escaped").exists()
    owner = P.ARCHIVE["owner"]
    kd = tmp_path / "keylog"
    shutil.copytree(a / remote.Source(str(a)).object_path(f"sheaf:{owner}:{owner}"), kd)
    kinv = json.loads((kd / "v1" / "inventory.json").read_bytes())
    state = kinv["versions"]["v1"]["state"]
    k0 = next(dg for dg, paths in state.items() if paths != ["genesis.json"])
    kinv["manifest"][k0] = ["v1/content/../../../outside"]
    kdata = json.dumps(kinv).encode()
    (kd / "v1" / "inventory.json").write_bytes(kdata)
    (kd / "v1" / "inventory.json.sha512").write_bytes(owners.sidecar(kdata))
    (tmp_path / "outside").write_text("not read")
    log = owners.load_key_log(kd)
    assert any("a content path out of the object" in p for p in log.problems)


def test_json_nested_too_deeply(tmp_path):
    from opensheaf import html
    assert names.json_value("[" * 64 + "]" * 64) is not None
    for text in ("[" * 65 + "]" * 65, "[" * 400000 + "]" * 400000, '{"a":' * 65 + "1" + "}" * 65):
        with pytest.raises(ValueError, match="nested"):
            names.json_value(text)
    deep = tmp_path / "deep"
    deep.mkdir()
    (deep / "opensheaf.json").write_text("[" * 400000 + "]" * 400000)
    a = make(tmp_path, "a")
    with remote.Resolver(places=["https://example.org/deep/"]) as r:
        assert r.source("https://example.org/deep/") is None and any("nested" in m for _, m in r.notes)
    m = {"kind": "document", "name": "a" * 52, "owner": "b" * 52, "at": ["https://example.org/deep/"],
         "version": "v1", "inventorySha512": "c" * 128, "cite": {"title": "Cached"}}
    assert html.remote_view(m) is None and "Cached" in html.remote_entry(m)


def test_a_copy_read_in_place_is_checked(tmp_path):
    a = make(tmp_path, "a")
    deposit(a, "paper", "one", new=True)
    oid = line(a, "paper")
    _, nm, owner = oid.split(":")
    d = P.obj_dir(oid)
    inv = P.load_inventory(d)
    pdf = d / next(cp for ps in inv["manifest"].values() for cp in ps if cp.endswith(".pdf"))
    good = pdf.read_bytes()
    c = make(tmp_path, "c")
    with remote.Resolver(places=[str(a)]) as r:
        assert r.resolve(f"sheaf:{nm}:{owner}")[1].status == "verified"
    pdf.write_bytes(b"%PDF tampered")
    for place in (str(a), "https://example.org/a/"):
        P.configure(c)
        with remote.Resolver(places=[place]) as r:
            assert r.resolve(f"sheaf:{nm}:{owner}")[1].status == "unavailable"
            assert any("does not have its digest" in m for _, m in r.notes)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(good)
    pdf.unlink()
    pdf.symlink_to(outside)
    P.configure(c)
    with remote.Resolver(places=[str(a)]) as r:
        assert r.resolve(f"sheaf:{nm}:{owner}")[1].status == "unavailable"


def test_only_the_version_resolved_to_is_read_whole(tmp_path):
    a = make(tmp_path, "a")
    deposit(a, "paper", "one", new=True)
    deposit(a, "paper", "two")
    oid = line(a, "paper")
    _, nm, owner = oid.split(":")
    d1 = head_digest(a, "paper", "v1")
    b = tmp_path / "b"
    shutil.copytree(a, b)
    d = P.obj_dir(oid)
    inv = P.load_inventory(d)
    pdf1 = d / next(cp for cp in remote.content_paths(inv, ["v1"]) if cp.endswith(".pdf"))
    assert pdf1.parts[-3] == "v1" and pdf1.name.endswith(".pdf")
    pdf1.write_bytes(b"%PDF tampered")
    c = make(tmp_path, "c")
    P.configure(c)
    with remote.Resolver(places=[str(a)]) as r:
        found = r.latest(nm, owner)
        assert (found.status, found.version) == ("verified", "v2")
        assert r.pin(nm, owner, "v1", d1).status == "unavailable"
        assert any(m.startswith(f"{a}: {oid} v1: ") and "does not have its digest" in m for _, m in r.notes)
    with remote.Resolver(places=[str(a), str(b)]) as r:
        found = r.pin(nm, owner, "v1", d1)
        assert (found.status, found.copy.where) == ("verified", str(b))
    obj1 = d / next(cp for cp, dg in remote.content_paths(inv, ["v1"], [P.OBJ]).items())
    obj1.write_bytes(obj1.read_bytes() + b" ")
    P.configure(c)
    with remote.Resolver(places=[str(a)]) as r:
        assert r.latest(nm, owner).status == "unavailable"
        assert any("object.json is missing, or does not have its digest" in m for _, m in r.notes)


def test_an_unsigned_head_cannot_restate_a_signed_version(tmp_path):
    a, c = make(tmp_path, "a"), make(tmp_path, "c")
    deposit(a, "paper", "one", new=True)
    obj_id = line(a, "paper")
    _, nm, owner = obj_id.split(":")
    d = P.obj_dir(obj_id)
    forged = json.loads((d / "v1" / "inventory.json").read_bytes())
    state = forged["versions"]["v1"]["state"]
    pdf = next(dg for dg, paths in state.items() if paths[0].endswith(".pdf"))
    other = b"%PDF-1.4 forged"
    state[names.sha512_hex(other)] = state.pop(pdf)
    forged["manifest"][names.sha512_hex(other)] = ["v2/content/forged.pdf"]
    forged["versions"]["v2"] = dict(forged["versions"]["v1"], message="forged")
    forged["head"] = "v2"
    (d / "v2" / "content").mkdir(parents=True)
    (d / "v2" / "content" / "forged.pdf").write_bytes(other)
    data = json.dumps(forged).encode()
    for f in (d / "v2" / "inventory.json", d / "inventory.json"):
        f.write_bytes(data)
        f.with_name(f.name + ".sha512").write_bytes(owners.sidecar(data))
    assert remote.version_problem(forged, 1, json.loads((d / "v1" / "inventory.json").read_bytes()))
    P.configure(c)
    with remote.Resolver() as r:
        assert r.latest(nm, owner, ["https://example.org/a/"]).status == "unavailable"
        assert any("not a copy of the line: v1: its inventory does not record the versions" in m
                   for _, m in r.notes)
    with pytest.raises(remote.Unavailable, match="v1: its inventory does not record the versions"):
        remote.fetch_object(remote.Source(str(a)), obj_id, tmp_path / "copy")
    assert any("v1: the inventory copy disagrees with the inventory" in e for e in errors(a))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class Server(http.server.ThreadingHTTPServer):
    def server_bind(self):                   # without the slow lookup of the host's name
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


@pytest.fixture
def server(tmp_path):
    httpd = Server(("127.0.0.1", 0), functools.partial(Quiet, directory=str(tmp_path)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    httpd.shutdown()


def test_resolution_over_http(tmp_path, monkeypatch, server):
    h = make(tmp_path, "h", "--layout", "hashed")
    deposit(h, "paper", "one", new=True)
    deposit(h, "paper", "two")
    u = uri(h, "paper")
    monkeypatch.setenv(remote.LOCATIONS, f"https://example.org/={server}")
    c = make(tmp_path, "c")
    P.configure(c)
    with remote.Resolver() as r:
        _, found = r.resolve(u)
        assert (found.status, found.version) == ("verified", "v2")
        assert found.copy.src.folder is None and found.copy.statuses == [sign.SIGNED, sign.SIGNED]


def test_over_http_only_what_resolution_needs_is_read(tmp_path, monkeypatch):
    seen = []

    class Seen(Quiet):
        def do_GET(self):
            seen.append(urllib.parse.unquote(urllib.parse.unquote(self.path)))
            super().do_GET()
    httpd = Server(("127.0.0.1", 0), functools.partial(Seen, directory=str(tmp_path)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        h = make(tmp_path, "h")
        deposit(h, "paper", "one", new=True)
        deposit(h, "paper", "two")
        oid = line(h, "paper")
        _, nm, owner = oid.split(":")
        hd = P.obj_dir(oid)
        inv = P.load_inventory(hd)
        pdf = {v: next(cp for cp in remote.content_paths(inv, [v]) if cp.endswith(".pdf")) for v in ("v1", "v2")}
        assert pdf["v1"] != pdf["v2"]
        d1 = head_digest(h, "paper", "v1")
        monkeypatch.setenv(remote.LOCATIONS, f"https://example.org/=http://127.0.0.1:{httpd.server_address[1]}/")
        c = make(tmp_path, "c")
        fetched = lambda cp: any(x.endswith("/" + cp) for x in seen)
        P.configure(c)
        with remote.Resolver() as r:
            found = r.latest(nm, owner, ["https://example.org/h/"])
            assert (found.status, found.version) == ("verified", "v2")
            assert found.copy.src.folder is None
            assert fetched(pdf["v2"]) and not fetched(pdf["v1"])
            assert r.pin(nm, owner, "v1", d1, ["https://example.org/h/"]).status == "verified"
            assert fetched(pdf["v1"])
        (hd / pdf["v2"]).write_bytes(b"%PDF tampered")
        P.configure(c)
        with remote.Resolver() as r:
            assert r.latest(nm, owner, ["https://example.org/h/"]).status == "unavailable"
            assert (f"https://example.org/h/: {oid} v2: {pdf['v2']} is missing, or does not have its digest: "
                    "not read (section 12.3)") in [m for _, m in r.notes]
        monkeypatch.setattr(remote, "MAX_RUN_FILES", 3)
        P.configure(c)
        with remote.Resolver() as r:
            assert r.latest(nm, owner, ["https://example.org/h/"]).status == "unavailable"
            assert any("not read: the copies of this run have brought 3 files" in m for _, m in r.notes)
    finally:
        httpd.shutdown()


def test_short_uri_over_http(tmp_path, monkeypatch, server):
    h = make(tmp_path, "h", "--layout", "hashed")
    deposit(h, "paper", "one", new=True)
    deposit(h, "paper", "two")
    _, nm, owner = line(h, "paper").split(":")
    at = "?at=" + urllib.parse.quote("https://example.org/h/", safe="")
    monkeypatch.setenv(remote.LOCATIONS, f"https://example.org/={server}")
    c = make(tmp_path, "c")
    P.configure(c)
    for text in (f"sheaf:{nm}", f"sheaf:{nm[:16]}", f"sheaf:{nm[:16]}:{owner[:16]}"):
        with remote.Resolver() as r:
            obj_id, found = r.resolve(text + at)
            assert obj_id == f"sheaf:{nm}:{owner}"
            assert (found.status, found.version) == ("verified", "v2")
            assert found.copy.statuses == [sign.SIGNED, sign.SIGNED]


def test_ambiguous_short_form_lists_originators(tmp_path):
    a = make(tmp_path, "a")
    deposit(a, "paper", "one", new=True)
    deposit(a, "other", "two", new=True)
    _, nm, owner = line(a, "paper").split(":")
    u = names.parse_sheaf(f"sheaf:{nm[:8]}:{owner[:8]}", short=True)
    u.matches = lambda n, o: True
    with remote.Resolver(here=False, places=[str(a)]) as r:
        with pytest.raises(ValueError, match="ambiguous, the candidates are") as e:
            r.expand(u, [str(a)])
    listed = str(e.value).splitlines()[1:]
    assert f"  sheaf:{nm}:{owner}  originator {owner}" in listed
    assert len(listed) >= 3 and all(x.endswith(f"  originator {owner}") for x in listed)


def test_addresses_given_by_others(tmp_path, monkeypatch):
    import time
    a = make(tmp_path, "a")
    deposit(a, "paper", "one", new=True)
    _, nm, owner = line(a, "paper").split(":")
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "opensheaf.json").write_text('{"specification": "0.2"}')
    assert remote.Source(str(a)).folder is not None
    for given in (str(a), f"file://{a}", "ftp://127.0.0.1/a/", "a/"):
        src = remote.Source(given, remote=True)
        assert src.folder is None and src.url is None
        with pytest.raises(remote.Unavailable, match="not an http or https"):
            src.discovery()
    with pytest.raises(remote.Unavailable, match="not an http or https"):
        remote.Source("ftp://127.0.0.1/a/").discovery()
    monkeypatch.setenv(remote.LOCATIONS, f"https://example.org/={tmp_path / 'a'}/")
    for climb in ("https://example.org/../secret/", "https://example.org/%2e%2e/secret/",
                  "https://example.org/x/..%2f..%2fsecret/"):
        with pytest.raises(remote.Unavailable, match="climbs out"):
            remote.Source(climb, remote=True).discovery()
    monkeypatch.setenv(remote.LOCATIONS, f"https://example.org/={tmp_path}/")
    P.configure(a)
    with remote.Resolver(here=False) as r:
        assert r.resolve(f"sheaf:{nm}:{owner}", [str(a)])[1].status == "unavailable"
        assert r.resolve(f"sheaf:{nm}:{owner}", ["https://example.org/a/"])[1].status == "verified"
    seen = []

    class Answers(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            if self.path.startswith("/ftp/"):
                self.send_response(302)
                self.send_header("Location", "ftp://127.0.0.1/opensheaf.json")
                self.end_headers()
            elif self.path.startswith("/slow/"):
                self.send_response(200)
                self.end_headers()
                try:
                    for _ in range(40):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(0.05)
                except OSError:              # the reader gave up
                    pass
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass
    httpd = Server(("127.0.0.1", 0), Answers)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with pytest.raises(remote.Unavailable, match="HTTP 302"):
            remote.Source(f"{base}/ftp/", remote=True).discovery()
        monkeypatch.setattr(remote, "DEADLINE", 0.5)
        with pytest.raises(remote.Unavailable, match="not read in"):
            remote.Source(f"{base}/slow/", remote=True).discovery()
        monkeypatch.setattr(remote, "MAX_JSON", 10)
        with pytest.raises(remote.Unavailable, match="more than 10 bytes"):
            remote.Source(f"{base}/slow/", remote=True).discovery()
        monkeypatch.setattr(remote, "MAX_JSON", 16 << 20)
        seen.clear()
        with remote.Resolver(here=False) as r:
            deep = f"{base}/" + "x/" * 30 + "v1/"
            assert r.archive_of(deep) == []
            assert len(seen) == remote.MAX_PROBES
            many = [f"{base}/m{k}/" for k in range(9)]
            assert len(r.where(many)) == remote.MAX_MIRRORS
            monkeypatch.setattr(remote, "MAX_PINS", 1)
            d1 = head_digest(a, "paper", "v1")
            assert r.pin(nm, owner, "v1", d1, ["https://example.org/a/"]).status == "verified"
            assert r.pin(nm, owner, "v1", d1, ["https://example.org/a/"]).status == "unavailable"
    finally:
        httpd.shutdown()


def test_curated_collection_across_archives(tmp_path, capsys):
    a = make(tmp_path, "papers")
    for label in ("one", "two"):
        deposit(a, label, label, new=True)
    c = make(tmp_path, "reading", "--curated")
    spec = tmp_path / "collection.yaml"
    spec.write_text(f"title: Reading\ntype: catalogue\nmembers:\n"
                    f"  - {{uri: '{uri(a, 'two')}', follow: yes}}\n  - '{uri(a, 'one')}'\n")
    run("--root", str(c), "collection", "sync", "reading-list", "--from", str(spec))
    mem = members(c, "reading-list")
    _, nm2, owner = line(a, "two").split(":")
    assert mem["type"] == "catalogue" and [m["name"] for m in mem["members"]][0] == nm2
    assert mem["members"][0]["at"] == ["https://example.org/papers/"]
    assert mem["members"][0]["follow"] == "latest" and "follow" not in mem["members"][1]
    assert errors(c) == []
    assert members(c, "main")["order"] == "manual"
    deposit(a, "two", "two again")
    run("--root", str(c), "collection", "update")
    new = members(c, "reading-list")["members"]
    assert (new[0]["version"], new[1]["version"]) == ("v2", "v1")
    run("--root", str(a), "withdraw", "two", "--reason", "a mistake")
    run("--root", str(c), "collection", "update")
    new = members(c, "reading-list")["members"]
    assert new[0]["version"] == "v3" and new[0]["inventorySha512"] == head_digest(a, "two", "v3")
    found = findings(c, remote_=True)
    assert [x for x in found if x["severity"] == "error"] == []
    assert sum(1 for x in found if x["message"].startswith("verified at https://example.org/papers/")) == 2
    capsys.readouterr()
    run("--root", str(c), "collection", "status", "reading-list")
    assert capsys.readouterr().out.count("verified: ") == 2


def test_a_pin_that_is_not_one(tmp_path):
    from opensheaf import collections
    a = make(tmp_path, "papers")
    deposit(a, "one", "one", new=True)
    c = make(tmp_path, "reading")
    spec = tmp_path / "collection.yaml"
    spec.write_text(f"title: Reading\ntype: catalogue\nmembers:\n  - '{uri(a, 'one')}'\n")
    run("--root", str(c), "collection", "sync", "list", "--from", str(spec))
    P.configure(c)
    m = members(c, "list")["members"][0]
    collections.write(line(c, "list"), dict(members(c, "list"), members=[dict(m, version="latest")]),
                      message="by hand")
    with remote.Resolver() as r:
        assert r.pin(m["name"], m["owner"], "latest", m["inventorySha512"]).status == "not a version"
        assert r.pin("../x", m["owner"], "v1", m["inventorySha512"]).status == "not a version"
    found = findings(c, remote_=True)
    assert any(x["severity"] == "error" for x in found)


def test_member_statuses(tmp_path):
    a = make(tmp_path, "a")
    for label in ("one", "two", "three"):
        deposit(a, label, label, new=True)
    c = make(tmp_path, "c")
    run("--root", str(c), "collection", "new", "list", "--type", "catalogue", "--title", "List")
    run("--root", str(c), "collection", "add", "list", uri(a, "one"), uri(a, "two"), uri(a, "three"))
    assert errors(c) == []
    from opensheaf import collections
    run("--root", str(a), "takedown", "one", "--reason", "Taken down at the request of the holder.", "--yes")
    P.configure(c)
    with remote.Resolver() as r:
        assert sorted(s for _, _, s in collections.statuses(members(c, "list"), r)) == \
            ["removed", "verified", "verified"]
        m = members(c, "list")["members"][1]
        assert r.pin(m["name"], m["owner"], "v1", "0" * 128, m["at"]).status == "mismatch"
    P.configure(a)
    first = P.key_log(P.ARCHIVE["owner"]).latest().keys["keys"][0]
    rk = rotation_files(tmp_path / "a-keys")
    P.configure(a)
    third = P.key_new(P.argparse_namespace(owner=None)).did
    run("--root", str(a), "owner", "expose", first, "--add", third, "--rotation-key", rk[0],
        "--rotation-key", rk[1], "--export", str(tmp_path / "a-keys-2"), "--no-passphrase", "--yes")
    P.configure(c)
    with remote.Resolver() as r:
        assert sorted(s for _, _, s in collections.statuses(members(c, "list"), r)) == \
            ["contested", "contested", "removed"]
    shutil.move(str(a), str(tmp_path / "gone"))
    P.configure(c)
    with remote.Resolver() as r:
        assert {s for _, _, s in collections.statuses(members(c, "list"), r)} == {"unavailable"}


def test_copies_that_disagree_with_a_pin(tmp_path):
    a = make(tmp_path, "a")
    deposit(a, "paper", "one", new=True)
    obj_id = line(a, "paper")
    _, nm, owner = obj_id.split(":")
    dig = head_digest(a, "paper", "v1")
    path = remote.Source(str(a)).object_path(obj_id)
    nocheck, tampered = tmp_path / "nocheck", tmp_path / "tampered"
    shutil.copytree(a, nocheck)
    (nocheck / path / "v1" / "inventory.json.sha512").unlink()
    shutil.copytree(a, tampered)
    inv = tampered / path / "v1" / "inventory.json"
    inv.write_bytes(inv.read_bytes() + b" ")
    (tampered / path / "v1" / "inventory.json.sha512").write_bytes(owners.sidecar(inv.read_bytes()))
    P.configure(a)
    with remote.Resolver(here=False, places=[str(nocheck)]) as r:
        assert r.pin(nm, owner, "v1", dig).status == "verified"
        assert remote.checksum_warning(str(nocheck), obj_id, 1) in [m for _, m in r.notes]
    with remote.Resolver(here=False, places=[str(tampered), str(a)]) as r:
        assert r.pin(nm, owner, "v1", dig).status == "verified"
        assert f"{tampered}: {obj_id} v1 does not match the pin (section 12.3)" in [m for _, m in r.notes]
    with remote.Resolver(here=False, places=[str(tampered)]) as r:
        assert r.pin(nm, owner, "v1", dig).status == "mismatch"
    warned, copy = [], tmp_path / "copy"
    remote.fetch_object(remote.Source(str(nocheck)), obj_id, copy, warn=warned.append)
    assert len(warned) == 1 and "checksum file" in warned[0]
    assert (copy / "v1" / "inventory.json.sha512").read_bytes() == \
        owners.sidecar((copy / "v1" / "inventory.json").read_bytes())


def test_selection_pins_revisions(tmp_path, capsys):
    a = make(tmp_path, "papers")
    for k in (1, 2, 3):
        deposit(a, "paper", f"version {k}", new=k == 1)
    s = make(tmp_path, "digest")
    spec = tmp_path / "digest.yaml"
    spec.write_text(f"type: selection\ntitle: Digest\nmembers:\n  - {{uri: '{uri(a, 'paper')}', "
                    "revisions: [2, 1, 2]}\n")
    run("--root", str(s), "collection", "sync", "digest", "--from", str(spec))
    m = members(s, "digest")["members"][0]
    assert "version" not in m and "follow" not in m
    assert [(x["documentVersion"], x["version"], x["inventorySha512"]) for x in m["revisions"]] == \
        [(n, f"v{n}", head_digest(a, "paper", f"v{n}")) for n in (1, 2)]
    assert errors(s) == []
    deposit(a, "paper", "version 4")
    head = P.load_inventory(P.obj_dir(line(s, "digest")))["head"]
    capsys.readouterr()
    run("--root", str(s), "collection", "update", "digest")
    assert "document version(s) 3, 4 not vetted" in capsys.readouterr().out
    assert P.load_inventory(P.obj_dir(line(s, "digest")))["head"] == head
    run("--root", str(s), "collection", "add", "digest", uri(a, "paper"), "--revision", "3", "--revision", "3")
    new = members(s, "digest")["members"][0]["revisions"]
    assert new[:2] == m["revisions"] and (new[2]["documentVersion"], new[2]["version"]) == (3, "v3")
    assert len(new) == 3
    found = findings(s, remote_=True)
    assert [x for x in found if x["severity"] == "error"] == []
    with pytest.raises(SystemExit):
        run("--root", str(s), "collection", "add", "digest", uri(a, "paper"), "--revision", "9")
    run("--root", str(s), "collection", "remove", "digest", uri(a, "paper"), "--revision", "2")
    assert [x["documentVersion"] for x in members(s, "digest")["members"][0]["revisions"]] == [1, 3]
    with pytest.raises(SystemExit, match="no member matches"):
        run("--root", str(s), "collection", "remove", "digest", uri(a, "paper"), "--revision", "2")
    run("--root", str(s), "collection", "remove", "digest", uri(a, "paper"), "--revision", "1", "--revision", "3")
    assert members(s, "digest")["members"] == []


def test_featured_collection_on_the_home_page(tmp_path):
    p, a = make(tmp_path, "papers"), make(tmp_path, "author")
    deposit(p, "one", "one", new=True)
    deposit(a, "mine", "mine", new=True)
    run("--root", str(a), "collect")
    (tmp_path / "reading.yaml").write_text(
        "title: A reading list\ndescription: Papers to read first.\ntype: selection\n"
        f"members:\n  - '{uri(p, 'one')}'\n  - {{label: mine}}\n")
    run("--root", str(a), "collection", "sync", "reading-list", "--from", str(tmp_path / "reading.yaml"))
    main = members(a, "main")["members"]
    assert [m["name"] for m in main] == [line(a, "mine").split(":")[1]]
    cfg = json.loads((a / "osheaf.json").read_text())
    cfg["index"] = {"html": {"templates": "templates", "featured": "reading-list"}}
    (a / "osheaf.json").write_text(json.dumps(cfg))
    run("--root", str(a), "index")
    home = (a / "index.html").read_text()
    assert home.index("<h2>A reading list</h2>") < home.index("<h2>In this archive</h2>")
    assert "Papers to read first." in home
    assert f'<a class="paper-title" href="https://example.org/papers/paper/{line(p, "one").split(":")[1]}/">One</a>' \
        in home
    assert "in <a href=\"https://example.org/papers/\">Papers</a>" in home
    for m in members(a, "reading-list")["members"] + main:
        assert P.member_pins(m)[-1][1][:32] in home
    assert errors(a) == []
    (tmp_path / "sub2.yaml").write_text("title: Part two\ntype: catalogue\nmembers: []\n")
    run("--root", str(a), "collection", "sync", "part-two", "--from", str(tmp_path / "sub2.yaml"))
    (tmp_path / "sub.yaml").write_text(
        "title: Part one\ndescription: The first part.\ntype: catalogue\n"
        f"members:\n  - {{label: mine}}\n  - '{uri(p, 'one')}'\n  - {{label: part-two}}\n")
    run("--root", str(a), "collection", "sync", "part-one", "--from", str(tmp_path / "sub.yaml"))
    (tmp_path / "reading.yaml").write_text(
        "title: A reading list\ndescription: Papers to read first.\ntype: selection\n"
        f"members:\n  - '{uri(p, 'one')}'\n  - {{label: mine}}\n  - {{label: part-one}}\n")
    run("--root", str(a), "collection", "sync", "reading-list", "--from", str(tmp_path / "reading.yaml"))
    run("--root", str(a), "index")
    part = (a / "paper" / "part-one" / "index.html").read_text()
    assert "A catalogue curated by" in part and "3 members" in part and "The first part." in part
    assert 'href="../../paper/mine/"' in part and 'href="../../paper/part-two/"' in part
    assert ">One</a>" in part and "PDF</a>" not in part.split("<h2>Members</h2>")[0]
    assert line(a, "part-one").rsplit(":", 1)[0] + "</code>" in part
    assert (a / "paper" / "part-two" / "index.html").exists() and (a / "paper" / "mine" / "index.html").exists()
    assert errors(a) == []
    cfg["index"]["html"]["featured"] = "mine"
    (a / "osheaf.json").write_text(json.dumps(cfg))
    with pytest.raises(SystemExit, match="not a collection"):
        run("--root", str(a), "index")


def test_only_http_links(tmp_path, monkeypatch, capsys):
    from opensheaf import html
    p, a = make(tmp_path, "papers"), make(tmp_path, "author")
    deposit(p, "one", "one", new=True)
    spec = tmp_path / "list.yaml"
    spec.write_text(f"title: A list\nmembers:\n  - '{uri(p, 'one')}'\n")
    run("--root", str(a), "collection", "sync", "list", "--from", str(spec))
    at = members(a, "list")["members"][0]["at"]
    spec.write_text(f"title: A list\nmembers:\n  - uri: '{uri(p, 'one')}'\n"
                    "    at: ['javascript:alert(1)//', 'http://example.com/']\n")
    capsys.readouterr()
    run("--root", str(a), "collection", "sync", "list", "--from", str(spec))
    assert members(a, "list")["members"][0]["at"] == at
    assert capsys.readouterr().out.count("not recorded") == 2
    assert html.safe_url("javascript:alert(1)") == "" and html.safe_url(" https://x/") == ""
    assert html.safe_url("HTTP://x/") == "HTTP://x/"
    assert html.link("javascript:alert(1)", "x") == "x"
    assert html.link("data:text/html,x", "x", "paper-title") == '<span class="paper-title">x</span>'
    assert html.link("https://x/?a=1&b", "x") == '<a href="https://x/?a=1&amp;b">x</a>'
    m = dict(members(a, "list")["members"][0], at=["javascript:alert(1)"])
    monkeypatch.setattr(html, "remote_view", lambda m: None)
    assert "href" not in html.remote_entry(m)
    monkeypatch.setattr(html, "remote_view", lambda m: {
        "archive": "Elsewhere", "at": "javascript:alert(2)", "pdf": "data:text/html,x",
        "title": "T", "by": "", "abstract": "", "landing": "javascript:alert(3)", "withdrawn": ""})
    out = html.remote_entry(m)
    assert "href" not in out and "Elsewhere" in out and ">T<" in out


def test_what_a_member_says_is_escaped(tmp_path, monkeypatch):
    from opensheaf import collections, html
    assert html.fill("{{a}} {{b}} {{c}}", {"a": "{{b}}", "b": "X"}) == "{{b}} X {{c}}"
    assert html.number(3) == "3" and html.number("<b>") == "?" and html.number(True) == "?"
    monkeypatch.setattr(html, "remote_view", lambda m: pytest.fail("a bad pin was followed"))
    m = {"kind": "document", "name": "a" * 64, "owner": "b" * 64, "at": [],
         "revisions": [{"version": "v1", "documentVersion": "<img src=x onerror=alert(1)>",
                        "inventorySha512": '"><script>alert(2)</script>'}],
         "cite": {"title": "{{versions}}"}}
    out = html.remote_entry(m)
    assert "<img" not in out and "<script" not in out and "no valid pin" in out and "versions ?" not in out
    assert "vetted: version ?" in out
    a = make(tmp_path, "author")
    deposit(a, "one", "one", new=True)
    spec = tmp_path / "list.yaml"
    spec.write_text("title: '{{versions}}'\ntype: catalogue\nmembers: []\n")
    run("--root", str(a), "collection", "sync", "list", "--from", str(spec))
    P.configure(a)
    _, nm, owner = line(a, "one").split(":")
    bad = {"kind": "document", "name": nm, "owner": owner, "version": "v99", "at": [],
           "inventorySha512": '"><script>alert(3)</script>'}
    collections.write(line(a, "list"), dict(members(a, "list"), members=[bad, m]), message="by hand")
    cfg = json.loads((a / "osheaf.json").read_text())
    cfg["index"] = {"html": {"featured": "list"}}
    (a / "osheaf.json").write_text(json.dumps(cfg))
    run("--root", str(a), "index")
    for page in [a / "index.html", *a.glob("paper/*/index.html")]:
        text = page.read_text()
        assert "<script>alert" not in text and "<img src=x" not in text, page
    page = (a / "paper" / "list" / "index.html").read_text()
    assert "{{versions}}" in page and page.count('<li class="version') == 2
    assert "<lastmod>" in (a / "sitemap.xml").read_text()


def test_a_pin_whose_number_bounds_nothing(monkeypatch):
    from opensheaf import html
    obj = json.dumps({"documentVersion": 1}).encode()
    d = names.sha512_hex(obj)
    ver = "v999999999999"
    inv = json.dumps({"head": ver, "versions": {ver: {"state": {d: ["object.json"]}}},
                      "manifest": {d: [f"{ver}/content/object.json"]}}).encode()

    class Evil:
        at = "https://evil.example/"

        def __init__(self, at, remote=False):
            pass

        def discovery(self):
            return {"specification": "0.2"}

        def object_path(self, obj_id):
            return "o"

        def get(self, rel, limit=None):
            return inv if rel.endswith("inventory.json") else obj
    monkeypatch.setattr(html.remote, "Source", Evil)
    html.SOURCES.clear()
    m = {"kind": "document", "name": "a" * 52, "owner": "b" * 52, "at": ["https://evil.example/"],
         "version": ver, "inventorySha512": names.sha512_hex(inv), "cite": {"title": "Cached"}}
    assert html.remote_view(m) is None


def forge(d, ver, logical, data):
    """Put DATA in place of LOGICAL in vVER of the object in D, its inventory rewritten to match."""
    p = d / ver / "inventory.json"
    inv = json.loads(p.read_text())
    old = next(dg for dg, ps in inv["versions"][ver]["state"].items() if logical in ps)
    cp = inv["manifest"].pop(old)[0]
    (d / cp).write_bytes(data)
    new = names.sha512_hex(data)
    inv["manifest"][new] = [cp]
    inv["versions"][ver]["state"][new] = inv["versions"][ver]["state"].pop(old)
    raw = json.dumps(inv).encode()
    p.write_bytes(raw)
    (d / "inventory.json").write_bytes(raw)
    return names.sha512_hex(raw)


def test_a_member_elsewhere_whose_files_are_not_those_pinned(tmp_path):
    from opensheaf import collections
    p, a = make(tmp_path, "papers"), make(tmp_path, "author")
    deposit(p, "one", "one", new=True)
    spec = tmp_path / "list.yaml"
    spec.write_text(f"title: A list\ntype: catalogue\nmembers:\n  - '{uri(p, 'one')}'\n")
    run("--root", str(a), "collection", "sync", "list", "--from", str(spec))
    cfg = json.loads((a / "osheaf.json").read_text())
    cfg["index"] = {"html": {"featured": "list"}}
    (a / "osheaf.json").write_text(json.dumps(cfg))
    run("--root", str(a), "index")
    home = (a / "index.html").read_text()
    assert ">One</a>" in home and "cached citation" not in home
    d = P.obj_dir(line(p, "one"))
    inv = P.load_inventory(d)
    dc_path = d / P.content_path(inv, "v1", "datacite.json")
    saved = dc_path.read_bytes()
    dc_path.write_bytes(saved.replace(b'"One"', b'"Forged"'))
    run("--root", str(a), "index")
    home = (a / "index.html").read_text()
    assert "Forged" not in home and "archive unavailable: cached citation" in home
    dc = json.loads(saved)
    dc["titles"] = []
    pin = forge(d, "v1", "datacite.json", json.dumps(dc).encode())
    P.configure(a)
    m = members(a, "list")["members"][0]
    collections.write(line(a, "list"), dict(members(a, "list"), members=[dict(m, inventorySha512=pin)]),
                      message="a pin by hand")
    run("--root", str(a), "index")
    home = (a / "index.html").read_text()
    assert "archive unavailable: cached citation" in home and ">One<" in home


def test_a_withdrawn_member_of_a_paged_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "OBJECTS_PER_PAGE", 1)
    p, a = make(tmp_path, "papers"), make(tmp_path, "author")
    deposit(p, "one", "one", new=True)
    deposit(p, "two", "two", new=True)
    spec = tmp_path / "list.yaml"
    spec.write_text(f"title: A list\ntype: catalogue\nmembers:\n  - '{uri(p, 'one')}'\n")
    run("--root", str(a), "collection", "sync", "list", "--from", str(spec))
    run("--root", str(p), "withdraw", "one", "--reason", "a mistake")
    disc = json.loads((p / "opensheaf.json").read_text())
    assert "objects" not in disc and disc["objectPages"]
    cfg = json.loads((a / "osheaf.json").read_text())
    cfg["index"] = {"html": {"featured": "list"}}
    (a / "osheaf.json").write_text(json.dumps(cfg))
    run("--root", str(a), "index")
    home = (a / "index.html").read_text()
    assert "Withdrawn by its owner" in home and "a mistake" in home


def test_mirror(tmp_path, capsys):
    a, lib = make(tmp_path, "authors"), make(tmp_path, "library")
    deposit(a, "open", "one", new=True)
    deposit(a, "open", "two")
    deposit(a, "closed", "closed", new=True, rights="All rights reserved")
    run("--root", str(lib), "mirror", uri(a, "closed"))
    assert "not one known to allow redistribution" in capsys.readouterr().err
    run("--root", str(lib), "mirror", uri(a, "open"), "--label", "open-copy")
    obj_id = line(a, "open")
    a_owner = obj_id.split(":")[2]
    P.configure(lib)
    assert (P.obj_dir(obj_id) / "v2").is_dir() and P.key_log(a_owner) is not None
    assert P.LABELS["open-copy"] == obj_id
    disc = json.loads((lib / "opensheaf.json").read_text())
    assert all("mirrorOf" not in o for o in disc["objects"]) and "mirrors" not in disc
    assert errors(lib) == []
    assert members(lib, "main")["members"] == []
    deposit(a, "open", "three")
    d = P.obj_dir(line(a, "open"))
    deposit(a, "open", "four")
    for f in (P.obj_dir(line(a, "open")) / sign.WITNESSES / "v4").iterdir():
        f.unlink()
    run("--root", str(lib), "mirror", "--all")
    P.configure(lib)
    inv = P.load_inventory(P.obj_dir(obj_id))
    assert inv["head"] == "v3"
    assert errors(lib) == []


def test_mirror_refuses_a_fork_of_the_line(tmp_path):
    a, lib = make(tmp_path, "authors"), make(tmp_path, "library")
    deposit(a, "open", "one", new=True)
    deposit(a, "open", "two")
    shutil.copytree(a, tmp_path / "twin")
    cfg = json.loads((tmp_path / "twin" / P.CONFIG_NAME).read_text())
    cfg["baseUrl"] = "https://example.org/twin/"
    (tmp_path / "twin" / P.CONFIG_NAME).write_text(json.dumps(cfg))
    deposit(a, "open", "three")
    deposit(tmp_path / "twin", "open", "three, otherwise")
    run("--root", str(lib), "mirror", uri(a, "open"))
    with pytest.raises(SystemExit, match="fork of the line"):
        run("--root", str(lib), "mirror", uri(a, "open"), "--at", "https://example.org/twin/")
    _, nm, owner = line(a, "open").split(":")
    P.configure(lib)
    with remote.Resolver() as r:
        found = r.latest(nm, owner, ["https://example.org/authors/", "https://example.org/twin/"])
        assert found.status == "fork" and any("a fork of the line" in m for _, m in r.notes)


def test_mirror_copies_what_it_judged(tmp_path, monkeypatch, capsys):
    a, lib = make(tmp_path, "authors"), make(tmp_path, "library")
    deposit(a, "open", "one", new=True)
    deposit(a, "open", "two")
    obj_id = line(a, "open")
    src = P.obj_dir(obj_id)
    fetch = remote.fetch_object

    def changing(*args, **kw):
        p = src / "v2" / "inventory.json"
        p.write_bytes(p.read_bytes() + b"\n")
        return fetch(*args, **kw)
    monkeypatch.setattr(remote, "fetch_object", changing)
    with pytest.raises(SystemExit, match="not the one verified"):
        run("--root", str(lib), "mirror", uri(a, "open"))
    P.configure(lib)
    assert not P.obj_dir(obj_id).exists()
    monkeypatch.setattr(remote, "fetch_object", fetch)
    p = src / "v2" / "inventory.json"
    p.write_bytes(p.read_bytes()[:-1])
    w = src / sign.WITNESSES / "v1"
    good = sorted(w.iterdir())[0]
    forged = json.loads(good.read_text())
    forged["inventorySha512"] = "0" * 128
    (w / "signature-forged.json").write_text(json.dumps(forged))
    (w / "signature-forged.json.ots").write_bytes(b"x")
    capsys.readouterr()
    run("--root", str(lib), "mirror", uri(a, "open"))
    assert "signature-forged.json" in capsys.readouterr().err
    P.configure(lib)
    mw = P.obj_dir(obj_id) / sign.WITNESSES / "v1"
    assert (mw / good.name).exists() and not (mw / "signature-forged.json").exists()
    assert not (mw / "signature-forged.json.ots").exists()
    assert errors(lib) == []


def test_check_remote_tries_the_copies(tmp_path):
    a, lib, c = make(tmp_path, "a"), make(tmp_path, "lib"), make(tmp_path, "c")
    deposit(a, "open", "one", new=True)
    run("--root", str(lib), "mirror", uri(a, "open"))
    run("--root", str(c), "collection", "new", "list", "--type", "catalogue", "--title", "List")
    run("--root", str(c), "collection", "add", "list", uri(a, "open"), "--at", "https://example.org/lib/")
    m = members(c, "list")["members"][0]
    assert m["at"] == ["https://example.org/a/", "https://example.org/lib/"]
    obj_dir = P.obj_dir(line(a, "open"))
    shutil.move(str(obj_dir), str(tmp_path / "lost"))
    assert [x for x in findings(c, True) if x["severity"] == "warning" and "member" in x["place"]] == []
    shutil.move(str(lib), str(tmp_path / "lib-gone"))
    assert any(x["message"] == "unavailable (section 8.5)" for x in findings(c, True))


def test_owner_pull_and_a_fork_of_the_key_log(tmp_path, capsys):
    a = make(tmp_path, "a")
    owner = P.ARCHIVE["owner"]
    deposit(a, "paper", "one", new=True)
    b = tmp_path / "b"
    run("init", str(b), "--name", "B", "--base-url", "https://example.org/b/", "--curator", "Doe, Jane",
        "--owner", owner, "--key-log", str(a / "ocfl" / owner / owner))
    rk = rotation_files(tmp_path / "a-keys")
    run("--root", str(a), "owner", "rotate", "--rotation-key", rk[0], "--rotation-key", rk[1],
        "--export", str(tmp_path / "k2"), "--no-passphrase", "--yes")
    run("--root", str(b), "owner", "pull", "https://example.org/a/")
    P.configure(b)
    assert len(P.key_log(owner).versions) == 2 and errors(b) == []
    twin = tmp_path / "twin"
    shutil.copytree(a, twin)
    run("--root", str(twin), "owner", "rotate", "--rotation-key", rotation_files(tmp_path / "k2")[0],
        "--rotation-key", rotation_files(tmp_path / "k2")[1], "--export", str(tmp_path / "k3a"),
        "--no-passphrase", "--yes")
    run("--root", str(a), "owner", "rotate", "--rotation-key", rotation_files(tmp_path / "k2")[0],
        "--rotation-key", rotation_files(tmp_path / "k2")[2], "--export", str(tmp_path / "k3b"),
        "--no-passphrase", "--yes")
    capsys.readouterr()
    run("--root", str(b), "owner", "pull", str(a / "ocfl" / owner / owner))
    run("--root", str(b), "owner", "pull", str(twin))
    assert "a fork at v3" in capsys.readouterr().out
    P.configure(b)
    log = P.key_log(owner)
    assert log.fork_point == 3 and log.ended and log.versions[-1].fork_record
    found = findings(b)
    assert [x for x in found if x["severity"] == "error"] == []
    assert any(x["message"] == "ended by a fork of its key log at v3 (section 6.3)" for x in found)
    carried = log.versions[-1].carried[0]
    assert any(e["inventorySha512"] == carried.digest and e["version"] == "v3" for e in P.read_index("sha512"))
    with pytest.raises(SystemExit, match="has ended"):
        deposit(b, "new-paper", "two", new=True)
    lib = make(tmp_path, "lib")
    run("--root", str(lib), "owner", "pull", "https://example.org/b/", "--owner", owner)
    with pytest.raises(SystemExit, match="frozen"):
        run("--root", str(lib), "mirror", uri(a, "paper"))
    run("--root", str(a), "owner", "pull", "https://example.org/twin/")
    P.configure(a)
    assert P.key_log(owner).fork_point == 3


def test_a_pin_to_a_key_log_version_that_is_not_one(tmp_path):
    from opensheaf import collections
    a = make(tmp_path, "a")
    owner = P.ARCHIVE["owner"]
    rk = rotation_files(tmp_path / "a-keys")
    run("--root", str(a), "owner", "rotate", "--rotation-key", rk[0], "--rotation-key", rk[1],
        "--export", str(tmp_path / "k2"), "--no-passphrase", "--yes")
    P.configure(a)
    kd = P.obj_dir(names.object_id(owner, owner))
    dig = P.digest(kd / "v2" / "inventory.json")
    member = {"kind": "owner", "name": owner, "owner": owner, "at": ["https://example.org/a/"],
              "version": "v2", "inventorySha512": dig}
    collections.write(None, {"format": collections.FORMAT, "type": "catalogue", "order": "manual",
                             "members": [member]}, message="test", title="Keys", owner=owner, label="keys")
    with remote.Resolver(here=False, places=[str(a)]) as r:
        assert r.pin(owner, owner, "v2", dig).status == "verified"
    assert not [e for e in errors(a) if "not a version of the key log" in e]
    shutil.rmtree(kd / sign.WITNESSES / "v2")
    P.configure(a)
    assert P.key_log(owner).lookup(2, dig) is not None and P.key_log(owner).verified(2, dig) is None
    with remote.Resolver(here=False, places=[str(a)]) as r:
        assert r.pin(owner, owner, "v2", dig).status == "not a version"
    assert any("not a version of the key log" in e for e in errors(a))


def test_sign_again(tmp_path):
    a = make(tmp_path, "a")
    first = P.key_log(P.ARCHIVE["owner"]).latest().keys["keys"][0]
    deposit(a, "paper", "one", new=True)
    P.configure(a)
    third = P.key_new(P.argparse_namespace(owner=None)).did
    rk = rotation_files(tmp_path / "a-keys")
    run("--root", str(a), "owner", "expose", first, "--add", third, "--rotation-key", rk[0],
        "--rotation-key", rk[1], "--export", str(tmp_path / "k2"), "--no-passphrase", "--yes")
    d = P.obj_dir(line(a, "paper"))
    assert P.line_statuses(d, P.load_inventory(d))[1] == [sign.CONTESTED]
    run("--root", str(a), "sign", "paper", "--version", "v1", "--yes")
    P.configure(a)
    assert P.line_statuses(d, P.load_inventory(d))[1] == [sign.SIGNED]
    assert errors(a) == []
    with pytest.raises(SystemExit, match="signing again is for a version contested"):
        run("--root", str(a), "sign", "paper", "--version", "v1", "--yes")


def test_accept_vetted_versions(tmp_path):
    a, j = make(tmp_path, "authors"), make(tmp_path, "journal")
    deposit(a, "paper", "one", new=True)
    deposit(a, "paper", "two")
    run("--root", str(j), "collection", "new", "issue-1", "--type", "selection", "--title", "Issue 1")
    run("--root", str(j), "accept", uri(a, "paper", 2), "--selection", "issue-1", "--label", "paper",
        "--with-original")
    _, nm, a_owner = line(a, "paper").split(":")
    branch_id = line(j, "paper")
    j_owner = P.ARCHIVE["owner"]
    assert branch_id == f"sheaf:{nm}:{j_owner}"
    d = P.obj_dir(branch_id)
    inv = P.load_inventory(d)
    obj = P.read_json(d, inv, P.OBJ)
    assert obj["parent"]["owner"] == a_owner and obj["parent"]["objectVersion"] == "v2"
    assert obj["parent"]["url"] == f"https://example.org/authors/ocfl/{a_owner}/{nm}/v2/"
    assert obj["documentVersion"] == 1 and obj["parent"]["documentVersion"] == 2 and "previous" not in obj
    jbase = json.loads((j / P.CONFIG_NAME).read_text())["baseUrl"]
    assert P.read_json(d, inv, "datacite.json")["url"] == f"{jbase}paper/{nm}-{j_owner}/"
    held = {p for ps in inv["versions"]["v1"]["state"].values() for p in ps}
    assert {"genesis.json", "paper.pdf", "parent/inventory.json", "parent/object.json"} <= held
    assert any(p.startswith("parent/signatures/signature-") for p in held)
    assert P.read_logical(d, inv, "parent/inventory.json").read_bytes() == \
        (P.obj_dir(line(a, "paper")) / "v2" / "inventory.json").read_bytes()
    P.configure(j)
    assert P.key_log(a_owner) is not None
    mem = members(j, "issue-1")["members"]
    assert [(m["owner"], [r["documentVersion"] for r in m["revisions"]]) for m in mem] == \
        [(j_owner, [1]), (a_owner, [2])]
    found = findings(j)
    assert [x for x in found if x["severity"] == "error"] == []
    assert any(x["message"].endswith(": confirmed (section 9.3)") for x in found)
    deposit(a, "paper", "three")
    P.configure(j)
    assert list(P.load_inventory(P.obj_dir(branch_id))["versions"]) == ["v1"]
    remark = tmp_path / "remark.md"
    remark.write_text("Accepted with a remark.")
    run("--root", str(j), "notice", "paper", "--about", "1", "--text", "A remark.", "--file", str(remark))
    run("--root", str(j), "accept", uri(a, "paper", 3), "--selection", "issue-1")
    P.configure(j)
    inv = P.load_inventory(P.obj_dir(branch_id))
    obj = P.read_json(P.obj_dir(branch_id), inv, P.OBJ)
    assert inv["head"] == "v3" and obj["documentVersion"] == 2 and obj["parent"]["objectVersion"] == "v3"
    assert obj["parent"]["documentVersion"] == 3 and obj["notices"][0]["text"] == "A remark."
    assert P.read_logical(P.obj_dir(branch_id), inv, obj["notices"][0]["path"]).read_text() == \
        "Accepted with a remark."
    assert [r["documentVersion"] for r in members(j, "issue-1")["members"][0]["revisions"]] == [1, 2]
    assert errors(j) == []
    with pytest.raises(SystemExit, match="the branch point of the branch already"):
        run("--root", str(j), "accept", uri(a, "paper", 3), "--selection", "issue-1")
    run("--root", str(a), "notice", "paper", "--about", "3", "--text", "A remark.")
    with pytest.raises(SystemExit, match="not a new branch point"):
        run("--root", str(j), "accept", uri(a, "paper"), "--selection", "issue-1")


def test_branch_of_a_branch_and_a_clash(tmp_path):
    a, j, b = make(tmp_path, "authors"), make(tmp_path, "journal"), make(tmp_path, "b")
    deposit(a, "paper", "one", new=True)
    run("--root", str(j), "branch", uri(a, "paper", 1), "--label", "accepted")
    run("--root", str(b), "branch", uri(j, "accepted", 1), "--label", "continued")
    _, nm, a_owner = line(a, "paper").split(":")
    j_owner = line(j, "accepted").split(":")[2]
    d = P.obj_dir(line(b, "continued"))
    inv = P.load_inventory(d)
    held = {p for ps in inv["versions"]["v1"]["state"].values() for p in ps}
    assert "parent/parent/inventory.json" in held and "parent/parent/object.json" in held
    assert any(p.startswith("parent/parent/signatures/") for p in held)
    P.configure(b)
    assert P.key_log(a_owner) is not None and P.key_log(j_owner) is not None
    found = findings(b)
    assert [x for x in found if x["severity"] == "error"] == []
    assert any(x["message"].endswith(": confirmed (section 9.3)") for x in found)
    run("--root", str(j), "branch", uri(b, "continued", 1), "--label", "again")
    renamed = line(j, "again").split(":")[1]
    assert renamed != nm and names.algorithm(renamed) == 1
    assert names.is_name_of(renamed, P.read_logical(d, inv, P.GENESIS).read_bytes())
    found = findings(j)
    assert [x for x in found if x["severity"] == "error"] == []
    assert not any("renamed by algorithm" in x["message"] for x in found)
    with pytest.raises(SystemExit, match="neither the parent's owner nor the originator"):
        run("--root", str(a), "branch", uri(j, "accepted", 1), "--label", "back")


def test_evidence_of_another_form(tmp_path):
    from opensheaf import branch
    g = names.genesis_record("document", originator="z" + "a" * 51)
    nm = names.name(g, 0)
    for pinv in (b"not json", b"[1]", b'{"versions": []}', b"[" * 100 + b"]" * 100):
        level = branch.level_of_files({"parent/inventory.json": pinv, "parent/object.json": b"{}"})
        v, problems = branch.verdict(level, {"parent": {"name": nm}, "name": nm, "owner": "x"}, g,
                                     lambda o: None)
        assert v == branch.INCONSISTENT and problems
    owner = "q" * 51 + "a"
    files = {"parent/" * k + "parent/object.json": json.dumps({"owner": owner}).encode()
             for k in range(200)}
    assert len(branch.chain_owners(files)) == branch.MAX_DEPTH + 1
    files["parent/parent/object.json"] = b"[]"
    assert branch.chain_owners(files) == [owner]


def test_inconsistent_branch_point(tmp_path):
    a, j = make(tmp_path, "authors"), make(tmp_path, "journal")
    deposit(a, "paper", "one", new=True)
    run("--root", str(j), "branch", uri(a, "paper", 1), "--label", "accepted")
    d = P.obj_dir(line(j, "accepted"))
    inv = P.load_inventory(d)
    from opensheaf import branch
    level = branch.level_of_version(d, inv, "v1")
    obj, genesis = P.read_json(d, inv, P.OBJ), P.read_logical(d, inv, P.GENESIS).read_bytes()
    assert branch.verdict(level, obj, genesis, P.key_log)[0] == branch.CONFIRMED
    unsigned = {p: level.read(p) for p in level.digests if not p.startswith("parent/signatures/")}
    v, problems = branch.verdict(branch.level_of_files(unsigned), obj, genesis, P.key_log)
    assert v == branch.INCONSISTENT and any("not a version: unsigned" in p for p in problems)
    changed = {p: level.read(p) for p in level.digests}
    changed["paper.pdf"] = b"%PDF-1.4 another"
    v, problems = branch.verdict(branch.level_of_files(changed), obj, genesis, P.key_log)
    assert v == branch.INCONSISTENT and any(p.startswith("paper.pdf") for p in problems)
    assert branch.verdict(level, obj, genesis, lambda o: None)[0] == branch.UNCHECKED
    pobj = json.loads(level.read("parent/object.json"))
    forged = json.dumps(dict(pobj, parent=dict(obj["parent"]))).encode()
    stated = branch.Level(level.digests, lambda p: forged if p == "parent/object.json" else level.read(p))
    v, problems = branch.verdict(stated, obj, genesis, P.key_log)
    assert v == branch.INCONSISTENT and \
        "parent/object.json is not the object.json the parent inventory records" in problems
    v, problems = branch.verdict(branch.level_of_files(unsigned), obj, genesis, P.key_log,
                                 resolve=lambda p: (True, sign.SIGNED))
    assert v == branch.CONFIRMED, problems
    v, problems = branch.verdict(level, obj, genesis, P.key_log, resolve=lambda p: (False, None))
    assert v == branch.INCONSISTENT and \
        "the parent version, resolved, does not match the pin (section 9.3)" in problems
    pid = line(a, "paper")
    pd = P.obj_dir(pid)
    found = {pid: (pd, P.load_inventory(pd))}
    v, problems = branch.verdict(level, obj, genesis, P.key_log, resolve=lambda p: (True, sign.CONTESTED))
    assert v == branch.UNCHECKED and "the parent version is contested (section 9.3)" in problems
    owner = obj["parent"]["owner"]
    logs = {owner: P.key_log(owner)}
    assert P.parent_resolution(found, logs)(obj["parent"]) == (True, sign.SIGNED)
    assert P.parent_resolution(found, logs)(dict(obj["parent"], inventorySha512="0" * 128)) == (False, None)
    assert P.parent_resolution({}, logs)(obj["parent"]) is None
    assert P.parent_resolution(found, {})(obj["parent"]) == (True, sign.UNCHECKED)


def test_the_history_of_a_branch(tmp_path):
    a, j = make(tmp_path, "authors"), make(tmp_path, "journal")
    deposit(a, "paper", "one", new=True)
    deposit(a, "paper", "two")
    run("--root", str(j), "branch", uri(a, "paper", 2), "--label", "continued")
    deposit(j, "continued", "three")
    deposit(j, "continued", "earlier", "--after", "1")
    d = P.obj_dir(line(j, "continued"))
    inv = P.load_inventory(d)
    hist = P.read_json(d, inv, P.OBJ)["history"]
    assert [P.doc_version_of(d, inv, v) for v in hist] == [1, 3, 2]
    assert P.document_version_errors(line(j, "continued"), d, inv) == []
    assert errors(j) == []


def test_the_archive_of_a_parent_url(tmp_path):
    a = make(tmp_path, "authors")
    deposit(a, "paper", "one", new=True)
    obj_id = line(a, "paper")
    s = tmp_path / "store"
    shutil.copytree(a, s)
    (s / "ocfl").rename(s / "objects")
    disc = json.loads((s / "opensheaf.json").read_text())
    disc["storageRoot"] = "objects/"
    (s / "opensheaf.json").write_text(json.dumps(disc))
    at = P.path_of(obj_id)
    url = f"https://example.org/store/objects/{at}/v1/"
    with remote.Resolver(here=False) as r:
        assert r.archive_of(url) == ["https://example.org/store/"]
        assert r.archive_of(url) is r.archive_of(url)
        found = r.latest(*obj_id.split(":")[1:], r.archive_of(url))
        assert found.status == "verified" and found.copy.where == "https://example.org/store/"
        assert r.archive_of(f"https://example.org/authors/ocfl/{at}/v1/") == ["https://example.org/authors/"]
        assert r.archive_of("https://example.org/store/objects/") == []
        assert r.archive_of(f"https://example.org/nowhere/ocfl/{at}/v1/") == []
        assert not [n for n in r.notes if "unavailable" in n[1]]


def test_owner_catalogues(tmp_path):
    a = make(tmp_path, "a")
    r = ["--root", str(a)]
    first = line(a, "main").split(":")[2]
    deposit(a, "paper", "one", new=True)
    run(*r, "collect")
    run(*r, "owner", "init", "--export", str(tmp_path / "second-keys"), "--no-passphrase", "--yes")
    P.configure(a)
    second = P.ARCHIVE["owners"][0]
    disc = json.loads((a / "opensheaf.json").read_text())
    assert [e["owner"] for e in disc["owners"]] == [first, second] and "mainCollection" not in disc
    cat1, cat2 = (e["catalogue"] for e in disc["owners"])
    assert cat1 == line(a, "main") and cat2.split(":")[2] == second and P.label_of(cat2) is None
    run(*r, "label", "--owner", second, "jane")
    P.configure(a)
    assert P.label_of(cat2) == "jane-catalogue"
    assert cat2 not in (P.ARCHIVE.get("formerAddresses") or {}).values()   # it had no page before
    run(*r, "label", "--owner", second, "jo")
    P.configure(a)
    assert P.label_of(cat2) == "jo-catalogue" and P.label_of(cat1) == "main"
    run(*r, "label", "--owner", second, "--unset")
    P.configure(a)
    assert P.label_of(cat2) is None
    run(*r, "label", "--owner", second, "jo")
    P.configure(a)
    assert P.label_of(cat2) == "jo-catalogue"
    run(*r, "label", "jo-catalogue", "--unset")
    run(*r, "label", "--owner", second, "jo")
    P.configure(a)
    assert P.label_of(cat2) == "jo-catalogue"

    def listed(cat):
        d = P.obj_dir(cat)
        return [(m["name"], m["owner"]) for m in P.read_json(d, P.load_inventory(d), "members.json")["members"]]

    def head(cat):
        return P.load_inventory(P.obj_dir(cat))["head"]

    assert listed(cat2) == [] and head(cat2) == "v1"
    head1 = head(cat1)
    deposit(a, "theirs", "two", "--owner", second, new=True)
    run(*r, "branch", uri(a, "paper", 1), "--owner", second, "--label", "continued")
    run(*r, "collect", "--owner", second)
    P.configure(a)
    assert head(cat1) == head1 and head(cat2) == "v2"
    run(*r, "collect")
    P.configure(a)
    assert head(cat1) == head1
    assert listed(cat1) == [tuple(line(a, "paper").split(":")[1:])]
    assert sorted(listed(cat2)) == sorted(tuple(line(a, x).split(":")[1:]) for x in ("theirs", "continued"))
    assert errors(a) == []
    home = (a / "index.html").read_text()
    pins = [head_digest(a, x, "v1")[:32] for x in ("paper", "theirs")]
    assert all(p in home for p in pins) and 'class="owner-heading"' not in home
    assert f'<a class="owner" href="owner/{second}/">jo</a>' in home
    assert f'<a class="owner" href="owner/{first}/">' in home
    cfg = json.loads((a / "osheaf.json").read_text())
    cfg["index"]["owners"] = "by-owner"
    (a / "osheaf.json").write_text(json.dumps(cfg, indent=2) + "\n")
    run(*r, "index")
    home = (a / "index.html").read_text()
    headings = [i for i in range(len(home)) if home.startswith('<h2 class="owner-heading">', i)]
    assert len(headings) == 2 and headings[0] < home.index(pins[0]) < headings[1] < home.index(pins[1])
    assert '>jo</a></h2>' in home and '<a class="owner" href="owner/' in home[headings[1]:]
    cfg["index"]["owners"] = "mixed"
    (a / "osheaf.json").write_text(json.dumps(cfg, indent=2) + "\n")
    with pytest.raises(SystemExit, match="together or by-owner"):
        run(*r, "index")
    cfg["index"]["owners"] = "together"
    (a / "osheaf.json").write_text(json.dumps(cfg, indent=2) + "\n")
    with pytest.raises(SystemExit, match="not an owner this archive hosts"):
        run(*r, "collect", "--owner", "a" * 51 + "q")
    disc = json.loads((a / "opensheaf.json").read_text())
    wrong = dict(disc, owners=[disc["owners"][0], {"owner": second, "catalogue": cat1}, disc["owners"][0]])
    (a / "opensheaf.json").write_text(json.dumps(wrong))
    messages = [x["message"] for x in findings(a) if x["severity"] == "error"]
    assert any(f"the catalogue of {second} in owners" in m for m in messages)
    assert any(f"owners lists {first} twice" in m for m in messages)
    (a / "opensheaf.json").write_text(json.dumps(dict(disc, owners=disc["owners"][::-1])))
    assert errors(a) == []
    d = P.obj_dir(cat2)
    mem = P.read_json(d, P.load_inventory(d), "members.json")
    theirs = next(m for m in mem["members"] if m["name"] == line(a, "theirs").split(":")[1])
    mine = dict(theirs, name=line(a, "paper").split(":")[1], owner=first,
                version="v1", inventorySha512=head_digest(a, "paper", "v1"))
    from opensheaf import collections
    collections.write(cat2, dict(mem, order="manual", members=mem["members"] + [mine]), message="Another's")
    found = findings(a)
    assert any(x["severity"] == "warning" and f"the owner catalogue of {second} lists" in x["message"]
               for x in found)
    (a / "opensheaf.json").write_text(json.dumps({k: v for k, v in disc.items() if k != "owners"}))
    assert any(x["severity"] == "error" and "no owners" in x["message"] for x in findings(a))


def test_collect_skips_an_owner_without_keys(tmp_path, capsys):
    a = make(tmp_path, "a")
    r = ["--root", str(a)]
    deposit(a, "paper", "one", new=True)
    run(*r, "owner", "init", "--export", str(tmp_path / "second-keys"), "--no-passphrase", "--yes")
    P.configure(a)
    second = P.ARCHIVE["owners"][0]
    deposit(a, "theirs", "two", "--owner", second, new=True)
    run(*r, "collect")
    P.configure(a)
    cat1, cat2 = P.CATALOGUES[P.ARCHIVE["owner"]], P.CATALOGUES[second]
    heads = {c: P.load_inventory(P.obj_dir(c))["head"] for c in (cat1, cat2)}
    deposit(a, "theirs", "three", "--owner", second)
    P.configure(a)
    P.forget_here(second, P.key_log(second).latest().keys["keys"])
    deposit(a, "paper", "four")
    capsys.readouterr()
    with pytest.raises(SystemExit, match=r"1 owner catalogue not collected \(.*\): this computer does not "
                                         r"hold the keys to sign for it; the others are collected"):
        run(*r, "collect")
    err = capsys.readouterr().err
    assert f"Warning: Skipped the owner catalogue of {names.short(second)}: this computer holds 0 of" in err
    assert f"osheaf collect --owner {second} collects it on a computer that holds its keys" in err
    P.configure(a)
    assert P.load_inventory(P.obj_dir(cat1))["head"] == f"v{int(heads[cat1][1:]) + 1}"
    assert P.load_inventory(P.obj_dir(cat2))["head"] == heads[cat2]
    assert P.CATALOGUES == {P.ARCHIVE["owner"]: cat1, second: cat2}
    assert head_digest(a, "paper", "v2")[:32] in (a / "index.html").read_text()
    assert errors(a) == []
    with pytest.raises(SystemExit, match="This computer holds 0 of the current keys"):
        run(*r, "collect", "--owner", second)
    assert P.load_inventory(P.obj_dir(cat2))["head"] == heads[cat2]


def test_draft_and_seal(tmp_path):
    a = make(tmp_path, "a")
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4 draft one")
    base = ["--pdf", str(pdf), "--no-source", "x", "--title", "Notes", "--author", "Doe, J"]
    run("--root", str(a), "draft", "new", "notes", *base)
    pdf.write_bytes(b"%PDF-1.4 draft two")
    run("--root", str(a), "draft", "deposit", "notes", *base)
    pdf.write_bytes(b"%PDF-1.4 draft two, corrected")
    run("--root", str(a), "draft", "deposit", "notes", *base, "--replace")
    d = P.OCFL / "draft" / "notes"
    inv = P.load_inventory(d)
    assert inv["head"] == "v2" and not (d / sign.WITNESSES).exists()
    obj = P.read_json(d, inv, P.OBJ)
    assert "name" not in obj and "owner" not in obj and "previous" not in obj
    disc = json.loads((a / "opensheaf.json").read_text())
    assert disc["drafts"] == [{"id": "sheaf:draft:notes", "kind": "document", "head": "v2"}]
    assert all(not e["id"].startswith("sheaf:draft") for e in P.read_index("sha512"))
    assert errors(a) == []
    run("--root", str(a), "seal", "notes", "--label", "lecture-notes")
    sealed = P.obj_dir(line(a, "lecture-notes"))
    sinv = P.load_inventory(sealed)
    sobj = P.read_json(sealed, sinv, P.OBJ)
    assert sobj["documentVersion"] == 1 and sobj["owner"] == P.ARCHIVE["owner"]
    assert P.read_logical(sealed, sinv, "paper.pdf").read_bytes() == b"%PDF-1.4 draft two, corrected"
    assert P.line_statuses(sealed, sinv)[1] == [sign.SIGNED]
    run("--root", str(a), "draft", "delete", "notes")
    disc = json.loads((a / "opensheaf.json").read_text())
    assert "drafts" not in disc and "tombstones" not in disc
    run("--root", str(a), "collect")
    assert errors(a) == []


@pytest.mark.parametrize("layout", ["owner-name", "hashed"])
def test_seal_delete_draft_leaves_no_empty_folder(tmp_path, layout):
    a = make(tmp_path, "a", *(["--layout", "hashed"] if layout == "hashed" else []))
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4 draft")
    run("--root", str(a), "draft", "new", "notes", "--pdf", str(pdf), "--no-source", "x", "--title", "Notes",
        "--author", "Doe, J")
    run("--root", str(a), "seal", "notes", "--label", "lecture-notes", "--delete-draft")
    assert not (P.OCFL / "draft").exists()
    assert [p for p in P.OCFL.rglob("*") if p.is_dir() and not any(p.iterdir())] == []
    assert errors(a) == []


def test_takedown_and_return(tmp_path, capsys):
    a, lib = make(tmp_path, "a"), make(tmp_path, "lib")
    deposit(a, "paper", "one", new=True)
    deposit(a, "other", "two", new=True)
    obj_id = line(a, "paper")
    _, nm, owner = obj_id.split(":")
    run("--root", str(lib), "mirror", uri(a, "paper"))
    run("--root", str(a), "takedown", "paper", "--reason", "At the request of the holder of the rights.",
        "--yes")
    P.configure(a)
    assert not P.obj_dir(obj_id).exists() and P.key_log(owner) is not None
    tomb = json.loads((a / "opensheaf.json").read_text())["tombstones"][0]
    assert set(tomb) == {"id", "kind", "name", "owner", "genesisName", "lastVersion", "inventorySha512",
                         "date", "reason"} and tomb["genesisName"] == nm
    assert [e["status"] for e in P.read_index("names") if e["id"] == obj_id] == ["removed"]
    assert all(nm not in e["names"] for e in P.read_index("owners"))
    found = findings(a)
    assert [x for x in found if x["severity"] == "error"] == []
    assert any(x["message"].startswith(f"removed: {obj_id}") for x in found)
    with pytest.raises(SystemExit, match="by law or at its keeper's request"):
        run("--root", str(a), "takedown", f"sheaf:{owner}:{owner}", "--reason", "x", "--yes")
    capsys.readouterr()
    run("--root", str(lib), "mirror", "--all")
    assert f"{obj_id} was taken down at" in capsys.readouterr().err
    P.configure(lib)
    assert P.obj_dir(obj_id).exists()
    pin = P.digest(P.obj_dir(obj_id) / "v1" / "inventory.json")
    run("--root", str(lib), "takedown", obj_id, "--reason", "Stopped keeping it.", "--yes")
    assert json.loads((lib / "opensheaf.json").read_text())["tombstones"][0]["inventorySha512"] == pin
    assert errors(lib) == []
    run("--root", str(lib), "takedown", f"sheaf:{owner}:{owner}", "--reason", "A court order.", "--by-law",
        "--yes")
    found = findings(lib)
    assert [x for x in found if x["severity"] == "error"] == []


def test_line_returns(tmp_path):
    a, lib = make(tmp_path, "a"), make(tmp_path, "lib")
    deposit(a, "paper", "one", new=True)
    obj_id = line(a, "paper")
    run("--root", str(lib), "mirror", uri(a, "paper"))
    run("--root", str(lib), "takedown", obj_id, "--reason", "Stopped keeping it.", "--yes")
    P.configure(lib)
    assert P.TOMBSTONES and not P.obj_dir(obj_id).exists()
    run("--root", str(lib), "mirror", uri(a, "paper"))
    P.configure(lib)
    assert not P.TOMBSTONES and P.obj_dir(obj_id).exists()
    assert errors(lib) == []


def test_object_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "OBJECTS_PER_PAGE", 2)
    a = make(tmp_path, "a")
    for label in ("one", "two", "three"):
        deposit(a, label, label, new=True)
    disc = json.loads((a / "opensheaf.json").read_text())
    assert "objects" not in disc and disc["objectPages"]
    pages = [json.loads((a / p).read_text()) for p in disc["objectPages"]]
    assert all(p["format"] == "opensheaf-objects/0.2" and len(p["objects"]) <= 2 for p in pages)
    listed = [o["id"] for p in pages for o in p["objects"]]
    assert len(listed) == len(set(listed)) == len(P.discovery()["objects"])
    assert errors(a) == []
    P.configure(a)
    assert P.LABELS["two"] == line(a, "two")
    line_id_two = line(a, "two")
    _, nm, owner = line_id_two.split(":")
    with remote.Resolver(here=False, places=[str(a)]) as r:
        assert r.pin(nm, owner, "v1", head_digest(a, "two", "v1")).status == "verified"
    first = a / disc["objectPages"][0]
    saved = first.read_bytes()
    first.unlink()
    assert any("is missing (section 3.1)" in e for e in errors(a))
    with remote.Resolver(here=False) as r:
        assert r.source(str(a)) is None
    before = (a / "opensheaf.json").read_bytes()
    assert (a / "paper" / "two" / "index.html").exists()
    for argv in (["index"], ["deposit", "two", "--pdf", str(a.parent / "two.pdf"), "--no-source", "x",
                             "--title", "Two", "--author", "Doe, J", "--issued", "2020-01-01"]):
        with pytest.raises(SystemExit, match="the labels of the lines are not known"):
            run("--root", str(a), *argv)
    P.configure(a)
    with pytest.raises(SystemExit, match="the labels of the lines are not known"):
        P.write_discovery()
    assert (a / "opensheaf.json").read_bytes() == before and (a / "paper" / "two" / "index.html").exists()
    assert not (P.obj_dir(line_id_two) / "v2").exists()
    first.write_bytes(b"\xef\xbb\xbf" + saved)
    assert any("without a byte order mark, and this file starts with one" in e for e in errors(a))
    first.write_bytes(saved.decode("utf-8").encode("utf-16"))
    assert any("JSON is UTF-8, and this file is not" in e for e in errors(a))
    first.write_bytes(saved)
    monkeypatch.setattr(P, "OBJECTS_PER_PAGE", 1000)
    P.configure(a)
    P.write_discovery()
    disc = json.loads((a / "opensheaf.json").read_text())
    assert "objectPages" not in disc and not (a / "objects").exists()
    assert errors(a) == []


def test_indexes(tmp_path):
    a = make(tmp_path, "a")
    deposit(a, "paper", "one", new=True)
    deposit(a, "paper", "two")
    run("--root", str(a), "collect")
    run("--root", str(a), "index")
    P.configure(a)
    disc = json.loads((a / "opensheaf.json").read_text())
    assert disc["indexes"] == {"names": 2, "owners": 2, "sha512": 2}
    obj_id = line(a, "paper")
    _, nm, owner = obj_id.split(":")
    entry = json.loads((a / "names" / f"{nm[:2]}.json").read_text())
    e = next(x for x in entry["entries"] if x["id"] == obj_id)
    d = P.obj_dir(obj_id)
    assert e["genesis"].encode() == P.read_logical(d, P.load_inventory(d), P.GENESIS).read_bytes()
    assert e["originator"] == owner and e["label"] == "paper" and e["status"] == "active"
    owners_ = json.loads((a / "owners" / f"{owner[:2]}.json").read_text())["entries"]
    assert set(next(x for x in owners_ if x["owner"] == owner)["names"]) >= {nm, owner}
    shas = [x for x in P.read_index("sha512") if x["id"] == obj_id]
    assert sorted(x["version"] for x in shas) == ["v1", "v2"]
    assert errors(a) == []
    target = a / "sha512" / f"{shas[0]['inventorySha512'][:2]}.json"
    target.unlink()
    assert any("no entry, or a stale one" in e for e in errors(a))


def test_the_verifier_reads_files_with_their_digests(tmp_path):
    a = make(tmp_path, "a")
    deposit(a, "paper", "one", new=True)
    d = P.obj_dir(line(a, "paper"))
    inv = P.load_inventory(d)
    g = d / P.content_path(inv, "v1", P.GENESIS)
    good = g.read_bytes()
    g.write_bytes(good.replace(b"{", b'{"x": 1e3, ', 1))
    errs = errors(a)
    assert f"paper: {P.content_path(inv, 'v1', P.GENESIS)} does not have the digest of the manifest" in errs
    assert not any("1e3" in e for e in errs), errs
    g.write_bytes(good)
    assert errors(a) == []
    o = d / P.content_path(inv, "v1", P.OBJ)
    o.write_bytes(o.read_bytes().replace(b'"documentVersion": 1', b'"documentVersion":  1'))
    found = [(x["severity"], x["place"], x["message"]) for x in findings(a)]
    assert ("error", "paper v1", "object.json cannot be read: it does not have the digest its inventory "
            "states (section 4.1)") in found
    assert ("error", "paper v1", "object.json does not record the line of the identifier (section 4.3)") in found
    assert ("warning", "paper v1", "not a version of the line: invalid (sections 7.3 and 7.5)") in found
    assert any(s == "warning" and m.endswith("invalid: its signer is not the owner of the line")
               for s, _, m in found), found


def test_tampered_evidence_is_not_read(tmp_path):
    a, j = make(tmp_path, "authors"), make(tmp_path, "journal")
    deposit(a, "paper", "one", new=True)
    run("--root", str(j), "branch", uri(a, "paper", 1), "--label", "accepted")
    pd = P.obj_dir(line(a, "paper"))
    shutil.copytree(pd, j / pd.relative_to(a))
    d = P.obj_dir(line(j, "accepted"))
    inv = P.load_inventory(d)
    sig = next(p for ps in inv["versions"]["v1"]["state"].values() for p in ps
               if p.startswith("parent/signatures/"))
    c = d / P.content_path(inv, "v1", sig)
    c.write_bytes(c.read_bytes().replace(b'"signature": "', b'"signature": "A', 1))
    errs = errors(j)
    assert f"accepted v1: inconsistent branch point: the evidence of the branch point cannot be read: {sig} " \
        "does not have the digest its inventory states (section 4.1)" in errs, errs


def test_a_key_log_that_cannot_be_read_ends_nothing(tmp_path):
    a, j = make(tmp_path, "authors"), make(tmp_path, "journal")
    deposit(a, "paper", "one", new=True)
    run("--root", str(j), "branch", uri(a, "paper", 1), "--label", "accepted")
    pid = line(a, "paper")
    pd = P.obj_dir(pid)
    shutil.copytree(pd, j / pd.relative_to(a))
    owner = pid.split(":")[2]
    P.configure(j)
    (P.obj_dir(names.object_id(owner, owner)) / "inventory.json").write_text("{not json")
    found = findings(j)
    assert not any("stopped on a file" in x["message"] for x in found), found
    assert any(x["severity"] == "error" and x["message"] == "an object without a readable inventory"
               for x in found)
    assert any(x["message"].startswith(f"the key log of its owner {owner} is not in the storage root")
               for x in found)


def test_both_objects_of_one_identifier_are_validated(tmp_path):
    pytest.importorskip("ocfl")
    a = make(tmp_path, "a")
    deposit(a, "paper", "one", new=True)
    d = P.obj_dir(line(a, "paper"))
    copy = P.OCFL / "0" / d.name
    shutil.copytree(d, copy)
    (copy / "stray.txt").write_text("not of OCFL")
    errs = errors(a)
    assert "paper: two objects of the storage root have this identifier (section 4)" in errs
    assert any(e.startswith("paper: OCFL validator:") and "stray.txt" in e for e in errs), errs
