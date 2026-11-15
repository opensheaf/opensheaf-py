The templates of the website
============================

The pages of the [website](30-website.md) are filled into three default
templates, kept in the package under `src/opensheaf/templates/`: the
home page, the landing page of a document, and the style sheet. `osheaf
init` copies them into the new archive's `templates` folder, where the
curator may change them freely; the copies, not these files, are then
used. An archive whose home page is a [TeXmacs index](16-index.md) uses
only the last two, and may put its own `paper.html` in its `templates`
folder to give the landing pages the look of its other pages. This chapter shows the defaults, and the placeholders each
template receives.

The templates are plain HTML and CSS, with placeholders `{{name}}` that
the website fills by string substitution. They are copied into archives
and served to readers, so, unlike the Python files, they carry no
notice saying where they were generated from. Mathematics in titles and
abstracts is typeset in the browser by MathJax, which both pages load.

What the pages share
--------------------

Both pages declare their character set and let a phone show them at its
own width.

    <!-- in the character set and viewport of a page: -->
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">

MathJax is configured, before it loads, to read mathematics between
single dollar signs, as section 8 of the specification writes it in
titles and abstracts, and to read `\$` as a literal dollar sign. Its
version is fixed, so that a new release cannot change the pages
unannounced; `defer` lets the page appear before the mathematics is
typeset.

    <!-- in MathJax for the mathematics of a page: -->
    <script>window.MathJax = {tex: {inlineMath: [['$', '$']], processEscapes: true}};</script>
    <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js"></script>

The home page
-------------

The home page receives:

- `{{archive_name}}`, the name of the archive, and `{{root}}`, the way
  back to the root of the archive (empty here);
- `{{lead}}`, the lead paragraph, in HTML;
- `{{papers}}`, the entries of the members of the main collection, as
  items of a list;
- `{{featured}}`, the featured collection (`index.html.featured`), a
  section with its title and the entries of its members, and
  `{{papers_heading}}`, a heading for the main collection's list when
  there is one; both are empty otherwise, and a template written before
  they existed simply does not show the featured collection;
- `{{count}}`, their number, and `{{updated}}`, the date of the pages.

The footer links the [OpenSheaf Explorer](https://opensheaf.org/explorer/), which
reads the archive from the browser, shows its objects, versions and
collections, and checks it as `osheaf verify` does; it is given the
archive's address in its `url` parameter.

It also receives `{{base_url}}`, the base URL of the archive, which the
default gives to the Explorer. Its head links the discovery document with
`describedby`, the start of everything for a program that reads the
archive.

    <!-- in src/opensheaf/templates/index.html: -->
    <!doctype html>
    <html lang="en">
    <head>
    <<the character set and viewport of a page>>
    <title>{{archive_name}}</title>
    <link rel="stylesheet" href="{{root}}style.css">
    <link rel="describedby" href="{{root}}opensheaf.json" type="application/json">
    <<MathJax for the mathematics of a page>>
    </head>
    <body>
    <header>
      <h1>{{archive_name}}</h1>
      <p class="lead">{{lead}}</p>
    </header>
    <main>
    {{featured}}
    {{papers_heading}}
      <ol class="papers">
    {{papers}}
      </ol>
    </main>
    <<the footer of the home page>>
    </body>
    </html>

The footer says how the pages were made, and that the format is a
draft: a reader should not take the archive's form as settled.

    <!-- in the footer of the home page: -->
    <footer>
      <p>{{count}} documents · updated {{updated}} ·
      made with <a href="https://github.com/opensheaf/opensheaf-py">opensheaf-py</a> ·
      format <a href="https://opensheaf.org">OpenSheaf 0.1</a> (a draft, which may still change)</p>
      <p><a href="https://opensheaf.org/explorer/?url={{base_url}}">Explore and verify this archive</a>
      with the OpenSheaf Explorer, in the browser</p>
    </footer>

The landing page
----------------

The landing page of a document receives, besides `{{archive_name}}`,
`{{base_url}}` and `{{root}}` (here `../../`):

- `{{head}}`, the tags for search engines, to be put in the head as they
  are;
- `{{title}}`, `{{authors}}`, `{{issued}}` (the date of first
  appearance) and `{{abstract}}` (paragraphs in HTML);
- `{{pdf}}`, the address of the PDF of the version presented: the current
  version, or for a member of a selection the last revision vetted (for a
  version without a PDF, its entry in the list of versions);
- `{{html_link}}`, the link to the HTML version of a TeXmacs document,
  preceded by its separator (` · <a href="...">HTML</a>`), or nothing;
- `{{withdrawn}}`, the withdrawal notice, empty for a document that is
  not withdrawn;
- `{{versions}}`, the versions, as items of a list;
- `{{cite}}`, the suggested citation, and `{{licence}}`, the licence,
  linked when it has an address;
- `{{pin}}`, the pin by which the collection fixes the document (the head
  of the object for a catalogue, the last revision for a
  selection), and `{{pin_url}}`, the address of the inventory it is the
  digest of.

    <!-- in src/opensheaf/templates/paper.html: -->
    <!doctype html>
    <html lang="en">
    <head>
    <<the character set and viewport of a page>>
    <title>{{title}} · {{archive_name}}</title>
    {{head}}
    <link rel="stylesheet" href="{{root}}style.css">
    <<MathJax for the mathematics of a page>>
    </head>
    <body>
    <nav><a href="{{root}}">{{archive_name}}</a></nav>
    <main class="paper-page">
      <<the document on its landing page>>
      <section>
        <h2>Versions</h2>
        <ol class="versions">
    {{versions}}
        </ol>
      </section>
      <<the citation on a landing page>>
    </main>
    <footer>
      <p>An <a href="https://opensheaf.org">OpenSheaf</a> archive (format 0.1, a draft, which may still change) ·
      made with <a href="https://github.com/opensheaf/opensheaf-py">opensheaf-py</a></p>
    </footer>
    </body>
    </html>

The versions are written in the file itself rather than in a part of
their own, because `{{versions}}` stands at the left margin: a part is
indented as its reference is, and the placeholder would move. They come
in the order of the history, the last first.

The page presents the version the collection presents, usually the
current version of the document; the withdrawal
notice, when there is one, comes before anything else about it, as
section 11.1 requires.

    <!-- in the document on its landing page: -->
    <h1>{{title}}</h1>
    <p class="paper-authors">{{authors}}</p>
    <p class="paper-meta">First issued {{issued}} · <a href="{{pdf}}">PDF</a>{{html_link}}</p>
    {{withdrawn}}
    <section class="abstract">
      <h2>Abstract</h2>
      {{abstract}}
    </section>

The last section is for those who cite or check: the citation, the
licence, and the pin by which the collection fixes the document, linked
to the inventory whose digest it is. Anyone can download the inventory, compute its SHA-512,
and compare.

    <!-- in the citation on a landing page: -->
    <section>
      <h2>Cite</h2>
      <p class="cite">{{cite}}</p>
      <p class="small">Licence: {{licence}}</p>
      <p class="small">Pin in the collection (SHA-512 of the inventory it fixes):
      <a href="{{pin_url}}"><code>{{pin}}</code></a></p>
    </section>

The style sheet
---------------

The style sheet is copied as it is, without placeholders. It is meant to
be edited, and says so. It follows the design of `opensheaf.org`,
described in the site's
[style](https://github.com/opensheaf/opensheaf.github.io/blob/main/.agents/skills/opensheaf-style/SKILL.md):
an archive's pages are documents, read like a mathematical text. A page
is a sheet of warm paper with black ink, in one column; the titles, the
authors, the abstracts and the text are set in CMU Serif, the Computer
Modern of TeX and TeXmacs, which also matches the mathematics MathJax
typesets; the apparatus around them (dates, facts, tags, the footer) in
the small IBM Plex Sans of the site, in grey; digests and code in
JetBrains Mono. Hierarchy comes from size, space and weight, not from
colour: headings in bold, links in ink with a thin grey underline. Three
quiet tones only say a state: green for the current version, red for a
withdrawal, amber for warnings.

    /* in src/opensheaf/templates/style.css: */
    /* The default style of an OpenSheaf archive (opensheaf-py); edit freely. */
    <<the faces of the default style>>
    <<the colours of the default style>>
    <<the page and its type in the default style>>
    <<the list of documents in the default style>>
    <<the versions in the default style>>
    <<notices and citations in the default style>>

The faces are those of the site and are loaded from it; an archive is
served from elsewhere, and the site allows it. A page read without a
network, or from a site that cannot reach `opensheaf.org`, falls back on
the faces of the system named with the colours below. An archive that
wants no font from elsewhere removes these lines.

    /* in the faces of the default style: */
    @font-face { font-family: "CMU Serif"; font-style: normal; font-weight: 400; font-display: swap;
      src: url("https://opensheaf.org/resources/fonts/cmu/cmunrm.woff2") format("woff2"); }
    @font-face { font-family: "CMU Serif"; font-style: italic; font-weight: 400; font-display: swap;
      src: url("https://opensheaf.org/resources/fonts/cmu/cmunti.woff2") format("woff2"); }
    @font-face { font-family: "CMU Serif"; font-style: normal; font-weight: 600 700; font-display: swap;
      src: url("https://opensheaf.org/resources/fonts/cmu/cmunbx.woff2") format("woff2"); }
    @font-face { font-family: "CMU Serif"; font-style: italic; font-weight: 600 700; font-display: swap;
      src: url("https://opensheaf.org/resources/fonts/cmu/cmunbi.woff2") format("woff2"); }
    @font-face { font-family: "IBM Plex Sans"; font-style: normal; font-weight: 100 700; font-display: swap;
      src: url("https://opensheaf.org/resources/fonts/plex/IBMPlexSans-Roman.woff2") format("woff2"); }
    @font-face { font-family: "IBM Plex Sans"; font-style: italic; font-weight: 100 700; font-display: swap;
      src: url("https://opensheaf.org/resources/fonts/plex/IBMPlexSans-Italic.woff2") format("woff2"); }
    @font-face { font-family: "JetBrains Mono"; font-style: normal; font-weight: 100 800; font-display: swap;
      src: url("https://opensheaf.org/resources/fonts/jetbrains/JetBrainsMono-Roman.woff2") format("woff2"); }

The colours and the faces are the block of variables `--os-*` of the
site's stylesheet (`resources/opensheaf.css`), copied whole, never one
value at a time: the paper, the surface of tinted blocks, the hairlines,
the ink, the secondary text, the faint grey of bullets and underlines,
the three states with their tints; light, dark (following the reader's
system) and print.

    /* in the colours of the default style: */
    :root {
        color-scheme: light;
        --os-paper: #f9f8f5;
        --os-surface: #f1efea;
        --os-rule: #dedbd3;
        --os-ink: #171716;
        --os-muted: #6a6861;
        --os-faint: #a09d95;
        --os-ok: #2c6a3e;
        --os-ok-bg: #e6efe4;
        --os-bad: #9d2b22;
        --os-bad-bg: #f6e4e0;
        --os-warn: #7d5200;
        --os-warn-bg: #f5ecd6;
        --os-serif: "CMU Serif", "Latin Modern Roman", "Computer Modern", "Times New Roman", serif;
        --os-sans: "IBM Plex Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        --os-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    }
    @media (prefers-color-scheme: dark) {
        :root:not([data-theme="light"]) {
            color-scheme: dark;
            --os-paper: #12141a;
            --os-surface: #1b1e25;
            --os-rule: #31353e;
            --os-ink: #e6e7ea;
            --os-muted: #9a9ea8;
            --os-faint: #646975;
            --os-ok: #93cfa1;
            --os-ok-bg: #182a23;
            --os-bad: #eda59c;
            --os-bad-bg: #342025;
            --os-warn: #e7c277;
            --os-warn-bg: #2d281c;
        }
    }
    :root[data-theme="dark"] {
        color-scheme: dark;
        --os-paper: #12141a;
        --os-surface: #1b1e25;
        --os-rule: #31353e;
        --os-ink: #e6e7ea;
        --os-muted: #9a9ea8;
        --os-faint: #646975;
        --os-ok: #93cfa1;
        --os-ok-bg: #182a23;
        --os-bad: #eda59c;
        --os-bad-bg: #342025;
        --os-warn: #e7c277;
        --os-warn-bg: #2d281c;
    }
    @media print {
        :root, :root[data-theme] {
            color-scheme: light !important;
            --os-paper: #fff !important;
            --os-surface: #fff !important;
            --os-rule: #999 !important;
            --os-ink: #000 !important;
            --os-muted: #333 !important;
            --os-faint: #666 !important;
            --os-ok: #000 !important;
            --os-ok-bg: #fff !important;
            --os-bad: #000 !important;
            --os-bad-bg: #fff !important;
            --os-warn: #000 !important;
            --os-warn-bg: #fff !important;
        }
    }

The column is at most 36 rem of text, at 20 pixels (18 on a phone), with
a margin of 16 pixels on narrow screens. The title of a page is centred,
like the title of a paper, with the authors in italics and the first
facts below it; on a landing page, the name of the archive stands above
it, on the left, as a masthead. Secondary text (dates, metadata, pins,
the footer) is in the small grey sans.

    /* in the page and its type in the default style: */
    * { box-sizing: border-box; }
    html { font-size: 20px; }
    @media (max-width: 40rem) { html { font-size: 18px; } }
    body { margin: 0; background: var(--os-paper); color: var(--os-ink); font-family: var(--os-serif);
           font-size: 1rem; line-height: 1.6; font-variant-numeric: lining-nums;
           -webkit-font-smoothing: antialiased; }
    header, main, footer, nav { max-width: calc(36rem + 32px); margin: 0 auto; padding: 0 16px; }
    header { padding-top: 3rem; text-align: center; }
    h1, h2 { font-weight: 700; line-height: 1.2; text-wrap: balance; }
    h1 { font-size: 2.1rem; letter-spacing: -0.01em; margin: 0.3em 0 0.4em; text-align: center; }
    h2 { font-size: 1.2rem; margin: 2em 0 0.5em; }
    a { color: inherit; text-decoration: underline; text-decoration-thickness: 1px;
        text-underline-offset: 0.2em; text-decoration-color: var(--os-faint); }
    a:hover, a:focus { text-decoration-color: currentColor; }
    .lead { font-style: italic; margin: 0 0 2.5rem; }
    .small, footer, .paper-meta, .version-date, .pin, details summary {
      font-family: var(--os-sans); color: var(--os-muted); }
    .small, footer { font-size: 0.7rem; line-height: 1.5; }
    nav { padding-top: 1.4rem; font-size: 1.05rem; }
    nav a { text-decoration: none; }
    footer { margin-top: 4rem; padding-bottom: 2.5rem; }
    footer a { color: inherit; }

The home page is a list of entries divided by hairlines, as in a
bibliography: the title a little larger than the text, the authors in
italics, then a line of facts in the small sans. A withdrawn document
keeps its place, its title in grey with a tag in the red of withdrawals.

    /* in the list of documents in the default style: */
    ol.papers { list-style: none; padding: 0; margin: 0; border-top: 1px solid var(--os-rule); }
    section.featured { margin: 0 0 3rem; }
    main > h2 { margin-top: 0; }
    li.paper { padding: 1rem 0; border-bottom: 1px solid var(--os-rule); }
    .paper-title { font-weight: 700; font-size: 1.1rem; text-decoration: none; }
    .paper-title:hover { text-decoration: underline; }
    .paper-authors { margin: 0.15rem 0; font-style: italic; }
    .paper-page .paper-authors, .paper-page .paper-meta { text-align: center; }
    .paper-meta, .pin, .version-date { font-size: 0.72rem; }
    details summary { cursor: pointer; font-size: 0.72rem; margin-top: 0.3rem; }
    details p, .abstract p { margin: 0.5em 0; }
    li.paper.withdrawn .paper-title { color: var(--os-muted); }
    li.paper.withdrawn .paper-title::after { content: "withdrawn"; font-family: var(--os-sans); font-size: 0.6rem;
      font-weight: 400; padding: 0.1rem 0.55rem; border-radius: 999px; margin-left: 0.5rem; vertical-align: 0.2em;
      background: var(--os-bad-bg); color: var(--os-bad); }

The versions of a landing page are divided by hairlines too. The current
version is marked by a small tag in the green of what is current, the
stage by a tag on the surface.

    /* in the versions in the default style: */
    ol.versions { list-style: none; padding: 0; margin: 0; border-top: 1px solid var(--os-rule); }
    li.version { padding: 0.6rem 0; border-bottom: 1px solid var(--os-rule); }
    .version-head { font-weight: 700; }
    .stage, .current { font-family: var(--os-sans); font-size: 0.65rem; font-weight: 400; padding: 0.1rem 0.55rem;
                       border-radius: 999px; background: var(--os-surface); margin-left: 0.3rem;
                       vertical-align: 0.1em; }
    .current { background: var(--os-ok-bg); color: var(--os-ok); }
    .changes { font-style: italic; }
    .files { font-size: 0.9rem; }
    .missing { color: var(--os-muted); }

Notices stand on the surface, withdrawals on the red tint, without a
frame; the citation is on the surface too, to be copied. A pin is a long
string of hexadecimal digits, and may be broken anywhere.

    /* in notices and citations in the default style: */
    .notice, div.withdrawn { background: var(--os-surface); border-radius: 4px; padding: 0.7rem 1rem; margin: 0.6rem 0; }
    div.withdrawn { background: var(--os-bad-bg); color: var(--os-bad); }
    .cite { background: var(--os-surface); border-radius: 4px; padding: 0.7rem 1rem; font-size: 0.92rem; }
    code { font-family: var(--os-mono); font-size: 0.75em; word-break: break-all;
           font-variant-ligatures: none; }
