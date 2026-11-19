# /ops run — do the task, record what happened

Covers `/ops run <id[, id…]>`, `/ops run <flow-name> [inputs]`, and `/ops run <description>`. With the trailing word `unattended`, read `shared/routes/unattended.md` first: its overrides, and `routes/unattended-run.md`'s, win where they apply. A run an attended routine's wake starts is attended, with no word (*A scheduled run*, section 3). A run ends in the session it started, the task closed with its record before you hand back — except one the user explicitly stops partway (*Pausing the run*), one at an `[external]` step (*Waiting on a third party*), and one waiting on a handed-off agent's report (*Handoffs*).

## 1. Resolve what to run

- **Digits** (`/ops run 12`, `/ops run 12, 14`) → those task ids. Unknown id → stop and say so; never treat a number as a flow or as new work.
- **A flow name** (closest match in `TASKS flow list`) → run it, on the task that already covers it if there is one. Candidates: `TASKS list --type ops --flow <name> --json` minus `done` tasks and rehearsals (`rehearsal: true`), then `TASKS related "<flow name + description>"` hits with no `flow` set that plainly cover it. One candidate at rest (`backlog`/`planned`, recurring included) that is clearly the flow's task — its `flow` matches, or one unmistakable `related` hit — runs at once, with one line: `running as T<id> (<title>); say "new" for a separate task`. Otherwise list the candidates with their status, ask once and wait: several, a parked one (`shelved`, `not-planned`, shown with its reason), a `proposed` one, a `doing` one (picking resumes that run), or only a weak `related` hit. Picking a parked or proposed one revives or approves it (`TASKS update <id> --status backlog`). The user may always file a new one instead. A picked task goes through section 2. Before filing a new one, `TASKS flow runs <name>` (it reads the archive, which `related` does not): a run dated **today** is usually the same run — confirm before filing another. Skip `[rehearsal]` entries here and in every comparison with past runs. Then file it (`shared/routes/add.md`, titled from the flow's purpose) and run it.
- **Anything else** → a description of work to do. File it through `shared/routes/add.md`, then run it without asking again.
- **Nothing** → show what is runnable (`TASKS list --type ops --status backlog`, plus `TASKS recur list --due`) and ask which.

Several ids run **one after another**, each through the whole cycle below, in the order given. Report each as it closes; if one stops, say which and carry on with the rest only if the user says to.

## 2. Preflight (per task)

- `TASKS show <id>`. Read the body: past notes, recorded inputs, `Decision:` lines. The last `Intent:` line is what the user wants out of the run (SKILL.md *Intent*).
- **An umbrella** (`kind: umbrella`, of either type) → not run: it gets its verification pass (`shared/routes/verify.md`), and nothing below applies.
- **Not an ops task** (no `type: ops`) → it is code work: continue as `/dev <id>` in this session (SKILL.md *Two task types*, crossing over) — unless it would change no files: then it converts to ops on the user's yes and runs here.
- **State**:
  - `done` → say so and stop.
  - `shelved` or `not-planned` → show the reason and stop unless the user revives it.
  - `proposed` → ask for the approval first.
  - `needs: decision` → resolve it first (`shared/routes/decide.md`); on a `doing` task that resumes the run where it stopped.
  - `unattended:` marker → an unattended run (`shared/routes/unattended.md`) is working it: stop and say so, never resume into it. If the user says that run is dead, `TASKS update <id> --unattended ""` takes it back where it stopped.
  - `waiting:` marker → stopped at an `[external]` step or a handed-off sequence: ask whether the reply or report is in. Not in → say who it waits on and whether the expected-by date has passed, and stop; chasing is the user's call. In → `TASKS wait <id> --clear` and carry on from the step after the latest `Waiting (<date>): …` record's step, with the reply (or the report's `Returns:` values) as its input.
  - Otherwise `doing` → a resume (yours or another machine's): read the body, say where it got to, and confirm with the user before touching anything. The **latest** `Paused (<date>): [<flow> <step>] …` record names the step to carry on from and the artifacts left (and on which machine): check they are reachable here; anything missing — re-do the steps that made it, or fetch it — is the user's call. No pause or waiting record → reconstruct from the notes and say plainly what you are unsure of.

  A resume keeps what the run settled — the flows in its `flow` field, its `Inputs:` lines, its started mark — so the steps below fill in only what is missing, and nothing recorded is asked again.
- **Deps**: nothing enforces them for a run as `claim` does for dev. Name every dep not `done` with its status (`TASKS show <dep>`) and stop before anything starts; going ahead anyway is the user's call.
- **No `Intent:` line** → once the checks above clear the task, get one (SKILL.md *Intent*); no run starts without it.
- **Pick the flow(s)**: read the `TASKS flow list` descriptions against the task, as you would pick a skill; `TASKS flow show <name>` the one that fits and follow its `uses`. Say which and why in one line. Several may fit a task that spans procedures: name them in run order. None fits → section 4.

  **Three or more is a split, not a run** (a flow that `uses` others counts once). Propose one task per flow, in run order, and wait. On the go-ahead, file them (`shared/routes/add.md`), each `--deps` on the one before and the first given the original's deps; turn the original into their umbrella (`TASKS update <id> --kind umbrella --deps <new-ids>`) and run the first. A **recurring** task is not split (it cannot also be an umbrella): propose one flow that `uses` those flows in order (`shared/routes/flow-create.md`) and, on the go-ahead, run the task through it. The user may also just say run it as one.
- **Check the sequences** of the chosen flows (`shared/routes/flows.md` *Sequences*): can you meet each one's `Needs:` here, and are you in its `Environment:` (`TASKS env show <name>`: what it expects, its machine)? An unmarked sequence is yours; `Agent:` is only who usually does it. An environment the registry does not hold → offer `TASKS env add`, or switching it to `Environment: inline` (`/ops flow edit <name>`); follow either once they choose. An inline one is checked against its `Expects:`; its `Accessors:` are who can reach it. Before the first step, tell the user which sequences you will run and which need a handoff — for each, who could take it (its `Agent:`; `TASKS agent show <name>` for who can reach it) and the way you propose (*Handoffs*), confirmed when the run gets there. A resume redoes this for the sequences ahead.
- **Collect the inputs.** Every input the chosen flows declare has a value before the first step: from the invocation, then the task body, then the user — the rest asked in plain words, all in one message. An input whose hint says how to derive it is derived and shown in that message to confirm. Record the values under the flow's input names before starting (`TASKS update <id> --append "Inputs: client=Acme; month=2026-09"`), so the run is reproducible even if the session dies. A credential is never an input: the environment supplies it — an existing session, its keychain, or the user signing in (SKILL.md *Ground rules*, secrets).
- **Mark it started** with the flows picked: `TASKS update <id> --status doing --assignee <me> --flow <name[,name]>` (`TASKS whoami` for the handle). It is refused while a rehearsal of any of those flows is `doing` (and a rehearsal is refused while a real run is): surface the refusal and stop, task unstarted, until the rehearsal is finished or closed (`/ops rehearse <flow-name>` resumes it).

## 3. Running a flow

Follow the flow as written: it is the procedure of record, not yours to silently improve mid-run.

- **Step marks, the floor and checkpoints** are `shared/routes/flows.md`'s, read with the flow. Run straight through consecutive `[agent]` (or unmarked) steps, reporting what came of each; only `[user]`, `[confirm]` and the floor pause the run (shown as in *Checkpoints*), and `[external]` stops it (*Waiting on a third party*).
- **A `uses` step** runs that flow here with the inputs the step names (`TASKS flow show <name>`), then comes back. Nested flows get no closing check of their own; the run has one, at the end.
- **Departures** are noted when they happen (`shared/routes/flows.md` *Departures*); what earns a note is SKILL.md *Runs (inline)*.
- **Record every file left outside the project**, here or on another machine, as the report saying so arrives (a handoff's or your own): `TASKS note <id> --at "<step>" "file: <env> <path> — <one-line description>"`, `<env>` the registry environment name (`project` when local, `inline seq <n>` for an inline one).
- **Check before you act.** Before a step that creates, files or sends something — on a resume above all — check whether it already happened; if so, note it and skip. A fact the flow says to check before use is checked, not taken from the flow's text.
- **Never fabricate.** A step that fails or gives nothing usable is reported as that — ask, or park the question. Never fill its output with a guessed value, a made-up reference or a file it did not produce, and never record a run as clean around one.
- **Never invent approvals.** If the flow says the user checks something, the run does not proceed on your judgment of it.
- **A sequence that drives a screen** — a web app, a desktop program, an OS dialog — is run per `shared/routes/gui.md`.
- **Code turns up** → the task needs code work: crossing over (SKILL.md *Two task types*) — say what the run found and, on the user's yes, convert it and continue as `/dev <id>`.

### Handoffs

A sequence you cannot do here is a handoff, not a failure. **Only the runner writes the board**: an agent handed a sequence reports back instead. Three ways, proposed in preflight (*Check the sequences*):

- **Pass the run on** to a capable agent with this skill, the new runner: `TASKS pause <id> --at "step <n>" --record "<handoff to whom, and why; what exists so far, and where>"`, `<n>` the sequence's first step; the user starts `/ops run <id>` there, which resumes from that record (section 2). The assignee stays the original runner, still accountable. It hands back the same way when a later sequence is yours again.
- **Hand one sequence off** with the brief below, and carry its report back into the run. A report that comes later than this session is waited on: `TASKS wait <id> --on "<agent> via <contributor>" --by YYYY-MM-DD --at "step <n>" --record "<what was handed over, and where>"`, `<n>` the sequence's last step, the date the user's to give, never invented; `/ops run <id>` resumes once it is in, with `TASKS wait <id> --clear`.
- **Nobody capable is reachable**, by you or the user → the user does the sequence's steps by hand, as `[user]` steps, and tells you what came of them.

**The brief** goes to every agent handed a sequence, this skill or not, and stands alone — as if the agent has no board and no flow. Keep it short: the steps (numbered as in the flow), the input values, the environment's expectations to check itself against first, the confirm rule (at a `[confirm]` step, or before anything outward or hard to undo, stop and show exactly what will go out, and go on only on the user's `go`), and what to report: what was accomplished, each `Returns:` field, any departure from the steps, and every file left behind (environment, path, one-line description).

**Record each handoff when it happens**: `TASKS note <id> --at "seq <n>" "<agent> via <contributor>: <what came back, or what is awaited>"` — `<agent> direct` when no contributor was in between, and then the run's assignee is accountable for it. The report's `Returns:` values are the next sequence's inputs.

**Keep the registry true.** A handoff to an agent the registry does not hold → offer `TASKS agent add <name> --accessors "<who reached it>" --desc "<who it is>"`. Through a contributor the agent does not list → offer to add them (`TASKS agent update <name> --accessors "<current, new>"`); one who lost access → offer to drop them the same way.

### Checkpoints

When the flow asks for a sanity check at a `[confirm]` step, read `TASKS flow runs <name>` (skipping `[rehearsal]` entries) and say in the checkpoint what is out of line with past runs, or that nothing is; no flow asking means no comparison.

The checkpoint itself — what it shows, the `About to:` block, the reply contract — is `shared/routes/flows.md` *Checkpoints*.

**Nobody there to say `go`** — an unattended run (`shared/routes/unattended.md`) or one driven asynchronously — never passes a checkpoint on its own judgment. It parks the checkpoint (*Parking an open question*) with the full `About to:` block, payload and numbering included: `TASKS update <id> --needs decision --append "Question: [step <n>] About to: 1. … · 2. … — go, or what to change?"`, `<n>` the checkpoint's step, where `/ops run <id>` carries on. A `go` recorded through `/ops decide` is the `go`: `/ops run <id>` then does exactly what the record shows. A decision that changes what goes out, or a payload that no longer matches the record on resume, is shown again for a fresh `go`.

### Parking an open question

A call that is not yours — money, other people, a commitment behind it — gets **asked**. Park only a question the user has seen and chosen not to answer yet (checking with someone, missing the figure, sleeping on it), or when nobody is there to ask — a session ending mid-run, a run driven asynchronously. Never park a question to avoid asking one. Record it on the board, not in the chat:

```
TASKS update <id> --needs decision --append "Question: <the call, the options, what is already known>"
```

**The status stays `doing`** and the assignee stays yours — never back to `backlog`. Say that it is parked, what unblocks it, and that `/ops decide <id>` answers it and `/ops run <id>` picks the run back up.

### A scheduled run

A run an attended routine's wake starts reaches the user as `shared/routes/wake.md` *A scheduled run* says. For an ops run:

- **The first step that needs the user** is a question preflight would ask, a `[user]` step, a checkpoint, or the closing question of a run that is not clean; agent steps before it run straight through, and a run that never needs the user closes as usual (section 5).
- **It parks** as *Parking an open question* does, `Question: [step <n>] …` (`[preflight]` in place of the step for a preflight question), a checkpoint with its full `About to:` block. An `[external]` step waits instead (*Waiting on a third party*); with no expected-by date to give, the date is the question.
- **Answered later** → `/ops decide <id>` records it, and `/ops run <id>` carries on from step `<n>` — or, for a `[preflight]` question, reruns preflight with the `Decision:` recorded.

### Pausing the run

**Only on the user's explicit call** a run stops partway, to be picked up in a later session or on another machine; a run finished in one sitting records no pause. Being stuck is not a pause: ask, or park the question.

```
TASKS pause <id> --at "<step>" --record "<what exists so far, and where it lives>"
```

`--at` is where the next session resumes: the numbered step (`step 4`), the step's own text when the flow has no numbers, or what was last done in a flow-less run. `--record` is what the run has produced — enough that someone else carries on rather than repeating it — and what it has deliberately not done yet.

Anything a later step needs goes where the next session can reach it (the repo, a shared drive, the ticket), never a temp path; for something too large or private to commit, ask the user where, preferring outside the repo. The record names the location and its machine. Tell the user `/ops run <id>` picks it back up.

### Waiting on a third party

At an `[external]` step the next move is up to someone outside — an office's response, a vendor's delivery — usually days out. Stop the run and record the wait as `shared/routes/flows.md` *Step marks* says (`[external]`). Tell the user `/ops run <id>` picks it back up once the reply is in.

## 4. Running with no flow

The procedure is written as you go, in chunks the user verifies. Each round, **you propose the next chunk** — a handful of steps that can be done together, ending where a human should look — as a short list, with what verifying it will look like. The user accepts (`go`), edits, or replaces it; do not ask them to choose who proposes. An outward or hard-to-undo step inside a chunk is its own checkpoint (*Checkpoints*). Do the chunk, show the result, and let them verify before the next round. Code turning up is a crossing over, as in section 3.

After each verified chunk, `TASKS note <id> --at "chunk <n>" "<what was actually done>"`, procedural (steps and inputs, not narration) and detailed enough for someone else to repeat.

Stop when the aim is met, not when you run out of ideas. Then section 5 — or, on a halt partway, *Pausing the run*, citing the last verified chunk for the step.

## 5. Closing

1. **The final check, always**, against the last `Intent:` line — what the user said they wanted, not your reading of the title or the flow. Show the outcome, not a transcript, and its evidence (the file, the reply, the confirmation number, the command output).
   - **A clean run closes without asking**: every step as the flow says — no `Note:` lines from this run (on a recurring task, those after its latest `Ran` line) other than `file:`, `draft:` or `left:` ones, no corrections, no handoffs; nothing outward without an explicit `go`; and the evidence shown settles that the intent is met, not merely that the steps ran. Go to step 2; the closing message is a line or two — closed as a clean run, the outcome and its evidence — with no quoted `Intent:`, no case for why it qualified, no invitation to object. An objection anyway is noted first (`TASKS note <id> "<what they objected to>"`); a normal task is then reopened (`TASKS update <id> --status doing`) and the run goes on to a second `Ran` record, while a recurring one, already re-armed, is left to its next run.
   - **Otherwise ask**: quote the last `Intent:` line — here is what was done, does this meet it? This covers a run with no flow, any deviation, and an outcome you can only argue for, not show. Say where it falls short before they answer. A no means the run goes on. If the intent itself moved, append the new `Intent:` line before closing.

   Unsure whether a run is clean → it is not; ask.
2. **Record and close**: `TASKS ran <id> --flow <name[,name]> --record "<inputs; deviations>"` stamps the flows, appends `Ran (<date>): …` and closes the task — or re-arms a recurring one to `backlog` and prints its next due date. The record is a sentence or two: what it was given and where it went differently (from the `Note (<date>): …` lines), naming every handoff (`seq 2 by grok-bot via B`); a flow followed exactly is said so. Omit `--flow` only when no flow was followed.
3. Report the close, and the next due date if one was printed.

## 6. After the task is closed

Offers, made after the close so they never hold up the user's work. Skip any that don't apply, and all of them if the user is done for the day.

- **Tweak the flows that ran** against what actually happened — the task's `Note:` lines first, and any the user remembers now (noted on the closed task first). A misleading step, a missing input, an ordering that fought the work, a trap the run fell into (a `Never …` line or a look-alike told apart, with its reason): propose the edit and, on their go-ahead, `TASKS flow update <name> --append "…"` or `--desc`/`--inputs`. Small fixes only; structural ones are `/ops flow edit <name>`, and a flow that keeps needing edits is a signal for `/ops meta`.
- **A flow with no sequence headings** (`shared/routes/flows.md` *Sequences*) → offer its sequence breakdown (`/ops flow edit <name>`) only when this run showed the work changing hands or place: a handoff, a step on another machine, a step needing a capability the runner lacked.
- **An inline environment that ran** → after its first run, or one whose notes say its `Expects:` was wrong, offer to promote it: `TASKS env add <name> --accessors "<its Accessors:>" --expects "<its Expects:, corrected by this run>"`, then `TASKS flow update <flow> --file <path>` with its `Environment: inline`, `Expects:` and `Accessors:` lines replaced by `Environment: <name>`. The user names it. Otherwise leave it; `/ops meta` catches it later.
- **A harness refusal** (a routine's run noted `harness refused …`) → propose a fix of the setup, not the flow: the call allowed or refused up front in the trigger's settings at its source (the routine's body says where), or the environment's `--expects` corrected (`TASKS env update <env> --expects "…"`; `shared/routes/schedule.md` step 7).
- **Context for future work** — something this run learned that later work here needs and no flow or environment holds (SKILL.md *Ground rules*, vendor-neutral context): a flow's own knowledge goes in the tweak above, a place's facts in its environment entry (`TASKS env update <env> --expects "…"`), and product-wide context in `AGENTS.md`. Propose that note in a line; on yes, file one dev task for all of the run's notes, since a tracked `AGENTS.md` changes through a PR: `TASKS add --title "<the note, in a few words>" --desc "<what to add to AGENTS.md> Intent: <what later work there will know>"` — no `--type`, no area (implement asks for one). A gitignored `AGENTS.md` is the user's own copy: edit it directly on their yes.
- **A flow with GUI steps** → also the two offers in `shared/routes/gui.md` *After the run*.
- **No flow was followed** → offer `/ops flow create from <id>` (`shared/routes/flow-create.md`), which reads the run's `Note:` lines.
- **Several flows were chained** → if the chain is likely to recur, offer a flow that composes them (`uses`).
- **Nothing is worth changing** → say nothing; reflexive edits are how a good flow rots.
