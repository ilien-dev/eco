---
name: uncontributing
description: Use before opening an issue, creating a branch, committing for a pull request, or writing a pull request title or description in the Eco repository. Walks through CONTRIBUTING.md (one change per PR, feature/ branch names, Conventional Commit titles, measured changes, the description format with character limits, screenshots) and checks the result with .github/scripts/check-pr.js.
---

# Contributing to Eco

`CONTRIBUTING.md` is the source of truth; this skill is the order to apply it in. If the two
disagree, follow `CONTRIBUTING.md` and point out the difference.

## 1. Is it in scope, and is it new?

- Read "What it does" and "Limits" in `README.md`. Eco finds the words people search for and
  puts them in the user's own README or website, proving each step with `eco.py`. If the change
  does not serve that, say so and stop: it will be rejected.
- Search for the same work before writing anything:
  ```
  gh pr list --repo ilien-dev/eco --state all --search "<keywords>"
  gh issue list --repo ilien-dev/eco --state all --search "<keywords>"
  ```
  If a PR or issue already covers it, report it to the user instead of duplicating it.

## 2. One thing only

Name the single change in one sentence. If the sentence needs an "and", it is two PRs: for
example a new research source **and** a report change **and** a reworded reference are three
pull requests. Propose the split to the user and do the first one. Leave unrelated fixes you
notice for later; mention them, do not include them.

## 3. Can it be measured?

A new feature or a change to existing behavior goes in only when the numbers show it adds
value, or at least that nothing gets worse. Decide how before writing code, and take the
`main` reading first, since it is lost once the code changes:

- Skill behavior (`SKILL.md`, references): the cases in `evals/eco-readme.json` and
  `evals/eco-site.json`, run with the skill from `main` and with the new one (the skill-creator
  eval loop: old version as baseline). Pass rate before → after. Add a case if none covers the
  new behavior.
- A check or a fix in `eco.py`: a test in `tests/run.py` that fails on `main` and passes after.
- Search position or traffic: `eco.py track`, `gsc`, `traffic` or `field`, before and after.
- Speed or size: the same measurement on `main` and on the branch.

If none of these can show the effect, tell the user the change will likely be declined, before
doing the work.

## 4. Branch

`feature/` followed by 1 to 4 lowercase words (letters and digits) joined by single hyphens,
for every kind of change: `feature/gsc-click-rank`, `feature/fix-report-encoding`.
Regex: `^feature/[a-z0-9]+(-[a-z0-9]+){0,3}$`.

## 5. Code

Follow the repository's `CLAUDE.md`/`AGENTS.md`. Edit only `shared/`, never the copies in
`skills/*/`. Before committing:
```
python tools/sync.py
python tests/run.py
```
It must pass; report failures with their output. `eco.py` stays Python 3.9+ and standard
library only. Do not change the version in `.claude-plugin/plugin.json`.

## 6. Title

A Conventional Commit of at most 72 characters, lowercase after the type, no final period. It
becomes the squash commit on `main`. Pick the type that tells the truth about the change:
`feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `ci`, `chore`.

## 7. Description

Copy `.github/pull_request_template.md` and fill every section. Limits are counted after HTML
comments are removed; delete the template comments anyway.

| Section | Limit | Content |
|---|---|---|
| `## What` | 280 chars | The one change, one or two sentences. |
| `## Why` | 280 chars | The problem for users. `Closes #N` when there is an issue. |
| `## How` | 500 chars | The approach and the main files. |
| `## Measurement` | 500 chars | `main` → branch, with the numbers from step 3. |
| `## Evidence` | 300 chars of text | Images, GIFs and links do not count. |
| `## Checklist` | — | Every box ticked, honestly. Untick and explain if one is not true. |

For `feat`, `fix`, `perf` and `refactor`, Measurement cannot be "not applicable"; for `docs`,
`ci`, `chore` and `test` write `Not applicable:` and the reason. Write plainly: what changed,
not how hard it was. No headings beyond these, no summary at the end.

**Evidence.**
- Recommend screenshots to the user for every PR, and offer to take them: one or several,
  whatever makes the change easiest to understand. For a visual change (the HTML report served
  with `eco.py serve`, anything in `brand/`, the README as GitHub renders it) they are asked for,
  before and after.
- Capture only that page or window (a headless browser screenshot of the URL, or the window by
  its handle), never the whole screen: it can catch the user's other windows. Save the files in
  a temporary folder, not in the repository.
- GitHub has no API to upload images into a PR description. Open the PR, then give the user the
  absolute paths of the files and ask them to drag them into the description. Put a placeholder
  line in Evidence meanwhile, e.g. `Screenshots: to be attached.`
- Non-visual change: name the tests that cover it, or the exact steps used to check it.

## 8. Check before opening

Write the description to a temporary file and run:
```
node .github/scripts/check-pr.js --branch <branch> --title "<title>" --body-file <file>
```
The same check runs in CI as the required status `Branch name and description`. Fix every
problem it lists, then open the PR:
```
gh pr create --title "<title>" --body-file <file>
```
Do not merge. Every PR needs an approval from someone with write access, and the maintainer
decides.

## Issues

Issues are contributions too. Use the forms in `.github/ISSUE_TEMPLATE/` (blank issues are
disabled): one bug or one idea per issue, the problem before the solution, how it would be
measured, and search first. Never include Search Console exports, a Chrome UX Report key, a
GitHub token or private data from the user's `.eco/` folder.
