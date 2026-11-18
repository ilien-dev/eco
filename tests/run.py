#!/usr/bin/env python3
"""Tests for skills/eco/scripts/eco.py. Run: python tests/run.py"""
from __future__ import annotations

import datetime
import io
import json
import re
import shutil
import sys
import tempfile
import threading
import urllib.request
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'shared' / 'scripts'))
import eco  # noqa: E402

FAILS: list[str] = []
CRLF, LF = bytes([13, 10]), bytes([10])


def check(name: str, cond: bool, detail: str = '') -> None:
    print(('ok    ' if cond else 'FAIL  ') + name + (f'  ({detail[:1500]})' if detail and not cond else ''))
    if not cond:
        FAILS.append(name)


def run(root: Path, *argv, mode: str = 'readme') -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            eco.main(['--root', str(root), '--mode', mode, *argv])
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue() + err.getvalue()


README = """<p align="center"><img src="hero.svg" alt="Demo of the tool"></p>

# Widget

A tool for widgets. See [install](#install).

## Install

Run `pip install widget` and read <https://example.com>.
"""

HTML = """<!doctype html><html lang="en"><head><title>Widget</title>
<meta name="description" content="Widget.">
<script type="application/ld+json">{"@type":"FAQPage","mainEntity":[{"name":"What is a github readme banner?"}]}</script>
</head><body><h1>Widget</h1><p>Hello.</p><div hidden>github readme banner</div><script>var x = "github readme banner";</script></body></html>"""


def payload(q, items):
    return json.dumps([q, items, [], {}])


def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    # --- packaging: each skill carries its own copy of the shared engine, and runs only by hand
    repo = HERE.parent
    for skill in ('eco-readme', 'eco-site'):
        for f in ('scripts/eco.py', 'references/research.md', 'references/placements.md'):
            a, b = repo / 'shared' / f, repo / 'skills' / skill / f
            same = b.exists() and a.read_bytes().replace(CRLF, LF) == b.read_bytes().replace(CRLF, LF)
            check(f'skills/{skill}/{f} matches shared/ (run tools/sync.py)', same)
        head = (repo / 'skills' / skill / 'SKILL.md').read_text(encoding='utf-8').split('---')[1]
        check(f'{skill} is manual only', f'name: {skill}' in head and 'disable-model-invocation: true' in head, head)
    # --- positions: verdicts and the Search Console export
    check('a better position is an improvement, a lower one is worse',
          [eco.rank_verdict(*a) for a in ((5, 2), (2, 5), (4, 4), (None, 7), (7, None), (None, None))]
          == ['up', 'down', 'same', 'entered', 'left', 'out'])
    check('a results page moving one place is noise', eco.rank_verdict(5, 4, eco.SERP_NOISE) == 'same' and eco.rank_verdict(5, 3, eco.SERP_NOISE) == 'up')
    g = eco.parse_gsc('\ufeffConsultas principales,Clics,Impresiones,CTR,Posición\nReadme Banner,10,200,5%,"14,2"\nother,1,3,33.3%,2.0\n')
    check('a Search Console export is read by column, whatever its language',
          g['readme banner'] == {'q': 'Readme Banner', 'clicks': 10, 'impressions': 200, 'position': 14.2}, str(g))
    check('own results: the host of the site or the path of the repository',
          eco.own_rank_in(['https://a.dev/x', 'https://www.widget.dev/es/', 'https://github.com/me/widget/tree/main'], [('host', 'widget.dev')]) == 2
          and eco.own_rank_in(['https://github.com/me/widget-two', 'https://github.com/Me/Widget#readme'], [('repo', 'github.com/me/widget')]) == 2
          and eco.own_rank_in(['https://a.dev'], [('host', 'widget.dev')]) is None)
    # --- parsers and matching
    r = eco.parse_readme(README)
    check('readme h1', r['h1'] == ['Widget'], str(r['h1']))
    check('readme lead skips the hero image', r['lead'].startswith('A tool for widgets'), r['lead'][:40])
    check('readme alt, heading, code', 'Demo of the tool' in r['alt'] and 'Install' in r['heading'] and 'pip install widget' in r['code'])
    check('readme anchors from headings', 'install' in r['anchors'], str(r['anchors']))
    r2 = eco.parse_readme('~~~\n# not a title\n~~~\n\nReal Title\n==========\n\nText here.\n')
    check('tilde fence skipped, setext H1 found', r2['h1'] == ['Real Title'], str(r2['h1']))
    r3 = eco.parse_readme('# T\n\nBody.\n\n<b>Keywords:</b> a · b · c · d · e · f · g\n')
    check('keyword footer is not body text', 'Keywords' not in r3['body'] and bool(r3['keyword_lines']), r3['body'])
    r4 = eco.parse_readme('# T\n\nA lead, with, many, commas, in, it, all, fine.\n\n| a, b, c, d, e, f, g | x |\n\n'
                          '<sub><b>Keywords:</b> one · two\nthree · four</sub>\n')
    check('a lead with commas is kept', r4['lead'].startswith('A lead, with'), r4['lead'])
    check('table rows with commas are kept', 'a, b, c' in r4['body'], r4['body'])
    check('a whole keyword block is dropped', 'three' not in r4['body'] and 'one' not in r4['body'], r4['body'])
    r5 = eco.parse_readme('# T\n\n## web_fetch tool\n\n## Notes\n\n## Notes\n')
    check('GitHub slugs keep underscores and number duplicates',
          {'web_fetch-tool', 'notes', 'notes-1'} <= set(r5['anchors']), str(r5['anchors']))
    check('a phrase split over two headings is not placed',
          eco.count_items(['Keep CLAUDE.md', 'and AGENTS.md in sync'], ['claude md and agents md']) == 0)
    hs = eco.parse_html('<html><head><title>Real</title></head><body><svg><title>Logo</title></svg><h1>X</h1><p>First para.</p><p>Second.</p></body></html>')
    check('an <svg> title is not the page title; the site lead is the first paragraph',
          hs['title'] == 'Real' and hs['lead'] == 'First para.', f"{hs['title']!r} {hs['lead']!r}")
    check('DuckDuckGo gets the language region', 'kl=es-es' in eco.suggest_url('banner github', 'es', 'ddg'))
    check('a seed that already asks gets no second question word',
          not any(q.startswith('how to how to') for q in eco.expand('how to make readme', 'en', 2, 'problem')))
    km1 = {'keywords': [{'phrase': 'a b', 'lang': 'en', 'tier': 'primary', 'placements': ['h1'], 'evidence': [{'source': 'suggest', 'detail': 'x'}]}]}
    km2 = json.loads(json.dumps(km1))
    km2['keywords'][0]['evidence'][0]['detail'] = 'a better note'
    check('editing an evidence note does not unlock the map', eco.map_hash(km1) == eco.map_hash(km2))
    h = eco.parse_html(HTML)
    check('html title', h['title'] == 'Widget')
    check('html visible text excludes scripts and hidden', 'github readme banner' not in h['body'], h['body'])
    check('html json-ld text is separate', 'github readme banner' in h['jsonld'])
    check('exact phrase, not a substring', eco.contains('a banner generator', 'readme banner generator') == 0)
    check('punctuation-insensitive match', eco.contains('Keep CLAUDE.md short', 'claude md') == 1 and eco.contains('self-hosted', 'self hosted') == 1)
    check('word boundary', eco.contains('readme banners', 'readme banner') == 0)
    check('overlapping variants count once', eco.count_in('web scraping mcp server', ['web scraping mcp server', 'mcp server']) == 1)
    wrapped = json.dumps({'results': [{'content': payload('readme banner', ['readme banner generator'])}]})
    check('suggest inside a web tool wrapper', eco.parse_suggest_text(wrapped) == [('readme banner', ['readme banner generator'])])
    check('several raw suggest responses in one file', len(eco.parse_suggest_text(payload('a', ['a b']) + '\n' + payload('c', []))) == 2)

    # --- page checks taken from what search engines need to use a page at all
    bad_page = eco.parse_html('<html><head><title>Widget banner maker for GitHub READMEs</title><title>Again</title>'
                              '<meta name="robots" content="noindex, follow">'
                              '<meta name="description" content="Widget banner maker for GitHub READMEs. Make one. Learn more now!">'
                              '<link rel="alternate" hreflang="es" href="/es/">'
                              '<script type="application/ld+json">{"@type": "FAQPage",}</script></head>'
                              '<body><h1>X</h1><img src="a.png"><img src="b.png" alt=""></body></html>')
    found = ' | '.join(eco.html_checks(bad_page, 'en', {'en', 'es', 'fr'}))
    for needle, what in [('noindex', 'noindex'), ('JSON-LD block 1', 'JSON-LD that does not parse'), ('no <html lang>', 'missing lang'),
                         ('page itself', 'hreflang without self'), ('[fr] version', 'missing hreflang to another version'),
                         ('og:image', 'missing og:image'), ('1 visible images without an alt', 'img without alt (alt="" is fine)'),
                         ('more than one title', 'duplicate title'), ('repeating the title', 'description echoes title'),
                         ('stock call to action', 'stock CTA')]:
        check(f'html check: {what}', needle in found, found)
    good_page = eco.parse_html('<html lang="en-US"><head><title>T</title><meta property="og:image" content="https://x/o.png">'
                               '<link rel="alternate" hreflang="en" href="/"><link rel="alternate" hreflang="es" href="/es/">'
                               '<meta name="description" content="Draws a banner that says what your project does."></head>'
                               '<body><h1>X</h1><img src="a.png" alt="A banner"></body></html>')
    found = eco.html_checks(good_page, 'en', {'en', 'es'})
    check('a page with lang, hreflang both ways, og:image and alt passes', not found, str(found))
    check('a call to action inside a sentence is not flagged',
          not eco.templated_meta('Widget', 'Draws README banners; the docs show how to get started.'))
    check('a call to action as its own sentence is flagged', 'stock call' in ' '.join(eco.templated_meta('Widget', 'Draws banners. Get started today!')))
    check('a description equal to the title is flagged', 'title again' in ' '.join(eco.templated_meta('Same words', 'Same words.')))

    # --- search results pages
    bing = ('<ol><li class="b_ad"><h2><a href="https://ads.example/x">Ad</a></h2></li>'
            '<li class="b_algo"><h2><a href="https://www.bing.com/ck/a?!&&p=1&u=a1aHR0cHM6Ly9naXRodWIuY29tL2EvYg&ntb=1">A</a></h2>'
            '<a href="https://github.com/a/b/other">x</a></li>'
            '<li class="b_algo"><h2><a href="https://www.reddit.com/r/x/">B</a></h2></li></ol>')
    check('bing results: redirect unwrapped, ads and extra links skipped',
          eco.parse_serp(bing) == ['https://github.com/a/b', 'https://www.reddit.com/r/x/'], str(eco.parse_serp(bing)))
    ddg = ('<div class="result result--ad"><a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Ad</a></div>'
           '<div class="result"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fgitlab.com%2Fx%2Fy&rut=1">X</a></div>')
    check('ddg results: ads skipped, redirect unwrapped', eco.parse_serp(ddg) == ['https://gitlab.com/x/y'], str(eco.parse_serp(ddg)))
    md = ('## [A](https://duckduckgo.com/l/?uddg=https%3A%2F%2Fgithub.com%2Fa%2Fb&rut=1)\n'
          '[B](/l/?uddg=https%3A%2F%2Fb.dev%2F&rut=2)\n')
    check('results from markdown, absolute and bare-path redirects', eco.parse_serp(md) == ['https://github.com/a/b', 'https://b.dev/'], str(eco.parse_serp(md)))
    wrapped_serp = json.dumps({'url': 'https://html.duckduckgo.com/html/?q=x', 'content': ddg + ' ' * 200})
    check('results inside a web tool JSON wrapper', eco.parse_serp(wrapped_serp) == ['https://gitlab.com/x/y'], str(eco.parse_serp(wrapped_serp)))
    check('results from a web tool JSON', eco.parse_serp(json.dumps({'results': [{'url': 'https://a.dev/'}, {'url': 'https://a.dev'}]})) == ['https://a.dev/'])
    check('result kinds', [eco.result_kind(u) for u in ('https://github.com/a/b', 'https://github.com/a', 'https://pypi.org/project/x',
                                                         'https://github.com/topics/readme-banner')]
          == ['repo', 'page', 'package', 'topic'])

    # --- claims
    cl = [c for c, _ in eco.extract_claims('Widget is 3x faster and used by 10k developers since 2024. Python 3.9 works. It has 47% less code.')]
    check('claims: multiplier, quantity, year, percentage; a version is not a claim',
          {'3x', '10k developers', '2024', '47%'} <= set(cl) and not any('3.9' in c for c in cl), str(cl))

    # --- a full run in a temp project
    tmp = Path(tempfile.mkdtemp(prefix='eco-test-'))
    try:
        code, out = run(tmp / 'nope', 'status')
        check('missing root is a clean error', code == 2 and 'does not exist' in out, out)
        write(tmp / 'README.md', README)
        write(tmp / 'dist' / 'index.html', HTML)
        code, out = run(tmp, 'init', '--lang', 'en', '--surface', 'README.md:en', '--surface', 'dist/index.html:en', '--repo', 'me/widget')
        check('the readme skill refuses an html surface', code == 2 and 'site skill' in out, out)
        code, out = run(tmp, 'init', '--lang', 'en', '--surface', 'README.md:en', '--repo', 'me/widget')
        check('init', code == 0, out)
        code, out = run(tmp, 'brief')
        check('empty brief fails', code == 1 and 'project.name' in out, out)
        bp = tmp / '.eco' / 'readme' / 'brief.json'
        b = json.loads(bp.read_text(encoding='utf-8'))
        b['project'] = {'name': 'Widget', 'what': 'Draws README banners.', 'problem': 'READMEs look bare.'}
        b['audience'] = {'primary': 'Open source maintainers', 'niche': True, 'adjacent': ['readme gif makers'],
                         'how_they_search': 'github readme banner'}
        b['read'] = ['README.md', 'src/']
        bp.write_text(json.dumps(b), encoding='utf-8')
        code, out = run(tmp, 'brief')
        check('niche without 2 adjacent audiences fails', code == 1 and 'adjacent' in out, out)
        b['audience']['adjacent'].append('banner template users')
        bp.write_text(json.dumps(b), encoding='utf-8')
        code, out = run(tmp, 'brief')
        check('complete brief passes and keeps originals', code == 0 and (tmp / '.eco' / 'readme' / 'original' / 'README.md').exists(), out)

        check('research gate fails with nothing fetched', run(tmp, 'research')[0] == 1)
        fams = {'result': ['readme banner', 'github banner'], 'problem': ['readme header'], 'alternative': ['readme gif'],
                'category': ['readme generator'], 'platform': ['github project banner'], 'adjacent': ['gif maker', 'banner template']}
        for fam, seeds in fams.items():
            run(tmp, 'suggest', 'urls', '--lang', 'en', '--family', fam, *sum((['--seed', s] for s in seeds), []))
        plan = json.loads((tmp / '.eco' / 'readme' / 'suggest-plan.json').read_text(encoding='utf-8'))
        check('question words only on problem and result seeds', not any(q['q'].startswith('how to readme gif') for q in plan['queries'])
              and any(q['q'] == 'how to readme banner' for q in plan['queries']))
        blob = '\n'.join(payload(q['q'], [q['q'] + ' generator', q['q'] + ' github readme banner']) for q in plan['queries'])
        blob += '\n' + payload('not planned at all', ['x'])
        blob += '\n' + payload(plan['queries'][0]['q'], ['totally unrelated words'])
        blob += '\n' + payload(plan['queries'][-1]['q'], [])
        echo_q = plan['queries'][-2]['q']
        blob += '\n' + payload(echo_q, [echo_q])
        write(tmp / '.eco' / 'readme' / 'raw' / 'suggest' / 'en' / 'all.txt', blob)
        code, out = run(tmp, 'suggest', 'parse')
        sug = json.loads((tmp / '.eco' / 'readme' / 'suggest.json').read_text(encoding='utf-8'))
        check('the echo of the query is not a suggestion',
              not any(r['suggestions'] for r in sug['responses'].values() if r['q'] == echo_q))
        check('unplanned and off-topic responses are ignored', 'not in the plan' in out and 'off-topic' in out, out)

        for n in ('readme-banner', 'github-banner'):
            write(tmp / '.eco' / 'readme' / 'raw' / 'github' / f'{n}.json', json.dumps({'total_count': 120, 'items': [
                {'full_name': f'x/{n}', 'description': 'readme banner maker', 'topics': ['readme', 'svg'], 'stargazers_count': 3},
                {'full_name': 'me/widget', 'description': 'w', 'topics': []}]}))
        code, out = run(tmp, 'github', 'urls', '--query', 'readme banner')
        check('github urls names the file and keeps the query for later', code == 0 and 'readme-banner.json  https://api.github.com/search/' in out, out)
        code, out = run(tmp, 'github', 'parse')
        check('github parse records our rank', 'me/widget: #2' in out, out)
        for n in range(3):
            write(tmp / '.eco' / 'readme' / 'raw' / 'competitors' / f'c{n}.html', f'<title>GitHub README banner generator {n}</title><h1>Animated README banner</h1><p>Make one.</p>')
        code, out = run(tmp, 'competitors')
        check('competitors: shared phrases', 'readme banner' in out and 'banner generator' in out, out)
        code, out = run(tmp, 'research')
        check('research gate passes', code == 0, out)

        kp = tmp / '.eco' / 'readme' / 'keywords.json'
        kws = [{'phrase': 'github readme banner', 'lang': 'en', 'tier': 'primary',
                'evidence': [{'source': 'suggest', 'detail': 'x'}], 'placements': ['h1', 'lead'], 'claim': 'true'},
               {'phrase': 'invented phrase nobody types', 'lang': 'en', 'tier': 'secondary',
                'evidence': [{'source': 'suggest'}], 'placements': ['body']},
               {'phrase': 'readme banner', 'lang': 'en', 'tier': 'secondary', 'variants': ['past cloudflare'],
                'evidence': [{'source': 'competitor'}], 'placements': ['body']}]
        kp.write_text(json.dumps({'keywords': kws}), encoding='utf-8')
        code, out = run(tmp, 'map')
        check('evidence is checked against the research', code == 1 and 'phrase is not in .eco/readme/suggest' in out, out)
        check('a variant must be the same words', "variant 'past cloudflare'" in out, out)
        check('map needs enough phrases and discarded ones', 'at least 10' in out and 'discarded' in out, out)
        kp.write_text(json.dumps({'keywords': [
            {'phrase': plan['queries'][-1]['q'], 'lang': 'en', 'tier': 'secondary', 'evidence': [{'source': 'suggest'}], 'placements': ['body']},
            {'phrase': 'animated readme banner', 'lang': 'en', 'tier': 'primary', 'evidence': [{'source': 'competitor'}], 'placements': ['h1', 'lead']}]}),
            encoding='utf-8')
        code, out = run(tmp, 'map')
        check('a planned query is not evidence; only suggestions are', repr(plan['queries'][-1]['q']) in out and 'not in .eco/readme/suggest' in out, out)
        check('a primary needs demand evidence, not only competitors', 'demand evidence' in out, out)
        kws[1] = {'phrase': 'readme header generator', 'lang': 'en', 'tier': 'secondary', 'evidence': [{'source': 'suggest'}], 'placements': ['body']}
        kws[2] = {'phrase': 'readme banners', 'lang': 'en', 'tier': 'secondary', 'variants': ['readme banner'],
                  'evidence': [{'source': 'competitor'}], 'placements': ['body']}
        for q in [q for q in plan['queries'] if q['q'] + ' generator' != 'readme header generator'][:12]:
            kws.append({'phrase': q['q'] + ' generator', 'lang': 'en', 'tier': 'long-tail', 'evidence': [{'source': 'suggest'}], 'placements': ['body']})
        kws += [{'phrase': f'dropped {i}', 'lang': 'en', 'tier': 'discarded', 'reason': 'no suggestions'} for i in range(3)]
        kp.write_text(json.dumps({'keywords': kws}), encoding='utf-8')
        code, out = run(tmp, 'map')
        check('a primary needs saved search results', code == 1 and 'no saved search results' in out, out)

        def serp_file(phrase, urls):
            write(tmp / '.eco' / 'readme' / 'raw' / 'serp' / f'{eco.serp_slug(phrase, "en")}.json', json.dumps({'results': [{'url': u} for u in urls]}))

        pages = [f'https://site{i}.dev/banner' for i in range(9)]
        code, out = run(tmp, 'serp', 'urls')
        check('serp urls lists the primaries', code == 0 and 'duckduckgo.com/html' in out and 'en-github-readme-banner' in out, out)
        serp_file('github readme banner', pages)
        run(tmp, 'serp', 'urls', '--phrase', 'readme header generator', '--lang', 'en')
        serp_file('readme header generator', pages[:8] + ['https://github.com/x/y'])
        code, out = run(tmp, 'serp', 'parse')
        check('serp parse reports shared results', 'share 8' in out and 'one search intent' in out, out)
        check('serp parse records where the project stands', 'yours: not in the first 9' in out, out)
        kws[1]['tier'], kws[1]['placements'] = 'primary', ['h1', 'lead']
        kp.write_text(json.dumps({'keywords': kws}), encoding='utf-8')
        code, out = run(tmp, 'map')
        check('two primaries with the same results are one intent', code == 1 and 'one search intent' in out, out)
        kws[1]['tier'], kws[1]['placements'] = 'secondary', ['body']
        kp.write_text(json.dumps({'keywords': kws}), encoding='utf-8')
        code, out = run(tmp, 'map')
        check('a README-only primary with no repo in the results is refused', code == 1 and 'no repository or GitHub topic page' in out, out)
        kws[0]['serp_note'] = 'the site of the project ranks for it; the README links there'
        kp.write_text(json.dumps({'keywords': kws}), encoding='utf-8')
        code, out = run(tmp, 'map')
        check('valid map passes', code == 0, out)

        code, out = run(tmp, 'audit', '--save', 'baseline')
        check('baseline audits the originals', code == 0 and 'originals' in out, out)

        write(tmp / 'README.md', README.replace('# Widget', '# Widget: a github readme banner maker').replace(
            'A tool for widgets.', 'Make a github readme banner for your project.'))
        code, out = run(tmp, 'audit', '--save', 'pre-quiron')
        check('audit passes after edits', code == 0, out)
        code, out = run(tmp, 'quiron', 'record', '--status', 'used', '--result', 'x')
        check('Quirón "used" with no text change is refused', code == 2 and 'byte-identical' in out, out)

        # A humanizer that drops the phrase from the lead and renames the linked heading.
        write(tmp / 'README.md', README.replace('# Widget', '# Widget: a github readme banner maker').replace(
            'A tool for widgets.', 'Make a header image for your project.').replace('## Install', '## Setup'))
        run(tmp, 'audit', '--save', 'final')
        code, out = run(tmp, 'compare', 'pre-quiron', 'final')
        check('compare catches a lost placement', code == 1 and 'lead' in out, out)
        check('compare catches a broken internal anchor', '#install' in out, out)
        run(tmp, 'quiron', 'record', '--status', 'used', '--result', '14/23 in band')
        code, out = run(tmp, 'report')
        check('report refuses while a placement is lost', code == 1 and 'lost after the pre-quiron' in out, out)
        code, out = run(tmp, 'audit', '--save', 'pre-quiron')
        check('pre-quiron cannot be retaken after Quirón', code == 1 and 'cannot be taken again' in out, out)

        edited = [k for k in kws if k['phrase'] != 'github readme banner'] + [dict(kws[0], placements=['title', 'h1'])]
        kp.write_text(json.dumps({'keywords': edited}), encoding='utf-8')
        code, out = run(tmp, 'audit', '--save', 'final')
        check('editing the map after pre-quiron is refused', code == 1 and 'changed after the pre-quiron' in out, out)
        kp.write_text(json.dumps({'keywords': kws}), encoding='utf-8')

        write(tmp / 'README.md', README.replace('# Widget', '# Widget: a github readme banner maker').replace(
            'A tool for widgets.', 'Make a github readme banner for your project, 3x faster than by hand.'))
        code, out = run(tmp, 'audit', '--save', 'final')
        check('audit lists a new claim', "new claims to check" in out and "'3x'" in out, out)
        run(tmp, 'pending', 'merge the PR')
        code, out = run(tmp, 'report')
        check('report refuses an unchecked new claim', code == 1 and 'not checked against a source' in out, out)
        write(tmp / 'docs' / 'bench.md', 'Drawing by hand: 30 s. Widget: 10 s.')
        code, out = run(tmp, 'claims', 'verify', '--claim', '3x', '--source', 'docs/bench.md')
        check('a source that does not state the number is refused', code == 2 and 'does not contain 3' in out, out)
        write(tmp / 'docs' / 'bench.md', 'Widget is 3x faster than drawing by hand (30 s vs 10 s).')
        code, out = run(tmp, 'claims', 'verify', '--claim', '3x', '--source', 'docs/bench.md')
        check('a claim checked against a file that states it', code == 0, out)
        code, out = run(tmp, 'claims', 'verify', '--claim', '2020', '--source', 'docs/bench.md')
        check('only new claims can be verified', code == 2 and 'not a new claim' in out, out)
        code, out = run(tmp, 'report')
        check('report renders when every check passes', code == 0 and 'Eco · keyword report' in out and '0 placements lost' in out, out)
        check('report shows what changed', 'h1: "Widget" → "Widget: a github readme banner maker"' in out, out)
        check('report shows the GitHub rank', 'Current GitHub rank' in out and '#2' in out, out)
        check('report shows the search results and the checked claims',
              'Search results' in out and '3x (checked against docs/bench.md)' in out, out)
        check('report saved', (tmp / '.eco' / 'readme' / 'report.md').exists())
        check('report says what the files prove', 'In the files: 0 → ' in out and 'researched phrases are in the text' in out, out)
        check('report compares with the pages that rank',
              'Against the 3 competitor pages read: 3 carry "github readme banner" [en] in the title or H1; yours does now' in out, out)
        check('with nothing measured after publishing, the report only says so',
              'On the published README: not checked.' in out and '| Where |' not in out, out)
        page_html = (tmp / '.eco' / 'readme' / 'report.html').read_text(encoding='utf-8')
        m = re.search(r'Verification:\*\* primary \+ secondary placements (\d+)/(\d+)', out)
        check('report.html carries the same verification as report.md',
              m is not None and f'<div class="big">{m.group(1)}/{m.group(2)}</div>' in page_html, out)
        check('report.html is English by default and self-contained', '<html lang="en">' in page_html
              and 'Checked by a script' in page_html and 'http' not in page_html.split('</style>')[0], page_html[:300])
        check('report.html has one script and escapes file text', page_html.count('<script>') == 1, page_html[-400:])
        code, out = run(tmp, 'report', '--lang', 'es')
        es_html = (tmp / '.eco' / 'readme' / 'report.html').read_text(encoding='utf-8')
        check('report --lang es writes the page in Spanish', code == 0 and '<html lang="es">' in es_html
              and 'Comprobado por un script' in es_html and 'Eco · keyword report' in out, out)
        code, out = run(tmp, 'report', '--lang', 'fr')
        check('a language with no labels asks for a --labels file', code == 2 and 'eco.py labels' in out, out)
        code, out = run(tmp, 'labels')
        labels = json.loads(out)
        write(tmp / 'fr.json', json.dumps({k: v for k, v in labels.items() if k != 'title'}))
        code, out = run(tmp, 'report', '--lang', 'fr', '--labels', 'fr.json')
        check('a labels file missing a key is refused', code == 2 and 'title' in out, out)
        write(tmp / 'fr.json', json.dumps(dict(labels, places_n='plusieurs endroits')))
        code, out = run(tmp, 'report', '--lang', 'fr', '--labels', 'fr.json')
        check('a labels file that drops a placeholder is refused', code == 2 and 'places_n' in out, out)
        write(tmp / 'fr.json', json.dumps(dict(labels, verified='Vérifié par un script')))
        code, out = run(tmp, 'report', '--lang', 'fr', '--labels', 'fr.json')
        fr_html = (tmp / '.eco' / 'readme' / 'report.html').read_text(encoding='utf-8')
        check('an agent-translated labels file is used', code == 0 and 'Vérifié par un script' in fr_html
              and '<html lang="fr">' in fr_html, out)
        srv = eco.report_server(tmp / '.eco' / 'readme')
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            port = srv.server_address[1]
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/report.html', timeout=10) as resp:
                served = resp.read().decode('utf-8')
            check('serve hands report.html over on localhost', srv.server_address[0] == '127.0.0.1' and 'Vérifié' in served)
        finally:
            srv.shutdown()
            srv.server_close()
        # After publishing: the same searches again, compared with what the research saved.
        check('report.html says it was not checked on GitHub', 'We could not check it on GitHub.' in page_html, page_html[-600:])
        code, out = run(tmp, 'track', 'urls')
        check('track urls repeats the searches of the research', code == 0 and 'github/readme-banner.json  https://api.github.com/' in out
              and 'github/github-banner.json  #' in out and 'serp/en-github-readme-banner.html  https://html.duckduckgo.com' in out, out)
        code, out = run(tmp, 'track', 'parse')
        check('track parse needs the fetched results', code == 2 and 'no results fetched' in out, out)
        today = datetime.date.today()
        tdir = tmp / '.eco' / 'readme' / 'raw' / 'track' / today.isoformat()
        other = {'full_name': 'x/readme-banner', 'description': 'd', 'topics': []}
        write(tdir / 'github' / 'readme-banner.json', json.dumps({'total_count': 130, 'items': [{'full_name': 'me/widget'}, other]}))
        write(tdir / 'github' / 'github-banner.json', json.dumps({'total_count': 120, 'items': [other, {'full_name': 'me/widget'}]}))
        write(tdir / 'serp' / 'en-github-readme-banner.json', json.dumps({'results': [
            {'url': u} for u in pages[:2] + ['https://github.com/me/widget'] + pages[2:8]]}))
        saved_fetch = eco.fetch_page
        repo_api = {'description': 'w', 'topics': []}
        current = lambda url: json.dumps(repo_api) if 'api.github.com' in url else (tmp / 'README.md').read_text(encoding='utf-8')  # noqa: E731
        try:
            eco.fetch_page = lambda url: README
            code, out = run(tmp, 'track', 'parse')
            check('track refuses while GitHub still shows the old README', code == 1 and 'still shows another text' in out
                  and not (tmp / '.eco' / 'readme' / 'track.json').exists(), out)
            eco.fetch_page = current
            code, out = run(tmp, 'track', 'parse', '--published', '2001-01-01')
            check('the publishing date cannot be before the edits', code == 2 and 'went public between' in out, out)
            code, out = run(tmp, 'track', 'parse')
            check('GitHub search is not measured when nothing it reads was changed', code == 0 and 'proposed no About or topics' in out
                  and '| GitHub search |' not in out and '| DuckDuckGo |' in out, out)
            run(tmp, 'offsite', '--about', 'Make a github readme banner', '--topics', 'readme,readme-banner')
            code, out = run(tmp, 'track', 'parse')
            check('nor while the proposed About is not on github.com', code == 0 and 'About on github.com is not the proposed one' in out
                  and '| GitHub search |' not in out, out)
            repo_api.update(description='Make a github readme banner', topics=['readme', 'readme-banner', 'svg'])
            code, out = run(tmp, 'track', 'parse')
            check('track compares each search before and after', code == 0 and '| GitHub search | readme-banner | #2 | #1 | improved |' in out
                  and '| DuckDuckGo | github readme banner [en] | not in the first 9 | #3 | improved: now in the results |' in out, out)
            check('an unchanged position on the first day is too early to call',
                  '| GitHub search | github-banner | #2 | #2 | too early to tell |' in out and '2 improved, 0 no change, 0 worse, 1 not known yet' in out, out)
            check('track says the cause is not proven', 'is not proven' in out, out)
            stp = tmp / '.eco' / 'readme' / 'state.json'
            sj = json.loads(stp.read_text(encoding='utf-8'))
            sj['steps']['audit-final']['at'] = (today - datetime.timedelta(days=20)).isoformat() + 'T10:00:00'
            stp.write_text(json.dumps(sj), encoding='utf-8')
            code, out = run(tmp, 'track', 'parse', '--published', (today - datetime.timedelta(days=10)).isoformat())
            check('once the index has had time, an unchanged position is no change',
                  code == 0 and '| GitHub search | github-banner | #2 | #2 | no change |' in out and '2 improved, 1 no change' in out, out)
        finally:
            eco.fetch_page = saved_fetch
        code, out = run(tmp, 'report')
        tracked_html = (tmp / '.eco' / 'readme' / 'report.html').read_text(encoding='utf-8')
        check('the report carries the measured positions', code == 0 and 'On the published README (public since' in out
              and '| GitHub search | readme-banner | #2 | #1 | improved |' in out, out)
        check('report.html shows the positions in plain words', 'Improved: now it shows up' in tracked_html
              and 'We could not check it on GitHub.' not in tracked_html and 'position 1' in tracked_html, tracked_html[-600:])
        code, out = run(tmp, 'gsc', 'q.csv', '--stage', 'before', '--period', '2020-01-01..2020-01-28')
        check('Search Console is for a site, not a README', code == 2 and 'only --mode site' in out, out)
        code, out = run(tmp, 'status')
        check('status says whether track ran', 'after publishing: track done' in out, out)

        write(tmp / 'README.md', README.replace('# Widget', '# Widget: a github readme banner maker!'))
        code, out = run(tmp, 'report')
        check('report refuses files changed after the final audit', code == 1 and 'changed after' in out, out)

        code, out = run(tmp, 'quiron', 'record', '--status', 'declined')
        check('Quirón has no "declined" status: Eco never offers an install', code == 2, out)
        code, out = run(tmp, 'offsite', '--about', 'x' * 400, '--topics', 'Bad Topic')
        check('offsite validates About length and topic format', code == 1 and '350' in out and 'lowercase' in out, out)

        stuffed = README.replace('A tool for widgets.', 'github readme banner ' * 20 +
                                 '\n\nWidget, a github readme banner. Widget is a readme header generator. Widget: a github readme banner tool.')
        write(tmp / 'README.md', stuffed)
        code, out = run(tmp, 'audit')
        check('stuffing is flagged', 'stuffing' in out, out)
        check('repeated "<Name> is a <keyword>" is flagged', 'sentences of the form' in out, out)
        code, out = run(tmp, 'status')
        check('status lists steps', 'audit-final' in out and 'github' in out and 'lighthouse' not in out, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- the site skill: its own folder, the build files around the pages, Lighthouse
    tmp = Path(tempfile.mkdtemp(prefix='eco-site-'))
    try:
        page = HTML.replace('<title>Widget</title>', '<title>Widget · GitHub README banner for any repo</title>'
                            '<link rel="canonical" href="https://widget.dev/"><meta property="og:image" content="https://widget.dev/og.png">')
        write(tmp / 'README.md', README)
        write(tmp / 'dist' / 'index.html', page)
        write(tmp / 'dist' / 'es' / 'index.html', page.replace('lang="en"', 'lang="es"'))
        code, out = run(tmp, 'init', '--lang', 'en', '--surface', 'README.md:en', mode='site')
        check('the site skill refuses a README', code == 2 and 'readme skill' in out, out)
        code, out = run(tmp, 'init', '--lang', 'en,es', '--surface', 'dist/index.html:en', '--surface', 'dist/es/index.html:es', mode='site')
        check('site init', code == 0 and (tmp / '.eco' / 'site' / 'brief.json').exists(), out)
        sp = tmp / '.eco' / 'site' / 'brief.json'
        sb = json.loads(sp.read_text(encoding='utf-8'))
        check('a site brief has no GitHub block', 'github' not in sb and 'build_dir' in sb, str(sb))
        sb['project'] = {'name': 'Widget', 'what': 'Draws README banners.', 'problem': 'READMEs look bare.'}
        sb['audience'] = {'primary': 'Maintainers', 'niche': False, 'adjacent': [], 'how_they_search': 'readme banner'}
        sb['read'] = ['README.md', 'src/']
        sb['site_url'] = 'https://widget.dev'
        sp.write_text(json.dumps(sb), encoding='utf-8')
        code, out = run(tmp, 'brief', mode='site')
        check('a site brief needs build_dir', code == 1 and 'build_dir' in out, out)
        sb['build_dir'] = 'dist'
        sp.write_text(json.dumps(sb), encoding='utf-8')
        code, out = run(tmp, 'brief', mode='site')
        check('site brief passes', code == 0, out)
        check('the two skills keep separate runs', (tmp / '.eco' / 'site' / 'original' / 'dist' / 'index.html').exists()
              and not (tmp / '.eco' / 'readme').exists())

        code, out = run(tmp, 'audit', mode='site')
        check('no robots.txt is flagged', 'no robots.txt in dist' in out and 'no sitemap in dist' in out, out)
        check('a missing llms.txt is a note, not a flag', 'NOTE no llms.txt' in out and 'FLAG no llms.txt' not in out, out)
        write(tmp / 'dist' / 'robots.txt', 'User-agent: *\nAllow: /\n\nUser-agent: OAI-SearchBot\nUser-agent: GPTBot\nDisallow: /\n')
        write(tmp / 'dist' / 'sitemap.xml', '<?xml version="1.0"?><urlset><url><loc>https://widget.dev/</loc></url></urlset>')
        write(tmp / 'dist' / 'llms.txt', 'Widget\n\nNo links here.\n')
        code, out = run(tmp, 'audit', mode='site')
        check('a blocked AI search bot is flagged', 'blocks OAI-SearchBot' in out, out)
        check('a blocked training bot is only noted', 'FLAG robots.txt blocks GPTBot' not in out and 'training crawlers (GPTBot)' in out, out)
        check('robots.txt without Sitemap is flagged', 'no Sitemap: line' in out, out)
        check('a page missing from the sitemap is flagged', 'does not list https://widget.dev/es/' in out, out)
        check('llms.txt format is checked', 'H1 (# Name)' in out and 'links no page' in out, out)
        sb['ai_crawlers_blocked'] = ['OAI-SearchBot']
        sp.write_text(json.dumps(sb), encoding='utf-8')
        write(tmp / 'dist' / 'robots.txt', 'User-agent: *\nAllow: /\n\nUser-agent: OAI-SearchBot\nUser-agent: GPTBot\nDisallow: /\n\n'
              'Sitemap: https://widget.dev/sitemap-index.xml\n')
        write(tmp / 'dist' / 'sitemap-index.xml', '<sitemapindex><sitemap><loc>https://widget.dev/sitemap-0.xml</loc></sitemap></sitemapindex>')
        write(tmp / 'dist' / 'sitemap-0.xml', '<urlset><url><loc>https://widget.dev/</loc></url><url><loc>https://widget.dev/es/</loc></url></urlset>')
        write(tmp / 'dist' / 'llms.txt', '# Widget\n\n> Banners for READMEs.\n\n- [Docs](https://widget.dev/docs/): how to use it\n')
        code, out = run(tmp, 'audit', mode='site')
        check('site files pass: deliberate block, sitemap index, valid llms.txt',
              not [l for l in out.splitlines() if 'FLAG' in l and any(x in l for x in ('robots', 'sitemap', 'llms'))]
              and 'training crawlers (GPTBot)' in out, out)

        lh = tmp / '.unlighthouse'

        def lh_run(paths, audits, lcp=1200.0):
            """A fake Unlighthouse run: audits is {path: [(id, category, score, weight)]}."""
            routes = []
            for path in paths:
                cats = {c: {'score': min([s for i, c2, s, w in audits.get(path, []) if c2 == c and w > 0] + [1])}
                        for c in eco.LH_CATEGORIES}
                routes.append({'path': path, 'categories': cats,
                               'metrics': {'largest-contentful-paint': {'numericValue': lcp}, 'total-blocking-time': {'numericValue': 50}}})
                rep = {'categories': {c: {'auditRefs': [{'id': i, 'weight': w} for i, c2, s, w in audits.get(path, []) if c2 == c]}
                                      for c in eco.LH_CATEGORIES},
                       'audits': {i: {'score': s, 'scoreDisplayMode': 'binary' if w else 'metricSavings', 'title': i.replace('-', ' ')}
                                  for i, c2, s, w in audits.get(path, [])}}
                write(lh / 'reports' / path.strip('/') / 'lighthouse.json', json.dumps(rep))
            avg = {c: {'averageScore': sum(r['categories'][c]['score'] for r in routes) / len(routes)} for c in eco.LH_CATEGORIES}
            write(lh / 'ci-result.json', json.dumps({'summary': {'categories': avg}, 'routes': routes}))

        code, out = run(tmp, 'lighthouse', '--stage', 'baseline', '--url', 'http://localhost:4321', mode='site')
        check('lighthouse without a run says how to run it', code == 2 and 'Unlighthouse' in out, out)
        lh_run(['/', '/es/'], {'/': [('color-contrast', 'accessibility', 0, 7), ('is-on-https', 'best-practices', 0, 5)]}, lcp=3200.0)
        code, out = run(tmp, 'lighthouse', '--stage', 'baseline', '--url', 'http://localhost:4321', mode='site')
        check('a local baseline of the untouched build is recorded', code == 0 and 'local build' in out and 'OPEN' in out, out)
        check('slow lab LCP is a warning', 'lab LCP 3.2 s' in out and 'WARN' in out, out)

        # The site report: research and map gates stubbed, everything after them real.
        saved = eco.check_research, eco.check_map, eco.fetch_page
        eco.check_research, eco.check_map = (lambda a: []), (lambda a: ([], {}))
        try:
            write(tmp / '.eco' / 'site' / 'keywords.json', json.dumps({'keywords': []}))
            alt = ('<link rel="alternate" hreflang="en" href="https://widget.dev/">'
                   '<link rel="alternate" hreflang="es" href="https://widget.dev/es/">')
            final_page = page.replace('content="Widget."', 'content="Widget draws a banner for your GitHub README that shows '
                                      'what the project does, ready to paste."').replace('</title>', '</title>' + alt)
            write(tmp / 'dist' / 'index.html', final_page)
            write(tmp / 'dist' / 'es' / 'index.html', final_page.replace('<html lang="en"', '<html lang="es"'))
            code, out = run(tmp, 'lighthouse', '--stage', 'baseline', '--url', 'http://localhost:4321', mode='site')
            check('a local baseline after edits is refused', code == 2 and 'before any edit' in out, out)
            eco.fetch_page = lambda url: page if url.endswith('/') and not url.endswith('/es/') else page.replace('<html lang="en"', '<html lang="es"')
            code, out = run(tmp, 'lighthouse', '--stage', 'baseline', '--url', 'https://widget.dev', mode='site')
            check('a production baseline is recorded', code == 0 and 'production' in out, out)
            code, out = run(tmp, 'audit', '--save', 'pre-quiron', mode='site')
            check('site pages pass the audit', code == 0, out)
            run(tmp, 'quiron', 'record', '--status', 'not-installed', mode='site')
            run(tmp, 'audit', '--save', 'final', mode='site')
            code, out = run(tmp, 'lighthouse', '--stage', 'final', '--url', 'https://widget.dev', mode='site')
            check('a final scan of production that lacks the edits is refused', code == 1 and 'does not serve the final pages' in out, out)
            code, out = run(tmp, 'report', mode='site')
            check('the site report needs a final Lighthouse run', code == 1 and 'no final Lighthouse run' in out, out)

            lh_run(['/'], {})
            code, out = run(tmp, 'lighthouse', '--stage', 'final', '--url', 'http://localhost:4321', mode='site')
            check('a page Unlighthouse did not scan is flagged', code == 1 and 'did not scan /es' in out, out)
            lh_run(['/', '/es/'], {'/': [('color-contrast', 'accessibility', 0, 7), ('is-on-https', 'best-practices', 0, 5),
                                         ('unused-javascript', 'performance', 0.5, 0)],
                                   '/es/': [('largest-contentful-paint', 'performance', 0.96, 25)]}, lcp=2600.0)
            code, out = run(tmp, 'lighthouse', '--stage', 'final', '--url', 'http://localhost:4321', mode='site')
            check('every weighted audit under 1 is open', code == 1 and '2 open audits' in out and 'color-contrast' in out
                  and 'largest-contentful-paint' in out, out)
            check('https is left to production on a local scan', 'local only' in out and 'is-on-https' in out, out)
            check('weight-0 diagnostics are hints', 'hint' in out and 'unused-javascript' in out, out)
            run(tmp, 'lighthouse', 'waive', '--audit', 'color-contrast', '--kind', 'declined',
                '--reason', 'the user keeps the brand grey on the hero', mode='site')
            code, out = run(tmp, 'lighthouse', '--stage', 'final', '--url', 'http://localhost:4321', mode='site')
            check('a declined change no longer blocks', code == 1 and '1 open audits' in out and 'waived: declined' in out, out)
            run(tmp, 'lighthouse', 'waive', '--audit', 'largest-contentful-paint', '--path', '/es/', '--kind', 'ceiling',
                '--reason', 'lab LCP varies 2.4-2.6 s across runs with nothing left to defer', mode='site')
            code, out = run(tmp, 'lighthouse', '--stage', 'final', '--url', 'http://localhost:4321', mode='site')
            rec = json.loads((tmp / '.eco' / 'site' / 'lighthouse-final.json').read_text(encoding='utf-8'))
            check('final passes when every audit is fixed or waived', code == 0 and set(rec['surfaces']) == {'dist/index.html', 'dist/es/index.html'}, out)

            code, out = run(tmp, 'report', mode='site')
            check('the site report shows Lighthouse before and after', code == 0 and 'before: production, after: local build' in out
                  and 'accessibility' in out and '→' in out, out)
            check('the report quotes each waiver', 'color-contrast (declined): the user keeps the brand grey' in out
                  and 'largest-contentful-paint on /es/ (ceiling)' in out, out)
            check('site notes go to Pending', 'training crawlers' in out.split('**Pending:**')[1], out)
            check('the site report says Quirón was not installed', 'Quirón not installed' in out, out)
            site_html = (tmp / '.eco' / 'site' / 'report.html').read_text(encoding='utf-8')
            check('a site not measured after publishing only says so', 'On the published site: not checked.' in out
                  and 'We could not check it on your published site.' in site_html, out)
            check('the site report.html shows Lighthouse', 'How fast and accessible it is' in site_html
                  and 'Accessibility' in site_html and 'color-contrast' in site_html, site_html[-2000:])

            eco.fetch_page = lambda url: final_page if not url.endswith('/es/') else final_page.replace('<html lang="en"', '<html lang="es"')
            code, out = run(tmp, 'lighthouse', '--stage', 'final', '--url', 'https://widget.dev', mode='site')
            check('on production, https is a real failure', code == 1 and 'OPEN' in out and 'is-on-https' in out, out)
            lh_run(['/', '/es/'], {})
            code, out = run(tmp, 'lighthouse', '--stage', 'final', '--url', 'https://widget.dev', mode='site')
            check('a final scan of production that serves the edits is accepted', code == 0 and 'production' in out, out)

            write(tmp / 'dist' / 'index.html', final_page.replace('<p>Hello.</p>', '<p>Hello there.</p>'))
            run(tmp, 'audit', '--save', 'final', mode='site')
            code, out = run(tmp, 'report', mode='site')
            check('a page changed after Lighthouse needs a new scan', code == 1 and 'changed after the final Lighthouse run' in out, out)
            # Search Console: one export from before publishing, one from after.
            code, out = run(tmp, 'track', 'urls', mode='site')
            check('with no saved search there is no "before" to track', code == 2 and 'no "before"' in out, out)
            kwp = tmp / '.eco' / 'site' / 'keywords.json'
            kwp.write_text(json.dumps({'keywords': [{'phrase': p_, 'lang': 'en', 'tier': 'primary'} for p_ in
                                                    ('readme banner', 'banner maker', 'svg banner')]}), encoding='utf-8')
            day = datetime.date.today()
            ago = lambda n: (day - datetime.timedelta(days=n)).isoformat()  # noqa: E731
            head = 'Top queries,Clicks,Impressions,CTR,Position\n'
            write(tmp / 'before.csv', head + 'readme banner,10,200,5%,14.2\nbanner maker,0,3,0%,40\nsvg banner,1,60,1.6%,8\n')
            write(tmp / 'after.csv', head + 'readme banner,25,300,8.3%,9.1\nbanner maker,4,50,8%,12.5\nsvg banner,0,4,0%,9\n')
            write(tmp / 'pages.csv', 'Top pages,Clicks,Impressions,CTR,Position\nhttps://widget.dev/,10,200,5%,14.2\n')
            code, out = run(tmp, 'gsc', 'before.csv', '--stage', 'before', '--period', 'last month', mode='site')
            check('a Search Console export needs its dates', code == 2 and 'START..END' in out, out)
            code, out = run(tmp, 'gsc', 'pages.csv', '--stage', 'before', '--period', f'{ago(30)}..{ago(2)}', mode='site')
            check('the Pages file of the export is refused', code == 2 and 'Pages file' in out, out)
            code, out = run(tmp, 'gsc', 'before.csv', '--stage', 'before', '--period', f'{ago(30)}..{ago(2)}', mode='site')
            check('the period before publishing is recorded', code == 0 and '3 of them phrases' in out and 'now the after period' in out, out)
            code, out = run(tmp, 'gsc', 'after.csv', '--stage', 'after', '--period', f'{ago(9)}..{ago(1)}', mode='site')
            check('a period that starts before the edits is not an "after"', code == 2 and 'before the changes could be public' in out, out)
            code, out = run(tmp, 'gsc', 'after.csv', '--stage', 'after', '--period', f'{ago(0)}..{ago(0)}', mode='site')
            check('Search Console positions are compared phrase by phrase', code == 0
                  and '| Google (Search Console) | readme banner [en] | average position 14.2 (200 impressions, 10 clicks) | '
                      'average position 9.1 (300 impressions, 25 clicks) | improved |' in out, out)
            check('too few impressions is not a result, in either direction',
                  '| improved: now in the results |' in out and '| not enough data |' in out and '2 improved, 0 no change, 0 worse, 1 not known yet' in out, out)
            kwp.write_text(json.dumps({'keywords': []}), encoding='utf-8')
            for f in ('gsc.json', 'track.md'):
                (tmp / '.eco' / 'site' / f).unlink()
        finally:
            eco.check_research, eco.check_map, eco.fetch_page = saved

        write(tmp / 'dist' / 'index.html', page.replace('<link rel="canonical" href="https://widget.dev/">', '<link rel="canonical" href="https://old.example/">'))
        code, out = run(tmp, 'audit', mode='site')
        check('canonical host is checked against site_url', 'points to old.example' in out, out)
        code, out = run(tmp, 'status', mode='site')
        check('site status has lighthouse, not github', 'lighthouse' in out and 'github' not in out, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print('all passed' if not FAILS else f'{len(FAILS)} failed: ' + ', '.join(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
