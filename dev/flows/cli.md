# TASKS flag wall

Full invocation patterns. SKILL.md keeps the short index and the append / error caveats; load this file when a flag is not already spelled in SKILL.md or the flow you are following. Do not guess flags.

```
TASKS --scope <subdir> <subcommand> ...   # target another board in the repo
                                          # (goes BEFORE the subcommand)
TASKS init --name <handle> [--scope <subdir>] [--integration <branch>]
           [--parent <branch>] [--iteration N] [--iteration-name <name>]
           [--iteration-started YYYY-MM-DD]
TASKS whoami [--role]                   # this checkout's identity (exits
                                        # nonzero if not set); --role prints
                                        # this identity's board role instead,
                                        # 'integrator' or 'contributor' — the
                                        # only way to ask, never compare
                                        # identities against board config
TASKS config [<key> [<value>]]          # settable: parent_branch,
                                        # iteration (renumber live index;
                                        # refused if that n is archived),
                                        # iteration_name, iteration_started
                                        # (all three refused once
                                        # closed, before land or in-place
                                        # new). integrator is
                                        # readable here but set below
TASKS integrator list                   # who may land, '(you)' on the current
                                        # identity
TASKS integrator add <name>             # grant the role (idempotent)
TASKS integrator rm <name>              # revoke it; refused for the last one
                                        # (an empty roster blocks land for
                                        # everyone). Ungated: any contributor
                                        # may run add/rm
TASKS area list
TASKS area set <name> [--desc "<one-line scope>"]
TASKS area rm <name> [--force]
TASKS flow list [--all] [--json]        # active flows, name — description;
                                        # --all adds retired ([retired])
TASKS flow show <name>                  # print the flow file
TASKS flow runs <name> [--json]         # every recorded run, newest first
TASKS flow create <new-name> --desc "<one line: what it does, when to use it>"
           [--inputs "<a, b (hint)>"]   # what a run must be told
           [--uses "<flow, flow>"]      # flows this one follows
           [--body "<procedure>" | --file <path|->]
                                        # <new-name>: lowercase letters, digits,
                                        # hyphens; id is minted max+1. Refused
                                        # if an active flow has the name, or a
                                        # retired one still holds it (rename
                                        # that first)
TASKS flow update <name> [--desc] [--inputs] [--uses]
           [--status active|retired]
           [--body "<procedure>" | --file <path|->]   # REPLACE the procedure
           [--append "<paragraph>"]     # add to the procedure
TASKS flow rename <name> <new-name>     # old name is free at once and kept in
                                        # `formerly` as a matching hint; other
                                        # flows' `uses` follow, tasks' recorded
                                        # runs do not (they resolve by id)
TASKS flow reid <name>                  # fresh id for a flow whose id another
                                        # flow also holds; refused when a task
                                        # already records it (reid the other)
TASKS flow retire <name>                # kept for the record; revive with
                                        # update --status active
                                        # <name> is an existing flow: closest
                                        # match (exact, then formerly, then
                                        # fuzzy with a clear leader; ambiguous
                                        # errors) — never a number, which is
                                        # always a task id. <new-name> is a
                                        # fresh slug and is never matched
TASKS add --title "<title>" [--area <m>] [--deps <id,id>]
          [--desc "<1–3 sentences>"] [--assignee <who>]
          [--kind umbrella|recurring]           # empty = normal
          [--cadence <N><unit>]                 # recurring only, unit d/w/m
          [--type ops|dev]                      # default dev; ops = run
                                                # through /ops flows, and
                                                # refuses --area
          [--status proposed|backlog|planned|later]  # default backlog
TASKS update <id> [--title "<t>"] [--area <m>] [--status <s>]
          [--kind umbrella|recurring|""] [--assignee <who>|""]
          [--branch <b>|""] [--pr <url>] [--needs decision|""]
          [--deps <id,id>]
          [--type ops|dev]                      # an ops task carries no area:
                                                # to ops is --type ops
                                                # --area "", to dev is
                                                # --type dev --area <m>
                                                # (one call, any flag order)
          [--flow <name[,name]>|""]             # flow(s) governing this task;
                                                # names resolve to `<id>
                                                # <name>` refs at write time
          [--append "<paragraph>"]              # add to body, keeping it
          [--desc "<new body>"]                 # REPLACE whole body
          [--cadence <N><unit>] [--last-run YYYY-MM-DD|""]
                                                # recurring only; the due date
                                                # is derived, never stored
          [--status later]                      # park for a later iteration
          [--status not-planned --reason "<why>"]   # reason is required
                                                # --status draft|review on a
                                                # task with a PR is refused;
                                                # use ready / unready
TASKS verify <id> "<how the children met the goal>"
                                        # close an umbrella; the record is
                                        # required, and --status done on one
                                        # is refused in favour of this
TASKS ran <id> --record "<inputs; deviations>"
               [--flow <name[,name]>] [--date YYYY-MM-DD]
                                        # close an ops task with its run
                                        # record (Ran (<date>): …); --flow
                                        # omitted keeps the task's flow
                                        # field. Recurring re-arms to backlog
                                        # instead of done. Refused on a dev
                                        # task, or one with a branch/PR
TASKS pause <id> --at "<step>" --record "<what exists so far, where>"
                 [--flow <name[,name]>] [--date YYYY-MM-DD]
                                        # an ops run stopped partway:
                                        # appends Paused (<date>): …, stays
                                        # doing with its assignee. Only a
                                        # doing ops task; resume is
                                        # /ops run <id>
TASKS note <id> "<text>" [--at "<step>"] [--date YYYY-MM-DD]
                                        # ops only: appends Note (<date>):
                                        # [<flow> <step>] …; any status but
                                        # proposed/not-planned (done too);
                                        # moves nothing
TASKS delete <id>
TASKS show <id>
TASKS collisions <id[,id…]>             # area occupancy vs doing/draft/review;
                                        # multi-id also prints in-set overlap;
                                        # exit 2 if any blocker is doing;
                                        # exit 3 if every blocker's PR is open
                                        # (draft or review, any assignee) —
                                        # implement offers proceed / stack /
                                        # wait, auto skips
                                        # (batch peers excluded from that check)
TASKS related "<text>"                  # existing tasks similar to <text>;
                                        # run before every add
TASKS list [--assignee <who>] [--status <s>] [--needs decision]
           [--type ops|dev] [--json]    # --type dev also matches untyped
                                        # tasks
TASKS recur list [--due]                # recurring tasks + derived due dates
                                        # (overdue and never-run first);
                                        # --due limits to due/overdue now
TASKS recur ran <id> [--date YYYY-MM-DD]
                                        # record a run with no PR: stamp
                                        # last_run (default today), re-arm to
                                        # backlog. Refused if branch or pr is
                                        # set — land owns that run.
TASKS board [--expand] [--by-area] [--watch]
                                        # index: one line per status (or
                                        # area) of task ids; then in-play
                                        # tasks one per line, umbrella
                                        # children indented under the
                                        # parent; done/later/not-planned
                                        # fold to a count, --expand lists
                                        # those three; --watch: r/a/e/c/q, arrows
                                        # scroll, space/b page, type id↵ to show
                                        # a task, c then id↵ for check (area
                                        # collisions + unfinished deps)
                                        # (./board)
TASKS iteration
TASKS iteration-close [--force]
TASKS iteration-new [<branch>] [--parent <branch>] [--name <name>]
                    [--iteration N] [--iteration-started YYYY-MM-DD]
                                        # omit branch: roll in place on a
                                        # no-parent board (after close)
TASKS iteration-land [--create-only] [--title T] [--body B]
                                        # open/merge iteration PR into parent
                                        # with merge commit (not squash);
                                        # refuses when there is no parent
TASKS claim <id> [--assignee <who>] [--branch <b>] [--stack-on <id>]
                                        # branch from origin/integration, or
                                        # from that task's pushed tip with
                                        # --stack-on (refuses a parent with no
                                        # branch or already on integration)
                                        # (ff empty leftover; refuse if
                                        # diverged or untagged), always a linked
                                        # worktree under .dev/worktrees
                                        # (primary stays hub), status=doing;
                                        # prints workdir + product + verified
                                        # base (edit + compile/test/run in product)
TASKS diff <id>                         # location + review diff from the
                                        # task worktree (not session cwd);
                                        # implement self-review / resume
                                        # (review: attaches origin/<branch>
                                        # if this clone has no checkout)
TASKS ship <id> --shipped "<what actually shipped>"
                [--message M] [--title T] [--body B]
                [--version-intent <intent>] [--base <branch>]
                [--batch <id,id,…>]     # commit if dirty ([n/T<id>] prefix),
                                        # push, gh pr create --draft if none
                                        # open, status=draft + pr URL (a first
                                        # ship always lands in draft; only
                                        # ready promotes it). Re-ship
                                        # reuses the open PR, so --title /
                                        # --body / --base apply on create
                                        # only; --version-intent also
                                        # rewrites the PR line on re-ship
                                        # ('none' drops it).
                                        # --shipped is REQUIRED on every ship
                                        # (result, not plan): appended to the
                                        # task body as Shipped (<date>): … and
                                        # mirrored onto the PR body each ship.
                                        # --version-intent has no default;
                                        # --base overrides the derived base
                                        # (a live task branch this one is
                                        # based on, else integration; refuses
                                        # if that branch moved since the
                                        # stack); --batch stamps Dev-batch
                                        # on PR + task body
TASKS ready <id>                        # draft → review: mark the PR ready
                                        # and hand it to the integrator. The
                                        # user's call, never an agent's own
                                        # move; anyone may run it
TASKS unready <id>                      # review → draft: take the PR back off
                                        # the integrator's queue. Assignee or
                                        # integrator only. Both mirror the
                                        # PR's draft bit; a repo with no draft
                                        # PRs only warns — the board owns the
                                        # state
TASKS batch-gate --ids <id,id,…>        # exit 2 if selection omits an open
                                        # stack parent (child before parent
                                        # is the one land order that still
                                        # breaks); a partial Dev-batch only
                                        # prints an advisory, exit 0
TASKS restack --ids <id,id,…> [--after N] [--onto <ref>]
              [--retarget] [--dry-run]  # fail-closed stack rebase (plan,
                                        # then apply unless --dry-run);
                                        # auto-retargets PR base to
                                        # integration when the stack parent
                                        # is outside the set; --onto rebases
                                        # every target onto that ref (no
                                        # cascade — the default keeps in-set
                                        # stack parents); moving onto a
                                        # new base excludes the old parent
                                        # tip (no duplicate replay)
TASKS preflight [--park|--discard]      # local integration ahead of origin
                                        # (check exits 2 if in-scope ahead;
                                        # --park / --discard are interactive)
TASKS land <id>                         # integrator-only (any name on the
                                        # roster) merge commit (never
                                        # squash, never rewrites the branch;
                                        # refuses a draft — ready it first):
                                        # merge, retarget stacked children to
                                        # integration, cleanup, done
                                        # (recurring: re-arms to backlog
                                        # with last_run stamped, not done)
TASKS cleanup <id>                      # worktree + branch prune (branch only if PR MERGED)
```
