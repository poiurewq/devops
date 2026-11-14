# TASKS flag wall

Full invocation patterns. SKILL.md keeps the short index and the append / error caveats; load this file when a flag is not already spelled in SKILL.md or the flow you are following. Do not guess flags.

```
TASKS --scope <subdir> <subcommand> ...   # target another board in the repo
                                          # (goes BEFORE the subcommand)
TASKS init [--name <handle>] [--scope <subdir>] [--integration <branch>]
           [--parent <branch>] [--iteration N] [--iteration-name <name>]
           [--iteration-started YYYY-MM-DD]
                                        # reads the GitHub login
                                        # (DEVOPS_GITHUB_LOGIN, else gh). No
                                        # --name: join as the handle that login
                                        # holds (error if none). --name:
                                        # register it, or fill its missing
                                        # login; refused if the login is
                                        # another handle or the handle another
                                        # login's. Required to create a board.
                                        # Refused when no login can be read:
                                        # no handle without a login. Writes
                                        # nothing about identity locally
TASKS whoami [--role]                   # the roster handle your GitHub login
                                        # holds (DEVOPS_GITHUB_LOGIN, else
                                        # gh's account), looked up on the
                                        # last-synced roster; nonzero if no
                                        # login or it is not on the roster.
                                        # --role prints its board role
                                        # instead, 'integrator' or
                                        # 'contributor' — the only way to
                                        # ask, never compare identities
                                        # against board config. --github is
                                        # an alias of plain whoami
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
TASKS contributor list                  # handles with GitHub logins, marks
                                        # integrators and '(you)'
TASKS contributor rm <name>             # yourself, or anyone as integrator;
                                        # refused for the last integrator and
                                        # for anyone assigned a task not done
                                        # or not-planned, and for the last
                                        # accessor of a registry entry.
                                        # Also drops them from the integrator
                                        # roster and every accessor list
TASKS contributor rename <name> <new>   # yourself, or anyone as integrator.
                                        # Renames on the roster, integrator
                                        # roster, live task assignees and
                                        # registry accessors (not archives
                                        # or run records); the old handle
                                        # stays reserved
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
           [--append "<paragraph>"]     # add to the procedure; repeatable,
                                        # one paragraph each, in order
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
TASKS agent list [--json]               # name — description (accessors)
TASKS agent show <name>                 # print the entry file
TASKS agent add <new-name> --accessors "<handle, handle>" --desc "<who it is>"
                                        # <new-name>: slug; project, runner,
                                        # any are reserved, and so is every
                                        # entry's former name. Accessors:
                                        # contributor handles who can reach
                                        # it now, at least one
TASKS agent rename <name> <new-name>    # old name joins `formerly`, stays
                                        # reserved and still matches
TASKS agent update <name> [--accessors "<handle, …>"]  # REPLACES the list
           [--desc "<who it is>"]
TASKS agent rm <name>                   # frees all its names
                                        # <name>: exact name or a former one
                                        # (prints what it matched); no fuzzy
TASKS env list [--json]                 # name — machine (accessors)
TASKS env show <name>                   # print the entry file
TASKS env add <new-name> --accessors "<handle, handle>"
           [--machine <m>]              # the machine it lives on
           [--expects "<prose>"]        # what a step can count on there
                                        # same name and accessor rules as agent
TASKS env update <name> [--accessors] [--machine <m>|""] [--expects]
TASKS env rename <name> <new-name>
TASKS env rm <name>                     # refused while a routine runs there
TASKS routine list [--json]             # name — mode, status, environment,
                                        # schedule (accessors); then each
                                        # one's tasks, and a task it should
                                        # have started and did not (or that
                                        # waits on it paused)
TASKS routine show <name>               # print the entry file
TASKS routine add <new-name> --accessors "<handle, handle>"
           --mode attended|unattended   # attended: exactly one task
           --environment <env>          # a registered environment
           --schedule "<cron> <timezone>" | <timestamp with offset>
                                        # what the trigger is set to: a
                                        # cron + IANA zone, or one fire time
           --trigger "<what and where, with its identifier>"
           --manage "<prose>"           # how to change or remove the
                                        # trigger at its source (the body)
                                        # same name and accessor rules as agent
TASKS routine update <name> [--accessors] [--mode] [--environment]
           [--schedule] [--trigger] [--manage]
           [--status active|paused]     # paused: the board-side off switch
                                        # for anyone who cannot reach the
                                        # source; wake stops on it
TASKS routine rename <name> <new-name>  # tasks keep resolving the old name
TASKS routine rm <name>                 # refused while a task points at it
TASKS routine wake <name>               # the entry gate a trigger runs:
                                        # exit 2 + reason when the routine is
                                        # paused, gone, or of the other
                                        # skill's tasks; else its due tasks
                                        # at rest, in due order, then
                                        # `skipped, waiting on a decision:`
                                        # (open needs) and `skipped, in
                                        # flight:` lines
TASKS add --title "<title>" [--area <m>] [--deps <id,id>]
          [--desc "<1–3 sentences>"] [--assignee <who>]
          [--kind umbrella|recurring]           # empty = normal
          [--cadence <N><unit>]                 # recurring only, unit d/w/m
          [--schedule "<cron> <timezone>"]      # recurring only, instead of
                                                # --cadence: 5-field cron +
                                                # IANA zone ("0 12 * * 3
                                                # America/New_York")
          [--next-due YYYY-MM-DD]               # recurring only: first run
                                                # date (default: due now on a
                                                # cadence, first scheduled
                                                # time from the start of
                                                # today on a schedule)
          [--type ops|dev]                      # default dev; ops = run
                                                # through /ops flows, and
                                                # refuses --area
          [--rehearsal]                         # ops only, never recurring:
                                                # a dry run of its flow
                                                # (rehearsal: true)
          [--routine <name>]                    # recurring only: the routine
                                                # whose trigger starts it
          [--status proposed|backlog|planned|later]  # default backlog
          [--umbrella <id[,id]>]                # add the new task to these
                                                # umbrellas' deps, same board
                                                # commit; refuses a
                                                # non-umbrella or one also
                                                # in --deps
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
                                                # <name>` refs at write time;
                                                # an ops task entering doing
                                                # is refused while the
                                                # opposite kind (run vs
                                                # rehearsal) of the same
                                                # flow id is doing
          [--unattended <model-id>|""]          # an unattended ops run's
                                                # (or audit's) marker, same
                                                # field claim sets: only on a
                                                # doing task; refused (as is
                                                # --status doing) while any
                                                # run's marker is set, same
                                                # model id too; "" clears
          [--append "<paragraph>"]              # add to body, keeping it;
                                                # repeatable, one paragraph
                                                # each, in order
          [--desc "<new body>"]                 # REPLACE whole body
          [--cadence <N><unit>|""] [--schedule "<cron> <timezone>"|""]
          [--last-run <date|timestamp>|""]     # recurring only; the due is
                                                # derived from these. One of
                                                # cadence/schedule; a
                                                # timestamp carries its offset
                                                # (2026-11-11T12:04-05:00)
          [--next-due YYYY-MM-DD|""]            # recurring only: overrides
                                                # the derived date until a
                                                # run is recorded
          [--routine <name>|""]                 # recurring only. Refused: a
                                                # second task on an attended
                                                # routine, or a task of the
                                                # other type; changing the
                                                # kind while it is set. Notes
                                                # a shared unattended session
                                                # and a flow with [user] steps;
                                                # editing a covered task's
                                                # clock reminds you of the
                                                # trigger at its source
          [--status later]                      # park for a later iteration
          [--status not-planned --reason "<why>"]   # reason is required
          [--status shelved --reason "<why>"]       # not needed for now;
                                                # reason required, revivable
                                                # --status draft|review on a
                                                # task with a PR is refused;
                                                # use ready / unready
TASKS verify <id> "<how the children met the goal>"
                                        # close an umbrella; the record is
                                        # required, and --status done on one
                                        # is refused in favour of this
TASKS ran <id> --record "<inputs; deviations>"
               [--flow <name[,name]>] [--date <date|timestamp>] [--rehearsal]
                                        # close an ops task with its run
                                        # record (Ran (<date>): …); --flow
                                        # omitted keeps the task's flow
                                        # field. Recurring re-arms to backlog
                                        # instead of done. Refused on a dev
                                        # task, or one with a branch/PR.
                                        # --rehearsal: a dry run, recorded
                                        # Rehearsed (<date>): … (needs a
                                        # flow; refused on a recurring task;
                                        # required on a rehearsal: true one)
TASKS pause <id> --at "<step>" --record "<what exists so far, where>"
                 [--flow <name[,name]>] [--date YYYY-MM-DD]
                                        # an ops run stopped partway:
                                        # appends Paused (<date>): …, stays
                                        # doing with its assignee. Only a
                                        # doing ops task; resume is
                                        # /ops run <id>
TASKS wait <id> --on "<who>" --by YYYY-MM-DD --at "<step>"
                --record "<what was sent, where>"
                [--flow <name[,name]>] [--date YYYY-MM-DD]
                                        # work stopped at an [external]
                                        # step or a handed-off sequence
                                        # (ops): sets waiting: <who> by
                                        # <date>, appends Waiting (<date>):
                                        # …, stays doing. Any doing task,
                                        # dev or ops; re-run moves the date.
                                        # The marker clears when the task
                                        # leaves doing
TASKS wait <id> --clear                 # the reply is in; stays doing
TASKS note <id> "<text>" [--at "<step>"] [--date YYYY-MM-DD]
                                        # ops or dev: appends Note (<date>):
                                        # [<flow> <step>] …; any status but
                                        # proposed/not-planned (done too);
                                        # moves nothing
TASKS delete <id>
TASKS show <id>
TASKS collisions <id[,id…]>             # area occupancy vs doing/draft/review;
                                        # multi-id also prints in-set overlap
                                        # and a parallel: ok|no verdict;
                                        # exit 2 if any blocker is doing;
                                        # exit 3 if every blocker's PR is open
                                        # (draft or review, any assignee) —
                                        # implement offers proceed / stack /
                                        # wait, an unattended run skips
                                        # (batch peers excluded from that check)
TASKS related "<text>" [--deps <id,id>] # existing tasks similar to <text>;
                                        # run before every add; --deps (the
                                        # new task's planned deps) adds an
                                        # `umbrella of T…:` line per open
                                        # umbrella directly holding one
TASKS list [--assignee <who>] [--status <s>] [--needs decision]
           [--type ops|dev] [--flow <name>] [--json]
                                        # --type dev also matches untyped
                                        # tasks; --flow: tasks whose flow
                                        # field records that flow
TASKS recur list [--due]                # recurring tasks + derived due dates
                                        # (overdue and never-run first);
                                        # --due limits to due/overdue now;
                                        # proposed/later/shelved/
                                        # not-planned (clock stopped) are
                                        # left out
TASKS recur ran <id> [--date <date|timestamp>]
                                        # record a run with no PR: stamp
                                        # last_run (default now), re-arm to
                                        # backlog. Refused if branch or pr is
                                        # set — land owns that run — or
                                        # while the clock is stopped
                                        # (proposed/later/shelved/
                                        # not-planned).
TASKS board [--expand] [--by-area] [--watch]
                                        # index: one line per status (or
                                        # area) of task ids; then in-play
                                        # tasks one per line, umbrella
                                        # children indented under the
                                        # parent; done/later/shelved/
                                        # not-planned fold to a count,
                                        # --expand lists those; --watch: r/a/e/c/q, arrows
                                        # scroll, space/b page, type id↵ to show
                                        # a task, c then id↵ for check (area
                                        # collisions + unfinished deps)
                                        # (./board)
TASKS iteration
TASKS iteration-close [--carry | --force]
                                        # --carry: unfinished tasks come back
                                        # at iteration-new with a fresh id,
                                        # status, branch and PR intact
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
                                        # --unattended <model-id>: unattended
                                        # runs only; marks the task
                                        # unattended:<model-id> while doing
                                        # and refuses any other claim of it
TASKS diff <id>                         # location + review diff from the
                                        # task worktree (not session cwd);
                                        # implement self-review / resume
                                        # (review: attaches origin/<branch>
                                        # if this clone has no checkout)
TASKS ship <id> --shipped "<what actually shipped>"
                [--message M] [--title T] [--body B]
                [--version-intent <intent>] [--base <branch>]
                [--batch <id,id,…>]     # commit if dirty ([n/T<id>] prefix;
                                        # [<scope> n/T<id>] on a scoped board),
                                        # push, open a draft PR if none
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
TASKS pr <id> view [--json]             # the task's PR: gh pr view, or REST
                                        # once GraphQL is refused (or with
                                        # DEVOPS_PR_TRANSPORT=rest); --json:
                                        # state, mergedAt, reviewDecision
                                        # (REST: latest approve / request-
                                        # changes per reviewer), isDraft,
                                        # base/head, mergeable, author, body,
                                        # reviews, comments
TASKS pr <id> diff                      # the PR's unified diff
TASKS pr <id> comment --body B          # conversation comment
TASKS pr <id> review --approve [--body B]
      | --request-changes --body B | --comment --body B
TASKS pr <id> close [--head <branch>]   # close it; --head acts on the open PR
                                        # from that branch instead (a leftover
                                        # the task no longer records); nothing
                                        # open is a no-op, a failed lookup an
                                        # error
```
