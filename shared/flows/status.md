# /<skill> status — your plate

`/<skill>` is the skill in use. One board holds both task types, so status covers your tasks of both.

`TASKS list --assignee <me>`, then the PR state refresh below for any with a PR. Report, in order:

1. **In flight, yours to move.** Dev tasks with their PR state — call out **changes requested** (your move to make) and your own **drafts**, which nobody else will move: each is yours to finish, review (`/dev review <id>`) and `ready`. Ops runs `doing` with no `waiting:` marker — each yours to finish and close.
2. **Waiting on someone else**: `doing` tasks with a `waiting:` marker — on whom and by when, overdue ones called out; nothing to do until the reply is in.
3. **Waiting on you**: `TASKS list --needs decision` and `--status proposed`. Status only surfaces them; `/<skill> decide <id>` answers either type (`shared/flows/decide.md`).
4. **Due**: `TASKS recur list --due`. Only when there is one: a line reading `routine … did not start` or `paused`, with who can reach that routine's source.
5. **Unscheduled recurring work**, only when there is one: a recurring task whose clock runs (not `proposed`, `shelved` or `not-planned`) with no `routine` and no `Decision: no routine` line (`TASKS list --json`) gets the offer to start it on its own (`shared/flows/schedule.md` *The offer*).

**If your list is empty** (`(no matching tasks)`), don't stop at "nothing assigned" — that's a dead end when the board has work. Add the unassigned backlog count, one or two candidates of this skill's type worth picking (`TASKS list --type <dev|ops> --status backlog`, unblocked ones first), and the command that starts one (SKILL.md *Running a task*) or `/<skill> pick <id>` to claim it for later. If the board is genuinely empty too, say so and point at `/<skill> add <task-or-goal>`.

## PR state refresh

Run during board, status and review, for dev tasks in `draft` or `review` with a `pr`, when gh is available: `TASKS pr <id> view --json` (read `state`, `mergedAt`, `reviewDecision`; over the REST fallback `reviewDecision` is only the latest approve / request-changes per reviewer, not branch-protection status).

- `draft` → not on the integrator's queue. If it is **yours**, it is your move, and it belongs in your own review inbox: review it (`/dev review <id>`) or keep building (`/dev <id>`), then `TASKS ready <id>` when you want eyes on it. A draft an unattended run shipped as you is yours the same way. Another human's draft is never listed — not as a review item, not as information — and is never yours to `ready`.
- Merged → `TASKS land <id>` (marks done, cleans local worktree/branch; safe if already done). If land/cleanup aborts, surface the script error — do not mark done by hand.
- `CHANGES_REQUESTED` → the assignee's move; surface it (`/dev <id>` resumes it).
- `APPROVED` and unmerged → if `TASKS whoami --role` prints `integrator`, ready to land via `/dev review <id>`; otherwise waiting on the integrator.
- Closed unmerged → flag it; only prompt for a decision if the current user is the assignee or integrator.
