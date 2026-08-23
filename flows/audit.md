# /dev audit [area] — scan the code, file what it finds

A health pass over the product's **code**, not the board: read what is
there and file what should change. `/dev meta` presses the board;
`/dev review` is the inbox of pending judgments. This is the one flow
that opens the codebase looking for work nobody has filed yet.

Findings are filed as `proposed` tasks. An audit never decides that work
should happen — it puts the question on the board. Nothing here claims,
branches, or ships: an audit run has no PR.

## Scope

No argument = the whole product. `/dev audit <area>` = that area alone
(a name from `TASKS area list`; anything else, ask which they meant).

A **recurring audit task** carries its own scope and emphasis in its body
— what this board cares about, what to skip. An empty body means the
whole product with the defaults below. Before starting, find the one
covering the scope you were asked for (`TASKS recur list`) and read its
body (`TASKS show <id>`) — the list gives due dates, not emphasis.

## The pass

Read code, not just names. What to weigh — no fixed order, not a
checklist to tour, and the board's own emphasis outranks this list:

- **Correctness** — logic that is wrong, not merely ugly: unhandled
  states, races, silent failure paths.
- **Security** — untrusted input, secrets, permissions, injection.
- **Architecture** — an eroded boundary; a rule `AGENTS.md` states that
  the code no longer follows.
- **Bloat** — dead code, duplicated logic, abstraction with one caller.
- **Tests** — what would break silently.
- **Docs** — an invariant learned the hard way that no `AGENTS.md` records.

Follow what looks wrong rather than sweeping evenly. Depth beats
coverage: three findings you can defend beat twenty you skimmed. If the
code is healthy, say so and file nothing — an audit that always files is
noise.

## Filing

Per finding:

1. Draft a title and a 1–3 sentence description: what is wrong, where,
   and why it matters. The evidence, not the fix — the fix is the
   implementer's call. Do not write constraints or non-goals the code
   does not force (SKILL.md *Do not manufacture specifications*).
2. `TASKS related "<title + description>"` — already filed, or an
   umbrella already covers the cluster → amend or attach rather than
   duplicate (`flows/add.md` step 2).
3. `TASKS add --title "..." --status proposed [--area <m>] [--desc "..."]`.

Then report **one line per filed task**: id, title, why. No findings
document, no severity table — the tasks are the output. Filed nothing?
One line saying so.

## Recording the run

An audit run has no PR, so it never lands. Stamp it instead:
`TASKS recur ran <id>` on the recurring task whose scope matches the pass
just run. That re-arms it to `backlog` and re-derives the due date. A
pass over one area stamps that area's recurring audit — never the
whole-board one. No recurring task covers that scope → nothing to stamp.

## Scheduling

Whether work recurs, and how often, is the user's call (SKILL.md
*Recurring*) — never file one silently.

After a pass whose scope has no recurring audit, offer **once** to
schedule it: recommend a cadence with a reason (how fast this code moves,
how much this pass turned up) and wait for their answer.

```
TASKS add --title "Recurring audit: <scope>" --kind recurring \
          --cadence <N><unit> --desc "<scope + emphasis>"
```

Whole-board and per-area audits are separate recurring tasks; a board may
hold several. Declined → drop it, and do not re-offer on every pass.

Rescheduling runs through this same command: when the user asks to change
the schedule, `TASKS update <id> --cadence <N><unit>` — the due date
re-derives immediately. `--status not-planned` stops one for good.
