# GUI steps — writing and running flows that drive a screen

A reference, not a verb. `flows/flow-create.md` reads it when a flow has steps done through a graphical interface (a web app, a desktop program, an OS dialog); `flows/run.md` reads it when a sequence needs one. Everything here sits on top of those flows and SKILL.md *Step marks* — it says how a GUI step is written and done, not when to stop for a `go`.

These rules cover the points where a GUI mistake costs something; ordinary navigation is left to the agent driving the screen.

## Writing a GUI step

- **Stable targets, most stable first.** Name where to go by a deep URL when the app has one (`https://app.example.com/billing/invoices?status=open`); otherwise by what a person sees — the visible label (`the "Export" button`) or the menu path (`Reports › Monthly › Export CSV`). Never by screen coordinates, pixel offsets, or "the third icon from the left": those break on the next window size or redesign. A target a step cannot name stably yet is said plainly, so a run or rehearsal fixes it.
- **Say what should be on screen where it matters.** Each GUI sequence says what should be on screen when it starts: the account or entity shown and the page (`the header reads "Unit 4B — 2026-09"`). A step repeats that only where landing on the wrong account or record is a real risk — after an account switcher, near a look-alike. Ordinary navigation gets none.
- **A visible postcondition after each state-changing action.** A step that saves, submits, uploads or changes anything says what proves it took (`a "Saved" banner`, `the row now shows status Paid`, `the invoice number appears in the list`). Read-only steps need none.
- **The confirm state is a filled, unsubmitted form.** The `[confirm]` step fills every field and stops with the submit button not yet pressed; pressing it is the next, separate step. The `go` is given on what is actually on screen, not on what the agent meant to type.
- **Full paths in OS save dialogs.** A step that saves or downloads through a system file dialog types the full destination path into it (`reports/{month}.csv` under the shared location the flow names), never trusting the dialog's last-used folder, and then checks the file landed there — exists, non-empty, the expected name.
- **Sign-in is an assumption, as everywhere.** "Assumes signed in to <app> in <environment>'s browser" — the session lives in that browser profile, never on the board (SKILL.md *Ground rules*, secrets).

## GUI expectations belong to the environment

What a place must provide for its GUI steps — which browser or profile holds the session, the app installed, a screen size or language the labels depend on, the download folder — goes in that environment's expectations: `TASKS env add|update <name> --expects "<prose>"`, or the `Expects:` line of an `Environment: inline` sequence. The flow's steps then name targets, not set-up; a run checks itself against those expectations before the first GUI step, like any other sequence (`flows/run.md` section 2).

## Running a GUI step

- **Check the context the flow wrote, and the record before a change.** Check each context the flow states where it states it, and make one quick check that the right account or record is on screen before any state-changing action. Navigation and reading need no ceremony. A mismatch is a stop: say what is on screen, and note it.
- **Verify the postcondition before going on.** No visible proof means the action did not take, as far as the run knows — report it as that (`flows/run.md`, *Never fabricate*); never retry a submit blindly, since it may have gone through once already (*Check before you act*).
- **A target that moved** — the label renamed, the menu reorganised — is found by what the step was for, then noted: `TASKS note <id> --at "<step>" "landmark moved: <old> → <new>"`.
- **Screenshots are optional, at checkpoints only, and never in the repo or on the board.** One can help a `[confirm]` show the filled form, or prove a postcondition. Where it is saved is up to the harness or the user, but never inside the repo, where one commit puts it in history for good; nor does it go into a task, a flow or a record. It can catch whatever else was on screen, secrets included. When a run keeps one, record it like any other file left outside the project (`flows/run.md`, the `file:` note).

## What a rehearsal or first run notes

A first pass through a GUI sequence is where its rough edges are cheapest to catch. Note each as it happens (`TASKS note <id> --at "<step>" "…"`), so the post-run tweak can write it into the flow:

- **Look-alikes** — two buttons, accounts, menus or records easily mistaken for each other, and what tells them apart.
- **Committing buttons** — anything that saves, submits, sends or pays on click, including ones whose label does not say so (`"Next" posts the payment`). Each needs a `[confirm]` step before it.
- **Landmarks** — the deep URL, label or menu path that reached a target the step could not name stably, and any that had moved. A target the step named and found needs no note.
- **Session quirks** — timeouts, re-sign-in prompts, two-factor interruptions, pop-ups or cookie banners in the way, a page that must load fully before it accepts input.

## After the run

Alongside the tweak in `flows/run.md` section 6, two offers specific to GUI steps, on the user's go-ahead:

- **An API route was found.** If the run found that a GUI step's job can be done through an API or CLI the environment can reach, offer to swap the step for it — repeatable and checkable beats driving a screen when both are equally reliable (`flows/flow-create.md`, *Goal and capability, not tools*). That is a structural edit: `/ops flow edit <name>`.
- **A landmark moved.** For each `landmark moved` note, offer the one-line fix to the step's target (`TASKS flow update <name> --file <path>`).
