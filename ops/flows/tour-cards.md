# ops tour cards

The ops-only cards of the tour (`shared/flows/tour.md` says how to give them).

6. **Flows.** A flow is a written, named procedure — how you close the month, onboard a client — kept in `.flows/` and shared like the board, and it outlives the tasks that run it. — See it: `TASKS flow list`.
7. **Runs and checkpoints.** A run is one pass of a flow against a task: each step is marked `[agent]`, `[user]` or `[confirm]`, the run stops for your `go` before anything goes out, and it closes with a record of what it was given and what went differently. — See it: `TASKS flow runs <name>`, or the `Ran:` line on a done task.
8. **The playbook is written by using it.** No flow yet is the normal start: the run goes a chunk at a time, notes what you actually did, and can be kept as a flow at the end; every later run is a chance to sharpen it. — See it: `f` in `./board` opens the flows pane, each flow with its run history.
9. **Sequences: when work changes hands.** A flow can split into sequences, each saying where it runs (an environment) and who usually does it (an agent), so a run knows when to hand a stretch to another machine or agent. A new place is described inline in the flow until a run has tested what it really needs; then it is registered by name for every flow to use. — See it: `TASKS env list` and `TASKS agent list`.
