# Flows — what a flow says, and following one

`/<skill>` is the skill in use. A flow is a written procedure, kept on the board by name (SKILL.md *State layout*). An ops run follows its task's flows; a dev task that names one has it followed while it is built. Either way the flow is the procedure of record for that work: read it (`TASKS flow show <name>`, and every flow in its `uses`) before the first step, and follow it as written — it is not yours to silently improve mid-way.

**Composition.** A flow may follow other flows; those go in its `uses` list and appear in its body as the step that runs them, with the inputs that step names. Keep each flow one coherent procedure — when work chains several flows by hand, that is the signal to offer a new flow that composes them, not a reason to grow one flow until it covers everything.

**Description quality matters.** The one-line `description` is what a future agent reads to pick the right flow for a task, exactly as a skill description is. Write what it is for and when to use it, not how it works.

**Sequences.** A flow body may group its steps into sequences: a heading, then labeled lines before its steps — `Environment:` (where it runs, an environment name), `Agent:` (optional: who usually does it, an agent name), `Needs:` (the capabilities it requires, in prose), `Inputs:` (what it takes) and `Returns:` (what it hands back) — plaintext, all of them. Step numbers continue across sequences, so a step's number stays its handle for the whole flow. A sequence with no `Environment:` or `Agent:` is the runner's, in this project — and a body with no headings is one such sequence, so a flow written before sequences needs no change. `Agent: runner` and `Environment: project` say that default out loud; `any` means no preference. `Environment: inline` describes a place the registry does not hold yet, right in the sequence: an `Expects:` line (what the place must provide) and an `Accessors:` line (the contributors who can reach it). A place starts inline until a run has tested what it really needs, then gets registered. `flow create` and `flow update` warn on an `Agent:` or `Environment:` name the board's registries do not hold, on a former name (saying what it now points at), on an inline sequence with no `Expects:`, and on an `Accessors:` handle that is not a board contributor.

A sequence naming another environment or agent, or needing a capability this session lacks, is not done here: before its first step, say what it needs and should return, and settle with the user how it gets done — for an inline one, quoting its `Expects:` and `Accessors:`. Handed to an agent the registry does not hold (`TASKS agent list`) → offer `TASKS agent add <name> --accessors "<who reached it>" --desc "<who it is>"`.

**Step marks.** Each numbered step carries a tag right after its number: `3. [confirm] Draft the invoice for {client}`, then `4. [agent] Send it`.

- `[agent]` — you do it and report what came of it. An unmarked step is the agent's.
- `[user]` — theirs: ask, wait, never do it for them.
- `[confirm]` — you do it, then stop: show what it produced and wait for the user's `go` before the work goes on. This is the load-bearing mark: it goes on the step right **before** anything outward or hard to undo — sending, paying, publishing, deleting, committing someone to something — the step that prepares it (the draft, the amount, the list of files), so the user signs off on exactly what will go out. When you then perform the irreversible act, show its result; when the user performs it (`[user]`), their doing it *is* the check, and no step follows it to re-verify.
- `[external]` — a third party does it (an office answers, a vendor ships) while the work waits, often for days. Reaching one stops the work: `TASKS wait <id> --on "<who>" --by YYYY-MM-DD --at "<step>" --record "<what was sent, and where>"`, the expected-by date their stated turnaround or the user's, never invented. `--record` is what they have (a reference number, the submission, where a copy lives), so the reply can be matched to it; a moved date is the same call with the new `--by`. A wait the flow did not mark is the same call plus a note (`TASKS note <id> --at "<step>" "waits on <who>; no [external] mark"`), so the fix to the flow adds the mark. The task stays `doing`, flagged `📨waiting <who> by <date>`. The skill's attended run of the task (SKILL.md *Running a task*) resumes it once the reply is in: `TASKS wait <id> --clear`, then on from the next step. The step that sends them what they act on is outward, so it is gated as any other.

**The floor:** an outward or hard-to-undo step with no `[confirm]` step right before it (and not itself `[user]`) is gated anyway — you stop before it and show what it will do — and noted (`TASKS note <id> --at "<step>" "no confirm before it, gated"`), so the fix to the flow proposes the `[confirm]` step for real. Read-only and trivially reversible steps never stop for a checkpoint.

**Checkpoints.** At a `[confirm]` step or the floor, show **what will actually happen next**, not the step's wording: the recipients, the amount, the text itself, the target. Number the outward steps when one checkpoint releases several. Close with the reply contract:

```
About to: 1. email the invoice to billing@acme.com (text above) · 2. log it in the ledger as $4,200
Reply "go", or say what to change.
```

- `go` does exactly what was shown, every numbered item included. It is the only shortcut word.
- Anything else is plain English ("don't log 2 yet", "CC finance"), read for intent; items it does not mention stay as proposed. **An adjustment that changes what goes out is shown again for a fresh `go`**; one that does not is echoed in one line in the same message as the work.

With nobody there to say `go` (an unattended run), a checkpoint is never passed on your own judgment: it goes on the board as a question (`shared/routes/unattended.md`).

**A step done through a screen** (a web app, a desktop program, an OS dialog) is written and done as `shared/routes/gui.md` says.

**Departures** — a step gated for lack of a `[confirm]`, every adjustment at a checkpoint, a step the user did their own way or one inserted mid-way, and anywhere reality departs from the flow (a step no longer applies, a system moved, something is missing: do what makes sense, asking if it is more than trivial, and say so) — are noted when they happen: `TASKS note <id> --at "<step>" "<what>"`, concrete ("step 4's export button is now under Reports, not Billing"). Steps that went as written get nothing. The notes feed the work's outcome record (SKILL.md *Running a task*), and after it the user is offered the fix to the flow (`TASKS flow update <name> --append "…"`, on their go-ahead).
