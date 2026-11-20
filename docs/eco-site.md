# Websites: robots.txt, sitemap, llms.txt and Lighthouse

`eco-site` does everything `eco-readme` does, page by page, and then checks what surrounds the pages.

**On a website, checks what surrounds the pages**: robots.txt (and whether AI search bots such
as OAI-SearchBot, Claude-SearchBot and PerplexityBot can reach the site), the sitemap, llms.txt,
and Lighthouse. With [Unlighthouse](https://unlighthouse.dev) it scans production when the
site is live (or the build, served as static files, when the changes are not deployed yet) and
works every page toward 100 in performance, accessibility, best practices and SEO. Fixes you
would not notice it makes on its own; anything that changes how the site looks or behaves,
such as removing an animation or changing a color, it asks you first.

`eco-site` needs Node.js 18 or newer for the Lighthouse step. Unlighthouse runs through
`npx`, so there is nothing else to install; the first run downloads a Chrome to
`~/.unlighthouse` if you have none.

On a site with several pages, each phrase belongs to one page, so two of your pages never compete
for the same search. With a Search Console export, the searches Google already shows you for at
positions 5 to 20 come first.

> [!NOTE]
> New in 0.2.0: the site checks are covered by the test suite and have not been through a full run on a real website yet.


[Back to the README](../README.md)
