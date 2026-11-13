#!/usr/bin/env python3
# Generated from literate/91-weave.md by tools/tangle.py: edit the document, not this file.
"""Weave the literate sources of opensheaf-py into a website.

    python3 tools/weave.py              write the pages into site/
    python3 tools/weave.py --out DIR    write them into DIR

Needs the packages markdown and pygments (pip install markdown pygments).
"""
import argparse
import html
import re
import sys
from pathlib import Path

import markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import BashLexer, TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tangle import FILE, REFERENCE, blocks, documents  # noqa: E402

REPOSITORY = "https://github.com/opensheaf/opensheaf-py"


def page_of(doc):
    return doc.stem + ".html"


def title_of(doc):
    lines = doc.read_text(encoding="utf-8").split("\n")
    for i, line in enumerate(lines):
        if line.startswith("# "):
            return line[2:].strip()
        if line.strip() and i + 1 < len(lines) and re.match(r"^=+\s*$", lines[i + 1]):
            return line.strip()
    return doc.stem


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def esc(text):
    return html.escape(text, quote=True)


class Web:
    """The documents, their code blocks, and how the chunks refer to one another."""

    def __init__(self, docs, branch="main"):
        self.docs, self.branch = docs, branch
        self.blocks = {doc: blocks(doc) for doc in docs}
        self.fragments = {}
        for doc in docs:
            for block in self.blocks[doc]:
                self.fragments.setdefault(block.name, []).append(block)
        self.anchor, self.number = {}, {}
        for name, fragments in self.fragments.items():
            for k, block in enumerate(fragments):
                self.anchor[block.doc, block.start] = f"{slug(name)}-{k + 1}"
                self.number[block.doc, block.start] = k
        self.users = {}
        for fragments in self.fragments.values():
            for block in fragments:
                for line in block.lines:
                    ref = REFERENCE.match(line)
                    if ref:
                        users = self.users.setdefault(ref.group(2), [])
                        if block.name not in [b.name for b in users]:
                            users.append(block)
        self.file = {}
        for name in self.fragments:
            if FILE.match(name):
                todo = [name]
                while todo:
                    chunk = todo.pop()
                    if chunk in self.file or chunk not in self.fragments:
                        continue
                    self.file[chunk] = name
                    todo.extend(ref.group(2) for block in self.fragments[chunk]
                                for line in block.lines for ref in [REFERENCE.match(line)] if ref)

    def href(self, block, here):
        anchor = self.anchor[block.doc, block.start]
        return f"#{anchor}" if block.doc == here else f"{page_of(block.doc)}#{anchor}"

    def chunk_link(self, name, here, css="ref"):
        if name not in self.fragments:
            return f'<span class="undefined">⟨{esc(name)}⟩</span>'
        return f'<a class="{css}" href="{self.href(self.fragments[name][0], here)}">⟨{esc(name)}⟩</a>'

    def lexer(self, name):
        file = self.file.get(name, "")
        try:
            return get_lexer_for_filename(file)
        except ClassNotFound:
            return BashLexer() if file.startswith("tools/") else TextLexer()

    def code_html(self, block, here):
        lines, refs = [], []
        for line in block.lines:
            ref = REFERENCE.match(line)
            if ref:
                lines.append(f"{ref.group(1)}CHUNKREF{len(refs)}X")
                refs.append(ref.group(2))
            else:
                lines.append(line)
        code = highlight("\n".join(lines) + "\n", self.lexer(block.name), HtmlFormatter(nowrap=True))
        for k, name in enumerate(refs):
            link = self.chunk_link(name, here)
            code = re.sub(rf'<span class="[^"]*">CHUNKREF{k}X</span>|CHUNKREF{k}X', lambda m: link, code)
        return code

    def block_html(self, block, here):
        name, fragments = block.name, self.fragments[block.name]
        k, anchor = self.number[block.doc, block.start], self.anchor[block.doc, block.start]
        title = f"<code>{esc(name)}</code>" if FILE.match(name) else f"⟨{esc(name)}⟩"
        notes = []
        if k > 0:
            notes.append(f'continues <a href="{self.href(fragments[k - 1], here)}">the fragment before</a>')
        if k + 1 < len(fragments):
            notes.append(f'continued <a href="{self.href(fragments[k + 1], here)}">further on</a>')
        users = self.users.get(name, [])
        if users:
            notes.append("used in " + ", ".join(
                f'<a href="{self.href(b, here)}">⟨{esc(b.name)}⟩</a>' for b in users))
        if FILE.match(name) and k == 0:
            notes.append(f'<a href="{REPOSITORY}/blob/{self.branch}/{name}">the file in the repository</a>')
        return (f'<div class="chunk" id="{anchor}">'
                f'<div class="chunk-name"><a href="#{anchor}">{title}</a> {"+≡" if k else "≡"}</div>'
                f'<pre class="code">{self.code_html(block, here)}</pre>'
                + (f'<div class="chunk-notes">{"; ".join(notes)}.</div>' if notes else "")
                + "</div>")

    def document_html(self, doc):
        lines = doc.read_text(encoding="utf-8").split("\n")
        parts, last = [], 0
        for k, block in enumerate(self.blocks[doc]):
            parts += lines[last:block.start] + ["", f"CHUNKBLOCK{k}X", ""]
            last = block.end
        parts += lines[last:]
        body = markdown.markdown("\n".join(parts), extensions=["tables", "fenced_code", "codehilite", "toc"],
                                 extension_configs={"codehilite": {"guess_lang": False, "css_class": "code"}})
        for k, block in enumerate(self.blocks[doc]):
            body = body.replace(f"<p>CHUNKBLOCK{k}X</p>", self.block_html(block, doc))
        body = re.sub(r'href="([\w.-]+)\.md(#[^"]*)?"',
                      lambda m: f'href="{m.group(1)}.html{m.group(2) or ""}"', body)
        return re.sub(r"<blockquote>\s*<p>\[!(WARNING|NOTE|IMPORTANT|TIP|CAUTION)\]\s*",
                      lambda m: f'<blockquote class="alert {m.group(1).lower()}"><p>', body)

    def index_html(self):
        here = Path("chunks.md")
        files = [n for n in self.fragments if FILE.match(n)]
        rows = "".join(
            f'<tr><td><a href="{self.href(self.fragments[n][0], here)}"><code>{esc(n)}</code></a></td>'
            f'<td>{esc(title_of(self.fragments[n][0].doc))}</td></tr>' for n in files)
        items = []
        for name in sorted((n for n in self.fragments if not FILE.match(n)), key=str.lower):
            fragments = ", ".join(f'<a href="{self.href(b, here)}">{k + 1}</a>'
                                  for k, b in enumerate(self.fragments[name]))
            users = ", ".join(f'<a href="{self.href(b, here)}">⟨{esc(b.name)}⟩</a>'
                              for b in self.users.get(name, []))
            items.append(f"<li>{self.chunk_link(name, here)}: {fragments}"
                         + (f"; used in {users}" if users else "") + "</li>")
        return ("<h1>Files and chunks</h1><h2>Files</h2>"
                f"<table><tr><td>File</td><td>Made in</td></tr>{rows}</table>"
                f'<h2>Chunks</h2><ul class="chunks">{"".join(items)}</ul>')


def fill(template, **values):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], template)


def write_pages(web, out, template):
    pages = [(page_of(d), title_of(d)) for d in web.docs] + [("chunks.html", "Files and chunks")]
    for k, (page, title) in enumerate(pages):
        body = web.index_html() if page == "chunks.html" else web.document_html(web.docs[k])
        nav = "".join(f'<li{" class=current" if p == page else ""}><a href="{p}">{esc(t)}</a></li>'
                      for p, t in pages)
        turn = ""
        if k > 0:
            turn += f'<a class="prev" href="{pages[k - 1][0]}">← {esc(pages[k - 1][1])}</a>'
        if k + 1 < len(pages):
            turn += f'<a class="next" href="{pages[k + 1][0]}">{esc(pages[k + 1][1])} →</a>'
        (out / page).write_text(fill(template, title=esc(title), nav=f"<ol>{nav}</ol>", body=body,
                                     turn=turn, repository=REPOSITORY), encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("documents", nargs="*", type=Path,
                   help="the literate documents (default: literate/*.md)")
    p.add_argument("--out", type=Path, default=Path("site"), help="where to write the website")
    p.add_argument("--branch", default="main", help="the branch the links to files point to")
    args = p.parse_args(argv)
    tools = Path(__file__).resolve().parent
    web = Web(args.documents or documents(), args.branch)
    args.out.mkdir(parents=True, exist_ok=True)
    write_pages(web, args.out, (tools / "weave.html").read_text(encoding="utf-8"))
    light = HtmlFormatter(style="default").get_style_defs(".code")
    dark = HtmlFormatter(style="github-dark").get_style_defs(".code")
    css = (tools / "weave.css").read_text(encoding="utf-8")
    (args.out / "style.css").write_text(
        f"{light}\n@media (prefers-color-scheme: dark) {{\n{dark}\n}}\n{css}", encoding="utf-8")
    print(f"wove {len(web.docs) + 1} pages into {args.out}")


if __name__ == "__main__":
    main()
