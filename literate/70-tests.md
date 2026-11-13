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

Four tests check functions on their own, without an archive.

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

Across archives
---------------

The last three tests use two archives in neighbouring folders: one of
authors, and a second one that collects, mirrors or accepts their
documents. A local folder stands for the address of an archive, so no
network is needed.

### A curated collection

Archive `papers` has two documents. Archive `reading` is created with a
curated main collection and synchronised from a `collection.yaml` that
lists `two` before `one`, the second with `follow: no`. The members keep
the curator's order (`manual`, section 10.2), record the identifier of
their archive, and their pins are confirmed by `check_remote`, which reads
the other archive as a verifier would (section 14). Then `two` gets a new
version in its archive; `collection update` moves `two` to it and leaves
`one`, which does not follow, at its version.

    # in test: collections, mirrors and accepted copies:
    def test_curated_collection_across_archives(tmp_path):
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
        members = P.read_json(c / "ocfl" / "collection-main", P.load_inventory(c / "ocfl" / "collection-main"),
                              "members.json")
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

### Mirrors

Mirroring copies a whole object and is allowed only if every version may
be redistributed (section 10.4). The authors' archive has `open`, two
versions under CC BY (the second inherits the licence), and `closed`,
with all rights reserved. A curated archive `journal` cannot mirror
`closed`. Its collection lists both, `open` with `mirror: yes`: `open` is
copied with every version and listed with the journal as a mirror, while
`closed` is only referenced. When the authors' archive disappears (its
folder is moved away), the remote check finds `closed` no longer, but
still confirms `open` on the copy.

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
        from opensheaf import collections
        shutil.move(str(a), str(tmp_path / "gone"))
        errors = collections.check_remote(members)
        assert len(errors) == 1 and "closed" in errors[0]          # the mirrored member is checked on the copy

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
licence of `v2`.)

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
        run("--root", str(j), "accept", str(a), "paper", "--version", "v3", "--licence-checked",
            "--changes", "Corrected by the editors.")
        inv = P.load_inventory(d)
        assert P.read_json(d, inv, P.OBJ)["documentVersion"] == 2
        run("--root", str(j), "collect")
        run("--root", str(j), "index")
        assert P.verify_errors() == []
