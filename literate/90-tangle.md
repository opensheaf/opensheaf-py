Tangling: from the documents to the program
===========================================

The documents in `literate/` are the source of opensheaf-py. The Python
files of the package, its templates and the tools that build them are
*tangled* out of the documents by a small program, `tools/tangle.py`, which
is itself tangled out of this chapter. The files it writes are kept in the
repository, so that the package installs and runs as any other Python
package; the documents are what one edits, and the continuous integration
checks that the files are exactly what the documents say.

The idea, and the syntax, come from Kragen Sitaker's
[handaxeweb](https://github.com/kragen/peg-bootstrap/blob/master/handaxeweb.md),
itself inspired by Phil Bewig's "The Essence of Literate Programming"
(1996): the essence of literate programming is rearranging chunks of code,
and a few dozen lines suffice for that. The documents are plain Markdown,
readable as they stand on GitHub and woven into a website by
`tools/weave.py` (next chapter).

The syntax
----------

- Program text is indented by four spaces, as a code block of Markdown.
- A code block whose first line is `in NAME:`, written as a comment of the
  language (`# in NAME:`, `<!-- in NAME: -->`, `/* in NAME: */`), starts a
  *fragment* of the chunk called NAME. That first line is not part of the
  program. A code block without it continues the last chunk of the same
  document.
- A line consisting only of `<<NAME>>`, after any indentation, is replaced
  by the chunk NAME, every line indented as the reference is. Only whole
  lines are references: `<<` is also an operator of Python.
- A chunk may have many fragments, anywhere in the documents; they are put
  together in the order of the documents (`index.md` first, then the others
  by name) and, in each, in the order they appear. Fragments are separated
  by one blank line, or by two when the chunk stands at the left margin of a
  Python file, where PEP 8 wants two blank lines between definitions.
- A chunk whose name looks like a path (`src/opensheaf/core.py`,
  `tools/build`: a name without spaces containing `/` or `.`) is a file:
  tangling writes it, relative to the root of the repository.
- Fenced code blocks (between lines of three backquotes) are illustrations:
  shell sessions, examples of files. They are never tangled.

handaxeweb also has versions of chunks (`in NAME v2:`), to keep several
versions of a program in one document. We leave them out: git keeps our
versions.

Here is a complete small example, with the program indented and the
reference on a line of its own:

```
    # in hello.py:
    import sys

    <<say hello>>

Saying hello needs only a print.

    # in say hello:
    print("hello", " ".join(sys.argv[1:]))
```

The program
-----------

`tools/tangle.py` reads the documents, collects the fragments of every
chunk, and writes every file chunk, expanding the references. It can also
check that the files are up to date, list the chunks, and tell from which
line of which document a line of a program comes, which is what one needs
when Python reports an error at a line of a tangled file.

    # in tools/tangle.py:
    #!/usr/bin/env python3
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

    <<the syntax as patterns>>

    <<reading the documents>>

    <<expanding the chunks>>

    <<the files>>

    <<the command line of the tangler>>

    if __name__ == "__main__":
        main()

### The syntax as patterns

A header is a line of the form `in NAME:`, with any punctuation (a comment
sign) before it and after the colon; a reference is a whole line
`<<NAME>>`; fences are lines starting, after at most three spaces, with
three backquotes or tildes; a file name is a name without spaces, with a
slash or a dot.

    # in the syntax as patterns:
    HEADER = re.compile(r"^[^\w\s]*\s*in (.+?):\s*[^\w\s]*$")
    REFERENCE = re.compile(r"^(\s*)<<(.+?)>>\s*$")
    FENCE = re.compile(r"^ {0,3}(```|~~~)")
    FILE = re.compile(r"^[\w.-]*[/.][\w./-]*$")

Every tangled file in which a comment is possible starts with a notice
saying where it comes from, after the `#!` line if there is one. Files
where a comment would be seen by others (the HTML templates, which are
copied into archives) or impossible (JSON) get no notice.

    # in the syntax as patterns:
    COMMENTS = {".py": "# {}", "": "# {}", ".sh": "# {}", ".toml": "# {}",
                ".yml": "# {}", ".yaml": "# {}"}
    NOTICE = "Generated from {doc} by tools/tangle.py: edit the document, not this file."

### Reading the documents

A code block, for us as for Markdown, is a run of lines indented by four
spaces, after a blank line (or at the start of the document) and outside a
fenced block; blank lines inside the run belong to it, blank lines at its
end do not. We record for each block the document, the lines it occupies
(the weaver replaces them by its rendering), the chunk it belongs to,
whether it began with a header, and its lines without the four spaces.

    # in reading the documents:
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

The blocks of a document are found in one pass. Inside a fence nothing is
code; otherwise an indented line after a blank line starts a block, which
extends over the indented and blank lines that follow.

    # in reading the documents:
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
                <<read the block that starts at line i>>
                continue
            i += 1
        return found

The block ends before its trailing blank lines. If its first line is a
header, it names the chunk; otherwise the block continues the chunk of the
block before it, and a document cannot start with such a block.

    # in read the block that starts at line i:
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
    <<warn about a header inside the block>>
    i = end

Two code blocks separated only by a blank line are, for Markdown, one
block; a header in the second is then program text. That is almost always
a mistake: a sentence of prose between the blocks separates them.

    # in warn about a header inside the block:
    for n in range(1, len(code)):
        if not code[n - 1] and HEADER.match(code[n]) and not code[n].startswith("#!"):
            print(f"{doc}:{start + n + 1 + bool(header)}: a header inside a code block "
                  "(put some prose before it)", file=sys.stderr)

The chunks are the fragments of all documents, grouped by name, in the
order of the documents: `index.md` first, then the others in the order of
their names (which start with numbers).

    # in reading the documents:
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

### Expanding the chunks

Expanding a chunk appends its lines to a list, each with the document and
line it comes from (blank lines between fragments come from nowhere). A
reference is expanded in place, with the indentation of the reference
added to every line; a chunk that includes itself, directly or not, is an
error, as is a reference to a chunk that is not defined.

    # in expanding the chunks:
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

### The files

A file is the expansion of its chunk, with the notice, ending with a
newline. With the text we return the origin of every line, for `--where`.

    # in the files:
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

A file is written only when its text changes, so that the dates of the
others stay, and with Unix line ends whatever the system. A file that
starts with `#!` is a script and is made executable.

    # in the files:
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        if text.startswith("#!"):
            path.chmod(path.stat().st_mode | 0o111)

A chunk that is neither a file nor used anywhere is probably a mistake (a
misspelt name); we say so, without stopping.

    # in the files:
    def unused(chunks):
        used = {ref.group(2) for fragments in chunks.values() for block in fragments
                for line in block.lines for ref in [REFERENCE.match(line)] if ref}
        return [name for name in chunks if name not in used and not FILE.match(name)]

### The command line

    # in the command line of the tangler:
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
        <<list, locate, or write the files>>

Listing shows each file with the document that starts it, then each chunk
with the places of its fragments.

    # in list, locate, or write the files:
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

Otherwise every file is tangled and compared with what is on disk; with
`--check` the differences are only reported.

    # in list, locate, or write the files:
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

Building
--------

`tools/build` tangles the program, following `build_handaxeweb`: since the
tangler is tangled from its own document, a change to this chapter is only
accepted if the new tangler, run on the documents, reproduces itself. The
tangler of the repository tangles everything into a temporary folder; the
new tangler found there does the same again; the two must agree, and then
the new tangler writes the files. Finally the website is woven, if the
packages it needs are installed.

    # in tools/build:
    #!/bin/sh
    # Tangle the program out of literate/, checking that the tangler
    # reproduces itself, then weave the website into site/.
    set -e
    cd "$(dirname "$0")/.."
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    python3 tools/tangle.py --out "$tmp/a"
    python3 "$tmp/a/tools/tangle.py" --out "$tmp/b"
    diff -r "$tmp/a" "$tmp/b"
    python3 "$tmp/b/tools/tangle.py"
    if python3 -c "import markdown, pygments" 2>/dev/null; then
        python3 tools/weave.py --out site
    else
        echo "not weaving: pip install markdown pygments" >&2
    fi
