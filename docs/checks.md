# Every check the script runs

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

[Back to the README](../README.md)
