The main collection
===================

The documents of an archive are listed by its *main catalogue* (section
8.1): an object of kind `collection` whose `members.json` (section 8.2)
names each document by its line, `name` and `owner`, and pins it, by an
object version and the SHA-512 digest of that version's inventory. It is a
*catalogue*: it keeps the archive's documents whole, every version, without
judging them, so each member pins the latest signed version of its line,
and follows it as it grows (section 8.3). The collection is itself a line,
like any object: each change of the list is a new version, signed by its
owner, so that the list of an archive at any past moment can be recovered
and checked. The index and the website are made from it
([next chapter](16-index.md)), and other archives' collections can include
it.

An archive that makes collections does so as an owner (section 8.1): the
main catalogue is a line of the archive's owner, sealed when the archive is
[created](18-init.md), labelled by `mainCollection` of the configuration,
and named by its identifier in `mainCollection` of the discovery document.
It lists the documents of the lines that the archive's owners write in the
archive, never the copies it holds of others' lines.

This chapter is `osheaf collect`, which writes a new version of the main
catalogue when the documents have changed. Collections curated by hand,
with members of other archives, are the subject of
[collections](20-collections.md), not yet ported to specification 0.2; a
main collection may be one of those (a *curated* archive), and then
`collect` leaves it alone.

    # in maintain the main collection of the archive:
    <<the order of the main collection>>


    <<the pins of a member and the version presented>>


    <<order the members of a collection by date>>


    <<write a new version of the main collection>>

The documents and their current versions
----------------------------------------

The documents of the archive are the objects of kind `document` whose
owner is one of the archive's owners (the configuration's `owner` and
`owners`). Collections, key logs and drafts are left out, and so are the
lines of other owners that the archive holds as copies (section 11). For
each document, the function returns the latest signed version of its line
(section 7.3), from which its history, current version and status are read
(section 4.2), the object version holding its
[current version](11-versions.md), and that version's two descriptions:
what readers are shown, and what the citation cached in the main
catalogue is made from. A line without a signed version is left out, with
a warning: nothing relies on a version that is not signed (section 7.3).

    # in the documents of the archive with their current versions:
    def documents():
        """(obj_id, dir, inventory, latest signed version, current object version, its
        object.json and datacite.json) of every document of the archive's owners."""
        out, mine = [], set(archive_owners())
        for obj_id, d, inv in objects():
            if inv is None or obj_id is None or obj_id.startswith("sheaf:draft:"):
                continue
            head = read_json(d, inv, OBJ)
            if head.get("kind") != "document" or head.get("owner") not in mine:
                continue
            signed = latest_signed(d, inv)
            if signed is None:
                print(f"warning: {label_of(obj_id) or obj_id} has no signed version (section 7.3): left out")
                continue
            cur = current_version(d, inv, signed)
            out.append((obj_id, d, inv, signed, cur, read_json(d, inv, OBJ, cur),
                        read_json(d, inv, "datacite.json", cur)))
        return out

The order
---------

`members.json` lists members in the order in which they are presented, and
that order is authoritative (section 8.2): a reader does not sort. A
collection may say by which rule its tools place members; the main
catalogue is newest first, by date, `issued-desc`.

    # in the order of the main collection:
    ORDER = "issued-desc"

The pins
--------

A member pins one object version in a catalogue, and one or more
in a selection, one per revision it vetted (section 8.4). Whatever reads
the pins of a member (verification, the website, the index) goes through
this function, which gives each as a triple: the object version, the digest
of its inventory and, for a revision, the document version it is stated to
hold.

    # in the pins of a member and the version presented:
    def member_pins(m):
        """[(object version, inventory digest, document version or None)] of a
        member: its version in a catalogue, each revision in a
        selection (section 8.4)."""
        if "revisions" in m:
            return [(r.get("version"), r.get("inventorySha512"), r.get("documentVersion"))
                    for r in m["revisions"]]
        return [(m.get("version"), m.get("inventorySha512"), None)]

Presentations show one version of each member. For a member of a catalogue
it is the current version, read from the history of the pinned version
(section 8.3), which is the latest signed version when the collection was
made; for a member of a selection it is the last revision of its set, the
one presented as the selection's.

    # in the pins of a member and the version presented:
    def presented_version(m, obj_dir, inv):
        """The object version presentations show for member M of an object held
        in OBJ_DIR (section 8.3)."""
        if m.get("revisions"):
            return m["revisions"][-1]["version"]
        return current_version(obj_dir, inv, m["version"])

Section 8.2 defines the rule so that every tool gets the same list: by the
`Issued` date (the first appearance of the work), then the `Available`
date, members with neither last, ties broken by `name` and then `owner`.
Python's sort is stable, so sorting first by line and then by date gives
the ties in the order of the lines, ascending even when the dates are
descending.

    # in order the members of a collection by date:
    def member_order(members):
        """Section 8.2: by Issued, then Available (newest first for issued-desc),
        members with neither last, ties broken by name and then owner."""
        def key(m):
            c = m.get("cite", {})
            return (c.get("issued") or "", c.get("available") or "")
        line = lambda m: (m.get("name", ""), m.get("owner", ""))
        dated = sorted((m for m in members if any(key(m))), key=line)
        dated.sort(key=key, reverse=(ORDER == "issued-desc"))
        return dated + sorted((m for m in members if not any(key(m))), key=line)

Writing a new version
---------------------

`osheaf collect` takes four steps, the last only if something changed.

    # in write a new version of the main collection:
    def collect(args):
        """A new version of the main catalogue when a document has a new signed version;
        members pin the latest signed version of their line and follow it (section 8.3)."""
        <<leave a curated main collection to its curator>>
        <<pin the current version of every document of the archive>>
        <<stop if the main collection would not change>>
        <<write the files of the main collection's new version>>

A main collection whose order is `manual` is curated: its members and
their order are decisions of its curator, made with `osheaf collection`.
A main catalogue not yet made (by `osheaf init`, which calls this command)
has no identifier yet: it will be sealed below.

    # in leave a curated main collection to its curator:
    init_storage_root()
    label = ARCHIVE["mainCollection"]
    coll_id = LABELS.get(label)
    coll_dir = obj_dir(coll_id) if coll_id else None
    cinv = load_inventory(coll_dir) if coll_dir else None
    if cinv and read_json(coll_dir, cinv, "members.json").get("order") == "manual":
        print(f"{label} is curated (order manual): use osheaf collection sync|update")
        return

Each document becomes a member pinned at the latest signed version of its
line, with `follow: latest`: the main catalogue follows its members whatever
their new versions hold (a new document version, a description, a notice,
a withdrawal; section 8.3), and pins only signed versions (section 8.5).
Since the inventory of a version lists every earlier version, and its
`object.json` the digest of the inventory before it, the pin fixes the
whole object up to it. A member names its line by `name` and `owner`,
never by a label or a location, and lists in `at` where copies may be
found: the archive's base URL (section 8.2). The citation is that of the
current version, which is what presentations show. Each member carries a
cached citation (`cite`: title, authors, year, `Issued` date), so that the
collection stays readable, and can be ordered, without resolving its
members, also if one becomes unavailable (section 8.2). The `Available`
date (or `Created`, for a version not public at the time) is needed only to
order the members, and is removed afterwards: it describes a version, not
the work, and would make the citation change at every new version.

    # in pin the current version of every document of the archive:
    members = []
    for obj_id, d, inv, signed, cur, obj, dc in documents():
        cite = {"title": dc["titles"][0]["title"],
                "creators": [display_name(c) for c in dc["creators"]],
                "year": dc["publicationYear"]}
        if date_of(dc, "Issued"):
            cite["issued"] = date_of(dc, "Issued")
        m = {"kind": "document", "name": obj["name"], "owner": obj["owner"], "at": [ARCHIVE["baseUrl"]],
             "version": signed, "inventorySha512": digest(d / signed / "inventory.json"),
             "follow": "latest", "cite": cite}
        # the Available date only orders, it is not part of the cached citation
        m["cite"]["available"] = date_of(dc, "Available", "Created")
        members.append(m)
    members = member_order(members)
    for m in members:
        m["cite"].pop("available", None)

The collection changes only when its members do: a new document, a new
signed version of one (which changes the pin), a different order. Running
`osheaf collect` with nothing new writes nothing, which keeps the history
of the collection meaningful. The document version of a collection counts
the changes of its member list (section 4.2), and the `Issued` date of its
first version is kept.

    # in stop if the main collection would not change:
    version, issued = 1, TODAY
    if cinv:
        old = read_json(coll_dir, cinv, "members.json")
        if old["members"] == members and old.get("type") == "catalogue":
            print(f"{label}: unchanged ({cinv['head']})")
            return
        version = read_json(coll_dir, cinv, OBJ)["documentVersion"] + 1
        issued = date_of(read_json(coll_dir, cinv, "datacite.json"), "Issued") or TODAY

The new version holds the files of a collection (section 8.2):
`members.json`, which states that the collection is a catalogue, its
`datacite.json` and its `object.json`, with its genesis record. The first
version seals the catalogue as a work of the archive's owner (section 10.2);
later ones carry its genesis record. Its `datacite.json` describes the
archive as a whole: titled with the archive's name, created by its curator,
of type `Collection`, available today, under CC0 like every member list
(section 8.6). Its `object.json` has only the fields common to all objects,
with the line. The version is signed by the archive's owner, and the
discovery document is rewritten.

    # in write the files of the main collection's new version:
    owner = ARCHIVE["owner"]
    if coll_id is None:
        genesis, coll_id = seal("collection", owner)
    else:
        genesis = read_logical(coll_dir, cinv, GENESIS).read_bytes()
    cur = ARCHIVE["curator"]
    creator_ = {"name": cur["name"], "nameType": "Personal", "familyName": cur["familyName"]}
    if cur.get("givenName"):
        creator_["givenName"] = cur["givenName"]
    if cur.get("affiliation"):
        creator_["affiliation"] = [{"name": cur["affiliation"]}]
    files = {
        "members.json": json_bytes({"format": "opensheaf-collection/0.2", "type": "catalogue",
                                    "order": ORDER, "members": members}),
        "datacite.json": json_bytes({
            "titles": [{"title": ARCHIVE["name"]}],
            "creators": [creator_],
            "publisher": {"name": ARCHIVE["name"]},
            "publicationYear": int(issued[:4]),
            "types": {"resourceTypeGeneral": "Collection"},
            "version": str(version),
            "url": ARCHIVE["baseUrl"],
            "dates": [{"date": issued, "dateType": "Issued"}, {"date": TODAY, "dateType": "Available"}],
            "descriptions": [{"description": "The documents deposited in this archive, newest first.",
                              "descriptionType": "Abstract"}],
            "rightsList": [dict(RIGHTS["cc0-1.0"])],
        }),
        GENESIS: genesis,
    }
    obj = {"format": OBJ_FORMAT, "specification": SPEC, "kind": "collection",
           "name": coll_id.split(":")[1], "owner": owner, "documentVersion": version, "status": "active"}
    LABELS[label] = coll_id
    inv = add_version(coll_id, files, obj, f"Collection version {version}: {len(members)} documents",
                      acknowledged=bool(getattr(args, "i_know", False)))
    write_discovery()
    print(f"{label}: {inv['head']} ({len(members)} members)")
