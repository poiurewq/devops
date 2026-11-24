# /<skill> catalog [<source>] — design and grow the catalog

`/<skill>` is the skill in use. The catalog holds the named things a project's work is about and their facts, written once and pointed at as `{key.field}` (SKILL.md *Catalog references*; its files, SKILL.md *State layout*). This route shapes it with the user: bare, from the facts the board writes out more than once and the catalog's own shape; with a source — a spreadsheet, a CSV or tracker export, a table in a document, a paste — from the table where those facts already live. Covers `/<skill> catalog`, `/<skill> catalog <source>` and absorb's hand-off; the subcommand forms (`catalog list`, `catalog add`, …) are the script's, run directly. Run from the product directory, or pass `--scope`. An unattended run never runs it: the catalog's shape and its keys are the user's call (SKILL.md *Catalog references*, who writes the catalog).

## 1. Read what is there

`TASKS catalog list`, then `TASKS catalog category show <category>` for each category it lists, so a proposal extends what exists instead of duplicating it. Names are one namespace with the agents, environments and routines too.

**With a source**, read it in full before proposing anything, then check what it is:

- **A table of facts about named things** — each row one thing (a client, a property, an account, a machine), each column a fact about it → this route; step 2.
- **A list of things to do** → `/<skill> absorb <source>` (`shared/routes/absorb.md`), which files them as tasks.
- **The steps of one procedure** → `/<skill> flow adopt <source>` (`shared/routes/flow-create.md`).
- **Mixed** (a tracker often holds facts beside a status or next-action column): say how it splits, take the facts here, and offer the rest to absorb.

**Bare**, scan the text as stored — the only form that tells a written-out value from a `{key.field}` reference, since the plain `show` prints both alike:

- **Live work**: the open tasks (`TASKS list --json`, every status but `done` and `not-planned`) and the active flows (`TASKS flow list`, then `TASKS flow show <name> --raw`). This is where a key would be used.
- **Finished work**, as evidence only: this iteration's `done` and `not-planned` tasks (the same `TASKS list --json`). A value repeated in finished work tends to come back. Their text is never rewritten: its records keep the value each run used (SKILL.md *Catalog references*).

Like distill, the scan stays on the current iteration.

From that, two kinds of candidate, each naming its evidence:

- **A key**: a value written out more than once — the same address, account number, URL or machine — that names one thing, proposed as a key (its category, name and values) with every place it appears, open and finished. A password, code or token is never a candidate, however often it repeats (SKILL.md *Ground rules*). Nor is a ledger entry or a figure derived from ledger entries — a payment, a reading, a balance, a last-paid date — however often it repeats (SKILL.md *Catalog references*, what it holds).
- **A shape change**: a category or field worth adding, splitting or merging — facts several keys keep in a free-text field, a category holding two kinds of thing, two categories describing one. Extend what exists before proposing anything new. No command moves a key between categories, so a split or merge that would move keys is described with what it takes, and left to the user.

Whatever the scan finds, also ask where the user keeps facts like these now; a table they name becomes the source. Nothing found and no table named → say in two lines what the catalog is for, and stop. Otherwise propose the candidates (step 2 sets the shape rules), and write each as the user approves it, in this session: a new category or field through step 2's commands, a new key through `TASKS catalog add`, the references through step 4.

## 2. Propose the shape

One message, then wait. Per category: its name (SKILL.md *State layout* has the name rule), what one key in it is, and its fields, each with a one-line description and `(one of: …)` where the source holds a fixed set. From a source, also say:

- which column becomes which field, and which columns are left out and why — a column that changes every run is a run's input, not a fact; a column of ledger entries or figures derived from them (amounts paid, readings, a balance, a last-paid date) stays in its system of record (SKILL.md *Catalog references*, what it holds), and is named as such — at most, where that system is (an account number, a URL) becomes a field; a password, code or token is never a catalog value (SKILL.md *Ground rules*), and is dropped without being copied anywhere;
- what names each key — usually one column, slugged — with three real examples;
- where a column names a row of another table (a property's owner is a client): that field holds a bare `{key}`, so `{a.b.c}` reads through it;
- an existing category it fits: extend it (`category update --field`) rather than declare a second one.

Take this slowly: the names, the fields and how the source maps onto categories, fields and key names are the user's call, and that agreed mapping is all step 3 follows. The user edits the proposal until they say yes. Then `TASKS catalog category add <category> --field "<field>: <what it holds>"…`, or `TASKS catalog category update <category> --field "…"…` for one that exists. Never declare a category or field they have not approved.

## 3. Fill in keys, in one pass

With the mapping agreed, transfer every row that fits it in one pass, with no confirmation per key: `TASKS catalog add <category> <key> --set "<field>=<value>"…` per key. Set aside, unwritten, every row that does not fit — a missing or ambiguous key name, a name the catalog already holds (current or former; `add` refuses it), a value outside its field's `one of`, a missing value the mapping did not expect, anything else odd — and anything that looks like a secret (dropped, never copied anywhere). Then report how many keys were written and bring the set-aside rows to the user together, each with what is wrong and a proposed fix: another name, an update of the key it clashes with when it is the same thing (shown as `«old» → «new»`, made with `TASKS catalog update <key> --set …`), a value, or leaving it out. Write each as they decide.

**Run again from the same source** (step 4), a row whose key already exists in the mapped category is that key, not a clash: its changed values are written in the pass (`TASKS catalog update <key> --set …`) and listed afterwards as `key.field «old» → «new»`, so any that went the wrong way can be set back. A key in that category the source no longer has comes back with the set-aside rows.

A pass cut short (the user stops it, a command fails) leaves the rest in the source; say which row it stopped at. Filing the rest as a task, naming the source and that row, only when the user asks for it (`shared/routes/add.md`).

## 4. Point at it, and leave the source alone

Once the keys exist, offer to replace facts the board writes out with references: an open task's text through `TASKS update <id> --desc`, starting from `TASKS show <id> --raw`, never inside a record line, which keeps the value its run used; a flow is named as a flow edit, `/<skill> flow edit <name>`, reviewed as any flow write. A `done` or `not-planned` task is never rewritten. Offer; the user picks which.

Never edit or delete the source. Ask which one is kept up to date from now on: if the source stays where the facts are maintained, `/<skill> catalog <source>` again brings the catalog up to it the same way (step 3, run again).

## Growing it later

The same route, bare or with a new source: a new category, a new field (`category update --field`), a field dropped (`category update --drop-field`, refused while a key still holds a value for it), a key or category renamed (`catalog rename`, `catalog category rename`; a former name stays reserved and keeps resolving). Each is the user's call, made here with them; a run only ever updates a value (SKILL.md *Catalog references*).
