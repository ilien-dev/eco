---
name: eco-site
description: "Keyword research and on-page SEO for a website: finds what people type when they have the problem the site solves (Google Suggest, competitor pages, search results), builds a keyword map, rewrites titles, meta descriptions, headings, FAQ and structured data, checks robots.txt, AI crawlers, the sitemap and llms.txt, takes every page toward 100 in all four Lighthouse categories with Unlighthouse, and proves every step with a script. Run it by hand with /eco:eco-site (plugin) or /eco-site."
disable-model-invocation: true
argument-hint: "[what the site should be found for]"
---

# Eco for a website

Echo, in the myth, could only repeat the words of others. That is the job: find the words
people use when they look for what this site offers, and make the pages say them back.

Eco works on what the project controls: its pages, their head tags, robots.txt, the sitemap
and llms.txt. Backlinks, domain age and mentions on other sites are out of scope; say so if
the user asks about them. For a README, the user runs `eco-readme` instead.

Lighthouse is part of the job, not a side report: the target is 100 in performance,
accessibility, best practices and SEO on every page in scope. Work toward it until each audit
passes or hits a real technical ceiling. Changes nobody can see or feel are yours to make;
anything that changes how the site looks or behaves is the user's call (step 7).

Every step leaves a file in `.eco/site/` and `eco.py report` refuses to run until the checks
behind every step pass, a Lighthouse run of the final pages included. The report is the proof
the work was done, not a description of it. `eco.py status` shows the next step at any time.

`eco.py` is in `scripts/` next to this file. Every call takes the project and the mode:

```
python3 <skill-dir>/scripts/eco.py --root <project> --mode site <command>
```

(On Windows, `python` instead of `python3`.) Below, `eco.py` stands for that whole prefix.

Speak to the user in their language. Keywords are researched per language of the text, not
per language of the conversation.

## 0. Requirements

Lighthouse is part of every run. Check `node --version` first (Node 18 or newer). Without Node,
stop and tell the user Eco needs it for the Lighthouse step, with the install link
(nodejs.org); do not install it yourself. Unlighthouse itself runs through `npx` and needs no
install; on its first run it downloads a Chrome to `~/.unlighthouse` when there is no system
Chrome. Tell the user that once, before the first run.

### Where Lighthouse scans

1. **Production first.** When `site_url` answers and serves this project, scan it: real hosting,
   CDN, compression, caching headers and HTTPS give numbers a local copy cannot.
2. **Otherwise, the local build**, served as static files the way a host would serve them, never
   a dev server (`npm run dev`, `astro dev`, `vite`) and never the framework's preview of the
   sources: `npx --yes serve@14 <build_dir> -l 4321`. It serves the built files with compression
   and clean URLs and runs none of the site's code. Only a site that needs a server to render
   (SSR) runs its own production start command on the build (`next start`, `node dist/server/entry.mjs`).
3. **Changes not deployed yet** follow rule 2: the final scan of edited pages is on the local
   build. `eco.py lighthouse --stage final` refuses production while it serves different text
   from the build, so a scan never credits the old site with the new pages.

From the project root, with the server running in the background (stop it afterwards):

```
npx --yes -p @unlighthouse/cli unlighthouse-ci --site <url> --reporter jsonExpanded --no-cache --throttle --urls /,/es/
```

- `--urls` lists the surfaces' paths: fast, and every result is in scope. When the user asks
  for the whole site, drop it.
- `--throttle` simulates a mid-range phone on a slow network, as PageSpeed Insights does; that
  is the score people compare against.
- `--no-cache` keeps an earlier build's results out of the scan.
- In Git Bash on Windows, prefix the command with `MSYS_NO_PATHCONV=1`, or Git Bash turns `/`
  into a Windows path and the home page is not scanned.
- It writes `.unlighthouse/` in the project root; ask before adding it to `.gitignore`.
- Lighthouse scores move a few points between runs. Before calling a number final, scan twice.

## 1. Understand the site and who it is for

What the user typed after the command, if anything, is what they want the site found for:
$ARGUMENTS. Treat it as a starting point for `audience.how_they_search`, not as a keyword.

Read before asking: the source of the site, its build config, the docs, the live pages. Ask the
user only for what none of them says.

```
eco.py init --lang en[,es] --surface dist/index.html:en --surface dist/es/index.html:es
```

Then fill in `.eco/site/brief.json` in the user's language, and later the evidence details and
discard reasons in `keywords.json` too: the report quotes them.

- `project`: name, what it does in one sentence, the problem it solves.
- `read`: the files and pages you actually read to understand it.
- `audience.primary`: who has that problem.
- `audience.how_they_search`: in words, what those people type when the problem hits them.
  They search for the problem or the result, rarely for the product name.
- `audience.niche` and `audience.adjacent`: when almost nobody searches for it directly, set
  `niche: true` and list the nearest problems and alternatives people do search.
- `surfaces`: **the built HTML** (`dist/`, `out/`, `_site/`), because that is what search
  engines read; edit the sources, rebuild, audit the build. With no build step, a saved copy of
  the live page.
- `build_dir`: the folder the build writes. robots.txt, the sitemap and llms.txt are checked
  there, and every surface must be inside it.
- `site_url`: the address where the site answers today. Open it once: a canonical or `og:url`
  pointing at another host (an old domain, a placeholder) is one of the most damaging SEO bugs
  and the audit checks for it. Compare the live page's head with the build too; when production
  is ahead of the checkout, tell the user before they deploy over it.
- `ai_crawlers_blocked`: bots the owner blocks on purpose (see step 4). Empty by default.
- `rules`: the project's own rules (paired translations, generated files never edited by hand,
  contribution rules). Read CLAUDE.md, AGENTS.md and CONTRIBUTING.md for them. If `init` warned
  that the checkout is not on the default branch, add that too.

`eco.py brief` checks it and keeps a copy of every surface in `.eco/site/original/`: that copy is
the baseline every later comparison uses, so run `brief` before you change anything.

Then the Lighthouse baseline, before any edit: scan as "Where Lighthouse scans" says and run
`eco.py lighthouse --stage baseline --url <url>`. A local baseline is refused once a page has
changed. It lists every audit under 1 per page (`OPEN`) and the diagnostics behind them
(`hint`): that is the work list for step 7, and the "before" column of the report.

Lighthouse measures in a lab. What real visitors measured comes from the Chrome UX Report, and it
has the one number Lighthouse lacks, INP. When `CRUX_API_KEY` is set in the environment, run
`eco.py field --stage baseline`: it asks for each page on phones and falls back to the whole site
when a page has too few visits. The key is a free Google API key the user creates; never create
one or ask for it to be pasted into the chat. Without it, skip this: the report then says the
speed numbers are lab estimates. A metric outside the "good" range goes to Pending by itself.

## 2. Research, as deep as the gate demands and then some

Read [references/research.md](references/research.md) before starting; it has the seed
recipe, how to find competitors and how to read what comes back.

Do each language separately: people type English words in other languages, and that only
shows up when you search in that language.

1. **Autocomplete (Google Suggest, Bing, DuckDuckGo).** Plan seeds by family (problem, result,
   category, alternative, platform, and `adjacent` for each adjacent audience of a niche site):
   `eco.py suggest urls --lang en --family problem --engine google --seed "..." --seed "..."`
   prints the URLs. Fetch them with your web tool and save the raw responses under
   `.eco/site/raw/suggest/<lang>/<engine>/`, then `eco.py suggest parse`. Use `--depth 2` on the
   two or three strongest seeds for the a-z expansion. With no web tool, `eco.py suggest fetch`
   fetches slowly by itself. `eco.py suggest terms --grep word` lists what came back. These
   services rate-limit: fetch in small batches, never refetch a query that has a response, and
   when Google makes you wait, plan the next batch with `--engine bing` or `--engine ddg`.
2. **Competitors.** Find the pages that rank for the main searches today, save their HTML under
   `.eco/site/raw/competitors/`, then `eco.py competitors`. It lists their titles, descriptions
   and headings and the phrases two or more of them share. It also lists the subtopics they
   share (a heading in one page that at least two of them write about) and which ones your pages
   never mention: candidates for a section or an FAQ answer in step 4, only where the site has a
   true answer. The report counts them covered before and after; none is required.
3. **Search Console, when the site has it.** It is the only source here with real numbers from
   Google. Ask the user once for a CSV export of the Performance report, Queries tab, last 28
   days, without "Compare" (a site with no Search Console, or a user who says no: skip it). Then
   `eco.py gsc <file> --stage research --period START..END`. It lists the searches Google
   already shows the site for at an average position of 5 to 20: demand that exists and that few
   people reach, so weigh them first as primaries, with `search-console` as evidence. It also
   names the queries already in the top 4: leave their words where they are. Keep the file; it is
   the "before" of step 9.

`eco.py research` checks the depth: for the main language 20 non-empty responses (one seed counts
for 8 at most), 5 fetched seeds and 4 of the 5 families; for each other language 10, 3 and 3; one
seed per adjacent audience; 3 competitors. These are floors. Stop when new queries stop bringing
new phrases, not when the gate turns green.

Suggest shows that people type a phrase, not how many. A phrase with no suggestions at all, in
any variant, goes to `discarded`.

## 3. The keyword map

Write `.eco/site/keywords.json`:

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

- `tier`: `primary` (the 1 to 5 searches the site should win; each needs `title`, `h1` or
  `lead` and at least two placements), `secondary`, `long-tail` (questions and specific
  phrasings, good for an FAQ), `discarded` (with a `reason`). Keep at least 10 phrases and
  discard at least 3. `lead` is the first paragraph: a primary can live there when the H1 is a
  slogan the owner wants to keep. One primary is a fine result for a small page.
- `evidence`: `suggest` and `competitor` are checked against the research files, and
  `search-console` against the export once `gsc --stage research` read one; without an export it
  is taken on trust, as `trends` is. A primary needs demand evidence (`suggest`, `search-console`
  or `trends`).
- `surfaces`: the page a phrase belongs to, as its path in the brief (`["dist/pricing/index.html"]`).
  Required as soon as the run has two or more pages in one language, and a primary names exactly
  one: two pages aimed at the same search compete for it and both rank lower. Give each page its
  own primaries, chosen by what the page is about. With one page per language, leave it out.
- `placements`: `title meta h1 h2 h3 alt og jsonld body`.
  [references/placements.md](references/placements.md) says what each one weighs and how to
  write it.
- `claim`: `true` when the site does what the phrase says; `negation` when people search it but
  the product is not that thing, so the phrase may only appear in an honest "is it X? No, ..."
  answer. Never place a phrase that promises something the product does not do.
- `variants`: optional forms that count as the same phrase (word order, plural, punctuation, or
  a form that is itself in the Suggest data).

Before checking it, look at what wins each primary today: `eco.py serp urls` lists one results
page per primary (DuckDuckGo by default, `--engine bing`); fetch each, save it as
`.eco/site/raw/serp/<slug>.<ext>`, run `eco.py serp parse`, and open the files once to make
sure they are results for that query and not a block.

`eco.py map` checks it, and refuses while the research gate fails, while a primary has no saved
results, and when two primaries share 7 or more of the top 10 results (one search: keep one).
Show the user the primaries and the discarded ones before editing (unless the request said not
to ask).

## 4. Put the words in place, and the files around them

`eco.py audit --save baseline` records where the originals stand.

Then edit the sources and rebuild. Restructure when the structure is in the way: a title that
names the product and nothing else, a first paragraph that never says what it is for, headings
that say nothing searchable. Everything in [references/placements.md](references/placements.md)
applies; the short version:

- Primaries must land where the map says. Secondaries and long-tail phrases are opportunities:
  place one where a sentence wants it, and leave it out where it would need a sentence of its own.
- One phrase per place, in natural sentences. The audit flags a phrase that takes more than 3%
  of the words, sits in more than half the headings, or a run of "<Name> is a <keyword>"
  sentences.
- Build sections around real searches when the site has an answer: a problem people type, a
  comparison ("X vs Y"), a "why not just ..." question. An FAQ answers the long-tail questions.
- A shared layout or template changes every page built from it. When only some pages are in
  scope, add what they need through a slot or a prop and compare the rest of the build before
  and after.
- Every claim in new text must be true. The audit lists every number, percentage, multiplier,
  year and superlative the new text adds; `eco.py claims verify --claim "3x" --source docs/bench.md`
  records where each comes from, and the report refuses while one is unchecked.
- Follow `rules` from the brief: a change to one language goes to its pair, generated files are
  rebuilt rather than edited.
- Every page: a title and meta description in range, one H1, alt text, JSON-LD that parses,
  Open Graph with an image, `<html lang>`, `hreflang` between language versions, a canonical on
  the site's own host. The audit also flags a `noindex`, duplicate head tags, and a meta
  description that repeats the title or ends in a stock call to action.
- Around the pages, in `build_dir`:
  - **robots.txt** that allows crawling and names the sitemap with its full URL.
  - **AI crawlers.** Search and answer bots (`OAI-SearchBot`, `ChatGPT-User`, `Claude-SearchBot`,
    `Claude-User`, `PerplexityBot`, `Perplexity-User`, plus `Googlebot` and `Bingbot`) decide
    whether the site can be shown or quoted in AI answers: a block is flagged. Training bots
    (`GPTBot`, `ClaudeBot`, `Google-Extended`, `CCBot`, `Applebot-Extended`) only decide whether
    the content trains models; blocking them is the owner's choice and only noted. When the owner
    blocks a search bot on purpose, ask, then list it in `ai_crawlers_blocked`.
  - **Sitemap** that lists every surface, each language version included (a sitemap index is
    followed).
  - **llms.txt** (llmstxt.org): an H1 with the name, a one-line summary, and links to the pages
    that matter. AI assistants and agents read it; Google Search does not. A missing one goes to
    Pending; offer to write it, and when it exists the audit checks its shape.
  Generated files (a sitemap plugin, a robots route) are fixed in their config, then rebuilt.
- Between the pages of the build, read as a crawler reads them: every page in scope needs a link
  from another page (flagged when none has one; the home page is exempt, and `hreflang` links
  count), its canonical names itself, and it carries no meta refresh. A link to an address the
  build lacks is noted for Pending: a redirect or a server route explains it, otherwise fix it.

Rebuild, then `eco.py audit` until no primary is missing and there are no flags. A saved
snapshot does not update itself: after a fix, save it again. Then `eco.py audit --save pre-quiron`.

## 5. Quirón, only when it is installed

Quirón is a separate skill that rewrites text so it reads as a person wrote it and measures the
result. Keyword-heavy copy often reads stiff, so it helps; it is never required.

1. `eco.py quiron detect`. Also check the skills listed in this session for `quiron`.
2. **Installed:** always ask, with the harness's question tool (AskUserQuestion in Claude Code),
   in one question: "Quirón can rewrite the new text so it reads more like a person wrote it,
   keeping the keywords in place. Run it now?" Options: run it / skip. Only when the request
   already answered it ("use Quirón", "skip the humanizer") take that answer without asking.
3. **Not installed:** do not ask and do not install it. Record `not-installed` and go on; the
   recommendation comes after the report (step 8).
4. To run it: copy the changed prose (not markup) into a text file, invoke Quirón on it, and pass
   it the primary and secondary phrases as fixed words it must keep; the FAQ questions are fixed
   too, since they are worded like the searches. Put the result back into the sources and rebuild.
5. `eco.py quiron record --status used|skipped|not-installed --result "<Quirón's one-line result>"`.
   `used` is refused when the pages did not change since `pre-quiron`. Once recorded, the
   pre-quiron snapshot cannot be retaken; to redo the pass, `eco.py quiron reset` first.

## 6. Check that nothing broke

`eco.py audit --save final`, then `eco.py compare pre-quiron final`.

If a placement was lost, the keyword wins: put it back with the smallest edit that keeps the
rest of Quirón's wording, rebuild, then audit again. Do not run a second Quirón rewrite. Also
reread the changed text once for anything the humanizing broke: a fact, a link, markup.

## 7. Lighthouse to 100

Scan the edited pages as "Where Lighthouse scans" says (the local build, unless production
already serves them), then `eco.py lighthouse --stage final --url <url>`. It prints each page's
four scores, every weighted audit under 1 as `OPEN`, and the weight-0 diagnostics as `hint`;
it fails while an open audit is neither fixed nor waived, or a surface was not scanned.

Work the list: fix in the sources, rebuild, `eco.py audit --save final`, scan again. Two kinds of
change:

- **Make them without asking** when nobody can see or feel them: image compression and modern
  formats, `width`/`height` on images, lazy-loading below the fold, preloading the LCP image,
  `font-display`, minifying, removing code nothing uses, deferring scripts that do not draw the
  first screen, compression and cache headers in the host config, labels, `alt`, ARIA names,
  landmarks, `lang`, heading order without restyling, meta and head tags.
- **Ask first** (AskUserQuestion), naming the audit, the category, the expected gain, and what
  the user would notice, when the fix changes how the site looks or behaves: removing or
  slowing an animation, changing colors for contrast, changing fonts, layout or sizes, removing
  or replacing a widget, embed, chat, analytics or other third-party script, changing what is
  interactive. Bundle related questions; one question per change, not per audit. When the user
  says no, record it:
  `eco.py lighthouse waive --audit color-contrast --kind declined --reason "keeps the brand grey on the hero"`.

When an audit cannot reach 1 for a reason the project cannot change (a third-party script the
site needs, a host that allows no header config, lab variance on a metric already in the
"good" range after the fixes above), record it with `--kind ceiling` and a reason the report
quotes; add `--path /es/` when it holds on one page only. A ceiling is a finding, not a shortcut:
try the fixes first. On a local scan, `is-on-https` and `redirects-http` are left to production.

The run is tied to the pages it measured: when they change after it, the report asks for a new
scan.

## 8. Report

`eco.py report --lang <code>` re-audits the pages, prints the summary and saves two files in
`.eco/site/`: `report.md`, always in English, and `report.html`, the page the user opens, in
`--lang`: the language the user writes to you in (built in: `en`, `es`). For any other language,
run `eco.py labels`, translate every value (keep the keys and the `{placeholders}`), save it as
`.eco/site/labels-<code>.json` and add `--labels .eco/site/labels-<code>.json`; a file that
misses a key is refused. Write the `eco.py pending` items in that language too: the page shows
them as written.

Then start `eco.py serve` in the background. It serves `.eco/site/` on 127.0.0.1, prints the
URL of `report.html` and keeps running until stopped; give the user that URL in your final
message. Your final message starts with report.md, verbatim; it has the
same sections every time, so the user can compare runs. Anything the script cannot know goes in
through `eco.py pending "..."` before running it, not as prose after it. After the report, add
at most three short lines, only for a decision the user has to make.

The report has a "What is proven" part with three kinds of evidence, and you add none of your
own: what the files show (researched phrases in the text, before and after), what the pages that
rank today do with each primary and how many of their shared subtopics this site covers, and the
published copy.
That last line reads "not checked" until step 9 has run. Never tell the user the project ranks
better, or will: say what was measured, and that the position can only be measured once the
changes are public.

When Quirón was `not-installed`, end with this note, in the user's language:

> Optional: Quirón is a separate skill that rewrites text so it reads as if a person wrote it,
> and measures the result. If the new copy sounds stiff to you, you can install it
> (github.com/ilien-dev/quiron) and run it on these pages yourself; ask it to keep the primary
> and secondary keywords listed above.

Never commit, deploy or publish as part of this skill.

## 9. After it is published: measure the position

A position can only move once the new pages are public, so this step runs later: when the user
comes back to ask whether it worked, or tells you the site is deployed. Offer it in one line at
the end of step 8 when the site has a live address.

1. `eco.py track urls` lists the results pages the research saved, each with a file name. Fetch
   them again and save each under `.eco/site/raw/track/<today>/` with that name. With no web
   tool, `eco.py track fetch` does it slowly.
2. `eco.py track parse` first checks that production serves the pages this run left. While it
   does not, it refuses: a position measured now would describe the old text. Pass
   `--published YYYY-MM-DD` when you know the day of the deploy.
3. It prints one row per search: before, after and a result, on the engine the research used
   (DuckDuckGo or Bing, never presented as Google). "too early to tell" means the position has
   not moved and the index has had under 14 days: run it again later.
4. Google's own numbers, when the user has Search Console: ask for a CSV export of the
   Performance report, Queries tab, without "Compare", for a period that starts the day the
   changes went public or later, 28 days when possible, and read it with
   `eco.py gsc <file> --stage after --period START..END`. The export of step 2 is the "before";
   when there was none, ask for one that ends before the changes went public and pass it with
   `--stage before`. A phrase with under 10 impressions comes out as "not enough data", in either
   direction. Each phrase with enough impressions in both periods also gets a click-rate row:
   that is the measure of the title and meta description, and it needs 100 impressions on each
   side to count. A click rate also rises with the position, so give both rows together.
5. Field data, when step 1 took a baseline: 28 days after the changes went public,
   `eco.py field --stage after`. Before that it refuses, because the average would still hold
   visits to the old pages.
6. Run `eco.py report --lang <code>` again so the page shows the rows. If the pages changed
   since the final audit the report refuses, and `.eco/site/track.md` is what you show.

Give the user the rows as printed, the worse ones too, and say that each move is measured while
its cause is not proven: other pages change as well. When the site is not published, or was only
improved locally, there is nothing to run and nothing to add: the report already says the
published site was not checked.
