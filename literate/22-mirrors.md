Copies: mirrors and key logs
============================

A collection refers to the lines of other archives without copying them
([collections](21-collections.md)). A reference needs nobody's
permission, but it depends on the other archive staying online. A *copy*
removes that dependence: a line's object as held in another storage root
(section 11). A *mirror* is a copy kept in an archive where the owner of
the line does not write (a library, a preservation copy); nothing marks
it, it is listed in `objects` like any line, and the rules of every copy
apply to it. This chapter is the module `mirror.py`, which makes and
updates mirrors, and keeps the copies of key logs that every copy needs
beside it (section 6.5), from which `osheaf owner pull` also takes a
fresher copy of an owner's own key log.

Version 0.1 marked a mirror with `mirrorOf` in the discovery document and
listed the copies of a member in its `mirrors`. Version 0.2 drops both: a
mirror is the same line, `sheaf:<name>:<owner>`, signed by its owner,
which any reader checks against the owner's key log kept beside it, and a
collection locates copies by the `at` of its members, mirrors included
(section 8.2).

The rules
---------

A mirror holds the object's versions up to the latest signed version of
the copy it copies, with their inventories, files and the witnesses it can
find, byte for byte, at the path its layout gives the line's identifier,
and beside it the key log of the line's owner (section 11.1). It grows
only by the owner's signed versions, from a copy that agrees with it, and
by witnesses (section 11.1). Section 7.5 says when an archive adds a
version:

1. only if, once added, it is signed and not contested against the key
   log the archive holds, which is why the key log is brought up to date
   first, from every copy found ("tools SHOULD fetch the latest version of
   the key log they can find before adding");
2. never a contested version, nor an invalid signature file;
3. once the archive knows of a fork of the owner's key log, no version of
   that owner's other lines at all: a fork *freezes* the owner. These
   tools trust no timestamps yet, which section 7.5 would admit as
   evidence, so a frozen owner's lines take no new version here;
4. a copy that does not agree with the mirror is a fork of the line,
   reported and never recorded: the mirror keeps the side it holds.

Copying is redistribution, and the archive keeping a mirror answers for
having the right to it, by the licences, the rights holders' agreement or
law (section 11.2); the tool only warns when the licences do not show it.
Key logs, inventories and signature files are metadata under CC0, copied
freely.

A line taken down here returns only from a copy holding the version its
tombstone pins (section 13.2), and its tombstone is then dropped
([takedowns](25-takedown.md)). A mirror is never made of a line of an
owner the archive hosts: those lines are written here.

The module
----------

    # in src/opensheaf/mirror.py:
    <<mirrors: the docstring and the imports>>


    <<mirrors: whether a licence allows redistribution>>


    <<mirrors: the copies of a key log>>


    <<mirrors: mirroring a line>>


    <<mirrors: the commands>>

The docstring gives the commands; the module reads other archives through
the [resolver](20-resolution.md).

    # in mirrors: the docstring and the imports:
    """Copies of lines and of key logs (sections 6.5, 7.5 and 11 of OpenSheaf 0.2): mirrors of lines
    written elsewhere, grown only by their owner's signed versions from copies that agree, with the
    key log of their owner kept beside them, met with every copy found (extended, or a fork record).

        osheaf mirror URI [--at URL]... [--label LABEL] [--licence-checked]
        osheaf mirror --all
        osheaf owner pull URL|PATH [--owner OWNER]
    """

    import copy
    import json
    import os
    import shutil
    import sys
    import tempfile
    from pathlib import Path

    from . import core as P, names, owners, remote, sign

    <<mirrors: the licences known to be open>>

Open licences
-------------

A licence is recognised as open in either of the two ways `datacite.json`
records it (section 4.4): by its SPDX identifier, written in lower case,
or by the URL of the licence. The list is short on purpose: licences that
certainly allow anyone to redistribute the work unchanged. arXiv's
default licence, for instance, gives arXiv alone the right to distribute,
and is not among them. The list is the tool's, not the format's: section
11.2 leaves the judgement to the archive. A version under none of these
licences is copied with a warning; a curator who knows that redistribution
is allowed otherwise (by the authors' agreement) silences it with
`--licence-checked`.

    # in mirrors: the licences known to be open:
    OPEN = {"cc-by-4.0", "cc-by-sa-4.0", "cc0-1.0", "gpl-3.0-only", "gpl-3.0-or-later", "cc-by-3.0"}
    OPEN_URIS = ("creativecommons.org/licenses/by/", "creativecommons.org/licenses/by-sa/",
                 "creativecommons.org/publicdomain/zero/", "gnu.org/licenses/gpl")

A URL matches by its stem, so that any version of a Creative Commons
licence, and its national ports, is recognised; the NonCommercial and
NoDerivatives variants are excluded explicitly. One open entry in the
`rightsList` suffices: a work offered under several licences may be
redistributed under any of them.

    # in mirrors: whether a licence allows redistribution:
    def is_open(rights):
        for r in rights or []:
            if (r.get("rightsIdentifier") or "").lower() in OPEN:
                return True
            uri = (r.get("rightsUri") or "").lower()
            if any(u in uri for u in OPEN_URIS) and "-nc" not in uri and "-nd" not in uri:
                return True
        return False

The copies of a key log
-----------------------

Every copy of an object holds beside it the key log of its owner, and a
branch those of its parents' owners, each up to the latest version that
whoever makes the copy knows (section 6.5). `record_key_log` writes into
the storage root what a [resolver](20-resolution.md) has found of an
owner's key log: the copy held here is met with every copy found
elsewhere, as an archive meets them (section 6.3, `KeyLog.pull` in
[chapter 6](06-owners.md)): extended when another copy is longer, given a
fork record when another copy differs, the fork record being the
archive's deposit; and a key log not held here is copied, from the first
copy found, met with the others. What happened to each copy is printed.

A key log taken down here returns only from a copy holding the version
its tombstone pins, also as carried by a fork record (section 13.2); its
tombstone is then dropped.

    # in mirrors: the copies of a key log:
    def record_key_log(r, owner):
        """Write the key log of OWNER, as the resolver R found it, into the storage root: the copy
        held here met with every other copy found (section 6.3); returns the KeyLog held, or None."""
        oid = names.object_id(owner, owner)
        found = r.found_logs(owner)
        local = next((log for w, log in found if w == "here"), None) or P.key_log(owner)
        others = [(w, log) for w, log in found if w != "here"]
        if local is None:
            if not others:
                return None
            w, first = others[0]
            first.check()
            from . import takedown
            if not takedown.may_return(oid, lambda n, d: first.lookup(n, d) is not None):
                print(f"warning: the key log of {owner} was taken down here, and the copy at {w} does not "
                      "hold the version its tombstone pins (section 13.2): not copied", file=sys.stderr)
                return None
            local = owners.KeyLog(first.genesis, [copy.deepcopy(v) for v in first.versions
                                                  if v.is_version])
            print(f"key log of {owner}: copied from {w} (v{len(local.versions)})")
            others = others[1:]
        for w, log in others:
            try:
                what, n = local.pull(log, user=P.depositor())
            except owners.OwnerError as e:
                print(f"warning: the key log of {owner} at {w}: {e}", file=sys.stderr)
                continue
            if what == "extended":
                print(f"key log of {owner}: {n} version{'' if n == 1 else 's'} added from the copy at {w}")
            elif what == "fork":
                print(f"key log of {owner}: a fork at v{n} met at {w}: fork record appended as "
                      f"v{local.versions[-1].number}; the owner has ended (section 6.3)")
            elif what == "reported":
                print(f"key log of {owner}: the copy at {w} forks at v{n}; a fork record is held already, "
                      "so it is reported, not recorded (section 6.3)")
        owners.write_key_log(P.obj_dir(oid), local)
        return P.key_log(owner)

Mirroring a line
----------------

`mirror_line` both makes a mirror and brings it up to date. The resolver
finds the copies of the line at the places given; the key log of its
owner is recorded first, so that the versions are judged against the key
log the archive will hold (rule 1); then the copy with the latest signed
version among those that agree is chosen, as a reader would (section
7.4), and its versions are judged again against the key log now held.

A tombstone of the line at a place copied from is reported first: a
takedown there does not reach the mirror, which this archive keeps or
takes down itself, answering for what it serves (section 13.3).

    # in mirrors: mirroring a line:
    def mirror_line(nm, owner, where, *, licence_checked=False, label=None):
        """Make or update the mirror of the line (NM, OWNER) from the copies at WHERE (section 11.1)."""
        obj_id = names.object_id(nm, owner)
        if owner in P.archive_owners():
            sys.exit(f"{obj_id} is a line of an owner this archive hosts: its owner writes it here, and it "
                     "is not mirrored (section 11)")
        with remote.Resolver(places=where) as r:
            copies = [c for c in r.copies(nm, owner, where) if c.where != "here"]
            for w in r.where(where):
                t = r.source(w).tombstone(obj_id) if r.source(w) else None
                if t:
                    print(f"Warning: {obj_id} was taken down at {w} on {t.get('date')} ({t.get('reason')}); "
                          "this archive decides whether to keep its mirror, and answers for what it serves "
                          "(section 13.3)", file=sys.stderr)
            if not copies:
                sys.exit(f"no copy of {obj_id} found at {', '.join(where) or 'the places given'}")
            log = record_key_log(r, owner)
            if log is None:
                sys.exit(f"no copy of the key log of {owner} found beside the line: a copy holds it beside "
                         "every line (section 6.5)")
            <<mirrors: the copy to take, and how far>>
            <<mirrors: check the mirror held, the licences and the tombstone>>
            <<mirrors: copy the versions into the storage root>>
        if label:
            P.LABELS[label] = obj_id
        remember(obj_id, where)
        P.write_discovery()

The copy taken. A frozen owner takes nothing (rule 3). Each copy is judged
against the key log held; the one with the latest signed version is
taken, and the others must agree with it, or the fork of the line is
reported and nothing is copied (rule 4; section 12.3: a reader does not
choose between signed sides). The versions copied stop at the latest
signed version, which is never contested (rule 2): a later contested
version stays out, and so does anything unsigned after it.

    # in mirrors: the copy to take, and how far:
    if log.fork_point:
        sys.exit(f"the key log of {owner} forks at v{log.fork_point}: the owner is frozen, and no version of "
                 "its lines is added here (section 7.5)")
    for c in copies:
        c.statuses = P.line_statuses(c.dir, c.inv, log)[1]
    copies.sort(key=lambda c: -c.latest_signed)
    source = copies[0]
    if not source.latest_signed:
        sys.exit(f"{obj_id}: no copy found has a signed version that is not contested (section 7.5)")
    for c in copies[1:]:
        if not source.agrees(c):
            sys.exit(f"{obj_id}: the copies at {source.where} and {c.where} do not agree: a fork of the line "
                     "(section 7.4), not copied")
    target = source.latest_signed
    for n, s in enumerate(source.statuses[target:], target + 1):
        print(f"{obj_id} v{n}: {s} at {source.where}: not added (section 7.5)")

The mirror held, if any, must agree with the copy (section 11.1): the
copy's inventory of the mirror's head is the same file. Every version
copied that is not under a licence known to be open is reported, unless
the curator has said that the copy is allowed (section 11.2). A tombstone of the line lets it return only from a copy
holding the version it pins (section 13.2).

    # in mirrors: check the mirror held, the licences and the tombstone:
    d = P.obj_dir(obj_id)
    inv = P.load_inventory(d)
    held = int(inv["head"][1:]) if inv else 0
    if held:
        k = min(held, target)
        if source.digest(k) != names.sha512_hex((d / f"v{k}" / "inventory.json").read_bytes()):
            sys.exit(f"{obj_id}: the copy at {source.where} does not agree with the mirror held here: a "
                     "fork of the line (section 7.4); the mirror keeps its own side")
    for n in range(held + 1, target + 1):
        dc = source.read("datacite.json", n) or {}
        if not licence_checked and not is_open(dc.get("rightsList")):
            print(f"Warning: {obj_id} v{n}: its licence is not one known to allow redistribution; the archive "
                  "answers for the copy (section 11.2); give --licence-checked if it is allowed",
                  file=sys.stderr)
    from . import takedown
    if not held and not takedown.may_return(obj_id, lambda n, dig: source.digest(n) == dig):
        sys.exit(f"{obj_id} was taken down here: it returns only from a copy holding the version its "
                 "tombstone pins (section 13.2)")

The copy. The object is fetched from the copy's archive, up to the target
version, every file checked against its digest, into a staging folder of
the archive, and moved into place: a new mirror whole, an existing one by
its new version folders, its new witness folders and its root inventory.
Witnesses of versions held are added when new; a witness file of the same
name with other bytes is reported, and the mirror keeps its own
(section 11.1). Files of the witness folder that are not witnesses are not
copied when they cannot be named (over HTTP), which is not removing them
(section 7.2).

    # in mirrors: copy the versions into the storage root:
    stage = Path(tempfile.mkdtemp(dir=P.ROOT, prefix=".staging-"))
    try:
        new = stage / "object"
        try:
            remote.fetch_object(source.src or remote.Source(source.where), obj_id, new, upto=target,
                                witness_names=remote.line_witness_names(log),
                                warn=lambda m: print(f"Warning: {m}; the mirror gets a checksum file "
                                                     "that states it", file=sys.stderr))
        except remote.Unavailable as e:
            sys.exit(str(e))
        if not held:
            d.parent.mkdir(parents=True, exist_ok=True)
            os.rename(new, d)
            print(f"{obj_id}: mirrored, v1 to v{target}, from {source.where}")
        else:
            for n in range(held + 1, target + 1):
                os.rename(new / f"v{n}", d / f"v{n}")
            added = 0
            for n in range(1, target + 1):
                w_new, w_old = new / sign.WITNESSES / f"v{n}", d / sign.WITNESSES / f"v{n}"
                for f in sorted(w_new.iterdir()) if w_new.is_dir() else []:
                    if not (w_old / f.name).exists():
                        w_old.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(f, w_old / f.name)
                        added += 1
                    elif (w_old / f.name).read_bytes() != f.read_bytes():
                        print(f"warning: {obj_id} v{n}: {f.name} at {source.where} differs from the one "
                              "held here, which is kept (section 11.1)", file=sys.stderr)
            if target > held:
                for name in ("inventory.json", "inventory.json.sha512"):
                    os.replace(new / name, d / name)
            print(f"{obj_id}: v{held + 1} to v{target} added from {source.where}" if target > held
                  else f"{obj_id}: up to date (v{held})" + (f", {added} witness file(s) added" if added else ""))
    finally:
        shutil.rmtree(stage, ignore_errors=True)

The places a mirror was made from are remembered in the configuration,
under `mirrors`, so that `osheaf mirror --all` can bring every mirror up
to date; they are hints like any location, and the discovery document
does not show them.

    # in mirrors: mirroring a line:
    def remember(obj_id, where):
        cfg_path = P.ROOT / P.CONFIG_NAME
        if not cfg_path.exists() or not where:
            return
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        known = cfg.setdefault("mirrors", {}).setdefault(obj_id, [])
        if all(w in known for w in where):
            return
        known += [w for w in where if w not in known]
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        P.ARCHIVE["mirrors"] = cfg["mirrors"]

The commands
------------

`osheaf mirror URI` mirrors the line a `sheaf:` URI names, at the URI's
`at` and the places given with `--at` (base URLs or folders); a label
gives it a readable name here. Without an owner part, the URI names the
originator's line, which the resolver finds. `osheaf mirror --all` brings
every mirror up to date from the places remembered; a mirror that cannot
be brought up to date (no copy found, a fork) is reported, and the others
go on.

    # in mirrors: the commands:
    def main(args):
        if getattr(args, "all", False):
            for obj_id, where in sorted((P.ARCHIVE.get("mirrors") or {}).items()):
                _, nm, owner = obj_id.split(":")
                if (P.obj_dir(obj_id) / "inventory.json").exists():
                    try:
                        mirror_line(nm, owner, where, licence_checked=args.licence_checked)
                    except SystemExit as e:
                        print(f"{obj_id}: {e}", file=sys.stderr)
            return
        if not args.uri:
            sys.exit("osheaf mirror URI, or --all")
        if args.label and (not P.LABEL_RE.match(args.label) or args.label in P.LABELS):
            sys.exit(f"{args.label}: a label of the form of section 3.1, not given to another line")
        where = list(args.at or [])
        with remote.Resolver(places=where) as r:
            try:
                u = names.parse_sheaf(args.uri, short=True, fold=True)
                nm, owner = r.expand(u, r.where([u.at] if u.at else []))
            except ValueError as e:
                sys.exit(str(e))
        where = ([u.at] if u.at else []) + where
        mirror_line(nm, owner, where, licence_checked=args.licence_checked, label=args.label)

`osheaf owner pull URL|PATH` meets the archive's copy of an owner's key log
(by default its own owner's) with the copy held at another place: an
archive, by its base URL or folder, or the folder of the owner object
itself. Pulling is how an owner that rotated its keys in one archive
brings its other archives up to date, and how an archive learns of a
fork; it is also how a key log is copied on its own (section 6.5).

    # in mirrors: the commands:
    def owner_pull(args):
        owner = getattr(args, "owner", None) or P.ARCHIVE["owner"]
        place = args.source
        folder = Path(place)
        with remote.Resolver(places=[]) as r:
            if folder.is_dir() and (folder / "inventory.json").is_file() and not (folder / "opensheaf.json").exists():
                try:
                    other = owners.load_key_log(folder)
                except owners.OwnerError as e:
                    sys.exit(str(e))
                if other.owner != owner:
                    P.stop(f"{place} is the key log of {names.short(other.owner)}, not of {names.short(owner)}")
                r.key_log(owner)
                r.logs[owner]["found"].append((place, other))
            else:
                r.key_log(owner, [place])
            if not any(w != "here" for w, _ in r.found_logs(owner)):
                P.stop(f"no copy of the key log of {names.short(owner)} at {place}")
            log = record_key_log(r, owner)
        P.write_discovery()
        if log is not None:
            print(f"The key log of {names.short(owner)} is here up to v{len(log.versions)}" +
                  (f"; it was ended by a fork at v{log.fork_point}." if log.fork_point else
                   "; the owner has ended." if log.ended else "."))
