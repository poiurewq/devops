# /<skill> init — identity, board creation or joining

`/<skill>` is the skill in use. One board serves both skills, so whichever runs init sets it up for both: a board created here holds dev and ops tasks alike, and joining it once is enough. Works from whatever branch the user happens to be on: board writes go through the script's hidden worktree, never the checkout.

## Prerequisites

Every board needs all three; help the user with any that is missing before going further.

- **At least one commit** — the script pins its board worktree to the integration branch's tip; on a brand-new repo, make an initial commit first.
- **A GitHub remote named `origin`** — the board syncs through it, so every contributor on any machine sees the same board, and dev tasks land through pull requests on it. Without one, board commits only queue locally.
- **`gh` installed and signed in**, with a network connection — a handle is tied to a GitHub login, and init reads it through gh and refuses without it. Go by what the script reports, never a gh check of your own. Only then: `gh` missing → point at https://cli.github.com (`brew install gh` on macOS); not signed in → walk them through `gh auth login`. Init stops until gh is signed in (or `DEVOPS_GITHUB_LOGIN` is set); re-run it after setup.

**The agent harness can gate the merge too.** `land`, `cleanup` and `iteration-land` merge a pull request or delete a branch, which a permission or safety layer may refuse even when `gh` is fine. They are agent-run by design, so a refusal strands finished work at the last step. Say it once here: if any of them is ever refused, allow those commands wherever this harness configures permissions — never hand-roll the merge around it.

## Steps

1. **Identity**: a handle is tied to one GitHub login, and one login holds one handle per board. The script reads the login — `DEVOPS_GITHUB_LOGIN` if set (cloud or CI), else the account `gh` is signed in as — and init refuses when it cannot read one, so fix that first (usually `gh auth login`): there is no handle without a login. Nothing is stored per checkout: whoever the login is on the roster is who you are. Skip if `TASKS whoami` already prints a handle for the target board and the user isn't asking to change it. In a monorepo, each product board has its own roster (same handle is fine — join each with init).
   - **Existing board**: run `TASKS init` with no `--name` first. When the login is on the roster it joins as that handle — tell the user which handle they are; no prompt. When it says the login is not on the roster, ask which applies: **new** to this board → ask for a handle, offering the login as the suggestion (their own contributor name is fine; it stays distinct from the login), then `TASKS init --name <handle>`; **already a contributor** under another GitHub account → `gh auth switch` to that account and re-run init.
   - **New board**: ask for a handle the same way, login suggested.
   - Never suggest a name from the board's roster — those are other people. Init refuses a handle another login holds, or a second handle for this login; surface that error and ask again.

2. **Scope** (monorepo support): if the repo hosts several products and the user wants a board for a subdir, confirm which one and pass `--scope <subdir>`. Default (no `--scope`) is the nearest board at or above cwd, else the repo root (create path only). Day-to-day commands require cwd under the product or `--scope`. Don't create scoped boards unprompted — one root board is the norm for a single-product repo.

3. **Existing board** (`.tasks/board.yml` present for that scope): the step 1 init joins it — registering a new contributor, or recording the login on a handle registered before logins were kept. Then run *AGENTS.md pointers* (below) and offer the tour (step 7). Done.

4. **New board**:
   - *Integration branch*: propose the current or default branch; if the repo already uses iteration branches, ask which. Pass `--integration` (and `--parent`, `--iteration N`, `--iteration-name`, `--iteration-started` when applicable — a parent branch only when the user asks for one, `shared/routes/iteration.md`).
   - Run `TASKS init --name <handle> [--scope s] [--integration b] [--parent p] [--iteration N] [--iteration-name <name>] [--iteration-started YYYY-MM-DD]`. It also writes the gitignored `./board` viewer at the product root (keys: SKILL.md *State layout*).
   - *Areas* are the repo's to decide, not the skill's: they lock regions of code, so a repo with code gets them and one without gets none. **Code present** → first give the user this primer (verbatim or near):

     > Areas are coarse labels for regions of the codebase. Every code task gets tagged with the area(s) it will touch. They keep the board organized — but their real job is coordination: dev steers contributors away from working in the same area at the same time, which is what prevents merge conflicts. More areas enable more concurrent work; there is no fixed upper bound. The natural limiter is multi-area occupancy — propose as many stable areas as enable parallelization without typical tasks needing many areas at once (over-granularity → confusing multi-area tags).
     >
     > Prefer names that mirror the tree when the work splits by path: shortest unique path, no filename extensions (`billing/api`, not `billing/api.go`; `cli` if only one). A name with `/` is a path; parents are implied by segments. A parent listed in areas.md (`billing`) locks the whole subtree; tag that parent or the specific children, not both, and prefer children. One-offs go to `billing/other`, not the parent. Do not list a parent until you need the wide lock or it already has children. Cross-cutting work that is not a path still gets a short slash-free phrase (`docs`, `ci`). No trailing slashes and no leading `./`. Areas can be added later when tasks start clustering.

     Then scan the top-level structure and propose areas with that parallelization heuristic and path-preferring names (no hard count cap), each `TASKS area set <name> --desc "<one line>"`, the user trimming or confirming first. **No code yet** → none; they appear later per the rule above.

5. **The first work, offered in one line**: `/<skill> add <task-or-goal>` files it, `/<skill> flow create` writes down a procedure they already have, and `/<skill> absorb <source>` imports a list of things to do that already lives somewhere (a TODO file, a roadmap, an issues dump).

6. Run *AGENTS.md pointers* (below), then report what was set up: scope, integration branch (and parent, if any), identity, integrator, areas, gh status, that `origin` syncs it, and the `./board` viewer.

7. **Offer the tour**, once, as the last line: `/<skill> tour` walks through how it works, a card at a time. Offer only — never start it unasked.

## AGENTS.md pointers

Runs on every init, joining or creating, so an agent opening this repo cold learns the board exists and where the skill comes from, and reaches for an existing flow instead of improvising one. Both pointers live in the product's own `AGENTS.md` (the `--scope` dir, else the repo root); a `CLAUDE.md` follows SKILL.md *Ground rules* (vendor-neutral context).

- **Custody line**: this repo's work is managed with devops (`/dev`, `/ops`; board in `.tasks/`), with https://github.com/poiurewq/devops for agents without the skill.
- **Flows clause**: when no skill covers what the user asks, check `/ops flow list` for an existing flow and suggest `/ops run`-ing it.

1. Read that `AGENTS.md`, or a lone `CLAUDE.md` when there is no `AGENTS.md`, and note which pointers are missing. No file means both are.
2. **A gitignored file is the user's private copy**: `git check-ignore -q <file>` on the file just read (`AGENTS.md` when neither exists) exits 0 → skip the board entirely and offer to add the missing pointers to that file directly, worded as above. Nothing is filed and no PR is needed; on no, nothing is recorded and the next init asks again. Otherwise go on.
3. `TASKS related "AGENTS.md devops pointer flows"`: drop any pointer a task already on the board covers, shelved ones included, so several people initing one board do not each file it and a declined offer is not asked again. Nothing left ends the check.
4. Offer to file **one** dev task covering what is left — never edit a tracked `AGENTS.md` here: the change goes through a PR like any change, and whether the user's agent instructions get it is their call. On yes, file it with `TASKS add --title "Add devops pointers to AGENTS.md" --desc "<desc>"`: the description asks for the pointers left, worded as above, and ends with an `Intent:` line — an agent opening this repo cold knows the board exists and where to get the skill, and points the user at a matching ops flow instead of improvising one (keep only the halves that apply). No area yet; implement asks for one. On no, file it anyway and shelve it with their reason — `TASKS update <id> --status shelved --reason "<why, in their words>"` — so the next init's board check finds it and stays quiet; `--status backlog` revives it.
