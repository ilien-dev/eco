<p align="center"><b>English</b> · <a href="README.es.md">Español</a></p>

# Eco: keyword research and on-page SEO for your README and website

Eco is an agent skill for Claude Code, Codex and other AI agents. It finds the words people
type when they look for what your project does, puts those words in the README or the site
where Google and GitHub search read them, and checks the result with a script instead of
taking the agent's word for it.

It works on the one thing you control: your own text. Backlinks, domain age and mentions on
other sites are out of its reach, and it says so.

## What it does

1. **Reads the project** (repo, docs, site) and writes down who it is for and how those people
   search. When a project is so niche that nobody searches for it by name, it looks for the
   nearest problems and alternatives people do search.
2. **Researches keywords per language**: autocomplete from Google, Bing and DuckDuckGo, GitHub repository search
   (with where your repo ranks today) and the pages and READMEs of competitors.
3. **Builds a keyword map**: primary, secondary, long-tail and discarded phrases, each with the
   research that backs it and the places it has to appear (title, meta description, H1, lead,
   headings, alt text, FAQ, GitHub About and topics).
4. **Rewrites the text** so those words sit where they count, without stuffing and without
   claims the project cannot back.
5. **Offers [Quirón](https://github.com/ilien-dev/quiron)**, a humanizer, for the new text. You
   can skip it; if it is not installed, Eco offers to install it.
6. **Checks that nothing broke**: every keyword placement, internal link and anchor survives the
   humanizing pass. When the two disagree, the keywords win.
7. **Reports** in the same format every time.

## Measured, not described

`scripts/eco.py` (Python 3.9+, standard library only) writes every step to `.eco/` and refuses
to produce the report until each check passes:

- the research is deep enough: non-empty autocomplete responses from several seed families per
  language, competitors, GitHub searches;
- every phrase's evidence is really in the research files;
- primary keywords sit in their required places, with no stuffing flags;
- the baseline is the original text, kept before any edit;
- the keyword map did not change between the snapshot before the humanizing pass and the final one;
- nothing was lost after the humanizing pass, and the report re-audits the files it describes.

## Install

```sh
npx skills add ilien-dev/eco
```

Or, in Claude Code, as a plugin:

```
/plugin marketplace add ilien-dev/eco
/plugin install eco@eco
```

## Use

Open your agent in the project and ask:

```
/eco make this README show up when people search for what it does
```

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
- Version 0.1.0: tested on four projects by one person, all in Claude Code. The interactive
  Quirón install, a project with no repo, and other agents have not been tried yet.

## License

MIT, see [LICENSE](LICENSE).
