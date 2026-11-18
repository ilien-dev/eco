#!/usr/bin/env python3
"""Copy the shared engine into each skill folder.

`shared/` is the only place to edit eco.py and the references. Each skill folder must carry
its own copy, because `npx skills add` installs every skill folder on its own. Run this after
any change to `shared/`; tests/run.py fails while a copy differs.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ('eco-readme', 'eco-site')
FILES = ('scripts/eco.py', 'references/research.md', 'references/placements.md')


def main() -> None:
    for skill in SKILLS:
        for f in FILES:
            dst = ROOT / 'skills' / skill / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'shared' / f, dst)
            print(f'shared/{f} -> skills/{skill}/{f}')


if __name__ == '__main__':
    main()
