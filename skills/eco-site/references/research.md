# Research

The aim is a complete picture of the searches that should lead to this project, in every
language its text is in. Breadth first, then depth on what turns out to matter.

## Seeds

Write seeds from the brief, per language, before fetching anything, and plan each batch with
its `--family`. Cover these five families (the gate wants four); a seed list that skips one
misses whole groups of searches:

1. **The problem**, in the searcher's words: "how to make readme stand out", "readme looks bare".
2. **The result** they want: "github readme banner", "animated svg readme".
3. **The category** the project belongs to: "readme generator", "claude code skills".
4. **The alternatives** they use today: the manual way, the tools it replaces ("readme gif",
   "canva github banner", "capsule render").
5. **The platform plus the noun**: "github" / "repo" / "project" combined with the result noun.

For a niche project, families 1, 4 and 5 carry most of the demand: people search for the job,
not for a tool that does not exist in their head yet. Add one `adjacent` seed per entry in
`audience.adjacent`.

The problem family is the one most often left thin. Look for the error messages, the failure
("403", "blocked", "too long", "not working") and the "how do I" questions people hit right
before they would want this project.

Use short seeds (two or three words). Suggest completes prefixes, so "readme banner" returns
"readme banner generator", "readme banner size", "readme banner github"; a long seed often
returns nothing.

## Reading Suggest

- Suggestions are ordered by popularity. The first three are stronger than the last three.
- The same completion arriving from several seeds (`hits` in `suggest.json`) is the clearest
  demand signal Suggest gives.
- A seed that returns nothing, along with its variants, is evidence for `discarded`.
- Words that keep appearing next to the seed ("generator", "size", "free", "template", "examples")
  are the modifiers the long-tail questions and the FAQ should answer.
- Spanish and other languages: look for English nouns inside them ("banner", "readme" and "github"
  typed as they are, next to words of the searcher's language). Use the form people type, not the
  dictionary translation.
- Suggest says that people type a phrase, never how many. If the user has Google Search Console,
  Google Trends or another volume source, record it as evidence (`search-console`, `trends`).

## GitHub search

- `github parse` records where the project ranks today in each search (`own_rank`); the report
  shows it. A project outside the top 30 for a big search should aim at smaller ones.
- That rank, and the project's place in each results page `serp parse` reads, are the "before"
  of the run. After publishing, `eco.py track` repeats the same searches and compares; nothing
  else in the run can say whether a position moved.
- `total_count` for each query shows how crowded a search is. A query with a few hundred repos
  can be won; one with fifty thousand is won by name and stars, which the text cannot change.
- The topics shared by the top repos are the topic vocabulary GitHub users browse. Propose the
  ones that are true of the project; GitHub allows 20.
- Read the About of the top five repos: those are the phrasings that already win there.

## Competitors

- Direct competitors: tools that solve the same problem. Indirect: articles, tutorials and
  template galleries that rank for the main searches. Both count; the indirect ones show what
  Google rewards for the query.
- Find them by searching the two or three strongest phrases with the web search tool and
  through GitHub search. Save at least three, more for a crowded field.
- From `competitors.json`, look at three things: the words in their titles and H1s, the
  phrases two or more of them share (that vocabulary is expected for the query), and what none of
  them says that the project can truthfully claim (that is where it can stand out).

## When to stop

When a new batch of seeds brings back phrases already in `suggest.json`. Write down in the
brief any family of searches you decided not to pursue and why.

## Search results of the primaries

Suggest proves people type a phrase; the results page shows what wins it. Once the draft map
has its primaries, `eco.py serp urls` lists one results page per primary (DuckDuckGo's HTML
page by default, `--engine bing` as the other; Google blocks automated reads of its own). Save
each page as `.eco/<readme|site>/raw/serp/<slug>.<ext>`: the engine HTML, or a web tool's JSON or markdown of
it. `eco.py serp parse` keeps the top 10 organic results, ads and engine links left out, and
sorts them into repos, GitHub topic pages, packages, forums, videos and pages.

Read them before trusting a primary:

- Open the file once. A page about something else (an engine that rewrote the query, a
  captcha, a consent wall) is not results; refetch it with the other engine.
- For a README, no repository and no GitHub topic page in the top 10 means the engine answers that
  search with articles or tools, and a README is unlikely to get in. `map` refuses such a
  primary unless the entry has a `serp_note` that says why it stays.
- Two primaries sharing 7 or more of the 10 results are the same search to the engine. `map`
  refuses the pair: keep one as primary, make the other a variant (when the words allow it) or
  a secondary. 4 to 6 shared results are related searches: they belong on the same page.
