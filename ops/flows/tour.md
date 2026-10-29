# /ops tour — the key concepts, one card at a time

A walk-through for someone new to ops. Never start it on your own: it runs only when the user asks (`/ops tour`, or yes to the offer at the end of init).

## How to give it

- **One card per message.** Say the card's sentence in your own words, then show it on their board: run the card's read-only command and quote a line or two of real output (a real task id, a real name). If that comes back empty, say what will show up there once there is work. Never write to the board during the tour.
- End each card with `next, or stop?`. Any reply but stop moves on; a question is answered first, then the tour continues. Stop ends it on the spot, with the last line below.
- No board here yet: give the cards anyway, pointers as "once it is set up, `<command>` shows this", and end on the init offer instead of add.
- Any term the tour has not introduced yet — in a card or in output you quote — gets a one-line aside where it first comes up. A newcomer should never meet a word they cannot place.
- Keep each card short. The tour is the map, not the manual — details are learned when a command first needs them.

## Shared core (same five cards as `/dev tour`)

1. **The board.** One board lives inside the repo: every task is a small file under `.tasks/`, synced through git, so every contributor on any machine sees the same thing. Its header names the current iteration: a stretch of work that is closed out and archived together, after which the next one starts. Being git history, the board is exactly as private as the repo and every clone keeps it for good: identifiers such as a username or an account number belong on it, but passwords, one-time codes, API keys and session tokens never do — sign-in stays in the environment that uses it (a browser session, the keychain). — See it: suggest `./board`, run in their own terminal rather than in the agent session (it is a live view driven by keys); here, show `TASKS board`, the same board as a snapshot.
2. **Tasks and statuses.** A task is a few sentences of aim, not a spec, and it moves `proposed` → `backlog` → `planned` → `doing` → `done`, with `later`, `shelved` and `not-planned` off to the side. — See it: `TASKS show <id>` on one of theirs.
3. **Identity.** Each checkout knows who you are on this board, so the tasks you pick and run carry your name, and roles attach to it — the integrator, for one, is whoever merges finished work and closes iterations. — See it: `TASKS whoami`.
4. **The script writes the board.** Nobody hand-edits `.tasks/`: every change goes through the skill's script, which commits and pushes it on the board's branch — that is what keeps a shared board free of conflicts. — See it: `git log --oneline` on the board's branch, one commit per change.
5. **Agents draft, you decide.** Reviews, design questions, approvals and closing calls always come back to a person; an agent surfaces them and waits. Most come up right in the session, while an agent is building or reviewing with you; the list commands catch the ones left on the board, mostly by agents working unattended. — See it: `TASKS list --needs decision` and `TASKS list --status proposed`.

## Ops cards

6. **Flows.** A flow is a written, named procedure — how you close the month, onboard a client — kept in `.flows/` and shared like the board, and it outlives the tasks that run it. — See it: `TASKS flow list`.
7. **Runs and checkpoints.** A run is one pass of a flow against a task: each step is marked `[agent]`, `[user]` or `[confirm]`, the run stops for your `go` before anything goes out, and it closes with a record of what it was given and what went differently. — See it: `TASKS flow runs <name>`, or the `Ran:` line on a done task.
8. **The playbook is written by using it.** No flow yet is the normal start: the run goes a chunk at a time, notes what you actually did, and can be kept as a flow at the end; every later run is a chance to sharpen it. — See it: `f` in `./board` opens the flows pane, each flow with its run history.
9. **Sequences: when work changes hands.** A flow can split into sequences, each saying where it runs (an environment) and who usually does it (an agent), so a run knows when to hand a stretch to another machine or agent. A new place is described inline in the flow until a run has tested what it really needs; then it is registered by name for every flow to use. — See it: `TASKS env list` and `TASKS agent list`.

## Ending

After the last card (or a stop), one line: `/ops add <task-or-goal>` files the first piece of work and `/ops run <id>` runs it, or `/ops help` has the full map. If `/dev` is among your available skills too, add one line that `/dev tour` covers the code side on the same board.
