---
name: ops
description: Playbook of flows plus the runs that follow them, on a shared task board inside the user's repo. Use for /ops and subcommands (init, tour, add, run, flow list/show/create/edit/retire, status, board, show, change, drop, delete, meta), and whenever the user asks to run a procedure or checklist, follow or write a flow, record what a run did, or work a task that is not code.
---

# ops — procedures that run, recorded where they ran

One board per project, shared by every contributor — human or agent — across machines. A **flow** is a written procedure; a **run** is one execution of a flow against a task, and the task file is the record of it. You are the interface: parse intent, run the script for all board and flow state, apply judgment yourself. When the routing table names a `flows/*.md`, read that file and follow it — don't improvise the flow.

`SKILL_DIR` = the directory containing this file.

`TASKS` = `SKILL_DIR/scripts/tasks.py` (an executable shim — one word, so it survives being stored in a shell variable; never prefix `python3`), run from inside the project. It targets the nearest board at or above cwd, or `--scope <subdir>`; there is no single-board fallback, so work in a repo of several projects runs from the project directory. If running a shim (this or `SKILL_CMD`) directly fails with `permission denied` (the file modes were lost, e.g. a synced skills dir), that is not a script error: use `python3 SKILL_DIR/scripts/<name>.py …` for that call and every later one this session, spelled out each time, never stored in a shell variable.

`SKILL_CMD` = `SKILL_DIR/scripts/skill.py` — acts on the installed skill, not the board (`flows/skill.md`).

## Script synopsis

`--scope` goes BEFORE the subcommand. Don't guess flags. The script serves both skills, so it also carries verbs this skill never uses (branches, PRs, review); the list below is the ops surface.

```
TASKS --scope <subdir> <subcommand> ...
TASKS init [--name <handle>] [--scope <subdir>] [--integration <branch>]
TASKS whoami
TASKS contributor list | rm <name>      # rm: yourself, or anyone as integrator
TASKS flow list [--all] [--json] | show <name> | runs <name>
      | create <name> --desc "<one line>" [--inputs "<a, b (hint)>"]
           [--uses "<flow, flow>"] [--body T | --file F]
      | update <name> [--desc] [--inputs] [--uses] [--status active|retired]
           [--body T | --file F] [--append "<paragraph>"]
      | rename <name> <new-name> | retire <name>     # names, never numbers
      | reid <name>                  # only when two boards minted one id
TASKS agent list [--json] | show <name> | rm <name>
      | rename <name> <new-name>     # a former name stays reserved
      | add <name> --accessors "<handle, handle>" --desc "<who it is>"
      | update <name> [--accessors "<handle, …>"] [--desc]
TASKS env list [--json] | show <name> | rm <name>
      | rename <name> <new-name>
      | add <name> --accessors "<handle, handle>" [--machine M]
           [--expects "<prose>"]
      | update <name> [--accessors] [--machine M|""] [--expects]
TASKS add --title "<title>" --type ops [--deps <id,id>]
          [--desc "<1–3 sentences>"] [--assignee <who>]
          [--kind umbrella|recurring] [--cadence <N><unit>]
          [--next-due <date>] [--status proposed|backlog|planned|later]
TASKS update <id> [--title] [--status] [--assignee <who>|""] [--deps]
          [--needs decision|""] [--flow <name[,name]>|""] [--append "<paragraph>"]
          [--desc "<new body>"] [--kind umbrella|recurring|""]
          [--cadence <N><unit>] [--next-due <date>|""] [--status later]
          [--status not-planned|shelved --reason "<why>"]
TASKS pause <id> --at "<step>" --record "<what exists so far>"
            [--flow <name[,name]>] [--date YYYY-MM-DD]
                                        # stop a run partway; stays doing
TASKS wait <id> --on "<who>" --by YYYY-MM-DD --at "<step>"
           --record "<what was sent, where>" [--flow <name[,name]>]
           [--date YYYY-MM-DD]          # at an [external] step or a handed-
                                        # off sequence; stays doing
TASKS wait <id> --clear                 # the reply is in; stays doing
TASKS note <id> [--at "<step>"] "<what the flow did not predict>"
            [--date YYYY-MM-DD]         # Note (<date>): …; any status but
                                        # proposed/not-planned, done included
TASKS ran <id> [--flow <name[,name]>] --record "<inputs; deviations>"
               [--date YYYY-MM-DD]   # close an ops task with its run record
TASKS verify <id> "<how the children met the goal>"   # close an umbrella
TASKS related "<text>"                  # run before every add
TASKS list [--type ops] [--assignee <who>] [--status <s>] [--needs decision]
           [--json]
TASKS recur list [--due]
TASKS show <id>
TASKS delete <id>
TASKS board [--expand] [--watch]
TASKS iteration
TASKS iteration-close [--carry | --force]
TASKS iteration-new [<branch>] [--name <name>] [--iteration N]
                    [--iteration-started YYYY-MM-DD]
                    # omit the branch to roll in place (no parent)
TASKS iteration-land [--create-only]    # parented boards only; needs gh
TASKS config [<key> [<value>]]          # iteration, iteration_name,
                                        # iteration_started, parent_branch
```

Caveats: `--append` adds to a body (no prior `show` needed, can't truncate); `--desc` **replaces** it — only for genuine rewrites. Flags combine in one call; an empty string (`--assignee ""`, `--flow ""`) clears a field; multi-word values need quoting. When no board is found the error lists known boards — cd in, or pass `--scope`. **Whenever a `TASKS` command exits non-zero or prints `error: …`, surface that output to the user verbatim and stop** — never hide it, paraphrase it away, or paper over it with hand-run git. When `whoami` warns that a GitHub login is already another handle's, surface it and ask the user which of its fixes to run.

## Ground rules

- **Ops changes the world, not the codebase.** A run sends the mail, files the form, updates the spreadsheet, moves the thing. It never edits, commits, or branches project code — no branches, no PRs, no review queue. A task that turns out to need code changes is not an ops task; say so and stop (see The boundary, below).
- **Never edit `.tasks/` or `.flows/` by hand.** All board and flow reads/writes go through `TASKS`, which serializes every mutation through the integration branch on the remote — that is what makes the board conflict-free across machines. Bypassing it breaks the model.
- **Humans decide; agents draft.** A run ends when the user says the task's aim was met, not when the steps are exhausted. Flow creation, flow edits, and proposal approvals are theirs too. Surface the question and wait. A question they decline to answer now is recorded on the task (`TASKS update <id> --needs decision --append "Question: …"`), never left in the chat — that is what puts it in `/ops decide` (`flows/run.md`).
- **Every run is recorded.** `TASKS ran <id> --record "…"` is what closes an ops task. The record says what the run was given and where it departed from the flow — it is the only durable trace of what happened, and it is what later makes a flow improvable.
- **A flow is a procedure, not a policy.** Write the steps someone could follow, each marked `[agent]`, `[user]`, `[confirm]`, or `[external]` (*Step marks*, below). Do not write constraints, approvals, or non-goals the user did not state.
- **User specs are one guess.** What the user lays out — filing a task, describing a step, sketching a flow — is one guess and may not be the best. When part of it doesn't make sense or could be clearly improved, say so; when something is unclear, ask. The commitment is to the work coming out right, not to the user's words.
- **Write short.** A task description is a few sentences: the aim. A flow is the shortest text that someone could actually follow. The same brevity applies to run records and to what you report back. Never produce long plans or status reports the user didn't ask for.
- Natural-language intents map onto subcommands; fulfil them and mention the keyword once ("done — btw, `/ops run 12` does this directly"). Always show a suggested command's argument shape — `/ops add <task-or-goal>`, `/ops run <id|flow-name|description>`, `/ops flow create [<name>]` — never a bare `/ops add ...`, which leaves the user guessing what goes there.
- **New work goes through `/ops add`.** Explicit `/ops add`, freeform "we should…", or an aim stated after `/ops` all land on the same path. `/ops run <description>` with no matching task files it through add first, then runs it.

## State layout

- `<scope>/.tasks/` — tracked, lives only on the board's integration branch: `NNN.md` (one file per task), `board.yml` (settings, iteration, who holds the board), `areas.md` (a dev concern — ops tasks carry no area), `log.md` (past-iteration index), `archive/<n>-<slug>/NNN.md` (every closed task, verbatim — the run records of past iterations live here and stay searchable; written by `/ops iteration close`).
- `<scope>/.flows/` — tracked, same home as `.tasks/`, written only through `TASKS flow …`. One file per flow, `<name>.md`: frontmatter `id` (numeric, fixed at create), `name`, `description` (one line), `inputs`, `uses` (flows it follows), `status` (`active`/`retired`), `formerly` (past names, a matching hint), `created`; body = the procedure. Flows outlive iterations — nothing archives them. `<scope>/.flows/agents/<name>.md` and `<scope>/.flows/environments/<name>.md` are the **registries** flows point at (written through `TASKS agent …` / `TASKS env …`, never read as flows): an agent is `name`, `accessors`, `description` (one line, who it is); an environment is `name`, `accessors`, optional `machine`, body = prose expectations; both carry `formerly` (past names). There are no ids: a run record names an entry by the name it had then, so `rename` keeps the old name in `formerly`, where it stays **reserved** (add and rename refuse it) and still resolves — `show`, `update`, `rename` and `rm` accept a former name and print what it matched. `rm` frees all of an entry's names. Every accessor is a board contributor and each entry keeps at least one, so every name leads to a human who can reach it; `project`, `runner` and `any` are reserved. Accessors are a routing aid — who can reach it now — not history: who ran an agent for a given run lives in that run's record.
- `<scope>/.dev/` — local to this checkout, gitignored: `identity` and the hidden worktree the script commits board changes through. Shared with `/dev` if it is installed; one identity per project either way.
- `<scope>/board` — local live viewer (`r` refresh, `a` toggle by-area, `e` toggle expand, `l` toggle a flat list of every task in this iteration, done included, latest board commit first (`a`/`e` do not apply while it is up), `c` check (an id, or `id,id…` for a group), `s` search (words + Enter ranks live tasks as `TASKS related` does, `e` widens it to done/later/shelved/not-planned (dimmed); while the `s>` prompt is open every letter is query text, Esc cancels, Ctrl-D still quits), `f` flows pane, `q` (or Esc) back one level — a typed id, then a task or flow opened from search hits back to the hits, then the shown output, then an open `c>` prompt, then the flows pane or latest list back to the board — and `q` quits from the plain board (Esc never quits; Ctrl-D quits from anywhere); the help line says `q back` while anything is open and `q quit` on a clean board (`r` is always refresh), arrows scroll, space/b page, type an id + Enter to show it). In the flows pane a typed number is the flow's id (its page ends with its run history; `h` opens an `h>` prompt where each flow id + Enter opens that flow scrolled there and the prompt stays open, a bare `h` on an open flow jumps there and opens it, and `h` again or `q` closes it), and `s` searches flows by name, description and procedure (retired ones tagged and dimmed); in the tasks pane a number is a task id.

An **ops task** carries `type: ops` in its frontmatter. It has no area (areas lock regions of a codebase; ops touches none), gets no branch and no PR, and closes with its run record rather than a merge. It may also be `kind: recurring` (perpetual work on a cadence) or `kind: umbrella` (a goal whose `deps` are its children). Tasks without `type: ops` on the same board are dev tasks — see The boundary.

Statuses for an ops task: `proposed` (filed for approval) → `backlog` → `planned` → `doing` (a run is under way) → `done`. A run the user stops partway stays `doing` with its assignee — `TASKS pause` records where it got to so a later session resumes from there (`flows/run.md`), and only `TASKS ran` closes it. A run stopped at an `[external]` step, or waiting on the report of a sequence handed to another agent, also stays `doing`, marked waiting by `TASKS wait`: the board flags it `📨waiting <who> by <date>` (red once overdue), marks its id `📨` on the Doing index row (`T81📨`, red once overdue), and sorts it after the runs you can act on. The mark clears when the task leaves `doing`. Off to the side: `later` (intended, not this iteration), `shelved` (not needed for now, with its reason) and `not-planned` (decided against, with its reason). `draft` and `review` are PR states and never apply here. `needs: decision` marks an open question awaiting the user (`❓needs-decision` on the line, `T81❓` on the index).

## Routing

| Invocation | Action |
|---|---|
| `/ops` (bare) | Read `flows/first-contact.md`. |
| `/ops help` | Read `flows/first-contact.md`. No board/identity → same setup path as bare. |
| `/ops tour` | Read `flows/tour.md` (the key concepts, one card at a time, on the user's own board). Only when asked; never run it unprompted. No board or identity yet → still give it (its no-board path); do not run init first. |
| `/ops init` | Read `flows/init.md` (identity, board creation or joining). |
| `/ops add <task-or-goal>` | Read `flows/add.md`. |
| Freeform new work | Same as `/ops add`. |
| `/ops run <id[, id…]>` | Read `flows/run.md` (preflight, flow choice, inputs, run, record). Several ids run one after another. |
| `/ops run <flow-name> [inputs]` | Read `flows/run.md` — files a task for that flow first. |
| `/ops run <description>` | Read `flows/run.md` — files via `flows/add.md` first, then runs it. |
| `/ops flow` / `/ops flow list` | `TASKS flow list` (`--all` includes retired). |
| `/ops flow show <name>` | `TASKS flow show <name>`. |
| `/ops flow runs <name>` | `TASKS flow runs <name>` — every run of it, newest first. |
| `/ops flow adopt <source>` | Read `flows/flow-create.md` — take a procedure the user already wrote (a doc, a pasted checklist, a file) into the playbook. No name needed up front; it is chosen once the scope is settled. A list of separate things to do is `/ops absorb` instead. |
| `/ops flow create [<name>] [from <id>\|from this conversation]` | Read `flows/flow-create.md` — write one from scratch, from a run, or from what was just discussed. |
| `/ops flow edit <name> [<what to change>]` | Read `flows/flow-create.md` (editing section). A change named in the invocation is made surgically; without one, the same collaborative rounds as create. |
| `/ops flow rename <name> <new-name>` | `TASKS flow rename <name> <new-name>`; say that the old name is free again and past runs still resolve. |
| `/ops flow retire <name>` | Confirm, then `TASKS flow retire <name>`. Kept for the record; never delete a flow that runs point at. |
| `/ops note <id> <text>` | `TASKS note <id> "<text>"`, with `--at <step>` when a run is under way (you know the step; the user need not say it). Mid-run the id can be left off, and "note: …" in chat means the same. Runs (inline) says what earns a note. |
| `/ops board` | `TASKS board`, then report. One board: dev tasks show alongside, marked. |
| `/ops status` | Your plate — see "Status" below. |
| `/ops show <id>` | `TASKS show <id>`. |
| `/ops change <id> <what>` / `modify` | Map onto `TASKS update <id> --…`; show the result. A new intent is `--append "Intent: …"`, never a `--desc` rewrite — the last `Intent:` line wins (flows/add.md *Intent*). |
| `/ops drop <id>` / "we're not doing this" | Not planned, below — offer delete as the alternative and let the user pick. "Not needed for now" is shelved instead. |
| `/ops delete <id>` | Confirm, then `TASKS delete <id>`. |
| `/ops iteration …` | Read `flows/iteration.md` (show, close, start the next). |
| `/ops config [key] [value]` | `TASKS config …` (settable: iteration, iteration_name, iteration_started, parent_branch). |
| `/ops absorb <source>` | Read `flows/absorb.md` (import a list of things to do as tasks; a written procedure goes to `/ops flow adopt` instead). |
| `/ops decide [id]` | Read `flows/decide.md` (open questions and proposed tasks — the judgments waiting on a person). |
| `/ops pick <id-or-desc>` | `TASKS update <id> --status planned --assignee <me>`; if it is already assigned to someone else, confirm the takeover with the user first. |
| `/ops meta` | Read `flows/meta.md` (pressure the playbook and the board). |
| `/ops skill …` | Read `flows/skill.md` (status, update, auto on/off, feedback). |

Anything not in the table maps onto the closest verb: read the intent, do it, and name the verb once. Before any board operation, check identity with `TASKS whoami` — never probe the filesystem for it. Identity is per project (`<scope>/.dev/identity`), so run from the project directory or pass `--scope`. If `whoami` errors, run the init flow. Given a description instead of an id, run `TASKS list`, match, and confirm if it is not obvious.

## Skill check

Run `SKILL_CMD check` once at the start of bare `/ops`, `/ops help`, `/ops init`, `/ops add`, `/ops run`, `/ops board`, and `/ops meta`. It runs at most every 24h and stays silent when the local version is current or the network fails. Show any line it prints and continue the command — never block work on it.

## Runs (inline)

A run is one execution against one task, and it ends inside the same session it started.

- **Every flow declares its inputs, and a run must have all of them.** Missing ones are asked for before the first step, in the user's words, and recorded on the task (`TASKS update <id> --append`) so the run is reproducible and the record is honest.
- **Checkpoints belong to the user.** Honour the flow's step marks, and gate every outward or hard-to-undo step on a `go` even when the flow forgot the `[confirm]` before it (*Step marks*, below). Whatever the flow says, a run always ends with one overall check: show what was done and ask whether it meets the task's last `Intent:` line — the user's aim in their words. Only then close.
- **Note what the flow did not predict.** A step the user did themselves, a step inserted mid-run, a correction: each gets `TASKS note <id> --at "<step>" "<what>"` when it happens. Steps that went as written get nothing — a note is the exception, so task bodies stay light. Notes are what the closing record's deviations, the post-run flow tweak, and `flow create from <id>` read; one remembered after the close still goes on the task. A `file:` note records a file left outside the project; it is not a deviation, and none of those three reads it.
- **Only the runner writes the board.** Before the first step the runner checks itself against every sequence's `Needs:` and `Environment:` and says which need a handoff. One it cannot do passes the run to a capable agent (a pause it resumes from), goes to another agent as a self-contained brief (every agent gets the brief, this skill or not) whose report comes back to the runner (a `wait` on `<agent> via <contributor>` when it comes later), or, with nobody capable reachable, to the user by hand. Each handoff is noted as it happens, naming the agent and the contributor it was reached through (`direct` when none — the assignee is accountable), and the closing record names them (`flows/run.md` *Handoffs*).
- **Closing is `TASKS ran <id> --flow <names> --record "<inputs; deviations>"`** — one call that stamps which flows ran, appends `Ran (<date>): …` to the task body, and closes the task (a recurring one re-arms to `backlog` with its next due date instead).
- **Then improve the flow.** After the task is closed, re-read each flow that ran against what actually happened and offer small fixes on the spot (`flows/run.md`). Runs are where a flow's rough edges show. Tweaks come after closing so they never hold up the user's task.
- **No flow yet?** The run is still a run: it proceeds in chunks the user verifies, each noted on the task as it is verified. At the end, offer to turn it into a flow (`/ops flow create from <id>`).

## Flows (inline)

Flows are named, never numbered: `/ops run weekly-invoice`, not a number — a number is always a task id. Names are slugs (`lowercase-with-hyphens`). Each flow also carries a fixed numeric `id` used only inside files: a task records a run as `flow: 7 weekly-invoice`, so lookups match on the id and a rename never rewrites history. `rename` frees the old name immediately and keeps it as a matching hint, so names stay natural as the playbook grows.

`flow show|update|rename|retire` accept the closest name — exact, then a past name, then a clear fuzzy match — and print what they matched, so the user never has to type a name exactly. Ambiguity is an error, not a guess. If two machines created flows before either synced, they can share an id; every flow command says so while that lasts, and `TASKS flow reid <name>` gives one of them a fresh id (only the one no run points at).

**Composition.** A flow may follow other flows; those go in its `uses` list and appear in its body as the step that runs them. Keep each flow one coherent procedure — when a run chains several flows by hand, that is the signal to offer a new flow that composes them, not a reason to grow one flow until it covers everything.

**Sequences.** A flow body may group its steps into sequences: a heading, then labeled lines before its steps — `Environment:` (where it runs, an environment name), `Agent:` (optional: who usually does it, an agent name), `Needs:` (the capabilities it requires, in prose), `Inputs:` (what it takes) and `Returns:` (what it hands back) — plaintext, all of them. Step numbers continue across sequences, so a step's number stays its handle for the whole flow. A sequence with no `Environment:` or `Agent:` is the runner's, in this project — and a body with no headings is one such sequence, so a flow written before sequences needs no change. `Agent: runner` and `Environment: project` say that default out loud; `any` means no preference. `flow create` and `flow update` warn on an `Agent:` or `Environment:` name the board's registries do not hold, and on a former name, saying what it now points at.

**Step marks.** Each numbered step carries a tag right after its number: `3. [confirm] Draft the invoice for {client}`, then `4. [agent] Send it`.

- `[agent]` — you do it and report what came of it. An unmarked step is the agent's.
- `[user]` — theirs: ask, wait, never do it for them.
- `[confirm]` — you do it, then stop: show what it produced and wait for the user's `go` before the run goes on. This is the load-bearing mark: it goes on the step right **before** anything outward or hard to undo — sending, paying, publishing, deleting, committing someone to something — the step that prepares it (the draft, the amount, the list of files), so the user signs off on exactly what will go out. When you then perform the irreversible act, show its result; when the user performs it (`[user]`), their doing it *is* the check, and no step follows it to re-verify.
- `[external]` — a third party does it (an office answers, a vendor ships) while the run waits, often for days. Reaching one stops the run: `TASKS wait` records who it waits on and when the reply is due, and `/ops run <id>` resumes once it is in (`flows/run.md`). The step that sends them what they act on is outward, so it is gated as any other.

**The floor:** an outward or hard-to-undo step with no `[confirm]` step right before it (and not itself `[user]`) is gated anyway — you stop before it and show what it will do — and noted (`TASKS note <id> --at "<step>" "no confirm before it, gated"`) so the post-run tweak and `/ops meta` propose the `[confirm]` step for real. Read-only and trivially reversible steps never stop for a checkpoint. The reply contract at a checkpoint is in `flows/run.md`.

**Description quality matters.** The one-line `description` is what a future agent reads to pick the right flow for a task, exactly as a skill description is. Write what it is for and when to use it, not how it works.

## Umbrella close (inline)

A `kind: umbrella` task is a goal whose `deps` are its children. Children all being done says the work happened, not that the goal was met, so an umbrella is **never** closed by a status flip — `update --status done` on one is refused. Closing it is `TASKS verify <id> "<how the children met the goal>"`, and it is a human call: read the children's `Ran:` records against the umbrella's last `Intent:` line, show the user the judgment, and wait. Gaps become new children (`TASKS update <umbrella> --deps <existing+new>`), not work done on the umbrella itself.

## Recurring (inline)

`kind: recurring` + `cadence: <N><unit>` (`d`/`w`/`m`, e.g. `2w`, `1m`) is perpetual work on a clock — the monthly close, the weekly review — not a task that finishes. `ran` stamps `last_run` and re-arms it to `backlog` rather than closing it; the next due date is derived (`last_run + cadence`), so changing the cadence re-dates it at once. `--next-due <date>` (on `add` or `update`) sets the next due date directly — a first run on a chosen future day, or one run moved — without faking a `last_run`; the next recorded run clears it and the cadence takes over (`""` clears it sooner). Use a date the user named; never invent one. `TASKS recur list --due` is the due view, and `board` marks each recurring id on its index row — `↻`, or a red `⏰` when due and its due state on its line. Status alone decides whether the clock runs: a proposed one is not approved yet, a later one is not this iteration, a shelved one is paused and a not-planned one retired. None is ever due, and recording a run on one is refused until it is revived; its cadence and dates are kept, so the clock resumes when it returns to an active status.

**Never invent a recurring task.** Whether work recurs, and how often, is the user's call: offer and wait.

## Not planned, later, and shelved (inline)

`not-planned` = decided against, kept with its reason so the idea is not re-litigated: `TASKS update <id> --status not-planned --reason "<why>"`. Ask the user for the reason in their own words. `delete` erases instead — for something filed in error. When the user wants a task gone, ask which they mean.

`later` = intended, not this iteration: `TASKS update <id> --status later`. Running one is refused until it is revived (`--status backlog`).

`shelved` = not needed for now, but may matter again — neither intended (later) nor decided against (not-planned): `TASKS update <id> --status shelved --reason "<why>"`, the reason required and recorded as `Shelved (<date>):`; ask for it in the user's own words. It folds to its own count on the board, does not block an iteration close, and carries onto the next board still shelved (a recurring one too — shelving pauses it, not-planned retires it). Running one is refused until it is revived (`--status backlog`).

A task with a live branch or PR cannot move to `later`, `shelved` or `not-planned`: `update` refuses, because the branch would outlive the move and the next iteration would orphan the PR. Decide the PR's fate with the user first (land it, close it, or keep it open), run `TASKS cleanup <id>` to drop its worktree (it keeps the branch and PR), then clear both in the same call (`--branch "" --pr ""`); the old values are recorded in the body as `Cleared on moving to <status> (<date>): …` and nothing is deleted.

## Status (`/ops status`)

`TASKS list --assignee <me>`, then report in order: runs in flight you can act on (`doing` with no `waiting:` marker — each is yours to finish and close), then runs waiting on a third party or a handed-off agent (who and by when, overdue ones called out — nothing to do until the reply is in), what is due (`TASKS recur list --due`), and anything waiting on you (`TASKS list --needs decision`, `--status proposed`).

Anything waiting on a decision is resolved in `flows/decide.md` (`/ops decide`), not here — status only surfaces it.

**If your list is empty**, don't stop at "nothing assigned": add the unassigned backlog count and one or two candidates worth running (`TASKS list --type ops --status backlog`), with `/ops run <id>`. If the board is empty too, say so and point at `/ops add <task-or-goal>`.

## The boundary

The board is shared with `/dev`, the development skill in this package, and either skill may be installed without the other. One rule keeps them apart: **a task that changes code is a dev task, and this skill does not do it.**

- A task on the board without `type: ops` is a dev task. Show it, report it, leave it alone; do not run it.
- An ops task that turns out to need code changes stops being an ops task. Say what you found and stop. If the user wants it built, converting it is `TASKS update <id> --type dev --area <name>`, and it is then `/dev <id>` that does the work — a run cannot. If `/dev` is not installed here, say that plainly rather than improvising the code change.
- Flows are not dev-only or ops-only. A dev task may name a flow and have it followed while the code work happens under `/dev`.
- Areas, task branches, per-task pull requests, and review belong to `/dev`. Iterations do not: `flows/iteration.md` covers all of it, including a board with a parent branch, whose iteration ends in a single pull request that `TASKS iteration-land` opens and merges. That one command is the only place this skill touches GitHub, and a board without a parent never reaches it.

Never run git yourself. Anything a run leaves in the working tree is the user's to keep or discard, and board and flow state is already committed and pushed by the script.
