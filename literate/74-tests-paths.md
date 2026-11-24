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
