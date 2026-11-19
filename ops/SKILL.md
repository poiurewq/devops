---
name: ops
description: Playbook of flows plus the runs that follow them, on a shared task board inside the user's repo. Use for /ops and subcommands (init, tour, add, run, next, wake, schedule, rehearse, flow list/show/create/edit/review/retire, agent, env, status, board, show, change, drop, delete, meta), and whenever the user asks to run a procedure or checklist, follow or write a flow, record what a run did, dry-run (rehearse) a flow, or work a task that is not code.
---

<!-- Built from src/ by src/build.py: edit there, then rebuild. -->

# ops — procedures that run, recorded where they ran

One board per project, shared by every contributor — human or agent — across machines. A **flow** is a written procedure; a **run** is one execution of a flow against a task, and the task file is the record of it. You are the interface: parse intent, run the script for all board and flow state, apply judgment yourself. When the routing table names a `routes/*.md`, read that file and follow it — don't improvise the route.

`SKILL_DIR` = the directory containing this file.

`TASKS` = `SKILL_DIR/scripts/tasks.py` (an executable shim — one word, so it survives being stored in a shell variable; never prefix `python3`), run from inside the repo. It targets the nearest board at or above cwd, or `--scope <subdir>`; there is no single-board fallback, so in a repo of several products, work runs from the product directory.

If running a shim (`TASKS` or `SKILL_CMD`) directly fails with `permission denied` (the file modes were lost, e.g. a synced skills dir), that is not a script error: use `python3 SKILL_DIR/scripts/<name>.py …` for that call and every later one this session, spelled out each time, never stored in a shell variable.

`SKILL_CMD` = `SKILL_DIR/scripts/skill.py` — acts on the installed skill, not the board (`shared/routes/skill.md`).

## Script synopsis

`--scope` goes BEFORE the subcommand. The script serves both skills, so it also carries verbs this skill never uses (branches, PRs, review); the list below is the ops surface.

```
TASKS --scope <subdir> <subcommand> ...
TASKS init [--name <handle>] [--scope <subdir>] [--integration <branch>]
           [--parent <branch>] [--iteration N] [--iteration-name <name>]
           [--iteration-started YYYY-MM-DD]
TASKS whoami [--role]                   # your handle (the roster handle your
                                        # GitHub login holds); --role:
                                        # integrator | contributor
TASKS config [<key> [<value>]]          # parent_branch, iteration,
                                        # iteration_name, iteration_started
TASKS contributor list | rm <name>      # rm: yourself, or anyone as integrator
      | rename <name> <new-name>       # same rule; the old handle stays reserved
TASKS flow list [--all] [--json] | show <name> | runs <name> [--json]
      | create <new-name> --desc "<one line>" [--inputs "<a, b (hint)>"]
           [--uses "<flow, flow>"] [--body T | --file F]
      | update <name> [--desc] [--inputs] [--uses] [--status active|retired]
           [--body T | --file F] [--append "<paragraph>"]   # --append repeats,
                                                            # one paragraph each, in order
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
TASKS routine list [--json] | show <name> | rm <name>
      | rename <name> <new-name>
      | add <name> --accessors "<handle, handle>"
           --mode attended|unattended --environment <env>
           --schedule "<cron> <timezone>"|<timestamp> --trigger "<what, where>"
           --manage "<how to change or remove it there>"
      | update <name> [--accessors] [--mode] [--environment] [--schedule]
           [--trigger] [--manage] [--status active|paused]
      | wake <name>                  # exit 2 + reason, else its due tasks
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
TASKS related "<text>" [--deps <id,id>] # run before every add; --deps
                                        # also lists their umbrellas
TASKS show <id>
TASKS delete <id>
TASKS verify <id> "<how the children met the goal>"   # close an umbrella
TASKS note <id> [--at "<step>"] "<what the work did not predict>"
            [--date YYYY-MM-DD]         # Note (<date>): …; any status but
                                        # proposed/not-planned, done included
TASKS ran <id> [--flow <name[,name]>] --record "<inputs; deviations>"
               [--date <date|timestamp>]   # close an ops task with its run record
               [--rehearsal]         # a dry run: Rehearsed (<date>): …
TASKS list [--type ops] [--assignee <who>] [--status <s>] [--needs decision]
           [--flow <name>] [--json]
TASKS recur list [--due]
TASKS board [--expand] [--watch]
TASKS iteration
TASKS iteration-close [--carry]
TASKS iteration-new [<branch>] [--parent <branch>] [--name <name>]
                    [--iteration N] [--iteration-started YYYY-MM-DD]
                    # omit the branch to roll in place (no parent)
TASKS iteration-land [--create-only] [--title T] [--body B]
                                        # parented boards only
```

Caveats: for a flag not spelled in this synopsis or the route you are following, run `TASKS <subcommand> --help` (the script's own flag reference) — never guess. `--append` adds to a body (no prior `show` needed, can't truncate); `--desc` **replaces** it — only for genuine rewrites. Flags combine in one call; an empty string (`--assignee ""`, `--needs ""`, `--flow ""`) clears a field; multi-word values need quoting. When no board is found the error lists known boards — cd in, or pass `--scope`. **Whenever a `TASKS` command exits non-zero or prints `error: …`, surface that output to the user verbatim and stop** — never hide it, paraphrase it away, or paper over it with hand-run git or gh.

## Ground rules

- **Never edit `.tasks/` or `.flows/` by hand, and never commit them from a code branch.** All board and flow reads/writes go through `TASKS`, which serializes every mutation through the integration branch on the remote — that is what makes the board conflict-free across machines. Bypassing it breaks the model.
- **Secrets never reach the board.** Passwords, one-time codes, API keys and session tokens never go into a task, a flow, a registry entry, or any record on one (`Inputs:`, `Note:`, `Decision:`, `Shipped:`, `Ran:`, …): the board is git history, which every clone keeps for good. Sign-in state and secrets live in the environment itself — its browser session, keychain or password manager — so a flow step says "assumes signed in to <X>" instead of carrying the credential. Identifiers (a username, an account number) are not secrets and go on the board as they are — in a flow body, an `Inputs:` line, a note or a record — since the board is as private as the repo. Reread every free-text board write for anything secret-shaped before sending it. A secret that lands anyway is reported to the user at once and fixed by rotating it, never by rewriting board history.
- **Humans decide; agents draft.** Review verdicts, design-fork resolutions, closing calls, proposal approvals, and flow creation and edits belong to the user: surface the question and wait. One the user chooses not to answer yet, or one that comes up with nobody there (an unattended run), goes on the task — `needs: decision` with the question in its body, or new work filed as `proposed` — never left in the chat and never decided around. Every flow write is checked first against an intent the user confirmed, by a fresh reviewer when its impact warrants (`shared/routes/flow-create.md` *Reviewing a flow write*).
- **User specs are one guess.** What the user lays out — filing a task, recommending a change, describing a step, sketching a flow — is one guess at the result and may not be the best. When any part doesn't make sense or could be clearly improved, say so; when something is unclear, ask. The commitment is to a good outcome, not to the user's words.
- **Under-specify tasks, and write short.** A task description is a few sentences: the goal. Details get resolved when the work is done. The same brevity applies to everything else you write — flows, appended decisions, run and shipped records, PR bodies, reports to the user. Review bandwidth is the scarcest resource on the board, and verbose text spends it. Never produce long specs, plans, or status reports the user didn't ask for.
- **Do not manufacture specifications.** When adding or modifying a task, never write constraints, non-goals, interfaces, or other requirements the user did not explicitly state or approve. Future agents treat the task file as human-approved. Non-goals belong on the task only when the user said them.
- Natural-language intents map onto subcommands; fulfil them and mention the keyword once ("done — btw, `/ops pick 12` does this directly"). Always show a suggested command's argument shape — `/ops add <task-or-goal>`, `/ops show <id>` — never a bare `/ops add ...`, which leaves the user guessing what goes there.
- **New work goes through `/ops add`.** Explicit `/ops add`, freeform "we should…", or a goal stated after `/ops` all land on the same path, and add triages it — never ask the user to pick a path. A verb given a description no task matches (`/dev implement <goal>`, `/ops run <description>`) files it through add first, then carries on.
- **A new task's id is the one `add` printed.** Every follow-up on a task just filed — implementing it, citing it, updating it, a dep or umbrella pointing at it — uses the `id:` from that `add` call's output, never one predicted from the board or counted on from an earlier add: another contributor may have filed in between.
- **Vendor-neutral context.** Product docs live in `AGENTS.md` at the directory that owns the work — the nearest one that covers it; a nested package's rule does not go in the repo root. Record what future work there needs and neither the code nor the board shows: conventions and decided architectural, procedural, or domain rules, not only pitfalls. Keep it lean. Each piece of knowledge has one home: what a flow needs goes in that flow, a place's facts in its environment entry (`TASKS env update`), and only product-wide context in `AGENTS.md`. A tracked `AGENTS.md` changes through a dev task like any other file; a gitignored one is the user's private copy, edited directly. If `CLAUDE.md` is present, it is a symlink to that `AGENTS.md` — not the reverse (promote a lone `CLAUDE.md`; if both are regular files, fold unique content into `AGENTS.md`, then replace `CLAUDE.md` with a symlink).
- **Design heuristics.** A product may keep a `## Design heuristics` section in its `AGENTS.md`: the user's standing calls for settling design forks, one line each, led by a short bold name so it can be cited. A fork one of them clearly settles is not a question: decide it, record `Decision: <choice> (heuristic: <name>)`, and tell the user which heuristic decided it so they can override. This holds in every route that meets forks, unattended runs included — applying a heuristic is the user's decision, not the agent's. A fork no heuristic clearly settles still goes to the user. When the user's call on a fork looks general enough to settle future ones, propose it as a new heuristic; add it only on their yes, as an `AGENTS.md` change (above).
- **Ops changes the world, not the codebase.** A run sends the mail, files the form, updates the spreadsheet, moves the thing. It never edits, commits, or branches project code — no branches, no PRs, no review queue. A task that turns out to need code changes goes on as a dev task (SKILL.md *Two task types*, crossing over).
- **Never run git yourself.** Anything a run leaves in the working tree is the user's to keep or discard, and board and flow state is already committed and pushed by the script.
- **Every run is recorded.** A run ends when the task's aim is met, not when the steps are exhausted — judged by the user, except for a clean run whose outcome the agent can show meets it (*Runs (inline)*). `TASKS ran <id> --record "…"` is what closes an ops task. The record says what the run was given and where it departed from the flow — it is the only durable trace of what happened, and it is what later makes a flow improvable.
- **A flow is a procedure, not a policy.** Write the steps someone could follow, each marked `[agent]`, `[user]`, `[confirm]`, or `[external]` (`shared/routes/flows.md` *Step marks*). Do not write constraints, approvals, or non-goals the user did not state.

## State layout (per board)

- `<scope>/.tasks/` — tracked, lives only on that board's integration branch: `NNN.md` (one file per task), `board.yml` (`schema_version`, integration_branch, parent_branch, iteration, iteration_name, iteration_started, integrator, contributors — each `handle (github-login)`), `areas.md` (area names + one-line scopes, for dev tasks), `log.md` (past-iteration index), `archive/<n>-<slug>/NNN.md` (every closed task, verbatim — the full record the log only indexes, run records included; dir is `archive/<n>/` when unnamed). `iteration` is a positive integer (identity, default 1 at init); `iteration_name` is an optional display label; `iteration_started` is `YYYY-MM-DD` (stamped at init / iteration-new, settable to match an external calendar) — `shared/routes/iteration.md`. Ship titles PRs `[n/T<id>] …` (`[<scope> n/T<id>] …` on a scoped board, e.g. `[tools/clk 3/T24]`). Missing `schema_version` means 0; see product `AGENTS.md` for compatibility rules when changing board schema.
- `<scope>/.flows/` — tracked, same home as `.tasks/` (integration branch only, written through `TASKS flow …`), but flows outlive iterations — nothing archives them. One file per flow, `<name>.md`: frontmatter `id` (numeric, fixed at create), `name`, `description` (one line, written like a skill description), `inputs`, `uses` (flows it follows), `status` (`active`/`retired`), `formerly` (past names, a matching hint only), `created`; body = the procedure (`shared/routes/flows.md`). Flows are referred to **by name**, never by number — a number is always a task id. Names are slugs (`lowercase-with-hyphens`). A task records the flows it followed as `flow: <id> <name-at-the-time>`, so lookups match on the id and a rename never rewrites history. `flow show|update|rename|retire` accept the closest name (exact, then a `formerly` entry, then fuzzy; ambiguous → error) and print what they matched. `rename` frees the old name at once; a task's recorded run keeps resolving through the id. `create` refuses a name a retired flow still holds (rename it first). Ids are minted `max+1` against the synced board, so two boards can mint the same one before either pushes (different file names, so nothing conflicts): every flow command warns while an id is shared, and `flow reid <name>` mints a fresh one for the flow whose runs nobody has recorded yet — it refuses when a task already records that flow, and names the other one to reid instead. Any task may name the flows that govern it (`update <id> --flow <name>`, set at the start of the work): an ops run follows them and records them with its `Ran:` line, and a dev task has them followed while it is built — it closes at land, so it never gets a `Ran:` line, and the field stays as the record of what governed it. `<scope>/.flows/agents/<name>.md` and `<scope>/.flows/environments/<name>.md` are the **registries** flows point at (written through `TASKS agent …` / `TASKS env …`, never read as flows): an agent is `name`, `accessors`, `description` (one line, who it is); an environment is `name`, `accessors`, optional `machine`, body = prose expectations; both carry `formerly` (past names). `<scope>/.flows/routines/<name>.md` is the third registry, the scheduled triggers that start recurring tasks (see Routines below), under the same name and accessor rules. There are no ids: a run record names an entry by the name it had then, so `rename` keeps the old name in `formerly`, where it stays **reserved** (add and rename refuse it) and still resolves — `show`, `update`, `rename` and `rm` accept a former name and print what it matched. `rm` frees all of an entry's names. Every accessor is a board contributor and each entry keeps at least one, so every name leads to a human who can reach it; `project`, `runner`, `any` and `inline` are reserved. Accessors are a routing aid — who can reach it now — not history: who ran an agent for a given run lives in that run's record.
- `<scope>/.dev/` — product-local, gitignored, per-checkout (root board → `.dev/` at the git toplevel): `boards.json` (scope→branch cache), `board/` (hidden worktree on a private branch `_dev-board` or `_dev-board-<scope>`, which the script commits board changes through), `worktrees/` (task worktrees). Identity is not stored here (*Identity* below).
- `<scope>/TASKS.md` — derived kanban view, gitignored, regenerated by `board`.
- `<scope>/board` — local live viewer (`r` refresh, `a` toggle by-area, `e` toggle expand, `l` toggle a flat list of every task in this iteration, done included, latest board commit first (`a`/`e` do not apply while it is up), `c` check (an id, or `id,id…` for a group), `s` search (words + Enter ranks live tasks as `TASKS related` does, `e` widens it to done/shelved/not-planned (dimmed); while the `s>` prompt is open every letter is query text, Esc cancels, Ctrl-D still quits), `f` flows pane, `g` registries pane, `q` (or Esc) back one level — a typed id, then a task or flow opened from search hits back to the hits, then the shown output, then an open `c>` prompt, then the flows pane, registries pane or latest list back to the board — and `q` quits from the plain board (Esc never quits; Ctrl-D quits from anywhere); the help line says `q back` while anything is open and `q quit` on a clean board (`r` is always refresh), arrows scroll, space/b page, type a task id + Enter to show it; in the flows pane a typed number is a flow id and opens that flow with its run history at the bottom, `h` opens an `h>` prompt where each flow id + Enter opens that flow scrolled to its history and the prompt stays open for the next (a bare `h` on an open flow jumps there and opens it; `h` again or `q` closes it), and `s` searches flows by name, description and procedure (retired ones tagged and dimmed); the registries pane lists agents, environments and routines one line each, and a typed row number + Enter opens that entry — the numbers only point at rows of that view, since registry entries have no ids), gitignored, written by `init` if missing and refreshed by `init` / `board` while still a stock wrapper. `./board update` rewrites it from the installed skill even if edited. Not `.dev/board` (that is the board worktree).

**Two task types**, one board. Frontmatter carries `type`: `dev` (written on every task the script touches; absent still reads as dev) or `ops`. A **dev task** changes code: it carries the areas it will touch (locks that keep two contributors out of the same region), is built on its own branch, and lands through a PR — `/dev` builds it. An **ops task** changes the world, not the codebase — it is run through flows, not built: it carries no area (the script refuses one), gets no branch and no PR (`claim` and `ship` refuse it), is marked `⚙ops` on the board, and closes with its run record (`TASKS ran`), not a merge — `/ops` runs it. **Crossing over**: a task met under the other skill's route continues in the same session, never stops at the boundary — load the other skill (the harness's skill tool where there is one, else read `../<other>/SKILL.md` from this skill's directory; both are always installed together) and follow its route, `/dev <id>` or `/ops run <id>`. A task already of that type just goes on there. One whose type is wrong converts first, on the user's yes: an ops task that turns out to need code — say what the run found, note the run so far (`TASKS note`), then `update <id> --type dev --area <name> --status backlog` so `claim` can take it; a dev task that would change no files — `update <id> --type ops --area ""`. An unattended run keeps its mode across (`/dev <id> unattended`, `/ops run <id> unattended`) and never converts: it parks the task as `needs: decision`. `type` is orthogonal to `kind`: `kind: umbrella` is a goal parent whose `deps` are its **direct children** (leaves or nested umbrellas) — hierarchy is the dep graph among `kind: umbrella` nodes, with no separate parent field — closed by a verification pass, never automatically (*Umbrella close*); `kind: recurring` is perpetual work on a clock (*Recurring*), and also carries `cadence` or `schedule`, `last_run`, `next_due` and `routine` (*Routines*), each omitted when empty; absent/empty is a normal task.

**The board view.** `TASKS board` is an index (one line per status of task ids; an id carries its line's attention marks: `T81❓` with an open `needs`, `T81📨` while a `doing` run waits on a third party or a handed-off agent, red once overdue; `T81🚨` in place of `⏰` when its routine did not start it) then in-play tasks one per line, umbrella children indented under their parent (which also carries a leaf status rollup), waiting runs after the ones you can act on; done, shelved, and not-planned fold to a count. `--expand` adds those three to the index and the list — it is not an umbrella un-collapse; `--by-area` indexes by area instead of status (same nesting; folded statuses stay counts on last index lines unless `--expand`).

**Statuses**: `proposed` (filed by an agent, awaiting human approval) → `backlog` → `planned` → `doing` → `draft` → `review` → `done`. `draft` and `review` are PR states, so only a dev task passes through them: `ship` always opens the PR into `draft` — the work is out, but not on the integrator's queue — and `TASKS ready <id>` promotes it (draft → review, and marks the PR ready) and `TASKS unready <id>` pulls it back; both are human calls, never an agent's own move, and `update --status draft|review` on a task with a PR is refused and redirected to them. `land` refuses a draft. An ops task goes from `doing` (a run under way) to `done` when `TASKS ran` closes it. A run stopped partway stays `doing` with its assignee: `TASKS pause` records where it got to, so a later session resumes from there, and `TASKS wait` marks one stopped at an `[external]` step or waiting on a handed-off agent's report (`📨waiting <who> by <date>` on its line, red once overdue — on a dev task too, which keeps its branch and area locks); the mark clears when the task leaves `doing`. Off to the side: `shelved` and `not-planned` (*Not planned and shelved*). `done`, `shelved`, and `not-planned` do not block an iteration close. A `recurring` task never reaches `done`: it re-arms to `backlog` after each run (*Recurring*). `needs: decision` marks an open question awaiting a human call, detailed in the task body (`❓needs-decision` on its line).

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
| `/ops flow` / `/ops flow list` | `TASKS flow list` (`--all` includes retired). |
| `/ops flow show <name>` | `TASKS flow show <name>`. |
| `/ops flow runs <name>` | `TASKS flow runs <name>` — every run of it, newest first. |
| `/ops flow adopt <source>` | Read `shared/routes/flow-create.md` — take a procedure the user already wrote (a doc, a pasted checklist, a file) into the playbook. No name needed up front; it is chosen once the scope is settled. A list of separate things to do is `/ops absorb` instead. |
| `/ops flow create [<name>] [from <id>\|from this conversation]` | Read `shared/routes/flow-create.md` — write one from scratch, from a run, or from what was just discussed. |
| `/ops flow edit <name> [<what to change>]` | Read `shared/routes/flow-create.md` (editing section). A change named in the invocation is made surgically; without one, the same collaborative rounds as create. |
| `/ops flow review <name>` | Read `shared/routes/flow-review.md` — check a drafted flow write against its intent and, once the user agrees, make it — as the fresh reviewer a flow write is handed to. |
| `/ops flow rename <name> <new-name>` | `TASKS flow rename <name> <new-name>`; say that the old name is free again and past runs still resolve. |
| `/ops flow retire <name>` | Confirm, then `TASKS flow retire <name>`. Kept for the record; never delete a flow that runs point at. |
| `/ops agent [list \| show \| add \| update \| rename \| rm] …` | `TASKS agent …` — the agents flows hand sequences to. `add` asks for the accessors (board contributors who can reach it) and a one-line description; `rm` confirms first. |
| `/ops env [list \| show \| add \| update \| rename \| rm] …` | `TASKS env …` — the places sequences run. `add` asks for the accessors, the machine if there is one, and what the place must provide (`--expects`); `rm` confirms first. |
| `/ops routine [list \| show \| add \| update \| rename \| rm] …` | `TASKS routine …` — the scheduled triggers that start recurring tasks (*Routines* below). `add` asks for the accessors, the mode, the environment, what the trigger is set to and where it lives, and how to change or remove it there; `rm` confirms first. |
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

## Identity

Before any board operation, check identity with `TASKS whoami` — never probe the filesystem for it yourself. Identity is not stored: it is the roster handle your GitHub login holds — `DEVOPS_GITHUB_LOGIN` if set (a login, not a handle; for cloud or CI), else the account `gh` is signed in as — so a `gh auth switch` changes it at once. Rosters are per board, so run from the product directory or pass `--scope`; a bare monorepo root with no board there errors. If `whoami` errors, run the init route (`shared/routes/init.md`).

**Contributors** are the board's roster of handles, each tied to one GitHub login so every handle traces to a person: one login maps to one handle, and handles are unique. Init reads the login from `gh` and joins or registers by it. `TASKS contributor list` shows who is who; `TASKS contributor rm <name>` removes a stale handle — run by that contributor or an integrator, refused for the last integrator, for anyone still assigned work, and for the last accessor of a registry entry; otherwise it also drops them from every accessor list. `TASKS contributor rename <name> <new-name>` (same who-may rule) renames a handle on the roster, the integrator roster, live task assignees and registry accessors — never archives or run records; the old handle stays reserved. A handle is renamed this way, never by re-joining, and nothing else needs updating: identity is looked up by login.

## Skill check

Run `SKILL_CMD check` once at the start of bare `/ops`, `/ops help`, `/ops init`, `/ops add`, `/ops run`, `/ops next`, `/ops board`, `/ops meta`, `/ops wake`, and `/ops schedule`.

It runs at most every 24h and stays silent when the local version is current or the network fails; a missing local `VERSION` counts as `0.0.0`. Show any line it prints (one quiet line) and continue the command — never block board work on it. With auto-update on, the check may apply a pull and print one success/failure line.

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

## Next

`/ops next` picks for you, among this skill's own type of task (`type: dev` for `/dev`, `type: ops` for `/ops`). Candidates are `backlog` or `planned` tasks, unassigned or yours, no open `needs`, every dep `done`. An umbrella is a candidate only once all its children are done — its verification pass is due (*Umbrella close*) — and then it ranks first; one with open children never is. Then due recurring work (`TASKS recur list --due`), then your own `planned` tasks, then the rest. Propose the top one in a line (title, and why it is first), with the runner-up; on a yes, run it as *Running a task* says (an umbrella goes to its pass). Nothing eligible → say so and point at `/ops add <task-or-goal>`. What could stop the work — collisions, a flow step that needs a person, fork risk — is not filtered here: you are there to make those calls. Runs already in flight are status's (`shared/routes/status.md`). `/ops next unattended` is a different choice (`shared/routes/unattended.md`), and it never picks an umbrella.

## Intent

Every task's body ends with one `Intent:` line: what the user actually wants out of the work, the outcome they would judge it by — not the change or the steps. It is the user's goal in their terms, never your inference dressed as theirs. Filing a task, the premise usually answers it already; ask (one question) only when the invocation leaves it unclear. It is a body line, not a frontmatter field: pass it as the last paragraph of `--desc`. On a recurring task it never restates the schedule ("weekly", "every month", a due day): `cadence`, `schedule` and `next_due` in the frontmatter hold that and change without touching the body, so the line names what each run is for. Several tasks from one ask each carry their own: an umbrella's is the user's goal, a child's is the part of that goal it serves.

The last `Intent:` line wins: when the intent changes (`/ops change <id> intent <new intent>`), append a new one with `TASKS update <id> --append "Intent: …"`, never a `--desc` rewrite, and earlier ones stay as the record that the goal moved. A task with no `Intent:` line gets one before work on it starts — ask the user what they want out of it and append their answer. Every closing judgment is against it: implement's and review's check of the diff, a run's final check, an umbrella's verification pass.

## Umbrella close

**An umbrella is never auto-closed.** Its children all being `done` says the work happened, not that the goal was met — separating those two judgments is the whole reason the umbrella exists. So no flow, and no agent, closes one off a status rollup: `TASKS update <id> --status done` on a `kind: umbrella` task is **refused**, and closing it has its own verb instead — `TASKS verify <id> "<how the children met the goal>"`, which records `Verified (<date>): …` in the body and closes the task. That record is carried into `log.md` at iteration close (an umbrella never ships or runs, so it is its only outcome line).

The pass itself is `shared/routes/verify.md`, which `/dev <id>` and `/ops run <id>` both route an umbrella to, whatever its type. It reads each child's own outcome record against the umbrella's last `Intent:` and ends in the same session, either filing the gaps as new children or closing with the record — no branch, no PR, no review. Anyone may run it — typically whoever filed the umbrella and knows its intent; unlike `land`, it is not integrator-only. An unattended run never runs it.

`meta` never proposes closing an umbrella. When one looks complete it says the goal check is **due** and worth prioritizing, and points at the pass.

## Recurring

`kind: recurring` + `cadence: <N><unit>` (unit `d`/`w`/`m`, e.g. `2w`, `1m`) or `schedule: <cron> <timezone>` (a 5-field cron expression and an IANA zone, e.g. `0 12 * * 3 America/New_York`; one or the other, never both) = perpetual work on a clock — an audit, a dependency sweep, the monthly close — not a task that finishes. It is never terminal: recording a run stamps `last_run` and re-arms it to `backlog` instead of closing it — `land` for a dev task, `TASKS recur ran <id> [--date]` for a dev run that never had a PR (refused while a branch or PR is live — `land` owns that run), `TASKS ran` for an ops task — and `--status done` is refused. The due date is **derived** by default (`last_run + cadence`, or the first scheduled time after `last_run`), so a clock edit re-dates it immediately; no `last_run` = due now on a cadence, and the first scheduled time on or after the start of its created day on a schedule. A missed scheduled time stays due until a run is recorded. Schedulers fire triggers early, so each scheduled time has an **early window** of 3 hours before it (at most half the gap from the scheduled time before). On a schedule, `last_run` records the scheduled time the run **covered**, not when it was recorded: a run recorded inside a time's early window covers that time, any other covers the latest time at or before it (a catch-up run recorded before today's window covers yesterday's, so today's stays due), and the next due is the time after it. A bare date is kept as given. Cadence tasks stamp the run time and have no window. `last_run` is stamped as a timestamp with offset (`2026-11-11T12:04-05:00`); `--last-run` and `--date` also take a bare date, which a schedule reads as the end of that day in its timezone. To set the date instead — a first run on a chosen future day, or the next run pushed or pulled — `add … --next-due <date>` or `update <id> --next-due <date>` records it without faking a `last_run`: it overrides the derived date until a run is recorded (`land`, `recur ran`, `ran` all clear it), then the cadence or schedule takes over — today's date makes a scheduled task due now, so its first run can be fired by hand; `""` clears it. Use a date the user named; never invent one. `TASKS recur list [--due]` is the due view; `board` marks each recurring id on its index row — `↻`, or a red `⏰` when due and its due state on its line.

Status alone decides whether the clock runs: in `proposed`, `shelved` or `not-planned` it is stopped — never due, left off `recur list` and unmarked on the index, and recording a run on it is refused until it is revived. Its cadence or schedule, `last_run` and `next_due` are kept, so the clock resumes when it returns to an active status. How an iteration close carries one is `shared/routes/iteration.md`'s.

**Agents never invent a recurring task.** Whether work recurs, and how often, is a human call: a flow may offer to schedule one and wait for the answer, an unattended run never files one.

## Routines

A **routine** mirrors a scheduled trigger that lives at its source — a harness's scheduler, cron, a cloud routine — so the board knows which recurring tasks start on their own, where and how. One file per routine, `<scope>/.flows/routines/<name>.md`, written through `TASKS routine …`: `name`, `accessors` (contributors who can reach the trigger's source), `mode` (`attended`: exactly one task, and the user is reached when it needs them; `unattended`: its tasks run in one session and share its context), `environment` (the registered environment it runs in), `schedule` (what the trigger is set to: a cron expression and an IANA zone in the recurring syntax, or one fire time as a timestamp with offset), `trigger` (one line: what it is and where, with its identifier), `status` (`active`/`paused`), `formerly`, `created`; body = how to change or remove the trigger at its source. Former names stay reserved and keep resolving, as for agents and environments; `rm` is refused while a task points at the routine, and `env rm` while a routine runs there. `paused` is the board-side off switch for anyone who cannot reach the source: the trigger still fires, and the wake stops on it. Setting one up for a task, or moving a task to another, is `/ops schedule <id> [<routine>]` (`shared/routes/schedule.md`).

A recurring task points at a routine with its `routine` field (`add` / `update --routine <name>`, `""` clears). A routine's tasks share one type, so `/dev` and `/ops` each wake only their own; a second task on an attended routine is refused; pointing a task at an unattended routine notes the shared session, and warns when the task's flow has `[user]` steps nobody will be there to do. Changing its kind away from `recurring` is refused while the routine is set — clear the routine first. Editing a covered task's cadence, schedule or `next_due` prints a reminder that its trigger lives at the source and may need the same change there.

**Not started.** A covered task that is due, at rest (`backlog`/`planned`) and has no open `needs`, whose routine's schedule says it should have fired for it more than an hour ago, reads `🚨routine <name> did not start` on its line, and its index id carries `🚨` in place of `⏰` — `routine <name> paused` (plain `⏰` on the id) when the routine is paused. It is derived whenever the board is read, never stored; `TASKS routine list` shows the same under each routine with the time it should have fired. A schedule this machine cannot read (say, a zone its timezone data lacks) is listed as `schedule unreadable (<why>)` and skipped by the check rather than stopping the board.

**Wake.** `TASKS routine wake <name>` is the gate a routine's run passes first: exit 2 with the reason when the routine is paused, no longer on the board, or runs the other skill's tasks; otherwise its due tasks at rest (`backlog`/`planned`), in due order — a scheduled task counts as due once inside its time's early window (see *Recurring*), so an early fire still runs it — then any due one with an open `needs` on a `skipped, waiting on a decision:` line and any still in flight on a `skipped, in flight:` line — a re-fire never hands out a parked question again, nor a run that is still going. A trigger's prompt is only `/ops wake <name> <dir>`, `<dir>` being the product directory's absolute path in its environment (`shared/routes/wake.md`): every rule a scheduled run follows lives in the skill and on the board, so the prompt at the source changes only if the checkout moves.

**Runner environment.** The environment a routine runs in must give a session everything a run needs with no one at the keyboard: a checkout of this repo that can push to the integration branch, with the product directory at the path the trigger's prompt names; this skill at a version the board accepts; `gh` signed in as a login on the board's roster (`TASKS whoami` checks it at the wake); for dev tasks, the right to open PRs; every tool call the run makes either allowed or refused up front, never left waiting on a permission prompt; and, for an attended routine, a way to notify the user. These are judged when the routine is set up and by watching its first run — the script does not check them.

## Not planned and shelved

Two ways to set a task of either type aside, each a human decision: agents propose them, and an unattended run never sets one. When the user wants a task gone, ask which they mean — `not-planned`, `shelved`, or `delete` — rather than choosing for them.

- `not-planned` = decided against, kept with its reason so the idea isn't re-litigated: `TASKS update <id> --status not-planned --reason "<why>"`, the reason required and appended to the body as `Not planned (<date>):`. It also retires a recurring task for good. `delete` (`TASKS delete <id>`, after confirming) erases instead — for something filed in error, a duplicate, noise.
- `shelved` = set aside for now — not this iteration, or not needed at present, but it may matter again; unlike `not-planned` it is not decided against. `TASKS update <id> --status shelved --reason "<why>"` (or `add --status shelved --reason "<why>"`), the reason required and appended as `Shelved (<date>):`. It holds no area lock, folds to its own `Shelved` count on the board, and `iteration-new` carries it onto the next board still shelved, with a `carried from <n>/T<id>` note — a recurring one too, since shelving pauses it.
- `later` is retired: `--status later` is refused with a pointer to `shelved`, and a task file still saying `later` reads as shelved.

Ask for a reason in the user's own words; if the answer is thin, ask once what changed. Neither is worked (claim, ship, land and a run all refuse it) or picked by `next`, and none blocks an iteration close (logged `[not planned]`, `[shelved]`). Revive with `--status backlog` or `/ops pick <id>`; a recorded reason stays as history.

A task with a live branch or PR cannot move to `shelved` or `not-planned`: `update` refuses, because the branch would outlive the move and the next iteration would orphan the PR. Decide the PR's fate with the user first (land it, close it, or keep it open), run `TASKS cleanup <id>` to drop its worktree (it keeps the branch and PR), then clear both in the same call (`--branch "" --pr ""`); the old values are recorded in the body as `Cleared on moving to <status> (<date>): …` and nothing is deleted.
