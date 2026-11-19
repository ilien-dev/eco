### Code

- Edit `eco.py` and the references only in `shared/`, then run `python tools/sync.py` to copy
  them into each `skills/*/` folder. `python tests/run.py` fails while a copy differs. CI runs
  it on Linux and Windows, with Python 3.9 and the latest.
- `eco.py` stays Python 3.9+ and standard library only.
- Both skills keep `disable-model-invocation: true`: they run only by hand.
- Code, comments and docs are in English.

### Evals

`evals/eco-readme.json` and `evals/eco-site.json` are in the format of the
[skill-creator](https://github.com/anthropics/skills) eval loop, which runs the skill from
`main` and yours side by side and adds up the results.

### Issues

- A bug report names the skill, the `eco.py` output word for word and your Eco, agent and
  Python versions.
- A feature request says how its effect on search position would be measured.
- Never paste a Search Console export, a Chrome UX Report key, a GitHub token or private data
  from your `.eco/` folder.
