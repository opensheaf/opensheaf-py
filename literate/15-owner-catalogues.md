The owner catalogues
====================

The documents of an archive are listed by *owner catalogues* (section
8.1): each owner the archive hosts has there a catalogue of its own, an
object of kind `collection` whose `members.json` (section 8.2) names each
of the owner's documents in the archive by its line, `name` and `owner`,
and pins it, by an object version and the SHA-512 digest of that version's
inventory. It is a *catalogue*: it keeps the documents whole, every
version, without judging them, so each member pins the latest signed
version of its line, and follows it as it grows (section 8.3). The
collection is itself a line of its owner, like any object: each change of
the list is a new version, signed by that owner, so that the list at any
past moment can be recovered and checked. The index and the website are
made from the owner catalogues, in the order of the owners
([next chapter](16-index.md)), and other archives' collections can include
them.

Version 0.2 had at first one *main catalogue* per archive, a line of the
archive's owner listing the lines of every owner it hosts; a deposit by
another owner then needed a new version signed by the archive's owner.
Since #72 each owner keeps its own: a change by an owner touches its
catalogue only, and no owner signs for another. An owner catalogue is
sealed when the owner is set up in the archive: by
[`osheaf init`](18-init.md) for the archive's first owner, by
[`osheaf owner init`](19-owner-commands.md) for another. The discovery
document names it with its owner in `owners` (section 3.1), and the tools
read it from there (`CATALOGUES`, in the chapter on the
[archive](10-archive.md)). It lists the documents of the lines that its
owner writes in the archive, branches of its own included (section 9),
never the copies the archive holds of others' lines, and is never mirrored
(section 11).

This chapter is `osheaf collect`, which writes a new version of the owner
catalogues whose documents have changed, or, with `--owner`, of one
owner's. Collections curated by hand, with members of other archives, are
the subject of [collections](21-collections.md); an owner catalogue may be
one of those (a *curated* archive, `osheaf init --curated`), and then
`collect` leaves it alone.

    # in maintain the owner catalogues of the archive:
    <<the order of an owner catalogue>>


    <<the pins of a member and the version presented>>


    <<order the members of a collection by date>>


    <<write a new version of the owner catalogues>>

The documents and their current versions
----------------------------------------

The documents of an owner in the archive are the objects of kind
`document` of that owner, which the archive hosts (the configuration's
`owner` and `owners`); without an owner, those of every owner it hosts.
Collections, key logs and drafts are left out, and so are the lines of
other owners that the archive holds as copies (section 11). For
each document, the function returns the latest signed version of its line
(section 7.3), from which its history, current version and status are read
(section 4.2), the object version holding its
[current version](11-versions.md), and that version's two descriptions:
what readers are shown, and what the citation cached in the owner
catalogue is made from. A line without a signed version is left out, with
a warning: nothing relies on a version that is not signed (section 7.3).

    # in the documents of the archive with their current versions:
    def documents(owner=None):
        """(obj_id, dir, inventory, latest signed version, current object version, its
        object.json and datacite.json) of every document of OWNER, or of the archive's owners."""
        out, mine = [], {owner} if owner else set(archive_owners())
        for obj_id, d, inv in objects():
            if inv is None or obj_id is None or obj_id.startswith("sheaf:draft:"):
                continue
            head = read_json(d, inv, OBJ)
            if head.get("kind") != "document" or head.get("owner") not in mine:
                continue
            signed = latest_signed(d, inv)
            if signed is None:
                print(f"warning: {label_of(obj_id) or obj_id} has no signed version (section 7.3): left out",
                      file=sys.stderr)
                continue
            cur = current_version(d, inv, signed)
            out.append((obj_id, d, inv, signed, cur, read_json(d, inv, OBJ, cur),
                        read_json(d, inv, "datacite.json", cur)))
        return out

The order
---------

`members.json` lists members in the order in which they are presented, and
that order is authoritative (section 8.2): a reader does not sort. A
collection may say by which rule its tools place members; an owner
catalogue is newest first, by date, `issued-desc`.

    # in the order of an owner catalogue:
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

`osheaf collect` goes through the owners the archive hosts, in their
order, or takes the one `--owner` names, and gives each owner catalogue a
new version when its documents have changed. An owner whose catalogue
would not change signs nothing, so the command needs the keys of only the
owners whose documents changed: a deposit by one owner touches its
catalogue only.

An archive may host an owner whose keys this computer does not hold. Going
through all the owners, `collect` skips such an owner when its catalogue
would change: it says so on the standard error, with the reason and the
command that collects it on a computer that holds its keys, and goes on
with the others. Nothing of the skipped owner is written: the stop comes
from `signing_keys`, before the version is built, and the labels and
catalogues the command had noted for it in memory are put back. The
command still ends with an error, which names the owners skipped, so that
a script sees that the archive is not collected in full; but before it
ends it writes the website again, as `main` does after every command that
changes the archive ([chapter 60](60-command-line.md)), which it would not
do after a stop: the catalogues collected before the skipped owner would
otherwise be published with a stale `index.html`, which `osheaf verify`
reports. With `--owner`, an owner that cannot be signed for stops the
command as before: nothing has been added.

    # in write a new version of the owner catalogues:
    def collect(args):
        """A new version of each owner catalogue (or of that of --owner) whose documents have a new
        signed version; members pin the latest signed version of their line and follow it (section 8.3).
        Without --owner, an owner this computer cannot sign for is skipped, and the command ends with
        an error after writing the website for the others."""
        init_storage_root()
        only = getattr(args, "owner", None)
        if only and only not in archive_owners():
            sys.exit(f"{only} is not an owner this archive hosts")
        if only:
            collect_owner(only, args)
            return
        skipped = []
        for owner in archive_owners():
            noted = dict(LABELS), dict(CATALOGUES)
            try:
                collect_owner(owner, args)
            except CannotSign as e:
                for now, before in zip((LABELS, CATALOGUES), noted):
                    now.clear()
                    now.update(before)
                skipped.append(owner)
                warn(f"skipped the owner catalogue of {names.short(owner)}: {e.reason}; "
                     f"osheaf collect --owner {owner} collects it on a computer that holds its keys")
        if skipped:
            present()
            stop(f"{plural(len(skipped), 'owner catalogue')} not collected ("
                 + ", ".join(names.short(o) for o in skipped)
                 + "): this computer does not hold the keys to sign for "
                 + ("it" if len(skipped) == 1 else "them")
                 + "; the others are collected and the website is written")


    def collect_owner(owner, args):
        """A new version of the owner catalogue of OWNER when its documents have changed; its first
        version, sealed, when the owner has none yet."""
        <<leave a curated owner catalogue to its curator>>
        <<pin the current version of every document of the owner>>
        <<stop if the owner catalogue would not change>>
        <<write the files of the owner catalogue's new version>>

An owner catalogue whose order is `manual` is curated: its members and
their order are decisions of its curator, made with `osheaf collection`.
An owner catalogue not yet made (when the owner is set up) has no
identifier yet: it will be sealed below; `osheaf init --curated` asks for
it curated from the start, empty and of order `manual`. The catalogue of
the archive's first owner is labelled `main`, if that label is free; that
of another owner `<label>-catalogue`, after the label of the owner's key
log, if the owner has one and that label is free, and none otherwise: it
is then named by its identifier. `osheaf label --owner` labels it so when
the owner gets a label later (in the chapter on the
[archive](10-archive.md)).

    # in maintain the owner catalogues of the archive:
    def catalogue_label(owner):
        """The label the owner catalogue of OWNER is given: main for the archive's first owner,
        <owner label>-catalogue for another owner with a label, else None."""
        if owner == ARCHIVE["owner"]:
            return CATALOGUE_LABEL
        own = label_of(names.object_id(owner, owner))
        return f"{own}-catalogue" if own and len(own) <= 64 - len("-catalogue") else None

The owner catalogue of the owner is read from the discovery document; a
curated one is left to its curator.


    # in leave a curated owner catalogue to its curator:
    coll_id = CATALOGUES.get(owner)
    coll_dir = obj_dir(coll_id) if coll_id else None
    cinv = load_inventory(coll_dir) if coll_dir else None
    label = (label_of(coll_id) if coll_id else None) or names.short(owner)
    if cinv and read_json(coll_dir, cinv, "members.json").get("order") == "manual":
        print(f"{label} is curated (order manual): use osheaf collection add|sync|update")
        return
    curated = cinv is None and bool(getattr(args, "curated", False))
    order = "manual" if curated else ORDER

Each document becomes a member pinned at the latest signed version of its
line, with `follow: latest`: the owner catalogue follows its members
whatever their new versions hold (a new document version, a description, a
notice, a withdrawal; section 8.3), and pins only signed versions (section
8.5). Since the inventory of a version lists every earlier version, and
its `object.json` the digest of the inventory before it, the pin fixes the
whole object up to it. A member names its line by `name` and `owner`,
never by a label or a location, and lists in `at` where copies may be
found: the archive's base URL (section 8.2). The citation is that of the
current version, which is what presentations show. Each member carries a
cached citation (`cite`: title, authors, year, `Issued` date and
`Available` date), so that the collection stays readable, and can be
ordered, without resolving its members, also if one becomes unavailable
(section 8.2). The `Available` date (or `Created`, for a version not
public at the time) is that of the current version: it changes with a new
version of the member, which moves its pin anyway, and keeping it lets any
later sort of the written list give the same order.

    # in pin the current version of every document of the owner:
    members = []
    for obj_id, d, inv, signed, cur, obj, dc in documents(owner):
        cite = {"title": dc["titles"][0]["title"],
                "creators": [display_name(c) for c in dc["creators"]],
                "year": dc["publicationYear"]}
        if date_of(dc, "Issued"):
            cite["issued"] = date_of(dc, "Issued")
        m = {"kind": "document", "name": obj["name"], "owner": obj["owner"], "at": [ARCHIVE["baseUrl"]],
             "version": signed, "inventorySha512": digest(d / signed / "inventory.json"),
             "follow": "latest", "cite": cite}
        if date_of(dc, "Available", "Created"):
            m["cite"]["available"] = date_of(dc, "Available", "Created")
        members.append(m)
    members = [] if curated else member_order(members)

The collection changes only when its members do: a new document, a new
signed version of one (which changes the pin), a different order. Running
`osheaf collect` with nothing new writes nothing, which keeps the history
of the collection meaningful. The document version of a collection counts
the changes of its member list (section 4.2), and the `Issued` date of its
first version is kept.

    # in stop if the owner catalogue would not change:
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
version seals the catalogue as a work of its owner (section 10.2); later
ones carry its genesis record. Its `datacite.json` describes the owner's
documents in the archive: titled with the archive's name (followed, for an
owner other than the archive's first, by the owner's label or short name),
created by the archive's curator, of type `Collection`, available today,
under CC0 like every member list (section 8.6). Its `object.json` has only
the fields common to all objects, with the line. The version is signed by
the owner, and the discovery document, which names the catalogue in
`owners`, is rewritten.

    # in write the files of the owner catalogue's new version:
    if coll_id is None:
        genesis, coll_id = seal("collection", owner)
        wanted = catalogue_label(owner)
        if wanted and wanted not in LABELS:
            LABELS[wanted] = coll_id
    else:
        genesis = read_logical(coll_dir, cinv, GENESIS).read_bytes()
    CATALOGUES[owner] = coll_id
    title = ARCHIVE["name"]
    if owner != ARCHIVE["owner"]:
        title += ", " + (label_of(names.object_id(owner, owner)) or names.short(owner))
    cur = ARCHIVE["curator"]
    creator_ = {"name": cur["name"], "nameType": "Personal", "familyName": cur["familyName"]}
    if cur.get("givenName"):
        creator_["givenName"] = cur["givenName"]
    if cur.get("affiliation"):
        creator_["affiliation"] = [{"name": cur["affiliation"]}]
    files = {
        "members.json": json_bytes({"format": "opensheaf-collection/0.2", "type": "catalogue",
                                    "order": order, "members": members}),
        "datacite.json": json_bytes({
            "titles": [{"title": title}],
            "creators": [creator_],
            "publisher": {"name": ARCHIVE["name"]},
            "publicationYear": int(issued[:4]),
            "types": {"resourceTypeGeneral": "Collection"},
            "version": str(version),
            "url": ARCHIVE["baseUrl"],
            "dates": [{"date": issued, "dateType": "Issued"}, {"date": TODAY, "dateType": "Available"}],
            "descriptions": [{"description": "The documents of one owner deposited in this archive, "
                                             "newest first.", "descriptionType": "Abstract"}],
            "rightsList": [dict(RIGHTS["cc0-1.0"])],
        }),
        GENESIS: genesis,
    }
    obj = {"format": OBJ_FORMAT, "specification": SPEC, "kind": "collection",
           "name": coll_id.split(":")[1], "owner": owner, "documentVersion": version, "status": "active"}
    label = label_of(coll_id) or coll_id
    inv = add_version(coll_id, files, obj, f"Collection version {version}: {len(members)} documents",
                      acknowledged=bool(getattr(args, "i_know", False)))
    write_discovery()
    print(f"Done: the owner catalogue {label} of {names.short(owner)} is at {inv['head']}, with "
          f"{plural(len(members), 'member') if members else 'no members'}.")
