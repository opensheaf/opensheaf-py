# Generated from literate/74-tests-paths.md by opensheaf-literate: edit the document, not this file.
"""Tests of paths, links and malformed files: the tools stay inside the archive and report
what they cannot read (no TeXmacs, no network)."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

from opensheaf import core as P
from test_core import FILES1, FILES2, archive, finish, keys_of_the_tests, put, run  # noqa: F401


def test_typeset_deletes_nothing_through_a_link(archive, tmp_path, monkeypatch):
    monkeypatch.setenv("TEXMACS_BIN", "/usr/bin/true")
    monkeypatch.setattr(P, "USER_PLUGINS", tmp_path / "plugins")
    (tmp_path / "plugins").mkdir()
    (P.TM_HOME / "system").mkdir(parents=True)
    (P.TM_HOME / "system" / "settings.scm").write_text("")
    victim = tmp_path / "Documents"
    victim.mkdir()
    (victim / "thesis.tex").write_text("years of work")
    P.SITE.mkdir(exist_ok=True)
    os.symlink(victim, P.SITE / "paper-a")
    src = tmp_path / "p.tm"
    src.write_text("<TeXmacs|2.1>\n<style|article>\n<body>x</body>\n")
    with pytest.raises(SystemExit, match="symbolic link"):
        P.typeset(src, "paper-a", tmp_path / "out.pdf", P.SITE / "paper-a")
    assert (victim / "thesis.tex").read_text() == "years of work"


def test_no_version_through_a_linked_object(archive, tmp_path):
    put("paper-a", 1, FILES1)
    finish()
    d = P.obj_dir(P.LABELS["paper-a"])
    outside = tmp_path / "outside"
    os.rename(d, outside)
    os.symlink(outside, d)
    P.configure(archive)
    with pytest.raises(SystemExit, match="symbolic link"):
        put("paper-a", 2, FILES2)
    assert not (outside / "v2").exists()


def test_no_index_file_written_through_a_link(archive, tmp_path):
    put("paper-a", 1, FILES1)
    finish()
    victim = tmp_path / "victim.txt"
    victim.write_text("precious")
    f = next((archive / "names").glob("*.json"))
    f.unlink()
    os.symlink(victim, f)
    P.configure(archive)
    with pytest.raises(SystemExit, match="symbolic link"):
        P.index(P.argparse_namespace(no_html=True))
    assert victim.read_text() == "precious"


def test_files_are_written_whole_with_the_usual_permissions(archive):
    P.write_file(archive / "x" / "y.txt", "text")
    assert (archive / "x" / "y.txt").read_text() == "text"
    umask = os.umask(0)
    os.umask(umask)
    assert (archive / "x" / "y.txt").stat().st_mode & 0o777 == 0o666 & ~umask
    assert [p.name for p in (archive / "x").iterdir()] == ["y.txt"]


def test_a_label_that_is_a_path_is_left_out(archive, tmp_path, capsys):
    put("paper-a", 1, FILES1)
    finish()
    disc = json.loads((archive / "opensheaf.json").read_text())
    for o in disc["objects"]:
        if o.get("label") == "paper-a":
            o["label"] = "../../escaped"
    (archive / "opensheaf.json").write_text(json.dumps(disc))
    P.configure(archive)
    assert "../../escaped" not in P.LABELS
    assert "not a label of a line" in capsys.readouterr().err
    P.index(P.argparse_namespace(no_html=True))
    assert not (tmp_path / "escaped").exists()
    assert not any(o.get("label") == "../../escaped"
                   for o in json.loads((archive / "opensheaf.json").read_text())["objects"])


def test_values_of_a_file_of_options_are_converted(tmp_path):
    from opensheaf import cli
    p = cli.build_parser()
    (tmp_path / "init.yaml").write_text(
        "name: Test\nbase-url: https://example.org/\ncurator: Doe, Jane\nnew-owner: true\n"
        "no-passphrase: false\nplain-current: 'no'\nyes: false\nrotation: 3\n")
    ns = cli.runs(p, p.parse_args(["init", "--from", str(tmp_path / "init.yaml")]))[0]
    assert (ns.new_owner, ns.no_passphrase, ns.plain_current, ns.yes, ns.rotation) == \
        (True, False, False, False, 3)
    for bad, what in (("i-know: maybe\n", "true or false"), ("stage: BOGUS\n", "one of"),
                      ("after: two\n", "after"), ("title: [a, b]\n", "a value")):
        (tmp_path / "dep.yaml").write_text("id: x\ntitle: T\nauthor: Doe, J\n" + bad)
        with pytest.raises(SystemExit):
            cli.runs(p, p.parse_args(["deposit", "--from", str(tmp_path / "dep.yaml")]))
    (tmp_path / "dep.yaml").write_text("id: x\ntitle: T\nauthor: Doe, J\ni-know: no\nnew: yes\nstage: AM\n")
    ns = cli.runs(p, p.parse_args(["deposit", "--from", str(tmp_path / "dep.yaml")]))[0]
    assert (ns.i_know, ns.new, ns.stage, ns.author) == (False, True, "AM", ["Doe, J"])


def rewrite(d, inv):
    data, sc = P.inventory_bytes(inv)
    for folder in (d, d / inv["head"]):
        (folder / "inventory.json").write_bytes(data)
        (folder / "inventory.json.sha512").write_bytes(sc)


@pytest.mark.parametrize("where", ["absolute", "up", "link"])
def test_content_paths_outside_the_object_are_not_read(archive, tmp_path, where):
    put("paper-a", 1, FILES1)
    finish()
    d = P.obj_dir(P.LABELS["paper-a"])
    inv = P.load_inventory(d)
    secret = tmp_path / "secret.json"
    secret.write_text('{"kind": "document", "x": "outside"}')
    dig = next(dg for dg, cps in inv["manifest"].items() if cps[0].endswith("object.json"))
    if where == "link":
        (d / inv["manifest"][dig][0]).unlink()
        os.symlink("/dev/zero", d / inv["manifest"][dig][0])
    else:
        inv["manifest"][dig] = [str(secret) if where == "absolute" else "v1/../../../../../secret.json"]
        rewrite(d, inv)
    with pytest.raises(P.UnsafePath):
        P.read_json(d, inv, P.OBJ)
    errors = P.verify_errors()
    assert any("not read" in e for e in errors)
    with pytest.raises(SystemExit, match="nothing is read"):
        run("--root", str(archive), "describe", "paper-a", "--title", "T")


@pytest.mark.parametrize("setting", [{"htmlResources": ["../../.ssh/id_ed25519"]},
                                     {"htmlResources": ["/etc/passwd"]},
                                     {"htmlPackage": "/etc/passwd"},
                                     {"htmlPackage": "../outside.ts"}])
def test_texmacs_settings_name_files_inside(archive, tmp_path, monkeypatch, setting):
    monkeypatch.setenv("TEXMACS_BIN", "/nonexistent/texmacs")
    monkeypatch.setattr(P, "TEXMACS", setting)
    (tmp_path / "outside.ts").write_text("x")
    src = tmp_path / "p.tm"
    src.write_text("<TeXmacs|2.1>\n<style|article>\n<body>x</body>\n")
    with pytest.raises(SystemExit, match="htmlResources|htmlPackage"):
        P.typeset(src, "paper-a", tmp_path / "out.pdf", P.SITE / "paper-a")


def test_paths_in_scheme_are_string_literals():
    assert P.scheme_string('a" (system "x") "\\b') == '"a\\" (system \\"x\\") \\"\\\\b"'
    assert '(system "x")' not in P.export_calls('/tmp/a" (system "x") "')


def test_init_keeps_the_profile_out_of_git(archive):
    assert {"texmacs_home/", ".staging-*"} <= set((archive / ".gitignore").read_text().splitlines())


def test_metadata_is_escaped_in_the_texmacs_index(archive):
    put("paper-a", 1, FILES1, available="not a date <b|x>", extra_obj={"external": [
        {"role": "source", "service": "arXiv", "label": "v1>><html-javascript|alert(1)><with|x|<x",
         "record": "https://arxiv.org/abs/2601.00001v1>|<x"}]})
    finish()
    cdir = P.obj_dir(P.LABELS["main"])
    m = P.read_json(cdir, P.load_inventory(cdir), "members.json")["members"][0]
    entry = P.index_entry(m)
    assert "<html-javascript" not in entry and "<b|x>" not in entry and "<with|x|<x" not in entry
    assert "v1<gtr><gtr><less>html-javascript" in entry


def fake_texmacs(tmp_path, monkeypatch, pdf=True):
    script = tmp_path / "texmacs"
    script.write_text(f"#!{sys.executable}\n" + (
        "import re, sys\n"
        "for p, kind in re.findall(r'\\(string->url \"((?:[^\"\\\\\\\\]|\\\\\\\\.)*)\"\\) \"(pdf|html)\"', sys.argv[-1]):\n"
        "    open(re.sub(r'\\\\\\\\(.)', r'\\1', p), 'wb').write(b'%PDF-1.4 typeset' if kind == 'pdf' else b'<html>new</html>')\n"
        if pdf else ""))
    script.chmod(0o755)
    monkeypatch.setenv("TEXMACS_BIN", str(script))
    monkeypatch.setattr(P, "USER_PLUGINS", tmp_path / "plugins")
    (tmp_path / "plugins").mkdir(exist_ok=True)


def test_a_failed_deposit_leaves_the_website(archive, tmp_path, monkeypatch):
    fake_texmacs(tmp_path, monkeypatch)
    cfg = json.loads((archive / "osheaf.json").read_text())
    cfg["texmacs"] = {"htmlPackage": "paper-html.ts"}
    (archive / "osheaf.json").write_text(json.dumps(cfg))
    (archive / "paper-html.ts").write_text("<TeXmacs|2.1>\n")
    src = tmp_path / "p.tm"
    src.write_text("<TeXmacs|2.1>\n<style|article>\n<body>x</body>\n")
    r = ["--root", str(archive), "deposit", "paper-t", str(src), "--title", "T", "--author", "Doe, J",
         "--rights", "cc-by-4.0"]
    site = archive / "site" / "paper-t"
    site.mkdir(parents=True)
    (site / "paper-t.html").write_text("<html>old</html>")
    (tmp_path / "scratch").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "scratch"))
    with pytest.raises(SystemExit, match="licence-file"):
        run(*r, "--new", "--licence-file", "LICENCE")
    assert (site / "paper-t.html").read_text() == "<html>old</html>"
    assert list((tmp_path / "scratch").iterdir()) == []
    run(*r, "--new")
    assert (site / "paper-t.html").read_text() == "<html>new</html>"
    fake_texmacs(tmp_path, monkeypatch, pdf=False)
    with pytest.raises(SystemExit, match="made no PDF"):
        run(*r[:-2], "--changes", "x")
    assert (site / "paper-t.html").read_text() == "<html>new</html>"


def break_inventory(d, change):
    inv = json.loads((d / "inventory.json").read_text())
    change(inv)
    (d / "inventory.json").write_text(json.dumps(inv))


@pytest.mark.parametrize("case", ["documentVersion text", "documentVersion missing", "discovery list",
                                  "deep inventory", "object.json latin-1", "object.json bom", "number 2.0",
                                  "number beyond", "discovery number", "extension float", "label newline", "hashed config",
                                  "versions list", "user text"])
def test_the_verifier_reports_what_it_cannot_read(archive, case):
    put("paper-a", 1, FILES1, extra_obj={"documentVersion": "1"} if case == "documentVersion text" else None)
    finish()
    if case == "documentVersion missing":
        put("paper-a", 2, FILES2, extra_obj={"documentVersion": None})
    if case in ("number 2.0", "number beyond", "extension float"):
        put("paper-a", 2, FILES2, extra_obj={"number 2.0": {"documentVersion": 2.0},
                                             "number beyond": {"documentVersion": 2 ** 53},
                                             "extension float": {"extensions": {
                                                 "https://example.org/ext": {"x": 0.5}}}}[case])
    d = P.obj_dir(P.LABELS["paper-a"])
    inv = P.load_inventory(d)
    expected = {"documentVersion text": "documentVersion is a positive integer",
                "documentVersion missing": "documentVersion is a positive integer",
                "discovery list": "is a JSON object", "deep inventory": "without a readable inventory",
                "object.json latin-1": "object.json: JSON is UTF-8, and this file is not",
                "object.json bom": "object.json: JSON is UTF-8 without a byte order mark, and this file starts",
                "number 2.0": "object.json: the number 2.0 is not an integer written without a fraction",
                "number beyond": "object.json: the number 9007199254740992 is beyond 2^53 - 1 (section 2)",
                "discovery number": "the number 1.5 is not an integer",
                "label newline": "'paper-a\\n' does not match",
                "extension float": "object.json: the number 0.5 is not an integer", "hashed config": "config.json is not a JSON object",
                "versions list": "no versions", "user text": "a user that is not"}[case]
    if case == "discovery list":
        (archive / "opensheaf.json").write_text("[]")
    elif case == "deep inventory":
        (d / "inventory.json").write_text("[" * 100000)
    elif case == "object.json latin-1":
        (d / P.content_path(inv, "v1", P.OBJ)).write_bytes(b"\xff\xfe{}")
    elif case == "object.json bom":
        cp = d / P.content_path(inv, "v1", P.OBJ)
        cp.write_bytes(b"\xef\xbb\xbf" + cp.read_bytes())
    elif case == "label newline":
        disc = json.loads((archive / "opensheaf.json").read_text())
        next(o for o in disc["objects"] if o.get("label") == "paper-a")["label"] = "paper-a\n"
        (archive / "opensheaf.json").write_text(json.dumps(disc))
    elif case == "discovery number":
        disc = (archive / "opensheaf.json").read_text()
        (archive / "opensheaf.json").write_text(disc.replace("{", '{"x-number": 1.5, ', 1))
    elif case == "hashed config":
        monkey = P.LAYOUT
        P.LAYOUT = P.HASHED_LAYOUT
        (P.OCFL / "extensions" / P.HASHED_LAYOUT).mkdir(parents=True)
        (P.OCFL / "extensions" / P.HASHED_LAYOUT / "config.json").write_text("[1")
    elif case == "versions list":
        break_inventory(d, lambda i: i.update(versions=["v1"]))
    elif case == "user text":
        break_inventory(d, lambda i: i["versions"]["v1"].update(user="me"))
    try:
        errors = P.verify_errors()
    finally:
        if case == "hashed config":
            P.LAYOUT = monkey
    assert any(expected in e for e in errors), errors
    assert not any("stopped on a file" in e for e in errors), [e for e in errors if "stopped" in e]


@pytest.mark.parametrize("text", ['{"format": "opensheaf-archive/0.2", "objects": [', "[]",
                                  '{"objects": 5, "owners": "x", "tombstones": 3}'],
                         ids=["cut", "list", "fields"])
def test_a_broken_discovery_document(archive, capsys, text):
    put("paper-a", 1, FILES1)
    finish()
    (archive / "opensheaf.json").write_text(text)
    r = ["--root", str(archive)]
    with pytest.raises(SystemExit) as e:
        run(*r, "verify")
    assert e.value.code == 1
    if text.startswith('{"objects": 5'):
        return
    assert "opensheaf.json" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="nothing is written"):
        run(*r, "collect")
    run(*r, "index")
    assert "without the labels" in capsys.readouterr().err
    disc = json.loads((archive / "opensheaf.json").read_text())
    assert disc["format"] == "opensheaf-archive/0.2" and len(disc["objects"]) >= 2


def test_a_broken_configuration_is_a_message(archive):
    (archive / "osheaf.json").write_text('{"owner": ')
    with pytest.raises(SystemExit, match="cannot be read"):
        P.configure(archive)
    (archive / "osheaf.json").write_text('[]')
    with pytest.raises(SystemExit, match="mapping"):
        P.configure(archive)


def test_reserved_names_in_a_document(archive, tmp_path):
    put("paper-a", 1, dict(FILES1, **{"members.json": b"{}", "keys.json": b"{}",
                                      "parent/object.json": b"{}", "forked/x": b"x", "figs/a.png": b"a"}))
    errors = finish()
    for name in ("members.json", "keys.json", "parent/object.json", "forked/x"):
        assert any(f"{name}: the name" in e for e in errors), name
    assert not any("figs/a.png" in e for e in errors)
    src, pdf = tmp_path / "main.tex", tmp_path / "paper.pdf"
    src.write_text("\\documentclass{article}")
    pdf.write_bytes(b"%PDF-1.4 x")
    r = ["--root", str(archive), "deposit", "paper-b", str(src), "--pdf", str(pdf), "--title", "T",
         "--author", "Doe, J", "--new", "--extra-source"]
    for logical in ("members.json", "parent/object.json", "genesis.json", "paper.pdf", "main.tex",
                    "a//b", "a\\b", "e\u0301.tex", "./x"):
        with pytest.raises(SystemExit, match="--extra-source"):
            run(*r, f"{src}={logical}")
    run(*r, f"{src}=sub/main.tex")


def test_an_interrupted_version_is_named(archive):
    put("paper-a", 1, FILES1)
    d = P.obj_dir(P.LABELS["paper-a"])
    (d / "v2" / "content").mkdir(parents=True)
    with pytest.raises(SystemExit, match="v2 was interrupted"):
        put("paper-a", 2, FILES2)
    assert not list(archive.glob(".staging-*"))
    (d / "v2" / "content").rmdir()
    (d / "v2").rmdir()
    put("paper-a", 2, FILES2)
    assert finish() == []


def test_options_that_would_do_nothing_are_refused(archive, tmp_path, capsys):
    with pytest.raises(SystemExit, match="--print"):
        run("--root", str(archive), "owner", "rotate", "--print", "--keys", "command")
    (tmp_path / "two.yaml").write_text(
        "- {name: A, base-url: 'https://example.org/a/', curator: 'Doe, J', new-owner: true}\n"
        "- {name: B, base-url: 'https://example.org/b/', curator: 'Doe, J', new-owner: true}\n")
    with pytest.raises(SystemExit):
        run("init", str(tmp_path / "a"), "--from", str(tmp_path / "two.yaml"))
    assert "one archive" in capsys.readouterr().err and not (tmp_path / "a").exists()
    (tmp_path / "dep.yaml").write_text(f"root: {tmp_path}\nid: x\ntitle: T\nauthor: Doe, J\n")
    with pytest.raises(SystemExit):
        run("--root", str(archive), "deposit", "--from", str(tmp_path / "dep.yaml"))
    assert "give --root on the command line" in capsys.readouterr().err
