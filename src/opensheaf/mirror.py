# Generated from literate/22-mirrors.md by opensheaf-literate: edit the document, not this file.
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
        if not takedown.may_return(oid, lambda n, d: first.verified(n, d) is not None):
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
        stage = Path(tempfile.mkdtemp(dir=P.ROOT, prefix=".staging-"))
        try:
            new = stage / "object"
            try:
                remote.fetch_object(source.src or remote.Source(source.where), obj_id, new, upto=target,
                                    witness_names=remote.line_witness_names(log),
                                    warn=lambda m: print(f"Warning: {m}; the mirror gets a checksum file "
                                                         "that states it", file=sys.stderr),
                                    expect={n: source.digest(n) for n in range(1, target + 1)})
            except remote.Unavailable as e:
                sys.exit(str(e))
            judgements, _ = P.line_statuses(new, P.load_inventory(new), log)
            for n, js in enumerate(judgements, 1):
                w = new / sign.WITNESSES / f"v{n}"
                for j in js:
                    if j.status == sign.INVALID:
                        print(f"warning: {obj_id} v{n}: {j.file} at {source.where}: {j.reason}: not copied",
                              file=sys.stderr)
                        for f in [w / j.file] + sorted(w.glob(f"{j.file}.*")):
                            f.unlink(missing_ok=True)
            if sign.latest_signed(P.line_statuses(new, P.load_inventory(new), log)[1]) != target:
                sys.exit(f"{obj_id}: the copy at {source.where} is no longer signed up to v{target}: not copied")
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
    if label:
        P.LABELS[label] = obj_id
    remember(obj_id, where)
    P.write_discovery()


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
