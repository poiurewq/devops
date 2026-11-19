# /dev <id[, id…]> — the task lead

One sitting, one interface: this session is the **lead** for the task. It spawns an **implementer** and a **reviewer** as subagents and **takes the user's place** toward them: each is invoked with exactly what the user would type, runs its route unchanged, and puts its questions to the lead as it would to the user. The user sees only real decisions: forks, intent mismatches, and review findings.

**No subagents on this host** → say so once and run `/dev implement <id>` (`routes/implement.md`) instead.

**`unattended` after the ids** → not the lead: nobody is there to stand in for and there is no reviewer pass. Read `shared/routes/unattended.md` instead.

## Spawning

- **Implementer**: `/dev implement <id[, id…]>` — several ids: *Several ids* below.
- **Reviewer**: `/dev review <id[, id…]>`, always a **fresh** subagent with no implement context.

Both run on the lead's model tier (the tier, not an exact model version). When the lead knows the host spawns subagents on its own model, leave the default. Otherwise set the tier in the spawn call's model option, not in the prompt: a host default or an agent type's pinned model can quietly drop the work to a lower tier.

Add one line to each prompt and nothing else: *ask any question in your reply, not with a question tool* — otherwise its questions reach the user directly and skip the lead. Never tell a subagent it is working for a lead, and never brief it to skip, reorder, or stop short of its route. Ignore the implementer's new-session hint for review: the fresh reviewer is that new session.

## Several ids

Before any implementer starts, the lead runs `routes/implement-batch.md` steps 1–5 once for the whole set — eligibility, outside deps, order, preflight, `TASKS collisions <id,id,…>` — with their questions going to the user. A proceed on collisions exit 3 is recorded as a `Decision:` on every member, so no implementer asks it again. Then it picks one of two shapes:

- **Parallel**, only when both hold: collisions prints `parallel: ok`, and nothing in the task descriptions suggests a member could grow into another's files (predicted areas often widen at implement). One implementer per member, all spawned at once: `/dev implement <id>`.
- **One batch implementer** otherwise — any risk, even slight: `/dev implement <id, id, …>`.

Review waits until every member has shipped, then one reviewer takes the whole set: `/dev review <id, id, …>`. Parallel members carry no `Dev-batch:` stamp, and each keeps its own version bump: they are independent changes, only built at the same time.

## Answering as the user

A subagent's question arrives as its reply; the lead's answer continues it. The lead answers on its own only what is already settled — by the task body and its `Intent:` and `Decision:` lines, by an `AGENTS.md` heuristic (record it `Decision: … (heuristic: <name>)` and list it as `decided`), or because it is a plain bug fix (a crash, a typo, a wrong path) nobody would discuss. Everything else goes to the user, gathered into one message where several are pending, and the user's answer goes back as given.

**New requests in a reply.** When the user's reply also asks for changes beyond the questions it answers, the lead judges each one first. A small one within the task's scope (its body and last `Intent:`) goes to the subagent as given. A sizable one, or any beyond that scope, is new work: the lead reasons about its premise as `shared/routes/add.md` *Premise* says, gives its own take, and settles the shape with the user before relaying — beyond scope, that includes the user's choice to defer it as a new task (`/dev add`) or widen this one (`TASKS update <id> --append`, with a `Decision:` line). Only the settled shape goes to the subagent.

**Never the lead's call:** a `go` on any wave that includes `TASKS ready` or `TASKS land`, any fork nothing above settles, and anything `routes/implement.md` or `routes/review.md` reserves for the user. Those wait for the user's own `go`.

## The sitting

1. **Route.** `TASKS show <id>`. `kind: umbrella` → the lead runs its verification pass itself (`shared/routes/verify.md`), no subagents. `type: ops` → `/ops run <id>`. `draft` or `review` → step 3. Anything else → step 2. Routing is by status only: who may touch the task, and which states stop work, are `routes/implement.md`'s and `routes/review.md`'s to judge — when a subagent stops, relay its reason to the user as given.
2. **Premise, then implement.** For a `backlog` or `planned` task that adds behavior, spans several files, or opens design surface, the lead first reads the code it touches and says in a few lines whether the premise holds — already solved, superseded, wrong layer, or a clearly better path to the intent. The user decides proceed, reshape, or drop, and the check ends `Reply "go" to proceed, or say how to reshape or drop it.` — the same `go` as every other lead checkpoint. Mechanical tasks skip this. Then spawn the implementer (several ids: *Several ids*). It runs the whole implement route — gates, claim, build, ship to `draft` — so the work is pushed before review.
3. **Review.** Visual work first goes through *Look and feel* (below), whether it just shipped or reached this step already in `draft` or `review`. Then spawn the reviewer. It checks intent first (`routes/review.md`), then the rest, and ends with numbered findings and a proposal line. The lead relays them to the user with any `decided` forks, keeping the numbering and adding the labels below; plain bug fixes it may approve itself, saying so. The user's reply goes back to the reviewer as given, except sizable or out-of-scope requests (*Answering as the user*) and the wave (step 5). On the user's own draft the reviewer makes the fixes and re-ships (`routes/review.md`).
4. **Another round?** The lead's judgment, stated in one line with its reason. The intent: a fresh reviewer earns its cost when the fixes carry real risk. Size is one sign (structural changes, new or reworked logic), but a small change in a sensitive spot counts too. Low-risk fixes, such as doc or wording edits, skip it. Cases in between are the lead's call. The user can always ask for one.
5. **Hand-off.** The reviewer's proposal line carries whatever wave `routes/review.md` proposes — `ready`, `land`, or an approve. Relay it, and act on it only when the user said `go`. **A wave with `ready` or `land` the lead runs itself**: the user approved it in the lead's own session, and a subagent cannot take that approval from another agent, so a relayed `go` stalls there. Pass the reviewer the rest of the reply with the wave held back in plain English (`fix 1, 3 · leave 4 · don't ready or land yet`); once its fixes are re-shipped and step 4's round, if one is run, comes back clean — or at once when there are no fixes — the lead runs the wave from the proposal line, following `routes/review.md`'s land steps, or `routes/review-batch.md`'s for several ids. New findings from that round go back to the user first. An approve or anything else in the wave goes back to the reviewer as given. Report what shipped, the PR, and where it stands.

## Look and feel

For a task that makes major changes to a visual or interactive surface — a GUI or a terminal UI; the lead judges what counts — the user looks at the running build before any reviewer is spawned, since visual and affordance problems only a human eye catches are cheaper fixed in quick rounds than found in review. Several ids: the members that qualify go through it together, before the one reviewer.

1. **Put the build in front of the user.** Where the lead can launch it (the app, the TUI, a page), it does, from the task's `product` dir — never the hub, which is integration (`TASKS diff <id>` prints where the task worktree is). Otherwise it boils the launch down to one command the user can paste. Then it asks for what they see, ending `Reply "go" once it looks right, or say what to change.`
2. **Each round's feedback** is handled as *New requests in a reply* says, with the lead's own design take on each request as in `shared/routes/add.md` *Premise* — a better fix than the one asked for, or one already on the board, is said before relaying. The agreed requests go to the implementer — the same one if it can still be continued, otherwise a new `/dev implement <id>`, which resumes the draft — given as the user would give them, to build and re-ship.
3. **Repeat** with the re-shipped build until the user is satisfied, then go on to the reviewer in *The sitting* step 3.

## A scheduled sitting

A sitting an attended routine's wake starts reaches the user as `shared/routes/wake.md` *A scheduled run* says, running as above up to the first thing that needs the user — the premise check's `go`, a question the lead cannot answer itself, a *Look and feel* round, the review findings or a wave. The wake's provenance tag goes to the implementer for the shipped record.

- **Before ship** (the premise check, a fork) → park it on the task, as wake.md says.
- **After ship** (a look-and-feel round, findings, a wave) → nothing is parked: the user's own draft already shows in their `/dev review` inbox. Notify and wait all the same.
- A session that ends first leaves it on the board: `/dev decide <id>` decides a parked question (`shared/routes/decide.md`), and `/dev <id>` picks the task back up (*Cut off partway*).

## Labels the lead adds

On top of `routes/review.md`'s set, in the lead's messages to the user:

- **decided** — settled by a named `AGENTS.md` heuristic and already recorded; shown so the user can override.
- **discuss** — the user's opt-in, never the lead's default: the lead talks that finding through with the reviewer (and the implementer, if the user asks) against the product's broader design — its `AGENTS.md`, neighbouring flows, decided rules — as a user would, then returns with one proposal for it.

The key line must say `discuss` involves the other agents, so it cannot be read as `ask`:

```
Proposed: fix 1, 3 · decided 2 · leave 4 · ask 5
(fix = change it now · decided = settled by a heuristic, override if you disagree · leave = no action · ask = your call · discuss = I talk it through with the reviewer/implementer, then propose)
Reply "go", or say what to change; answer 5 as "5: …".
```

## Cut off partway

Everything durable is on the board or origin: `Decision:` lines, the shipped draft, its records. `/dev <id>` routes back in by state — an unshipped task to a new implementer (implement resumes a `doing` task), a shipped one to a fresh reviewer (after *Look and feel* for visual work). Review results are never carried over from an earlier session, only re-run.
