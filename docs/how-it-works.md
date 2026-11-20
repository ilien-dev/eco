# How a run works

Eco works on the one thing you control: your own text. Backlinks, domain age and mentions on
other sites are out of its reach, and it says so.

Every run goes through these steps:

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

Use it: type `/eco:eco-readme` or `/eco:eco-site` (or `/eco-readme`, `/eco-site` after `npx skills add`).
Each skill keeps its run in its own folder, `.eco/readme/` or `.eco/site/`, so a project can have both.
Eco never commits, pushes or edits your GitHub About on its own: changes outside the repo are
proposed as an exact `gh repo edit` command.


[Back to the README](../README.md)
