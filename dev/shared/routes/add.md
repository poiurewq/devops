# /<skill> add <task-or-goal> — sit with the ask, then file

`/<skill>` is the skill in use. Covers `/<skill> add <task-or-goal>`, freeform new work, and the `/dev plan` alias. One entry point, whichever skill it came through: sit with the ask, decide what kind of work it is, then file. The skill the user typed never decides the task's type — the work does.

## Premise (before filing)

Sit with the ask before choosing a path (SKILL.md *User specs are one guess*). What is the underlying problem? Does the proposed shape solve it? Any deeper consequences? If you need context to judge that, gather it where the work lives: for a change to files, the codebase first, online when the ask would add or change the stack or you cannot see enough locally; for the user's own process, ask them — guessing at someone's process is worse than one question. If you see a better approach, say so — the outcome beats the wording. If the problem is unclear, ask. Real concerns only; do not invent nits. Push-back is conversation; if you raised one, wait for a direction before going on. The task body is only what the user accepted.

**Does a flow already cover it?** Check `TASKS flow list`. For work that changes the world, the task may just be "run `<flow-name>`" — say so, and offer `/ops run <flow-name>` instead of filing anything new. For a change to files, a flow that governs how that work is done is attached to the task once filed (`TASKS update <id> --flow <name>`).

## Which type

Decide by what the work **does**, not by who asks or which skill they typed:

- It changes files in this repo → a **dev** task: built on a branch, landed through a PR.
- It changes the world — send, file, publish, order, schedule, review with human eyes, decide, update a system that lives elsewhere → an **ops** task: run, and closed with its run record.
- Both → two tasks, one of each. "Update the pricing page copy" is a dev task when the page lives in this repo; "email the new prices to every customer" is an ops task, even though both came from one decision.
- Unclear → one question.

Say the type once, in passing ("filed as an ops task"); never ask the user to pick a skill.

## How many tasks

Do not ask the user which path. Decide:

| Path | When |
|---|---|
| **One task** | One right-sized unit: for a dev task ≈ one focused PR, for an ops task one sitting with a clear aim, even a long one. Continue with **Filing** below. |
| **Several, filed directly** | A few distinct pieces, each done and checked separately, that you can already see — such as ops pieces that run on different days. Draft each as below, siblings with `--deps` where one has to happen after another. |
| **Plan** | Several deliverables already visible with real ordering across them, or an iteration-level / multi-PR goal the user wants broken down now. Read `shared/routes/plan.md`. |
| **Shape** | Many threads must be cut *together* before tasks are knowable — a new product, a first iteration, a large new subsystem. Read `shared/routes/shape.md`. |

**Grey area → prefer one task** (under-specify): implement decomposes an oversized dev task and a run decomposes what it finds, and detail is cheaper to add then than to invent now. Plan is for breakdown the user needs *now*, not every large-sounding phrase; shape is rarer than plan. When the user states a goal that several tasks add up to, file the children first, then an umbrella with `--kind umbrella --deps <child-ids>` and the goal in its body — closing it later is its own judgment (SKILL.md *Umbrella close*). Deps: wire the ordering you actually see — most procedures have a real sequence — and never invent one. Mention the path once ("filed as one task" / "filed three, the third waits on the second" / "breaking into tasks" / "shaping this onto the board").

## Filing

1. Draft a title and a 1–3 sentence description from what the user said, then its `Intent:` line (SKILL.md *Intent*). Do not add non-goals, constraints, approvals or design choices they did not state (SKILL.md ground rule *Do not manufacture specifications*). A dev task gets an area: reuse one from `TASKS area list` before inventing one, and a new board gets none until ~3 tasks cluster — empty is allowed, implement asks for one before claiming. An ops task gets none (the script refuses one).
2. **Check the board first**: `TASKS related "<title + description>"`.
   - Substantially the same task exists → say so and propose amending it (`TASKS update <id> …`) instead of adding a duplicate. The user decides; add anyway if they want them separate.
   - A near-identical task already `done` is usually not a duplicate — recurring work legitimately comes round again. Check whether it should be `--kind recurring` instead (SKILL.md *Recurring*): offer, and let the user choose the cadence. Never set one on your own.
   - Otherwise judge the neighbours for **dependencies in both directions** — must something else happen first (`--deps`), or does an existing task now wait on this one (update *its* deps)? Propose the links.
   - A neighbour marked `☂` is an **umbrella** that may already cover this cluster → propose the new task as its child (`--umbrella <id>` on the add). That is membership, not ordering.
   - **Once deps are picked**, run `TASKS related "<title + description>" --deps <ids>` again: each `umbrella of T…:` line it adds names an umbrella those deps sit under. Ask whether the new task belongs under it too; on yes, file with `--umbrella <id>`. Skip an umbrella already settled by the bullet above.
3. File it, then show the task as recorded (the script prints it):
   - dev: `TASKS add --title "…" [--area <m>] [--deps 1,2] [--umbrella <id>] [--desc "…"]`
   - ops: `TASKS add --title "…" --type ops [--deps 1,2] [--umbrella <id>] [--desc "…"]` — `--type ops` is not optional; without it the task is filed as code work.

   Perpetual work is `--kind recurring` with `--cadence <N><unit>` or `--schedule "<cron> <timezone>"` (SKILL.md *Recurring*), and gets the offer to start it on its own (`shared/routes/schedule.md` *The offer*).
4. **Next step, by type**: a dev task → `/dev <id>` to see it through; an ops task → `/ops run <id>` if it is ready to do now, nothing if it is future work.

**Reached from a verb given a description** (`/dev implement <goal>`, `/ops run <description>`, a verification pass's gaps): file exactly as above, then carry straight on into that verb on the new task(s) — the user already said to do it, so don't ask again.
