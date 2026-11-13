Mirrors
=======

A collection refers to the members of other archives without copying
them ([collections](20-collections.md)). A reference needs nobody's
permission, but it depends on the other archive staying online. A
*mirror* removes that dependence: it is a copy, in this archive's storage
root, of another archive's object, byte for byte and with all its
versions (section 10.4 of the specification). This chapter describes
`src/opensheaf/mirror.py`, which makes and updates mirrors; it uses the
reading of other archives from the chapter on collections, and its
licence check is used again by [accepted copies](22-accepted-copies.md).

What a mirror is
----------------

A mirror is the same object as the original, not a new one. It keeps the
original identifier, and its `object.json` files keep naming the
original archive: nothing in it is rewritten, so every inventory and
every digest stays valid, and a pin made on the original is confirmed by
the copy. This is how the rest of the tools recognise a mirror: an object
of the storage root whose head names another archive. The main
collection leaves such objects out, a collection lists the copy in a
member's `mirrors`, and the verification of a collection falls back on
the copy when the original archive fails.

Since OCFL objects only grow, bringing a mirror up to date means copying
the versions it does not have yet, and nothing else; a mirror is never
changed otherwise. Two rules limit what may be mirrored. The identifier
must be free: an object of this archive with the same identifier rules
the mirror out (identifiers are never reused, section 6.3). And copying
is redistribution, which the licence of every version copied must allow.

The specification now also asks the discovery document to list a mirror
with `mirrorOf`, the identifier of the original archive (section 6.1).
The discovery document written by these tools (in the chapters on the
core) does not do so yet.

The module
----------

    # in src/opensheaf/mirror.py:
    <<the documentation of mirror.py>>


    <<whether a licence allows redistribution>>


    <<mirroring an object of another archive>>


    <<whether an object is a mirror>>


    <<the command mirror>>

The documentation states the command and the rule on licences. The
module reuses `Remote` and `get` from the collections module, so that
mirrors read other archives exactly as collections do.

    # in the documentation of mirror.py:
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

    <<the licences known to be open>>

Open licences
-------------

A licence is recognised as open in either of the two ways `datacite.json`
records it (section 8): by its SPDX identifier, written in lower case, or
by the URL of the licence. The list is short on purpose: licences that
certainly allow anyone to redistribute the work unchanged. arXiv's
default licence, for instance, gives arXiv alone the right to distribute,
and is not among them.

    # in the licences known to be open:
    OPEN = {"cc-by-4.0", "cc-by-sa-4.0", "cc0-1.0", "gpl-3.0-only", "gpl-3.0-or-later", "cc-by-3.0"}
    OPEN_URIS = ("creativecommons.org/licenses/by/", "creativecommons.org/licenses/by-sa/",
                 "creativecommons.org/publicdomain/zero/", "gnu.org/licenses/gpl")

A URL matches by its stem, so that any version of a Creative Commons
licence, and its national ports, is recognised. The stems of CC BY and CC
BY-SA do not match the NonCommercial and NoDerivatives variants anyway
(`licenses/by-nc/` does not contain `licenses/by/`), and the test for
`-nc` and `-nd` makes the exclusion explicit. One open entry in the
`rightsList` suffices: a work offered under several licences may be
redistributed under any of them.

    # in whether a licence allows redistribution:
    def is_open(rights):
        for r in rights or []:
            if (r.get("rightsIdentifier") or "").lower() in OPEN:
                return True
            uri = (r.get("rightsUri") or "").lower()
            if any(u in uri for u in OPEN_URIS) and "-nc" not in uri and "-nd" not in uri:
                return True
        return False

When the licence is not open, redistribution may still be allowed, for
instance by the authors' permission. The tool cannot know that, and asks
the curator to say so with `--licence-checked`.

Mirroring an object
-------------------

`mirror` both creates a mirror and brings it up to date. It reads the
original archive, refuses to mirror an object of this very archive, and
then applies the two rules above before copying anything.

    # in mirroring an object of another archive:
    def mirror(url, obj_id, licence_checked=False):
        """Copy (or bring up to date) object OBJ_ID of the archive at URL."""
        r = Remote(url)
        if r.archive_id == P.ARCHIVE["archiveId"]:
            sys.exit(f"{obj_id} is an object of this archive")
        inv = r.inventory(obj_id)
        <<refuse to mirror versions without an open licence>>
        <<refuse to mirror over an object of this archive>>
        tmp = Path(tempfile.mkdtemp(dir=P.OCFL))
        try:
            <<copy the new versions of a mirrored object into a staging folder>>
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        print(f"{obj_id}: mirrored from {r.archive_id} ({len(new)} new version(s), head {inv['head']})")
        return r

The licence is checked on every version of the original, also on the
versions already mirrored: the whole object is what the mirror
distributes. The message names the closed versions with their licence,
and suggests the alternatives: a reference, which needs no permission,
or `--licence-checked`.

    # in refuse to mirror versions without an open licence:
    closed = []
    for ver in inv["versions"]:
        dc = json.loads(r.file(obj_id, inv, ver, "datacite.json"))
        if not is_open(dc.get("rightsList")):
            closed.append(f"{ver} ({(dc.get('rightsList') or [{}])[0].get('rights', 'no licence')})")
    if closed and not licence_checked:
        sys.exit(f"{obj_id}: not mirrored: these versions are not under an open licence: "
                 f"{', '.join(closed)}. Pin it in a collection instead (a reference needs no "
                 "permission), or mirror with --licence-checked if redistribution is allowed.")

An object of the same identifier that is already here must be a mirror
of the same archive; anything else (a document of this archive, or a
mirror of another archive's object that happens to share the identifier)
is left alone.

    # in refuse to mirror over an object of this archive:
    d = P.OCFL / obj_id
    have = P.load_inventory(d)
    if have:
        here = P.read_json(d, have, P.OBJ)
        if here.get("archiveId") != r.archive_id:
            sys.exit(f"this archive has an object {obj_id} already (section 10.4: a mirror keeps its "
                     "identifier only if no object of this archive has it)")

### Copying through a staging folder

The copy is made in a staging folder and moved into place only when
every file has been checked, so that a failure half-way (a network
error, a file that does not match its digest) leaves the storage root as
it was. The staging folder is made inside the storage root, so that the
final move is a rename on the same file system; the `finally` above
removes it whatever happens, also after `sys.exit`, which raises an
exception. A mirror being updated is first copied whole into the staging
folder, and the versions whose folder is not there yet are the new
ones.

    # in copy the new versions of a mirrored object into a staging folder:
    stage = tmp / obj_id
    if have:
        shutil.copytree(d, stage)
    else:
        stage.mkdir()
    new = [v for v in inv["versions"] if not (stage / v).exists()]
    base = r.root + obj_id + "/"
    for ver in new:
        <<copy one version of a mirrored object, checking every file>>
    <<copy the root of a mirrored object and check its inventory>>
    <<put the staged mirror in place>>

A version folder of an OCFL object holds the inventory of that version,
with its sidecar, and the content files added in that version: those
whose content path starts with the version's name. The files of earlier
versions are not copied again, since OCFL stores each content once and
later versions refer to it. Each file is checked against the digest by
which the manifest of the head lists it, before it is written.

    # in copy one version of a mirrored object, checking every file:
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

The root of the object holds the OCFL declaration file and the inventory
of the head, with its sidecar. The digests of the files were checked
against this inventory, as read at the start; the inventory now copied
is checked against its own sidecar.

    # in copy the root of a mirrored object and check its inventory:
    for name in ("0=ocfl_object_1.1", "inventory.json", "inventory.json.sha512"):
        (stage / name).write_bytes(get(base + name))
    if hashlib.sha512((stage / "inventory.json").read_bytes()).hexdigest() != \
            (stage / "inventory.json.sha512").read_text().split()[0]:
        sys.exit(f"{obj_id}: the inventory does not match its checksum file; nothing mirrored")

The old mirror, if any, is replaced by the staged one. Between the two
operations the object is briefly absent, but never incomplete.

    # in put the staged mirror in place:
    if d.exists():
        shutil.rmtree(d)
    shutil.move(str(stage), str(d))

Recognising a mirror
--------------------

An object is a mirror when its head names another archive. The test is
kept here for other modules; at present nothing calls it, and the
chapters on the core make the same test inline.

    # in whether an object is a mirror:
    def is_mirror(obj_dir, inv):
        return P.read_json(obj_dir, inv, P.OBJ).get("archiveId") != P.ARCHIVE["archiveId"]

The command
-----------

`osheaf mirror ARCHIVE-URL ID [--licence-checked]` creates the storage
root if needed and mirrors the object. A mirror can also be made while
composing a collection, with `mirror: yes` in the member's entry of
`collection.yaml`.

    # in the command mirror:
    def main(args):
        P.init_storage_root()
        mirror(args.url, args.id, args.licence_checked)
