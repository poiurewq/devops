# Unattended — how an ops task runs with nobody there

The ops part of `shared/routes/unattended.md`, which holds the mode — identity, provenance, the marker, the hard limits, `next unattended`'s candidates, the report and its one notification; read that first. `routes/run.md` still governs, with the overrides below.

**No flow, no run**: a task with no flow — none on the task, and none the flow pick in `routes/run.md` makes obvious — is reported and left alone, named or selected: a run without a flow is verified by a person as it goes (`routes/run.md` section 4). `next unattended` also passes over rehearsals (`rehearsal: true`): a rehearsal is the user's own pass through a flow.

**The marker**: start the run with run.md's start call plus `--unattended <model-id>` (`TASKS update <id> --status doing --assignee <owner> --flow <name[,name]> --unattended <model-id>`). The script refuses it while any run's marker is set, one with your model id included. `ran` clears it by leaving `doing`; every stop below hands it back with `--unattended ""`.

## A run goes to its first stop

Each run follows `routes/run.md` until it ends or reaches something only a person can settle. There it **parks** — `TASKS update <id> --needs decision --unattended "" --append "Question: [step <n>] … (unattended, <model-id>)"`, `<n>` being the step `/ops run <id>` carries on from — and the run is over for this session. A run already started stays `doing` with `<owner>` as assignee; one parked in preflight stays where it was. A dev run parks the same way, its branch pushed by `TASKS pause` (`/dev`'s `routes/unattended-run.md`, step 5); an ops run's work so far is out in the world already, and the task records where it got to, so a person picks it up from there.

- **Preflight** — anything run.md would ask before the first step: no `Intent:` line, an input with no value and no hint to derive it, an unfinished dep, a flow choice that is not obvious, a split into three or more flows, an unregistered environment. Park the question in preflight's words, tagged `[preflight]` in place of the step.
- **A checkpoint** — a `[confirm]` step, or the floor before an outward step — parks with its full `About to:` block, as `routes/run.md` *Checkpoints* (*Nobody there to say `go`*) writes it.
- **A `[user]` step** parks naming what the user has to do.
- **An `[external]` step** waits instead: `TASKS wait` as `routes/run.md` *Waiting on a third party*, with `--by` from the flow or the third party's stated turnaround, then `TASKS update <id> --unattended ""`. No date given → park the question of when, never invent one.
- **A handoff** this session cannot do itself parks with the sequence, what it needs, and who could take it (section 2 *Check the sequences*); it is not passed on or briefed without a person's say.
- **Closing**: a clean run (`routes/run.md` *Closing*) closes with `TASKS ran` as usual. Any other run parks the closing question — the outcome, its evidence, and where it falls short of the `Intent:` — instead of asking.
- Section 6's offers are skipped; the run's notes are already on the task for whoever reads it next.

A parked run whose question now has an answer is never resumed unattended: it is resumed attended, with `/ops run <id>`.

## Report

One line per run: closed (with the next due date if `ran` printed one), parked (the question, and that `/ops decide <id>` answers it, then `/ops run <id>` resumes it), or waiting (on whom, by when).
