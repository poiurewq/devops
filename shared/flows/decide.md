# /<skill> decide [id] — the questions waiting on a person

`/<skill>` is the skill in use; one board holds both task types, so either skill decides for either. Two kinds of pending judgment sit on the board: **open questions** on tasks (`needs: decision`) and **proposed tasks** awaiting approval. You draft; the user decides. Never resolve a question or accept a proposal without an explicit go-ahead in this conversation. `/dev review` lists them in its inbox too, and hands each here.

**Plain language first.** For every question and proposal — in the list and when going into one — open with one plain sentence of what the task is for, taken from its body. Not a recap of how it got there.

## `/<skill> decide` (no id) — show what is waiting

1. **Open questions**: `TASKS list --needs decision` — each with one plain sentence of purpose, then the question itself in one line.
2. **Proposed tasks**: `TASKS list --status proposed` — one plain sentence of purpose each, grouped by goal or umbrella when their bodies say so.

Let the user pick what to handle, and batch small ones into a single sitting rather than walking them through a queue. If nothing is waiting, say so plainly and point at whatever is actually next (`/<skill> status`).

## Deciding an open question

1. `TASKS show <id>` — the body carries the question, the options, and whatever the agent or person who parked it recommended. Present it as one decision, not a discussion of everything the task touches.
2. On the user's call, record it: `TASKS update <id> --needs "" --append "Decision: <choice + one-line why>"`. A decision that assigns a dev task an area also sets it on that update (`--area`, after `TASKS area set` if the name is new). The decision stays on the task, so the work that follows it does not re-open the question.
3. **Leave the status alone.** A question parked mid-work is still `doing`, so the half-finished run keeps its assignee and resumes from where it parked; one parked before the work started (an ops `[preflight]` question, a dev fork whose branch was given up) left the task at rest, so it is picked as usual; a question on a `proposed` task leaves it proposed — approving it is the next section's call.
4. If the answer is "don't do this at all", that is a not-planned outcome instead: `TASKS update <id> --needs "" --status not-planned --reason "<the user's why>"` — whether or not work had started.
5. If the user wants it done now, run it straight on with the command for its type (SKILL.md *Running a task* of that type's skill): `/dev <id>` for a dev task, `/ops run <id>` for an ops task — the decision is already recorded.

## Adjudicating proposed tasks

1. Walk them with the user, grouped by goal: for each, one plain sentence of purpose, then keep, change, or drop.
2. **Keep** (with any **change** they ask for) → `TASKS update <id> --status backlog`, plus those edits. Intended but not this stretch of work → `--status shelved --reason "<why>"`. If the proposal belongs under a goal already on the board, wire it up: `TASKS update <umbrella> --deps <existing+new>`. If it decomposes a parent task (its body says so), make that parent their umbrella: `TASKS update <parent> --kind umbrella --deps <accepted-ids>` (merged with its existing deps), noting the decomposition in its body (`--append`).
3. **Drop** → offer both and let them pick: `TASKS update <id> --status not-planned --reason "<why>"` keeps the record so the idea is not re-proposed, by an unattended run or an audit among others, and `TASKS delete <id>` erases something filed in error.

## How this inbox fills

Questions land here when work parks one: a run or an unattended run with nobody to ask, a scheduled run that reached the user, an implement fork. Proposals land here from unattended runs, audits and absorbs. Two things worth holding on to from this side: someone is almost always there to ask, so parking is for a question they have declined to answer now, not a substitute for asking one; and a question parked mid-work is a paused run, not an abandoned one, which is why resolving it leaves the status alone.
