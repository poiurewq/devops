# /ops meta — pressure the playbook and the board

`/ops board` shows what is outstanding. `/ops meta` presses on whether the playbook and the board still make sense. Not a namespace: no subcommands. An optional noun is a **focus** (one flow, one task, one area of the work), not a child verb. Freeform "is our playbook any good?" routes here.

## Sitting

Read `TASKS flow list --all`, `TASKS board`, and `TASKS flow runs <name>` for the flows that look interesting. Everything below is derived from the runs recorded on tasks — there are no separate statistics, so the records are the evidence. If the user named a focus, start there.

Follow attention. Do not open with a tour of axes. Open with whatever looks wrong, and say why you think so.

Things a sitting may notice — not a checklist:

- **A flow nobody runs.** `TASKS flow runs <name>` is empty, or the last run is old. Either the work stopped, the flow is not being found, or its description does not say what it is for. Ask which; the fix for the third is an edit, not a retirement.
- **A flow that deviates every time.** Recent `Ran:` records keep noting the same departure. The flow is describing a procedure nobody follows any more — propose the specific edit that makes it true again.
- **An unguarded outward step.** A step that sends, pays, publishes, or deletes with no `[confirm]` step before it and not itself `[user]` — or `Note:` lines saying a run gated one. Propose the `[confirm]` step. The reverse too: a `[confirm]` whose next step is read-only, or a check after a step the user performed, is ceremony; propose dropping it.
- **A description that no longer picks it.** Read each description as if choosing between flows for a task. Vague ones ("handles the monthly stuff") cause the wrong flow to be picked, and the symptom shows up as deviations elsewhere.
- **Two flows too alike.** Near-identical names or descriptions mean a future run will pick between them by accident. Merge, or sharpen both descriptions so the boundary is obvious.
- **A chain that keeps recurring.** Read the `Ran:` records across tasks rather than one flow's history: when the same flows appear together, in the same order, run after run, that sequence is a procedure nobody has written down. Propose one flow that `uses` them in that order, and say how many runs you are going by — twice is a coincidence, five times is a pattern. A chain whose order varies run to run is not one flow; say that instead of inventing an order. This is the mirror of the split at run-preflight (`flows/run.md`): that one breaks up a task carrying several unrelated procedures, this one composes procedures that never travel apart.
- **A flow doing too much.** One procedure with unrelated halves, or a body with a branch at the top ("if it's a renewal, skip to 7"). Propose the split.
- **Tasks that never run.** Ops backlog piling up untouched: either it is not really wanted (`not-planned`, with a reason) or it is waiting on something nobody named.
- **Recurring work that is always late.** A cadence that never matches reality is worse than none — propose a cadence that matches what the records actually show, and let the user decide.
- **An umbrella whose children don't add up to its goal.** Name the gap. Never propose closing it (SKILL.md *Umbrella close*) — when one looks complete, say the goal check is due and point at it.

Speak in the user's frame. Propose concrete edits — a description rewrite, a split, a merge, a retire, a cadence change, a task to file. They say apply, or keep talking. Mutations only on an explicit go-ahead, and through `TASKS`.

## What this is not

Not a run: nothing here executes a procedure. Not a substitute for the tweak pass at the end of a run — that catches the small things while the run is fresh, and this catches the patterns across runs that no single run can see.
