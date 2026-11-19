---
name: ops
description: Playbook of flows plus the runs that follow them, on a shared task board inside the user's repo. Use for /ops and subcommands (init, tour, add, run, next, wake, schedule, rehearse, flow list/show/create/edit/review/retire, agent, env, status, board, show, change, drop, delete, meta), and whenever the user asks to run a procedure or checklist, follow or write a flow, record what a run did, dry-run (rehearse) a flow, or work a task that is not code.
---

# ops — procedures that run, recorded where they ran

One board per project, shared by every contributor — human or agent — across machines. A **flow** is a written procedure; a **run** is one execution of a flow against a task, and the task file is the record of it. You are the interface: parse intent, run the script for all board and flow state, apply judgment yourself. When the routing table names a `routes/*.md`, read that file and follow it — don't improvise the route.

<!-- core: skill-paths -->

## Script synopsis

`--scope` goes BEFORE the subcommand. The script serves both skills, so it also carries verbs this skill never uses (branches, PRs, review); the list below is the ops surface.

```
<!-- core: synopsis-setup -->
<!-- core: synopsis-registries -->
TASKS add --title "<title>" --type ops [--deps <id,id>]
          [--desc "<1–3 sentences>"] [--assignee <who>]
          [--kind umbrella|recurring] [--cadence <N><unit>]
          [--schedule "<cron> <timezone>"]
          [--next-due <date>] [--status proposed|backlog|planned|shelved --reason "<why>"]
          [--rehearsal]                 # a dry run of its flow (rehearse.md)
          [--routine <name>]            # the routine that starts it
          [--umbrella <id[,id]>]        # file under it: adds to its deps
TASKS update <id> [--title] [--status] [--assignee <who>|""] [--deps]
          [--needs decision|""] [--flow <name[,name]>|""] [--append "<paragraph>"]
                                        # --append repeats, one paragraph each, in order
          [--desc "<new body>"] [--kind umbrella|recurring|""]
          [--cadence <N><unit>|""] [--schedule "<cron> <timezone>"|""]
          [--next-due <date>|""] [--routine <name>|""]
          [--unattended <model-id>|""]  # an unattended run's marker (shared/routes/unattended.md)
          [--status not-planned|shelved --reason "<why>"]
TASKS pause <id> --at "<step>" --record "<what exists so far>"
            [--flow <name[,name]>] [--date YYYY-MM-DD]
                                        # stop a run partway; stays doing
TASKS wait <id> --on "<who>" --by YYYY-MM-DD --at "<step>"
           --record "<what was sent, where>" [--flow <name[,name]>]
           [--date YYYY-MM-DD]          # at an [external] step or a handed-
                                        # off sequence; stays doing
TASKS wait <id> --clear                 # the reply is in; stays doing
<!-- core: synopsis-records -->
               [--rehearsal]         # a dry run: Rehearsed (<date>): …
TASKS list [--type ops] [--assignee <who>] [--status <s>] [--needs decision]
           [--flow <name>] [--json]
TASKS recur list [--due]
TASKS board [--expand] [--watch]
<!-- core: synopsis-iteration -->
```

<!-- core: synopsis-caveats -->

<!-- core: ground-rules -->
- **Ops changes the world, not the codebase.** A run sends the mail, files the form, updates the spreadsheet, moves the thing. It never edits, commits, or branches project code — no branches, no PRs, no review queue. A task that turns out to need code changes goes on as a dev task (SKILL.md *Two task types*, crossing over).
- **Never run git yourself.** Anything a run leaves in the working tree is the user's to keep or discard, and board and flow state is already committed and pushed by the script.
- **Every run is recorded.** A run ends when the task's aim is met, not when the steps are exhausted — judged by the user, except for a clean run whose outcome the agent can show meets it (*Runs (inline)*). `TASKS ran <id> --record "…"` is what closes an ops task. The record says what the run was given and where it departed from the flow — it is the only durable trace of what happened, and it is what later makes a flow improvable.
- **A flow is a procedure, not a policy.** Write the steps someone could follow, each marked `[agent]`, `[user]`, `[confirm]`, or `[external]` (`shared/routes/flows.md` *Step marks*). Do not write constraints, approvals, or non-goals the user did not state.

<!-- core: state-layout -->

## Routing

| Invocation | Action |
|---|---|
| `/ops` (bare) | Read `routes/first-contact.md`. |
| `/ops help` | Read `routes/first-contact.md`. No board/identity → same setup path as bare. |
| `/ops tour` | Read `shared/routes/tour.md` (the key concepts, one card at a time, on the user's own board). Only when asked; never run it unprompted. No board or identity yet → still give it (its no-board path); do not run init first. |
| `/ops init` | Read `shared/routes/init.md` (prerequisites, identity, board creation or joining, areas when the repo has code, the AGENTS.md pointers). |
| `/ops add <task-or-goal>` | Read `shared/routes/add.md` (premise, the task's type, then one task, several, plan, or shape). |
| Freeform new work | Same as `/ops add`. |
| `/ops run <id[, id…]>` | Read `routes/run.md` (preflight, flow choice, inputs, run, record). Several ids run one after another. |
| `/ops run <flow-name> [inputs]` | Read `routes/run.md` — runs the one ops task clearly on that flow, asks when there is a real choice, else files one first. |
| `/ops run <description>` | Read `routes/run.md` — files via `shared/routes/add.md` first, then runs it. |
| `/ops next` | *Next* below — pick the top task for me, then run it on a yes. |
| `/ops run <id> unattended` / `/ops next unattended` | Read `shared/routes/unattended.md`, then `routes/unattended-run.md` (a run with nobody there: goes to its first stop, parks every decision on the board). Only on the trailing word — never assumed. |
| `/ops wake <routine> <dir>` | Read `shared/routes/wake.md` (a routine's run: the skill check, the gate, then its due tasks — attended or unattended by the routine's mode — and, on a one-time trigger, re-pointing it). The whole prompt a trigger at its source carries. |
| `/ops schedule <id> [<routine>]` | Read `shared/routes/schedule.md` (set up a routine so a recurring task starts on its own: pick or create the routine and its runner environment, the trigger proposed from this harness and created at its source on `go`, the task pointed at it, a watched first run; also moves a task between routines). Also where the offer after add and status leads. |
| `/ops rehearse [<flow-name>]` / "dry run <flow-name>" | Read `routes/rehearse.md` (no flow named → it asks which, offering likely candidates) — go through a new or changed flow once, with the user present, holding back its outward steps, then sharpen the flow from what it found. Its own task (`add --rehearsal`), closed with `ran --rehearsal`; while it is `doing`, the script refuses starting a real run of that flow, and the reverse. |
<!-- core: routing-flows -->
| `/ops note <id> <text>` | `TASKS note <id> "<text>"`, with `--at <step>` when a run is under way (you know the step; the user need not say it). Mid-run the id can be left off, and "note: …" in chat means the same. Runs (inline) says what earns a note. |
| `/ops board` | `TASKS board`, then report. One board: dev tasks show alongside, marked. |
| `/ops status` | Read `shared/routes/status.md` (your plate). |
| `/ops show <id>` | `TASKS show <id>`. |
| `/ops change <id> <what>` / `modify` | Map onto `TASKS update <id> --…`; show the result. A new intent is appended (*Intent*). |
| `/ops drop <id>` / "we're not doing this" | *Not planned and shelved* below — offer delete as the alternative and let the user pick. "Not needed for now" is shelved instead. |
| `/ops delete <id>` | Confirm, then `TASKS delete <id>`. |
| `/ops iteration …` | Read `shared/routes/iteration.md` (show, close, start the next). |
| `/ops config [key] [value]` | `TASKS config …` (settable: iteration, iteration_name, iteration_started, parent_branch). |
| `/ops absorb <source>` | Read `shared/routes/absorb.md` (import a list of things to do, each filed as the type its work is; a written procedure goes to `/ops flow adopt` instead). |
| `/ops decide [id]` | Read `shared/routes/decide.md` (open questions and proposed tasks, of either type — the judgments waiting on a person). |
| `/ops pick <id-or-desc>` | `TASKS update <id> --status planned --assignee <me>`; if it is already assigned to someone else, confirm the takeover with the user first. |
| `/ops meta` | Read `routes/meta.md` (pressure the playbook and the board). |
| `/ops skill …` | Read `shared/routes/skill.md` (status, update, auto on/off, feedback). |

Anything not in the table maps onto the closest verb: read the intent, do it, and name the verb once. Given a description instead of an id, run `TASKS list`, match, and confirm if it is not obvious.

<!-- core: identity -->

## Skill check

Run `SKILL_CMD check` once at the start of bare `/ops`, `/ops help`, `/ops init`, `/ops add`, `/ops run`, `/ops next`, `/ops board`, `/ops meta`, `/ops wake`, and `/ops schedule`.

<!-- core: skill-check -->

## Runs (inline)

A run is one execution against one task, and it ends inside the same session it started.

- **Every flow declares its inputs, and a run has all of them** before the first step, recorded on the task (`routes/run.md` *Collect the inputs*).
- **Checkpoints belong to the user.** Honour the flow's step marks and the floor (`shared/routes/flows.md`). Every run ends with one check against the task's last `Intent:` line; only a **clean run** — as the flow says, nothing outward without a `go`, the outcome shown to meet the intent — closes without asking (`routes/run.md` *Closing*).
- **Note what the flow did not predict.** A step the user did themselves, a step inserted mid-run, a correction: each gets `TASKS note <id> --at "<step>" "<what>"` when it happens. Steps that went as written get nothing — a note is the exception, so task bodies stay light. Notes are what the closing record's deviations, the post-run flow tweak, and `flow create from <id>` read; one remembered after the close still goes on the task. A `file:` note records a file left outside the project, a `draft:` note something left unsubmitted on an external platform, and a `left:` note something a rehearsal could not clean up; none is a deviation, and none of those three reads them.
- **Only the runner writes the board.** A sequence the runner cannot do is handed off, and whoever takes it reports back to the runner (`routes/run.md` *Handoffs*).
- **Closing is `TASKS ran <id> --flow <names> --record "<inputs; deviations>"`**, which appends `Ran (<date>): …` and closes the task, or re-arms a recurring one. A rehearsal closes with `--rehearsal`, writing `Rehearsed (<date>): …` instead, so it never passes for a real run; it is refused on a recurring task (`routes/rehearse.md`).
- **Then improve the flow.** After the close, offer small fixes to each flow that ran, from what actually happened (`routes/run.md` section 6).
- **Unattended is a mode, chosen explicitly** by the trailing word `unattended`: the run goes to its first stop and puts every decision on the board instead of asking (`shared/routes/unattended.md`); without the word, a run is attended.
- **A scheduled attended run** — one an attended routine's wake starts — reaches the user as `shared/routes/wake.md` *A scheduled run* says (`routes/run.md` *A scheduled run*).
- **No flow yet?** The run is still a run: it proceeds in chunks the user verifies, each noted on the task as it is verified. At the end, offer to turn it into a flow (`/ops flow create from <id>`).

## Running a task

How this skill runs one of its tasks, for the shared routes (`shared/routes/…`) that cite this section:

- **Attended run**: `/ops run <id>` (`routes/run.md`; an umbrella goes to its verification pass, `shared/routes/verify.md`).
- **Unattended run**: `/ops run <id> unattended` (`shared/routes/unattended.md`, its ops part `routes/unattended-run.md`) — every checkpoint, `[user]` step and decision parked on the board.
- **Scheduled run** (an attended routine's wake): `/ops run <id>` as *A scheduled run* (`routes/run.md`).
- **Answering a parked question**: `/ops decide <id>` (`shared/routes/decide.md`); a run parked mid-way is then resumed attended with `/ops run <id>`.
- **The run's outcome record** is its `Ran` record (`TASKS ran`), which also re-arms a recurring task.

<!-- core: next -->

<!-- core: intent -->

<!-- core: umbrella -->

<!-- core: recurring -->

<!-- core: routines -->

<!-- core: not-planned -->
