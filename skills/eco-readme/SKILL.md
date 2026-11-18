---
name: eco-readme
description: "Keyword research and SEO for a GitHub README: finds what people type when they have the problem the project solves (Google Suggest, GitHub search, competitor READMEs), builds a keyword map, rewrites the H1, lead, headings and alt text, proposes the GitHub About and topics, and proves every step with a script. Run it by hand with /eco:eco-readme (plugin) or /eco-readme."
disable-model-invocation: true
argument-hint: "[what the README should be found for]"
---

# Eco for a README

Echo, in the myth, could only repeat the words of others. That is the job: find the words
people use when they look for what this project does, and make the README say them back.

Eco works on what the project controls: its own text, plus the GitHub About and topics, which
it proposes and never applies on its own. Stars, backlinks and the repository name are out of
scope; say so if the user asks about them. For a website, the user runs `eco-site` instead.

Every step leaves a file in `.eco/readme/` and `eco.py report` refuses to run until the checks
behind every step pass. The report is the proof the work was done, not a description of it.
`eco.py status` shows the next step at any time.

`eco.py` is in `scripts/` next to this file. Every call takes the project and the mode:

```
python3 <skill-dir>/scripts/eco.py --root <project> --mode readme <command>
```

(On Windows, `python` instead of `python3`.) Below, `eco.py` stands for that whole prefix.

Speak to the user in their language. Keywords are researched per language of the text, not
per language of the conversation.

## 1. Understand the project and who it is for

What the user typed after the command, if anything, is what they want the README found for:
$ARGUMENTS. Treat it as a starting point for `audience.how_they_search`, not as a keyword.

Read before asking: the README and docs, the code, `package.json`/`pyproject.toml`/plugin
manifests. Ask the user only for what none of them says.

```
eco.py init --lang en[,es] --surface README.md:en --surface README.es.md:es --repo OWNER/NAME
```

Then fill in `.eco/readme/brief.json` in the user's language, and later the evidence details
and discard reasons in `keywords.json` too: the report quotes them.

- `project`: name, what it does in one sentence, the problem it solves.
- `read`: the files and pages you actually read to understand it.
- `audience.primary`: who has that problem.
- `audience.how_they_search`: in words, what those people type when the problem hits them.
  They search for the problem or the result, rarely for the tool. Nobody searches "agent skill
  that draws SVG"; they search "github readme banner".
- `audience.niche` and `audience.adjacent`: when the project is so specific that almost nobody
  searches for it directly, set `niche: true` and list the nearest problems and alternatives
  people do search: the manual way of doing it, the tools it replaces, the broader category.
- `surfaces`: the README files whose text will change.
- `github.about_file`: save
  `gh repo view OWNER/NAME --json description,repositoryTopics,homepageUrl` to `.eco/readme/github-about.json`
  and point here. GitHub's repository search looks at the name, the About and the topics by
  default (the README only with `in:readme`), and Google builds the title of the repo page from
  the name and the About. So for GitHub search the About and topics matter more than the README;
  for Google the README matters as much.
- When a rule pairs translations ("a change to README.md goes with the same change in
  README.es.md"), read it as the same places and structure in both files, each with the phrases
  researched in its own language. If the rule files are not in this checkout, read them from the
  default branch.
- `rules`: the project's own rules about these files (paired translations, files never edited
  by hand, contribution rules, manifests such as `package.json` or `plugin.json` whose keywords
  should follow the map). Read CLAUDE.md, AGENTS.md and CONTRIBUTING.md for them. If `init`
  warned that the checkout is not on the default branch, add that too.

`eco.py brief` checks it and keeps a copy of every surface in `.eco/readme/original/`: that copy
is the baseline every later comparison uses, so run `brief` before you change any text.

When the project has a GitHub repository the user can push to, save who reaches it today:
`eco.py traffic --stage before` prints two `gh api` commands; run them, then run it again. It
records the unique visitors of the last 14 days: from search engines, from other GitHub pages and
in all. GitHub keeps 14 days and nothing older, so a reading skipped now cannot be taken later.
With no `gh`, or no push access, skip it: the report then has positions and no visitors.

## 2. Research, as deep as the gate demands and then some

Read [references/research.md](references/research.md) before starting; it has the seed
recipe, how to find competitors and how to read what comes back.

Do each language separately: Spanish speakers type English words ("banner", "readme"), and
that only shows up when you search in Spanish.

1. **Autocomplete (Google Suggest, Bing, DuckDuckGo).** Plan seeds by family (problem, result,
   category, alternative, platform, and `adjacent` for each adjacent audience of a niche project):
   `eco.py suggest urls --lang en --family problem --engine google --seed "..." --seed "..."`
   prints the URLs. Fetch them with your web tool and save the raw responses under
   `.eco/readme/raw/suggest/<lang>/<engine>/` (one file per response or a tool's combined output
   both parse), then `eco.py suggest parse`. Use `--depth 2` on the two or three strongest seeds
   for the a-z expansion. Responses to queries that were never planned, or that share no word
   with their query, are ignored. With no web tool, `eco.py suggest fetch` fetches slowly by
   itself. `eco.py suggest terms --grep word` lists what came back. These services rate-limit:
   fetch in small batches, never refetch a query that has a response, and when Google makes you
   wait, plan the next batch with `--engine bing` or `--engine ddg`. Google remains the
   reference for Google ranking; use it for the strongest seeds.
2. **GitHub search**: `eco.py github urls --query "..."` prints each search with a file name;
   fetch it (or `gh api "search/repositories?q=...&per_page=30"`) and save it under
   `.eco/readme/raw/github/` with that name, then `eco.py github parse`. It gives the size of
   each search, the topics competitors use and where the project ranks today: the "before" that
   step 8 compares with, so keep the names as printed.
3. **Competitors.** Find the READMEs and pages that rank for the main searches today, save them
   under `.eco/readme/raw/competitors/`, then `eco.py competitors`. It lists their titles,
   descriptions and headings and the phrases two or more of them share. It also lists the
   subtopics they share (a heading in one that at least two of them write about) and which ones
   your README never mentions: candidates for a section in step 4, only where the project has a
   true answer. The report counts them covered before and after; none is required.

`eco.py research` checks the depth: for the main language (the first in the brief) 20 non-empty
responses (one seed counts for 8 at most), 5 fetched seeds and 4 of the 5 families; for each
other language 10, 3 and 3; one seed per adjacent audience; 3 competitors; 2 GitHub searches.
These are floors. Stop when new queries stop bringing new phrases, not when the gate turns green.

Suggest shows that people type a phrase, not how many. A phrase with no suggestions at all, in
any variant, goes to `discarded`.

## 3. The keyword map

Write `.eco/readme/keywords.json`:

```json
{"keywords": [
  {"phrase": "github readme banner", "lang": "en", "tier": "primary",
   "evidence": [{"source": "suggest", "detail": "8 variants: generator, size, maker"}],
   "placements": ["h1", "lead", "about"], "claim": "true"},
  {"phrase": "readme generator", "lang": "en", "tier": "secondary",
   "evidence": [{"source": "suggest", "detail": "github readme generator ai/free/online"}],
   "placements": ["heading"], "claim": "negation"},
  {"phrase": "readme hero", "lang": "en", "tier": "discarded", "reason": "no suggestions"}
]}
```

- `tier`: `primary` (the 1 to 5 searches the project should win; each needs `h1`, `lead` or
  `about` and at least two placements), `secondary`, `long-tail` (questions and specific
  phrasings), `discarded` (with a `reason`). Keep at least 10 phrases and discard at least 3.
- `evidence`: where the phrase came from. `suggest`, `github` and `competitor` are checked: the
  phrase must be in what the service suggested (not in the query you typed), in a GitHub
  description or topic, or in a competitor's title, description, lead or headings.
  `search-console` and `trends` are taken on trust. A primary needs demand evidence (`suggest`,
  `search-console` or `trends`): GitHub and competitors show how others word it, not that people
  search it.
- `placements`: README `h1 lead heading alt body` (`lead` is the first 300 characters of prose
  after the H1); GitHub `about topics`. [references/placements.md](references/placements.md)
  says what each one weighs and how to write it.
- `claim`: `true` when the project does what the phrase says. `negation` when people search it
  but the project is not that thing: the phrase may only appear in an honest "is it X? No, ..."
  answer. Never place a phrase that promises something the project does not do.
- `variants`: optional forms that count as the same phrase: the same words in another order,
  plural or punctuation, or a form that is itself in the Suggest data.

Before checking it, look at what wins each primary today: `eco.py serp urls` lists one results
page per primary (DuckDuckGo by default, `--engine bing`); fetch each, save it as
`.eco/readme/raw/serp/<slug>.<ext>` (with no web tool, `eco.py serp fetch` does it slowly), run
`eco.py serp parse`, and open the files once to make sure they are results for that query and
not a block. [references/research.md](references/research.md) says how to read them.

`eco.py map` checks it, and refuses while the research gate fails, while a primary has no saved
results, when two primaries share 7 or more of the top 10 results (one search: keep one), and
when no repository or GitHub topic page is in a primary's top 10 (unless the entry has a
`serp_note` saying why it stays). Show the user the primaries and the discarded ones before
editing (unless the request said not to ask).

## 4. Put the words in place

`eco.py audit --save baseline` records where the originals stand.

Then rewrite. Restructure when the structure is in the way: an H1 that names the tool and
nothing else, a first paragraph that never says what the project is for, headings that say
nothing searchable. Everything in [references/placements.md](references/placements.md)
applies; the short version:

- Primaries must land where the map says. Secondaries and long-tail phrases are opportunities:
  place one where a sentence wants it, and leave it out where it would need a sentence of its own.
- One phrase per place, in natural sentences. The audit flags a phrase that takes more than 3%
  of the words, sits in more than half the headings, or a run of "<Name> is a <keyword>"
  sentences. A keyword list at the bottom of a README is not counted as text.
- Build sections around real searches when the project has an answer: a problem people type
  ("WebFetch 403"), a comparison ("X vs Y"), a "why not just ..." question.
- Keep each file's line endings when editing (on Windows, tools in Git Bash can turn CRLF into LF).
- Renaming a heading breaks links to its anchor. Keep the old one with `<a id="old-anchor"></a>`
  above the new heading; `compare` fails when an internal link loses its target.
- Every claim in new text must be true of the project. The audit lists every number,
  percentage, multiplier, year and superlative the new text adds;
  `eco.py claims verify --claim "3x" --source docs/bench.md` records where each comes from (a
  project file must state the number; a URL is taken on trust), and the report refuses while one
  is unchecked. A claim with no source comes out of the text.
- Follow `rules` from the brief: a change to one language goes to its pair.
- The GitHub About, topics and homepage live outside the repo. Write the exact
  `gh repo edit` command and run it only after the user says yes in this conversation; record it
  with `eco.py offsite --about "..." --topics a,b --homepage URL [--applied]` (the full topic
  list after the change). Once recorded, the audit checks `about` and `topics` placements against
  this proposal and reports them apart: a proposal nobody applies does not ship, so every primary
  still has to be in an H1 or lead, or in an About that is live.

`eco.py audit` until no primary is missing and there are no flags. A saved snapshot does not
update itself: after a fix, save it again. Then `eco.py audit --save pre-quiron`.

## 5. Quirón, only when it is installed

Quirón is a separate skill that rewrites text so it reads as a person wrote it and measures the
result. Keyword-heavy copy often reads stiff, so it helps; it is never required.

1. `eco.py quiron detect`. Also check the skills listed in this session for `quiron`.
2. **Installed:** always ask, with the harness's question tool (AskUserQuestion in Claude Code),
   in one question: "Quirón can rewrite the new text so it reads more like a person wrote it,
   keeping the keywords in place. Run it now?" Options: run it / skip. Only when the request
   already answered it ("use Quirón", "skip the humanizer") take that answer without asking.
3. **Not installed:** do not ask and do not install it. Record `not-installed` and go on; the
   recommendation comes after the report (step 7).
4. To run it: copy the changed prose (not markup) into a text file, invoke Quirón on it, and pass
   it the primary and secondary phrases as fixed words it must keep. Follow its own workflow;
   when the user cannot be asked, skip its questions to the writer and say so. Put the result
   back into the files.
5. `eco.py quiron record --status used|skipped|not-installed --result "<Quirón's one-line result>"`.
   `used` is refused when the files did not change since `pre-quiron`. Once recorded, the
   pre-quiron snapshot cannot be retaken; to redo the pass, `eco.py quiron reset` first.

## 6. Check that nothing broke

`eco.py audit --save final`, then `eco.py compare pre-quiron final`.

If a placement was lost, the keyword wins: put it back with the smallest edit that keeps the
rest of Quirón's wording, then audit again. Do not run a second Quirón rewrite. Also reread the
changed text once for anything the humanizing broke: a fact, a link, a command, markup.

## 7. Report

`eco.py report --lang <code>` re-audits the files, prints the summary and saves two files in
`.eco/readme/`: `report.md`, always in English, and `report.html`, the page the user opens, in
`--lang`: the language the user writes to you in (built in: `en`, `es`). For any other language,
run `eco.py labels`, translate every value (keep the keys and the `{placeholders}`), save it as
`.eco/readme/labels-<code>.json` and add `--labels .eco/readme/labels-<code>.json`; a file that
misses a key is refused. Write the `eco.py pending` items in that language too: the page shows
them as written.

Then start `eco.py serve` in the background. It serves `.eco/readme/` on 127.0.0.1, prints the
URL of `report.html` and keeps running until stopped; give the user that URL in your final
message. Your final message starts with report.md, verbatim; it has the
same sections every time, so the user can compare runs. Anything the script cannot know goes in
through `eco.py pending "..."` before running it, not as prose after it. After the report, add
at most three short lines, only for a decision the user has to make.

The report has a "What is proven" part with three kinds of evidence, and you add none of your
own: what the files show (researched phrases in the text, before and after), what the pages that
rank today do with each primary and how many of their shared subtopics this README covers, and
the published copy.
That last line reads "not checked" until step 8 has run. Never tell the user the project ranks
better, or will: say what was measured, and that the position can only be measured once the
changes are public.

When Quirón was `not-installed`, end with this note, in the user's language:

> Optional: Quirón is a separate skill that rewrites text so it reads as if a person wrote it,
> and measures the result. If the new README sounds stiff to you, you can install it
> (github.com/ilien-dev/quiron) and run it on these files yourself; ask it to keep the primary
> and secondary keywords listed above.

Never commit or publish as part of this skill.

## 8. After it is published: measure the position

A position can only move once the new text is public, so this step runs later: when the user
comes back to ask whether it worked, or tells you the changes are merged. Offer it in one line
at the end of step 7 when the project has a GitHub repository.

1. `eco.py track urls` lists the searches the research saved, each with a file name. Fetch them
   again and save each under `.eco/readme/raw/track/<today>/` with that name. With no web tool,
   `eco.py track fetch` does it slowly.
2. `eco.py track parse` first checks that GitHub shows the README this run left. While it does
   not, it refuses: a position measured now would describe the old text. Pass
   `--published YYYY-MM-DD` when you know the day the changes were merged (`git log`).
3. GitHub's repository search reads the name, About and topics, not the README. Its rows are
   left out until the About and topics on github.com are the ones recorded with
   `eco.py offsite`; the search-engine rows do not depend on that.
4. It prints one row per search: before, after and a result. "too early to tell" means the
   position has not moved and the index has had under 3 days (GitHub) or 14 days (search
   engines): run it again later.
5. Visitors, when step 1 saved a reading: 14 days after the changes went public,
   `eco.py traffic --stage after` prints the two commands again and then compares. Before that it
   refuses, because GitHub's 14 days would still hold days of the old README. A position says
   where the repository shows up; this says whether more people arrived from a search.
6. Run `eco.py report --lang <code>` again so the page shows the rows. If the files changed
   since the final audit the report refuses, and `.eco/readme/track.md` is what you show.

Give the user the rows as printed, the worse ones too, and say that each move is measured while
its cause is not proven: other repositories change as well. With no GitHub repository, or when
the user does not publish, there is nothing to run and nothing to add: the report already says
the published README was not checked.
