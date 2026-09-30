# /ops add <task-or-goal> — sit with the ask, then file

Covers `/ops add <task-or-goal>` and freeform new work. One entry point; sit with the ask, then file.

## Premise (before filing)

Sit with the ask before filing (SKILL.md *User specs are one guess*). What is the user actually trying to get done? Does what they described achieve it? If a flow already covers this, say so — the task may just be "run `<flow-name>`". If you need context to judge, ask them; there is no codebase to read your way to an answer here, and guessing at someone's process is worse than one question. If you see a better approach, say so — the outcome beats the wording. Real concerns only; do not invent nits. Push-back is conversation; if you raised one, wait for a direction. The task body is only what the user accepted.

## Is it an ops task?

Ops tasks change the world: send, file, publish, order, schedule, review with human eyes, decide. If doing this means editing the project's code, it is a dev task — say so and stop filing it here. `/dev add <task-or-goal>` is where it goes if that skill is installed; if it is not, say plainly that this skill does not do code work.

The line is what the work *does*, not who asks. "Update the pricing page copy" is code if the page lives in this repo. "Email the new prices to every customer" is ops, even though both came from one decision — those are two tasks.

## One task, or several?

Decide; do not ask the user to pick a shape.

- **One task** when it is one sitting with a clear aim, even a long one. Prefer this in a grey area — a run decomposes what it finds, and detail is cheaper to add at run time than to invent now.
- **Several** when distinct pieces must each be done and checked separately, or when they will run on different days. File them as siblings, with `--deps` where one genuinely has to happen after another. Ordering is ordinary in ops work — most procedures have a real sequence — so wire the deps you actually see rather than hunting for reasons to leave them out.
- **An umbrella** when the user states a goal that several of those tasks add up to: file the children first, then the parent with `--kind umbrella --deps <child-ids>` and the goal in its body. Closing it later is its own judgment (SKILL.md *Umbrella close*), not a side effect of the children finishing.

Say which you did, once ("filed as one task" / "filed three, the third waits on the second").

## Filing

1. Draft a title and a one-to-three sentence description from what the user said. Do not add constraints, approvals, or non-goals they did not state — a future agent will treat the task file as approved by them. No area: ops tasks carry none.
2. **Check the board first**: `TASKS related "<title + description>"`.
   - Substantially the same task already exists → say so and propose amending it (`TASKS update <id> …`) rather than filing a duplicate. The user decides.
   - A near-identical task that is already `done` is usually not a duplicate — recurring work legitimately comes round again. Check whether it should be `--kind recurring` instead (SKILL.md *Recurring*): offer, and let the user choose the cadence. Never set one on your own.
   - Otherwise judge the neighbours for **dependencies in both directions** — must something else happen first (`--deps`), or does an existing task now wait on this one (update *its* deps)?
   - A neighbour marked `☂` is an umbrella that may already cover this: propose the new task as its child (`TASKS update <umbrella> --deps <existing+new>`).
3. `TASKS add --title "…" --type ops [--deps 1,2] [--desc "…"]`, then show the task as recorded (the script prints it). `--type ops` is not optional — without it the task is filed as code work.
4. Offer the obvious next step: `/ops run <id>` if it is ready to do now, nothing if it is future work.

Coming from `/ops run <description>` (no matching task): file exactly as above, then continue straight into the run — the user already said to do it, so don't ask again.
