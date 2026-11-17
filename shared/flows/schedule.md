# /<skill> schedule <id> [<routine>] — set up a routine for a recurring task

`/<skill>` is the skill in use. Makes a recurring task start on its own: a trigger at its source that runs the wake for the task's type (`/dev wake <routine> <dir>` for a dev task, `/ops wake <routine> <dir>` for an ops task), mirrored on the board as a routine the task points at (SKILL.md *Routines*). One conversation, in whatever harness the user runs. Covers `/<skill> schedule <id> [<routine>]` and the offers that lead here. Run from the product directory, or pass `--scope`. An unattended run never offers it and never runs it: it creates something outside the board.

## The offer

Made once, in one line, where a recurring task whose clock runs (not `proposed`, `shelved` or `not-planned`, SKILL.md *Recurring*) has no `routine` and no `Decision: no routine` line in its body: after add files it, after an audit files one, and in status. Yes → step 1. No → ask why, in the user's words, and record it: `TASKS update <id> --append "Decision: no routine — <why>"`. No offer is made for that task again; `/<skill> schedule <id>` still sets it up later.

## 1. Resolve

`TASKS show <id>`. Not `kind: recurring` → stop: a routine only starts recurring work, and whether work recurs is the user's call (SKILL.md *Recurring*).

**Already on a routine** (`routine:` set) → `TASKS routine show <name>` and offer: keep it, move to an existing routine, or a new one. Keep → stop, after offering the fix for any harness refusal its runs have noted on the task (step 7).

A `<routine>` named in the invocation is where the task goes — a move, or a first routine for a task without one: skip to step 6 with it.

## 2. Pick or create the routine

`TASKS routine list`, then recommend one with a reason and wait:

- **Mode.** `attended` holds this task alone; a run reaches the user at its first step that needs them and waits (SKILL.md *Running a task*) — for work that needs the user most runs. `unattended` may hold several; each run puts everything that needs a person on the board and stops there (`shared/flows/unattended.md`) — for work that rarely needs anyone.
- **An existing unattended routine** of this task's type fits when its environment suits this task and its schedule fires at least as often as the task falls due. Joining it means the tasks share one session's context each wake: say so, and recommend a routine of its own for a task that should not see the others'.
- Otherwise a **new routine**: steps 3–5.

Joining an existing one → step 6.

## 3. Runner environment

`TASKS env list`. Recommend one that meets SKILL.md *Routines* (Runner environment) — this harness on this machine, or a cloud one — and wait. None fits → register it, named by the user: `TASKS env add <name> --accessors "<who can reach it>" [--machine <m>] --expects "<what a run there can count on>"`. Its `--expects` names where this product directory sits there, since the trigger's prompt carries that path (step 4); an existing environment that does not name it gets it added with `TASKS env update <env> --expects "…"`. What setup cannot confirm (a call held at a permission prompt) is the watched run's to find (step 7).

## 4. Propose the trigger

You know the harness you are running in: propose a trigger from it — its scheduled-agent feature, a cloud routine, cron on the machine — with every setting spelled out against the contract:

- **Prompt**: exactly `/dev wake <name> <dir>` for a dev task or `/ops wake <name> <dir>` for an ops task, nothing else (`shared/flows/wake.md`), `<dir>` being the product directory's absolute path in the chosen environment as its `--expects` records it (step 3).
- **Schedule**: the task's `schedule` when it has one. On a cadence, a cron firing at least once per cadence, at a time the user picks. A harness that offers only one-time fires gets the task's next due as a timestamp, and each wake re-points it.
- **Permissions**: every call a run makes allowed or refused up front, never left at a prompt; for an attended routine, a way to notify the user.

Agree the routine's name with the user. A part the harness cannot meet → say which and what it costs; none of it → say so and stop, since another harness has to hold this trigger. Creating a trigger is an outward act: show the concrete settings and wait for `go`. An adjustment is shown again for a fresh `go`.

## 5. Create and record

On `go`, create it at the source when the harness lets this session; otherwise give the user the exact settings and wait until they say it exists. Read back its identifier, then mirror it:

```
TASKS routine add <name> --accessors "<who can reach the source>" --mode attended|unattended \
      --environment <env> --schedule "<cron> <timezone>"|<timestamp> \
      --trigger "<what and where, with its identifier>" --manage "<how to change or remove it there>"
```

Never record a routine the source does not hold: the board mirrors it.

## 6. Point the task

**The task's clock first moves onto the routine's** when the routine's schedule is a cron. A cadence counts from the last run, stamped when the run is recorded, and has no early window, so a run recorded after its fire pushes the due past the next fire and the wake skips it, every period. A schedule never drifts, since a run records the scheduled time it covered. So a cadence task gets a schedule made of the routine's fire times: `TASKS update <id> --cadence "" --schedule "<cron> <timezone>"`. A routine that fires as often as the task falls due → its schedule itself. One that fires more often → pick the fires the task keeps, in the routine's zone (a monthly task on a daily noon routine: noon on one day a month). A scheduled task whose times are not all among the routine's fires (a move included) is realigned the same way, with `--schedule` alone: a time off the fires runs at the next fire after it, late, so aligning puts its runs on time. When no subset of the fires matches the task's frequency (cron ORs its two day fields, so neither one Monday a month nor every other Monday can be written), take the nearest schedule even off the fires: each such time runs at the next fire, late but never drifting. Get the user's OK on a picked subset or a schedule off the fires, and on any change to a schedule the task already had. A routine on a one-time fire leaves the clock alone, since each wake re-points it to the task's next due.

Then `TASKS update <id> --routine <name>`. Show what it prints; a refusal is surfaced verbatim. A warning about `[user]` steps on an unattended routine means nobody will be there to do them: say so and offer an attended routine instead.

**A move** that leaves the old routine with no tasks (`TASKS routine list`) → offer to remove its trigger at the source (its body says how), then, on `go`, `TASKS routine rm <old>`: source first, board second.

## 7. The watched first run

A new trigger and environment are untested until a run goes through, so the setup ends with one the user watches.

- **Can run early, and this session can fire the trigger now** ("run now" at its source) → `TASKS update <id> --next-due <today>` makes it due, then fire it.
- **Otherwise** — it must not run early (its timing matters, or each run sends something), or the trigger cannot be fired from here → tell the user when it first fires. A task already due then gets `TASKS update <id> --next-due <the date of that first fire>` on the user's OK: the not-started check counts from when the task fell due, not from when the routine was made, so without it the board reads `🚨routine <name> did not start` until that fire.

Either way the run should pass the wake without a permission prompt or a refused call. Each one is noted on the task at the step it hit and named in the wake's report (`shared/flows/wake.md` step 3). For each one, propose the fix — the call allowed or refused up front at the source, or the environment's `--expects` corrected (`TASKS env update <env> --expects "…"`) — and make it on the user's go-ahead, here if the run happens in this session, or when they come back with `/<skill> schedule <id>`, which reads the task's `Note:` lines.
