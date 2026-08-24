---
name: dev
description: Multi-contributor task board and dev workflow for a repo, or per-subdir boards in a monorepo. Use for /dev and subcommands (init, add, plan, board, kanban, status, pick, implement, review, audit, auto, absorb, change, delete, show, config, area, meta, iteration, update), and whenever the user asks to add/see/assign/implement/review tasks on the repo's task board, or asks "what should I work on".
---

# dev — coordinated development for humans and agents

One task board per product (a repo, or a subdir of a monorepo), shared by every contributor — human or agent — across worktrees and machines. You are the interface: parse intent, run the script for all board state, apply judgment yourself. When the routing table names a `flows/*.md`, read that file and follow it — don't improvise the flow.

`SKILL_DIR` = the directory containing this file.

`TASKS` = `python3 SKILL_DIR/scripts/tasks.py`, run from inside the repo. It targets the nearest board at or above cwd, or `--scope <subdir>`; there is no single-board fallback, so monorepo work runs from the product directory.

`SKILL_CMD` = `python3 SKILL_DIR/scripts/skill.py` — acts on the installed skill, not the board (`flows/skill.md`).

## Script synopsis

`--scope` goes BEFORE the subcommand. Don't guess flags. This index is enough for names; full flag wall is `flows/cli.md` — load it only when a flag is not already spelled here or in the flow you are following.

```
TASKS --scope <subdir> <subcommand> ...
TASKS init --name <handle> [--scope <subdir>] [--integration <branch>]
           [--parent <branch>] [--iteration N] [--iteration-name <name>]
           [--iteration-started YYYY-MM-DD]
TASKS whoami
TASKS config [<key> [<value>]]          # integrator, parent_branch, iteration,
                                        # iteration_name, iteration_started
TASKS area list | set <name> [--desc "<one-line scope>"] | rm <name> [--force]
TASKS add --title "<title>" [--area <m>] [--deps <id,id>]
          [--desc "<1–3 sentences>"] [--assignee <who>]
          [--kind umbrella|recurring] [--cadence <N><unit>]
          [--status proposed|backlog|planned|later]
TASKS update <id> [--title] [--area] [--status] [--kind umbrella|recurring|""]
          [--assignee <who>|""] [--branch <b>|""] [--pr]
          [--needs decision|""] [--deps] [--append "<paragraph>"]
          [--desc "<new body>"] [--cadence <N><unit>] [--last-run <date>|""]
          [--status later] [--status not-planned --reason "<why>"]
TASKS verify <id> "<how the children met the goal>"   # close an umbrella
TASKS delete <id>
TASKS show <id>
TASKS collisions <id[,id…]>             # 2 doing-blocked, 3 PR open
TASKS related "<text>"                  # run before every add
TASKS list [--assignee <who>] [--status <s>] [--needs decision] [--json]
TASKS recur list [--due] | recur ran <id> [--date YYYY-MM-DD]
TASKS board [--expand] [--by-area] [--watch]
TASKS iteration
TASKS iteration-close [--force]
TASKS iteration-new <branch> [--parent <branch>] [--name <name>]
                    [--iteration N] [--iteration-started YYYY-MM-DD]
TASKS iteration-land [--create-only] [--title T] [--body B]
TASKS claim <id> [--assignee <who>] [--branch <b>] [--stack-on <id>]
                                        # refuse if diverged or untagged
TASKS diff <id>
TASKS ship <id> --shipped "<what actually shipped>"
                [--message M] [--title T] [--body B]
                [--version-intent <intent>] [--base <branch>]
                [--batch <id,id,…>]
TASKS ready <id>                        # draft → review; the user's call
TASKS unready <id>                      # review → draft; assignee or
                                        # integrator only
TASKS batch-gate --ids <id,id,…>
TASKS restack --ids <id,id,…> [--after N] [--onto <ref>]
              [--retarget] [--dry-run]
TASKS preflight [--park|--discard]
TASKS land <id>
TASKS cleanup <id>
```

Caveats: `--append` adds to a body (no prior `show` needed, can't truncate); `--desc` **replaces** it — only for genuine rewrites. Flags combine in one call; an empty string (`--assignee ""`, `--needs ""`, `--branch ""`) clears a field; multi-word values need quoting. `--area` takes a comma-separated list (`--area "cli, docs"`); `all` is reserved (see Area stewardship). When no board is found the error lists known boards — cd in, or pass `--scope`. **Whenever a `TASKS` command exits non-zero or prints `error: …`, surface that output to the user verbatim and stop** — never hide it, paraphrase it away, or paper over it with manual git/gh.

## Ground rules

- **Never edit `.tasks/` by hand and never commit to it from a code branch.** All board reads/writes go through `TASKS`, which serializes every mutation through the integration branch on the remote — that is what makes the board conflict-free. Bypassing it breaks the model.
- **Scripted git lifecycle.** Never improvise multi-step git/gh for task work: use `claim`, `diff` (self-review from the task worktree), `ship`, `ready`/`unready`, `land`/`cleanup`, `preflight` (park/discard), `iteration-land`, and for stacks `restack`/`batch-gate`. Flows decide and call; they don't spell out raw sequences to re-invent. Read-only observation (`gh pr view` / `gh pr diff`) and human review actions stay outside those helpers.
- **PR is the only merge flow.** GitHub and an authenticated `gh` are assumed; init walks the user through setup, and implement/review are gated on `gh auth status` succeeding. Task branches start from `origin/<integration>`; if local integration is ahead on this board's scope, implement stops to park-as-PR or discard first (flows/implement.md). Auto never parks or discards — it skips and reports.
- **Humans decide; agents draft.** Review verdicts, design-fork resolutions, and proposal approvals belong to the user. Interactive flows surface the question and wait; auto files board-native proposals (`proposed` status, `needs: decision`) and never decides them.
- **User specs are one guess.** Specifications the user lays out — on add, or when recommending changes during implement or review — are one guess at an implementation and may not be the best. When any part doesn't make sense or could be clearly improved, say so; when something is unclear, ask. The commitment is to a good product, not to the user's words.
- **Vendor-neutral**: product docs live in `AGENTS.md` at the directory that owns the code (create or update the nearest one that covers what you touched — a nested package's rule does not go in the repo root). Record non-obvious invariants there: conventions and decided architectural, procedural, or domain rules, not only implementer gotchas. Keep it lean; skip anything obvious from the code. If `CLAUDE.md` is present, it is a symlink to that `AGENTS.md` — not the reverse (promote a lone `CLAUDE.md`; if both are regular files, fold unique content into `AGENTS.md`, then replace `CLAUDE.md` with a symlink).
- **Under-specify tasks, and write short.** A task description is a few sentences: the goal. Details get resolved at implementation time. The same brevity applies to everything else you write — appended decisions, PR bodies, reports to the user. Review bandwidth is the scarcest resource on the board, and verbose text spends it. Never produce long specs, plans, or status reports the user didn't ask for.
- **Do not manufacture specifications.** When adding or modifying a task, never write constraints, non-goals, interfaces, or other requirements the user did not explicitly state or approve. Future agents treat the task file as human-approved. Non-goals belong on the task only when the user said them.
- Natural-language intents map onto subcommands; fulfill them and mention the keyword once ("done — btw, `/dev pick 12` does this directly"). Always show a suggested command's argument shape — `/dev add <task-or-goal>`, `/dev implement <id[, id…]|goal>`, `/dev meta [id-or-area]` — never a bare `/dev add ...`, which leaves the user guessing what goes there.
- **New work goes through `/dev add`.** Explicit `/dev add`, freeform "we should…", or a goal after `/dev` all land on the same path; the agent triages inside add (direct file, plan, or shape) — never ask the user to pick a path. `/dev plan` is a legacy alias. `/dev implement <goal>` with no matching board task also files via add first, then builds (flows/implement.md).

## State layout (per board)

- `<scope>/.tasks/` — tracked, lives only on that board's integration branch: `NNN.md` (one file per task), `board.yml` (`schema_version`, integration_branch, parent_branch, iteration, iteration_name, iteration_started, integrator, contributors), `areas.md` (area names + one-line scopes), `log.md` (past-iteration index), `archive/<n>-<slug>/NNN.md` (every closed task, verbatim — the full record the log only indexes; dir is `archive/<n>/` when unnamed). `iteration` is a positive integer (identity, default 1 at init); `iteration_name` is an optional display label; `iteration_started` is `YYYY-MM-DD` (stamped at init / iteration-new, settable to match an external calendar). Close records both dates as `started:` / `closed:` lines under `## <n>` (or `## <n> — <name>`). Ship titles PRs `[n/T<id>] …`. Missing `schema_version` means 0; see product `AGENTS.md` for compatibility rules when changing board schema. Task frontmatter may carry `kind` (`umbrella` = goal parent; `recurring` = perpetual work on a cadence, see Recurring below; absent/empty = normal). An umbrella's `deps` are its **direct children** (leaves or nested umbrellas) — hierarchy is the dep graph among `kind: umbrella` nodes, with no separate parent field. Closing one is a verification pass, never automatic (see Umbrella close below). A recurring task also carries `cadence` and `last_run`, both omitted when empty. `TASKS board` is an index (one line per status of task ids) then in-play tasks one per line, umbrella children indented under their parent (which also carries a leaf status rollup); done, later, and not-planned fold to a count. `--expand` adds those three to the index and the list — it is not an umbrella un-collapse; `--by-area` indexes by area instead of status (same nesting; folded statuses stay counts on last index lines unless `--expand`).
- `<scope>/.dev/` — product-local, gitignored, per-checkout (root board → `.dev/` at the git toplevel): `identity`, `boards.json` (scope→branch cache), `board/` (hidden worktree on a private branch `_dev-board` or `_dev-board-<scope>`), `worktrees/` (task worktrees).
- `<scope>/TASKS.md` — derived kanban view, gitignored, regenerated by `board`.
- `<scope>/board` — local live viewer (`r` refresh, `a` toggle by-area, `e` toggle expand, `q` quit, arrows scroll, type a task id + Enter for area collisions), gitignored, written by `init` if missing and refreshed by `init` / `board` while still a stock wrapper. `./board update` rewrites it from the installed skill even if edited. Not `.dev/board` (that is the board worktree).

Statuses: `proposed` (auto-filed, awaiting human approval) → `backlog` → `planned` → `doing` → `draft` → `review` → `done`. `ship` always opens the PR into `draft`: the work is out, but not on the integrator's queue. `TASKS ready <id>` promotes it (draft → review, and marks the PR ready) and `TASKS unready <id>` pulls it back — both are human calls, never an agent's own move, and `update --status draft|review` on a task with a PR is refused and redirected to them. `land` refuses a draft. Off to the side: `later` — intended, not this iteration (reseeds on iteration-new; see below); `not-planned` — deliberately decided against (see below). `done`, `later`, and `not-planned` do not block an iteration close. A `recurring` task never reaches `done`: it re-arms to `backlog` after each run (see below). `needs: decision` marks an open design fork awaiting a human call, detailed in the task body.

## Routing

| Invocation | Action |
|---|---|
| `/dev` (bare) | Read `flows/first-contact.md`. |
| `/dev help` | Read `flows/first-contact.md`. No board/identity → same setup path as bare. |
| `/dev init` | Read `flows/init.md` (identity, board creation/adoption, gh setup, areas). |
| `/dev add <task-or-goal>` | Read `flows/add.md` (triage, then direct add, plan, or shape). |
| `/dev plan <goal>` | Alias of `/dev add` (same triage). |
| Freeform new work | Same as `/dev add`. |
| `/dev implement <id[, id…]|goal>` | Read `flows/implement.md` (multi → also `flows/implement-batch.md`; claim, forks, PR). |
| `/dev review [id[, id…]]` | Read `flows/review.md` (inbox; multi-id → `flows/review-batch.md`; a `draft` id is its author's own loop — only your own drafts, and `auto/…` ones, reach the inbox). |
| `/dev audit [area]` | Read `flows/audit.md` (scan the codebase for work worth filing; offers to schedule a recurring audit when none covers that scope). Not `/dev review`, which is the PR inbox. |
| `/dev auto` | Read `flows/auto.md` (autonomous implement cycle). |
| `/dev absorb <source>` | Read `flows/absorb.md` (import an external task list). |
| `/dev iteration ...` | Read `flows/iteration.md` (show / close / new). |
| `/dev board` / `kanban` | `TASKS board` (status index + in-play list); `TASKS board --by-area` for the area cut; then PR state refresh (below). |
| `/dev meta [id-or-area]` | Read `flows/meta.md` (pressure the board; optional focus). `/dev meta area` (or `areas`) is reserved: area-validity pass only. Freeform "does this board still make sense?" too. |
| `/dev status` | Your plate — see "Status" below. |
| `/dev pick <id-or-desc>` | `TASKS update <id> --status planned --assignee <me>`; if already assigned to someone else, confirm the takeover with the user first. |
| `/dev change <id> <what>` / `modify` | Map onto `TASKS update <id> --...`; show the result. |
| `/dev delete <id>` | Confirm, then `TASKS delete <id>`. |
| `/dev drop <id>` / "we're not doing this" | Not planned, below — offer delete as the alternative and let the user pick. |
| `/dev show <id>` | `TASKS show <id>`. |
| `/dev config [key] [value]` | `TASKS config ...` (settable: integrator, parent_branch, iteration, iteration_name, iteration_started). |
| `/dev area ...` | Area stewardship, below. |
| `/dev skill` | Read `flows/skill.md` (`SKILL_CMD status`). |
| `/dev skill update` | Read `flows/skill.md` (`SKILL_CMD update`). |
| `/dev skill update auto on/off` | Read `flows/skill.md` (`SKILL_CMD auto on/off`). |
| `/dev skill feedback <text>` | Read `flows/skill.md`. |

Before any board operation, check identity with `TASKS whoami` — never probe the filesystem for it yourself. Identity is **product-local** (`<scope>/.dev/identity`), so run from the product directory or pass `--scope`; a bare monorepo root with no board there errors. If `whoami` errors, run the init flow. Given a description instead of an id, run `TASKS list`, match, confirm if not obvious. **`/dev implement` only:** if nothing matches, run the `/dev add` path first (`flows/add.md`), then continue implement on the new task(s) — details in `flows/implement.md`. Other id-or-desc commands (`pick`, `show`, …) still require a match.

## Skill check

Run `SKILL_CMD check` once at the start of bare `/dev`, `/dev help`, `/dev init`, `/dev add` (including freeform add and `/dev plan`), `/dev board` / `kanban`, `/dev implement`, `/dev review`, and `/dev meta`. It runs at most every 24h and stays silent when the local version is current or the network fails; a missing local `VERSION` counts as `0.0.0`. Show any line it prints (one quiet line) and continue the command — never block board work on it. With auto-update on, the check may apply a pull and print one success/failure line.

## Not planned (inline)

`not-planned` = decided against, kept with its reason so the idea isn't re-litigated. `delete` = erase (filed in error, duplicate, noise).

`TASKS update <id> --status not-planned --reason "<why>"` — the script requires the reason and appends it to the body as `Not planned (<date>):`. Ask the user for it in their own words; if the answer is thin, ask once what changed. Reversible: `--status backlog` revives, the reason stays as history.

A human decision — agents propose it, auto never uses it. When the user wants a task gone, ask which they mean (delete or not-planned) rather than choosing for them.

## Later (inline)

`later` = intended, not this iteration. Not a new verb: `/dev change <id> later` → `TASKS update <id> --status later` (or `add --status later`). No `--reason`. Claim, ship, land, and auto refuse it. Iteration close treats it like not-planned (logged `[later]`, not unfinished). `iteration-new` re-adds archived later tasks with fresh ids, still later, plus a `carried from <n>/T<id>` note — no walk. Revive with `--status backlog` or `/dev pick <id>`.

## Umbrella close (inline)

**An umbrella is never auto-closed.** Its children all being `done` says the work happened, not that the goal was met — separating those two judgments is the whole reason the umbrella exists. So no flow, and no agent, closes one off a status rollup: `TASKS update <id> --status done` on a `kind: umbrella` task is **refused**, and closing it has its own verb instead — `TASKS verify <id> "<how the children met the goal>"`, which records `Verified (<date>): …` in the body and closes the task. That record is carried into `log.md` at iteration close (an umbrella never ships, so it is its only outcome line).

The pass itself is `/dev implement <umbrella-id>` (flows/implement.md): an umbrella usually carries no code, so implement claims no branch, opens no PR, and does **not** go through `/dev review` — it reads the leaves and their `Shipped:` records against the umbrella's stated goal and ends in the same session, either filing the gaps as new children or closing with the record. Anyone may run it — typically whoever filed the umbrella and knows its intent; unlike `land`, it is not integrator-only. Real code found missing is a new leaf task, not work on the umbrella itself.

`/dev meta` never proposes closing an umbrella. When one looks complete it says the goal check is **due** and worth prioritizing, and points at `/dev implement <id>`.

## Recurring (inline)

`kind: recurring` + `cadence: <N><unit>` (unit `d`/`w`/`m`, e.g. `2w`, `1m`) = perpetual work on a clock — an audit, a dependency sweep — not a task that finishes. It is never terminal: `land` stamps `last_run` and re-arms it to `backlog` instead of marking it done, `--status done` is refused, and `TASKS recur ran <id> [--date]` records a run that never had a PR (refused while a branch or PR is live — `land` owns that run). The due date is **derived** (`last_run + cadence`), never stored, so a cadence edit re-dates it immediately; no `last_run` = due now. `TASKS recur list [--due]` is the due view; `board` marks due tasks and indexes a `Recurring` row.

Iteration close treats one **at rest** (`backlog`/`planned`) like `later`: non-blocking, archived, carried onto the next board as `backlog`. A run in flight (`doing`/`review`) blocks close like any other task; `proposed` blocks too and stays `proposed` when reseeded; `not-planned` retires it for good — that is the way to stop one.

**Agents never invent a recurring task.** Whether work recurs, and how often, is a human call: a flow may offer to schedule one and wait for the answer, auto never files one.

## Area stewardship (inline)

Areas are **coordination** locks, not labels. A task's `area` may list several, comma-separated. Two tasks **collide** when any name on one **segment-prefix-overlaps** any name on the other: split on `/`; `flows` overlaps `flows/implement` and `flows/other`; `flows/implement` does not overlap `flows/review`; `flow` does not overlap `flows` (string prefix is the trap). The script owns this (`areas_overlap` / `in_flight_area_collisions`); `TASKS collisions <id[,id…]>` and watch-mode type-id query it. A `doing` blocker — any assignee, this user included — **aborts** implement (exit 2; print the output, do not claim). Blockers whose PRs are **all open** (`draft` or `review`, any assignee) exit 3 instead: there is a pushed tip to build on, so interactive implement offers **proceed** (claim from integration — the areas overlap but the files usually do not), **stack** (`claim --stack-on <blocker-id>`, when the task truly needs the unmerged code; ship derives the PR base, land retargets rather than rebases) or **wait** (flows/implement.md). Auto skips both exits and never stacks. Untagged tasks skip that check (empty overlaps nothing except `all`), so `claim` refuses an empty area. Implement recommends a reuse or new name and waits; auto files the same as `needs: decision` (does not `area set` or tag until a human decides). Add may still leave area empty when a cluster cannot be named yet. No placeholder. A multi-id call excludes the other ids in the set from that fail check (batch members are sequential) and prints `set:` overlap lines as information only. Resume of one batch member uses that same set (`flows/implement.md`), not the single id. Reserved **`all`** marks a task that may touch everything (wide refactors, some umbrellas) and collides with every task: only on an otherwise-quiet board (nothing in `doing`, `draft`, or `review`) with the user's explicit confirmation that other contributors are paused; auto never picks it; never listed in areas.md.

A name with `/` is a path; parents are implied by segments (no parent field). A parent is a subtree-wide lock (`flows` = any/all `flows/*`) and is only assignable if listed in areas.md — do not invent it because a directory exists. Tag the parent **or** the specific children, not both. Prefer the children so locks stay narrow; do not tag the parent because the work *might* go wide — widen at implement if a fork actually crosses them (pause, update `--area`, re-run collisions before touching those files; exit 2 → revert `--area`, keep the `Decision:` for resume; exit 3 is the user's proceed-or-not call, with no stack option mid-branch; auto files `needs: decision` instead — flows/implement.md). Residuals that are not a named child go to `…/other` (`flows/other`), never the parent. A listed path-parent may itself be slash-free (`flows`) and still own `flows/*`. Conceptual names (`docs`, `ci`) stay slash-free and do not grow children — `docs`, not `docs/readme`.

No fixed upper bound. Limiter is multi-area occupancy: as many stable areas as enable parallelization without typical tasks needing many at once (over-granularity → confusing multi-area tags). Init proposes under that heuristic (flows/init.md).

Areas live in `.tasks/areas.md` via `TASKS area list|set|rm`. Path-split work: repo-relative path or the shortest uniquely distinguishing portion (`cli`, `billing/api`) — no filename extensions (`flows/iteration`, not `flows/iteration.md`). Cross-cutting non-directory work: short slash-free phrase (spaces fine). Form: no trailing `/`, no leading `./`, no `:` or `,`. The one-line `--desc` carries the rest.

`/dev area` with no args → `area list` only. Validity (stale names, path-renames, parent-used-as-residual, leftover extensions) lives under `/dev meta area` (flows/meta.md). `area list` open counts and `area rm` (without `--force`) match **exact names only** — a parent is not responsible for its children's tasks; later still occupies; not-planned does not. `TASKS board --by-area` indexes along the area axis: multi-area tasks appear on each listed area's id line, umbrella children nest as on the status board, and done/later/not-planned fold to counts on last index lines.

## Status (`/dev status`)

`TASKS list --assignee <me>`, then the PR refresh below. Report, in order: your in-flight tasks and their PR state (call out **changes requested** — that's your move to make, and your own **drafts**, which nobody else will move: each is yours to finish, review, and `ready`), then anything waiting on you (`TASKS list --needs decision`, `--status proposed`).

**If your list is empty** (`(no matching tasks)`), don't stop at "nothing assigned" — that's a dead end when the board has work. Add: the unassigned backlog count, one or two candidates worth picking (`TASKS list --status backlog`, prefer unblocked ones), and `/dev pick <id>`. If the board is genuinely empty too, say so and point at `/dev add <task-or-goal>`.

## PR state refresh (during board/status/review)

For tasks in `draft` or `review` with a `pr`, when gh is available: `gh pr view <url> --json state,mergedAt,reviewDecision`.

- `draft` → not on the integrator's queue. If it is **yours**, it is your move, and it belongs in your own review inbox: review it (`/dev review <id>`) or keep building (flows/implement.md), then `TASKS ready <id>` when you want eyes on it. An `auto/…` draft is listed the same way for whoever is here — auto cannot promote its own work and never returns. Another human's draft is never listed — not as a review item, not as information — and is never yours to `ready`.
- Merged → `TASKS land <id>` (marks done, cleans local worktree/branch; safe if already done). If land/cleanup aborts, surface the script error — do not mark done by hand.
- `CHANGES_REQUESTED` → the assignee's move; surface it (resume path in flows/implement.md).
- `APPROVED` and unmerged → if `whoami` is the integrator, ready to land via review; otherwise waiting on the integrator.
- Closed unmerged → flag it; only prompt for a decision if the current user is the assignee or integrator.

## Branch & role conventions

- Branch-per-task: `dev/<id>-<slug>` (scoped boards: `dev/<scope-with-/->-<id>-<slug>`), owned by the task's assignee, short-lived, merged promptly via PR with a merge commit. Land never rewrites a task branch: divergence is absorbed by the merge, and a conflict or stale branch is merged forward (never rebased) so PRs stacked on it stay valid.
- Review: anyone except the task's assignee; the integrator may review anything, including their own work. A `draft` is the exception — it is the author's own review loop until they `ready` it, except an `auto/…` draft, which any human may review and ready. Land: only the integrator (`TASKS land` refuses a live merge otherwise; already-merged cleanup stays allowed).
- The `integrator` (default: board creator; `/dev config integrator <name>`) owns the integration branch: default reviewer, conflict arbitration, iteration close, and land.
- Code branches contain code only; the board never rides them — `.tasks/` may appear in a feature checkout (inherited from integration), which is fine as long as the PR does not modify it.
