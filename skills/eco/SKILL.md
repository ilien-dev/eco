---
name: eco
description: "Keyword research and on-page SEO for a README or a website: finds what people actually type when they have the problem a project solves (Google Suggest, GitHub search, competitor pages), builds a keyword map, rewrites titles, headings, descriptions and FAQ so those words are where search engines and GitHub look, and proves it with scripts. Use it whenever someone wants a repo or site to be found: SEO, keywords, ranking on Google or in GitHub search, a README or landing page that nobody finds, GitHub About and topics, meta titles and descriptions, or a Spanish/other-language version that should rank too, even if they never say 'SEO'."
---

# Eco

Echo, in the myth, could only repeat the words of others. That is the job: find the words
people use when they look for what this project does, and make the project say them back.

Eco works on what the project controls: its own text. Links from other sites, domain age and
backlinks are out of scope; say so if the user asks about them.

Every step leaves a file in `.eco/` and `scripts/eco.py report` refuses to run until the checks
behind every step pass. That is deliberate: the report is the proof the work was done, not a
description of it. Run `eco.py status` at any time to see the next step.

`eco.py` is in `scripts/` next to this file. Call it with the project as `--root`:

```
python3 <skill-dir>/scripts/eco.py --root <project> <command>
```

(On Windows, `python` instead of `python3`.)

Speak to the user in their language. Keywords are researched per language of the text, not
per language of the conversation.

## 1. Understand the project and who it is for

Read before asking: the README and docs, the code, `package.json`/`pyproject.toml`/plugin
manifests, the site's pages. For a site with a repo, read the repo; with no repo, read the
live pages; ask the user only for what neither says.

```
eco.py init --lang en[,es] --surface README.md:en --surface README.es.md:es --repo OWNER/NAME
```

Then fill in `.eco/brief.json` in the user's language, and later the evidence details and
discard reasons in `keywords.json` too: the report quotes them.

- `project`: name, what it does in one sentence, the problem it solves.
- `read`: the files and pages you actually read to understand it.
- `audience.primary`: who has that problem.
- `audience.how_they_search`: in words, what those people type when the problem hits them.
  They search for the problem or the result, rarely for the tool. Nobody searches "agent skill
  that draws SVG"; they search "github readme banner".
- `audience.niche` and `audience.adjacent`: when the project is so specific that almost nobody
  searches for it directly (a skill for one narrow job, a new category), set `niche: true` and
  list the nearest problems and alternatives people do search: the manual way of doing it, the
  tools it replaces, the broader category. Those searches are where the audience is.
- `surfaces`: the files whose text will change. **For a website, the built HTML** (`dist/`,
  `out/`, `_site/`, or a saved copy of the live page), because that is what search engines read;
  edit the sources, rebuild, audit the build. For a repository, the README files.
- `github.about_file`: when the repo is on GitHub, save
  `gh repo view OWNER/NAME --json description,repositoryTopics,homepageUrl` to `.eco/github-about.json`
  and point here. GitHub's repository search looks at the name, the About and the topics by
  default (the README only with `in:readme`), and Google builds the title of the repo page from
  the name and the About. So for GitHub search the About and topics matter more than the README;
  for Google the README matters as much.
- `site_url`: for a website, the address where it answers today. Open it once: a canonical or
  `og:url` pointing at another host (an old domain, a placeholder) is one of the most damaging
  SEO bugs and the audit checks for it. Compare the live page's head with the build too; when
  production is ahead of the checkout, tell the user before they deploy over it.
- When a rule pairs translations ("a change to README.md goes with the same change in
  README.es.md"), read it as the same places and structure in both files, each with the phrases
  researched in its own language. If the rule files are not in this checkout, read them from the
  default branch.
- `rules`: the project's own rules about these files (paired translations, files never edited
  by hand, contribution rules, manifests such as `package.json` or `plugin.json` whose keywords
  should follow the map). Read CLAUDE.md, AGENTS.md and CONTRIBUTING.md for them. If `init`
  warned that the checkout is not on the default branch, add that too.

`eco.py brief` checks it and keeps a copy of every surface in `.eco/original/`: that copy is the
baseline every later comparison uses, so run `brief` before you change any text.

## 2. Research, as deep as the gate demands and then some

Read [references/research.md](references/research.md) before starting; it has the seed
recipe, how to find competitors and how to read what comes back.

Do each language separately: Spanish speakers type English words ("banner", "readme"), and
that only shows up when you search in Spanish.

1. **Autocomplete (Google Suggest, Bing, DuckDuckGo).** Plan seeds by family (problem, result,
   category, alternative, platform, and `adjacent` for each adjacent audience of a niche project):
   `eco.py suggest urls --lang en --family problem --engine google --seed "..." --seed "..."`
   prints the URLs. Fetch them with your web tool and save the raw responses under
   `.eco/raw/suggest/<lang>/<engine>/` (one file per response or a tool's combined output both
   parse), then `eco.py suggest parse`. Use `--depth 2` on the two or three strongest seeds to get
   the a-z expansion. Responses to queries that were never planned, or that share no word with
   their query, are ignored. If the harness has no web tool, `eco.py suggest fetch` fetches slowly
   by itself. Saved files can have any extension; the content is sniffed. `eco.py suggest terms
   --grep word` lists what came back. These services rate-limit: fetch in small batches, never refetch a query that has a
   response, and when Google makes you wait, plan the next batch with `--engine bing` or
   `--engine ddg` instead of waiting. Google remains the reference for Google ranking; use it for
   the strongest seeds.
2. **GitHub search** (when a README is a surface): `eco.py github urls --query "..."`, fetch (or
   `gh api "search/repositories?q=...&per_page=30" > .eco/raw/github/<name>.json`),
   then `eco.py github parse`. It gives the size of each search and the topics competitors use.
3. **Competitors.** Find the pages and repos that rank for the main searches today, save their
   HTML or README under `.eco/raw/competitors/`, then `eco.py competitors`. It lists their titles,
   descriptions and headings and the phrases two or more of them share.

`eco.py research` checks the depth: for the main language (the first in the brief) 20 non-empty
responses (one seed counts for 8 at most), 5 fetched seeds and 4 of the 5 families; for each other
language 10, 3 and 3; one seed per adjacent audience; 3
competitors; 2 GitHub searches for a README, which also record where the project ranks today.
These are floors. Stop when new queries stop
bringing new phrases, not when the gate turns green.

Suggest shows that people type a phrase, not how many. A phrase with no suggestions at all, in
any variant, goes to `discarded`.

## 3. The keyword map

Write `.eco/keywords.json`:

```json
{"keywords": [
  {"phrase": "github readme banner", "lang": "en", "tier": "primary",
   "evidence": [{"source": "suggest", "detail": "8 variants: generator, size, maker"}],
   "placements": ["title", "h1", "alt"], "claim": "true"},
  {"phrase": "readme generator", "lang": "en", "tier": "secondary",
   "evidence": [{"source": "suggest", "detail": "github readme generator ai/free/online"}],
   "placements": ["h3"], "claim": "negation"},
  {"phrase": "readme hero", "lang": "en", "tier": "discarded", "reason": "no suggestions"}
]}
```

- `tier`: `primary` (the 1 to 5 searches the project should win; each needs one of `title`, `h1`,
  `lead` or `about` and at least two placements), `secondary`, `long-tail` (questions and specific
  phrasings, good for an FAQ), `discarded` (with a `reason`). Keep at least 10 phrases and discard
  at least 3. On a site, `lead` is the first paragraph: a primary can live there when the H1 is a
  slogan the project wants to keep. One primary is a fine result for a small page.
- `evidence`: where the phrase came from. `suggest`, `github` and `competitor` are checked: the
  phrase must be in what the service suggested (not in the query you typed), in a GitHub
  description or topic, or in a competitor's title, description, lead or headings.
  `search-console` and `trends` are taken on trust. A primary needs demand evidence (`suggest`,
  `search-console` or `trends`): GitHub and competitors show how others word it, not that people
  search it.
- `placements`: where the phrase must appear. Site: `title meta h1 h2 h3 alt og jsonld body`.
  README: `h1 lead heading alt body` (`lead` is the first 300 characters of prose after the H1).
  GitHub: `about topics`. [references/placements.md](references/placements.md) says what each one
  weighs and how to write it.
- `claim`: `true` when the project does what the phrase says. `negation` when people search it
  but the project is not that thing: the phrase may only appear in an honest "is it X? No, ..."
  answer. Never place a phrase that promises something the project does not do.
- `variants`: optional forms that count as the same phrase: the same words in another order,
  plural or punctuation (`CLAUDE.md` and `claude md` already match), or a form that is itself in
  the Suggest data. Anything else is a different phrase and gets its own entry.

`eco.py map` checks it, and refuses while the research gate fails. Show the user the primaries
and the discarded ones before editing (unless the request said not to ask).

## 4. Put the words in place

`eco.py audit --save baseline` records where the originals stand (it reads `.eco/original/`).

Then rewrite. Restructure when the structure is in the way: a title that names the tool and
nothing else, a first paragraph that never says what the project is for, headings that say
nothing searchable. Everything in [references/placements.md](references/placements.md)
applies; the short version:

- Primaries must land where the map says. Secondaries and long-tail phrases are opportunities:
  place one where a sentence wants it, and leave it out where it would need a sentence of its own.
  The report shows how many landed; a lower number with natural text is the better result.
- One phrase per place, in natural sentences. The audit flags a phrase that takes more than 3%
  of the words, sits in more than half the headings, or a run of "<Name> is a <keyword>"
  sentences, because readers and search engines both read that as stuffing. A keyword list at the
  bottom of a README is not counted as text.
- Build sections around real searches when the project has an answer: a problem people type
  ("WebFetch 403"), a comparison ("X vs Y"), a "why not just ..." question. That beats squeezing
  the phrase into an existing sentence.
- A shared layout or template changes every page built from it. When only some pages are in
  scope, add what they need through a slot or a prop and compare the rest of the build before
  and after.
- Keep each file's line endings when editing (on Windows, tools in Git Bash can turn CRLF into LF).
- Renaming a heading breaks links to its anchor. Keep the old one with `<a id="old-anchor"></a>`
  above the new heading; `compare` fails when an internal link loses its target.
- Every claim in new text must be true of the project. Check it against the code or docs, as
  you would a fact in an article.
- Follow `rules` from the brief: a change to one language goes to its pair, built files are
  rebuilt rather than edited.
- A website gets what a README cannot: a title and meta description in range, one H1, alt text,
  an FAQ that answers the long-tail questions, JSON-LD, Open Graph with an image, `hreflang`
  between language versions, a sitemap. A README gets the H1, the lead, headings and alt text.
- The GitHub About, topics and homepage live outside the repo. Write the exact
  `gh repo edit` command and run it only after the user says yes in this conversation; record it
  with `eco.py offsite --about "..." --topics a,b --homepage URL [--applied]` (the full topic
  list after the change). Once recorded, the audit checks `about` and `topics` placements against
  this proposal and reports them apart: a proposal nobody applies does not ship, so every primary
  still has to be in a title, H1 or lead of the files, or in an About that is live.

Rebuild a site, then `eco.py audit` until no primary is missing and there are no flags. A saved
snapshot does not update itself: after a fix, save it again. Then
`eco.py audit --save pre-quiron`.

## 5. Quirón (optional humanizing pass)

Quirón is a separate skill that makes text read as a person wrote it and measures the result.
Keyword-heavy copy often reads stiff, so it helps, but the user decides.

1. `eco.py quiron detect`. Also check the skills listed in this session for `quiron`.
2. Ask the user with the harness's question tool (AskUserQuestion in Claude Code), in one
   question that explains it in a line. If the prompt already answered (for example "skip the
   humanizer" or "use Quirón"), take that answer and do not ask.
   - Installed: "Quirón can rewrite the new text so it reads less like AI and measure it.
     Run it now?" Options: run it / skip.
   - Not installed: "Quirón is a skill that makes text read less like AI and measures the result.
     Install it?" Options: install / skip.
3. To install: in Claude Code run `claude plugin marketplace add ilien-dev/quiron` and
   `claude plugin install quiron@quiron`; if the CLI refuses, give the user those two lines to run
   with `!`. In any other harness: `npx skills add ilien-dev/quiron`. A skill installed during a
   session may not load until the session restarts: then record `pending-reload`, tell the user,
   and go on to step 6 without it. After a successful install, ask whether to run it.
4. To run it: copy the changed prose (not markup) into a text file, invoke Quirón on it, and pass
   it the primary and secondary phrases as fixed words it must keep; the FAQ questions are fixed
   too, since they are worded like the searches. Follow its own workflow; when the user cannot be
   asked, skip its questions to the writer and say so. Put the result back into the sources.
5. Record the outcome: `eco.py quiron record --status used|skipped|declined|not-installed|pending-reload --result "<Quirón's one-line result>"`.
   `used` is refused when the files did not change since `pre-quiron`. Once recorded, the
   pre-quiron snapshot cannot be retaken; to redo the pass, `eco.py quiron reset` first.

## 6. Check that nothing broke

`eco.py audit --save final`, then `eco.py compare pre-quiron final`.

If a placement was lost, the keyword wins: put it back with the smallest edit that keeps the
rest of Quirón's wording, then audit again. Do not run a second Quirón rewrite (its own rule is
one pass); its `check.sh` may be run once more to measure the edited text. Also reread the
changed text once for anything the humanizing broke: a fact, a link, a command, markup.

## 7. Report

`eco.py report --lang <user's language>` re-audits the files, prints the summary and saves
`.eco/report.md`. Your final message to the user starts with that report, verbatim; it has the
same sections every time, so the user can compare runs. Anything the script cannot know goes in
through `eco.py pending "..."` before running it, not as prose after it. After the report, add at
most three short lines, only for a decision the user has to make.

Never commit or publish as part of this skill.
