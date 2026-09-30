# /ops absorb <source> — import a list people already keep

For work that already lives somewhere else: a checklist in a document, a note of things to do, a spreadsheet column, a message someone sent. The user points at it or pastes it.

**This verb files tasks.** Turning written-down steps into a flow is `/ops flow adopt <source>` (`flows/flow-create.md`). Both start from something the user already wrote, so say which one the material is before filing anything.

## 1. Read it, and check it is a list of tasks

Read the source in full before proposing anything, then classify it:

- **A list of separate things to do** → that is this flow. Continue at step 2.
- **The steps of one procedure** ("close the month: first export, then reconcile, then send") → hand it over. Say plainly that this reads as one procedure rather than a list, and offer `/ops flow adopt <source>`; filing each step as its own task would scatter one procedure across the board and lose its order. Do not file the tasks and then mention the flow as an afterthought.
- **Both**, which is common: say how it splits, file the task half here, and offer the procedure half to `/ops flow adopt <source>`.

If it is one procedure that also needs doing now, that is a flow plus one task to run it — offer both.

## 2. Extract candidates

Pull out the items, and run `TASKS related "<item>"` on each so anything the board already carries is caught rather than duplicated. Items that repeat on a clock ("every Monday…", "monthly") are worth flagging for the user as candidates for `--kind recurring` — offer, and let them set the cadence. Never set one yourself.

## 3. Ask which mode they want (they can mix, per batch)

- **Adjudicate now**: walk them through in batches of about ten, each with your proposed disposition — **keep** (with a title and a one-to-three sentence description), **drop** (already done, stale, or a duplicate — say which), or **change** (needs their wording or a scope call). They decide; add the keeps with `TASKS add --title "…" --type ops [--deps …]` in the order any real sequence implies.
- **Funnel to proposed**: for a long list nobody has time to go through now, add each plausible item with `--status proposed` and your best-guess title, pausing only on items too unclear to record faithfully. They queue up for `/ops decide` (`flows/decide.md`). Obvious junk may be skipped, but say what you skipped and why.

Drops are simply never added. Do not add one and then mark it `not-planned` — that status is for work the board already carried.

## 4. Point at the board, and leave the original alone

Say that the board is now where this work lives, and let the user retire the source themselves. Do not edit or delete it: a document elsewhere is theirs, and a file in this repo is a code change, which belongs to `/dev`.
