# /dev <id[, id…]> — the task lead

One sitting, one interface: this session is the **lead** for the task. It spawns an **implementer** and a **reviewer** as subagents and **takes the user's place** toward them: each is invoked with exactly what the user would type, runs its flow unchanged, and puts its questions to the lead as it would to the user. The user sees only real decisions: forks, intent mismatches, and review findings.

**No subagents on this host** → say so once and run `/dev implement <id>` (`flows/implement.md`) instead.

## Spawning

- **Implementer**: `/dev implement <id[, id…]>`.
- **Reviewer**: `/dev review <id[, id…]>`, always a **fresh** subagent with no implement context.

Both run on the lead's model tier (the tier, not an exact model version). When the lead knows the host spawns subagents on its own model, leave the default. Otherwise set the tier in the spawn call's model option, not in the prompt: a host default or an agent type's pinned model can quietly drop the work to a lower tier.

Add one line to each prompt and nothing else: *ask any question in your reply, not with a question tool* — otherwise its questions reach the user directly and skip the lead. Never tell a subagent it is working for a lead, and never brief it to skip, reorder, or stop short of its flow. Ignore the implementer's new-session hint for review: the fresh reviewer is that new session.

## Answering as the user

A subagent's question arrives as its reply; the lead's answer continues it. The lead answers on its own only what is already settled — by the task body and its `Intent:` and `Decision:` lines, by an `AGENTS.md` heuristic (record it `Decision: … (heuristic: <name>)` and list it as `decided`), or because it is a plain bug fix (a crash, a typo, a wrong path) nobody would discuss. Everything else goes to the user, gathered into one message where several are pending, and the user's answer goes back as given.

**Never the lead's call:** a `go` on any wave that includes `TASKS ready` or `TASKS land`, any fork nothing above settles, and anything `flows/implement.md` or `flows/review.md` reserves for the user. Those wait for the user's own `go`.

## The sitting

1. **Route.** `TASKS show <id>`. `kind: umbrella` → the lead runs the verification pass in `flows/implement.md` itself, no subagents. `type: ops` → `/ops run <id>`. `draft` or `review` → step 3. Anything else → step 2. Routing is by status only: who may touch the task, and which states stop work, are `flows/implement.md`'s and `flows/review.md`'s to judge — when a subagent stops, relay its reason to the user as given.
2. **Premise, then implement.** For a `backlog` or `planned` task that adds behavior, spans several files, or opens design surface, the lead first reads the code it touches and says in a few lines whether the premise holds — already solved, superseded, wrong layer, or a clearly better path to the intent. The user decides proceed, reshape, or drop, and the check ends `Reply "go" to proceed, or say how to reshape or drop it.` — the same `go` as every other lead checkpoint. Mechanical tasks skip this. Then spawn the implementer. It runs the whole implement flow — gates, claim, build, ship to `draft` — so the work is pushed before review.
3. **Review.** Spawn the reviewer. It checks intent first (`flows/review.md`), then the rest, and ends with numbered findings and a proposal line. The lead relays them to the user with any `decided` forks, keeping the numbering and adding the labels below; plain bug fixes it may approve itself, saying so. The user's reply goes back to the reviewer as given, except the wave (step 5). On the user's own draft the reviewer makes the fixes and re-ships (`flows/review.md`).
4. **Another round?** The lead's call, stated in one line with its reason: fixes that added logic or touched new files go to a fresh reviewer; trivial ones do not. The user can always ask for one.
5. **Hand-off.** The reviewer's proposal line carries whatever wave `flows/review.md` proposes — `ready`, `land`, or an approve. Relay it, and act on it only when the user said `go`. **A wave with `ready` or `land` the lead runs itself**: the user approved it in the lead's own session, and a subagent cannot take that approval from another agent, so a relayed `go` stalls there. Pass the reviewer the rest of the reply with the wave held back in plain English (`fix 1, 3 · leave 4 · don't ready or land yet`); once its fixes are re-shipped and step 4's round, if one is run, comes back clean — or at once when there are no fixes — the lead runs the wave from the proposal line, following `flows/review.md`'s land steps, or `flows/review-batch.md`'s for several ids. New findings from that round go back to the user first. An approve or anything else in the wave goes back to the reviewer as given. Report what shipped, the PR, and where it stands.

## Labels the lead adds

On top of `flows/review.md`'s set, in the lead's messages to the user:

- **decided** — settled by a named `AGENTS.md` heuristic and already recorded; shown so the user can override.
- **discuss** — the user's opt-in, never the lead's default: the lead talks that finding through with the reviewer (and the implementer, if the user asks) against the product's broader design — its `AGENTS.md`, neighbouring flows, decided rules — as a user would, then returns with one proposal for it.

The key line must say `discuss` involves the other agents, so it cannot be read as `ask`:

```
Proposed: fix 1, 3 · decided 2 · leave 4 · ask 5
(fix = change it now · decided = settled by a heuristic, override if you disagree · leave = no action · ask = your call · discuss = I talk it through with the reviewer/implementer, then propose)
Reply "go", or say what to change; answer 5 as "5: …".
```

## Cut off partway

Everything durable is on the board or origin: `Decision:` lines, the shipped draft, its records. `/dev <id>` routes back in by state — an unshipped task to a new implementer (implement resumes a `doing` task), a shipped one to a fresh reviewer. Review results are never carried over from an earlier session, only re-run.
