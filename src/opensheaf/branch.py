# Generated from literate/23-branches.md by opensheaf-literate: edit the document, not this file.
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
            return names.json_value(data) if data is not None else None
        except P.DigestMismatch:
            raise
        except ValueError:
            return None


def level_of_version(d, inv, ver):
    """The Level of the object version VER of the object in D, each file read only with the
    digest its inventory states (DigestMismatch otherwise)."""
    state = inv["versions"][ver]["state"]
    digests = {p: dig for dig, ps in state.items() for p in ps}

    def read(p):
        data = P.content_file(d, inv["manifest"][digests[p]][0]).read_bytes()
        if names.sha512_hex(data) != str(digests[p]).lower():
            raise P.DigestMismatch(f"{p} does not have the digest its inventory states (section 4.1)")
        return data
    return Level(digests, read)


def level_of_files(files):
    """The Level of FILES, {logical path: bytes}."""
    return Level({p: names.sha512_hex(b) for p, b in files.items()}, lambda p: files[p])


INCONSISTENT, CONFIRMED, UNCHECKED = "inconsistent", "confirmed", "unchecked"
ORDER = {CONFIRMED: 0, UNCHECKED: 1, INCONSISTENT: 2}


def verdict(level, obj, genesis, logs, depth=0, resolve=None):
    """(verdict, problems) of the branch point that OBJ (an object.json) records, the content of
    its level being LEVEL; GENESIS the bytes of the genesis record; LOGS(owner) a key log or None;
    RESOLVE(parent), if given, the parent version as the verifier finds it in the parent's line:
    None if it finds none, else (whether it matches the pin, its status there)."""
    try:
        return level_verdict(level, obj, genesis, logs, depth, resolve)
    except P.DigestMismatch as e:
        return INCONSISTENT, [f"the evidence of the branch point cannot be read: {e}"]
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
        return INCONSISTENT, [f"the evidence of the branch point cannot be read: {type(e).__name__} {e}"]


def level_verdict(level, obj, genesis, logs, depth=0, resolve=None):
    """verdict, the files read as they should be (an exception for a file of another form)."""
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
    nm, pname = obj.get("name") or "", p.get("name") or ""
    if not names.is_name_of(nm, genesis) or not names.is_name_of(pname, genesis):
        problems.append("the name and parent.name are not names of genesis.json (section 5.2)")
    elif nm != pname and names.algorithm(nm) <= names.algorithm(pname):
        problems.append("a branch renamed after a clash has a greater algorithm number than parent.name "
                        "(section 5.3)")
    pinv_bytes = level.read("parent/inventory.json") if "parent/inventory.json" in level.digests else None
    pinv = names.json_value(pinv_bytes) if pinv_bytes else None
    pobj_bytes = level.read("parent/object.json") if "parent/object.json" in level.digests else None
    pobj = level.json("parent/object.json")
    if not isinstance(pinv, dict) or not isinstance(pobj, dict):
        return INCONSISTENT, problems + ["parent/inventory.json or parent/object.json is missing, or not "
                                         "of the form of an inventory and an object.json (section 9.2)"]
    if names.sha512_hex(pinv_bytes) != p.get("inventorySha512") or pinv.get("head") != p.get("objectVersion"):
        problems.append("parent/inventory.json is not the inventory the pin of parent names")
    pstate = {path: dig for dig, ps in pinv.get("versions", {}).get(pinv.get("head"), {}).get("state", {}).items()
              for path in ps}
    if pstate.get(P.OBJ) is None or pstate.get(P.OBJ) != names.sha512_hex(pobj_bytes):
        problems.append("parent/object.json is not the object.json the parent inventory records")
    if depth == 0:
        own = {"datacite.json", P.OBJ} | {n["path"] for n in obj.get("notices", []) if n.get("path")}
        for path, dig in pstate.items():
            if path in own or P.is_evidence(path):
                continue
            if level.digests.get(path) != dig:
                problems.append(f"{path}: a file of the parent version is missing, or differs (section 9.3)")
        for path in level.digests:
            if path not in own and not P.is_evidence(path) and path not in pstate:
                problems.append(f"{path}: not a file of the parent version (section 9.3)")
    if (p.get("owner"), p.get("name"), p.get("documentVersion")) != \
            (pobj.get("owner"), pobj.get("name"), pobj.get("documentVersion")):
        problems.append("parent does not agree with parent/object.json")
    if obj.get("owner") in (p.get("owner"), rec.get("originator")):
        problems.append("the owner of a branch is neither the parent's owner nor the originator (section 9.3)")
    if not ((p.get("owner") == rec.get("originator") and "parent" not in pobj) or "parent" in pobj):
        problems.append("the parent is the originator's line, or a branch with its own parent (section 9.3)")
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
    resolved = resolve(p) if resolve is not None else None
    if resolved is not None and not resolved[0]:
        problems.append("the parent version, resolved, does not match the pin (section 9.3)")
    elif resolved is not None and resolved[1] == sign.CONTESTED:
        status = sign.CONTESTED
    elif resolved is not None and resolved[1] in (sign.SIGNED, sign.VOUCHED) and status != sign.CONTESTED:
        status = resolved[1]
    if status in (sign.UNSIGNED, sign.INVALID):
        problems.append(f"the parent version is not a version: {status} (sections 7.3 and 9.3)")
    result = CONFIRMED if status in (sign.SIGNED, sign.VOUCHED) else UNCHECKED
    notes = [] if result == CONFIRMED else [f"the parent version is {status} (section 9.3)"]
    if problems:
        return INCONSISTENT, problems
    if "parent" in pobj:
        inner = level.sub(P.EVIDENCE)
        chain = Level({path: dig for path, dig in inner.digests.items() if P.is_evidence(path)}, inner.read)
        evidence = {path: dig for path, dig in pstate.items() if P.is_evidence(path)}
        if chain.digests != evidence:
            return INCONSISTENT, ["parent/parent/ is not the evidence of the parent version (section 9.3)"]
        sub, more = verdict(chain, pobj, genesis, logs, depth + 1, resolve)
        if sub == INCONSISTENT:
            return INCONSISTENT, [f"parent/parent/: {m}" for m in more]
        notes += [f"parent/parent/: {m}" for m in more]
        result = max(result, sub, key=ORDER.get)
    return result, notes


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


def chain_owners(files):
    """The owners of the parent versions at every level of the evidence in FILES."""
    out, prefix = [], ""
    while prefix + "parent/object.json" in files and len(out) <= MAX_DEPTH:
        try:
            owner = names.json_value(files[prefix + "parent/object.json"]).get("owner")
        except (ValueError, AttributeError):
            break
        if not isinstance(owner, str) or not names.OWNER_NAME.match(owner):
            break
        out.append(owner)
        prefix += "parent/"
    return out


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
                     "and 9.1): the originator takes in another line's work by depositing it (section 9.5)")
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
        pobj = json.loads(files["parent/object.json"])
        pdc = c.read("datacite.json", k) or {}
        keep = ("mainSource", "sourceFormat", "sourcesMissing", "renditions", "toolchain", "changes", "stage",
                "licence", "agreement")
        obj = {"format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": pobj["kind"], "name": nm, "owner": owner,
               "parent": parent, "documentVersion": 1,
               **{f: pobj[f] for f in keep if f in pobj}, "status": "active"}
        if move:
            d = P.obj_dir(obj_id)
            binv = P.load_inventory(d)
            obj["documentVersion"] = max(P.doc_version_of(d, binv, x) for x in binv["versions"]) + 1
            own_notices = P.read_json(d, binv, P.OBJ).get("notices", [])
            if own_notices:
                obj["notices"] = own_notices
            for n in own_notices:
                if n.get("path"):
                    if n["path"] in files:
                        sys.exit(f"{n['path']}: a notice of the branch has the path of a file of the new parent "
                                 "version (section 9.4)")
                    files[n["path"]] = P.read_logical(d, binv, n["path"]).read_bytes()
        dc = {key: v for key, v in pdc.items() if key not in ("doi", "url")}
        dc["publisher"] = {"name": P.ARCHIVE["name"]}
        dc["version"] = str(obj["documentVersion"])
        dc["url"] = P.landing_url(obj_id, names.read_genesis(files[P.GENESIS]).get("originator"))
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
        logs = lambda o: P.key_log(o)
        v, problems = verdict(level_of_files(content), obj, genesis, logs)
        if v != CONFIRMED:
            sys.exit(f"{obj_id}: the branch point would be {v}: " + "; ".join(problems))
        inv = P.add_version(obj_id, content, obj, message or (
            f"New branch point {parent['objectVersion']} of {line}" if move else
            f"Branch of {line} at {parent['objectVersion']} (document version {parent['documentVersion']})"))
    if label and not move:
        P.LABELS[label] = obj_id
    P.write_discovery()
    print(f"{label or P.label_of(obj_id) or obj_id}: {inv['head']} "
          + ("takes the new branch point " if move else "branch of ")
          + f"{line} {parent['objectVersion']} (document version {parent['documentVersion']})")
    return obj_id, inv["head"], inv, parent_at


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


def main(args):
    if not args.label and not args.uri:
        sys.exit("osheaf branch URI --label LABEL")
    make_branch(args.uri, list(args.at or []), owner=args.owner, label=args.label, message=args.message)


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
