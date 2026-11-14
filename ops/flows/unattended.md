# Unattended — a run with nobody there

Read when the invocation ends in the word `unattended`: `/ops run <id> unattended`, `/ops next unattended`, or an unattended routine's wake, which passes the word the same way. Unattended is chosen, never inferred: without the word a run is attended, whoever started it. It changes who is there, not what a run is — `flows/run.md` still governs, with the overrides below.

**Identity**: the run acts as the human who owns this machine's GitHub account. `TASKS whoami` prints the handle — call it `<owner>`, and assign as `<owner>`. If it errors, stop and report it: joining a board is a human step (`/ops init`), and an unattended run never registers a contributor. Which agent did the work is provenance, not identity: end every `Ran` record and every parked `Question:` it writes with `(unattended, <model-id>)` — `(unattended, <model-id>, routine <name>)` when a routine's wake started the run (`flows/wake.md`).

**Hard limits**: never resolve a `needs: decision` question, approve a `proposed` task, mark a task `not-planned`, `later` or `shelved`, delete one, file a recurring task or offer a schedule, create or edit a flow, rehearse one, or pause a run (a pause is the user's call). Never pass a checkpoint on your own judgment, and never fabricate a step's output. Anything that needs a person is put on the board as a question, never decided around.

**No flow, no run**: a task with no flow — none on the task, and none the flow pick in `flows/run.md` makes obvious — is reported and left alone, named or selected: a run without a flow is verified chunk by chunk by a person (`flows/run.md` section 4).

**The marker**: while this session is working a run, the task carries `unattended:<model-id>`, so nobody resumes into it. Start the run with run.md's start call plus `--unattended <model-id>` (`TASKS update <id> --status doing --assignee <owner> --flow <name[,name]> --unattended <model-id>`). The script refuses it while any run's marker is set, one with your model id included — report that and leave the task (under `next unattended`, select again). Every stop below that leaves the task `doing` hands it back with `--unattended ""`; `ran` clears it by leaving `doing`.

## A run goes to its first stop

Each run follows `flows/run.md` until it ends or reaches something only a person can settle. There it **parks** — `TASKS update <id> --needs decision --unattended "" --append "Question: [step <n>] … (unattended, <model-id>)"`, `<n>` being the step `/ops run <id>` carries on from — and the run is over for this session. A run already started stays `doing` with `<owner>` as assignee; one parked in preflight stays where it was.

- **Preflight** — anything run.md would ask before the first step: no `Intent:` line, an input with no value and no hint to derive it, an unfinished dep, a flow choice that is not obvious, a split into three or more flows, an unregistered environment. Park the question in preflight's words, tagged `[preflight]` in place of the step.
- **A checkpoint** — a `[confirm]` step, or the floor before an outward step — parks with its full `About to:` block, as `flows/run.md` *Checkpoints* (*Nobody there to say `go`*) writes it.
- **A `[user]` step** parks naming what the user has to do.
- **An `[external]` step** waits instead: `TASKS wait` as `flows/run.md` *Waiting on a third party*, with `--by` from the flow or the third party's stated turnaround, then `TASKS update <id> --unattended ""`. No date given → park the question of when, never invent one.
- **A handoff** this session cannot do itself parks with the sequence, what it needs, and who could take it (section 2 *Check the sequences*); it is not passed on or briefed without a person's say.
- **Closing**: a clean run (`flows/run.md` *Closing*) closes with `TASKS ran` as usual. Any other run parks the closing question — the outcome, its evidence, and where it falls short of the `Intent:` — instead of asking.
- Section 6's offers are skipped; the run's notes are already on the task for whoever reads it next.

## Resuming a parked run

A run whose parked question now has an answer — `doing`, assigned to `<owner>`, no `needs` flag, no `unattended:` marker, and a `Decision:` line after its latest `Question: [step <n>] …` (written by `/ops decide`) — carries on from step `<n>`, after taking the marker: `TASKS update <id> --unattended <model-id>` (refused → another run took it first; leave it). A `go` on a checkpoint does exactly what its `About to:` block shows. A decision that changes what goes out, or a payload that no longer matches the block when the run gets there, parks again with the new block for a fresh `go`. A `[preflight]` question left the task at rest, so once answered it is picked as an ordinary task (below), not resumed.

## `/ops next unattended` — one run

1. `TASKS whoami` (Identity above).
2. **Select**, in this order, and take the first:
   - a parked run with an answer (above), oldest first;
   - due recurring ops work (`TASKS recur list --due`), at rest, unassigned or `<owner>`'s, no `needs`;
   - `backlog` or `planned` ops tasks, unassigned or `<owner>`'s, no `needs`, every dep `done` — `<owner>`'s own `planned` tasks first (SKILL.md *Next*).

   Never an umbrella (its close is a human judgment), a rehearsal (`rehearsal: true`), a task with no flow (*No flow, no run* above), or a task on an **attended** routine (`TASKS routine show <name>`: its trigger reaches a person, and taking it here would run it with nobody there).
3. Run it as above — one run per invocation.

An unattended routine's wake (`flows/wake.md`) first resumes its in-flight tasks whose parked question has an answer (above), then runs each task `TASKS routine wake` lists, in order, the same way.

## Report

One line per run: closed (with the next due date if `ran` printed one), parked (the question, and that `/ops decide <id>` answers it), or waiting (on whom, by when). Nothing eligible → say so. The report lands wherever the invoking automation routes it. When anything parked or is waiting and the harness can notify, the report also goes to the user as one notification for the session, never one per run.
