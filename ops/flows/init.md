# /ops init — identity, board creation, joining

## Step 0 — welcome (first contact only)

When the user arrived via bare `/ops` or `/ops help` and this project has no board, open with the following **verbatim** — don't paraphrase, don't extend; only trim a section if the user has made clear they already know it:

---
**Welcome to ops** — a shared board for the work that isn't code, plus a playbook of the procedures you run over and over.

**What it is.** A **flow** is a written procedure: how you close the month, onboard a client, publish an issue. A **run** is one execution of it, recorded on the task it was run for — inputs it was given, anything that went differently. Both live in small files inside your project, synced through git, so every contributor on any machine sees the same board and the same playbook.

**How it works.** You file what needs doing. When you run a task, I find the flow that fits, ask for anything it needs, and walk it with you — checking in where the flow says to, and once more at the end before anything is marked done. No flow yet? We do it a chunk at a time, I write down what we actually did, and you can turn that into a flow at the end.

**The philosophy.** The playbook is written by using it. Procedures start rough and get sharper every run, and you approve every step that matters. Nothing is marked done because the steps ran out — only because you said the aim was met.

Want me to set it up here? It takes about a minute — a name for attribution, and that's nearly it.
---

If they accept, continue below. If they decline, point at `/ops help` for later and stop — don't set anything up unasked.

Works from whatever branch the user happens to be on: board writes go through the script's own hidden worktree, never the checkout.

Prerequisites: a git repository with at least one commit, and a remote named `origin` if the board is to be shared across machines or people. Without a remote, board commits queue locally and sync to nobody — fine for a solo trial, worth saying plainly. Ops opens no pull requests for tasks, so it needs no GitHub CLI — with one exception: a board configured with a parent branch merges each closed iteration into that parent through one pull request, which needs an authenticated `gh` (`flows/iteration.md`). A new board has no parent unless the user asks for one. The agent harness may gate that command separately, since it merges a pull request: if `iteration-land` is refused, allow it wherever this harness configures permissions.

1. **Identity**: ask for a short stable handle (suggest one derived from `git config user.name`, never from the board's existing contributors — those are likely other people). Identity is per project (`<scope>/.dev/identity`). Skip if that file already exists and the user isn't asking to change it.

2. **Scope**: if the repo holds several projects and the user wants a board for a subdir, confirm which and pass `--scope <subdir>`. Default is the nearest board at or above cwd, else the repo root. Don't create scoped boards unprompted — one board is the norm.

3. **Board already exists** (`.tasks/board.yml` present for that scope — including one `/dev` created): just run `TASKS init --name <handle>`. It joins and registers the contributor. Say that the board is shared: their ops tasks and any dev tasks live side by side, marked. Done.

4. **No board yet**: propose the current branch as the board's home (`--integration <branch>`; `main` is the usual answer, and a board that lives on `main` never has to be closed or landed). Then `TASKS init --name <handle> [--scope s] [--integration b]`. This also writes a gitignored `./board` viewer at the project root (`r` refresh, `f` flows pane, `q` quit, arrows scroll, type an id + Enter).

   **No areas.** Areas are a `/dev` concept for locking regions of a codebase; ops tasks carry none, and the script refuses one on an ops task. Don't propose them.

5. **First flow — offer, don't build.** A new playbook is empty, and that is the normal state: flows are written from runs, not up front. Say so, and offer the two ways in: `/ops add <task-or-goal>` then `/ops run <id>` (the run writes itself down as it goes, and at the end you can keep it as a flow), or `/ops flow create` now if they already have a procedure written down somewhere. A list of things to do that already lives in a document is `/ops absorb <source>` (`flows/absorb.md`).

6. Report what was set up: project, board branch, identity, whether a remote is syncing it, and the `./board` viewer.
