# Generated from literate/25-takedown.md by opensheaf-literate: edit the document, not this file.
"""Takedowns and tombstones (sections 13.2 and 13.3 of OpenSheaf 0.2).

    osheaf takedown LABEL|ID --reason TEXT [--by-law | --keeper] [--yes]
"""

import json
import shutil
import sys

from . import core as P, names, owners


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
    label = P.label_of(obj_id)
    if label:
        del P.LABELS[label]
    cfg = json.loads((P.ROOT / P.CONFIG_NAME).read_text(encoding="utf-8"))
    former = dict(cfg.get("formerAddresses") or {})
    gone = [a for a, i in former.items() if i == obj_id]
    for folder in [P.ROOT / "paper" / (label or nm), P.SITE / (label or nm)] + \
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
