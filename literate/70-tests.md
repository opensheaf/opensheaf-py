The tests
=========

The tests check the archive machinery on small archives built in temporary
folders. They need neither TeXmacs nor the network: the sources are LaTeX
files of one line, the PDFs a few bytes that start like a PDF, and the
"other archives" of the tests on collections are folders next to the
first. They run with `pytest`, on every push, on the oldest and the newest
supported Python.

There are two kinds of tests. The first kind writes object versions by
hand, without the deposit command, so as to build archives that the
command would refuse to make, and checks that verification (section 14 of
the specification) finds what is wrong with them; it tests the rules of
document versions of section 7.3. The second kind runs `osheaf` as a user
would, through the `main` function of the [command line](60-command-line.md),
and checks the files it writes: the deposits, the website, files of
options, and the work across archives (collections, mirrors, accepted
copies), explained in the chapters on the core and on collections. A few
tests in between check small functions on their own.

All the tests are in one file, `tests/test_core.py`, in this order. The
prose below follows it, except that the helper `make_archive` is explained
with `run`, before the first test that uses it.

    # in tests/test_core.py:
    <<test: the imports of the tests>>

    <<test: the configuration of a test archive>>


    <<test: a fresh archive for each test>>


    <<test: writing an object version by hand>>


    <<test: three document versions>>


    <<test: closing and verifying an archive>>


    <<test: the rules of document versions>>


    <<test: small functions>>


    <<test: running osheaf>>


    <<test: deposits through osheaf>>


    <<test: making an archive with osheaf init>>


    <<test: notices, withdrawal and completion through osheaf>>


    <<test: collections, mirrors and accepted copies>>

The tests use the core under the short name `P`, as the other modules of
the package do, and the arXiv module for its text functions.

    # in test: the imports of the tests:
    """Tests of the archive machinery on small archives built in temporary
    folders (no TeXmacs, no network)."""

    import json
    import shutil
    import tempfile
    from pathlib import Path

    import pytest

    from opensheaf import arxiv, core as P

Archives built by hand
----------------------

### A test archive

The configuration of the archives built by hand is the content of an
`osheaf.json`, with only what the core needs: the identifier of the
archive, its name and address, the identifier of its main collection, the
curator, and the depositor recorded in the inventories (section 7.1).

    # in test: the configuration of a test archive:
    CONFIG = {
        "archiveId": "tag:example.org,2026:test",
        "name": "Test archive",
        "baseUrl": "https://example.org/archive/",
        "mainCollection": "collection-test",
        "curator": {"name": "Doe, Jane", "givenName": "Jane", "familyName": "Doe", "affiliation": "Nowhere"},
        "depositor": {"name": "Jane Doe", "address": "https://example.org/jane"},
    }

The fixture `archive` gives each test that asks for it a new archive: a
temporary folder with that configuration and an empty storage root. The
core keeps the paths of the archive it works on in module variables, set
by `P.configure`; so the fixture configures the core, and every later call
of the test acts on this archive. The folder is removed after the test.

    # in test: a fresh archive for each test:
    @pytest.fixture
    def archive():
        root = Path(tempfile.mkdtemp())
        (root / "osheaf.json").write_text(json.dumps(CONFIG))
        P.configure(root)
        P.init_storage_root()
        yield root
        shutil.rmtree(root, ignore_errors=True)

### Writing object versions directly

`put` adds one object version to an object, holding document version N
with the given files. It does by hand what a deposit does, but decides
nothing: the document version number is whatever the test says, which is
how the tests make the mistakes that verification must find.

It writes an `object.json` and a `datacite.json` of the minimal form
(sections 8 and 9), a document with a LaTeX main source and a PDF
rendition. `extra_obj` adds or replaces fields of `object.json`, such as
notices; with `sourcesMissing` the version has no main source, as section
9 requires. The one thing taken from the core is `carry_forward`, which
keeps the notices of the previous head and maintains the history: with
`after`, a document version is placed after another (a version found
later); with `description_only`, the version replaces the entry of its
document version in the history instead. Finally `P.add_version` writes
the files as a new OCFL version of the object.

    # in test: writing an object version by hand:
    def put(obj_id, n, files, *, after=None, available="2026-01-01", message="test", extra_obj=None,
            description_only=False):
        """Add an object version holding document version N with FILES ({name: bytes})."""
        tmp = Path(tempfile.mkdtemp())
        d = P.OCFL / obj_id
        inv = P.load_inventory(d)
        prev = P.read_json(d, inv, P.OBJ) if inv else None
        obj = {"format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": "document",
               "archiveId": CONFIG["archiveId"], "objectId": obj_id, "documentVersion": n,
               "mainSource": "main.tex", "sourceFormat": "application/x-tex",
               "renditions": [{"path": "paper.pdf", "mediaType": "application/pdf"}], "status": "active"}
        obj.update(extra_obj or {})
        if obj.get("sourcesMissing"):
            obj.pop("mainSource")
            obj.pop("sourceFormat")
        P.carry_forward(prev, obj, inv, P.next_object_version(inv), None if description_only else after)
        dc = {"titles": [{"title": f"Paper {obj_id}"}], "creators": [{"name": "Doe, Jane"}],
              "publisher": {"name": "Test"}, "publicationYear": 2026,
              "types": {"resourceTypeGeneral": "Preprint"}, "version": str(n),
              "dates": [{"date": "2026-01-01", "dateType": "Issued"},
                        {"date": available, "dateType": "Available"}]}
        content = {}
        for name, data in files.items():
            (tmp / name).write_bytes(data)
            content[name] = tmp / name
        P.write_json(tmp / P.OBJ, obj)
        P.write_json(tmp / "datacite.json", dc)
        content[P.OBJ], content["datacite.json"] = tmp / P.OBJ, tmp / "datacite.json"
        inv = P.add_version(obj_id, content, message)
        shutil.rmtree(tmp)
        return inv

Three sets of files, each a source and a PDF, stand for three different
document versions: what matters to the rules is only whether two versions
hold the same files or not.

    # in test: three document versions:
    FILES1 = {"main.tex": b"\\documentclass{article}one", "paper.pdf": b"%PDF one"}
    FILES2 = {"main.tex": b"\\documentclass{article}two", "paper.pdf": b"%PDF two"}
    FILES3 = {"main.tex": b"\\documentclass{article}three", "paper.pdf": b"%PDF three"}

`finish` does what one does after deposits: a new version of the main
collection, the discovery document, and the checks. It returns the list of
errors found, empty for a valid archive.

    # in test: closing and verifying an archive:
    def finish():
        P.collect(None)
        P.write_json(P.ROOT / "opensheaf.json", P.discovery())
        return P.verify_errors()

### The rules of document versions

The tests of this section follow section 7.3 of the specification. The
first builds the simplest valid archive: two document versions of one
paper and one of another. The current version of `paper-a` is its object
version `v2`, and the main collection, ordered by date of issue
(`issued-desc`, section 10.2), pins each document at the object version
that holds its current version.

    # in test: the rules of document versions:
    def test_simple_archive_verifies(archive):
        put("paper-a", 1, FILES1)
        put("paper-a", 2, FILES2, available="2026-02-01")
        put("paper-b", 1, FILES3, available="2026-03-01")
        assert finish() == []
        d = P.OCFL / "paper-a"
        inv = P.load_inventory(d)
        assert P.current_version(d, inv) == "v2"
        members = P.read_json(P.OCFL / CONFIG["mainCollection"],
                              P.load_inventory(P.OCFL / CONFIG["mainCollection"]), "members.json")
        assert members["order"] == "issued-desc"
        assert {m["id"]: m["version"] for m in members["members"]} == {"paper-a": "v2", "paper-b": "v1"}

Document versions are numbered from 1 without gaps. A paper whose second
object version claims to be document version 3 breaks the numbering.

    # in test: the rules of document versions:
    def test_gap_in_numbering_is_an_error(archive):
        put("paper-a", 1, FILES1)
        put("paper-a", 3, FILES2)
        errors = finish()
        assert any("breaks the numbering" in e for e in errors)

A new number is given exactly when new files are added; conversely, two
object versions with the same document version must hold the same files.
Here the second object version reuses number 1 with other files.

    # in test: the rules of document versions:
    def test_same_number_with_other_files_is_an_error(archive):
        put("paper-a", 1, FILES1)
        put("paper-a", 1, FILES2)
        assert any("other files than document version 1" in e for e in finish())

A version found later, earlier in the work than the current one, is
deposited with `after`: it gets the next number, 3, but its place in the
history is after document version 1. The object then has a `history`,
listing the object versions in the order of the work, and the current
version, the last entry of the history, stays `v2`: dates and numbers
never decide it.

    # in test: the rules of document versions:
    def test_version_found_later_keeps_the_current_version(archive):
        put("paper-a", 1, FILES1)
        put("paper-a", 2, FILES2)
        # an earlier version found later, placed between 1 and 2
        put("paper-a", 3, FILES3, after=1)
        d = P.OCFL / "paper-a"
        inv = P.load_inventory(d)
        head = P.read_json(d, inv, P.OBJ)
        assert head["history"] == ["v1", "v3", "v2"]
        assert P.current_version(d, inv) == "v2"
        assert finish() == []

The same archive then gets a description-only version of document version
2: the same files, a new object version `v4`. The entry of document
version 2 in the history becomes `v4`, the last object version holding
it, since it carries the most complete description; so `v4` is now the
current version.

    # in test: the rules of document versions:
    def test_description_only_version_updates_the_history(archive):
        put("paper-a", 1, FILES1)
        put("paper-a", 2, FILES2)
        put("paper-a", 3, FILES3, after=1)
        # a description-only version of the current version (document version 2)
        put("paper-a", 2, FILES2, description_only=True)
        d = P.OCFL / "paper-a"
        inv = P.load_inventory(d)
        assert P.read_json(d, inv, P.OBJ)["history"] == ["v1", "v3", "v4"]
        assert P.current_version(d, inv) == "v4"
        assert finish() == []

A notice about document version 1 is added by a description-only version;
a later document version must keep it, unchanged. `carry_forward` copies
it, and the verifier checks that every notice stays.

    # in test: the rules of document versions:
    def test_notices_are_kept(archive):
        notice = {"documentVersion": 1, "date": "2026-02-01", "text": "Theorem 2 is wrong as stated."}
        put("paper-a", 1, FILES1)
        put("paper-a", 1, FILES1, extra_obj={"notices": [notice]}, description_only=True)
        put("paper-a", 2, FILES2)
        d = P.OCFL / "paper-a"
        assert P.read_json(d, P.load_inventory(d), P.OBJ)["notices"] == [notice]
        assert finish() == []

The main collection is an archive collection (section 10.2): it says so
in its `type`, and each member pins the head of its object, whatever the
head holds. Here the head of `paper-a` holds a version found later, and
is not the object version holding the current version; the member pins
the head all the same, and presentations show the current version, read
from the history of the pinned version.

    # in test: the rules of document versions:
    def test_main_collection_pins_heads(archive):
        put("paper-a", 1, FILES1)
        put("paper-a", 2, FILES2)
        put("paper-a", 3, FILES3, after=1)
        assert finish() == []
        cdir = P.OCFL / CONFIG["mainCollection"]
        members = P.read_json(cdir, P.load_inventory(cdir), "members.json")
        assert members["type"] == "archive"
        m = members["members"][0]
        d = P.OCFL / "paper-a"
        assert m["version"] == "v3" and m["inventorySha512"] == P.digest(d / "v3" / "inventory.json")
        assert m["follow"] == "latest"
        assert P.presented_version(m, d, P.load_inventory(d)) == "v2"

A selection's members pin revisions and nothing else (section 10.2), and
verification checks it (section 14). This collection, written by hand, has
a member with both a version and revisions, and a member whose revision
states a document version that its object version does not hold; a third
collection has no `type` at all.

    # in test: the rules of document versions:
    def test_verify_catches_malformed_selection_members(archive):
        from opensheaf import collections
        put("paper-a", 1, FILES1)
        put("paper-a", 2, FILES2)
        d = P.OCFL / "paper-a"
        pin1 = P.digest(d / "v1" / "inventory.json")
        base = {"kind": "document", "archive": CONFIG["archiveId"], "archiveUrl": CONFIG["baseUrl"], "id": "paper-a"}
        both = dict(base, version="v1", inventorySha512=pin1,
                    revisions=[{"documentVersion": 1, "version": "v1", "inventorySha512": pin1}])
        wrong = dict(base, revisions=[{"documentVersion": 2, "version": "v1", "inventorySha512": pin1}])
        collections.write("issue", [both, wrong], "Issue", "An issue.", "manual", None, "selection")
        errors = finish()
        assert any("has no version, inventorySha512 or follow" in e for e in errors)
        assert any("v1 does not hold document version 2" in e for e in errors)
        collections.write("untyped", [base], "Untyped", "No type.", "manual", None, "archive")
        cdir = P.OCFL / "untyped"
        mem = P.read_json(cdir, P.load_inventory(cdir), "members.json")
        mem.pop("type")
        tmp = Path(tempfile.mkdtemp())
        P.write_json(tmp / "members.json", mem)
        files = {n: P.read_logical(cdir, P.load_inventory(cdir), n) for n in ("datacite.json", P.OBJ)}
        P.add_version("untyped", dict(files, **{"members.json": tmp / "members.json"}), "no type")
        P.write_json(P.ROOT / "opensheaf.json", P.discovery())
        assert any("untyped: v2 members.json has no valid type" in e for e in P.verify_errors())

A version may have no sources, only its PDF, as for some old versions on
arXiv. Its `object.json` then says why in `sourcesMissing` and names no
main source, and the archive is valid.

    # in test: the rules of document versions:
    def test_sources_missing(archive):
        put("paper-a", 1, {"paper.pdf": b"%PDF only"},
            extra_obj={"sourcesMissing": {"text": "arXiv keeps only the PDF of this version"}})
        d = P.OCFL / "paper-a"
        obj = P.read_json(d, P.load_inventory(d), P.OBJ)
        assert "mainSource" not in obj and obj["sourcesMissing"]
        assert finish() == []

Small functions
---------------

Five tests check functions on their own, without an archive.

The order `issued-desc` of section 10.2 sorts the members by their
`Issued` date, newest first, then by their `Available` date; members with
neither date come last, and ties are broken by the object identifier, so
that the order is reproducible. Here `a` and `b` have the same date and
`c` has none.

    # in test: small functions:
    def test_member_order():
        m = lambda i, issued, avail=None: {"id": i, "cite": {"issued": issued, "available": avail}}
        out = P.member_order([m("b", "2020-01-01"), m("a", "2020-01-01"), m("c", None), m("d", "2024-05-01")])
        assert [x["id"] for x in out] == ["d", "a", "b", "c"]

Titles and abstracts imported from arXiv are LaTeX; the specification
wants plain text with mathematics between single dollars (section 8). The
arXiv chapter explains `clean_text`: quotes and accents outside
mathematics become Unicode, display mathematics becomes `$...$`, and the
authors' macros without arguments are replaced by their definitions.
`unknown_macros` lists the macros of the mathematics that MathJax would
not know.

    # in test: small functions:
    def test_clean_text():
        s = r"Comment on ``Dynamic behavior'' of H\"older drift, It\^o, \[ \R^3 \] and $\be^2<4\pi$"
        out = arxiv.clean_text(s, {"R": r"\mathbb{R}", "be": r"\beta"})
        assert out == "Comment on “Dynamic behavior” of Hölder drift, Itô, " \
                      "${\\mathbb{R}}^3$ and ${\\beta}^2<4\\pi$"
        assert arxiv.unknown_macros(r"$\FF L^p$ and $\alpha$") == ["FF"]

The definitions come from the preamble of the source, by
`preamble_macros`: only macros without arguments, and only those defined
before `\begin{document}`.

    # in test: small functions:
    def test_preamble_macros():
        tex = r"\newcommand{\R}{\mathbb{R}}\def\be{\beta}\newcommand{\F}[1]{x}\begin{document}\newcommand{\Z}{z}"
        assert arxiv.preamble_macros(tex) == {"R": r"\mathbb{R}", "be": r"\beta"}

Text written into TeXmacs documents is escaped by `tm_escape`: the
characters special to TeXmacs become their symbols, and a letter outside
the Cork encoding becomes a Unicode symbol `\<#17A\>`. `tex_text` turns
TeX accents and special letters of author names into Unicode.

    # in test: small functions:
    def test_tm_escape():
        assert P.tm_escape("Brzeźniak a|b <x>") == "Brze\\<#17A\\>niak a\\|b <less>x<gtr>"
        assert P.tex_text(r"H{\o}egh It\^o Pawe{\l}") == "Høegh Itô Paweł"

An arXiv e-print is untrusted (section 15). `unpack` extracts a small
tar archive, skipping a member whose path would leave the folder, and
refuses an archive with too many members or one that expands beyond the
limit. The limits are lowered for the test, so that the archives stay
small: five members against a limit of three, and a hundred kilobytes of
zeros, which gzip makes a few hundred bytes, against a limit of a
thousand bytes.

    # in test: small functions:
    def test_unpack_limits(tmp_path, monkeypatch):
        import gzip
        import io
        import tarfile

        def eprint(name, members):
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tf:
                for n, data in members:
                    ti = tarfile.TarInfo(n)
                    ti.size = len(data)
                    tf.addfile(ti, io.BytesIO(data))
            f = tmp_path / name
            f.write_bytes(gzip.compress(buf.getvalue()))
            return f
        ok = eprint("ok", [("main.tex", b"\\documentclass{article}"), ("../evil.tex", b"x")])
        kind, files, notes = arxiv.unpack(ok, tmp_path / "out", "2611.14296")
        assert kind == "tar" and [lp for lp, _ in files] == ["source/main.tex"]
        assert any("unsafe path ../evil.tex" in n for n in notes)
        monkeypatch.setattr(arxiv, "MAX_MEMBERS", 3)
        with pytest.raises(SystemExit, match="more than 3 files"):
            arxiv.unpack(eprint("many", [(f"f{i}.tex", b"x") for i in range(5)]), tmp_path / "out-many", "2611.14296")
        monkeypatch.setattr(arxiv, "MAX_UNPACKED", 1000)
        bomb = tmp_path / "bomb"
        bomb.write_bytes(gzip.compress(b"\0" * 100000))
        with pytest.raises(SystemExit, match="expands to more than"):
            arxiv.unpack(bomb, tmp_path / "bomb-out", "2611.14296")

Through the command line
------------------------

### Running `osheaf`

The other tests run commands as a user types them, with `run`, which calls
`main` of the command line with a list of arguments. An error of the
command is a `SystemExit`, which a test expects with `pytest.raises`.

    # in test: running osheaf:
    def run(*argv):
        from opensheaf import cli
        cli.main(list(argv))

Since every command configures the core for its archive, the checks a
test makes afterwards with `P.verify_errors()` and `P.ARCHIVE` concern the
archive of the last command run. The tests therefore end with a command
(usually `index`) on the archive they then verify.

Most tests begin by creating archives with `osheaf init`. `make_archive`
gives each a name, from which come its identifier and address, and makes
its main collection curated if asked.

    # in test: making an archive with osheaf init:
    def make_archive(root, name="T", curated=False):
        argv = ["init", str(root), "--archive-id", f"tag:example.org,2026:{name}", "--name", name,
                "--base-url", f"https://example.org/{name}/", "--curator", "Doe, Jane"]
        run(*(argv + (["--curated"] if curated else [])))

### Deposits and the website

The first test follows the life of a small archive kept without TeXmacs.
After `init`, it deposits a LaTeX source with its PDF, with an abstract
and a licence; then a second version of the same paper with only a change
note; then a paper of which only the PDF remains. After `collect` and
`index` the archive must verify. The second version must have kept the
abstract and the licence of the first, since a new version inherits them
unless they are given. The website must show the title with its
mathematics in the `citation_title` tag read by Google Scholar, both
versions with the change note, the reason why the sources of the old notes
are missing, and both papers in the index and in the sitemap.

    # in test: deposits through osheaf:
    def test_init_deposit_website(tmp_path):
        """A house-made archive without TeXmacs: init, a LaTeX deposit with its
        PDF, a new version keeping abstract and licence, a PDF-only deposit, the
        website, and the checks."""
        root = tmp_path / "archive"
        run("init", str(root), "--archive-id", "tag:example.org,2026:t", "--name", "Papers of Jane Doe",
            "--base-url", "https://example.org/papers", "--curator", "Doe, Jane")
        src, pdf = tmp_path / "main.tex", tmp_path / "paper.pdf"
        src.write_text("\\documentclass{article}\\begin{document}x\\end{document}")
        pdf.write_bytes(b"%PDF-1.4 test")
        r = ["--root", str(root)]
        run(*r, "deposit", "first-paper", str(src), "--pdf", str(pdf), "--title", "On $\\Phi^4_3$",
            "--author", "Doe, Jane", "--abstract", "We prove $x<y$.", "--rights", "cc-by-4.0",
            "--available", "2025-01-02")
        run(*r, "deposit", "first-paper", str(src), "--pdf", str(pdf), "--title", "On $\\Phi^4_3$",
            "--author", "Doe, Jane", "--changes", "Typos.", "--available", "2025-02-03")
        run(*r, "deposit", "old-notes", "--pdf", str(pdf), "--no-source", "lost",
            "--title", "Old notes", "--author", "Doe, Jane", "--available", "2019-05-01")
        run(*r, "collect")
        run(*r, "index")
        assert P.verify_errors() == []
        d = root / "ocfl" / "first-paper"
        inv = P.load_inventory(d)
        dc2 = P.read_json(d, inv, "datacite.json", "v2")
        assert dc2["rightsList"][0]["rightsIdentifier"] == "cc-by-4.0"
        assert dc2["descriptions"][0]["description"] == "We prove $x<y$."
        assert P.read_json(d, inv, P.OBJ, "v2")["changes"] == {"text": "Typos."}
        page = (root / "paper" / "first-paper" / "index.html").read_text()
        assert 'name="citation_title" content="On $\\Phi^4_3$"' in page
        assert "Version 2" in page and "Version 1" in page and "Typos." in page
        notes = (root / "paper" / "old-notes" / "index.html").read_text()
        assert "sources not available: lost" in notes
        assert "first-paper" in (root / "index.html").read_text()
        assert "paper/old-notes/" in (root / "sitemap.xml").read_text()

The archive typesets only TeXmacs sources. Any other source must come
with its PDF, and a deposit of a LaTeX source alone is refused.

    # in test: deposits through osheaf:
    def test_deposit_needs_pdf_or_texmacs(tmp_path):
        root = tmp_path / "archive"
        run("init", str(root), "--archive-id", "tag:example.org,2026:t", "--name", "T",
            "--base-url", "https://example.org/", "--curator", "Doe, Jane")
        src = tmp_path / "main.tex"
        src.write_text("x")
        with pytest.raises(SystemExit):
            run("--root", str(root), "deposit", "p", str(src), "--title", "T", "--author", "Doe, J")

The website finds the PDF of a version among the renditions of its
`object.json`, whatever its name. A document written by hand has its PDF
as `article.pdf`, as an accepted copy of a document of another archive
may; the website, written by `html.render` from the members of the main
collection, links that file from the landing page, its tag for Google
Scholar and the home page.

    # in test: deposits through osheaf:
    def test_pdf_found_from_renditions(archive):
        put("paper-a", 1, {"main.tex": b"\\documentclass{article}", "article.pdf": b"%PDF article"},
            extra_obj={"renditions": [{"path": "article.pdf", "mediaType": "application/pdf"}]})
        assert finish() == []
        from opensheaf import html
        coll = P.OCFL / CONFIG["mainCollection"]
        html.render(P.read_json(coll, P.load_inventory(coll), "members.json")["members"])
        page = (archive / "paper" / "paper-a" / "index.html").read_text()
        assert 'name="citation_pdf_url" content="https://example.org/archive/ocfl/paper-a/v1/content/article.pdf"' in page
        assert 'href="../../ocfl/paper-a/v1/content/article.pdf"' in page
        assert 'href="ocfl/paper-a/v1/content/article.pdf"' in (archive / "index.html").read_text()

### Files of options

The next test checks the files of options of the command line. The
archive is created from `archive.yaml`. The paper lives in a folder of
its own with a figure in a sub-folder, and `paper.yaml` holds two entries,
two versions of the same paper, deposited in order with one command. The
first entry uses every convenience: plural keys, an extra source and an
author written as mappings, an abstract of two paragraphs, a relation.
Its values are those a converting YAML reader would spoil: the arXiv
identifier `2611.14296`, the date `2025-01-02`, the version `1.10` in the
change note. The test checks that they arrive as written, that the paths
were read relative to the file, and that the second version inherits the
licence.

Then three more things: a title given on the command line overrides the
one of the file; a file with an unknown key (`titel`) is refused; and an
archive whose configuration is `osheaf.yaml` instead of `osheaf.json` is
found, read and verified like any other.

    # in test: deposits through osheaf:
    def test_yaml_inputs(tmp_path):
        """init and deposits from YAML: values stay text, paths are relative to
        the file, a list deposits in order, the command line overrides, unknown
        keys are refused, and osheaf.yaml works as configuration."""
        (tmp_path / "archive.yaml").write_text(
            "archive-id: tag:example.org,2026:y\n"
            "name: Papers of Jane Doe\n"
            "base-url: https://example.org/papers/\n"
            "curator: Doe, Jane\n")
        root = tmp_path / "archive"
        run("init", str(root), "--from", str(tmp_path / "archive.yaml"))
        w = tmp_path / "work"
        (w / "fig").mkdir(parents=True)
        (w / "main.tex").write_text("\\documentclass{article}")
        (w / "fig" / "a.pdf").write_bytes(b"%PDF fig")
        (w / "paper.pdf").write_bytes(b"%PDF-1.4 paper")
        (w / "paper.yaml").write_text(
            "- id: yaml-paper\n"
            "  source: main.tex\n"
            "  pdf: paper.pdf\n"
            "  extra-sources: [{file: fig/a.pdf, path: fig/a.pdf}]\n"
            "  title: On $\\Phi^4_3$\n"
            "  authors:\n"
            "    - Doe, Jane|Example University\n"
            "    - {name: 'Roe, Richard', affiliation: Elsewhere}\n"
            "  abstract: |\n"
            "    First paragraph with $x$.\n"
            "\n"
            "    Second paragraph.\n"
            "  keywords: [one, two]\n"
            "  rights: cc-by-4.0\n"
            "  available: 2025-01-02\n"
            "  related: ['IsIdenticalTo:arxiv:2611.14296']\n"
            "- id: yaml-paper\n"
            "  source: main.tex\n"
            "  pdf: paper.pdf\n"
            "  title: On $\\Phi^4_3$\n"
            "  authors: ['Doe, Jane|Example University']\n"
            "  available: 2025-02-03\n"
            "  changes: Version 1.10 corrects typos.\n")
        run("--root", str(root), "deposit", "--from", str(w / "paper.yaml"))
        d = root / "ocfl" / "yaml-paper"
        inv = P.load_inventory(d)
        dc1, dc2 = (P.read_json(d, inv, "datacite.json", v) for v in ("v1", "v2"))
        assert dc1["relatedIdentifiers"][0]["relatedIdentifier"] == "arXiv:2611.14296"
        assert {x["dateType"]: x["date"] for x in dc1["dates"]}["Available"] == "2025-01-02"
        assert dc1["creators"][1]["affiliation"] == [{"name": "Elsewhere"}]
        assert dc1["descriptions"][0]["description"] == "First paragraph with $x$.\n\nSecond paragraph."
        assert P.read_json(d, inv, P.OBJ, "v2")["changes"]["text"] == "Version 1.10 corrects typos."
        assert "fig/a.pdf" in {p for ps in inv["versions"]["v1"]["state"].values() for p in ps}
        assert dc2["rightsList"][0]["rightsIdentifier"] == "cc-by-4.0"
        # the command line overrides the file
        (w / "one.yaml").write_text("id: other\nsource: main.tex\npdf: paper.pdf\ntitle: From the file\n"
                                    "author: Doe, Jane\n")
        run("--root", str(root), "deposit", "--from", str(w / "one.yaml"), "--title", "From the command line")
        oinv = P.load_inventory(root / "ocfl" / "other")
        assert P.read_json(root / "ocfl" / "other", oinv, "datacite.json")["titles"][0]["title"] == \
            "From the command line"
        # unknown keys are refused
        (w / "bad.yaml").write_text("id: bad\ntitel: typo\n")
        with pytest.raises(SystemExit):
            run("--root", str(root), "deposit", "--from", str(w / "bad.yaml"))
        run("--root", str(root), "collect")
        run("--root", str(root), "index")
        assert P.verify_errors() == []
        # osheaf.yaml instead of osheaf.json
        cfg = json.loads((root / "osheaf.json").read_text())
        import yaml
        (root / "osheaf.json").unlink()
        (root / "osheaf.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True))
        P.configure(P.find_root(root))
        assert P.ARCHIVE["archiveId"] == "tag:example.org,2026:y"
        assert P.verify_errors() == []

A value of the file applies unless the option was given on the command
line, also for an option with a default of its own: the `type` of a
deposit (by default `Preprint`) and the `relation` of `relate` (by
default `IsIdenticalTo`) are taken from the files, while `--type` on the
command line still overrides the file. The key `date` means `available`
in a file for `deposit`, and the date of the agreement in a file for
`relicense`, which has an option of that name.

    # in test: deposits through osheaf:
    def test_yaml_options_with_defaults(tmp_path):
        root = tmp_path / "a"
        make_archive(root)
        (tmp_path / "p.tex").write_text("\\documentclass{article}")
        (tmp_path / "p.pdf").write_bytes(b"%PDF-1.4 p")
        r = ["--root", str(root)]
        (tmp_path / "p.yaml").write_text("id: p\nsource: p.tex\npdf: p.pdf\ntitle: P\nauthor: Doe, J\n"
                                         "type: JournalArticle\ndate: 2025-01-02\n")
        run(*r, "deposit", "--from", str(tmp_path / "p.yaml"))
        (tmp_path / "q.yaml").write_text("id: q\nsource: p.tex\npdf: p.pdf\ntitle: Q\nauthor: Doe, J\n"
                                         "type: JournalArticle\n")
        run(*r, "deposit", "--from", str(tmp_path / "q.yaml"), "--type", "Book")
        (tmp_path / "relate.yaml").write_text("id: p\nto: doi:10.1000/xyz\nrelation: IsVersionOf\n")
        run(*r, "relate", "--from", str(tmp_path / "relate.yaml"))
        (tmp_path / "licence.yaml").write_text("id: p\nrights: cc-by-4.0\nmethod: by e-mail\ndate: 2025-05-05\n")
        run(*r, "relicense", "--from", str(tmp_path / "licence.yaml"))
        p, q = root / "ocfl" / "p", root / "ocfl" / "q"
        pinv, qinv = P.load_inventory(p), P.load_inventory(q)
        dc1 = P.read_json(p, pinv, "datacite.json", "v1")
        assert dc1["types"]["resourceTypeGeneral"] == "JournalArticle"
        assert P.date_of(dc1, "Available") == "2025-01-02"
        assert P.read_json(q, qinv, "datacite.json")["types"]["resourceTypeGeneral"] == "Book"
        rel = P.read_json(p, pinv, "datacite.json")["relatedIdentifiers"]
        assert rel[-1]["relatedIdentifier"] == "10.1000/xyz" and rel[-1]["relationType"] == "IsVersionOf"
        assert P.read_json(p, pinv, P.OBJ)["agreement"]["date"] == "2025-05-05"
        run(*r, "collect")
        run(*r, "index")
        assert P.verify_errors() == []

### Notices, withdrawal and completion

This test goes through the later statements about a document. A paper is
deposited without its sources (object version `v1`); a notice about its
document version 1 is added, with a short text and a file in Markdown
(`v2`); the sources are found and the version is completed (`v3`); a
second document version follows (`v4`); and the paper is withdrawn
(`v5`). The completed version keeps its number 1, names its main source
and no longer has `sourcesMissing`; the head is withdrawn and still has
the notice, whose file stays in the content under `notices/`. Finally, a
withdrawn document gets no new versions (section 11.1): the last deposit
is refused.

    # in test: notices, withdrawal and completion through osheaf:
    def test_notice_withdraw_complete(tmp_path):
        root = tmp_path / "a"
        make_archive(root)
        pdf, src, note = tmp_path / "p.pdf", tmp_path / "p.tex", tmp_path / "erratum.md"
        pdf.write_bytes(b"%PDF-1.4 p")
        src.write_text("\\documentclass{article}")
        note.write_text("Theorem 2 is wrong.")
        r = ["--root", str(root)]
        run(*r, "deposit", "lost", "--pdf", str(pdf), "--no-source", "lost", "--title", "T", "--author", "Doe, J")
        run(*r, "notice", "lost", "--about", "1", "--text", "Theorem 2 is wrong.", "--file", str(note))
        run(*r, "complete", "lost", "--version", "1", "--source", str(src))
        pdf2 = tmp_path / "p2.pdf"
        pdf2.write_bytes(b"%PDF-1.4 p2")
        run(*r, "deposit", "lost", str(src), "--pdf", str(pdf2), "--title", "T", "--author", "Doe, J")
        run(*r, "withdraw", "lost", "--reason", "an error")
        run(*r, "collect")
        run(*r, "index")
        assert P.verify_errors() == []
        d = root / "ocfl" / "lost"
        inv = P.load_inventory(d)
        v3 = P.read_json(d, inv, P.OBJ, "v3")
        assert v3["documentVersion"] == 1 and v3["mainSource"] == "p.tex" and "sourcesMissing" not in v3
        head = P.read_json(d, inv, P.OBJ)
        assert head["status"] == "withdrawn" and head["notices"][0]["documentVersion"] == 1
        assert "notices/erratum.md" in {p for ps in inv["versions"][inv["head"]]["state"].values() for p in ps}
        with pytest.raises(SystemExit):        # a withdrawn document gets no new versions
            run(*r, "deposit", "lost", str(src), "--pdf", str(pdf2), "--title", "T", "--author", "Doe, J")

The completion of an *earlier* version is the case where the head stops
holding the current version without a history. A paper is deposited
without sources (`v1`), then in a second version with them (`v2`), then
withdrawn, with the reason in a file (`v3`); finally the sources of the
first version are found and added (`v4`). The head `v4` holds document
version 1, yet the current version is still document version 2, in its
last object version `v3`. The completion keeps the withdrawal of the
head: its status, its reason with the file, and the `Withdrawn` date of
`datacite.json`.

    # in test: notices, withdrawal and completion through osheaf:
    def test_complete_an_earlier_version(tmp_path):
        root = tmp_path / "a"
        make_archive(root)
        pdf, pdf2, src, why = tmp_path / "p.pdf", tmp_path / "p2.pdf", tmp_path / "p.tex", tmp_path / "why.md"
        pdf.write_bytes(b"%PDF-1.4 p")
        pdf2.write_bytes(b"%PDF-1.4 p2")
        src.write_text("\\documentclass{article}")
        why.write_text("The main result is wrong.")
        r = ["--root", str(root)]
        run(*r, "deposit", "early", "--pdf", str(pdf), "--no-source", "lost", "--title", "T", "--author", "Doe, J")
        run(*r, "deposit", "early", str(src), "--pdf", str(pdf2), "--title", "T", "--author", "Doe, J")
        run(*r, "withdraw", "early", "--reason", "wrong", "--file", str(why), "--date", "2026-03-04")
        run(*r, "complete", "early", "--version", "1", "--source", str(src))
        d = root / "ocfl" / "early"
        inv = P.load_inventory(d)
        head = P.read_json(d, inv, P.OBJ)
        assert inv["head"] == "v4" and head["documentVersion"] == 1 and "history" not in head
        assert P.current_version(d, inv) == "v3"
        assert head["status"] == "withdrawn" and head["withdrawal"] == P.read_json(d, inv, P.OBJ, "v3")["withdrawal"]
        assert P.date_of(P.read_json(d, inv, "datacite.json"), "Withdrawn") == "2026-03-04"
        assert "withdrawal/why.md" in {p for ps in inv["versions"]["v4"]["state"].values() for p in ps}
        run(*r, "collect")
        run(*r, "index")
        assert P.verify_errors() == []

Across archives
---------------

The last tests use archives in neighbouring folders: one of authors, and
others that collect, select, mirror or accept their documents. A local folder stands for the address of an archive, so no
network is needed.

### A curated collection

Archive `papers` has two documents. Archive `reading` is created with a
curated main collection and synchronised from a `collection.yaml` that
lists `two` before `one`, the second with `follow: no`. The file has no
`type`, as files written before the specification had kinds: the
collection is an archive collection, and the tool says so. The members
keep the curator's order (`manual`, section 10.2), record the identifier
of their archive, and their pins are confirmed by `check_remote`, which
reads the other archive as a verifier would (section 14). Then `two` gets
a new version in its archive; `collection update` moves `two` to it and
leaves `one`, which does not follow, at its version. Finally `two` is
withdrawn: an archive collection follows the head whatever it holds
(section 10.2), so `update` pins the withdrawal too, and the home page
shows it.

    # in test: collections, mirrors and accepted copies:
    def test_curated_collection_across_archives(tmp_path, capsys):
        a, c = tmp_path / "a", tmp_path / "c"
        make_archive(a, "papers")
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF-1.4 p")
        for i in ("one", "two"):
            run("--root", str(a), "deposit", i, "--pdf", str(pdf), "--no-source", "x", "--title", i.title(),
                "--author", "Doe, J", "--issued", "2020-01-01")
        run("--root", str(a), "collect")
        run("--root", str(a), "index")
        make_archive(c, "reading", curated=True)
        (tmp_path / "collection.yaml").write_text(
            f"title: Reading\nmembers:\n  - {{archive: {a}, id: two}}\n  - {{archive: {a}, id: one, follow: no}}\n")
        run("--root", str(c), "collection", "sync", "--from", str(tmp_path / "collection.yaml"))
        assert "no type: an archive collection" in capsys.readouterr().out
        members = P.read_json(c / "ocfl" / "collection-main", P.load_inventory(c / "ocfl" / "collection-main"),
                              "members.json")
        assert members["type"] == "archive"
        assert [m["id"] for m in members["members"]] == ["two", "one"] and members["order"] == "manual"
        assert members["members"][0]["archive"] == "tag:example.org,2026:papers"
        run("--root", str(c), "index")
        assert P.verify_errors() == []
        from opensheaf import collections
        assert collections.check_remote(members["members"]) == []
        # a new version in the member archive: update follows "two" only
        run("--root", str(a), "deposit", "two", "--pdf", str(pdf), "--no-source", "x", "--title", "Two",
            "--author", "Doe, J", "--changes", "again")
        run("--root", str(c), "collection", "update")
        new = P.read_json(c / "ocfl" / "collection-main", P.load_inventory(c / "ocfl" / "collection-main"),
                          "members.json")["members"]
        assert new[0]["version"] == "v2" and new[1]["version"] == "v1"
        assert collections.check_remote(new) == []
        # a withdrawal is a new head, which the archive collection follows
        run("--root", str(a), "withdraw", "two", "--reason", "a mistake")
        run("--root", str(c), "collection", "update")
        new = P.read_json(c / "ocfl" / "collection-main", P.load_inventory(c / "ocfl" / "collection-main"),
                          "members.json")["members"]
        assert new[0]["version"] == "v3"
        assert new[0]["inventorySha512"] == P.digest(a / "ocfl" / "two" / "v3" / "inventory.json")
        run("--root", str(c), "index")
        assert P.verify_errors() == []
        assert "Withdrawn in its archive" in (c / "index.html").read_text()

### A selection

A selection pins the revisions its curator vetted (section 10.2). Archive
`papers` has a document in three versions, each with its own title, so
that the version shown can be told. The selection, the main collection of
archive `digest`, vets versions 1 and 2, given in the wrong order: the
revisions are pinned in the order of the history, each by the object
version holding it, and the version presented is the last, version 2,
which the home page shows with the versions vetted and the pin of that
revision. Then the authors add a notice about version 2 (a
description-only version `v4`, which holds the current version 3) and a
fourth version. Neither `sync` with the same file nor `update` changes the
selection (section 10.2: tools never change revision sets on their own);
`update` reports the versions not vetted. When the curator adds version
3, it is pinned by the entry of the history, `v4`, and the earlier
revisions keep their pins.

    # in test: collections, mirrors and accepted copies:
    def test_selection_pins_revisions(tmp_path, capsys):
        from opensheaf import collections
        a, s = tmp_path / "a", tmp_path / "s"
        make_archive(a, "papers")
        pdf = tmp_path / "p.pdf"
        r = ["--root", str(a)]
        for k in (1, 2, 3):
            pdf.write_bytes(b"%PDF-1.4 version " + str(k).encode())
            run(*r, "deposit", "paper", "--pdf", str(pdf), "--no-source", "x", "--title", f"Title {k}",
                "--author", "Doe, J", "--issued", "2020-01-01")
        run(*r, "collect")
        run(*r, "index")
        make_archive(s, "digest", curated=True)
        spec = tmp_path / "digest.yaml"
        spec.write_text(f"type: selection\ntitle: Digest\nmembers:\n  - {{archive: {a}, id: paper, revisions: [2, 1]}}\n")
        run("--root", str(s), "collection", "sync", "--from", str(spec))
        cdir = s / "ocfl" / "collection-main"
        doc = P.read_json(cdir, P.load_inventory(cdir), "members.json")
        m = doc["members"][0]
        assert doc["type"] == "selection" and "version" not in m and "follow" not in m
        pins = [(x["documentVersion"], x["version"], x["inventorySha512"]) for x in m["revisions"]]
        assert pins == [(n, f"v{n}", P.digest(a / "ocfl" / "paper" / f"v{n}" / "inventory.json")) for n in (1, 2)]
        run("--root", str(s), "index")
        assert P.verify_errors() == []
        home = (s / "index.html").read_text()
        assert "Title 2" in home and "Title 3" not in home and "vetted: versions 1, 2" in home
        assert m["revisions"][-1]["inventorySha512"][:32] in home
        assert collections.check_remote(doc["members"]) == []
        run(*r, "notice", "paper", "--about", "2", "--text", "A remark.")
        pdf.write_bytes(b"%PDF-1.4 version 4")
        run(*r, "deposit", "paper", "--pdf", str(pdf), "--no-source", "x", "--title", "Title 4", "--author", "Doe, J")
        head = P.load_inventory(cdir)["head"]
        run("--root", str(s), "collection", "sync", "--from", str(spec))
        run("--root", str(s), "collection", "update")
        assert "document version(s) 3, 4 not vetted" in capsys.readouterr().out
        assert P.load_inventory(cdir)["head"] == head          # the selection is unchanged
        # vetting version 3 is the curator's act: a new version of the selection
        spec.write_text(f"type: selection\ntitle: Digest\nmembers:\n  - {{archive: {a}, id: paper, revisions: [1, 2, 3]}}\n")
        run("--root", str(s), "collection", "sync", "--from", str(spec))
        new = P.read_json(cdir, P.load_inventory(cdir), "members.json")["members"][0]["revisions"]
        assert new[:2] == m["revisions"] and (new[2]["documentVersion"], new[2]["version"]) == (3, "v4")
        with pytest.raises(SystemExit):        # a selection's member has no version
            spec.write_text(f"type: selection\nmembers:\n  - {{archive: {a}, id: paper, version: v1}}\n")
            run("--root", str(s), "collection", "sync", "--from", str(spec))

### Mirrors

Mirroring copies a whole object and is allowed only if every version may
be redistributed (section 10.4). The authors' archive has `open`, two
versions under CC BY (the second inherits the licence), and `closed`,
with all rights reserved. A curated archive `journal` cannot mirror
`closed`. Its collection lists both, `open` with `mirror: yes`: `open` is
copied with every version and listed with the journal as a mirror, while
`closed` is only referenced; the discovery document lists the copy with
`mirrorOf`, the authors' archive (section 6.1). The authors then deposit
a third version of `open`: `collection update` brings the mirror up to
date before following the new head, so that the copy still holds the
pinned version and the website reads it. When the authors' archive
disappears (its folder is moved away), the remote check finds `closed` no
longer, but still confirms `open` on the copy.

    # in test: collections, mirrors and accepted copies:
    def test_mirror(tmp_path):
        """Open objects are mirrored (every version, checked), closed ones refused;
        a collection checks a mirrored member on the copy when its archive is gone."""
        a, j = tmp_path / "a", tmp_path / "j"
        make_archive(a, "authors")
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF-1.4 p")
        r = ["--root", str(a)]
        run(*r, "deposit", "open", "--pdf", str(pdf), "--no-source", "x", "--title", "Open", "--author", "Doe, J",
            "--rights", "cc-by-4.0")
        run(*r, "deposit", "open", "--pdf", str(pdf), "--no-source", "x", "--title", "Open", "--author", "Doe, J",
            "--changes", "v2")
        run(*r, "deposit", "closed", "--pdf", str(pdf), "--no-source", "x", "--title", "Closed", "--author", "Doe, J")
        run(*r, "collect")
        run(*r, "index")
        make_archive(j, "journal", curated=True)
        with pytest.raises(SystemExit):
            run("--root", str(j), "mirror", str(a), "closed")
        (tmp_path / "issue.yaml").write_text(
            f"title: Issue\nmembers:\n  - {{archive: {a}, id: open, mirror: yes}}\n  - {{archive: {a}, id: closed}}\n")
        run("--root", str(j), "collection", "sync", "--from", str(tmp_path / "issue.yaml"))
        run("--root", str(j), "index")
        assert P.verify_errors() == []
        assert (j / "ocfl" / "open" / "v2").exists() and not (j / "ocfl" / "closed").exists()
        members = P.read_json(j / "ocfl" / "collection-main", P.load_inventory(j / "ocfl" / "collection-main"),
                              "members.json")["members"]
        assert members[0]["mirrors"] == ["https://example.org/journal/"] and "mirrors" not in members[1]
        listed = {o["id"]: o for o in json.loads((j / "opensheaf.json").read_text())["objects"]}
        assert listed["open"]["mirrorOf"] == "tag:example.org,2026:authors" and "mirrorOf" not in listed["collection-main"]
        run(*r, "deposit", "open", "--pdf", str(pdf), "--no-source", "x", "--title", "Open", "--author", "Doe, J",
            "--changes", "v3")
        run("--root", str(j), "collection", "update")
        run("--root", str(j), "index")
        assert P.verify_errors() == []
        assert (j / "ocfl" / "open" / "v3").exists()
        members = P.read_json(j / "ocfl" / "collection-main", P.load_inventory(j / "ocfl" / "collection-main"),
                              "members.json")["members"]
        assert members[0]["version"] == "v3" and members[0]["mirrors"] == ["https://example.org/journal/"]
        assert "PDF (mirrored here)" in (j / "index.html").read_text()
        from opensheaf import collections
        shutil.move(str(a), str(tmp_path / "gone"))
        errors = collections.check_remote(members)
        assert len(errors) == 1 and "closed" in errors[0]          # the mirrored member is checked on the copy

A pin is also resolved at the mirrors that the discovery document of the
member's archive lists (section 6.4), when the archive is reachable but
the object is not. Archive `library` mirrors `open` of the authors, who
list the library among their mirrors; a reading list in a third archive
references `open` without mirrors. When the object is lost from the
authors' storage root, the pin is confirmed on the library's copy.

    # in test: collections, mirrors and accepted copies:
    def test_check_remote_tries_the_archive_mirrors(tmp_path):
        from opensheaf import collections
        a, lib, c = tmp_path / "a", tmp_path / "lib", tmp_path / "c"
        make_archive(a, "authors")
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF-1.4 p")
        run("--root", str(a), "deposit", "open", "--pdf", str(pdf), "--no-source", "x", "--title", "Open",
            "--author", "Doe, J", "--rights", "cc-by-4.0")
        run("--root", str(a), "collect")
        run("--root", str(a), "index")
        make_archive(lib, "library")
        run("--root", str(lib), "mirror", str(a), "open")
        run("--root", str(lib), "index")
        disc = json.loads((a / "opensheaf.json").read_text())
        disc["mirrors"] = [collections.norm_url(str(lib))]
        (a / "opensheaf.json").write_text(json.dumps(disc))
        make_archive(c, "reading", curated=True)
        (tmp_path / "c.yaml").write_text(f"type: archive\nmembers:\n  - {{archive: {a}, id: open}}\n")
        run("--root", str(c), "collection", "sync", "--from", str(tmp_path / "c.yaml"))
        members = P.read_json(c / "ocfl" / "collection-main", P.load_inventory(c / "ocfl" / "collection-main"),
                              "members.json")["members"]
        assert "mirrors" not in members[0]
        shutil.move(str(a / "ocfl" / "open"), str(tmp_path / "lost"))
        assert collections.check_remote(members) == []
        shutil.move(str(lib), str(tmp_path / "lib-gone"))
        assert len(collections.check_remote(members)) == 1

### Accepted copies

A journal accepts one version of a paper (section 10.5). The authors
deposit the paper twice, the first time with all rights reserved and the
second under CC BY. Accepting the first is refused, since only an open
licence allows the copy; accepting the second, as version of record with
the journal's terms as agreement, makes the journal's document. When the
authors deposit a third version, the journal's copy does not change: it
has still one object version, whose PDF is byte for byte the accepted
one, and whose `object.json` records its source as `paper v2`, pinned by
the SHA-512 of that version's inventory. A correction is the journal's
decision: accepting the authors' `v3` makes the journal's document version
2. (`--licence-checked` is given there, though `v3` has inherited the open
licence of `v2`.) The journal's issue is a selection of its own document
(section 10.5), vetting the accepted version 1 and, once the editors add
it, the correction; the remote check compares the copy with its source.

    # in test: collections, mirrors and accepted copies:
    def test_accept_vetted_version(tmp_path):
        """A journal accepts one version (byte for byte, with its source and pin);
        the authors' later versions change nothing; a correction is the journal's
        new document version."""
        a, j = tmp_path / "a", tmp_path / "j"
        make_archive(a, "authors")
        pdfs = []
        for k in range(3):
            f = tmp_path / f"p{k}.pdf"
            f.write_bytes(b"%PDF-1.4 version " + str(k).encode())
            pdfs.append(f)
        src = tmp_path / "p.tex"
        src.write_text("\\documentclass{article}")
        r = ["--root", str(a)]
        run(*r, "deposit", "paper", str(src), "--pdf", str(pdfs[0]), "--title", "P", "--author", "Doe, J")
        run(*r, "deposit", "paper", str(src), "--pdf", str(pdfs[1]), "--title", "P", "--author", "Doe, J",
            "--rights", "cc-by-4.0")
        make_archive(j, "journal")
        with pytest.raises(SystemExit):                       # v1 is not openly licensed
            run("--root", str(j), "accept", str(a), "paper", "--version", "v1")
        run("--root", str(j), "accept", str(a), "paper", "--version", "v2", "--stage", "VoR",
            "--agreement", "the journal's terms")
        run(*r, "deposit", "paper", str(src), "--pdf", str(pdfs[2]), "--title", "P", "--author", "Doe, J")
        d = j / "ocfl" / "paper"
        inv = P.load_inventory(d)
        assert list(inv["versions"]) == ["v1"]                # the authors' v3 changes nothing here
        pdf_here = (d / P.content_path(inv, "v1", "paper.pdf")).read_bytes()
        assert pdf_here == pdfs[1].read_bytes()
        obj = P.read_json(d, inv, P.OBJ)
        ext = obj["external"][0]
        assert ext["role"] == "source" and ext["label"] == "paper v2"
        assert ext["files"][0]["sha512"] == P.digest(a / "ocfl" / "paper" / "v2" / "inventory.json")
        issue = tmp_path / "issue.yaml"
        issue.write_text("id: issue-1\ntype: selection\ntitle: Issue 1\nmembers:\n  - {archive: ., id: paper}\n")
        run("--root", str(j), "collection", "sync", "--from", str(issue))
        run("--root", str(j), "accept", str(a), "paper", "--version", "v3", "--licence-checked",
            "--changes", "Corrected by the editors.")
        inv = P.load_inventory(d)
        assert P.read_json(d, inv, P.OBJ)["documentVersion"] == 2
        issue.write_text("id: issue-1\ntype: selection\ntitle: Issue 1\nmembers:\n"
                         "  - {archive: ., id: paper, revisions: [1, 2]}\n")
        run("--root", str(j), "collection", "sync", "--from", str(issue))
        idir = j / "ocfl" / "issue-1"
        revs = P.read_json(idir, P.load_inventory(idir), "members.json")["members"][0]["revisions"]
        assert [(x["documentVersion"], x["version"]) for x in revs] == [(1, "v1"), (2, "v2")]
        assert revs[0]["inventorySha512"] == P.digest(d / "v1" / "inventory.json")
        run("--root", str(j), "collect")
        run("--root", str(j), "index")
        assert P.verify_errors() == []
        from opensheaf import collections
        assert collections.check_accepted_copies() == []

An accepted copy holds exactly the files of the vetted version
(section 10.5), the files of its notices included, and names the source
at the storage root that the source's discovery document states. Here
the vetted version `v2` is a description-only version with a notice in a
file, and the authors' archive keeps its storage root in `store/`
instead of `ocfl/`.

    # in test: collections, mirrors and accepted copies:
    def test_accept_keeps_notice_files_and_storage_root(tmp_path):
        from opensheaf import collections
        a, j = tmp_path / "a", tmp_path / "j"
        make_archive(a, "authors")
        pdf, src, note = tmp_path / "p.pdf", tmp_path / "p.tex", tmp_path / "erratum.md"
        pdf.write_bytes(b"%PDF-1.4 p")
        src.write_text("\\documentclass{article}")
        note.write_text("Theorem 2 is wrong.")
        r = ["--root", str(a)]
        run(*r, "deposit", "paper", str(src), "--pdf", str(pdf), "--title", "P", "--author", "Doe, J",
            "--rights", "cc-by-4.0")
        run(*r, "notice", "paper", "--about", "1", "--text", "Theorem 2 is wrong.", "--file", str(note))
        run(*r, "collect")
        run(*r, "index")
        (a / "ocfl").rename(a / "store")
        disc = json.loads((a / "opensheaf.json").read_text())
        disc["storageRoot"] = "store/"
        (a / "opensheaf.json").write_text(json.dumps(disc))
        make_archive(j, "journal")
        run("--root", str(j), "accept", str(a), "paper", "--version", "v2")
        d = j / "ocfl" / "paper"
        inv = P.load_inventory(d)
        assert "notices/erratum.md" in {p for ps in inv["versions"]["v1"]["state"].values() for p in ps}
        source = collections.norm_url(str(a)) + "store/paper/v2/"
        assert P.read_json(d, inv, P.OBJ)["external"][0]["record"] == source
        rel = P.read_json(d, inv, "datacite.json")["relatedIdentifiers"]
        assert {"relatedIdentifier": source, "relatedIdentifierType": "URL", "relationType": "IsIdenticalTo"} in rel
        run("--root", str(j), "collect")
        run("--root", str(j), "index")
        assert P.verify_errors() == []
