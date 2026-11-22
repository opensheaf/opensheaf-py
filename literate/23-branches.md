Branches and accepted copies
============================

A *branch* is a line of another owner that continues a work from a signed
version of another line, its *branch point* or *parent version*: a
co-author carrying the work on, the successor of an ended owner, a journal
keeping the version it vetted (section 9). It has the work's genesis
record, and so its name, or after a clash another name of the same
record; it is a new object, with its own identifier, holding the branch
point and its own versions, never the parent's other versions. An
*accepted copy* is a branch kept by the owner of a selection from a
revision it vetted (section 9.6).

This chapter is the module `branch.py`: making a branch (`osheaf branch`),
moving its branch point, checking a branch point as section 9.3 says
(which [verification](17-verify.md) uses), and accepting a version into a
selection (`osheaf accept`).

Version 0.1 had no branches: a journal's accepted copy was a document of
its own archive, with an `external` record of role `source` naming the
version it was copied from, and its own identifier. That code is gone. An
accepted copy is now a branch under the journal's owner, which anyone can
check against the authors' signatures without access to their archive,
because it carries the *evidence* of its branch point.

The evidence
------------

The first version of a branch holds exactly the files of the parent
version, the genesis record included, except the parent's `datacite.json`,
`object.json` and own evidence; its own `datacite.json` and `object.json`;
and the evidence of the branch point (section 9.2):

all in the folder `parent/`:

- `parent/inventory.json`: the inventory of the parent version, byte for
  byte, which fixes its files and its pin;
- `parent/object.json`: its `object.json`;
- `parent/signatures/`: the parent owner's signature files of the parent
  version, named as in its witness folder, with the files kept beside them
  (timestamps), so that the branch point's signatures travel with it;
- `parent/parent/`, when the parent is itself a branch: the parent
  version's own folder `parent/`, byte for byte, and so on level by level,
  back to a version of the originator's line.

Its `object.json` records the branch point in `parent`: the parent line
(`owner`, `name`), the pin (`objectVersion`, `inventorySha512`), the
`documentVersion` it holds, and `url`, a hint where it was found
(section 9.1). The key logs that the evidence needs (of the parent's
owner, and of the owner at every level of the chain) are kept beside the
branch in the storage root, never in it (section 6.5).

Naming
------

A branch is named by `parent.name`, unless its owner already has a line of
that name here, in which case it is named by the smallest algorithm number
greater than that of `parent.name` that gives a line free for its owner,
and `parent` keeps the parent's name (section 5.3); if none up to 15 is
free, it is refused. When the line it would take is the owner's own branch
of the same parent line, and the new branch point is later in that line's
history, the owner *moves* that branch's branch point instead (section
9.4). A tool refuses a branch owned by the originator, or by the parent's
owner (sections 5.3 and 9.1).

Moving the branch point
-----------------------

A branch may take as a new branch point a later version of the same parent
line, with a higher object version and a document version later than the
previous branch point's in the history of the new parent version (a
journal accepting the authors' corrected version). The version that moves
holds exactly the files of the new parent version with new evidence, and
is numbered on from the branch's last document version (section 9.4,
provisionally, #57); its own notes and notices lose their files.

The module
----------

    # in src/opensheaf/branch.py:
    """Branches and accepted copies (section 9 of OpenSheaf 0.2): the evidence of a branch point, the
    names of branches, moving a branch point, the checks and verdicts of section 9.3, and accepted
    copies listed by a selection.

        osheaf branch URI [--at URL]... [--label LABEL] [--owner OWNER]
        osheaf accept URI [--at URL]... --selection LABEL [--label LABEL] [--with-original]
    """

    import json
    import sys

    from . import core as P, names, remote, sign

    MAX_DEPTH = 64


    <<branches: the content of a version, level by level>>


    <<branches: checking a branch point>>


    <<branches: the evidence of a branch point>>


    <<branches: the name of a new branch>>


    <<branches: making a branch or moving its branch point>>


    <<branches: accepting a version into a selection>>

Checking a branch point
-----------------------

The checks of section 9.3 read the content of a version level by level:
the branch's own files, then, under `parent/parent/`, the parent's
evidence, and so on. A `Level` is that view: the digests of its logical
paths, and a function reading one.

    # in branches: the content of a version, level by level:
    class Level:
        """The content of one level of a branch point: {logical path: digest} and a reader."""

        def __init__(self, digests, read):
            self.digests, self.read = digests, read

        def sub(self, prefix):
            """The level under PREFIX (parent/), its paths without PREFIX."""
            return Level({p[len(prefix):]: d for p, d in self.digests.items() if p.startswith(prefix)},
                         lambda p: self.read(prefix + p))

        def json(self, path):
            data = self.read(path) if path in self.digests else None
            try:
                return json.loads(data) if data is not None else None
            except ValueError:
                return None


    def level_of_version(d, inv, ver):
        """The Level of the object version VER of the object in D."""
        state = inv["versions"][ver]["state"]
        digests = {p: dig for dig, ps in state.items() for p in ps}
        return Level(digests, lambda p: (d / inv["manifest"][digests[p]][0]).read_bytes())


    def level_of_files(files):
        """The Level of FILES, {logical path: bytes}."""
        return Level({p: names.sha512_hex(b) for p, b in files.items()}, lambda p: files[p])

A branch point is *consistent* when the five checks of section 9.3 pass,
and its *verdict* is, in this order: *inconsistent* when a check fails or a
parent version is not a version (section 7.3); *confirmed* when the parent
version, at every level, is signed and not contested; and otherwise
*unchecked*. The checks, at each level, against the `object.json` of the
level below (the branch's own at the first level):

- **the name**: the branch's `name` and `parent.name` are names of the
  genesis record, the branch's being `parent.name` or a name of a greater
  algorithm number;
- **the pin**: `parent/inventory.json` has the digest `parent.inventorySha512`
  and the head `parent.objectVersion`, and `parent/object.json` the digest
  that inventory records for `object.json`;
- **the files**, at the first level only (a parent version may be a later
  version of its own branch): every file of the parent version but its
  descriptions and evidence is present with the same digest, and nothing
  else is present but the branch's descriptions and evidence;
- **the parent**: `parent` agrees with `parent/object.json`; the branch's
  owner is neither the parent's owner nor the originator; and the parent
  is the originator's line without a parent, or a branch with one;
- **the signatures**: the signature files of `parent/signatures/` are
  judged against the parent owner's key log kept beside the branch
  (`logs`), as the signatures of the parent version would be in its own
  witness folder (section 7.3, case 3);
- **the chain**: when the parent has a `parent`, `parent/parent/` holds its
  evidence, each file with the digest the parent's inventory records for
  it, and is checked in turn.

A chain deeper than `MAX_DEPTH` is not followed further, and the branch
point is then unchecked (section 9.3).

    # in branches: checking a branch point:
    INCONSISTENT, CONFIRMED, UNCHECKED = "inconsistent", "confirmed", "unchecked"
    ORDER = {CONFIRMED: 0, UNCHECKED: 1, INCONSISTENT: 2}


    def verdict(level, obj, genesis, logs, depth=0):
        """(verdict, problems) of the branch point that OBJ (an object.json) records, the content of
        its level being LEVEL; GENESIS the bytes of the genesis record; LOGS(owner) a key log or None."""
        p = obj.get("parent")
        if not isinstance(p, dict):
            return INCONSISTENT, ["object.json has no parent"]
        if depth > MAX_DEPTH:
            return UNCHECKED, [f"the chain is not followed beyond {MAX_DEPTH} levels"]
        problems = []
        try:
            rec = names.read_genesis(genesis)
        except ValueError as e:
            return INCONSISTENT, [f"genesis.json: {e}"]
        <<branches: the name and the pin of a branch point>>
        <<branches: the files of a branch point>>
        <<branches: the parent of a branch point>>
        <<branches: the signatures of a branch point>>
        if problems:
            return INCONSISTENT, problems
        <<branches: the chain of a branch point>>
        return result, notes

The name and the pin.

    # in branches: the name and the pin of a branch point:
    nm, pname = obj.get("name") or "", p.get("name") or ""
    if not names.is_name_of(nm, genesis) or not names.is_name_of(pname, genesis):
        problems.append("the name and parent.name are not names of genesis.json (section 5.2)")
    elif nm != pname and names.algorithm(nm) <= names.algorithm(pname):
        problems.append("a branch renamed after a clash has a greater algorithm number than parent.name "
                        "(section 5.3)")
    pinv_bytes = level.read("parent/inventory.json") if "parent/inventory.json" in level.digests else None
    pinv = json.loads(pinv_bytes) if pinv_bytes else None
    pobj = level.json("parent/object.json")
    if pinv is None or pobj is None:
        return INCONSISTENT, problems + ["parent/inventory.json or parent/object.json is missing (section 9.2)"]
    if names.sha512_hex(pinv_bytes) != p.get("inventorySha512") or pinv.get("head") != p.get("objectVersion"):
        problems.append("parent/inventory.json is not the inventory the pin of parent names")
    pstate = {path: dig for dig, ps in pinv.get("versions", {}).get(pinv.get("head"), {}).get("state", {}).items()
              for path in ps}
    if pstate.get(P.OBJ) != level.digests.get("parent/object.json"):
        problems.append("parent/object.json is not the object.json the parent inventory records")

The files, at the first level.

    # in branches: the files of a branch point:
    if depth == 0:
        own = {"datacite.json", P.OBJ}
        for path, dig in pstate.items():
            if path in own or P.is_evidence(path):
                continue
            if level.digests.get(path) != dig:
                problems.append(f"{path}: a file of the parent version is missing, or differs (section 9.3)")
        for path in level.digests:
            if path not in own and not P.is_evidence(path) and path not in pstate:
                problems.append(f"{path}: not a file of the parent version (section 9.3)")

The parent.

    # in branches: the parent of a branch point:
    if (p.get("owner"), p.get("name"), p.get("documentVersion")) != \
            (pobj.get("owner"), pobj.get("name"), pobj.get("documentVersion")):
        problems.append("parent does not agree with parent/object.json")
    if obj.get("owner") in (p.get("owner"), rec.get("originator")):
        problems.append("the owner of a branch is neither the parent's owner nor the originator (section 9.3)")
    if not ((p.get("owner") == rec.get("originator") and "parent" not in pobj) or "parent" in pobj):
        problems.append("the parent is the originator's line, or a branch with its own parent (section 9.3)")

The signatures, judged as those of the parent version, with the parent
owner's key log; without one they are unchecked. A parent version that is
not a version (unsigned, or with an invalid signature file and no good
ones) makes the branch point inconsistent.

    # in branches: the signatures of a branch point:
    log = logs(p.get("owner"))
    pid = names.object_id(p.get("name"), p.get("owner")) if names.NAME.match(pname) and \
        names.OWNER_NAME.match(p.get("owner") or "") else None
    witnesses = {path[len("parent/signatures/"):]: level.read(path) for path in level.digests
                 if path.startswith("parent/signatures/") and "/" not in path[len("parent/signatures/"):]}
    if pid is None:
        return INCONSISTENT, problems + ["parent does not name a line"]
    judgements = sign.judge_folder(witnesses, object_id=pid, version=p.get("objectVersion"),
                                   inventory=p.get("inventorySha512"), owner=p.get("owner"),
                                   lookup=log.lookup if log else (lambda n, dg: None))
    status = sign.line_statuses([judgements], exposed=log.exposed_keys() if log else frozenset(),
                                fork_point=log.fork_point if log else None)[0]
    if status in (sign.UNSIGNED, sign.INVALID):
        problems.append(f"the parent version is not a version: {status} (sections 7.3 and 9.3)")
    result = CONFIRMED if status in (sign.SIGNED, sign.VOUCHED) else UNCHECKED
    notes = [] if result == CONFIRMED else [f"the parent version is {status} (section 9.3)"]

The chain, level by level: each file `parent/parent/<path>` has the
digest the parent's inventory records for `parent/<path>`, and
nothing of the parent's evidence is missing; the level is then checked as
a branch point of its own, the parent's `object.json` standing for the
branch's. The weakest verdict wins.

    # in branches: the chain of a branch point:
    if "parent" in pobj:
        inner = level.sub(P.EVIDENCE)
        chain = Level({path: dig for path, dig in inner.digests.items() if P.is_evidence(path)}, inner.read)
        evidence = {path: dig for path, dig in pstate.items() if P.is_evidence(path)}
        if chain.digests != evidence:
            return INCONSISTENT, ["parent/parent/ is not the evidence of the parent version (section 9.3)"]
        sub, more = verdict(chain, pobj, genesis, logs, depth + 1)
        if sub == INCONSISTENT:
            return INCONSISTENT, [f"parent/parent/: {m}" for m in more]
        notes += [f"parent/parent/: {m}" for m in more]
        result = max(result, sub, key=ORDER.get)

The evidence of a branch point
------------------------------

Taking the files of a branch point from a copy of the parent line (a
`Copy` of the [resolver](20-resolution.md)): the parent version's files,
but its descriptions and evidence; its inventory and `object.json`; its
signature files that are good, with the files kept beside them (named
after them, `signature-<k>.json.<...>`); and its own evidence under
`parent/parent/`. Signature files that are not good are not evidence, and
are left out.

    # in branches: the evidence of a branch point:
    def branch_point_files(c, k):
        """({logical path: bytes} of the parent version vK of the copy C and of its evidence,
        the `parent` record without url)."""
        ver = f"v{k}"
        level = level_of_version(c.dir, c.inv, ver)
        pobj = level.json(P.OBJ)
        files = {path: level.read(path) for path in level.digests
                 if path not in ("datacite.json", P.OBJ) and not P.is_evidence(path)}
        files["parent/inventory.json"] = (c.dir / ver / "inventory.json").read_bytes()
        files["parent/object.json"] = level.read(P.OBJ)
        witnesses = P.witnesses_of(c.dir, ver)
        good = [j.file for j in sign.judge_folder(witnesses, object_id=c.id, version=ver, inventory=c.digest(k),
                                                  owner=pobj["owner"], lookup=c.log.lookup if c.log else
                                                  (lambda n, dg: None)) if j.status == sign.GOOD]
        for name, data in witnesses.items():
            if name in good or any(name.startswith(g + ".") for g in good):
                files[f"parent/signatures/{name}"] = data
        for path in P.evidence_paths(c.inv, ver):
            files[f"parent/{path}"] = level.read(path)
        parent = {"owner": pobj["owner"], "name": pobj["name"], "objectVersion": ver,
                  "documentVersion": pobj["documentVersion"], "inventorySha512": c.digest(k)}
        return files, parent

The owners whose key logs a branch needs beside it: the parent's, and the
one at every level of the chain.

    # in branches: the evidence of a branch point:
    def chain_owners(files):
        """The owners of the parent versions at every level of the evidence in FILES."""
        out, prefix = [], ""
        while prefix + "parent/object.json" in files:
            out.append(json.loads(files[prefix + "parent/object.json"])["owner"])
            prefix += "parent/"
        return out

The name of a new branch
------------------------

The names of the record are tried from `parent.name` upwards, as section
5.3 says: a line free for the owner (no object and no tombstone here)
takes the branch; the owner's own branch of the same parent line, when
the new branch point is later in its history, has its branch point moved;
any other line of the owner is a clash, and the next number is tried.

    # in branches: the name of a new branch:
    def branch_name(genesis, parent, owner, later):
        """(name, move): the name of the new branch of OWNER from PARENT, and whether it moves the
        branch point of the owner's branch of that name; LATER(branch obj) says whether PARENT is a
        later branch point than that branch's (section 9.4)."""
        taken = {t.get("name") for t in P.TOMBSTONES if t.get("owner") == owner}
        for k in range(names.algorithm(parent["name"]), 16):
            nm = names.name(genesis, k)
            obj_id = names.object_id(nm, owner)
            d = P.obj_dir(obj_id)
            inv = P.load_inventory(d)
            if inv is None and nm not in taken:
                return nm, False
            if inv is None:
                continue
            head = P.read_json(d, inv, P.OBJ) or {}
            hp = head.get("parent") or {}
            if (hp.get("owner"), hp.get("name")) == (parent["owner"], parent["name"]) and later(head):
                return nm, True
        sys.exit(f"no name of the genesis record from algorithm {names.algorithm(parent['name'])} to 15 is "
                 f"free for {owner}: the branch is refused (section 5.3)")

Making a branch
---------------

`make_branch` resolves the parent version, which must be signed and not
contested (section 9.1: "only a signed version is branched"); checks the
owner (sections 5.3 and 9.1); copies beside the branch the key logs its
evidence needs (section 6.5), from the copies found; names the branch, or
finds the branch whose branch point moves; and writes the version, after
checking its branch point as a verifier will. The first version holds the
parent's document version; a version that moves the branch point takes
the next number of the branch. A branch is a line of its owner: `osheaf
collect` lists it in that owner's [catalogue](15-owner-catalogues.md),
never in the catalogue of the parent's owner (section 9), and an accepted
copy likewise in the catalogue of the selection's owner.

    # in branches: making a branch or moving its branch point:
    def make_branch(uri, where, *, owner=None, label=None, message=None):
        """Make a branch of the version URI names, or move the branch point of the owner's branch of
        that line; returns (identifier, object version, inventory, the base URLs of the parent)."""
        owner = owner or P.ARCHIVE["owner"]
        if owner not in P.archive_owners():
            sys.exit(f"{owner} is not an owner this archive hosts")
        from . import mirror
        with remote.Resolver(places=where) as r:
            try:
                line, found = r.resolve(uri)
            except ValueError as e:
                sys.exit(str(e))
            if found.status != "verified" or found.copy is None:
                sys.exit(f"{uri}: {found.status}: only a signed version, not contested, is branched (section 9.1)")
            c, k = found.copy, int(found.version[1:])
            files, parent = branch_point_files(c, k)
            genesis = files[P.GENESIS]
            rec = names.read_genesis(genesis)
            if owner in (parent["owner"], rec.get("originator")):
                sys.exit("the owner of a branch is neither the parent's owner nor the originator (sections 5.3 "
                         "and 9.1): the originator's own lines take in another line's work otherwise (#57)")
            url = (P.ARCHIVE["baseUrl"] + "ocfl/" + P.path_of(c.id) + f"/v{k}/" if c.where == "here"
                   else c.src.object_url(c.id, f"v{k}") if c.src else None)
            parent_at = [P.ARCHIVE["baseUrl"]] if c.where == "here" else [c.src.at] if c.src and c.src.at else []
            if url:
                parent["url"] = url
            for o in chain_owners(files):
                r.key_log(o, r.where([c.where] if c.where != "here" else []))
                if mirror.record_key_log(r, o) is None:
                    sys.exit(f"no key log of {o} found: the evidence of the branch point needs it beside "
                             "the branch (section 6.5)")
            nm, move = branch_name(genesis, parent, owner, lambda head: later(head, c, k))
            obj_id = names.object_id(nm, owner)
            <<branches: the files and records of the new version>>
            logs = lambda o: P.key_log(o)
            v, problems = verdict(level_of_files(content), obj, genesis, logs)
            if v != CONFIRMED:
                sys.exit(f"{obj_id}: the branch point would be {v}: " + "; ".join(problems))
            inv = P.add_version(obj_id, content, obj, message or (
                f"Branch point moved to {parent['objectVersion']} of {line}" if move else
                f"Branch of {line} at {parent['objectVersion']} (document version {parent['documentVersion']})"))
        if label and not move:
            P.LABELS[label] = obj_id
        P.write_discovery()
        print(f"{label or P.label_of(obj_id) or obj_id}: {inv['head']} "
              + ("moves the branch point to " if move else "branch of ")
              + f"{line} {parent['objectVersion']} (document version {parent['documentVersion']})")
        return obj_id, inv["head"], inv, parent_at

Whether a new branch point is later than a branch's current one
(section 9.4): a higher object version of the same parent line, holding a
document version later in the history of the new parent version. The
same document version is not a new branch point, and the same parent
version is the branch point already: the tools stop there, rather than
make a second branch of the same version under another name. An earlier
version makes a new branch, renamed (section 5.3).

    # in branches: making a branch or moving its branch point:
    def later(head, c, k):
        """Whether vK of the parent copy C is a later branch point than that of the branch HEAD."""
        old = head["parent"]
        if k == int(old["objectVersion"][1:]):
            sys.exit(f"v{k} is the branch point of the branch already")
        if k < int(old["objectVersion"][1:]):
            return False
        order = [P.doc_version_of(c.dir, c.inv, h) for h in P.history_of(c.dir, c.inv, f"v{k}")]
        new_dv = P.doc_version_of(c.dir, c.inv, f"v{k}")
        if new_dv == old["documentVersion"]:
            sys.exit(f"v{k} holds document version {new_dv}, as the branch point does: not a new branch point "
                     "(section 9.4)")
        return old["documentVersion"] in order and new_dv in order and \
            order.index(new_dv) > order.index(old["documentVersion"])

The records of the branch. `object.json` keeps the parent's description of
the document's files (main source, renditions, toolchain, change note,
stage, notices, licence note, agreement), and records the branch's own
line and its branch point; it drops what belongs to the parent's line
alone (its history, its external records, its withdrawal). `datacite.json`
is the parent's, with the branch's owner as publisher (here the archive,
section 9.7), the branch's own address, no DOI of the parent's, and an
`IsIdenticalTo` relation to the parent version: its DOI, or else
`parent.url` (section 9.7).

    # in branches: the files and records of the new version:
    pobj = json.loads(files["parent/object.json"])
    pdc = c.read("datacite.json", k) or {}
    keep = ("mainSource", "sourceFormat", "sourcesMissing", "renditions", "toolchain", "changes", "stage",
            "notices", "licence", "agreement")
    obj = {"format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": pobj["kind"], "name": nm, "owner": owner,
           "parent": parent, "documentVersion": parent["documentVersion"],
           **{f: pobj[f] for f in keep if f in pobj}, "status": "active"}
    if move:
        d = P.obj_dir(obj_id)
        binv = P.load_inventory(d)
        obj["documentVersion"] = max(P.doc_version_of(d, binv, x) for x in binv["versions"]) + 1
        notes = {n["path"] for n in obj.pop("notices", []) if n.get("path")}
        files = {path: b for path, b in files.items() if path not in notes}
    dc = {key: v for key, v in pdc.items() if key not in ("doi", "url")}
    dc["publisher"] = {"name": P.ARCHIVE["name"]}
    dc["version"] = str(obj["documentVersion"])
    if label or P.label_of(obj_id):
        dc["url"] = P.landing_url(label or P.label_of(obj_id))
    rel = ({"relatedIdentifier": pdc["doi"], "relatedIdentifierType": "DOI", "relationType": "IsIdenticalTo"}
           if pdc.get("doi") else {"relatedIdentifier": parent["url"], "relatedIdentifierType": "URL",
                                   "relationType": "IsIdenticalTo"} if parent.get("url") else None)
    if rel:
        dc["relatedIdentifiers"] = [x for x in dc.get("relatedIdentifiers", [])
                                    if x.get("relationType") != "IsIdenticalTo" or x.get("relatedIdentifierType")
                                    not in ("URL", "DOI")] + [rel]
    content = dict(files, **{"datacite.json": P.json_bytes(dc)})
    if label and not move and (label in P.LABELS or not P.LABEL_RE.match(label)):
        sys.exit(f"--label: a new label of the form of section 3.1 (not {label!r})")

The command `osheaf branch` makes the branch under the archive's owner, or
another owner it hosts.

    # in branches: making a branch or moving its branch point:
    def main(args):
        if not args.label and not args.uri:
            sys.exit("osheaf branch URI --label LABEL")
        make_branch(args.uri, list(args.at or []), owner=args.owner, label=args.label, message=args.message)

Accepting a version
-------------------

A journal accepting a version (section 9.6) makes an accepted copy, a
branch under the selection's owner, and lists it as a member of the
selection, with the revision it holds; with `--with-original` the
selection also lists the original revision set, the parent version
(section 9.6: it MAY), to which a later acceptance adds its revision. Accepting a later version of the same paper moves
the accepted copy's branch point, and the new revision is added to the
member's revision set: a new version of the selection, the curator's act,
whose message says what was accepted (section 8.4).

    # in branches: accepting a version into a selection:
    def accept(args):
        from . import collections
        sel_id, d, inv, mem = collections.held(args.selection)
        if mem.get("type") != "selection":
            sys.exit(f"{args.selection} is not a selection (section 8.1)")
        owner = sel_id.split(":")[2]
        obj_id, ver, binv, parent_at = make_branch(args.uri, list(args.at or []), owner=owner, label=args.label,
                                        message=args.message)
        bd = P.obj_dir(obj_id)
        bobj = P.read_json(bd, binv, P.OBJ, ver)
        _, nm, _ = obj_id.split(":")
        revision = {"documentVersion": bobj["documentVersion"], "version": ver,
                    "inventorySha512": P.digest(bd / ver / "inventory.json")}
        members = mem["members"]
        m = next((x for x in members if (x["name"], x["owner"]) == (nm, owner)), None)
        if m is None:
            m = collections.member_record("selection", bd, binv, int(ver[1:]), nm, owner, [P.ARCHIVE["baseUrl"]])
            members.append(m)
        elif all(x["documentVersion"] != revision["documentVersion"] for x in m["revisions"]):
            m["revisions"].append(revision)
        if args.with_original:
            p = bobj["parent"]
            if not parent_at:
                sys.exit("--with-original: the parent was found at no https base URL to record (section 8.2)")
            vetted = {"documentVersion": p["documentVersion"], "version": p["objectVersion"],
                      "inventorySha512": p["inventorySha512"]}
            orig = next((x for x in members if (x["name"], x["owner"]) == (p["name"], p["owner"])), None)
            if orig is None:
                members.append({"kind": bobj["kind"], "name": p["name"], "owner": p["owner"], "at": parent_at,
                                "revisions": [vetted]})
            elif all(x["documentVersion"] != vetted["documentVersion"] for x in orig["revisions"]):
                orig["revisions"].append(vetted)
        collections.write(sel_id, mem, message=args.message or
                          f"Accepted: document version {revision['documentVersion']} of {nm[:16]}..., "
                          f"kept as {obj_id} {ver}")
