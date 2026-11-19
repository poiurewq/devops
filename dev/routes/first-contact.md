# /dev (bare) and /dev help — first contact

Covers bare `/dev` and `/dev help`. Do not improvise the welcome or the options table.

## First contact (bare `/dev`)

Classify with two script calls — `TASKS board` (board?) and `TASKS whoami` (identity?):

- **Board exists** (and identity set): show `TASKS board`, then **context options only** (below) — never the full options table, and no per-command commentary. Close with one line that `/dev help` has the complete menu.
- **No board** — assume the user knows nothing beyond the name. Deliver the *Welcome* below **verbatim** (it exists so every agent gives the same first impression — don't improvise your own; only trim a section if the user has made clear they already know it), then run `shared/routes/init.md` if they accept. If they decline, point at `/dev help` for later and stop — don't set anything up unasked. Don't dump the full command reference on them; they'll learn verbs as they need them.
- **Board exists but no identity** (new contributor): skip the sales pitch — one line ("this repo runs its task board with dev; let's get you on it"), then `shared/routes/init.md`'s identity/join steps.

### Welcome (no board)

---
**Welcome to dev** — a shared task board that lives inside your repo, plus a workflow around it built for teams of humans *and* AI agents.

**What it is.** Every task is a small file under `.tasks/`, synced through git — so every contributor, on any machine or branch, sees the same board. Agents can work the board in parallel without stepping on each other.

**How it works.** You declare tasks (or higher-level goals — dev breaks them down). Contributors pick tasks up, each on its own branch, and everything lands through a PR. Reviews, design decisions, and approvals always come back to a human: agents draft, you decide.

**The philosophy.** Minimal ceremony. A task is a few sentences, not a spec — details get worked out at implementation time, and real design questions are surfaced to you instead of silently guessed. The tooling handles the process (branching, reviews, attribution, board hygiene) so nobody has to remember it.

Want me to set it up here? It takes about a minute — a name for attribution and a couple of choices about branches — and you can add your first task right after.
---

### Context options (bare only; after identity)

From board state (and a light PR refresh on `draft` / `review` tasks if useful, `shared/routes/status.md` *PR state refresh*), emit only the lines that apply — short command shapes, ids filled in when known. Skip categories that don't apply; do not pad toward a full menu.

| When | Offer |
|---|---|
| Open forks (`needs: decision`), `proposed` tasks, or open PRs to review | `/dev review` |
| Your `doing` / `planned` / `draft` / `review` work | `/dev status` · `/dev <id>` (a `draft` is yours to finish, review via `/dev review <id>`, and `ready`; `review` gets a resume note) |
| Unassigned backlog and a quiet plate | 1–2 unblocked candidates via `/dev <id>` or `/dev pick <id>` |
| No open work on the board | `/dev add <task-or-goal>` |

Prefer the highest-signal row(s); one or two lines is enough. Always end with the `/dev help` hint.

## `/dev help`

When board and identity exist: emit the options table **verbatim** (below), plus an optional one-liner that bare `/dev` is board + next steps — nothing else. No board, or board without identity: same setup path as bare first contact (welcome / join) — don't show the table before the board is usable.

### Options table (reproduce as-is)

Every agent shows the same menu, so the user learns one map of the tool. Emit it whole — don't reorder, trim to "what's relevant", or annotate.

| | |
|---|---|
| **Learn** | `/dev tour` — how dev works, one card at a time |
| **See** | `/dev board` — the whole board (status) · `/dev board --by-area` — cut by area · `/dev status` — your plate · `/dev show <id>` — one task |
| **Add work** | `/dev add <task-or-goal>` — file a task, or work a goal or pile of threads onto the board · `/dev absorb <file>` — import an existing list · `/dev audit [area]` — scan the code and file what it finds |
| **Do work** | `/dev pick <id>` — claim it · `/dev <id[, id…]>` — see a task through in one sitting: build, check against intent, review, with you deciding only the real calls · `/dev implement <id[, id…]|goal>` — only build it (or a batch) and open PR(s), no review; unknown goal is filed via add triage first · `/dev next` — pick the top task for you · `… unattended` after `/dev <id>` or `/dev next` — an agent builds it with nobody there, to a draft |
| **Decide** | `/dev review` — PRs, design questions, and proposals waiting on you · `/dev decide` — only the questions and proposals · `/dev meta` — pressure the board · `/dev meta area` — area-validity only |
| **Adjust** | `/dev change <id> <what>` · `/dev delete <id>` · `/dev area` · `/dev config` |
| **Iterate** | `/dev iteration` — show, close, or start the next one |
| **Skill** | `/dev skill` — version and update state · `/dev skill update` — pull latest dev skill · `/dev skill update auto on/off` — opt-in auto-apply · `/dev skill feedback <text>` — file a bug or idea about the skill as an issue on its public repo |
