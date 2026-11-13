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
