The main collection
===================

The documents of an archive are listed by its *main collection*: an object
of kind `collection` whose `members.json` (section 10) names each document
and pins it, by an object version and the SHA-512 digest of that version's
inventory. It is an *archive collection* (section 10.1): it keeps the
archive's documents whole, every version, without judging them, so each
member pins the head of its object, and follows it as it grows. The
collection is itself versioned, like any object: each change of the list
is a new version, so that the list of an archive at any past moment can be
recovered and checked. The index and the website are made
from it ([next chapter](16-index.md)), and other archives' collections can
include it.

This chapter is `osheaf collect`, which writes a new version of the main
collection when the documents have changed. Collections curated by hand,
with members of other archives, are the subject of
[collections](20-collections.md); a main collection may be one of those
(a *curated* archive), and then `collect` leaves it alone.

    # in maintain the main collection of the archive:
    <<the order of the main collection>>


    <<the pins of a member and the version presented>>


    <<order the members of a collection by date>>


    <<write a new version of the main collection>>

The documents and their current versions
----------------------------------------

A [mirror](21-mirrors.md) is a copy, in this storage root, of another
archive's object, and stays that archive's object: its `object.json` files
keep naming the original archive (section 10.4). That is how the tools
recognise it, from the head: the function returns the identifier of the
original archive, which the [discovery document](16-index.md) writes as
`mirrorOf`, or `None` for an object of this archive.

    # in the documents of the archive with their current versions:
    def mirror_of(obj_dir, inv):
        """The archive whose object this one mirrors (section 10.4), or None."""
        aid = read_json(obj_dir, inv, OBJ).get("archiveId")
        return aid if aid != ARCHIVE["archiveId"] else None

The documents of the archive are the objects of kind `document` that
belong to it. Collections are left out, and so are mirrors, which share
the storage root but are not the archive's own. For each document, the
function returns the object version holding its
[current version](11-versions.md), with that version's two descriptions:
what readers are shown, and what the citation cached in the main
collection is made from.

    # in the documents of the archive with their current versions:
    def documents():
        """(obj_id, dir, inventory, current object version, its object.json and
        datacite.json) of every document."""
        out = []
        for obj_id, d, inv in objects():
            if read_json(d, inv, OBJ)["kind"] != "document" or mirror_of(d, inv):
                continue  # collections, and mirrors of other archives' objects
            cur = current_version(d, inv)
            out.append((obj_id, d, inv, cur, read_json(d, inv, OBJ, cur), read_json(d, inv, "datacite.json", cur)))
        return out

The order
---------

`members.json` lists members in the order in which they are presented, and
that order is authoritative (section 10.2): a reader does not sort. A
collection may say by which rule its tools place members; the main
collection is newest first, by date, `issued-desc`.

    # in the order of the main collection:
    ORDER = "issued-desc"

The pins
--------

A member pins one object version in an archive collection, and one or more
in a selection, one per revision it vetted (section 10.2). Whatever reads
the pins of a member (verification, the website, the index) goes through
this function, which gives each as a triple: the object version, the digest
of its inventory and, for a revision, the document version it is stated to
hold.

    # in the pins of a member and the version presented:
    def member_pins(m):
        """[(object version, inventory digest, document version or None)] of a
        member: its version in an archive collection, each revision in a
        selection (section 10.2)."""
        if "revisions" in m:
            return [(r.get("version"), r.get("inventorySha512"), r.get("documentVersion"))
                    for r in m["revisions"]]
        return [(m.get("version"), m.get("inventorySha512"), None)]

Presentations show one version of each member. For a member of an archive
collection it is the current version, read from the history of the pinned
version (section 10.2), which is the head when the collection was made; for
a member of a selection it is the last revision of its set, the one
presented as the selection's.

    # in the pins of a member and the version presented:
    def presented_version(m, obj_dir, inv):
        """The object version presentations show for member M of an object held
        in OBJ_DIR (section 10.2)."""
        if m.get("revisions"):
            return m["revisions"][-1]["version"]
        return current_version(obj_dir, inv, m["version"])

Section 10.2 defines the rule so that every tool gets the same list: by the
`Issued` date (the first appearance of the work), then the `Available`
date, members with neither last, ties broken by object identifier. Python's
sort is stable, so sorting first by identifier and then by date gives the
ties in identifier order, ascending even when the dates are descending.

    # in order the members of a collection by date:
    def member_order(members):
        """Section 10.2: by Issued, then Available (newest first for issued-desc),
        members with neither last, ties broken by object identifier."""
        def key(m):
            c = m.get("cite", {})
            return (c.get("issued") or "", c.get("available") or "")
        dated = sorted((m for m in members if any(key(m))), key=lambda m: m["id"])
        dated.sort(key=key, reverse=(ORDER == "issued-desc"))
        return dated + sorted((m for m in members if not any(key(m))), key=lambda m: m["id"])

Writing a new version
---------------------

`osheaf collect` takes four steps, the last only if something changed.

    # in write a new version of the main collection:
    def collect(args):
        """A new version of the main collection when a document has a new object
        version; members pin the head of their object and follow it (an archive
        collection, section 10.2)."""
        <<leave a curated main collection to its curator>>
        <<pin the current version of every document of the archive>>
        <<stop if the main collection would not change>>
        <<write the files of the main collection's new version>>

A main collection whose order is `manual` is curated: its members and
their order are decisions of its curator, made with `osheaf collection`.

    # in leave a curated main collection to its curator:
    init_storage_root()
    coll_id = ARCHIVE["mainCollection"]
    cinv = load_inventory(OCFL / coll_id)
    if cinv and read_json(OCFL / coll_id, cinv, "members.json").get("order") == "manual":
        print(f"{coll_id} is curated (order manual): use osheaf collection sync|update")
        return

Each document becomes a member pinned at the head of its object, with
`follow: latest`: the main collection is an archive collection, which
follows its members whatever their new heads hold (a new document version,
a description, a notice, a withdrawal; section 10.2). Since the inventory
of the head lists every earlier version, the pin fixes the whole object as
it stands. The citation is that of the current version, which is what
presentations show. Each member carries a
cached citation (`cite`: title, authors, year, `Issued` date), so that the
collection stays readable, and can be ordered, without resolving its
members, also if one becomes unavailable (section 10.2). The `Available`
date (or `Created`, for a version not public at the time) is needed only to
order the members, and is removed afterwards: it describes a version, not
the work, and would make the citation change at every new version.

    # in pin the current version of every document of the archive:
    members = []
    for obj_id, d, inv, cur, obj, dc in documents():
        cite = {"title": dc["titles"][0]["title"],
                "creators": [display_name(c) for c in dc["creators"]],
                "year": dc["publicationYear"]}
        if date_of(dc, "Issued"):
            cite["issued"] = date_of(dc, "Issued")
        m = {"kind": "document", "archive": ARCHIVE["archiveId"], "archiveUrl": ARCHIVE["baseUrl"],
             "id": obj_id, "version": inv["head"], "inventorySha512": digest(d / inv["head"] / "inventory.json"),
             "follow": "latest", "cite": cite}
        # the Available date only orders, it is not part of the cached citation
        m["cite"]["available"] = date_of(dc, "Available", "Created")
        members.append(m)
    members = member_order(members)
    for m in members:
        m["cite"].pop("available", None)

The collection changes only when its members do: a new document, a new
object version of one (which changes the pin), a different order. A
collection written before `members.json` had a `type` also changes, once,
to gain it. Running `osheaf collect` with nothing new writes nothing, which
keeps the history of the collection meaningful. The document version of a
collection counts the changes of its member list (section 7.4), and the
`Issued` date of its first version is kept.

    # in stop if the main collection would not change:
    coll_dir = OCFL / coll_id
    inv = load_inventory(coll_dir)
    version, issued = 1, TODAY
    if inv:
        old = read_json(coll_dir, inv, "members.json")
        if old["members"] == members and old.get("type") == "archive":
            print(f"{coll_id}: unchanged ({inv['head']})")
            return
        version = read_json(coll_dir, inv, OBJ)["documentVersion"] + 1
        issued = date_of(read_json(coll_dir, inv, "datacite.json"), "Issued") or TODAY

The new version holds the three files of a collection (section 7.4).
`members.json` states that the collection is an archive collection
(section 10.2). Its `datacite.json` describes the archive as a whole: titled with the archive's
name, created by its curator, of type `Collection`, available today, under
CC0 like every member list (section 10.6). Its `object.json` has only the
fields common to all objects.

    # in write the files of the main collection's new version:
    cur = ARCHIVE["curator"]
    tmp = Path(tempfile.mkdtemp())
    write_json(tmp / "members.json", {"format": "opensheaf-collection/0.1", "type": "archive",
                                      "order": ORDER, "members": members})
    write_json(tmp / "datacite.json", {
        "titles": [{"title": ARCHIVE["name"]}],
        "creators": [{"name": cur["name"], "nameType": "Personal", "givenName": cur["givenName"],
                      "familyName": cur["familyName"], "affiliation": [{"name": cur["affiliation"]}]}],
        "publisher": {"name": ARCHIVE["name"]},
        "publicationYear": int(issued[:4]),
        "types": {"resourceTypeGeneral": "Collection"},
        "version": str(version),
        "url": ARCHIVE["baseUrl"],
        "dates": [{"date": issued, "dateType": "Issued"}, {"date": TODAY, "dateType": "Available"}],
        "descriptions": [{"description": "The documents deposited in this archive, newest first.",
                          "descriptionType": "Abstract"}],
        "rightsList": [dict(RIGHTS["cc0-1.0"])],
    })
    write_json(tmp / OBJ, {
        "format": OBJ_FORMAT, "specification": SPEC, "kind": "collection",
        "archiveId": ARCHIVE["archiveId"], "objectId": coll_id, "documentVersion": version,
        "status": "active",
    })
    inv = add_version(coll_id, {n: tmp / n for n in ("members.json", "datacite.json", OBJ)},
                      f"Collection version {version}: {len(members)} documents")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{coll_id}: {inv['head']} ({len(members)} members)")
