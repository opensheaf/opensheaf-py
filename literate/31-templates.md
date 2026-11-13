The templates of the website
============================

The pages of the [website](30-website.md) are filled into three default
templates, kept in the package under `src/opensheaf/templates/`: the
home page, the landing page of a document, and the style sheet. `osheaf
init` copies them into the new archive's `templates` folder, where the
curator may change them freely; the copies, not these files, are then
used. This chapter shows the defaults, and the placeholders each
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
- `{{papers}}`, the entries of the members, as items of a list;
- `{{count}}`, their number, and `{{updated}}`, the date of the pages.

It also receives `{{base_url}}`, the base URL of the archive, which the
default does not use. Its head links the discovery document with
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
    </footer>

The landing page
----------------

The landing page of a document receives, besides `{{archive_name}}`,
`{{base_url}}` and `{{root}}` (here `../../`):

- `{{head}}`, the tags for search engines, to be put in the head as they
  are;
- `{{title}}`, `{{authors}}`, `{{issued}}` (the date of first
  appearance) and `{{abstract}}` (paragraphs in HTML);
- `{{pdf}}`, the address of the PDF of the current version (for a version
  without a PDF, its entry in the list of versions);
- `{{withdrawn}}`, the withdrawal notice, empty for a document that is
  not withdrawn;
- `{{versions}}`, the versions, as items of a list;
- `{{cite}}`, the suggested citation, and `{{licence}}`, the licence,
  linked when it has an address;
- `{{pin}}`, the pin of the version shown, and `{{pin_url}}`, the
  address of the inventory it is the digest of.

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

The page presents the current version of the document; the withdrawal
notice, when there is one, comes before anything else about it, as
section 11.1 requires.

    <!-- in the document on its landing page: -->
    <h1>{{title}}</h1>
    <p class="paper-authors">{{authors}}</p>
    <p class="paper-meta">First issued {{issued}} · <a href="{{pdf}}">PDF of the current version</a></p>
    {{withdrawn}}
    <section class="abstract">
      <h2>Abstract</h2>
      {{abstract}}
    </section>

The last section is for those who cite or check: the citation, the
licence, and the pin of the version shown, linked to the inventory whose
digest it is. Anyone can download the inventory, compute its SHA-512,
and compare.

    <!-- in the citation on a landing page: -->
    <section>
      <h2>Cite</h2>
      <p class="cite">{{cite}}</p>
      <p class="small">Licence: {{licence}}</p>
      <p class="small">Pin of the current version (SHA-512 of its inventory):
      <a href="{{pin_url}}"><code>{{pin}}</code></a></p>
    </section>

The style sheet
---------------

The style sheet is copied as it is, without placeholders. It is meant to
be edited, and says so. It is a single column of text, set in a serif
face available on most systems, with no web fonts to load.

    /* in src/opensheaf/templates/style.css: */
    /* The default style of an OpenSheaf archive (opensheaf-py); edit freely. */
    <<the colours of the default style>>
    <<the page and its type in the default style>>
    <<the list of documents in the default style>>
    <<the versions in the default style>>
    <<notices and citations in the default style>>

The colours are custom properties, defined once for a light background
and once for a dark one, chosen by the reader's system setting.

    /* in the colours of the default style: */
    :root {
      --bg: #fdfcf9; --fg: #22252b; --muted: #5d6270; --rule: #dedad2;
      --link: #2b5c9e; --accent: #b4572a; --box: #f3f0ea;
    }
    @media (prefers-color-scheme: dark) {
      :root { --bg: #17191d; --fg: #e4e2dd; --muted: #a2a6b0; --rule: #33363d;
              --link: #8fb4e8; --accent: #e59a6b; --box: #22252b; }
    }

The column is at most 46 rem wide, with a margin of 16 pixels on narrow
screens. Secondary text (the lead, dates, metadata, pins) is in the
muted colour.

    /* in the page and its type in the default style: */
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--fg);
           font: 17px/1.55 Charter, "Bitstream Charter", "Sitka Text", Cambria, Georgia, serif; }
    header, main, footer, nav { max-width: 46rem; margin: 0 auto; padding: 0 16px; }
    header { padding-top: 2.5rem; }
    h1 { font-size: 1.7rem; line-height: 1.25; margin: 0.4em 0; }
    h2 { font-size: 1.1rem; margin: 1.8em 0 0.5em; color: var(--muted);
         text-transform: uppercase; letter-spacing: 0.06em; }
    a { color: var(--link); text-underline-offset: 2px; }
    .lead, .small, footer, .paper-meta, .version-date, .pin { color: var(--muted); }
    .small, footer { font-size: 0.85rem; }
    nav { padding-top: 1.2rem; font-size: 0.9rem; }
    footer { border-top: 1px solid var(--rule); margin-top: 3rem; padding-top: 1rem; padding-bottom: 2rem; }

The home page is a list of entries separated by rules, without numbers.

    /* in the list of documents in the default style: */
    ol.papers { list-style: none; padding: 0; }
    li.paper { padding: 1rem 0; border-bottom: 1px solid var(--rule); }
    .paper-title { font-weight: bold; font-size: 1.08rem; text-decoration: none; }
    .paper-title:hover { text-decoration: underline; }
    .paper-authors { margin: 0.15rem 0; }
    .paper-meta, .pin { font-size: 0.88rem; }
    details summary { cursor: pointer; color: var(--muted); font-size: 0.9rem; margin-top: 0.3rem; }
    details p, .abstract p { margin: 0.5em 0; }

Each version on a landing page has a rule on its left, in the accent
colour for the current version, which is also marked by a small label,
as is the stage.

    /* in the versions in the default style: */
    ol.versions { list-style: none; padding: 0; }
    li.version { border-left: 3px solid var(--rule); padding: 0.4rem 0 0.4rem 0.9rem; margin: 0.6rem 0; }
    li.version.is-current { border-left-color: var(--accent); }
    .version-head { font-weight: bold; }
    .stage, .current { font-size: 0.75rem; font-weight: normal; padding: 0.05rem 0.4rem;
                       border-radius: 3px; background: var(--box); margin-left: 0.3rem; }
    .current { color: var(--accent); }
    .changes { font-style: italic; }
    .files { font-size: 0.92rem; }
    .missing { color: var(--muted); }

Notices and withdrawals stand out in a box with the accent rule; the
citation is in a box too, to be copied. A pin is a long string of
hexadecimal digits, and may be broken anywhere.

    /* in notices and citations in the default style: */
    .notice, .withdrawn { background: var(--box); border-left: 3px solid var(--accent);
                          padding: 0.5rem 0.8rem; margin: 0.5rem 0; }
    .cite { background: var(--box); padding: 0.6rem 0.8rem; font-size: 0.92rem; }
    code { font-size: 0.8rem; word-break: break-all; }
