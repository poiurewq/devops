# /ops flow create and /ops flow edit — write the procedure down

Covers `/ops flow create [<name>]`, `/ops flow adopt <source>`, and `/ops flow edit <name> [<what to change>]`. Writing a flow is collaborative: you synthesise, the user steers, and it sharpens over rounds rather than arriving whole.

## What makes a good flow

- **One coherent procedure.** If it needs "and then, if it's the other kind of thing, do this instead", it is probably two flows, or one flow that `uses` another.
- **A description that picks it.** The one-line `description` is what a future agent reads to decide this is the right flow for a task — what it is for and when to use it, not how it works. Write it the way a tool's own description is written.
- **Goal and capability, not tools.** A step says what it achieves and what it needs ("export last month's invoices as CSV"), not which button or binary, so it survives a tool changing. Where the tool matters, name it: an API or CLI beats driving a GUI when both are equally reliable, since it is repeatable and its output checkable; a GUI is a legitimate choice when it is the reliable path.
- **Inputs a run can be asked for.** Name the things that differ run to run (`client`, `month`, `amount (USD)`), without spaces, and write each as `{name}` where a step uses it (`3. [confirm] Draft the invoice for {client}`); create and update warn on an input the body never uses and on a near-miss placeholder. When an input can be worked out rather than asked, the hint says how (`month (the month just closed)`), so the run derives it and only confirms. Anything constant belongs in the body, not the inputs.
- **Exact where it is fixed, checked where it drifts.** A fixed fact — an account number, a URL, a file pattern — is written exactly, never paraphrased. A fact that drifts — a price, a contact, where a setting lives — gets checked before use rather than written down as a value that silently goes stale.
- **Steps marked by who does them.** Tag each step `[agent]`, `[user]`, `[confirm]`, or `[external]` (SKILL.md *Step marks*). `[external]` is a step someone outside performs while the run waits on them — an office's answer, a vendor's delivery — so the run stops there rather than pretending the next step follows on. A `[confirm]` step goes right **before** anything sent, published, paid for, or deleted — the step that prepares it, so the user signs off on exactly what will go out; afterwards it is too late. Only an act the agent performs gets a check of its result after it; when the user performs it, their doing it is the check. Two or three real checkpoints beat a check after every step.
- **No credentials, only sign-in assumptions.** A step that needs a login says "assumes signed in to <X>"; the password, code or key stays in the environment, never in the flow or its inputs (SKILL.md *Ground rules*, secrets). A fixed identifier the steps need — a username, an account number — may be written in the body.
- **Numbered steps.** A run that stops partway cites where it stopped (`flows/run.md`), and a number is a steadier handle than a line of prose. Number them, continuing across sequences rather than restarting in each; if a later edit renumbers them, say so when you show the change, because pause records already written point at the old numbers.
- **Sequences where the work changes hands or place.** When some steps need another machine, another agent, or a capability the runner may not have, group them into a sequence (SKILL.md *Sequences*) stating its `Environment:`, what it `Needs:`, the `Agent:` who usually does it if there is one, what it takes (`Inputs:`) and what it hands back (`Returns:`). A flow that runs start to finish in one place needs none. Lean toward ending a handed-off sequence at its outward step, so the `go` comes back through the runner; a `[confirm]` inside one stays allowed when confirming there is easier — a prepared message already on that agent's screen, say. Use names from `TASKS agent list` / `TASKS env list`. A place this flow is the first to use goes in as `Environment: inline`, with `Expects:` (what it must provide) and `Accessors:` (who can reach it — the creator's handle unless they name someone else); it gets registered once a run has tested it, not before.
- **GUI steps follow `flows/gui.md`.** When any step is done through a screen — a web app, a desktop program, an OS dialog — read it before the outline round: stable targets, what should be on screen where landing on the wrong account or record is a real risk, a visible postcondition after each change, the confirm state as a filled, unsubmitted form, and what the place must provide in its environment's expectations.
- **Outputs a later step can still reach.** Where a step produces something the next one needs, say exactly where it goes and in what format (`reports/{month}.csv`, one row per invoice): a shared location — the repo, a drive, the ticket — not a temp path on whichever machine ran it. A run can be paused and resumed elsewhere, and an artifact nobody else can open stops it dead. How files are named is each flow's own call; that it says so exactly is not.
- **Safe to run twice.** A step that creates, files or sends something checks first whether it already happened (the file exists, the invoice is already logged), so a resumed or repeated run does not double it.
- **Never lines come from runs.** A `Never …` line, or a note telling two look-alikes apart (two accounts with near names, two similar buttons), carries its reason and is added when a run trips on the trap (`flows/run.md` section 6), not guessed at creation — guessed ones make a flow long and are mostly wrong.
- **A sanity check against past runs is opt-in.** Where a value should look like last time's — an amount, a row count — a `[confirm]` step may say to compare it with past runs; the runner then flags what is out of line at that checkpoint. Add one only where a wrong value would go out unnoticed.
- **Short.** Someone should be able to follow it without reading it twice.

## Rounds

Do not write the whole thing and ask for approval. Go a layer at a time, showing your work and waiting at each:

1. **Scope.** What this flow covers, when someone would reach for it, what it deliberately leaves out, and whether it should follow existing flows (`TASKS flow list` first — a new flow that overlaps an old one is usually an edit to the old one). Get this agreed before writing steps.
2. **Outline.** The step list, numbered, one line each, tagged `[agent]`, `[user]`, `[confirm]`, or `[external]`, with the checkpoints where they fall and the inputs each step needs, grouped into sequences if any steps run elsewhere or by someone else. This is where structure is cheap to change, so push on it: wrong order, a missing branch, a checkpoint in a useless place.
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

Then show the user the flow as recorded (`TASKS flow show <name>`) and delete the temp file, and suggest rehearsing it before anyone relies on it: `/ops rehearse <name>` (`flows/rehearse.md`), in a new session, so the pass reads only the flow as written and not the conversation that wrote it. If the script warns that the id is shared with another flow, pass that warning on and follow it (`TASKS flow reid <name>`). If it warns on a sequence's agent or environment name (create and update both check), pass that on too: a former name gets the current one written in; an unknown agent is either a typo or an entry to register (`TASKS agent add`) — ask which. An unknown environment gets three options: a typo, register it now (`TASKS env add`), or rewrite the sequence as `Environment: inline` with its `Expects:` and `Accessors:` — recommend inline when no other flow names this place, since this flow is its first use and no run has tested it yet. Once it is inline, do not suggest registering it before the flow's first run or rehearsal: an entry nobody has run against is a guess.

## Editing (`/ops flow edit <name>`)

- **A change named in the invocation** ("`/ops flow edit month-end-close drop step 3`", "add an input for the currency") is surgical: read the flow, make exactly that change, show the result. No rounds, no rewrite of prose the user did not ask about. `TASKS flow update <name> --file <path>` for a body change, `--append` to add a paragraph, `--desc` / `--inputs` / `--uses` for the frontmatter.
- **No change named** → the rounds above, starting from the flow as it stands. Scope first: what is wrong with it today.
- **After a significant edit** — steps reordered, added or removed, a sequence or checkpoint moved, anything beyond a wording fix — suggest rehearsing again in a new session (`/ops rehearse <name>`).
- **Untagged or prose-marked steps** found on any edit: propose the tags alongside the change asked for (one line, not a rewrite) — an outward or hard-to-undo step gets a `[confirm]` step before it, or becomes `[user]`. Flows written before step marks existed get converted this way, a touch at a time.
- **Renaming** is `TASKS flow rename <old> <new>` — the old name is free again immediately and past runs still resolve through the flow's id, so renaming is cheap. Say that, so nobody keeps a bad name out of fear.
- **Retiring** is for a procedure nobody should follow any more: `TASKS flow retire <name>`, kept for the record because past runs point at it. Never delete one. A flow that is merely out of date gets edited; retire is for one whose reason to exist is gone.
