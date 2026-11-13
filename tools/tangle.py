#!/usr/bin/env python3
# Generated from literate/90-tangle.md by tools/tangle.py: edit the document, not this file.
"""Tangle the literate sources of opensheaf-py: write the program files.

    python3 tools/tangle.py              write every file defined in literate/
    python3 tools/tangle.py --check      exit 1 if a file differs from its document
    python3 tools/tangle.py --out DIR    write the files under DIR instead
    python3 tools/tangle.py --list       list the files and the chunks
    python3 tools/tangle.py --where src/opensheaf/core.py:120
                                         the document line a program line comes from
"""
import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HEADER = re.compile(r"^[^\w\s]*\s*in (.+?):\s*[^\w\s]*$")
REFERENCE = re.compile(r"^(\s*)<<(.+?)>>\s*$")
FENCE = re.compile(r"^ {0,3}(```|~~~)")
FILE = re.compile(r"^[\w.-]*[/.][\w./-]*$")


COMMENTS = {".py": "# {}", "": "# {}", ".sh": "# {}", ".toml": "# {}",
            ".yml": "# {}", ".yaml": "# {}"}
NOTICE = "Generated from {doc} by tools/tangle.py: edit the document, not this file."

@dataclass
class Block:
    doc: Path        # the document
    start: int       # its first line in the document, counting from 0
    end: int         # the line after its last
    name: str        # the chunk it belongs to
    header: bool     # whether its first line is a header
    lines: list      # its program lines, without the four spaces

    @property
    def first(self):
        """The line of the document, counting from 1, of its first program line."""
        return self.start + 1 + self.header


def is_blank(line):
    return not line.strip()


def is_indented(line):
    return line.startswith("    ")


def blocks(doc, text=None):
    """The code blocks of a document, in order."""
    if text is None:
        text = doc.read_text(encoding="utf-8")
    lines = text.split("\n")
    found, name, fenced, i = [], None, False, 0
    while i < len(lines):
        line = lines[i]
        if FENCE.match(line):
            fenced = not fenced
        elif (not fenced and is_indented(line) and not is_blank(line)
              and (i == 0 or is_blank(lines[i - 1]))):
            start = i
            while i < len(lines) and (is_indented(lines[i]) or is_blank(lines[i])):
                i += 1
            end = i
            while is_blank(lines[end - 1]):
                end -= 1
            code = ["" if is_blank(line) else line[4:] for line in lines[start:end]]
            header = HEADER.match(code[0])
            if header:
                name, code = header.group(1), code[1:]
            elif name is None:
                raise SystemExit(f"{doc}:{start + 1}: a code block before the first chunk name")
            found.append(Block(doc, start, end, name, bool(header), code))
            for n in range(1, len(code)):
                if not code[n - 1] and HEADER.match(code[n]) and not code[n].startswith("#!"):
                    print(f"{doc}:{start + n + 1 + bool(header)}: a header inside a code block "
                          "(put some prose before it)", file=sys.stderr)
            i = end
            continue
        i += 1
    return found


def documents(folder="literate"):
    """The literate documents, in reading order."""
    return sorted(Path(folder).glob("*.md"), key=lambda d: (d.name != "index.md", d.name))


def read_chunks(docs):
    """The fragments of every chunk, by name."""
    chunks = {}
    for doc in docs:
        for block in blocks(doc):
            chunks.setdefault(block.name, []).append(block)
    return chunks

def expand(chunks, name, indent, out, python, stack=()):
    """Append the lines of chunk `name` to `out` as (text, document, line)."""
    if name not in chunks:
        raise SystemExit(f"<<{name}>> is used in <<{stack[-1]}>> but never defined")
    if name in stack:
        raise SystemExit("<<{}>> includes itself: {}".format(name, " > ".join(stack + (name,))))
    gap = 2 if python and indent == "" else 1
    for k, block in enumerate(chunks[name]):
        if k:
            out.extend([("", None, None)] * gap)
        for n, line in enumerate(block.lines):
            ref = REFERENCE.match(line)
            if ref:
                expand(chunks, ref.group(2), indent + ref.group(1), out, python, stack + (name,))
            else:
                out.append((indent + line if line else "", block.doc, block.first + n))

def file_names(chunks):
    return [name for name in chunks if FILE.match(name)]


def tangle(chunks, name):
    """The text of file `name`, and where each of its lines comes from."""
    out = []
    expand(chunks, name, "", out, name.endswith(".py"))
    comment = COMMENTS.get(Path(name).suffix)
    if comment:
        notice = comment.format(NOTICE.format(doc=chunks[name][0].doc.as_posix()))
        at = 1 if out and out[0][0].startswith("#!") else 0
        out.insert(at, (notice, None, None))
    return "\n".join(text for text, _, _ in out) + "\n", out


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    if text.startswith("#!"):
        path.chmod(path.stat().st_mode | 0o111)


def unused(chunks):
    used = {ref.group(2) for fragments in chunks.values() for block in fragments
            for line in block.lines for ref in [REFERENCE.match(line)] if ref}
    return [name for name in chunks if name not in used and not FILE.match(name)]

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("documents", nargs="*", type=Path,
                   help="the literate documents (default: literate/*.md)")
    p.add_argument("--out", type=Path, default=Path("."), help="where to write the files")
    p.add_argument("--check", action="store_true",
                   help="write nothing; exit 1 if a file differs from its document")
    p.add_argument("--list", action="store_true", help="list the files and the chunks")
    p.add_argument("--where", metavar="FILE:LINE",
                   help="the line of the document a line of a file comes from")
    args = p.parse_args(argv)
    chunks = read_chunks(args.documents or documents())
    for name in unused(chunks):
        block = chunks[name][0]
        print(f"{block.doc}:{block.start + 1}: <<{name}>> is never used", file=sys.stderr)
    if args.list:
        for name in file_names(chunks):
            print(f"{name}  ({chunks[name][0].doc})")
        print()
        for name, fragments in chunks.items():
            if not FILE.match(name):
                print(f"<<{name}>>  " + ", ".join(f"{b.doc.name}:{b.start + 1}" for b in fragments))
        return
    if args.where:
        name, line = args.where.rsplit(":", 1)
        _, lines = tangle(chunks, name)
        _, doc, n = lines[int(line) - 1]
        print(f"{doc}:{n}" if doc else "a line added by the tangler")
        return

    stale = []
    for name in file_names(chunks):
        text, _ = tangle(chunks, name)
        path = args.out / name
        if path.exists() and path.read_bytes() == text.encode("utf-8"):
            continue
        stale.append(name)
        if not args.check:
            write(path, text)
    if args.check and stale:
        sys.exit("not as the documents say (run tools/build): " + ", ".join(stale))
    for name in stale:
        print("wrote", name)

if __name__ == "__main__":
    main()
