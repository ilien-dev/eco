#!/usr/bin/env python3
"""eco: keyword research and placement checks for a README or a website.

Every step writes a JSON file under .eco/ in the project, and `report` refuses to run
until the checks behind each step pass. Python 3.9+, standard library only.

Steps, in order (run `eco.py status` to see where a run stands):
  init          write .eco/brief.json, then fill it in
  brief         check the brief; keeps a copy of every surface as it is now (the baseline)
  suggest       list Google Suggest URLs to fetch, then parse what was fetched
  github        list GitHub search URLs to fetch, then parse what was fetched
  competitors   parse fetched competitor pages and READMEs
  research      check that the research is deep enough
  map           check .eco/keywords.json against the research
  audit         check each keyword in the places the map requires; --save a snapshot
  compare       what one snapshot has and another lost: placements, links, anchors, code
  quiron        detect Quirón, record whether it was used
  offsite       record the GitHub About, topics and homepage, proposed or applied
  pending       record something left for the user
  report        the fixed summary, only when every check passes
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import html as _html
import json
import os
import re
import shutil
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


def eco_dir(args, create=True) -> Path:
    d = root_dir(args) / ECO
    if create:
        d.mkdir(exist_ok=True)
    return d


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
    for s in args.surface or []:
        path, _, lang = s.partition(':')
        kind = 'readme' if path.lower().endswith(('.md', '.markdown')) else 'html'
        brief['surfaces'].append({'path': path, 'kind': kind, 'lang': lang or brief['languages'][0]})
    if args.repo:
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
        return ['no .eco/brief.json: run eco.py init']
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
        if s.get('kind') not in ('readme', 'html'):
            errs.append(f"surface {s.get('path')}: kind must be readme or html")
        elif not p.exists():
            errs.append(f"surface {s.get('path')}: file not found (for a site, point at the built HTML)")
        elif s['kind'] == 'html' and p.suffix.lower() not in ('.html', '.htm'):
            errs.append(f"surface {s.get('path')}: an html surface must be rendered HTML, not a template")
        if s.get('lang') not in b.get('languages', []):
            errs.append(f"surface {s.get('path')}: lang {s.get('lang')!r} is not in languages")
    if any(s.get('kind') == 'html' for s in b.get('surfaces', [])):
        u = str(b.get('site_url') or '')
        if not re.match(r'https?://[^/\s]+', u):
            errs.append('site_url: the live address of the site (open it once to be sure it answers); '
                        'the audit checks the canonical and og:url against it')
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
          f'.eco/raw/suggest/{args.lang}/{args.engine}/, then: eco.py suggest parse', file=sys.stderr)


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

def cmd_github_urls(args):
    for q in args.query:
        print('https://api.github.com/search/repositories?' + urllib.parse.urlencode({'q': q, 'per_page': 30}))
    print('# best-match order, as people see it. Fetch each (or `gh api "search/repositories?q=...&per_page=30"`), '
          'save under .eco/raw/github/ (one file per query, named after it), then: eco.py github parse', file=sys.stderr)


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
            if name == 'description':
                self.meta = a.get('content', '')
            elif name in ('og:title', 'og:description', 'twitter:title', 'twitter:description', 'og:image:alt'):
                self.og.append(a.get('content', ''))
            elif name == 'og:url':
                self.urls.append(('og:url', a.get('content', '')))
        elif tag == 'link' and (a.get('rel') or '').lower() == 'canonical':
            self.urls.append(('canonical', a.get('href', '')))
        elif tag == 'img' and a.get('alt') and not self._hidden():
            self.alts.append(a['alt'])
        elif tag == 'title' and not self._hidden() and not self.title:
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
    ld_text = []
    for blob in p.jsonld:
        try:
            ld_text.append(' '.join(_strings(json.loads(blob))))
        except ValueError:
            ld_text.append(blob)
    body = re.sub(r'\s+', ' ', ' '.join(p.visible)).strip()
    return {
        'kind': 'html', 'lang': p.lang, 'title': p.title.strip(), 'meta': p.meta.strip(),
        'h1': p.headings['h1'], 'h2': p.headings['h2'], 'h3': p.headings['h3'],
        'alt': p.alts, 'og': p.og, 'jsonld': ' '.join(ld_text), 'body': body,
        'lead': p.paras[0] if p.paras else '', 'links': p.links, 'anchors': p.ids,
        'code': [], 'headings_all': p.headings['h1'] + p.headings['h2'] + p.headings['h3'],
        'urls': p.urls + [('json-ld', u) for u in re.findall(r'"(?:url|@id)"\s*:\s*"(https?://[^"]+)"', ' '.join(p.jsonld))],
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
        return ['no .eco/keywords.json'], {}
    corpus = research_corpus(d)
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
                    errs.append(f"{tag}: evidence says {e['source']}, but the phrase is not in .eco/{e['source']}"
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


def audit_pages(args, pages: dict, gh, km) -> dict:
    result = {'at': _dt.datetime.now().isoformat(timespec='seconds'), 'map_hash': map_hash(km),
              'surfaces': {}, 'placements': [], 'missing': [], 'flags': [], 'github': gh}
    brief = load(eco_dir(args) / 'brief.json', {})
    name = (brief.get('project', {}) or {}).get('name', '')
    site_host = urllib.parse.urlparse(str(brief.get('site_url') or '')).netloc.lower()
    for path, (s, pg, digest) in pages.items():
        info = {'kind': s['kind'], 'lang': s['lang'], 'hash': digest, 'h1': pg.get('h1', [])[:3],
                'lead': pg.get('lead', '')[:200], 'words': len(words(pg['body'])),
                'links': sorted(set(pg.get('links', []))), 'anchors': sorted(set(pg.get('anchors', []))),
                'code': sorted(set(pg.get('code', []))), 'headings': pg.get('headings_all', [])}
        if s['kind'] == 'html':
            info.update(title=pg['title'], meta=pg['meta'])
            if not TITLE_RANGE[0] <= len(pg['title']) <= TITLE_RANGE[1]:
                result['flags'].append(f'{path}: title is {len(pg["title"])} characters; aim for {TITLE_RANGE[0]}-{TITLE_RANGE[1]}')
            if not META_RANGE[0] <= len(pg['meta']) <= META_RANGE[1]:
                result['flags'].append(f'{path}: meta description is {len(pg["meta"])} characters; aim for {META_RANGE[0]}-{META_RANGE[1]}')
            if len(pg['h1']) != 1:
                result['flags'].append(f'{path}: {len(pg["h1"])} h1 elements; a page needs exactly one')
            if not any(k == 'canonical' for k, _ in pg.get('urls', [])):
                result['flags'].append(f'{path}: no <link rel="canonical">')
            for kind, u in pg.get('urls', []):
                host = urllib.parse.urlparse(u).netloc.lower()
                if site_host and host and host != site_host:
                    result['flags'].append(f'{path}: {kind} points to {host}, but the site answers at {site_host}')
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
    return audit_pages(args, pages, gh, km)


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
        print(f'saved .eco/audit-{args.save}.json')
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


# ---------------------------------------------------------------- Quirón

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
               status={}),
    'es': dict(title='Eco · informe de keywords', project='Proyecto', audience='Público', adjacent='adyacente',
               research='Investigación', queries='consultas de autocompletado', repos='repos de GitHub', comps='competidores',
               rank='Posición actual en GitHub', notin='fuera de los 30 primeros', map='Mapa de keywords',
               primary='primarias', secondary='secundarias', longtail='long-tail', discarded='descartadas', kw='Keyword',
               lang='Idioma', tier='Nivel', where='Dónde quedó', changes='Cambios',
               main='colocaciones de primarias y secundarias', before='antes', after='después', offsite='Fuera del repo',
               proposed='propuesto, sin aplicar', applied='aplicado', none='nada', human='Humanización',
               verify='Verificación', lost='colocaciones perdidas', flags='alertas', gone='quitado', pending='Pendiente',
               nothing='nada', dropped='Descartadas', notdone='No hecho: commit, push, pull request.',
               renamed='encabezados renombrados', links='enlaces', code='fragmentos de código', kws='keywords',
               nogoogle='Sin datos de Google para [{lang}]: sus frases se apoyan solo en Bing y DuckDuckGo.',
               status={'used': 'usado', 'skipped': 'omitido', 'declined': 'rechazado', 'not-installed': 'no instalado',
                       'pending-reload': 'instalado, pendiente de reiniciar la sesión'}),
}
TIER_LABEL = {'en': {}, 'es': {'primary': 'primaria', 'secondary': 'secundaria', 'long-tail': 'long-tail'}}


def cmd_report(args):
    d = eco_dir(args)
    st = state(args)
    errs = check_brief(args) + check_research(args) + check_map(args)[0]
    final = load(d / 'audit-final.json')
    if final is None:
        errs.append('no final audit: run `audit --save final` after the last edit')
    q = st['steps'].get('quiron')
    if q is None:
        errs.append('Quirón step not recorded: `quiron record --status used|skipped|declined|not-installed|pending-reload`')
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
        for path, g in integrity(base, final).items():
            if g['broken_internal']:
                errs.append(f'{path}: internal links broken: {", ".join(g["broken_internal"])}')
            integ[path] = g
    if errs:
        for e in errs:
            bad(e)
        sys.exit(1)

    L = LABELS.get(args.lang, LABELS['en'])
    TL = TIER_LABEL.get(args.lang, {})
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
    out.append('')
    out.append(f"**{L['map']}:** {tiers['primary']} {L['primary']}, {tiers['secondary']} {L['secondary']}, "
               f"{tiers['long-tail']} {L['longtail']}, {tiers['discarded']} {L['discarded']}.")
    out.append('')
    out.append(f"| {L['kw']} | {L['lang']} | {L['tier']} | {L['where']} |")
    out.append('|---|---|---|---|')
    for k in sorted(km['keywords'], key=lambda k: (TIERS.index(k['tier']), k['lang'], k['phrase'])):
        if k['tier'] in ('primary', 'secondary'):
            pl = sorted(where.get((k['phrase'], k['lang']), []))
            out.append(f"| {k['phrase']} | {k['lang']} | {TL.get(k['tier'], k['tier'])} | {', '.join(pl) or '-'} |")
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
    out.append(f"**{L['human']}:** Quirón {L['status'].get(q['status'], q['status'])}" + (f" · {q['result']}" if q.get('result') else ''))
    out.append('')
    main_rows = [p for p in final['placements'] if p['tier'] in ('primary', 'secondary') and p['surface'] != 'github (proposed)']
    hit = sum(1 for p in main_rows if p['count'] > 0)
    out.append(f"**{L['verify']}:** {L['main']} {hit}/{len(main_rows)}, {len(lost)} {L['lost']}, "
               f"{len(final['flags'])} {L['flags']}.")
    out.append('')
    pend = st.get('pending', [])
    out.append(f"**{L['pending']}:**" + ('' if pend else f" {L['nothing']}."))
    out += [f'- {x}' for x in pend]
    out.append(f"- {L['notdone']}")
    text = '\n'.join(out) + '\n'
    (d / 'report.md').write_text(text, encoding='utf-8')
    print(text)
    mark(args, 'report', hash=sha(text))


# ---------------------------------------------------------------- status

ORDER = ['init', 'brief', 'suggest', 'github', 'competitors', 'research', 'map', 'audit-baseline',
         'audit-pre-quiron', 'quiron', 'audit-final', 'report']


def cmd_status(args):
    d = eco_dir(args, create=False)
    st = load(d / 'state.json', {'steps': {}}) if d.exists() else {'steps': {}}
    b = load(d / 'brief.json', {}) if d.exists() else {}
    needs_github = any(s.get('kind') == 'readme' for s in b.get('surfaces', []))
    for s in ORDER:
        if s == 'github' and not needs_github:
            continue
        done = st['steps'].get(s)
        print(f"{'done' if done else '    '}  {s}" + (f"  ({done['at']})" if done else ''))
    nxt = next((s for s in ORDER if not st['steps'].get(s) and not (s == 'github' and not needs_github)), None)
    print(f'next: {nxt}' if nxt else 'all steps done')


# ---------------------------------------------------------------- CLI

def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(prog='eco.py', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root', help='project root (default: current directory)')
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

    p = sub.add_parser('quiron')
    p.add_argument('action', choices=['detect', 'record', 'reset'])
    p.add_argument('--status', choices=['used', 'skipped', 'declined', 'not-installed', 'pending-reload'])
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

    p = sub.add_parser('report')
    p.add_argument('--lang', default='en', help='language of the labels: en or es')
    p.set_defaults(fn=cmd_report)
    sub.add_parser('status').set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == '__main__':
    main()
