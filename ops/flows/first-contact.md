# /ops (bare) and /ops help — first contact

Covers bare `/ops` and `/ops help`. Do not improvise the welcome or the options table.

## First contact (bare `/ops`)

Classify with two script calls — `TASKS board` (board?) and `TASKS whoami` (identity?):

- **Board exists** (and identity set): show what is live — runs in flight, anything due (`TASKS recur list --due`) — then **context options only** (below). Never the full options table, and no per-command commentary. Close with one line that `/ops help` has the complete menu.
- **No board** — assume the user knows nothing beyond the name. Read `flows/init.md` and deliver its step-0 welcome **verbatim** (it exists so every agent gives the same first impression — don't improvise your own), then run the init flow if they accept.
- **Board exists but no identity** (new contributor, or a board `/dev` already set up here): skip the sales pitch — one line ("this project keeps its work on a shared board; let's get you on it"), then the init flow's identity/join steps.

### Context options (bare only; after identity)

From board and playbook state, emit only the lines that apply — short command shapes, ids and names filled in when known. Skip categories that don't apply; do not pad toward a full menu.

| When | Offer |
|---|---|
| A run is in flight (`doing`, assigned to this user) | `/ops run <id>` — pick it back up |
| Recurring work is due (`TASKS recur list --due`) | `/ops run <id>` |
| Open questions (`needs: decision`) or `proposed` tasks | `/ops decide` |
| Unassigned ops backlog and a quiet plate | 1–2 candidates via `/ops run <id>` |
| Tasks on the board but no flows yet (`TASKS flow list` empty) | `/ops run <id>` files the procedure as it goes; `/ops flow create` once one settles |
| No open ops work | `/ops add <task-or-goal>` |

Prefer the highest-signal rows; one or two lines is enough. Always end with the `/ops help` hint.

## `/ops help`

When board and identity exist: emit the options table **verbatim** (below), plus an optional one-liner that bare `/ops` is the live picture plus next steps — nothing else. No board, or board without identity: same setup path as bare first contact — don't show the table before the board is usable.

### Options table (reproduce as-is)

Every agent shows the same menu, so the user learns one map of the tool. Emit it whole — don't reorder, trim to "what's relevant", or annotate.

| | |
|---|---|
| **See** | `/ops board` — the whole board · `/ops status` — your plate · `/ops show <id>` — one task |
| **Add work** | `/ops add <task-or-goal>` — file something to be done · `/ops absorb <source>` — import a list of things to do |
| **Do work** | `/ops pick <id>` — claim it for later · `/ops run <id[, id…]>` — run a task and record it · `/ops run <flow-name>` — run a flow now · `/ops run <description>` — file it and run it |
| **Playbook** | `/ops flow list` — every flow · `/ops flow show <name>` — read one · `/ops flow runs <name>` — every run of it · `/ops flow adopt <source>` — take in one you already wrote · `/ops flow create` — write one (from a run, a conversation, or scratch) · `/ops flow edit <name> [<what>]` · `/ops flow retire <name>` |
| **Adjust** | `/ops change <id> <what>` · `/ops drop <id>` — decided against · `/ops delete <id>` |
| **Decide** | `/ops decide` — open questions and proposed tasks waiting on you |
| **Think** | `/ops meta` — pressure the playbook and the board |
| **Iterate** | `/ops iteration` — show, close, or start the next stretch of work |
| **Skill** | `/ops skill` — version and update state · `/ops skill update` — pull the latest · `/ops skill update auto on/off` — opt-in auto-apply · `/ops skill feedback <text>` — file a bug or idea about the skill as an issue on its public repo |
