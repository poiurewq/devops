# Unattended — a run with nobody there

`/<skill>` is the skill in use. Read when the invocation ends in the word `unattended`: `/dev <id[, id…]> unattended`, `/ops run <id[, id…]> unattended`, `/<skill> next unattended`, or an unattended routine's wake, which passes the word the same way. Unattended is chosen, never inferred: without the word a run is attended, whoever started it. It is for scheduled or parallel agent sessions with no human present, and changes who is there, not what a run is: the skill's own run still governs (SKILL.md *Running a task*), with this file's overrides and the skill's own part, `flows/unattended-run.md` — how a task of this skill's type runs with nobody there. Several ids run one after another, each its own run, never as a batch. Runs may go concurrently against one board: taking the task (the marker, below) is the mutex.

## The mode

**Identity**: the run acts as the human who owns this machine's GitHub account, so every piece of its work traces to a responsible person. `TASKS whoami` prints the roster handle the current GitHub login holds — call it `<owner>`, and assign as `<owner>` explicitly (`--assignee <owner>`). If it errors (gh unreadable, or the login not on the roster), stop and report it: joining a board is a human step (`/<skill> init`), and an unattended run never registers a contributor. Run from the product directory or pass `--scope`.

**Provenance**: which agent did the work is provenance, not identity. Every outcome record the run writes (SKILL.md *Running a task*) and every `Question:` it parks ends `(unattended, <model-id>)` — `(unattended, <model-id>, routine <name>)` when a routine's wake started it (`shared/flows/wake.md`) — so a reader can tell agent work from the owner's own.

**The marker**: while this session works a task, it carries `unattended:<model-id>`, set by the call that takes the task (`flows/unattended-run.md` says which), so the owner can tell it from their own work and nobody resumes into it. The script refuses to take a task another run's marker holds: report that and leave it (under `next unattended`, select again). Leaving `doing` clears the marker; a stop that leaves the task `doing` hands it back with `TASKS update <id> --unattended ""`.

**Hard limits** — never decide for the human:

- never resolve a `needs: decision` question, approve a `proposed` task (the run's own findings included), mark a task `not-planned` or `shelved`, or delete one — a pointless-looking task gets `needs: decision` with the reasoning instead;
- never file a recurring task or offer a schedule;
- never pick or run an umbrella: its close is a human judgment (SKILL.md *Umbrella close*);
- never pass a checkpoint on its own judgment, and never fabricate a step's output;
- never merge, approve, `ready` or `unready` a PR, and never park, discard or reset the local integration branch;
- never create, edit or rehearse a flow, and never pause an ops run (a pause is the user's call; a dev run's park is the one exception, `flows/unattended-run.md`).

Anything that needs a person goes on the board — `needs: decision` with a `Question:` in the body, or new work filed as `proposed` — and humans dispose of it (answering a parked question, SKILL.md *Running a task*).

**A run goes to its first stop**: it does what it can without a person and stops at the first thing only a person can settle, filing that as a decision. What a stop looks like differs by task type, and `flows/unattended-run.md` says it for this skill's type.

## `/<skill> next unattended` — select one

Candidates are SKILL.md *Next*'s — this skill's type only, in its order (due recurring work first, then `<owner>`'s own `planned` tasks, then the rest; `backlog` or `planned`, unassigned or `<owner>`'s, no open `needs`, every dep `done`) — minus:

- **umbrellas**, ready or not (hard limits above);
- **any task on an attended routine** (`TASKS routine show <name>`): its trigger reaches a person, and taking it here would run it with nobody there;
- what `flows/unattended-run.md` excludes for this type.

A recurring task is a candidate only while due; nothing due → move on. Take the first candidate and run it; one that turns out to be excluded is reported and the next is taken. Nothing suitable → say so and stop. A named id the same rules exclude is reported and left alone.

An unattended routine's wake (`shared/flows/wake.md`) runs each task `TASKS routine wake` lists, in order, the same way.

## Report

Each run ends with its summary — closed or shipped, parked or flagged (the question, and what answers it), skipped (why), or waiting (on whom, by when) — and `flows/unattended-run.md` says what a run of this type reports. Nothing eligible → say so. The report lands wherever the invoking automation routes it. When anything in the session parked, was flagged or is waiting, and the harness can notify, the summaries also go to the owner as **one notification for the session**, never one per run.
