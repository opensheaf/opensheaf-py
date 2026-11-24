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
    before = set(Path(tempfile.gettempdir()).glob("osheaf-*"))
    with pytest.raises(SystemExit, match="licence-file"):
        run(*r, "--new", "--licence-file", "LICENCE")
    assert (site / "paper-t.html").read_text() == "<html>old</html>"
    assert set(Path(tempfile.gettempdir()).glob("osheaf-*")) <= before
    run(*r, "--new")
    assert (site / "paper-t.html").read_text() == "<html>new</html>"
    fake_texmacs(tmp_path, monkeypatch, pdf=False)
    with pytest.raises(SystemExit, match="made no PDF"):
        run(*r[:-2], "--changes", "x")
    assert (site / "paper-t.html").read_text() == "<html>new</html>"
