#!/usr/bin/env python3
"""Tests for skills/eco/scripts/eco.py. Run: python tests/run.py"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'skills' / 'eco' / 'scripts'))
import eco  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = '') -> None:
    print(('ok    ' if cond else 'FAIL  ') + name + (f'  ({detail[:1500]})' if detail and not cond else ''))
    if not cond:
        FAILS.append(name)


def run(root: Path, *argv) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            eco.main(['--root', str(root), *argv])
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

    # --- a full run in a temp project
    tmp = Path(tempfile.mkdtemp(prefix='eco-test-'))
    try:
        code, out = run(tmp / 'nope', 'status')
        check('missing root is a clean error', code == 2 and 'does not exist' in out, out)
        write(tmp / 'README.md', README)
        write(tmp / 'dist' / 'index.html', HTML)
        code, out = run(tmp, 'init', '--lang', 'en', '--surface', 'README.md:en', '--surface', 'dist/index.html:en', '--repo', 'me/widget')
        check('init', code == 0, out)
        code, out = run(tmp, 'brief')
        check('empty brief fails', code == 1 and 'project.name' in out, out)
        bp = tmp / '.eco' / 'brief.json'
        b = json.loads(bp.read_text(encoding='utf-8'))
        b['project'] = {'name': 'Widget', 'what': 'Draws README banners.', 'problem': 'READMEs look bare.'}
        b['audience'] = {'primary': 'Open source maintainers', 'niche': True, 'adjacent': ['readme gif makers'],
                         'how_they_search': 'github readme banner'}
        b['read'] = ['README.md', 'src/']
        b['site_url'] = 'https://widget.dev'
        bp.write_text(json.dumps(b), encoding='utf-8')
        code, out = run(tmp, 'brief')
        check('niche without 2 adjacent audiences fails', code == 1 and 'adjacent' in out, out)
        b['audience']['adjacent'].append('banner template users')
        bp.write_text(json.dumps(b), encoding='utf-8')
        code, out = run(tmp, 'brief')
        check('complete brief passes and keeps originals', code == 0 and (tmp / '.eco' / 'original' / 'README.md').exists(), out)

        check('research gate fails with nothing fetched', run(tmp, 'research')[0] == 1)
        fams = {'result': ['readme banner', 'github banner'], 'problem': ['readme header'], 'alternative': ['readme gif'],
                'category': ['readme generator'], 'platform': ['github project banner'], 'adjacent': ['gif maker', 'banner template']}
        for fam, seeds in fams.items():
            run(tmp, 'suggest', 'urls', '--lang', 'en', '--family', fam, *sum((['--seed', s] for s in seeds), []))
        plan = json.loads((tmp / '.eco' / 'suggest-plan.json').read_text(encoding='utf-8'))
        check('question words only on problem and result seeds', not any(q['q'].startswith('how to readme gif') for q in plan['queries'])
              and any(q['q'] == 'how to readme banner' for q in plan['queries']))
        blob = '\n'.join(payload(q['q'], [q['q'] + ' generator', q['q'] + ' github readme banner']) for q in plan['queries'])
        blob += '\n' + payload('not planned at all', ['x'])
        blob += '\n' + payload(plan['queries'][0]['q'], ['totally unrelated words'])
        blob += '\n' + payload(plan['queries'][-1]['q'], [])
        echo_q = plan['queries'][-2]['q']
        blob += '\n' + payload(echo_q, [echo_q])
        write(tmp / '.eco' / 'raw' / 'suggest' / 'en' / 'all.txt', blob)
        code, out = run(tmp, 'suggest', 'parse')
        sug = json.loads((tmp / '.eco' / 'suggest.json').read_text(encoding='utf-8'))
        check('the echo of the query is not a suggestion',
              not any(r['suggestions'] for r in sug['responses'].values() if r['q'] == echo_q))
        check('unplanned and off-topic responses are ignored', 'not in the plan' in out and 'off-topic' in out, out)

        for n in ('readme-banner', 'github-banner'):
            write(tmp / '.eco' / 'raw' / 'github' / f'{n}.json', json.dumps({'total_count': 120, 'items': [
                {'full_name': f'x/{n}', 'description': 'readme banner maker', 'topics': ['readme', 'svg'], 'stargazers_count': 3},
                {'full_name': 'me/widget', 'description': 'w', 'topics': []}]}))
        code, out = run(tmp, 'github', 'parse')
        check('github parse records our rank', 'me/widget: #2' in out, out)
        for n in range(3):
            write(tmp / '.eco' / 'raw' / 'competitors' / f'c{n}.html', f'<title>GitHub README banner generator {n}</title><h1>Animated README banner</h1><p>Make one.</p>')
        code, out = run(tmp, 'competitors')
        check('competitors: shared phrases', 'readme banner' in out and 'banner generator' in out, out)
        code, out = run(tmp, 'research')
        check('research gate passes', code == 0, out)

        kp = tmp / '.eco' / 'keywords.json'
        kws = [{'phrase': 'github readme banner', 'lang': 'en', 'tier': 'primary',
                'evidence': [{'source': 'suggest', 'detail': 'x'}], 'placements': ['title', 'h1', 'lead'], 'claim': 'true'},
               {'phrase': 'invented phrase nobody types', 'lang': 'en', 'tier': 'secondary',
                'evidence': [{'source': 'suggest'}], 'placements': ['body']},
               {'phrase': 'readme banner', 'lang': 'en', 'tier': 'secondary', 'variants': ['past cloudflare'],
                'evidence': [{'source': 'competitor'}], 'placements': ['body']}]
        kp.write_text(json.dumps({'keywords': kws}), encoding='utf-8')
        code, out = run(tmp, 'map')
        check('evidence is checked against the research', code == 1 and 'phrase is not in .eco/suggest' in out, out)
        check('a variant must be the same words', "variant 'past cloudflare'" in out, out)
        check('map needs enough phrases and discarded ones', 'at least 10' in out and 'discarded' in out, out)
        kp.write_text(json.dumps({'keywords': [
            {'phrase': plan['queries'][-1]['q'], 'lang': 'en', 'tier': 'secondary', 'evidence': [{'source': 'suggest'}], 'placements': ['body']},
            {'phrase': 'animated readme banner', 'lang': 'en', 'tier': 'primary', 'evidence': [{'source': 'competitor'}], 'placements': ['h1', 'title']}]}),
            encoding='utf-8')
        code, out = run(tmp, 'map')
        check('a planned query is not evidence; only suggestions are', repr(plan['queries'][-1]['q']) in out and 'not in .eco/suggest' in out, out)
        check('a primary needs demand evidence, not only competitors', 'demand evidence' in out, out)
        kws[1] = {'phrase': 'readme header generator', 'lang': 'en', 'tier': 'secondary', 'evidence': [{'source': 'suggest'}], 'placements': ['meta']}
        kws[2] = {'phrase': 'readme banners', 'lang': 'en', 'tier': 'secondary', 'variants': ['readme banner'],
                  'evidence': [{'source': 'competitor'}], 'placements': ['body']}
        for q in [q for q in plan['queries'] if q['q'] + ' generator' != 'readme header generator'][:12]:
            kws.append({'phrase': q['q'] + ' generator', 'lang': 'en', 'tier': 'long-tail', 'evidence': [{'source': 'suggest'}], 'placements': ['body']})
        kws += [{'phrase': f'dropped {i}', 'lang': 'en', 'tier': 'discarded', 'reason': 'no suggestions'} for i in range(3)]
        kp.write_text(json.dumps({'keywords': kws}), encoding='utf-8')
        code, out = run(tmp, 'map')
        check('valid map passes', code == 0, out)

        code, out = run(tmp, 'audit', '--save', 'baseline')
        check('baseline audits the originals', code == 0 and 'originals' in out, out)

        write(tmp / 'README.md', README.replace('# Widget', '# Widget: a github readme banner maker').replace(
            'A tool for widgets.', 'Make a github readme banner for your project.'))
        write(tmp / 'dist' / 'index.html', HTML.replace('<title>Widget</title>', '<title>Widget · GitHub README banner for any repo</title>').replace(
            'content="Widget."', 'content="Widget is a readme header generator for GitHub: it draws a banner that shows what your project does."').replace(
            '<h1>Widget</h1>', '<h1>Your github readme banner</h1>').replace(
            '</title>', '</title><link rel="canonical" href="https://widget.dev/">').replace(
            '<p>Hello.</p>', '<p>Make a github readme banner.</p>'))
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
            'A tool for widgets.', 'Make a github readme banner for your project.'))
        run(tmp, 'audit', '--save', 'final')
        run(tmp, 'pending', 'merge the PR')
        code, out = run(tmp, 'report', '--lang', 'es')
        check('report renders when every check passes', code == 0 and 'Eco · informe de keywords' in out and '0 colocaciones perdidas' in out, out)
        check('report shows what changed', 'h1: "Widget" → "Widget: a github readme banner maker"' in out, out)
        check('report shows the GitHub rank', 'Posición actual en GitHub' in out and '#2' in out, out)
        check('report saved', (tmp / '.eco' / 'report.md').exists())
        write(tmp / 'README.md', README.replace('# Widget', '# Widget: a github readme banner maker!'))
        code, out = run(tmp, 'report')
        check('report refuses files changed after the final audit', code == 1 and 'changed after' in out, out)

        write(tmp / 'dist' / 'index.html', HTML.replace('<title>Widget</title>', '<title>Widget · GitHub README banner for any repo</title>'
              '<link rel="canonical" href="https://old.example/">'))
        code, out = run(tmp, 'audit')
        check('canonical host is checked against site_url', 'points to old.example' in out, out)
        code, out = run(tmp, 'offsite', '--about', 'x' * 400, '--topics', 'Bad Topic')
        check('offsite validates About length and topic format', code == 1 and '350' in out and 'lowercase' in out, out)

        stuffed = HTML.replace('<p>Hello.</p>', '<p>' + 'github readme banner ' * 20 + '</p>' +
                               '<p>Widget, a github readme banner. Widget is a readme header generator. Widget: a github readme banner tool.</p>')
        write(tmp / 'dist' / 'index.html', stuffed)
        code, out = run(tmp, 'audit')
        check('stuffing is flagged', 'stuffing' in out, out)
        check('repeated "<Name> is a <keyword>" is flagged', 'sentences of the form' in out, out)
        code, out = run(tmp, 'status')
        check('status lists steps', 'audit-final' in out, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print('all passed' if not FAILS else f'{len(FAILS)} failed: ' + ', '.join(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main()
