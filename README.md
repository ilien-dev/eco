# Eco: keyword research and on-page SEO for your README and website

Eco is a pair of agent skills for Claude Code, Codex and other AI agents: `eco-readme` for a
GitHub README and `eco-site` for a website. Each finds the words people type when they look for
what your project does, puts those words where Google and GitHub search read them, and checks
the result with a script instead of taking the agent's word for it.

It works on the one thing you control: your own text. Backlinks, domain age and mentions on
other sites are out of its reach, and it says so.

## What it does

1. **Reads the project** (repo, docs, site) and writes down who it is for and how those people
   search. When a project is so niche that nobody searches for it by name, it looks for the
   nearest problems and alternatives people do search.
2. **Researches keywords per language**: autocomplete from Google, Bing and DuckDuckGo, GitHub repository search
   (with where your repo ranks today) and the pages and READMEs of competitors, with the subtopics
   they share and you never mention. For a site with Search Console, an export of your own
   queries: the searches Google already shows you for at positions 5 to 20 come first.
3. **Builds a keyword map**: primary, secondary, long-tail and discarded phrases, each with the
   research that backs it and the places it has to appear (title, meta description, H1, lead,
   headings, alt text, FAQ, GitHub About and topics). On a site with several pages, each phrase
   belongs to one page, so two of your pages never compete for the same search.
4. **Rewrites the text** so those words sit where they count, without stuffing and without
   claims the project cannot back.
5. **On a website, checks what surrounds the pages**: robots.txt (and whether AI search bots such
   as OAI-SearchBot, Claude-SearchBot and PerplexityBot can reach the site), the sitemap, llms.txt,
   and Lighthouse. With [Unlighthouse](https://unlighthouse.dev) it scans production when the
   site is live (or the build, served as static files, when the changes are not deployed yet) and
   works every page toward 100 in performance, accessibility, best practices and SEO. Fixes you
   would not notice it makes on its own; anything that changes how the site looks or behaves,
   such as removing an animation or changing a color, it asks you first.
6. **Asks whether to run [Quirón](https://github.com/ilien-dev/quiron)**, a humanizer, on the new
   text, when you have it installed. Eco never installs it; if you do not have it, the closing
   message tells you what it does so you can try it on your own.
7. **Checks that nothing broke**: every keyword placement, internal link and anchor survives the
   humanizing pass. When the two disagree, the keywords win.
8. **Reports** in the same format every time: a fixed summary in English, and a page you open in
   your browser, in the language you talk to your agent in, with what was found, what changed
   (before and after) and what is left for you.

## Measured, not described

`scripts/eco.py` (Python 3.9+, standard library only) writes every step to `.eco/` and refuses
to produce the report until each check passes:

- the research is deep enough: non-empty autocomplete responses from several seed families per
  language, competitors, GitHub searches;
- every phrase's evidence is really in the research files;
- every primary has a saved results page: two primaries that share most of their top 10 results
  are one search, and a README primary needs a repository or GitHub topic page in its top 10
  (or a recorded reason to keep it);
- primary keywords sit in their required places, with no stuffing flags;
- on a site with several pages, every phrase names its page and no primary sits on two;
- every changed page of a site has a link from another page of the build, a canonical that names
  itself and no meta refresh;
- on a site, robots.txt lets search and AI search bots in and names the sitemap, the sitemap
  lists every changed page, an llms.txt (when there is one) has the shape llmstxt.org asks for,
  and every Lighthouse audit that weighs on a score passes on the final pages, or is recorded as
  a technical ceiling or a change you declined, with the reason;
- a built page can be indexed and read: no `noindex`, JSON-LD that parses, `<html lang>` and
  `hreflang` both ways, `og:image`, alt attributes, no duplicate or templated meta tags;
- every number, year or superlative the new text adds has a recorded source;
- the baseline is the original text, kept before any edit;
- the keyword map did not change between the snapshot before the humanizing pass and the final one;
- nothing was lost after the humanizing pass, and the report re-audits the files it describes.

The report then says what is proven, and nothing more: how many researched phrases the text
carries now against before, whether it does with each main phrase what the pages that rank
already do, and the search position. That last one can only move once the changes are public, so
it reads "not checked" until you publish and run the last step. `eco.py track` then repeats the
searches saved during the research, refuses while the public copy still shows the old text, and
gives each search a result: improved, no change, worse, or too early to tell. For a site,
`eco.py gsc` compares Search Console exports from before and after, position and click rate, and
`eco.py field` compares what real Chrome users measured (LCP, INP, CLS) when you have a free
Chrome UX Report key. For a README, `eco.py traffic` compares GitHub's own count of visitors who
arrived from a search engine, 14 days before against 14 days after.

## Install

In Claude Code, as a plugin:

```
/plugin marketplace add ilien-dev/eco
/plugin install eco@eco
```

Or as standalone skills, for Claude Code and other agents:

```sh
npx skills add ilien-dev/eco
```

`eco-site` also needs Node.js 18 or newer for the Lighthouse step. Unlighthouse runs through
`npx`, so there is nothing else to install; the first run downloads a Chrome to
`~/.unlighthouse` if you have none.

## Use

Eco does not start by itself. A keyword run takes a while and changes your text, so both skills
only run when you call them, in the project you want to work on:

| You want | Plugin install | `npx skills` install |
|---|---|---|
| A README that people find on Google and GitHub | `/eco:eco-readme` | `/eco-readme` |
| A website that people find on Google and AI search | `/eco:eco-site` | `/eco-site` |

Add what the project should be found for, if you know:

```
/eco:eco-readme make this README show up when people search for a readme banner
```

Asking "improve my SEO" in plain words will not trigger Eco: type the command. (Claude Code
honours this; other agents may load skills on their own rules.) Each skill keeps its run in its
own folder, `.eco/readme/` or `.eco/site/`, so a project can have both.

Eco never commits, pushes or edits your GitHub About on its own. Changes outside the repo are
proposed as an exact `gh repo edit` command.

## Why Eco

In Greek myth, Echo was a nymph who could only repeat the last words others said. That is the
whole job here: listen to the words people use when they search, and make your project say them
back. Like the other projects by the same author, it takes its name from mythology.

## Limits

- Google Suggest shows that people type a phrase, not how many do. With Search Console or Trends
  data, record it as evidence and Eco uses it.
- GitHub's default repository search reads the name, About and topics, not the README, and
  weighs stars heavily. Eco proposes the About and topics; the name and stars are yours.
- A position that moved is measured; that Eco's edits moved it is not proven, because other
  pages and repositories change in the same weeks. Search-engine positions come from DuckDuckGo
  or Bing results pages; Google's only come from your own Search Console exports.
- Lighthouse runs in a lab, on your machine, even when it scans production: its LCP, CLS and TBT
  are estimates that move a few points between runs, and TBT stands in for INP, which only field
  data has. A score of 100 is the target, not a promise: some sites hit a ceiling (a third-party
  script they need, a host without header settings), and the report says which and why.
- Field data needs a Google API key of yours (`CRUX_API_KEY`) and a site with enough Chrome
  visits; a small site has none, and the report says so. GitHub traffic needs push access to the
  repository and covers 14 days, so the "before" has to be saved during the run.
- A subtopic is counted by its words: the report says how many of the subtopics the ranking
  pages share appear in your text, not how well your text answers them.
- Version 0.2.0: the README skill was tested on four projects by one person in Claude Code. The
  site checks, the Lighthouse step and everything added in 0.2.0 (a page per phrase, Search
  Console in the research, click rate, GitHub traffic, field data, links between pages, shared
  subtopics) are covered by the test suite and have not been through a full run on a real
  project yet. A project with no repo and other agents have not been tried either.

## License

MIT, see [LICENSE](LICENSE).
