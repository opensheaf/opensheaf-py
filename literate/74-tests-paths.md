The tests of paths, links and malformed files
=============================================

These tests check that the tools stay inside the archive and keep going on
files they did not write: symbolic links in the archive, labels, content
paths and settings that point outside it, metadata that is not what the
tools would write, files of options, and commands interrupted half way.
Most of them come from an audit of the tools, and each builds the bad
archive or file it is about. They use the archives, the keys and the
helpers of the [other tests](70-tests.md), imported from
`tests/test_core.py` (the fixtures with them, so that the keys of these
tests are as predictable and as far from the user's as theirs), and are
in `tests/test_paths.py`.

    # in tests/test_paths.py:
    <<path tests: the imports>>


    <<path tests: symbolic links in the archive>>


    <<path tests: labels of the discovery document>>


    <<path tests: files of options>>


    <<path tests: content paths>>

The imports
-----------

    # in path tests: the imports:
    """Tests of paths, links and malformed files: the tools stay inside the archive and report
    what they cannot read (no TeXmacs, no network)."""

    import json
    import os
    from pathlib import Path

    import pytest

    from opensheaf import core as P
    from test_core import FILES1, FILES2, archive, finish, keys_of_the_tests, put, run  # noqa: F401

Symbolic links
--------------

A link in the archive must not carry a write or a deletion out of it
([chapter 10](10-archive.md), `unlinked`). The folder of the HTML version
of a document, linked to a folder of the user's, is not emptied by
`typeset` (TeXmacs is replaced by `true`, which writes nothing); an object
folder linked elsewhere receives no new version; a file of an index linked
to a file outside is not overwritten.

    # in path tests: symbolic links in the archive:
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

Labels
------

A label of the discovery document that is not one is left out when the
archive is configured, with a warning; the index then writes nothing
outside the archive.

    # in path tests: labels of the discovery document:
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

Files of options
----------------

The values of a file of options are converted as the command line
converts them: `false` and `no` leave a switch off, a number is a number,
and a value that is not one of the choices of its option, or not true or
false for a switch, is refused.

    # in path tests: files of options:
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

Content paths
-------------

A content path of an inventory that is absolute, goes up with `..`, or
names a symbolic link (here to `/dev/zero`, which never ends) is not read:
the commands stop with a message, and the verifier reports it and checks
the object no further. `rewrite` writes an inventory the tools would not
write, with its checksum and its copy in the head version.

    # in path tests: content paths:
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
