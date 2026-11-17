## Not planned and shelved

Two ways to set a task of either type aside, each a human decision: agents propose them, and an unattended run never sets one. When the user wants a task gone, ask which they mean — `not-planned`, `shelved`, or `delete` — rather than choosing for them.

- `not-planned` = decided against, kept with its reason so the idea isn't re-litigated: `TASKS update <id> --status not-planned --reason "<why>"`, the reason required and appended to the body as `Not planned (<date>):`. It also retires a recurring task for good. `delete` (`TASKS delete <id>`, after confirming) erases instead — for something filed in error, a duplicate, noise.
- `shelved` = set aside for now — not this iteration, or not needed at present, but it may matter again; unlike `not-planned` it is not decided against. `TASKS update <id> --status shelved --reason "<why>"` (or `add --status shelved --reason "<why>"`), the reason required and appended as `Shelved (<date>):`. It holds no area lock, folds to its own `Shelved` count on the board, and `iteration-new` carries it onto the next board still shelved, with a `carried from <n>/T<id>` note — a recurring one too, since shelving pauses it.
- `later` is retired: `--status later` is refused with a pointer to `shelved`, and a task file still saying `later` reads as shelved.

Ask for a reason in the user's own words; if the answer is thin, ask once what changed. Neither is worked (claim, ship, land and a run all refuse it) or picked by `next`, and none blocks an iteration close (logged `[not planned]`, `[shelved]`). Revive with `--status backlog` or `/{{skill}} pick <id>`; a recorded reason stays as history.

A task with a live branch or PR cannot move to `shelved` or `not-planned`: `update` refuses, because the branch would outlive the move and the next iteration would orphan the PR. Decide the PR's fate with the user first (land it, close it, or keep it open), run `TASKS cleanup <id>` to drop its worktree (it keeps the branch and PR), then clear both in the same call (`--branch "" --pr ""`); the old values are recorded in the body as `Cleared on moving to <status> (<date>): …` and nothing is deleted.
