Takedowns and tombstones
========================

An owner *withdraws* a line, by a description-only version that keeps
every version ([description-only versions](14-description.md), section
13.1); an archive *takes down* an object, which deletes it and leaves a
tombstone (sections 13.2 and 13.3). This chapter is the module
`takedown.py`: the command `osheaf takedown`, the tombstones it writes,
and the rule by which a line taken down returns.

What a takedown does
--------------------

A takedown deletes a sealed object, witness folder included, from the
storage root, with the folders the deletion leaves empty, and from the
presentation files, and adds a tombstone to the discovery document. Every
removal of a sealed object is a takedown, whatever its reason: content
that must not be served (by law, for a breach of rights, to erase personal
data), or a line the archive stops keeping. It removes one object: a
branch holding the same files, or a mirror elsewhere, is taken down on its
own (section 13.2). A draft is never taken down: it is deleted, and leaves
no tombstone ([drafts](24-drafts.md)).

**Owner objects.** A takedown of a line leaves in place the key logs its
copy carries (section 6.5): other lines of the owner need them, and a
returning line too. A key log that an object of the archive needs (a line
of its owner, or a branch whose evidence holds its owner's signatures) is
taken down only for itself, and only by law or at its keeper's request
(section 6.6); never at a request signed by the owner's keys, which a
thief may hold. The command asks for `--by-law` or `--keeper` then, and a
confirmation; the owner's signatures in what the archive keeps become
unchecked there (section 7.3), and the tombstone stands in for the key log
(section 6.5), which [verification](17-verify.md) reports as a warning.

**The tombstone** (section 13.3) records the object's `id`, `kind`, `name`
and `owner`; its genesis name, so that a later deposit of the same genesis
record is refused (section 5.4); its head when taken down and the digest
of that version's inventory, a pin; the date; and a reason, a plain text
that should not repeat what was taken down. It is never removed, except
when the line returns: it keeps the line taken (section 5.3), and the
discovery document never lists its identifier among `objects`. The
[indexes](16-index.md) keep the object's entries in `names/` and
`sha512/`, with the status `removed`, so they are written just before the
files go.

**Returning.** A line taken down returns only from a copy holding the
version its tombstone pins (section 13.2), added as section 7.5 says: it
is the same line, not a reuse of its identifier, and its tombstone is
dropped. A [mirror](22-mirrors.md) and the copies of key logs check this
with `may_return`, given a function telling whether the copy holds a
version with a given digest. Section 13.2 also lets a line return from the
latest signed version before the pin, when the version pinned is not
signed; these tools ask for the version pinned, which is what they can
check from the tombstone alone.

The module
----------

    # in src/opensheaf/takedown.py:
    """Takedowns and tombstones (sections 13.2 and 13.3 of OpenSheaf 0.2).

        osheaf takedown LABEL|ID --reason TEXT [--by-law | --keeper] [--yes]
    """

    import json
    import shutil
    import sys

    from . import core as P, names, owners


    <<takedown: the tombstone of a line, and its return>>


    <<takedown: the key logs the objects of the archive need>>


    <<takedown: the command>>

The tombstone of a line, and the return of a line taken down.

    # in takedown: the tombstone of a line, and its return:
    def tombstone_of(obj_id):
        """The tombstone of OBJ_ID in the archive, or None."""
        return next((t for t in P.TOMBSTONES if t.get("id") == obj_id), None)


    def may_return(obj_id, holds):
        """Whether the line OBJ_ID may come back from a copy (section 13.2): True when it has no
        tombstone, or when HOLDS(number, digest) says the copy holds the version the tombstone
        pins, whose tombstone is then dropped (written with the next discovery document)."""
        t = tombstone_of(obj_id)
        if t is None:
            return True
        if not holds(int(t["lastVersion"][1:]), t["inventorySha512"]):
            return False
        P.TOMBSTONES.remove(t)
        print(f"{obj_id} returns: its tombstone is dropped (section 13.2)")
        return True

The key logs needed: the owner of every line held, and for a branch the
owner of each parent whose signatures its evidence holds, at every level
of `parent/parent/` (section 6.5), in any version.

    # in takedown: the key logs the objects of the archive need:
    def needed_owners():
        """{owner name: [identifiers of the objects that need its key log]} (section 6.5)."""
        out = {}
        for obj_id, d, inv in P.objects():
            if not obj_id or inv is None or obj_id.startswith("sheaf:draft:"):
                continue
            _, nm, owner = obj_id.split(":")
            if nm == owner:
                continue
            out.setdefault(owner, []).append(obj_id)
            for ver in inv["versions"]:
                prefix = ""
                while True:
                    p = P.read_logical(d, inv, prefix + "parent/object.json", ver)
                    if p is None:
                        break
                    try:
                        pobj = json.loads(p.read_text(encoding="utf-8"))
                    except ValueError:
                        break
                    if obj_id not in out.setdefault(pobj.get("owner"), []):
                        out[pobj.get("owner")].append(obj_id)
                    prefix += "parent/"
        return out

The command. The object is named by its label or identifier (a key log by
`sheaf:<owner>:<owner>`); a confirmation is asked, the first eight
characters of the line's name typed back, unless `--yes`. The landing page
of the line and its HTML version go with it, at once, and so do its former
addresses (`formerAddresses` of `osheaf.json`, written by `osheaf label`):
the pages left there, and their record; the rest of the
presentation files (the home page, the pages of the collections that list
it, the sitemap) are written again by the [command line](60-command-line.md)
after the command, as after every change (appendix A.3), and the
[website](30-website.md) leaves out every member whose line has a tombstone
here. The owner catalogue keeps its member, a pin of a version now removed
(section 8.5), until `osheaf collect` writes its next version (section
13.2).

    # in takedown: the command:
    def main(args):
        obj_id = P.resolve(args.id)
        if obj_id.startswith("sheaf:draft:"):
            sys.exit("a draft is deleted, not taken down: osheaf draft delete (section 10.1)")
        d = P.obj_dir(obj_id)
        inv = P.load_inventory(d)
        head = P.read_json(d, inv, P.OBJ) or {}
        _, nm, owner = obj_id.split(":")
        if head.get("kind") == "owner":
            users = [i for i in needed_owners().get(owner, []) if i != obj_id]
            if users and not (args.by_law or args.keeper):
                sys.exit(f"the key log of {owner} is needed by {len(users)} object(s) of this archive: it is "
                         "taken down only for itself, by law or at its keeper's request (section 13.2); give "
                         "--by-law or --keeper")
            if users:
                print(f"warning: the signatures of {owner} in {len(users)} object(s) become unchecked here, and "
                      "the tombstone stands in for its key log (sections 6.5 and 13.2)", file=sys.stderr)
        if not args.reason or not args.reason.strip():
            sys.exit("a takedown needs --reason, a plain text (section 13.3)")
        if not getattr(args, "yes", False):
            typed = input(f"take down {obj_id} for good? type {nm[:8]} to confirm: ").strip()
            if typed != nm[:8]:
                sys.exit("not confirmed: nothing was taken down")
        genesis = P.read_logical(d, inv, P.GENESIS, "v1").read_bytes()
        tomb = {"id": obj_id, "kind": head.get("kind"), "name": nm, "owner": owner,
                "genesisName": names.name(genesis), "lastVersion": inv["head"],
                "inventorySha512": owners.sidecar_digest((d / "inventory.json.sha512").read_bytes()),
                "date": P.TODAY, "reason": args.reason.strip()}
        P.write_indexes()
        home = P.name_address(obj_id)
        label = P.label_of(obj_id)
        if label:
            del P.LABELS[label]
        cfg = json.loads((P.ROOT / P.CONFIG_NAME).read_text(encoding="utf-8"))
        former = dict(cfg.get("formerAddresses") or {})
        gone = [a for a, i in former.items() if i == obj_id]
        for folder in [P.ROOT / "paper" / home, P.ROOT / "paper" / (label or nm), P.SITE / (label or nm)] + \
                [P.SITE / a for a in gone if P.LABEL_RE.match(a)]:
            shutil.rmtree(folder, ignore_errors=True)
        if gone:
            cfg["formerAddresses"] = {a: i for a, i in former.items() if i != obj_id}
            if not cfg["formerAddresses"]:
                del cfg["formerAddresses"]
            P.write_config(cfg)
        shutil.rmtree(d)
        parent = d.parent
        while parent != P.OCFL and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
        P.TOMBSTONES.append(tomb)
        P.write_discovery()
        print(f"{label or obj_id}: taken down ({inv['head']}); tombstone written (section 13.3)")
