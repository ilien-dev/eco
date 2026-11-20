# Limits

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

[Back to the README](../README.md)
