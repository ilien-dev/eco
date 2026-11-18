# Placements

Where a phrase sits matters more than how many times it appears. Write each place for a
person first; a phrase that does not fit a sentence naturally belongs somewhere else.

## Website

| Placement | What it is | How to write it |
|---|---|---|
| `title` | `<title>` | 30 to 60 characters. The strongest primary near the start, then the project name or a second phrase. It becomes the blue link in results. |
| `meta` | `<meta name="description">` | 70 to 160 characters. One sentence that says what it is and for whom, with one or two primaries. It is the snippet under the link, not a ranking signal by itself, so write it to be clicked. |
| `h1` | the one `<h1>` | Exactly one per page. It can be a slogan, but give it the main noun ("README banner"), not only wordplay. |
| `h2`, `h3` | section headings | Name what the section is about in the words people search. Vary them; one phrase in every heading is stuffing. |
| `alt` | image alt text | Describe the image; include the phrase only when the image really shows it. |
| `og` | Open Graph and Twitter tags | Title, description and image alt for link previews. |
| `jsonld` | structured data | `SoftwareApplication` (or the type that fits), `FAQPage` built from the visible FAQ, `inLanguage`. Never put text there that the page does not show. Since 2023 Google shows FAQ rich results only for a few authoritative sites, so the FAQ earns its place through the visible text, not the snippet. |
| `body` | visible text | The lead paragraph matters most. An FAQ section is the natural home for long-tail questions: ask them in the searcher's words and answer in two or three true sentences. |

Also, for a site:

- Each language at its own URL (`/`, `/es/`), with reciprocal `hreflang` links (`en`, `es`,
  `x-default`), `og:locale`, and a sitemap that lists every language version.
- A canonical link on every page, a 404 that is `noindex`.
- Research each language separately and translate the copy around the keywords, not the keywords.

## README

| Placement | What it is | How to write it |
|---|---|---|
| `h1` | the first `#` heading or `<h1>` | Project name plus what it is, in the searched phrase: "Jano: an animated SVG banner for your GitHub README". |
| `lead` | the first 300 characters of prose after the H1 | Says what the project does and for whom, with the primaries. GitHub and Google both show this text. |
| `heading` | `##` and below | Sections named in searched words where it is natural: "Install", "Use", plus one or two that carry a phrase. When you rename one, keep its old anchor with `<a id="old"></a>`. |
| `alt` | image alt text | The README hero and screenshots. Describe them; add the phrase when the picture shows it. |

## GitHub, outside the repo

- **Name**: the strongest signal in GitHub search, and the one the text cannot change. Never
  rename a repo as part of this skill; mention it if the name hides what the project is.
- **About** (description): up to 350 characters. GitHub's default repository search matches the
  name, the About and the topics (the README only with `in:readme`), and Google uses the name
  plus the About as the repo page's title. Put the main primary at the start. Stars weigh heavily
  in GitHub's ranking; the text cannot change that, so aim at searches small enough to win.
- **Topics**: up to 20, lowercase with hyphens. Use the topics competitors share when they are
  true of the project, plus the primaries as topics (`readme-banner`).
- **Homepage**: the project's site, when there is one.
- **Manifests**: `package.json`, `pyproject.toml`, plugin manifests and marketplace entries have
  keyword lists that package registries search. Align them with the map when they exist.

These change a public page. Propose the exact command and wait for a yes:

```
gh repo edit OWNER/NAME --description "..." --homepage https://... --add-topic a,b,c
```

## Stuffing and truth

- A phrase that takes more than 3% of the visible words, or sits in more than half the headings,
  is flagged by the audit. Readers notice it before search engines do.
- A phrase for something the project does not do (`claim: negation`) may appear only where the
  text says it is not that: "Is Jano a README generator? No, ...". That answers the search
  honestly and keeps the visitor.
- Every number, size, compatibility or feature in new text must be checked against the code or
  docs before it is written.
