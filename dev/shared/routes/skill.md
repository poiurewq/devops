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
| `/<skill> skill uninstall` | `SKILL_CMD uninstall [--remove-config]` (*Uninstall* below) |

The throttled `SKILL_CMD check` when-list stays in SKILL.md — it runs on common entry points, not only here.

## Feedback to the maintainers (`/<skill> skill feedback`)

Opens an issue on poiurewq/devops — the maintainer inbox for the skills themselves. Not for the user's own work, and not a way to file board tasks (that is `/<skill> add <task-or-goal>`); if they seem to mean their own project, ask before filing.

Draft a title (one line) and body (what they saw and what they expected) from what the user said. **Show the draft and get their OK before running the command**, and say plainly what it does: files a GitHub issue on the public poiurewq/devops repo, which cannot be quietly undone. The script appends skill version, install kind, python, and OS. Never put repo or project names, paths, branch or client names, or task and flow content in the title or body — this is a public repo, and boards carry other people's business. Report the issue URL the script prints.

## Uninstall (`/<skill> skill uninstall`)

Removes both skills from this machine: every dev and ops link in the agent skills directories that points into the clone, then the clone itself (kept, with the reason, when it holds uncommitted or unpushed work). Copies built with `--copy-to` and everything in the user's repos — boards, flows, `.dev/`, `./board` — stay; the script refuses on a copy and says to delete its folder instead. Before running it, say exactly that and ask for a yes, and ask whether to remove their prefs (`~/.config/devops-skill/config.yml`) too — only on a yes pass `--remove-config`. The command then runs the installer without further prompts, so the chat yes is the consent. It removes the skill this session runs from, so it is the session's last action: run it, report its output, and run nothing from the skill after it. The same uninstall from a terminal is the README one-liner.
