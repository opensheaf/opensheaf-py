Drafts and sealing
==================

A *draft* is a sandbox for a work not yet sealed, on which nothing may
rely; *sealing* makes from a work, under a new genesis record, the first
version of its originator's line (section 10). `osheaf deposit --new`
seals a work from files outside any archive ([deposits](13-deposit.md)).
This chapter is the module `drafts.py`, which keeps drafts in the archive
and seals a line from one.

What a draft is
---------------

A draft belongs to the reserved owner `draft`: its identifier is
`sheaf:draft:<id>`, where `<id>` is chosen by the archive, with the form of
a label, and it is at `draft/<id>/` in the owner-name layout (section
10.1). It is a document in the format of any document, with
`object.json` and `datacite.json`, but no genesis record or other identity
files, and its `object.json` has no `name`, `owner` or `parent`. Its
document versions are numbered by the rules of section 4.2, as any
document's.

A draft is the archive's alone: it is never signed, pinned, copied out,
indexed or named by a `sheaf:` URI. The discovery document lists it apart,
in `drafts` (section 3.1), as unfinished work. And a draft may change: it
is the only object that may be rewritten or deleted (section 10.1). These
tools add versions to a draft with every deposit, as to any object, and
rewrite only its head, on request (`--replace`): the head version folder
is removed and the root inventory goes back to the version before, after
which the deposit adds the version again. A draft deleted leaves no
tombstone (section 13).

Sealing
-------

`osheaf seal DRAFT --label LABEL` seals the work of the draft: it writes a
new genesis record, with the archive's owner (or `--owner`) as
`originator`, and makes the line `sheaf:<name>:<owner>`, whose first
version holds the genesis record and the files of the draft's head as
document version 1, signed by the owner (section 10.2). The versions of
the draft are never part of the line, and nothing in the line refers to
them: so the draft's history and notices, which name its own versions,
are left out, with the files of the notices, and the description keeps
everything but the version and the date of its last change. The draft
stays, and may be deleted (`--delete-draft`), or kept for the next round.

The module
----------

    # in src/opensheaf/drafts.py:
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


    <<drafts: the folder of a draft>>


    <<drafts: depositing into a draft>>


    <<drafts: sealing a draft>>

A draft is named by its `<id>` alone, local to the archive; `draft_dir`
finds it, and `drop_head` rewrites it, removing its head version. A
draft removed (by `draft delete`, by `seal --delete-draft`, or by
rewriting its only version) is removed by `remove`, which also removes the
folders above it that are left empty, up to the storage root: `draft/`
once it holds no draft, and under the hashed layout the folders of the
three tuples (`ocfl/93b/8be/2c1/`, say), as a takedown does. An empty
folder in a storage root is refused by OCFL validators (E073).

    # in drafts: the folder of a draft:
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


    def remove(d):
        """Remove the draft in D, and the folders above it left empty, up to the storage root (draft/,
        or the tuples of the hashed layout): an empty folder there is not an object, and OCFL
        validators refuse it (E073)."""
        shutil.rmtree(P.unlinked(d))
        parent = d.parent
        while parent != P.OCFL and P.OCFL in parent.parents and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


    def drop_head(d, inv):
        """Remove the head version of the draft in D: the draft may be rewritten (section 10.1)."""
        n = int(inv["head"][1:])
        if n == 1:
            remove(d)
            return
        shutil.rmtree(P.unlinked(d / f"v{n}"))
        for name in ("inventory.json", "inventory.json.sha512"):
            shutil.copyfile(d / f"v{n - 1}" / name, d / f"{name}.tmp")
            os.replace(d / f"{name}.tmp", d / name)


    def delete(args):
        """osheaf draft delete ID: the draft goes, and leaves no tombstone (section 10.1)."""
        obj_id, d, _ = draft_dir(args.id)
        remove(d)
        P.write_discovery()
        print(f"draft {args.id}: deleted")

A deposit into a draft is a deposit ([chapter 13](13-deposit.md)) with
`draft` set; `draft new` makes the draft, `draft deposit` adds a version,
or with `--replace` rewrites the head.

    # in drafts: depositing into a draft:
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

The seal. The files of the draft's head are read through its inventory,
and become the files of the new line's first version, with the genesis
record added and the two descriptions rewritten; `add_version` signs it.

    # in drafts: sealing a draft:
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
        files = {p: P.content_file(d, inv["manifest"][dig][0]) for dig, ps in state.items() for p in ps
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
            remove(d)
        P.write_discovery()
        print(f"{label}: {new['head']} (document version 1) {line}, sealed from the draft {args.id}")
