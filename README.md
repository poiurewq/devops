# devops — coordinated work for humans and agents

Two agent skills that share one task board living inside your repo, synced through git so every contributor, on any machine or branch, sees the same board.

- **`/dev`** — the development workflow: tasks, branches, PRs, review, iterations.
- **`/ops`** — procedures that are not code: a playbook of flows, each run recorded on its task.

They ship and update together, and either can be installed on its own.

Public source: https://github.com/poiurewq/devops

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/poiurewq/devops/main/install.py | python3 -
```

The installer clones the package once to `~/.local/share/devops` (`$XDG_DATA_HOME` is honoured), then asks which skills to install and which agent skill directories to install them into. It looks for `~/.claude*/skills` and `~/.grok*/skills`, and offers the directories you already keep skills in as the default. Agent directories with no skills folder yet are listed separately, so an old profile is never installed into by accident. At that prompt you can pick an exact set by number or path, add any other path, or drop one from the default with `-2`. Each skill is a symlink into that one clone, so an update is a single pull.

If you already have the old `dev` skill cloned directly into a skills directory, the installer offers to replace it with a symlink. A clone holding uncommitted or unpushed work is left alone and reported.

At any prompt, `q` quits and nothing is changed; ctrl-C does the same.

Useful flags: `--dry-run` prints the plan and changes nothing; `--home DIR` puts the clone elsewhere; `--root PATH` (repeatable) and `--skills dev,ops` skip the prompts; `--yes` takes the defaults without asking. The prompts come from your terminal, so they work even though the command above pipes the script into python. With no terminal at all (a CI job, cron), the installer still links into free paths but refuses to replace an existing install unless you pass `--yes`.

Requires `git`, `python3`, and for board workflows `gh` (GitHub CLI) authenticated against the target repo.

## Getting started

In a repo (with at least one commit and a GitHub `origin`):

```text
/dev
```

That walks you through identity + board setup. Then `/dev help` for the full command map. After init, `./board` (from the product directory) is a live view — `r` refresh, `a` toggle by-area, `e` toggle expand, `c` check, `f` flows pane, `q` quit, arrows scroll, space/b page, type a task id + Enter to read it.

## Updating (`/dev skill`, `/ops skill`)

`/dev skill ...` and `/ops skill ...` act on the installed package (same subcommands, so an install with only `/ops` has them too); every other command acts on your board. The package tracks `main` on this repo, and a throttled check on common entry points prints one quiet line when you are behind. One update moves both skills.

| Command | Effect |
|---|---|
| `/dev skill` | version, auto-update state, these commands |
| `/dev skill update` | `git pull --ff-only` in the clone |
| `/dev skill update auto on` | opt-in: checks may apply updates |
| `/dev skill update auto off` | default — notify only |
| `/dev skill feedback <text>` | file a GitHub issue on this repo — bugs and ideas about the skills |

Prefs (survive pulls): `~/.config/devops-skill/config.yml`. An install that predates the dev + ops package keeps its settings: the old `~/.config/dev-skill/config.yml` is read when the new file is absent, and the first write creates the new one.

`/dev skill feedback` opens a public GitHub issue on this repo via `gh`; your agent shows you the draft first, and only version and platform are attached — no repo names, paths, or task content.

To add a skill or a skills directory later, or to repair a link, re-run the installer. It fast-forwards the clone and only acts on what changed.

## Layout (this repo)

```
install.py         # clone once, symlink each skill into your agent skill dirs
VERSION            # one semver for the package (dev and ops ship together)
lib/tasks.py       # board state API (shared)
lib/skill.py       # status / update / feedback (shared)
dev/SKILL.md       # /dev agent-facing router
dev/flows/         # /dev multi-step procedures
dev/scripts/       # shims that exec lib/ (resolve symlinks first)
ops/               # /ops, same shape
```

Each skill directory (`dev/`, `ops/`) is what gets linked into an agent's skills root; `lib/` is reached through the shims, never linked directly.
