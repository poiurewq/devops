# /<skill> absorb <source> — import a list people already keep

`/<skill>` is the skill in use. For work that already lives somewhere else: a TODO file or roadmap in the repo, an issues export, a checklist in a document, a spreadsheet column, a message someone sent. The user points at it or pastes it.

**This verb files tasks.** Turning written-down steps into a flow is `/<skill> flow adopt <source>` (`shared/routes/flow-create.md`), and taking a table of facts into the catalog is `/<skill> catalog <source>` (`shared/routes/catalog.md`). All three start from something the user already wrote, so say which one the material is before filing anything.

## 1. Read it, and check it is a list of tasks

Read the source in full before proposing anything, then classify it:

- **A list of separate things to do** → that is this route. Continue at step 2.
- **The steps of one procedure** ("close the month: first export, then reconcile, then send") → hand it over. Say plainly that this reads as one procedure rather than a list, and offer `/<skill> flow adopt <source>`; filing each step as its own task would scatter one procedure across the board and lose its order. Do not file the tasks and then mention the flow as an afterthought.
- **A table of facts about named things** — each row one thing (a client, a property, an account), each column a fact about it, nothing to be done → hand it to `/<skill> catalog <source>` (`shared/routes/catalog.md`) in this session: it proposes the categories and fields, then fills in keys on the user's yes. Filing a task per row would turn records into work nobody has to do.
- **Both**, which is common: say how it splits, file the task half here, and offer the procedure half to `/<skill> flow adopt <source>` and the facts to `/<skill> catalog <source>`. A tracker with a status or next-action column beside its facts is the usual case.

If it is one procedure that also needs doing now, that is a flow plus one task to run it — offer both.

## 2. Extract candidates

Pull out the items, and run `TASKS related "<item>"` on each so anything the board already carries is caught rather than duplicated. Give each its type by what it does (`shared/routes/add.md` *Which type*), never by the skill in use: one list often holds both, and an item that is both becomes two tasks. Items that repeat on a clock ("every Monday…", "monthly") are worth flagging for the user as candidates for `--kind recurring` — offer, and let them set the cadence. Never set one yourself.

## 3. Ask which mode they want (they can mix, per batch)

- **Adjudicate now**: walk them through in batches of about ten, each with your proposed disposition — **keep** (with its type, a title, an area for a dev task, deps, and a one-to-three sentence description), **drop** (already done, stale, or a duplicate — say which), or **change** (needs their wording or a scope call). They decide; add the keeps as `shared/routes/add.md` *Filing* says (`--type ops` on every ops task), in the order any real sequence implies.
- **Funnel to proposed**: for a long list nobody has time to go through now, add each plausible item with `--status proposed` and your best-guess type, title, area and deps, pausing only on items too unclear to record faithfully. Each carries an `Intent:` line in the source's own words where it states the goal; for the items where it does not, ask the user once, in one batched question listing them. They queue up for `/<skill> decide` (`shared/routes/decide.md`). Obvious junk may be skipped, but say what you skipped and why.

Drops are simply never added. Do not add one and then mark it `not-planned` — that status is for work the board already carried.

## 4. Point at the board, and leave the original alone

Say that the board is now where this work lives. Never edit or delete the source yourself. A document outside the repo is the user's to retire. A source file in this repo can be retired (deleted, or cut to a one-line pointer to the board) only through a code change, so offer to file a dev task for it; the user decides.
