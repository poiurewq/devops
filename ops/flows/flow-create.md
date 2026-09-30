# /ops flow create and /ops flow edit — write the procedure down

Covers `/ops flow create [<name>]`, `/ops flow adopt <source>`, and `/ops flow edit <name> [<what to change>]`. Writing a flow is collaborative: you synthesise, the user steers, and it sharpens over rounds rather than arriving whole.

## What makes a good flow

- **One coherent procedure.** If it needs "and then, if it's the other kind of thing, do this instead", it is probably two flows, or one flow that `uses` another.
- **A description that picks it.** The one-line `description` is what a future agent reads to decide this is the right flow for a task — what it is for and when to use it, not how it works. Write it the way a tool's own description is written.
- **Inputs a run can be asked for.** Name the things that differ run to run (`client`, `month`, `amount (USD)`). Anything constant belongs in the body, not the inputs.
- **Steps marked by who does them.** Tag each step `[agent]`, `[user]`, or `[confirm]` (SKILL.md *Step marks*). A `[confirm]` step goes right **before** anything sent, published, paid for, or deleted — the step that prepares it, so the user signs off on exactly what will go out; afterwards it is too late. Only an act the agent performs gets a check of its result after it; when the user performs it, their doing it is the check. Two or three real checkpoints beat a check after every step.
- **Numbered steps.** A run that stops partway cites where it stopped (`flows/run.md`), and a number is a steadier handle than a line of prose. Number them; if a later edit renumbers them, say so when you show the change, because pause records already written point at the old numbers.
- **Outputs a later step can still reach.** Where a step produces something the next one needs, say where it goes: a shared location — the repo, a drive, the ticket — not a temp path on whichever machine ran it. A run can be paused and resumed elsewhere, and an artifact nobody else can open stops it dead.
- **Short.** Someone should be able to follow it without reading it twice.

## Rounds

Do not write the whole thing and ask for approval. Go a layer at a time, showing your work and waiting at each:

1. **Scope.** What this flow covers, when someone would reach for it, what it deliberately leaves out, and whether it should follow existing flows (`TASKS flow list` first — a new flow that overlaps an old one is usually an edit to the old one). Get this agreed before writing steps.
2. **Outline.** The step list, numbered, one line each, tagged `[agent]`, `[user]`, or `[confirm]`, with the checkpoints where they fall and the inputs each step needs. This is where structure is cheap to change, so push on it: wrong order, a missing branch, a checkpoint in a useless place.
3. **Detail.** Flesh each step into instructions someone could follow. Name systems, fields, and formats concretely. Keep the marks and checkpoints from the outline.
4. **Commit.** Only once they say it is right.

Re-run any round as often as it takes; stop as soon as the user is satisfied rather than working through all four out of habit.

## Where the material comes from

- **From a run** (`from <id>`): read the task (`TASKS show <id>`) — the notes accumulated during the run and its `Ran:` record are the raw draft. **Simplify rather than transcribe.** Drop what was specific to that one run, fold the "wait, do this first" detours into the right order, and cut verification steps down: if the artefacts of several steps don't depend on each other, one check at the end replaces a check after each. Say what you dropped when you show the outline.
- **From a conversation** (`from this conversation`): the procedure is buried in what was just discussed. **Present the scope first and get it approved before outlining** — a conversation contains more than the procedure, and guessing which parts are the flow wastes a round.
- **From scratch**: the user describes it. Ask only what the outline genuinely leaves open.
- **From something written down** (`/ops flow adopt <source>`, or `from <source>` — a document, a checklist they paste, a file they point at): treat it as the outline round's input, not as finished — it was written for a human reader, and the marks, inputs, and checkpoints still have to be decided; every outward or hard-to-undo step leaves the outline either `[user]` or with a `[confirm]` step right before it. If what you were handed turns out to be a list of unrelated things to do rather than one procedure, hand it back the other way: say so and offer `/ops absorb <source>` (`flows/absorb.md`), which files them as tasks.

## Committing it

**The name is decided here, not at the start.** Adopting a source or working from a run begins with material, not a title, and what the procedure should be called is usually only clear once its scope is settled — so propose a name at this round and let the user take it or change it. Only `/ops flow create <name>` fixes one up front, because there the user already had one in mind.

Name it as a slug: lowercase, hyphens, no numbers-as-names (`month-end-close`, `onboard-client`). Short and about the work, not the tool. Check `TASKS flow list --all` for something too close — a name that is one word off another is how the wrong flow gets picked later.

Write the body to a temporary file and pass it, rather than trying to fit a procedure on the command line:

```
TASKS flow create <name> --desc "<one line>" --inputs "<a, b (hint)>" [--uses "<flow, flow>"] --file <path>
```

Then show the user the flow as recorded (`TASKS flow show <name>`) and delete the temp file. If the script warns that the id is shared with another flow, pass that warning on and follow it (`TASKS flow reid <name>`).

## Editing (`/ops flow edit <name>`)

- **A change named in the invocation** ("`/ops flow edit month-end-close drop step 3`", "add an input for the currency") is surgical: read the flow, make exactly that change, show the result. No rounds, no rewrite of prose the user did not ask about. `TASKS flow update <name> --file <path>` for a body change, `--append` to add a paragraph, `--desc` / `--inputs` / `--uses` for the frontmatter.
- **No change named** → the rounds above, starting from the flow as it stands. Scope first: what is wrong with it today.
- **Untagged or prose-marked steps** found on any edit: propose the tags alongside the change asked for (one line, not a rewrite) — an outward or hard-to-undo step gets a `[confirm]` step before it, or becomes `[user]`. Flows written before step marks existed get converted this way, a touch at a time.
- **Renaming** is `TASKS flow rename <old> <new>` — the old name is free again immediately and past runs still resolve through the flow's id, so renaming is cheap. Say that, so nobody keeps a bad name out of fear.
- **Retiring** is for a procedure nobody should follow any more: `TASKS flow retire <name>`, kept for the record because past runs point at it. Never delete one. A flow that is merely out of date gets edited; retire is for one whose reason to exist is gone.
