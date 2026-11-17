# /<skill> skill … — the installed skill, not the board

`/<skill>` is the skill in use. Everything under `/<skill> skill` acts on the **installed skill**, never on the user's board, flows or repo — `/<skill> skill feedback` is feedback on *this tool*, not on their work.

`dev` and `ops` ship together in the `devops` package, installed as one clone (see https://github.com/poiurewq/devops) with each skill symlinked into the agent's skills directory. One update moves both skills. Prefs live at `~/.config/devops-skill/config.yml` and survive updates.

| Invocation | Script |
|---|---|
| `/<skill> skill` | `SKILL_CMD status` |
| `/<skill> skill update` | `SKILL_CMD update` |
| `/<skill> skill update auto` | `SKILL_CMD auto` (report current setting) |
| `/<skill> skill update auto on/off` | `SKILL_CMD auto on/off` |
| `/<skill> skill feedback <text>` | `SKILL_CMD feedback --title "<t>" [--body "<b>"]` |

The throttled `SKILL_CMD check` when-list stays in SKILL.md — it runs on common entry points, not only here.

## Feedback to the maintainers (`/<skill> skill feedback`)

Opens an issue on poiurewq/devops — the maintainer inbox for the skills themselves. Not for the user's own work, and not a way to file board tasks (that is `/<skill> add <task-or-goal>`); if they seem to mean their own project, ask before filing.

Draft a title (one line) and body (what they saw and what they expected) from what the user said. **Show the draft and get their OK before running the command**, and say plainly what it does: files a GitHub issue on the public poiurewq/devops repo, which cannot be quietly undone. The script appends skill version, install kind, python, and OS. Never put repo or project names, paths, branch or client names, or task and flow content in the title or body — this is a public repo, and boards carry other people's business. Report the issue URL the script prints.
