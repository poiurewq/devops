---
name: dev
description: Multi-contributor task board and dev workflow for a repo, or per-subdir boards in a monorepo. Use for /dev and subcommands (init, tour, add, plan, board, kanban, status, pick, implement, review, decide, audit, next, wake, schedule, absorb, flow list/show/create/edit/review/retire, agent, env, catalog, routine, change, delete, show, config, area, meta, iteration, distill, update), and whenever the user asks to add/see/assign/implement/review tasks on the repo's task board, or asks "what should I work on".
---

<!-- Built from src/ by src/build.py: edit there, then rebuild. -->

# dev — coordinated development for humans and agents

One task board per product (a repo, or a subdir of a monorepo), shared by every contributor — human or agent — across worktrees and machines. You are the interface: parse intent, run the script for all board state, apply judgment yourself. When the routing table names a `routes/*.md`, read that file and follow it — don't improvise the route.

`SKILL_DIR` = the directory containing this file.

`TASKS` = `SKILL_DIR/scripts/tasks.py` (an executable shim — one word, so it survives being stored in a shell variable; never prefix `python3`), run from inside the repo. It targets the nearest board at or above cwd, or `--scope <subdir>`; there is no single-board fallback, so in a repo of several products, work runs from the product directory.

If running a shim (`TASKS` or `SKILL_CMD`) directly fails with `permission denied` (the file modes were lost, e.g. a synced skills dir), that is not a script error: use `python3 SKILL_DIR/scripts/<name>.py …` for that call and every later one this session, spelled out each time, never stored in a shell variable.

On Windows (native Python with Git for Windows), never run a shim directly: run every call as `py SKILL_DIR/scripts/<name>.py …`, spelled out the same way. `board --watch` does not run there; plain `board` prints the board. A board with scheduled recurring tasks needs the timezone database (`py -m pip install tzdata`), which the script names when it is missing.

`SKILL_CMD` = `SKILL_DIR/scripts/skill.py` — acts on the installed skill, not the board (`shared/routes/skill.md`).

## Script synopsis

`--scope` goes BEFORE the subcommand. This index is enough for names.

```
TASKS --scope <subdir> <subcommand> ...
TASKS init [--name <handle>] [--scope <subdir>] [--integration <branch>]
           [--parent <branch>] [--iteration N] [--iteration-name <name>]
           [--iteration-started YYYY-MM-DD]
TASKS whoami [--role]                   # your handle (the roster handle your
                                        # GitHub login holds); --role:
                                        # integrator | contributor
TASKS config [<key> [<value>]]          # parent_branch, iteration,
                                        # iteration_name, iteration_started
TASKS contributor list | rm <name>      # rm: yourself, or anyone as integrator
      | rename <name> <new-name>       # same rule; the old handle stays reserved
TASKS integrator list | add <name> | rm <name>
TASKS area list | set <name> [--desc "<one-line scope>"] | rm <name> [--force]
TASKS flow list [--all] [--json] | show <name> [--raw] | runs <name> [--json]
      | create <new-name> --desc "<one line>" [--inputs "<a, b (hint)>"]
           [--uses "<flow, flow>"] [--body T | --file F]
      | update <name> [--desc] [--inputs] [--uses] [--status active|retired]
           [--body T | --file F] [--append "<paragraph>"]   # --append repeats,
                                                            # one paragraph each, in order
      | rename <name> <new-name> | retire <name>     # names, never numbers
      | reid <name>                  # only when two boards minted one id
TASKS agent list [--json] | show <name> [--raw] | rm <name>
      | rename <name> <new-name>     # a former name stays reserved
      | add <name> --accessors "<handle, handle>" --desc "<who it is>"
      | update <name> [--accessors "<handle, …>"] [--desc]
TASKS env list [--json] | show <name> [--raw] | rm <name>
      | rename <name> <new-name>
      | add <name> --accessors "<handle, handle>" [--machine M]
           [--expects "<prose>"]
      | update <name> [--accessors] [--machine M|""] [--expects]
TASKS routine list [--json] | show <name> [--raw] | rm <name>
      | rename <name> <new-name>
      | add <name> --accessors "<handle, handle>"
           --mode attended|unattended --environment <env>
           --schedule "<cron> <timezone>"|<timestamp> --trigger "<what, where>"
           --manage "<how to change or remove it there>"
      | update <name> [--accessors] [--mode] [--environment] [--schedule]
           [--trigger] [--manage] [--status active|paused]
      | wake <name>                  # exit 2 + reason, else its due tasks
TASKS catalog list [<category>] [--json] | show <key> [--raw] | rm <key>
      | get <key>.<field>[.<field>…]  # the value a reference resolves to
      | add <category> <key> [--set "<field>=<value>"]…   # --set repeats
      | update <key> --set "<field>=<value>"…            # empty value clears
      | rename <key> <new-name>      # a former name stays reserved
      | category add <category> --field "<field>: <what it holds>[ (one of: a, b)]"…
      | category update <category> [--field "…"]… [--drop-field <field>]…
      | category show <category> | category rm <category>
      | category rename <category> <new-name>
TASKS add --title "<title>" [--area <m>] [--deps <id,id>]
          [--desc "<1–3 sentences>"] [--assignee <who>]
          [--kind umbrella|recurring] [--cadence <N><unit>]
          [--schedule "<cron> <timezone>"] [--next-due <date>]
          [--type ops] [--status proposed|backlog|planned|shelved --reason "<why>"]
          [--routine <name>]
          [--distill]                   # with --type ops: a distill sitting
          [--umbrella <id[,id]>]        # file under it: adds to its deps
TASKS update <id> [--title] [--area] [--status] [--kind umbrella|recurring|""]
          [--type ops|dev] [--assignee <who>|""] [--branch <b>|""] [--pr]
          [--needs decision|""] [--deps] [--append "<paragraph>"]
          [--desc "<new body>"] [--cadence <N><unit>|""]
          [--schedule "<cron> <timezone>"|""] [--last-run <date|timestamp>|""]
          [--next-due <date>|""] [--routine <name>|""]
          [--flow <name[,name]>|""]
          [--status not-planned|shelved --reason "<why>"]
TASKS related "<text>" [--deps <id,id>] # run before every add; --deps
                                        # also lists their umbrellas
TASKS show <id> [--raw]                 # --raw: {key.field} unresolved
TASKS delete <id>
TASKS verify <id> "<how the children met the goal>"   # close an umbrella
TASKS note <id> [--at "<step>"] "<what the work did not predict>"
            [--date YYYY-MM-DD]         # Note (<date>): …; any status but
                                        # proposed/not-planned, done included
TASKS inputs <id> "<input>=<value>; …"  # Inputs: …, the values a run was
                                        # given (never a live {key.field})
TASKS distilled <sitting> "<T3-T7, T9>" # tasks whose every candidate the
                                        # user has dealt with; stays open
TASKS ran <id> [--flow <name[,name]>] --record "<inputs; deviations>"
               [--date <date|timestamp>]   # close an ops task with its run record;
                                        # on a distill sitting also records
                                        # it and its dependents as distilled
TASKS collisions <id[,id…]>             # 2 doing-blocked, 3 PR open
TASKS list [--assignee <who>] [--status <s>] [--needs decision]
           [--type ops|dev] [--flow <name>] [--json]
TASKS recur list [--due] | recur ran <id> [--date <date|timestamp>]
TASKS board [--expand] [--by-area] [--watch]
TASKS iteration
TASKS iteration-close [--carry] [--skip-distill "<why>"]
                                        # skip: only when the user asks
TASKS iteration-new [<branch>] [--parent <branch>] [--name <name>]
                    [--iteration N] [--iteration-started YYYY-MM-DD]
                    # omit the branch to roll in place (no parent)
TASKS iteration-land [--create-only] [--title T] [--body B]
                                        # parented boards only
TASKS claim <id> [--assignee <who>] [--branch <b>] [--stack-on <id>]
           [--unattended <model-id>]    # refuse if diverged or untagged
TASKS diff <id>
TASKS ship <id> --shipped "<what actually shipped>"
                [--message M] [--title T] [--body B]
                [--version-intent <intent>] [--base <branch>]
                [--batch <id,id,…>]
TASKS ready <id>                        # draft → review; the user's call
TASKS unready <id>                      # review → draft; assignee or
                                        # integrator only
TASKS batch-gate --ids <id,id,…>
TASKS restack --ids <id,id,…> [--after N] [--onto <ref>]
              [--retarget] [--dry-run]
TASKS preflight [--park|--discard]
TASKS land <id>
TASKS cleanup <id>
TASKS pr <id> view [--json] | diff | close [--head <branch>]
      | comment --body B | review --approve|--request-changes|--comment [--body B]
```

Caveats: for a flag not spelled in this synopsis or the route you are following, run `TASKS <subcommand> --help` (the script's own flag reference) — never guess. `--append` adds to a body (no prior `show` needed, can't truncate); `--desc` **replaces** it — only for genuine rewrites. Any rewrite of stored text (`update --desc`, `flow update --body|--file`, `env update --expects`, `routine update --manage`, `catalog update`) starts from `show --raw`: the plain `show` resolves `{key.field}` to its current value, and text drafted from it would freeze that value. Flags combine in one call; an empty string (`--assignee ""`, `--needs ""`, `--flow ""`) clears a field; multi-word values need quoting. When no board is found the error lists known boards — cd in, or pass `--scope`. **Whenever a `TASKS` command exits non-zero or prints `error: …`, surface that output to the user verbatim and stop** — never hide it, paraphrase it away, or paper over it with hand-run git or gh.

`--area` takes a comma-separated list (`--area "cli, docs"`); `all` is reserved (see Area stewardship).

## Ground rules

- **Never edit `.tasks/`, `.flows/` or `.catalog/` by hand, and never commit them from a code branch.** All board and flow reads/writes go through `TASKS`, which serializes every mutation through the integration branch on the remote — that is what makes the board conflict-free across machines. Bypassing it breaks the model.
- **Secrets never reach the board.** Passwords, one-time codes, API keys and session tokens never go into a task, a flow, a registry entry, or any record on one (`Inputs:`, `Note:`, `Decision:`, `Shipped:`, `Ran:`, …): the board is git history, which every clone keeps for good. Sign-in state and secrets live in the environment itself — its browser session, keychain or password manager — so a flow step says "assumes signed in to <X>" instead of carrying the credential. Identifiers (a username, an account number) are not secrets and go on the board as they are — in a flow body, an `Inputs:` line, a note or a record — since the board is as private as the repo. Reread every free-text board write for anything secret-shaped before sending it. A secret that lands anyway is reported to the user at once and fixed by rotating it, never by rewriting board history.
- **Humans decide; agents draft.** Review verdicts, design-fork resolutions, closing calls, proposal approvals, and flow creation and edits belong to the user: surface the question and wait. One the user chooses not to answer yet, or one that comes up with nobody there (an unattended run), goes on the task — `needs: decision` with the question in its body, or new work filed as `proposed` — never left in the chat and never decided around. Every flow write is checked first against an intent the user confirmed, by a fresh reviewer when its impact warrants (`shared/routes/flow-create.md` *Reviewing a flow write*).
- **User specs are one guess.** What the user lays out — filing a task, recommending a change, describing a step, sketching a flow — is one guess at the result and may not be the best. When any part doesn't make sense or could be clearly improved, say so; when something is unclear, ask. The commitment is to a good outcome, not to the user's words.
- **Under-specify tasks, and write short.** A task description is a few sentences: the goal. Details get resolved when the work is done. The same brevity applies to everything else you write — flows, appended decisions, run and shipped records, PR bodies, reports to the user. Review bandwidth is the scarcest resource on the board, and verbose text spends it. Never produce long specs, plans, or status reports the user didn't ask for.
- **Do not manufacture specifications.** When adding or modifying a task, never write constraints, non-goals, interfaces, or other requirements the user did not explicitly state or approve. Future agents treat the task file as human-approved. Non-goals belong on the task only when the user said them.
- Natural-language intents map onto subcommands; fulfil them and mention the keyword once ("done — btw, `/dev pick 12` does this directly"). Always show a suggested command's argument shape — `/dev add <task-or-goal>`, `/dev show <id>` — never a bare `/dev add ...`, which leaves the user guessing what goes there.
- **New work goes through `/dev add`.** Explicit `/dev add`, freeform "we should…", or a goal stated after `/dev` all land on the same path, and add triages it — never ask the user to pick a path. A verb given a description no task matches (`/dev implement <goal>`, `/ops run <description>`) files it through add first, then carries on.
- **A new task's id is the one `add` printed.** Every follow-up on a task just filed — implementing it, citing it, updating it, a dep or umbrella pointing at it — uses the `id:` from that `add` call's output, never one predicted from the board or counted on from an earlier add: another contributor may have filed in between.
- **Vendor-neutral context.** Product docs live in `AGENTS.md` at the directory that owns the work — the nearest one that covers it; a nested package's rule does not go in the repo root. Record what future work there needs and neither the code nor the board shows, of two kinds: **context** — what the project is, does, and aims at — and **heuristics** (below), not only pitfalls. Keep it lean. Each piece of knowledge has one home: what a flow needs goes in that flow, a place's facts in its environment entry (`TASKS env update`), and only product-wide context in `AGENTS.md`. A tracked `AGENTS.md` changes through a dev task like any other file; a gitignored one is the user's private copy, edited directly. If `CLAUDE.md` is present, it is a symlink to that `AGENTS.md` — not the reverse (promote a lone `CLAUDE.md`; if both are regular files, fold unique content into `AGENTS.md`, then replace `CLAUDE.md` with a symlink).
- **Heuristics.** A heuristic is how decisions get made here — an approach, preference, convention or rule the user holds; settling a design fork is one case. No heading is imposed: any clear rule in an `AGENTS.md` that applies to the work counts, cited in short form — its bold name if it has one, else its section and a few words (`Decision: <choice> (heuristic: <short form>)`). A decision one of them clearly settles is not a question: decide it, record that `Decision:` line, and tell the user which heuristic decided it so they can override. This holds in every route that meets decisions, unattended runs included — applying a heuristic is the user's decision, not the agent's. A decision no heuristic clearly settles still goes to the user. When the user's call looks general enough to settle future ones, leave it as the `Decision:` line on the task and carry on: distill promotes it into `AGENTS.md` later, so no run stops for that side task.
- **Scripted git lifecycle.** Never improvise multi-step git/gh for task work: use `claim`, `diff` (self-review from the task worktree), `ship`, `ready`/`unready`, `land`/`cleanup`, `preflight` (park/discard), `iteration-land`, and for stacks `restack`/`batch-gate`. Routes decide and call; they don't spell out raw sequences to re-invent. Reading a PR and the human review actions on it go through `TASKS pr <id> view|diff|comment|review|close`, never `gh pr` directly — `TASKS pr` runs `gh pr` and, where GraphQL is blocked (some hosted agent sandboxes), switches to GitHub's REST API, as every script PR call does. `DEVOPS_PR_TRANSPORT=rest` forces REST from the start.
- **PR is the only merge flow.** GitHub and an authenticated `gh` are assumed; init walks the user through setup, and the script checks gh sign-in before any GitHub step (implement stops at preflight's error). Task branches start from `origin/<integration>`; if local integration is ahead on this board's scope, implement stops to park-as-PR or discard first (routes/implement.md). An unattended run never parks or discards — it skips and reports.
- **To build a task, suggest `/dev <id[, id…]>`**, never `/dev implement <id>` — in a route, a report, or script output; the lead routes umbrellas, ops tasks and hosts without subagents itself.

## State layout (per board)

- `<scope>/.tasks/` — tracked, lives only on that board's integration branch: `NNN.md` (one file per task), `board.yml` (`schema_version`, integration_branch, parent_branch, iteration, iteration_name, iteration_started, integrator, contributors — each `handle (github-login)`), `areas.md` (area names + one-line scopes, for dev tasks), `log.md` (past-iteration index), `archive/<n>-<slug>/NNN.md` (every closed task, verbatim — the full record the log only indexes, run records included; dir is `archive/<n>/` when unnamed). `iteration` is a positive integer (identity, default 1 at init); `iteration_name` is an optional display label; `iteration_started` is `YYYY-MM-DD` (stamped at init / iteration-new, settable to match an external calendar) — `shared/routes/iteration.md`. Ship titles PRs `[n/T<id>] …` (`[<scope> n/T<id>] …` on a scoped board, e.g. `[tools/clk 3/T24]`). Missing `schema_version` means 0; see product `AGENTS.md` for compatibility rules when changing board schema.
- `<scope>/.flows/` — tracked, same home as `.tasks/` (integration branch only, written through `TASKS flow …`), but flows outlive iterations — nothing archives them. One file per flow, `<name>.md`: frontmatter `id` (numeric, fixed at create), `name`, `description` (one line, written like a skill description), `inputs`, `uses` (flows it follows), `status` (`active`/`retired`), `formerly` (past names, a matching hint only), `created`; body = the procedure (`shared/routes/flows.md`). Flows are referred to **by name**, never by number — a number is always a task id. Names are slugs (`lowercase-with-hyphens`). A task records the flows it followed as `flow: <id> <name-at-the-time>`, so lookups match on the id and a rename never rewrites history. `flow show|update|rename|retire` accept the closest name (exact, then a `formerly` entry, then fuzzy; ambiguous → error) and print what they matched. `rename` frees the old name at once; a task's recorded run keeps resolving through the id. `create` refuses a name a retired flow still holds (rename it first). Ids are minted `max+1` against the synced board, so two boards can mint the same one before either pushes (different file names, so nothing conflicts): every flow command warns while an id is shared, and `flow reid <name>` mints a fresh one for the flow whose runs nobody has recorded yet — it refuses when a task already records that flow, and names the other one to reid instead. Any task may name the flows that govern it (`update <id> --flow <name>`, set at the start of the work): an ops run follows them and records them with its `Ran:` line, and a dev task has them followed while it is built — it closes at land, so it never gets a `Ran:` line, and the field stays as the record of what governed it.
- `<scope>/.catalog/` — tracked, same home and rules as `.flows/`: the named things tasks and flows point at, one dir per **category** and one `<name>.md` per entry, every category sharing one namespace of names (current and former), so add and rename refuse a name any category holds. Every catalog name — entry, key, category and field — follows one rule: lowercase letters, digits, `-` and `_`, not a bare number (`studio_mac`, `elm-st`); flow names keep their own. Its built-in categories are the **registries** flows point at. `<scope>/.catalog/agents/<name>.md` and `<scope>/.catalog/environments/<name>.md` are written through `TASKS agent …` / `TASKS env …`: an agent is `name`, `accessors`, `description` (one line, who it is); an environment is `name`, `accessors`, optional `machine`, body = prose expectations; both carry `formerly` (past names). `<scope>/.catalog/routines/<name>.md` is the third registry, the scheduled triggers that start recurring tasks (see Routines below), under the same name and accessor rules. There are no ids: a run record names an entry by the name it had then, so `rename` keeps the old name in `formerly`, where it stays **reserved** (add and rename refuse it) and still resolves — `show`, `update`, `rename` and `rm` accept a former name and print what it matched. `rm` frees all of an entry's names. Every accessor is a board contributor and each entry keeps at least one, so every name leads to a human who can reach it; `project`, `runner`, `any` and `inline` are reserved. Accessors are a routing aid — who can reach it now — not history: who ran an agent for a given run lives in that run's record. A board from before schema 13 kept the registries in `.flows/agents|environments|routines/`; the first command that finds files there moves them into `.catalog/` in one board commit and warns about any name two categories share. **User categories** sit beside them, written through `TASKS catalog …`: `<scope>/.catalog/<category>.md` declares one (never `agents`, `environments` or `routines`) with one field per body line, `<field>: <one line: what it holds>`, which may end `(one of: a, b, c)` — a value outside those only warns; `<scope>/.catalog/<category>/<key>.md` is one **key**: `name`, one line per field, `formerly`, `created`. Values are one line of text, and a bare `{key}` in a value is a reference to that key. A key's name is in the one catalog namespace, renames keep `formerly` (reserved, still resolving) as for the registries, and `catalog rm` is refused while a live task (any status but `done` and `not-planned`), an active flow or another catalog entry references it — `agent|env|routine rm` too. A category is renamed with `catalog category rename` (references name keys, not categories, so none change), removed only once it holds no keys, and loses a field only once no key holds a value for it; free-text notes on a key are just a field the category declares (`note: anything worth knowing`).
- `<scope>/.dev/` — product-local, gitignored, per-checkout (root board → `.dev/` at the git toplevel): `boards.json` (scope→branch cache), `board/` (hidden worktree on a private branch `_dev-board` or `_dev-board-<scope>`, which the script commits board changes through), `worktrees/` (task worktrees). Identity is not stored here (*Identity* below).
- `<scope>/TASKS.md` — derived kanban view, gitignored, regenerated by `board`.
- `<scope>/board` — local live viewer (`r` refresh, `a` toggle by-area, `e` toggle expand, `l` toggle a flat list of every task in this iteration, done included, latest board commit first (`a`/`e` do not apply while it is up), `c` check (an id, or `id,id…` for a group), `s` search (words + Enter ranks live tasks as `TASKS related` does, `e` widens it to done/shelved/not-planned (dimmed); while the `s>` prompt is open every letter is query text, Esc cancels, Ctrl-D still quits), `f` flows pane, `g` registries pane, `q` (or Esc) back one level — a typed id, then a task or flow opened from search hits back to the hits, then the shown output, then an open `c>` prompt, then the flows pane, registries pane or latest list back to the board — and `q` quits from the plain board (Esc never quits; Ctrl-D quits from anywhere); the help line says `q back` while anything is open and `q quit` on a clean board (`r` is always refresh), arrows scroll, space/b page, type a task id + Enter to show it; in the flows pane a typed number is a flow id and opens that flow with its run history at the bottom, `h` opens an `h>` prompt where each flow id + Enter opens that flow scrolled to its history and the prompt stays open for the next (a bare `h` on an open flow jumps there and opens it; `h` again or `q` closes it), and `s` searches flows by name, description and procedure (retired ones tagged and dimmed); the registries pane lists agents, environments and routines one line each, and a typed row number + Enter opens that entry — the numbers only point at rows of that view, since registry entries have no ids), gitignored, written by `init` if missing and refreshed by `init` / `board` while still a stock wrapper. `./board update` rewrites it from the installed skill even if edited. Not `.dev/board` (that is the board worktree).

**Two task types**, one board. Frontmatter carries `type`: `dev` (written on every task the script touches; absent still reads as dev) or `ops`. A **dev task** changes code: it carries the areas it will touch (locks that keep two contributors out of the same region), is built on its own branch, and lands through a PR — `/dev` builds it. An **ops task** changes the world, not the codebase — it is run through flows, not built: it carries no area (the script refuses one), gets no branch and no PR (`claim` and `ship` refuse it), is marked `⚙ops` on the board, and closes with its run record (`TASKS ran`), not a merge — `/ops` runs it. **Crossing over**: a task met under the other skill's route continues in the same session, never stops at the boundary — load the other skill (the harness's skill tool where there is one, else read `../<other>/SKILL.md` from this skill's directory; both are always installed together) and follow its route, `/dev <id>` or `/ops run <id>`. A task already of that type just goes on there. One whose type is wrong converts first, on the user's yes: an ops task that turns out to need code — say what the run found, note the run so far (`TASKS note`), then `update <id> --type dev --area <name> --status backlog` so `claim` can take it; a dev task that would change no files — `update <id> --type ops --area ""`. An unattended run keeps its mode across (`/dev <id> unattended`, `/ops run <id> unattended`) and never converts: it parks the task as `needs: decision`. `type` is orthogonal to `kind`: `kind: umbrella` is a goal parent whose `deps` are its **direct children** (leaves or nested umbrellas) — hierarchy is the dep graph among `kind: umbrella` nodes, with no separate parent field — closed by a verification pass, never automatically (*Umbrella close*); `kind: recurring` is perpetual work on a clock (*Recurring*), and also carries `cadence` or `schedule`, `last_run`, `next_due` and `routine` (*Routines*), each omitted when empty; absent/empty is a normal task.

**The board view.** `TASKS board` is an index (one line per status of task ids; an id carries its line's attention marks: `T81❓` with an open `needs`, `T81📨` while a `doing` run waits on a third party or a handed-off agent, red once overdue; `T81🚨` in place of `⏰` when its routine did not start it) then in-play tasks one per line, umbrella children indented under their parent (which also carries a leaf status rollup), waiting runs after the ones you can act on; done, shelved, and not-planned fold to a count. `--expand` adds those three to the index and the list — it is not an umbrella un-collapse; `--by-area` indexes by area instead of status (same nesting; folded statuses stay counts on last index lines unless `--expand`).

**Statuses**: `proposed` (filed by an agent, awaiting human approval) → `backlog` → `planned` → `doing` → `draft` → `review` → `done`. `draft` and `review` are PR states, so only a dev task passes through them: `ship` always opens the PR into `draft` — the work is out, but not on the integrator's queue — and `TASKS ready <id>` promotes it (draft → review, and marks the PR ready) and `TASKS unready <id>` pulls it back; both are human calls, never an agent's own move, and `update --status draft|review` on a task with a PR is refused and redirected to them. `land` refuses a draft. An ops task goes from `doing` (a run under way) to `done` when `TASKS ran` closes it. A run stopped partway stays `doing` with its assignee: `TASKS pause` records where it got to, so a later session resumes from there, and `TASKS wait` marks one stopped at an `[external]` step or waiting on a handed-off agent's report (`📨waiting <who> by <date>` on its line, red once overdue — on a dev task too, which keeps its branch and area locks); the mark clears when the task leaves `doing`. Off to the side: `shelved` and `not-planned` (*Not planned and shelved*). `done`, `shelved`, and `not-planned` do not block an iteration close. A `recurring` task never reaches `done`: it re-arms to `backlog` after each run (*Recurring*). `needs: decision` marks an open question awaiting a human call, detailed in the task body (`❓needs-decision` on its line).

## Catalog references

Write a fact once, as a catalog key, and point at it wherever it is used: `{key.field}` in a task, a flow, a record or another key's value names that field of the key with that name or former name, in any category — a built-in entry's fields resolve the same way (`{studio-mac.machine}`). `{a.b.c}` chains: `a.b` holds a bare `{x}`, so `c` is read from `x`. Text read through `TASKS` (`show`, `flow show`, `catalog show`, `agent|env|routine show`, and the `./board` viewer) shows each reference, outside code spans and fenced blocks, as `key.field «value»`, live, and warns about each one it cannot resolve. `TASKS catalog get <key>.<field>` prints one value. Every `show` takes `--raw` for the text as stored, which is what a rewrite starts from (*Script synopsis*, caveats). In a flow a **declared input wins**: in `{property.address}` with an input `property`, that reference is left for the run, which takes the input's value as a key name and reads the field from it (`TASKS catalog get <that key>.address`). `flow create|update` warn when an input is named like a catalog key (the key is then out of reach in that flow) and when a reference's key is a near-miss of one the catalog holds. Catalog values are identifiers and facts, never secrets (*Ground rules*).

**What it holds: facts, not ledger entries.** A fact is overwritten when it changes; a ledger entry is added to. Entries that grow by being added to — transactions, payments, invoices, readings, logs, status history — and figures derived from them — balances, totals, counts, a last-paid date — stay in their system of record, and a key may hold where that is (an account number, a URL). What happened in the board's own work stays in its run records. A value that would go stale the moment its system records something new never goes in the catalog.

**A record holds the value a run used**, never a live reference: a run's `Inputs:` (`TASKS inputs`) and every record line — `ran`, `note`, `pause`, `wait`, `verify`, `ship --shipped`, a `--reason` — refuse a `{key.field}` outside code, since it would read as whatever the catalog holds later. Write the value the run used, as `key.field «value»` (the shown form) or the plain value; the script never resolves one for you, since the catalog may have changed while the run went on. Task text written with `--desc` or `--append` stays live.

**Who writes the catalog.** Its shape — a category, a field, a new key, a rename or a removal — is the user's call, made with them (`/dev catalog`, `shared/routes/catalog.md`). A run may update a value its work finds changed (`TASKS catalog update <key> --set "<field>=<value>"`) and reports each one in its record, as `key.field «old» → «new»`; an unattended run updates only the values its flow says to, and parks any other it finds wrong as a question.

## Routing

| Invocation | Action |
|---|---|
| `/dev` (bare) | Read `routes/first-contact.md`. |
| `/dev help` | Read `routes/first-contact.md`. No board/identity → same setup path as bare. |
| `/dev tour` | Read `shared/routes/tour.md` (the key concepts, one card at a time, on the user's own board). Only when asked; never run it unprompted. No board or identity yet → still give it (its no-board path); do not run init first. |
| `/dev init` | Read `shared/routes/init.md` (prerequisites, identity, board creation or joining, areas, the AGENTS.md pointers). |
| `/dev add <task-or-goal>` | Read `shared/routes/add.md` (premise, the task's type, then one task, several, plan, or shape). |
| `/dev plan <goal>` | Alias of `/dev add` (same triage). |
| Freeform new work | Same as `/dev add`. |
| `/dev implement <id[, id…]|goal>` | Read `routes/implement.md` (multi → also `routes/implement-batch.md`; claim, forks, PR; follows the task's flow, and redirects a task that changes no code). |
| `/dev <id[, id…]>` | Read `routes/lead.md` (the task lead: routes by state, runs implement and review through implementer and reviewer subagents, surfaces only real decisions; no subagents → `/dev implement`). |
| `/dev review [id[, id…]]` | Read `routes/review.md` (inbox; multi-id → `routes/review-batch.md`; a `draft` id is its author's own loop — only your own drafts reach the inbox, unattended work as you included). |
| `/dev decide [id]` | Read `shared/routes/decide.md` (open questions and proposed tasks, of either type — the judgments waiting on a person). `/dev review` lists them too. |
| `/dev audit [area]` | Read `routes/audit.md` (scan the codebase for work worth filing; offers to schedule a recurring audit when none covers that scope). Not `/dev review`, which is the PR inbox. |
| `/dev next` | *Next* below — pick the top task for me, then build it on a yes. |
| `/dev <id[, id…]> unattended` / `/dev next unattended` | Read `shared/routes/unattended.md`, then `routes/unattended-run.md` (nobody there: not the lead — implement with forks filed as `needs: decision`, ship to `draft`, stop; no reviewer pass). Only on the trailing word — never assumed. |
| `/dev wake <routine> <dir>` | Read `shared/routes/wake.md` (a routine's run: the skill check, the gate, then its due tasks — attended or unattended by the routine's mode — and, on a one-time trigger, re-pointing it). The whole prompt a trigger at its source carries. |
| `/dev schedule <id> [<routine>]` | Read `shared/routes/schedule.md` (set up a routine so a recurring task starts on its own: pick or create the routine and its runner environment, the trigger proposed from this harness and created at its source on `go`, the task pointed at it, a watched first run; also moves a task between routines). Also where the offer after add, audit and status leads. |
| `/dev absorb <source>` | Read `shared/routes/absorb.md` (import a list of things to do, each filed as the type its work is; a written procedure goes to `/dev flow adopt` instead, and a table of facts about named things to `/dev catalog <source>`). |
| `/dev iteration ...` | Read `shared/routes/iteration.md` (show / close / new). |
| `/dev distill` | Read `shared/routes/distill.md` (a sitting: turn this iteration's task records into `AGENTS.md` context and heuristics, each item the user's call; required before an iteration closes). |
| `/dev board` / `kanban` | `TASKS board` (status index + in-play list); `TASKS board --by-area` for the area cut; then the PR state refresh (`shared/routes/status.md`). |
| `/dev flow` / `/dev flow list` | `TASKS flow list` (`--all` includes retired). |
| `/dev flow show <name>` | `TASKS flow show <name>`. |
| `/dev flow runs <name>` | `TASKS flow runs <name>` — every run of it, newest first. |
| `/dev flow adopt <source>` | Read `shared/routes/flow-create.md` — take a procedure the user already wrote (a doc, a pasted checklist, a file) into the playbook. No name needed up front; it is chosen once the scope is settled. A list of separate things to do is `/dev absorb` instead. |
| `/dev flow create [<name>] [from <id>\|from this conversation]` | Read `shared/routes/flow-create.md` — write one from scratch, from a run, or from what was just discussed. |
| `/dev flow edit <name> [<what to change>]` | Read `shared/routes/flow-create.md` (editing section). A change named in the invocation is made surgically; without one, the same collaborative rounds as create. |
| `/dev flow review <name>` | Read `shared/routes/flow-review.md` — check a drafted flow write against its intent and, once the user agrees, make it — as the fresh reviewer a flow write is handed to. |
| `/dev flow rename <name> <new-name>` | `TASKS flow rename <name> <new-name>`; say that the old name is free again and past runs still resolve. |
| `/dev flow retire <name>` | Confirm, then `TASKS flow retire <name>`. Kept for the record; never delete a flow that runs point at. |
| `/dev agent [list \| show \| add \| update \| rename \| rm] …` | `TASKS agent …` — the agents flows hand sequences to. `add` asks for the accessors (board contributors who can reach it) and a one-line description; `rm` confirms first. |
| `/dev env [list \| show \| add \| update \| rename \| rm] …` | `TASKS env …` — the places sequences run. `add` asks for the accessors, the machine if there is one, and what the place must provide (`--expects`); `rm` confirms first. |
| `/dev catalog` / `/dev catalog <source>` | Read `shared/routes/catalog.md` — design and grow the catalog with the user; bare, look for facts the board writes out more than once (this iteration's tasks, active flows) and categories or fields worth adding, splitting or merging; with a source (a spreadsheet, a tracker export, a table they paste), propose categories, fields and key names from it, then, once they agree, fill in the keys in one pass and bring them the rows that do not fit. A word after `catalog` that is one of the subcommands below is the script's. |
| `/dev catalog [list \| show \| get \| add \| update \| rename \| rm \| category] …` | `TASKS catalog …` — user categories and their keys, the named facts `{key.field}` points at (*Catalog references*). `category add` asks what each field holds and whether it takes only certain values; `rm` confirms first. |
| `/dev routine [list \| show \| add \| update \| rename \| rm] …` | `TASKS routine …` — the scheduled triggers that start recurring tasks (*Routines* below). `add` asks for the accessors, the mode, the environment, what the trigger is set to and where it lives, and how to change or remove it there; `rm` confirms first. |
| `/dev meta [id-or-area]` | Read `routes/meta.md` (pressure the board; optional focus). `/dev meta area` (or `areas`) is reserved: area-validity pass only. Freeform "does this board still make sense?" too. |
| `/dev status` | Read `shared/routes/status.md` (your plate). |
| `/dev pick <id-or-desc>` | `TASKS update <id> --status planned --assignee <me>`; if already assigned to someone else, confirm the takeover with the user first. |
| `/dev change <id> <what>` / `modify` | Map onto `TASKS update <id> --...`; show the result. A new intent is appended (*Intent*). |
| `/dev delete <id>` | Confirm, then `TASKS delete <id>`. |
| `/dev drop <id>` / "we're not doing this" | *Not planned and shelved* below — offer delete as the alternative and let the user pick. "Not needed for now" is shelved instead. |
| `/dev show <id>` | `TASKS show <id>`. |
| `/dev config [key] [value]` | `TASKS config ...` (settable: parent_branch, iteration, iteration_name, iteration_started). Who may land is `TASKS integrator list|add <name>|rm <name>` — see Branch & role conventions. |
| `/dev area ...` | Area stewardship, below. |
| `/dev integrator ...` | `TASKS integrator list|add <name>|rm <name>` — who may land; see Branch & role conventions. |
| `/dev skill` | Read `shared/routes/skill.md` (`SKILL_CMD status`). |
| `/dev skill update` | Read `shared/routes/skill.md` (`SKILL_CMD update`). |
| `/dev skill update auto on/off` | Read `shared/routes/skill.md` (`SKILL_CMD auto on/off`). |
| `/dev skill feedback <text>` | Read `shared/routes/skill.md`. |
| `/dev skill uninstall` | Read `shared/routes/skill.md` (confirm, then `SKILL_CMD uninstall`, the session's last action). |

Given a description instead of an id, run `TASKS list`, match, confirm if not obvious. **`/dev implement` only:** if nothing matches, run the `/dev add` path first (`shared/routes/add.md`), then continue implement on the new task(s) — details in `routes/implement.md`. Other id-or-desc commands (`pick`, `show`, …) still require a match.

## Identity

Before any board operation, check identity with `TASKS whoami` — never probe the filesystem for it yourself. Identity is not stored: it is the roster handle your GitHub login holds — `DEVOPS_GITHUB_LOGIN` if set (a login, not a handle; for cloud or CI), else the account `gh` is signed in as — so a `gh auth switch` changes it at once. Rosters are per board, so run from the product directory or pass `--scope`; a bare monorepo root with no board there errors. If `whoami` errors, run the init route (`shared/routes/init.md`).

**Contributors** are the board's roster of handles, each tied to one GitHub login so every handle traces to a person: one login maps to one handle, and handles are unique. Init reads the login from `gh` and joins or registers by it. `TASKS contributor list` shows who is who; `TASKS contributor rm <name>` removes a stale handle — run by that contributor or an integrator, refused for the last integrator, for anyone still assigned work, and for the last accessor of a registry entry; otherwise it also drops them from every accessor list. `TASKS contributor rename <name> <new-name>` (same who-may rule) renames a handle on the roster, the integrator roster, live task assignees and registry accessors — never archives or run records; the old handle stays reserved. A handle is renamed this way, never by re-joining, and nothing else needs updating: identity is looked up by login.

## Skill check

Run `SKILL_CMD check` once at the start of bare `/dev`, `/dev help`, `/dev init`, `/dev add` (including freeform add and `/dev plan`), `/dev board` / `kanban`, `/dev <id>`, `/dev implement`, `/dev next`, `/dev review`, `/dev meta`, `/dev wake`, and `/dev schedule`.

It runs at most every 24h and stays silent when the local version is current or the network fails; a missing local `VERSION` counts as `0.0.0`. Show any line it prints (one quiet line) and continue the command — never block board work on it. With auto-update on, the check may apply a pull and print one success/failure line.

## Not planned and shelved

Two ways to set a task of either type aside, each a human decision: agents propose them, and an unattended run never sets one. When the user wants a task gone, ask which they mean — `not-planned`, `shelved`, or `delete` — rather than choosing for them.

- `not-planned` = decided against, kept with its reason so the idea isn't re-litigated: `TASKS update <id> --status not-planned --reason "<why>"`, the reason required and appended to the body as `Not planned (<date>):`. It also retires a recurring task for good. `delete` (`TASKS delete <id>`, after confirming) erases instead — for something filed in error, a duplicate, noise.
- `shelved` = set aside for now — not this iteration, or not needed at present, but it may matter again; unlike `not-planned` it is not decided against. `TASKS update <id> --status shelved --reason "<why>"` (or `add --status shelved --reason "<why>"`), the reason required and appended as `Shelved (<date>):`. It holds no area lock, folds to its own `Shelved` count on the board, and `iteration-new` carries it onto the next board still shelved, with a `carried from <n>/T<id>` note — a recurring one too, since shelving pauses it.
- `later` is retired: `--status later` is refused with a pointer to `shelved`, and a task file still saying `later` reads as shelved.

Ask for a reason in the user's own words; if the answer is thin, ask once what changed. Neither is worked (claim, ship, land and a run all refuse it) or picked by `next`, and none blocks an iteration close (logged `[not planned]`, `[shelved]`). Revive with `--status backlog` or `/dev pick <id>`; a recorded reason stays as history.

A task with a live branch or PR cannot move to `shelved` or `not-planned`: `update` refuses, because the branch would outlive the move and the next iteration would orphan the PR. Decide the PR's fate with the user first (land it, close it, or keep it open), run `TASKS cleanup <id>` to drop its worktree (it keeps the branch and PR), then clear both in the same call (`--branch "" --pr ""`); the old values are recorded in the body as `Cleared on moving to <status> (<date>): …` and nothing is deleted.

## Intent

Every task's body ends with one `Intent:` line: what the user actually wants out of the work, the outcome they would judge it by — not the change or the steps. It is the user's goal in their terms, never your inference dressed as theirs. Filing a task, the premise usually answers it already; ask (one question) only when the invocation leaves it unclear. It is a body line, not a frontmatter field: pass it as the last paragraph of `--desc`. On a recurring task it never restates the schedule ("weekly", "every month", a due day): `cadence`, `schedule` and `next_due` in the frontmatter hold that and change without touching the body, so the line names what each run is for. Several tasks from one ask each carry their own: an umbrella's is the user's goal, a child's is the part of that goal it serves.

The last `Intent:` line wins: when the intent changes (`/dev change <id> intent <new intent>`), append a new one with `TASKS update <id> --append "Intent: …"`, never a `--desc` rewrite, and earlier ones stay as the record that the goal moved. A task with no `Intent:` line gets one before work on it starts — ask the user what they want out of it and append their answer. Every closing judgment is against it: implement's and review's check of the diff, a run's final check, an umbrella's verification pass.

## Umbrella close

**An umbrella is never auto-closed.** Its children all being `done` says the work happened, not that the goal was met — separating those two judgments is the whole reason the umbrella exists. So no flow, and no agent, closes one off a status rollup: `TASKS update <id> --status done` on a `kind: umbrella` task is **refused**, and closing it has its own verb instead — `TASKS verify <id> "<how the children met the goal>"`, which records `Verified (<date>): …` in the body and closes the task. That record is carried into `log.md` at iteration close (an umbrella never ships or runs, so it is its only outcome line).

The pass itself is `shared/routes/verify.md`, which `/dev <id>` and `/ops run <id>` both route an umbrella to, whatever its type. It reads each child's own outcome record against the umbrella's last `Intent:` and ends in the same session, either filing the gaps as new children or closing with the record — no branch, no PR, no review. Anyone may run it — typically whoever filed the umbrella and knows its intent; unlike `land`, it is not integrator-only. An unattended run never runs it.

`meta` never proposes closing an umbrella. When one looks complete it says the goal check is **due** and worth prioritizing, and points at the pass.

## Recurring

`kind: recurring` + `cadence: <N><unit>` (unit `d`/`w`/`m`, e.g. `2w`, `1m`) or `schedule: <cron> <timezone>` (a 5-field cron expression and an IANA zone, e.g. `0 12 * * 3 America/New_York`; one or the other, never both) = perpetual work on a clock — an audit, a dependency sweep, the monthly close — not a task that finishes. It is never terminal: recording a run stamps `last_run` and re-arms it to `backlog` instead of closing it — `land` for a dev task, `TASKS recur ran <id> [--date]` for a dev run that never had a PR (refused while a branch or PR is live — `land` owns that run), `TASKS ran` for an ops task — and `--status done` is refused. The due date is **derived** by default (`last_run + cadence`, or the first scheduled time after `last_run`), so a clock edit re-dates it immediately; no `last_run` = due now on a cadence, and the first scheduled time on or after the start of its created day on a schedule. A missed scheduled time stays due until a run is recorded. Schedulers fire triggers early, so each scheduled time has an **early window** of 3 hours before it (at most half the gap from the scheduled time before). On a schedule, `last_run` records the scheduled time the run **covered**, not when it was recorded: a run recorded inside a time's early window covers that time, any other covers the latest time at or before it (a catch-up run recorded before today's window covers yesterday's, so today's stays due), and the next due is the time after it. A bare date is kept as given. Cadence tasks stamp the run time and have no window. `last_run` is stamped as a timestamp with offset (`2026-11-11T12:04-05:00`); `--last-run` and `--date` also take a bare date, which a schedule reads as the end of that day in its timezone. To set the date instead — a first run on a chosen future day, or the next run pushed or pulled — `add … --next-due <date>` or `update <id> --next-due <date>` records it without faking a `last_run`: it overrides the derived date until a run is recorded (`land`, `recur ran`, `ran` all clear it), then the cadence or schedule takes over — today's date makes a scheduled task due now, so its first run can be fired by hand; `""` clears it. Use a date the user named; never invent one. `TASKS recur list [--due]` is the due view; `board` marks each recurring id on its index row — `↻`, or a red `⏰` when due and its due state on its line.

Status alone decides whether the clock runs: in `proposed`, `shelved` or `not-planned` it is stopped — never due, left off `recur list` and unmarked on the index, and recording a run on it is refused until it is revived. Its cadence or schedule, `last_run` and `next_due` are kept, so the clock resumes when it returns to an active status. How an iteration close carries one is `shared/routes/iteration.md`'s.

**Agents never invent a recurring task.** Whether work recurs, and how often, is a human call: a flow may offer to schedule one and wait for the answer, an unattended run never files one.

A dev run's branch gets a `-<YYYY-MM-DD>` suffix (`-2`, `-3`… for a second that day), so a run never reuses an earlier one's leftover.

## Routines

A **routine** mirrors a scheduled trigger that lives at its source — a harness's scheduler, cron, a cloud routine — so the board knows which recurring tasks start on their own, where and how. One file per routine, `<scope>/.catalog/routines/<name>.md`, written through `TASKS routine …`: `name`, `accessors` (contributors who can reach the trigger's source), `mode` (`attended`: exactly one task, and the user is reached when it needs them; `unattended`: its tasks run in one session and share its context), `environment` (the registered environment it runs in), `schedule` (what the trigger is set to: a cron expression and an IANA zone in the recurring syntax, or one fire time as a timestamp with offset), `trigger` (one line: what it is and where, with its identifier), `status` (`active`/`paused`), `formerly`, `created`; body = how to change or remove the trigger at its source. Former names stay reserved and keep resolving, as for agents and environments; `rm` is refused while a task points at the routine, and `env rm` while a routine runs there. `paused` is the board-side off switch for anyone who cannot reach the source: the trigger still fires, and the wake stops on it. Setting one up for a task, or moving a task to another, is `/dev schedule <id> [<routine>]` (`shared/routes/schedule.md`).

A recurring task points at a routine with its `routine` field (`add` / `update --routine <name>`, `""` clears). A routine's tasks share one type, so `/dev` and `/ops` each wake only their own; a second task on an attended routine is refused; pointing a task at an unattended routine notes the shared session, and warns when the task's flow has `[user]` steps nobody will be there to do. Changing its kind away from `recurring` is refused while the routine is set — clear the routine first. Editing a covered task's cadence, schedule or `next_due` prints a reminder that its trigger lives at the source and may need the same change there.

**Not started.** A covered task that is due, at rest (`backlog`/`planned`) and has no open `needs`, whose routine's schedule says it should have fired for it more than an hour ago, reads `🚨routine <name> did not start` on its line, and its index id carries `🚨` in place of `⏰` — `routine <name> paused` (plain `⏰` on the id) when the routine is paused. It is derived whenever the board is read, never stored; `TASKS routine list` shows the same under each routine with the time it should have fired. A schedule this machine cannot read (say, a zone its timezone data lacks) is listed as `schedule unreadable (<why>)` and skipped by the check rather than stopping the board.

**Wake.** `TASKS routine wake <name>` is the gate a routine's run passes first: exit 2 with the reason when the routine is paused, no longer on the board, or runs the other skill's tasks; otherwise its due tasks at rest (`backlog`/`planned`), in due order — a scheduled task counts as due once inside its time's early window (see *Recurring*), so an early fire still runs it — then any due one with an open `needs` on a `skipped, waiting on a decision:` line and any still in flight on a `skipped, in flight:` line — a re-fire never hands out a parked question again, nor a run that is still going. A trigger's prompt is only `/dev wake <name> <dir>`, `<dir>` being the product directory's absolute path in its environment (`shared/routes/wake.md`): every rule a scheduled run follows lives in the skill and on the board, so the prompt at the source changes only if the checkout moves.

**Runner environment.** The environment a routine runs in must give a session everything a run needs with no one at the keyboard: a checkout of this repo that can push to the integration branch, with the product directory at the path the trigger's prompt names; this skill at a version the board accepts; `gh` signed in as a login on the board's roster (`TASKS whoami` checks it at the wake); for dev tasks, the right to open PRs; every tool call the run makes either allowed or refused up front, never left waiting on a permission prompt; and, for an attended routine, a way to notify the user. These are judged when the routine is set up and by watching its first run — the script does not check them.

## Area stewardship (inline)

Areas are **coordination** locks, not labels. A task's `area` may list several, comma-separated. Two tasks **collide** when any name on one **segment-prefix-overlaps** any name on the other: split on `/`; `routes` overlaps `routes/implement` and `routes/other`; `routes/implement` does not overlap `routes/review`; `route` does not overlap `routes` (string prefix is the trap). The script owns this; `TASKS collisions <id[,id…]>` queries occupancy. Watch-mode `c` then id is a check: that occupancy plus whether the task's deps are not yet done (blocked sides only; both clear → one clear). `c` then `id,id…` checks a group: each member against the board outside the group, then two verdicts within it — **parallel** (no area overlap and no deps between members) and **batch** (in-group deps only order the run; a cycle blocks). A `done`, `shelved` or `not-planned` member is listed by status and left out of both. No batch order is suggested beyond the deps it names. A `doing` blocker — any assignee, this user included — **aborts** implement (exit 2; print the output, do not claim). Blockers whose PRs are **all open** (`draft` or `review`, any assignee) exit 3 instead: there is a pushed tip to build on, so interactive implement offers **proceed** (claim from integration — the areas overlap but the files usually do not), **stack** (`claim --stack-on <blocker-id>`, when the task truly needs the unmerged code; ship derives the PR base, land retargets rather than rebases) or **wait** (routes/implement.md). An unattended run skips both exits and never stacks. Untagged tasks skip that check (empty overlaps nothing except `all`), so `claim` refuses an empty area on a dev task. Ops tasks (`type: ops`) never carry an area: they touch no code, so there is nothing to lock — the script refuses an area on one. Implement recommends a reuse or new name and waits; an unattended run files the same as `needs: decision` (does not `area set` or tag until a human decides). Add may still leave area empty when a cluster cannot be named yet. No placeholder. A multi-id call excludes the other ids in the set from that fail check (batch members are sequential) and prints `set:` overlap lines and the group's `parallel: ok | no — <reasons>` verdict as information only. Resume of one batch member uses that same set (`routes/implement.md`), not the single id. Reserved **`all`** marks a task that may touch everything (wide refactors, some umbrellas) and collides with every task: only on an otherwise-quiet board (nothing in `doing`, `draft`, or `review`) with the user's explicit confirmation that other contributors are paused; an unattended run never picks it; never listed in areas.md.

A name with `/` is a path; parents are implied by segments (no parent field). A parent is a subtree-wide lock (`routes` = any/all `routes/*`) and is only assignable if listed in areas.md — do not invent it because a directory exists. Tag the parent **or** the specific children, not both. Prefer the children so locks stay narrow; do not tag the parent because the work *might* go wide — widen at implement if a fork actually crosses them (pause, update `--area`, re-run collisions before touching those files; exit 2 → revert `--area`, keep the `Decision:` for resume; exit 3 is the user's proceed-or-not call, with no stack option mid-branch; an unattended run files `needs: decision` instead — routes/implement.md). Residuals that are not a named child go to `…/other` (`routes/other`), never the parent. A listed path-parent may itself be slash-free (`routes`) and still own `routes/*`. Conceptual names (`docs`, `ci`) stay slash-free and do not grow children — `docs`, not `docs/readme`.

No fixed upper bound. Limiter is multi-area occupancy: as many stable areas as enable parallelization without typical tasks needing many at once (over-granularity → confusing multi-area tags). Init proposes under that heuristic (`shared/routes/init.md`).

Areas live in `.tasks/areas.md` via `TASKS area list|set|rm`. Path-split work: repo-relative path or the shortest uniquely distinguishing portion (`cli`, `billing/api`) — no filename extensions (`routes/iteration`, not `routes/iteration.md`). Cross-cutting non-directory work: short slash-free phrase (spaces fine). Form: no trailing `/`, no leading `./`, no `:` or `,`. The one-line `--desc` carries the rest.

`/dev area` with no args → `area list` only. Validity (stale names, path-renames, parent-used-as-residual, leftover extensions) lives under `/dev meta area` (routes/meta.md). `area list` open counts and `area rm` (without `--force`) match **exact names only** — a parent is not responsible for its children's tasks; shelved and not-planned do not occupy. `TASKS board --by-area` indexes along the area axis: multi-area tasks appear on each listed area's id line, umbrella children nest as on the status board, and done/shelved/not-planned fold to counts on last index lines.

## Running a task

How this skill runs one of its tasks, for the shared routes (`shared/routes/…`) that cite this section:

- **Attended run**: `/dev <id>` (`routes/lead.md`; an umbrella goes to its verification pass, `shared/routes/verify.md`). A recurring audit (a recurring task naming an audit pass, `Recurring audit: <scope>`) runs `/dev audit` with its scope instead (`routes/audit.md`).
- **Unattended run**: `/dev <id> unattended` (`shared/routes/unattended.md`, its dev part `routes/unattended-run.md`) — forks filed as `needs: decision`, stops at draft. A recurring audit goes through that part's *Audits*.
- **Scheduled run** (an attended routine's wake): `/dev <id>` as *A scheduled sitting* (`routes/lead.md`) — or the audit route above.
- **Answering a parked question**: `/dev decide <id>` (`shared/routes/decide.md`); a task parked mid-work is then picked back up with `/dev <id>`.
- **The run's outcome record** is its `Shipped:` record; a recurring run re-arms at land.

## Next

`/dev next` picks for you, among this skill's own type of task (`type: dev` for `/dev`, `type: ops` for `/ops`). Candidates are `backlog` or `planned` tasks, unassigned or yours, no open `needs`, every dep `done`. An umbrella is a candidate only once all its children are done — its verification pass is due (*Umbrella close*) — and then it ranks first; one with open children never is. Then due recurring work (`TASKS recur list --due`), then your own `planned` tasks, then the rest. Propose the top one in a line (title, and why it is first), with the runner-up; on a yes, run it as *Running a task* says (an umbrella goes to its pass). Nothing eligible → say so and point at `/dev add <task-or-goal>`. What could stop the work — collisions, a flow step that needs a person, fork risk — is not filtered here: you are there to make those calls. Runs already in flight are status's (`shared/routes/status.md`). `/dev next unattended` is a different choice (`shared/routes/unattended.md`), and it never picks an umbrella.

## Branch & role conventions

- Branch-per-task: `dev/<id>-<slug>` (scoped boards: `dev/<scope-with-/->-<id>-<slug>`), owned by the task's assignee, short-lived, merged promptly via PR with a merge commit. Land never rewrites a task branch: divergence is absorbed by the merge, and a conflict or stale branch is merged forward (never rebased) so PRs stacked on it stay valid.
- Review: anyone except the task's assignee; the integrator may review anything, including their own work. A `draft` is the exception — it is the author's own review loop until they `ready` it. An unattended run works as the human who owns the machine's GitHub login (shared/routes/unattended.md), so its drafts are that person's. Land: only the integrator (`TASKS land` refuses a live merge otherwise; already-merged cleanup stays allowed).
- The **integrator** role owns the integration branch: default reviewer, conflict arbitration, iteration close, and land. Ask the script who holds it — `TASKS whoami --role` prints `integrator` or `contributor` for the current identity — and never compare identities yourself. The board creator gets the role at init; `TASKS integrator list | add <name> | rm <name>` reads and changes it (a board may hold the role in more than one pair of hands; the last one cannot be removed, since an empty roster blocks land for everyone).
- Code branches contain code only; the board never rides them — `.tasks/` may appear in a feature checkout (inherited from integration), which is fine as long as the PR does not modify it.
