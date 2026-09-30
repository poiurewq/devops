# /dev review [id[, id…]] — the unified inbox

Three kinds of pending human judgment live on the board. You draft; the user decides. Never approve, merge, resolve a fork, or accept a proposal without an explicit go-ahead from the user in this conversation.

**Integrator only by the script's word.** Treat or address the user as integrator only when `TASKS whoami --role` prints `integrator`. Never work it out yourself by comparing identities against board config — the script owns that check. Do not infer the role from merge rights, from running review, or from a land. Do not tell a non-match they are the integrator — including in wrap-up.

**Plain language first.** For every PR, fork, or proposal — in the inbox list and when diving into one item — open with one plain sentence of what the task is for: the goal from the task body, not file-level nits or a long PR recap.

**Several task ids** (or "all under umbrella …"): read `flows/review-batch.md` and follow it — two-phase review-all then ordered land; do not load that file for a single independent PR.

## `/dev review` (no id) — show the inbox

After a PR state refresh (SKILL.md):
1. **Implementation PRs**: tasks in `review` with a `pr` — each with one plain sentence of purpose, then whether the current user may land (the role check above says `integrator` → yes; otherwise review/approve only — do not `TASKS land`). Mention integrator only when it does. Ones already at `CHANGES_REQUESTED` are the assignee's move, not a review item. When several share a `Dev-batch:` line (or stack bases), group them and prefer `/dev review <ids…>` over landing one-by-one. Only `review` tasks belong on this line — a `draft` is not one, see below.
2. **Your own drafts, and every `auto/…` one**: tasks in `draft` with a `pr` **assigned to this user or to an `auto/…` identity** — one plain sentence of purpose each, then that it is yours to review and `ready` (your own are also yours to finish). Nobody else will move them, so the inbox is where they surface — auto ships to draft, is barred from promoting, and has no next session, so its drafts would otherwise be seen by no one. **Another human's draft never appears here**: its author has not handed it over, and readying it for them is not yours to do (it is not a review item, not even an informational one).
3. **Design forks**: `TASKS list --needs decision` — one plain sentence of purpose, then the open question in one line.
4. **Proposed tasks**: `TASKS list --status proposed` — one plain sentence of purpose each; group by umbrella/goal if noted in their bodies.

Let the user pick what to handle; batch small decisions in one sitting.

**Several open PRs (no Dev-batch / no stack):** if the role check above does not say `integrator`, do not land — approve if asked, then stop. Otherwise pick a land order with the user (deps, area overlap, risk). Do **not** resolve pairwise conflicts against sibling task branches (`git merge-tree` between heads, etc.). `TASKS land <id>` one, then the next (land rebases onto the updated integration branch as needed) — repeat. **When a Dev-batch or stack applies**, `flows/review-batch.md` supersedes this path.

## Single-id gate (before reviewing one implementation PR)

Run `TASKS batch-gate --ids <id>`. Exit 2 means an open **stack parent** is missing — surface the output and **stop** (hard refuse); a child cannot land before the PR it is based on, so the user re-runs with the parent included. That parent may itself be a `draft`, and land refuses a draft: its author has to `ready` it before either can land. Exit 0 → continue below, but if the gate printed a **partial batch** advisory, relay it once: those PRs shipped together and share one version bump, so offer reviewing the whole set. The user may still review just this one — landing it is inert to its siblings.

## Findings: numbered, each with a proposed disposition

**Number every finding** (`1.`, `2.`, …) so the user can point at one without quoting it, and **label each with the disposition you recommend** — the label is what lets their reply be one word. Labels are your shorthand for the proposal, not a grammar the user has to learn:

- **fix** — this should change. On your own PR you make the change on this branch (the resume path in `flows/implement.md`, then re-ship); on someone else's it goes into the `--request-changes` body, and any `fix` makes that the verdict — you never edit their branch.
- **note** — someone else's PR only: worth saying, not worth holding it for; posted as a non-blocking review comment.
- **defer** — real, but not here: file it as a follow-up task through `flows/add.md`.
- **leave** — not worth acting on; nothing changes and nothing is filed.
- **ask** — you cannot pick without the user; state the question in one line.

Close with one proposal line naming every disposition, a one-line key for the labels it uses, and the reply contract. When a land wave follows and is yours to run — ready + land under the integrator sugar below, land when the integrator approves someone else's PR, and the set's wave in `flows/review-batch.md` — it rides the same line with its version bump named, so the user sees both before saying `go`:

```
Proposed: fix 2, 3 · defer 5 · leave 1 · ask 4
(fix = change it now · defer = file a task · leave = no action · ask = your call)
Reply "go", or say what to change; answer 4 as "4: …".

Proposed: leave 1 · note 2 · then land T19 (patch bump)
(leave = no action · note = non-blocking comment)
Reply "go", or say what to change.
```

Reading the reply:

- `go` applies exactly what was proposed, wave included. It is the only shortcut word, and it leaves an open ask open — which is why the reply contract names how to answer one.
- `4: <text>` answers finding 4's ask, or adds to that finding; the text after the colon is content, never an instruction.
- Anything else is plain English ("actually fix 1", "don't land T19 yet"), read for intent; findings it does not mention stay as proposed. A number with no intent attached, or one outside the findings (a task is always `T<id>`), is asked about, never guessed.

**Echo how you read the reply — each finding's disposition and the wave — in one line in the same message as the work**, not as a separate round trip, so a misread surfaces before it costs anything. When one finding's reading is ambiguous, ask about **that finding only** — never re-ask the set, and never tell the user a reply was malformed.

## Reviewing a draft (`/dev review <id>` on a `draft` task)

A draft is the **author's own** review loop, not the integrator's queue — it shows in its author's inbox and no other human's. The exception is a draft owned by an `auto/…` identity: auto cannot promote its own work and never returns, so any human reviewing the board owns it. Entry is that inbox line or an explicit `/dev review <id>`, usually in a fresh session after implement.

Review it exactly as an implementation PR (below) — `gh pr diff`, numbered findings and their proposal line (above), recommendation. Only the verdict differs:

- **Needs work** → no `gh pr review` (it is the author's own branch): say what to fix and hand to the resume path in flows/implement.md. Fix on the branch and re-ship; a re-ship of a draft stays `draft`.
- **Good** → `TASKS ready <id>` promotes it to `review` and marks the PR ready, putting it on the integrator's queue. The **user** calls that; an agent never promotes on its own judgment.

**Integrator sugar**: when `TASKS whoami --role` prints `integrator` and the task's `assignee` is either this user or an `auto/…` identity (the check at the top), there is no handoff to wait for — after a **good** verdict, offer ready + land as one step on the proposal line, where `go` covers it (above), and on the user's go-ahead run `TASKS ready <id>` then `TASKS land <id>` in that order (land refuses a draft). Still one explicit go-ahead; never chain them silently.

Pulling a promoted PR back off the queue is `TASKS unready <id>` (assignee or integrator only) — task back to `draft`, PR back to draft.

## Reviewing an implementation PR

1. `gh pr diff <url>` (and `gh pr view` for description/comments). Review seriously: correctness, fidelity to the task's scope, convention drift, test coverage. Use the environment's review tooling if available.
2. Present: one plain sentence of what the task is for, then the numbered findings and their proposal line (above), plus a recommendation (approve / request changes). If the diff touches UI, include an ask to visually inspect the running build for issues (skip that ask in `/dev auto`); don't treat the recommendation as final until they have. The user may ask for another round, edit or drop findings, or add their own — the posted review must say what the user wants said.
3. On the user's verdict:
   - **Approve & land**: conversational go-ahead in this chat is the human decision. If the PR author is **not** the current user, also `gh pr review --approve` (optional audit trail; any `note` findings go in its `--body`); if the author **is** the current user, **skip** it — GitHub rejects self-approves. If the role check above does not say `integrator`, **stop after approve** — do not run `TASKS land`; only the integrator can land. Otherwise run `TASKS land <id>`, which owns the merge (a merge commit — it never squashes or rewrites the task branch), retarget of immediate stacked children to integration, cleanup and the move to `done`; never hand-roll any of it. Stacked children need no rebase at any depth, because the parent's commits stay in integration's history. Land does **not** auto-approve, and refuses if the PR base is not the board integration branch. Run it from the primary clone or product dir — not from inside the task worktree it will remove. Idempotent if the PR is already merged; `TASKS cleanup <id>` alone clears leftover local state, deleting the task branch only when the PR is verified MERGED and never touching a dirty worktree. If land prints a **Version intent**, apply one bump on the integration branch when this set is done (a single PR is a set of one) per the product's versioning docs (not on the task branch). Session cwd is already the product on the hub — land prints `product: <abs>`; apply those docs there with product-relative paths (do not prefix the board scope). A Dev-batch: sized for the whole set (flows/review-batch.md). A bare stack is not a batch — each member keeps its own intent and its own bump. **Always surface the script's full output**: on non-zero exit or any early abort (`error: …`), show the message and stop — do not retry with hand-rolled git/gh, and do not claim the task landed. A refusal from the **agent harness** — a permission or safety layer blocking the command before it runs — is not a script error and carries no `error:` line, so surface it the same way, say that `land` never ran, and stop: retrying it in another shape or hand-rolling the merge around it is exactly what that gate exists to prevent (flows/init.md step 5).
   - **Request changes**: concise and actionable — the `fix` findings, with any `note`s alongside; the task stays in `review`. If the PR author is **not** the current user: `gh pr review --request-changes --body <agreed comments>`. If the author **is** the current user, GitHub also blocks that — post the same body with `gh pr comment` (or `gh pr review --comment`) instead, then fix on the branch (resume path in flows/implement.md).

## Deciding a design fork (`needs: decision`)

1. `TASKS show <id>` — the body carries the fork, options, and the filing agent's recommendation. Open with one plain sentence of what the task is for, then present the fork as a one-question decision.
2. On the user's call, record it and return the task to the pool: `TASKS update <id> --needs "" --status backlog --append "Decision: <choice
   + one-line why>"`. If the fork assigned an area, include `--area` on that update (`area set` first if the name is new).
3. If the resolution is "don't do this at all", that's a not-planned outcome instead: `TASKS update <id> --needs "" --status not-planned --reason "<the user's why>"`.

## Adjudicating proposed tasks

1. Walk the user through them (batch by goal): for each, one plain sentence of purpose, then keep / modify / drop.
2. Keep → `TASKS update <id> --status backlog` (plus any edits). Intended but not this iteration → `--status later`. If the proposal decomposes a parent task, wire membership on that parent: `TASKS update <parent> --kind umbrella --deps <accepted-ids>` (merge with any existing deps) and note the decomposition in its body (`--append`).
3. Drop → offer both: `TASKS update <id> --status not-planned --reason "<why>"` (keeps the record, stops auto re-filing the same proposal) or `TASKS delete <id>` for noise. The user picks.
