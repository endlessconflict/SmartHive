# Agent skills

Prompt-only skills for AI coding agents (Claude Code and others that read `.claude/skills/`). Vendored as plain files, without the upstream plugins' Node.js hooks.

| Skill | Upstream | Commit | License | What it does |
|---|---|---|---|---|
| `ponytail` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 552acd5 | MIT | Minimal code: YAGNI, stdlib first, shortest working diff, one runnable check per non-trivial logic |
| `caveman` | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | 99aafe1 | Apache-2.0 | Terse chat replies. Docs, code, commits and tickets stay in normal prose |

Update: copy the upstream `SKILL.md` again and bump the commit in this table.
