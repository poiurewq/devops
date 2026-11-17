## Umbrella close

**An umbrella is never auto-closed.** Its children all being `done` says the work happened, not that the goal was met — separating those two judgments is the whole reason the umbrella exists. So no flow, and no agent, closes one off a status rollup: `TASKS update <id> --status done` on a `kind: umbrella` task is **refused**, and closing it has its own verb instead — `TASKS verify <id> "<how the children met the goal>"`, which records `Verified (<date>): …` in the body and closes the task. That record is carried into `log.md` at iteration close (an umbrella never ships or runs, so it is its only outcome line).

The pass itself is `shared/flows/verify.md`, which `/dev <id>` and `/ops run <id>` both route an umbrella to, whatever its type. It reads each child's own outcome record against the umbrella's last `Intent:` and ends in the same session, either filing the gaps as new children or closing with the record — no branch, no PR, no review. Anyone may run it — typically whoever filed the umbrella and knows its intent; unlike `land`, it is not integrator-only. An unattended run never runs it.

`meta` never proposes closing an umbrella. When one looks complete it says the goal check is **due** and worth prioritizing, and points at the pass.
