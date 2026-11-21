# /<skill> distill — turn the iteration's records into AGENTS.md

`/<skill>` is the skill in use. A distill sitting reads what this iteration's tasks recorded — decisions, notes, run and shipped records, reasons for dropping work — and proposes what of it belongs in the product's `AGENTS.md` files as context or heuristics (SKILL.md *Ground rules*, vendor-neutral context and heuristics). It runs when the user chooses, and always before an iteration closes: `iteration-close` refuses while any `done` or `not-planned` task is in no `Distilled` line (`shared/routes/iteration.md`). Every item is the user's call, so an unattended run never distills.

## 1. Open the sitting

A sitting is an ops task of its own, marked `distill: true`, run here — never through `/ops run`. An open one (`TASKS list --type ops --status doing --assignee <me> --json`, the one with `distill: true`) is resumed: its own `Distilled` lines say which tasks are finished, and the `AGENTS.md` task it already filed is the one whose deps list it. Otherwise file one and start it: `TASKS add --type ops --distill --title "Distill iteration <n>" --desc "<one line> Intent: the iteration's records are dealt with — an AGENTS.md task filed with what the user approved, or nothing found worth filing."`, then `TASKS update <id> --status doing --assignee <me>`.

## 2. Gather

- **The AGENTS.md files**: every one under the product directory (nested ones included, `.dev/` skipped) and in each directory above it up to the repo root, gitignored ones included (`git check-ignore` says which). A `CLAUDE.md` symlinked to one is the same file.
- **The records**: `TASKS list --json`, keeping the non-recurring `done` and `not-planned` tasks whose id is in no `Distilled (<date>): …` line on any task's body — the set the close gate checks — plus every recurring task with run records (recurring tasks are never marked distilled, so their records are read each sitting).

Read the tasks in id order, each body top to bottom. A later `Decision:` overrides an earlier one, and an override is signal: the user changed their mind, which is often the most general lesson there.

## 3. Candidates

Each candidate names its evidence (task ids and record lines), its target file and section, and its proposed wording, and carries one label:

- **heuristic** — how the user decides here (SKILL.md *Ground rules*, heuristics), stated generally enough to settle a future call; give it a bold name so it can be cited.
- **context** — what the project is, does or aims at, that later work needs and neither the code nor the board shows.
- **contradiction** — a record and an `AGENTS.md` line that disagree. Either may be newer: say which is which and let the user decide which stands.
- **elsewhere** — a fact that belongs in a flow or an environment entry, not `AGENTS.md` (each piece of knowledge has one home). Named only; the user acts on it with `/<skill> flow edit <name>` or `TASKS env update`.

Leave out what is already in an `AGENTS.md`, what the code or board makes plain, and what only that one task needed. Put each item in the nearest `AGENTS.md` that covers the work it is about, not the repo root by default. Then **reorganization**: moves, merges or rewordings of existing `AGENTS.md` content where it would read better — proposed last, against the files as the approved items leave them.

## 4. Present

One category at a time — contradictions, heuristics, context, then reorganization — in batches of about ten, strongest evidence first within a category. The user approves, rewords or declines each. After each reply, in this order:

1. **Write what was approved.** Items for a tracked `AGENTS.md` go into one dev task: the first approval files it — `TASKS add --title "AGENTS.md: what iteration <n> taught" --deps <sitting> --desc "<each item: file § section: wording> Intent: later agents here act on what this iteration's records taught."`, no area (implement asks), so it waits for the sitting to close; later approvals are appended to it (`TASKS update <id> --append "<file § section: wording>"`). A gitignored `AGENTS.md` is the user's own copy: edit it directly. Declined items are not recorded.
2. **Record what is finished**: `TASKS distilled <sitting> "<ids>"`, naming the tasks whose last remaining candidate was in this batch — dealt with, whatever the answer.

The user may stop after any batch.

## 5. Close

- **The final message** lists the elsewhere items and the tasks that yielded no candidate. Once the user has replied, `TASKS distilled <sitting> "<those ids>"`.
- `TASKS ran <sitting> --record "<what was read; approved n, declined m; filed T<id>>"`. On a sitting, `ran` also records the sitting and the task it filed (which depends on it) as distilled, so they are never named by hand. A sitting stopped early still closes this way; the tasks it did not finish stay for the next sitting.
- Report the filed task, built like any other (`/dev <id>`).
