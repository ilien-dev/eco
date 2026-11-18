#!/usr/bin/env python3
"""eco: keyword research and placement checks for a README or a website.

Every step writes a JSON file under .eco/<mode>/ in the project (--mode readme or site), and `report` refuses to run
until the checks behind each step pass. Python 3.9+, standard library only.

Steps, in order (run `eco.py status` to see where a run stands):
  init          write .eco/brief.json, then fill it in
  brief         check the brief; keeps a copy of every surface as it is now (the baseline)
  suggest       list Google Suggest URLs to fetch, then parse what was fetched
  github        list GitHub search URLs to fetch, then parse what was fetched
  competitors   parse fetched competitor pages and READMEs
  research      check that the research is deep enough
  serp          list results pages to fetch for the primaries, then parse what was fetched
  map           check .eco/keywords.json against the research and the results pages
  audit         check each keyword in the places the map requires; --save a snapshot
  compare       what one snapshot has and another lost: placements, links, anchors, code
  claims        numbers, years and superlatives the new text adds; record the source of each
  quiron        detect Quirón, record whether it was used
  lighthouse    site only: read an Unlighthouse run of the final build
  offsite       record the GitHub About, topics and homepage, proposed or applied
  pending       record something left for the user
  report        the fixed summary, only when every check passes
  track         after publishing: repeat the saved searches and compare the project's position, before and after
  gsc           site only: read a Search Console export of the weeks before or after publishing
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime as _dt
import hashlib
import html as _html
import io
import json
import math
import os
import re
import shutil
import string
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

VERSION = '0.1.0'
ECO = '.eco'

# Research depth required before the map. Raise them for a bigger project; never lower
# them to get past the gate: a thin search is what this skill exists to prevent.
# The first language in the brief is the main one; the others get lower floors, since fewer
# people search in them and more queries come back empty.
MIN_SUGGEST_RESPONSES = (20, 10)    # non-empty responses: main language, each other language
MAX_PER_SEED = 8                    # responses one seed can contribute to that count
MIN_SUGGEST_SEEDS = (5, 3)          # fetched seeds
MIN_FAMILIES = (4, 3)               # of: problem, result, category, alternative, platform
MIN_COMPETITORS = 3
MIN_GITHUB_QUERIES = 2          # when a README is a surface
MIN_PHRASES = 10                # non-discarded phrases in the map
MIN_DISCARDED = 3
MAX_PRIMARY = 5                 # per language

TITLE_RANGE = (30, 60)
META_RANGE = (70, 160)
ABOUT_MAX = 350
TOPICS_MAX = 20
DENSITY_CAP = 0.03              # share of visible words taken by one phrase
HEADING_SHARE_CAP = 0.5         # share of headings that carry the same phrase
IS_A_CAP = 2                    # "<Name> is a <keyword>" sentences before it reads forced

HTML_PLACEMENTS = {'title', 'meta', 'h1', 'lead', 'h2', 'h3', 'alt', 'og', 'jsonld', 'body'}
README_PLACEMENTS = {'h1', 'lead', 'heading', 'alt', 'body'}
GITHUB_PLACEMENTS = {'about', 'topics'}
TIERS = ('primary', 'secondary', 'long-tail', 'discarded')
CHECKED_SOURCES = {'suggest', 'github', 'competitor'}
DEMAND_SOURCES = CHECKED_SOURCES | {'search-console', 'trends', 'user'}
FAMILIES = ('problem', 'result', 'category', 'alternative', 'platform', 'adjacent')

# Question words only make sense in front of a problem or a result ("how to make readme
# banner"); in front of a category or a product name they make queries nobody types.
QUESTION_WORDS = {
    'en': ['how to', 'best', 'free'], 'es': ['cómo', 'mejor', 'gratis'],
    'pt': ['como', 'melhor', 'grátis'], 'fr': ['comment', 'meilleur', 'gratuit'],
    'de': ['wie', 'beste', 'kostenlos'],
}
SUFFIXES = {
    'en': ['for', 'vs', 'alternative'], 'es': ['para', 'vs', 'alternativa'],
    'pt': ['para', 'vs', 'alternativa'], 'fr': ['pour', 'vs', 'alternative'],
    'de': ['für', 'vs', 'alternative'],
}
STOPWORDS = set('''a an the and or of to for in on with by is are be it its this that you your we our
from as at how what why can do does not no yes more learn use using get one all de la el los las
y o en con para por que un una es del se su sus lo al como más'''.split())


# ---------------------------------------------------------------- small helpers

def die(msg: str, code: int = 2) -> None:
    print(f'eco: {msg}', file=sys.stderr)
    sys.exit(code)


def root_dir(args) -> Path:
    r = Path(getattr(args, 'root', None) or os.getcwd()).resolve()
    if not r.is_dir():
        die(f'project root {r} does not exist')
    return r


MODES = ('readme', 'site')
MODE_KIND = {'readme': 'readme', 'site': 'html'}


def eco_dir(args, create=True) -> Path:
    """Each skill keeps its own run: .eco/readme/ or .eco/site/, so one never wipes the other."""
    d = root_dir(args) / ECO / args.mode
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def rel(args) -> str:
    return f'{ECO}/{args.mode}'


def load(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding='utf-8') as f:
        return json.load(f)


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def sha(data) -> str:
    if isinstance(data, Path):
        data = data.read_bytes() if data.exists() else b''
    elif isinstance(data, str):
        data = data.encode('utf-8')
    elif not isinstance(data, bytes):
        data = json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()[:16]


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


def norm(text: str) -> str:
    """Case-folded, NFC, typographic quotes and dashes made plain, whitespace collapsed."""
    t = unicodedata.normalize('NFC', _html.unescape(text or ''))
    t = t.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    t = t.replace('–', '-').replace('—', '-').replace(' ', ' ')
    return re.sub(r'\s+', ' ', t).strip().casefold()


def flat(text: str) -> str:
    """norm() plus punctuation inside phrases made into spaces: 'CLAUDE.md' == 'claude md',
    'self-hosted' == 'self hosted'. Used for matching, never for display."""
    t = norm(text)
    t = re.sub(r"(?<=\w)[.\-_/:'](?=\w)", ' ', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def _pattern(phrases) -> re.Pattern | None:
    ps = sorted({flat(p) for p in phrases if flat(p)}, key=len, reverse=True)
    if not ps:
        return None
    return re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(p) for p in ps) + r')(?!\w)')


def count_in(text: str, phrases) -> int:
    """Occurrences of any of the phrases, each position of the text counted once."""
    pat = _pattern(phrases if isinstance(phrases, (list, tuple, set)) else [phrases])
    return len(pat.findall(flat(text))) if pat else 0


def contains(haystack: str, phrase: str) -> int:
    return count_in(haystack, [phrase])


def words(text: str) -> list[str]:
    return flat(text).split()


def tokens(text: str) -> list[str]:
    """Words with a plural -s/-es dropped, for comparing a variant with its phrase."""
    out = []
    for w in words(text):
        if len(w) > 4 and w.endswith('es'):
            w = w[:-2]
        elif len(w) > 3 and w.endswith('s'):
            w = w[:-1]
        out.append(w)
    return out


def state(args) -> dict:
    st = load(eco_dir(args) / 'state.json', None) or {}
    st.setdefault('version', VERSION)
    st.setdefault('steps', {})
    st.setdefault('pending', [])
    st.setdefault('log', [])
    return st


def mark(args, step: str, **info) -> None:
    st = state(args)
    now = _dt.datetime.now().isoformat(timespec='seconds')
    st['steps'][step] = {'at': now, **info}
    st['log'].append({'at': now, 'step': step, **info})
    save(eco_dir(args) / 'state.json', st)


def ok(msg: str) -> None:
    print(f'OK    {msg}')


def bad(msg: str) -> None:
    print(f'FAIL  {msg}')


def warn(msg: str) -> None:
    print(f'WARN  {msg}')


def git(root: Path, *a) -> str | None:
    try:
        r = subprocess.run(['git', *a], cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace')
        return r.stdout.strip() if r.returncode == 0 else None
    except OSError:
        return None


# ---------------------------------------------------------------- init / brief

BRIEF_TEMPLATE = {
    'project': {'name': '', 'what': '', 'problem': ''},
    'audience': {'primary': '', 'niche': False, 'adjacent': [], 'how_they_search': ''},
    'languages': [],
    'surfaces': [],
    'read': [],
    'github': {'repo': None, 'about_file': None},
    'site_url': None,
    'build_dir': None,
    'ai_crawlers_blocked': [],
    'rules': [],
}


def cmd_init(args):
    d = eco_dir(args)
    p = d / 'brief.json'
    if p.exists() and not args.force:
        die(f'{p} exists; pass --force to start over')
    if args.force:
        shutil.rmtree(d / 'original', ignore_errors=True)
        for f in list(d.glob('audit-*.json')) + [d / 'state.json']:
            if f.exists():
                f.unlink()
    brief = json.loads(json.dumps(BRIEF_TEMPLATE))
    brief['languages'] = [l.strip() for l in args.lang.split(',') if l.strip()]
    if args.mode == 'readme':
        for k in ('site_url', 'build_dir', 'ai_crawlers_blocked'):
            brief.pop(k)
    else:
        brief.pop('github')
    for s in args.surface or []:
        path, _, lang = s.partition(':')
        kind = 'readme' if path.lower().endswith(('.md', '.markdown')) else 'html'
        if kind != MODE_KIND[args.mode]:
            die(f'{path}: the {args.mode} skill works on ' + ('README files' if args.mode == 'readme' else
                'built HTML pages') + f'; use the {"site" if args.mode == "readme" else "readme"} skill for this one')
        brief['surfaces'].append({'path': path, 'kind': kind, 'lang': lang or brief['languages'][0]})
    if args.repo and 'github' in brief:
        brief['github']['repo'] = args.repo
    save(p, brief)
    root = root_dir(args)
    print(f'wrote {p}. Fill in project, audience, read and surfaces (in the user\'s language), then: eco.py brief')
    gi = root / '.gitignore'
    if not gi.exists() or '.eco' not in gi.read_text(encoding='utf-8', errors='ignore'):
        print('note: .eco/ is not in .gitignore; ask the user before adding it')
    branch = git(root, 'rev-parse', '--abbrev-ref', 'HEAD')
    default = ''
    if args.repo:
        try:
            r = subprocess.run(['gh', 'repo', 'view', args.repo, '--json', 'defaultBranchRef', '-q', '.defaultBranchRef.name'],
                               capture_output=True, text=True, timeout=20)
            default = r.stdout.strip() if r.returncode == 0 else ''
        except (OSError, subprocess.SubprocessError):
            pass
    default = default or (git(root, 'symbolic-ref', '--short', 'refs/remotes/origin/HEAD') or '').replace('origin/', '')
    if branch and default and branch != default:
        print(f'note: this checkout is on {branch!r}, not the default branch {default!r}. Search engines index the '
              f'default branch; tell the user the changes will only count once merged there.')
    mark(args, 'init', branch=branch or '')


def check_brief(args) -> list[str]:
    b = load(eco_dir(args) / 'brief.json')
    if b is None:
        return [f'no {rel(args)}/brief.json: run eco.py init']
    errs = []
    for k in ('name', 'what', 'problem'):
        if not str(b.get('project', {}).get(k, '')).strip():
            errs.append(f'project.{k} is empty')
    a = b.get('audience', {})
    if not str(a.get('primary', '')).strip():
        errs.append('audience.primary is empty')
    if not str(a.get('how_they_search', '')).strip():
        errs.append('audience.how_they_search is empty: say what these people type when the problem hits them')
    if a.get('niche') and len(a.get('adjacent', [])) < 2:
        errs.append('audience.niche is true: list at least 2 adjacent audiences or problems in audience.adjacent')
    if len(b.get('read', [])) < 2:
        errs.append('read: list the files or pages you read to understand the project (at least 2)')
    if not b.get('languages'):
        errs.append('languages is empty')
    if not b.get('surfaces'):
        errs.append('surfaces is empty')
    for s in b.get('surfaces', []):
        p = root_dir(args) / s.get('path', '')
        if s.get('kind') != MODE_KIND[args.mode]:
            errs.append(f"surface {s.get('path')}: the {args.mode} skill takes kind {MODE_KIND[args.mode]!r} only")
        elif not p.exists():
            errs.append(f"surface {s.get('path')}: file not found (for a site, point at the built HTML)")
        elif s['kind'] == 'html' and p.suffix.lower() not in ('.html', '.htm'):
            errs.append(f"surface {s.get('path')}: an html surface must be rendered HTML, not a template")
        if s.get('lang') not in b.get('languages', []):
            errs.append(f"surface {s.get('path')}: lang {s.get('lang')!r} is not in languages")
    if args.mode == 'site':
        u = str(b.get('site_url') or '')
        if not re.match(r'https?://[^/\s]+', u):
            errs.append('site_url: the live address of the site (open it once to be sure it answers); '
                        'the audit checks the canonical and og:url against it')
        bd = str(b.get('build_dir') or '')
        if not bd or not (root_dir(args) / bd).is_dir():
            errs.append('build_dir: the folder the build writes (dist/, out/, _site/); robots.txt, the sitemap '
                        'and llms.txt are checked there')
        else:
            for s in b.get('surfaces', []):
                try:
                    (root_dir(args) / s.get('path', '')).resolve().relative_to((root_dir(args) / bd).resolve())
                except ValueError:
                    errs.append(f"surface {s.get('path')}: not inside build_dir {bd}")
    return errs


def cmd_brief(args):
    errs = check_brief(args)
    for e in errs:
        bad(e)
    if errs:
        sys.exit(1)
    d = eco_dir(args)
    b = load(d / 'brief.json')
    orig = d / 'original'
    kept = []
    for s in b['surfaces']:
        dst = orig / s['path']
        if not dst.exists():  # the first copy is the baseline; later runs of `brief` never replace it
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root_dir(args) / s['path'], dst)
            kept.append(s['path'])
    ok('brief is complete' + (f'; kept the original of {", ".join(kept)} as the baseline' if kept else ''))
    mark(args, 'brief', originals={s['path']: sha(orig / s['path']) for s in b['surfaces']})


# ---------------------------------------------------------------- Google Suggest

# Three autocomplete services answer in the same shape, ["query", ["suggestion", ...]]. Spreading
# queries over them halves the wait when one host rate-limits, and each sees different searchers.
ENGINES = ('google', 'bing', 'ddg')
DDG_REGION = {'en': 'us-en', 'es': 'es-es', 'pt': 'br-pt', 'fr': 'fr-fr', 'de': 'de-de'}


def suggest_url(q: str, lang: str, engine: str = 'google') -> str:
    if engine == 'bing':
        return 'https://api.bing.com/osjson.aspx?' + urllib.parse.urlencode({'query': q, 'language': lang})
    if engine == 'ddg':
        return 'https://duckduckgo.com/ac/?' + urllib.parse.urlencode({'q': q, 'type': 'list', 'kl': DDG_REGION.get(lang, 'wt-wt')})
    return 'https://suggestqueries.google.com/complete/search?' + urllib.parse.urlencode(
        {'client': 'firefox', 'hl': lang, 'ie': 'utf-8', 'oe': 'utf-8', 'q': q})


def expand(seed: str, lang: str, depth: int, family: str) -> list[str]:
    """depth 0: the seed. 1: plus the two modifiers that fit its family. 2: every modifier and a-z."""
    qw, sf = QUESTION_WORDS.get(lang, QUESTION_WORDS['en']), SUFFIXES.get(lang, SUFFIXES['en'])
    qs = [seed]
    asks = any(norm(seed).startswith(norm(w) + ' ') for w in qw)
    if depth >= 1:
        if family in ('problem', 'result'):
            qs += ([] if asks else [f'{qw[0]} {seed}']) + [f'{seed} {sf[0]}']
        else:
            qs += [f'{seed} {sf[0]}', f'{seed} {sf[1]}']
    if depth >= 2:
        if family in ('problem', 'result'):
            qs += ([] if asks else [f'{w} {seed}' for w in qw[1:]]) + [f'{seed} {w}' for w in sf[1:]]
        else:
            qs += [f'{seed} {w}' for w in sf[2:]]
        qs += [f'{seed} {c}' for c in 'abcdefghijklmnopqrstuvwxyz']
    return list(dict.fromkeys(qs))


def cmd_suggest_urls(args):
    seeds = list(args.seed or [])
    if args.seeds_file:
        seeds += [l.strip() for l in Path(args.seeds_file).read_text(encoding='utf-8').splitlines() if l.strip()]
    if not seeds:
        die('give --seed (repeatable) or --seeds-file')
    d = eco_dir(args)
    man = load(d / 'suggest-plan.json', {'queries': []})
    have = {(q['q'], q['lang'], q.get('engine', 'google')) for q in man['queries']}
    new = []
    for s in seeds:
        for q in expand(s, args.lang, args.depth, args.family):
            if (q, args.lang, args.engine) not in have:
                have.add((q, args.lang, args.engine))
                item = {'q': q, 'lang': args.lang, 'engine': args.engine, 'seed': s, 'family': args.family,
                        'url': suggest_url(q, args.lang, args.engine)}
                man['queries'].append(item)
                new.append(item)
    save(d / 'suggest-plan.json', man)
    for it in new:
        print(it['url'])
    print(f'# {len(new)} new URLs ({len(man["queries"])} planned). Fetch them and save the responses under '
          f'{rel(args)}/raw/suggest/{args.lang}/{args.engine}/, then: eco.py suggest parse', file=sys.stderr)


def _suggest_arrays(obj, out):
    """Walk any JSON (a raw response, or a web tool's wrapper around several) for
    Suggest responses: a list whose first item is the query and second a list of strings."""
    if isinstance(obj, list):
        if len(obj) >= 2 and isinstance(obj[0], str) and isinstance(obj[1], list) and all(isinstance(x, str) for x in obj[1]):
            out.append((obj[0], obj[1]))
            return
        for x in obj:
            _suggest_arrays(x, out)
    elif isinstance(obj, dict):
        for x in obj.values():
            _suggest_arrays(x, out)
    elif isinstance(obj, str) and obj.lstrip().startswith('['):
        try:
            _suggest_arrays(json.loads(obj), out)
        except ValueError:
            pass


def parse_suggest_text(text: str) -> list[tuple[str, list[str]]]:
    out: list = []
    try:
        _suggest_arrays(json.loads(text), out)
        return out
    except ValueError:
        pass
    dec = json.JSONDecoder()
    i = text.find('["')
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
            _suggest_arrays(obj, out)
            i = text.find('["', end)
        except ValueError:
            i = text.find('["', i + 2)
    return out


def cmd_suggest_parse(args):
    d = eco_dir(args)
    raw = d / 'raw' / 'suggest'
    files = [Path(f) for f in args.files] if args.files else sorted(raw.rglob('*'))
    plan = load(d / 'suggest-plan.json', {'queries': []})
    planned: dict = {}
    for q in plan['queries']:
        planned.setdefault(norm(q['q']), []).append(q)
    data = load(d / 'suggest.json', {'responses': {}})
    unplanned = suspicious = 0
    for f in files:
        if not f.is_file():
            continue
        # Folders (raw/suggest/es/bing/...) settle queries planned in two languages or engines.
        parts = f.relative_to(raw).parts[:-1] if raw in f.parents else ()
        folder_lang = next((p for p in parts if p in QUESTION_WORDS), None)
        folder_engine = next((p for p in parts if p in ENGINES), None)
        for q, sugg in parse_suggest_text(read_text(f)):
            items = planned.get(norm(q))
            if not items:
                unplanned += 1
                continue
            item = next((i for i in items if (folder_lang is None or i['lang'] == folder_lang)
                         and (folder_engine is None or i.get('engine', 'google') == folder_engine)), items[0])
            # Keep suggestions that carry most of the query's content words, and drop the echo of
            # the query itself: neither "dark mode reader" for "readme dark mode image" nor the
            # query read back to us is evidence that people search it.
            qtok = {w for w in tokens(q) if len(w) > 1} - STOPWORDS
            need = max(1, -(-len(qtok) * 3 // 5))
            kept = [x for x in sugg if flat(x) != flat(q) and len(qtok & set(tokens(x))) >= need]
            if sugg and not kept and any(flat(x) != flat(q) for x in sugg):
                suspicious += 1
            sugg = kept
            eng = item.get('engine', 'google')
            data['responses'][f"{item['lang']}|{eng}|{item['q']}"] = {
                'q': item['q'], 'lang': item['lang'], 'engine': eng, 'seed': item['seed'],
                'family': item.get('family', ''), 'suggestions': sugg}
    terms: dict = {}
    for r in data['responses'].values():
        for s in r['suggestions']:
            k = f"{r['lang']}|{norm(s)}"
            t = terms.setdefault(k, {'phrase': norm(s), 'lang': r['lang'], 'hits': 0, 'from': []})
            t['hits'] += 1
            if r['q'] not in t['from']:
                t['from'].append(r['q'])
    data['terms'] = sorted(terms.values(), key=lambda t: (-t['hits'], t['phrase']))
    data['empty'] = sorted(r['q'] for r in data['responses'].values() if not r['suggestions'])
    save(d / 'suggest.json', data)
    by_lang = Counter(r['lang'] for r in data['responses'].values() if r['suggestions'])
    got = {(r['q'], r['lang'], r.get('engine', 'google')) for r in data['responses'].values()}
    todo = [q for q in plan['queries'] if (q['q'], q['lang'], q.get('engine', 'google')) not in got]
    print(f'{len(data["responses"])} responses ({dict(by_lang)} non-empty), {len(data["terms"])} distinct suggestions, '
          f'{len(data["empty"])} empty; {len(todo)} planned queries not fetched yet (that is fine: the gate counts responses)')
    if unplanned:
        warn(f'{unplanned} responses ignored: their query is not in the plan (plan it with `suggest urls` first)')
    if suspicious:
        warn(f'{suspicious} responses had only off-topic suggestions (fewer than 3 in 5 of the query words); counted as empty')
    for t in data['terms'][:args.top]:
        print(f"  {t['hits']:3}  [{t['lang']}] {t['phrase']}")
    mark(args, 'suggest', responses=len(data['responses']))


def cmd_suggest_terms(args):
    data = load(eco_dir(args) / 'suggest.json', {'terms': []})
    pat = flat(args.grep or '')
    for t in data.get('terms', []):
        if (not args.lang or t['lang'] == args.lang) and pat in flat(t['phrase']):
            print(f"  {t['hits']:3}  [{t['lang']}] {t['phrase']}")


def cmd_suggest_fetch(args):
    """For harnesses with no web tool: fetch the planned URLs directly, slowly."""
    d = eco_dir(args)
    plan = load(d / 'suggest-plan.json', {'queries': []})
    for q in plan['queries']:
        out = d / 'raw' / 'suggest' / q['lang'] / q.get('engine', 'google') / f"{hashlib.sha1(q['q'].encode('utf-8')).hexdigest()[:12]}.json"
        if out.exists():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(q['url'], headers={'User-Agent': 'eco-keyword-research/' + VERSION})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                out.write_bytes(r.read())
        except Exception as e:  # noqa: BLE001 - report and keep going
            print(f'skip {q["q"]!r}: {e}', file=sys.stderr)
        time.sleep(args.delay)
    print('fetched; now run: eco.py suggest parse')


# ---------------------------------------------------------------- GitHub search

GITHUB_PER_PAGE = 30


def github_search_url(q: str) -> str:
    return 'https://api.github.com/search/repositories?' + urllib.parse.urlencode({'q': q, 'per_page': GITHUB_PER_PAGE})


def cmd_github_urls(args):
    d = eco_dir(args)
    plan = load(d / 'github-plan.json', {'queries': {}})
    for q in args.query:
        slug = flat(q).replace(' ', '-')[:120]
        plan['queries'][slug] = q
        print(f'{slug}.json  {github_search_url(q)}')
    save(d / 'github-plan.json', plan)
    print('# best-match order, as people see it. Fetch each (or `gh api "search/repositories?q=...&per_page=30"`), '
          f'save it under {rel(args)}/raw/github/ with the name in front of it (`track` repeats the search under that name '
          'after publishing), then: eco.py github parse', file=sys.stderr)


def _github_results(obj, out):
    if isinstance(obj, dict):
        if 'total_count' in obj and isinstance(obj.get('items'), list):
            out.append(obj)
            return
        for v in obj.values():
            _github_results(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _github_results(v, out)
    elif isinstance(obj, str) and obj.lstrip().startswith('{'):
        try:
            _github_results(json.loads(obj), out)
        except ValueError:
            pass


def cmd_github_parse(args):
    d = eco_dir(args)
    b = load(d / 'brief.json', {})
    own = (b.get('github', {}).get('repo') or '').lower()
    files = [Path(f) for f in args.files] if args.files else sorted((d / 'raw' / 'github').rglob('*'))
    data = load(d / 'github.json', {'searches': [], 'repos': {}})
    for f in files:
        if not f.is_file():
            continue
        try:
            obj = json.loads(read_text(f))
        except ValueError:
            continue
        found: list = []
        _github_results(obj, found)
        data['searches'] = [s for s in data['searches'] if s['file'] != str(f)]
        for n, res in enumerate(found):
            names = [str(i.get('full_name', '')).lower() for i in res['items']]
            data['searches'].append({
                'file': str(f), 'label': f.stem + (f'#{n + 1}' if len(found) > 1 else ''),
                'total_count': res['total_count'], 'top': names[:10],
                'own_rank': names.index(own) + 1 if own and own in names else None})
            for it in res['items']:
                data['repos'][it.get('full_name')] = {
                    'description': it.get('description') or '', 'topics': it.get('topics') or [],
                    'stars': it.get('stargazers_count', 0), 'homepage': it.get('homepage') or ''}
    topics = Counter(t for r in data['repos'].values() for t in r['topics'])
    data['topics'] = topics.most_common()
    save(d / 'github.json', data)
    print(f"{len(data['searches'])} searches, {len(data['repos'])} repos, {len(topics)} topics")
    for s in data['searches']:
        rank = f"  {own}: #{s['own_rank']}" if s.get('own_rank') else (f'  {own}: not in the top results' if own else '')
        print(f"  {s['total_count']:>8} repos  {s['label']}{rank}")
    print('  top topics: ' + ', '.join(f'{t} ({n})' for t, n in topics.most_common(args.top)))
    mark(args, 'github', searches=len(data['searches']))


# ---------------------------------------------------------------- page parsing

class _Page(HTMLParser):
    SKIP = {'script', 'style', 'noscript', 'template', 'svg'}
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ''
        self.meta = ''
        self.og: list[str] = []
        self.headings: dict = {'h1': [], 'h2': [], 'h3': []}
        self.alts: list[str] = []
        self.jsonld: list[str] = []
        self.visible: list[str] = []
        self.paras: list[str] = []
        self.links: list[str] = []
        self.ids: list[str] = []
        self.urls: list[tuple[str, str]] = []
        self._stack: list[tuple[str, bool]] = []
        self._cur_h: str | None = None
        self._buf: list[str] = []
        self._pbuf: list[str] | None = None
        self._in_title = False
        self._in_ld = False
        self._ld: list[str] = []
        self.lang = ''
        self.robots: list[str] = []
        self.hreflang: list[tuple[str, str]] = []
        self.og_image = False
        self.no_alt = 0
        self.tag_counts: Counter = Counter()

    def _hidden(self) -> bool:
        return any(h for _, h in self._stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html':
            self.lang = a.get('lang', '')
        if a.get('id'):
            self.ids.append(a['id'])
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        if tag == 'meta':
            name = (a.get('name') or a.get('property') or '').lower()
            if name in ('description', 'robots', 'googlebot', 'og:title', 'og:description'):
                self.tag_counts[name] += 1
            if name in ('robots', 'googlebot'):
                self.robots.append((a.get('content') or '').lower())
            elif name == 'og:image' and (a.get('content') or '').strip():
                self.og_image = True
            if name == 'description':
                if not self.meta:
                    self.meta = a.get('content', '')
            elif name in ('og:title', 'og:description', 'twitter:title', 'twitter:description', 'og:image:alt'):
                self.og.append(a.get('content', ''))
            elif name == 'og:url':
                self.urls.append(('og:url', a.get('content', '')))
        elif tag == 'link' and (a.get('rel') or '').lower() == 'canonical':
            self.tag_counts['canonical'] += 1
            self.urls.append(('canonical', a.get('href', '')))
        elif tag == 'link' and (a.get('rel') or '').lower() == 'alternate' and a.get('hreflang'):
            self.hreflang.append((a['hreflang'].lower(), a.get('href', '')))
        elif tag == 'img' and not self._hidden():
            if a.get('alt'):
                self.alts.append(a['alt'])
            elif 'alt' not in a and (a.get('aria-hidden') or '').lower() != 'true' and (a.get('role') or '') != 'presentation':
                self.no_alt += 1  # alt="" marks a decorative image; no alt at all is the gap
        elif tag == 'title' and not self._hidden():
            self.tag_counts['title'] += 1
            if not self.title:
                self._in_title = True
        elif tag == 'script' and (a.get('type') or '').lower() == 'application/ld+json':
            self._in_ld = True
        if tag in self.VOID:
            return
        style = (a.get('style') or '').replace(' ', '').lower()
        hidden = tag in self.SKIP or 'hidden' in a or 'display:none' in style or 'visibility:hidden' in style
        self._stack.append((tag, hidden))
        if tag in self.headings and not self._hidden():
            self._cur_h, self._buf = tag, []
        if tag == 'p' and not self._hidden():
            self._pbuf = []

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        if tag == 'script' and self._in_ld:
            self._in_ld = False
            self.jsonld.append(''.join(self._ld))
            self._ld = []
        if tag == self._cur_h:
            self.headings[tag].append(re.sub(r'\s+', ' ', ''.join(self._buf)).strip())
            self._cur_h = None
        if tag == 'p' and self._pbuf is not None:
            t = re.sub(r'\s+', ' ', ''.join(self._pbuf)).strip()
            if t:
                self.paras.append(t)
            self._pbuf = None
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._in_ld:
            self._ld.append(data)
            return
        if self._hidden():
            return
        self.visible.append(data)
        if self._cur_h:
            self._buf.append(data)
        if self._pbuf is not None:
            self._pbuf.append(data)


def parse_html(text: str) -> dict:
    p = _Page()
    p.feed(text)
    ld_text, ld_errors = [], []
    for i, blob in enumerate(p.jsonld):
        try:
            ld_text.append(' '.join(_strings(json.loads(blob))))
        except ValueError as e:
            # Kept for the placement check, but Google ignores a block that does not parse.
            ld_text.append(blob)
            ld_errors.append(f'block {i + 1}: {e}')
    body = re.sub(r'\s+', ' ', ' '.join(p.visible)).strip()
    return {
        'kind': 'html', 'lang': p.lang, 'title': p.title.strip(), 'meta': p.meta.strip(),
        'h1': p.headings['h1'], 'h2': p.headings['h2'], 'h3': p.headings['h3'],
        'alt': p.alts, 'og': p.og, 'jsonld': ' '.join(ld_text), 'body': body,
        'lead': p.paras[0] if p.paras else '', 'links': p.links, 'anchors': p.ids,
        'code': [], 'headings_all': p.headings['h1'] + p.headings['h2'] + p.headings['h3'],
        'urls': p.urls + [('json-ld', u) for u in re.findall(r'"(?:url|@id)"\s*:\s*"(https?://[^"]+)"', ' '.join(p.jsonld))],
        'jsonld_errors': ld_errors, 'robots': p.robots, 'hreflang': p.hreflang, 'og_image': p.og_image,
        'img_no_alt': p.no_alt, 'duplicates': sorted(t for t, n in p.tag_counts.items() if n > 1),
    }


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in ('@context', '@type', 'url', 'sameAs', 'license', 'image'):
                yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _md_text(s: str) -> str:
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', s)
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)
    s = re.sub(r'[*_`>#|]', ' ', s)
    return re.sub(r'\s+', ' ', _html.unescape(s)).strip()


def gh_slug(heading: str) -> str:
    """GitHub's anchor for a heading (underscores and hyphens kept, other punctuation dropped)."""
    s = re.sub(r'<[^>]+>', '', heading)
    s = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'', s)
    s = _html.unescape(s).strip().lower()
    s = re.sub(r'[^\w\- ]', '', s)
    return s.replace(' ', '-')


def gh_slugs(headings) -> list[str]:
    seen: Counter = Counter()
    out = []
    for h in headings:
        base = gh_slug(h)
        out.append(base if not seen[base] else f'{base}-{seen[base]}')
        seen[base] += 1
    return out


KEYWORD_LIST = re.compile(r'^\s*(<sub>\s*)?(<b>\s*|\*\*)?(keywords?|palabras clave|tags)\b', re.I)


def parse_readme(text: str) -> dict:
    no_code = re.sub(r'^(```|~~~).*?^\1[^\n]*$', ' ', text, flags=re.S | re.M)
    code = re.findall(r'`([^`\n]+)`', no_code)
    lines = no_code.split('\n')
    # A "Keywords:" footer, and the lines that follow it up to the next blank line, are a list for
    # crawlers, not text. So is a line of 5+ middle-dot separated items with no sentence in it.
    kw_idx: set = set()
    in_block = False
    for i, l in enumerate(lines):
        if KEYWORD_LIST.match(l) and re.search(r'keyword', l, re.I):
            in_block = True
        elif not l.strip():
            in_block = False
        if in_block or (l.count('·') >= 5 and not l.lstrip().startswith('|') and not re.search(r'[a-z]{3,}\. [A-Z]', l)):
            kw_idx.add(i)
    kw_lines = [lines[i] for i in sorted(kw_idx)]
    prose = '\n'.join(l for i, l in enumerate(lines) if i not in kw_idx)
    h1: list[tuple[int, str]] = []
    for m in re.finditer(r'^#[ \t]+([^\n]+)$', prose, flags=re.M):
        h1.append((m.start(), m.group(1)))
    for m in re.finditer(r'<h1[^>]*>(.*?)</h1>', prose, flags=re.I | re.S):
        h1.append((m.start(), _md_text(m.group(1))))
    for m in re.finditer(r'^([^\n#<>|][^\n]*)\n=+[ \t]*$', prose, flags=re.M):
        h1.append((m.start(), m.group(1)))
    h1.sort()
    heads: list[tuple[int, str]] = []
    for m in re.finditer(r'^#{2,4}[ \t]+([^\n]+)$', prose, flags=re.M):
        heads.append((m.start(), m.group(1)))
    for m in re.finditer(r'<h[2-4][^>]*>(.*?)</h[2-4]>', prose, flags=re.I | re.S):
        heads.append((m.start(), _md_text(m.group(1))))
    heads.sort()
    alts = re.findall(r'!\[([^\]]+)\]', prose) + re.findall(r'<img[^>]*\balt="([^"]+)"', prose, flags=re.I)
    after = prose[h1[0][0]:] if h1 else prose
    after = after.split('\n', 1)[1] if h1 and '\n' in after else after
    after = re.sub(r'^=+[ \t]*$', ' ', after, count=1, flags=re.M)
    after = re.sub(r'<picture.*?</picture>|<img[^>]*>|!\[[^\]]*\]\([^)]*\)', ' ', after, flags=re.S | re.I)
    after = re.sub(r'^\s*(<p[^>]*>\s*)?(<a [^>]*>\s*)*$', ' ', after, flags=re.M)
    after = re.sub(r'^#{2,6}[^\n]*$', ' ', after, flags=re.M)
    lead = _md_text(after)[:300]
    links = re.findall(r'\]\(([^)\s]+)', no_code) + re.findall(r'href="([^"]+)"', no_code)
    anchors = gh_slugs([h for _, h in sorted(h1 + heads)]) + re.findall(r'<a[^>]*\b(?:id|name)="([^"]+)"', no_code)
    return {'kind': 'readme', 'h1': [_md_text(x) for _, x in h1], 'heading': [_md_text(x) for _, x in heads],
            'alt': alts, 'lead': lead, 'body': _md_text(prose), 'keyword_lines': [l.strip()[:120] for l in kw_lines],
            'links': links, 'anchors': anchors, 'code': code,
            'headings_all': [_md_text(x) for _, x in h1 + heads]}


def parse_surface(path: Path, kind: str) -> dict:
    text = read_text(path)
    return parse_html(text) if kind == 'html' else parse_readme(text)


def field_items(page: dict, placement: str) -> list[str]:
    v = page.get(placement, '')
    return list(v) if isinstance(v, list) else [v]


def count_items(items, phrases) -> int:
    """Matches inside each item separately: a phrase split over two headings is not placed."""
    return sum(count_in(t, phrases) for t in items)


# ---------------------------------------------------------------- competitors

def ngrams(text: str, n: int) -> list[str]:
    w = words(text)
    out = []
    for i in range(len(w) - n + 1):
        g = w[i:i + n]
        if g[0] in STOPWORDS or g[-1] in STOPWORDS or len(g[0]) < 2:
            continue
        out.append(' '.join(g))
    return out


def cmd_competitors(args):
    d = eco_dir(args)
    files = [Path(f) for f in args.files] if args.files else sorted((d / 'raw' / 'competitors').rglob('*'))
    data = load(d / 'competitors.json', {'pages': {}})
    for f in files:
        if not f.is_file():
            continue
        text = read_text(f)
        looks_html = bool(re.search(r'<(html|head|title|body|h1|meta)\b', text, re.I))
        kind = 'html' if looks_html else 'readme'
        page = parse_html(text) if kind == 'html' else parse_readme(text)
        data['pages'][f.name] = {
            'kind': kind, 'title': page.get('title', ''), 'meta': page.get('meta', ''), 'h1': page.get('h1', [])[:2],
            'h2': (page.get('h2') or page.get('heading') or [])[:20], 'lead': page.get('lead', '')}
    grams = Counter()
    for pg in data['pages'].values():
        strong = ' . '.join([pg['title'], pg['meta'], ' . '.join(pg['h1']), ' . '.join(pg['h2']), pg['lead']])
        for n in (2, 3):
            grams.update(set(ngrams(strong, n)))
    data['shared_phrases'] = [[g, c] for g, c in grams.most_common(80) if c >= 2]
    save(d / 'competitors.json', data)
    print(f"{len(data['pages'])} competitor pages parsed")
    for name, pg in data['pages'].items():
        print(f"  {name}: {pg['title'][:70] or (pg['h1'][:1] or [''])[0][:70]}")
    print('  phrases shared by 2+ competitors: ' + ', '.join(f'{g} ({c})' for g, c in data['shared_phrases'][:args.top]))
    mark(args, 'competitors', pages=len(data['pages']))


# ---------------------------------------------------------------- search results (SERP)

SERP_ENGINES = ('ddg', 'bing')
SERP_TOP = 10
SERP_SAME_INTENT = 7            # shared top-10 results: two phrases are one search
ENGINE_HOSTS = ('bing.com', 'microsoft.com', 'msn.com', 'duckduckgo.com', 'google.com', 'googleusercontent.com')
REPO_HOSTS = ('github.com', 'gitlab.com', 'codeberg.org', 'bitbucket.org')
# First path segments on those hosts that are site pages, not someone's repository.
NOT_OWNERS = {'topics', 'collections', 'marketplace', 'features', 'login', 'signup', 'orgs', 'sponsors', 'search',
              'explore', 'trending', 'about', 'pricing', 'enterprise', 'settings', 'apps', 'site', 'resources',
              'solutions', 'customer-stories', 'readme', 'events', 'security', 'users', 'help', 'blog', 'docs'}


def serp_url(q: str, lang: str, engine: str) -> str:
    if engine == 'ddg':
        return 'https://html.duckduckgo.com/html/?' + urllib.parse.urlencode({'q': q, 'kl': DDG_REGION.get(lang, 'wt-wt')})
    return 'https://www.bing.com/search?' + urllib.parse.urlencode({'q': q, 'setlang': lang, 'count': SERP_TOP})


def serp_slug(q: str, lang: str) -> str:
    return f"{lang}-{flat(q).replace(' ', '-')}"[:120]


def _unwrap(href: str) -> str:
    """The target of a Bing or DuckDuckGo redirect link."""
    href = _html.unescape(href or '').strip()
    if href.startswith('//'):
        href = 'https:' + href
    u = urllib.parse.urlparse(href)
    qs = urllib.parse.parse_qs(u.query)
    if u.netloc.endswith('duckduckgo.com') and qs.get('uddg'):
        return qs['uddg'][0]
    if u.netloc.endswith('bing.com') and u.path.startswith('/ck/') and qs.get('u'):
        v = qs['u'][0]
        if v.startswith('a1'):
            try:
                return base64.urlsafe_b64decode(v[2:] + '=' * (-len(v[2:]) % 4)).decode('utf-8', 'replace')
            except ValueError:
                return ''
    return href


def _engine_host(u: str) -> bool:
    host = urllib.parse.urlparse(u).netloc.lower()
    return not host or any(host == h or host.endswith('.' + h) for h in ENGINE_HOSTS)


def url_key(u: str) -> str:
    p = urllib.parse.urlparse(u)
    host = re.sub(r'^www\.', '', p.netloc.lower())
    return host + p.path.rstrip('/').lower()


def own_keys(b: dict) -> list[tuple[str, str]]:
    """What marks a search result as the project's own: the host of the site, the path of the repository."""
    out = []
    url = str(b.get('site_url') or '')
    host = re.sub(r'^www\.', '', urllib.parse.urlparse(url).netloc.lower())
    if host and not is_local(url):
        out.append(('host', host))
    repo = str((b.get('github') or {}).get('repo') or '').strip('/').lower()
    if repo:
        out.append(('repo', 'github.com/' + repo))
    return out


def own_rank_in(urls, keys) -> int | None:
    """1-based position of the first result that is the project's own; None when it is not among them."""
    for i, u in enumerate(urls, 1):
        k = url_key(u)
        host = k.split('/')[0]
        for kind, v in keys:
            if kind == 'host' and (host == v or host.endswith('.' + v)):
                return i
            if kind == 'repo' and (k == v or k.startswith(v + '/')):
                return i
    return None


class _Serp(HTMLParser):
    """Organic results of a saved Bing or DuckDuckGo results page, ads left out."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[str] = []
        self._stack: list[tuple[str, str]] = []
        self._taken = False

    def _in(self, cls: str) -> bool:
        return any(cls in c.split() for _, c in self._stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get('class') or ''
        if tag == 'li' and 'b_algo' in cls.split():
            self._taken = False
        if tag == 'a' and a.get('href'):
            if 'result__a' in cls.split() and not self._in('result--ad'):
                self.results.append(_unwrap(a['href']))
            elif self._in('b_algo') and any(t == 'h2' for t, _ in self._stack) and not self._taken:
                self.results.append(_unwrap(a['href']))
                self._taken = True
        if tag not in _Page.VOID:
            self._stack.append((tag, cls))

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break


def _json_urls(obj, out):
    if isinstance(obj, dict):
        for k in ('url', 'link', 'href'):
            if isinstance(obj.get(k), str) and obj[k].startswith('http'):
                out.append(obj[k])
                break
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _json_urls(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _json_urls(v, out)


def _page_urls(text: str) -> list[str]:
    p = _Serp()
    p.feed(text)
    if p.results:
        return p.results
    # Markdown of a results page; a web tool may give the engine's own links as bare paths.
    links = re.findall(r'\]\(((?:https?:)?//[^)\s]+|/l/\?uddg=[^)\s]+)\)', text)
    return [_unwrap('https://duckduckgo.com' + u if u.startswith('/l/') else u) for u in links]


def _json_strings(obj, out):
    if isinstance(obj, str):
        if len(obj) > 200:
            out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _json_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _json_strings(v, out)


def parse_serp(text: str, top: int | None = SERP_TOP) -> list[str]:
    """Results in order, from engine HTML, a web tool's JSON or its markdown; `top=None` keeps every one."""
    found: list[str] = []
    try:
        obj = json.loads(text)
    except ValueError:
        found = _page_urls(text)
    else:
        _json_urls(obj, found)
        if not [u for u in found if not _engine_host(u)]:
            # A wrapper around the page (its url is the engine's): read the page it carries.
            blobs: list[str] = []
            _json_strings(obj, blobs)
            found = [u for b in blobs for u in _page_urls(b)]
    out, seen = [], set()
    for u in found:
        if _engine_host(u):
            continue
        k = url_key(u)
        if k not in seen:
            seen.add(k)
            out.append(u)
    return out[:top]


def result_kind(u: str) -> str:
    p = urllib.parse.urlparse(u)
    host = re.sub(r'^www\.', '', p.netloc.lower())
    parts = [x for x in p.path.split('/') if x]
    if host == 'github.com' and len(parts) == 2 and parts[0].lower() == 'topics':
        return 'topic'  # lists the repos tagged with it: a repo gets there through its topics
    if host in REPO_HOSTS and len(parts) >= 2 and parts[0].lower() not in NOT_OWNERS:
        return 'repo'
    if host in ('npmjs.com', 'pypi.org', 'crates.io', 'pkg.go.dev', 'marketplace.visualstudio.com'):
        return 'package'
    if host in ('youtube.com', 'youtu.be', 'vimeo.com'):
        return 'video'
    if host in ('reddit.com', 'stackoverflow.com', 'news.ycombinator.com', 'dev.to', 'medium.com') or host.endswith('.stackexchange.com'):
        return 'forum'
    return 'page'


def cmd_serp_urls(args):
    d = eco_dir(args)
    km = load(d / 'keywords.json', {'keywords': []})
    phrases = [(k['phrase'], k['lang']) for k in km.get('keywords', []) if k.get('tier') == 'primary']
    phrases += [(p, args.lang) for p in (args.phrase or [])]
    if not phrases:
        die('no primary in .eco/keywords.json yet (or pass --phrase with --lang)')
    plan = load(d / 'serp-plan.json', {'queries': {}})
    for q, lang in phrases:
        if not lang:
            die(f'--phrase {q!r} needs --lang')
        slug = serp_slug(q, lang)
        plan['queries'][slug] = {'q': q, 'lang': lang, 'engine': args.engine, 'url': serp_url(q, lang, args.engine)}
        print(f"{slug}  {plan['queries'][slug]['url']}")
    save(d / 'serp-plan.json', plan)
    print(f'# fetch each page and save it as {rel(args)}/raw/serp/<slug>.<ext> (the engine HTML, or a web tool\'s JSON or '
          'markdown of it), then: eco.py serp parse', file=sys.stderr)


def cmd_serp_fetch(args):
    """Fallback for a harness with no web tool: fetch the planned pages slowly, skip saved ones."""
    d = eco_dir(args)
    plan = load(d / 'serp-plan.json', {'queries': {}})
    out = d / 'raw' / 'serp'
    out.mkdir(parents=True, exist_ok=True)
    have = {f.name.split('.')[0] for f in out.iterdir() if f.is_file()}
    todo = [(slug, q) for slug, q in plan['queries'].items() if slug not in have]
    for i, (slug, q) in enumerate(todo):
        if i:
            time.sleep(args.delay)
        req = urllib.request.Request(q['url'], headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
                                                        'Accept-Language': q['lang']})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode('utf-8', 'replace')
        except OSError as e:
            warn(f"{slug}: {e}; stopping here, run it again later")
            break
        (out / f'{slug}.html').write_text(body, encoding='utf-8')
        print(f'saved {slug}.html ({len(parse_serp(body))} results)')
    print('# then: eco.py serp parse', file=sys.stderr)


def cmd_serp_parse(args):
    d = eco_dir(args)
    plan = load(d / 'serp-plan.json', {'queries': {}})
    data = load(d / 'serp.json', {'queries': {}})
    keys = own_keys(load(d / 'brief.json', {}))
    for f in sorted((d / 'raw' / 'serp').rglob('*')) if (d / 'raw' / 'serp').exists() else []:
        if not f.is_file():
            continue
        slug = f.name.split('.')[0]
        if slug not in plan['queries']:
            warn(f'{f.name}: not in the plan (run `eco.py serp urls` first; the file name is the slug)')
            continue
        every = parse_serp(read_text(f), None)
        res = every[:SERP_TOP]
        if not res:
            warn(f'{f.name}: no results found; the page may be a block or a captcha, not results')
            continue
        # Where the project stands before any edit ships: the "before" that `track` compares with.
        data['queries'][slug] = dict(plan['queries'][slug], results=res, kinds=dict(Counter(result_kind(u) for u in res)),
                                     own_rank=own_rank_in(every, keys), seen=len(every))
    save(d / 'serp.json', data)
    for slug, s in data['queries'].items():
        kinds = ', '.join(f'{n} {k}' for k, n in sorted(s['kinds'].items(), key=lambda x: -x[1]))
        own = ''
        if keys and 'own_rank' in s:
            own = f"; yours: #{s['own_rank']}" if s['own_rank'] else f"; yours: not in the first {s['seen']}"
        print(f"  [{s['lang']}] {s['q']}: {len(s['results'])} results ({kinds}){own}")
    for a, b, n in serp_overlaps(data):
        print(f"  {a!r} and {b!r} share {n} of the top {SERP_TOP}" + ('; one search intent' if n >= SERP_SAME_INTENT else ''))
    mark(args, 'serp', queries=len(data['queries']))


def serp_overlaps(data: dict) -> list[tuple[str, str, int]]:
    qs = list(data.get('queries', {}).values())
    out = []
    for i, a in enumerate(qs):
        for b in qs[i + 1:]:
            if a['lang'] == b['lang']:
                n = len({url_key(u) for u in a['results']} & {url_key(u) for u in b['results']})
                if n >= 4:
                    out.append((a['q'], b['q'], n))
    return out


def serp_for(data: dict, phrases, lang: str) -> dict | None:
    keys = {flat(p) for p in phrases}
    return next((s for s in data.get('queries', {}).values() if s['lang'] == lang and flat(s['q']) in keys), None)


# ---------------------------------------------------------------- research gate

def check_research(args) -> list[str]:
    d = eco_dir(args)
    b = load(d / 'brief.json', {})
    errs = []
    sug = load(d / 'suggest.json', {'responses': {}})
    for li, lang in enumerate(b.get('languages', [])):
        main = 0 if li == 0 else 1
        rs = [r for r in sug['responses'].values() if r['lang'] == lang]
        per_seed = Counter(r['seed'] for r in rs if r['suggestions'])
        counted = sum(min(n, MAX_PER_SEED) for n in per_seed.values())
        if counted < MIN_SUGGEST_RESPONSES[main]:
            errs.append(f'[{lang}] {counted} non-empty Suggest responses count (at most {MAX_PER_SEED} per seed); '
                        f'need {MIN_SUGGEST_RESPONSES[main]}. Add seeds rather than deepening one')
        fetched_seeds = {r['seed'] for r in rs}
        if len(fetched_seeds) < MIN_SUGGEST_SEEDS[main]:
            errs.append(f'[{lang}] {len(fetched_seeds)} seeds fetched; need {MIN_SUGGEST_SEEDS[main]}')
        fams = {r['family'] for r in rs if r.get('family') in FAMILIES[:5]}
        if len(fams) < MIN_FAMILIES[main]:
            missing = [f for f in FAMILIES[:5] if f not in fams]
            errs.append(f'[{lang}] seed families covered: {sorted(fams) or "none"}; need {MIN_FAMILIES[main]} of 5 '
                        f'(missing: {", ".join(missing)}). Plan seeds with --family')
        if b.get('audience', {}).get('niche'):
            adj = {r['seed'] for r in rs if r.get('family') == 'adjacent'}
            need = len(b['audience'].get('adjacent', []))
            if len(adj) < need:
                errs.append(f'[{lang}] the brief lists {need} adjacent audiences but {len(adj)} adjacent seeds were fetched '
                            f'(plan one per adjacent entry with --family adjacent)')
    comp = load(d / 'competitors.json', {'pages': {}})
    if len(comp['pages']) < MIN_COMPETITORS:
        errs.append(f"{len(comp['pages'])} competitor pages parsed; need {MIN_COMPETITORS}")
    if any(s.get('kind') == 'readme' for s in b.get('surfaces', [])):
        gh = load(d / 'github.json', {'searches': []})
        if len(gh['searches']) < MIN_GITHUB_QUERIES:
            errs.append(f"{len(gh['searches'])} GitHub searches parsed; need {MIN_GITHUB_QUERIES} for a README")
    return errs


def cmd_research(args):
    errs = check_brief(args) + check_research(args)
    for e in errs:
        bad(e)
    if errs:
        sys.exit(1)
    ok('research is deep enough to build the map')
    mark(args, 'research')


# ---------------------------------------------------------------- keyword map

def research_corpus(d: Path) -> dict:
    sug = load(d / 'suggest.json', {'responses': {}})
    gh = load(d / 'github.json', {'repos': {}})
    comp = load(d / 'competitors.json', {'pages': {}})
    by_lang: dict = {}
    for r in sug['responses'].values():
        # Only what the service suggested counts; the query we typed proves nothing.
        by_lang.setdefault(r['lang'], []).extend(r['suggestions'])
    return {
        'suggest': by_lang,
        'github': [r['description'] for r in gh['repos'].values()]
                  + [t.replace('-', ' ') for r in gh['repos'].values() for t in r['topics']],
        'competitor': [x for p in comp['pages'].values() for x in [p['title'], p['meta'], p['lead'], *p['h1'], *p['h2']]],
    }


def found_in(corpus: dict, source: str, lang: str, phrases) -> bool:
    items = corpus['suggest'].get(lang, []) if source == 'suggest' else corpus.get(source, [])
    return count_items(items, phrases) > 0


def map_hash(km: dict) -> str:
    """What the text has to satisfy: phrases, tiers, placements and variants. Evidence notes and
    discard reasons can still be edited after the text without unlocking anything."""
    return sha([{k: e.get(k) for k in ('phrase', 'lang', 'tier', 'placements', 'variants')}
                for e in km.get('keywords', []) if e.get('tier') != 'discarded'])


def check_map(args) -> tuple[list[str], dict]:
    d = eco_dir(args)
    b = load(d / 'brief.json', {})
    km = load(d / 'keywords.json')
    if km is None:
        return [f'no {rel(args)}/keywords.json'], {}
    corpus = research_corpus(d)
    serp = load(d / 'serp.json', {'queries': {}})
    errs = [f'research first: {e}' for e in check_research(args)]
    kws = km.get('keywords', [])
    kinds = {s['kind'] for s in b.get('surfaces', [])}
    allowed = set()
    if 'html' in kinds:
        allowed |= HTML_PLACEMENTS
    if 'readme' in kinds:
        allowed |= README_PLACEMENTS
    if b.get('github', {}).get('repo'):
        allowed |= GITHUB_PLACEMENTS
    seen = set()
    for i, k in enumerate(kws):
        tag = f"keyword {i + 1} {k.get('phrase')!r}"
        if not str(k.get('phrase', '')).strip():
            errs.append(f'keyword {i + 1}: empty phrase')
            continue
        key = (flat(k['phrase']), k.get('lang'))
        if key in seen:
            errs.append(f'{tag}: duplicate')
        seen.add(key)
        if k.get('lang') not in b.get('languages', []):
            errs.append(f"{tag}: lang {k.get('lang')!r} not in the brief's languages")
        tier = k.get('tier')
        if tier not in TIERS:
            errs.append(f'{tag}: tier must be one of {", ".join(TIERS)}')
            continue
        if tier == 'discarded':
            if not str(k.get('reason', '')).strip():
                errs.append(f'{tag}: a discarded phrase needs a reason')
            continue
        variants = list(k.get('variants', []))
        base = set(tokens(k['phrase']))
        for v in variants:
            if set(tokens(v)) != base and not found_in(corpus, 'suggest', k.get('lang'), [v]):
                errs.append(f'{tag}: variant {v!r} is not the same words as the phrase (plural, punctuation or order) '
                            f'and is not itself in the Suggest data; make it its own phrase')
        ev = k.get('evidence', [])
        if not ev or not all(isinstance(e, dict) and e.get('source') in DEMAND_SOURCES for e in ev):
            errs.append(f'{tag}: evidence must list sources from {sorted(DEMAND_SOURCES)}')
        else:
            for e in ev:
                if e['source'] in CHECKED_SOURCES and not found_in(corpus, e['source'], k.get('lang'), [k['phrase']] + variants):
                    errs.append(f"{tag}: evidence says {e['source']}, but the phrase is not in {rel(args)}/{e['source']}"
                                f"{'.json' if e['source'] != 'competitor' else 's.json'}")
            if tier == 'primary' and not any(e['source'] in ('suggest', 'search-console', 'trends') for e in ev):
                errs.append(f'{tag}: a primary needs demand evidence (suggest, search-console or trends); '
                            f'github and competitor show wording, not that people search it')
        pl = k.get('placements', [])
        unknown = [p for p in pl if p not in allowed]
        if unknown:
            errs.append(f'{tag}: unknown placements {unknown}; allowed here: {sorted(allowed)}')
        if tier == 'primary':
            if not {'title', 'h1', 'lead', 'about'} & set(pl):
                errs.append(f'{tag}: a primary needs one of title, h1, lead or about')
            if len(pl) < 2:
                errs.append(f'{tag}: a primary needs at least 2 placements')
        if k.get('claim', 'true') not in ('true', 'negation'):
            errs.append(f"{tag}: claim must be 'true' (the project does this) or 'negation' (only in a 'no, it is not' answer)")
        if k.get('claim') == 'negation' and tier == 'primary':
            errs.append(f'{tag}: a negation cannot be a primary; the project should not lead with what it is not')
        if tier == 'primary':
            sp = serp_for(serp, [k['phrase']] + variants, k.get('lang'))
            if sp is None:
                errs.append(f'{tag}: no saved search results for this primary; run `eco.py serp urls`, fetch, `eco.py serp parse`')
            elif (kinds == {'readme'} and not sp['kinds'].get('repo') and not sp['kinds'].get('topic')
                  and not str(k.get('serp_note', '')).strip()):
                errs.append(f'{tag}: no repository or GitHub topic page in the top {SERP_TOP} results, so a README is '
                            f'unlikely to rank for it; make it secondary, or keep it with a serp_note that says why')
    prim = [k for k in kws if k.get('tier') == 'primary']
    for i, a in enumerate(prim):
        for b_ in prim[i + 1:]:
            if a.get('lang') != b_.get('lang'):
                continue
            sa = serp_for(serp, [a['phrase']] + list(a.get('variants', [])), a.get('lang'))
            sb = serp_for(serp, [b_['phrase']] + list(b_.get('variants', [])), b_.get('lang'))
            if sa and sb and sa is not sb:
                n = len({url_key(u) for u in sa['results']} & {url_key(u) for u in sb['results']})
                if n >= SERP_SAME_INTENT:
                    errs.append(f"primaries {a['phrase']!r} and {b_['phrase']!r} share {n} of the top {SERP_TOP} results: "
                                f'one search intent. Keep one primary; make the other a variant or a secondary')
    for lang in b.get('languages', []):
        n = sum(1 for k in kws if k.get('tier') == 'primary' and k.get('lang') == lang)
        if n == 0:
            errs.append(f'[{lang}] no primary keyword')
        if n > MAX_PRIMARY:
            errs.append(f'[{lang}] {n} primaries; keep {MAX_PRIMARY} or fewer, the searches the project should win')
    live = [k for k in kws if k.get('tier') != 'discarded']
    if len(live) < MIN_PHRASES:
        errs.append(f'{len(live)} phrases kept in the map; record at least {MIN_PHRASES} (primary, secondary and long-tail)')
    if sum(1 for k in kws if k.get('tier') == 'discarded') < MIN_DISCARDED:
        errs.append(f'record at least {MIN_DISCARDED} discarded phrases with the reason the research ruled them out')
    return errs, km


def cmd_map(args):
    errs, km = check_map(args)
    for e in errs:
        bad(e)
    if errs:
        sys.exit(1)
    c = Counter(k['tier'] for k in km['keywords'])
    ok(f"map valid: {c['primary']} primary, {c['secondary']} secondary, {c['long-tail']} long-tail, {c['discarded']} discarded")
    mark(args, 'map', hash=map_hash(km))


# ---------------------------------------------------------------- audit

def github_page(args, b) -> dict | None:
    """The About and topics to audit: the proposal recorded with `offsite`, else the live ones."""
    off = state(args).get('offsite')
    if off and (off.get('about') or off.get('topics')):
        return {'about': off.get('about') or '', 'topics': [t.replace('-', ' ') for t in off.get('topics', [])],
                'source': 'offsite proposal' if not off.get('applied') else 'offsite (applied)'}
    f = b.get('github', {}).get('about_file')
    if not f or not (root_dir(args) / f).exists():
        return None
    g = json.loads(read_text(root_dir(args) / f))
    topics = g.get('repositoryTopics') or g.get('topics') or []
    topics = [t['name'] if isinstance(t, dict) else t for t in topics]
    return {'about': g.get('description') or '', 'topics': [t.replace('-', ' ') for t in topics], 'source': f}


# A description that ends in one of these was filled in by a template or a model, not written.
STOCK_CTA = re.compile(r'(?:^|[.!?]\s+)(?:learn more|read more|find out more|discover more|click here|get started|start (?:for )?free'
                       r'|try it(?: for)? free|try it|sign up|join now|shop now|book now|order now|contact us)'
                       r'(?: now| today| here)?\s*[.!]*\s*$', re.I)
BRAND_SEPARATOR = re.compile(r'\s[|·–—-]\s')
ECHO_MIN_CHARS = 25     # a shorter title can open a real sentence ("Word counter that ...")


def templated_meta(title: str, meta: str) -> list[str]:
    """Deterministic signs that the meta description was generated from the title."""
    t, m = flat(title), flat(meta)
    if not t or not m:
        return []
    if t == m:
        return ['the meta description is the title again; write the sentence a searcher would click']
    out = []
    core = flat(BRAND_SEPARATOR.split(title)[0])
    if len(core) >= ECHO_MIN_CHARS and m.startswith(core):
        out.append('the meta description opens by repeating the title; the snippet sits under the title, so say something new')
    cta = STOCK_CTA.search(meta.strip())
    if cta:
        out.append(f'the meta description ends in a stock call to action ("{cta.group(0).lstrip(".!? ").strip()}"); '
                   f'end on what the page gives')
    return out


def lang_tag(code: str) -> str:
    return code.lower().split('-')[0].split('_')[0]


def html_checks(pg: dict, lang: str, html_langs: set) -> list[str]:
    """Checks on a built page that decide whether search engines can use it at all."""
    out = []
    directives = {d.strip() for r in pg.get('robots', []) for d in r.split(',')}
    if directives & {'noindex', 'none'}:
        out.append('meta robots says noindex: search engines are asked to drop this page, so no placement on it counts')
    for e in pg.get('jsonld_errors', []):
        out.append(f'JSON-LD {e}; search engines ignore a block that does not parse')
    if not pg.get('lang'):
        out.append('no <html lang>; declare the language of the page')
    elif lang_tag(pg['lang']) != lang_tag(lang):
        out.append(f'<html lang="{pg["lang"]}"> but the brief says this surface is [{lang}]')
    tags = {lang_tag(h) for h, _ in pg.get('hreflang', []) if h != 'x-default'}
    if pg.get('hreflang') and lang_tag(lang) not in tags:
        out.append(f'hreflang links do not include the page itself ([{lang}]); each version lists every version, itself included')
    for other in sorted(html_langs - {lang}):
        if lang_tag(other) not in tags:
            out.append(f'no hreflang link to the [{other}] version; language versions link to each other both ways')
    if not pg.get('og_image'):
        out.append('no og:image; a shared link shows no picture')
    if pg.get('img_no_alt'):
        out.append(f'{pg["img_no_alt"]} visible images without an alt attribute (alt="" for a decorative one)')
    for t in pg.get('duplicates', []):
        out.append(f'more than one {t} tag; search engines pick one, maybe not yours')
    out += templated_meta(pg.get('title', ''), pg.get('meta', ''))
    return out


# Robots.txt tokens, from each vendor's own page (checked 2026-11):
# developers.openai.com/api/docs/bots, support.claude.com/en/articles/8896518,
# docs.perplexity.ai/docs/resources/perplexity-crawlers,
# developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers.
# Search and retrieval bots decide whether the site can be shown or quoted in answers: blocking
# them is flagged. Training bots only decide whether content trains models: blocking them is a
# legitimate choice and only noted.
SEARCH_BOTS = ('Googlebot', 'Bingbot', 'OAI-SearchBot', 'ChatGPT-User', 'Claude-SearchBot', 'Claude-User',
               'PerplexityBot', 'Perplexity-User')
TRAINING_BOTS = ('GPTBot', 'ClaudeBot', 'Google-Extended', 'CCBot', 'Applebot-Extended')


def parse_robots(text: str) -> tuple[list, list[str]]:
    """Groups of (user agents, rules) and the Sitemap lines of a robots.txt."""
    groups, sitemaps, agents, rules, last = [], [], [], [], ''
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if ':' not in line:
            continue
        k, v = (x.strip() for x in line.split(':', 1))
        k = k.lower()
        if k == 'sitemap':
            sitemaps.append(v)
            continue
        if k == 'user-agent':
            if last != 'user-agent' and agents:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(v.lower())
        elif k in ('allow', 'disallow') and agents:
            rules.append((k, v))
        last = k
    if agents:
        groups.append((agents, rules))
    return groups, sitemaps


def robots_blocks(groups, bot: str) -> bool:
    """Whether the group that applies to this bot shuts it out of the whole site."""
    named = [r for a, r in groups if bot.lower() in a]
    rules = [x for r in named for x in r] if named else [x for a, r in groups if '*' in a for x in r]
    return any(k == 'disallow' and v == '/' for k, v in rules) and not any(k == 'allow' and v == '/' for k, v in rules)


def surface_url(site_url: str, build: Path, page: Path) -> str:
    r = page.resolve().relative_to(build.resolve()).as_posix()
    r = re.sub(r'(^|/)index\.html?$', r'\1', r)
    return site_url.rstrip('/') + '/' + r


def url_norm(u: str) -> str:
    pr = urllib.parse.urlparse(u.strip())
    path = re.sub(r'(/index)?\.html?$', '', pr.path).rstrip('/')
    return f'{pr.netloc.lower()}{path}'


def sitemap_locs(build: Path, site_host: str, start: list, seen=None) -> tuple[list[str], list[str]]:
    """Every <loc> of the local sitemaps, following a sitemap index; and the errors."""
    seen = seen if seen is not None else set()
    locs, errs = [], []
    for f in start:
        if f in seen:
            continue
        seen.add(f)
        name = f.relative_to(build).as_posix()
        if not f.exists():
            errs.append(f'{name} is named as a sitemap but is not in the build')
            continue
        text = read_text(f)
        if not re.search(r'<(urlset|sitemapindex)\b', text):
            errs.append(f'{name} is not a sitemap (no <urlset> or <sitemapindex>)')
            continue
        found = [_html.unescape(x).strip() for x in re.findall(r'<loc>\s*(.*?)\s*</loc>', text, re.S)]
        if re.search(r'<sitemapindex\b', text):
            child = [build / urllib.parse.urlparse(u).path.lstrip('/') for u in found
                     if urllib.parse.urlparse(u).netloc.lower() == site_host]
            l2, e2 = sitemap_locs(build, site_host, child, seen)
            locs += l2
            errs += e2
        else:
            locs += found
    return locs, errs


def site_checks(args, b: dict) -> tuple[list[str], list[str]]:
    """Flags (they block the report) and notes (they go to Pending) on robots.txt, the sitemap and llms.txt."""
    root = root_dir(args)
    bd = b['build_dir']
    build = root / bd
    site_url = str(b.get('site_url') or '')
    site_host = urllib.parse.urlparse(site_url).netloc.lower()
    flags, notes = [], []
    sitemap_files = []
    rb = build / 'robots.txt'
    if not rb.exists():
        flags.append(f'no robots.txt in {bd}; publish one that allows crawling and names the sitemap')
    else:
        groups, sitemaps = parse_robots(read_text(rb))
        on_purpose = {x.lower() for x in b.get('ai_crawlers_blocked', [])}
        if robots_blocks(groups, '*'):
            flags.append('robots.txt shuts out every crawler it does not name (User-agent: * with Disallow: /)')
        for bot in SEARCH_BOTS:
            if robots_blocks(groups, bot) and bot.lower() not in on_purpose:
                flags.append(f'robots.txt blocks {bot}, so the site cannot be shown or quoted through it; allow it, '
                             f'or list it in brief.ai_crawlers_blocked if that is deliberate')
        blocked_training = [bot for bot in TRAINING_BOTS if robots_blocks(groups, bot)]
        if blocked_training:
            notes.append('robots.txt blocks training crawlers (' + ', '.join(blocked_training) + '): the content stays '
                         'out of model training; search is not affected')
        if not sitemaps:
            flags.append('robots.txt has no Sitemap: line; name the sitemap there with its full URL')
        for u in sitemaps:
            pr = urllib.parse.urlparse(u)
            if site_host and pr.netloc.lower() != site_host:
                flags.append(f'robots.txt names a sitemap on {pr.netloc}, but the site answers at {site_host}')
            else:
                sitemap_files.append(build / pr.path.lstrip('/'))
    if not sitemap_files:
        sitemap_files = [f for f in (build / 'sitemap.xml', build / 'sitemap-index.xml', build / 'sitemap_index.xml')
                         if f.exists()]
    if not sitemap_files:
        flags.append(f'no sitemap in {bd}; list every page there, each language version included')
    else:
        locs, errs = sitemap_locs(build, site_host, sitemap_files)
        flags += errs
        listed = {url_norm(u) for u in locs}
        for s in b.get('surfaces', []):
            u = surface_url(site_url, build, root / s['path'])
            if url_norm(u) not in listed:
                flags.append(f'the sitemap does not list {u} ({s["path"]})')
    lt = build / 'llms.txt'
    if not lt.exists():
        notes.append('no llms.txt: AI assistants and agents read it to find the important pages (Google Search does '
                     'not use it); worth adding to a docs or product site')
    else:
        text = read_text(lt).lstrip('﻿')
        first = next((l for l in text.splitlines() if l.strip()), '')
        if not re.match(r'#\s+\S', first):
            flags.append('llms.txt does not start with an H1 (# Name), as llmstxt.org asks')
        if not re.search(r'\[[^\]]+\]\([^)]+\)', text):
            flags.append('llms.txt links no page; list the important ones as - [Title](url): note')
    return flags, notes


def audit_pages(args, pages: dict, gh, km) -> dict:
    result = {'at': _dt.datetime.now().isoformat(timespec='seconds'), 'map_hash': map_hash(km),
              'surfaces': {}, 'placements': [], 'missing': [], 'flags': [], 'github': gh}
    brief = load(eco_dir(args) / 'brief.json', {})
    name = (brief.get('project', {}) or {}).get('name', '')
    site_host = urllib.parse.urlparse(str(brief.get('site_url') or '')).netloc.lower()
    html_langs = {s['lang'] for s, _, _ in pages.values() if s['kind'] == 'html'}
    for path, (s, pg, digest) in pages.items():
        info = {'kind': s['kind'], 'lang': s['lang'], 'hash': digest, 'h1': pg.get('h1', [])[:3],
                'lead': pg.get('lead', '')[:200], 'words': len(words(pg['body'])),
                'links': sorted(set(pg.get('links', []))), 'anchors': sorted(set(pg.get('anchors', []))),
                'code': sorted(set(pg.get('code', []))), 'headings': pg.get('headings_all', []),
                'claims': extract_claims(' . '.join([pg.get('title', ''), pg.get('meta', ''), pg['body'], pg.get('jsonld', '')]))}
        if s['kind'] == 'html':
            info.update(title=pg['title'], meta=pg['meta'])
            # Google publishes no length limit; results cut by pixel width, at roughly these lengths.
            if not TITLE_RANGE[0] <= len(pg['title']) <= TITLE_RANGE[1]:
                result['flags'].append(f'{path}: title is {len(pg["title"])} characters; aim for {TITLE_RANGE[0]}-{TITLE_RANGE[1]} '
                                       f'(a display heuristic: longer titles may be cut in results)')
            if not META_RANGE[0] <= len(pg['meta']) <= META_RANGE[1]:
                result['flags'].append(f'{path}: meta description is {len(pg["meta"])} characters; aim for {META_RANGE[0]}-{META_RANGE[1]} '
                                       f'(a display heuristic: longer snippets may be cut)')
            if len(pg['h1']) != 1:
                result['flags'].append(f'{path}: {len(pg["h1"])} h1 elements; a page needs exactly one')
            if not any(k == 'canonical' for k, _ in pg.get('urls', [])):
                result['flags'].append(f'{path}: no <link rel="canonical">')
            for kind, u in pg.get('urls', []):
                host = urllib.parse.urlparse(u).netloc.lower()
                if site_host and host and host != site_host:
                    result['flags'].append(f'{path}: {kind} points to {host}, but the site answers at {site_host}')
            result['flags'] += [f'{path}: {f}' for f in html_checks(pg, s['lang'], html_langs)]
        else:
            if len(pg['h1']) > 1:
                result['flags'].append(f'{path}: {len(pg["h1"])} H1 headings; a README needs one, the first')
            if pg.get('keyword_lines'):
                info['keyword_lines'] = pg['keyword_lines']
        result['surfaces'][path] = info
        # "<Name> is a <phrase>" again and again reads as written for a crawler.
        if name:
            phrases = [k['phrase'] for k in km.get('keywords', []) if k.get('tier') != 'discarded' and k['lang'] == s['lang']]
            pat = _pattern(phrases)
            if pat:
                is_a = re.findall(r'(?<!\w)' + re.escape(norm(name)) + r'(?: (?:is|es|est|ist)|,|:) (?:a|an|un|una|une|ein|eine) ([^.!?;]{0,80})',
                                  norm(pg['body']))
                forced = [x for x in is_a if pat.search(flat(x))]
                if len(forced) > IS_A_CAP:
                    result['flags'].append(f'{path}: {len(forced)} sentences of the form "{name} is a <keyword>"; '
                                           f'keep {IS_A_CAP} at most and say the rest another way')
    for k in km.get('keywords', []):
        if k.get('tier') == 'discarded':
            continue
        variants = [k['phrase']] + list(k.get('variants', []))
        for pl in k.get('placements', []):
            targets = []
            if pl in GITHUB_PLACEMENTS:
                if gh is not None:
                    where = 'github (proposed)' if gh.get('source') == 'offsite proposal' else 'github'
                    targets.append((where, [gh['about']] if pl == 'about' else gh['topics']))
            else:
                for path, (s, pg, _) in pages.items():
                    if s['lang'] != k['lang']:
                        continue
                    if (s['kind'] == 'html' and pl in HTML_PLACEMENTS) or (s['kind'] == 'readme' and pl in README_PLACEMENTS):
                        targets.append((path, field_items(pg, pl)))
            for where, items in targets:
                n = count_items(items, variants)
                row = {'phrase': k['phrase'], 'lang': k['lang'], 'tier': k['tier'], 'placement': pl, 'surface': where, 'count': n}
                result['placements'].append(row)
                if n == 0:
                    result['missing'].append(row)
        for path, (s, pg, _) in pages.items():
            if s['lang'] != k['lang']:
                continue
            body_words = max(1, len(words(pg['body'])))
            n = count_in(pg['body'], variants)
            share = n * len(words(k['phrase'])) / body_words
            if share > DENSITY_CAP and n > 2:
                result['flags'].append(f'{path}: "{k["phrase"]}" takes {share:.1%} of the visible words (cap {DENSITY_CAP:.0%}); it reads as stuffing')
            heads = (pg.get('h2', []) + pg.get('h3', [])) if s['kind'] == 'html' else pg.get('heading', [])
            if len(heads) >= 3:  # noqa: SIM102
                hn = sum(1 for h in heads if count_in(h, variants))
                if hn >= 2 and hn / len(heads) > HEADING_SHARE_CAP:
                    result['flags'].append(f'{path}: "{k["phrase"]}" is in {hn} of {len(heads)} headings; vary them')
    # A primary has to be in the shipped text: the title, H1 or lead of a file, or an About that is live.
    for k in km.get('keywords', []):
        if k.get('tier') != 'primary':
            continue
        strong = [r for r in result['placements'] if r['phrase'] == k['phrase'] and r['lang'] == k['lang'] and r['count'] > 0
                  and (r['placement'] in ('title', 'h1', 'lead') or (r['placement'] == 'about' and r['surface'] == 'github'))]
        if not strong and any(r['phrase'] == k['phrase'] and r['count'] > 0 for r in result['placements']):
            result['flags'].append(f'primary "{k["phrase"]}" is not in any title, H1 or lead, nor in a live About '
                                   f'(an unapplied proposal does not ship)')
    if gh is not None:
        if len(gh['about']) > ABOUT_MAX:
            result['flags'].append(f'GitHub About is {len(gh["about"])} characters; the limit is {ABOUT_MAX}')
        if len(gh['topics']) > TOPICS_MAX:
            result['flags'].append(f'{len(gh["topics"])} GitHub topics; the limit is {TOPICS_MAX}')
    elif any(set(k.get('placements', [])) & GITHUB_PLACEMENTS for k in km.get('keywords', []) if k.get('tier') != 'discarded'):
        result['flags'].append('the map places keywords in the GitHub About or topics, but there is neither an `offsite` '
                               'proposal nor brief.github.about_file to audit them against')
    return result


def run_audit(args, original=False) -> dict:
    d = eco_dir(args)
    b = load(d / 'brief.json', {})
    km = load(d / 'keywords.json', {'keywords': []})
    pages = {}
    for s in b.get('surfaces', []):
        p = (d / 'original' / s['path']) if original else (root_dir(args) / s['path'])
        if not p.exists():
            die(f'{p} not found' + (' (run `eco.py brief` before editing to keep the original)' if original else ''))
        pages[s['path']] = (s, parse_surface(p, s['kind']), sha(p))
    gh = None if original else github_page(args, b)
    if original and b.get('github', {}).get('about_file') and (root_dir(args) / b['github']['about_file']).exists():
        g = json.loads(read_text(root_dir(args) / b['github']['about_file']))
        topics = [t['name'] if isinstance(t, dict) else t for t in (g.get('repositoryTopics') or g.get('topics') or [])]
        gh = {'about': g.get('description') or '', 'topics': [t.replace('-', ' ') for t in topics], 'source': 'live'}
    r = audit_pages(args, pages, gh, km)
    r['notes'] = []
    if args.mode == 'site' and not original:
        # robots.txt, the sitemap and llms.txt have no original copy: they are checked on the current build only.
        flags, r['notes'] = site_checks(args, b)
        r['flags'] += flags
    return r


def cmd_audit(args):
    if args.save == 'baseline':
        r = run_audit(args, original=True)
        print('baseline: auditing the originals kept by `eco.py brief`, not the current files')
    else:
        r = run_audit(args)
    total = len(r['placements'])
    hit = total - len(r['missing'])
    for path, s in r['surfaces'].items():
        extra = f"title {len(s.get('title', ''))} ch, meta {len(s.get('meta', ''))} ch" if s['kind'] == 'html' else f"lead: {s.get('lead', '')[:60]!r}"
        print(f'{path} [{s["lang"]}] {s["words"]} words; {extra}')
        for l in s.get('keyword_lines', []):
            print(f'  NOTE keyword list not counted as text: {l[:80]!r}')
    print(f'placements: {hit}/{total}')
    for m in r['missing']:
        print(f"  {'MISSING' if m['tier'] == 'primary' else 'not placed'} [{m['tier']}] {m['phrase']!r} in {m['placement']} of {m['surface']}")
    for f in r['flags']:
        print(f'  FLAG {f}')
    for n in r.get('notes', []):
        print(f'  NOTE {n} (goes to Pending in the report)')
    if args.save != 'baseline':
        nc = new_claims(run_audit(args, original=True), r)
        todo = [c for c in nc if c['claim'] not in state(args).get('claims', {})]
        if todo:
            print(f'  {len(todo)} new claims to check before the report (`eco.py claims`): '
                  + ', '.join(repr(c['claim']) for c in todo[:8]))
    if args.save:
        if args.save == 'pre-quiron' and state(args)['steps'].get('quiron', {}).get('status') == 'used':
            bad('Quirón is already recorded as used; the pre-quiron snapshot cannot be taken again. '
                'To start the humanizing step over, run `eco.py quiron reset` and redo the pass')
            sys.exit(1)
        if args.save == 'final':
            pre = load(eco_dir(args) / 'audit-pre-quiron.json')
            if pre and pre['map_hash'] != r['map_hash']:
                bad('keywords.json changed after the pre-quiron snapshot; the map is fixed once text is edited. '
                    'Put the phrases back in the map or redo the pre-quiron audit before the humanizing pass')
                sys.exit(1)
        save(eco_dir(args) / f'audit-{args.save}.json', r)
        print(f'saved {rel(args)}/audit-{args.save}.json')
        mark(args, f'audit-{args.save}', placements=f'{hit}/{total}', flags=len(r['flags']),
             surfaces={p: s['hash'] for p, s in r['surfaces'].items()})
    if args.save == 'baseline':
        sys.exit(0)
    primary_missing = [m for m in r['missing'] if m['tier'] == 'primary']
    sys.exit(1 if (primary_missing or r['flags'] or (args.strict and r['missing'])) else 0)


def compare(a: dict, b: dict) -> list[dict]:
    key = lambda p: (p['phrase'], p['lang'], p['placement'], p['surface'])  # noqa: E731
    had = {key(p) for p in a['placements'] if p['count'] > 0}
    now = {key(p): p for p in b['placements']}
    return [dict(zip(('phrase', 'lang', 'placement', 'surface'), k)) for k in sorted(had) if k not in now or now[k]['count'] == 0]


def integrity(a: dict, b: dict) -> dict:
    """Links, anchors and inline code present in a and gone in b, per surface. Anchors that
    something in b still links to (#anchor) are errors; the rest is listed for the report."""
    out = {}
    for path, sa in a['surfaces'].items():
        sb = b['surfaces'].get(path)
        if not sb:
            continue
        gone = {k: sorted(set(sa.get(k, [])) - set(sb.get(k, []))) for k in ('links', 'anchors', 'code')}
        had, has = set(sa.get('anchors', [])), set(sb.get('anchors', []))
        gone['broken_internal'] = sorted(l for l in set(sb.get('links', []))
                                         if l.startswith('#') and l[1:] in had and l[1:] not in has)
        if any(gone.values()):
            out[path] = gone
    return out


def cmd_compare(args):
    d = eco_dir(args)
    a, b = load(d / f'audit-{args.before}.json'), load(d / f'audit-{args.after}.json')
    if a is None or b is None:
        die(f'need .eco/audit-{args.before}.json and .eco/audit-{args.after}.json (run audit --save)')
    lost = compare(a, b)
    for l in lost:
        bad(f"lost {l['phrase']!r} [{l['lang']}] from {l['placement']} of {l['surface']}")
    integ = integrity(a, b)
    broken = 0
    for path, g in integ.items():
        for x in g['broken_internal']:
            bad(f'{path}: link {x} points to a heading that no longer exists; keep the old anchor (<a id="{x[1:]}"></a>)')
            broken += 1
        for k in ('links', 'anchors', 'code'):
            if g[k]:
                warn(f"{path}: {k} gone: {', '.join(g[k][:8])}{' ...' if len(g[k]) > 8 else ''}")
    if lost or broken:
        if lost:
            print(f'{len(lost)} placements lost between {args.before} and {args.after}: put the keywords back with the smallest edit')
        sys.exit(1)
    ok(f'no keyword placement lost and no internal link broken between {args.before} and {args.after}')
    mark(args, f'compare-{args.before}-{args.after}', lost=0)


# ---------------------------------------------------------------- claims

# Statements a reader can check: numbers with a unit, percentages, multipliers, years,
# superlatives. Matched in any language for the digits; the words are English.
CLAIM_PATTERNS = [
    r'\d+(?:[.,]\d+)?\s?%',
    r'\d+(?:[.,]\d+)?\s?[x×](?!\w)',
    r'(?:twice|\w+ times) (?:as|faster|smaller|cheaper|fewer|more|less)\b',
    r'(?:more than|over|up to|at least|less than|under|nearly|almost) \d+(?:[.,]\d+)*\+?(?: ?[km]\b)?',
    r'\d+(?:[.,]\d+)*\s?(?:[km]\+?|\+)?\s?(?:million|billion|thousand)?\s?(?:users|stars|downloads|installs|companies|teams|'
    r'developers|sites|websites|pages|projects|repos|repositories|languages|countries|customers|requests|queries|'
    r'tests|agents|skills|checks|commands|ms|milliseconds|seconds|minutes|hours|kb|mb|gb)\b',
    r'\d+(?:[.,]\d+)?\s?(?:million|billion|thousand|[km])\b(?![.\-]\d)',
    r'(?<![\w.\-])(?:19|20)\d{2}(?!\w|[.\-]\d)',
    r'\b(?:fastest|cheapest|most popular|number one|world\'s first|the first (?:tool|skill|library|plugin))\b',
    r'#1\b',
]
CLAIM_RE = re.compile('|'.join(f'(?:{p})' for p in CLAIM_PATTERNS), re.I)


def extract_claims(text: str) -> list[list[str]]:
    """[claim, sentence] pairs; the claim is the key a verification is recorded under."""
    t = re.sub(r'\s+', ' ', text or '')
    out, seen = [], set()
    for m in CLAIM_RE.finditer(t):
        key = norm(m.group(0))
        start = max(t.rfind('. ', 0, m.start()) + 2, m.start() - 120, 0)
        end = t.find('. ', m.end())
        end = min(end + 1 if end >= 0 else len(t), m.end() + 120)
        if key not in seen:
            seen.add(key)
            out.append([key, t[start:end].strip()])
    return out


def new_claims(base: dict, now: dict) -> list[dict]:
    """Claims in the current text that no original surface made."""
    had = {c for s in base['surfaces'].values() for c, _ in s.get('claims', [])}
    out = []
    for path, s in now['surfaces'].items():
        for c, ctx in s.get('claims', []):
            if c not in had:
                out.append({'claim': c, 'context': ctx, 'surface': path})
    return out


def cmd_claims(args):
    st = state(args)
    checked = st.setdefault('claims', {})
    if args.action == 'verify':
        if not args.claim or not args.source:
            die('claims verify needs --claim (as `eco.py claims` lists it) and --source (a file in the project or a URL)')
        key = norm(args.claim)
        listed = {c['claim'] for c in new_claims(run_audit(args, original=True), run_audit(args))}
        if key not in listed:
            die(f'{key!r} is not a new claim; `eco.py claims` lists them')
        if not re.match(r'https?://', args.source):
            src = root_dir(args) / args.source
            if not src.is_file():
                die(f'{args.source} is not a file in the project')
            digits = re.findall(r'\d+(?:[.,]\d+)?', key)
            body = read_text(src)
            gone = [x for x in digits if not re.search(r'(?<![\d.,])' + re.escape(x) + r'(?![\d])', body)]
            if gone:
                die(f'{args.source} does not contain {", ".join(gone)}; point at the file that states it, or fix the text')
            if not digits and not args.note:
                die('a claim without a number (a superlative) needs --note saying how the source supports it')
        checked[key] = {'source': args.source, 'note': args.note or '', 'at': _dt.datetime.now().isoformat(timespec='seconds')}
        save(eco_dir(args) / 'state.json', st)
        ok(f'{key!r} checked against {args.source}')
        return
    claims = new_claims(run_audit(args, original=True), run_audit(args))
    if not claims:
        ok('no new claims: no number, percentage, year or superlative the original text did not make')
        return
    for c in claims:
        mark_ = f"checked: {checked[c['claim']]['source']}" if c['claim'] in checked else 'NOT CHECKED'
        print(f"  {c['claim']!r} in {c['surface']} [{mark_}]: {c['context'][:160]}")
    todo = [c for c in claims if c['claim'] not in checked]
    if todo:
        print(f'{len(todo)} new claims to check: `eco.py claims verify --claim "..." --source FILE|URL`')
        sys.exit(1)
    ok(f'{len(claims)} new claims, every one checked against a source')


# ---------------------------------------------------------------- Lighthouse

# The target is 100 in every category. An audit that carries weight in a category and scores
# under 1 is "open": it is fixed, or recorded with `lighthouse waive` as a technical ceiling or a
# change the user declined. Weight-0 diagnostics are shown as hints, since they say where the
# time goes but do not move a score by themselves.
LH_CATEGORIES = ('performance', 'accessibility', 'best-practices', 'seo')
LH_SKIP_MODES = {'notApplicable', 'manual', 'informative', 'error'}
# Lab thresholds for "good" (web.dev/articles/vitals). TBT stands in for INP, which only field
# data has: say "lab" whenever these are shown.
CWV_GOOD = {'largest-contentful-paint': (2500, 'LCP', 'ms'), 'cumulative-layout-shift': (0.1, 'CLS', ''),
            'total-blocking-time': (200, 'TBT', 'ms')}
# Audits that only fail because a local server speaks plain HTTP; production decides them.
LOCAL_ONLY = {'is-on-https', 'redirects-http'}
LOCAL_HOSTS = {'localhost', '127.0.0.1', '[::1]', '::1', '0.0.0.0'}
WAIVE_KINDS = ('ceiling', 'declined')


def route_key(path: str) -> str:
    return re.sub(r'(/index)?\.html?$', '', urllib.parse.urlparse(path).path).strip('/')


def is_local(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    return host in LOCAL_HOSTS or host.endswith('.localhost')


def fetch_page(url: str) -> str:
    """The HTML production serves for one URL. Kept small so tests can replace it."""
    req = urllib.request.Request(url, headers={'User-Agent': 'eco-site-check/' + VERSION, 'Accept': 'text/html'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')


def page_fingerprint(pg: dict) -> dict:
    return {'title': flat(pg.get('title', '')), 'meta': flat(pg.get('meta', '')),
            'h1': [flat(h) for h in pg.get('h1', [])], 'body': flat(pg.get('body', ''))}


def production_differs(args, b: dict, url: str) -> list[str]:
    """Surfaces whose live text differs from the build: a scan of production measures them only
    once the changes are deployed."""
    root = root_dir(args)
    build = root / b['build_dir']
    out = []
    for s in b.get('surfaces', []):
        live_url = surface_url(url, build, root / s['path'])
        try:
            live = page_fingerprint(parse_html(fetch_page(live_url)))
        except (OSError, ValueError) as e:
            out.append(f'{s["path"]}: {live_url} did not answer ({e})')
            continue
        built = page_fingerprint(parse_html(read_text(root / s['path'])))
        diff = [k for k in built if built[k] != live[k]]
        if diff:
            out.append(f'{s["path"]}: production differs from the build in {", ".join(diff)}')
    return out


def read_lighthouse_run(out: Path) -> tuple[list[dict], dict]:
    res = out / 'ci-result.json'
    data = json.loads(read_text(res))
    rows = []
    for r in data.get('routes') or []:
        path = r.get('path', '/')
        row = {'path': path, 'categories': {k: (v or {}).get('score') for k, v in (r.get('categories') or {}).items()},
               'metrics': {k: (v or {}).get('numericValue') for k, v in (r.get('metrics') or {}).items()},
               'open': [], 'hints': []}
        rep_file = out / 'reports' / path.strip('/') / 'lighthouse.json'
        if rep_file.exists():
            lh = json.loads(read_text(rep_file))
            for cat in LH_CATEGORIES:
                for ref in (lh.get('categories', {}).get(cat, {}) or {}).get('auditRefs', []):
                    a = lh.get('audits', {}).get(ref.get('id'), {})
                    if a.get('scoreDisplayMode') in LH_SKIP_MODES or a.get('score') is None:
                        continue
                    item = {'id': ref['id'], 'category': cat, 'score': a['score'], 'title': a.get('title', ''),
                            'display': a.get('displayValue', '')}
                    if ref.get('weight', 0) > 0 and a['score'] < 1:
                        row['open'].append(item)
                    elif ref.get('weight', 0) == 0 and a['score'] < 0.9:
                        row['hints'].append(item)
        else:
            for cat in LH_CATEGORIES:
                sc = row['categories'].get(cat)
                if sc is not None and sc < 1:
                    row['open'].append({'id': f'{cat}-score', 'category': cat, 'score': sc,
                                        'title': f'{cat} {round(sc * 100)} (no per-page report to name the audits)', 'display': ''})
        rows.append(row)
    summary = {k: (v or {}).get('averageScore') for k, v in ((data.get('summary') or {}).get('categories') or {}).items()}
    return rows, summary


def waived(st: dict, audit: str, path: str) -> dict | None:
    for w in st.get('waivers', []):
        if w['audit'] == audit and (not w.get('path') or route_key(w['path']) == route_key(path)):
            return w
    return None


def lighthouse_open(st: dict, rec: dict) -> list[str]:
    """Open audits of a final run that are neither fixed nor waived."""
    out = []
    for r in rec['routes']:
        for a in r['open']:
            if rec['local'] and a['id'] in LOCAL_ONLY:
                continue
            if not waived(st, a['id'], r['path']):
                out.append(f"{r['path']} {a['category']}: {a['id']} ({a['title']}"
                           + (f", {a['display']}" if a.get('display') else '') + ')')
    return out


def cmd_lighthouse(args):
    d = eco_dir(args)
    b = load(d / 'brief.json')
    if b is None or check_brief(args):
        die('the brief is not complete: run eco.py brief first')
    st = state(args)
    if args.action == 'waive':
        if not args.audit or not args.reason or not args.kind:
            die('waive needs --audit, --kind ceiling|declined and --reason')
        st.setdefault('waivers', [])
        st['waivers'] = [w for w in st['waivers'] if not (w['audit'] == args.audit and w.get('path') == args.path)]
        st['waivers'].append({'audit': args.audit, 'path': args.path, 'kind': args.kind, 'reason': args.reason})
        save(d / 'state.json', st)
        ok(f'{args.audit} recorded as {args.kind}' + (f' on {args.path}' if args.path else ' on every page'))
        return
    if not args.url or not args.stage:
        die('lighthouse needs --stage baseline|final and --url')
    root = root_dir(args)
    out = root / args.dir
    if not (out / 'ci-result.json').exists():
        die(f'{out / "ci-result.json"} not found. Run Unlighthouse from {root} (see the skill, step 7), then this again')
    local = is_local(args.url)
    if args.stage == 'baseline':
        if local:
            changed = [s['path'] for s in b['surfaces'] if sha(root / s['path']) != sha(d / 'original' / s['path'])]
            if changed:
                die('a local baseline must scan the build as it was before any edit, and these pages changed: '
                    + ', '.join(changed))
        elif urllib.parse.urlparse(args.url).hostname != urllib.parse.urlparse(b['site_url']).hostname:
            warn(f'{args.url} is not site_url ({b["site_url"]}); recorded as a remote baseline')
    else:
        final = load(d / 'audit-final.json')
        if final is None:
            die('the final Lighthouse run comes after `audit --save final`')
        if not local:
            diff = production_differs(args, b, args.url)
            if diff:
                for x in diff:
                    bad(x)
                die('production does not serve the final pages yet: scan the local build instead (step 7), or deploy first',
                    code=1)
    rows, summary = read_lighthouse_run(out)
    if not rows:
        die(f'{out / "ci-result.json"} has no routes: Unlighthouse scanned nothing')
    flags = []
    site_url = str(b.get('site_url') or '')
    scanned = {route_key(r['path']) for r in rows}
    build = root / b['build_dir']
    for sf in b.get('surfaces', []):
        key = route_key(surface_url(site_url, build, root / sf['path']))
        if key not in scanned:
            flags.append(f'Unlighthouse did not scan /{key} ({sf["path"]}); pass it in --urls')
    notes = []
    for r in rows:
        for k, (limit, label, unit) in CWV_GOOD.items():
            v = r['metrics'].get(k)
            if v is not None and v > limit:
                shown = f'{v / 1000:.1f} s' if unit == 'ms' and v >= 1000 else (f'{v:.0f} ms' if unit == 'ms' else f'{v:.2f}')
                notes.append(f'{r["path"]}: lab {label} {shown} (good is under {limit}{unit and " " + unit})')
    rec = {'at': _dt.datetime.now().isoformat(timespec='seconds'), 'stage': args.stage, 'url': args.url, 'local': local,
           'surfaces': {sf['path']: sha(root / sf['path']) for sf in b.get('surfaces', [])},
           'summary': summary, 'routes': rows, 'flags': flags, 'notes': notes}
    save(d / f'lighthouse-{args.stage}.json', rec)
    where = 'local build' if local else 'production'
    print(f'{args.stage}: {len(rows)} pages scanned on {where} ({args.url})')
    print('averages: ' + ', '.join(f'{k} {round(v * 100)}' for k, v in summary.items() if v is not None))
    for r in rows:
        print(f"{r['path']}: " + ', '.join(f'{k} {round(v * 100)}' for k, v in r['categories'].items() if v is not None))
        for a in r['open']:
            tag = 'local only' if local and a['id'] in LOCAL_ONLY else (
                f"waived: {waived(st, a['id'], r['path'])['kind']}" if waived(st, a['id'], r['path']) else 'OPEN')
            print(f"  {tag:<12} {a['category']}: {a['id']} {a['score']} {a['title']}" + (f" ({a['display']})" if a.get('display') else ''))
        for a in r['hints'][:12]:
            print(f"  hint         {a['category']}: {a['id']} {a['title']}" + (f" ({a['display']})" if a.get('display') else ''))
    for n in notes:
        warn(n)
    for f in flags:
        bad(f)
    mark(args, f'lighthouse-{args.stage}', routes=len(rows), where=where)
    left = lighthouse_open(st, rec)
    if args.stage == 'final' and (flags or left):
        print(f'{len(left)} open audits: fix them, or record a technical ceiling or a declined change with '
              f'`eco.py lighthouse waive --audit ID --kind ceiling|declined --reason "..."`')
        sys.exit(1)
    ok(f'{args.stage} recorded' + ('' if args.stage == 'baseline' else '; every audit passes or is waived'))


# ---------------------------------------------------------------- Quirón

# used: it ran on the new text. skipped: it is installed and the user said no. not-installed: Eco
# never installs it; the closing message recommends it instead.
QUIRON_STATUSES = ('used', 'skipped', 'not-installed')


def quiron_installed(root: Path) -> list[str]:
    home = Path.home()
    found = []
    reg = home / '.claude' / 'plugins' / 'installed_plugins.json'
    if reg.exists():
        try:
            data = json.loads(read_text(reg))
            for key, entries in (data.get('plugins') or {}).items():
                if key.split('@')[0] == 'quiron':
                    for e in entries if isinstance(entries, list) else [entries]:
                        p = Path(e.get('installPath', '')) if isinstance(e, dict) else None
                        if p and p.exists() and next(p.rglob('SKILL.md'), None):
                            found.append(str(p))
        except (ValueError, OSError, AttributeError):
            pass
    for p in (home / '.claude' / 'skills' / 'quiron', home / '.agents' / 'skills' / 'quiron',
              home / '.codex' / 'skills' / 'quiron', root / '.claude' / 'skills' / 'quiron',
              root / '.agents' / 'skills' / 'quiron'):
        if (p / 'SKILL.md').exists():
            found.append(str(p))
    return found


def cmd_quiron(args):
    if args.action == 'detect':
        found = quiron_installed(root_dir(args))
        print(json.dumps({'installed': bool(found), 'paths': found}, indent=2))
        print('# also check the skills listed in this session for "quiron"', file=sys.stderr)
        mark(args, 'quiron-detect', installed=bool(found))
        return
    if args.action == 'reset':
        st = state(args)
        st['steps'].pop('quiron', None)
        st['log'].append({'at': _dt.datetime.now().isoformat(timespec='seconds'), 'step': 'quiron-reset'})
        save(eco_dir(args) / 'state.json', st)
        ok('Quirón record cleared; take a new pre-quiron snapshot before the pass')
        return
    if not args.status:
        die('quiron record needs --status')
    if args.status == 'used':
        pre = load(eco_dir(args) / 'audit-pre-quiron.json')
        if pre is None:
            die('record Quirón as used only after `audit --save pre-quiron` and the pass itself')
        now = run_audit(args)
        changed = [p for p, s in now['surfaces'].items() if pre['surfaces'].get(p, {}).get('hash') != s['hash']]
        if not changed and not args.unchanged:
            die('the surfaces are byte-identical to the pre-quiron snapshot; if Quirón really changed nothing, pass --unchanged')
        if not args.result:
            die('pass --result with Quirón\'s own one-line result (features in band, FAIL/TELL, converged)')
    pre = load(eco_dir(args) / 'audit-pre-quiron.json')
    mark(args, 'quiron', status=args.status, result=args.result or '',
         pre=({p_: s_['hash'] for p_, s_ in pre['surfaces'].items()} if pre else None))
    ok(f'Quirón: {args.status}')


# ---------------------------------------------------------------- off-site and pending

def cmd_offsite(args):
    topics = [t.strip() for t in (args.topics or '').split(',') if t.strip()]
    errs = []
    if args.about and len(args.about) > ABOUT_MAX:
        errs.append(f'About is {len(args.about)} characters; GitHub allows {ABOUT_MAX}')
    if len(topics) > TOPICS_MAX:
        errs.append(f'{len(topics)} topics; GitHub allows {TOPICS_MAX} in total, existing ones included')
    for t in topics:
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,49}', t):
            errs.append(f'topic {t!r}: lowercase letters, digits and hyphens, at most 50 characters')
    for e in errs:
        bad(e)
    if errs:
        sys.exit(1)
    st = state(args)
    st['offsite'] = {'about': args.about, 'topics': topics, 'homepage': args.homepage, 'applied': args.applied}
    save(eco_dir(args) / 'state.json', st)
    ok('off-site proposal recorded' + (' (applied)' if args.applied else ' (proposed)'))


def cmd_pending(args):
    st = state(args)
    st['pending'].append(args.text)
    save(eco_dir(args) / 'state.json', st)
    ok('pending item recorded')


# ---------------------------------------------------------------- track: positions before and after publishing

# A position can only move once the new text is public, so nothing here runs inside the main flow: the
# research saves where the project stands (github.json, serp.json), and `track` repeats the same searches
# after publishing. Each row gets a verdict; a row that cannot be measured says so instead of guessing.
TRACK_SETTLE = {'github': 3, 'serp': 14}    # days after publishing before "no change" counts as a result
SERP_NOISE = 2                              # places a results page moves by itself between two fetches
GSC_MIN_IMPRESSIONS = 10                    # under this, an average position is a handful of searches
GSC_MIN_MOVE = 1.0                          # average-position change that counts
IMPROVED, WORSE = ('up', 'entered'), ('down', 'left')
VERDICTS = {'up': 'improved', 'entered': 'improved: now in the results', 'down': 'worse', 'left': 'worse: no longer in the results',
            'same': 'no change', 'out': 'still outside the results', 'early': 'too early to tell', 'thin': 'not enough data'}
TRACK_SOURCES = {'github': 'GitHub search', 'ddg': 'DuckDuckGo', 'bing': 'Bing', 'gsc': 'Google (Search Console)'}


def _day(s) -> _dt.date:
    return _dt.date.fromisoformat(str(s)[:10])


def rank_verdict(before, after, noise: int = 1) -> str:
    if before is None and after is None:
        return 'out'
    if before is None:
        return 'entered'
    if after is None:
        return 'left'
    if before - after >= noise:
        return 'up'
    if after - before >= noise:
        return 'down'
    return 'same'


def fetch_readme(repo: str, path: str) -> str:
    """The README GitHub shows today, on the default branch. Goes through fetch_page so tests can replace it."""
    return fetch_page(f'https://raw.githubusercontent.com/{repo}/HEAD/{urllib.parse.quote(path)}')


def _readme_print(pg: dict) -> dict:
    return {k: flat(' '.join(pg[k]) if isinstance(pg[k], list) else pg[k]) for k in ('h1', 'lead', 'body')}


def live_check(args, b: dict) -> list[str]:
    """Why the published copy is not the text this run left; empty when it is. A position measured
    while the old text is still public would describe the old text."""
    root = root_dir(args)
    if args.mode == 'site':
        return production_differs(args, b, b['site_url'])
    repo = str((b.get('github') or {}).get('repo') or '').strip('/')
    out = []
    for s in b.get('surfaces', []):
        if s['kind'] != 'readme':
            continue
        try:
            live = _readme_print(parse_readme(fetch_readme(repo, s['path'])))
        except (OSError, ValueError) as e:
            out.append(f'{s["path"]}: github.com/{repo} did not answer ({e})')
            continue
        mine = _readme_print(parse_readme(read_text(root / s['path'])))
        diff = [k for k in mine if mine[k] != live[k]]
        if diff:
            out.append(f'{s["path"]}: github.com/{repo} still shows another text ({", ".join(diff)} differ)')
    return out


def about_not_live(args, b: dict) -> str | None:
    """Why GitHub's repository search cannot show this run yet. That search reads the name, the About
    and the topics, not the README, so only an applied `offsite` proposal can move a position there."""
    off = state(args).get('offsite') or {}
    if not (off.get('about') or off.get('topics')):
        return 'this run proposed no About or topics'
    repo = str((b.get('github') or {}).get('repo') or '').strip('/')
    try:
        g = json.loads(fetch_page(f'https://api.github.com/repos/{repo}'))
        about, topics = (g.get('description') or '').strip(), set(g.get('topics') or [])
    except (OSError, ValueError, AttributeError) as e:
        return f'api.github.com/repos/{repo} did not answer ({e})'
    if off.get('about') and about != off['about'].strip():
        return 'the About on github.com is not the proposed one'
    missing = [t for t in off.get('topics', []) if t not in topics]
    if missing:
        return 'the repository lacks the proposed topics ' + ', '.join(missing)
    return None


def track_target(args, b: dict) -> list[tuple[str, str]]:
    """The project's own addresses, or stop: with nothing published there is nothing to measure."""
    need = 'host' if args.mode == 'site' else 'repo'
    keys = own_keys(b)
    if not any(k[0] == need for k in keys):
        die('nothing published to measure: the brief has no ' + ('live site_url' if need == 'host' else 'GitHub repository')
            + '. The report already says the published copy was not checked', 2)
    return keys


def cmd_track_urls(args):
    d = eco_dir(args)
    track_target(args, load(d / 'brief.json', {}))
    gp = load(d / 'github-plan.json', {'queries': {}})['queries']
    sp = load(d / 'serp-plan.json', {'queries': {}})['queries']
    sq = load(d / 'serp.json', {'queries': {}})['queries']
    before = load(d / 'github.json', {'searches': []})['searches']
    n = 0
    for s in before:
        n += 1
        if s['label'] in gp:
            print(f"github/{s['label']}.json  {github_search_url(gp[s['label']])}")
        else:
            print(f"github/{s['label']}.json  # the search saved as {s['file']}: its query was not recorded, repeat it as it was")
    for slug, q in sp.items():
        if 'own_rank' in sq.get(slug, {}):
            print(f"serp/{slug}.html  {q['url']}")
            n += 1
    if not n:
        die("the research saved no search with the project's position in it, so there is no \"before\" to compare with", 2)
    print(f'# fetch each and save it as {rel(args)}/raw/track/{_dt.date.today().isoformat()}/<the name in front> '
          '(any extension), or run `eco.py track fetch`; then: eco.py track parse', file=sys.stderr)


def cmd_track_fetch(args):
    """Fallback for a harness with no web tool: repeat the planned searches slowly, skip saved ones."""
    d = eco_dir(args)
    track_target(args, load(d / 'brief.json', {}))
    out = d / 'raw' / 'track' / _dt.date.today().isoformat()
    gp = load(d / 'github-plan.json', {'queries': {}})['queries']
    sq = load(d / 'serp.json', {'queries': {}})['queries']
    todo = [(out / 'github' / f"{s['label']}.json", github_search_url(gp[s['label']]), 'en')
            for s in load(d / 'github.json', {'searches': []})['searches'] if s['label'] in gp]
    todo += [(out / 'serp' / f'{slug}.html', q['url'], q['lang'])
             for slug, q in load(d / 'serp-plan.json', {'queries': {}})['queries'].items() if 'own_rank' in sq.get(slug, {})]
    first = True
    for path, url, lang in todo:
        if path.exists():
            continue
        if not first:
            time.sleep(args.delay)
        first = False
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
                                                   'Accept-Language': lang})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
        except OSError as e:
            warn(f'{path.name}: {e}; stopping here, run it again later')
            break
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        print(f'saved {path.parent.name}/{path.name}')
    print('# then: eco.py track parse', file=sys.stderr)


def cmd_track_parse(args):
    d = eco_dir(args)
    b = load(d / 'brief.json', {})
    keys = track_target(args, b)
    done = state(args)['steps'].get('audit-final')
    if not done:
        die('no final audit yet: track measures a finished run, after its changes are published', 2)
    today = _dt.date.today()
    since = None
    if args.published:
        try:
            since = _day(args.published)
        except ValueError:
            die('--published takes a date, YYYY-MM-DD', 2)
        if not _day(done['at']) <= since <= today:
            die(f"--published {since}: the changes were finished on {done['at'][:10]}, so they went public between that day and today", 2)
    base = d / 'raw' / 'track'
    days = sorted(p for p in base.iterdir() if p.is_dir()) if base.exists() else []
    folder = base / args.day if args.day else (days[-1] if days else None)
    if folder is None or not folder.is_dir():
        die('no results fetched yet: run `eco.py track urls`', 2)
    try:
        _day(folder.name)
    except ValueError:
        die(f'{folder.name}: the folder is named after the day the searches were repeated, YYYY-MM-DD', 2)
    why = live_check(args, b)
    if why:
        for w in why:
            bad(w)
        print('The published copy is not the text of this run, so a position measured now would describe the old text. '
              'Publish the changes, then run `eco.py track parse` again.')
        sys.exit(1)
    own = str((b.get('github') or {}).get('repo') or '').strip('/').lower()
    plan = load(d / 'serp-plan.json', {'queries': {}})['queries']
    snap = {'at': folder.name, 'github': {}, 'serp': {}}
    gh_files = sorted((folder / 'github').glob('*')) if (folder / 'github').exists() else []
    skip = about_not_live(args, b) if gh_files else None
    if skip:
        warn(f"GitHub search left out: {skip}. That search reads the name, About and topics, not the README, "
             "so its position says nothing about this run until they are applied")
        gh_files = []
    for f in gh_files:
        found: list = []
        try:
            _github_results(json.loads(read_text(f)), found)
        except ValueError:
            pass
        if not found:
            warn(f'github/{f.name}: no search results in it; left out')
            continue
        names = [str(i.get('full_name', '')).lower() for i in found[0]['items']]
        snap['github'][f.stem] = {'rank': names.index(own) + 1 if own and own in names else None,
                                  'total': found[0]['total_count'], 'seen': len(names)}
    for f in sorted((folder / 'serp').glob('*')) if (folder / 'serp').exists() else []:
        slug = f.name.split('.')[0]
        if slug not in plan:
            warn(f'serp/{f.name}: not a search of this run (the file name is the one `track urls` printed); left out')
            continue
        every = parse_serp(read_text(f), None)
        if not every:
            warn(f'serp/{f.name}: no results found; the page may be a block or a captcha, not results; left out')
            continue
        snap['serp'][slug] = {'rank': own_rank_in(every, keys), 'seen': len(every)}
    if not snap['github'] and not snap['serp']:
        die(f'no usable result file under {folder}', 2)
    tr = load(d / 'track.json', {'live_since': None, 'snapshots': []})
    tr['live_since'] = since.isoformat() if since else (tr['live_since'] or today.isoformat())
    tr['snapshots'] = sorted([s for s in tr['snapshots'] if s['at'] != snap['at']] + [snap], key=lambda s: s['at'])
    save(d / 'track.json', tr)
    rows = track_rows(args)
    if not rows:
        die('none of the repeated searches has a "before" saved by the research, so there is nothing to compare', 2)
    text = '\n'.join(track_lines(args, rows)) + '\n'
    (d / 'track.md').write_text(text, encoding='utf-8')
    print(text)
    mark(args, 'track', rows=len(rows), improved=sum(1 for r in rows if r['verdict'] in IMPROVED),
         worse=sum(1 for r in rows if r['verdict'] in WORSE))


def _num(s: str) -> float:
    s = re.sub(r'[^\d.,-]', '', s or '')
    if ',' in s and '.' in s:
        s = s.replace(',', '')
    try:
        return float(s.replace(',', '.') or 0)
    except ValueError:
        return 0.0


def parse_gsc(text: str) -> dict:
    """Rows of a Search Console "Queries" export, keyed by the query. The headers come in the language of
    the account, so the columns are read by position: query, clicks, impressions, CTR, position."""
    rows = [r for r in csv.reader(io.StringIO(text.lstrip('﻿'))) if r]
    if len(rows) < 2 or len(rows[0]) != 5:
        die('not a Search Console queries export: it has five columns (query, clicks, impressions, CTR, position). '
            'Export one period at a time, without "Compare", and pass the Queries file', 2)
    if any(re.match(r'https?://', r[0]) for r in rows[1:6]):
        die('this is the Pages file of the export; pass the Queries one', 2)
    out = {}
    for r in rows[1:]:
        if len(r) == 5:
            out[flat(r[0])] = {'q': r[0], 'clicks': int(_num(r[1])), 'impressions': int(_num(r[2])), 'position': round(_num(r[4]), 1)}
    return out


def cmd_gsc(args):
    if args.mode != 'site':
        die('Search Console covers a site you own, not github.com: only --mode site reads it', 2)
    d = eco_dir(args)
    done = state(args)['steps'].get('audit-final')
    if not done:
        die('no final audit yet: Search Console is read after a finished run', 2)
    m = re.fullmatch(r'(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})', args.period or '')
    try:
        start, end = (_day(m.group(1)), _day(m.group(2))) if m else (None, None)
    except ValueError:
        start = end = None
    if not start or end < start or end > _dt.date.today():
        die('--period START..END with the dates of the export, e.g. 2026-01-01..2026-01-28 (it cannot end after today)', 2)
    data = load(d / 'gsc.json', {})
    public = _day(load(d / 'track.json', {}).get('live_since') or done['at'])
    if args.stage == 'before' and end >= public and load(d / 'track.json', {}).get('live_since'):
        die(f"the 'before' period ends {end}, when the changes were already public ({public}); export an earlier one", 2)
    if args.stage == 'after' and start < public:
        die(f"the 'after' period starts {start}, before the changes could be public ({public}); "
            'it has to start on the day they went public or later', 2)
    other = data.get('after' if args.stage == 'before' else 'before')
    if other and ((args.stage == 'before' and end >= _day(other['period'][0])) or (args.stage == 'after' and start <= _day(other['period'][1]))):
        die(f"the two periods overlap ({args.period} and {'..'.join(other['period'])})", 2)
    p = Path(args.file)
    rows = parse_gsc(read_text(p if p.is_absolute() else root_dir(args) / p))
    km = load(d / 'keywords.json', {'keywords': []})
    kept = {}
    for k in km['keywords']:
        if k.get('tier') == 'discarded':
            continue
        hits = [rows[v] for v in dict.fromkeys(flat(x) for x in [k['phrase']] + list(k.get('variants', []))) if v in rows]
        if hits:
            imp = sum(h['impressions'] for h in hits)
            kept[k['phrase']] = {'lang': k['lang'], 'clicks': sum(h['clicks'] for h in hits), 'impressions': imp,
                                 'position': round(sum(h['position'] * h['impressions'] for h in hits) / imp, 1) if imp else hits[0]['position']}
    data[args.stage] = {'period': [start.isoformat(), end.isoformat()], 'queries': len(rows), 'rows': kept}
    save(d / 'gsc.json', data)
    ok(f"{args.stage}: {len(rows)} queries in the export, {len(kept)} of them phrases of the keyword map")
    if 'before' in data and 'after' in data:
        text = '\n'.join(track_lines(args, track_rows(args))) + '\n'
        (d / 'track.md').write_text(text, encoding='utf-8')
        print(text)
    else:
        print(f"now the {'after' if args.stage == 'before' else 'before'} period: a position needs both to compare")
    mark(args, f'gsc-{args.stage}', phrases=len(kept))


def track_rows(args) -> list[dict]:
    """One row per search measured before and after publishing, each with a verdict."""
    d = eco_dir(args)
    tr = load(d / 'track.json', {'live_since': None, 'snapshots': []})
    rows = []
    if tr['snapshots']:
        snap = tr['snapshots'][-1]
        age = (_day(snap['at']) - _day(tr['live_since'])).days

        def settle(v: str, kind: str) -> str:
            return 'early' if v in ('same', 'out') and age < TRACK_SETTLE[kind] else v

        def within(rank, depth):
            return rank if rank and rank <= depth else None

        before = {s['label']: s for s in load(d / 'github.json', {'searches': []})['searches']}
        for label, a in snap['github'].items():
            if label in before:
                depth = max(a['seen'], 1) if a['seen'] < GITHUB_PER_PAGE else GITHUB_PER_PAGE
                r0, r1 = within(before[label].get('own_rank'), depth), within(a['rank'], depth)
                rows.append({'source': 'github', 'q': label, 'lang': '', 'before': r0, 'after': r1, 'depth': depth,
                             'verdict': settle(rank_verdict(r0, r1), 'github')})
        sq = load(d / 'serp.json', {'queries': {}})['queries']
        for slug, a in snap['serp'].items():
            s = sq.get(slug)
            if s and 'own_rank' in s:
                depth = min(a['seen'], s['seen'])
                r0, r1 = within(s['own_rank'], depth), within(a['rank'], depth)
                rows.append({'source': s.get('engine', 'ddg'), 'q': s['q'], 'lang': s['lang'], 'before': r0, 'after': r1,
                             'depth': depth, 'verdict': settle(rank_verdict(r0, r1, SERP_NOISE), 'serp')})
    g = load(d / 'gsc.json', {})
    if 'before' in g and 'after' in g:
        for phrase in sorted(set(g['before']['rows']) | set(g['after']['rows'])):
            b0, a0 = g['before']['rows'].get(phrase), g['after']['rows'].get(phrase)
            if not a0 or a0['impressions'] < GSC_MIN_IMPRESSIONS:
                v = 'thin'
            elif not b0 or b0['impressions'] < GSC_MIN_IMPRESSIONS:
                v = 'entered'
            else:
                move = b0['position'] - a0['position']
                v = 'up' if move >= GSC_MIN_MOVE else ('down' if move <= -GSC_MIN_MOVE else 'same')
            rows.append({'source': 'gsc', 'q': phrase, 'lang': (a0 or b0)['lang'],
                         'before': b0['position'] if b0 else None, 'after': a0['position'] if a0 else None,
                         'imp': [b0['impressions'] if b0 else 0, a0['impressions'] if a0 else 0],
                         'clicks': [b0['clicks'] if b0 else 0, a0['clicks'] if a0 else 0], 'verdict': v})
    return rows


def track_summary(rows) -> dict:
    c = Counter('improved' if r['verdict'] in IMPROVED else 'worse' if r['verdict'] in WORSE
                else 'unknown' if r['verdict'] in ('early', 'thin') else 'same' for r in rows)
    return {k: c[k] for k in ('improved', 'same', 'worse', 'unknown')}


def track_when(args) -> dict:
    d = eco_dir(args)
    tr = load(d / 'track.json', {'live_since': None, 'snapshots': []})
    g = load(d / 'gsc.json', {})
    return {'live_since': tr.get('live_since'), 'measured': tr['snapshots'][-1]['at'] if tr['snapshots'] else None,
            'gsc': ['..'.join(g[s]['period']) for s in ('before', 'after')] if 'before' in g and 'after' in g else None}


def track_cell(r: dict, key: str) -> str:
    v = r[key]
    if r['source'] == 'gsc':
        i = 0 if key == 'before' else 1
        return 'no impressions' if v is None else f"average position {v} ({r['imp'][i]} impressions, {r['clicks'][i]} clicks)"
    return f'#{v}' if v else f"not in the first {r['depth']}"


def track_lines(args, rows) -> list[str]:
    """The published-copy part of report.md, also printed by `track parse` and saved as track.md."""
    what = 'site' if args.mode == 'site' else 'README'
    if not rows:
        return [f'- On the published {what}: not checked.']
    n, w = track_summary(rows), track_when(args)
    dates = '; '.join(x for x in (f"public since {w['live_since']}, searches repeated {w['measured']}" if w['measured'] else '',
                                  f"Search Console {w['gsc'][0]} against {w['gsc'][1]}" if w['gsc'] else '') if x)
    out = [f"- On the published {what} ({dates}): {n['improved']} improved, {n['same']} no change, {n['worse']} worse, "
           f"{n['unknown']} not known yet.", '',
           '| Where | Search | Before | After | Result |', '|---|---|---|---|---|']
    for r in rows:
        out.append(f"| {TRACK_SOURCES[r['source']]} | {r['q']}{' [' + r['lang'] + ']' if r['lang'] else ''} | {track_cell(r, 'before')} | "
                   f"{track_cell(r, 'after')} | {VERDICTS[r['verdict']]} |")
    out += ['', 'The positions are measured. That the edits caused each move is not proven: other pages and repositories change too.']
    return out


def proof_data(km: dict, comp: dict, base: dict, final: dict) -> dict:
    """What the run can show without the published copy: how many researched phrases the text carries,
    and whether it now does with each primary what the pages that rank already do."""
    def live(a, strong=False):
        return {(p['phrase'], p['lang']) for p in a['placements'] if p['count'] > 0 and p['surface'] != 'github (proposed)'
                and (not strong or p['placement'] in ('title', 'h1', 'lead', 'about'))}

    phrases = [(k['phrase'], k['lang']) for k in km['keywords'] if k['tier'] != 'discarded']
    b_live, f_live, b_strong, f_strong = live(base), live(final), live(base, True), live(final, True)
    pages = list(comp.get('pages', {}).values())
    rivals = []
    for k in km['keywords']:
        if k['tier'] != 'primary' or not pages:
            continue
        variants = [k['phrase']] + list(k.get('variants', []))
        n = sum(1 for pg in pages if count_in(' . '.join([pg.get('title', '')] + list(pg.get('h1', []))), variants))
        key = (k['phrase'], k['lang'])
        rivals.append({'phrase': k['phrase'], 'lang': k['lang'], 'pages': n, 'of': len(pages),
                       'before': key in b_strong, 'after': key in f_strong})
    return {'before': sum(1 for p in phrases if p in b_live), 'after': sum(1 for p in phrases if p in f_live),
            'total': len(phrases), 'rivals': rivals}


# ---------------------------------------------------------------- report

LABELS = {
    'en': dict(title='Eco · keyword report', project='Project', audience='Audience', adjacent='adjacent',
               research='Research', queries='autocomplete queries', repos='GitHub repos', comps='competitors', rank='Current GitHub rank',
               notin='not in the top 30', map='Keyword map', primary='primary', secondary='secondary', longtail='long-tail',
               discarded='discarded', kw='Keyword', lang='Lang', tier='Tier', where='Placed in', changes='Changes',
               main='primary + secondary placements', before='before', after='after', offsite='Outside the repo',
               proposed='proposed, not applied', applied='applied', none='none', human='Humanization',
               verify='Verification', lost='placements lost', flags='flags', gone='removed', pending='Pending',
               nothing='nothing', dropped='Dropped', notdone='Not done: commit, push, pull request.',
               renamed='headings renamed', links='links', code='code spans', kws='keywords',
               nogoogle='No Google data for [{lang}]: its phrases rest on Bing and DuckDuckGo only.',
               serp='Search results', claims='New claims', checked='checked against', status={'not-installed': 'not installed', 'skipped': 'skipped by the user'}),
}


def cmd_report(args):
    page_lang, T = html_labels(args)
    d = eco_dir(args)
    st = state(args)
    errs = check_brief(args) + check_research(args) + check_map(args)[0]
    final = load(d / 'audit-final.json')
    if final is None:
        errs.append('no final audit: run `audit --save final` after the last edit')
    q = st['steps'].get('quiron')
    if q is None:
        errs.append('Quirón step not recorded: `quiron record --status used|skipped|not-installed`')
    lost, integ = [], {}
    base = run_audit(args, original=True) if not errs else None
    live = run_audit(args) if not errs else None
    if final is not None and live is not None:
        if {p: s['hash'] for p, s in live['surfaces'].items()} != {p: s['hash'] for p, s in final['surfaces'].items()}:
            errs.append('the files changed after `audit --save final`; audit again')
        if final['map_hash'] != live['map_hash']:
            errs.append('keywords.json changed after the final audit; audit again')
        if [m for m in final['missing'] if m['tier'] == 'primary']:
            errs.append('final audit still misses primary placements')
        if final['flags']:
            errs.append('final audit has flags')
        pre = load(d / 'audit-pre-quiron.json')
        if pre is None:
            errs.append('no `audit --save pre-quiron` snapshot (take it after editing, before any humanizing pass)')
        elif q and q.get('status') == 'used' and q.get('pre') and q['pre'] != {p_: s_['hash'] for p_, s_ in pre['surfaces'].items()}:
            errs.append('the pre-quiron snapshot was replaced after Quirón was recorded')
        else:
            if pre['map_hash'] != final['map_hash']:
                errs.append('keywords.json changed between the pre-quiron and final audits')
            lost = compare(pre, final)
            if lost:
                errs.append(f'{len(lost)} placements lost after the pre-quiron snapshot; restore them and audit again')
            for path, g in integrity(pre, final).items():
                if g['broken_internal']:
                    errs.append(f'{path}: internal links broken after the pre-quiron snapshot: {", ".join(g["broken_internal"])}')
        if args.mode == 'site':
            if load(d / 'lighthouse-baseline.json') is None:
                errs.append('no Lighthouse baseline: `eco.py lighthouse --stage baseline` (production, or the build before any edit)')
            lh = load(d / 'lighthouse-final.json')
            if lh is None:
                errs.append('no final Lighthouse run: `eco.py lighthouse --stage final` after `audit --save final`')
            else:
                if lh['surfaces'] != {p_: s_['hash'] for p_, s_ in final['surfaces'].items()}:
                    errs.append('the pages changed after the final Lighthouse run; rebuild, scan again and run '
                                '`eco.py lighthouse --stage final`')
                errs += lh['flags']
                left = lighthouse_open(st, lh)
                if left:
                    errs.append(f'{len(left)} Lighthouse audits below 1, neither fixed nor waived: ' + '; '.join(left[:6]))
        unchecked = [c for c in new_claims(base, final) if c['claim'] not in st.get('claims', {})]
        if unchecked:
            errs.append(f'{len(unchecked)} new claims not checked against a source ('
                        + ', '.join(repr(c['claim']) for c in unchecked[:6]) + '): `eco.py claims`')
        for path, g in integrity(base, final).items():
            if g['broken_internal']:
                errs.append(f'{path}: internal links broken: {", ".join(g["broken_internal"])}')
            integ[path] = g
    if errs:
        for e in errs:
            bad(e)
        sys.exit(1)

    L = LABELS['en']
    b = load(d / 'brief.json')
    km = load(d / 'keywords.json')
    sug = load(d / 'suggest.json', {'responses': {}})
    gh = load(d / 'github.json', {'repos': {}, 'searches': []})
    comp = load(d / 'competitors.json', {'pages': {}})
    tiers = Counter(k['tier'] for k in km['keywords'])
    where: dict = {}
    longtail_hit = sum(1 for k in km['keywords'] if k['tier'] == 'long-tail'
                       and any(p['phrase'] == k['phrase'] and p['count'] > 0 for p in final['placements']))
    for p in final['placements']:
        if p['count'] > 0:
            where.setdefault((p['phrase'], p['lang']), set()).add(p['placement'] if p['surface'] != 'github' else f"github {p['placement']}")
    out = [f"## {L['title']}: {b['project']['name']}", '']
    adj = ', '.join(b['audience'].get('adjacent', []))
    out.append(f"**{L['project']}:** {b['project']['what']}  ")
    out.append(f"**{L['audience']}:** {b['audience']['primary']}" + (f" ({L['adjacent']}: {adj})" if adj else ''))
    out.append('')
    langs = Counter(f"{r['lang']} {r.get('engine', 'google')}" for r in sug['responses'].values())
    out.append(f"**{L['research']}:** {len(sug['responses'])} {L['queries']} ("
               + ', '.join(f'{k} {v}' for k, v in sorted(langs.items())) + ")"
               + (f", {len(gh['repos'])} {L['repos']}" if gh['repos'] else '') + f", {len(comp['pages'])} {L['comps']}.")
    for lang in b['languages']:
        if not any(r['lang'] == lang and r.get('engine', 'google') == 'google' and r['suggestions'] for r in sug['responses'].values()):
            out.append(L['nogoogle'].format(lang=lang))
    own = b.get('github', {}).get('repo')
    if own and gh.get('searches'):
        ranks = '; '.join(f"{s['label']}: " + (f"#{s['own_rank']}" if s.get('own_rank') else L['notin']) for s in gh['searches'][:6])
        out.append(f"{L['rank']} ({own}): {ranks}.")
    serp = load(d / 'serp.json', {'queries': {}})
    if serp['queries']:
        out.append(f"**{L['serp']}** (top {SERP_TOP}): " + '; '.join(
            f"{s['q']} [{s['lang']}]: " + ', '.join(f'{n} {k}' for k, n in sorted(s['kinds'].items(), key=lambda x: -x[1]))
            for s in serp['queries'].values()) + '.')
        for a, b_, n in serp_overlaps(serp):
            out.append(f"{a} / {b_}: {n} shared results.")
        mine = [s for s in serp['queries'].values() if 'own_rank' in s]
        if mine and own_keys(b):
            out.append('Your position in those results before the changes: ' + '; '.join(
                f"{s['q']} [{s['lang']}]: " + (f"#{s['own_rank']}" if s['own_rank'] else f"not in the first {s['seen']}") for s in mine) + '.')
    out.append('')
    out.append(f"**{L['map']}:** {tiers['primary']} {L['primary']}, {tiers['secondary']} {L['secondary']}, "
               f"{tiers['long-tail']} {L['longtail']}, {tiers['discarded']} {L['discarded']}.")
    out.append('')
    out.append(f"| {L['kw']} | {L['lang']} | {L['tier']} | {L['where']} |")
    out.append('|---|---|---|---|')
    for k in sorted(km['keywords'], key=lambda k: (TIERS.index(k['tier']), k['lang'], k['phrase'])):
        if k['tier'] in ('primary', 'secondary'):
            pl = sorted(where.get((k['phrase'], k['lang']), []))
            out.append(f"| {k['phrase']} | {k['lang']} | {k['tier']} | {', '.join(pl) or '-'} |")
    if tiers['long-tail']:
        out.append('')
        out.append(f"long-tail: {longtail_hit}/{tiers['long-tail']} · " + ', '.join(
            k['phrase'] for k in km['keywords'] if k['tier'] == 'long-tail')[:300])
    for lang in b['languages']:
        dropped = [k for k in km['keywords'] if k['tier'] == 'discarded' and k['lang'] == lang][:8]
        if dropped:
            out.append('')
            out.append(f"{L['dropped']} [{lang}]: " + '; '.join(f"{k['phrase']} ({k['reason']})" for k in dropped))
    out.append('')
    out.append(f"**{L['changes']}:**")

    def count(audit, surface, tiers_):
        rows = [p for p in audit['placements'] if p['surface'] == surface and p['tier'] in tiers_]
        return sum(1 for p in rows if p['count'] > 0), len(rows)

    shown = list(final['surfaces']) + (['github'] if any(p['surface'] == 'github' for p in final['placements']) else [])
    for s in shown:
        h0, t0 = count(base, s, ('primary', 'secondary'))
        h1, t1 = count(final, s, ('primary', 'secondary'))
        l0, lt0 = count(base, s, ('long-tail',))
        l1, lt1 = count(final, s, ('long-tail',))
        line = f"- `{s}`: {L['main']} {h0}/{t0} → {h1}/{t1}"
        if lt1:
            line += f"; long-tail {l0}/{lt0} → {l1}/{lt1}"
        out.append(line)
        if s == 'github':
            continue
        bs, fs = base['surfaces'].get(s, {}), final['surfaces'].get(s, {})
        for fld in ('title', 'meta', 'h1', 'lead'):
            old, new = bs.get(fld), fs.get(fld)
            if isinstance(old, list):
                old, new = (old or [''])[0], (new or [''])[0]
            if old != new and new:
                old = old or ''
                i = next((j for j in range(min(len(old), len(new))) if old[j] != new[j]), min(len(old), len(new)))
                start = max(0, old.rfind(' ', 0, max(0, i - 25)) + 1) if i > 40 else 0
                pre = '…' if start else ''
                out.append(f"  - {fld}: \"{pre}{old[start:start + 110]}\" → \"{pre}{new[start:start + 130]}\"")
        renamed = [h for h in bs.get('headings', []) if h not in fs.get('headings', [])]
        if renamed:
            out.append(f"  - {L['renamed']}: {len(renamed)}")
        g = integ.get(s)
        if g and (g['links'] or g['code']):
            bits = []
            if g['links']:
                bits.append(f"{len(g['links'])} {L['links']}")
            if g['code']:
                bits.append(f"{len(g['code'])} {L['code']}")
            out.append(f"  - {L['gone']}: " + ', '.join(bits))
    out.append('')
    off = st.get('offsite')
    if off:
        bits = []
        if off.get('about'):
            bits.append(f"About \"{off['about']}\"")
        if off.get('topics'):
            bits.append('topics ' + ', '.join(off['topics']))
        if off.get('homepage'):
            bits.append(f"homepage {off['homepage']}")
        prop = sorted({p['phrase'] for p in final['placements'] if p['surface'] == 'github (proposed)' and p['count'] > 0})
        out.append(f"**{L['offsite']}** ({L['applied'] if off.get('applied') else L['proposed']}): " + '; '.join(bits)
                   + (f" · {L['kws']}: {', '.join(prop)}" if prop else ''))
    else:
        out.append(f"**{L['offsite']}:** {L['none']}")
    out.append('')
    nc = new_claims(base, final)
    if nc:
        out.append(f"**{L['claims']}:** " + '; '.join(
            f"{c['claim']} ({L['checked']} {st['claims'][c['claim']]['source']})" for c in nc))
        out.append('')
    lh = load(d / 'lighthouse-final.json') if args.mode == 'site' else None
    if lh:
        lb = load(d / 'lighthouse-baseline.json')
        where = lambda r: 'local build' if r['local'] else 'production'
        out.append(f"**Lighthouse** (average of {len(lh['routes'])} pages; before: {where(lb)}, after: {where(lh)}): " + ', '.join(
            f"{k} {round(lb['summary'][k] * 100) if lb['summary'].get(k) is not None else '-'} → {round(v * 100)}"
            for k, v in lh['summary'].items() if v is not None) + '.')
        worst = {}
        for r in lh['routes']:
            for k, (_, label, unit) in CWV_GOOD.items():
                v = r['metrics'].get(k)
                if v is not None and v > worst.get(label, (-1, ''))[0]:
                    worst[label] = (v, unit)
        if worst:
            out.append('Lab metrics, slowest page: ' + ', '.join(
                f'{lb_} {v / 1000:.1f} s' if u == 'ms' and v >= 1000 else (f'{lb_} {v:.0f} ms' if u == 'ms' else f'{lb_} {v:.2f}')
                for lb_, (v, u) in worst.items()) + ' (TBT is the lab stand-in for INP).')
        used = {(a_['id'], r['path']) for r in lh['routes'] for a_ in r['open']}
        ws = [w for w in st.get('waivers', []) if any(i == w['audit'] for i, _ in used)]
        for w in ws:
            out.append(f"- {w['audit']}" + (f" on {w['path']}" if w.get('path') else '') + f" ({w['kind']}): {w['reason']}")
        if lh['local']:
            out.append('Measured on the local build: is-on-https and redirects-http are decided by the production host.')
        out.append('')
    out.append(f"**{L['human']}:** Quirón {L['status'].get(q['status'], q['status'])}" + (f" · {q['result']}" if q.get('result') else ''))
    out.append('')
    main_rows = [p for p in final['placements'] if p['tier'] in ('primary', 'secondary') and p['surface'] != 'github (proposed)']
    hit = sum(1 for p in main_rows if p['count'] > 0)
    out.append(f"**{L['verify']}:** {L['main']} {hit}/{len(main_rows)}, {len(lost)} {L['lost']}, "
               f"{len(final['flags'])} {L['flags']}.")
    out.append('')
    proof = proof_data(km, comp, base, final)
    rows = track_rows(args)
    out.append('**What is proven:**')
    out.append(f"- In the files: {proof['before']} → {proof['after']} of the {proof['total']} researched phrases are in the text.")
    for r in proof['rivals']:
        yours = 'yours already did' if r['before'] and r['after'] else 'yours does now' if r['after'] else 'yours does not'
        out.append(f"- Against the {r['of']} competitor pages read: {r['pages']} carry \"{r['phrase']}\" [{r['lang']}] in the title or H1; {yours}.")
    out += track_lines(args, rows)
    out.append('')
    pend = list(st.get('pending', [])) + final.get('notes', []) + (lh['notes'] if lh else [])
    out.append(f"**{L['pending']}:**" + ('' if pend else f" {L['nothing']}."))
    out += [f'- {x}' for x in pend]
    out.append(f"- {L['notdone']}")
    text = '\n'.join(out) + '\n'
    (d / 'report.md').write_text(text, encoding='utf-8')
    lb = load(d / 'lighthouse-baseline.json') if lh else None
    R = report_data(args, b, km, sug, gh, comp, serp, base, final, integ, st, q, lh, lb, lost, main_rows)
    R.update(proof=proof, track=rows, track_sum=track_summary(rows), track_when=track_when(args),
             own_serp=[s for s in serp['queries'].values() if 'own_rank' in s] if own_keys(b) else [])
    (d / 'report.html').write_text(render_html(R, T, page_lang), encoding='utf-8')
    print(text)
    print(f'HTML report ({page_lang}): {rel(args)}/report.html; show it with `eco.py serve`', file=sys.stderr)
    mark(args, 'report', hash=sha(text))


# ---------------------------------------------------------------- HTML report

# The page a person opens after a run. report.md stays the fixed English proof; this page tells the same
# numbers in plain words, in the language the user talks to the agent in. Built-in: en, es. Any other
# language: the agent translates `eco.py labels` into a JSON file and passes it with --labels.
HTML_LABELS = {
    'en': {
        'title': 'Keyword report', 'sample': '', 'theme': 'Light / dark',
        'kicker_site': 'Your website, reviewed by eco', 'kicker_readme': 'Your README, reviewed by eco',
        'headline': 'now uses the words people type when they look for what you do.',
        'map_label': 'Map of your words: your project in the middle, the chosen words around it',
        'center': 'Your project', 'center_sub': '{n} places checked',
        'verified': 'Checked by a script', 'spots': 'key spots carry the right word',
        'before': 'Before', 'now': 'Now', 'lost': 'Words lost', 'flags': 'Alerts', 'broken': 'Broken links',
        'speed': 'Speed',
        'did_t': 'What we did', 'did': 'We looked at {q} real searches, {r} similar projects and {c} competitors, and chose {k} words.',
        'better_t': 'What improved', 'better': 'From {b} to {a} of {t} key spots with the right word.',
        'checked_t': 'What we checked', 'checked': 'Nothing was lost while polishing the text, and no internal link is broken.',
        'todo_t': 'Your part', 'todo_n': '{n} short tasks, at the end of this page.',
        'changes_h': 'The places we changed', 'longtail_line': 'Long phrases: from {b} to {a} of {t}',
        'renamed': 'headings renamed', 'gone_links': 'links removed', 'gone_code': 'code snippets removed',
        'empty': '(empty)', 'github': 'GitHub profile',
        'words_h': 'The words we chose',
        'tier_primary': 'Main', 'tier_primary_d': 'What your audience searches most',
        'tier_secondary': 'Supporting', 'tier_secondary_d': 'They back up the main ones',
        'tier_long': 'Long phrases', 'tier_long_d': 'Specific questions, less competition',
        'tier_disc': 'Left out', 'tier_disc_d': 'Each one with its reason',
        'in_text': '{a} of {t} are in your text', 'places_n': '{n} places', 'place_1': '1 place',
        'mode_site': 'website', 'mode_readme': 'README',
        'research_h': 'How we found them', 'research_q': '{n} autocomplete searches',
        'repos': '{n} GitHub repositories', 'comps': '{n} competitor pages',
        'nogoogle': 'No Google data for [{lang}]: those phrases rest on Bing and DuckDuckGo.',
        'rank_h': 'Your repository on GitHub today', 'rank_pos': 'position {n}', 'rank_out': 'not in the top 30',
        'serp_h': 'What ranks today (top 10)', 'shared': '{a} and {b} share {n} results',
        'speed_h': 'How fast and accessible it is', 'lh_note': 'Average of {n} pages. Before: {b}. After: {a}.',
        'lh_prod': 'the live site', 'lh_local': 'a copy on your computer',
        'cat_performance': 'Speed', 'cat_accessibility': 'Accessibility', 'cat_best-practices': 'Good practices', 'cat_seo': 'SEO',
        'slowest': 'Slowest page', 'waived_ceiling': 'cannot go higher', 'waived_declined': 'you chose to keep it',
        'local_https': 'HTTPS is decided by your server, not by the local copy.',
        'offsite_h': 'Outside your site', 'applied': 'applied', 'proposed': 'proposed, not applied yet',
        'about': 'Description', 'topics': 'Topics', 'homepage': 'Website',
        'claims_h': 'Facts we checked', 'claim_src': 'checked against {s}',
        'style_h': 'Style review', 'q_used': 'Quirón rewrote the text so it reads naturally; the keywords stayed in place.',
        'q_skipped': 'You chose to skip the style review.', 'q_missing': 'Quirón is not installed, so there was no style review.',
        'todo_h': 'Your part', 'notdone': 'Review and publish the changes: eco does not commit, push or open a pull request.',
        'more': 'See more', 'footer': 'Made by eco {v} · every number on this page comes from a check that passed',
        'pl_title': 'Title in Google', 'pl_meta': 'Description in Google', 'pl_h1': 'Page title', 'pl_lead': 'First paragraph',
        'pl_h2': 'Subheadings', 'pl_h3': 'Subheadings', 'pl_heading': 'Subheadings', 'pl_alt': 'Image text',
        'pl_og': 'Social preview', 'pl_jsonld': 'Structured data', 'pl_body': 'Body text',
        'pl_about': 'GitHub description', 'pl_topics': 'GitHub topics',
        'proof_h': 'What we can prove',
        'proof_files_t': 'In your text', 'proof_files': 'Before, {b} of the {t} phrases people search for were in your text. Now {a} are.',
        'proof_rivals_t': 'Next to the pages that show up today',
        'proof_rival': '{n} of the {t} pages we read put «{p}» in their title or main heading.',
        'rival_gain': 'Yours did not. Now it does.', 'rival_keep': 'Yours already did.', 'rival_miss': 'Yours still does not.',
        'proof_live_site': 'On your published site', 'proof_live_readme': 'On GitHub',
        'live_none_site': 'We could not check it on your published site.', 'live_none_readme': 'We could not check it on GitHub.',
        'live_sum': '{up} improved · {same} no change · {down} worse · {unk} not known yet',
        'live_dates': 'Public since {d}. Searches repeated on {m}.', 'live_gsc': 'Search Console: {b} against {a}.',
        'live_caveat': 'These positions are measured. We cannot prove our changes caused each move: other pages change too.',
        'pos_out': 'not in the first {n}', 'pos_avg': 'average position {n} ({i} views)', 'pos_none': 'no views',
        'src_github': 'GitHub search', 'src_ddg': 'DuckDuckGo', 'src_bing': 'Bing', 'src_gsc': 'Google',
        'v_up': 'Improved', 'v_entered': 'Improved: now it shows up', 'v_down': 'Worse', 'v_left': 'Worse: it no longer shows up',
        'v_same': 'No change', 'v_out': 'Still does not show up', 'v_early': 'Too early to tell', 'v_thin': 'Not enough data',
        'own_h': 'Where you showed up before the changes',
    },
    'es': {
        'title': 'Informe de palabras', 'sample': '', 'theme': 'Claro / oscuro',
        'kicker_site': 'Tu sitio web, revisado por eco', 'kicker_readme': 'Tu README, revisado por eco',
        'headline': 'ya usa las palabras que escribe la gente cuando busca lo que haces.',
        'map_label': 'Mapa de tus palabras: tu proyecto en el centro y las palabras elegidas alrededor',
        'center': 'Tu proyecto', 'center_sub': '{n} lugares revisados',
        'verified': 'Comprobado por un script', 'spots': 'lugares clave tienen la palabra correcta',
        'before': 'Antes', 'now': 'Ahora', 'lost': 'Palabras perdidas', 'flags': 'Alertas', 'broken': 'Enlaces rotos',
        'speed': 'Velocidad',
        'did_t': 'Qué hicimos', 'did': 'Miramos {q} búsquedas reales, {r} proyectos parecidos y {c} competidores, y elegimos {k} palabras.',
        'better_t': 'Qué mejoró', 'better': 'De {b} a {a} de {t} lugares clave con la palabra correcta.',
        'checked_t': 'Qué comprobamos', 'checked': 'Nada se perdió al pulir el texto y no hay enlaces internos rotos.',
        'todo_t': 'Lo que te toca', 'todo_n': '{n} tareas cortas, al final de esta página.',
        'changes_h': 'Los lugares que cambiamos', 'longtail_line': 'Frases largas: de {b} a {a} de {t}',
        'renamed': 'subtítulos renombrados', 'gone_links': 'enlaces quitados', 'gone_code': 'fragmentos de código quitados',
        'empty': '(vacío)', 'github': 'Perfil de GitHub',
        'words_h': 'Las palabras que elegimos',
        'tier_primary': 'Principales', 'tier_primary_d': 'Lo que más busca tu público',
        'tier_secondary': 'De apoyo', 'tier_secondary_d': 'Refuerzan a las principales',
        'tier_long': 'Frases largas', 'tier_long_d': 'Preguntas concretas, menos competencia',
        'tier_disc': 'Descartadas', 'tier_disc_d': 'Cada una con su motivo',
        'in_text': '{a} de {t} están en tu texto', 'places_n': '{n} lugares', 'place_1': '1 lugar',
        'mode_site': 'sitio web', 'mode_readme': 'README',
        'research_h': 'Cómo las encontramos', 'research_q': '{n} búsquedas en el autocompletado',
        'repos': '{n} repositorios de GitHub', 'comps': '{n} páginas de competidores',
        'nogoogle': 'Sin datos de Google para [{lang}]: esas frases se apoyan en Bing y DuckDuckGo.',
        'rank_h': 'Tu repositorio hoy en GitHub', 'rank_pos': 'puesto {n}', 'rank_out': 'fuera de los 30 primeros',
        'serp_h': 'Qué aparece hoy (10 primeros)', 'shared': '{a} y {b} comparten {n} resultados',
        'speed_h': 'Qué tan rápido y accesible es', 'lh_note': 'Promedio de {n} páginas. Antes: {b}. Después: {a}.',
        'lh_prod': 'el sitio publicado', 'lh_local': 'una copia en tu equipo',
        'cat_performance': 'Velocidad', 'cat_accessibility': 'Accesibilidad', 'cat_best-practices': 'Buenas prácticas', 'cat_seo': 'SEO',
        'slowest': 'La página más lenta', 'waived_ceiling': 'no puede subir más', 'waived_declined': 'decidiste dejarlo así',
        'local_https': 'HTTPS lo decide tu servidor, no la copia local.',
        'offsite_h': 'Fuera de tu sitio', 'applied': 'aplicado', 'proposed': 'propuesto, sin aplicar todavía',
        'about': 'Descripción', 'topics': 'Temas', 'homepage': 'Web',
        'claims_h': 'Datos que comprobamos', 'claim_src': 'comprobado en {s}',
        'style_h': 'Revisión de estilo', 'q_used': 'Quirón reescribió el texto para que suene natural; las palabras clave siguieron en su sitio.',
        'q_skipped': 'Decidiste saltarte la revisión de estilo.', 'q_missing': 'Quirón no está instalado, así que no hubo revisión de estilo.',
        'todo_h': 'Lo que te toca', 'notdone': 'Revisa y publica los cambios: eco no hace commit, push ni pull request.',
        'more': 'Ver más', 'footer': 'Hecho por eco {v} · cada número de esta página sale de una comprobación que pasó',
        'pl_title': 'Título en Google', 'pl_meta': 'Descripción en Google', 'pl_h1': 'Título de la página', 'pl_lead': 'Primer párrafo',
        'pl_h2': 'Subtítulos', 'pl_h3': 'Subtítulos', 'pl_heading': 'Subtítulos', 'pl_alt': 'Texto de las imágenes',
        'pl_og': 'Vista previa en redes', 'pl_jsonld': 'Datos estructurados', 'pl_body': 'Texto',
        'pl_about': 'Descripción de GitHub', 'pl_topics': 'Temas de GitHub',
        'proof_h': 'Lo que podemos demostrar',
        'proof_files_t': 'En tu texto', 'proof_files': 'Antes, {b} de las {t} frases que busca la gente estaban en tu texto. Ahora están {a}.',
        'proof_rivals_t': 'Frente a las páginas que aparecen hoy',
        'proof_rival': '{n} de las {t} páginas que leímos ponen «{p}» en su título o encabezado principal.',
        'rival_gain': 'La tuya no lo hacía. Ahora sí.', 'rival_keep': 'La tuya ya lo hacía.', 'rival_miss': 'La tuya todavía no.',
        'proof_live_site': 'En tu sitio publicado', 'proof_live_readme': 'En GitHub',
        'live_none_site': 'No pudimos comprobarlo en tu sitio publicado.', 'live_none_readme': 'No pudimos comprobarlo en GitHub.',
        'live_sum': '{up} mejoraron · {same} sin cambio · {down} empeoraron · {unk} aún sin saber',
        'live_dates': 'Publicado desde el {d}. Búsquedas repetidas el {m}.', 'live_gsc': 'Search Console: {b} frente a {a}.',
        'live_caveat': 'Estas posiciones están medidas. No podemos demostrar que nuestros cambios causaron cada movimiento: otras páginas también cambian.',
        'pos_out': 'fuera de los {n} primeros', 'pos_avg': 'posición media {n} ({i} apariciones)', 'pos_none': 'sin apariciones',
        'src_github': 'Búsqueda de GitHub', 'src_ddg': 'DuckDuckGo', 'src_bing': 'Bing', 'src_gsc': 'Google',
        'v_up': 'Mejoró', 'v_entered': 'Mejoró: ahora aparece', 'v_down': 'Empeoró', 'v_left': 'Empeoró: ya no aparece',
        'v_same': 'Sin cambio', 'v_out': 'Sigue sin aparecer', 'v_early': 'Demasiado pronto para saberlo', 'v_thin': 'Faltan datos',
        'own_h': 'Dónde aparecías antes de los cambios',
    },
}

SYMBOL_D = ('M8.24 220L89 80.12Q96 68 103 80.12L128.51 124.31L158.1 60.69Q164 48 169.9 60.69L244 220Z'
            'M84 220V202A44 44 0 0 1 172 202V220ZM108 220V202A20 20 0 0 1 148 202V220Z')
MOUNTAIN_D = 'M8.24 220L89 80.12Q96 68 103 80.12L128.51 124.31L158.1 60.69Q164 48 169.9 60.69L244 220Z'


def html_labels(args) -> tuple[str, dict]:
    """The labels for --lang, from the built-in set or an agent-written --labels file; refuses a partial file."""
    lang = (getattr(args, 'lang', None) or 'en').strip().lower()
    path = getattr(args, 'labels', None)
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = root_dir(args) / p
        try:
            got = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError) as e:
            die(f'cannot read --labels {path}: {e}', 2)
        if not isinstance(got, dict):
            die('--labels must be a JSON object of label: text', 2)
        missing = [k for k in HTML_LABELS['en'] if not isinstance(got.get(k), str)]
        if missing:
            die(f'--labels misses {len(missing)} keys: ' + ', '.join(missing[:12]) + '; `eco.py labels` prints them all', 2)
        fields = lambda t: {f for _, f, _, _ in string.Formatter().parse(t) if f is not None}  # noqa: E731
        wrong = []
        for k, en in HTML_LABELS['en'].items():
            try:
                if fields(got[k]) != fields(en):
                    wrong.append(k)
            except ValueError:
                wrong.append(k)
        if wrong:
            die('--labels changes the {placeholders} of: ' + ', '.join(wrong[:12]) + '; keep them exactly as `eco.py labels` '
                'prints them, and write a literal brace as {{ or }}', 2)
        return lang, {k: got[k] for k in HTML_LABELS['en']}
    if lang not in HTML_LABELS:
        die(f'no built-in labels for {lang!r} (built in: {", ".join(HTML_LABELS)}): translate `eco.py labels` '
            f'into a JSON file and pass it with --labels', 2)
    return lang, HTML_LABELS[lang]


def cmd_labels(args):
    print(json.dumps(HTML_LABELS['en'], ensure_ascii=False, indent=2))


def report_data(args, b, km, sug, gh, comp, serp, base, final, integ, st, q, lh, lb, lost, main_rows):
    """Every value the HTML page shows, taken from the same files and audits as report.md."""
    keys = {(p['phrase'], p['lang'], p['placement'], p['surface']) for p in main_rows}
    before_hit = sum(1 for p in base['placements'] if p['count'] > 0
                     and (p['phrase'], p['lang'], p['placement'], p['surface']) in keys)
    places: dict = {}
    for p in final['placements']:
        if p['count'] > 0 and p['surface'] != 'github (proposed)':
            places.setdefault((p['phrase'], p['lang']), []).append(p['placement'])
    kws = sorted(km['keywords'], key=lambda k: (TIERS.index(k['tier']), k['lang'], k['phrase']))

    def count(audit, surface, tiers_):
        rows = [p for p in audit['placements'] if p['surface'] == surface and p['tier'] in tiers_]
        return sum(1 for p in rows if p['count'] > 0), len(rows)

    surfaces = []
    shown = list(final['surfaces']) + (['github'] if any(p['surface'] == 'github' for p in final['placements']) else [])
    for s in shown:
        h0, t0 = count(base, s, ('primary', 'secondary'))
        h1, t1 = count(final, s, ('primary', 'secondary'))
        l0, lt0 = count(base, s, ('long-tail',))
        l1, lt1 = count(final, s, ('long-tail',))
        fields = []
        bs, fs = base['surfaces'].get(s, {}), final['surfaces'].get(s, {})
        for fld in ('title', 'meta', 'h1', 'lead'):
            old, new = bs.get(fld), fs.get(fld)
            if isinstance(old, list) or isinstance(new, list):
                old, new = (old or [''])[0], (new or [''])[0]
            if new and old != new:
                fields.append((fld, (old or '')[:220], new[:260]))
        g = integ.get(s) or {}
        surfaces.append({'name': s, 'h0': h0, 't0': t0, 'h1': h1, 't1': t1, 'l0': l0, 'l1': l1, 'lt': lt1,
                         'fields': fields, 'renamed': len([h for h in bs.get('headings', []) if h not in fs.get('headings', [])]),
                         'links': len(g.get('links') or []), 'code': len(g.get('code') or [])})
    engines, langs = Counter(), Counter()
    for r in sug['responses'].values():
        engines[r.get('engine', 'google')] += 1
        langs[r['lang']] += 1
    nogoogle = [lang for lang in b['languages'] if not any(r['lang'] == lang and r.get('engine', 'google') == 'google'
                                                           and r['suggestions'] for r in sug['responses'].values())]
    lhd = None
    if lh:
        worst = {}
        for r in lh['routes']:
            for k, (_, label, unit) in CWV_GOOD.items():
                v = r['metrics'].get(k)
                if v is not None and v > worst.get(label, (-1, ''))[0]:
                    worst[label] = (v, unit)
        used = {(a_['id'], r['path']) for r in lh['routes'] for a_ in r['open']}
        lhd = {'n': len(lh['routes']), 'before_local': lb['local'], 'after_local': lh['local'],
               'scores': [(k, lb['summary'].get(k), v) for k, v in lh['summary'].items() if v is not None],
               'worst': worst, 'local': lh['local'],
               'waivers': [w for w in st.get('waivers', []) if any(i == w['audit'] for i, _ in used)]}
    return {
        'mode': args.mode, 'name': b['project']['name'], 'what': b['project']['what'],
        'audience': b['audience']['primary'], 'adjacent': b['audience'].get('adjacent', []),
        'hit': sum(1 for p in main_rows if p['count'] > 0), 'total': len(main_rows), 'before_hit': before_hit,
        'lost': len(lost), 'flags': len(final['flags']),
        'broken': sum(len(g.get('broken_internal') or []) for g in integ.values()),
        'queries': len(sug['responses']), 'engines': dict(engines), 'langs': dict(langs), 'nogoogle': nogoogle,
        'repos': len(gh['repos']), 'comps': len(comp['pages']),
        'own': b.get('github', {}).get('repo'), 'ranks': [(s['label'], s.get('own_rank')) for s in gh.get('searches', [])[:6]],
        'serp': list(serp['queries'].values()), 'overlaps': serp_overlaps(serp),
        'keywords': [dict(k, places=sorted(set(places.get((k['phrase'], k['lang']), [])))) for k in kws],
        'surfaces': surfaces, 'offsite': st.get('offsite'),
        'offsite_kws': sorted({p['phrase'] for p in final['placements'] if p['surface'] == 'github (proposed)' and p['count'] > 0}),
        'claims': [(c['claim'], st['claims'][c['claim']]['source']) for c in new_claims(base, final)],
        'lighthouse': lhd, 'quiron': q,
        'pending': list(st.get('pending', [])) + final.get('notes', []) + (lh['notes'] if lh else []),
    }


HTML_CSS = """
:root{--bg:#E8E8E6;--sf:#F4F4F2;--sf2:#FFFFFF;--ink:#151515;--mut:#5E5E5A;--line:#C9C9C4;--inv:#151515;--inv-ink:#F4F4F2;
--a:#C4F03A;--on-a:#151515;--ag:#4A6600;--b:#6D5BFF;--c:#FF5F0F;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#121212;--sf:#1C1C1C;--sf2:#242424;--ink:#EDEDEB;--mut:#A3A39E;
--line:#34342F;--inv:#EDEDEB;--inv-ink:#151515;--ag:#C4F03A;--b:#9C8FFF;color-scheme:dark}}
:root[data-theme=dark]{--bg:#121212;--sf:#1C1C1C;--sf2:#242424;--ink:#EDEDEB;--mut:#A3A39E;--line:#34342F;--inv:#EDEDEB;
--inv-ink:#151515;--ag:#C4F03A;--b:#9C8FFF;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 Geist,Inter,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
.mono{font-family:'Geist Mono',ui-monospace,SFMono-Regular,Consolas,monospace}
.mut{color:var(--mut)}
.wrap{max-width:1200px;margin:0 auto;padding:20px 16px 72px}
.ic{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round;flex:none}
header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px}
.brand{display:flex;align-items:center;gap:12px}
.tile{width:44px;height:44px;background:var(--a);display:flex;align-items:center;justify-content:center}
.tile path{fill:var(--on-a)}
#theme{min-height:44px;min-width:44px;border:1px solid var(--line);background:var(--sf);color:var(--ink);font:inherit;font-size:14px;
padding:0 14px;cursor:pointer;display:inline-flex;align-items:center;gap:8px}
.sq{width:10px;height:10px;background:var(--a);outline:1.5px solid var(--ink);display:inline-block;flex:none}
.ci{width:10px;height:10px;border-radius:50%;background:var(--b);display:inline-block;flex:none}
.tr{width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-bottom:10px solid var(--c);display:inline-block;flex:none}
.xx{width:10px;height:10px;display:inline-block;flex:none;background:linear-gradient(45deg,transparent 42%,var(--mut) 42%,var(--mut) 58%,transparent 58%),linear-gradient(-45deg,transparent 42%,var(--mut) 42%,var(--mut) 58%,transparent 58%)}
mark{background:var(--a);color:var(--on-a);padding:0 3px}
.map{position:relative;background:var(--sf);margin-top:16px;overflow:hidden}
.map>svg{display:block;width:100%;height:auto}
.cl{fill:none;stroke:var(--line);stroke-width:1.2}
.terr{fill:url(#dots);stroke:var(--ag);stroke-width:2}
.dotf{fill:var(--ag)}
.m1{fill:var(--a);stroke:var(--ink);stroke-width:2}.m2{fill:var(--b);stroke:var(--ink);stroke-width:2}
.mk{transform-box:fill-box;transform-origin:center;animation:pin .5s cubic-bezier(.3,1.6,.5,1) backwards}
.lb{fill:var(--ink);font-size:15px;font-family:inherit}.lbm{fill:var(--mut);font-size:12px}
.mt{fill:none;stroke:var(--ink);stroke-width:3}
.arc{fill:none;stroke:var(--ag);stroke-width:3;transform-box:fill-box;transform-origin:50% 100%;animation:echo 2.6s ease-out 3}
.arc.d1{animation-delay:.35s}.arc.d2{animation-delay:.7s}
.title{position:absolute;left:28px;top:24px;max-width:520px}
.title h1{font-size:56px;line-height:.95;letter-spacing:-2.5px;font-weight:600;margin:4px 0 0}
.title h1 span{display:block;font-weight:300;font-size:30px;letter-spacing:-1px;margin-top:8px}
.stat{position:absolute;right:0;top:0;width:330px;background:var(--a);color:var(--on-a);padding:22px 24px}
.stat .big{font-size:88px;line-height:.85;letter-spacing:-4px;margin-top:8px}
.srow{display:grid;grid-template-columns:130px minmax(0,1fr);gap:10px;padding:8px 0;border-top:1px solid currentColor;font-size:14px}
.legend{display:inline-flex;flex-wrap:wrap;gap:6px 16px;margin-top:16px;background:var(--inv);color:var(--inv-ink);padding:10px 14px;font-size:13px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend .sq{outline-color:var(--inv-ink)}
.legend .xx{background:linear-gradient(45deg,transparent 42%,currentColor 42%,currentColor 58%,transparent 58%),linear-gradient(-45deg,transparent 42%,currentColor 42%,currentColor 58%,transparent 58%)}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:12px}
.card{background:var(--sf);padding:20px;display:flex;flex-direction:column;gap:8px}
.card h3{margin:0;font-size:17px;font-weight:600;display:flex;align-items:center;gap:8px}
.card.inv{background:var(--inv);color:var(--inv-ink)}
h2{font-size:36px;font-weight:500;letter-spacing:-1.3px;margin:56px 0 18px;line-height:1.05}
.places{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(320px,100%),1fr));gap:12px}
.place{background:var(--sf);padding:20px;display:flex;flex-direction:column;gap:10px;min-width:0}
.place .n{font-size:48px;font-weight:300;letter-spacing:-2px;line-height:1}
.bar{height:8px;background:var(--line);overflow:hidden}
.bar i{display:block;height:100%;background:var(--ag);transform-origin:left;animation:grow 1.6s cubic-bezier(.2,.8,.2,1)}
.ba{border-top:1px solid var(--line);padding-top:10px;font-size:14px;overflow-wrap:anywhere}
.ba s{color:var(--mut);text-decoration-thickness:1.5px}
.tiers{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.tier{background:var(--sf);padding:18px;min-width:0}
.tier h4{margin:0 0 4px;display:flex;align-items:center;gap:8px;font-size:16px}
.kw{padding:8px 0;border-top:1px solid var(--line);font-size:15px;overflow-wrap:anywhere}
.kw small{display:block;color:var(--mut);font-size:12.5px}
.rings{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.rg{background:var(--sf);padding:18px;display:flex;flex-direction:column;gap:6px}
.ring .trk{fill:none;stroke:var(--line);stroke-width:3}
.ring .val{fill:none;stroke:var(--ag);stroke-width:3;stroke-dasharray:100;transform:rotate(-90deg);transform-origin:50% 50%;animation:ring 1.8s cubic-bezier(.2,.8,.2,1)}
.todo{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(280px,100%),1fr));gap:12px}
.td{border:1.5px solid var(--ink);padding:20px;display:flex;flex-direction:column;gap:8px;overflow-wrap:anywhere}
.td .n{font-size:13px;background:var(--a);color:var(--on-a);align-self:flex-start;padding:2px 8px}
details{border-top:1px solid var(--line)}
details:last-of-type{border-bottom:1px solid var(--line)}
summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:12px;padding:16px 0;font-size:18px;font-weight:500;min-height:44px}
summary::-webkit-details-marker{display:none}
summary .more{margin-left:auto;font-size:13px;color:var(--mut)}
.det{padding:0 0 18px;display:grid;gap:8px;overflow-wrap:anywhere}
footer{margin-top:28px;text-align:center;font-size:13px}
.in{animation:pop .7s ease-out backwards}
@keyframes pop{from{opacity:0;transform:translateY(10px)}}
@keyframes pin{from{opacity:0;transform:scale(0)}}
@keyframes echo{0%{transform:scale(.55);opacity:0}35%{opacity:1}100%{transform:scale(1);opacity:1}}
@keyframes ring{from{stroke-dashoffset:var(--o0,100)}}
@keyframes grow{from{transform:scaleX(var(--f,0))}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
@media (max-width:980px){.stat,.title{position:static;width:auto;max-width:none;margin:12px}.title{padding:8px 4px 0}
.title h1{font-size:38px}.title h1 span{font-size:22px}.stat .big{font-size:64px}.cards,.tiers,.rings{grid-template-columns:minmax(0,1fr)}h2{font-size:28px}}
"""

HTML_JS = """(function(){var r=document.documentElement,b=document.getElementById('theme');if(!b)return;
function dark(){return(r.getAttribute('data-theme')||(window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'))==='dark'}
try{var t=localStorage.getItem('eco-theme');if(t==='dark'||t==='light')r.setAttribute('data-theme',t)}catch(e){}
b.hidden=false;b.setAttribute('aria-pressed',String(dark()));
b.addEventListener('click',function(){var t=dark()?'light':'dark';r.setAttribute('data-theme',t);b.setAttribute('aria-pressed',String(t==='dark'));
try{localStorage.setItem('eco-theme',t)}catch(e){}})})();"""

ICONS = {
    'search': '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    'spark': '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
    'shield': '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5L16 9.5"/>',
    'list': '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    'moon': '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    'page': '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
    'branch': '<circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="8" r="2"/><path d="M6 8v8M18 10c0 4-6 3-10 6"/>',
}


def icon(name: str) -> str:
    return f'<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'


def render_html(R: dict, T: dict, lang: str) -> str:
    E = lambda v: _html.escape(str(v), quote=True)  # noqa: E731
    fmt = lambda key, **kw: E(T[key].format(**kw))  # noqa: E731
    pl = lambda p: T.get('pl_' + p, p)  # noqa: E731
    kws = R['keywords']
    tier = lambda t: [k for k in kws if k['tier'] == t]  # noqa: E731
    prim, sec, longt, disc = tier('primary'), tier('secondary'), tier('long-tail'), tier('discarded')
    lt_hit = sum(1 for k in longt if k['places'])
    o = []
    w = o.append
    w(f'<!doctype html><html lang="{E(lang)}"><head><meta charset="utf-8">'
      f'<meta name="viewport" content="width=device-width, initial-scale=1">'
      f'<title>{E(T["title"])} · {E(R["name"])}</title><style>{HTML_CSS}</style></head><body><div class="wrap">')
    w(f'<header><div class="brand"><div class="tile"><svg viewBox="0 0 256 256" width="32" height="32" aria-hidden="true">'
      f'<path transform="translate(0 -6)" fill-rule="evenodd" d="{SYMBOL_D}"/></svg></div>'
      f'<div><div style="font-weight:600">eco · {E(T["title"])}</div><div class="mono mut" style="font-size:12.5px">'
      f'{E(R["name"])} · {E(_dt.date.today().isoformat())} · {E(T["mode_" + R["mode"]])}</div></div></div>'
      f'<button id="theme" type="button" hidden aria-label="{E(T["theme"])}">{icon("moon")}{E(T["theme"])}</button></header>')
    # the map: project in the middle, primaries on the inner ring, secondaries on the outer one
    shown = [(k, 1) for k in prim[:4]] + [(k, 2) for k in sec[:8]]
    marks = []
    # The title sits top left and the verdict top right: primaries take the upper arc between them,
    # secondaries the lower half, from the left side round to the right.
    for ring, rx, ry, a0, a1 in ((1, 300, 190, 190.0, 282.0), (2, 440, 250, 200.0, 20.0)):
        items = [k for k, r in shown if r == ring]
        for i, k in enumerate(items):
            t = i / (len(items) - 1) if len(items) > 1 else 0.5
            ang = math.radians(a0 + (a1 - a0) * t)
            x, y = 610 + rx * math.cos(ang), 410 + ry * math.sin(ang)
            x, y = min(max(x, 40), 1160), min(max(y, 60), 660)
            text = k['phrase'] if len(k['phrase']) <= 30 else k['phrase'][:29] + '…'
            right = x >= 610 and x + 8.5 * len(text) < 1185
            tx = x + 16 if right else x - 16
            shape = (f'<rect class="m1" x="{x - 9:.0f}" y="{y - 9:.0f}" width="18" height="18"/>' if ring == 1
                     else f'<circle class="m2" cx="{x:.0f}" cy="{y:.0f}" r="9"/>')
            marks.append(f'<g class="mk" style="animation-delay:{0.3 + 0.08 * len(marks):.2f}s">{shape}</g>'
                         f'<text class="lb" x="{tx:.0f}" y="{y + 5:.0f}" text-anchor="{"start" if right else "end"}">{E(text)}</text>'
                         f'<text class="lbm" x="{tx:.0f}" y="{y + 22:.0f}" text-anchor="{"start" if right else "end"}">'
                         f'{E(T["place_1"]) if len(k["places"]) == 1 else fmt("places_n", n=len(k["places"]))}</text>')
    blob = 'M0 -180C140 -190 240 -100 230 0C220 110 120 180 0 170C-120 160 -220 100 -210 0C-200 -110 -120 -170 0 -180Z'
    rings = ''.join(f'<path class="cl" vector-effect="non-scaling-stroke" transform="scale({s}) rotate({r})" d="{blob}"/>'
                    for s, r in ((2.6, -8), (2.2, -6), (1.85, -3), (1.5, 0), (1.18, 4), (.9, 8), (.64, 12), (.42, 16)))
    w(f'<section class="map" aria-label="{E(T["map_label"])}"><svg viewBox="0 0 1200 700" role="img" aria-label="{E(T["map_label"])}">'
      f'<defs><pattern id="dots" width="8" height="8" patternUnits="userSpaceOnUse"><circle class="dotf" cx="2" cy="2" r="1.3"/></pattern></defs>'
      f'<g transform="translate(560 400)">{rings}</g>'
      f'<path class="terr" d="M420 330C470 270 560 250 650 268C730 284 790 330 802 400C814 470 766 530 690 548C610 566 520 560 460 520C400 480 380 380 420 330Z"/>'
      f'<g transform="translate(556 352) scale(.42)"><path class="mt" d="{MOUNTAIN_D}"/>'
      f'<path class="arc" d="M84 214A44 44 0 0 1 172 214"/><path class="arc d1" d="M54 214A74 74 0 0 1 202 214"/>'
      f'<path class="arc d2" d="M24 214A104 104 0 0 1 232 214"/></g>'
      f'<text class="lb" x="612" y="470" text-anchor="middle" font-weight="600">{E(T["center"])}</text>'
      f'<text class="lbm" x="612" y="488" text-anchor="middle">{fmt("center_sub", n=R["total"])}</text>'
      + ''.join(marks) + '</svg>')
    w(f'<div class="title in"><span class="mut" style="font-size:14px">{E(T["kicker_" + R["mode"]])}</span>'
      f'<h1>{E(R["name"])}<span>{E(T["headline"])}</span></h1>'
      f'<div class="legend"><span><span class="sq"></span>{E(T["tier_primary"])}</span><span><span class="ci"></span>{E(T["tier_secondary"])}</span>'
      f'<span><span class="tr"></span>{E(T["tier_long"])}</span><span><span class="xx"></span>{E(T["tier_disc"])}</span></div></div>')
    lhd = R['lighthouse']
    perf = next((s for s in (lhd or {}).get('scores', []) if s[0] == 'performance'), None)
    w(f'<div class="stat in" style="animation-delay:.2s"><div style="font-weight:600;display:flex;align-items:center;gap:8px">'
      f'{icon("shield")}{E(T["verified"])}</div><div class="big">{R["hit"]}/{R["total"]}</div>'
      f'<div style="margin:6px 0 12px">{E(T["spots"])}</div>'
      f'<div class="srow"><span>{E(T["before"])}</span><b>{R["before_hit"]}/{R["total"]}</b></div>'
      f'<div class="srow"><span>{E(T["lost"])}</span><b>{R["lost"]}</b></div>'
      f'<div class="srow"><span>{E(T["flags"])}</span><b>{R["flags"]}</b></div>'
      f'<div class="srow"><span>{E(T["broken"])}</span><b>{R["broken"]}</b></div>'
      + (f'<div class="srow"><span>{E(T["speed"])}</span><b>{round((perf[1] or 0) * 100)} → {round(perf[2] * 100)}</b></div>'
         if perf and perf[1] is not None else '') + '</div>')
    w('</section>')
    pend = R['pending']
    w('<section class="cards">'
      f'<div class="card in">{"<h3>" + icon("search") + E(T["did_t"]) + "</h3>"}<span>{fmt("did", q=R["queries"], r=R["repos"], c=R["comps"], k=len(prim) + len(sec))}</span></div>'
      f'<div class="card in" style="animation-delay:.1s"><h3>{icon("spark")}{E(T["better_t"])}</h3><span>{fmt("better", b=R["before_hit"], a=R["hit"], t=R["total"])}</span></div>'
      f'<div class="card in" style="animation-delay:.2s"><h3>{icon("shield")}{E(T["checked_t"])}</h3><span>{E(T["checked"])}</span></div>'
      f'<div class="card inv in" style="animation-delay:.3s"><h3>{icon("list")}{E(T["todo_t"])}</h3><span>{fmt("todo_n", n=len(pend) + 1)}</span></div>'
      '</section>')
    # changes, surface by surface
    w(f'<h2>{E(T["changes_h"])}</h2><div class="places">')
    for s in R['surfaces']:
        name = T['github'] if s['name'] == 'github' else s['name']
        f0 = (s['h0'] / s['t0']) if s['t0'] else 0
        rows = ''.join(f'<div class="ba"><span class="mut" style="font-size:12px">{E(pl(fl))}</span><br><s>{E(old or T["empty"])}</s><br>{E(new)}</div>'
                       for fl, old, new in s['fields'])
        extra = []
        if s['lt']:
            extra.append(fmt('longtail_line', b=s['l0'], a=s['l1'], t=s['lt']))
        if s['renamed']:
            extra.append(f'{s["renamed"]} {E(T["renamed"])}')
        if s['links']:
            extra.append(f'{s["links"]} {E(T["gone_links"])}')
        if s['code']:
            extra.append(f'{s["code"]} {E(T["gone_code"])}')
        w(f'<div class="place"><div style="display:flex;justify-content:space-between;gap:8px;align-items:center">'
          f'<b style="display:flex;gap:8px;align-items:center">{icon("branch" if s["name"] == "github" else "page")}{E(name)}</b></div>'
          f'<div class="n">{s["h0"]} → {s["h1"]}<span class="mut" style="font-size:20px;letter-spacing:0">/{s["t1"]}</span></div>'
          f'<div class="bar"><i style="--f:{f0:.2f}"></i></div>{rows}'
          + (f'<div class="mut" style="font-size:13px">{" · ".join(extra)}</div>' if extra else '') + '</div>')
    w('</div>')
    off = R['offsite']
    if off:
        bits = []
        if off.get('about'):
            bits.append(f'<div><span class="mut">{E(T["about"])}:</span> {E(off["about"])}</div>')
        if off.get('topics'):
            bits.append(f'<div><span class="mut">{E(T["topics"])}:</span> <span class="mono">{E(" · ".join(off["topics"]))}</span></div>')
        if off.get('homepage'):
            bits.append(f'<div><span class="mut">{E(T["homepage"])}:</span> <span class="mono">{E(off["homepage"])}</span></div>')
        w(f'<div class="place" style="margin-top:12px"><b>{E(T["offsite_h"])} · '
          f'{E(T["applied"] if off.get("applied") else T["proposed"])}</b>{"".join(bits)}</div>')
    # what the run can prove: in the files, next to the pages that rank, and on the published copy
    pr = R['proof']
    head = lambda ic, t: f'<b style="display:flex;gap:8px;align-items:center">{icon(ic)}{E(t)}</b>'  # noqa: E731
    w(f'<h2>{E(T["proof_h"])}</h2><div class="places">')
    w(f'<div class="place">{head("page", T["proof_files_t"])}'
      f'<div class="n">{pr["before"]} → {pr["after"]}<span class="mut" style="font-size:20px;letter-spacing:0">/{pr["total"]}</span></div>'
      f'<span>{fmt("proof_files", b=pr["before"], a=pr["after"], t=pr["total"])}</span></div>')
    if pr['rivals']:
        w(f'<div class="place">{head("search", T["proof_rivals_t"])}'
          + ''.join(f'<div class="ba">{fmt("proof_rival", n=r["pages"], t=r["of"], p=r["phrase"])} <b>'
                    f'{E(T["rival_keep"] if r["before"] and r["after"] else T["rival_gain"] if r["after"] else T["rival_miss"])}</b></div>'
                    for r in pr['rivals']) + '</div>')
    live_t = T['proof_live_' + R['mode']]
    if R['track']:
        n, when = R['track_sum'], R['track_when']

        def cell(r, key):
            v = r[key]
            if r['source'] == 'gsc':
                return T['pos_none'] if v is None else T['pos_avg'].format(n=v, i=r['imp'][0 if key == 'before' else 1])
            return T['rank_pos'].format(n=v) if v else T['pos_out'].format(n=r['depth'])

        w(f'<div class="place">{head("shield", live_t)}'
          f'<span>{fmt("live_sum", up=n["improved"], same=n["same"], down=n["worse"], unk=n["unknown"])}</span>'
          + ''.join(f'<div class="ba"><span class="mut" style="font-size:12px">{E(T["src_" + r["source"]])}</span><br>{E(r["q"])}<br>'
                    f'<s>{E(cell(r, "before"))}</s> → {E(cell(r, "after"))} · <b>{E(T["v_" + r["verdict"]])}</b></div>' for r in R['track'])
          + '<div class="mut" style="font-size:13px">'
          + (fmt('live_dates', d=when['live_since'], m=when['measured']) + ' ' if when['measured'] else '')
          + (fmt('live_gsc', b=when['gsc'][0], a=when['gsc'][1]) + ' ' if when['gsc'] else '')
          + f'{E(T["live_caveat"])}</div></div>')
    else:
        w(f'<div class="place">{head("shield", live_t)}<span class="mut">{E(T["live_none_" + R["mode"]])}</span></div>')
    w('</div>')
    # words
    w(f'<h2>{E(T["words_h"])}</h2><div class="tiers">')

    def tier_box(shape, title, desc, items, body):
        return (f'<div class="tier"><h4><span class="{shape}"></span>{E(title)} · {len(items)}</h4>'
                f'<div class="mut" style="font-size:13px;margin-bottom:8px">{E(desc)}</div>{body}</div>')

    w(tier_box('sq', T['tier_primary'], T['tier_primary_d'], prim, ''.join(
        f'<div class="kw">{E(k["phrase"])}<small>{E(", ".join(dict.fromkeys(pl(p) for p in k["places"])))} · {E(k["lang"])}</small></div>' for k in prim)))
    w(tier_box('ci', T['tier_secondary'], T['tier_secondary_d'], sec, ''.join(
        f'<div class="kw">{E(k["phrase"])}<small>{E(", ".join(dict.fromkeys(pl(p) for p in k["places"])))} · {E(k["lang"])}</small></div>' for k in sec)))
    w(tier_box('tr', T['tier_long'], fmt('in_text', a=lt_hit, t=len(longt)), longt, ''.join(
        f'<div class="kw">{E(k["phrase"])}</div>' for k in longt[:12])))
    w(tier_box('xx', T['tier_disc'], T['tier_disc_d'], disc, ''.join(
        f'<div class="kw">{E(k["phrase"])}<small>{E(k.get("reason", ""))}</small></div>' for k in disc[:12])))
    w('</div>')
    if lhd:
        w(f'<h2>{E(T["speed_h"])}</h2><div class="rings">')
        for key, before, after in lhd['scores']:
            a100 = round(after * 100)
            b100 = round(before * 100) if before is not None else None
            w(f'<div class="rg"><svg class="ring" viewBox="0 0 36 36" width="70" height="70" aria-hidden="true">'
              f'<circle class="trk" cx="18" cy="18" r="15.915"/><circle class="val" cx="18" cy="18" r="15.915" '
              f'style="--o0:{100 - (b100 if b100 is not None else 0)};stroke-dashoffset:{100 - a100}"/></svg>'
              f'<b style="font-size:28px;font-weight:400">{"-" if b100 is None else b100} → {a100}</b><span>{E(T.get("cat_" + key, key))}</span></div>')
        where = lambda local: T['lh_local'] if local else T['lh_prod']  # noqa: E731
        w(f'</div><p class="mut" style="font-size:14px">{fmt("lh_note", n=lhd["n"], b=where(lhd["before_local"]), a=where(lhd["after_local"]))}</p>')
    # your part
    w(f'<h2>{E(T["todo_h"])}</h2><div class="todo">')
    for i, x in enumerate(pend, 1):
        w(f'<div class="td"><span class="n mono">{i:02d}</span><span>{E(x)}</span></div>')
    w(f'<div class="td"><span class="n mono">{len(pend) + 1:02d}</span><b>{E(T["notdone"])}</b></div></div>')
    # details
    w(f'<h2 style="font-size:24px">{E(T["more"])}</h2>')
    det = [f'<div>{fmt("research_q", n=R["queries"])}: ' + E(', '.join(f'{k} {v}' for k, v in sorted(R['engines'].items())))
           + ' · ' + E(', '.join(f'{k} {v}' for k, v in sorted(R['langs'].items()))) + '</div>',
           f'<div>{fmt("repos", n=R["repos"])} · {fmt("comps", n=R["comps"])}</div>']
    det += [f'<div class="mut">{fmt("nogoogle", lang=x)}</div>' for x in R['nogoogle']]
    if R['own'] and R['ranks']:
        det.append(f'<div><b>{E(T["rank_h"])}</b> <span class="mono">({E(R["own"])})</span>: ' + E('; '.join(
            f'{lab}: ' + (T['rank_pos'].format(n=rk) if rk else T['rank_out']) for lab, rk in R['ranks'])) + '</div>')
    if R['serp']:
        det.append(f'<div><b>{E(T["serp_h"])}</b>: ' + E('; '.join(
            f"{s['q']} [{s['lang']}]: " + ', '.join(f'{n} {k}' for k, n in sorted(s['kinds'].items(), key=lambda x: -x[1]))
            for s in R['serp'])) + '</div>')
        det += [f'<div class="mut">{fmt("shared", a=a, b=b_, n=n)}</div>' for a, b_, n in R['overlaps']]
    if R['own_serp']:
        det.append(f'<div><b>{E(T["own_h"])}</b>: ' + E('; '.join(
            f"{s['q']} [{s['lang']}]: " + (T['rank_pos'].format(n=s['own_rank']) if s['own_rank'] else T['pos_out'].format(n=s['seen']))
            for s in R['own_serp'])) + '</div>')
    w(f'<details><summary>{icon("search")}{E(T["research_h"])}<span class="more">{E(T["more"])}</span></summary><div class="det">{"".join(det)}</div></details>')
    if lhd:
        bits = []
        if lhd['worst']:
            bits.append(f'<div><b>{E(T["slowest"])}</b>: ' + E(', '.join(
                (f'{lb_} {v / 1000:.1f} s' if u == 'ms' and v >= 1000 else (f'{lb_} {v:.0f} ms' if u == 'ms' else f'{lb_} {v:.2f}'))
                for lb_, (v, u) in lhd['worst'].items())) + '</div>')
        for wv in lhd['waivers']:
            bits.append(f'<div>{E(wv["audit"])}{" · " + E(wv["path"]) if wv.get("path") else ""} '
                        f'({E(T.get("waived_" + wv["kind"], wv["kind"]))}): {E(wv["reason"])}</div>')
        if lhd['local']:
            bits.append(f'<div class="mut">{E(T["local_https"])}</div>')
        if bits:
            w(f'<details><summary>{icon("spark")}{E(T["slowest"])}<span class="more">{E(T["more"])}</span></summary><div class="det">{"".join(bits)}</div></details>')
    if R['claims']:
        w(f'<details><summary>{icon("shield")}{E(T["claims_h"])}<span class="more">{E(T["more"])}</span></summary><div class="det">'
          + ''.join(f'<div>«{E(c)}» · {fmt("claim_src", s=src)}</div>' for c, src in R['claims']) + '</div></details>')
    q = R['quiron'] or {}
    qtext = {'used': T['q_used'], 'skipped': T['q_skipped'], 'not-installed': T['q_missing']}.get(q.get('status'), q.get('status', ''))
    w(f'<details><summary>{icon("page")}{E(T["style_h"])}<span class="more">{E(T["more"])}</span></summary><div class="det">'
      f'<div>{E(qtext)}</div>' + (f'<div class="mut">{E(q["result"])}</div>' if q.get('result') else '') + '</div></details>')
    w(f'<footer class="mut mono">{fmt("footer", v=VERSION)}</footer></div><script>{HTML_JS}</script></body></html>\n')
    return ''.join(o)


def cmd_serve(args):
    """Serve .eco/<mode>/ on localhost so the user can open report.html in a browser."""
    d = eco_dir(args, create=False)
    if not (d / 'report.html').exists():
        die('no report.html yet: run `eco.py report` first', 2)
    srv = report_server(d, args.port)
    url = f'http://127.0.0.1:{srv.server_address[1]}/report.html'
    print(f'serving {rel(args)}/ at {url} (Ctrl+C to stop)', flush=True)
    if args.open:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def report_server(directory: Path, port: int = 0):
    """A local-only static server for one folder; port 0 picks a free one."""
    import functools
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D401 - keep the agent's output clean
            pass

    return ThreadingHTTPServer(('127.0.0.1', port), functools.partial(Quiet, directory=str(directory)))


# ---------------------------------------------------------------- status

ORDER = ['init', 'brief', 'lighthouse-baseline', 'suggest', 'github', 'competitors', 'research', 'serp', 'map', 'audit-baseline',
         'audit-pre-quiron', 'quiron', 'audit-final', 'lighthouse-final', 'report']


def cmd_status(args):
    d = eco_dir(args, create=False)
    st = load(d / 'state.json', {'steps': {}}) if d.exists() else {'steps': {}}
    b = load(d / 'brief.json', {}) if d.exists() else {}
    skip = {'lighthouse-baseline', 'lighthouse-final'} if args.mode == 'readme' else {'github'}
    for s in ORDER:
        if s in skip:
            continue
        done = st['steps'].get(s)
        print(f"{'done' if done else '    '}  {s}" + (f"  ({done['at']})" if done else ''))
    nxt = next((s for s in ORDER if not st['steps'].get(s) and s not in skip), None)
    print(f'next: {nxt}' if nxt else 'all steps done')
    t = st['steps'].get('track')
    print('after publishing: track ' + (f"done ({t['at']})" if t else 'not run'))


# ---------------------------------------------------------------- CLI

def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(prog='eco.py', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', help='project root (default: current directory)')
    ap.add_argument('--mode', required=True, choices=MODES, help='readme or site: which skill this run belongs to')
    ap.add_argument('--version', action='version', version=VERSION)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('init')
    p.add_argument('--lang', required=True, help='comma-separated, e.g. en,es')
    p.add_argument('--surface', action='append', help='PATH[:LANG], e.g. README.md:en or dist/es/index.html:es')
    p.add_argument('--repo', help='OWNER/NAME on GitHub')
    p.add_argument('--force', action='store_true')
    p.set_defaults(fn=cmd_init)
    sub.add_parser('brief').set_defaults(fn=cmd_brief)

    p = sub.add_parser('suggest')
    ss = p.add_subparsers(dest='sub', required=True)
    q = ss.add_parser('urls')
    q.add_argument('--lang', required=True)
    q.add_argument('--family', required=True, choices=FAMILIES, help='which kind of search these seeds stand for')
    q.add_argument('--seed', action='append')
    q.add_argument('--seeds-file')
    q.add_argument('--depth', type=int, default=1, help='0: the seed; 1: plus two modifiers; 2: every modifier and a..z')
    q.add_argument('--engine', choices=ENGINES, default='google', help='autocomplete service; spread queries when one is rate-limited')
    q.set_defaults(fn=cmd_suggest_urls)
    q = ss.add_parser('parse')
    q.add_argument('files', nargs='*')
    q.add_argument('--top', type=int, default=40)
    q.set_defaults(fn=cmd_suggest_parse)
    q = ss.add_parser('terms', help='list every suggestion, optionally filtered')
    q.add_argument('--grep')
    q.add_argument('--lang')
    q.set_defaults(fn=cmd_suggest_terms)
    q = ss.add_parser('fetch')
    q.add_argument('--delay', type=float, default=5.0)
    q.set_defaults(fn=cmd_suggest_fetch)

    p = sub.add_parser('github')
    gs = p.add_subparsers(dest='sub', required=True)
    q = gs.add_parser('urls')
    q.add_argument('--query', action='append', required=True)
    q.set_defaults(fn=cmd_github_urls)
    q = gs.add_parser('parse')
    q.add_argument('files', nargs='*')
    q.add_argument('--top', type=int, default=25)
    q.set_defaults(fn=cmd_github_parse)

    p = sub.add_parser('competitors')
    p.add_argument('files', nargs='*')
    p.add_argument('--top', type=int, default=25)
    p.set_defaults(fn=cmd_competitors)

    p = sub.add_parser('serp')
    sp = p.add_subparsers(dest='sub', required=True)
    q = sp.add_parser('urls', help='results pages to fetch for every primary in keywords.json')
    q.add_argument('--engine', choices=SERP_ENGINES, default='ddg')
    q.add_argument('--phrase', action='append', help='another phrase to look up (with --lang)')
    q.add_argument('--lang')
    q.set_defaults(fn=cmd_serp_urls)
    sp.add_parser('parse').set_defaults(fn=cmd_serp_parse)
    q = sp.add_parser('fetch', help='fetch the planned pages without a web tool, slowly')
    q.add_argument('--delay', type=float, default=8.0)
    q.set_defaults(fn=cmd_serp_fetch)

    sub.add_parser('research').set_defaults(fn=cmd_research)
    sub.add_parser('map').set_defaults(fn=cmd_map)

    p = sub.add_parser('audit')
    p.add_argument('--save', choices=['baseline', 'pre-quiron', 'final'])
    p.add_argument('--strict', action='store_true', help='fail on any phrase not placed, not only primary ones')
    p.set_defaults(fn=cmd_audit)

    p = sub.add_parser('compare')
    p.add_argument('before')
    p.add_argument('after')
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser('claims', help='numbers, years and superlatives the new text adds, and their sources')
    p.add_argument('action', nargs='?', choices=['list', 'verify'], default='list')
    p.add_argument('--claim')
    p.add_argument('--source', help='a file in the project that states it, or a URL')
    p.add_argument('--note')
    p.set_defaults(fn=cmd_claims)

    p = sub.add_parser('quiron')
    p.add_argument('action', choices=['detect', 'record', 'reset'])
    p.add_argument('--status', choices=QUIRON_STATUSES)
    p.add_argument('--result', help="Quirón's one-line result, e.g. '15/23 in band, 0 FAIL, converged'")
    p.add_argument('--unchanged', action='store_true', help='Quirón ran and changed nothing')
    p.set_defaults(fn=cmd_quiron)

    p = sub.add_parser('offsite')
    p.add_argument('--about')
    p.add_argument('--topics', help='the full list after the change, comma-separated')
    p.add_argument('--homepage')
    p.add_argument('--applied', action='store_true')
    p.set_defaults(fn=cmd_offsite)

    p = sub.add_parser('pending')
    p.add_argument('text')
    p.set_defaults(fn=cmd_pending)

    p = sub.add_parser('lighthouse', help='site only: read an Unlighthouse run, or waive an audit that cannot reach 100')
    p.add_argument('action', nargs='?', choices=['read', 'waive'], default='read')
    p.add_argument('--stage', choices=['baseline', 'final'], help='baseline: before any edit; final: the pages the report describes')
    p.add_argument('--url', help='the address Unlighthouse scanned: production, or the local build served as static files')
    p.add_argument('--dir', default='.unlighthouse', help='Unlighthouse output folder, relative to the root')
    p.add_argument('--audit', help='waive: the Lighthouse audit id')
    p.add_argument('--path', help='waive: only on this page (default: every page)')
    p.add_argument('--kind', choices=WAIVE_KINDS, help='ceiling: cannot reach 1 for a technical reason; declined: the user said no')
    p.add_argument('--reason', help='waive: why, in one sentence the report quotes')
    p.set_defaults(fn=cmd_lighthouse)

    p = sub.add_parser('report', help='the fixed summary (report.md, English) and the page for the user (report.html)')
    p.add_argument('--lang', default='en', help='language of report.html: the one the user talks to you in (built in: en, es)')
    p.add_argument('--labels', help='JSON file with every key of `eco.py labels`, translated, for any other language')
    p.set_defaults(fn=cmd_report)
    sub.add_parser('labels', help='print the report.html labels in English, to translate for --labels').set_defaults(fn=cmd_labels)
    p = sub.add_parser('serve', help='serve report.html on 127.0.0.1 so the user can open it in a browser')
    p.add_argument('--port', type=int, default=0, help='port (default: a free one)')
    p.add_argument('--open', action='store_true', help='also open it in the default browser')
    p.set_defaults(fn=cmd_serve)
    sub.add_parser('status').set_defaults(fn=cmd_status)

    p = sub.add_parser('track', help='after publishing: repeat the saved searches and compare the position, before and after')
    ts = p.add_subparsers(dest='sub', required=True)
    ts.add_parser('urls', help='the searches of the research, to fetch again').set_defaults(fn=cmd_track_urls)
    q = ts.add_parser('fetch', help='fetch them without a web tool, slowly')
    q.add_argument('--delay', type=float, default=8.0)
    q.set_defaults(fn=cmd_track_fetch)
    q = ts.add_parser('parse', help='check the published copy carries the new text, then compare positions')
    q.add_argument('--published', help='YYYY-MM-DD the changes went public, when known (default: the first day track finds them live)')
    q.add_argument('--day', help='which raw/track/<day> folder to read (default: the newest)')
    q.set_defaults(fn=cmd_track_parse)

    p = sub.add_parser('gsc', help='site only: a Search Console queries export (CSV) of the weeks before or after publishing')
    p.add_argument('file', help='the Queries CSV of the export')
    p.add_argument('--stage', required=True, choices=['before', 'after'])
    p.add_argument('--period', required=True, help='START..END of the export, YYYY-MM-DD..YYYY-MM-DD')
    p.set_defaults(fn=cmd_gsc)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == '__main__':
    main()
