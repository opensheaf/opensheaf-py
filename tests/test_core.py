# Generated from literate/70-tests.md by opensheaf-literate: edit the document, not this file.
"""Tests of the archive machinery on small archives built in temporary
folders (no TeXmacs, no network)."""

import functools
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from opensheaf import arxiv, core as P, keys, names, owners, sign, wallet

@pytest.fixture(autouse=True)
def keys_of_the_tests(tmp_path, monkeypatch, request):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv(keys.KEY_STORE, "file")
    monkeypatch.delenv(keys.SIGNING_KEY, raising=False)
    monkeypatch.delenv(P.PASSPHRASE, raising=False)
    monkeypatch.delenv(wallet.WALLET, raising=False)
    keys.forget_seen()
    monkeypatch.setattr(wallet, "GH", "/nonexistent/gh")
    monkeypatch.setattr(wallet, "COPY", ["/nonexistent/pbcopy"])
    monkeypatch.setattr(wallet, "PASTE", ["/nonexistent/pbpaste"])
    monkeypatch.setattr(owners, "fetch_json", lambda url: pytest.fail(f"the network was read: {url}"))
    monkeypatch.setenv(keys.TEST_KEYS, ",".join(f"{request.node.name} {i}" for i in range(80)))


CONFIG = {"baseUrl": "https://example.org/archive/"}


@pytest.fixture
def archive(tmp_path):
    root = tmp_path / "archive"
    run("init", str(root), "--name", "Test archive", "--base-url", CONFIG["baseUrl"],
        "--curator", "Doe, Jane", "--new-owner", "--export", str(tmp_path / "keys"),
        "--no-passphrase", "--yes")
    yield root


def put(label, n, files, *, after=None, available="2026-01-01", message="test", extra_obj=None,
        description_only=False, rights=({"rights": "Creative Commons Attribution 4.0 International",
                                         "rightsIdentifier": "cc-by-4.0", "rightsIdentifierScheme": "SPDX",
                                         "rightsUri": "https://creativecommons.org/licenses/by/4.0/"},)):
    """Add an object version of LABEL holding document version N with FILES ({name: bytes})."""
    owner = P.ARCHIVE["owner"]
    if label in P.LABELS:
        obj_id = P.LABELS[label]
        d = P.obj_dir(obj_id)
        inv = P.load_inventory(d)
        prev, genesis = P.read_json(d, inv, P.OBJ), P.read_logical(d, inv, P.GENESIS).read_bytes()
    else:
        genesis, obj_id = P.seal("document", owner)
        inv = prev = None
        P.LABELS[label] = obj_id
    obj = {"format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": "document",
           "name": obj_id.split(":")[1], "owner": owner, "documentVersion": n,
           "mainSource": "main.tex", "sourceFormat": "application/x-tex",
           "renditions": [{"path": "paper.pdf", "mediaType": "application/pdf"}], "status": "active"}
    obj.update(extra_obj or {})
    if obj.get("sourcesMissing"):
        obj.pop("mainSource")
        obj.pop("sourceFormat")
    P.carry_forward(prev, obj, inv, P.next_object_version(inv), None if description_only else after)
    dc = {"titles": [{"title": f"Paper {label}"}], "creators": [{"name": "Doe, Jane", "nameType": "Personal"}],
          "publisher": {"name": "Test"}, "publicationYear": 2026,
          "types": {"resourceTypeGeneral": "Preprint"}, "version": str(n),
          "dates": [{"date": "2026-01-01", "dateType": "Issued"},
                    {"date": available, "dateType": "Available"}],
          "rightsList": list(rights)}
    if not rights:
        del dc["rightsList"]
    content = dict(files, **{"datacite.json": P.json_bytes(dc), P.GENESIS: genesis})
    content.update({p: f for p, f in P.carried_files(obj_id, inv).items() if p not in content})
    return P.add_version(obj_id, content, obj, message, acknowledged=True)


def head_of(label):
    """The folder and the inventory of the line LABEL."""
    d = P.obj_dir(P.LABELS[label])
    return d, P.load_inventory(d)


FILES1 = {"main.tex": b"\\documentclass{article}one", "paper.pdf": b"%PDF one"}
FILES2 = {"main.tex": b"\\documentclass{article}two", "paper.pdf": b"%PDF two"}
FILES3 = {"main.tex": b"\\documentclass{article}three", "paper.pdf": b"%PDF three"}


def finish():
    P.collect(None)
    P.index(P.argparse_namespace(no_html=True))
    return P.verify_errors()


def test_simple_archive_verifies(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 2, FILES2, available="2026-02-01")
    put("paper-b", 1, FILES3, available="2026-03-01")
    assert finish() == []
    d, inv = head_of("paper-a")
    assert P.current_version(d, inv) == "v2"
    cdir, cinv = head_of("main")
    members = P.read_json(cdir, cinv, "members.json")
    assert members["order"] == "issued-desc" and members["format"] == "opensheaf-collection/0.2"
    name = {lb: P.LABELS[lb].split(":")[1] for lb in ("paper-a", "paper-b")}
    assert {m["name"]: m["version"] for m in members["members"]} == {name["paper-a"]: "v2", name["paper-b"]: "v1"}
    assert all(m["owner"] == P.ARCHIVE["owner"] and m["at"] == [CONFIG["baseUrl"]] for m in members["members"])


def test_missing_rights_is_an_error(archive):
    put("paper-a", 1, FILES1, rights=())
    put("paper-b", 1, FILES3, rights=({"rights": "All rights reserved"},))
    errors = finish()
    assert [e for e in errors if "rightsList" in e] == \
        ["paper-a v1: datacite.json has no licence or rights statement in rightsList (section 4.4)"]


def test_landing_page_describes_itself(archive):
    import re
    put("paper-a", 1, FILES1)
    assert finish() == []
    obj_id = P.LABELS["paper-a"]
    page = P.ROOT / "paper" / P.name_address(obj_id) / "index.html"
    text = page.read_text()
    for r in ("cite-as", "describedby", "item", "license", "type"):
        assert f'<link rel="{r}"' in text
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)[1])
    assert ld["@type"] == "ScholarlyArticle" and ld["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert f"sheaf:{obj_id.split(':')[1]}" in ld["identifier"]
    assert any(e["encodingFormat"] == "application/pdf" for e in ld["encoding"])
    page.write_text(re.sub(r'<script type="application/ld\+json">.*?</script>', "", text, flags=re.S))
    assert any("lacks a schema.org record" in e for e in P.verify_errors())


def test_gap_in_numbering_is_an_error(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 3, FILES2)
    errors = finish()
    assert any("breaks the numbering" in e for e in errors)


def test_same_number_with_other_files_is_an_error(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 1, FILES2)
    assert any("other files than document version 1" in e for e in finish())


def test_new_number_with_the_same_files_is_an_error(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 2, FILES2)
    put("paper-a", 3, FILES1)
    put("paper-b", 1, FILES3)
    put("paper-b", 2, FILES3, extra_obj={"changes": {"text": "The same files, now refereed."}})
    put("paper-c", 1, FILES1)
    put("paper-c", 2, FILES2)
    put("paper-c", 3, FILES2)
    put("paper-d", 1, {**FILES1, "fig.png": b"a figure"})
    put("paper-d", 2, {**FILES1, "figure.png": b"a figure"})
    errors = finish()
    assert errors == ["paper-c: v3 document version 3 holds the same files and change note"
                      " as the current version 2: it is no new document version (section 4.2)"]


def test_description_only_version_keeps_the_fields_of_its_document_version(archive):
    zenodo = {"role": "deposit", "service": "Zenodo", "record": "https://zenodo.org/records/1"}
    arxiv = {"role": "source", "service": "arXiv", "record": "https://arxiv.org/abs/2601.00001v1"}
    put("paper-a", 1, FILES1)
    put("paper-a", 1, FILES1, description_only=True,
        extra_obj={"renditions": [{"path": "paper.pdf", "mediaType": "application/octet-stream"}]})
    put("paper-b", 1, FILES1, extra_obj={"external": [arxiv]})
    put("paper-b", 1, FILES1, description_only=True, extra_obj={"external": [arxiv, zenodo]})
    put("paper-c", 1, FILES1, extra_obj={"external": [arxiv]})
    put("paper-c", 1, FILES1, description_only=True)
    put("paper-d", 1, FILES1)
    put("paper-d", 1, FILES1, description_only=True,
        extra_obj={"toolchain": [{"name": "TeX Live", "version": "2026"}]})
    assert sorted(finish()) == [
        "paper-a: v2 changes renditions of document version 1, which belongs to it (section 4.2)",
        "paper-c: v2 drops or changes an external record of document version 1 (section 4.2)",
        "paper-d: v2 changes toolchain of document version 1, which belongs to it (section 4.2)"]


def test_collections_follow_the_rules_of_documents(archive):
    put("paper-a", 1, FILES1)
    put("paper-b", 1, FILES3)
    members = []
    for label in ("paper-a", "paper-b"):
        d, inv = head_of(label)
        _, nm, owner = P.LABELS[label].split(":")
        members.append({"kind": "document", "name": nm, "owner": owner, "at": [CONFIG["baseUrl"]],
                        "version": "v1", "inventorySha512": P.digest(d / "v1" / "inventory.json")})
    put_collection("list", members[:1], "catalogue")
    obj_id = P.LABELS["list"]

    def again(n, mem):
        d = P.obj_dir(obj_id)
        inv = P.load_inventory(d)
        obj = dict(P.read_json(d, inv, P.OBJ), documentVersion=n)
        dc = dict(P.read_json(d, inv, "datacite.json"), version=str(n))
        files = {"members.json": P.json_bytes({"format": "opensheaf-collection/0.2", "type": "catalogue",
                                               "members": mem}),
                 "datacite.json": P.json_bytes(dc), P.GENESIS: P.read_logical(d, inv, P.GENESIS).read_bytes()}
        P.carry_forward(P.read_json(d, inv, P.OBJ), obj, inv, P.next_object_version(inv))
        return P.add_version(obj_id, files, obj, "a collection", acknowledged=True)

    again(2, members)          # a new member list: document version 2
    again(1, members[:1])      # a description-only version of document version 1
    d, inv = head_of("list")
    assert P.current_version(d, inv) == "v2"
    assert [e for e in finish() if e.startswith("list:")] == []
    again(2, members[1:])      # another member list under the number 2
    assert "list: v4 has other files than document version 2" in finish()


def test_version_found_later_keeps_the_current_version(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 2, FILES2)
    # an earlier version found later, placed between 1 and 2
    put("paper-a", 3, FILES3, after=1)
    d, inv = head_of("paper-a")
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
    d, inv = head_of("paper-a")
    assert P.read_json(d, inv, P.OBJ)["history"] == ["v1", "v3", "v4"]
    assert P.current_version(d, inv) == "v4"
    assert finish() == []


def test_notices_are_kept(archive):
    notice = {"documentVersion": 1, "date": "2026-02-01", "text": "Theorem 2 is wrong as stated."}
    put("paper-a", 1, FILES1)
    put("paper-a", 1, FILES1, extra_obj={"notices": [notice]}, description_only=True)
    put("paper-a", 2, FILES2)
    d, inv = head_of("paper-a")
    assert P.read_json(d, inv, P.OBJ)["notices"] == [notice]
    assert finish() == []


def test_withdrawals_are_kept_until_a_new_version(archive):
    gone = {"date": "2026-03-01", "reason": {"text": "An error."}}
    put("paper-a", 1, FILES1)
    put("paper-a", 1, FILES1, extra_obj={"status": "withdrawn", "withdrawal": gone}, description_only=True)
    put("paper-a", 1, FILES1, description_only=True)
    put("paper-b", 1, FILES1, extra_obj={"status": "withdrawn", "withdrawal": gone})
    put("paper-c", 1, FILES1)
    put("paper-c", 1, FILES1, extra_obj={"status": "withdrawn", "withdrawal": gone}, description_only=True)
    put("paper-c", 2, FILES2)
    errors = finish()
    assert "paper-a: v3 drops or changes the withdrawal of v2: only a new document version reinstates a " \
           "line (section 13.1)" in errors
    assert "paper-b: v1 is a new document version and a withdrawal: a withdrawal is a description-only " \
           "version (section 13.1)" in errors
    assert not any(e.startswith("paper-c:") for e in errors)
    d, inv = head_of("paper-c")
    assert P.withdrawn_versions(d, inv) == {1: "v2"}


def test_notices_replace_earlier_ones(archive):
    first = {"documentVersion": 1, "date": "2026-02-01", "text": "Theorem 2 is wrong as stated."}
    fix = {"documentVersion": 1, "date": "2026-03-01", "text": "Theorem 2 is right.", "replaces": 1}
    put("paper-a", 1, FILES1)
    put("paper-a", 1, FILES1, extra_obj={"notices": [first]}, description_only=True)
    put("paper-a", 1, FILES1, extra_obj={"notices": [fix]}, description_only=True)
    put("paper-b", 1, FILES1)
    put("paper-b", 2, FILES2, extra_obj={"notices": [first]})
    put("paper-b", 2, FILES2, extra_obj={"notices": [dict(fix, documentVersion=2)]}, description_only=True)
    put("paper-c", 1, FILES1, extra_obj={"notices": [first, fix]})
    put("paper-c", 1, FILES1, extra_obj={"notices": [dict(fix, text="Again.")]}, description_only=True)
    put("paper-d", 1, FILES1, extra_obj={"notices": [dict(fix, replaces=1)]})
    assert sorted(finish()) == [
        "paper-b: v3 notice 2 replaces notice 1, about another document version",
        "paper-c: v2 notice 3 replaces notice 1, which is already replaced",
        "paper-d: v1 notice 1 replaces no earlier notice (1)"]


def test_owner_catalogue_pins_the_latest_signed_versions(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 2, FILES2)
    put("paper-a", 3, FILES3, after=1)
    assert finish() == []
    cdir, cinv = head_of("main")
    members = P.read_json(cdir, cinv, "members.json")
    assert members["type"] == "catalogue"
    m = members["members"][0]
    d, inv = head_of("paper-a")
    assert m["version"] == "v3" and m["inventorySha512"] == P.digest(d / "v3" / "inventory.json")
    assert m["follow"] == "latest"
    assert P.presented_version(m, d, inv) == "v2"


def test_owner_catalogue_order_is_reproducible(archive):
    put("paper-a", 1, FILES1, available="2026-01-03")
    put("paper-b", 1, FILES2, available="2026-01-05")
    put("paper-c", 1, FILES3, available="2026-01-04")
    assert finish() == []
    cdir, cinv = head_of("main")
    members = P.read_json(cdir, cinv, "members.json")["members"]
    assert [m["cite"]["available"] for m in members] == ["2026-01-05", "2026-01-04", "2026-01-03"]
    assert P.member_order([dict(m) for m in reversed(members)]) == members


def put_collection(label, members, kind):
    genesis, obj_id = P.seal("collection", P.ARCHIVE["owner"])
    P.LABELS[label] = obj_id
    obj = {"format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": "collection",
           "name": obj_id.split(":")[1], "owner": P.ARCHIVE["owner"], "documentVersion": 1, "status": "active"}
    dc = {"titles": [{"title": label}], "creators": [{"name": "Doe, Jane", "nameType": "Personal"}],
          "publisher": {"name": "Test"}, "publicationYear": 2026,
          "types": {"resourceTypeGeneral": "Collection"}, "version": "1",
          "rightsList": [dict(P.RIGHTS["cc0-1.0"])]}
    files = {"members.json": P.json_bytes({"format": "opensheaf-collection/0.2", "type": kind,
                                           "members": members}),
             "datacite.json": P.json_bytes(dc), P.GENESIS: genesis}
    return P.add_version(obj_id, files, obj, "a collection")


def test_verify_catches_malformed_selection_members(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 2, FILES2)
    d, inv = head_of("paper-a")
    pin1 = P.digest(d / "v1" / "inventory.json")
    _, nm, owner = P.LABELS["paper-a"].split(":")
    base = {"kind": "document", "name": nm, "owner": owner, "at": [CONFIG["baseUrl"]]}
    both = dict(base, version="v1", inventorySha512=pin1,
                revisions=[{"documentVersion": 1, "version": "v1", "inventorySha512": pin1}])
    wrong = dict(base, revisions=[{"documentVersion": 2, "version": "v1", "inventorySha512": pin1}])
    put_collection("issue", [both, wrong], "selection")
    errors = finish()
    assert any("has no version, inventorySha512 or follow" in e for e in errors)
    assert any("v1: does not hold document version 2" in e for e in errors)


def test_upper_case_digests_are_reported(archive):
    put("paper-a", 1, FILES1)
    put("paper-b", 1, FILES2)
    assert finish() == []
    d = P.obj_dir(P.LABELS["paper-a"])
    sc = d / "inventory.json.sha512"
    sc.write_bytes(sc.read_bytes().split()[0].upper() + b"  inventory.json\n")
    d = P.obj_dir(P.LABELS["paper-b"])
    inv = json.loads((d / "inventory.json").read_text())
    inv["manifest"] = {k.upper(): v for k, v in inv["manifest"].items()}
    for v in inv["versions"].values():
        v["state"] = {k.upper(): p for k, p in v["state"].items()}
    (d / "inventory.json").write_text(json.dumps(inv, indent=2) + "\n")
    errors = P.verify_errors()
    assert "paper-a: inventory.json.sha512 states its digest not in lower case (section 4.1)" in errors
    assert "paper-b: the inventory has digests not in lower case (section 4.1)" in errors


def test_sources_missing(archive):
    put("paper-a", 1, {"paper.pdf": b"%PDF only"},
        extra_obj={"sourcesMissing": {"text": "arXiv keeps only the PDF of this version"}})
    d, inv = head_of("paper-a")
    obj = P.read_json(d, inv, P.OBJ)
    assert "mainSource" not in obj and obj["sourcesMissing"]
    assert finish() == []


def test_licence_terms_added_by_a_description_only_version(archive):
    licence = {"path": "LICENCE.txt", "mediaType": "text/plain"}
    put("paper-a", 1, FILES1)
    put("paper-a", 1, dict(FILES1, **{"LICENCE.txt": b"The terms of the licence."}),
        extra_obj={"licence": licence}, description_only=True)
    assert finish() == []


def test_inventory_copies_record_the_versions_up_to_theirs(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 2, FILES2)
    assert finish() == []
    d, _ = head_of("paper-a")
    shutil.copyfile(d / "v1" / "inventory.json", d / "v2" / "inventory.json")
    errors = P.verify_errors()
    assert "paper-a v2: the inventory copy has the head v1" in errors
    assert "paper-a v2: the inventory copy does not record exactly the versions v1 to v2" in errors
    copy = P.load_inventory(d)
    copy["versions"]["v1"]["message"] = "another message"
    (d / "v2" / "inventory.json").write_text(json.dumps(copy))
    errors = P.verify_errors()
    assert "paper-a v2: the inventory copy disagrees with the inventory about the versions it records" in errors
    assert not any("the inventory copy has the head" in e for e in errors)


def test_no_version_on_a_head_whose_checksum_file_is_wrong(archive):
    put("paper-a", 1, FILES1)
    d, _ = head_of("paper-a")
    sc = d / "v1" / "inventory.json.sha512"
    good = sc.read_bytes()
    for bad in (None, b"not a checksum file", owners.sidecar(b"other bytes")):
        if bad is None:
            sc.unlink()
        else:
            sc.write_bytes(bad)
        with pytest.raises(SystemExit, match="the checksum file of its inventory is missing"):
            put("paper-a", 2, FILES2)
        assert head_of("paper-a")[1]["head"] == "v1" and not (d / "v2").exists()
    sc.write_bytes(good)
    put("paper-a", 2, FILES2)
    d, inv = head_of("paper-a")
    assert P.read_json(d, inv, P.OBJ)["previous"] == names.sha512_hex((d / "v1" / "inventory.json").read_bytes())


def test_pin_to_a_removed_object_is_reported_as_removed(archive):
    put("paper-a", 1, FILES1)
    put("paper-b", 1, FILES2)
    assert finish() == []
    disc = json.loads((archive / "opensheaf.json").read_text())
    obj_id = P.LABELS["paper-a"]
    entry = next(o for o in disc["objects"] if o["id"] == obj_id)
    disc["objects"].remove(entry)
    d, _ = head_of("paper-a")
    genesis = P.read_logical(d, P.load_inventory(d), P.GENESIS).read_bytes()
    disc["tombstones"] = [{"id": obj_id, "kind": "document", "name": entry["name"], "owner": entry["owner"],
                           "genesisName": names.name(genesis), "lastVersion": entry["head"],
                           "inventorySha512": entry["inventorySha512"], "date": "2026-03-01",
                           "reason": "Removed at the request of a rights holder."}]
    (archive / "opensheaf.json").write_text(json.dumps(disc))
    shutil.rmtree(d)
    P.configure(archive)
    P.write_indexes()          # the entries of paper-a stay, with the status removed
    found = P.verify_findings()
    assert [x for x in found if x["severity"] == "error"] == []
    assert any(x["severity"] == "result" and "removed: a tombstone" in x["message"] for x in found)
    removed = [e for e in P.read_index("sha512") if e["id"] == obj_id]
    assert removed and all(e["status"] == "removed" for e in removed)


def test_schema_formats_are_checked(archive, monkeypatch):
    put("paper-a", 1, FILES1)
    assert finish() == []
    disc = json.loads((archive / "opensheaf.json").read_text())
    disc["contact"] = "not a uri"
    (archive / "opensheaf.json").write_text(json.dumps(disc))
    assert "opensheaf.json: 'not a uri' is not a 'uri'" in P.verify_errors()
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    found = P.verify_findings()
    assert [x for x in found if x["severity"] == "error"] == []
    assert any("the JSON Schemas are not checked" in x["message"] for x in found)


def test_versions_are_signed_and_chained(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 2, FILES2)
    d, inv = head_of("paper-a")
    log = P.key_log(P.ARCHIVE["owner"])
    v1, v2 = (P.read_json(d, inv, P.OBJ, v) for v in ("v1", "v2"))
    assert "previous" not in v1
    assert v2["previous"] == P.digest(d / "v1" / "inventory.json")
    assert (d / "v1" / "inventory.json.sha512").read_text().endswith("  inventory.json\n")
    judgements, statuses = P.line_statuses(d, inv)
    assert statuses == [sign.SIGNED, sign.SIGNED]
    j = judgements[1][0]
    assert j.status == sign.GOOD and j.key in log.latest().keys["keys"] and j.key_log == (1, log.versions[0].digest)
    assert P.latest_signed(d, inv) == "v2"
    assert P.read_logical(d, inv, P.GENESIS, "v1").read_bytes() == P.read_logical(d, inv, P.GENESIS).read_bytes()


def test_inventories_in_the_order_of_the_key_logs(archive):
    put("paper-a", 1, FILES1)
    d, inv = head_of("paper-a")
    data = (d / "inventory.json").read_bytes()
    assert data == owners.inventory_file(owners.ordered_inventory(json.loads(data)))
    assert list(json.loads(data)) == sorted(json.loads(data))


def test_paths_of_the_layouts():
    paper = ("sheaf:zzgdggwlldcrw4bdeuvntiaobtw2kge6bc4go737pfekhfc5oz4q:"
             "56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa")
    assert P.path_of(paper, P.HASHED_LAYOUT) == (
        "946/75e/b2e/sheaf%3azzgdggwlldcrw4bdeuvntiaobtw2kge6bc4go737pfekhfc5oz4q%3a56wo6cdpjsxk7ddgnqfp2quip"
        "fghukhtmvjua-94675eb2e27de7146a912666db928784432a4c206a6b390da5a0ed7d15975580")
    assert P.path_of(paper, P.OWNER_NAME_LAYOUT) == (
        "56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa/zzgdggwlldcrw4bdeuvntiaobtw2kge6bc4go737pfekhfc5oz4q")
    assert P.path_of("sheaf:draft:notes-1", P.OWNER_NAME_LAYOUT) == "draft/notes-1"
    with pytest.raises(ValueError):
        P.path_of("paper-a", P.OWNER_NAME_LAYOUT)


def test_files_validate_against_the_schemas(archive):
    jsonschema = pytest.importorskip("jsonschema")
    put("paper-a", 1, FILES1)
    put("paper-a", 2, FILES2)
    finish()

    def check(name, data):
        schema = json.loads((P.SCHEMAS / f"opensheaf-{name}-0.2.schema.json").read_text())
        errors = list(jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
                      .iter_errors(data))
        assert not errors, (name, data, errors[0].message)
    check("archive", json.loads((archive / "opensheaf.json").read_text()))
    for obj_id, d, inv in P.objects():
        for ver in inv["versions"]:
            obj = P.read_json(d, inv, P.OBJ, ver)
            if obj["kind"] != "owner":
                check("object", obj)
            check("genesis", P.read_json(d, inv, P.GENESIS, ver))
            if obj["kind"] == "collection":
                check("collection", P.read_json(d, inv, "members.json", ver))
            if obj["kind"] == "owner":
                check("keys", P.read_json(d, inv, "keys.json", ver))
            for data in P.witnesses_of(d, ver).values():
                check("signature", json.loads(data))


def test_ocfl_validator_accepts_the_objects(archive):
    validator = pytest.importorskip("ocfl.validator")
    import ocfl
    put("paper-a", 1, FILES1)
    put("paper-a", 2, FILES2)
    finish()
    for obj_id, d, inv in P.objects():
        v = validator.Validator(log_warnings=True)
        assert v.validate_object(str(d)), v.status_str()
        codes = {line.split("]")[0].strip("[") for line in v.status_str().splitlines() if line}
        assert codes <= {"W007a", "W007b", "W013"}, v.status_str()
    assert ocfl.StorageRoot(root=str(P.OCFL)).validate(log_warnings=False)


def test_member_order():
    m = lambda i, issued, avail=None: {"name": i, "owner": "o", "cite": {"issued": issued, "available": avail}}
    out = P.member_order([m("b", "2020-01-01"), m("a", "2020-01-01"), m("c", None), m("d", "2024-05-01")])
    assert [x["name"] for x in out] == ["d", "a", "b", "c"]


def test_clean_text():
    s = r"Comment on ``Dynamic behavior'' of H\"older drift, It\^o, \[ \R^3 \] and $\be^2<4\pi$"
    out = arxiv.clean_text(s, {"R": r"\mathbb{R}", "be": r"\beta"})
    assert out == "Comment on “Dynamic behavior” of Hölder drift, Itô, " \
                  "${\\mathbb{R}}^3$ and ${\\beta}^2<4\\pi$"
    assert arxiv.unknown_macros(r"$\FF L^p$ and $\alpha$") == ["FF"]


def test_clean_text_markup():
    assert arxiv.clean_text(r"a \emph{distribution} in the Osterwalder--Schrader sense") == \
        "a distribution in the Osterwalder–Schrader sense"
    assert arxiv.clean_text(r"{\it without} the Korteweg-de~Vries equation --- or Dyson--Schwinger") == \
        "without the Korteweg-de Vries equation — or Dyson–Schwinger"
    assert arxiv.clean_text(r"$\rho$-\tmtextit{irregularity}") == r"$\rho$-irregularity"
    assert arxiv.clean_text(r"{\em x}, {\bf y}, \textit{z}, \textbf{\textsl{w}}, \tmtextbf{u}, \tmem{v}") == \
        "x, y, z, w, u, v"
    assert arxiv.clean_text(r"$a--b$ and \url{https://example.org/~user}") == \
        r"$a--b$ and \url{https://example.org/~user}"


def test_arxiv_author_names():
    assert arxiv.author_names("Andreia Chapouto, Jiawei Li, and Tadahiro Oh") == \
        ["Andreia Chapouto", "Jiawei Li", "Tadahiro Oh"]
    assert arxiv.author_names("Massimiliano Gubinelli (CEREMADE), Samy Tindel (INRIA Nancy - Grand Est / "
                              "IECN, IECL) and Iv\\'an Torrecilla (IECN (Nancy))") == \
        ["Massimiliano Gubinelli", "Samy Tindel", "Iv\\'an Torrecilla"]


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


def test_zenodo_token_order(monkeypatch):
    import sys
    import types
    from opensheaf import zenodo
    s = zenodo.SERVICES[True]
    store = {}

    def get_password(service, user):
        if store.get("fail"):
            raise RuntimeError("no backend")
        return store.get(service)
    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(get_password=get_password))
    asked = []

    def security(cmd, **kw):
        asked.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="from-security\n")
    monkeypatch.setattr(zenodo.subprocess, "run", security)
    monkeypatch.setattr(zenodo.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(zenodo.sys, "platform", "linux")
    monkeypatch.delenv("ZENODO_TOKEN", raising=False)
    assert zenodo.read_token(s) is None
    store["zenodo-token"] = "from-keyring"
    assert zenodo.read_token(s) == "from-keyring"
    monkeypatch.setenv("ZENODO_TOKEN", " from-env ")
    assert zenodo.read_token(s) == "from-env"
    monkeypatch.delenv("ZENODO_TOKEN")
    store["fail"] = True
    assert zenodo.read_token(s) is None and asked == []
    monkeypatch.setattr(zenodo.sys, "platform", "darwin")
    assert zenodo.read_token(s) == "from-security"
    assert asked[0][:4] == ["security", "find-generic-password", "-s", "zenodo-token"]
    assert zenodo.read_token(zenodo.SERVICES[False]) == "from-security"
    assert asked[1][3] == "zenodo-sandbox-token"


def run(*argv):
    from opensheaf import cli
    cli.main(list(argv))


def make_archive(root, name="T", *extra):
    run("init", str(root), "--name", name, "--base-url", f"https://example.org/{name}/",
        "--curator", "Doe, Jane", "--new-owner", "--export", str(Path(root).parent / f"{name}-keys"),
        "--no-passphrase", "--yes", *extra)


def rotation_files(folder):
    return sorted(str(p) for p in Path(folder).glob("rotation-*.txt"))


def test_init_with_a_new_owner(tmp_path):
    root = tmp_path / "a"
    make_archive(root)
    owner = json.loads((root / "osheaf.json").read_text())["owner"]
    assert names.OWNER_NAME.match(owner) and "archiveId" not in json.loads((root / "osheaf.json").read_text())
    log_dir = root / "ocfl" / owner / owner
    log = owners.load_key_log(log_dir)
    assert log.owner == owner and len(log.versions) == 1 and log.check() == ([], [])
    assert (log_dir / "v1" / "inventory.json").read_bytes() == owners.first_version(log.genesis).inventory
    assert (root / "ocfl" / P.LAYOUT_FILE).exists() and not (root / "ocfl" / "ocfl_layout.json").exists()
    rk = rotation_files(tmp_path / "T-keys")
    assert len(rk) == 3 and all(keys.read_rotation_key(Path(f)).owner == owner for f in rk)
    assert json.loads(log.versions[0].files["keys.json"])["nextThreshold"] == 2
    disc = json.loads((root / "opensheaf.json").read_text())
    assert (disc["format"], disc["specification"]) == ("opensheaf-archive/0.2", "0.2")
    assert disc["owners"] == [{"owner": owner, "catalogue": P.LABELS["main"]}] and "mainCollection" not in disc
    assert {o["kind"] for o in disc["objects"]} == {"owner", "collection"}
    assert next(o for o in disc["objects"] if o["kind"] == "collection")["label"] == "main"
    assert (tmp_path / "config" / "opensheaf" / "keys" / owner).is_dir()
    assert P.verify_errors() == []
    attrs = (root / ".gitattributes").read_text()
    assert "ocfl/**        -text -filter -ident -working-tree-encoding -export-subst -merge" in attrs
    assert "requests/" not in attrs and "key-log/" not in attrs
    mine = tmp_path / "b"
    mine.mkdir()
    (mine / ".gitattributes").write_text("* text=auto\n")
    make_archive(mine, "U")
    assert (mine / ".gitattributes").read_text() == "* text=auto\n"


def test_init_with_the_hashed_layout(tmp_path):
    root = tmp_path / "h"
    make_archive(root, "H", "--layout", "hashed")
    assert json.loads((root / "ocfl" / "ocfl_layout.json").read_text())["extension"] == P.HASHED_LAYOUT
    assert not (root / "ocfl" / P.LAYOUT_FILE).exists()
    for obj_id, d, inv in P.objects():
        assert d.relative_to(P.OCFL).as_posix() == P.path_of(obj_id, P.HASHED_LAYOUT)
    (tmp_path / "p.tex").write_text("\\documentclass{article}")
    (tmp_path / "p.pdf").write_bytes(b"%PDF-1.4 p")
    run("--root", str(root), "deposit", "p", str(tmp_path / "p.tex"), "--pdf", str(tmp_path / "p.pdf"),
        "--title", "P", "--author", "Doe, J", "--new")
    run("--root", str(root), "collect")
    assert json.loads((root / "opensheaf.json").read_text())["storageLayout"] == P.HASHED_LAYOUT
    assert P.verify_errors() == []


def test_init_with_an_existing_owner(tmp_path):
    make_archive(tmp_path / "a")
    owner = P.ARCHIVE["owner"]
    root = tmp_path / "b"
    run("init", str(root), "--name", "B", "--base-url", "https://example.org/b/", "--curator", "Doe, Jane",
        "--owner", owner, "--key-log", str(tmp_path / "a" / "ocfl" / owner / owner))
    assert P.ARCHIVE["owner"] == owner and P.verify_errors() == []
    with pytest.raises(SystemExit):
        run("init", str(tmp_path / "c"), "--name", "C", "--base-url", "https://example.org/c/",
            "--curator", "Doe, Jane", "--owner", owner)


def test_init_with_a_texmacs_index(tmp_path):
    bad = tmp_path / "bad.tm"
    bad.write_text("<TeXmacs|2.1>\n\n<\\body>\n  Nothing.\n</body>\n")
    with pytest.raises(SystemExit, match="one paragraph <paper-index>"):
        make_archive(tmp_path / "x", "X", "--index", "texmacs", "--index-template", str(bad))
    with pytest.raises(SystemExit, match="goes with --index texmacs"):
        make_archive(tmp_path / "y", "Y", "--index-template", str(bad))
    assert not (tmp_path / "x" / "osheaf.json").exists() and not (tmp_path / "x" / "ocfl").exists()
    root = tmp_path / "t"
    run("init", str(root), "--name", "Papers <of> Doe", "--base-url", "https://example.org/t/", "--curator",
        "Doe, Jane", "--new-owner", "--export", str(tmp_path / "t-keys"), "--no-passphrase", "--yes",
        "--index", "texmacs")
    cfg = json.loads((root / "osheaf.json").read_text())
    assert cfg["profiles"] == ["texmacs"] and cfg["index"] == {"template": "index-template.tm"}
    assert json.loads((root / "opensheaf.json").read_text())["profiles"] == ["texmacs"]
    template = (root / "index-template.tm").read_text(encoding="latin-1")
    assert "<chapter*|Papers <less>of<gtr> Doe>" in template and "\n  <paper-index>\n" in template
    assert not (root / "templates").exists() and not (root / "index.html").exists()
    assert (root / "index.tm").exists() and (root / "paper" / "main" / "index.html").exists()
    assert (root / "style.css").exists()
    assert [x for x in P.verify_findings() if x["severity"] != "result"] == []


def test_init_deposit(tmp_path):
    root = tmp_path / "archive"
    make_archive(root)
    src, pdf = tmp_path / "main.tex", tmp_path / "paper.pdf"
    src.write_text("\\documentclass{article}\\begin{document}x\\end{document}")
    pdf.write_bytes(b"%PDF-1.4 test")
    r = ["--root", str(root)]
    paper = [str(src), "--pdf", str(pdf), "--title", "On $\\Phi^4_3$", "--author", "Doe, Jane"]
    with pytest.raises(SystemExit, match="give --new"):
        run(*r, "deposit", "first-paper", *paper)
    run(*r, "deposit", "first-paper", *paper, "--abstract", "We prove $x<y$.", "--rights", "cc-by-4.0",
        "--available", "2025-01-02", "--new")
    with pytest.raises(SystemExit, match="label of a line already"):
        run(*r, "deposit", "first-paper", *paper, "--new")
    run(*r, "deposit", "first-paper", *paper, "--changes", "Typos.", "--available", "2025-02-03")
    run(*r, "deposit", "old-notes", "--pdf", str(pdf), "--no-source", "lost",
        "--title", "Old notes", "--author", "Doe, Jane", "--created", "2019-05-01", "--new")
    run(*r, "collect")
    run(*r, "index")
    assert P.verify_errors() == []
    d = P.obj_dir(P.resolve("first-paper"))
    inv = P.load_inventory(d)
    _, nm, owner = P.LABELS["first-paper"].split(":")
    genesis = P.read_logical(d, inv, P.GENESIS).read_bytes()
    assert nm == names.name(genesis) and json.loads(genesis)["originator"] == owner == P.ARCHIVE["owner"]
    v1, v2 = (P.read_json(d, inv, P.OBJ, v) for v in ("v1", "v2"))
    assert (v1["name"], v1["owner"]) == (nm, owner) and "previous" not in v1
    assert v2["previous"] == P.digest(d / "v1" / "inventory.json")
    assert P.line_statuses(d, inv)[1] == [sign.SIGNED, sign.SIGNED]
    dc2 = P.read_json(d, inv, "datacite.json", "v2")
    assert dc2["rightsList"][0]["rightsIdentifier"] == "cc-by-4.0"
    assert dc2["descriptions"][0]["description"] == "We prove $x<y$."
    assert v2["changes"] == {"text": "Typos."}
    disc = json.loads((root / "opensheaf.json").read_text())
    assert {o.get("label") for o in disc["objects"]} == {"main", "first-paper", "old-notes", None}
    notes = P.obj_dir(P.resolve("old-notes"))
    dcn = P.read_json(notes, P.load_inventory(notes), "datacite.json", "v1")
    assert (P.date_of(dcn, "Available"), P.date_of(dcn, "Created")) == (P.TODAY, "2019-05-01")


def test_deposit_needs_pdf_or_texmacs(tmp_path):
    root = tmp_path / "archive"
    make_archive(root)
    src = tmp_path / "main.tex"
    src.write_text("x")
    with pytest.raises(SystemExit):
        run("--root", str(root), "deposit", "p", str(src), "--title", "T", "--author", "Doe, J", "--new")


def test_licence_file_of_a_deposit(tmp_path):
    root = tmp_path / "archive"
    make_archive(root)
    src, pdf, lic = tmp_path / "main.tex", tmp_path / "p.pdf", tmp_path / "LICENSE"
    src.write_text("x")
    pdf.write_bytes(b"%PDF-1.4 p")
    lic.write_text("Licence terms of the sources.")
    base = ["--root", str(root), "deposit", "p", str(src), "--pdf", str(pdf), "--title", "T",
            "--author", "Doe, J", "--rights", "Licence of the authors", "--extra-source", str(lic), "--new"]
    with pytest.raises(SystemExit):
        run(*base, "--licence-file", "COPYING")
    run(*base, "--licence-file", "LICENSE")
    d = P.obj_dir(P.resolve("p"))
    obj = P.read_json(d, P.load_inventory(d), P.OBJ)
    assert obj["licence"] == {"path": "LICENSE", "mediaType": "text/plain"}
    run("--root", str(root), "collect")
    assert P.verify_errors() == []


def test_deposit_of_the_current_files_and_a_revert(tmp_path):
    root = tmp_path / "archive"
    make_archive(root)
    src, pdf1, pdf2 = tmp_path / "main.tex", tmp_path / "p1.pdf", tmp_path / "p2.pdf"
    src.write_text("x")
    pdf1.write_bytes(b"%PDF-1.4 one")
    pdf2.write_bytes(b"%PDF-1.4 two")
    base = ["--root", str(root), "deposit", "p", str(src), "--title", "T", "--author", "Doe, J"]
    run(*base, "--pdf", str(pdf1), "--new")
    with pytest.raises(SystemExit, match="nothing new to deposit"):
        run(*base, "--pdf", str(pdf1))
    run(*base, "--pdf", str(pdf2))
    run(*base, "--pdf", str(pdf1))
    d = P.obj_dir(P.resolve("p"))
    assert P.doc_version_of(d, P.load_inventory(d), "v3") == 3
    run("--root", str(root), "collect")
    assert P.verify_errors() == []


def test_yaml_inputs(tmp_path):
    """init and deposits from YAML: values stay text, paths are relative to
    the file, a list deposits in order, the command line overrides, unknown
    keys are refused, and osheaf.yaml works as configuration."""
    (tmp_path / "archive.yaml").write_text(
        "new-owner: yes\n"
        f"export: {tmp_path / 'keys'}\n"
        "no-passphrase: yes\n"
        "yes: yes\n"
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
        "  new: yes\n"
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
    d = P.obj_dir(P.resolve("yaml-paper"))
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
    (w / "one.yaml").write_text("id: other\nnew: yes\nsource: main.tex\npdf: paper.pdf\ntitle: From the file\n"
                                "author: Doe, Jane\n")
    run("--root", str(root), "deposit", "--from", str(w / "one.yaml"), "--title", "From the command line")
    other = P.obj_dir(P.resolve("other"))
    assert P.read_json(other, P.load_inventory(other), "datacite.json")["titles"][0]["title"] == \
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
    assert P.ARCHIVE["owner"] == cfg["owner"] and P.LABELS["yaml-paper"]
    assert P.verify_errors() == []


def test_yaml_options_with_defaults(tmp_path):
    root = tmp_path / "a"
    make_archive(root)
    (tmp_path / "p.tex").write_text("\\documentclass{article}")
    (tmp_path / "p.pdf").write_bytes(b"%PDF-1.4 p")
    r = ["--root", str(root)]
    (tmp_path / "p.yaml").write_text("id: p\nnew: yes\nsource: p.tex\npdf: p.pdf\ntitle: P\nauthor: Doe, J\n"
                                     "type: JournalArticle\ndate: 2025-01-02\n")
    run(*r, "deposit", "--from", str(tmp_path / "p.yaml"))
    (tmp_path / "q.yaml").write_text("id: q\nnew: yes\nsource: p.tex\npdf: p.pdf\ntitle: Q\nauthor: Doe, J\n"
                                     "type: JournalArticle\n")
    run(*r, "deposit", "--from", str(tmp_path / "q.yaml"), "--type", "Book")
    (tmp_path / "relate.yaml").write_text("id: p\nto: doi:10.1000/xyz\nrelation: IsVersionOf\n")
    run(*r, "relate", "--from", str(tmp_path / "relate.yaml"))
    (tmp_path / "licence.yaml").write_text("id: p\nrights: cc-by-4.0\nmethod: by e-mail\ndate: 2025-05-05\n")
    run(*r, "relicense", "--from", str(tmp_path / "licence.yaml"))
    p, q = P.obj_dir(P.resolve("p")), P.obj_dir(P.resolve("q"))
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


def test_notice_withdraw_complete(tmp_path):
    root = tmp_path / "a"
    make_archive(root)
    pdf, src, note = tmp_path / "p.pdf", tmp_path / "p.tex", tmp_path / "erratum.md"
    pdf.write_bytes(b"%PDF-1.4 p")
    src.write_text("\\documentclass{article}")
    note.write_text("Theorem 2 is wrong.")
    r = ["--root", str(root)]
    run(*r, "deposit", "lost", "--new", "--pdf", str(pdf), "--no-source", "lost", "--title", "T", "--author", "Doe, J")
    run(*r, "notice", "lost", "--about", "1", "--text", "Theorem 2 is wrong.", "--file", str(note))
    run(*r, "complete", "lost", "--version", "1", "--source", str(src))
    pdf2 = tmp_path / "p2.pdf"
    pdf2.write_bytes(b"%PDF-1.4 p2")
    run(*r, "deposit", "lost", str(src), "--pdf", str(pdf2), "--title", "T", "--author", "Doe, J")
    run(*r, "withdraw", "lost", "--reason", "an error")
    run(*r, "collect")
    run(*r, "index")
    assert P.verify_errors() == []
    d = P.obj_dir(P.resolve("lost"))
    inv = P.load_inventory(d)
    v3 = P.read_json(d, inv, P.OBJ, "v3")
    assert v3["documentVersion"] == 1 and v3["mainSource"] == "p.tex" and "sourcesMissing" not in v3
    head = P.read_json(d, inv, P.OBJ)
    assert head["status"] == "withdrawn" and head["notices"][0]["documentVersion"] == 1
    assert "notices/erratum.md" in {p for ps in inv["versions"][inv["head"]]["state"].values() for p in ps}
    with pytest.raises(SystemExit):        # the files of the current version
        run(*r, "deposit", "lost", str(src), "--pdf", str(pdf2), "--title", "T", "--author", "Doe, J")
    pdf3 = tmp_path / "p3.pdf"
    pdf3.write_bytes(b"%PDF-1.4 p3")
    run(*r, "deposit", "lost", str(src), "--pdf", str(pdf3), "--title", "T", "--author", "Doe, J",
        "--changes", "Corrected; the error is fixed.")
    inv = P.load_inventory(d)
    head = P.read_json(d, inv, P.OBJ)
    assert inv["head"] == "v6" and head["documentVersion"] == 3 and head["status"] == "active"
    assert "withdrawal" not in head
    assert P.withdrawn_versions(d, inv) == {1: "v5", 2: "v5"}
    run(*r, "collect")
    assert P.verify_errors() == []
    page = (root / "paper" / "lost" / "index.html").read_text()
    assert page.count('class="withdrawn"') == 2
    run(*r, "withdraw", "lost", "--reason", "another error")
    inv = P.load_inventory(d)
    assert P.withdrawn_versions(d, inv) == {1: "v5", 2: "v5", 3: "v7"}


def test_complete_an_earlier_version(tmp_path):
    root = tmp_path / "a"
    make_archive(root)
    pdf, pdf2, src, why = tmp_path / "p.pdf", tmp_path / "p2.pdf", tmp_path / "p.tex", tmp_path / "why.md"
    pdf.write_bytes(b"%PDF-1.4 p")
    pdf2.write_bytes(b"%PDF-1.4 p2")
    src.write_text("\\documentclass{article}")
    why.write_text("The main result is wrong.")
    r = ["--root", str(root)]
    run(*r, "deposit", "early", "--new", "--pdf", str(pdf), "--no-source", "lost", "--title", "T", "--author", "Doe, J")
    run(*r, "deposit", "early", str(src), "--pdf", str(pdf2), "--title", "T", "--author", "Doe, J")
    run(*r, "withdraw", "early", "--reason", "wrong", "--file", str(why), "--date", "2026-03-04")
    run(*r, "complete", "early", "--version", "1", "--source", str(src))
    d = P.obj_dir(P.resolve("early"))
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


def test_describe(tmp_path):
    root = tmp_path / "a"
    make_archive(root)
    src, pdf = tmp_path / "p.tex", tmp_path / "p.pdf"
    src.write_text("\\documentclass{article}")
    pdf.write_bytes(b"%PDF-1.4 p")
    r = ["--root", str(root)]
    run(*r, "deposit", "p", str(src), "--pdf", str(pdf), "--title", "Tpyo", "--author", "Duch, P.",
        "--abstract", "A \\emphdistribution.", "--keyword", "old", "--rights", "cc-by-4.0", "--new")
    d = P.obj_dir(P.resolve("p"))
    inv = P.load_inventory(d)
    dc = P.read_json(d, inv, "datacite.json")
    dc["subjects"].append({"subject": "math.PR", "subjectScheme": "arXiv"})
    P.write_json(tmp_path / "dc.json", dc)
    files = {lp: d / inv["manifest"][dg][0] for dg, lps in inv["versions"]["v1"]["state"].items() for lp in lps}
    files["datacite.json"] = tmp_path / "dc.json"
    obj = files.pop(P.OBJ) and P.read_json(d, inv, P.OBJ)
    P.add_version(P.resolve("p"), files, obj, "a subject with a scheme")
    run(*r, "describe", "p", "--title", "Typo", "--author", "Duch, Paweł|IMPAN", "--keyword", "new")
    (tmp_path / "abstract.txt").write_text("A distribution.\n")
    (tmp_path / "describe.yaml").write_text("id: p\nabstract-file: abstract.txt\n")
    run(*r, "describe", "--from", str(tmp_path / "describe.yaml"))
    with pytest.raises(SystemExit):
        run(*r, "describe", "p", "--title", "Typo")
    inv = P.load_inventory(d)
    dc = P.read_json(d, inv, "datacite.json")
    assert inv["head"] == "v4" and P.read_json(d, inv, P.OBJ)["documentVersion"] == 1
    assert dc["titles"][0]["title"] == "Typo"
    assert dc["creators"] == [{"name": "Duch, Paweł", "nameType": "Personal", "familyName": "Duch",
                               "givenName": "Paweł", "affiliation": [{"name": "IMPAN"}]}]
    assert dc["descriptions"][0]["description"] == "A distribution."
    assert dc["subjects"] == [{"subject": "new"}, {"subject": "math.PR", "subjectScheme": "arXiv"}]
    assert dc["rightsList"][0]["rightsIdentifier"] == "cc-by-4.0"
    assert inv["versions"]["v3"]["message"] == \
        "Description corrected: title, keywords, authors (description-only version)"
    assert inv["versions"]["v4"]["message"] == "Description corrected: abstract (description-only version)"
    run(*r, "collect")
    run(*r, "index")
    assert P.verify_errors() == []


def new_device_key(root):
    P.configure(root)
    return P.key_new(P.argparse_namespace(owner=None)).did


def test_rotate_expose_end(tmp_path, capsys):
    root = tmp_path / "a"
    make_archive(root)
    r = ["--root", str(root)]
    owner = P.ARCHIVE["owner"]
    first = P.key_log(owner).latest().keys["keys"][0]
    (tmp_path / "p.tex").write_text("\\documentclass{article}")
    pdf = tmp_path / "p.pdf"
    paper = ["p", str(tmp_path / "p.tex"), "--pdf", str(pdf), "--title", "P", "--author", "Doe, J"]
    pdf.write_bytes(b"%PDF-1.4 one")
    run(*r, "deposit", *paper, "--new")
    laptop = new_device_key(root)
    rk1 = rotation_files(tmp_path / "T-keys")
    run(*r, "owner", "rotate", "--add", laptop, "--retire", first, "--rotation-key", rk1[0],
        "--rotation-key", rk1[2], "--export", str(tmp_path / "keys-2"), "--no-passphrase", "--yes")
    log = P.key_log(owner)
    assert len(log.versions) == 2 and log.latest().keys["keys"] == [laptop] and log.check() == ([], [])
    pdf.write_bytes(b"%PDF-1.4 two")
    run(*r, "deposit", *paper)
    d = P.obj_dir(P.resolve("p"))
    j = P.line_statuses(d, P.load_inventory(d))[0][1][0]
    assert j.status == sign.GOOD and j.key == laptop and j.key_log[0] == 2
    assert P.verify_errors() == []
    third = new_device_key(root)
    rk2 = rotation_files(tmp_path / "keys-2")
    run(*r, "owner", "expose", laptop, "--add", third, "--rotation-key", rk2[1], "--rotation-key", rk2[2],
        "--export", str(tmp_path / "keys-3"), "--no-passphrase", "--yes")
    assert P.key_log(owner).exposed_keys() == {laptop}
    assert P.line_statuses(d, P.load_inventory(d))[1] == [sign.SIGNED, sign.CONTESTED]
    found = P.verify_findings()
    assert not [x for x in found if x["severity"] == "error"]
    assert any(x["severity"] == "result" and x["message"] == f"exposed key {laptop}" for x in found)
    assert any(x["severity"] == "result" and x["message"] == "contested (section 7.3)" for x in found)
    pdf.write_bytes(b"%PDF-1.4 three")
    with pytest.raises(SystemExit, match="v2: contested"):
        run(*r, "deposit", *paper)
    run(*r, "deposit", *paper, "--i-know")
    inv = P.load_inventory(d)
    assert P.line_statuses(d, inv)[1] == [sign.SIGNED, sign.SIGNED, sign.SIGNED]
    assert P.line_statuses(d, inv)[0][2][0].key == third
    run(*r, "collect")
    assert P.verify_errors() == []
    successor = names.name(names.genesis_record("owner", keys=[third], threshold=1,
                                                next_digests=[names.key_digest(laptop)], next_threshold=1))
    rk3 = rotation_files(tmp_path / "keys-3")
    run(*r, "owner", "end", "--successor", successor, "--rotation-key", rk3[0], "--rotation-key", rk3[1])
    log = P.key_log(owner)
    assert log.ended and log.successor == successor
    with pytest.raises(SystemExit, match="has ended"):
        run(*r, "deposit", *paper, "--changes", "A version after the end.")
    capsys.readouterr()
    run(*r, "owner", "show")
    assert "ended" in capsys.readouterr().out
    assert P.verify_errors() == []


def test_rotation_keys_are_checked(tmp_path, monkeypatch):
    root = tmp_path / "a"
    make_archive(root)
    r = ["--root", str(root)]
    rk1 = rotation_files(tmp_path / "T-keys")
    with pytest.raises(SystemExit, match="is not a rotation key|needs 2 rotation keys"):
        run(*r, "owner", "rotate", "--rotation-key", rk1[0], "--export", str(tmp_path / "k2"),
            "--no-passphrase", "--yes")
    with pytest.raises(SystemExit, match="inside the archive"):
        run(*r, "owner", "rotate", "--rotation-key", rk1[0], "--rotation-key", rk1[1],
            "--export", str(root / "keys"), "--no-passphrase", "--yes")
    assert not (root / "keys").exists() and len(P.key_log(P.ARCHIVE["owner"]).versions) == 1
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    fast = dict(opslimit=keys.pwhash.argon2id.OPSLIMIT_MIN, memlimit=keys.pwhash.argon2id.MEMLIMIT_MIN)
    monkeypatch.setattr(keys, "export_rotation_keys", functools.partial(keys.export_rotation_keys, **fast))
    run(*r, "owner", "rotate", "--rotation-key", rk1[0], "--rotation-key", rk1[1],
        "--export", str(tmp_path / "k2"), "--yes")
    assert "encryption argon2id-secretbox" in Path(rotation_files(tmp_path / "k2")[0]).read_text()
    with pytest.raises(SystemExit, match="not a rotation key"):
        run(*r, "owner", "end", "--rotation-key", rk1[0], "--rotation-key", rk1[2])
    rk2 = rotation_files(tmp_path / "k2")
    monkeypatch.setenv(P.PASSPHRASE, "wrong horse")
    with pytest.raises(SystemExit, match="wrong passphrase"):
        run(*r, "owner", "end", "--rotation-key", rk2[0], "--rotation-key", rk2[1])
    monkeypatch.setenv(P.PASSPHRASE, "correct horse")
    run(*r, "owner", "end", "--rotation-key", rk2[0], "--rotation-key", rk2[1])
    assert P.key_log(P.ARCHIVE["owner"]).ended


def test_key_new_takes_an_owner_name_only(tmp_path):
    root = tmp_path / "a"
    make_archive(root)
    r = ["--root", str(root)]
    for bad in ("../..", "../../escaped", "a b", "-w", P.ARCHIVE["owner"].upper()):
        with pytest.raises(SystemExit, match="an owner name"):
            run(*r, "key", "new", f"--owner={bad}")
        with pytest.raises(keys.KeyStoreError, match="not an owner name"):
            keys.store_current_key(bad, keys.Key(bytes(32)))
        with pytest.raises(keys.KeyStoreError, match="not an owner name"):
            keys.current_keys(bad, [keys.Key(bytes(32)).did])
    assert not (tmp_path / "escaped").exists()
    assert sorted(p.name for p in (tmp_path / "config" / "opensheaf" / "keys").iterdir()) == [P.ARCHIVE["owner"]]


def test_single_rotation_key_and_confirmation(tmp_path, monkeypatch, capsys):
    root = tmp_path / "s"
    make_archive(root, "S", "--single-rotation-key")
    assert owners.SINGLE_ROTATION_RISK in capsys.readouterr().err
    log = P.key_log(P.ARCHIVE["owner"])
    assert json.loads(log.versions[0].files["keys.json"])["nextThreshold"] == 1
    monkeypatch.setattr("builtins.input", lambda prompt: "XXXX")
    with pytest.raises(SystemExit, match="Not confirmed"):
        run("--root", str(root), "owner", "rotate", "--rotation-key", rotation_files(tmp_path / "S-keys")[0],
            "--export", str(tmp_path / "s2"), "--no-passphrase")
    assert len(P.key_log(P.ARCHIVE["owner"]).versions) == 1


def test_wrong_previous_is_an_error(archive, monkeypatch):
    put("paper-a", 1, FILES1)
    real = P.previous_digest
    monkeypatch.setattr(P, "previous_digest", lambda obj_id, d, head: "0" * 128)
    put("paper-a", 2, FILES2)
    monkeypatch.setattr(P, "previous_digest", real)
    assert "paper-a v2: previous is not the digest of the inventory of v1 (section 4.3)" in finish()


def test_unsigned_and_invalid_versions(archive):
    put("paper-a", 1, FILES1)
    put("paper-a", 2, FILES2)
    put("paper-b", 1, FILES3)
    assert finish() == []
    d, _ = head_of("paper-a")
    for f in (d / sign.WITNESSES / "v2").iterdir():
        f.unlink()
    found = P.verify_findings()
    warnings = [f"{x['place']}: {x['message']}" for x in found if x["severity"] == "warning"]
    assert "paper-a v2: not a version of the line: unsigned (sections 7.3 and 7.5)" in warnings
    assert any("v2: not a version: a collection pins only signed versions" in e for e in P.verify_errors())
    b, _ = head_of("paper-b")
    sig = next((b / sign.WITNESSES / "v1").iterdir())
    data = json.loads(sig.read_text())
    data["signature"] = ("A" if data["signature"][0] != "A" else "B") + data["signature"][1:]
    sig.write_text(json.dumps(data, indent=2) + "\n")
    found = P.verify_findings()
    warnings = [f"{x['place']}: {x['message']}" for x in found if x["severity"] == "warning"]
    assert f"paper-b v1: {sig.name}: invalid: the signature does not verify" in warnings
    assert "paper-b v1: not a version of the line: invalid (sections 7.3 and 7.5)" in warnings


def test_stale_discovery_document(archive):
    put("paper-a", 1, FILES1)
    assert finish() == []
    put("paper-a", 2, FILES2)
    assert any(e.startswith("opensheaf.json: the entry of paper-a is stale: head v1 instead of v2")
               for e in P.verify_errors())
    P.write_discovery()
    assert P.verify_errors() == []


def test_keys_in_the_archive_are_reported(archive, tmp_path):
    shutil.copy(rotation_files(tmp_path / "keys")[0], archive / "backup.txt")
    found = P.verify_findings()
    assert {"severity": "warning", "place": "backup.txt",
            "message": "looks like a private key: keys are never kept in an archive (section 15.4)"} in found
    assert P.verify_errors() == []


def test_specification_0_1_is_rebuilt(tmp_path, capsys):
    old = tmp_path / "old"
    old.mkdir()
    (old / "osheaf.json").write_text(json.dumps({"archiveId": "tag:example.org,2026:old", "name": "Old"}))
    (old / "opensheaf.json").write_text(json.dumps({"format": "opensheaf-archive/0.1", "specification": "0.1"}))
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        run("--root", str(old), "verify", "--json")
    assert e.value.code == 1
    assert json.loads(capsys.readouterr().out) == [
        {"severity": "error", "place": "archive", "message": "specification 0.1: rebuild (section 16.1)"}]
    with pytest.raises(SystemExit, match="rebuild it"):
        run("--root", str(old), "collect")


def test_verify_json_is_json_alone(archive, capsys):
    put("paper-a", 1, FILES1)
    assert finish() == []
    d, _ = head_of("main")
    shutil.rmtree(d / sign.WITNESSES)
    capsys.readouterr()
    with pytest.raises(SystemExit):
        run("--root", str(archive), "verify", "--json")
    out, err = capsys.readouterr()
    assert any(x["place"] == "main v1" for x in json.loads(out))
    assert "the owner catalogue of" in err and "has no signed version" in err


def test_pdf_found_from_renditions(archive):
    put("paper-a", 1, {"main.tex": b"\\documentclass{article}", "article.pdf": b"%PDF article"},
        extra_obj={"renditions": [{"path": "article.pdf", "mediaType": "application/pdf"}]})
    assert finish() == []
    at = P.path_of(P.LABELS["paper-a"])
    page = (archive / "paper" / "paper-a" / "index.html").read_text()
    assert f'name="citation_pdf_url" content="https://example.org/archive/ocfl/{at}/v1/content/article.pdf"' in page
    assert f'href="../../ocfl/{at}/v1/content/article.pdf"' in page
    assert f'href="ocfl/{at}/v1/content/article.pdf"' in (archive / "index.html").read_text()


def test_index_pins_required_by_the_profile_website(archive, monkeypatch):
    put("paper-a", 1, FILES1)
    assert finish() == []
    nm = P.LABELS["paper-a"].split(":")[1]
    (archive / "index.html").write_text("<p>an index made by other tools</p>")
    shutil.rmtree(archive / "paper" / nm)
    errors = P.verify_errors()
    assert f"index.html: does not show the pin of {nm}" in errors
    assert any(e.startswith(f"paper/{nm}/index.html: no landing page giving the sheaf: URI") for e in errors)
    monkeypatch.setitem(P.ARCHIVE, "profiles", [])
    P.write_discovery()
    found = P.verify_findings()
    assert [x for x in found if x["severity"] == "error"] == []
    assert {"severity": "warning", "place": "index.html", "message": f"does not show the pin of {nm} "
            "(the archive does not declare the profile website)"} in found


def test_landing_page_of_a_line(tmp_path):
    root = tmp_path / "a"
    make_archive(root)
    src, pdf = tmp_path / "p.tex", tmp_path / "p.pdf"
    src.write_text("\\documentclass{article}")
    pdf.write_bytes(b"%PDF-1.4 p")
    r = ["--root", str(root)]
    paper = [str(src), "--pdf", str(pdf), "--title", "On $x$", "--author", "Doe, Jane"]
    run(*r, "deposit", "p", *paper, "--new", "--available", "2025-01-02")
    run(*r, "deposit", "p", *paper, "--changes", "Typos.", "--available", "2025-02-03")
    run(*r, "notice", "p", "--about", "1", "--text", "Lemma 2 is wrong as stated.")
    run(*r, "collect")
    obj_id = P.LABELS["p"]
    _, nm, owner = obj_id.split(":")
    d = P.obj_dir(obj_id)
    page = (root / "paper" / "p" / "index.html").read_text()
    assert f"<code class=\"copy\">sheaf:{nm}</code>" in page and f">sheaf:{nm[:16]}</code>" in page
    assert obj_id not in page and f"sheaf:{nm[:16]}:{owner[:16]}" not in page
    assert f'href="../../owner/{owner}/"' in page
    assert "Version 2" in page and "Version 1" in page and "Lemma 2 is wrong as stated." in page
    assert f"sheaf:{nm}/v2?sha512={P.digest(d / 'v3' / 'inventory.json')}" in page
    assert f"sheaf:{nm}/v1?sha512={P.digest(d / 'v1' / 'inventory.json')}" in page
    assert "contested" not in page and "Withdrawn" not in page
    owner_page = (root / "owner" / owner / "index.html").read_text()
    assert "Current keys (1 of 1 sign)" in owner_page and "Rotation keys committed to: 3" in owner_page
    assert 'href="../../paper/p/"' in owner_page
    assert f"https://example.org/T/owner/{owner}/" in (root / "sitemap.xml").read_text()
    assert P.verify_errors() == []
    run(*r, "withdraw", "p", "--reason", "The main result is wrong.")
    page = (root / "paper" / "p" / "index.html").read_text()
    assert "<strong>Withdrawn" in page and "The main result is wrong." in page
    assert '<li class="paper withdrawn">' in (root / "index.html").read_text()
    first = P.key_log(owner).latest().keys["keys"][0]
    third = P.key_new(P.argparse_namespace(owner=None)).did
    rk = rotation_files(tmp_path / "T-keys")
    run(*r, "owner", "expose", first, "--add", third, "--rotation-key", rk[0], "--rotation-key", rk[1],
        "--export", str(tmp_path / "T-keys-2"), "--no-passphrase", "--yes")
    main = P.LABELS["main"]
    run(*r, "sign", "main", "--version", P.load_inventory(P.obj_dir(main))["head"], "--yes")
    page = (root / "paper" / "p" / "index.html").read_text()
    assert '<div class="contested"><strong>Contested:</strong>' in page
    assert '<span class="contested">contested</span>' in page and "1 key exposed" in page
    assert "Exposed keys" in (root / "owner" / owner / "index.html").read_text()


def test_two_notices_on_a_line(tmp_path):
    root = tmp_path / "a"
    make_archive(root)
    src, pdf = tmp_path / "p.tex", tmp_path / "p.pdf"
    src.write_text("\\documentclass{article}")
    pdf.write_bytes(b"%PDF-1.4 p")
    r = ["--root", str(root)]
    paper = [str(src), "--pdf", str(pdf), "--title", "T", "--author", "Doe, Jane"]
    run(*r, "deposit", "p", *paper, "--new")
    run(*r, "notice", "p", "--about", "1", "--text", "Lemma 2 is wrong as stated.")
    run(*r, "notice", "p", "--about", "1", "--text", "Lemma 3 is wrong too.")
    d = P.obj_dir(P.LABELS["p"])
    inv = P.load_inventory(d)
    assert [n["text"] for n in P.read_json(d, inv, P.OBJ)["notices"]] == \
        ["Lemma 2 is wrong as stated.", "Lemma 3 is wrong too."]
    run(*r, "collect")
    page = (root / "paper" / "p" / "index.html").read_text()
    assert "Lemma 2 is wrong as stated." in page and "Lemma 3 is wrong too." in page
    run(*r, "notice", "p", "--about", "1", "--replaces", "1", "--text", "Lemma 2 is right after all.")
    with pytest.raises(SystemExit):
        run(*r, "notice", "p", "--about", "1", "--replaces", "1", "--text", "Again.")
    run(*r, "collect")
    page = (root / "paper" / "p" / "index.html").read_text()
    assert "Lemma 2 is wrong as stated." not in page and "Lemma 3 is wrong too." in page
    assert "Notice 3" in page and "replacing notice 1" in page
    pdf.write_bytes(b"%PDF-1.4 p2")
    run(*r, "deposit", "p", *paper, "--changes", "Lemmas fixed.")
    inv = P.load_inventory(d)
    assert len(P.read_json(d, inv, P.OBJ)["notices"]) == 3
    assert P.verify_errors() == []


def test_takedown_removes_the_pages(archive):
    put("paper-a", 1, FILES1)
    put("paper-b", 1, FILES2)
    assert finish() == []
    gone = P.LABELS["paper-a"]
    pin = P.digest(P.obj_dir(gone) / "v1" / "inventory.json")
    assert pin[:32] in (archive / "index.html").read_text()
    run("--root", str(archive), "takedown", "paper-a", "--reason", "At the request of the holder of the rights.",
        "--yes")
    sitemap = (archive / "sitemap.xml").read_text()
    assert "paper/paper-a/" not in sitemap and "paper/paper-b/" in sitemap
    assert not (archive / "paper" / "paper-a").exists()
    assert pin[:32] not in (archive / "index.html").read_text()
    assert P.verify_errors() == []


def test_relabel(tmp_path, capsys):
    root = tmp_path / "a"
    make_archive(root)
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-1.4 p")
    r = ["--root", str(root)]
    paper = ["--pdf", str(pdf), "--no-source", "x", "--title", "T", "--author", "Doe, Jane"]
    run(*r, "deposit", "old", *paper, "--new")
    run(*r, "deposit", "other", *paper, "--new")
    run(*r, "collect")
    obj_id = P.LABELS["old"]
    _, nm, owner = obj_id.split(":")
    (root / "site" / "old").mkdir(parents=True)
    (root / "site" / "old" / "old.html").write_text('<img src="old-1.png">')
    (root / "site" / "old" / "old-1.png").write_bytes(b"png")
    capsys.readouterr()
    run(*r, "label", "old", "new")
    out = capsys.readouterr().out
    assert out.startswith(f"Done: {obj_id} is labelled new, no longer old.\n" \
        "Its old address paper/old/ leads to paper/new/ (osheaf.json, formerAddresses).\n")
    cfg = json.loads((root / "osheaf.json").read_text())
    assert cfg["formerAddresses"] == {"old": obj_id}
    disc = json.loads((root / "opensheaf.json").read_text())
    assert next(o for o in disc["objects"] if o["id"] == obj_id)["label"] == "new"
    assert "new" in (root / "names" / f"{nm[:2]}.json").read_text()
    assert "T" in (root / "paper" / "new" / "index.html").read_text()
    moved = (root / "paper" / "old" / "index.html").read_text()
    assert P.REDIRECT_MARK in moved and 'url=../new/' in moved and "https://example.org/T/paper/new/" in moved
    assert "paper/old/" not in (root / "sitemap.xml").read_text()
    assert (root / "site" / "new" / "new.html").read_text() == '<img src="old-1.png">'
    assert (root / "site" / "new" / "old-1.png").exists()
    assert "url=../new/new.html" in (root / "site" / "old" / "old.html").read_text()
    assert P.verify_errors() == []
    pdf.write_bytes(b"%PDF-1.4 p2")
    run(*r, "deposit", "new", *paper, "--changes", "Typos.")
    d = P.obj_dir(obj_id)
    inv = P.load_inventory(d)
    assert P.read_json(d, inv, "datacite.json", "v1")["url"] == f"https://example.org/T/paper/{nm}/"
    assert P.read_json(d, inv, "datacite.json")["url"] == f"https://example.org/T/paper/{nm}/"
    assert "T" in (root / "paper" / nm / "index.html").read_text()
    run(*r, "label", "new", "newer")
    assert json.loads((root / "osheaf.json").read_text())["formerAddresses"] == {"new": obj_id, "old": obj_id}
    assert "url=../newer/" in (root / "paper" / "old" / "index.html").read_text()
    assert "url=../newer/" in (root / "paper" / "new" / "index.html").read_text()
    assert "url=../newer/newer.html" in (root / "site" / "old" / "old.html").read_text()
    run(*r, "label", "newer", "old")
    assert json.loads((root / "osheaf.json").read_text())["formerAddresses"] == {"new": obj_id, "newer": obj_id}
    assert P.REDIRECT_MARK not in (root / "paper" / "old" / "index.html").read_text()
    assert (root / "site" / "old" / "old.html").read_text() == '<img src="old-1.png">'
    for bad, why in ((["old", "other"], "label of another line"), (["old", "Bad_Label"], "must match"),
                     (["old"], "give the new label")):
        with pytest.raises(SystemExit, match=why):
            run(*r, "label", *bad)
    catalogue = P.LABELS["main"]
    run(*r, "label", "main", "papers")
    disc = json.loads((root / "opensheaf.json").read_text())
    assert P.LABELS["papers"] == catalogue and disc["owners"][0]["catalogue"] == catalogue
    run(*r, "collect")
    run(*r, "label", "--owner", owner, "jane-doe")
    disc = json.loads((root / "opensheaf.json").read_text())
    assert next(o for o in disc["objects"] if o["kind"] == "owner")["label"] == "jane-doe"
    assert "jane-doe" not in json.dumps(json.loads((root / "osheaf.json").read_text()).get("formerAddresses"))
    run(*r, "label", "--owner", owner, "--unset")
    assert "label" not in next(o for o in json.loads((root / "opensheaf.json").read_text())["objects"]
                               if o["kind"] == "owner")
    run(*r, "label", "old", "--unset")
    assert "T" in (root / "paper" / nm / "index.html").read_text()
    assert "url=../" + nm + "/" in (root / "paper" / "old" / "index.html").read_text()
    assert P.verify_errors() == []
    run(*r, "takedown", obj_id, "--reason", "At the request of the holder of the rights.", "--yes")
    assert json.loads((root / "osheaf.json").read_text())["formerAddresses"] == {"main": P.LABELS["papers"]}
    assert not (root / "paper" / "old").exists() and not (root / "site" / "old").exists()
    assert P.verify_errors() == []


def test_texmacs_index_with_landing_pages(tmp_path):
    """A TeXmacs index: index.tm with uniform entries, and the landing pages,
    from the archive's own template, and the sitemap of the website."""
    root = tmp_path / "a"
    (root / "templates").mkdir(parents=True)
    (root / "templates" / "paper.html").write_text(
        "<html><head>{{head}}<link rel=stylesheet href='{{root}}resources/notes-base.css'></head>"
        "<body class=house>{{title}} by {{authors}}{{html_link}} {{sheaf_uri}}<ol>{{versions}}</ol></body></html>")
    (root / "index-template.tm").write_text("<TeXmacs|2.1.5>\n\n<\\body>\n  <paper-index>\n</body>\n")
    make_archive(root, "T", "--index", "texmacs", "--index-template", str(root / "index-template.tm"))
    cfg = json.loads((root / "osheaf.json").read_text())
    assert cfg["profiles"] == ["texmacs"] and cfg["index"] == {"template": "index-template.tm"}
    assert sorted(p.name for p in (root / "templates").iterdir()) == ["paper.html"]
    assert (root / "index.tm").exists() and not (root / "index.html").exists()
    src, pdf = tmp_path / "p.tex", tmp_path / "p.pdf"
    src.write_text("\\documentclass{article}")
    pdf.write_bytes(b"%PDF-1.4 p")
    r = ["--root", str(root)]
    run(*r, "deposit", "p", str(src), "--pdf", str(pdf), "--title", "On $x$", "--author", "Doe, Jane",
        "--author", "Roe, Richard", "--author", "Poe, Ann", "--changes", "Typos.", "--available", "2025-01-02",
        "--new")
    run(*r, "relate", "p", "--to", "arxiv:2607.08385v1")
    (root / "site" / "p").mkdir(parents=True)
    (root / "site" / "p" / "p.html").write_text("<html>the paper</html>")
    run(*r, "collect")
    run(*r, "index", "--no-html")
    tm = (root / "index.tm").read_text(encoding="latin-1")
    assert "<hlink|On <specific|texmacs|<verbatim|x>><specific|html*|\\\\(x\\\\)>|paper/p/>" in tm
    assert "By Jane Doe, Richard Roe and Ann Poe." in tm
    assert "<hlink|arXiv:2607.08385|https://arxiv.org/abs/2607.08385>" in tm and "v1|" not in tm
    assert "changes: Typos." in tm
    page = (root / "paper" / "p" / "index.html").read_text()
    assert "class=house" in page and "Jane Doe, Richard Roe and Ann Poe" in page
    canonical = P.LABELS["p"].rsplit(":", 1)[0]
    assert canonical in page and P.LABELS["p"] not in page
    assert 'name="citation_author" content="Roe, Richard"' in page
    assert 'href="../../site/p/p.html">HTML</a>' in page
    assert '>arXiv:2607.08385</a>' in page and "changes: Typos." in page
    sitemap = (root / "sitemap.xml").read_text()
    assert "https://example.org/T/paper/p/" in sitemap and "https://example.org/T/site/p/p.html" in sitemap
    assert not (root / "index.html").exists() and not (root / "style.css").exists()
    d = P.obj_dir(P.LABELS["p"])
    assert P.read_json(d, P.load_inventory(d), "datacite.json")["url"] == \
        f"https://example.org/T/paper/{P.LABELS['p'].split(':')[1]}/"
    assert P.changes_note({"changes": {"text": "61 pages"},
                           "external": [{"role": "source", "service": "arXiv"}]}) == "arXiv comments: 61 pages"
    assert P.verify_errors() == []
    assert not [x for x in P.verify_findings() if x["place"].startswith(("paper/", "index.html"))]
    home = root / "paper" / P.LABELS["p"].split(":")[1] / "index.html"
    home.write_text(page.replace(f"{canonical}<ol>", f"{P.LABELS['p']}<ol>"))
    assert not [x for x in P.verify_findings() if x["place"].startswith(("paper/", "index.html"))]
    home.write_text(page.replace(canonical, "a line"))
    found = P.verify_findings()
    assert [x for x in found if x["severity"] == "error"] == []
    assert {"severity": "warning", "place": home.relative_to(root).as_posix(), "message": f"no landing page giving the "
            f"sheaf: URI of p (appendix A.3) (the archive does not declare the profile website)"} in found


def test_page_addresses(archive, monkeypatch):
    n, m, o1, o2 = "n" * 51 + "a", "m" * 51 + "a", "o" * 51 + "a", "p" * 51 + "a"
    held = [f"sheaf:{n}:{o1}", f"sheaf:{n}:{o2}", f"sheaf:{m}:{o1}"]
    assert [P.name_address(i, o1) for i in held] == [n, f"{n}-{o2}", m]
    monkeypatch.setattr(P, "LABELS", {"lab": held[0]})
    assert P.page_address(held[0]) == "lab" and P.page_address(held[2]) == m
    assert P.landing_url(held[1], o1) == f"{P.ARCHIVE['baseUrl']}paper/{n}-{o2}/"


def test_keeper_of_the_owner(tmp_path, monkeypatch, capsys):
    orcid = "https://orcid.org/0000-0002-4014-2949"
    record = {"researcher-url": []}
    asked = []
    monkeypatch.setattr(owners, "fetch_json", lambda url: asked.append(url) or record)
    root = tmp_path / "a"
    make_archive(root, "T", "--keeper", orcid)
    owner = P.ARCHIVE["owner"]
    record["researcher-url"] = [{"url-name": "OpenSheaf", "url": {"value": f"https://example.org/T/owner/{owner}/"}}]
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-1.4 p")
    r = ["--root", str(root)]
    run(*r, "deposit", "p", "--pdf", str(pdf), "--no-source", "x", "--title", "On x", "--author", "Doe, Jane",
        "--new")
    run(*r, "collect")
    assert set(asked) == {"https://pub.orcid.org/v3.0/0000-0002-4014-2949/researcher-urls"}
    page = (root / "paper" / "p" / "index.html").read_text()
    assert f'keeper <a href="{orcid}">{orcid}</a> (confirmed)' in page
    owner_page = (root / "owner" / owner / "index.html").read_text()
    assert f'Keeper: <a href="{orcid}">{orcid}</a> (confirmed)' in owner_page
    capsys.readouterr()
    run(*r, "owner", "show")
    assert f"Keeper        {orcid}  confirmed (ORCID record links the owner)" in capsys.readouterr().out
    run(*r, "owner", "show", "--offline")
    assert f"Keeper        {orcid}  not checked (offline: --offline given)" in capsys.readouterr().out
    messages = {x["message"]: x["severity"] for x in P.verify_findings()}
    assert messages[f"keeper {orcid}: not checked (osheaf verify --remote reads its ORCID record or domain, "
                    "section 6.6)"] == "result"
    messages = {x["message"]: x["severity"] for x in P.verify_findings(remote=True)}
    assert messages[f"keeper {orcid}: confirmed (ORCID record links the owner; section 6.6)"] == "result"
    record["researcher-url"] = []
    messages = {x["message"]: x["severity"] for x in P.verify_findings(remote=True)}
    assert messages[f"keeper {orcid}: claimed only (the ORCID record has no link naming the owner; "
                    "section 6.6)"] == "result"

    def offline(url):
        raise owners.KeeperUnreachable(f"{url}: no network")
    found = P.verify_findings(remote=True, keeper_fetch=offline)
    assert [x["severity"] for x in found if x["message"].startswith(f"keeper {orcid}: not checked (offline: ")] \
        == ["warning"]
    assert P.verify_errors() == []
    from opensheaf import html
    html.render(P.catalogue_members(), keeper_fetch=offline)
    page = (root / "paper" / "p" / "index.html").read_text()
    assert f'keeper <a href="{orcid}">{orcid}</a>' in page and "(confirmed)" not in page


def arxiv_downloads(folder, aid="2611.00001", label="first-paper"):
    import gzip
    paper = folder / "papers" / aid
    paper.mkdir(parents=True)
    (paper / "record.xml").write_text(f"""<?xml version="1.0"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><GetRecord><record><metadata>
<arXivRaw xmlns="http://arxiv.org/OAI/arXivRaw/"><id>{aid}</id>
<version version="v1"><date>Mon, 2 Nov 2026 10:00:00 GMT</date></version>
<version version="v2"><date>Tue, 10 Nov 2026 10:00:00 GMT</date></version>
<title>On the $\\Phi^4_3$ model</title><authors>Jane Doe and Richard Roe</authors>
<categories>math-ph math.PR</categories><license>http://creativecommons.org/licenses/by/4.0/</license>
<abstract>We prove $x&lt;y$.</abstract></arXivRaw></metadata></record></GetRecord></OAI-PMH>
""")
    (paper / "v1.pdf").write_bytes(b"%PDF-1.4 one")
    (paper / "v1-source.gz").write_bytes(gzip.compress(b"\\documentclass{article}\\begin{document}x\\end{document}"))
    (paper / "v2.pdf").write_bytes(b"%PDF-1.4 two")
    cc = "http://creativecommons.org/licenses/by/4.0/"
    (folder / "version-licences.json").write_text(json.dumps({
        f"{aid}v1": {"licence": cc, "comments": "10 pages"}, f"{aid}v2": {"licence": cc, "comments": "11 pages"}}))
    (folder / "identifiers.json").write_text(json.dumps({aid: label}))


def test_arxiv_import_of_two_versions(tmp_path):
    root = tmp_path / "a"
    make_archive(root)
    dl = tmp_path / "downloads"
    arxiv_downloads(dl)
    r = ["--root", str(root)]
    run(*r, "arxiv", "import", str(dl), "--agreement", "deposited by an author")
    P.configure(root)
    obj_id = P.LABELS["first-paper"]
    d = P.obj_dir(obj_id)
    inv = P.load_inventory(d)
    assert inv["head"] == "v2" and P.line_statuses(d, inv)[1] == [sign.SIGNED, sign.SIGNED]
    v1, v2 = (P.read_json(d, inv, P.OBJ, v) for v in ("v1", "v2"))
    assert (v1["name"], v1["owner"]) == tuple(obj_id.split(":")[1:]) and "previous" not in v1
    assert v2["previous"] == P.digest(d / "v1" / "inventory.json")
    assert v1["mainSource"] == "source/2611.00001.tex" and "sourcesMissing" in v2
    assert [o["external"][0]["label"] for o in (v1, v2)] == ["v1", "v2"]
    assert v1["external"][0]["record"] == "https://arxiv.org/abs/2611.00001v1"
    assert v2["agreement"]["method"] == "deposited by an author"
    assert v2["agreement"]["by"] == ["Doe, Jane", "Roe, Richard"]
    dc = P.read_json(d, inv, "datacite.json", "v2")
    assert dc["url"] == f"https://example.org/T/paper/{obj_id.split(':')[1]}/" and dc["version"] == "2"
    assert P.read_logical(d, inv, P.GENESIS).read_bytes() == P.read_logical(d, inv, P.GENESIS, "v1").read_bytes()
    run(*r, "arxiv", "import", str(dl))
    run(*r, "arxiv", "import", str(dl), "--update")
    assert P.load_inventory(d)["head"] == "v2"
    run(*r, "collect")
    run(*r, "index")
    assert "Version 2 (arXiv v2)" in (root / "paper" / "first-paper" / "index.html").read_text()
    assert P.verify_errors() == []
    other = tmp_path / "other"
    arxiv_downloads(other, "2611.00002", "first-paper")
    with pytest.raises(SystemExit, match="not related to this arXiv paper"):
        run(*r, "arxiv", "import", str(other))


class FakeZenodo:
    """Zenodo's deposit API, as far as the binding uses it, in memory."""

    def __init__(self, production=True):
        from opensheaf import zenodo
        self.production = production
        self.s = zenodo.SERVICES[production]
        self.records, self.uploads, self.calls, self.next = {}, {}, [], 100

    def doi(self, recid):
        return f"{self.s['prefix']}/zenodo.{recid}"

    def _record(self, concept):
        self.next += 1
        rec = {"id": self.next, "conceptrecid": concept or self.next + 1000,
               "links": {"bucket": f"https://zenodo.invalid/bucket/{self.next}",
                         "latest_draft": f"https://zenodo.invalid/api/deposit/depositions/{self.next}"},
               "files": [{"id": "inherited"}] if concept else []}
        self.records[rec["id"]] = rec
        return rec

    def call(self, method, url, data=None, raw=None):
        import hashlib
        self.calls.append((method, url))
        if method == "POST" and url == "/deposit/depositions":
            return self._record(None)
        if url.endswith("/actions/newversion"):
            rec = self._record(self.records[int(url.split("/")[-3])]["conceptrecid"])
            return {"links": {"latest_draft": rec["links"]["latest_draft"]}}
        if url.endswith("/actions/publish"):
            rec = self.records[int(url.split("/")[-3])]
            return {"doi": self.doi(rec["id"]), "conceptdoi": self.doi(rec["conceptrecid"])}
        if method == "GET":
            return self.records[int(url.rsplit("/", 1)[1])]
        if method == "PUT" and "/bucket/" in url:
            self.uploads[url.rsplit("/", 1)[1]] = raw
            return {"checksum": "md5:" + hashlib.md5(raw).hexdigest()}
        return {}


@pytest.fixture
def fake_zenodo(monkeypatch):
    import urllib.request
    from opensheaf import zenodo

    def no_network(*a, **k):
        raise AssertionError("a test reached for the network")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    fakes = {True: FakeZenodo(True), False: FakeZenodo(False)}
    monkeypatch.setattr(zenodo, "Zenodo", lambda production: fakes[production])
    return fakes


def test_zenodo_deposit(tmp_path, fake_zenodo):
    root = tmp_path / "a"
    make_archive(root)
    src, pdf = tmp_path / "p.tex", tmp_path / "p.pdf"
    src.write_text("\\documentclass{article}")
    pdf.write_bytes(b"%PDF-1.4 p")
    r = ["--root", str(root)]
    paper = [str(src), "--pdf", str(pdf), "--title", "On $x$", "--author", "Doe, Jane", "--rights", "cc-by-4.0"]
    run(*r, "deposit", "p", *paper, "--new")
    run(*r, "zenodo", "p")
    P.configure(root)
    d = P.obj_dir(P.LABELS["p"])
    assert P.load_inventory(d)["head"] == "v1" and not (root / "zenodo-staging").exists()
    assert fake_zenodo[False].uploads and "10.5072" not in (d / "v1" / "inventory.json").read_text()
    run(*r, "zenodo", "p", "--production")
    inv = P.load_inventory(d)
    assert inv["head"] == "v2" and P.line_statuses(d, inv)[1] == [sign.SIGNED, sign.SIGNED]
    obj, dc = P.read_json(d, inv, P.OBJ), P.read_json(d, inv, "datacite.json")
    entry = obj["external"][0]
    assert entry["role"] == "deposit" and entry["service"] == "Zenodo" and entry["doi"] == dc["doi"]
    assert dc["doi"].startswith("10.5281/zenodo.") and entry["record"].startswith("https://zenodo.org/records/")
    assert obj["previous"] == P.digest(d / "v1" / "inventory.json") and obj["documentVersion"] == 1
    assert dc["url"] == f"https://example.org/T/paper/{P.LABELS['p'].split(':')[1]}/"
    assert sorted(fake_zenodo[True].uploads) == ["datacite.json", "genesis.json", "object.json", "p.tex", "paper.pdf"]
    assert fake_zenodo[True].uploads["object.json"] == P.read_logical(d, inv, P.OBJ).read_bytes()
    with pytest.raises(SystemExit, match="already on Zenodo"):
        run(*r, "zenodo", "p", "--production")
    run(*r, "deposit", "p", *paper, "--changes", "Typos.")
    run(*r, "zenodo", "p", "--production")
    inv = P.load_inventory(d)
    dc2 = P.read_json(d, inv, "datacite.json")
    assert {"relatedIdentifier": dc["doi"], "relatedIdentifierType": "DOI",
            "relationType": "IsNewVersionOf"} in dc2["relatedIdentifiers"]
    assert any(u.endswith("/actions/newversion") for _, u in fake_zenodo[True].calls)
    assert set(P.line_statuses(d, inv)[1]) == {sign.SIGNED}
    run(*r, "collect")
    assert P.verify_errors() == []


def test_zenodo_completes_and_signs_again(tmp_path, fake_zenodo, monkeypatch):
    root = tmp_path / "a"
    make_archive(root)
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-1.4 p")
    r = ["--root", str(root)]
    paper = ["--pdf", str(pdf), "--no-source", "lost", "--title", "P", "--author", "Doe, Jane"]
    run(*r, "deposit", "p", *paper, "--new")
    install = P.install_version

    def crash(*a, **k):
        raise RuntimeError("the disk is full")
    monkeypatch.setattr(P, "install_version", crash)
    with pytest.raises(RuntimeError, match="the disk is full"):
        run(*r, "zenodo", "p", "--production")
    monkeypatch.setattr(P, "install_version", install)
    obj_id = P.LABELS["p"]
    assert json.loads((root / "zenodo-staging" / P.path_of(obj_id) / "state.json").read_text())["phase"] == "published"
    with pytest.raises(SystemExit, match="completes it first"):
        run(*r, "deposit", "p", *paper, "--changes", "x")
    owner = obj_id.split(":")[2]
    first = P.key_log(owner).latest().keys["keys"][0]
    third = P.key_new(P.argparse_namespace(owner=None)).did
    rk = rotation_files(tmp_path / "T-keys")
    run(*r, "owner", "expose", first, "--add", third, "--rotation-key", rk[0], "--rotation-key", rk[1],
        "--export", str(tmp_path / "T-keys-2"), "--no-passphrase", "--yes")
    P.configure(root)
    d = P.obj_dir(obj_id)
    assert P.line_statuses(d, P.load_inventory(d))[1] == [sign.CONTESTED]
    run(*r, "zenodo", "p", "--production")
    P.configure(root)
    inv = P.load_inventory(d)
    assert inv["head"] == "v2" and P.line_statuses(d, inv)[1] == [sign.SIGNED, sign.SIGNED]
    assert len(P.witnesses_of(d, "v2")) == 2
    assert not (root / "zenodo-staging").exists()
    assert P.read_json(d, inv, "datacite.json")["doi"].startswith("10.5281/zenodo.")
