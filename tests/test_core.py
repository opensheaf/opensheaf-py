# Generated from literate/70-tests.md by tools/tangle.py: edit the document, not this file.
"""Tests of the archive machinery on small archives built in temporary
folders (no TeXmacs, no network)."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from opensheaf import arxiv, core as P

CONFIG = {
    "archiveId": "tag:example.org,2026:test",
    "name": "Test archive",
    "baseUrl": "https://example.org/archive/",
    "mainCollection": "collection-test",
    "curator": {"name": "Doe, Jane", "givenName": "Jane", "familyName": "Doe", "affiliation": "Nowhere"},
    "depositor": {"name": "Jane Doe", "address": "https://example.org/jane"},
}


@pytest.fixture
def archive():
    root = Path(tempfile.mkdtemp())
    (root / "osheaf.json").write_text(json.dumps(CONFIG))
    P.configure(root)
    P.init_storage_root()
    yield root
    shutil.rmtree(root, ignore_errors=True)


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


FILES1 = {"main.tex": b"\\documentclass{article}one", "paper.pdf": b"%PDF one"}
FILES2 = {"main.tex": b"\\documentclass{article}two", "paper.pdf": b"%PDF two"}
FILES3 = {"main.tex": b"\\documentclass{article}three", "paper.pdf": b"%PDF three"}


def finish():
    P.collect(None)
    P.write_json(P.ROOT / "opensheaf.json", P.discovery())
    return P.verify_errors()


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


def test_gap_in_numbering_is_an_error(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 3, FILES2)
    errors = finish()
    assert any("breaks the numbering" in e for e in errors)


def test_same_number_with_other_files_is_an_error(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 1, FILES2)
    assert any("other files than document version 1" in e for e in finish())


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


def test_notices_are_kept(archive):
    notice = {"documentVersion": 1, "date": "2026-02-01", "text": "Theorem 2 is wrong as stated."}
    put("paper-a", 1, FILES1)
    put("paper-a", 1, FILES1, extra_obj={"notices": [notice]}, description_only=True)
    put("paper-a", 2, FILES2)
    d = P.OCFL / "paper-a"
    assert P.read_json(d, P.load_inventory(d), P.OBJ)["notices"] == [notice]
    assert finish() == []


def test_sources_missing(archive):
    put("paper-a", 1, {"paper.pdf": b"%PDF only"},
        extra_obj={"sourcesMissing": {"text": "arXiv keeps only the PDF of this version"}})
    d = P.OCFL / "paper-a"
    obj = P.read_json(d, P.load_inventory(d), P.OBJ)
    assert "mainSource" not in obj and obj["sourcesMissing"]
    assert finish() == []


def test_member_order():
    m = lambda i, issued, avail=None: {"id": i, "cite": {"issued": issued, "available": avail}}
    out = P.member_order([m("b", "2020-01-01"), m("a", "2020-01-01"), m("c", None), m("d", "2024-05-01")])
    assert [x["id"] for x in out] == ["d", "a", "b", "c"]


def test_clean_text():
    s = r"Comment on ``Dynamic behavior'' of H\"older drift, It\^o, \[ \R^3 \] and $\be^2<4\pi$"
    out = arxiv.clean_text(s, {"R": r"\mathbb{R}", "be": r"\beta"})
    assert out == "Comment on “Dynamic behavior” of Hölder drift, Itô, " \
                  "${\\mathbb{R}}^3$ and ${\\beta}^2<4\\pi$"
    assert arxiv.unknown_macros(r"$\FF L^p$ and $\alpha$") == ["FF"]


def test_preamble_macros():
    tex = r"\newcommand{\R}{\mathbb{R}}\def\be{\beta}\newcommand{\F}[1]{x}\begin{document}\newcommand{\Z}{z}"
    assert arxiv.preamble_macros(tex) == {"R": r"\mathbb{R}", "be": r"\beta"}


def test_tm_escape():
    assert P.tm_escape("Brzeźniak a|b <x>") == "Brze\\<#17A\\>niak a\\|b <less>x<gtr>"
    assert P.tex_text(r"H{\o}egh It\^o Pawe{\l}") == "Høegh Itô Paweł"


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


def run(*argv):
    from opensheaf import cli
    cli.main(list(argv))


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


def test_deposit_needs_pdf_or_texmacs(tmp_path):
    root = tmp_path / "archive"
    run("init", str(root), "--archive-id", "tag:example.org,2026:t", "--name", "T",
        "--base-url", "https://example.org/", "--curator", "Doe, Jane")
    src = tmp_path / "main.tex"
    src.write_text("x")
    with pytest.raises(SystemExit):
        run("--root", str(root), "deposit", "p", str(src), "--title", "T", "--author", "Doe, J")


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


def make_archive(root, name="T", curated=False):
    argv = ["init", str(root), "--archive-id", f"tag:example.org,2026:{name}", "--name", name,
            "--base-url", f"https://example.org/{name}/", "--curator", "Doe, Jane"]
    run(*(argv + (["--curated"] if curated else [])))


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
