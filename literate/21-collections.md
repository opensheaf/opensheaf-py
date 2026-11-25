Collections across archives
===========================

An OpenSheaf archive lists the documents of each owner it hosts in that
owner's *owner catalogue*, which `osheaf collect` builds from the documents
deposited ([chapter 15](15-owner-catalogues.md)). This chapter is about the
collections a curator composes: a reading list, the papers of a group, the
issue of a journal. Their members may be lines of this archive or of any
other, each fixed by a pin, so that a collection states exactly what it
contains even when its members belong to archives the curator does not
control (section 8). The module is `collections.py`; it finds the members
with the [resolver](20-resolution.md).

What a collection is
--------------------

A collection is a line like any other (section 8): an object of kind
`collection`, signed by its owner, its *curator*, whose versions hold
`members.json`, the list of members, besides `datacite.json`,
`object.json` and the genesis record. What it contains changes only by a
new version, and its document version counts the changes of its member
list (section 4.2).

Each member is a line of a document or of another collection, in any
archive, named by `name` and `owner`, by which copies are found and
checked against its owner's signatures, never by a label or a location;
`at` lists base URLs where copies may be found, mirrors included, equal
hints that need no signature (section 8.2). A member also carries `cite`,
a cached citation, not authoritative, so that the collection can be read
and ordered without resolving it.

Collections are of two types (section 8.1):

- a **catalogue** keeps objects whole and is impartial about their
  versions: each member pins an object version, `version` and
  `inventorySha512`, which fixes the object with all its versions up to
  it. A member may have `follow: latest`, a setting of the curator: its
  tool moves the pin to the latest signed version of the line when the
  line grows, whatever that version holds (section 8.3);
- a **selection** vets particular versions, a journal the version it
  accepted, a reading list the one it recommends: each member pins a
  *revision set*, the document versions the curator vetted, each by the
  object version that held it and its digest, in the order of the
  member's history (section 8.4). Tools never change revision sets on
  their own: adding or removing a revision is the curator's act, a new
  version of the selection.

```json
{
  "format": "opensheaf-collection/0.2",
  "type": "catalogue",
  "order": "manual",
  "members": [
    { "kind": "document",
      "name": "zzgdggwlldcrw4bdeuvntiaobtw2kge6bc4go737pfekhfc5oz4q",
      "owner": "56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa",
      "at": [ "https://mgubi.org/papers/" ],
      "version": "v2", "inventorySha512": "e3e1…", "follow": "latest",
      "cite": { "title": "…", "creators": [ "P. Duch", "M. Gubinelli" ], "year": 2026,
                "available": "2026-03-02" } }
  ]
}
```

A collection pins only signed versions, never a draft (section 8.5); and
since a pin fixes an inventory, which fixes every file and every earlier
version, a collection version fixes everything it contains, also across
archives: collections are hash trees.

The statuses of members
-----------------------

Whoever reads a collection resolves its members as section 12.3 says, from
their `at` and the places it knows, and reports for each member (each
revision, in a selection) one of the statuses of section 8.5: *verified*,
*contested*, *mismatch*, *unchecked*, *not a version*, *unavailable*,
*removed*. The [resolver](20-resolution.md) computes them (`Resolver.pin`);
`osheaf collection status` prints them, and `osheaf verify --remote`
reports them as findings (section 14.5).

The commands
------------

```
osheaf collection new LABEL --type catalogue|selection --title TITLE [--description TEXT]
                            [--order manual|issued-desc|issued-asc] [--owner OWNER]
osheaf collection add LABEL URI... [--at URL]... [--follow] [--revision N]...
osheaf collection remove LABEL URI... [--revision N]...
osheaf collection follow LABEL URI... [--off]
osheaf collection update [LABEL...]
osheaf collection status LABEL
osheaf collection sync LABEL --from collection.yaml
```

A member is given by a `sheaf:` URI, whose `at` is tried first, or by the
label of a line of this archive. `add` pins the latest signed version of
the line (in a catalogue), or the current version of its latest signed
version, or the document versions `--revision` names (in a selection),
unless the URI is a pin, which is taken as it is; `follow` sets or clears
`follow: latest`; `update` follows the members that follow their lines,
and reports for a selection the document versions it has not vetted;
`sync` writes a collection from a file, which states its members in the
curator's order:

```yaml
title: Reading list
description: Papers to read first.
type: catalogue              # or selection
order: manual
members:
  - sheaf:zzgdggwlldcrw4bdeuvntiaobtw2kge6bc4go737pfekhfc5oz4q?at=https%3A%2F%2Fmgubi.org%2Fpapers%2F
  - {uri: "sheaf:…:…", at: [https://journal.example.org/], follow: yes}
  - {label: my-paper, revisions: [1, 2]}
```

A member already in the collection keeps its pin, unless the entry pins
another version or names other revisions; a new member is pinned as `add`
does.

The module
----------

    # in src/opensheaf/collections.py:
    """Collections across archives (section 8 of OpenSheaf 0.2): catalogues and selections whose
    members are lines of any archive, pinned; members resolved from their at and checked; followed
    members moved to the latest signed version extending their pin; statuses of section 8.5.

        osheaf collection new LABEL --type catalogue|selection --title TITLE [--description TEXT]
        osheaf collection add LABEL URI... [--at URL]... [--follow] [--revision N]...
        osheaf collection remove LABEL URI... [--revision N]...
        osheaf collection follow LABEL URI... [--off]
        osheaf collection update [LABEL...]
        osheaf collection status LABEL
        osheaf collection sync LABEL --from collection.yaml
    """

    import json
    import sys

    from . import core as P, names, remote

    KINDS = ("catalogue", "selection")
    ORDERS = ("manual", "issued-desc", "issued-asc")
    FORMAT = "opensheaf-collection/0.2"


    <<collections: the collections of the archive>>


    <<collections: members and revisions>>


    <<collections: writing a collection version>>


    <<collections: finding the version a member pins>>


    <<collections: the commands>>

The collections of the archive
------------------------------

A command names a collection by its label. It must be a collection of an
owner this archive hosts, since a new version is signed by its owner.

    # in collections: the collections of the archive:
    def held(label):
        """(identifier, folder, inventory, members.json) of the collection LABEL of this archive."""
        coll_id = P.resolve(label)
        d = P.obj_dir(coll_id)
        inv = P.load_inventory(d)
        head = P.read_json(d, inv, P.OBJ) or {}
        if head.get("kind") != "collection":
            sys.exit(f"{label} is not a collection")
        if head.get("owner") not in P.archive_owners():
            sys.exit(f"{label} is a collection of an owner this archive does not host")
        return coll_id, d, inv, P.read_json(d, inv, "members.json")

Members and revisions
---------------------

The member record of a line, from a copy of it in the folder `d`: its kind
and line; where copies are found; the pin of a catalogue, or the revision
set of a selection; the DOI of the version; the cached citation of the
current version as of the version pinned (section 8.3: presentations show
the current version read from the history of the version pinned).

    # in collections: members and revisions:
    def cite(d, inv, k):
        """The cached citation (section 8.2) of the line held in D, as of its version vK."""
        dc = P.read_json(d, inv, "datacite.json", P.current_version(d, inv, f"v{k}")) or {}
        out = {"title": dc.get("titles", [{}])[0].get("title", ""),
               "creators": [P.display_name(c) for c in dc.get("creators", [])]}
        if isinstance(dc.get("publicationYear"), int):
            out["year"] = dc["publicationYear"]
        if P.date_of(dc, "Issued"):
            out["issued"] = P.date_of(dc, "Issued")
        if P.date_of(dc, "Available", "Created"):
            out["available"] = P.date_of(dc, "Available", "Created")
        return out


    def revision(d, inv, k):
        """The revision (section 8.4) of the document version vK holds."""
        obj = P.read_json(d, inv, P.OBJ, f"v{k}")
        dc = P.read_json(d, inv, "datacite.json", f"v{k}") or {}
        out = {"documentVersion": obj["documentVersion"], "version": f"v{k}",
               "inventorySha512": P.digest(d / f"v{k}" / "inventory.json")}
        if dc.get("doi"):
            out["doi"] = dc["doi"]
        return out


    def member_record(kind, d, inv, k, nm, owner, at, follow=False):
        """The member of a collection of type KIND for the line (NM, OWNER) pinned at vK of its copy in D."""
        obj = P.read_json(d, inv, P.OBJ, f"v{k}")
        dc = P.read_json(d, inv, "datacite.json", f"v{k}") or {}
        m = {"kind": obj["kind"], "name": nm, "owner": owner, "at": list(at)}
        if kind == "catalogue":
            m.update(version=f"v{k}", inventorySha512=P.digest(d / f"v{k}" / "inventory.json"))
            if follow:
                m["follow"] = "latest"
        else:
            m["revisions"] = [revision(d, inv, k)]
        if dc.get("doi") and kind == "catalogue":
            m["doi"] = dc["doi"]
        m["cite"] = cite(d, inv, k)
        return m

Revisions are kept in the order of the member's history (section 8.4), as
the history of the latest signed version gives it; document versions it
does not list (a history not yet known) go after, by number.

    # in collections: members and revisions:
    def history_order(c):
        """The document versions of the copy C in the order of its latest signed version's history."""
        if not c.latest_signed:
            return []
        return [P.doc_version_of(c.dir, c.inv, h) for h in P.history_of(c.dir, c.inv, f"v{c.latest_signed}")]


    def sort_revisions(revs, order):
        return sorted(revs, key=lambda x: (order.index(x["documentVersion"]) if x["documentVersion"] in order
                                           else len(order) + x["documentVersion"]))

Writing a collection version
----------------------------

A new version of a collection holds its `members.json`, its
`datacite.json` and its genesis record. The members are placed by the
collection's `order`: in `manual` order as the curator gave them, or by
date, as the owner catalogues order them (section 8.2). The document
version goes up only when the member list changes (section 4.2); a change
of the title or description alone is a description-only version. Nothing
is written when nothing changes.

The description (section 8.6): the title and abstract given, the curator
of the archive as creator, the archive as publisher, the type
`Collection`, a `HasPart` relation to the version DOI of every member and
revision that has one, and CC0, since a collection holds only metadata.

    # in collections: writing a collection version:
    def describe(title, description, version, issued, members, url=None):
        cur = P.ARCHIVE["curator"]
        creator = {"name": cur["name"], "nameType": "Personal", "familyName": cur["familyName"]}
        if cur.get("givenName"):
            creator["givenName"] = cur["givenName"]
        dc = {"titles": [{"title": title}], "creators": [creator], "publisher": {"name": P.ARCHIVE["name"]},
              "publicationYear": int(issued[:4]), "types": {"resourceTypeGeneral": "Collection"},
              "version": str(version),
              "dates": [{"date": issued, "dateType": "Issued"}, {"date": P.TODAY, "dateType": "Available"}],
              "rightsList": [dict(P.RIGHTS["cc0-1.0"])]}
        if url:
            dc["url"] = url
        if description:
            dc["descriptions"] = [{"description": description, "descriptionType": "Abstract"}]
        dois = [m["doi"] for m in members if m.get("doi")] + \
            [r["doi"] for m in members for r in m.get("revisions", []) if r.get("doi")]
        if dois:
            dc["relatedIdentifiers"] = [{"relatedIdentifier": x, "relatedIdentifierType": "DOI",
                                         "relationType": "HasPart"} for x in dict.fromkeys(dois)]
        return dc


    def write(coll_id, mem, *, message, title=None, description=None, owner=None, label=None):
        """Write a new version of the collection COLL_ID with MEM as members.json (a new collection if
        it does not exist yet); returns the inventory, or None if nothing changed."""
        d = P.obj_dir(coll_id) if coll_id else None
        inv = P.load_inventory(d) if d else None
        mem = dict(mem)
        if mem.get("order", "manual") != "manual":
            P.ORDER, saved = mem["order"], P.ORDER
            try:
                mem["members"] = P.member_order(mem["members"])
            finally:
                P.ORDER = saved
        version, issued, genesis = 1, P.TODAY, None
        if inv:
            old_mem = P.read_json(d, inv, "members.json")
            old_dc = P.read_json(d, inv, "datacite.json") or {}
            old_title = old_dc.get("titles", [{}])[0].get("title")
            old_desc = next((x["description"] for x in old_dc.get("descriptions", [])
                             if x.get("descriptionType") == "Abstract"), None)
            title = title if title is not None else old_title
            description = description if description is not None else old_desc
            version = P.read_json(d, inv, P.OBJ)["documentVersion"]
            if old_mem != mem:
                version += 1
            elif (title, description) == (old_title, old_desc):
                print(f"{P.label_of(coll_id) or coll_id}: unchanged ({inv['head']})")
                return None
            issued = P.date_of(old_dc, "Issued") or P.TODAY
            genesis = P.read_logical(d, inv, P.GENESIS).read_bytes()
            owner = coll_id.split(":")[2]
        else:
            genesis, coll_id = P.seal("collection", owner)
        label = label or P.label_of(coll_id)
        files = {"members.json": P.json_bytes(mem), P.GENESIS: genesis,
                 "datacite.json": P.json_bytes(describe(title, description, version, issued, mem["members"],
                                                        P.landing_url(coll_id) if label else None))}
        obj = {"format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": "collection",
               "name": coll_id.split(":")[1], "owner": owner, "documentVersion": version, "status": "active"}
        if label:
            P.LABELS[label] = coll_id
        inv = P.add_version(coll_id, files, obj, message)
        P.write_discovery()
        n = len(mem["members"])
        print(f"Done: the collection {label or coll_id} is at {inv['head']}, document version {version}, with "
              f"{P.plural(n, 'member') if n else 'no members'}.")
        return inv

Finding the version a member pins
---------------------------------

A member is given by a URI or a label. A label of this archive names a
line held here, whose `at` is the archive's base URL. A URI is resolved:
its `at` first, then the places given with `--at`, then the archive's own
storage root. The locations recorded in `at` are the `https` base URLs
among them, and that of the archive where the copy was found, when it has
one; a member needs at least one (section 8.2).

The version pinned is the URI's pin if it has one; otherwise, in a
catalogue, the latest signed version of the line; in a selection, each
document version `--revision` names, or else the current version of the
latest signed version; a document version named twice is pinned once,
since a selection vets each revision once (section 8.4). Only a verified
version is pinned: a collection pins only signed versions, and a contested one is never a verified member
(sections 7.3 and 8.5). The current version of a selection's member is
checked as the resolver checks the version it resolves to: a copy that
does not hold every file of it, with its digest, pins nothing
(`Resolver.contents`, [resolution](20-resolution.md)).

    # in collections: finding the version a member pins:
    def target(r, text, where):
        """(name, owner, the URI or None, the places to try) of the member TEXT (a URI or a label)."""
        if text in P.LABELS:
            _, nm, owner = P.LABELS[text].split(":")
            return nm, owner, None, ["here"]
        try:
            u = names.parse_sheaf(text, short=True, fold=True)
            places = r.where(([u.at] if u.at else []) + list(where))
            nm, owner = r.expand(u, places)
        except ValueError as e:
            sys.exit(str(e))
        return nm, owner, u, places


    def https_bases(places):
        """The https base URLs among PLACES, the only ones a member records in at (section 8.2)."""
        return [w for w in places if isinstance(w, str) and w.startswith("https://") and w.endswith("/")]


    def recorded_at(found, places):
        """The base URLs a member records in at (section 8.2)."""
        out = https_bases(places)
        c = found.copy
        if c is not None and c.where == "here":
            out.append(P.ARCHIVE["baseUrl"])
        elif c is not None and c.src is not None and c.src.at:
            out.append(c.src.at)
        return list(dict.fromkeys(out))


    def pinned(r, nm, owner, u, places, kind, revisions=()):
        """[Found] of the versions to pin for a member: one in a catalogue, one per revision."""
        revisions = list(dict.fromkeys(revisions))
        if u is not None and u.sha512:
            founds = [r.resolve(str(u), places)[1]]
        elif kind == "selection" and revisions:
            founds = [r.document_version(nm, owner, n, places) for n in revisions]
        else:
            found = r.latest(nm, owner, places)
            if kind == "selection" and found.copy is not None:
                c = found.copy
                cur = P.current_version(c.dir, c.inv, found.version)
                found = remote.Found(remote.MEMBER_STATUS.get(c.status(int(cur[1:])), "not a version"), c, cur,
                                     c.digest(int(cur[1:])), found.copies)
                if found.ok and r.contents(c, int(cur[1:])):
                    found = remote.Found("unavailable", None, None, None, found.copies)
            founds = [found]
        for f in founds:
            if f.status != "verified" or f.copy is None:
                notes = "; ".join(m for _, m in r.notes)
                sys.exit(f"sheaf:{nm}:{owner}: {f.status}" + (f" ({notes})" if notes else "")
                         + ": a collection pins only verified versions (section 8.5)")
        return founds

The commands
------------

`new` makes an empty collection, of the type given, signed by the
archive's owner or another it hosts; its label names it in the archive.

    # in collections: the commands:
    def new(args):
        if args.label in P.LABELS or not P.LABEL_RE.match(args.label or ""):
            sys.exit(f"{args.label}: a new label of the form of section 3.1")
        if args.type not in KINDS or not args.title:
            sys.exit("a new collection needs --type catalogue|selection and --title")
        owner = args.owner or P.ARCHIVE["owner"]
        if owner not in P.archive_owners():
            sys.exit(f"{owner} is not an owner this archive hosts")
        P.init_storage_root()
        mem = {"format": FORMAT, "type": args.type, "order": args.order or "manual", "members": []}
        write(None, mem, message=f"New {args.type}: {args.title}", title=args.title,
              description=args.description, owner=owner, label=args.label)

`add` adds members, or, in a selection, revisions to a member already
there; `remove` removes members, or only some revisions; `follow` sets or
clears `follow` on members of a catalogue. Each makes one new version, with
a message saying what was decided (section 8.4). With `--revision`, `remove`
removes those revisions of a selection's member and keeps the member with
the others, or removes it with its last one; it stops when nothing it names
is there to remove.

    # in collections: the commands:
    def add(args):
        coll_id, d, inv, mem = held(args.collection)
        kind, changed = mem["type"], []
        if kind == "catalogue" and args.revision:
            sys.exit("--revision is for selections: a catalogue pins one version of each member")
        with remote.Resolver(places=list(args.at or [])) as r:
            for text in args.uri:
                nm, owner, u, places = target(r, text, args.at or [])
                founds = pinned(r, nm, owner, u, places, kind, args.revision or ())
                at = recorded_at(founds[0], places)
                if not at:
                    sys.exit(f"{text}: no https base URL where copies are found: give --at URL (section 8.2)")
                c = founds[0].copy
                m = next((x for x in mem["members"] if (x["name"], x["owner"]) == (nm, owner)), None)
                if m is not None and kind == "catalogue":
                    sys.exit(f"{text} is a member already (osheaf collection follow, or update)")
                rest = founds
                if m is None:
                    m = member_record(kind, c.dir, c.inv, int(founds[0].version[1:]), nm, owner, at, args.follow)
                    mem["members"].append(m)
                    rest = founds[1:]
                if kind == "selection":
                    for f in rest:
                        rev = revision(f.copy.dir, f.copy.inv, int(f.version[1:]))
                        if all(x["documentVersion"] != rev["documentVersion"] for x in m["revisions"]):
                            m["revisions"].append(rev)
                    m["revisions"] = sort_revisions(m["revisions"], history_order(c))
                changed.append(f"sheaf:{nm}:{owner}")
        write(coll_id, mem, message=args.message or f"Added: {', '.join(changed)}")


    def matches(m, text):
        """Whether the member M is the line TEXT names (a URI, a label, or a prefix of a name)."""
        if text in P.LABELS:
            return P.LABELS[text] == names.object_id(m["name"], m["owner"])
        try:
            u = names.parse_sheaf(text, short=True, fold=True)
        except ValueError:
            return m["name"].startswith(text)
        return u.matches(m["name"], m["owner"])


    def remove(args):
        coll_id, d, inv, mem = held(args.collection)
        out, changed = [], False
        for m in mem["members"]:
            if not any(matches(m, t) for t in args.uri):
                out.append(m)
            elif args.revision and m.get("revisions"):
                kept = [x for x in m["revisions"] if x["documentVersion"] not in args.revision]
                changed = changed or len(kept) < len(m["revisions"])
                if kept:
                    out.append(dict(m, revisions=kept))
            else:
                changed = True
        if not changed:
            sys.exit("no member matches")
        mem["members"] = out
        write(coll_id, mem, message=args.message or f"Removed: {', '.join(args.uri)}")


    def follow(args):
        coll_id, d, inv, mem = held(args.collection)
        if mem["type"] != "catalogue":
            sys.exit("only the members of a catalogue follow their lines (section 8.3)")
        found = [m for m in mem["members"] if any(matches(m, t) for t in args.uri)]
        if not found:
            sys.exit("no member matches")
        for m in found:
            if args.off:
                m.pop("follow", None)
            else:
                m["follow"] = "latest"
        write(coll_id, mem, message=args.message or ("Not followed: " if args.off else "Followed: ")
              + ", ".join(args.uri))

### Following

`update` reads the archives of the members that follow their lines, and
moves each pin to the latest signed version of its line among the copies
that agree (section 8.3), with a fresh citation; whatever the new version
holds (a new document version, a description, a notice, a withdrawal), it
is followed. It never follows to a contested version, which is never the
latest signed version; nor to a copy whose version at the pin is not the
one pinned, which is a fork of the line, reported, the pin kept; nor,
once it knows that the owner's key log forks, to anything (section 7.5).
For a selection it only reports the document versions of the latest
signed version's history that are not vetted: changing a revision set is
the curator's act. Without a label, every collection of the archive's
owners is updated, but the owner catalogues kept by `osheaf collect`.

    # in collections: the commands:
    def update(args):
        labels = args.collection or [lb for lb, i in sorted(P.LABELS.items()) if is_curated(lb, i)]
        for label in labels:
            coll_id, d, inv, mem = held(label)
            changed = []
            with remote.Resolver() as r:
                for m in mem["members"]:
                    if mem["type"] == "selection":
                        report_unvetted(r, label, m)
                    elif m.get("follow") == "latest":
                        if follow_member(r, label, m):
                            changed.append(f"sheaf:{m['name']}:{m['owner']} {m['version']}")
                for s, msg in r.notes:
                    print(f"{s}: {msg}")
            if changed:
                write(coll_id, mem, message=f"Followed: {', '.join(changed)}")
            else:
                print(f"{label}: no member to follow further")


    def is_curated(label, obj_id):
        d = P.obj_dir(obj_id)
        inv = P.load_inventory(d)
        head = P.read_json(d, inv, P.OBJ) if inv else {}
        if (head or {}).get("kind") != "collection" or head.get("owner") not in P.archive_owners():
            return False
        mem = P.read_json(d, inv, "members.json") or {}
        return not (obj_id in P.CATALOGUES.values() and mem.get("order") != "manual")


    def follow_member(r, label, m):
        """Move the pin of the followed member M to the latest signed version extending it (section 8.3)."""
        log = r.key_log(m["owner"], r.where(m["at"]))
        if log is not None and log.fork_point:
            print(f"{label}: sheaf:{m['name']}:{m['owner']}: its owner's key log forks at v{log.fork_point}: "
                  "not followed (section 7.5)")
            return False
        found = r.latest(m["name"], m["owner"], m["at"])
        if found.copy is None:
            print(f"{label}: sheaf:{m['name']}:{m['owner']}: {found.status}: the pin is kept")
            return False
        c, k, old = found.copy, int(found.version[1:]), int(m["version"][1:])
        if c.digest(old) != m["inventorySha512"]:
            print(f"{label}: sheaf:{m['name']}:{m['owner']}: the copy at {c.where} does not extend the pin "
                  f"{m['version']}: a fork of the line (section 7.4); the pin is kept")
            return False
        if k <= old:
            return False
        m.update(version=f"v{k}", inventorySha512=c.digest(k), cite=cite(c.dir, c.inv, k))
        return True


    def report_unvetted(r, label, m):
        found = r.latest(m["name"], m["owner"], m["at"])
        if found.copy is None:
            return
        vetted = {x["documentVersion"] for x in m["revisions"]}
        rest = [n for n in history_order(found.copy) if n not in vetted]
        if rest:
            print(f"{label}: sheaf:{m['name']}:{m['owner']}: document version(s) "
                  f"{', '.join(map(str, rest))} not vetted")

### Statuses

`status` resolves every member, every revision in a selection, and prints
its status (section 8.5), with the notes of the resolver.

    # in collections: the commands:
    def statuses(mem, r):
        """[(member, version, status)] of the pins of the members of MEM (section 8.5)."""
        out = []
        for m in mem["members"]:
            for ver, dig, _ in P.member_pins(m):
                found = r.pin(m["name"], m["owner"], ver, dig, m.get("at", []))
                out.append((m, ver, found.status))
        return out


    def status(args):
        coll_id, d, inv, mem = held(args.collection)
        with remote.Resolver() as r:
            for m, ver, st in statuses(mem, r):
                print(f"{st}: sheaf:{m['name']}:{m['owner']} {ver} ({m.get('cite', {}).get('title', '')})")
            for s, msg in r.notes:
                print(f"{s}: {msg}")

### From a file

`sync` writes a collection from its description in a YAML or JSON file,
making it if the label is new (then the file gives its `type` and
`title`). Members are listed in the curator's order.

    # in collections: the commands:
    def load_spec(path):
        """The description of a collection, from a YAML or JSON file."""
        from pathlib import Path
        text = Path(path).read_text(encoding="utf-8")
        if str(path).endswith(".json"):
            spec = json.loads(text)
        else:
            import yaml
            spec = yaml.safe_load(text)
        if not isinstance(spec, dict) or not isinstance(spec.get("members", []), list):
            sys.exit(f"{path}: a mapping with members, a list")
        for k in spec:
            if k not in ("title", "description", "type", "order", "owner", "members"):
                sys.exit(f"{path}: unknown key {k}")
        if spec.get("type", "catalogue") not in KINDS or spec.get("order", "manual") not in ORDERS:
            sys.exit(f"{path}: type is catalogue or selection, order one of {', '.join(ORDERS)}")
        return spec


    def sync(args):
        spec = load_spec(args.from_file)
        exists = args.collection in P.LABELS
        if exists:
            coll_id, d, inv, old = held(args.collection)
            kind = old["type"]
            if spec.get("type", kind) != kind:
                sys.exit(f"{args.collection} is a {kind}: its type does not change")
        else:
            if not spec.get("title"):
                sys.exit("a new collection needs a title")
            coll_id, old, kind = None, {"members": []}, spec.get("type", "catalogue")
            if "type" not in spec:
                print(f"{args.collection}: no type: a catalogue")
        members = []
        with remote.Resolver() as r:
            for entry in spec.get("members", []):
                members.append(sync_member(r, entry, kind, old["members"]))
        mem = {"format": FORMAT, "type": kind, "order": spec.get("order", old.get("order", "manual")),
               "members": members}
        owner = spec.get("owner") or P.ARCHIVE["owner"]
        if not exists:
            P.init_storage_root()
        write(coll_id, mem, message=args.message or f"Members from {args.from_file}",
              title=spec.get("title"), description=spec.get("description"), owner=owner,
              label=args.collection)

An entry of the file: a URI or a label as a string, or a mapping with
`uri` or `label`, and optionally `at`, `follow` and `revisions`. A member
already in the collection keeps its pin, its `at` and its citation unless
the entry says otherwise; a pin, revisions not yet vetted, or a new
member are resolved. The locations an entry adds to the `at` of a member
already there are held to the same rule as those of a new one: only
`https` base URLs are recorded, the others are left out with a note, so
that a file of members cannot put another kind of address into a
collection, and from there into the links of a website.

    # in collections: the commands:
    def sync_member(r, entry, kind, old_members):
        if isinstance(entry, str):
            entry = {"uri": entry}
        text = entry.get("uri") or entry.get("label")
        if not text:
            sys.exit(f"a member needs uri or label: {entry}")
        at = entry.get("at") or []
        at = [at] if isinstance(at, str) else list(at)
        nm, owner, u, places = target(r, str(text), at)
        follow = entry.get("follow") in (True, "yes", "true", "latest")
        revs = list(dict.fromkeys(int(x) for x in entry.get("revisions", [])))
        if kind == "catalogue" and revs:
            sys.exit(f"{text}: revisions are for selections")
        old = next((m for m in old_members if (m["name"], m["owner"]) == (nm, owner)), None)
        if old is not None and not (u is not None and u.sha512):
            m = json.loads(json.dumps(old))
            added = https_bases(at)
            for w in at:
                if w not in added:
                    print(f"{text}: at {w}: not an https base URL ending in /: not recorded")
            if added:
                m["at"] = list(dict.fromkeys(added + m["at"]))
            if kind == "catalogue":
                m.pop("follow", None)
                if follow:
                    m["follow"] = "latest"
                return m
            vetted = {x["documentVersion"] for x in m["revisions"]}
            if not revs or set(revs) == vetted:
                return m
            founds = pinned(r, nm, owner, u, places, kind, [n for n in revs if n not in vetted])
            m["revisions"] = [x for x in m["revisions"] if x["documentVersion"] in revs]
            m["revisions"] += [revision(f.copy.dir, f.copy.inv, int(f.version[1:])) for f in founds]
            m["revisions"] = sort_revisions(m["revisions"], history_order(founds[0].copy))
            return m
        founds = pinned(r, nm, owner, u, places, kind, revs)
        rec_at = recorded_at(founds[0], places)
        if not rec_at:
            sys.exit(f"{text}: no https base URL where copies are found: give at (section 8.2)")
        c = founds[0].copy
        m = member_record(kind, c.dir, c.inv, int(founds[0].version[1:]), nm, owner, rec_at, follow)
        if kind == "selection":
            m["revisions"] = sort_revisions([revision(f.copy.dir, f.copy.inv, int(f.version[1:]))
                                             for f in founds], history_order(c))
        return m
