# /ops iteration — show, close, start the next

An iteration is one stretch of work on the board plus the archive it leaves behind. Task ids restart each iteration, so a task from an earlier one is written `<n>/T<id>`. Most boards keep every iteration on one branch and start the next in place; a board with a `parent_branch` merges each one into that parent instead (below). A board that never closes is perfectly fine — closing is for when the live board has more finished work on it than current work.

**Closing loses nothing.** Every task file is copied verbatim into `.tasks/archive/<n>-<slug>/`, so the run records on them stay readable and `TASKS flow runs <name>` keeps finding them. Flows are not touched at all: the playbook outlives iterations.

## `/ops iteration` — show

`TASKS iteration` prints the project, the iteration's number and display name, when it started, and how much is done.

`TASKS config iteration_name <name>` and `config iteration_started <date>` adjust the label and start date; `config iteration <n>` renumbers the live iteration, and is refused if that number already has an archive. All three are refused once the iteration is closed but not yet rolled, since the close wrote that number into `log.md`.

## `/ops iteration close`

1. **Confirm intent, and deal with what is unfinished.** Ask per task: run it now, park it (`--status later` — intended, not this stretch), carry it over (it moves into the next iteration with its status and record intact, run in flight included; only its id changes), or drop it (`--status not-planned --reason "<why>"`, or delete — the user picks). Recurring tasks sitting at rest do not block and are carried automatically, cadence and last-run date intact. A run actually in flight blocks the close unless it is carried: finish it or carry it, since leaving it behind with `--force` loses the record of what was done.
2. **An unfinished umbrella deserves a pause.** It means the goal it names was not met. If its children are all done, it needs its verification pass first (SKILL.md *Umbrella close*), which is a judgment, not a status flip.
3. `TASKS iteration-close`. When the user chose to carry the unfinished tasks over, add `--carry`: it takes every unfinished task, so run, park, or drop the ones that should not come along first. `--force` instead logs them as unfinished and leaves them behind — only after the user has accepted that list; genuinely abandoned work should be `not-planned` first, and parked work `later`. This copies every task into the archive and indexes them in `.tasks/log.md`, one line each with its `Ran:` records underneath, then clears the live board.
4. Start the next one straight away (below), unless the user wants to leave the board empty for a while.

## `/ops iteration new`

`TASKS iteration-new [--name <name>] [--iteration N] [--iteration-started <date>]`. Ask for a display name first; unnamed is allowed, but a name is what makes the archive readable later. The script refuses until the close has run.

The new board starts empty except for what carries over on its own: tasks closed with `--carry` (status, assignee and record intact), tasks parked as `later`, and recurring tasks. All are renumbered 1..N in their old order, and each gets a `carried from <n>/T<id>` note; links to tasks that did not come back are dropped. Do not re-add those by hand. Anything left behind by `--force` is re-filed through `flows/add.md`, reading it from `.tasks/archive/<n>-<slug>/`.

## A board with a parent branch

Most ops boards live on one branch and roll in place, as above. A board that has a `parent_branch` works differently: each iteration lives on its own branch and is merged into the parent when it closes. `TASKS iteration` shows whether this board has one.

There is one extra step, and it is one command:

1. `TASKS iteration-close`, exactly as above.
2. `TASKS iteration-land` — opens a pull request from the iteration branch into the parent and merges it with a merge commit. It needs `gh` installed and authenticated (`gh auth status`); that is the only place this skill touches GitHub. It is idempotent: run it again after a merge and it says so rather than opening a second one. The agent harness may refuse it outright, since it merges; that is not a script error, and the fix is to allow the command wherever this harness configures permissions, not to merge by hand. Nobody has to review it — the diff is the archive the close just wrote — but if the team gates that branch, `--create-only` opens the pull request and stops so a person can merge it.
3. `TASKS iteration-new <branch> [--name <name>]` — the next iteration starts on a new branch off the parent. The script refuses until the merge in step 2 has actually landed, because the new board branches from the parent and would otherwise be missing this iteration's archive.

Then tell the user to switch their checkout: `git checkout <branch>`.

Setting a board up this way is `TASKS config parent_branch <branch>`, and it is a real commitment — every future iteration ends in a pull request. A board with no parent needs no GitHub at all, so do not propose one unasked.
