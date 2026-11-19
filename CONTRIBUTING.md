# Contributing to Eco

Thanks for wanting to help. Contributing to Eco does not only mean pull requests: a clear
issue that reports a bug or proposes an improvement is a contribution too.

Before anything else, read "What it does" and "Limits" in the [README](README.md). Eco does
one job: it finds the words people search for and puts them where search engines read them, in
your own README or website, and it proves each step with a script. **A contribution that
drifts away from that purpose will be rejected**, however well it is made.

## Nothing is guaranteed

Opening an issue or a pull request does not guarantee that it will be accepted or merged.
Every change is reviewed before it goes in, with no exceptions, including the maintainer's
own. A change can be declined for its scope, its approach or the cost of maintaining it.

## Before you start

- **Search first.** Look through the [open pull requests](https://github.com/ilien-dev/eco/pulls)
  and the [issues](https://github.com/ilien-dev/eco/issues), open and closed. Someone may
  already be working on the same thing, or it may have been discussed and declined. If you
  find it, add to that conversation instead of starting a new one.
- **For anything bigger than a small fix, open an issue first** and wait for an answer. It is
  the cheapest way to find out whether the change fits before you write it.

## Issues

Use the forms: **Bug report** or **Feature request**. One issue per problem or idea.

- A bug report says which skill, what you did, what you expected, what happened (the
  `eco.py` output word for word) and your Eco, agent and Python versions.
- A feature request says the problem first, then the solution you have in mind, and how its
  effect would be measured.
- Never paste a Search Console export, a Chrome UX Report key, a GitHub token or private data
  from your `.eco/` folder.

## Every change is measured

A new feature, or a change to something that already exists, goes in only when it is measured
and the numbers show that it adds value, or at least that nothing gets worse. A change that
looks good but cannot be measured is declined. The measurement goes in the **Measurement**
section of the PR, with the result on `main` and on your branch:

- **What a skill does** (a `SKILL.md`, a reference, the steps an agent follows): run the cases
  in `evals/eco-readme.json` and `evals/eco-site.json` with the skill from `main` and with your
  version, and give the pass rate of each, before → after. They are in the format of the
  [skill-creator](https://github.com/anthropics/skills) eval loop, which runs both versions side
  by side and adds up the results. If the change adds behavior that no case covers, add the case
  in the same PR.
- **A new check or a fix in `eco.py`**: the test in `tests/run.py` that fails on `main` and
  passes on your branch.
- **A claim about search position or traffic**: the output of `eco.py track`, `gsc`, `traffic`
  or `field` before and after, on a real README or site you can name.
- **Speed or size**: the time or the size on `main` and on the branch, measured the same way.

For a `feat`, `fix`, `perf` or `refactor` PR the section cannot say "not applicable". For
`docs`, `ci`, `chore` or `test` it can, with the reason.

## Pull requests

### One thing at a time

Each pull request does **one thing**. If you add a new research source, the PR adds that source
and nothing else: no change to the report, no rewording of a reference, no unrelated cleanup.
Those go in their own pull requests.

Keep it as simple as possible. The smaller and more focused a PR is, the easier it is to see
what it adds, whether it is done right and whether it fits Eco. A PR that mixes several changes
will be asked to split, or closed.

### Branch name

```
<type>/<1 to 4 words>
```

`<type>` is the same Conventional Commit type the title starts with: `feat`, `fix`, `perf`,
`refactor`, `docs`, `test`, `build`, `ci`, `chore`, `style` or `revert`. Then 1 to 4 words of
lowercase letters and digits joined by single hyphens.

- `feat/gsc-click-rank` ✓
- `fix/report-encoding` ✓
- `docs/contribution-rules` ✓
- `feat/GSC-Rank` ✗ (uppercase)
- `feature/gsc-click-rank` ✗ (the type is `feat`, not `feature`)
- `feat/rank-primaries-by-gsc-clicks` ✗ (five words)

### Title

The title is a [Conventional Commit](https://www.conventionalcommits.org/) of at most 72
characters: `feat: ...`, `fix: ...`, `perf: ...`, `refactor: ...`, `docs: ...`, `test: ...`,
`ci: ...`, `chore: ...`. PRs are squash-merged and the title becomes the commit on `main`, so
it has to describe the change exactly.

### Description

Start from the template GitHub fills in for you
([`.github/pull_request_template.md`](.github/pull_request_template.md)). Every section is
required and has a limit:

| Section | Limit | What goes in it |
|---|---|---|
| **What** | 280 characters | The one change this PR makes. |
| **Why** | 280 characters | The problem it solves. Link the issue (`Closes #12`). |
| **How** | 500 characters | The approach, and the main files it touches. |
| **Measurement** | 500 characters | The numbers on `main` and on the branch (see above). |
| **Evidence** | 300 characters of text | Screenshots; the tests or steps that check it. |
| **Checklist** | — | Every box ticked. |

**Evidence.** Screenshots are always welcome, one or as many as it takes to make the change
easy to understand. For a visual change (the HTML report, anything in `brand/`, how the README
renders on GitHub) they are asked for, before and after. Take them yourself or ask your agent to
take them; capture only that page or window, never the whole screen. Drag the files into the
description box on GitHub to upload them. Images, GIFs and links do not count toward the limit.
For a change with nothing to see, name the tests that cover it or say how you checked it.

A CI check verifies the branch name, the title length and the description. You can run it
yourself before opening the PR:

```
node .github/scripts/check-pr.js --branch feat/gsc-click-rank \
  --title "feat: rank primaries by search console clicks" --body-file pr.md
```

### Code

- Edit `eco.py` and the references only in `shared/`, then run `python tools/sync.py` to copy
  them into each `skills/*/` folder. `python tests/run.py` must pass; it fails while a copy
  differs. CI runs it on Linux and Windows, with Python 3.9 and the latest.
- `eco.py` stays Python 3.9+ and standard library only.
- Both skills keep `disable-model-invocation: true`.
- Code, comments and docs are in English.
- Do not edit the version in `.claude-plugin/plugin.json`; the maintainer does it on a release.

### Review

A pull request is merged only after an approval from someone with write access to the
repository (for now, the maintainer) and with every check green. A new push dismisses an
earlier approval. Answer review comments in the PR; keep extra changes for another PR.

## Working with an AI agent

The rules are the same. Agents that read `.claude/skills` or `.agents/skills` have an
`uncontributing` skill that walks through them step by step.
