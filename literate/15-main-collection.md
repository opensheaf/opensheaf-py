The main collection
===================

The documents of an archive are listed by its *main collection*: an object
of kind `collection` whose `members.json` (section 10) names each document
and pins it, by an object version and the SHA-512 digest of that version's
inventory. The collection is itself versioned, like any object: each change
of the list is a new version, so that the list of an archive at any past
moment can be recovered and checked. The index and the website are made
from it ([next chapter](16-index.md)), and other archives' collections can
include it.

This chapter is `osheaf collect`, which writes a new version of the main
collection when the documents have changed. Collections curated by hand,
with members of other archives, are the subject of
[collections](20-collections.md); a main collection may be one of those
(a *curated* archive), and then `collect` leaves it alone.

    # in maintain the main collection of the archive:
    <<the order of the main collection>>


    <<order the members of a collection by date>>


    <<write a new version of the main collection>>

The documents and their current versions
----------------------------------------

The documents of the archive are the objects of kind `document` that
belong to it. Collections are left out, and so are objects whose head names
another archive: [mirrors](21-mirrors.md) of other archives' objects,
which share the storage root but are not the archive's own. For each
document, the function returns the object version holding its
[current version](11-versions.md), with that version's two descriptions:
what readers are shown. The [website](30-website.md) uses it too.

    # in the documents of the archive with their current versions:
    # ---------------------------------------------------------------------------
    # Collection

    def documents():
        """(obj_id, dir, inventory, current object version, its object.json and
        datacite.json) of every document."""
        out = []
        for obj_id, d, inv in objects():
            head = read_json(d, inv, OBJ)
            if head["kind"] != "document" or head.get("archiveId") != ARCHIVE["archiveId"]:
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

Section 10.2 defines the rule so that every tool gets the same list: by the
`Issued` date (the first appearance of the work), then the `Available`
date, members with neither last, ties broken by object identifier. Python's
sort is stable, so sorting first by identifier and then by date gives the
ties in identifier order, ascending even when the dates are descending.

    # in order the members of a collection by date:
    def member_order(members):
        """Section 10: by Issued, then Available (newest first for issued-desc),
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
        """A new version of the main collection when a document has a new current
        version or a new description of it; members pin the object version
        holding the current version."""
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

Each document becomes a member pinned at the object version holding its
current version, with `follow: latest`, so that collections of other
archives that include it know that it moves forward. Each member carries a
cached citation (`cite`: title, authors, year, `Issued` date), so that the
collection stays readable, and can be ordered, without resolving its
members, also if one becomes unavailable (section 10.2). The `Available`
date (or `Created`, for a version not public at the time) is needed only to
order the members, and is removed afterwards: it describes a version, not
the work, and would make the citation change at every new version.

The specification was amended since this code was written: a collection
is now an archive collection or a selection, and `members.json` says which
(`type`); the main collection is an archive collection, whose members pin
the *head* of each object and follow the head (section 10.2), whatever it
holds. These tools write no `type`, and pin the object version holding the
current version, which differs from the head only after an earlier version
was deposited later, described or completed.

    # in pin the current version of every document of the archive:
    members = []
    for obj_id, d, inv, cur, obj, dc in documents():
        cite = {"title": dc["titles"][0]["title"],
                "creators": [display_name(c) for c in dc["creators"]],
                "year": dc["publicationYear"]}
        if date_of(dc, "Issued"):
            cite["issued"] = date_of(dc, "Issued")
        m = {"kind": "document", "archive": ARCHIVE["archiveId"], "archiveUrl": ARCHIVE["baseUrl"],
             "id": obj_id, "version": cur, "inventorySha512": digest(d / cur / "inventory.json"),
             "follow": "latest", "cite": cite}
        # the Available date only orders, it is not part of the cached citation
        m["cite"]["available"] = date_of(dc, "Available", "Created")
        members.append(m)
    members = member_order(members)
    for m in members:
        m["cite"].pop("available", None)

The collection changes only when its members do: a new document, a new
version, a description-only version (which changes the pin), a different
order. Running `osheaf collect` with nothing new writes nothing, which
keeps the history of the collection meaningful. The document version of a
collection counts the changes of its member list (section 7.4), and the
`Issued` date of its first version is kept.

    # in stop if the main collection would not change:
    coll_dir = OCFL / coll_id
    inv = load_inventory(coll_dir)
    version, issued = 1, TODAY
    if inv:
        old = read_json(coll_dir, inv, "members.json")
        if old["members"] == members:
            print(f"{coll_id}: unchanged ({inv['head']})")
            return
        version = read_json(coll_dir, inv, OBJ)["documentVersion"] + 1
        issued = date_of(read_json(coll_dir, inv, "datacite.json"), "Issued") or TODAY

The new version holds the three files of a collection (section 7.4). Its
`datacite.json` describes the archive as a whole: titled with the archive's
name, created by its curator, of type `Collection`, available today, under
CC0 like every member list (section 10.6). Its `object.json` has only the
fields common to all objects.

    # in write the files of the main collection's new version:
    cur = ARCHIVE["curator"]
    tmp = Path(tempfile.mkdtemp())
    write_json(tmp / "members.json", {"format": "opensheaf-collection/0.1", "order": ORDER,
                                      "members": members})
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
