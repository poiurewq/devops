---
name: dev
description: Multi-contributor task board and dev workflow for a repo, or per-subdir boards in a monorepo. Use for /dev and subcommands (init, tour, add, plan, board, kanban, status, pick, implement, review, decide, audit, next, wake, schedule, absorb, flow list/show/create/edit/review/retire, agent, env, routine, change, delete, show, config, area, meta, iteration, distill, update), and whenever the user asks to add/see/assign/implement/review tasks on the repo's task board, or asks "what should I work on".
---

# dev — coordinated development for humans and agents

One task board per product (a repo, or a subdir of a monorepo), shared by every contributor — human or agent — across worktrees and machines. You are the interface: parse intent, run the script for all board state, apply judgment yourself. When the routing table names a `routes/*.md`, read that file and follow it — don't improvise the route.

<!-- core: skill-paths -->

## Script synopsis

`--scope` goes BEFORE the subcommand. This index is enough for names.

```
<!-- core: synopsis-setup -->
TASKS integrator list | add <name> | rm <name>
TASKS area list | set <name> [--desc "<one-line scope>"] | rm <name> [--force]
<!-- core: synopsis-registries -->
TASKS add --title "<title>" [--area <m>] [--deps <id,id>]
          [--desc "<1–3 sentences>"] [--assignee <who>]
          [--kind umbrella|recurring] [--cadence <N><unit>]
          [--schedule "<cron> <timezone>"] [--next-due <date>]
          [--type ops] [--status proposed|backlog|planned|shelved --reason "<why>"]
          [--routine <name>]
          [--distill]                   # with --type ops: a distill sitting
          [--umbrella <id[,id]>]        # file under it: adds to its deps
TASKS update <id> [--title] [--area] [--status] [--kind umbrella|recurring|""]
          [--type ops|dev] [--assignee <who>|""] [--branch <b>|""] [--pr]
          [--needs decision|""] [--deps] [--append "<paragraph>"]
          [--desc "<new body>"] [--cadence <N><unit>|""]
          [--schedule "<cron> <timezone>"|""] [--last-run <date|timestamp>|""]
          [--next-due <date>|""] [--routine <name>|""]
          [--flow <name[,name]>|""]
          [--status not-planned|shelved --reason "<why>"]
<!-- core: synopsis-records -->
TASKS collisions <id[,id…]>             # 2 doing-blocked, 3 PR open
TASKS list [--assignee <who>] [--status <s>] [--needs decision]
           [--type ops|dev] [--flow <name>] [--json]
TASKS recur list [--due] | recur ran <id> [--date <date|timestamp>]
TASKS board [--expand] [--by-area] [--watch]
<!-- core: synopsis-iteration -->
TASKS claim <id> [--assignee <who>] [--branch <b>] [--stack-on <id>]
           [--unattended <model-id>]    # refuse if diverged or untagged
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
TASKS pr <id> view [--json] | diff | close [--head <branch>]
      | comment --body B | review --approve|--request-changes|--comment [--body B]
```

<!-- core: synopsis-caveats -->

`--area` takes a comma-separated list (`--area "cli, docs"`); `all` is reserved (see Area stewardship).

<!-- core: ground-rules -->
- **Scripted git lifecycle.** Never improvise multi-step git/gh for task work: use `claim`, `diff` (self-review from the task worktree), `ship`, `ready`/`unready`, `land`/`cleanup`, `preflight` (park/discard), `iteration-land`, and for stacks `restack`/`batch-gate`. Routes decide and call; they don't spell out raw sequences to re-invent. Reading a PR and the human review actions on it go through `TASKS pr <id> view|diff|comment|review|close`, never `gh pr` directly — `TASKS pr` runs `gh pr` and, where GraphQL is blocked (some hosted agent sandboxes), switches to GitHub's REST API, as every script PR call does. `DEVOPS_PR_TRANSPORT=rest` forces REST from the start.
- **PR is the only merge flow.** GitHub and an authenticated `gh` are assumed; init walks the user through setup, and the script checks gh sign-in before any GitHub step (implement stops at preflight's error). Task branches start from `origin/<integration>`; if local integration is ahead on this board's scope, implement stops to park-as-PR or discard first (routes/implement.md). An unattended run never parks or discards — it skips and reports.
- **To build a task, suggest `/dev <id[, id…]>`**, never `/dev implement <id>` — in a route, a report, or script output; the lead routes umbrellas, ops tasks and hosts without subagents itself.

<!-- core: state-layout -->

## Routing

| Invocation | Action |
|---|---|
| `/dev` (bare) | Read `routes/first-contact.md`. |
| `/dev help` | Read `routes/first-contact.md`. No board/identity → same setup path as bare. |
| `/dev tour` | Read `shared/routes/tour.md` (the key concepts, one card at a time, on the user's own board). Only when asked; never run it unprompted. No board or identity yet → still give it (its no-board path); do not run init first. |
| `/dev init` | Read `shared/routes/init.md` (prerequisites, identity, board creation or joining, areas, the AGENTS.md pointers). |
| `/dev add <task-or-goal>` | Read `shared/routes/add.md` (premise, the task's type, then one task, several, plan, or shape). |
| `/dev plan <goal>` | Alias of `/dev add` (same triage). |
| Freeform new work | Same as `/dev add`. |
| `/dev implement <id[, id…]|goal>` | Read `routes/implement.md` (multi → also `routes/implement-batch.md`; claim, forks, PR; follows the task's flow, and redirects a task that changes no code). |
| `/dev <id[, id…]>` | Read `routes/lead.md` (the task lead: routes by state, runs implement and review through implementer and reviewer subagents, surfaces only real decisions; no subagents → `/dev implement`). |
| `/dev review [id[, id…]]` | Read `routes/review.md` (inbox; multi-id → `routes/review-batch.md`; a `draft` id is its author's own loop — only your own drafts reach the inbox, unattended work as you included). |
| `/dev decide [id]` | Read `shared/routes/decide.md` (open questions and proposed tasks, of either type — the judgments waiting on a person). `/dev review` lists them too. |
| `/dev audit [area]` | Read `routes/audit.md` (scan the codebase for work worth filing; offers to schedule a recurring audit when none covers that scope). Not `/dev review`, which is the PR inbox. |
| `/dev next` | *Next* below — pick the top task for me, then build it on a yes. |
| `/dev <id[, id…]> unattended` / `/dev next unattended` | Read `shared/routes/unattended.md`, then `routes/unattended-run.md` (nobody there: not the lead — implement with forks filed as `needs: decision`, ship to `draft`, stop; no reviewer pass). Only on the trailing word — never assumed. |
| `/dev wake <routine> <dir>` | Read `shared/routes/wake.md` (a routine's run: the skill check, the gate, then its due tasks — attended or unattended by the routine's mode — and, on a one-time trigger, re-pointing it). The whole prompt a trigger at its source carries. |
| `/dev schedule <id> [<routine>]` | Read `shared/routes/schedule.md` (set up a routine so a recurring task starts on its own: pick or create the routine and its runner environment, the trigger proposed from this harness and created at its source on `go`, the task pointed at it, a watched first run; also moves a task between routines). Also where the offer after add, audit and status leads. |
| `/dev absorb <source>` | Read `shared/routes/absorb.md` (import a list of things to do, each filed as the type its work is; a written procedure goes to `/dev flow adopt` instead). |
| `/dev iteration ...` | Read `shared/routes/iteration.md` (show / close / new). |
| `/dev distill` | Read `shared/routes/distill.md` (a sitting: turn this iteration's task records into `AGENTS.md` context and heuristics, each item the user's call; required before an iteration closes). |
| `/dev board` / `kanban` | `TASKS board` (status index + in-play list); `TASKS board --by-area` for the area cut; then the PR state refresh (`shared/routes/status.md`). |
<!-- core: routing-flows -->
| `/dev meta [id-or-area]` | Read `routes/meta.md` (pressure the board; optional focus). `/dev meta area` (or `areas`) is reserved: area-validity pass only. Freeform "does this board still make sense?" too. |
| `/dev status` | Read `shared/routes/status.md` (your plate). |
| `/dev pick <id-or-desc>` | `TASKS update <id> --status planned --assignee <me>`; if already assigned to someone else, confirm the takeover with the user first. |
| `/dev change <id> <what>` / `modify` | Map onto `TASKS update <id> --...`; show the result. A new intent is appended (*Intent*). |
| `/dev delete <id>` | Confirm, then `TASKS delete <id>`. |
| `/dev drop <id>` / "we're not doing this" | *Not planned and shelved* below — offer delete as the alternative and let the user pick. "Not needed for now" is shelved instead. |
| `/dev show <id>` | `TASKS show <id>`. |
| `/dev config [key] [value]` | `TASKS config ...` (settable: parent_branch, iteration, iteration_name, iteration_started). Who may land is `TASKS integrator list|add <name>|rm <name>` — see Branch & role conventions. |
| `/dev area ...` | Area stewardship, below. |
| `/dev integrator ...` | `TASKS integrator list|add <name>|rm <name>` — who may land; see Branch & role conventions. |
| `/dev skill` | Read `shared/routes/skill.md` (`SKILL_CMD status`). |
| `/dev skill update` | Read `shared/routes/skill.md` (`SKILL_CMD update`). |
| `/dev skill update auto on/off` | Read `shared/routes/skill.md` (`SKILL_CMD auto on/off`). |
| `/dev skill feedback <text>` | Read `shared/routes/skill.md`. |

Given a description instead of an id, run `TASKS list`, match, confirm if not obvious. **`/dev implement` only:** if nothing matches, run the `/dev add` path first (`shared/routes/add.md`), then continue implement on the new task(s) — details in `routes/implement.md`. Other id-or-desc commands (`pick`, `show`, …) still require a match.

<!-- core: identity -->

## Skill check

Run `SKILL_CMD check` once at the start of bare `/dev`, `/dev help`, `/dev init`, `/dev add` (including freeform add and `/dev plan`), `/dev board` / `kanban`, `/dev <id>`, `/dev implement`, `/dev next`, `/dev review`, `/dev meta`, `/dev wake`, and `/dev schedule`.

<!-- core: skill-check -->

<!-- core: not-planned -->

<!-- core: intent -->

<!-- core: umbrella -->

<!-- core: recurring -->

A dev run's branch gets a `-<YYYY-MM-DD>` suffix (`-2`, `-3`… for a second that day), so a run never reuses an earlier one's leftover.

<!-- core: routines -->

## Area stewardship (inline)

Areas are **coordination** locks, not labels. A task's `area` may list several, comma-separated. Two tasks **collide** when any name on one **segment-prefix-overlaps** any name on the other: split on `/`; `routes` overlaps `routes/implement` and `routes/other`; `routes/implement` does not overlap `routes/review`; `route` does not overlap `routes` (string prefix is the trap). The script owns this; `TASKS collisions <id[,id…]>` queries occupancy. Watch-mode `c` then id is a check: that occupancy plus whether the task's deps are not yet done (blocked sides only; both clear → one clear). `c` then `id,id…` checks a group: each member against the board outside the group, then two verdicts within it — **parallel** (no area overlap and no deps between members) and **batch** (in-group deps only order the run; a cycle blocks). A `done`, `shelved` or `not-planned` member is listed by status and left out of both. No batch order is suggested beyond the deps it names. A `doing` blocker — any assignee, this user included — **aborts** implement (exit 2; print the output, do not claim). Blockers whose PRs are **all open** (`draft` or `review`, any assignee) exit 3 instead: there is a pushed tip to build on, so interactive implement offers **proceed** (claim from integration — the areas overlap but the files usually do not), **stack** (`claim --stack-on <blocker-id>`, when the task truly needs the unmerged code; ship derives the PR base, land retargets rather than rebases) or **wait** (routes/implement.md). An unattended run skips both exits and never stacks. Untagged tasks skip that check (empty overlaps nothing except `all`), so `claim` refuses an empty area on a dev task. Ops tasks (`type: ops`) never carry an area: they touch no code, so there is nothing to lock — the script refuses an area on one. Implement recommends a reuse or new name and waits; an unattended run files the same as `needs: decision` (does not `area set` or tag until a human decides). Add may still leave area empty when a cluster cannot be named yet. No placeholder. A multi-id call excludes the other ids in the set from that fail check (batch members are sequential) and prints `set:` overlap lines and the group's `parallel: ok | no — <reasons>` verdict as information only. Resume of one batch member uses that same set (`routes/implement.md`), not the single id. Reserved **`all`** marks a task that may touch everything (wide refactors, some umbrellas) and collides with every task: only on an otherwise-quiet board (nothing in `doing`, `draft`, or `review`) with the user's explicit confirmation that other contributors are paused; an unattended run never picks it; never listed in areas.md.

A name with `/` is a path; parents are implied by segments (no parent field). A parent is a subtree-wide lock (`routes` = any/all `routes/*`) and is only assignable if listed in areas.md — do not invent it because a directory exists. Tag the parent **or** the specific children, not both. Prefer the children so locks stay narrow; do not tag the parent because the work *might* go wide — widen at implement if a fork actually crosses them (pause, update `--area`, re-run collisions before touching those files; exit 2 → revert `--area`, keep the `Decision:` for resume; exit 3 is the user's proceed-or-not call, with no stack option mid-branch; an unattended run files `needs: decision` instead — routes/implement.md). Residuals that are not a named child go to `…/other` (`routes/other`), never the parent. A listed path-parent may itself be slash-free (`routes`) and still own `routes/*`. Conceptual names (`docs`, `ci`) stay slash-free and do not grow children — `docs`, not `docs/readme`.

No fixed upper bound. Limiter is multi-area occupancy: as many stable areas as enable parallelization without typical tasks needing many at once (over-granularity → confusing multi-area tags). Init proposes under that heuristic (`shared/routes/init.md`).

Areas live in `.tasks/areas.md` via `TASKS area list|set|rm`. Path-split work: repo-relative path or the shortest uniquely distinguishing portion (`cli`, `billing/api`) — no filename extensions (`routes/iteration`, not `routes/iteration.md`). Cross-cutting non-directory work: short slash-free phrase (spaces fine). Form: no trailing `/`, no leading `./`, no `:` or `,`. The one-line `--desc` carries the rest.

`/dev area` with no args → `area list` only. Validity (stale names, path-renames, parent-used-as-residual, leftover extensions) lives under `/dev meta area` (routes/meta.md). `area list` open counts and `area rm` (without `--force`) match **exact names only** — a parent is not responsible for its children's tasks; shelved and not-planned do not occupy. `TASKS board --by-area` indexes along the area axis: multi-area tasks appear on each listed area's id line, umbrella children nest as on the status board, and done/shelved/not-planned fold to counts on last index lines.

## Running a task

How this skill runs one of its tasks, for the shared routes (`shared/routes/…`) that cite this section:

- **Attended run**: `/dev <id>` (`routes/lead.md`; an umbrella goes to its verification pass, `shared/routes/verify.md`). A recurring audit (a recurring task naming an audit pass, `Recurring audit: <scope>`) runs `/dev audit` with its scope instead (`routes/audit.md`).
- **Unattended run**: `/dev <id> unattended` (`shared/routes/unattended.md`, its dev part `routes/unattended-run.md`) — forks filed as `needs: decision`, stops at draft. A recurring audit goes through that part's *Audits*.
- **Scheduled run** (an attended routine's wake): `/dev <id>` as *A scheduled sitting* (`routes/lead.md`) — or the audit route above.
- **Answering a parked question**: `/dev decide <id>` (`shared/routes/decide.md`); a task parked mid-work is then picked back up with `/dev <id>`.
- **The run's outcome record** is its `Shipped:` record; a recurring run re-arms at land.

<!-- core: next -->

## Branch & role conventions

- Branch-per-task: `dev/<id>-<slug>` (scoped boards: `dev/<scope-with-/->-<id>-<slug>`), owned by the task's assignee, short-lived, merged promptly via PR with a merge commit. Land never rewrites a task branch: divergence is absorbed by the merge, and a conflict or stale branch is merged forward (never rebased) so PRs stacked on it stay valid.
- Review: anyone except the task's assignee; the integrator may review anything, including their own work. A `draft` is the exception — it is the author's own review loop until they `ready` it. An unattended run works as the human who owns the machine's GitHub login (shared/routes/unattended.md), so its drafts are that person's. Land: only the integrator (`TASKS land` refuses a live merge otherwise; already-merged cleanup stays allowed).
- The **integrator** role owns the integration branch: default reviewer, conflict arbitration, iteration close, and land. Ask the script who holds it — `TASKS whoami --role` prints `integrator` or `contributor` for the current identity — and never compare identities yourself. The board creator gets the role at init; `TASKS integrator list | add <name> | rm <name>` reads and changes it (a board may hold the role in more than one pair of hands; the last one cannot be removed, since an empty roster blocks land for everyone).
- Code branches contain code only; the board never rides them — `.tasks/` may appear in a feature checkout (inherited from integration), which is fine as long as the PR does not modify it.
