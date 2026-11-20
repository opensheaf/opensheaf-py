The tests across archives
=========================

These tests use several archives in neighbouring folders of a test: one of
authors, and others that collect, mirror, branch or accept their
documents. Each archive has a base URL `https://example.org/<name>/`, which
collections and URIs record, and the *locations* of the
[resolver](20-resolution.md) map `https://example.org/` to the folder of
the test, so that no network is needed; one test serves the folder over
HTTP instead, with a local server, to read archives as a remote reader
does. They are in `tests/test_across.py`.

    # in tests/test_across.py:
    <<across: the imports and the helpers>>


    <<across: resolution>>


    <<across: collections>>


    <<across: mirrors and key logs>>


    <<across: signing again>>


    <<across: branches and accepted copies>>


    <<across: drafts>>


    <<across: takedowns and indexes>>

The helpers
-----------

The keys of the tests are those of the [other tests](70-tests.md):
predictable, in a key store of files of the test, with no wallet, GitHub
or clipboard within reach. `locations` maps the
base URLs to the folder of the test. `make` creates an archive named
`name` in that folder, with a new owner whose rotation keys go to
`<name>-keys`; `deposit` deposits a PDF alone, with a licence, as a new
work or a new version; `line` gives the identifier of a line by its label,
and `uri` a `sheaf:` URI of it, with the archive's base URL as `at`.

    # in across: the imports and the helpers:
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

Resolution
----------

A paper of archive `a`, in two versions, is resolved from another archive,
`c`, by its `sheaf:` URI (section 12.3): the originator's line, without
owner part, resolves to its latest signed version; `/v1` to the object
version holding document version 1; a pin to that version, and a wrong
digest to a mismatch. A short form is expanded among the lines the
archives read list. `osheaf resolve` prints the result as JSON, with the
full form of the pin.

    # in across: resolution:
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

Over HTTP, a reader cannot list folders: it reads the discovery document,
computes the path of each object in the archive's layout (here the hashed
layout, whose folder names hold `%3a`, encoded again in URLs), and fetches
the witnesses whose names it can compute from the owner's key log. The
archive is served by a local HTTP server, and the locations send the base
URL there.

    # in across: resolution:
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

Collections
-----------

Archive `papers` has two documents. Archive `reading` makes a catalogue
from a `collection.yaml` listing them by their URIs, the first followed
(section 8.3). Its members record the lines, never a label, and the base
URL where copies are found. A new version of the followed paper is
followed by `collection update`, and so is a withdrawal, a new signed
version like any other; the paper not followed keeps its pin. Every
member is verified across archives (`verify --remote`, section 14.5), and
`collection status` says so.

    # in across: collections:
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

The statuses of section 8.5, across archives: a member whose line is taken
down in its archive is removed; a pin of another digest is a mismatch; a
member whose archive has gone is unavailable; a version signed with a key
its owner later exposes is contested.

    # in across: collections:
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

A selection pins the revisions its curator vetted (section 8.4). Archive
`digest` vets document versions 2 and 1 of a paper with three; they are
kept in the order of the paper's history, each with the object version
that held it and its digest. Later versions of the paper change nothing:
`update` only reports the versions not vetted, and vetting one more is
the curator's act, a new version of the selection.

    # in across: collections:
    def test_selection_pins_revisions(tmp_path, capsys):
        a = make(tmp_path, "papers")
        for k in (1, 2, 3):
            deposit(a, "paper", f"version {k}", new=k == 1)
        s = make(tmp_path, "digest")
        spec = tmp_path / "digest.yaml"
        spec.write_text(f"type: selection\ntitle: Digest\nmembers:\n  - {{uri: '{uri(a, 'paper')}', "
                        "revisions: [2, 1]}\n")
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
        run("--root", str(s), "collection", "add", "digest", uri(a, "paper"), "--revision", "3")
        new = members(s, "digest")["members"][0]["revisions"]
        assert new[:2] == m["revisions"] and (new[2]["documentVersion"], new[2]["version"]) == (3, "v3")
        found = findings(s, remote_=True)
        assert [x for x in found if x["severity"] == "error"] == []
        with pytest.raises(SystemExit):
            run("--root", str(s), "collection", "add", "digest", uri(a, "paper"), "--revision", "9")

### A featured collection

An author's archive `author` holds a paper of its own and a reading list,
a selection with a paper of another archive and the author's own paper. The
main catalogue lists the archive's own documents (the reading list is a
line of the archive, not a member of the main catalogue); with
`index.html.featured` naming the reading list by its label, the home page
lists it first, under its title and with its description as the lead
paragraph, then the main catalogue, under its own heading. Both show their
pins, and the verifier, which checks the main catalogue's, is satisfied.
The paper of the other archive is read from there, checked against its
pin: its title links its own landing page, there. A collection of the
archive inside the featured one gets a landing page listing its members by
their lines, and a collection inside that one gets a page too. A setting
that names something other than a collection of the archive stops `osheaf
index`.

    # in across: collections:
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
        assert '<a class="paper-title" href="https://example.org/papers/paper/one/">One</a>' in home
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
        assert line(a, "part-one") in part
        assert (a / "paper" / "part-two" / "index.html").exists() and (a / "paper" / "mine" / "index.html").exists()
        assert errors(a) == []
        cfg["index"]["html"]["featured"] = "mine"
        (a / "osheaf.json").write_text(json.dumps(cfg))
        with pytest.raises(SystemExit, match="not a collection"):
            run("--root", str(a), "index")

Mirrors and key logs
--------------------

A library mirrors an openly licensed paper of the authors (section 11):
every version up to the latest signed, with the authors' key log beside
it; a paper whose licence does not allow redistribution is refused. The
mirror is listed like any line, without `mirrorOf`; the main catalogue
leaves it out, since its owner does not write here. Run again, the mirror
gets the new versions; a version without signatures is not added
(section 7.5).

    # in across: mirrors and key logs:
    def test_mirror(tmp_path):
        a, lib = make(tmp_path, "authors"), make(tmp_path, "library")
        deposit(a, "open", "one", new=True)
        deposit(a, "open", "two")
        deposit(a, "closed", "closed", new=True, rights="All rights reserved")
        with pytest.raises(SystemExit, match="does not clearly allow redistribution"):
            run("--root", str(lib), "mirror", uri(a, "closed"))
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

Two copies of a line that do not agree are a fork of the line (section
7.4): the paper is signed twice at version 3, once in each of two copies
of the authors' archive; the library, which mirrored one, refuses the
other, and keeps its side. A resolver given both copies notes the fork,
and does not choose.

    # in across: mirrors and key logs:
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

A copy is checked against pins too: a member pinned in archive `a` is
found at a mirror in the library when `a` loses it, and is unavailable
when both are gone (copies that agree, section 7.4).

    # in across: mirrors and key logs:
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

An owner that writes in two archives keeps a copy of its key log in each
(section 6.5). Keys changed in one reach the other by `owner pull`, which
extends its copy. When two copies are signed differently at the same
number, by rotation keys stolen before use, the key log forks (section
6.3): the archive keeps the side it saw first, and appends a fork record
carrying the other side, which ends the owner. Nothing is then signed for
it, and its lines are frozen: no archive mirrors them (section 7.5). The
fork record is a valid version, which the verifier reports, and the
indexes list the version it carries.

    # in across: mirrors and key logs:
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

Signing again
-------------

A version signed with a key the owner then exposes is contested
(section 7.3); while the owner is not ended, it signs the version again
with a current key not exposed, and the version is signed (section 7.1).
A version that is not contested is not signed again.

    # in across: signing again:
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

Branches and accepted copies
----------------------------

A journal accepts version 2 of the authors' paper (section 9.6): the
accepted copy is a branch under the journal's owner, named by the paper's
genesis name, holding the files of the authors' version 2, its genesis
record and the evidence of the branch point, and listed by the issue, a
selection, with the revision it holds and, with `--with-original`, the
authors' revision set. The authors' key log is kept beside it. The
authors' version 3 changes nothing in it; accepting version 3 moves the
branch point (section 9.4), the next document version of the branch, and
adds the revision. The verifier confirms the branch point at both
versions.

    # in across: branches and accepted copies:
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
        assert obj["documentVersion"] == 2 and "previous" not in obj
        held = {p for ps in inv["versions"]["v1"]["state"].values() for p in ps}
        assert {"genesis.json", "paper.pdf", "parent.inventory.json", "parent.object.json"} <= held
        assert any(p.startswith("parent.signatures/signature-") for p in held)
        assert P.read_logical(d, inv, "parent.inventory.json").read_bytes() == \
            (P.obj_dir(line(a, "paper")) / "v2" / "inventory.json").read_bytes()
        P.configure(j)
        assert P.key_log(a_owner) is not None
        mem = members(j, "issue-1")["members"]
        assert [(m["owner"], [r["documentVersion"] for r in m["revisions"]]) for m in mem] == \
            [(j_owner, [2]), (a_owner, [2])]
        found = findings(j)
        assert [x for x in found if x["severity"] == "error"] == []
        assert any(x["message"].endswith(": confirmed (section 9.3)") for x in found)
        deposit(a, "paper", "three")
        P.configure(j)
        assert list(P.load_inventory(P.obj_dir(branch_id))["versions"]) == ["v1"]
        run("--root", str(j), "accept", uri(a, "paper", 3), "--selection", "issue-1")
        P.configure(j)
        inv = P.load_inventory(P.obj_dir(branch_id))
        obj = P.read_json(P.obj_dir(branch_id), inv, P.OBJ)
        assert inv["head"] == "v2" and obj["documentVersion"] == 3 and obj["parent"]["objectVersion"] == "v3"
        assert [r["documentVersion"] for r in members(j, "issue-1")["members"][0]["revisions"]] == [2, 3]
        assert errors(j) == []
        with pytest.raises(SystemExit, match="the branch point of the branch already"):
            run("--root", str(j), "accept", uri(a, "paper", 3), "--selection", "issue-1")
        run("--root", str(a), "notice", "paper", "--about", "3", "--text", "A remark.")
        with pytest.raises(SystemExit, match="not a new branch point"):
            run("--root", str(j), "accept", uri(a, "paper"), "--selection", "issue-1")

A branch of a branch carries the evidence of its parent in `parent.chain/`
(section 9.2), and the key logs of every owner whose signatures the
evidence holds beside it (section 6.5). And when the owner of a branch
already has a line of the name, from another parent line, the new branch
is renamed by the next algorithm number (section 5.3); the verifier finds
the rename justified.

    # in across: branches and accepted copies:
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
        assert "parent.chain/parent.inventory.json" in held and "parent.chain/parent.object.json" in held
        assert any(p.startswith("parent.chain/parent.signatures/") for p in held)
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

A branch point whose evidence is tampered with is inconsistent, an error.

    # in across: branches and accepted copies:
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
        unsigned = {p: level.read(p) for p in level.digests if not p.startswith("parent.signatures/")}
        v, problems = branch.verdict(branch.level_of_files(unsigned), obj, genesis, P.key_log)
        assert v == branch.INCONSISTENT and any("not a version: unsigned" in p for p in problems)
        changed = {p: level.read(p) for p in level.digests}
        changed["paper.pdf"] = b"%PDF-1.4 another"
        v, problems = branch.verdict(branch.level_of_files(changed), obj, genesis, P.key_log)
        assert v == branch.INCONSISTENT and any(p.startswith("paper.pdf") for p in problems)
        assert branch.verdict(level, obj, genesis, lambda o: None)[0] == branch.UNCHECKED

A branch numbers on from its branch point (section 9.4), and holds none
of the parent's earlier versions: its history, once written, lists its
document versions from that of the branch point. Here a branch of version
2 gets version 3, then a version found later placed after 2, which writes
the history; the archive verifies.

    # in across: branches and accepted copies:
    def test_the_history_of_a_branch(tmp_path):
        a, j = make(tmp_path, "authors"), make(tmp_path, "journal")
        deposit(a, "paper", "one", new=True)
        deposit(a, "paper", "two")
        run("--root", str(j), "branch", uri(a, "paper", 2), "--label", "continued")
        deposit(j, "continued", "three")
        deposit(j, "continued", "earlier", "--after", "2")
        d = P.obj_dir(line(j, "continued"))
        inv = P.load_inventory(d)
        hist = P.read_json(d, inv, P.OBJ)["history"]
        assert [P.doc_version_of(d, inv, v) for v in hist] == [2, 4, 3]
        assert P.document_version_errors(line(j, "continued"), d, inv) == []
        assert errors(j) == []

The parent of a branch is found from `parent.url`, the URL of the parent
version (section 9.1), in the archive that holds it, whose base URL the
resolver derives from the discovery documents it finds above that URL
(section 3.1): here a copy of an archive whose storage root is `objects/`,
not `ocfl/`. The answer is kept; the storage root itself, or a URL in no
archive, has none.

    # in across: branches and accepted copies:
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

Drafts
------

A draft (section 10.1) is deposited into like a document, unsigned, at
`draft/<id>/`, listed apart in the discovery document; its head may be
rewritten. Sealing it makes a new line, signed, whose first version holds
the draft's files as document version 1 (section 10.2). The draft is then
deleted, and leaves no tombstone.

    # in across: drafts:
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

Takedowns and indexes
---------------------

A takedown deletes the object, with its witness folder, and writes a
tombstone with the fields of section 13.3, which the schema of the
discovery document accepts; the indexes keep the line's entries with the
status `removed`, and `owners/` drops its name. The key log of the owner
stays, since the archive's other lines need it, and taking it down is
refused but by law or at the keeper's request. A line taken down returns
to a library from a copy holding the version its tombstone pins, and its
tombstone is dropped (section 13.2).

    # in across: takedowns and indexes:
    def test_takedown_and_return(tmp_path):
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
        P.configure(lib)
        pin = P.digest(P.obj_dir(obj_id) / "v1" / "inventory.json")
        run("--root", str(lib), "takedown", obj_id, "--reason", "Stopped keeping it.", "--yes")
        assert json.loads((lib / "opensheaf.json").read_text())["tombstones"][0]["inventorySha512"] == pin
        assert errors(lib) == []
        run("--root", str(lib), "takedown", f"sheaf:{owner}:{owner}", "--reason", "A court order.", "--by-law",
            "--yes")
        found = findings(lib)
        assert [x for x in found if x["severity"] == "error"] == []

The return of a line: a library that took a mirror down mirrors it again
from a copy holding the version its tombstone pins.

    # in across: takedowns and indexes:
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

The indexes (section 12.5): `names/` lists every object with a genesis
record, with its genesis text; `owners/` the lines of each owner; `sha512/`
every version. A tampered index is reported by the verifier.

    # in across: takedowns and indexes:
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
