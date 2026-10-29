# /ops rehearse — go through a flow once without its real-world effects

Covers `/ops rehearse [<flow-name>]` and "dry run <flow-name>". A rehearsal tests a new or changed flow before anyone relies on it: every step is walked with the user present, the outward ones mostly held back, and what the flow got wrong comes out as an edit to it. It is a run in every other respect — `flows/run.md` applies wherever this file is silent (step marks, checkpoints, handoffs, notes, never fabricate) — but it is never mistaken for one: its own task, closed with `TASKS ran --rehearsal`.

## 1. File the rehearsal task

- **No flow named** → ask which one; never guess. Offer the likely candidates: active flows created or edited recently (`created` in `TASKS flow list --json`; an edit made this session or one the user mentions) and active flows with no recorded runs yet (`TASKS flow runs <name>`).
- Resolve the flow (`TASKS flow show <name>`, closest-name resolution) and follow its `uses` into the flows it composes — those are rehearsed with it.
- An open task already on the board with `rehearsal: true` whose `flow` field (`<id> <name>`, in `TASKS list --type ops --json`) carries this flow's id is this rehearsal — match on the id, not the name in the title, which a rename leaves behind: resume it as `flows/run.md` section 2 resumes a run. Otherwise file one directly (`TASKS related` first, as `flows/add.md` does): `TASKS add --type ops --rehearsal --title "Rehearse <flow-name>" --desc "…"`, the description ending in its `Intent:` line — what the user wants this rehearsal to settle (`flows/add.md` *Intent*; ask only when the invocation leaves it unclear) — then `TASKS update <id> --flow <name[,name]>`. The flow ref is required — `ran --rehearsal` refuses a task without one. Never rehearse on the real task, and never on a recurring one.
- **The user is present.** A rehearsal is never driven unattended: its checkpoints and feedback need a person. Nobody there → say so and stop.

## 2. Preflight

Do `flows/run.md` section 2 for this task (sequences, handoffs, inputs, mark started). Marking it started is refused while a real run of the flow is `doing`: surface that and stop until the run closes. Inputs are the values a real run would get, or stand-ins the user picks; record them as usual. Then sort every step that is outward or hard to undo (SKILL.md *Step marks*, *The floor*) into one of two kinds:

- **Dry** — skipped. When the run reaches it, say exactly what it would do (the payload, as at a checkpoint) and go on without doing it. The default.
- **Wet-required** — a later step needs its real output (a confirmation number, an uploaded file's URL, a reply), so it has to happen for the rehearsal to reach that step. The user may keep one dry anyway; the steps that need its output then go dry with it.

Steps that only read, or are trivially reversible, run normally. A step that leaves something unsubmitted on an external platform — a saved draft, a filled form, a staged upload — runs too; it is cleaned up at the end (section 4). An `[external]` step after a dry send is dry: say what reply the flow expects, and use a stand-in the user gives for the steps after it, or skip them.

Show the sorted list in one message — each step, dry or wet, and for a wet one which later step needs it — and get **one approval for the wet set** (none to get when every step is dry). That approval admits them to the rehearsal; it is not their `go`. Each still stops at its own `[confirm]` (or the floor) when the run reaches it, with the payload shown.

## 3. Walking it

Follow the flow as `flows/run.md` section 3 does, with the dry/wet sort applied. Note as it happens (`TASKS note <id> --at "<step>" "…"`) — in a rehearsal notes are the point, so lean toward noting:

- **Deviations** — a step that did not work as written, an order that fought the work, a missing input, a step inserted.
- **Disambiguations** — a step that could be read two ways, and which way was right; look-alike accounts, records or buttons and what tells them apart.
- **Things to avoid** — for GUI steps, the committing buttons, look-alikes, landmarks and session quirks in `flows/gui.md` *What a rehearsal or first run notes*.
- **Drafts left behind** — every non-file thing left on an external platform: `TASKS note <id> --at "<step>" "draft: <platform> <where> — <one-line description>"`. Like a `file:` note (`flows/run.md` section 3), it is a cleanup item, not a deviation.

A handed-off sequence gets the usual brief (`flows/run.md` *Handoffs*) plus which of its steps are dry, and asks the agent to report, beside the usual fields, every draft it left and what in the steps was unclear to it.

## 4. Clean up

Gather the task's `file:` and `draft:` notes and show them as one list before touching anything; removing them is a delete, so it waits for the user's `go` on that list.

- **Here** (`project`, or this machine's environment) → remove each on the `go`, then show what is gone.
- **On another machine, or another agent's platform** → hand that part of the list to the agent that left it (a short brief: what to remove, where, and to report back), or to the user to do by hand. Record each handoff as a note.
- **What a wet step did stays.** Say plainly which effects are real and remain; the record names them.

Anything that could not be removed is noted (`TASKS note <id> "left: <what, where, why>"`) and named in the record.

## 5. Feedback and close

1. **The intent check.** Quote the task's last `Intent:` line — what this rehearsal was to settle — and ask whether it did. A no is not a failure to hide: say what is still open, and keep going or carry it into the edit (section 6), as the user says.
2. **Ask for feedback** — from the user, and from every agent that took a sequence (a short question through the way it was reached: what was unclear, what it would change). Note each answer on the task, naming who gave it.
3. **Close**: `TASKS ran <id> --rehearsal --flow <name[,name]> --record "<inputs; dry and wet steps; deviations; cleanup, and what stays>"`. This writes `Rehearsed (<date>): …`, which `flow runs` lists marked `[rehearsal]` and real-run checks skip.

## 6. Propose the flow edit

Then, from the notes and the feedback, propose the edit the rehearsal earned — and it may be structural: reordered steps, a sequence split off, a `[confirm]` added before a step that turned out to commit, an input added or derived. Small fixes go in directly on the user's go-ahead (`TASKS flow update <name> --append "…"` or `--file`); anything larger goes through `flows/flow-create.md` *Editing*, in this session while the rehearsal is fresh. A rehearsal that found nothing proposes nothing — say so.

- **An inline environment** (SKILL.md *Sequences*) that the rehearsal walked: if its `Expects:` held up unchanged, its shape has settled — offer to register it (`flows/run.md` section 6, the inline-environment offer). If the rehearsal corrected it, fix the `Expects:` in the edit and leave registration for the next rehearsal or run.
- **A significant edit** → suggest rehearsing again, in a new session (`/ops rehearse <name>`), so the next pass reads only the flow as written.
