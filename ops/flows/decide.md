# /ops decide [id] — the questions waiting on a person

Two kinds of pending judgment sit on the board: **open questions** on tasks (`needs: decision`) and **proposed tasks** awaiting approval. You draft; the user decides. Never resolve a question or accept a proposal without an explicit go-ahead in this conversation.

**Plain language first.** For every question and proposal — in the list and when going into one — open with one plain sentence of what the task is for, taken from its body. Not a recap of how it got there.

## `/ops decide` (no id) — show what is waiting

1. **Open questions**: `TASKS list --needs decision` — each with one plain sentence of purpose, then the question itself in one line.
2. **Proposed tasks**: `TASKS list --status proposed` — one plain sentence of purpose each, grouped by goal or umbrella when their bodies say so.

Let the user pick what to handle, and batch small ones into a single sitting rather than walking them through a queue. If nothing is waiting, say so plainly and point at whatever is actually next (`/ops status`).

## Deciding an open question

1. `TASKS show <id>` — the body carries the question, the options, and whatever the person who parked it recommended. Present it as one decision, not a discussion of everything the task touches.
2. On the user's call, record it: `TASKS update <id> --needs "" --append "Decision: <choice + one-line why>"`. The decision stays on the task, so the run that follows it does not re-open the question.
3. **Then put it back where it belongs.** A question parked mid-run is still `doing` — clear the flag and leave the status alone, so the half-finished run keeps its assignee and `/ops run <id>` resumes it. Only a question parked on work that never started goes back to the pool: add `--status backlog`.
4. If the answer is "don't do this at all", that is a not-planned outcome instead: `TASKS update <id> --needs "" --status not-planned --reason "<the user's why>"` — whether or not a run had started.
5. If the user wants it done now, `/ops run <id>` follows straight on — the decision is already recorded.

## Adjudicating proposed tasks

1. Walk them with the user, grouped by goal: for each, one plain sentence of purpose, then keep, change, or drop.
2. **Keep** → `TASKS update <id> --status backlog`, plus any edits they asked for. Intended but not this stretch of work → `--status later`. If the proposal belongs under a goal already on the board, wire it up: `TASKS update <umbrella> --deps <existing+new>`.
3. **Drop** → offer both and let them pick: `TASKS update <id> --status not-planned --reason "<why>"` keeps the record so the idea is not re-proposed, and `TASKS delete <id>` erases something filed in error.

## How this inbox fills

Questions land here when a run parks one — the mechanics are in `flows/run.md`. Two things worth holding on to from this side: someone is almost always there to ask, so parking is for a question they have declined to answer now, not a substitute for asking one; and a question parked mid-run is a paused run, not an abandoned one, which is why resolving it leaves the status alone.
