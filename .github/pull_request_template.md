<!--
Title: a Conventional Commit of at most 72 characters, e.g. "feat: rank primaries by search console clicks".
Branch: feature/ + 1 to 4 lowercase words joined by hyphens, e.g. feature/gsc-click-rank.
One PR = one change. Read CONTRIBUTING.md before opening it.
Comments like this one are removed before the limits are counted.
-->

## What
<!-- At most 280 characters. The one change this PR makes, in one or two sentences. -->

## Why
<!-- At most 280 characters. The problem it solves for the people who use Eco. Link the issue: "Closes #12". -->

## How
<!-- At most 500 characters. The approach, and the main files it touches (shared/scripts/eco.py, a SKILL.md, a reference). -->

## Measurement
<!--
At most 500 characters. Required for feat, fix, perf and refactor: what you measured on main and on this
branch, with the numbers, before -> after. It must show that the change adds value, or at least that
nothing gets worse. Evals: the evals/eco-*.json cases, pass rate on main against this branch. Search:
eco.py track, gsc, traffic or field output. A new check: the test that fails on main and passes here.
Other types (docs, ci, chore, test): "Not applicable:" and the reason.
-->

## Evidence
<!--
At most 300 characters of text; images, GIFs and links do not count.
Screenshots are always welcome, and asked for in any visual change (report.html, brand/, how the README renders):
before and after. Capture only that page or window, never the whole screen. Drag the files into this box on GitHub.
Other changes: the tests that cover it, or how you checked it by hand.
-->

## Checklist
- [ ] This PR does one thing, and nothing else is mixed in
- [ ] I searched open PRs and issues and nobody is already doing this
- [ ] I edited `shared/` only, ran `python tools/sync.py`, and `python tests/run.py` passes
- [ ] The Measurement section has numbers from main and from this branch, or says why it does not apply
- [ ] I did not change the version in `.claude-plugin/plugin.json`
