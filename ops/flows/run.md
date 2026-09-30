# /ops run — do the task, record what happened

Covers `/ops run <id[, id…]>`, `/ops run <flow-name> [inputs]`, and `/ops run <description>`. A run ends in the session it started: the task is closed with its record before you hand back. The exception is a run the user explicitly stops partway — *Pausing the run* below records where it got to, so a later session resumes instead of starting over.

## 1. Resolve what to run

- **Digits** (`/ops run 12`, `/ops run 12, 14`) → those task ids. Unknown id → stop and say so; never treat a number as a flow or as new work.
- **A flow name** (matches something in `TASKS flow list`, closest-name resolution) → this is "run this procedure now". First `TASKS related "<flow name + description>"`: if an open task already names that flow, run it instead of filing a second. A task that ran the same flow **today** is usually the same run — say so and confirm before filing another, since some flows are dated by nature. Otherwise file one (`flows/add.md`, title from the flow's purpose), then run it.
- **Anything else** → a description of work to do. File it through `flows/add.md`, then run it without asking again.
- **Nothing** → show what is runnable (`TASKS list --type ops --status backlog`, plus `TASKS recur list --due`) and ask which.

Several ids run **one after another**, each through the whole cycle below, in the order given. Report each as it closes; if one stops, say which and carry on with the rest only if the user says to.

## 2. Preflight (per task)

- `TASKS show <id>`. Read the body: past notes, inputs already recorded, `Decision:` lines.
- **Not an ops task** (no `type: ops`) → stop. This is code work; `/dev implement <id>` is what does it. If the user insists it is really procedural, converting it is theirs to approve: `TASKS update <id> --type ops --area ""`.
- **State**: `done` → say so and stop. `later` or `not-planned` → parked or decided against; show the reason and stop unless the user revives it. `proposed` → not approved yet; ask for the call first. `needs: decision` → an open question blocks it; resolve that first (`flows/decide.md`). Together with `doing` it is a blocked run, not a fresh one — resolving the question resumes it where it stopped. `doing` → a run is already under way (yours, or another machine's), so this is a resume: read the body and say where it got to before touching anything, then confirm with the user. A `Paused (<date>): [<flow> <step>] …` record is a run stopped deliberately; a run paused more than once carries several, and only the **latest** says where it stands — take the step it names as the place to carry on from, and check the artifacts it names are reachable from here, since the record says which machine they were left on. Anything missing is the user's call before you continue: re-do the steps that made it, or fetch it first. Without a pause record the run stopped without saying where, so reconstruct what you can from the notes and say plainly what you are unsure of. A resume keeps what the run already settled: the flows are the ones in the task's `flow` field, the inputs are its `Inputs:` lines, and it is already marked started — so picking the flows, collecting inputs, and marking it started below apply only to what is still missing, and the user is not asked again for anything recorded.
- **Deps**: `TASKS show` prints them, and for an ops task they are ordinary rather than exceptional — but nothing enforces them for a run the way `claim` does on the dev side, so this is where they get checked. Any dep that is not `done` gets named with its status before anything starts (`TASKS show <dep>`), and the run stops there. The user may still say go ahead — an ordering can be stale, or turn out not to block — but that is theirs to say, not an assumption to run on.
- **Pick the flow(s)**: `TASKS flow list` and read the descriptions against this task, the way you would pick a skill. Then `TASKS flow show <name>` for the one that fits, and follow its `uses` into the flows it composes. Say which you picked and why, in one line. More than one may fit a task that spans procedures — that is allowed; name them in the order they will run. **Three or more is a split, not a run**: a task needing that many separate procedures is really that many tasks, and running them as one leaves nobody a place to stop in between. A `uses` chain does not count — a flow that composes others is still one procedure. Say which flows you picked, propose the tasks they map onto (one per flow, in the order the flows would run), and wait. On the user's go-ahead, file them through `flows/add.md`, wire each to the one before it with `--deps` — the order is fixed by construction, since the flows run in sequence — give the first one the original's own deps (an umbrella's deps are its children, so any left on the original would read as one, and a dep the user just overrode still has to be named where the run now starts), and turn the original into their umbrella (`TASKS update <id> --kind umbrella --deps <new-ids>`); then run the first. A **recurring** task is not split: `kind` holds one value, so making it an umbrella would drop its recurrence. Propose instead one flow that `uses` those flows in that order (`flows/flow-create.md`) — the same composition `flows/meta.md` proposes for a chain that keeps recurring — and on the go-ahead run the task through it. They may also just say run it as one, which is equally theirs to say. None fits → section 4.
- **Collect the inputs.** Every input the chosen flows declare must have a value before the first step. Take what the invocation gave, then the task body, then ask the user for the rest in plain words — all of them in one message, not one at a time. Record what you were told on the task (`TASKS update <id> --append "Inputs: …"`) before starting, so the run is reproducible and the record is honest even if the session dies.
- Mark it started: `TASKS update <id> --status doing --assignee <me>` (`TASKS whoami` for the handle).

## 3. Running a flow

Follow the flow's body as written. It is the procedure of record — not a suggestion, and not yours to silently improve mid-run.

- **Honour its step marks** (SKILL.md *Step marks*). `[user]` is theirs: ask, wait, do not do it for them. `[agent]` (or unmarked) you do, then report what came of it — and run straight through consecutive agent steps without stopping; only `[user]`, `[confirm]`, and the floor below pause the run. `[confirm]` is a checkpoint (next).
- **The floor.** An outward or hard-to-undo step with no `[confirm]` step right before it (and not itself `[user]`) gets a checkpoint anyway: stop before it and show what it will do. Note it (`TASKS note <id> --at "<step>" "no confirm before it, gated"`), which is how the flow gets its `[confirm]` step at the tweak in section 6.
- **A `uses` step** means run that flow here, with the inputs the step names. Read it (`TASKS flow show <name>`) and follow it, then come back. Nested flows do not each get their own closing checkpoint — the run has one, at the end.
- **When reality departs from the flow** — a step no longer applies, a system moved, something is missing — say so, do what actually makes sense (asking if the departure is more than trivial), and note it: `TASKS note <id> --at "<step>" "<what>"`. The same goes for a step the user did themselves instead of the flow's way, and for a step inserted mid-run. Record at the moment it happens, not at the end, so the note survives a session that dies. Those notes become the `deviations` half of the record and are what later makes the flow better. Keep them concrete: "step 4's export button is now under Reports, not Billing". A step that went as written gets no note.
- **Never invent approvals.** If the flow says the user checks something, the run does not proceed on your judgment of it.

### Checkpoints

At a `[confirm]` step, do it, then stop and show **what will actually happen next**, not the step's wording: the recipients, the amount, the text itself, the target. When one checkpoint releases several outward steps, number them. Close with the reply contract:

```
About to: 1. email the invoice to billing@acme.com (text above) · 2. log it in the ledger as $4,200
Reply "go", or say what to change.
```

- `go` does exactly what was shown, every numbered item included. It is the only shortcut word.
- Anything else is plain English ("don't log 2 yet", "CC finance"), read for intent; items it does not mention stay as proposed. **An adjustment that changes what goes out is shown again for a fresh `go`** — nobody can take back a send they never saw. One that does not is echoed in one line in the same message as the work.
- Every adjustment is noted: `TASKS note <id> --at "<step>" "<what changed>"`. It is a departure from the flow, and the tweak pass reads it.
- After you perform the irreversible act, show the result — that is the check. A `[user]` step that performs it needs none: their doing it is the check.

### Parking an open question

A run can reach a call that is not yours to make — something with money, other people, or a commitment behind it. You are talking to someone, so **ask**. Parking is for the question they have seen and chosen not to answer yet: they want to check with someone, they do not have the figure, they want to sleep on it.

Record it rather than leaving it in the chat, which does not survive the session:

```
TASKS update <id> --needs decision --append "Question: <the call, the options, what is already known>"
```

**The status stays `doing`** and the assignee stays yours — the run is open, just blocked, and the board shows it as `⚑needs-decision` so it reads as paused rather than active. Do not send it back to `backlog`; that would throw away the fact that a run is half-done. Say plainly that it is parked, what unblocks it, and that `/ops decide <id>` answers it and `/ops run <id>` picks the run back up.

The edge case is nobody being there to ask at all — a session ending mid-run, or a run driven asynchronously. Same mechanism. Either way, never park a question to avoid asking one.

### Pausing the run

A run can stop partway and be picked up in a later session, or on another machine. **Only on the user's explicit call**: by default nothing is recorded, so a run that finishes in one sitting carries no pause line and task bodies stay light. Being stuck is not a pause — that is a question to ask, or the parked question above.

```
TASKS pause <id> --at "<step>" --record "<what exists so far, and where it lives>"
```

`--at` is the handle the next session resumes from: the numbered step when the flow has them (`step 4`), the step's own text when it does not, and what was last done for a flow-less run. `--record` is what the run has produced — enough that someone else carries on rather than repeating it — and what it has deliberately not done yet.

**The status stays `doing`** and the assignee stays yours: the run is open, just not being worked. A paused run and an active one look alike on the board, which is why the record has to say plainly what was done and what was not. Tell the user that `/ops run <id>` picks it back up.

**Where the artifacts live decides whether the pause works.** Anything a later step needs has to be somewhere the next session can reach — the repo, a shared drive, the ticket — not a temp path on this machine. For something too large or too private to commit (a recording, a scan, a screenshot set), ask the user where it should go rather than choosing, and prefer somewhere outside the repo. Either way name both the location and the machine it is on in the record, so a resumer elsewhere knows what it is looking for and whose machine holds it.

## 4. Running with no flow

The procedure gets written as you go, in chunks the user verifies.

Each round: **you propose the next chunk** — a handful of steps that can be done together, ending where a human should look. Show it as a short list and say what verifying it will look like. The user accepts (`go`), edits, or replaces it with their own steps; do not ask them to choose who proposes. An outward or hard-to-undo step inside a chunk is a checkpoint of its own, shown and gated as in *Checkpoints* above. Then do that chunk, show the result, and let them verify before the next round.

Write as you go: after each verified chunk, `TASKS note <id> --at "chunk <n>" "<what was actually done>"`, in enough detail that someone else could repeat it. That accumulating text is the draft of a future flow, so keep it procedural — steps and inputs, not narration.

Stop when the aim is met, not when you run out of ideas. Then section 5 — or, if the user calls a halt partway, *Pausing the run* above, citing the last verified chunk in place of a step number.

## 5. Closing

1. **The final check, always.** Whatever the flow already had the user verify, end with one overall question: here is what was done, does this meet the task's aim? Show the outcome, not a transcript. If they say no, keep going — the run is not over.
2. **Record and close**: `TASKS ran <id> --flow <name[,name]> --record "<inputs; deviations>"`. One call: it stamps the flows followed, appends `Ran (<date>): …` to the task, and closes it — or, for a recurring task, re-arms it to `backlog` and prints the next due date. Keep the record to a sentence or two: what it was given, and where it went differently — the task's `Note (<date>): …` lines are where the deviations come from. When a flow was followed exactly, say so — that is a useful fact, not an empty one. Omit `--flow` only when no flow was followed at all.
3. Report the close, and the next due date if one was printed.

## 6. After the task is closed

These are offers, and they come **after** the close so nothing holds up the user's work. Skip any that don't apply, and drop them all if the user is done for the day.

- **Tweak the flows that ran.** Re-read each one against what actually happened — the task's `Note:` lines first, and any the user remembers now, noted on the closed task before you propose the edit. A step whose wording misled you, a missing input, an ordering that fought the real work — fix it now while the run is fresh: propose the specific edit and, on their go-ahead, `TASKS flow update <name> --append "…"` or `--desc`/`--inputs`. Small fixes only. Anything structural is `/ops flow edit <name>`, and a flow that keeps needing edits is a signal for `/ops meta`.
- **No flow was followed** → offer to keep this run as one: `/ops flow create from <id>` (`flows/flow-create.md`), which reads the run's `Note:` lines.
- **Several flows were chained** → if that chain is likely to recur, offer a flow that composes them (`uses`), rather than letting each run rediscover the order.
- **Nothing is worth changing** → say nothing. Most runs of a settled flow change nothing, and reflexive edits are how a good flow rots.
