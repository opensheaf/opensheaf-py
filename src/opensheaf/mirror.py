# Generated from literate/21-mirrors.md by tools/tangle.py: edit the document, not this file.
"""Mirrors (section 10.4 of the specification): a copy, in this archive's
storage root, of another archive's object, byte for byte and with all its
versions, kept under its own identifier.

    osheaf mirror ARCHIVE-URL ID [--licence-checked]

A mirror is allowed only if the licence of the copied content allows
redistribution: the tool checks the rightsList of every version and refuses
unless each is an open licence (CC BY, CC BY-SA, CC0, GPL), or the curator
states with --licence-checked that redistribution is allowed (for instance by
the authors' permission). A reference (a member pinned in a collection,
without a copy) needs no permission. Every copied file is checked against the
digest of the source's inventory; a mirror that exists already gets the new
versions only.
"""

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

from . import core as P
from .collections import Remote, get

OPEN = {"cc-by-4.0", "cc-by-sa-4.0", "cc0-1.0", "gpl-3.0-only", "gpl-3.0-or-later", "cc-by-3.0"}
OPEN_URIS = ("creativecommons.org/licenses/by/", "creativecommons.org/licenses/by-sa/",
             "creativecommons.org/publicdomain/zero/", "gnu.org/licenses/gpl")


def is_open(rights):
    for r in rights or []:
        if (r.get("rightsIdentifier") or "").lower() in OPEN:
            return True
        uri = (r.get("rightsUri") or "").lower()
        if any(u in uri for u in OPEN_URIS) and "-nc" not in uri and "-nd" not in uri:
            return True
    return False


def mirror(url, obj_id, licence_checked=False):
    """Copy (or bring up to date) object OBJ_ID of the archive at URL."""
    r = Remote(url)
    if r.archive_id == P.ARCHIVE["archiveId"]:
        sys.exit(f"{obj_id} is an object of this archive")
    inv = r.inventory(obj_id)
    closed = []
    for ver in inv["versions"]:
        dc = json.loads(r.file(obj_id, inv, ver, "datacite.json"))
        if not is_open(dc.get("rightsList")):
            closed.append(f"{ver} ({(dc.get('rightsList') or [{}])[0].get('rights', 'no licence')})")
    if closed and not licence_checked:
        sys.exit(f"{obj_id}: not mirrored: these versions are not under an open licence: "
                 f"{', '.join(closed)}. Pin it in a collection instead (a reference needs no "
                 "permission), or mirror with --licence-checked if redistribution is allowed.")
    d = P.OCFL / obj_id
    have = P.load_inventory(d)
    if have:
        here = P.read_json(d, have, P.OBJ)
        if here.get("archiveId") != r.archive_id:
            sys.exit(f"this archive has an object {obj_id} already (section 10.4: a mirror keeps its "
                     "identifier only if no object of this archive has it)")
    tmp = Path(tempfile.mkdtemp(dir=P.OCFL))
    try:
        stage = tmp / obj_id
        if have:
            shutil.copytree(d, stage)
        else:
            stage.mkdir()
        new = [v for v in inv["versions"] if not (stage / v).exists()]
        base = r.root + obj_id + "/"
        for ver in new:
            for name in ("inventory.json", "inventory.json.sha512"):
                (stage / ver).mkdir(parents=True, exist_ok=True)
                (stage / ver / name).write_bytes(get(base + f"{ver}/{name}"))
            for dig, paths in inv["manifest"].items():
                for cp in paths:
                    if cp.startswith(ver + "/"):
                        data = get(base + cp)
                        if hashlib.sha512(data).hexdigest() != dig:
                            sys.exit(f"{obj_id}: {cp} does not match its digest; nothing mirrored")
                        f = stage / cp
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_bytes(data)
        for name in ("0=ocfl_object_1.1", "inventory.json", "inventory.json.sha512"):
            (stage / name).write_bytes(get(base + name))
        if hashlib.sha512((stage / "inventory.json").read_bytes()).hexdigest() != \
                (stage / "inventory.json.sha512").read_text().split()[0]:
            sys.exit(f"{obj_id}: the inventory does not match its checksum file; nothing mirrored")
        if d.exists():
            shutil.rmtree(d)
        shutil.move(str(stage), str(d))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{obj_id}: mirrored from {r.archive_id} ({len(new)} new version(s), head {inv['head']})")
    return r


def is_mirror(obj_dir, inv):
    return P.read_json(obj_dir, inv, P.OBJ).get("archiveId") != P.ARCHIVE["archiveId"]


def main(args):
    P.init_storage_root()
    mirror(args.url, args.id, args.licence_checked)
