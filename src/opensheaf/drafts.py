# Generated from literate/24-drafts.md by opensheaf-literate: edit the document, not this file.
"""Drafts and sealing (section 10 of OpenSheaf 0.2).

    osheaf draft new ID [SOURCE] [the options of deposit]
    osheaf draft deposit ID [SOURCE] [the options of deposit] [--replace]
    osheaf draft delete ID
    osheaf seal ID --label LABEL [--owner OWNER] [--delete-draft]
"""

import os
import shutil
import sys

from . import core as P


def draft_dir(draft_id):
    """(identifier, folder, inventory) of the draft DRAFT_ID, which must exist."""
    if not draft_id or not P.LABEL_RE.match(draft_id) or len(draft_id) > 64:
        sys.exit(f"{draft_id}: not the identifier of a draft (section 10.1)")
    obj_id = f"sheaf:draft:{draft_id}"
    d = P.obj_dir(obj_id)
    inv = P.load_inventory(d)
    if inv is None:
        sys.exit(f"no draft {draft_id} in this archive")
    return obj_id, d, inv


def drop_head(d, inv):
    """Remove the head version of the draft in D: the draft may be rewritten (section 10.1)."""
    n = int(inv["head"][1:])
    if n == 1:
        shutil.rmtree(P.unlinked(d))
        return
    shutil.rmtree(P.unlinked(d / f"v{n}"))
    for name in ("inventory.json", "inventory.json.sha512"):
        shutil.copyfile(d / f"v{n - 1}" / name, d / f"{name}.tmp")
        os.replace(d / f"{name}.tmp", d / name)


def delete(args):
    """osheaf draft delete ID: the draft goes, and leaves no tombstone (section 10.1)."""
    obj_id, d, _ = draft_dir(args.id)
    shutil.rmtree(P.unlinked(d))
    if d.parent != P.OCFL and not any(d.parent.iterdir()):
        d.parent.rmdir()
    P.write_discovery()
    print(f"draft {args.id}: deleted")


def deposit(args, new=False):
    """osheaf draft new|deposit ID ...: a document version deposited into the draft ID."""
    if not args.title or not args.author:
        sys.exit("a deposit into a draft needs --title and --author")
    args.draft, args.new = True, new
    if not new and getattr(args, "replace", False):
        _, d, inv = draft_dir(args.id)
        drop_head(d, inv)
        if not (d / "inventory.json").exists():
            args.new = True
    P.deposit(args)


def seal(args):
    """osheaf seal ID --label LABEL: seal the work of the draft ID as a new line (section 10.2)."""
    obj_id, d, inv = draft_dir(args.id)
    label = args.label
    if not label or not P.LABEL_RE.match(label) or len(label) > 64 or label in P.LABELS:
        sys.exit(f"--label: a new label of the form of section 3.1 (not {label!r})")
    owner = getattr(args, "owner", None) or P.ARCHIVE["owner"]
    if owner not in P.archive_owners():
        sys.exit(f"{owner} is not an owner this archive hosts")
    head = P.read_json(d, inv, P.OBJ)
    dc = P.read_json(d, inv, "datacite.json")
    notes = {n["path"] for n in head.get("notices", []) if n.get("path")}
    state = inv["versions"][inv["head"]]["state"]
    files = {p: d / inv["manifest"][dig][0] for dig, ps in state.items() for p in ps
             if p not in (P.OBJ, "datacite.json") and p not in notes}
    obj = {k: v for k, v in head.items() if k not in ("history", "notices", "previous")}
    obj["documentVersion"] = 1
    dc["version"] = "1"
    dc["dates"] = [x for x in dc.get("dates", []) if x.get("dateType") != "Updated"]
    genesis, line = P.seal(head["kind"], owner)
    obj = {"format": obj["format"], "specification": obj["specification"], "kind": obj["kind"],
           "name": line.split(":")[1], "owner": owner,
           **{k: v for k, v in obj.items() if k not in ("format", "specification", "kind")}}
    dc["url"] = P.landing_url(line)
    files[P.GENESIS] = genesis
    files["datacite.json"] = P.json_bytes(dc)
    new = P.add_version(line, files, obj, getattr(args, "message", None) or f"Sealed from the draft {args.id}")
    P.LABELS[label] = line
    if getattr(args, "delete_draft", False):
        shutil.rmtree(P.unlinked(d))
    P.write_discovery()
    print(f"{label}: {new['head']} (document version 1) {line}, sealed from the draft {args.id}")
