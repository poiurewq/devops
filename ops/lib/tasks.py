#!/usr/bin/env python3
"""Task-board CRUD for the `dev` skill.

A repo can hold one board (at <root>/.tasks/) or several (a monorepo with
<subdir>/.tasks/ per product). The script targets the nearest board at or
above cwd, or an explicit --scope; there is no single-board fallback.
Checkout-local state lives under the product root: <scope>/.dev/ (root board
→ .dev/ at the primary clone root) — boards cache, board worktree,
and task worktrees. Paths resolve via the hub (git-common-dir, or the worktree
that already owns .dev/board), not a linked task worktree's toplevel.
Each board lives ONLY on its integration branch. Mutations go through a
hidden worktree at <product>/.dev/board on a private branch (_dev-board or
_dev-board-<scope>), commit there, and push to the integration branch. When
several product boards share one integration branch, push uses rebase/retry
(policy A). Code branches never commit to .tasks/.

Stdlib + git for board CRUD. Git/gh lifecycle helpers: `claim` (implement
setup, optionally stacked on another task's review tip), `ship`
(commit/push/PR, PR base derived for a stack; optional Dev-batch stamp),
`preflight`,
`restack` (fail-closed stack rebase), `batch-gate` (stack land order),
`ready` / `unready` (draft ⇄ review, mirrored onto the PR's draft bit),
`land` / `cleanup`, `iteration-land`. Never auto-approve reviews.
"""
import argparse
import calendar
import contextlib
import datetime
import difflib
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.parse
import zoneinfo

STATUSES = ["proposed", "backlog", "planned", "doing", "draft", "review",
            "done", "shelved", "not-planned"]
# Retired status (T88): a task file still saying `later` reads as shelved
# (parse_task), and `--status later` is refused with a pointer to shelved.
RETIRED_LATER = "later"
LATER_RETIRED_ERR = ('error: the later status is retired; set the task aside '
                     'with --status shelved --reason "<why>"')
# Hottest-first list/index. Watch and static `TASKS board` / TASKS.md share
# this; STATUSES stays the pipeline (validation, rollup counts). shelved
# sits above done (T99) so set-aside work stays findable under --expand.
_WATCH_HEAD = ("review", "draft", "doing", "planned", "proposed",
               "backlog", "shelved")
WATCH_STATUSES = [s for s in _WATCH_HEAD if s in STATUSES] + [
    s for s in STATUSES if s not in _WATCH_HEAD]
# Don't block an iteration close. shelved = set aside: kept with its reason,
# holds no area, and carries over as shelved until someone revives it.
TERMINAL = ("done", "shelved", "not-planned")
# Out of umbrella progress (not done, not this iteration).
OUT_OF_PLAY = ("shelved", "not-planned")
STATUS_LABEL = {"not-planned": "Not planned", "shelved": "Shelved"}
# --status values that need --reason, and the body line each one writes.
REASON_STATUSES = {"not-planned": "Not planned", "shelved": "Shelved"}
TASKS_DIR = ".tasks"
# Flow store: one procedure per file, <scope>/.flows/<name>.md. Same home
# and rules as .tasks/ (integration branch only, written through the board
# worktree), but flows outlive iterations — nothing archives them.
FLOWS_DIR = ".flows"
# Catalog: <scope>/.catalog/<category>/<key>.md, named things tasks and flows
# point at. Same home and rules as .flows/. Its built-in categories are the
# agent, environment and routine registries (REGISTRIES); every category
# shares one key namespace.
CATALOG_DIR = ".catalog"
# Local live viewer dropped by init at <product>/board. Not .dev/board —
# that path is the hidden board worktree.
VIEWER_NAME = "board"
# On-disk board schema. Bump when board.yml / task frontmatter / .tasks layout
# changes in a way future scripts must detect. Missing schema_version on disk
# means 0 (pre-stamp boards). Never downgrade a higher version on write.
# 2: later is a valid task status (additive; older readers ignore unknown).
# 3: iteration is a positive integer identity; iteration_name and
#    iteration_started added. Pre-3 dated names fail closed (no migrate).
# 4: kind: recurring, with cadence + last_run frontmatter (additive; both
#    omitted from the file when empty, so non-recurring tasks are unchanged).
# 5: draft status between doing and review. No new fields, but an older
#    script refuses the value on update and drops those tasks from the
#    board render (it iterates its own status list).
# 6: the integrator field is a comma-separated roster. A one-name board is
#    byte-identical to schema 5; on a multi-integrator board an older script
#    fails closed (it compares the whole joined string, so land refuses for
#    everyone) rather than granting anyone merge rights it should not.
# 7: optional `type` frontmatter (`ops` = a task run through /ops flows, no
#    code, no branch, no PR; absent = dev). Omitted when empty, so dev task
#    files are byte-identical to schema 6. An older script rewriting an ops
#    task would drop the field (it renders only its own FIELDS).
# 8: `type: dev` is written explicitly on every dev task this script renders
#    (absent still reads as dev, so old files stay valid unmigrated). A
#    schema-7 script refuses `type: dev` on any add/update that validates it.
# 9: shelved status (not needed for now; revivable, carried over as shelved).
#    No new fields, but an older script refuses the value on update, drops
#    those tasks from the board render, and reads one as unfinished at close.
# 10: each `contributors` entry may carry its GitHub login, `handle (login)`
#    (bare `handle` = login not recorded yet). An older script compares whole
#    entries, so its init would re-register `Q` beside `Q (login)`.
# 11: optional `schedule` (cron expression + IANA timezone) as the clock of a
#    recurring task instead of `cadence`, and `last_run` is stamped as a
#    timestamp with offset on every run. An older script reads last_run as a
#    bare date and errors on any recurring task once it has run (and on one
#    with no cadence).
# 12: optional `routine` on a recurring task, pointing at an entry in
#    .flows/routines/. An older script drops the field on rewrite, which
#    silently takes the task off its routine.
# 13: the agent, environment and routine registries move from .flows/ into
#    .catalog/ (migrate_registries, on the first sync that finds files in
#    the old dirs), and their names share one namespace. An older script
#    reads the old dirs, so it sees no registries and writes new ones there,
#    which the next newer sync moves across.
SCHEMA_VERSION = 13
CONFIG_KEYS = ["schema_version", "integration_branch", "parent_branch",
               "iteration", "iteration_name", "iteration_started",
               "integrator", "contributors"]
SETTABLE_KEYS = ["parent_branch", "iteration",
                 "iteration_name", "iteration_started"]
# kind: optional. "" = normal task; "umbrella" = goal parent whose deps are
# direct children (leaves or nested umbrellas); "recurring" = perpetual task
# on a time cadence (see Recurring tasks below). Hierarchy lives in deps;
# reverse index is computed at board time. Readers ignore unknown kinds.
RECURRING = "recurring"
# type: "dev" = code on a branch, PR, review; "ops" = a task run through
# /ops flows: no code, no area, no branch, no PR. Absent or empty reads as
# dev, and render writes it as `dev`. An ops task that turns out to need
# code becomes a dev task and gains an area then. Orthogonal to kind (an
# ops task may be recurring).
DEV = "dev"
OPS = "ops"
# flow: optional. The flow(s) a run followed, as `<id> <name>` pairs, comma
# separated (`7 send-invoice, 3 prep-agenda`), the name as it was at the
# time. A record, not a pointer: lookups match on the id, so a flow rename
# never rewrites a task. Set by `ran` (or `update --flow` at run start).
# rehearsal: optional, `true` on an ops task that is a dry run of its flow
# (`add --rehearsal`). The field, not the `Rehearse ` title, is what makes a
# task one: `update` refuses a real run and a rehearsal of the same flow id
# both being doing (rehearsal_clash_refusal).
# distill: optional, `true` on the ops task that is a distill sitting
# (`add --distill`). Only such a task takes `distilled`, and `ran` on one
# appends a Distilled line for the sitting and its dependents (the task it
# filed, which lists the sitting in its deps).
# waiting: optional, `<who> by <YYYY-MM-DD>` — work stopped at an
# [external] step or a handed-off sequence, awaiting a third party or an
# agent's report. Set by `wait`; only a doing task
# (dev or ops) carries it, and render_task drops it the moment the task
# leaves doing, so every path out of doing clears it without knowing it
# exists.
# routine: optional, on a recurring task: the name of the routine (in
# .catalog/routines/) whose trigger starts it. A pointer that resolves through
# the routine's former names; the board derives whether that routine should
# already have started a due task (routine_stall), and stores nothing.
# unattended: optional, the model id of an unattended run that claimed the
# task (`claim --unattended`). Same lifetime as waiting — only a doing task
# carries it — so the run's ship to draft and a manual move to backlog
# clear it, and a park hands it back with `update --unattended ""`. While it
# is set, claim refuses anyone else's resume.
FIELDS = ["id", "title", "area", "status", "kind", "type", "assignee", "branch",
          "deps", "pr", "needs", "waiting", "unattended", "flow", "rehearsal",
          "distill", "created", "cadence", "schedule", "last_run", "next_due",
          "routine"]
# Written only when non-empty, so an ordinary task file is byte-identical to
# what a pre-schema-4 script produced. Older readers ignore them either way.
# `type` is not among them: render always writes it (schema 8).
OPTIONAL_FIELDS = ("waiting", "unattended", "flow", "rehearsal", "distill",
                   "cadence", "schedule", "last_run", "next_due",
                   "routine")
# Board push races on a shared integration branch: rebase onto origin and
# retry this many times before queueing locally.
PUSH_RETRIES = 3
# Wall-clock caps on one network git call (fetch/push/ls-remote/pull). A
# dropped SSH connection otherwise hangs the command indefinitely; a timeout
# returns as an ordinary failure, so fetches degrade and pushes retry/queue.
# Board-branch calls (tiny payloads) pass GIT_NETWORK_TIMEOUT_S; every other
# network call defaults to the code cap, which leaves room for a large push.
GIT_NETWORK_TIMEOUT_S = 60
GIT_CODE_NETWORK_TIMEOUT_S = 600
GIT_NETWORK_COMMANDS = ("fetch", "push", "ls-remote", "pull")
GIT_TIMEOUT_RC = 124  # run_with_deadline's exit code for a timed-out call
# Native Windows (Git for Windows): no process groups by signal, no termios,
# so a few things go the Windows way or are refused there.
WINDOWS = os.name == "nt"
# Land: merge retries when GitHub reports not-mergeable / recomputing.
# Land never rewrites the task branch; a conflict is merged forward.
LAND_RETRIES = 5
# After a push, GitHub often leaves mergeable=UNKNOWN while recomputing.
# Poll before the merge call so the first attempt is not a guaranteed failure.
LAND_MERGEABLE_TIMEOUT_S = 30
LAND_MERGEABLE_POLL_S = 1.0


def sh(args, cwd=None, check=True, timeout=None):
    if timeout is None:
        r = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    else:
        r = run_with_deadline(args, cwd, timeout)
    if check and r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        sys.exit(f"error running {' '.join(args)}:\n{err}")
    return r


def run_with_deadline(args, cwd, timeout):
    """subprocess.run with a timeout that also kills git's ssh child.

    run(timeout=) kills only git and leaves the stalled ssh running. So git
    gets its own session and the whole process group is killed. A timeout
    comes back as a failed CompletedProcess (GIT_TIMEOUT_RC), never an
    exception. On Windows the group is a new process group, killed as a
    tree by taskkill."""
    if WINDOWS:
        group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        group = {"start_new_session": True}
    p = subprocess.Popen(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, **group)
    try:
        out, err = p.communicate(timeout=timeout)
        return subprocess.CompletedProcess(args, p.returncode, out, err)
    except subprocess.TimeoutExpired:
        _kill_group(p)
        return subprocess.CompletedProcess(
            args, GIT_TIMEOUT_RC, "",
            f"{' '.join(args)} timed out after {timeout}s")
    except BaseException:
        # Ctrl-C: the terminal's SIGINT never reaches git's own session, so
        # without this git and ssh outlive the interrupted command.
        _kill_group(p)
        raise


def _kill_group(p):
    if WINDOWS:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                       capture_output=True)
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        p.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass  # a grandchild escaped the group; stop waiting on its pipes


def git(*args, cwd=None, check=True, timeout=None):
    if timeout is None and args and args[0] in GIT_NETWORK_COMMANDS:
        timeout = GIT_CODE_NETWORK_TIMEOUT_S
    return sh(["git", *args], cwd=cwd, check=check, timeout=timeout)


def gh(*args, cwd=None, check=True):
    return sh(["gh", *args], cwd=cwd, check=check)


def worktree_root(cwd=None):
    """Root of the current git worktree (where the user is standing)."""
    return git("rev-parse", "--show-toplevel", cwd=cwd).stdout.strip()


def repo_root():
    """Primary clone / hub worktree — not a linked task worktree.

    Board mutator paths, product .dev/, and git worktree add must use this so
    board commands work when cwd is inside a task worktree. Scope discovery
    still walks the *current* worktree (see find_scope / nearest_scope).
    """
    r = git("rev-parse", "--path-format=absolute", "--git-common-dir",
            check=False)
    if r.returncode == 0:
        common = r.stdout.strip()
    else:
        # Git < 2.31: no --path-format
        common = git("rev-parse", "--git-common-dir").stdout.strip()
    if not os.path.isabs(common):
        common = os.path.abspath(common)
    common = os.path.normpath(common)
    # Only a .git *directory* is the hub's git dir. --git-common-dir does
    # not return a worktree's .git file; a relative common dir resolved
    # against that worktree's cwd can land on it — its parent is the
    # worktree, not the hub.
    if os.path.basename(common) == ".git" and os.path.isdir(common):
        return os.path.dirname(common)
    hub = hub_from_board_worktrees()
    if hub:
        return hub
    return worktree_root()


def _is_board_worktree_path(path):
    """True if path is a board mutator: …/.dev/board (root or scoped)."""
    norm = os.path.normpath(os.path.realpath(path))
    return (os.path.basename(norm) == "board"
            and os.path.basename(os.path.dirname(norm)) == ".dev")


def hub_from_board_worktrees(cwd=None):
    """Hub checkout that already owns a board mutator worktree.

    Used when git-common-dir is not <hub>/.git (bare repo, separate-git-dir).
    The board path is <hub>/.dev/board or <hub>/<scope>/.dev/board; the hub is
    that product directory's git toplevel. Does not use worktree-list paths for
    the hub itself: a separate-git-dir clone lists the git dir, not the tree.
    Returns None before the first board worktree exists (init).
    """
    try:
        here = worktree_root(cwd)
    except SystemExit:
        return None
    hubs = []
    for t in list_worktrees(here):
        if not _is_board_worktree_path(t["path"]):
            continue
        product = os.path.dirname(os.path.dirname(os.path.realpath(t["path"])))
        try:
            hub = worktree_root(cwd=product)
        except SystemExit:
            continue
        hubs.append(os.path.realpath(hub))
    if not hubs:
        return None
    return min(hubs, key=len)


def git_path(root, rel):
    """Resolve a path inside the git dir (e.g. info/exclude).

    Uses --git-path, not --git-dir: worktree git-dirs do not own shared
    files such as info/exclude.
    """
    r = git("rev-parse", "--path-format=absolute", "--git-path", rel,
            cwd=root, check=False)
    if r.returncode == 0:
        return os.path.normpath(r.stdout.strip())
    p = git("rev-parse", "--git-path", rel, cwd=root).stdout.strip()
    if not os.path.isabs(p):
        p = os.path.join(root, p)
    return os.path.normpath(p)


def has_remote(root):
    return git("remote", "get-url", "origin", cwd=root, check=False).returncode == 0


def ref_exists(root, ref):
    return git("rev-parse", "--verify", "--quiet", ref, cwd=root, check=False).returncode == 0


def is_ancestor(root, maybe_anc, ref):
    """True if maybe_anc is an ancestor of ref (equal counts)."""
    r = git("merge-base", "--is-ancestor", maybe_anc, ref, cwd=root, check=False)
    return r.returncode == 0


def tdir(scope):
    """Board dir relative to repo root ('.tasks' or '<scope>/.tasks'),
    `/`-separated: it also names a path in git's `<rev>:<path>`, which
    rejects backslashes."""
    return scope_form(os.path.normpath(os.path.join(scope, TASKS_DIR)))


def fdir(scope):
    """Flow store dir relative to repo root ('.flows' or '<scope>/.flows'),
    `/`-separated like tdir."""
    return scope_form(os.path.normpath(os.path.join(scope, FLOWS_DIR)))


def cdir(scope):
    """Catalog dir relative to repo root ('.catalog' or '<scope>/.catalog'),
    `/`-separated like tdir."""
    return scope_form(os.path.normpath(os.path.join(scope, CATALOG_DIR)))


def shown_path(path):
    """A path as printed for the user: one separator style (the OS's), since
    a root from git (`C:/…`) joined with a scope would otherwise mix them."""
    return os.path.normpath(path)


def product_root(root, scope):
    """Directory that owns the board: git toplevel for scope '.', else
    <toplevel>/<scope>. `root` is the primary clone (repo_root)."""
    if scope in (".", ""):
        return root
    return os.path.join(root, scope)


def viewer_path(root, scope):
    """Local live-viewer script: <product>/board."""
    return os.path.join(product_root(root, scope), VIEWER_NAME)


def viewer_ignore_line(scope):
    """Gitignore line for the viewer. Anchored so a project `board/` is safe."""
    rel = VIEWER_NAME if scope in (".", "") else os.path.join(scope, VIEWER_NAME)
    return "/" + rel.replace(os.sep, "/")


def append_ignore_line(path, line):
    """Append `line` to a gitignore-style file if missing. True if wrote."""
    existing = open(path).read() if os.path.exists(path) else ""
    if line in existing.splitlines():
        return False
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", newline="\n") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(line + "\n")
    return True


# Thin wrapper init writes. __TASKS_PY__ is replaced with repr(path).
BOARD_VIEWER_SCRIPT = '''\
#!/usr/bin/env python3
"""Local board viewer (r/a/e/c/f/q; arrows scroll; space/b page; type id↵). `./board update` rewrites this file from the installed skill. Written by dev init; left alone if you edit it."""
import os, sys
TASKS = __TASKS_PY__
os.chdir(os.path.dirname(os.path.abspath(__file__)))
if not os.path.isfile(TASKS):
    sys.exit("error: dev skill not found at %s — this wrapper is stale; regenerate it by running `python3 <dev-skill>/scripts/tasks.py board` in %s" % (TASKS, os.getcwd()))
ARGS = ["--refresh-viewer"] if sys.argv[1:2] == ["update"] else ["--watch"]
os.execv(sys.executable, [sys.executable, TASKS, "board"] + ARGS)
'''

# Code lines a generated ./board may contain (any template generation).
# Opening docstring and blanks are ignored; anything else is a user edit.
_STOCK_VIEWER_LINE = re.compile(
    r"^(?:"
    r"#!/usr/bin/env python3"
    r"|import os, sys"
    r"|TASKS = (?:'[^']*'|\"[^\"]*\")"
    r"|os\.chdir\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)"
    r"|if not os\.path\.isfile\(TASKS\):"
    r"|    sys\.exit\(.+\)"
    r"|ARGS = \[\"--refresh-viewer\"\] if sys\.argv\[1:2\] == \[\"update\"\] else \[\"--watch\"\]"
    r"|os\.execv\(sys\.executable, \[sys\.executable, TASKS, \"board\", \"--watch\"\]\)"
    r"|os\.execv\(sys\.executable, \[sys\.executable, TASKS, \"board\"\] \+ ARGS\)"
    r")$"
)


# A task worktree is deleted at land/cleanup; a skill copy living there
# must never be baked into the long-lived hub wrapper.
_EPHEMERAL_SKILL_PATH = re.compile(r"(^|/)\.dev/worktrees(/|$)")


def skill_path_is_ephemeral(path):
    """True if this copy of the skill lives under some product's
    .dev/worktrees/ (a task worktree, deleted at land)."""
    return bool(_EPHEMERAL_SKILL_PATH.search(
        os.path.abspath(path).replace("\\", "/")))


def viewer_tasks_py(real):
    """The tasks.py path ./board bakes, given this file's real path.

    Resolved, unlike invoking_skill: /dev and /ops reach lib/ through
    different skill-dir links, and baking either would flip the wrapper
    back and forth between them. Where each skill carries its own lib/ (the
    published tree, a self-contained copy) resolving is not enough, since
    the two real paths differ: there dev's copy is baked whichever skill
    ran, as the shared lib/ reads as dev too.
    """
    skill_dir = os.path.dirname(os.path.dirname(real))
    dev_copy = os.path.join(os.path.dirname(skill_dir), "dev", "lib",
                            "tasks.py")
    if os.path.isfile(os.path.join(skill_dir, "SKILL.md")) \
            and os.path.isfile(dev_copy):
        return dev_copy
    return real


def viewer_script():
    """Current ./board contents for this install."""
    return BOARD_VIEWER_SCRIPT.replace(
        "__TASKS_PY__", repr(viewer_tasks_py(os.path.realpath(__file__))))


def viewer_is_stock(text):
    """True if text is still an init-generated thin wrapper.

    Docstring and TASKS path may drift; extra statements or a different
    command mean the user edited it.
    """
    text = text.replace("\r\n", "\n")
    text = re.sub(
        r"(?s)\A(#!.*\n)?(?:\n)*(\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?''')[ \t]*\n",
        r"\1",
        text,
        count=1,
    )
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if not any('TASKS, "board"' in ln for ln in lines):
        return False
    return all(_STOCK_VIEWER_LINE.match(ln) for ln in lines)


def ensure_board_viewer(root, scope, force=False):
    """Write <product>/board if missing or still a stock wrapper.

    Returns (path, wrote). Leaves a user-edited file and a directory alone;
    force overwrites an edited one (./board update). Never writes when this
    copy of the skill is ephemeral (skill_path_is_ephemeral), nor on
    Windows, where the live viewer does not run.
    """
    dest = viewer_path(root, scope)
    if WINDOWS or os.path.isdir(dest):
        return dest, False
    content = viewer_script()
    if os.path.isfile(dest):
        try:
            existing = open(dest, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            existing = None
        if existing == content:
            return dest, False
        if not force and (existing is None or not viewer_is_stock(existing)):
            return dest, False
    if skill_path_is_ephemeral(__file__):
        print(f"warning: leaving ./{VIEWER_NAME} alone — this copy of the "
              f"skill is in a task worktree ({os.path.abspath(__file__)}), "
              f"which is deleted at land; run 'board' from the installed "
              f"skill to refresh the wrapper", file=sys.stderr)
        return dest, False
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.chmod(dest, 0o755)
    return dest, True


def board_branch_name(scope):
    """Private worktree branch for this product's board mutator. Distinct per
    scope so multiple product boards can each hold a worktree in one clone."""
    if scope in (".", ""):
        return "_dev-board"
    return "_dev-board-" + scope.replace("/", "-").replace("\\", "-")


def board_worktree_rel(scope):
    """Path of the board worktree relative to the git toplevel."""
    if scope in (".", ""):
        return os.path.join(".dev", "board")
    return os.path.join(scope, ".dev", "board")


# ---------- local (per-product, per-checkout, gitignored) state ----------

def dev_dir(root, scope):
    d = os.path.join(product_root(root, scope), ".dev")
    os.makedirs(d, exist_ok=True)
    return d


def read_local(root, scope, name):
    p = os.path.join(product_root(root, scope), ".dev", name)
    if os.path.exists(p):
        with open(p) as f:
            return f.read().strip()
    return None


def read_cache(root, scope):
    p = os.path.join(product_root(root, scope), ".dev", "boards.json")
    if os.path.exists(p):
        with open(p) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"warning: ignoring unreadable {p}", file=sys.stderr)
    return {}


def cached_board(root, scope):
    """True if this product's boards.json names a branch for `scope`."""
    return bool(read_cache(root, scope).get(scope))


def write_cache(root, scope, branch):
    c = read_cache(root, scope)
    c[scope] = branch
    with open(os.path.join(dev_dir(root, scope), "boards.json"), "w") as f:
        json.dump(c, f, indent=1)


SCOPE_OVERRIDE = None  # set from --scope in main()


def scope_form(rel):
    """A scope as the board writes it: `/`-separated on every OS, since it
    names branches, PR titles and commit subjects every clone shares."""
    return rel.replace(os.sep, "/")


def discover_boards(root):
    """All board scopes visible in the checkout (shallow scan for board.yml)."""
    scopes = set()
    for pat in (".tasks", "*/.tasks", "*/*/.tasks", "*/*/*/.tasks"):
        for p in glob.glob(os.path.join(root, pat, "board.yml")):
            d = os.path.dirname(os.path.dirname(p))
            scopes.add(scope_form(os.path.relpath(d, root)))
    return sorted(scopes)


def find_scope(root):
    """Board to target: --scope override, else nearest board at/above cwd.
    No single-board fallback — cwd under the product or --scope is required.

    Walk the *current* worktree so a task worktree still resolves scope
    `dev` (not a path under .dev/worktrees/…). Board paths use primary
    `root` (repo_root)."""
    if SCOPE_OVERRIDE:
        scope = os.path.normpath(SCOPE_OVERRIDE)
        if scope != "." and (os.path.isabs(scope) or scope.startswith("..")):
            sys.exit("error: --scope must be a subdir path relative to the repo root")
        return scope_form(scope)
    # Prefer the worktree containing cwd (task worktrees are linked trees).
    try:
        wt = worktree_root()
    except SystemExit:
        wt = root
    s = nearest_scope(wt, root)
    if s is not None:
        return s
    # cwd outside any worktree but under primary: walk primary
    if not same_path(wt, root):
        s = nearest_scope(root, root)
        if s is not None:
            return s
    boards = discover_boards(root)
    if boards:
        sys.exit("error: no board at or above cwd; boards exist at: "
                 f"{', '.join(boards)}. cd into one or pass --scope <subdir>")
    return None


def nearest_scope(walk_root, primary=None):
    """Nearest board at or above cwd within walk_root: a checkout board.yml,
    or — when `primary` (repo_root) is given — that product's boards.json
    cache at the matching path in the primary clone. The cache is what init
    leaves behind while the checkout has not pulled the new board yet, and
    reading it from primary lets a task worktree resolve the same way."""
    root_abs = os.path.realpath(walk_root)
    cur = os.path.realpath(os.getcwd())
    if not path_is_inside(cur, root_abs):
        cur = root_abs
    probe = cur
    while True:
        at_root = same_path(probe, root_abs)
        rel = "." if at_root else scope_form(os.path.relpath(probe, root_abs))
        if os.path.exists(os.path.join(probe, TASKS_DIR, "board.yml")):
            return rel
        if primary is not None and cached_board(primary, rel):
            return rel
        if at_root:
            break
        probe = os.path.dirname(probe)
    return None


def integration_branch(root, scope):
    """From the checkout's board.yml for this scope, else the product cache."""
    p = os.path.join(root, tdir(scope), "board.yml")
    if os.path.exists(p):
        with open(p) as f:
            cfg = parse_kv(f.read())
        if cfg.get("integration_branch"):
            return cfg["integration_branch"]
    b = read_cache(root, scope).get(scope)
    if b:
        return b
    sys.exit(f"error: no board found ({tdir(scope)}/board.yml). "
             "Run: tasks.py init --name <you>")


# ---------- board worktree ----------

def ensure_worktree(root, scope, branch):
    rel = board_worktree_rel(scope)
    bw = os.path.join(root, rel)
    if os.path.exists(os.path.join(bw, ".git")):
        return bw
    git("worktree", "prune", cwd=root, check=False)
    os.makedirs(os.path.dirname(bw), exist_ok=True)
    git("fetch", "origin", branch, cwd=root, check=False,
        timeout=GIT_NETWORK_TIMEOUT_S)
    start = f"origin/{branch}" if ref_exists(root, f"origin/{branch}") else branch
    if not ref_exists(root, start):
        sys.exit(f"error: integration branch '{branch}' not found locally or on origin")
    private = board_branch_name(scope)
    git("worktree", "add", "-B", private, rel, start, cwd=root)
    return bw


def unpushed_board_commits(bw):
    """Board commits a failed push left queued: on the board worktree's HEAD
    but on no origin branch and no other local branch. Being ahead of the
    branch being synced is not enough — after a pointer hop HEAD holds
    another branch's pushed history, which is not a queue."""
    return git("rev-list", "--count", "HEAD", "--not", "--exclude=_dev-board*",
               "--branches", "--remotes=origin", cwd=bw).stdout.strip() != "0"


def sync_board(root, scope, branch, owner=None):
    """Bring the product board worktree up to date with the freshest board state.

    Queued commits belong to `owner` (the branch the board last resolved
    to; default `branch`) and are replayed and flushed only when syncing
    that branch. Syncing any other branch while they wait leaves the
    worktree alone, so a pointer hop never carries one board's commits
    onto another; resolve_board decides what to do with them.

    A failed fetch leaves the board on the local copy; BOARD_SYNC_FAILURE
    says so, for the viewer and `board` to show."""
    global BOARD_SYNC_FAILURE
    bw = ensure_worktree(root, scope, branch)
    r = git("fetch", "origin", branch, cwd=bw, check=False,
            timeout=GIT_NETWORK_TIMEOUT_S)
    if r.returncode != 0 and has_remote(root):
        BOARD_SYNC_FAILURE = sync_failure_line(branch, r)
    upstream = f"origin/{branch}" if ref_exists(root, f"origin/{branch}") else branch
    if not ref_exists(root, upstream):
        sys.exit(f"error: integration branch '{branch}' not found locally or on origin")
    if not unpushed_board_commits(bw):
        git("reset", "--hard", upstream, cwd=bw)
    elif (owner or branch) == branch:
        # queued offline commits: replay them on top of the fresh upstream
        r = git("rebase", upstream, cwd=bw, check=False)
        if r.returncode != 0:
            git("rebase", "--abort", cwd=bw, check=False)
            sys.exit(f"error: queued board commits conflict with {upstream}; "
                     f"resolve manually in {board_worktree_rel(scope)}")
        flush_queued_board_commits(root, scope, branch, bw)
    return bw


# Set by sync_board when its fetch fails: the board just read is the local
# copy. resolve_board clears it, so it describes the latest sync only.
BOARD_SYNC_FAILURE = ""
BOARD_SYNCING = "syncing board with origin…"


def sync_failure_line(branch, r):
    """One line saying the board shown is the local copy, and why."""
    if r.returncode == GIT_TIMEOUT_RC:
        why = f"git fetch origin {branch} timed out after {GIT_NETWORK_TIMEOUT_S}s"
    else:
        first = next((ln.strip() for ln in git_err(r).splitlines()
                      if ln.strip()), "")
        why = f"git fetch origin {branch} failed: {first}"
    return f"warning: showing the local board copy, not synced ({why})"


def git_err(r):
    """Stderr (or stdout) of a failed git run, for a warning line."""
    return (r.stderr or r.stdout or "").strip() or "(no output)"


def flush_queued_board_commits(root, scope, branch, bw):
    """Push board commits an earlier failed push left queued (best-effort).

    board_commit promises the queue goes out on the next board operation, but
    only board_commit pushes — without this a read-only command would leave
    the commit sitting on the private branch indefinitely.
    """
    if not has_remote(root):
        return
    r = git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=bw, check=False,
            timeout=GIT_NETWORK_TIMEOUT_S)
    if r.returncode != 0:
        print(f"warning: board commits are still queued locally on "
              f"{board_branch_name(scope)}; push failed:\n{git_err(r)}",
              file=sys.stderr)
        return
    print(f"pushed queued board commits to {branch}", file=sys.stderr)
    update_local_branch(root, scope, branch,
                        git("rev-parse", "HEAD", cwd=bw).stdout.strip())


_STALE_WARNED = set()  # (scope, branch) already warned this process


def resolve_board(root, scope):
    """Sync the board worktree, following integration_branch pointers: a
    branch whose board.yml names another branch (e.g. the parent after an
    iteration switch) redirects there. Returns (branch, bw); caches the
    resolved branch.

    Pointers are read from each branch's upstream, not the worktree, which
    sync_board leaves untouched while another branch's commits are queued.
    Queued commits that cannot reach their own branch before the board
    moves on are refused rather than replayed onto the next one."""
    global BOARD_SYNC_FAILURE
    BOARD_SYNC_FAILURE = ""
    branch = integration_branch(root, scope)
    owner = read_cache(root, scope).get(scope) or branch
    bw = sync_board(root, scope, branch, owner)
    for _ in range(3):
        upstream = (f"origin/{branch}" if ref_exists(root, f"origin/{branch}")
                    else branch)
        r = git("show", f"{upstream}:{tdir(scope)}/board.yml", cwd=root,
                check=False)
        if r.returncode != 0:
            break
        target = parse_kv(r.stdout).get("integration_branch") or branch
        if target == branch:
            break
        branch = target
        bw = sync_board(root, scope, branch, owner)
    if branch != owner and unpushed_board_commits(bw):
        sys.exit(f"error: board commits queued on {board_branch_name(scope)} "
                 f"for '{owner}' were not pushed, and the board has moved to "
                 f"'{branch}'. They are kept: re-run once pushing to "
                 f"'{owner}' works, or discard them with: git -C "
                 f"{board_worktree_rel(scope)} reset --hard origin/{owner}")
    if read_cache(root, scope).get(scope) != branch:
        write_cache(root, scope, branch)
    # A command may resolve several times (board re-read after git work,
    # every watch refresh); the warning is one per command, so once per
    # process for each board it lands on.
    if (scope, branch) not in _STALE_WARNED:
        _STALE_WARNED.add((scope, branch))
        warn_stale_checkout(root, scope, branch, bw)
    return branch, bw


def checkout_board_branch(root, scope):
    """integration_branch named by the checkout's own board.yml, or ''."""
    p = os.path.join(root, tdir(scope), "board.yml")
    if not os.path.exists(p):
        return ""
    with open(p) as f:
        return (parse_kv(f.read()).get("integration_branch") or "").strip()


def closed_iteration_branches(bw, scope):
    """Integration branches of closed iterations (log.md `branch:` lines)."""
    log = os.path.join(bw, tdir(scope), "log.md")
    if not os.path.exists(log):
        return set()
    with open(log) as f:
        return set(re.findall(r"(?m)^branch: (\S+)", f.read()))


def warn_stale_checkout(root, scope, branch, bw):
    """Warn when the checkout is not on the board's integration branch.

    Three ways to get here after a branched iteration roll. Redirected
    before a pull: the checkout's board.yml names an old branch whose
    board.yml points on. Redirected after a pull: the pointer is in the
    checkout's board.yml too, so only the checkout's git branch is stale —
    recognised as one log.md says a closed iteration lived on, so a
    feature branch on the hub is not mistaken for one. Not redirected: the
    old branch's pointer push was refused (or it predates old-branch
    pointers), so the board is the closed iteration itself and only the
    parent says where work moved.
    Warn only — the redirect, where there is one, is resolve_board's.
    """
    named = checkout_board_branch(root, scope)
    current = current_branch_name(root)
    stale = ""
    if named and named != branch:
        stale = named
    elif (current and current != branch
          and current in closed_iteration_branches(bw, scope)):
        stale = current
    if stale and current not in ("", "HEAD", stale):
        # A feature branch cut from the old iteration: name the branch it
        # is on, and do not tell it to check out away from its own work.
        print(f"warning: your checkout is on '{current}', which carries the "
              f"board of '{stale}', but the board is on '{branch}'. Move "
              f"that work onto '{branch}'.", file=sys.stderr)
        return
    if stale:
        print(f"warning: your checkout is on '{stale}', but the board is on "
              f"'{branch}'. Switch your checkout: git checkout {branch}",
              file=sys.stderr)
        return
    warn_closed_iteration(root, scope, branch, bw)


def warn_closed_iteration(root, scope, branch, bw):
    """Warn when this board is a closed iteration whose parent already
    points at the next one.

    A branched iteration-new also points the old branch at the new one;
    this covers an old branch whose pointer push was refused, where only
    the parent's board.yml says where work moved. The log.md
    close heading is the cheap gate; the parent is fetched and read only
    once the iteration is closed.
    """
    yml = board_yml_path(bw, scope)
    log = os.path.join(bw, tdir(scope), "log.md")
    if not (os.path.exists(yml) and os.path.exists(log)):
        return
    with open(yml) as f:
        cfg = parse_kv(f.read())
    parent = (cfg.get("parent_branch") or "").strip()
    idx = (cfg.get("iteration") or "").strip()
    # An unreadable index is not this check's to fail on.
    if not parent or not idx.isdigit():
        return
    with open(log) as f:
        if not log_has_close_section(f.read(), idx):
            return
    git("fetch", "origin", parent, cwd=bw, check=False,
        timeout=GIT_NETWORK_TIMEOUT_S)
    ref = f"origin/{parent}" if ref_exists(root, f"origin/{parent}") else parent
    r = git("show", f"{ref}:{tdir(scope)}/board.yml", cwd=root, check=False)
    if r.returncode != 0:
        return
    target = (parse_kv(r.stdout).get("integration_branch") or "").strip()
    if target and target != branch:
        print(f"warning: iteration {idx} on '{branch}' is "
              f"closed and the board has moved to '{target}'. Switch your "
              f"checkout: git checkout {target}", file=sys.stderr)


def ctx():
    root = repo_root()
    scope = find_scope(root)
    if scope is None:
        sys.exit(f"error: no board found (no {TASKS_DIR}/board.yml from cwd up "
                 "to repo root). Run: tasks.py init --name <you>")
    branch, bw = resolve_board(root, scope)
    err = missing_board_error(bw, scope, branch)
    if err:
        sys.exit(err)
    migrate_registries(root, scope, branch, bw)
    return root, scope, branch, bw


def missing_board_error(bw, scope, branch):
    """The boards.json cache only locates a board; the synced board worktree
    decides whether it exists (a removed board, or an init that died after
    write_cache). Returns the error to exit with, or None."""
    if os.path.exists(board_yml_path(bw, scope)):
        return None
    return (f"error: no board at '{scope}' on '{branch}' (stale "
            f".dev/boards.json?); re-run init or remove that entry")


def invoking_skill():
    """The skill this script runs as ('dev', 'ops'): the skill dir it was
    reached through (<skill>/lib/tasks.py, never resolved). Run from the
    package's own lib/ there is no SKILL.md beside it; defaults to 'dev'."""
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isfile(os.path.join(skill_dir, "SKILL.md")):
        return os.path.basename(skill_dir)
    return "dev"


def scoped_message(scope, message):
    """Board commit subject: 'dev: …' → '<skill>: …', or '<skill>(<scope>): …'
    on a scoped board, so an /ops commit never names /dev and boards sharing
    one integration branch stay distinguishable in the log."""
    if not message.startswith("dev: "):
        return message
    prefix = invoking_skill() if scope == "." else f"{invoking_skill()}({scope})"
    return f"{prefix}: {message[len('dev: '):]}"


def board_commit(root, branch, bw, scope, message, queue=True):
    """Commit this board's changes, push to its integration branch (rebase/
    retry when the tip moved — shared-main policy A), fast-forward local
    checkouts best-effort. A failed push queues the commit on the private
    branch and leaves local integration where it is; the next board
    operation flushes it (flush_queued_board_commits). With queue=False the
    caller discards a failed commit itself, so nothing promises a flush.
    Returns whether the commit reached origin (True when there is no
    remote)."""
    paths = [tdir(scope)]
    for d in (fdir(scope), cdir(scope)):
        if os.path.isdir(os.path.join(bw, d)):
            paths.append(d)
    if os.path.exists(os.path.join(bw, ".gitignore")):
        paths.append(".gitignore")
    git("add", "-A", "--", *paths, cwd=bw)
    if git("diff", "--cached", "--quiet", cwd=bw, check=False).returncode == 0:
        print("no changes")
        return True
    git("commit", "-m", scoped_message(scope, message), cwd=bw)
    sha = git("rev-parse", "HEAD", cwd=bw).stdout.strip()
    private = board_branch_name(scope)
    if has_remote(root):
        pushed = False
        last_err = ""
        for attempt in range(1, PUSH_RETRIES + 1):
            r = git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=bw,
                    check=False, timeout=GIT_NETWORK_TIMEOUT_S)
            if r.returncode == 0:
                pushed = True
                break
            last_err = git_err(r)
            if r.returncode == GIT_TIMEOUT_RC:
                # A stalled network will stall the retries too: queue now.
                break
            # Non-ff or race: fetch, rebase onto origin, retry (policy A).
            git("fetch", "origin", branch, cwd=bw, check=False,
                timeout=GIT_NETWORK_TIMEOUT_S)
            upstream = f"origin/{branch}"
            if not ref_exists(root, upstream):
                break
            rr = git("rebase", upstream, cwd=bw, check=False)
            if rr.returncode != 0:
                git("rebase", "--abort", cwd=bw, check=False)
                sys.exit(f"error: board push rebase conflict with {upstream}; "
                         f"resolve manually in {board_worktree_rel(scope)}")
            sha = git("rev-parse", "HEAD", cwd=bw).stdout.strip()
            if attempt < PUSH_RETRIES:
                # A non-race failure (auth, network, hook) rebases to a no-op,
                # so without this all attempts fire in milliseconds.
                print(f"  board push attempt {attempt} failed; retry…",
                      file=sys.stderr)
                time.sleep(min(2 * attempt, 8))
        if not pushed and not queue:
            print(f"warning: push to '{branch}' failed:\n{last_err}",
                  file=sys.stderr)
            return False
        if not pushed:
            # Do NOT fast-forward local integration: the commit lives on the
            # private branch, and moving integration would make the next
            # preflight report in-scope .tasks/ ahead — whose discard remedy
            # would delete this very task.
            print(f"warning: push failed; board commit queued locally on "
                  f"{private} and will be pushed on the next board operation."
                  f"\n{last_err}", file=sys.stderr)
            return False
    update_local_branch(root, scope, branch, sha)
    return True


def update_local_branch(root, scope, branch, sha):
    """Best-effort: fast-forward the local branch / checkout to include sha."""
    bw_path = path_key(os.path.join(root, board_worktree_rel(scope)))
    out = git("worktree", "list", "--porcelain", cwd=root).stdout
    checkout = None
    path = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line.split(" ", 1)[1]
        elif line == f"branch refs/heads/{branch}":
            if path_key(path) != bw_path:
                checkout = path
    if checkout:
        clean = git("status", "--porcelain", cwd=checkout, check=False).stdout.strip() == ""
        if clean:
            git("merge", "--ff-only", sha, cwd=checkout, check=False)
    else:
        git("branch", "-f", branch, sha, cwd=root, check=False)


# ---------- board.yml / areas.md ----------

def board_yml_path(bw, scope):
    return os.path.join(bw, tdir(scope), "board.yml")


def board_schema_version(cfg):
    """Integer schema version from board.yml; missing or invalid → 0."""
    raw = (cfg.get("schema_version") or "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def ensure_schema_version(cfg):
    """Stamp schema_version for write; never downgrade a newer board."""
    if board_schema_version(cfg) < SCHEMA_VERSION:
        cfg["schema_version"] = str(SCHEMA_VERSION)
    return cfg


def read_board_cfg(bw, scope):
    with open(board_yml_path(bw, scope)) as f:
        cfg = parse_kv(f.read())
    v = board_schema_version(cfg)
    if v > SCHEMA_VERSION:
        print(f"warning: board schema_version {v} is newer than this tasks.py "
              f"(supports {SCHEMA_VERSION}); unknown fields may be ignored",
              file=sys.stderr)
    # Schema 3: identity is a positive integer. No migrate-on-read.
    iteration_index(cfg)
    return cfg


def board_integrators(cfg):
    """The integrator roster: one comma-separated board.yml key, not a list
    of keys, so a single-integrator board writes exactly what it always did.
    Callers ask this or is_integrator(); nothing else splits the field."""
    return [n.strip() for n in (cfg.get("integrator") or "").split(",")
            if n.strip()]


def is_integrator(ident, cfg):
    return ident in board_integrators(cfg)


_CONTRIBUTOR_RE = re.compile(r"(.+?)\s*\(([^()]*)\)")


def board_contributors(cfg):
    """The contributor roster as (handle, login) pairs, in board order.

    One comma-separated board.yml key; each entry is `handle (login)`, or a
    bare `handle` whose GitHub login is not recorded yet (login ""). Callers
    go through this and format_contributors; nothing else splits the field."""
    out = []
    for e in (cfg.get("contributors") or "").split(","):
        e = e.strip()
        if not e:
            continue
        m = _CONTRIBUTOR_RE.fullmatch(e)
        out.append((m.group(1).strip(), m.group(2).strip()) if m else (e, ""))
    return out


def format_contributors(entries):
    return ", ".join(f"{h} ({l})" if l else h for h, l in entries)


def valid_handle(name):
    return bool(name) and not any(c in name for c in ",()")


def same_login(a, b):
    # GitHub logins are case-insensitive.
    return bool(a) and bool(b) and a.lower() == b.lower()


def roster_join(entries, name, login, formers=None):
    """Resolve an init against the contributor roster. Pure: returns
    (entries, handle, error); error is None on success, and entries is the
    roster to write (unchanged when nothing needs recording).

    One GitHub login maps to exactly one handle, and handles are unique
    ignoring case (`Q` and `q` would read as one person). No name: the
    login picks the handle, and the error names any login-less handles so
    an existing contributor knows to record theirs. A name: registered, or
    its missing login filled in — refused when the login is already another handle, or
    the handle already belongs to another login. `login` is required: init
    refuses before this when gh cannot read one, so no handle is ever taken
    on trust. A handle in `formers` (board_former_handles) stays reserved
    for the contributor who renamed away from it."""
    held = next((h for h, l in entries if same_login(l, login)), None)
    if name is None:
        if held is None:
            bare = [h for h, l in entries if not l]
            return entries, None, (
                f"GitHub login '{login}' is not on this board's roster. "
                + (f"Already on it as one of {', '.join(bare)} (no GitHub "
                   "login recorded yet): init --name <that handle> records "
                   "it. " if bare else "")
                + f"New contributor: init --name <handle> (suggested: "
                f"{login}). Already a contributor under another GitHub "
                "account: gh auth switch to it, then re-run init")
        return entries, held, None
    if not valid_handle(name):
        return entries, None, "handle must be non-empty and free of , ( )"
    if held is not None and held != name:
        return entries, None, (
            f"GitHub login '{login}' is already '{held}' on this board (one "
            f"GitHub account, one handle); run init without --name to join "
            f"as '{held}'")
    was = former_holder(formers, name)
    if was is not None and name not in [h for h, _ in entries]:
        return entries, None, (
            f"handle '{name}' is a former handle of '{was}' and stays "
            f"reserved; pick another handle, or init without --name if "
            f"'{was}' is you")
    # Only a new handle is checked: a pre-existing case pair (a roster
    # from before this rule) must still be able to record its logins.
    clash = None if name in [h for h, _ in entries] else next(
        (h for h, _ in entries if h.lower() == name.lower()), None)
    if clash is not None:
        return entries, None, (
            f"handle '{name}' differs from '{clash}' only by case; pick "
            f"another handle, or init --name {clash} if that one is yours")
    for i, (h, l) in enumerate(entries):
        if h != name:
            continue
        if same_login(l, login):
            return entries, name, None
        if l:
            return entries, None, (
                f"handle '{name}' belongs to GitHub login '{l}', not "
                f"'{login}'; pick another handle, or gh auth switch to "
                f"'{l}' if that account is yours")
        return entries[:i] + [(h, login)] + entries[i + 1:], name, None
    return entries + [(name, login)], name, None


def login_backfill(entries, handle, login):
    """Record `login` on `handle` when the roster has that handle with no
    login yet. Pure: returns the roster. Never registers a handle, never
    replaces a recorded login, and never records a login another handle
    already holds (one login, one handle)."""
    if not login or (handle, "") not in entries:
        return entries
    if any(same_login(l, login) for _, l in entries):
        return entries
    return [(h, login) if (h, l) == (handle, "") else (h, l)
            for h, l in entries]


def board_former_handles(cfg):
    """Renamed-away handles as {old: current}, from the additive
    `former_handles` key (`old (current), …`; handles are free of , ( ), so
    the same entry shape as `contributors` parses unambiguously). Kept out
    of `contributors` so no schema bump: an older script preserves the key
    and ignores it."""
    out = {}
    for e in (cfg.get("former_handles") or "").split(","):
        m = _CONTRIBUTOR_RE.fullmatch(e.strip())
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def set_former_handles(cfg, formers):
    if formers:
        cfg["former_handles"] = ", ".join(f"{o} ({c})"
                                          for o, c in formers.items())
    else:
        cfg.pop("former_handles", None)


def former_holder(formers, name):
    """The current handle that once was `name` (ignoring case), else None."""
    return next((c for o, c in (formers or {}).items()
                 if o.lower() == (name or "").lower()), None)


def contributor_rename_refusal(ident, old, new, entries, integrators,
                               formers):
    """Why `contributor rename <old> <new>` must not run, or None. Pure.
    Yourself or an integrator; `new` is a valid handle unique ignoring case
    (`old` itself excepted, so a case-only rename works), and not a former
    handle of anyone else — a former handle stays reserved."""
    handles = [h for h, _ in entries]
    if old not in handles:
        was = former_holder(formers, old)
        return (f"'{old}' is not a contributor"
                + (f" (it is a former handle of '{was}')" if was else
                   f" ({', '.join(handles) or 'none'})"))
    if ident != old and ident not in integrators:
        return (f"only '{old}' themself or a board integrator "
                f"({', '.join(integrators) or 'unset'}) can rename them "
                f"(whoami='{ident}')")
    if not valid_handle(new):
        return "handle must be non-empty and free of , ( )"
    if new == old:
        return f"'{old}' is already that handle"
    clash = next((h for h in handles
                  if h != old and h.lower() == new.lower()), None)
    if clash is not None:
        return f"handle '{new}' is taken by '{clash}' (handles are unique " \
               "ignoring case)"
    was = former_holder(formers, new)
    if was is not None and was != old:
        return (f"handle '{new}' is a former handle of '{was}' and stays "
                "reserved")
    return None


def roster_rename(entries, integrators, formers, old, new):
    """Apply a rename to the roster. Pure: returns (entries, integrators,
    formers). The login stays with the handle; `old` joins the former
    handles, every former handle of `old` now points at `new`, and `new`
    leaves them (renaming back to a former handle)."""
    entries = [(new if h == old else h, l) for h, l in entries]
    integrators = [new if n == old else n for n in integrators]
    formers = {o: (new if c == old else c) for o, c in formers.items()
               if o.lower() != new.lower()}
    formers[old] = new
    return entries, integrators, formers


LOGIN_ENV = "DEVOPS_GITHUB_LOGIN"
_LOGIN_MEMO = {}


def gh_login(root):
    """This machine's GitHub login, as (login, None), or (None, why).

    Read order: the DEVOPS_GITHUB_LOGIN env var (a login, not a handle, so a
    rename never strands it; it overrides gh); with GH_TOKEN/GITHUB_TOKEN
    set, `gh api user`, since gh then acts as the token's account and the
    stored config may name another; else gh's stored config (no network),
    falling back to `gh api user` when that is empty. Memoized per process.
    Identity hangs on the login, so callers refuse rather than fall back to
    a bare handle."""
    if "v" not in _LOGIN_MEMO:
        _LOGIN_MEMO["v"] = _read_login(root)
    return _LOGIN_MEMO["v"]


def _read_login(root):
    env = (os.environ.get(LOGIN_ENV) or "").strip()
    if env:
        return env, None
    if not shutil.which("gh"):
        return None, ("gh (GitHub CLI) is not installed; install it and run "
                      "gh auth login, or set " + LOGIN_ENV + " — a board "
                      "handle is tied to your GitHub login")
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        r = sh(["gh", "config", "get", "user", "-h", "github.com"], cwd=root,
               check=False, timeout=GIT_NETWORK_TIMEOUT_S)
        login = r.stdout.strip() if r.returncode == 0 else ""
        if login:
            return login, None
    r = sh(["gh", "api", "user", "--jq", ".login"], cwd=root, check=False,
           timeout=GIT_NETWORK_TIMEOUT_S)
    login = r.stdout.strip() if r.returncode == 0 else ""
    if login:
        return login, None
    if r.returncode == 4:  # gh's exit code for "authentication required"
        return None, ("gh is not signed in; run gh auth login (or set "
                      f"{LOGIN_ENV}), then re-run")
    detail = (r.stderr or r.stdout or "").strip().splitlines()
    return None, ("gh could not read your GitHub login"
                  + (f" ({detail[0]})" if detail else "")
                  + "; check the network and gh sign-in, then re-run")


def current_identity(root, scope):
    """This session's handle, as (handle, None), or (None, why).

    The GitHub login (gh_login) looked up on the roster as last synced — no
    fetch unless this checkout has never synced the board — so a rename or
    a gh account switch takes effect at once with nothing stored locally.
    A login not on the roster gets one legacy chance (legacy_identity)."""
    login, err = gh_login(root)
    if err:
        return None, err
    yml = board_yml_path(os.path.join(root, board_worktree_rel(scope)), scope)
    if not os.path.exists(yml):
        with contextlib.redirect_stdout(sys.stderr):
            resolve_board(root, scope)
    if not os.path.exists(yml):
        return None, f"no board.yml for '{scope}' yet; run init"
    with open(yml) as f:
        entries = board_contributors(parse_kv(f.read()))
    _, handle, err = roster_join(entries, None, login)
    if handle:
        return handle, None
    return legacy_identity(root, scope, login) or (None, err)


def legacy_identity(root, scope, login):
    """Migrate a checkout from before identity came from the login: when its
    leftover .dev/identity names a roster handle with no login yet (or a
    former handle of one), record `login` there and act as that handle.
    Returns (handle, None) or None. Never registers anyone; after the
    backfill the login is on the roster and the file is never read again.
    Output goes to stderr (whoami's stdout is the handle)."""
    old = read_local(root, scope, "identity")
    if not old:
        return None
    with contextlib.redirect_stdout(sys.stderr):
        branch, bw = resolve_board(root, scope)
        if missing_board_error(bw, scope, branch):
            return None
        cfg = read_board_cfg(bw, scope)
        entries = board_contributors(cfg)
        handle = (old if old in [h for h, _ in entries]
                  else former_holder(board_former_handles(cfg), old))
        filled = login_backfill(entries, handle, login)
        if filled == entries:
            return None
        cfg["contributors"] = format_contributors(filled)
        write_board_cfg(bw, scope, cfg)
        board_commit(root, branch, bw, scope,
                     f"dev: record GitHub login for {handle}")
    print(f"note: recorded GitHub login '{login}' for '{handle}'; identity "
          "now comes from the login, and .dev/identity is no longer read",
          file=sys.stderr)
    return handle, None


def write_board_cfg(bw, scope, cfg):
    ensure_schema_version(cfg)
    lines = [f"{k}: {cfg.get(k, '')}" for k in CONFIG_KEYS]
    known = set(CONFIG_KEYS)
    # Preserve unknown keys so an older script rewriting a newer board does
    # not strip future fields (best-effort forward compat on write).
    for k, v in cfg.items():
        if k not in known:
            lines.append(f"{k}: {v}")
    with open(board_yml_path(bw, scope), "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def areas_path(bw, scope):
    return os.path.join(bw, tdir(scope), "areas.md")


def read_areas(bw, scope):
    mods = {}
    p = areas_path(bw, scope)
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                m = re.match(r"^- ([^:]+):\s*(.*)$", line)
                if m:
                    mods[m.group(1).strip()] = m.group(2).strip()
    return mods


def write_areas(bw, scope, mods):
    with open(areas_path(bw, scope), "w", newline="\n") as f:
        f.write("# Areas\n\n")
        for name, desc in mods.items():
            f.write(f"- {name}: {desc}\n")


# ---------- flow store (.flows/) ----------
# <scope>/.flows/<name>.md :
#   ---
#   id: 7                  (numeric, assigned at create, never changes)
#   name: send-invoice     (the file name; the only thing users type)
#   description: one line, written like a skill description
#   inputs: client, amount (defaults to today)
#   uses: prep-agenda, other-flow      (flows this one follows)
#   status: active | retired
#   formerly: old-name, older-name     (past names; a matching hint only)
#   created: 2026-09-18
#   ---
#   the procedure
#
# Renames free the old name at once — nothing is reserved. History matches
# on the id (tasks record `flow: 7 send-invoice`), so no file is rewritten.
# No verb accepts a bare number as a flow: a number is always a task id.

FLOW_FIELDS = ["id", "name", "description", "inputs", "uses", "status",
               "formerly", "created"]
FLOW_STATUSES = ("active", "retired")
FLOW_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def flow_path(bw, scope, name):
    return os.path.join(bw, fdir(scope), f"{name}.md")


def validate_flow_name(name):
    if not FLOW_NAME_RE.match(name or ""):
        sys.exit(f"error: flow name '{name}' must be a slug: lowercase "
                 "letters, digits, hyphens (send-invoice)")
    if name.isdigit():
        sys.exit("error: flows are referred to by name; a number is a task id")
    return name


def split_names(s):
    """Comma-separated names → list (order kept, blanks dropped)."""
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def parse_flow(path):
    with open(path) as f:
        text = f.read()
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        sys.exit(f"error: malformed flow file {path}")
    meta = parse_kv(m.group(1))
    try:
        meta["id"] = int(meta.get("id", ""))
    except ValueError:
        sys.exit(f"error: flow file {path} has no numeric id")
    for k in FLOW_FIELDS:
        meta.setdefault(k, "")
    meta["body"] = m.group(2).strip()
    meta["path"] = path
    return meta


def render_flow(meta):
    lines = ["---"]
    for k in FLOW_FIELDS:
        lines.append(f"{k}: {meta.get(k, '')}")
    lines.append("---")
    body = (meta.get("body") or "").strip()
    return "\n".join(lines) + ("\n\n" + body + "\n" if body else "\n")


def all_flows(bw, scope):
    d = os.path.join(bw, fdir(scope))
    if not os.path.isdir(d):
        return []
    flows = [parse_flow(p) for p in sorted(glob.glob(os.path.join(d, "*.md")))]
    return sorted(flows, key=lambda f: f["id"])


def duplicate_flow_ids(flows):
    """{id: [flows]} for every id held by more than one flow.

    Ids are minted as max+1 against whatever the board worktree has just
    synced, so two boards that mint one before either pushes both land it:
    the file names differ, so the board rebase merges them with no conflict.
    Run history matches on the id, so the collision has to be visible and
    repairable (`flow reid`) rather than silently conflating two flows.
    """
    by_id = {}
    for f in flows:
        by_id.setdefault(f["id"], []).append(f)
    return {i: fs for i, fs in by_id.items() if len(fs) > 1}


def warn_duplicate_flow_ids(flows):
    for fid, fs in sorted(duplicate_flow_ids(flows).items()):
        names = ", ".join(f["name"] for f in fs)
        print(f"warning: flow id {fid} is held by {len(fs)} flows ({names}); "
              f"run history matches on the id, so repair it: flow reid <name>",
              file=sys.stderr)


def flow_ref_tokens(flow):
    """The `<id> <name>` refs that record this flow: its fixed id paired with
    every name it has held. The one id+name rule behind run history, reid's
    holders and list --flow — the name is what tells apart two flows sharing
    an id."""
    names = {flow["name"]} | set(split_names(flow.get("formerly")))
    return {f"{flow['id']} {n}" for n in names}


def flow_ref_holders(bw, scope, flow):
    """Task files recording a run of this flow: its id paired with a name the
    flow has held. Live tasks and archived ones — an archive is verbatim and
    can never be rewritten, so a reid must not orphan one. Name-aware on
    purpose: when two flows share an id, the name in the record is what says
    whose run it was.
    """
    want = flow_ref_tokens(flow)
    d = os.path.join(bw, tdir(scope))
    paths = sorted(glob.glob(os.path.join(d, "[0-9]*.md")))
    paths += sorted(glob.glob(os.path.join(d, "archive", "*", "[0-9]*.md")))
    hits = []
    for path in paths:
        try:
            with open(path) as fh:
                text = fh.read()
        except OSError:
            continue
        m = re.search(r"^flow:[ \t]*(.*)$", text, re.M)
        if m and any(t in want for t in split_names(m.group(1))):
            hits.append(os.path.relpath(path, d))
    return hits


# One run record, split: Ran (<date>): [<refs>] <text>. The refs tag is
# what format_ran writes; a landed recurring run leaves the bare
# `Ran (<date>).` line instead, which parses with no tag and no text. A
# rehearsal's `Rehearsed (<date>): [<refs>] <text>` splits the same way.
RAN_PARTS_RE = re.compile(
    r"^(Ran|Rehearsed) \((\d{4}-\d{2}-\d{2})\)[:.][ \t]*"
    r"(?:\[([^\]]*)\])?[ \t]*(.*)$", re.S)


# Left on a task reseed_later_tasks carried onto the next board.
CARRIED_FROM_RE = re.compile(r"^carried from (\d+)/T(\d+)$", re.M)


def flow_run_entries(bw, scope, flow):
    """Every recorded run of this flow, newest first.

    A run is a `Ran (<date>)` record, not a task: a recurring task holds one
    per run. A `Rehearsed (<date>)` record is listed too, flagged
    `rehearsal`, so a dry run is visible but never passes for a real one.
    Records are matched on their refs tag, which pairs the flow's
    fixed id with a name it held — the same id+name rule (flow_ref_tokens)
    as reid's holders, so a rename never loses history and two flows
    sharing an id are still told apart. A tagless record (a landed recurring run) counts when
    the task's own `flow` field points here. A task that points here with no
    record of its own is labelled by status: in flight (listed first, no
    date) only while doing/draft/review on the live board; a done task — a
    landed dev run — is a normal run dated by its latest `Shipped` record
    (undated, still listed, when it has none); any other status is left out,
    since no run happened there (a resting recurring task's runs are its own
    records). An archived doing/draft/review copy is left out too: a --carry
    close puts the live run on the next board, so listing it would show one
    run twice.

    A carried task (--carry, or a shelved one, reseeded by
    iteration-new) is copied body and all, so its predecessor's records live
    in two files at once. The `carried from <n>/T<id>` marker reseed leaves
    is what tells them apart: a record the ancestor already holds is the
    ancestor's run, counted where it happened and skipped here. Without
    that, every iteration close would duplicate a recurring task's whole
    history. A recurring task reseeded without --carry and not shelved is
    trimmed instead (trim_run_records), so it holds no inherited records.
    """
    want = flow_ref_tokens(flow)
    d = os.path.join(bw, tdir(scope))
    paths = [(p, None) for p in sorted(glob.glob(os.path.join(d, "[0-9]*.md")))]
    for p in sorted(glob.glob(os.path.join(d, "archive", "*", "[0-9]*.md"))):
        paths.append((p, archive_dir_index(os.path.basename(os.path.dirname(p)))))
    loaded = []
    by_key = {}
    for path, arch in paths:
        try:
            meta = parse_task(path)
        except SystemExit:
            continue
        recs = [" ".join(r.split()) for r in
                collect_ran(meta["body"]) + collect_rehearsed(meta["body"])]
        loaded.append((arch, meta, recs))
        by_key.setdefault((arch, meta["id"]), set()).update(recs)
    entries = []
    for arch, meta, recs in loaded:
        inherited = set()
        for anc in CARRIED_FROM_RE.finditer(meta["body"]):
            inherited |= by_key.get((int(anc.group(1)), int(anc.group(2))),
                                    set())
        on_task = bool(set(split_names(meta.get("flow", ""))) & want)
        label = f"{arch}/T{meta['id']}" if arch else f"T{meta['id']}"
        found = 0
        for rec in recs:
            if rec in inherited:
                continue
            m = RAN_PARTS_RE.match(rec)
            if not m:
                continue
            verb, date, tag = m.group(1), m.group(2), m.group(3)
            text = m.group(4).strip()
            if tag is None:
                if not on_task:
                    continue
            elif not (set(split_names(tag)) & want):
                continue
            found += 1
            entries.append({"date": date, "label": label, "id": meta["id"],
                            "title": meta.get("title", ""),
                            "status": meta["status"], "text": text,
                            "archived": arch is not None,
                            "rehearsal": verb == "Rehearsed"})
        live_run = arch is None and meta["status"] in IN_FLIGHT
        if on_task and not found and (live_run or meta["status"] == "done"):
            date = text = ""
            shipped = collect_shipped(meta["body"])
            if meta["status"] == "done" and shipped:
                m = SHIPPED_PARTS_RE.match(" ".join(shipped[-1].split()))
                date, text = m.group(1), m.group(2).strip()
            entries.append({"date": date, "label": label, "id": meta["id"],
                            "title": meta.get("title", ""),
                            "status": meta["status"], "text": text,
                            "archived": arch is not None,
                            "rehearsal": False})
    # In flight first, then newest first; an undated done run sinks last.
    entries.sort(key=lambda e: (e["date"] or ("9999-99-99" if e["status"]
                                              in IN_FLIGHT else ""), e["id"]),
                 reverse=True)
    return entries


def format_flow_run(e, color=False):
    """One run line: when, which task, and what the record said."""
    in_flight = not e["date"] and e["status"] in IN_FLIGHT
    when = e["date"] or ("in flight" if in_flight else "no date")
    head = f"  {when:<10}  {e['label']} {e['title']}"
    if color:
        shown = _ansi(_STATUS_COLOR["doing"] if in_flight else _DIM,
                      f"{when:<10}")
        head = (f"  {shown}  {_status_ansi(e['status'], e['label'])} "
                f"{e['title']}")
    bits = ["rehearsal"] if e.get("rehearsal") else []
    if not e["date"]:
        bits.append(e["status"])
    if e["archived"]:
        bits.append("archived")
    if bits:
        head += f" [{', '.join(bits)}]"
    if e["text"]:
        head += f"\n{' ' * 14}{e['text']}"
    return head


def flow_runs_text(bw, scope, flow, color=False):
    """`flow runs <name>` body: the header line plus every run."""
    entries = flow_run_entries(bw, scope, flow)
    name = _ansi(_FLOW_NAME, flow["name"]) if color else flow["name"]
    head = f"{name} (id {flow['id']})"
    if not flow_is_active(flow):
        head += " [retired]"
    k = sum(1 for e in entries if e["rehearsal"])
    n = len(entries) - k
    head += f" — {n} run{'' if n == 1 else 's'}"
    if k:
        head += f", {k} rehearsal{'' if k == 1 else 's'}"
    lines = [head]
    if not entries:
        lines.append("  (no runs recorded)")
    lines.extend(format_flow_run(e, color=color) for e in entries)
    return "\n".join(lines)


def flow_is_active(f):
    return (f.get("status") or "active") != "retired"


def find_flow(bw, scope, text, flows=None, quiet=False):
    """Resolve a loosely typed name to one flow, or exit.

    Exact active name, then exact retired name, then a `formerly` entry
    (active first), then a fuzzy match over those same names when one
    candidate stands clear of the rest. Never a bare number.
    """
    text = (text or "").strip()
    if not text:
        sys.exit("error: flow name required")
    if text.isdigit():
        sys.exit(f"error: flows are referred to by name; {text} would be "
                 f"task T{text}. See: flow list")
    flows = all_flows(bw, scope) if flows is None else flows
    if not flows:
        sys.exit(f"error: no flows yet ({fdir(scope)}/ is empty); "
                 "create one: flow create <name> --desc \"…\"")
    ranked = sorted(flows, key=lambda f: (not flow_is_active(f), f["id"]))
    for f in ranked:
        if f["name"] == text:
            return f
    for f in ranked:
        if text in split_names(f.get("formerly")):
            if not quiet:
                print(f"matched: {text} → {f['name']} (formerly)",
                      file=sys.stderr)
            return f
    names = {}
    for f in ranked:
        for n in [f["name"]] + split_names(f.get("formerly")):
            names.setdefault(n, f)
    scored = sorted(((difflib.SequenceMatcher(None, text, n).ratio(), n)
                     for n in names), reverse=True)
    top = [(r, n) for r, n in scored if r >= 0.6]
    if top and (len(top) == 1 or top[0][0] - top[1][0] >= 0.15
                or names[top[0][1]] is names[top[1][1]]):
        f = names[top[0][1]]
        if not quiet:
            print(f"matched: {text} → {f['name']}", file=sys.stderr)
        return f
    if top:
        cands = ", ".join(names[n]["name"] for _, n in top[:4])
        sys.exit(f"error: '{text}' is ambiguous between flows: {cands}")
    sys.exit(f"error: no flow matches '{text}'. See: flow list")


def flow_body_from_args(args):
    """--body text, or --file (a path or '-' for stdin); None if neither."""
    body = getattr(args, "body", None)
    path = getattr(args, "file", None)
    if path and body is not None:
        sys.exit("error: pass --body or --file, not both")
    if path:
        if path == "-":
            return sys.stdin.read().strip()
        with open(path) as f:
            return f.read().strip()
    if body is not None:
        return body.strip()
    return None


def check_uses(uses, flows, self_name=None):
    names = {f["name"] for f in flows if flow_is_active(f)}
    for u in uses:
        if u == self_name:
            sys.exit(f"error: a flow cannot use itself ({u})")
        if u not in names:
            print(f"warning: uses '{u}' is not an active flow", file=sys.stderr)


def flow_line(f, show_status=False):
    tag = ""
    if show_status and not flow_is_active(f):
        tag = " [retired]"
    return f"{f['name']}{tag} — {f.get('description') or '(no description)'}"


def write_flow(meta):
    with open(meta["path"], "w", newline="\n") as f:
        f.write(render_flow(meta))


FLOW_REF_RE = re.compile(r"^(\d+) (\S+)$")


def resolve_flow_refs(bw, scope, text, flows=None):
    """Comma-separated flow names (or `<id> <name>` refs) → the canonical
    `<id> <name>` list a task records. Names resolve through find_flow;
    an explicit ref only needs its id to exist (the name is history)."""
    flows = all_flows(bw, scope) if flows is None else flows
    by_id = {f["id"]: f for f in flows}
    dups = duplicate_flow_ids(flows)
    refs = []
    for tok in split_names(text):
        m = FLOW_REF_RE.match(tok)
        if m:
            fid = int(m.group(1))
            if fid not in by_id:
                sys.exit(f"error: no flow with id {fid} ('{tok}')")
            ref = f"{fid} {m.group(2)}"
        else:
            f = find_flow(bw, scope, tok, flows)
            ref = f"{f['id']} {f['name']}"
        fid = int(ref.split(" ", 1)[0])
        if fid in dups:
            # Recording it now would make this run indistinguishable from the
            # other flow's, and an archived record can never be rewritten.
            names = ", ".join(f["name"] for f in dups[fid])
            sys.exit(f"error: flow id {fid} is held by {len(dups[fid])} flows "
                     f"({names}); a run recorded against it could not be told "
                     f"from the other's. Repair first: flow reid <name>")
        if ref not in refs:
            refs.append(ref)
    return refs


def task_follows_flow(t, flow):
    """True when the task's `flow` field records this flow (flow_ref_tokens),
    so a rename keeps matching and a flow sharing the id does not."""
    return bool(set(split_names(t.get("flow") or "")) & flow_ref_tokens(flow))


def parse_flow_refs(text):
    """A task's `flow` field → [(id, name)], skipping malformed tokens."""
    out = []
    for tok in split_names(text):
        m = FLOW_REF_RE.match(tok)
        if m:
            out.append((int(m.group(1)), m.group(2)))
    return out


def cmd_flow(args):
    root, scope, branch, bw = ctx()
    flows = all_flows(bw, scope)
    warn_duplicate_flow_ids(flows)
    act = args.action
    if act == "list":
        sel = flows if args.all else [f for f in flows if flow_is_active(f)]
        if args.json:
            print(json.dumps([{k: f.get(k, "") for k in FLOW_FIELDS}
                              for f in sel], indent=1))
            return
        if not sel:
            print("(no flows)" if args.all else "(no active flows)")
            return
        for f in sel:
            print(flow_line(f, show_status=args.all))
        return
    if act == "show":
        f = find_flow(bw, scope, args.name, flows)
        show_file(f["path"], bw, scope, args.raw,
                  skip=flow_input_names(f.get("inputs")))
        return
    if act == "runs":
        f = find_flow(bw, scope, args.name, flows)
        if args.json:
            print(json.dumps(flow_run_entries(bw, scope, f), indent=1))
            return
        print(flow_runs_text(bw, scope, f, color=_use_color()))
        return
    if act == "create":
        name = validate_flow_name((args.name or "").strip())
        taken = next((f for f in flows if f["name"] == name), None)
        if taken:
            if flow_is_active(taken):
                sys.exit(f"error: flow '{name}' already exists (id {taken['id']})")
            sys.exit(f"error: retired flow '{name}' still holds that name; "
                     f"rename it first: flow rename {name} <new-name>")
        desc = " ".join((args.desc or "").split())
        if not desc:
            sys.exit("error: flow create needs --desc \"<one line: what it "
                     "does and when to use it>\"")
        uses = split_names(args.uses)
        check_uses(uses, flows, name)
        os.makedirs(os.path.join(bw, fdir(scope)), exist_ok=True)
        meta = {
            "id": max((f["id"] for f in flows), default=0) + 1,
            "name": name, "description": desc,
            "inputs": ", ".join(split_names(args.inputs)),
            "uses": ", ".join(uses), "status": "active", "formerly": "",
            "created": datetime.date.today().isoformat(),
            "body": flow_body_from_args(args) or "",
            "path": flow_path(bw, scope, name),
        }
        write_flow(meta)
        board_commit(root, branch, bw, scope, f"dev: flow create {name}")
        print(render_flow(meta).rstrip())
        warn_sequence_names(bw, scope, meta["body"])
        warn_placeholders(meta["inputs"], meta["body"])
        warn_catalog_refs(bw, scope, meta["inputs"], meta["body"])
        return
    f = find_flow(bw, scope, args.name, flows)
    name = f["name"]
    if act == "update":
        changes = []
        if args.desc is not None:
            f["description"] = " ".join(args.desc.split())
            changes.append("description")
        if args.inputs is not None:
            f["inputs"] = ", ".join(split_names(args.inputs))
            changes.append("inputs")
        if args.uses is not None:
            uses = split_names(args.uses)
            check_uses(uses, flows, name)
            f["uses"] = ", ".join(uses)
            changes.append("uses")
        if args.status is not None:
            if args.status not in FLOW_STATUSES:
                sys.exit(f"error: status must be one of {list(FLOW_STATUSES)}")
            f["status"] = args.status
            changes.append(f"status={args.status}")
        body = flow_body_from_args(args)
        if body is not None:
            f["body"] = body
            changes.append("body")
        if args.append is not None:
            for text in args.append:
                f["body"] = append_body(f["body"], text)
            changes.append("append")
        if not changes:
            sys.exit("error: nothing to update")
        write_flow(f)
        board_commit(root, branch, bw, scope,
                     f"dev: flow update {name} ({', '.join(changes)})")
        print(f"flow {name} updated: {', '.join(changes)}")
        warn_sequence_names(bw, scope, f["body"])
        warn_placeholders(f["inputs"], f["body"])
        warn_catalog_refs(bw, scope, f["inputs"], f["body"])
        return
    if act == "rename":
        new = validate_flow_name((args.new_name or "").strip())
        if new == name:
            sys.exit(f"error: flow is already named '{name}'")
        if any(x["name"] == new for x in flows):
            sys.exit(f"error: flow '{new}' already exists")
        old_path = f["path"]
        formerly = [n for n in split_names(f.get("formerly")) if n != new]
        if name not in formerly:
            formerly.append(name)
        f["formerly"] = ", ".join(formerly)
        f["name"] = new
        f["path"] = flow_path(bw, scope, new)
        # Other flows that use the old name follow the rename — `uses` is a
        # live pointer, unlike a task's recorded run.
        followers = []
        for x in flows:
            if x is f:
                continue
            u = split_names(x.get("uses"))
            if name in u:
                x["uses"] = ", ".join(new if n == name else n for n in u)
                write_flow(x)
                followers.append(x["name"])
        os.replace(old_path, f["path"])
        write_flow(f)
        board_commit(root, branch, bw, scope, f"dev: flow rename {name} → {new}")
        print(f"flow {name} → {new} (id {f['id']}; '{name}' is free again)")
        if followers:
            print(f"  uses updated in: {', '.join(followers)}")
        return
    if act == "reid":
        dups = duplicate_flow_ids(flows)
        if f["id"] not in dups:
            sys.exit(f"error: flow '{name}' holds id {f['id']} alone; reid "
                     f"only repairs an id two flows minted independently")
        held = flow_ref_holders(bw, scope, f)
        if held:
            others = ", ".join(x["name"] for x in dups[f["id"]] if x is not f)
            sys.exit(f"error: {len(held)} task(s) already record this flow's "
                     f"runs ({', '.join(held)}); a new id would orphan them. "
                     f"Reid the other flow instead: flow reid {others}")
        old_id = f["id"]
        f["id"] = max(x["id"] for x in flows) + 1
        write_flow(f)
        board_commit(root, branch, bw, scope,
                     f"dev: flow reid {name} ({old_id} → {f['id']})")
        print(f"flow {name}: id {old_id} → {f['id']} (no runs recorded, so "
              f"nothing points at the old id)")
        return
    if act == "retire":
        if not flow_is_active(f):
            sys.exit(f"error: flow '{name}' is already retired")
        users = [x["name"] for x in flows
                 if flow_is_active(x) and name in split_names(x.get("uses"))]
        if users:
            print(f"warning: active flows still use '{name}': "
                  f"{', '.join(users)}", file=sys.stderr)
        f["status"] = "retired"
        write_flow(f)
        board_commit(root, branch, bw, scope, f"dev: flow retire {name}")
        print(f"flow {name} retired (id {f['id']} keeps resolving its runs; "
              f"revive with flow update {name} --status active)")
        return


# ---------- agent, environment and routine registries ----------
# <scope>/.catalog/agents/<name>.md and <scope>/.catalog/environments/<name>.md,
# one entry per file: the catalog's built-in categories, each schema defined
# here in REGISTRIES. Like flows they outlive iterations; board_commit stages
# .catalog/ and the ship guard refuses it with .tasks/ and .flows/. Before
# schema 13 they lived in .flows/<dir>/ (migrate_registries moves them).
#   ---
#   name: grok-bot
#   accessors: Q, bob     (board contributors who can reach it now; never
#                          empty, so every name leads to a human)
#   description: one line, who it is            (agent only)
#   machine: studio-mac                         (environment only, optional)
#   formerly: old-name     (past names; still reserved, still resolve)
#   created: 2026-10-27
#   ---
#   prose expectations                          (environment only)
#
# <scope>/.catalog/routines/<name>.md is the third registry: a routine mirrors
# a scheduled trigger that lives at its source (a harness's scheduler, cron,
# a cloud routine), so the board knows which recurring tasks start on their
# own. Beside name, accessors (who can reach the source), formerly and
# created it carries mode (attended | unattended), environment (a registered
# environment), schedule (what the trigger is set to: cron + IANA zone, or
# one fire time), trigger (free text: what and where, with its identifier)
# and status (active | paused — the board-side off switch); its body says
# how to change or remove the trigger at its source. Tasks point at one
# through their `routine` field.
#
# Accessors are a routing aid, not history: who ran an agent for a given run
# lives in that run's record. There is no id: run records name an entry by
# the name it had then, so unlike a flow's, a former name stays reserved
# (add/rename refuse it, in every category: the catalog is one namespace)
# and keeps resolving for as long as the entry exists. Lookups stay within
# a category. rm frees all of its names.

REGISTRIES = {
    "agent": {"dir": "agents", "label": "agent",
              "fields": ["name", "accessors", "description", "formerly",
                         "created"]},
    "env": {"dir": "environments", "label": "environment",
            "fields": ["name", "accessors", "machine", "formerly",
                       "created"]},
    "routine": {"dir": "routines", "label": "routine",
                "fields": ["name", "accessors", "mode", "environment",
                           "schedule", "trigger", "status", "formerly",
                           "created"]},
}
# Words a flow uses for "whoever is running it" / "this repo" / "no
# preference" / "described right here in the sequence", so no entry may
# take them.
REGISTRY_RESERVED = ("project", "runner", "any", "inline")


def registry_dir(bw, scope, kind):
    return os.path.join(bw, cdir(scope), REGISTRIES[kind]["dir"])


def legacy_registry_dir(bw, scope, kind):
    """Where a registry lived before schema 13 (and where an older script
    still writes it)."""
    return os.path.join(bw, fdir(scope), REGISTRIES[kind]["dir"])


def all_registries(bw, scope):
    """Every entry of every built-in category: the one namespace."""
    return [e for kind in REGISTRIES for e in all_registry(bw, scope, kind)]


def registry_clash_warnings(entries):
    """One line per name two categories both hold (current or former), with
    the rename that clears it where one holds it as its current name. Pure.
    A rename keeps the old name as a former one, so the name stays held by
    both — but lookups stay within a category, so only a current name held
    elsewhere is worth renaming."""
    held = {}
    for e in entries:
        for n in [e["name"]] + split_names(e.get("formerly")):
            held.setdefault(n, []).append(e)
    out = []
    for name, es in sorted(held.items()):
        if len({e["kind"] for e in es}) < 2:
            continue
        who = ", ".join(f"{REGISTRIES[e['kind']]['label']} '{e['name']}'"
                        + ("" if e["name"] == name else " (former name)")
                        for e in es)
        cur = [e for e in es if e["name"] == name]
        fix = (f"; rename one: {cur[-1]['kind']} rename {name} <new-name>"
               if cur else "; each category still resolves it as its own")
        out.append(f"warning: catalog name '{name}' is held by {who}{fix}")
    return out


def move_legacy_registries(bw, scope):
    """Move registry files an older layout left in .flows/<dir>/ into
    .catalog/<dir>/ on disk; returns how many moved. A file whose name is
    already taken in .catalog/ is left where it is, with a warning."""
    moves, kept = [], []
    for kind in REGISTRIES:
        old = legacy_registry_dir(bw, scope, kind)
        for p in sorted(glob.glob(os.path.join(old, "*.md"))):
            dest = os.path.join(registry_dir(bw, scope, kind),
                                os.path.basename(p))
            (kept if os.path.exists(dest) else moves).append((p, dest))
    for p, dest in kept:
        print(f"warning: {os.path.relpath(p, bw)} not moved: "
              f"{os.path.relpath(dest, bw)} already exists; merge them by "
              "hand on the board branch", file=sys.stderr)
    for p, dest in moves:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.replace(p, dest)
    for kind in REGISTRIES:
        try:
            os.rmdir(legacy_registry_dir(bw, scope, kind))
        except OSError:
            pass
    return len(moves)


def migrate_registries(root, scope, branch, bw):
    """Schema 13: whenever the legacy .flows/<dir>/ registries hold files
    (an older script may write there after the move), move them into
    .catalog/ in one board commit that stamps the schema, then warn about
    names two categories share. A board with nothing to move is stamped on
    its next ordinary write, so a read-only command never commits."""
    n = move_legacy_registries(bw, scope)
    if not n:
        return
    write_board_cfg(bw, scope, read_board_cfg(bw, scope))
    board_commit(root, branch, bw, scope,
                 f"dev: move {n} agent/environment/routine file(s) from "
                 ".flows/ into .catalog/")
    for w in registry_clash_warnings(all_registries(bw, scope)):
        print(w, file=sys.stderr)


def all_registry(bw, scope, kind):
    out = []
    for p in sorted(glob.glob(os.path.join(registry_dir(bw, scope, kind),
                                           "*.md"))):
        with open(p) as fh:
            m = re.match(r"^---\n(.*?)\n---\n?(.*)$", fh.read(), re.DOTALL)
        if not m:
            sys.exit(f"error: malformed {REGISTRIES[kind]['label']} file {p}")
        meta = parse_kv(m.group(1))
        for k in REGISTRIES[kind]["fields"]:
            meta.setdefault(k, "")
        meta.update(kind=kind, body=m.group(2).strip(), path=p)
        out.append(meta)
    return out


def write_registry(meta):
    lines = ["---"] + [f"{k}: {meta.get(k, '')}"
                       for k in REGISTRIES[meta["kind"]]["fields"]] + ["---"]
    body = (meta.get("body") or "").strip()
    with open(meta["path"], "w", newline="\n") as f:
        f.write("\n".join(lines) + ("\n\n" + body + "\n" if body else "\n"))


# The one name rule for every catalog name (built-in entries, user keys,
# categories and fields): lowercase letters, digits, '-' and '_', starting
# with a letter or digit, never a bare number (the lookahead wants one
# non-digit). Flow names keep their own rule (FLOW_NAME_RE).
CATALOG_NAME = r"(?=[a-z0-9_-]*[a-z_-])[a-z0-9][a-z0-9_-]*"
CATALOG_NAME_RE = re.compile(rf"^{CATALOG_NAME}$")
CATALOG_NAME_RULE = ("lowercase letters, digits, '-' and '_', not a bare "
                     "number")


def registry_name_error(name):
    """Why `name` cannot name a registry entry, or None. Pure."""
    if not CATALOG_NAME_RE.match(name or ""):
        return (f"name '{name}' must be {CATALOG_NAME_RULE} (grok-bot, "
                "studio_mac)")
    if name in REGISTRY_RESERVED:
        return (f"'{name}' is reserved ({', '.join(REGISTRY_RESERVED)} mean "
                "something to a flow already)")
    return None


def registry_holder(entries, name):
    """The entry holding `name` as its name or a former one, else None.
    Pure. A current name wins over another entry's former one (which add
    and rename never let arise, but a merged board might)."""
    return (next((e for e in entries if e["name"] == name), None)
            or next((e for e in entries
                     if name in split_names(e.get("formerly"))), None))


def catalog_name_taken(entries, name, kind):
    """Why `name` cannot be taken in category `kind` because another
    category holds it (current or former), or None. Pure: the catalog is
    one namespace."""
    other = registry_holder([x for x in entries if x["kind"] != kind], name)
    if other is None:
        return None
    return (f"'{name}' is held by {entry_label(other)} "
            f"'{other['name']}'"
            + ("" if other["name"] == name else " as a former name")
            + "; catalog names are shared across categories")


def registry_rename(e, new):
    """Rename entry `e` in place to `new`: the old name joins `formerly`,
    and `new` leaves it (renaming back to a former name). Pure."""
    formerly = [n for n in split_names(e.get("formerly")) if n != new]
    if e["name"] not in formerly:
        formerly.append(e["name"])
    e["formerly"] = ", ".join(formerly)
    e["name"] = new
    return e


def accessors_error(accessors, handles):
    """Why this accessor list cannot be written, or None. Pure."""
    if not accessors:
        return ("needs at least one accessor (--accessors \"<handle, …>\"): "
                "every name has to lead to a contributor who can reach it")
    unknown = [a for a in accessors if a not in handles]
    if unknown:
        return (f"accessors must be board contributors; not on the roster: "
                f"{', '.join(unknown)} ({', '.join(handles) or 'none'})")
    return None


def last_accessor_of(entries, name):
    """Entries `name` is the only accessor of, as 'agent x' labels. Pure."""
    return [f"{REGISTRIES[e['kind']]['label']} {e['name']}" for e in entries
            if split_names(e.get("accessors")) == [name]]


def registry_line(e):
    kind = e["kind"]
    if kind == "agent":
        what = e.get("description") or "(no description)"
    elif kind == "routine":
        _, why = read_routine_schedule(e)
        sched = (f"schedule unreadable ({why})" if why
                 else f"schedule {e['schedule']}")
        what = (f"{e.get('mode')}, {e.get('status')}, environment "
                f"{e.get('environment')}, {sched}")
    else:
        what = (f"machine: {e['machine']}" if e.get("machine")
                else "(no machine)")
    was = f"; formerly {e['formerly']}" if e.get("formerly") else ""
    return (f"{e['name']} — {what} "
            f"(accessors: {e.get('accessors') or 'none'}{was})")


ROUTINE_MODES = ("attended", "unattended")
ROUTINE_STATUSES = ("active", "paused")
ROUTINE_SCHEDULE_HELP = ("a routine's schedule is a 5-field cron expression "
                         "and an IANA timezone (\"0 12 * * 3 "
                         "America/New_York\"), or one fire time as a "
                         "timestamp with offset (2026-11-12T09:00-05:00)")
# How long past the time a routine should have fired for a due task before
# the board says it did not start.
ROUTINE_GRACE = datetime.timedelta(hours=1)


def parse_routine_schedule(value):
    """A routine's schedule: a cron expression + zone (parsed as a task's
    schedule) or one fire time (an aware datetime). Exits on a bad value."""
    raw = " ".join((value or "").split())
    if raw and " " not in raw:
        try:
            when = datetime.datetime.fromisoformat(raw)
        except ValueError:
            when = None
        if when is None or when.tzinfo is None:
            sys.exit(f"error: bad routine schedule '{value}'; "
                     f"{ROUTINE_SCHEDULE_HELP}")
        return when
    sched = parse_schedule(raw, "routine schedule")
    if cron_next(sched, datetime.datetime.now().astimezone()) is None:
        sys.exit(f"error: routine schedule '{raw}' never fires")
    return sched


def tzdata_install():
    """The command that gives this Python a timezone database: Windows has no
    system zone data, so zoneinfo reads it from the tzdata package."""
    return f"{'py' if WINDOWS else 'python3'} -m pip install tzdata"


def read_routine_schedule(r):
    """(parsed schedule, None), or (None, why it cannot be read). Never
    exits: every board read derives stalls from it, and a zone this
    machine's tz database lacks must not stop the board, only that check."""
    raw = " ".join((r.get("schedule") or "").split())
    if not raw:
        return None, "none set"
    try:
        return parse_routine_schedule(raw), None
    except (SystemExit, ValueError, OSError):
        toks = raw.split()
        if len(toks) == 6:
            try:
                zoneinfo.ZoneInfo(toks[5])
            except (ValueError, OSError, zoneinfo.ZoneInfoNotFoundError):
                if not zoneinfo.available_timezones():
                    return None, ("no timezone database (install one with: "
                                  f"{tzdata_install()})")
                return None, f"unknown zone {toks[5]}"
        return None, f"bad value '{raw}'"


def routine_expected_fire(sched, since):
    """When a routine with this parsed schedule should fire for a task due
    at `since`: its first cron time at or after it. A one-time trigger set
    earlier than `since` fired for an earlier run and was never re-pointed,
    so the task counts as expected at `since` itself. Pure."""
    if isinstance(sched, datetime.datetime):
        return max(sched, since)
    return cron_next(sched, since - datetime.timedelta(microseconds=1))


def routine_of(t, routines):
    """The routine entry task `t` points at, by its name or a former one."""
    name = (t.get("routine") or "").strip()
    return registry_holder(routines, name) if name else None


def routine_tasks(tasks, routines, r):
    """Tasks pointing at routine entry `r`, under any of its names."""
    return [t for t in tasks if routine_of(t, routines) is r]


def routine_stall(t, r, now):
    """Why a task its routine should already have started has not, or None:
    ('paused' | 'missing', None), or ('did not start', when it should have
    fired). Only a due task at rest with no open needs is checked — one in
    flight has started, one with needs waits on a human. A routine whose
    schedule cannot be read is skipped; routine list says why. Pure."""
    if (not recur_at_rest(t) or not on_the_clock(t) or t.get("needs")
            or not task_is_due(t, now)):
        return None
    if r is None:
        return ("missing", None)
    if r.get("status") == "paused":
        return ("paused", None)
    due = task_due_date(t)
    if due is None:
        created = (t.get("created") or "").strip()
        if not created:
            return None
        due = iso_date(created, "created")
    sched, _ = read_routine_schedule(r)
    if sched is None:
        return None
    expected = routine_expected_fire(sched, due_instant(due))
    if expected is not None and expected + ROUTINE_GRACE < due_instant(now):
        return ("did not start", expected)
    return None


def stall_words(stall):
    return "not on the board" if stall[0] == "missing" else stall[0]


def routine_not_started(t):
    """A covered task its routine should have started and will not: it did
    not start, or the routine is gone. Paused is a human's choice, so it
    keeps the plain due mark."""
    stall = t.get("routine_stall")
    return bool(stall) and stall[0] != "paused"


def routine_stall_text(t):
    """The board's note for a stalled covered task, or ''."""
    stall = t.get("routine_stall")
    if not stall:
        return ""
    mark = "🚨" if routine_not_started(t) else ""
    return f"{mark}routine {stall[2]} {stall_words(stall)}"


def note_routine_stalls(tasks, routines, now=None):
    """Derive each covered task's stall as routine_stall, (reason, expected,
    the routine's current name): kept in memory, never written, since
    render_task writes FIELDS only."""
    now = now or datetime.datetime.now().astimezone()
    for t in tasks:
        r = routine_of(t, routines)
        stall = routine_stall(t, r, now) if t.get("routine") else None
        if stall:
            t["routine_stall"] = stall + (r["name"] if r else t["routine"],)


def routine_pointer_check(meta, tasks, routines, flows):
    """(entry, error, notes) for pointing task `meta` at its routine field.
    An attended routine holds exactly one task, and a routine's tasks share
    one type (/dev wake and /ops wake each run only their own). Notes: an
    unattended routine's tasks share one session's context, and a flow with
    [user] steps has nobody to do them there. Pure."""
    name = (meta.get("routine") or "").strip()
    if not is_recurring(meta):
        return None, (f"routine only applies to kind {RECURRING} tasks; "
                      f"T{meta['id']} is not one"), []
    r = registry_holder(routines, name)
    if r is None:
        have = ", ".join(x["name"] for x in routines) or "none"
        return None, f"no routine '{name}' ({have}). See: routine list", []
    others = [t for t in routine_tasks(tasks, routines, r)
              if t["id"] != meta["id"]]
    ids = ", ".join(f"T{t['id']}" for t in others)
    if r.get("mode") == "attended" and others:
        return r, (f"routine {r['name']} is attended and already runs {ids}; "
                   "an attended routine holds exactly one task"), []
    clash = [t for t in others if task_type(t) != task_type(meta)]
    if clash:
        return r, (f"routine {r['name']} runs {task_type(clash[0])} tasks "
                   f"({ids}) and T{meta['id']} is {task_type(meta)}; a "
                   "routine's tasks share one type"), []
    notes = []
    if r.get("mode") == "unattended":
        if others:
            notes.append(f"note: routine {r['name']} also runs {ids}; its "
                         "tasks run in one session and share its context")
        by_id = {f["id"]: f for f in flows}
        for fid, _ in parse_flow_refs(meta.get("flow")):
            f = by_id.get(fid)
            if f and "[user]" in (f.get("body") or ""):
                notes.append(f"warning: flow {f['name']} has [user] steps "
                             f"and routine {r['name']} is unattended: "
                             "nobody is there to do them")
    return r, None, notes


def routine_trigger_reminder(meta):
    r = meta["routine"]
    return (f"reminder: T{meta['id']} is started by routine {r}; if its "
            f"trigger no longer fits, change it at the source (routine show "
            f"{r} says how), then routine update {r} --schedule")


def cmd_routine_wake(bw, scope, entries, name):
    """The routine's entry gate: exit 2 with the reason when the record is
    paused, gone, or of the other skill's tasks; else its due tasks at rest
    in due order, then those waiting on a decision and those in flight on
    skipped lines (a re-fire must not hand out a parked question again, nor
    a run that is still going)."""
    e = registry_holder(entries, name)
    if e is None:
        print(f"wake: no routine '{name}' on this board, so this trigger has "
              "nothing to run; remove it at its source", file=sys.stderr)
        sys.exit(2)
    if e["status"] == "paused":
        print(f"wake: routine '{e['name']}' is paused on the board; nothing "
              f"runs until routine update {e['name']} --status active",
              file=sys.stderr)
        sys.exit(2)
    tasks = all_tasks(bw, scope)
    mine = routine_tasks(tasks, entries, e)
    skill = invoking_skill()
    other = [t for t in mine if task_type(t) != skill]
    if other:
        print(f"wake: routine '{e['name']}' runs {task_type(other[0])} "
              f"tasks; wake it with /{task_type(other[0])} wake",
              file=sys.stderr)
        sys.exit(2)
    due, waiting, busy = wake_partition(mine)
    for t in due:
        print(fmt_line(t, tasks))
    if not due:
        print(f"(nothing due on routine {e['name']})")
    if waiting:
        print("skipped, waiting on a decision: " + ", ".join(
            f"T{t['id']}" for t in waiting))
    if busy:
        print("skipped, in flight: " + ", ".join(
            f"T{t['id']} ({t['status']})" for t in busy))


def wake_partition(mine, now=None):
    """A routine's tasks as the wake sees them: (due at rest, in due order,
    a scheduled task within its time's early window counted as due; due at
    rest but with an open needs, which a human must answer before a re-fire
    may hand it out again; in flight). Pure given `now`."""
    ready = sorted((t for t in mine if recur_at_rest(t)
                    and task_is_due(t, now, early=True)),
                   key=recur_due_sort)
    due = [t for t in ready if not t.get("needs")]
    waiting = [t for t in ready if t.get("needs")]
    busy = [t for t in mine if t["status"] in IN_FLIGHT]
    return due, waiting, busy


def routine_fields(args, e, act, entries, tasks, envs):
    """Apply a routine's own flags to entry `e`; the changed field names.
    add needs every one of them but --status (a new routine is active)."""
    if act == "add":
        missing = [f"--{f}" for f in ("mode", "environment", "schedule",
                                      "trigger", "manage")
                   if not (getattr(args, f) or "").strip()]
        if missing:
            sys.exit(f"error: routine add needs {', '.join(missing)}")
        e["status"] = "active"
    changes = []
    if args.mode is not None:
        mode = args.mode.strip()
        if mode not in ROUTINE_MODES:
            sys.exit(f"error: mode must be one of {', '.join(ROUTINE_MODES)}")
        mine = routine_tasks(tasks, entries, e) if act != "add" else []
        if mode == "attended" and len(mine) > 1:
            sys.exit(f"error: an attended routine holds exactly one task and "
                     f"{e['name']} runs "
                     + ", ".join(f"T{t['id']}" for t in mine))
        e["mode"] = mode
        changes.append("mode")
    if args.environment is not None:
        env = registry_holder(envs, args.environment.strip())
        if env is None:
            have = ", ".join(x["name"] for x in envs) or "none"
            sys.exit(f"error: no environment '{args.environment.strip()}' "
                     f"({have}); register it first: env add <name>")
        e["environment"] = env["name"]
        changes.append("environment")
    if args.schedule is not None:
        parse_routine_schedule(args.schedule)
        e["schedule"] = " ".join(args.schedule.split())
        changes.append("schedule")
    if args.trigger is not None:
        trigger = " ".join(args.trigger.split())
        if not trigger:
            sys.exit("error: a routine's trigger cannot be empty")
        e["trigger"] = trigger
        changes.append("trigger")
    status = getattr(args, "status", None)
    if status is not None:
        if status.strip() not in ROUTINE_STATUSES:
            sys.exit("error: status must be one of "
                     + ", ".join(ROUTINE_STATUSES))
        e["status"] = status.strip()
        changes.append("status")
    if args.manage is not None:
        if not args.manage.strip():
            sys.exit("error: a routine says how to change or remove its "
                     "trigger at the source; --manage cannot be empty")
        e["body"] = args.manage.strip()
        changes.append("manage")
    return changes


def cmd_registry(args):
    root, scope, branch, bw = ctx()
    kind = args.registry
    label = REGISTRIES[kind]["label"]
    entries = all_registry(bw, scope, kind)
    act = args.action
    name = (getattr(args, "name", None) or "").strip()
    if act == "wake":
        cmd_routine_wake(bw, scope, entries, name)
        return
    tasks = all_tasks(bw, scope) if kind == "routine" else []
    if act == "list":
        if args.json:
            print(json.dumps([{k: e.get(k, "") for k in
                               REGISTRIES[kind]["fields"] + ["body"]}
                              for e in entries], indent=1))
            return
        for e in entries:
            print(registry_line(e))
            mine = routine_tasks(tasks, entries, e) if tasks else []
            if mine:
                print("  tasks: " + ", ".join(f"T{t['id']}" for t in mine))
            for t in mine:
                stall = t.get("routine_stall")
                if stall:
                    when = (f" (should have fired {format_due(stall[1])})"
                            if stall[1] else "")
                    print(f"  T{t['id']} {stall_words(stall)}{when}")
        if not entries:
            print(f"(no {label}s)")
        return
    e = registry_holder(entries, name)
    if act == "add":
        err = registry_name_error(name)
        if err:
            sys.exit(f"error: {err}")
        if e:
            sys.exit(f"error: {label} " + (
                f"'{name}' already exists" if e["name"] == name else
                f"'{e['name']}' was formerly '{name}', so that name stays "
                "reserved (run records may use it)"))
        err = catalog_name_taken(catalog_entries(bw, scope), name, kind)
        if err:
            sys.exit(f"error: {err}")
        e = {"kind": kind, "name": name, "created":
             datetime.date.today().isoformat(),
             "path": os.path.join(registry_dir(bw, scope, kind), f"{name}.md")}
        if kind == "agent" and not " ".join((args.desc or "").split()):
            sys.exit("error: agent add needs --desc \"<one line: who it "
                     "is>\"")
    elif e is None:
        have = ", ".join(x["name"] for x in entries) or "none"
        sys.exit(f"error: no {label} '{name}' ({have}). See: {kind} list")
    elif e["name"] != name:
        print(f"matched {label} '{e['name']}' (formerly '{name}')",
              file=sys.stderr)
    if act == "show":
        show_file(e["path"], bw, scope, args.raw)
        return
    if act == "rm":
        everything = catalog_entries(bw, scope)
        err = catalog_rm_refusal(bw, scope, next(
            x for x in everything if x["path"] == e["path"]), everything)
        if err:
            sys.exit(f"error: {err}")
        held = (", ".join(f"T{t['id']}" for t in
                          routine_tasks(tasks, entries, e))
                if kind == "routine" else "")
        if held:
            sys.exit(f"error: {held} point at routine {e['name']}; clear "
                     "each first (update <id> --routine \"\")")
        used = ([r["name"] for r in all_registry(bw, scope, "routine")
                 if registry_holder([e], r.get("environment")) is e]
                if kind == "env" else [])
        if used:
            sys.exit(f"error: environment {e['name']} is used by routine "
                     f"{', '.join(used)}; point each elsewhere first (routine "
                     "update <name> --environment <env>)")
        os.remove(e["path"])
        board_commit(root, branch, bw, scope, f"dev: {kind} rm {e['name']}")
        freed = [e["name"]] + split_names(e.get("formerly"))
        print(f"{label} '{e['name']}' removed (frees {', '.join(freed)})")
        return
    if act == "rename":
        new = (args.new_name or "").strip()
        old = e["name"]
        err = registry_name_error(new)
        if err:
            sys.exit(f"error: {err}")
        if new == old:
            sys.exit(f"error: {label} is already named '{old}'")
        held = registry_holder(entries, new)
        if held is not None and held is not e:
            sys.exit(f"error: '{new}' is held by {label} '{held['name']}'"
                     + ("" if held["name"] == new else " as a former name"))
        err = catalog_name_taken(catalog_entries(bw, scope), new, kind)
        if err:
            sys.exit(f"error: {err}")
        old_path = e["path"]
        registry_rename(e, new)
        e["path"] = os.path.join(registry_dir(bw, scope, kind), f"{new}.md")
        os.replace(old_path, e["path"])
        write_registry(e)
        write_board_cfg(bw, scope, read_board_cfg(bw, scope))  # stamp 13
        board_commit(root, branch, bw, scope, f"dev: {kind} rename {old} → {new}")
        print(f"{label} {old} → {new} (formerly: {e['formerly']}; former "
              "names stay reserved and still match)")
        return
    changes = []
    if args.accessors is not None or act == "add":
        acc = list(dict.fromkeys(split_names(args.accessors)))
        handles = [h for h, _ in board_contributors(read_board_cfg(bw, scope))]
        err = accessors_error(acc, handles)
        if err:
            sys.exit(f"error: {label} {err}")
        e["accessors"] = ", ".join(acc)
        changes.append("accessors")
    if kind == "agent" and args.desc is not None:
        desc = " ".join(args.desc.split())
        if not desc:
            sys.exit("error: an agent's description cannot be empty")
        e["description"] = desc
        changes.append("description")
    if kind == "env" and args.machine is not None:
        e["machine"] = args.machine.strip()
        changes.append("machine")
    if kind == "env" and args.expects is not None:
        e["body"] = args.expects.strip()
        changes.append("expectations")
    if kind == "routine":
        changes += routine_fields(args, e, act, entries, tasks,
                                  all_registry(bw, scope, "env"))
    if act == "update" and not changes:
        sys.exit("error: nothing to update")
    os.makedirs(os.path.dirname(e["path"]), exist_ok=True)
    write_registry(e)
    write_board_cfg(bw, scope, read_board_cfg(bw, scope))  # stamp 13
    board_commit(root, branch, bw, scope,
                 f"dev: {kind} {act} {e['name']}"
                 + (f" ({', '.join(changes)})" if act == "update" else ""))
    print(f"{label} '{e['name']}' {'added' if act == 'add' else 'updated'}: "
          + registry_line(e))


# ---------- user catalog: categories, keys and {key.field} references ----------
# <scope>/.catalog/<category>.md declares a user category; its body holds one
# field per line, `<field>: <one line: what it holds>`, where a description
# ending in `(one of: a, b, c)` names the values the field expects (a value
# outside them only warns). <scope>/.catalog/<category>/<key>.md holds one
# key:
#   ---
#   name: elm-st
#   address: 12 Elm St          (one line per field, in the category's order)
#   owner: {bob}                (a bare {key} in a value is a reference)
#   formerly: old-name          (past names; still reserved, still resolve)
#   created: 2026-11-23
#   ---
# Keys share the one catalog namespace with the built-in entries (agents,
# environments, routines), so {key.field} names a key in any category and a
# built-in entry's fields resolve like any key's. {a.b.c} chains: a.b holds
# {x}, so c is read from x. Text read through TASKS (show, flow show, the
# registry and catalog show) resolves each {key.field} outside code spans
# and fenced blocks as `key.field «value»` and reports the ones it cannot;
# --raw prints the file as stored. In a flow a declared input wins: in
# {property.address} with an input `property`, the runner supplies the key.

RAW_HELP = ("print the file as stored, {key.field} references unresolved "
            "(read this before rewriting the text)")
SET_HELP = ("<field>=<value>, one line (repeatable; an empty value "
            "clears it)")
CATALOG_BUILTIN_DIRS = tuple(r["dir"] for r in REGISTRIES.values())
# Frontmatter every key carries besides its fields, so no field may take it.
CATALOG_META = ("name", "formerly", "created")
CATALOG_ENUM_RE = re.compile(r"\s*\(one of:\s*([^)]*)\)\s*$")
# A bare {key} inside a value: a reference to that key, which is how a
# reference chains. Outside a value a bare {name} is a flow placeholder.
CATALOG_KEY_REF_RE = re.compile(rf"(?<!\$)\{{({CATALOG_NAME})\}}")
# Inline code spans (same-length backtick runs) are skipped, and so is every
# line inside a ``` or ~~~ fence.
CATALOG_SCAN_RE = re.compile(
    r"(?P<code>(`+).*?(?<!`)\2(?!`))"
    rf"|(?<!\$)\{{(?P<ref>{CATALOG_NAME}(?:\.{CATALOG_NAME})+)\}}")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def category_path(bw, scope, name):
    return os.path.join(bw, cdir(scope), f"{name}.md")


def parse_category_fields(body):
    """[{'name', 'description', 'one_of'}] from a category body. Pure."""
    out = []
    for line in (body or "").splitlines():
        m = re.match(rf"^({CATALOG_NAME}):\s*(.*)$", line.strip())
        if not m:
            continue
        en = CATALOG_ENUM_RE.search(m.group(2))
        out.append({"name": m.group(1), "description": m.group(2).strip(),
                    "one_of": split_names(en.group(1)) if en else []})
    return out


def all_categories(bw, scope):
    """Every user category (.catalog/<category>.md), by name."""
    out = []
    for p in sorted(glob.glob(os.path.join(bw, cdir(scope), "*.md"))):
        with open(p) as fh:
            m = re.match(r"^---\n(.*?)\n---\n?(.*)$", fh.read(), re.DOTALL)
        if not m:
            sys.exit(f"error: malformed catalog category file {p}")
        meta = parse_kv(m.group(1))
        out.append({"name": os.path.basename(p)[:-3],
                    "created": meta.get("created", ""),
                    "fields": parse_category_fields(m.group(2)), "path": p})
    return out


def write_category(cat):
    lines = ["---", f"name: {cat['name']}", f"created: {cat['created']}",
             "---", ""] + [f"{f['name']}: {f['description']}"
                           for f in cat["fields"]]
    with open(cat["path"], "w", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def category_name_error(name):
    """Why `name` cannot name a user category, or None. Pure."""
    if not CATALOG_NAME_RE.match(name or ""):
        return (f"category name '{name}' must be {CATALOG_NAME_RULE} "
                "(properties, rental_units)")
    if name in CATALOG_BUILTIN_DIRS:
        return (f"'{name}' is a built-in category; its entries are written "
                f"through TASKS agent|env|routine")
    return None


def category_field_spec(text):
    """(field dict, None) from `<field>: <description>`, or (None, why).
    Pure."""
    m = re.match(r"^\s*([^:\s]+)\s*:\s*(.*)$", text or "")
    if not m or not m.group(2).strip():
        return None, (f"field '{text}' must read \"<field>: <one line: what "
                      "it holds>\" (end it with \"(one of: a, b)\" to name "
                      "the values it expects)")
    name, desc = m.group(1), " ".join(m.group(2).split())
    if not CATALOG_NAME_RE.match(name):
        return None, f"field name '{name}' must be {CATALOG_NAME_RULE}"
    if name in CATALOG_META:
        return None, (f"'{name}' is not a field name: every key already "
                      f"carries {', '.join(CATALOG_META)}")
    [f] = parse_category_fields(f"{name}: {desc}")
    return f, None


def all_catalog_keys(bw, scope, cats=None):
    """Every key of every user category. Each carries its category's field
    names, so resolving a reference needs nothing but the entries."""
    out = []
    for cat in all_categories(bw, scope) if cats is None else cats:
        fields = [f["name"] for f in cat["fields"]]
        d = os.path.join(bw, cdir(scope), cat["name"])
        for p in sorted(glob.glob(os.path.join(d, "*.md"))):
            with open(p) as fh:
                m = re.match(r"^---\n(.*?)\n---\n?(.*)$", fh.read(),
                             re.DOTALL)
            if not m:
                sys.exit(f"error: malformed catalog key file {p}")
            meta = parse_kv(m.group(1))
            out.append({"kind": "key", "category": cat["name"],
                        "name": meta.get("name") or os.path.basename(p)[:-3],
                        "formerly": meta.get("formerly", ""),
                        "created": meta.get("created", ""),
                        "values": {k: v for k, v in meta.items()
                                   if k not in CATALOG_META},
                        "fields": fields, "body": m.group(2).strip(),
                        "path": p})
    return out


def catalog_entries(bw, scope):
    """The whole catalog namespace: built-in entries and user keys."""
    return all_registries(bw, scope) + all_catalog_keys(bw, scope)


def write_catalog_key(e):
    fields = e["fields"] + [k for k in e["values"] if k not in e["fields"]]
    lines = (["---", f"name: {e['name']}"]
             + [f"{k}: {e['values'].get(k, '')}" for k in fields]
             + [f"formerly: {e.get('formerly', '')}",
                f"created: {e.get('created', '')}", "---"])
    body = (e.get("body") or "").strip()
    with open(e["path"], "w", newline="\n") as fh:
        fh.write("\n".join(lines) + ("\n\n" + body + "\n" if body else "\n"))


def entry_label(e):
    """'agent', 'environment', 'routine', or '<category> key'."""
    if e["kind"] in REGISTRIES:
        return REGISTRIES[e["kind"]]["label"]
    return f"{e['category']} key"


def entry_fields(e):
    if e["kind"] in REGISTRIES:
        return REGISTRIES[e["kind"]]["fields"]
    return ["name"] + e["fields"] + [k for k in e["values"]
                                     if k not in e["fields"]]


def entry_value(e, field):
    if e["kind"] in REGISTRIES or field == "name":
        return e.get(field) or ""
    return e["values"].get(field, "")


def catalog_set(e, cat, text):
    """Apply one `--set <field>=<value>` to key `e`: (warning or None) on
    success, else exits. A value outside the field's `one of` only warns,
    and a reference ({key}) is never held to it."""
    field, eq, value = (text or "").partition("=")
    field, value = field.strip(), value.strip()
    err = catalog_set_error(cat, field, eq, value)
    if err:
        sys.exit(f"error: {err}")
    e["values"][field] = value
    spec = next(f for f in cat["fields"] if f["name"] == field)
    if (value and spec["one_of"] and value not in spec["one_of"]
            and not CATALOG_KEY_REF_RE.fullmatch(value)):
        return (f"{e['name']}.{field} is '{value}', not one of "
                f"{', '.join(spec['one_of'])}")
    return None


def catalog_set_error(cat, field, eq, value):
    """Why `--set field=value` cannot be written to a key of `cat`, or
    None. Pure."""
    if not eq or not field:
        return f"--set takes <field>=<value>, got '{field}{eq}{value}'"
    names = [f["name"] for f in cat["fields"]]
    if field not in names:
        return (f"category {cat['name']} has no field '{field}' "
                f"({', '.join(names) or 'none'}); add it: catalog category "
                f"update {cat['name']} --field \"{field}: <what it holds>\"")
    if "\n" in value or "\r" in value:
        return f"{field}: a value is one line"
    return None


def catalog_ref_value(ref, entries):
    """(value, None) for a reference `key.field[.field…]`, or (None, why).
    Each field but the last must hold a bare {key}, which the next field is
    read from. Pure."""
    parts = ref.split(".")
    e = registry_holder(entries, parts[0])
    if e is None:
        return None, f"no catalog key '{parts[0]}'"
    for i, field in enumerate(parts[1:], 1):
        here = ".".join(parts[:i])
        if field not in entry_fields(e):
            who = ("" if here == e["name"]
                   else f" ({entry_label(e)} '{e['name']}')")
            return None, f"{here}{who} has no field '{field}'"
        value = entry_value(e, field)
        here = ".".join(parts[:i + 1])
        if not value:
            return None, f"{here} is empty"
        if i == len(parts) - 1:
            return value, None
        m = CATALOG_KEY_REF_RE.fullmatch(value)
        if not m:
            return None, (f"{here} holds '{value}', not a {{key}} reference, "
                          "so it cannot be read further")
        e = registry_holder(entries, m.group(1))
        if e is None:
            return None, f"{here} points at '{m.group(1)}', no catalog key"


def catalog_text_map(text, fn):
    """`text` with each {key.field} outside code spans and fenced blocks
    replaced by fn(ref), or kept where fn returns None. Pure."""
    out, fence = [], None
    for line in (text or "").split("\n"):
        m = FENCE_RE.match(line)
        if fence:
            if (m and m.group(1)[0] == fence[0]
                    and len(m.group(1)) >= len(fence)):
                fence = None
            out.append(line)
            continue
        if m:
            fence = m.group(1)
            out.append(line)
            continue
        out.append(CATALOG_SCAN_RE.sub(
            lambda mm: mm.group(0) if mm.group("code")
            else (fn(mm.group("ref")) or mm.group(0)), line))
    return "\n".join(out)


def catalog_refs(text):
    """Every {key.field} reference outside code, in order. Pure."""
    refs = []
    catalog_text_map(text, lambda r: refs.append(r))
    return refs


def resolve_catalog_text(text, entries, skip=()):
    """(text with each {key.field} shown as `key.field «value»`, [(ref,
    why)] for the ones that do not resolve). A reference whose head is in
    `skip` (a flow's declared inputs) is left as written. Pure."""
    bad = []

    def one(ref):
        if ref.split(".", 1)[0] in skip:
            return None
        value, why = catalog_ref_value(ref, entries)
        if why:
            if (ref, why) not in bad:
                bad.append((ref, why))
            return None
        return f"{ref} «{value}»"
    return catalog_text_map(text, one), bad


def live_ref_refusal(what, *texts):
    """Why record text cannot be written as given, or None. A record keeps
    the value a run used; a live {key.field} in it would be shown with
    whatever the catalog holds when it is read, so past records would change
    with the catalog. Nothing is resolved here: the value the run used may
    no longer be the catalog's, so only the writer knows it. Pure."""
    refs = list(dict.fromkeys(r for t in texts for r in catalog_refs(t)))
    if not refs:
        return None
    return (f"{what} holds a live catalog reference "
            f"({', '.join(f'{{{r}}}' for r in refs)}); a record keeps the "
            f"value the run used, so write that value instead: "
            f"`{refs[0]} «<value>»`, or the plain value (naming the syntax, "
            f"not a value? put it in backticks)")


def print_resolved(text, entries, skip=()):
    out, bad = resolve_catalog_text(text, entries, skip)
    print(out)
    for ref, why in bad:
        print(f"warning: unresolved catalog reference {{{ref}}}: {why}",
              file=sys.stderr)


def show_file(path, bw, scope, raw, skip=()):
    """Print a board file, its catalog references resolved unless raw."""
    with open(path) as fh:
        text = fh.read().rstrip()
    if raw:
        print(text)
    else:
        print_resolved(text, catalog_entries(bw, scope), skip)


def flow_input_names(inputs):
    """Each declared input's name: its text before the first '('; commas
    inside parentheses (a hint) do not split. Pure."""
    names = [item.split("(", 1)[0].strip()
             for item in re.split(r",(?![^(]*\))", inputs or "")]
    return [n for n in names if n]


def catalog_lint_warnings(inputs, body, entries):
    """Flow lint: an input named like a catalog key (the input wins, so the
    key is out of reach in this flow), and a {key.field} whose key is a
    near-miss of one the catalog holds. Pure."""
    names = flow_input_names(inputs)
    out = []
    for n in names:
        e = registry_holder(entries, n)
        if e is not None:
            out.append(f"input '{n}' is named like {entry_label(e)} "
                       f"'{e['name']}'; in {{{n}.…}} the input wins, so "
                       "rename the input if the key is meant")
    known = sorted({n for e in entries
                    for n in [e["name"]] + split_names(e.get("formerly"))})
    for ref in dict.fromkeys(catalog_refs(body)):
        head, rest = ref.split(".", 1)
        if head in names or registry_holder(entries, head) is not None:
            continue
        near = difflib.get_close_matches(head, known, n=1, cutoff=0.8)
        if near:
            out.append(f"{{{ref}}} names no catalog key; did you mean "
                       f"{{{near[0]}.{rest}}}?")
    return out


def warn_catalog_refs(bw, scope, inputs, body):
    for w in catalog_lint_warnings(inputs, body, catalog_entries(bw, scope)):
        print(f"warning: {w}", file=sys.stderr)


def catalog_ref_holders(entry, tasks, flows, entries):
    """What still references `entry` (by its name or a former one): live
    tasks (any status but done and not-planned), active flows (a reference
    headed by one of the flow's inputs is the input's, not the key's) and
    other catalog entries, as labels. Pure."""
    names = {entry["name"], *split_names(entry.get("formerly"))}

    def hits(text, skip=(), bare=False):
        heads = {r.split(".", 1)[0] for r in catalog_refs(text)} - set(skip)
        if bare:
            heads |= set(CATALOG_KEY_REF_RE.findall(text))
        return bool(names & heads)
    out = [f"T{t['id']}" for t in tasks
           if t["status"] not in ("done", "not-planned")
           and hits(t.get("title", "") + "\n" + t.get("body", ""))]
    out += [f"flow {f['name']}" for f in flows if flow_is_active(f)
            and hits(f.get("description", "") + "\n" + f.get("body", ""),
                     skip=flow_input_names(f.get("inputs")))]
    for e in entries:
        if e is entry:
            continue
        # Field values chain through a bare {key}; a body's bare {name} is
        # a placeholder, so only its {key.field} refs count.
        values = "\n".join(entry_value(e, f) for f in entry_fields(e)
                           if f != "name")
        if hits(values, bare=True) or hits(e.get("body") or ""):
            out.append(f"{entry_label(e)} {e['name']}")
    return out


def catalog_rm_refusal(bw, scope, entry, entries):
    """The error text when `entry` is still referenced, else None."""
    held = catalog_ref_holders(entry, all_tasks(bw, scope),
                               all_flows(bw, scope), entries)
    if not held:
        return None
    return (f"{entry_label(entry)} '{entry['name']}' is still referenced by "
            f"{', '.join(held)}; change those references first (done and "
            "not-planned tasks, retired flows and archives do not count)")


def catalog_key_line(e):
    vals = "; ".join(f"{k}: {v}" for k, v in e["values"].items() if v)
    was = f" (formerly {e['formerly']})" if e.get("formerly") else ""
    return f"{e['name']} — {vals or '(no values)'}{was}"


def find_category(cats, name):
    cat = next((c for c in cats if c["name"] == name), None)
    if cat is None:
        if name in CATALOG_BUILTIN_DIRS:
            return None
        have = ", ".join(c["name"] for c in cats) or "none"
        sys.exit(f"error: no catalog category '{name}' ({have}). See: "
                 "catalog list")
    return cat


def builtin_kind(dirname):
    return next(k for k, r in REGISTRIES.items() if r["dir"] == dirname)


def cmd_catalog_category(args, root, scope, branch, bw, cats, keys):
    act = args.category_action
    name = (args.name or "").strip()
    if act == "add":
        err = category_name_error(name)
        if err:
            sys.exit(f"error: {err}")
        if any(c["name"] == name for c in cats):
            sys.exit(f"error: category '{name}' already exists")
        cat = {"name": name, "created": datetime.date.today().isoformat(),
               "fields": [], "path": category_path(bw, scope, name)}
        if not args.field:
            sys.exit("error: category add needs at least one --field "
                     "\"<field>: <one line: what it holds>\"")
    else:
        cat = find_category(cats, name)
        if cat is None:
            sys.exit(f"error: '{name}' is a built-in category; its fields "
                     "are fixed")
    mine = [k for k in keys if k["category"] == cat["name"]]
    if act == "show":
        with open(cat["path"]) as fh:
            print(fh.read().rstrip())
        return
    if act == "rename":
        new = (args.new_name or "").strip()
        err = category_name_error(new)
        if err:
            sys.exit(f"error: {err}")
        if new == name:
            sys.exit(f"error: category is already named '{name}'")
        old_dir = os.path.join(bw, cdir(scope), name)
        new_dir = os.path.join(bw, cdir(scope), new)
        if any(c["name"] == new for c in cats) or os.path.exists(new_dir):
            sys.exit(f"error: category '{new}' already exists")
        old_path, cat["name"] = cat["path"], new
        cat["path"] = category_path(bw, scope, new)
        os.replace(old_path, cat["path"])
        if os.path.isdir(old_dir):
            os.replace(old_dir, new_dir)
        write_category(cat)
        board_commit(root, branch, bw, scope,
                     f"dev: catalog category rename {name} → {new}")
        print(f"category {name} → {new} ({len(mine)} key"
              f"{'' if len(mine) == 1 else 's'} moved; references name "
              "keys, so none change)")
        return
    if act == "rm":
        if mine:
            sys.exit(f"error: category {name} still holds "
                     f"{', '.join(k['name'] for k in mine)}; rm each first "
                     "(catalog rm <key>)")
        os.remove(cat["path"])
        try:
            os.rmdir(os.path.join(bw, cdir(scope), name))
        except OSError:
            pass
        board_commit(root, branch, bw, scope, f"dev: catalog category rm "
                                              f"{name}")
        print(f"category '{name}' removed")
        return
    changes = []
    for text in args.field or []:
        f, err = category_field_spec(text)
        if err:
            sys.exit(f"error: {err}")
        old = next((x for x in cat["fields"] if x["name"] == f["name"]),
                   None)
        if old is None:
            cat["fields"].append(f)
        else:
            old.update(f)
        changes.append(f["name"])
    for field in getattr(args, "drop_field", None) or []:
        if not any(x["name"] == field for x in cat["fields"]):
            sys.exit(f"error: category {name} has no field '{field}'")
        held = [k["name"] for k in mine if k["values"].get(field)]
        if held:
            sys.exit(f"error: {', '.join(held)} still "
                     f"hold{'s' if len(held) == 1 else ''} a value for "
                     f"'{field}'; clear each first (catalog update <key> "
                     f"--set {field}=)")
        cat["fields"] = [x for x in cat["fields"] if x["name"] != field]
        for k in mine:
            if field in k["values"]:
                del k["values"][field]
                k["fields"] = [x["name"] for x in cat["fields"]]
                write_catalog_key(k)
        changes.append(f"-{field}")
    if not changes:
        sys.exit("error: nothing to update")
    os.makedirs(os.path.dirname(cat["path"]), exist_ok=True)
    write_category(cat)
    board_commit(root, branch, bw, scope,
                 f"dev: catalog category {act} {name} ({', '.join(changes)})")
    print(f"category '{name}' {'added' if act == 'add' else 'updated'}: "
          + ", ".join(f["name"] for f in cat["fields"]))


def cmd_catalog(args):
    root, scope, branch, bw = ctx()
    cats = all_categories(bw, scope)
    keys = all_catalog_keys(bw, scope, cats)
    entries = all_registries(bw, scope) + keys
    act = args.action
    if act == "category":
        cmd_catalog_category(args, root, scope, branch, bw, cats, keys)
        return
    if act == "list":
        name = (args.category or "").strip()
        if not name:
            rows = []
            for kind, r in REGISTRIES.items():
                n = sum(1 for e in entries if e["kind"] == kind)
                rows.append({"name": r["dir"], "builtin": True, "keys": n,
                             "fields": REGISTRIES[kind]["fields"]})
            for c in cats:
                rows.append({"name": c["name"], "builtin": False,
                             "keys": sum(1 for k in keys
                                         if k["category"] == c["name"]),
                             "fields": [f["name"] for f in c["fields"]]})
            if args.json:
                print(json.dumps(rows, indent=1))
                return
            for r in rows:
                what = ("built-in" if r["builtin"]
                        else "fields: " + ", ".join(r["fields"]))
                print(f"{r['name']} — {what} ({r['keys']} "
                      f"key{'' if r['keys'] == 1 else 's'})")
            return
        cat = find_category(cats, name)
        if cat is None:
            sel = [e for e in entries if e["kind"] == builtin_kind(name)]
        else:
            sel = [k for k in keys if k["category"] == name]
        if args.json:
            print(json.dumps([{"name": e["name"], "category": name,
                               "values": {f: entry_value(e, f)
                                          for f in entry_fields(e)
                                          if f != "name"},
                               "formerly": e.get("formerly", "")}
                              for e in sel], indent=1))
            return
        for e in sel:
            print(registry_line(e) if cat is None else catalog_key_line(e))
        if not sel:
            print(f"(no keys in {name})")
        return
    if act == "get":
        ref = (args.ref or "").strip().strip("{}")
        if "." not in ref:
            sys.exit("error: catalog get takes <key>.<field>[.<field>…]")
        value, why = catalog_ref_value(ref, entries)
        if why:
            sys.exit(f"error: {{{ref}}} does not resolve: {why}")
        print(value)
        return
    name = (args.name or "").strip()
    if act == "add":
        cat = find_category(cats, args.category.strip())
        if cat is None:
            kind = builtin_kind(args.category.strip())
            sys.exit(f"error: {args.category.strip()} is a built-in "
                     f"category; add one with: {kind} add {name} …")
        err = registry_name_error(name)
        if err:
            sys.exit(f"error: {err}")
        held = registry_holder(entries, name)
        if held is not None:
            sys.exit(f"error: '{name}' is held by {entry_label(held)} "
                     f"'{held['name']}'"
                     + ("" if held["name"] == name else " as a former name")
                     + "; catalog names are shared across categories")
        e = {"kind": "key", "category": cat["name"], "name": name,
             "formerly": "", "created": datetime.date.today().isoformat(),
             "values": {f["name"]: "" for f in cat["fields"]},
             "fields": [f["name"] for f in cat["fields"]], "body": "",
             "path": os.path.join(bw, cdir(scope), cat["name"],
                                  f"{name}.md")}
    else:
        e = registry_holder(entries, name)
        if e is None:
            sys.exit(f"error: no catalog key '{name}'. See: catalog list")
        if e["name"] != name:
            print(f"matched {entry_label(e)} '{e['name']}' (formerly "
                  f"'{name}')", file=sys.stderr)
        if act == "show":
            show_file(e["path"], bw, scope, args.raw)
            return
        if e["kind"] != "key":
            sys.exit(f"error: {e['name']} is a built-in {entry_label(e)}; "
                     f"use: {e['kind']} {act} {e['name']} …")
        cat = find_category(cats, e["category"])
    if act == "rm":
        err = catalog_rm_refusal(bw, scope, e, entries)
        if err:
            sys.exit(f"error: {err}")
        os.remove(e["path"])
        board_commit(root, branch, bw, scope, f"dev: catalog rm {e['name']}")
        freed = [e["name"]] + split_names(e.get("formerly"))
        print(f"{entry_label(e)} '{e['name']}' removed (frees "
              f"{', '.join(freed)})")
        return
    if act == "rename":
        new, old = (args.new_name or "").strip(), e["name"]
        err = registry_name_error(new)
        if err:
            sys.exit(f"error: {err}")
        if new == old:
            sys.exit(f"error: key is already named '{old}'")
        held = registry_holder(entries, new)
        if held is not None and held is not e:
            sys.exit(f"error: '{new}' is held by {entry_label(held)} "
                     f"'{held['name']}'"
                     + ("" if held["name"] == new else " as a former name"))
        old_path = e["path"]
        registry_rename(e, new)
        e["path"] = os.path.join(os.path.dirname(old_path), f"{new}.md")
        os.replace(old_path, e["path"])
        write_catalog_key(e)
        board_commit(root, branch, bw, scope,
                     f"dev: catalog rename {old} → {new}")
        print(f"key {old} → {new} (formerly: {e['formerly']}; former names "
              "stay reserved and references to them still resolve)")
        return
    warnings = [w for w in (catalog_set(e, cat, s) for s in args.set or [])
                if w]
    if act == "update" and not args.set:
        sys.exit("error: nothing to update (--set <field>=<value>)")
    os.makedirs(os.path.dirname(e["path"]), exist_ok=True)
    write_catalog_key(e)
    fields = ", ".join(s.partition("=")[0].strip() for s in args.set or [])
    board_commit(root, branch, bw, scope,
                 f"dev: catalog {act} {e['name']}"
                 + (f" ({fields})" if act == "update" else ""))
    print(f"{entry_label(e)} '{e['name']}' "
          f"{'added' if act == 'add' else 'updated'}: {catalog_key_line(e)}")
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)


# ---------- flow sequences ----------
# A flow body groups its steps into sequences: a markdown heading, then
# labeled lines before the steps —
#   ## Draft on the studio mac
#   Environment: studio-mac
#   Agent: grok-bot (usually)
#   Needs: a signed-in browser
#   Inputs: client
#   Returns: the draft's URL
# `Environment: inline` describes a place no registry entry holds yet, on
# its own `Expects:` and `Accessors:` lines.
# All of it is prose for whoever runs the flow. The script reads the first
# word of Agent: and Environment:, an inline sequence's Expects:, and the
# handles on Accessors:, and only to warn. No heading, or no label, means
# runner + project.

SEQUENCE_LABEL_RE = re.compile(
    r"^(Environment|Agent|Needs|Inputs|Returns|Expects|Accessors):\s*(.*)$")


def flow_sequences(body):
    """[{'title', 'labels': {label: value}}] for each heading in a flow
    body, labels read from the block of labeled lines right under it
    (blank lines skipped). Pure."""
    seqs, labels = [], None
    for line in (body or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            labels = {}
            seqs.append({"title": s.lstrip("#").strip(), "labels": labels})
            continue
        if labels is None or not s:
            continue
        m = SEQUENCE_LABEL_RE.match(s)
        if m:
            labels.setdefault(m.group(1), m.group(2).strip())
        else:
            labels = None    # the steps began; later lines are not labels
    return seqs


def sequence_name_warnings(body, agents, envs, handles):
    """Warnings for Agent:/Environment: names the registries do not hold
    as a current name: a former name says what it now points at, an
    unknown one says so. Reserved words (runner, project, any, inline)
    pass. Also an inline environment with no Expects:, and an Accessors:
    handle that is not a board contributor. Pure."""
    out = []
    for seq in flow_sequences(body):
        where = f"sequence '{seq['title']}'"
        unknown = [h for h in split_names(seq["labels"].get("Accessors"))
                   if h not in handles]
        if unknown:
            out.append(f"{where} lists accessors that are not board "
                       f"contributors: {', '.join(unknown)} "
                       f"({', '.join(handles) or 'none'})")
        for label, kind, entries in (("Agent", "agent", agents),
                                     ("Environment", "env", envs)):
            word = re.split(r"[\s(]", seq["labels"].get(label, ""), 1)[0]
            name = word.rstrip(".,;:")
            if (kind == "env" and name == "inline"
                    and not seq["labels"].get("Expects")):
                out.append(f"{where} is inline but has no Expects: line; "
                           "say what the place must provide")
            if not name or name in REGISTRY_RESERVED:
                continue
            e = registry_holder(entries, name)
            if e is not None and e["name"] == name:
                continue
            what = REGISTRIES[kind]["label"]
            if e is not None:
                out.append(f"{what} '{name}' in {where} is a former name of "
                           f"'{e['name']}'; write the current name")
            else:
                have = ", ".join(x["name"] for x in entries) or "none"
                out.append(f"{where} names {what} '{name}', which the board "
                           f"does not have ({have}); add it: {kind} add "
                           f"{name} …")
    return out


def warn_sequence_names(bw, scope, body):
    handles = [h for h, _ in board_contributors(read_board_cfg(bw, scope))]
    for w in sequence_name_warnings(body, all_registry(bw, scope, "agent"),
                                    all_registry(bw, scope, "env"), handles):
        print(f"warning: {w}", file=sys.stderr)


# Inputs are written as {name} where a step uses them. The script checks
# that pairing at authoring time, and only to warn: a {placeholder} with no
# declared input is fine (a derived value) unless it is a near-miss of one,
# and ${...} is shell, never a placeholder.
PLACEHOLDER_RE = re.compile(r"(?<!\$)\{([A-Za-z_][\w-]*)\}")


def placeholder_warnings(inputs, body):
    """Warnings for declared inputs never referenced as {name} in the
    body, an input name {name} cannot spell (spaces), and an undeclared
    {placeholder} that looks like a typo of a declared input. An input's
    name is its text before the first '('; a hint may hold commas, so
    only commas outside parentheses separate inputs. Pure."""
    out, names = [], []
    for item in re.split(r",(?![^(]*\))", inputs or ""):
        name = item.split("(", 1)[0].strip()
        if not name:
            continue
        if re.search(r"\s", name):
            out.append(f"input '{name}' cannot be referenced as a "
                       "{placeholder}; rename it without spaces "
                       f"({'_'.join(name.split())})")
            continue
        names.append(name)
    used = PLACEHOLDER_RE.findall(body or "")
    # {input.field}: the input holds a catalog key.
    used += [h for h in (r.split(".", 1)[0] for r in catalog_refs(body))
             if h in names]
    for name in names:
        if name not in used:
            out.append(f"input '{name}' is declared but never referenced as "
                       f"{{{name}}} in the body (inputs are written as "
                       "{name} where a step uses them)")
    lowered = {n.lower(): n for n in names}
    for ph in dict.fromkeys(used):
        if ph in names:
            continue
        near = lowered.get(ph.lower()) or next(iter(
            difflib.get_close_matches(ph, names, n=1, cutoff=0.8)), None)
        if near:
            out.append(f"{{{ph}}} is not a declared input; did you mean "
                       f"{{{near}}}?")
    return out


def warn_placeholders(inputs, body):
    for w in placeholder_warnings(inputs, body):
        print(f"warning: {w}", file=sys.stderr)


# ---------- task file format ----------
# <scope>/.tasks/NNN.md :
#   ---
#   id: 12
#   title: Fix token refresh
#   area: auth
#   status: backlog
#   kind:                    (optional; "umbrella" = goal parent)
#   assignee: qz
#   branch: dev/12-fix-token-refresh
#   deps: [3, 7]
#   pr: https://github.com/...
#   needs: decision        (set while a design fork awaits a human call)
#   created: 2026-08-09
#   ---
#   freeform description

def parse_kv(text):
    d = {}
    for line in text.splitlines():
        m = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if m:
            d[m.group(1)] = m.group(2).strip()
    return d


def parse_task(path):
    with open(path) as f:
        text = f.read()
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        sys.exit(f"error: malformed task file {path}")
    meta = parse_kv(m.group(1))
    meta["id"] = int(meta["id"])
    deps = meta.get("deps", "")
    meta["deps"] = [int(x) for x in re.findall(r"\d+", deps)]
    meta["kind"] = meta.get("kind", "") or ""
    # later was folded into shelved (T88). Reading it as shelved keeps an
    # older board, and its archives, working with no migration; the next
    # rewrite stamps shelved, which every schema-9+ script knows.
    if meta.get("status") == RETIRED_LATER:
        meta["status"] = "shelved"
    for k in OPTIONAL_FIELDS:
        meta[k] = meta.get(k, "") or ""
    meta["body"] = m.group(2).strip()
    meta["path"] = path
    return meta


def render_task(meta):
    lines = ["---"]
    for k in FIELDS:
        v = meta.get(k, "")
        if k == "deps":
            v = "[" + ", ".join(str(d) for d in meta.get("deps", [])) + "]"
        elif k == "type":
            v = task_type(meta)
        elif k in OPTIONAL_FIELDS and not v:
            continue
        elif k in ("waiting", "unattended") and not waiting_allowed(meta):
            continue
        lines.append(f"{k}: {v}")
    lines.append("---")
    body = meta.get("body", "").strip()
    return "\n".join(lines) + ("\n\n" + body + "\n" if body else "\n")


def is_umbrella(t):
    return (t.get("kind") or "").strip() == "umbrella"


def task_type(t):
    """The task's type, with absent/empty read as dev."""
    return (t.get("type") or "").strip() or DEV


def is_ops(t):
    return task_type(t) == OPS


def off_board_guard(old, new, status):
    """Guard for `update --status` shelved|not-planned (OUT_OF_PLAY).

    Returns (error, cleared). A task moved off the board must not keep a
    live branch or PR: shelved and not-planned drop its area lock, and the
    next iteration's reseed clears both fields, orphaning the PR. `error`
    is set while `new` still carries either — the same call must clear
    them. `cleared` names what that call dropped (old values) so the body
    can record it and the work stays findable. Nothing is ever deleted.
    """
    if status not in OUT_OF_PLAY:
        return None, []
    live = [f"{k} {new[k].strip()}" for k in ("branch", "pr")
            if (new.get(k) or "").strip()]
    if live:
        reason = ' --reason "<why>"' if status in REASON_STATUSES else ""
        return (f"error: T{new['id']} still has {' and '.join(live)}; "
                f"moving it to {status} would strand them. Decide the PR's "
                f"fate first (land it, close it, or keep it open), run TASKS "
                f"cleanup {new['id']} to drop its worktree (the branch and PR "
                f"are kept), then clear both in the same call: TASKS update "
                f"{new['id']} --status "
                f"{status}{reason} --branch \"\" --pr \"\" (the old values are "
                f"recorded in the body; nothing is deleted)"), []
    return None, [f"{k} {old[k].strip()}" for k in ("branch", "pr")
                  if (old.get(k) or "").strip()]


def validate_type(meta, set_type=False, set_area=False, new=False):
    """type is dev, ops, or empty (= dev); an ops task carries no area.
    Exits on error.

    Both remedies are valid when the two collide, so the message leads with
    the one matching what the caller just asked for: setting `--type ops`
    on a tagged task means drop the area, while tagging an ops task means
    it has to become a dev task first. `new` is an add, where no task
    exists yet to point an update at.
    """
    typ = (meta.get("type") or "").strip()
    if typ not in ("", DEV, OPS):
        sys.exit(f"error: type must be '{DEV}' or '{OPS}'")
    if typ == OPS and split_areas(meta.get("area", "")):
        why = "(areas lock code; ops touches none)"
        if new:
            sys.exit(f"error: an ops task carries no area {why}. Add it "
                     f"without --area, or without --type {OPS} if it needs "
                     f"code")
        tid = meta["id"]
        head = f"error: T{tid} is an ops task and carries no area {why}"
        to_ops = f"drop the area: update {tid} --type {OPS} --area \"\""
        to_dev = (f"make it a dev task first: update {tid} --type {DEV} "
                  f"--area <name>")
        if set_type and not set_area:
            sys.exit(f"{head}. To run it through /ops flows, {to_ops}")
        if set_area and not set_type:
            sys.exit(f"{head}. If it needs code, {to_dev}")
        sys.exit(f"{head}. Either {to_ops}, or if it needs code, {to_dev}")


# --- Recurring tasks -------------------------------------------------
#
# kind: recurring + cadence "<N><unit>" (d/w/m), or + schedule "<cron>
# <IANA tz>" for a wall-clock time. A recurring task is never terminal:
# instead of done it re-arms — last_run is stamped and status goes back to
# backlog. The due date is DERIVED (last_run + cadence, or the first
# scheduled time after last_run), never stored, so a clock edit takes effect
# immediately and the two can't drift. A cadence task with no last_run yet is
# due now; a scheduled one with no last_run counts from the start of its
# created day. The one override is next_due, a date a human set (`update
# --next-due`): it replaces the derived due in either direction — a first run
# on a chosen day, or the next run pushed or pulled — without inventing a
# last_run. Any recorded run clears it, so it governs exactly one run and the
# clock takes over again after.
#
# last_run is stamped as a timestamp with offset (2026-11-11T12:04-05:00): the
# run time on a cadence, the scheduled time the run covered on a schedule
# (`run_stamp`), so the next due is simply the time after it. A
# bare date (older boards, or `--date YYYY-MM-DD`) still reads: a cadence uses
# its date either way, and a schedule reads it as the end of that day in the
# schedule's timezone.

CADENCE_RE = re.compile(r"^(\d+)([dwm])$")
CADENCE_HELP = "cadence must be <N><unit> with unit d, w, or m (e.g. 2w, 1m)"


def is_recurring(t):
    return (t.get("kind") or "").strip() == RECURRING


# Standard 5-field cron: numbers, `*`, lists, ranges, steps, and day/month
# names. As in vixie cron, when day-of-month and day-of-week are both
# restricted (neither starts with `*`) a day matches if either does.
SCHEDULE_HELP = ("schedule must be a 5-field cron expression and an IANA "
                 "timezone, e.g. \"0 12 * * 3 America/New_York\"")
CRON_MONTHS = {n: i for i, n in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
CRON_DAYS = {n: i for i, n in enumerate("sun mon tue wed thu fri sat".split())}
CRON_FIELDS = (("minute", 0, 59, {}), ("hour", 0, 23, {}),
               ("day-of-month", 1, 31, {}), ("month", 1, 12, CRON_MONTHS),
               ("day-of-week", 0, 7, CRON_DAYS))
# How far ahead to look for the next scheduled time: past the longest gap a
# satisfiable expression has (Feb 29 only, 8 years across 2100). Nothing
# within it = the schedule never fires (Feb 30), refused on write.
CRON_HORIZON_DAYS = 366 * 9


def _cron_field(text, name, lo, hi, names):
    def num(tok):
        tok = tok.lower()
        if tok in names:
            return names[tok]
        if not tok.isdigit() or not lo <= int(tok) <= hi:
            raise ValueError(f"{name} value '{tok}' is out of range {lo}-{hi}")
        return int(tok)
    out = set()
    for part in text.split(","):
        rng, slash, step = part.partition("/")
        if slash and not (step.isdigit() and int(step) > 0):
            raise ValueError(f"bad {name} step in '{part}'")
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a, b = (num(x) for x in rng.split("-", 1))
            if a > b:
                raise ValueError(f"bad {name} range '{rng}'")
        elif step:
            raise ValueError(f"a {name} step needs * or a range: '{part}'")
        else:
            a = b = num(rng)
        out.update(range(a, b + 1, int(step or 1)))
    return out


def parse_schedule(value, what="schedule"):
    """Cron fields plus timezone, as a dict. Exits on a bad schedule."""
    toks = (value or "").split()
    if len(toks) != 6:
        sys.exit(f"error: bad {what} '{value}'; {SCHEDULE_HELP}")
    try:
        tz = zoneinfo.ZoneInfo(toks[5])
    except (ValueError, zoneinfo.ZoneInfoNotFoundError):
        if not zoneinfo.available_timezones():
            sys.exit(f"error: {what} '{value}': this Python has no timezone "
                     f"database; install one with: {tzdata_install()}")
        sys.exit(f"error: bad {what} '{value}': unknown timezone "
                 f"'{toks[5]}' (an IANA name such as America/New_York)")
    sched = {"tz": tz, "dom_star": toks[2].startswith("*"),
             "dow_star": toks[4].startswith("*")}
    try:
        for tok, (name, lo, hi, names) in zip(toks, CRON_FIELDS):
            sched[name] = _cron_field(tok, name, lo, hi, names)
    except ValueError as e:
        sys.exit(f"error: bad {what} '{value}': {e}")
    sched["day-of-week"] = {d % 7 for d in sched["day-of-week"]}
    return sched


def _cron_day(sched, day):
    if day.month not in sched["month"]:
        return False
    dom = day.day in sched["day-of-month"]
    dow = day.isoweekday() % 7 in sched["day-of-week"]
    if sched["dom_star"] or sched["dow_star"]:
        return dom and dow
    return dom or dow


def cron_next(sched, after):
    """First scheduled time strictly after `after` (aware), in the schedule's
    timezone, or None if there is none within CRON_HORIZON_DAYS. Compared in
    UTC, so a wall time a DST gap skips is shifted past the gap."""
    tz, utc = sched["tz"], datetime.timezone.utc
    after = after.astimezone(utc)
    day = after.astimezone(tz).date()
    for _ in range(CRON_HORIZON_DAYS):
        if _cron_day(sched, day):
            hits = [datetime.datetime(day.year, day.month, day.day, h, m,
                                      tzinfo=tz).astimezone(utc)
                    for h in sched["hour"] for m in sched["minute"]]
            hits = [h for h in hits if h > after]
            if hits:
                return min(hits).astimezone(tz)
        day += datetime.timedelta(days=1)
    return None


def parse_run_time(value, what="last_run"):
    """A run's time: YYYY-MM-DD, or a timestamp with its UTC offset
    (2026-11-11T12:04-05:00). Returns a date or an aware datetime."""
    raw = (value or "").strip()
    try:
        if "T" not in raw:
            return datetime.date.fromisoformat(raw)
        ts = datetime.datetime.fromisoformat(raw)
        if ts.tzinfo is not None:
            return ts
    except ValueError:
        pass
    sys.exit(f"error: {what} must be YYYY-MM-DD or a timestamp with its "
             f"offset, e.g. 2026-11-11T12:04-05:00 (got {value!r})")


def run_day(ran):
    """The calendar date of a run time (date or aware datetime)."""
    return ran.date() if isinstance(ran, datetime.datetime) else ran


def format_run_time(ran):
    if isinstance(ran, datetime.datetime):
        return ran.isoformat(timespec="minutes")
    return ran.isoformat()


def due_instant(due):
    """A due date or time as an aware datetime: a bare date is local midnight,
    so it is reached when today reaches it."""
    if isinstance(due, datetime.datetime):
        return due
    return datetime.datetime.combine(due, datetime.time()).astimezone()


def format_due(due):
    if isinstance(due, datetime.datetime):
        return due.strftime("%Y-%m-%d %H:%M %Z")
    return due.isoformat()


# Statuses that stop a recurring task's clock: proposed is not approved yet,
# shelved pauses it, not-planned retires it. None
# is ever due, and `recur ran` refuses each until revived. Cadence, last_run
# and next_due are kept, so the clock resumes when the status goes active.
RECUR_STOPPED = ("proposed", "shelved", "not-planned")


def on_the_clock(t):
    """A recurring task whose cadence is live (status not in RECUR_STOPPED)."""
    return is_recurring(t) and t.get("status") not in RECUR_STOPPED


def parse_cadence(value, what="cadence"):
    m = CADENCE_RE.match((value or "").strip())
    if not m:
        sys.exit(f"error: bad {what} '{value}'; {CADENCE_HELP}")
    n = int(m.group(1))
    if n < 1:
        sys.exit(f"error: bad {what} '{value}'; {CADENCE_HELP}")
    return n, m.group(2)


def add_months(d, n):
    """Calendar month add, clamping the day to the target month's length.

    Jan 31 + 1m = Feb 28/29 — the alternative (rolling into March) would let
    a monthly task drift a day later every short month.
    """
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def cadence_next(last_run, cadence):
    """Date a task with this last_run and cadence next comes due."""
    n, unit = parse_cadence(cadence)
    if unit == "d":
        return last_run + datetime.timedelta(days=n)
    if unit == "w":
        return last_run + datetime.timedelta(weeks=n)
    return add_months(last_run, n)


def task_due_date(t):
    """When a recurring task is due: next_due if set (a date); else, for a
    schedule, the first scheduled time after last_run (or on or after the
    start of its created day) as an aware datetime; else last_run + cadence
    (a date); else None (= due now)."""
    if not is_recurring(t):
        return None
    pinned = (t.get("next_due") or "").strip()
    if pinned:
        return iso_date(pinned, "next_due")
    last = (t.get("last_run") or "").strip()
    schedule = (t.get("schedule") or "").strip()
    if schedule:
        sched = parse_schedule(schedule)
        after = schedule_counts_from(t, sched)
        return cron_next(sched, after) if after else None
    if not last:
        return None
    return cadence_next(run_day(parse_run_time(last)), t.get("cadence"))


def schedule_counts_from(t, sched):
    """The instant a scheduled task's next time is counted (strictly) from:
    its last_run, or for a task never run just before the start of its
    created day, so that day's first scheduled time counts. None = due now.
    A bare last_run date is the end of that day in the schedule's timezone,
    a created date its start."""
    last = (t.get("last_run") or "").strip()
    created = (t.get("created") or "").strip()
    if not (last or created):
        return None
    ran = parse_run_time(last or created)
    if isinstance(ran, datetime.datetime):
        return ran
    start = ran + datetime.timedelta(days=1) if last else ran
    return (datetime.datetime.combine(start, datetime.time(),
                                      tzinfo=sched["tz"])
            - datetime.timedelta(microseconds=1))


# Schedulers fire triggers early (a noon trigger around 11:06), so each
# scheduled time has an early window: routine wake hands a task out inside
# it, and a run recorded inside it covers that time (`slot_covered`). The
# window is capped at half the gap from the scheduled time before, so a run
# covers the nearer time and a short schedule never skips one. Cadence tasks
# and a pinned next_due have no window.
SCHEDULE_EARLY = datetime.timedelta(hours=3)


def in_early_window(sched, slot, when):
    """Whether instant `when` falls in scheduled time `slot`'s early window:
    before it by at most SCHEDULE_EARLY, and nearer to it than to the
    scheduled time before it (no time in [when - lead, slot)). Pure."""
    utc = datetime.timezone.utc
    slot, when = slot.astimezone(utc), when.astimezone(utc)
    lead = slot - when
    if not datetime.timedelta(0) < lead <= SCHEDULE_EARLY:
        return False
    first = cron_next(sched, when - lead - datetime.timedelta(microseconds=1))
    return first is not None and first.astimezone(utc) == slot


def cron_prev(sched, at):
    """Latest scheduled time at or before `at` (aware), in the schedule's
    timezone, or None if there is none within CRON_HORIZON_DAYS."""
    tz, utc = sched["tz"], datetime.timezone.utc
    at = at.astimezone(utc)
    day = at.astimezone(tz).date()
    for _ in range(CRON_HORIZON_DAYS):
        if _cron_day(sched, day):
            hits = [datetime.datetime(day.year, day.month, day.day, h, m,
                                      tzinfo=tz).astimezone(utc)
                    for h in sched["hour"] for m in sched["minute"]]
            hits = [h for h in hits if h <= at]
            if hits:
                return max(hits).astimezone(tz)
        day -= datetime.timedelta(days=1)
    return None


def slot_covered(sched, when):
    """The scheduled time a run recorded at `when` covers: the next one when
    `when` is in its early window, else the latest at or before `when` (a
    catch-up run before today's window covers yesterday's). Falls back to `when`
    when the schedule has no such time. Pure."""
    nxt = cron_next(sched, when)
    if nxt is not None and in_early_window(sched, nxt, when):
        return nxt
    return cron_prev(sched, when) or when


def run_stamp(meta, ran):
    """The last_run a run recorded at `ran` (date or aware datetime) leaves:
    on a scheduled task, the scheduled time it covered, so the next due is
    the time after it; otherwise (a cadence task, or a bare date, which has
    no time of day to judge) the run time itself."""
    schedule = (meta.get("schedule") or "").strip()
    if schedule and isinstance(ran, datetime.datetime):
        ran = slot_covered(parse_schedule(schedule), ran)
    return format_run_time(ran)


def last_run_label(meta):
    """last_run as shown to a reader: on a scheduled task it is the scheduled
    time the run covered, not when it ran, so it is labelled that way."""
    last = (meta.get("last_run") or "").strip()
    schedule = (meta.get("schedule") or "").strip()
    if schedule and "T" in last:
        slot = parse_run_time(last).astimezone(parse_schedule(schedule)["tz"])
        return f"covered the {format_due(slot)} run"
    return f"last run {last}"


def task_is_due(t, now=None, early=False):
    """Due now (or at `now`, a date or aware datetime). `early` (routine
    wake only) also counts a scheduled time's early window as due."""
    if not on_the_clock(t):
        return False
    due = task_due_date(t)
    now = due_instant(now) if now else datetime.datetime.now().astimezone()
    if due is None or due_instant(due) <= now:
        return True
    # Only a schedule derives a datetime due; next_due is a date.
    return (early and isinstance(due, datetime.datetime)
            and in_early_window(parse_schedule(t["schedule"]), due, now))


def recur_sort_rank(t):
    """Tiebreak within one status: due first, armed-but-not-due last.

    A separate component of the sort key from the status rank on purpose —
    umbrella status ranking (T94) can change that component without
    disturbing this one. Recurring tasks are never umbrellas.
    """
    if not is_recurring(t):
        return 0
    return -1 if task_is_due(t) else 1


# A recurring task is "at rest" between runs: approved, nothing in flight, so
# it is not unfinished work. Any other status means a run is under way, the
# task was retired, or it is still awaiting approval (proposed) — status wins
# over recurrence there, or an unapproved proposal would reseed as backlog.
RECUR_RESTING = ("backlog", "planned")


def recur_at_rest(t):
    return is_recurring(t) and t["status"] in RECUR_RESTING


def is_rehearsal(t):
    return (t.get("rehearsal") or "").strip() == "true"


def validate_rehearsal(meta):
    """A rehearsal is a one-off ops task (ran --rehearsal refuses a recurring
    one). Exits on error."""
    if not is_rehearsal(meta):
        return
    if not is_ops(meta):
        sys.exit(f"error: a rehearsal is an ops task; T{meta['id']} would be "
                 f"{task_type(meta)}")
    if is_recurring(meta):
        sys.exit(f"error: a rehearsal is a one-off task on its flow; "
                 f"T{meta['id']} would be recurring")


def is_distill(t):
    return (t.get("distill") or "").strip() == "true"


def validate_distill(meta):
    """A distill sitting is an ops task. Exits on error."""
    if is_distill(meta) and not is_ops(meta):
        sys.exit(f"error: a distill sitting is an ops task; T{meta['id']} "
                 f"would be {task_type(meta)}")


def rehearsal_clash_refusal(meta, tasks):
    """Refusal message when this doing ops task and another doing ops task
    share a flow id with opposite rehearsal markers, else ''. A real run
    must not race a flow still being tested and edited, and a rehearsal
    must not start under a live run. Matched on the id, so a renamed flow
    cannot slip past.
    """
    if not (is_ops(meta) and meta.get("status") == "doing"):
        return ""
    mine = {fid for fid, _ in parse_flow_refs(meta.get("flow"))}
    for t in tasks:
        if (t["id"] == meta["id"] or not is_ops(t)
                or t.get("status") != "doing"
                or is_rehearsal(t) == is_rehearsal(meta)):
            continue
        for fid, name in parse_flow_refs(t.get("flow")):
            if fid not in mine:
                continue
            if is_rehearsal(t):
                return (f"error: flow {fid} {name} is being rehearsed in "
                        f"T{t['id']}; finish or close that rehearsal before "
                        f"T{meta['id']} runs it (/ops rehearse {name} "
                        f"resumes it)")
            return (f"error: flow {fid} {name} has a real run in flight "
                    f"(T{t['id']}); finish it before rehearsing that flow "
                    f"in T{meta['id']}")
    return ""


def validate_recurring(meta):
    """kind and its clock (cadence or schedule, exactly one) must agree;
    last_run is a date or timestamp, next_due a date. Exits on error."""
    cadence = (meta.get("cadence") or "").strip()
    schedule = (meta.get("schedule") or "").strip()
    if is_recurring(meta):
        if cadence and schedule:
            sys.exit(f"error: a {RECURRING} task has a cadence or a schedule, "
                     "not both; clear one (--cadence \"\" or --schedule \"\")")
        if not (cadence or schedule):
            sys.exit(f"error: kind {RECURRING} requires --cadence <N><unit> "
                     "(e.g. 2w, 1m) or --schedule \"<cron> <timezone>\"")
        if cadence:
            parse_cadence(cadence)
        elif cron_next(parse_schedule(schedule),
                       datetime.datetime.now().astimezone()) is None:
            sys.exit(f"error: schedule '{schedule}' never fires")
    elif cadence or schedule:
        field = "cadence" if cadence else "schedule"
        sys.exit(f"error: {field} only applies to kind {RECURRING} tasks")
    for field in ("last_run", "next_due"):
        value = (meta.get(field) or "").strip()
        if value:
            if not is_recurring(meta):
                sys.exit(f"error: {field} only applies to kind {RECURRING} "
                         "tasks")
            if field == "last_run":
                parse_run_time(value, field)
            else:
                parse_iso_date(value, field)


def rearm_recurring(root, scope, branch, bw, meta, ran_on=None, record=None):
    """Record a run: stamp last_run and re-arm instead of going terminal.

    Callers pass a freshly read record. `ran_on` is a date or an aware
    datetime (default: now, stamped to the minute with its offset; a
    scheduled task stamps the time it covered, `run_stamp`). Clears
    the per-run fields (assignee, branch, pr) and any next_due override (it
    governed this run) so the next cycle starts clean; the run itself is
    recorded in the body — a bare `Ran (<date>).` for a landed or `recur
    ran` run (the Shipped record already says what happened), or the full
    `Ran (<date>): …` line an ops run passes in.
    """
    ran = ran_on or datetime.datetime.now().astimezone()
    day = run_day(ran).isoformat()
    meta["last_run"] = run_stamp(meta, ran)
    meta["next_due"] = ""
    meta["status"] = "backlog"
    meta["assignee"] = meta["branch"] = meta["pr"] = ""
    meta["body"] = append_body(meta["body"], record or f"Ran ({day}).")
    with open(meta["path"], "w", newline="\n") as f:
        f.write(render_task(meta))
    board_commit(root, branch, bw, scope,
                 f"dev: T{meta['id']} ran {day} (re-armed)")
    return meta


def membership_leaves(umbrella, by_id, _seen=None):
    """Leaf tasks under an umbrella via membership edges only.

    An umbrella's deps are direct children. A child that is itself an
    umbrella contributes its leaves recursively; a non-umbrella child is a
    leaf (its own deps are ordering, not membership). Nested-ready without
    a separate parent field.
    """
    if _seen is None:
        _seen = set()
    leaves = []
    for d in umbrella.get("deps", []):
        if d in _seen:
            continue
        _seen.add(d)
        child = by_id.get(d)
        if not child:
            continue
        if is_umbrella(child):
            leaves.extend(membership_leaves(child, by_id, _seen))
        else:
            leaves.append(child)
    return leaves


def umbrella_rollup(umbrella, tasks):
    """Short status rollup over membership leaves (not ordering-only deps).

    shelved and not-planned leaves are out of scope: excluded from
    both the done numerator and the denominator, and omitted from open
    status counts.
    """
    by_id = {t["id"]: t for t in tasks}
    leaves = membership_leaves(umbrella, by_id)
    # Progress is over work still in play — drop shelved / not-planned.
    active = [t for t in leaves if t["status"] not in OUT_OF_PLAY]
    if not active:
        if leaves:
            parked = {t["status"] for t in leaves if t["status"] in OUT_OF_PLAY}
            return "☂ all " + "/".join(s for s in OUT_OF_PLAY if s in parked)
        return "☂ no children"
    n = len(active)
    done = sum(1 for t in active if t["status"] == "done")
    blocked = 0
    for t in active:
        if t["status"] in TERMINAL or t["status"] in OPEN_PR:
            continue
        if any(by_id.get(d, {}).get("status") != "done" for d in t.get("deps", [])):
            blocked += 1
    # Compact status counts for non-done active leaves (omit zeros).
    counts = {}
    for t in active:
        if t["status"] == "done":
            continue
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    order = [s for s in STATUSES if s != "done" and s not in OUT_OF_PLAY]
    parts = [f"☂ {done}/{n} done"]
    for s in order:
        if counts.get(s):
            parts.append(f"{counts[s]} {s}")
    if blocked:
        parts.append(f"{blocked} blocked")
    return " · ".join(parts)


def task_glob(bw, scope):
    return glob.glob(os.path.join(bw, tdir(scope), "[0-9][0-9][0-9].md"))


def all_tasks(bw, scope):
    tasks = sorted((parse_task(p) for p in task_glob(bw, scope)),
                   key=lambda t: t["id"])
    if any(t["routine"] for t in tasks):
        note_routine_stalls(tasks, all_registry(bw, scope, "routine"))
    return tasks


def find_task(bw, scope, tid):
    p = os.path.join(bw, tdir(scope), f"{int(tid):03d}.md")
    if not os.path.exists(p):
        sys.exit(f"error: no task with id {tid}")
    return parse_task(p)


def split_areas(s):
    return [a.strip() for a in s.split(",") if a.strip()]


def occupies_area(t):
    return t["status"] not in ("done", "shelved", "not-planned")


# Shipped, not yet landed: there is an open PR either way. `draft` adds
# "the author is not asking for review yet" — the board owns that state,
# and the PR's draft bit mirrors it where GitHub supports one.
OPEN_PR = ("draft", "review")
# The in-flight set implement negotiates over / unattended runs skip.
IN_FLIGHT = ("doing",) + OPEN_PR


def areas_overlap(a, b):
    """Segment-prefix overlap (SKILL Area stewardship).

    Split on `/`. `routes` overlaps `routes/implement`; `routes/implement` does
    not overlap `routes/review`. String prefix is the trap (`route` vs `routes`).
    Reserved `all` overlaps every name.
    """
    if a == "all" or b == "all":
        return True
    sa = [p for p in a.split("/") if p]
    sb = [p for p in b.split("/") if p]
    n = min(len(sa), len(sb))
    return bool(n) and sa[:n] == sb[:n]


def task_areas_overlap(a_areas, b_areas):
    """True if any area on one overlaps any on the other.

    Reserved `all` on either side overlaps every task, including untagged.
    """
    if "all" in a_areas or "all" in b_areas:
        return True
    return any(areas_overlap(x, y) for x in a_areas for y in b_areas)


def in_flight_area_collisions(task, tasks, exclude_ids=None):
    """In-flight tasks whose areas overlap `task`, excluding itself.

    ``exclude_ids`` drops extra ids from the scan (batch peers — they are
    sequential, not outside occupancy).
    """
    skip = {task["id"]}
    if exclude_ids:
        skip.update(exclude_ids)
    mine = split_areas(task.get("area", ""))
    hits = []
    for other in tasks:
        if other["id"] in skip:
            continue
        if other.get("status") not in IN_FLIGHT:
            continue
        if task_areas_overlap(mine, split_areas(other.get("area", ""))):
            hits.append(other)
    return hits


def set_area_overlaps(ids, tasks):
    """Pairs among ``ids`` whose areas overlap, regardless of status."""
    by_id = {t["id"]: t for t in tasks}
    seen = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    pairs = []
    for i, a in enumerate(seen):
        ta = by_id.get(a)
        if ta is None:
            continue
        aa = split_areas(ta.get("area", ""))
        for b in seen[i + 1:]:
            tb = by_id.get(b)
            if tb is None:
                continue
            if task_areas_overlap(aa, split_areas(tb.get("area", ""))):
                pairs.append((ta, tb))
    return pairs


def _task_head(task, color=False):
    label = task.get("area") or ("(ops)" if is_ops(task) else "(untagged)")
    tid = f"T{task['id']}"
    return (f"{_status_ansi(task['status'], tid)} {_ansi(_DIM, label)}"
            if color else f"{tid} {label}")


def format_area_collisions(task, blockers, color=False):
    head = _task_head(task, color=color)
    if not blockers:
        clear = _ansi(_OK, "clear") if color else "clear"
        return f"{head} — {clear}"
    bits = []
    for o in blockers:
        oa = o.get("area") or "(untagged)"
        oid, st = f"T{o['id']}", o["status"]
        if color:
            bits.append(f"{_status_ansi(st, oid)} {_status_ansi(st, st)} ({oa})")
        else:
            bits.append(f"{oid} {st} ({oa})")
    blocked = _ansi(_ERR, "blocked") if color else "blocked"
    return f"{head} — {blocked}: {', '.join(bits)}"


def unfinished_deps(task, tasks):
    """Direct deps whose status is not done. Missing ids count as unfinished."""
    by_id = {t["id"]: t for t in tasks}
    hits = []
    for d in task.get("deps") or []:
        other = by_id.get(d)
        if other is None or other.get("status") != "done":
            hits.append(other if other is not None else {
                "id": d, "status": "missing"})
    return hits


def format_unfinished_deps(blockers, color=False):
    bits = []
    for o in blockers:
        oid, st = f"T{o['id']}", o["status"]
        if color:
            bits.append(f"{_status_ansi(st, oid)} {_status_ansi(st, st)}")
        else:
            bits.append(f"{oid} {st}")
    blocked = _ansi(_ERR, "blocked") if color else "blocked"
    return f"deps {blocked}: {', '.join(bits)}"


def watch_missing_tid(tid, color=False):
    msg = f"T{tid} — no such task"
    return _ansi(_ERR, msg) if color else msg


def watch_check_line(tid, tasks, color=False):
    """Watch-mode c: occupancy plus unfinished deps.

    Only blocked sides print; both clear → one 'clear'.
    Not cmd_collisions — that stays the implement gate (exit 2/3).
    """
    task = next((t for t in tasks if t["id"] == tid), None)
    if task is None:
        return watch_missing_tid(tid, color=color)
    return _check_line(task, tasks, color=color)


def _check_line(task, tasks, group=(), color=False):
    """One task's check against the board, ignoring ``group`` peers."""
    occ_hits = in_flight_area_collisions(task, tasks, exclude_ids=group)
    dep_hits = [o for o in unfinished_deps(task, tasks)
                if o["id"] not in group]
    if not dep_hits:
        return format_area_collisions(task, occ_hits, color=color)
    deps = format_unfinished_deps(dep_hits, color=color)
    if not occ_hits:
        return f"{_task_head(task, color=color)} — {deps}"
    occ = format_area_collisions(task, occ_hits, color=color)
    return f"{occ} · {deps}"


def watch_group_check_lines(ids, tasks, color=False):
    """Watch-mode c with several ids: outside the group, then within it.

    Outside: each member as the single-id check, peers ignored. Within:
    area overlap and unfinished deps between members — both rule out
    running in parallel, but only order a batch (a dep cycle blocks it).
    No batch order is suggested: deps already name the forced ones.
    A TERMINAL member is not going to start, so it is listed by status
    and left out of every other check.
    """
    by_id = {t["id"]: t for t in tasks}
    missing = [i for i in ids if i not in by_id]
    if missing:
        return [watch_missing_tid(i, color=color) for i in missing]
    live = [i for i in ids if by_id[i].get("status") not in TERMINAL]
    group = set(live)
    lines = ["outside group:"]
    for i in ids:
        if i in group:
            line = _check_line(by_id[i], tasks, group=group, color=color)
        else:
            st = by_id[i]["status"]
            line = (f"{_task_head(by_id[i], color=color)} — "
                    f"{_status_ansi(st, st) if color else st}")
        lines.append("  " + line)
    if len(live) < 2:
        return lines
    reasons, cycle = group_verdicts(live, tasks)
    ok = _ansi(_OK, "ok") if color else "ok"
    no = _ansi(_ERR, "no") if color else "no"
    lines.append("within group:")
    lines.append("  " + parallel_line(reasons, color=color))
    if cycle:
        cycle = ", ".join(f"T{i}" for i in cycle)
        lines.append(f"  batch: {no} — dep cycle; cannot order {cycle}")
    else:
        lines.append(f"  batch: {ok}")
    return lines


def group_verdicts(ids, tasks):
    """Within-group checks among live members ``ids``.

    Returns (reasons parallel is ruled out — area overlap or a dep between
    members, ids a dep cycle leaves unordered). Shared by watch-mode c and
    multi-id ``collisions``, so both give the same parallel verdict.
    """
    by_id = {t["id"]: t for t in tasks}
    group = set(ids)
    reasons = [f"T{a['id']} and T{b['id']} share areas"
               for a, b in set_area_overlaps(ids, tasks)]
    needs = {i: [o["id"] for o in unfinished_deps(by_id[i], tasks)
                 if o["id"] in group] for i in ids}
    reasons += [f"T{i} needs T{d}" for i in ids for d in needs[i]]
    done, left = set(), set(ids)
    while left:
        ready = {i for i in left if all(d in done for d in needs[i])}
        if not ready:
            break
        done |= ready
        left -= ready
    return reasons, [i for i in ids if i in left]


def parallel_line(reasons, color=False):
    if not reasons:
        return f"parallel: {_ansi(_OK, 'ok') if color else 'ok'}"
    no = _ansi(_ERR, "no") if color else "no"
    return f"parallel: {no} — {'; '.join(reasons)}"


def watch_task_view(tid, tasks, entries=()):
    """Frontmatter + body for the live viewer, or None if missing, its
    catalog references resolved against `entries`."""
    task = next((t for t in tasks if t["id"] == tid), None)
    if task is None:
        return None
    return resolve_catalog_text(render_task(task).rstrip(), entries)[0]


def watch_search_view(query, tasks, expand=False, color=False):
    """Watch-mode s: tasks ranked as `related` ranks them.

    A full pane, not a footer — the board rarely leaves room for one.
    Like the board, TERMINAL tasks are left out unless expanded (e); when
    shown they are dimmed, not reordered — ties keep id order.
    """
    lines = [f"# Search: {query}", ""]
    pool = [t for t in tasks if expand or t["status"] not in TERMINAL]
    hits = related_hits(query, pool)
    if not hits:
        lines.append("(nothing related)" if expand else
                     "(nothing related; e includes "
                     "done/shelved/not-planned)")
    for score, t in hits:
        if color and t["status"] in TERMINAL:
            lines.append(_ansi(_DIM, f"{score:.2f} {fmt_line(t, tasks)}"))
        else:
            lines.append(f"{score:.2f} {fmt_line(t, tasks, color=color)}")
    return "\n".join(lines)


def flows_pane_text(bw, scope, color=False):
    """Watch-mode f: the playbook index, one line per flow."""
    flows = all_flows(bw, scope)
    title = "# Flows"
    if scope != ".":
        title += f" ({scope})"
    lines = [title, ""]
    if not flows:
        lines.append("(no flows yet)")
        return "\n".join(lines)
    active = [f for f in flows if flow_is_active(f)]
    retired = [f for f in flows if not flow_is_active(f)]
    width = max(len(f["name"]) for f in flows)
    for group, head in ((active, None), (retired, "Retired")):
        if not group:
            continue
        if head:
            lines.extend(["", _ansi(_DIM, head) if color else head])
        for f in group:
            fid = f"{f['id']:>3}"
            name = f["name"].ljust(width)
            if color:
                fid = _ansi(_DIM, fid)
                name = _ansi(_FLOW_NAME if head is None else _DIM, name)
            line = f"{fid}  {name}  {f.get('description', '')}".rstrip()
            uses = split_names(f.get("uses"))
            if uses:
                tail = f"uses {', '.join(uses)}"
                line += f"  \u00b7 {_ansi(_DIM, tail) if color else tail}"
            lines.append(line)
    return "\n".join(lines)


REGISTRY_PANE_HEADS = {"agent": "Agents", "env": "Environments",
                       "routine": "Routines"}


def registries_pane(bw, scope, color=False):
    """Watch-mode g: agents, environments and routines, one line each.

    Returns (text, rows); rows[n - 1] is the (kind, name) that row n opens.
    Registries have no ids: the numbers only point at rows of this view,
    so they are written `n)` and run on across the three sections.
    """
    title = "# Registries"
    if scope != ".":
        title += f" ({scope})"
    note = "Numbers are references for this view, not ids."
    lines = [title, _ansi(_DIM, note) if color else note]
    rows = []
    for kind, head in REGISTRY_PANE_HEADS.items():
        lines.extend(["", head])
        entries = all_registry(bw, scope, kind)
        if not entries:
            none = f"(no {REGISTRIES[kind]['label']}s)"
            lines.append(_ansi(_DIM, none) if color else none)
        for e in entries:
            rows.append((kind, e["name"]))
            ref = f"{len(rows):>2})"
            line = registry_line(e)
            if color:
                ref = _ansi(_DIM, ref)
                line = _ansi(_FLOW_NAME, e["name"]) + line[len(e["name"]):]
            lines.append(f"{ref} {line}")
    return "\n".join(lines), rows


def watch_registry_view(bw, scope, kind, name, tasks=()):
    """One registry entry's file, titled by its name, or None if gone.

    A renamed entry is still found (its former name resolves). A routine
    also lists the tasks pointing at it.
    """
    entries = all_registry(bw, scope, kind)
    e = registry_holder(entries, name)
    if e is None:
        return None
    with open(e["path"]) as fh:
        text = fh.read().rstrip()
    text = resolve_catalog_text(text, catalog_entries(bw, scope))[0]
    page = f"# {REGISTRIES[kind]['label']} {e['name']}\n\n{text}"
    mine = routine_tasks(tasks, entries, e) if kind == "routine" else []
    if mine:
        page += "\n\ntasks: " + ", ".join(f"T{t['id']}" for t in mine)
    return page


def watch_flow_search_view(query, flows, color=False):
    """Flows-pane s: flows ranked as `related` ranks tasks.

    Name, description and procedure all count. Retired flows are listed
    (the index lists them too), tagged — dimming alone is lost without
    color — and dimmed.
    """
    lines = [f"# Flow search: {query}", ""]
    hits = related_hits(query, flows, fields=("name", "description", "body"))
    if not hits:
        lines.append("(nothing related)")
    for score, f in hits:
        tag = "" if flow_is_active(f) else " (retired)"
        line = (f"{score:.2f} {f['id']:>3}  {f['name']}{tag}  "
                f"{f.get('description', '')}").rstrip()
        if color and not flow_is_active(f):
            line = _ansi(_DIM, line)
        lines.append(line)
    return "\n".join(lines)


def watch_flow_view(bw, scope, fid):
    """One flow's file plus its run history, or None if no such id.

    Returns (page, line where the run history starts) — h scrolls there.
    """
    flow = next((f for f in all_flows(bw, scope) if f["id"] == fid), None)
    if flow is None:
        return None
    try:
        with open(flow["path"]) as fh:
            text = fh.read().rstrip()
    except OSError:
        text = render_flow(flow).rstrip()
    text = resolve_catalog_text(text, catalog_entries(bw, scope),
                                skip=flow_input_names(flow["inputs"]))[0]
    runs = flow_runs_text(bw, scope, flow, color=_use_color())
    return f"{text}\n\n{runs}", len(text.splitlines()) + 1


def watch_missing_reg(kind, name, color=False):
    msg = f"{REGISTRIES[kind]['label']} {name} — no longer there"
    return _ansi(_ERR, msg) if color else msg


def watch_missing_fid(fid, color=False):
    msg = f"flow {fid} — no such flow"
    return _ansi(_ERR, msg) if color else msg


def parse_watch_fid(buf):
    """Digits only. In the flows pane a number is a flow id, not a task."""
    s = buf.strip()
    return int(s) if s.isdigit() else None


def parse_watch_tid(buf):
    """Digits, optional leading t/T. None if not an id."""
    s = buf.strip()
    if s[:1] in "tT":
        s = s[1:]
    if not s.isdigit():
        return None
    return int(s)


def parse_watch_ids(buf):
    """Comma-separated ids for a check, in typed order. None if any is bad."""
    ids = []
    for part in buf.split(","):
        tid = parse_watch_tid(part)
        if tid is None:
            return None
        if tid not in ids:
            ids.append(tid)
    return ids


def watch_check_result(ids, tasks, color=False):
    """The c result: one line for one id, the group check for several."""
    if len(ids) == 1:
        return watch_check_line(ids[0], tasks, color=color)
    return "\n".join(watch_group_check_lines(ids, tasks, color=color))


def append_body(body, text):
    body = (body or "").strip()
    text = text.strip()
    return (body + "\n\n" + text).strip() if body else text


def slugify(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:40].rstrip("-") or "task"


def parse_positive_int(value, what="value"):
    raw = str(value if value is not None else "").strip()
    if not raw.isdigit() or int(raw) < 1:
        sys.exit(f"error: {what} must be a positive integer (got {value!r})")
    return int(raw)


def iso_date(value, what="date"):
    """Validated YYYY-MM-DD as a date object (parse_iso_date returns the str)."""
    return datetime.date.fromisoformat(parse_iso_date(value, what))


def parse_iso_date(value, what="date"):
    raw = (value or "").strip()
    try:
        datetime.date.fromisoformat(raw)
    except ValueError:
        sys.exit(f"error: {what} must be YYYY-MM-DD (got {value!r})")
    return raw


def iteration_index(cfg):
    """Live iteration identity. Fail closed if board.yml is pre-schema-3."""
    return parse_positive_int(cfg.get("iteration"), "board.yml iteration")


def iteration_name(cfg):
    return (cfg.get("iteration_name") or "").strip()


def iteration_started(cfg):
    return (cfg.get("iteration_started") or "").strip()


def iteration_label(cfg):
    """Human-facing '1' or '1 — MVP'."""
    idx = iteration_index(cfg)
    name = iteration_name(cfg)
    return f"{idx} — {name}" if name else str(idx)


def title_prefix(idx, tid, scope="."):
    """PR title / ship commit tag: '[n/T<id>]', or '[<scope> n/T<id>]' on a
    scoped board so tasks from boards sharing one repo stay distinguishable
    (same reason board commits carry their scope — scoped_message)."""
    ref = f"{int(idx)}/T{int(tid)}"
    return f"[{ref}]" if scope == "." else f"[{scope} {ref}]"


def with_title_prefix(text, prefix, tid):
    """Lead `text` with `prefix`, replacing a leading tag for this same task
    from another iteration or scope (`[1/T42] …` on a `[devops 3/T42]`
    board) rather than stacking a second one in front of it. A tag naming
    a different task id is left alone and gets the prefix in front."""
    m = re.match(r"\[[^\[\]]*?\bT(\d+)\]\s*", text)
    if m and int(m.group(1)) == int(tid):
        text = text[m.end():]
    return text if text.startswith(prefix) else f"{prefix} {text}"


# Schema-3 dirs are `{n}` or `{n}-{slug}`. Pre-3 leftovers are
# `YYYY-MM-DD` or `YYYY-MM-DD-slug` — those must not parse as year N.
ARCHIVE_INDEX_RE = re.compile(r"^(\d+)(?:-.*)?$")
PRE3_ARCHIVE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:-.*)?$")


def archive_dir_index(ent):
    """Integer index from a schema-3 archive dir name, or None."""
    if PRE3_ARCHIVE_RE.match(ent):
        return None
    m = ARCHIVE_INDEX_RE.match(ent)
    return int(m.group(1)) if m else None


def iteration_archive_slug(index, name=""):
    """Directory name: '{n}-{slug}' or '{n}' when unnamed."""
    name = (name or "").strip()
    slug = slugify(name) if name else ""
    return f"{int(index)}-{slug}" if slug else str(int(index))


def require_schema3_archive_slug(index, name="", what="iteration"):
    """Fail closed if {n}-{slug} would look like a pre-3 date dir.

    Those names are invisible to archive_dir_index, so a year-like index
    plus an MM-DD display name would skip clash detection and overwrite.
    """
    slug = iteration_archive_slug(index, name)
    if PRE3_ARCHIVE_RE.match(slug):
        shown = (name or "").strip() or "(none)"
        sys.exit(f"error: {what} {int(index)} name {shown!r} would archive "
                 f"as {slug!r}, which looks like a pre-schema-3 date dir "
                 "and would be invisible to the index scan. Pick a "
                 "different number or display name.")
    return slug


def iteration_close_heading(index, name=""):
    name = (name or "").strip()
    return f"## {int(index)} — {name}" if name else f"## {int(index)}"


def log_has_close_section(text, index):
    """True if log.md has a close heading for this index ('## N' or '## N — …').

    Must not treat '## 1' as a match for 10.
    """
    return re.search(rf"(?m)^## {int(index)}(?: — |$)", text) is not None


def default_task_branch(scope, tid, title):
    """Branch name for a task: dev/<id>-<slug> or dev/<scope>-<id>-<slug>."""
    slug = slugify(title)
    if scope in (".", ""):
        return f"dev/{int(tid)}-{slug}"
    scope_slug = scope.replace("/", "-").replace("\\", "-")
    return f"dev/{scope_slug}-{int(tid)}-{slug}"


def recurring_run_branch(base, day, taken):
    """A recurring task's branch for one run: <base>-<YYYY-MM-DD>, then -2,
    -3… while `taken` (existing branch names) holds it. Each run gets its
    own name, so a leftover from an earlier run is never picked up."""
    name = f"{base}-{day.isoformat()}"
    n = 1
    while (f"{name}-{n}" if n > 1 else name) in taken:
        n += 1
    return f"{name}-{n}" if n > 1 else name


def current_branch_name(cwd):
    r = git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd, check=False)
    if r.returncode != 0:
        return ""
    return (r.stdout or "").strip()


def task_worktree_path(root, scope, tid, title):
    """Canonical path for a task worktree under product .dev/worktrees/."""
    name = f"{int(tid)}-{slugify(title)}"
    return os.path.join(product_root(root, scope), ".dev", "worktrees", name)


def ff_task_branch(root, branch, start_ref):
    """Fast-forward `branch` to start_ref. Caller must have checked ancestry."""
    checkout = branch_checkout_cwd(root, branch)
    if checkout:
        if worktree_is_dirty(checkout):
            sys.exit(f"error: task branch '{branch}' is behind {start_ref} "
                     f"but worktree is dirty; commit/stash or reset first:"
                     f"\n{checkout}")
        r = git("merge", "--ff-only", start_ref, cwd=checkout, check=False)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            sys.exit(f"error: could not fast-forward '{branch}' to "
                     f"{start_ref}:\n{err}")
    else:
        r = git("branch", "-f", branch, start_ref, cwd=root, check=False)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            sys.exit(f"error: could not fast-forward '{branch}' to "
                     f"{start_ref}:\n{err}")
    print(f"note: fast-forwarded leftover '{branch}' to {start_ref}")


def adopt_pushed_task_branch(root, branch):
    """Resume of a recorded branch: fetch it, and fast-forward a stale local
    copy to it. Work pushed elsewhere (a parked run, another machine) is
    otherwise invisible to ensure_task_branch, which would build on a stale
    local branch or cut a fresh one from integration. A local branch ahead
    of or diverged from origin is left alone: it holds unpushed work."""
    git("fetch", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
        cwd=root, check=False)
    remote = f"origin/{branch}"
    if not (ref_exists(root, remote) and ref_exists(root, f"refs/heads/{branch}")):
        return
    if (is_ancestor(root, branch, remote)
            and not is_ancestor(root, remote, branch)):
        ff_task_branch(root, branch, remote)


def ensure_task_branch(root, branch, start_ref, resume=False):
    """Create local task branch from start_ref if missing; no checkout.

    An existing branch is reused only when start_ref is already an ancestor
    of its tip (at or ahead of the intended base). An empty leftover (the
    branch is a strict ancestor of start_ref) is fast-forwarded. A leftover
    that has diverged is an error — recovery is in routes/implement.md
    (show unique commits and leftover dirty status, ask keep vs throw;
    do not write branch: first; keep: commit/stash if dirty; refuse
    throw-away while dirty; throw-away: TASKS pr <id> close then delete).
    `resume` (the task's own recorded branch) keeps a diverged branch as it
    is: integration moves with every board commit, so a branch with work on
    it has always diverged by the time anyone resumes it; ship and land
    absorb that with a merge, never a rebase here.
    """
    if not ref_exists(root, start_ref):
        sys.exit(f"error: start ref '{start_ref}' not found; fetch origin first")

    if not ref_exists(root, f"refs/heads/{branch}"):
        if ref_exists(root, f"origin/{branch}"):
            git("branch", "--track", branch, f"origin/{branch}", cwd=root,
                check=False)
            if not ref_exists(root, f"refs/heads/{branch}"):
                git("branch", branch, f"origin/{branch}", cwd=root)
        else:
            git("branch", branch, start_ref, cwd=root)
            return

    if is_ancestor(root, start_ref, branch):
        return
    if is_ancestor(root, branch, start_ref):
        ff_task_branch(root, branch, start_ref)
        return
    if resume:
        return
    ahead = git("rev-list", "--count", f"{start_ref}..{branch}",
                cwd=root, check=False).stdout.strip() or "?"
    behind = git("rev-list", "--count", f"{branch}..{start_ref}",
                 cwd=root, check=False).stdout.strip() or "?"
    sys.exit(f"error: task branch '{branch}' has diverged from {start_ref} "
             f"({ahead} unique, {behind} behind); show unique commits and "
             f"leftover dirty status and ask keep vs throw before writing "
             f"branch: (routes/implement.md)")


def verified_claim_base(root, branch, start_ref, resume=False):
    """start_ref if it is an ancestor of branch; else refuse to name a base.
    A resumed branch that has diverged reports where it forked instead."""
    if not is_ancestor(root, start_ref, branch) and resume:
        fork = git("merge-base", start_ref, branch, cwd=root,
                   check=False).stdout.strip()
        if fork:
            return f"{fork[:12]} (resumed; {start_ref} has moved on)"
    if not is_ancestor(root, start_ref, branch):
        sys.exit(f"error: task branch '{branch}' is not based on {start_ref}; "
                 f"refusing to report an unverified base")
    return start_ref


def free_task_branch_from_primary(root, branch, integration):
    """If primary has `branch` checked out, move it to integration (hub).

    Required before `git worktree add` can attach the same branch elsewhere.
    Refuses when primary is dirty so we never discard uncommitted work.
    """
    checkout = branch_checkout_cwd(root, branch)
    if not checkout:
        return
    if not same_path(checkout, root):
        return  # already on a linked worktree — caller reuses it
    if worktree_is_dirty(root):
        sys.exit(f"error: primary clone is on task branch '{branch}' and dirty; "
                 f"commit/stash or move primary to '{integration}' before claim")
    r = git("checkout", integration, cwd=root, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        sys.exit(f"error: could not move primary to '{integration}' to free "
                 f"'{branch}' for a task worktree:\n{err}")


def ensure_task_worktree(root, scope, tid, title, branch):
    """Create or reuse the canonical linked worktree for this task branch."""
    wt_path = task_worktree_path(root, scope, tid, title)
    os.makedirs(os.path.dirname(wt_path), exist_ok=True)
    if os.path.exists(wt_path):
        if os.path.exists(os.path.join(wt_path, ".git")):
            git("worktree", "prune", cwd=root, check=False)
            cur = current_branch_name(wt_path)
            if cur == branch:
                return wt_path
            sys.exit(f"error: path exists but is not a live worktree for "
                     f"'{branch}': {wt_path}")
        sys.exit(f"error: task worktree path exists without .git "
                 f"(remove by hand): {wt_path}")
    r = git("worktree", "add", wt_path, branch, cwd=root, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        sys.exit(f"error: git worktree add failed for '{branch}':\n{err}")
    return wt_path


def resolve_task_ready_path(root, scope, tid, title, branch, integration):
    """Return the path where the agent should work — always a linked worktree.

    Policy: task implement work lives under `<scope>/.dev/worktrees/`; the
    primary clone stays on integration as a hub for parallel agents. Never
    checks out the task branch on primary. Idempotent resume reuses an
    existing task worktree for this id/branch.
    """
    root_rp = path_key(root)

    # Resume: existing linked worktree for this task (never primary).
    for path in find_task_worktree_paths(root, scope, tid, branch):
        if path_key(path) == root_rp:
            continue
        if not os.path.isdir(path):
            continue
        if not os.path.exists(os.path.join(path, ".git")):
            continue
        cur = current_branch_name(path)
        if cur != branch:
            if worktree_is_dirty(path):
                sys.exit(f"error: task worktree {path} is dirty and not on "
                         f"'{branch}' (on '{cur}'); commit/stash or remove it")
            r = git("checkout", branch, cwd=path, check=False)
            if r.returncode != 0:
                err = (r.stderr or r.stdout or "").strip()
                sys.exit(f"error: could not checkout '{branch}' in "
                         f"{path}:\n{err}")
        return path

    # Branch already on a non-primary worktree (odd path / renamed title).
    checkout = branch_checkout_cwd(root, branch)
    if checkout and path_key(checkout) != root_rp:
        return checkout

    # Free the branch if a prior claim left it on primary, then always add
    # a linked worktree under .dev/worktrees/.
    free_task_branch_from_primary(root, branch, integration)
    return ensure_task_worktree(root, scope, tid, title, branch)


# ---------- land / cleanup (task PR merge path) ----------

def gh_sign_in_failure(status, api):
    """None when gh counts as signed in, else the detail to show.

    status is the `gh auth status` result, api the `gh api user --jq .login`
    one (None when status passed and it was not run). A working api call
    wins over a failed status: Claude cloud's proxy token is reported
    invalid by `gh auth status` while every API call through it works."""
    if status.returncode == 0:
        return None
    if api is not None and api.returncode == 0 and api.stdout.strip():
        return None
    return (status.stderr or status.stdout or "").strip()


GH_MISSING = "gh is not installed; see https://cli.github.com"


def gh_sign_in_error(root):
    """None when gh is signed in (gh_sign_in_failure), else the detail."""
    if not shutil.which("gh"):
        return GH_MISSING
    status = sh(["gh", "auth", "status"], cwd=root, check=False)
    api = None
    if status.returncode != 0:
        api = sh(["gh", "api", "user", "--jq", ".login"], cwd=root,
                 check=False, timeout=GIT_NETWORK_TIMEOUT_S)
    return gh_sign_in_failure(status, api)


def require_gh(root):
    """Exit unless gh is available and signed in (gh_sign_in_error)."""
    err = gh_sign_in_error(root)
    if err == GH_MISSING:
        sys.exit(f"error: {err}")
    if err is not None:
        sys.exit("error: gh not authenticated. "
                 f"Run: gh auth login\n{err}")


def path_key(path):
    """A path in comparable form: resolved, and case-folded on Windows, where
    git and the shell may spell one path in different cases. Compare paths
    through this, never bare realpath."""
    return os.path.normcase(os.path.realpath(path))


def same_path(a, b):
    return path_key(a) == path_key(b)


def path_is_inside(inner, outer):
    inner = path_key(inner)
    outer = path_key(outer)
    return inner == outer or inner.startswith(outer.rstrip(os.sep) + os.sep)


def list_worktrees(root):
    """Parse `git worktree list --porcelain` into path/branch/head dicts."""
    out = git("worktree", "list", "--porcelain", cwd=root).stdout
    trees, cur = [], {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            if cur:
                trees.append(cur)
            cur = {"path": line.split(" ", 1)[1], "branch": None, "head": None}
        elif line.startswith("HEAD "):
            cur["head"] = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            ref = line.split(" ", 1)[1]
            if ref.startswith("refs/heads/"):
                cur["branch"] = ref[len("refs/heads/"):]
            else:
                cur["branch"] = ref
        elif line == "detached":
            cur["branch"] = None
    if cur:
        trees.append(cur)
    return trees


def parse_version_intent(body):
    """Pull `Version intent: <token>` from a PR body, if present."""
    m = re.search(r"(?im)^\s*Version intent:\s*(\S+)", body or "")
    return m.group(1) if m else None


def version_intent_bump(intent):
    """Real bump token, or None when missing/none (stay silent)."""
    intent = (intent or "").strip()
    if not intent or intent.lower() == "none":
        return None
    return intent


def set_version_intent_in_text(text, intent):
    """Replace, add, or (for none) drop the Version intent line."""
    intent = version_intent_bump(intent)
    text = re.sub(r"(?im)^[ \t]*Version intent:.*(?:\n|\Z)", "",
                  text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    if intent:
        text = text.rstrip() + f"\n\nVersion intent: {intent}\n"
    return text


def task_branch_name(meta, pr_head=None):
    """Prefer board-recorded branch; fall back to PR head ref."""
    b = (meta.get("branch") or "").strip()
    if b:
        return b
    if pr_head:
        return pr_head.strip()
    return ""


def find_task_worktree_paths(root, scope, tid, branch):
    """Local paths that hold this task's checkout (by branch and convention)."""
    found = []
    seen = set()
    if branch:
        for t in list_worktrees(root):
            if t.get("branch") == branch:
                path = t["path"]
                rp = path_key(path)
                if rp not in seen:
                    seen.add(rp)
                    found.append(path)
    wt_dir = os.path.join(product_root(root, scope), ".dev", "worktrees")
    if os.path.isdir(wt_dir):
        prefix = f"{int(tid)}-"
        tid_s = str(int(tid))
        for name in sorted(os.listdir(wt_dir)):
            if name == tid_s or name.startswith(prefix):
                path = os.path.join(wt_dir, name)
                if not os.path.isdir(path):
                    continue
                rp = path_key(path)
                if rp in seen:
                    continue
                # Ids restart each iteration and carried tasks are
                # renumbered, so <id>- can be another task's worktree: one
                # on a different named branch is never this task's to
                # reuse or remove. Mid-rebase the worktree is detached, so
                # its branch is read from the rebase state; a plain detached
                # HEAD names no branch and still matches.
                if branch and os.path.exists(os.path.join(path, ".git")):
                    held = current_branch_name(path)
                    if held == "HEAD":
                        held = rebase_head_branch(path) or "HEAD"
                    if held not in (branch, "HEAD"):
                        continue
                seen.add(rp)
                found.append(path)
    return found


def _git_path(cwd, name):
    """Absolute path from `git rev-parse --git-path name` in `cwd`."""
    if not cwd:
        return ""
    r = git("rev-parse", "--git-path", name, cwd=cwd, check=False)
    path = (r.stdout or "").strip()
    if r.returncode != 0 or not path:
        return ""
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return path


def rebase_head_branch(cwd):
    """Branch being rebased in `cwd`, or None if no in-progress rebase.

    Mid-rebase, `git worktree list` reports the worktree as detached; the
    branch name lives in rebase-merge/head-name (or rebase-apply).
    """
    for name in ("rebase-merge/head-name", "rebase-apply/head-name"):
        path = _git_path(cwd, name)
        if path and os.path.isfile(path):
            raw = open(path).read().strip()
            if raw.startswith("refs/heads/"):
                return raw[len("refs/heads/"):]
            return raw or None
    return None


def rebase_onto_sha(cwd):
    """Commit an in-progress rebase in `cwd` is replaying onto, or None."""
    for name in ("rebase-merge/onto", "rebase-apply/onto"):
        path = _git_path(cwd, name)
        if path and os.path.isfile(path):
            return open(path).read().strip() or None
    return None


def branch_checkout_cwd(root, branch):
    """Worktree path that has `branch` checked out, or None.

    Includes a worktree whose rebase is in progress on `branch` (porcelain
    lists those as detached).
    """
    if not branch:
        return None
    for t in list_worktrees(root):
        path = t.get("path")
        if t.get("branch") == branch:
            return path
        if path and rebase_head_branch(path) == branch:
            return path
    return None


def ensure_local_branch(root, branch, start_ref=None):
    """Create local branch tracking start_ref if missing. No checkout."""
    if not branch:
        return
    if ref_exists(root, f"refs/heads/{branch}"):
        return
    start = start_ref
    if not start:
        if ref_exists(root, f"origin/{branch}"):
            start = f"origin/{branch}"
        else:
            sys.exit(f"error: task branch '{branch}' not found locally or on origin")
    git("branch", "--track", branch, start, cwd=root, check=False)
    if not ref_exists(root, f"refs/heads/{branch}"):
        git("branch", branch, start, cwd=root)


def rebase_in_progress(cwd):
    """True if `cwd` has an unfinished rebase (merge or apply)."""
    if not cwd:
        return False
    for name in ("rebase-merge", "rebase-apply"):
        path = _git_path(cwd, name)
        if path and os.path.isdir(path):
            return True
    return False


def sync_task_branch_from_remote(root, branch, keep_ahead=False):
    """Point local task branch at origin/<branch> when that ref exists.

    Restack and review-attach should start from the PR tip, not a stale
    local ref. Refuses when local is strictly ahead of origin (would
    discard unpushed commits via reset/--force branch move), unless
    keep_ahead: restack keeps rewritten local commits (a rebase rewrites
    SHAs, so the same patches look 'ahead') and the caller force-pushes.
    """
    remote = f"origin/{branch}"
    if not ref_exists(root, remote):
        ensure_local_branch(root, branch, None)
        return
    ensure_local_branch(root, branch, remote)
    ahead = git("rev-list", "--count", f"{remote}..{branch}",
                cwd=root).stdout.strip()
    if ahead not in ("", "0"):
        if keep_ahead:
            return
        sys.exit(f"error: local '{branch}' is {ahead} commit(s) ahead of "
                 f"{remote}; not discarding unpushed commits "
                 f"(reset to {remote} if this leftover is stale)")
    checkout = branch_checkout_cwd(root, branch)
    if checkout:
        dirty = git("status", "--porcelain", cwd=checkout,
                    check=False).stdout.strip()
        if dirty:
            sys.exit(f"error: task worktree has uncommitted changes; "
                     f"commit or stash first:\n{checkout}")
        git("reset", "--hard", remote, cwd=checkout)
    else:
        git("branch", "-f", branch, remote, cwd=root)


def _rebase_argv(upstream, old_base=None):
    """git rebase args: exclude old_base commits when moving a stack child."""
    if old_base:
        return ["rebase", "--onto", upstream, old_base]
    return ["rebase", upstream]


def _onto_label(upstream, old_base=None):
    return f"{upstream} (excluding {old_base})" if old_base else upstream


def _unmerged_paths(cwd):
    r = git("diff", "--name-only", "--diff-filter=U", cwd=cwd, check=False)
    return [p for p in (r.stdout or "").splitlines() if p]


def _exit_conflicted_rebase(branch, onto, checkout, err=""):
    """Leave the rebase in progress; tell the caller to resolve and re-run."""
    files = _unmerged_paths(checkout)
    listed = "".join(f"\n  {p}" for p in files)
    extra = f"\nUnmerged:{listed}" if files else ""
    detail = f"\n{err}" if err else ""
    sys.exit(f"error: rebase of '{branch}' onto {onto} conflicted in "
             f"{checkout}. Resolve, git add, then re-run restack."
             f"{extra}{detail}")


def _git_no_editor(*args, cwd=None):
    """git with GIT_EDITOR=true so rebase --continue does not open an editor."""
    env = os.environ.copy()
    env["GIT_EDITOR"] = "true"
    env["GIT_SEQUENCE_EDITOR"] = "true"
    env["EDITOR"] = "true"
    return subprocess.run(["git", *args], cwd=cwd, text=True,
                          capture_output=True, env=env)


def _is_restack_temp(path):
    name = os.path.basename((path or "").rstrip(os.sep))
    return name.startswith("dev-restack-rebase-")


def _prune_restack_temp_worktree(root, path):
    """Drop a restack temp worktree after a successful rebase/continue."""
    if not path or not _is_restack_temp(path) or rebase_in_progress(path):
        return
    git("worktree", "remove", "--force", path, cwd=root, check=False)
    shutil.rmtree(path, ignore_errors=True)
    git("worktree", "prune", cwd=root, check=False)


def _continue_in_progress_rebase(root, branch, checkout, upstream,
                                 old_base=None):
    """Continue a restack rebase left in `checkout`. Returns True (rewritten).

    Only continues a rebase that is replaying onto this step's upstream —
    someone else's in-progress rebase is refused, not adopted and
    force-pushed. An unreadable `onto` is refused for the same reason.
    """
    want = git("rev-parse", f"{upstream}^{{commit}}", cwd=root,
               check=False).stdout.strip()
    onto = rebase_onto_sha(checkout)
    if not onto or not want or onto != want:
        sys.exit(f"error: a rebase of '{branch}' is in progress in "
                 f"{checkout}, but onto {onto or '(unknown)'}, not "
                 f"{upstream} ({want[:12] or '?'}); finish or abort it, "
                 f"then re-run restack")
    unmerged = _unmerged_paths(checkout)
    if unmerged:
        listed = "".join(f"\n  {p}" for p in unmerged)
        sys.exit(f"error: rebase of '{branch}' still in progress in "
                 f"{checkout} with unmerged paths. Resolve, git add, then "
                 f"re-run restack:{listed}")
    r = _git_no_editor("rebase", "--continue", cwd=checkout)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        if rebase_in_progress(checkout):
            _exit_conflicted_rebase(branch, _onto_label(upstream, old_base),
                                    checkout, err)
        sys.exit(f"error: rebase --continue of '{branch}' failed in "
                 f"{checkout}:\n{err}")
    _prune_restack_temp_worktree(root, checkout)
    return True


def _rebase_in_existing_checkout(root, branch, upstream, checkout,
                                 old_base=None):
    """Rebase where `branch` is already checked out (task worktree or primary).

    A conflict is left in place so the worktree has something to resolve;
    re-run restack continues it. Do not abort.
    """
    if rebase_in_progress(checkout):
        return _continue_in_progress_rebase(root, branch, checkout, upstream,
                                            old_base)
    dirty = git("status", "--porcelain", cwd=checkout,
                check=False).stdout.strip()
    if dirty:
        sys.exit(f"error: task worktree has uncommitted changes; "
                 f"commit or stash first:\n{checkout}")
    before = git("rev-parse", branch, cwd=root).stdout.strip()
    r = git(*_rebase_argv(upstream, old_base), cwd=checkout, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        onto = _onto_label(upstream, old_base)
        if rebase_in_progress(checkout):
            _exit_conflicted_rebase(branch, onto, checkout, err)
        sys.exit(f"error: rebase of '{branch}' onto {onto} failed in "
                 f"{checkout}:\n{err}")
    after = git("rev-parse", branch, cwd=root).stdout.strip()
    return before != after


def _rebase_via_temp_worktree(root, branch, upstream, old_base=None):
    """Rebase without touching the primary clone's checked-out branch.

    Checks the branch out in a temp worktree (not detached) so a conflict
    is findable on re-run via branch_checkout_cwd, then the branch ref is
    already at the new tip when the worktree is removed. Never runs
    `git rebase <upstream> <branch>`, which would switch the primary checkout.
    """
    before = git("rev-parse", branch, cwd=root).stdout.strip()
    tmp = tempfile.mkdtemp(prefix="dev-restack-rebase-")
    try:
        r = git("worktree", "add", tmp, branch, cwd=root, check=False)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            sys.exit(f"error: could not create temp worktree to rebase "
                     f"'{branch}':\n{err}")
        r = git(*_rebase_argv(upstream, old_base), cwd=tmp, check=False)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            onto = _onto_label(upstream, old_base)
            if rebase_in_progress(tmp):
                # Leave tmp; finally must not delete a conflicted rebase.
                _exit_conflicted_rebase(branch, onto, tmp, err)
            sys.exit(f"error: rebase of '{branch}' onto {onto} failed:\n{err}")
        new = git("rev-parse", "HEAD", cwd=tmp).stdout.strip()
        git("worktree", "remove", "--force", tmp, cwd=root, check=False)
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        tmp = None

        checkout = branch_checkout_cwd(root, branch)
        if checkout:
            dirty = git("status", "--porcelain", cwd=checkout,
                        check=False).stdout.strip()
            if dirty:
                sys.exit(f"error: rebased tip is {new[:12]} but worktree has "
                         f"uncommitted changes; commit/stash, reset to the "
                         f"rebased tip, then re-run restack:\n"
                         f"{checkout}")
            git("reset", "--hard", new, cwd=checkout)
        else:
            git("branch", "-f", branch, new, cwd=root)
        after = git("rev-parse", branch, cwd=root).stdout.strip()
        return before != after
    finally:
        if tmp and os.path.isdir(tmp) and not rebase_in_progress(tmp):
            git("worktree", "remove", "--force", tmp, cwd=root, check=False)
            shutil.rmtree(tmp, ignore_errors=True)
        git("worktree", "prune", cwd=root, check=False)


def rebase_task_onto_ref(root, branch, upstream, old_base=None):
    """Rebase task branch onto upstream ref. Returns True if rewritten.

    Restack only — land never rewrites a task branch. Force-push is the
    caller's job when True; conflicts leave the rebase in the worktree
    and exit (re-run continues). Rebases in the existing checkout if the
    branch is already checked out; otherwise uses a temp worktree so the
    primary clone is never switched onto the task branch solely for the
    rebase. Never rewrites integration.

    Local commits ahead of origin are kept (rewritten restack progress),
    not refused. old_base, when set, is the tip to exclude (`git rebase
    --onto upstream old_base`) when a rewritten stack parent must not be
    replayed. Do not skip when old_base is not an ancestor: the parent
    may have moved ahead of the child. An already-moved child is a no-op
    (`rebase --onto` reports up to date), and behind==0 is not a valid
    skip there — a stacked child usually already contains integration.
    """
    if not ref_exists(root, upstream):
        # Try origin/<name> if bare branch name given
        if not upstream.startswith("origin/") and ref_exists(
                root, f"origin/{upstream}"):
            upstream = f"origin/{upstream}"
        elif not ref_exists(root, upstream):
            sys.exit(f"error: upstream '{upstream}' missing after fetch")
    old_base = resolve_rebase_exclude(root, old_base)
    checkout = branch_checkout_cwd(root, branch)
    if checkout and rebase_in_progress(checkout):
        return _continue_in_progress_rebase(root, branch, checkout, upstream,
                                            old_base)
    sync_task_branch_from_remote(root, branch, keep_ahead=True)
    if not old_base:
        behind = git("rev-list", "--count", f"{branch}..{upstream}",
                     cwd=root).stdout.strip()
        if behind == "0":
            return False
    checkout = branch_checkout_cwd(root, branch)
    if checkout:
        return _rebase_in_existing_checkout(
            root, branch, upstream, checkout, old_base=old_base)
    return _rebase_via_temp_worktree(root, branch, upstream,
                                     old_base=old_base)


def resolve_rebase_exclude(root, old_base):
    """Resolve a restack exclude ref (SHA, branch, or origin/<branch>)."""
    if not old_base:
        return None
    old_base = str(old_base).strip()
    if not old_base:
        return None
    if ref_exists(root, old_base):
        return git("rev-parse", old_base, cwd=root).stdout.strip()
    if not old_base.startswith("origin/") and ref_exists(
            root, f"origin/{old_base}"):
        return git("rev-parse", f"origin/{old_base}", cwd=root).stdout.strip()
    sys.exit(f"error: restack exclude '{old_base}' missing after fetch")


def ref_short_name(ref):
    """Branch name without origin/ prefix."""
    ref = (ref or "").strip()
    if ref.startswith("origin/"):
        return ref[len("origin/"):]
    return ref


def open_prs_based_on(root, base_branch):
    """Open PRs whose GitHub base is base_branch. Paginates; no hard cap."""
    r = gh("api", "--method", "GET", "--paginate",
           "--jq",
           ".[] | {url: .html_url, headRefName: .head.ref, "
           "baseRefName: .base.ref}",
           "repos/{owner}/{repo}/pulls",
           "-f", "state=open",
           "-f", f"base={base_branch}",
           "-F", "per_page=100",
           cwd=root, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        sys.exit(f"error: could not list PRs based on '{base_branch}':\n{err}")
    out = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            sys.exit(f"error: could not parse PR list for base '{base_branch}'")
        head = (item.get("headRefName") or "").strip()
        url = (item.get("url") or "").strip()
        base = (item.get("baseRefName") or "").strip() or base_branch
        if head and url:
            out.append({"url": url, "head": head, "base": base})
    return out


def retarget_children(root, parent_branch, integration, *, fail_closed=True):
    """Point PRs stacked on parent_branch at integration. Fail-closed.

    GitHub does not auto-retarget: deleting a branch that open PRs are
    based on CLOSES them, even when its own PR merged. So this runs after
    the merge and before cleanup deletes the branch. Only the PR base
    moves — the parent's commits are already ancestors of integration
    after a merge commit, so no child branch is rewritten at any depth.
    With fail_closed=False a failed retarget returns its error instead of
    exiting (the caller must then not delete parent_branch); else None.
    """
    children = open_prs_based_on(root, parent_branch)
    if not children:
        return None
    print(f"  retargeting {len(children)} stacked PR(s) to {integration}")
    for pr in children:
        url, head = pr["url"], pr["head"]
        r = pr_cmd("edit", url, "--base", integration, cwd=root)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            if not fail_closed:
                return f"could not retarget {url} ({head}):\n  {indent_err(err)}"
            sys.exit(f"error: could not retarget {url} ({head}) from "
                     f"'{parent_branch}' to '{integration}'; not deleting "
                     f"'{parent_branch}' (that would close this PR). "
                     f"Retarget it, then re-run land.\n{err}")
        print(f"  retarget {head}: {parent_branch} → {integration}")
    return None


def merge_forward_task_branch(root, branch, integration):
    """Merge origin/<integration> into the task branch, in place.

    Absorbs a conflict without rewriting, so PRs stacked on this branch
    stay valid. Only a clean merge is kept: a conflicted one is aborted
    (atomic, unlike a half-applied rebase) and handed to the author, who
    owns the branch and the context to resolve it. Returns False when the
    branch already contains integration — then the CONFLICTING verdict is
    not divergence and merging forward cannot fix it.
    """
    up = f"origin/{integration}"
    git("fetch", "origin", integration, cwd=root, check=False)
    git("fetch", "origin", branch, cwd=root, check=False)
    if not ref_exists(root, up):
        sys.exit(f"error: '{up}' missing after fetch; cannot merge forward")
    # Merge forward from the reviewed tip, not a stale local ref (refuses
    # if local is ahead, so unpushed work is never published by land).
    sync_task_branch_from_remote(root, branch)
    behind = git("rev-list", "--count", f"{branch}..{up}",
                 cwd=root).stdout.strip()
    if behind in ("", "0"):
        return False
    checkout = branch_checkout_cwd(root, branch)
    tmp = None
    if not checkout:
        tmp = tempfile.mkdtemp(prefix="dev-land-merge-")
        r = git("worktree", "add", tmp, branch, cwd=root, check=False)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            shutil.rmtree(tmp, ignore_errors=True)
            sys.exit(f"error: could not create temp worktree to merge "
                     f"'{branch}' forward:\n{err}")
        checkout = tmp
    try:
        dirty = git("status", "--porcelain", cwd=checkout,
                    check=False).stdout.strip()
        if dirty:
            sys.exit(f"error: worktree for '{branch}' is dirty at "
                     f"{checkout}; commit or stash, then re-run land")
        r = git("merge", "--no-edit", up, cwd=checkout, check=False)
        if r.returncode != 0:
            git("merge", "--abort", cwd=checkout, check=False)
            err = (r.stderr or r.stdout or "").strip()
            sys.exit(f"error: '{branch}' conflicts with {up} and land does "
                     f"not resolve conflicts or rewrite your branch.\n"
                     f"Resolve on the branch (git merge {up} — merge, do "
                     f"not rebase, or any PR stacked on it needs a "
                     f"restack), push, then re-run land.\n{err}")
        print(f"  merged {up} into {branch}; pushing")
        push_task_branch(root, branch, force=False)
        return True
    finally:
        if tmp:
            git("worktree", "remove", "--force", tmp, cwd=root, check=False)
            shutil.rmtree(tmp, ignore_errors=True)
            git("worktree", "prune", cwd=root, check=False)


def push_task_branch(root, branch, force=False):
    """Push task branch to origin; force-with-lease only after a rebase."""
    if not branch:
        return
    args = ["push", "origin", f"refs/heads/{branch}:refs/heads/{branch}"]
    if force:
        args.insert(1, "--force-with-lease")
    r = git(*args, cwd=root, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        sys.exit(f"error: push of '{branch}' failed:\n{err}")


def wait_for_pr_mergeable(root, pr, *, timeout_s=None, poll_s=None):
    """Poll until GitHub settles mergeable, or timeout.

    Returns one of: MERGEABLE, CONFLICTING, UNKNOWN, MERGED.
    UNKNOWN means still computing after timeout — caller may try merge anyway.
    """
    if timeout_s is None:
        timeout_s = LAND_MERGEABLE_TIMEOUT_S
    if poll_s is None:
        poll_s = LAND_MERGEABLE_POLL_S
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    last = "UNKNOWN"
    announced = False
    while True:
        info = pr_view(root, pr, soft=True)
        if info and pr_is_merged(info):
            return "MERGED"
        raw = (info or {}).get("mergeable")
        # gh usually returns MERGEABLE|CONFLICTING|UNKNOWN; REST may use bool.
        if raw is True:
            m = "MERGEABLE"
        elif raw is False:
            m = "CONFLICTING"
        elif raw is None or raw == "":
            m = "UNKNOWN"
        else:
            m = str(raw).upper()
        if m in ("MERGEABLE", "CONFLICTING"):
            if announced:
                print(f"  PR mergeable={m}")
            return m
        last = m or "UNKNOWN"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(f"  PR mergeable still {last} after {timeout_s}s; trying merge")
            return "UNKNOWN"
        if not announced:
            print(f"  waiting for GitHub mergeable (currently {last})…")
            announced = True
        time.sleep(min(float(poll_s), remaining))


def merge_error_transient(err):
    """True only when a failed gh pr merge is worth another attempt.

    Permanent policy/review/auth failures return False so land fails fast.
    Default is permanent: only known "branch behind / conflict / flake"
    shapes retry.
    """
    e = (err or "").lower()
    if not e:
        return False
    # Permanent — never retry.
    permanent = (
        "pull request not found",
        "could not resolve",
        "no pull requests found",
        "authentication",
        "permission denied",
        "not allowed on this repository",
        "merge commits are not allowed",
        "squash merges are not allowed",
        "rebase merges are not allowed",
        "protected branch",
        "resource not accessible",
        "policy",
        "prohibits the merge",
    )
    if any(p in e for p in permanent):
        return False
    # Review / approval / draft: land never auto-approves or un-drafts.
    if "draft" in e:
        return False
    if "review" in e and ("required" in e or "approv" in e or "pending" in e):
        return False
    if "approv" in e and ("required" in e or "needed" in e or "pending" in e
                          or "missing" in e):
        return False
    # Status checks: pending/waiting may clear; hard failures must not spin.
    if "status check" in e:
        if any(w in e for w in ("fail", "unsuccessful", "errored")):
            return False
        if any(w in e for w in (
                "pending", "waiting", "in progress", "expected",
                "not complete", "incomplete")):
            return True
        # Unknown status-check wording — fail fast rather than retry-loop.
        return False
    # Transient — rebase onto updated base and/or wait may help.
    needles = (
        "not mergeable",
        "merge conflict",
        "head branch is out of date",
        "base branch was modified",
        "temporarily unavailable",
        "try again",
    )
    return any(n in e for n in needles)


def merge_error_wants_update(err):
    """True when a failed gh pr merge asks for the branch to catch up.

    Land does not rebase, so the only remedy for these is merging
    origin/<integration> forward into the branch (what GitHub's "Update
    branch" button does). Flake/status-check shapes are excluded — they
    clear on their own and must not mutate the branch.
    """
    e = (err or "").lower()
    return any(n in e for n in (
        "head branch is out of date",
        "base branch was modified",
        "not mergeable",
        "merge conflict",
    ))


def merge_commits_disallowed(err):
    """True when gh pr merge failed because the repo forbids merge commits."""
    e = (err or "").lower()
    return ("merge commits are not allowed" in e
            or ("merge commit" in e and "not allowed" in e))


def merge_fail_permanent_message(err):
    """Human-facing exit text for a non-retryable merge failure."""
    low = (err or "").lower()
    if "draft" in low:
        return (f"error: PR is draft; mark ready for review before land:\n"
                f"{err}")
    if "approv" in low or ("review" in low and (
            "required" in low or "pending" in low or "approv" in low)):
        return (f"error: merge blocked by review rules "
                f"(land does not auto-approve):\n{err}")
    if "status check" in low and any(
            w in low for w in ("fail", "unsuccessful", "errored")):
        return (f"error: merge blocked by failed status check(s); "
                f"fix CI before land:\n{err}")
    return f"error: merge failed (not retryable):\n{err}"


def draft_unsupported(err):
    """True when gh refused --draft because the repo/plan has no drafts.

    Draft PRs need a paid plan on a private repo. That is a limit of the
    mirror, not of the board: `draft` stays a real board state there, so
    ship downgrades the PR, not the task.
    """
    e = (err or "").lower()
    return "draft" in e and any(w in e for w in (
        "not supported", "unsupported", "not available", "not enabled",
        "upgrade", "plan"))


# ---------- PR transport: gh pr, or GitHub REST when GraphQL is blocked ----------
#
# Every PR call goes through pr_cmd, spelled as `gh pr` arguments. Locally
# that is exactly `gh pr …`. `gh pr` speaks GraphQL, which some hosted agent
# sandboxes block; the first call refused that way switches this process to
# REST (`gh api`) for the rest of its run, and DEVOPS_PR_TRANSPORT=rest
# starts there. rest_pr translates the same arguments and returns what
# `gh pr` would have printed, so call sites never know which ran. The board
# records a PR by its html URL.

PR_URL_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")
GRAPHQL_BLOCKED = "graphql is not available"
_PR_TRANSPORT = []  # memo: [] until first use, then ["gh"] or ["rest"]


def pr_transport_from_env(env):
    """'rest' only when DEVOPS_PR_TRANSPORT says so; anything else is gh."""
    v = (env.get("DEVOPS_PR_TRANSPORT") or "").strip().lower()
    return "rest" if v == "rest" else "gh"


def graphql_blocked(returncode, err):
    """True when a failed gh pr call was refused for GraphQL itself."""
    return returncode != 0 and GRAPHQL_BLOCKED in (err or "").lower()


def pr_transport():
    if not _PR_TRANSPORT:
        _PR_TRANSPORT.append(pr_transport_from_env(os.environ))
    return _PR_TRANSPORT[0]


def switch_pr_transport_to_rest():
    pr_transport()
    _PR_TRANSPORT[0] = "rest"
    print("note: GitHub GraphQL is not available here; PR calls use the "
          "REST API (gh api) for the rest of this command", file=sys.stderr)


def pr_cmd(*args, cwd=None):
    """`gh pr <args>` (never exits), or its REST equivalent once REST is in
    use. A GraphQL refusal switches and retries this same call over REST."""
    if pr_transport() == "gh":
        r = gh("pr", *args, cwd=cwd, check=False)
        if not graphql_blocked(r.returncode, gh_err(r)):
            return r
        switch_pr_transport_to_rest()
    return rest_pr(cwd, list(args))


def pr_hint_retarget(url, base):
    """The command a human runs to retarget a PR, for the transport in use."""
    if pr_transport() == "rest":
        return f"gh api --method PATCH {pr_api_path(url)} -f base={base}"
    return f"gh pr edit {url} --base {base}"


def pr_call_label(sub):
    """How an error names a PR call: the transport that actually ran it."""
    if pr_transport() == "rest":
        return f"PR {sub} over the REST API (gh api)"
    return f"gh pr {sub}"


def pr_hint_create(base, head, title):
    if pr_transport() == "rest":
        return (f"gh api --method POST repos/{{owner}}/{{repo}}/pulls "
                f"-f base={base} -f head={head} -f title={title!r}")
    return f"gh pr create --base {base} --head {head} --title {title!r}"


def pr_api_path(pr):
    """REST path of a PR, from its URL (what the board records) or number."""
    pr = (pr or "").strip()
    m = PR_URL_RE.search(pr)
    if m:
        return f"repos/{m[1]}/{m[2]}/pulls/{m[3]}"
    if pr.isdigit():
        return f"repos/{{owner}}/{{repo}}/pulls/{pr}"
    sys.exit(f"error: not a PR URL or number: {pr!r}")


def pr_issue_path(pr):
    """REST path of a PR's issue (where conversation comments live)."""
    head, _, num = pr_api_path(pr).rpartition("/pulls/")
    return f"{head}/issues/{num}"


def gh_rest(root, method, path, fields=None, *, accept=None):
    """One `gh api` call; never exits. Bools go typed (-F), the rest raw."""
    argv = ["api", "--method", method, path]
    if accept:
        argv += ["-H", f"Accept: {accept}"]
    for k, v in (fields or {}).items():
        if isinstance(v, bool):
            argv += ["-F", f"{k}={'true' if v else 'false'}"]
        else:
            argv += ["-f", f"{k}={v}"]
    return gh(*argv, cwd=root, check=False)


def gh_err(r):
    """gh api puts 'gh: <message> (HTTP n)' on stderr and the JSON error
    body (with any validation detail) on stdout; callers match on both."""
    return "\n".join(s.strip() for s in (r.stderr, r.stdout)
                     if s and s.strip())


def rest_json(r):
    try:
        return json.loads(r.stdout or "null")
    except json.JSONDecodeError:
        return None


def pr_from_rest(d):
    """A REST pull object under `gh pr view --json` field names."""
    merged = bool(d.get("merged_at") or d.get("merged"))
    m = d.get("mergeable")
    return {
        "number": d.get("number"),
        "url": d.get("html_url") or "",
        "title": d.get("title") or "",
        "body": d.get("body") or "",
        "state": "MERGED" if merged else (d.get("state") or "").upper(),
        "mergedAt": d.get("merged_at"),
        "mergeable": ("UNKNOWN" if m is None
                      else "MERGEABLE" if m else "CONFLICTING"),
        "isDraft": bool(d.get("draft")),
        "headRefName": ((d.get("head") or {}).get("ref") or ""),
        "headRefOid": ((d.get("head") or {}).get("sha") or ""),
        "baseRefName": ((d.get("base") or {}).get("ref") or ""),
        "author": {"login": (d.get("user") or {}).get("login") or ""},
    }


def review_decision(reviews):
    """Latest APPROVED / CHANGES_REQUESTED per reviewer, rolled up.

    REST has no reviewDecision (that is GraphQL, which also weighs branch
    protection), so this only reports what reviewers said: any standing
    change request wins, else any approval, else ''.
    """
    latest = {}
    for rv in reviews or []:
        st = (rv.get("state") or "").upper()
        if st in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[(rv.get("user") or {}).get("login") or ""] = st
    states = set(latest.values())
    if "CHANGES_REQUESTED" in states:
        return "CHANGES_REQUESTED"
    return "APPROVED" if "APPROVED" in states else ""


PR_VALUE_FLAGS = ("--base", "--head", "--title", "--body", "--json",
                  "--state", "--limit")


def parse_pr_args(args):
    """gh pr argv → (subcommand, positional PR or '', {flag: value|True})."""
    sub, pos, opts = args[0], "", {}
    i = 1
    while i < len(args):
        a = args[i]
        if a in PR_VALUE_FLAGS:
            opts[a[2:]] = args[i + 1]
            i += 2
            continue
        if a.startswith("--"):
            opts[a[2:]] = True
        elif not pos:
            pos = a
        i += 1
    return sub, pos, opts


def _rest_done(r, stdout=None):
    """A REST result shaped like gh pr's: what it prints on success, the
    whole error (message + JSON detail) on stderr on failure."""
    if r.returncode != 0:
        return subprocess.CompletedProcess(r.args, r.returncode, "",
                                           gh_err(r))
    out = r.stdout if stdout is None else stdout
    return subprocess.CompletedProcess(r.args, 0, out, "")


def _rest_fail(msg):
    return subprocess.CompletedProcess(["gh", "api"], 1, "", msg)


def rest_list_all(root, path):
    r = gh_rest(root, "GET", f"{path}?per_page=100")
    items = rest_json(r) if r.returncode == 0 else None
    return items if isinstance(items, list) else None, r


def _rest_pr_json(root, pr, fields):
    """`gh pr view --json fields` over REST (dict) or a failed result."""
    r = gh_rest(root, "GET", pr_api_path(pr))
    d = rest_json(r) if r.returncode == 0 else None
    if not isinstance(d, dict):
        return _rest_done(r) if r.returncode else _rest_fail(
            f"could not parse the REST reply for {pr}")
    info = pr_from_rest(d)
    if {"reviews", "reviewDecision"} & set(fields):
        reviews, rr = rest_list_all(root, f"{pr_api_path(pr)}/reviews")
        if reviews is None:
            return _rest_done(rr)
        info["reviewDecision"] = review_decision(reviews)
        info["reviews"] = [{"author": {"login": (rv.get("user") or {})
                                       .get("login") or ""},
                            "state": rv.get("state"),
                            "body": rv.get("body") or ""}
                           for rv in reviews]
    if "comments" in fields:
        # Conversation comments only, as gh pr view lists them: inline
        # review comments (pulls/{n}/comments) are not part of it.
        comments, rc = rest_list_all(root, f"{pr_issue_path(pr)}/comments")
        if comments is None:
            return _rest_done(rc)
        info["comments"] = [
            {"author": {"login": (c.get("user") or {}).get("login") or ""},
             "body": c.get("body") or ""}
            for c in comments]
    return info


def format_rest_pr_view(info):
    """Plain `gh pr view`-like text for a REST-built view."""
    draft = " draft" if info["isDraft"] else ""
    lines = [info["title"], info["url"],
             f"state: {info['state']}{draft}  {info['baseRefName']} ← "
             f"{info['headRefName']}  reviews: "
             f"{info['reviewDecision'] or 'none'}  "
             f"author: {info['author']['login']}",
             "", info["body"].strip()]
    for rv in info["reviews"]:
        body = rv["body"].strip()
        lines += ["", f"— review {rv['state']} by {rv['author']['login']}"
                  + (f":\n{body}" if body else "")]
    for c in info["comments"]:
        lines += ["", f"— {c['author']['login']}:\n{c['body'].strip()}"]
    return "\n".join(lines) + "\n"


def rest_pr(root, args):
    """Run `gh pr <args>` over REST; returns what gh pr would have."""
    sub, pr, o = parse_pr_args(args)
    if sub == "view":
        fields = (o.get("json") or "").split(",") if o.get("json") else \
            ["reviews", "comments"]
        info = _rest_pr_json(root, pr, fields)
        if not isinstance(info, dict):
            return info
        if not o.get("json"):
            return subprocess.CompletedProcess(
                ["gh", "api"], 0, format_rest_pr_view(info), "")
        return subprocess.CompletedProcess(
            ["gh", "api"], 0,
            json.dumps({k: info.get(k) for k in fields}), "")
    if sub == "list":
        state = o.get("state") or "open"
        head = urllib.parse.quote(o.get("head") or "", safe="/")
        r = gh_rest(root, "GET",
                    f"repos/{{owner}}/{{repo}}/pulls?"
                    f"state={'closed' if state == 'merged' else state}"
                    f"&head={{owner}}:{head}&per_page=100")
        items = rest_json(r) if r.returncode == 0 else None
        if not isinstance(items, list):
            return _rest_done(r) if r.returncode else _rest_fail(
                "could not parse the REST PR list")
        rows = [pr_from_rest(d) for d in items if isinstance(d, dict)]
        if state == "merged":
            rows = [x for x in rows if x["state"] == "MERGED"]
        if o.get("base"):
            rows = [x for x in rows if x["baseRefName"] == o["base"]]
        rows = rows[:int(o.get("limit") or 30)]
        keys = (o.get("json") or "url").split(",")
        return subprocess.CompletedProcess(
            ["gh", "api"], 0, json.dumps([{k: x.get(k) for k in keys}
                                          for x in rows]), "")
    if sub == "create":
        fields = {k: o[k] for k in ("base", "head", "title", "body")
                  if k in o}
        if o.get("draft"):
            fields["draft"] = True
        r = gh_rest(root, "POST", "repos/{owner}/{repo}/pulls", fields)
        d = rest_json(r) if r.returncode == 0 else None
        url = d.get("html_url") if isinstance(d, dict) else ""
        return _rest_done(r, f"{url}\n")
    path = pr_api_path(pr)
    if sub == "edit":
        fields = {k: o[k] for k in ("base", "body", "title") if k in o}
        return _rest_done(gh_rest(root, "PATCH", path, fields), f"{pr}\n")
    if sub == "close":
        return _rest_done(gh_rest(root, "PATCH", path, {"state": "closed"}),
                          f"closed {pr}\n")
    if sub == "merge":
        return _rest_done(gh_rest(root, "PUT", f"{path}/merge",
                                  {"merge_method": "merge"}),
                          f"merged {pr}\n")
    if sub == "ready":
        # Plain REST cannot flip the draft bit; the sandbox's GitHub proxy
        # offers these routes for it, and its GraphQL refusal names them.
        route = "convert_to_draft" if o.get("undo") else "ready_for_review"
        return _rest_done(gh_rest(root, "POST", f"{path}/ccr/{route}"), "")
    if sub == "diff":
        return _rest_done(gh_rest(root, "GET", path,
                                  accept="application/vnd.github.diff"))
    if sub == "comment":
        return _rest_done(gh_rest(root, "POST", f"{pr_issue_path(pr)}/comments",
                                  {"body": o.get("body") or ""}),
                          f"commented on {pr}\n")
    if sub == "review":
        event = ("APPROVE" if o.get("approve") else
                 "REQUEST_CHANGES" if o.get("request-changes") else "COMMENT")
        fields = {"event": event}
        if o.get("body"):
            fields["body"] = o["body"]
        return _rest_done(gh_rest(root, "POST", f"{path}/reviews", fields),
                          f"{event.lower().replace('_', ' ')} on {pr}\n")
    return _rest_fail(f"no REST equivalent for gh pr {sub}")


def sync_pr_draft_bit(root, pr, want_draft):
    """Mirror the board's draft/review state onto the PR's draft bit.

    The board is the source of truth, so a refusal warns and returns False
    rather than failing the caller — otherwise a repo without draft PRs
    could not use the draft state at all. Already in the wanted state is a
    no-op, which also re-converges a board that drifted from the PR.
    """
    info = pr_view(root, pr, soft=True) or {}
    if info.get("isDraft") is want_draft:
        return True
    argv = ["ready", pr] + (["--undo"] if want_draft else [])
    r = pr_cmd(*argv, cwd=root)
    if r.returncode == 0:
        return True
    err = (r.stderr or r.stdout or "").strip()
    want = "draft" if want_draft else "ready"
    print(f"warning: could not mark the PR {want} (this repo may not "
          f"support draft PRs); the board state stands:\n{err}",
          file=sys.stderr)
    return False


def pr_view(root, pr, *, soft=False):
    """JSON fields for land/cleanup. soft=True returns None on failure."""
    r = pr_cmd("view", pr,
           "--json", "state,mergedAt,mergeable,headRefName,baseRefName,"
           "body,url,title,isDraft",
           cwd=root)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        if soft:
            return None
        sys.exit(f"error: {pr_call_label('view')} failed for {pr}:\n{err}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        if soft:
            return None
        sys.exit(f"error: could not parse {pr_call_label('view')} output "
                 f"for {pr}")


def pr_is_merged(info):
    if not info:
        return False
    return bool((info.get("state") or "").upper() == "MERGED"
                or info.get("mergedAt"))


def task_branch_safe_to_drop(root, meta, branch):
    """Whether remote/local task branch may be deleted without losing work.

    Requires evidence the PR landed (MERGED). Refuses when gh cannot verify.
    Returns (ok: bool, reason: str).
    """
    if not branch:
        return False, "no branch recorded"
    pr = (meta.get("pr") or "").strip()
    if not pr:
        return False, "no PR URL to verify merge; refusing to delete branch"
    # Prefer soft view so cleanup never aborts the whole command on gh flake.
    if gh_sign_in_error(root) is not None:
        return False, "gh not authenticated; refusing to delete branch"
    info = pr_view(root, pr, soft=True)
    if info is None:
        return False, f"could not verify PR state for {pr}; refusing to delete branch"
    if pr_is_merged(info):
        return True, "PR merged"
    state = (info.get("state") or "?").upper()
    return False, f"PR is {state} (not merged); refusing to delete branch"


def worktree_is_dirty(path):
    r = git("status", "--porcelain", cwd=path, check=False)
    if r.returncode != 0:
        return True  # treat unknown as dirty — do not force-remove
    return bool((r.stdout or "").strip())


def mark_task_done(root, scope, branch, bw, meta):
    """Finish a task on the board. Returns True if changed.

    A recurring task never goes done: it re-arms (last_run stamped, back to
    backlog) so the next cycle is already on the board. Both land paths go
    through here, and both pass `branch` to cleanup explicitly, so clearing
    the task's branch field here does not strand the worktree.
    """
    meta = find_task(bw, scope, meta["id"])
    if is_recurring(meta):
        rearm_recurring(root, scope, branch, bw, meta)
        return True
    if meta["status"] == "done":
        return False
    meta["status"] = "done"
    with open(meta["path"], "w", newline="\n") as f:
        f.write(render_task(meta))
    board_commit(root, branch, bw, scope,
                 f"dev: update T{meta['id']} (status=done)")
    return True


def land_outcome(meta):
    """What land did to the task: done, or re-armed for its next run."""
    if not is_recurring(meta):
        return "done"
    due = task_due_date(meta)
    return f"re-armed (next due {format_due(due)})" if due else "re-armed"


def _switch_primary_off_task_branch(root, scope, branch, actions):
    """If primary clone has the task branch checked out, move it to integration.

    Needed so local branch delete can succeed after land when someone had the
    task branch checked out on the primary tree (not only in a task worktree).
    """
    still = branch_checkout_cwd(root, branch)
    if not still or not same_path(still, root):
        return
    if worktree_is_dirty(root):
        actions.append(f"primary clone still on '{branch}' (dirty; not switching)")
        return
    ibranch = integration_branch(root, scope)
    target = f"origin/{ibranch}" if ref_exists(root, f"origin/{ibranch}") else ibranch
    if not ref_exists(root, target) and not ref_exists(root, ibranch):
        actions.append(f"primary clone still on '{branch}' "
                       f"(no {ibranch} ref to switch to)")
        return
    # Prefer a real local branch checkout so primary is not left detached.
    if ref_exists(root, f"refs/heads/{ibranch}"):
        r = git("checkout", ibranch, cwd=root, check=False)
    elif ref_exists(root, f"origin/{ibranch}"):
        r = git("checkout", "-B", ibranch, f"origin/{ibranch}", cwd=root,
                check=False)
    else:
        r = git("checkout", ibranch, cwd=root, check=False)
    if r.returncode == 0:
        actions.append(f"switched primary clone to '{ibranch}'")
    else:
        err = (r.stderr or r.stdout or "").strip()
        actions.append(f"could not switch primary off '{branch}': {err}")


def husk_is_all_ignored(root, husk):
    """True when every file in `husk` would be gitignored at the same path
    in the repo (a task worktree is a checkout of the repo root)."""
    rels = []
    for dirpath, dirnames, filenames in os.walk(husk):
        for name in filenames + [d for d in dirnames
                                 if os.path.islink(os.path.join(dirpath, d))]:
            rels.append(os.path.relpath(os.path.join(dirpath, name), husk))
    if not rels:
        return True
    r = subprocess.run(["git", "check-ignore", "-z", "--stdin"], cwd=root,
                       input="\0".join(rels) + "\0", text=True,
                       capture_output=True)
    if r.returncode not in (0, 1):
        return False
    return set(rels) <= set(p for p in r.stdout.split("\0") if p)


def sweep_worktree_husks(root, scope, cwd, actions):
    """Remove every no-.git dir under .dev/worktrees/ (any task id) whose
    files are all gitignored — what a tool such as Xcode writes back after
    the worktree was removed. Anything else is left and reported."""
    wt_dir = os.path.join(product_root(root, scope), ".dev", "worktrees")
    if not os.path.isdir(wt_dir):
        return
    for name in sorted(os.listdir(wt_dir)):
        path = os.path.join(wt_dir, name)
        if (os.path.islink(path) or not os.path.isdir(path)
                or os.path.exists(os.path.join(path, ".git"))
                or path_is_inside(cwd, path)):
            continue
        if not husk_is_all_ignored(root, path):
            actions.append(f"left orphan dir {path} (no .git, holds "
                           f"files that are not gitignored; remove by hand)")
            continue
        try:
            shutil.rmtree(path)
            actions.append(f"removed gitignored leftovers {path}")
        except OSError as e:
            actions.append(f"could not remove leftovers {path}: {e}")


def indent_err(err):
    return "\n  ".join(err.splitlines())


_HTTP_403 = re.compile(r"HTTP(?:/[\d.]+)?\s+403\b|returned error:\s*403\b",
                       re.IGNORECASE)


def remote_delete_refused_msg(err, what, env=None):
    """Action line for a remote branch delete the remote refused. In a
    Claude cloud session (CLAUDE_CODE_REMOTE set) an HTTP 403 is expected
    (its proxy refuses every branch delete), so it gets one calm line
    without git's output. Any other refusal, and a 403 anywhere else (a
    token without push rights, SSO not authorized), keeps the git error.
    `what` names what was left, e.g. 'left origin/<b> on the remote'."""
    env = os.environ if env is None else env
    later = "a later local land or cleanup removes it"
    if env.get("CLAUDE_CODE_REMOTE") and _HTTP_403.search(err or ""):
        return (f"{what} (this session may not delete remote branches); "
                f"{later}, nothing to do now")
    return f"{what} (the remote refused the delete); {later}:\n  {indent_err(err)}"


def task_branch_re(scope):
    """This board's conventional task branch names (default_task_branch)."""
    prefix = default_task_branch(scope, 0, "")[:-len("0-task")]
    return re.compile(rf"{re.escape(prefix)}\d+-")


def sweep_candidates(tips, scope, keep):
    """Remote task branches the sweep may look at: this board's naming,
    minus `keep` (the task's own branch and every in-flight task's)."""
    pat = task_branch_re(scope)
    return [b for b in sorted(tips) if pat.match(b) and b not in keep]


def sweep_merged_task_branches(root, scope, bw, own, actions):
    """Delete merged task branches left on origin (a cloud session's land
    cannot delete them). Reads the remote, not the board, so recurring and
    archived tasks are covered. A branch goes only when its tip is in
    origin/<integration>, no in-flight task holds it, and a merged PR has
    it as head at that exact tip. Candidates are found with local git;
    gh is called only for one. Stops at the first refused delete or failed
    lookup, so a session that cannot delete pays for one candidate."""
    integration = integration_branch(root, scope)
    up = f"origin/{integration}"
    if not ref_exists(root, up):
        return
    r = git("for-each-ref", "--format=%(refname) %(objectname)",
            "refs/remotes/origin/", cwd=root, check=False)
    tips = {}
    for line in (r.stdout or "").splitlines():
        ref, _, sha = line.partition(" ")
        tips[ref[len("refs/remotes/origin/"):]] = sha
    keep = {own} | {t["branch"] for t in all_tasks(bw, scope)
                    if t["status"] in IN_FLIGHT and t.get("branch")}
    for b in sweep_candidates(tips, scope, keep):
        tip = tips[b]
        if not is_ancestor(root, tip, up):
            continue
        r = pr_cmd("list", "--head", b, "--state", "merged",
                   "--json", "headRefOid,url", cwd=root)
        try:
            rows = json.loads(r.stdout) if r.returncode == 0 else None
        except json.JSONDecodeError:
            rows = None
        if not isinstance(rows, list):
            err = (r.stderr or r.stdout or "").strip()
            actions.append(f"stopped the merged-branch sweep: could not look "
                           f"up PRs for '{b}':\n  {indent_err(err)}")
            return
        merged = [x for x in rows if x.get("headRefOid") == tip]
        if not merged:
            continue
        # An unrelated branch's retarget must not fail this land/cleanup.
        err = retarget_children(root, b, integration, fail_closed=False)
        if err:
            actions.append(f"stopped the merged-branch sweep: kept origin/{b} "
                           f"(deleting it would close a stacked PR); {err}")
            return
        r = git("push", "origin", "--delete", b, cwd=root, check=False)
        if r.returncode == 0:
            actions.append(f"swept origin/{b} "
                           f"(merged in {merged[0].get('url')})")
            continue
        err = (r.stderr or r.stdout or "").strip()
        if "does not exist" in err.lower():
            git("branch", "-d", "-r", f"origin/{b}", cwd=root, check=False)
            continue
        actions.append(remote_delete_refused_msg(
            err, f"stopped the merged-branch sweep at origin/{b}"))
        return


def cleanup_task_artifacts(root, scope, bw, meta, branch=None, *, verbose=True):
    """Idempotent cleanup: clean worktrees; branches only after PR merge proof.

    Never deletes origin/<branch> or the local task branch unless the task's
    PR is verified MERGED via gh. Retargets any PR still based on the
    branch to integration first (deleting it would close them) and fails
    closed if that retarget fails. Dirty worktrees are left alone (no
    --force wipe of uncommitted work). Safe to re-run; safe on open PRs.
    Then sweeps other merged task branches a cloud session left behind,
    unless the remote just refused this branch's own delete.
    """
    tid = meta["id"]
    branch = branch if branch is not None else task_branch_name(meta)
    actions = []
    cwd = os.getcwd()

    for path in find_task_worktree_paths(root, scope, tid, branch):
        if path_is_inside(cwd, path):
            sys.exit(f"error: cwd is inside task worktree {path}; "
                     "cd to the primary clone (or product dir) and re-run")
        if same_path(path, root):
            continue
        if same_path(path, os.path.join(root, board_worktree_rel(scope))):
            continue
        if not os.path.exists(path):
            continue
        # No .git link: not a worktree any more — the husk sweep below owns it.
        if os.path.isdir(path) and not os.path.exists(os.path.join(path, ".git")):
            continue
        if worktree_is_dirty(path):
            actions.append(f"skipped dirty worktree {path} "
                           f"(uncommitted changes; commit/stash or remove by hand)")
            continue
        r = git("worktree", "remove", path, cwd=root, check=False)
        if r.returncode != 0:
            git("worktree", "prune", cwd=root, check=False)
            # Force only after clean check — handles locked admin files, not dirt.
            r = git("worktree", "remove", "--force", path, cwd=root, check=False)
        if r.returncode == 0:
            actions.append(f"removed worktree {path}")
        else:
            err = (r.stderr or r.stdout or "").strip()
            actions.append(f"worktree remove failed for {path}: {err}")

    git("worktree", "prune", cwd=root, check=False)
    sweep_worktree_husks(root, scope, cwd, actions)

    drop_ok, drop_reason = task_branch_safe_to_drop(root, meta, branch)
    if branch and not drop_ok:
        actions.append(f"kept branch '{branch}': {drop_reason}")

    remote = has_remote(root)
    if remote:
        # Also brings in the task branches the sweep below looks at.
        git("fetch", "origin", "--prune", cwd=root, check=False)
    refused = False
    if branch and drop_ok:
        if remote:
            # Deleting a branch open PRs are based on closes them, so the
            # retarget lives with the delete, not only in land.
            retarget_children(root, branch, integration_branch(root, scope))
            if ref_exists(root, f"origin/{branch}"):
                r = git("push", "origin", "--delete", branch, cwd=root,
                        check=False)
                if r.returncode == 0:
                    actions.append(f"deleted origin/{branch}")
                else:
                    err = (r.stderr or r.stdout or "").strip()
                    if "remote ref does not exist" in err.lower() or \
                       "does not exist" in err.lower():
                        actions.append(f"origin/{branch} already gone")
                    else:
                        refused = True
                        actions.append(remote_delete_refused_msg(
                            err, f"left origin/{branch} on the remote"))
            else:
                actions.append(f"origin/{branch} already absent")

        # Move primary off the task branch before deleting it.
        _switch_primary_off_task_branch(root, scope, branch, actions)

        still = branch_checkout_cwd(root, branch)
        if still:
            actions.append(f"local branch '{branch}' still checked out at "
                           f"{still}; not deleted")
        elif ref_exists(root, f"refs/heads/{branch}"):
            # -D, not -d: the branch may have been merged into integration
            # rather than the current HEAD — only reached when PR is
            # verified MERGED.
            r = git("branch", "-D", branch, cwd=root, check=False)
            if r.returncode == 0:
                actions.append(f"deleted local branch {branch}")
            else:
                err = (r.stderr or r.stdout or "").strip()
                actions.append(f"could not delete local {branch}: {err}")
        else:
            actions.append(f"local branch {branch} already absent")

        if ref_exists(root, f"refs/remotes/origin/{branch}"):
            git("branch", "-d", "-r", f"origin/{branch}", cwd=root, check=False)
            actions.append(f"pruned origin/{branch} remote-tracking ref")

    if remote and not refused:
        sweep_merged_task_branches(root, scope, bw, branch, actions)

    if not actions:
        actions.append("already clean")
    if verbose:
        for a in actions:
            print(f"cleanup: {a}")
    return actions


def cmd_cleanup(args):
    """Idempotent cleanup; refuses to delete branches unless PR is MERGED."""
    root, scope, _ibranch, bw = ctx()
    meta = find_task(bw, scope, args.id)
    branch = task_branch_name(meta)
    if not branch and not find_task_worktree_paths(root, scope, meta["id"], ""):
        print(f"T{meta['id']}: nothing to clean (no branch / worktree "
              f"recorded); sweeping merged task branches")
        cleanup_task_artifacts(root, scope, bw, meta, "")
        return
    print(f"T{meta['id']}: cleaning branch={branch or '(none)'} …")
    cleanup_task_artifacts(root, scope, bw, meta, branch)


def note_version_intent(intent, integration, product):
    """Post-land bump reminder. Silent when intent is missing or none."""
    intent = version_intent_bump(intent)
    if not intent:
        return
    print(f"note: Version intent is '{intent}' — apply one bump "
          f"on '{integration}' when this set is done (per product "
          f"versioning docs)")
    print(f"  product: {shown_path(product)}")


def cmd_land(args):
    """Post-approval land: merge, retarget children, cleanup.

    Merge is integrator-only (whoami on the integrator roster). Already-merged
    and already-done paths are cleanup and stay allowed for anyone so
    board/status/review refresh can mark done.
    Merges with a merge commit and never rewrites the task branch: the
    branch's commits become ancestors of integration, so PRs stacked on
    it need no rebase at any depth. Divergence is absorbed by the merge;
    a real conflict is merged forward into the branch (clean only) or
    handed back to the author. Immediate children are retargeted to
    integration after the merge and before cleanup deletes the branch —
    deleting it first would close them. Already-done is cleanup only.
    Does not approve the PR. Surfaces a non-none Version intent from the
    PR body only — omitted or none stays silent; product version file
    edits stay with the merger / product docs.
    """
    root, scope, integration, bw = ctx()
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    pr = (meta.get("pr") or "").strip()

    if meta["status"] in OUT_OF_PLAY:
        sys.exit(f"error: T{tid} is {meta['status']}; revive before landing")
    if meta["status"] == "done":
        print(f"T{tid}: already done — running cleanup only")
        branch = task_branch_name(meta)
        cleanup_task_artifacts(root, scope, bw, meta, branch)
        return

    if meta["status"] == "draft":
        sys.exit(f"error: T{tid} is draft — its author has not asked for "
                 f"review yet. Promote it first: TASKS ready {tid} "
                 f"(the user's call, not an agent's)")

    if not pr:
        # A landed recurring task has no pr: re-arming cleared it. That is the
        # idempotent re-run, not a missing PR — say so instead of asking for
        # one. Never run = a real error (nothing was ever shipped).
        if is_recurring(meta) and (meta.get("last_run") or "").strip():
            print(f"T{tid}: recurring, {last_run_label(meta)} — "
                  f"{land_outcome(meta)}; nothing to land, cleanup only")
            cleanup_task_artifacts(root, scope, bw, meta, task_branch_name(meta))
            return
        sys.exit(f"error: T{tid} has no pr URL; open a PR before land")

    require_gh(root)
    info = pr_view(root, pr)
    state = (info.get("state") or "").upper()
    head = info.get("headRefName") or ""
    base = (info.get("baseRefName") or "").strip()
    body = info.get("body") or ""
    intent = version_intent_bump(parse_version_intent(body))
    branch = task_branch_name(meta, head)
    if not branch:
        sys.exit(f"error: T{tid} has no branch and PR head is empty")

    print(f"T{tid}: land {pr}")
    print(f"  branch: {branch}")
    print(f"  base:   {base or integration}")
    print(f"  state:  {state}")
    if intent:
        print(f"  Version intent: {intent}")

    if pr_is_merged(info):
        print(f"T{tid}: PR already merged — retargeting children, then done")
        retarget_children(root, branch, integration)
        mark_task_done(root, scope, integration, bw, meta)
        # Cleanup keys off the PR URL as merge evidence and ignores status,
        # so hand it the pre-land record: re-arming a recurring task clears
        # pr, which would otherwise leave the branch undeleted.
        cleanup_task_artifacts(root, scope, bw, meta, branch)
        meta = find_task(bw, scope, tid)
        note_version_intent(intent, integration,
                            os.path.abspath(product_root(root, scope)))
        print(f"T{tid}: {land_outcome(meta)}")
        return

    if state == "CLOSED":
        sys.exit(f"error: T{tid} PR is closed without merge: {pr}")

    ident = identity_or_exit(root, scope)
    integrators = board_integrators(read_board_cfg(bw, scope))
    if not integrators:
        sys.exit("error: no integrator configured; cannot land. "
                 "Set: TASKS integrator add <name>")
    if ident not in integrators:
        sys.exit(f"error: only a board integrator can land "
                 f"(whoami='{ident}', integrator: {', '.join(integrators)})")

    if base and base != integration:
        sys.exit(f"error: T{tid} PR base is '{base}', board integration is "
                 f"'{integration}'. Retarget the PR "
                 f"({pr_hint_retarget(pr, integration)}) or fix board "
                 f"config before land.")

    if not has_remote(root):
        sys.exit("error: no origin remote; cannot land")

    # The merge commit carries the PR title in its body (its subject is
    # "Merge pull request #N from …"), so bring the title up to the task's
    # current one first (a retitle after the last ship). Title only; a
    # failed edit only costs the mirror, so it warns.
    prefix = title_prefix(iteration_index(read_board_cfg(bw, scope)), tid,
                          scope)
    want_title = ship_pr_title(meta, prefix)
    if want_title != (info.get("title") or ""):
        r = pr_cmd("edit", pr, "--title", want_title, cwd=root)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            print(f"  warning: could not update the PR title: {err}",
                  file=sys.stderr)
        else:
            print(f"  updated PR title: {want_title}")

    git("fetch", "origin", integration, cwd=root, check=False)
    git("fetch", "origin", branch, cwd=root, check=False)
    # Land never pushes the task branch: it merges what was reviewed.
    merged = False
    last_err = ""
    for attempt in range(1, LAND_RETRIES + 1):
        # Right after a push, mergeable is often UNKNOWN; wait rather than
        # fail once. A merge commit absorbs a behind-but-clean branch, so
        # only a real content conflict reports CONFLICTING.
        readiness = wait_for_pr_mergeable(root, pr)
        if readiness == "MERGED":
            merged = True
            print(f"  PR became merged while waiting (attempt {attempt})")
            break
        if readiness == "CONFLICTING":
            print(f"  PR mergeable=CONFLICTING (attempt {attempt}); "
                  f"merging origin/{integration} forward…")
            if merge_forward_task_branch(root, branch, integration):
                last_err = (f"PR mergeable=CONFLICTING after merging "
                            f"origin/{integration} forward (attempt "
                            f"{attempt})")
            else:
                last_err = (f"PR mergeable=CONFLICTING but '{branch}' "
                            f"already contains origin/{integration}; "
                            f"GitHub may still be recomputing (attempt "
                            f"{attempt})")
                print(f"  already contains origin/{integration}; waiting")
            if attempt < LAND_RETRIES:
                time.sleep(min(2 * attempt, 8))
            continue

        # Merge commit, never squash: the branch's commits must stay in
        # integration's history so stacked children need no rewrite.
        # cleanup handles branch/worktree deletion explicitly.
        r = pr_cmd("merge", pr, "--merge", cwd=root)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode == 0:
            merged = True
            print(f"  merged (attempt {attempt})")
            break
        last_err = out
        low = out.lower()
        if "already merged" in low or "pull request is already merged" in low:
            merged = True
            print(f"  already merged (attempt {attempt})")
            break
        if merge_commits_disallowed(out):
            sys.exit(
                f"error: this repository does not allow merge commits, which "
                f"land requires — squashing would rewrite '{branch}' and "
                f"strand any PR stacked on it.\nEnable 'Allow merge commits' "
                f"in the repository's settings (Settings → General → Pull "
                f"Requests), then re-run land.\n{out}")
        info = pr_view(root, pr)
        if pr_is_merged(info):
            merged = True
            print(f"  PR became merged externally (attempt {attempt})")
            break
        if not merge_error_transient(out):
            sys.exit(merge_fail_permanent_message(out))
        print(f"  merge attempt {attempt} failed (transient); retry…")
        git("fetch", "origin", integration, cwd=root, check=False)
        # A stale branch cannot fix itself by waiting: land never rebases,
        # so merge integration forward (no-op if already contained).
        if merge_error_wants_update(out):
            merge_forward_task_branch(root, branch, integration)
        if attempt < LAND_RETRIES:
            time.sleep(min(2 * attempt, 8))

    if not merged:
        sys.exit(f"error: could not merge T{tid} PR after {LAND_RETRIES} "
                 f"attempts:\n{last_err}")

    # Before cleanup: deleting this branch while a PR is based on it closes
    # that PR (GitHub does not auto-retarget). Fail-closed.
    retarget_children(root, branch, integration)

    integration, bw = resolve_board(root, scope)
    mark_task_done(root, scope, integration, bw, meta)
    # Pre-land record: see the cleanup note on the already-merged path above.
    cleanup_task_artifacts(root, scope, bw, meta, branch)
    meta = find_task(bw, scope, tid)
    note_version_intent(intent, integration,
                        os.path.abspath(product_root(root, scope)))
    print(f"T{tid}: landed and {land_outcome(meta)}")


# ---------- claim (implement setup) ----------

def identity_or_exit(root, scope):
    ident, err = current_identity(root, scope)
    if err:
        sys.exit(f"error: {err}")
    return ident


def resolve_stack_start(root, bw, scope, tid, parent_id, integration):
    """Start ref for `claim --stack-on`: another task's pushed review tip.

    Offered when `collisions` exits 3 and the new task genuinely builds on
    that unmerged code (routes/implement.md); when it does not, claim
    normally and let the two PRs merge independently. The ref is
    origin/<parent branch> — the same tip GitHub will use as the child
    PR's base, so the child's diff is exactly its own commits. Refuses a
    parent with no branch, or one already on integration (nothing left to
    stack on). Initial claim only: resume claims without --stack-on, since
    origin/<integration> is a valid base once the child is ahead of it.
    """
    if parent_id == tid:
        sys.exit(f"error: --stack-on T{tid} is the task itself")
    parent = find_task(bw, scope, parent_id)
    pbranch = task_branch_name(parent)
    if not pbranch:
        sys.exit(f"error: T{parent_id} has no branch; nothing to stack on")
    git("fetch", "origin",
        f"+refs/heads/{pbranch}:refs/remotes/origin/{pbranch}",
        cwd=root, check=False)
    remote = f"origin/{pbranch}"
    if not ref_exists(root, remote):
        sys.exit(f"error: T{parent_id} branch '{pbranch}' is not on origin; "
                 f"nothing to stack on (has it shipped?)")
    if is_ancestor(root, remote, f"origin/{integration}"):
        sys.exit(f"error: T{parent_id} ('{pbranch}') is already on "
                 f"{integration}; claim without --stack-on")
    print(f"note: stacking on T{parent_id} ({parent['status']}, {pbranch})")
    return remote


def claim_unattended_refusal(meta, run):
    """Error text when a claim would resume into a running unattended run's
    work, else ''. Only that run may re-claim it (same model id); the
    owner takes a dead run back by moving the task to backlog."""
    held = task_unattended(meta)
    if not held or held == run:
        return ""
    return (f"error: T{meta['id']} is being worked by an unattended run "
            f"({held}); do not resume into its work. If that run is "
            f"dead, take it back with: update {meta['id']} --status backlog")


def update_unattended_refusal(old, meta, run, status_req):
    """Error text for an update that would set the unattended marker
    wrongly, else ''. `run` is the --unattended value (None when absent,
    '' clears — always allowed, it is how an ops run hands back or the
    owner takes a dead one back in place). A marker is only for a task
    left `doing`. Setting one, or asking for `doing`, is refused while the
    task already holds any marker — the same model id included, unlike
    claim: an ops run starts from a task not yet doing and resumes only
    after handing the marker back, so it never re-stamps, and two sessions
    of one model must not both take the task."""
    if run == "" or (run is None and status_req != "doing"):
        return ""
    if run and meta["status"] != "doing":
        return (f"error: --unattended marks a doing task; pass --status "
                f"doing (T{meta['id']} would be {meta['status']})")
    held = task_unattended(old)
    if not held:
        return ""
    return (f"error: T{meta['id']} is being worked by an unattended run "
            f"({held}); do not start or resume it. If that run is dead, "
            f"take it back where it stopped with: update {meta['id']} "
            f"--unattended \"\"")


def cmd_claim(args):
    """Implement claim/setup: branch from origin/integration, always a
    linked worktree under .dev/worktrees (primary stays on integration as
    hub), record branch + doing + assignee. Resume reuses a branch that is
    at or ahead of origin/integration; empty leftovers are fast-forwarded;
    diverged leftovers error. Printed base is verified. --stack-on <id>
    starts on another task's review tip instead (resolve_stack_start).
    """
    root, scope, integration, bw = ctx()
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    status = meta["status"]

    if status in TERMINAL:
        sys.exit(f"error: T{tid} is {status}; cannot claim")
    if status == "proposed":
        sys.exit(f"error: T{tid} is proposed; approve via review before claim")
    if status in OPEN_PR:
        sys.exit(f"error: T{tid} is in {status}; do not claim — resume via "
                 f"diff (handoff: update --assignee first)")
    if (meta.get("needs") or "").strip() == "decision":
        sys.exit(f"error: T{tid} has needs: decision; resolve before claim")
    if is_umbrella(meta):
        sys.exit(f"error: T{tid} is an umbrella: a goal, not a unit of code. "
                 f"It gets no branch and no PR — run /dev {tid} for "
                 f"the verification pass, and file any real code as a child.")
    if is_ops(meta):
        sys.exit(f"error: T{tid} is an ops task: no branch, no PR — run it "
                 f"with /ops run {tid}. If it needs code, make it a dev task "
                 f"first: update {tid} --type {DEV} --area <name>")
    if not split_areas(meta.get("area", "")):
        sys.exit(f"error: T{tid} has no area; set a real name "
                 f"(reuse or area set) before claim")
    run = (args.unattended or "").strip()
    refusal = claim_unattended_refusal(meta, run)
    if refusal:
        sys.exit(refusal)

    assignee = (args.assignee if args.assignee is not None else "").strip()
    if not assignee:
        assignee = identity_or_exit(root, scope)

    branch = (args.branch or "").strip() or (meta.get("branch") or "").strip()
    if not branch:
        branch = default_task_branch(scope, tid, meta["title"])
        if is_recurring(meta):
            local = git("for-each-ref", "--format=%(refname)",
                        f"refs/heads/{branch}-*", cwd=root, check=False)
            remote = git("ls-remote", "--heads", "origin",
                         f"refs/heads/{branch}-*", cwd=root, check=False)
            taken = {w[len("refs/heads/"):]
                     for w in (local.stdout + remote.stdout).split()
                     if w.startswith("refs/heads/")}
            branch = recurring_run_branch(branch, datetime.date.today(), taken)

    undone = [d for d in meta.get("deps", [])
              if find_task(bw, scope, d)["status"] != "done"]
    if undone:
        print(f"warning: T{tid} has unfinished deps: {undone}", file=sys.stderr)

    if not has_remote(root):
        sys.exit("error: no origin remote; cannot claim from origin/integration")
    git("fetch", "origin", integration, cwd=root, check=False)
    start = f"origin/{integration}"
    if not ref_exists(root, start):
        sys.exit(f"error: {start} missing after fetch")
    if args.stack_on is not None:
        start = resolve_stack_start(
            root, bw, scope, tid, args.stack_on, integration)
    # The task's own recorded branch is a resume, not a leftover: un-claim
    # clears the field, so a branch still recorded is this task's work.
    resume = (meta.get("branch") or "").strip() == branch
    if resume:
        adopt_pushed_task_branch(root, branch)

    ensure_task_branch(root, branch, start, resume=resume)
    ready = resolve_task_ready_path(
        root, scope, tid, meta["title"], branch, integration)
    base = verified_claim_base(root, branch, start, resume=resume)

    # Refresh meta after git work (board may have moved on shared integration).
    integration, bw = resolve_board(root, scope)
    meta = find_task(bw, scope, tid)
    # An unattended run may have claimed it during the git work: never
    # overwrite its marker.
    refusal = claim_unattended_refusal(meta, run)
    if refusal:
        sys.exit(refusal)
    changes = []
    if meta["status"] != "doing":
        meta["status"] = "doing"
        changes.append("status=doing")
    if meta.get("assignee") != assignee:
        meta["assignee"] = assignee
        changes.append(f"assignee={assignee}")
    if meta.get("branch") != branch:
        meta["branch"] = branch
        changes.append(f"branch={branch}")
    if run and meta.get("unattended") != run:
        meta["unattended"] = run
        changes.append(f"unattended={run}")
    if changes:
        with open(meta["path"], "w", newline="\n") as f:
            f.write(render_task(meta))
        board_commit(root, integration, bw, scope,
                     f"dev: update T{tid} ({', '.join(changes)})")
        print(f"T{tid} updated: {', '.join(changes)}")
    else:
        print(f"T{tid}: already claimed (doing, {assignee}, {branch})")

    print(f"T{tid}: ready")
    print(f"  branch:  {branch}")
    print(f"  workdir: {shown_path(ready)}")
    print(f"  product: {shown_path(product_root(ready, scope))}")
    print(f"  base:    {base}")


# ---------- ship (implement: commit, push, open PR) ----------

def path_is_tasks_dir(path):
    """True if path is inside a .tasks, .flows or .catalog directory (board
    state — must not ship on a code branch)."""
    norm = path.replace("\\", "/")
    return bool(re.search(r"(^|/)\.(tasks|flows|catalog)(/|$)", norm))


def path_under_task_worktrees(root, scope, path):
    """True if path is under <product>/.dev/worktrees/ (claim policy)."""
    wt_root = path_key(
        os.path.join(product_root(root, scope), ".dev", "worktrees"))
    try:
        real = path_key(path)
    except OSError:
        return False
    try:
        return os.path.commonpath([wt_root, real]) == wt_root
    except ValueError:
        return False


def find_open_pr_for_branch(root, branch, base="", *, strict=False):
    """Return PR url for an open PR with this head branch, or ''.

    A falsy ``base`` matches any base — the caller has not fixed one yet,
    and land retargets a stacked PR's base anyway, so the head branch is
    the stable identity. A failed lookup also returns '' unless
    ``strict`` (any-base only), which exits instead: '' must then mean
    nothing is open, not that nobody could tell.
    """
    if not base:
        r = pr_cmd("list", "--head", branch, "--state", "open",
               "--json", "url", "--limit", "5", cwd=root)
        try:
            items = json.loads(r.stdout or "[]") if r.returncode == 0 \
                else None
        except json.JSONDecodeError:
            items = None
        if not isinstance(items, list):
            if strict:
                err = (r.stderr or r.stdout or "").strip()
                sys.exit(f"error: could not look up the open PR on "
                         f"'{branch}' ({pr_call_label('list')} failed):\n"
                         f"{err}")
            return ""
        return (items[0].get("url") or "").strip() if items else ""
    r = pr_cmd("list", "--head", branch, "--base", base, "--state", "open",
           "--json", "url,number", "--limit", "5", cwd=root)
    if r.returncode != 0:
        return ""
    try:
        items = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return ""
    if not items:
        r = pr_cmd("list", "--head", branch, "--state", "open",
               "--json", "url,baseRefName", "--limit", "5", cwd=root)
        if r.returncode != 0:
            return ""
        try:
            items = json.loads(r.stdout or "[]")
        except json.JSONDecodeError:
            return ""
        items = [i for i in items if (i.get("baseRefName") or "") == base]
    if not items:
        return ""
    return (items[0].get("url") or "").strip()


def attach_review_branch(root, scope, tid, title, branch, integration):
    """Attach a recorded draft/review branch. Never create from integration."""
    remote = f"origin/{branch}"
    if has_remote(root):
        git("fetch", "origin",
            f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
            cwd=root, check=False)
    if not ref_exists(root, remote):
        sys.exit(f"error: T{tid} has shipped but '{branch}' is not "
                 f"checked out and {remote} is missing")
    sync_task_branch_from_remote(root, branch)
    ready = resolve_task_ready_path(
        root, scope, tid, title, branch, integration)
    print(f"note: attached review branch '{branch}'")
    return ready


def ship_work_cwd(root, scope, meta, branch, integration):
    """Directory that has the task branch checked out for committing/pushing.

    Prefer a claim-style linked worktree under .dev/worktrees/; fall back to
    any checkout of the branch. A shipped task (draft/review) with no
    checkout attaches origin/<branch> (never created from integration).
    Soft-warn when not under .dev/worktrees/.
    """
    work = None
    for path in find_task_worktree_paths(root, scope, meta["id"], branch):
        if current_branch_name(path) != branch:
            continue
        if path_under_task_worktrees(root, scope, path):
            return path
        if work is None:
            work = path
    if work is None:
        work = branch_checkout_cwd(root, branch)
    if not work:
        if (meta.get("status") or "").strip() in OPEN_PR:
            return attach_review_branch(
                root, scope, meta["id"], meta["title"], branch, integration)
        sys.exit(f"error: task branch '{branch}' is not checked out anywhere; "
                 f"run claim first")
    if not path_under_task_worktrees(root, scope, work):
        print(f"warning: shipping from {shown_path(work)} (not under "
              f"<scope>/.dev/worktrees/); prefer the claim workdir",
              file=sys.stderr)
    return work


def cmd_diff(args):
    """Self-review: location + diff from the task worktree, not session cwd."""
    root, scope, integration, bw = ctx()
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    branch = task_branch_name(meta)
    if not branch:
        if meta["status"] in OPEN_PR:
            sys.exit(f"error: T{tid} is in {meta['status']} with no branch")
        sys.exit(f"error: T{tid} has no branch; run claim first")
    work = ship_work_cwd(root, scope, meta, branch, integration)

    print(f"T{tid}: diff")
    print(f"  workdir: {shown_path(work)}")
    print(f"  product: {shown_path(product_root(work, scope))}")
    print(f"  branch:  {branch}")
    # Diff against what the PR is (or will be) based on: a stacked task
    # measured against integration shows its parent's files as its own.
    # An open PR's base is authoritative (--base, land's retarget);
    # before the PR exists, ship's own derivation says what it will be.
    base_branch = ""
    pr_url = (meta.get("pr") or "").strip()
    if pr_url:
        info = pr_view(root, pr_url, soft=True) or {}
        if (info.get("state") or "").upper() == "OPEN":
            base_branch = (info.get("baseRefName") or "").strip()
    if not base_branch:
        base_branch = derive_stack_base(root, bw, scope, meta, branch,
                                        integration, soft=True)
    base_branch = base_branch or integration
    base = f"origin/{base_branch}"
    if not ref_exists(root, base):
        base = base_branch
        if not ref_exists(root, base):
            sys.exit(f"error: no {base} to diff against")
    print(f"  base:    {base}")

    st = git("status", "--porcelain", cwd=work, check=False)
    if st.returncode != 0:
        err = (st.stderr or st.stdout or "").strip()
        sys.exit(f"error: git status failed in {work}:\n{err}")
    porcelain = st.stdout or ""
    if porcelain.strip():
        print("uncommitted:")
        sys.stdout.write(porcelain)
        if not porcelain.endswith("\n"):
            sys.stdout.write("\n")
        tracked = git("diff", "HEAD", cwd=work, check=False)
        if tracked.returncode != 0:
            err = (tracked.stderr or tracked.stdout or "").strip()
            sys.exit(f"error: git diff HEAD failed in {work}:\n{err}")
        if (tracked.stdout or "").strip():
            sys.stdout.write(tracked.stdout)
            if not tracked.stdout.endswith("\n"):
                sys.stdout.write("\n")
    else:
        print("uncommitted: (none)")

    print(f"vs {base}:")
    r = git("diff", f"{base}...HEAD", cwd=work, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        sys.exit(f"error: git diff {base}...HEAD failed:\n{err}")
    out = r.stdout or ""
    if out.strip():
        sys.stdout.write(out)
        if not out.endswith("\n"):
            sys.stdout.write("\n")
    else:
        print("(none)")


def commits_ahead(root, branch, base_ref):
    """Commits on branch not in base_ref, or None if rev-list failed."""
    r = git("rev-list", "--count", f"{base_ref}..{branch}", cwd=root,
            check=False)
    if r.returncode != 0:
        return None
    s = (r.stdout or "").strip()
    if not s.isdigit():
        return None
    return int(s)


# ---------- Dev-batch stamp + restack / batch-gate ----------

DEV_BATCH_RE = re.compile(
    r"(?im)^[ \t]*Dev-batch:[ \t]*([0-9]+(?:[ \t]*,[ \t]*[0-9]+)*)[ \t]*(?=\r?$)")


def parse_id_list(s):
    """Parse '1,2,3' or '1 2 3' into a sorted unique list of ints."""
    if not s:
        return []
    ids = [int(x) for x in re.findall(r"\d+", str(s))]
    return sorted(set(ids))


def format_dev_batch(ids):
    """Machine line: Dev-batch: 19,20,22,23 (sorted)."""
    ids = sorted(set(int(i) for i in ids))
    return "Dev-batch: " + ",".join(str(i) for i in ids)


def parse_dev_batch(text):
    """Extract Dev-batch ids from task body or PR body, or []."""
    if not text:
        return []
    m = DEV_BATCH_RE.search(text)
    if not m:
        return []
    return parse_id_list(m.group(1))


def ensure_dev_batch_in_text(text, ids):
    """Insert or replace Dev-batch line; returns new text."""
    line = format_dev_batch(ids)
    text = text or ""
    if DEV_BATCH_RE.search(text):
        return DEV_BATCH_RE.sub(line, text, count=1)
    return text.rstrip() + ("\n\n" if text.strip() else "") + line + "\n"


# ---------- shipped-state record ----------

# One record per ship, as its own paragraph in the task body:
#   Shipped (2026-08-12): what actually landed, not what was planned.
SHIPPED_RE = re.compile(
    r"(?ims)^Shipped \(\d{4}-\d{2}-\d{2}\):.*?(?=\n[ \t]*\n|\Z)")


# One shipped record, split into its date and text.
SHIPPED_PARTS_RE = re.compile(r"^Shipped \((\d{4}-\d{2}-\d{2})\):[ \t]*(.*)$",
                              re.S | re.I)


def format_shipped(text, date=None):
    """One shipped record. Collapsed to a single paragraph so it parses back."""
    text = " ".join((text or "").split())
    date = date or datetime.date.today().isoformat()
    return f"Shipped ({date}): {text}"


def collect_shipped(text):
    """Every shipped record in a task or PR body, in order."""
    return [m.group(0).strip() for m in SHIPPED_RE.finditer(text or "")]


# ---------- verified record (umbrella close) ----------

# An umbrella never ships, so its close carries its own record instead:
#   Verified (2026-08-22): how the children actually met the goal.
VERIFIED_RE = re.compile(
    r"(?ims)^Verified \(\d{4}-\d{2}-\d{2}\):.*?(?=\n[ \t]*\n|\Z)")


def format_verified(text, date=None):
    """One verification record, collapsed to a single paragraph."""
    text = " ".join((text or "").split())
    date = date or datetime.date.today().isoformat()
    return f"Verified ({date}): {text}"


def collect_verified(text):
    """Every verification record in a task body, in order."""
    return [m.group(0).strip() for m in VERIFIED_RE.finditer(text or "")]


# ---------- ran record (ops run close) ----------

# An ops task never ships; its close records the run instead:
#   Ran (2026-09-18): [7 send-invoice] inputs: client=acme; deviations: none.
# `[no flow]` marks a run that followed no stored flow (the chunked loop).
RAN_RE = re.compile(
    r"(?ims)^Ran \(\d{4}-\d{2}-\d{2}\)[:.].*?(?=\n[ \t]*\n|\Z)")


def format_ran(text, refs, date=None, verb="Ran"):
    """One run record (or, with verb="Rehearsed", one rehearsal record),
    collapsed to a single paragraph."""
    text = " ".join((text or "").split())
    date = date or datetime.date.today().isoformat()
    tag = ", ".join(refs) if refs else "no flow"
    return f"{verb} ({date}): [{tag}] {text}"


def collect_ran(text):
    """Every run record in a task body, in order (bare `Ran (<date>).` lines
    from landed recurring runs included)."""
    return [m.group(0).strip() for m in RAN_RE.finditer(text or "")]


# A rehearsal (a dry run of a flow, `ran --rehearsal`) closes with its own
# verb rather than a tag inside Ran, so a Ran reader skips it without
# knowing; the ones that must show it (run history, log.md) opt in:
#   Rehearsed (2026-10-29): [7 send-invoice] dry: steps 4, 6; …
REHEARSED_RE = re.compile(
    r"(?ims)^Rehearsed \(\d{4}-\d{2}-\d{2}\):.*?(?=\n[ \t]*\n|\Z)")


def collect_rehearsed(text):
    """Every rehearsal record in a task body, in order."""
    return [m.group(0).strip() for m in REHEARSED_RE.finditer(text or "")]


# ---------- distilled record (what a distill sitting covered) ----------

# A distill sitting (a `distill: true` ops task) records, after each reply
# from the user, the tasks whose every candidate the user has now dealt with
# (approved, declined or edited) — `distilled <sitting> <ids>`, ranges
# compacted; `ran` on the sitting adds one for itself and its dependents
# (the task it filed, which depends on it). A sitting stopped partway leaves the rest uncovered:
#   Distilled (2026-11-20): T3-T7, T9, T12
# iteration-close refuses while a done or not-planned task on the live board
# is in no such line. Ids renumber at every iteration boundary, so reseed
# strips these lines from every copy it makes (strip_distilled).
DISTILLED_RE = re.compile(
    r"(?im)^Distilled \(\d{4}-\d{2}-\d{2}\):[ \t]*(.*)$")
DISTILLED_PARA_RE = re.compile(r"^Distilled \(\d{4}-\d{2}-\d{2}\):")
DISTILLED_TOKEN_RE = re.compile(r"^[Tt]?(\d+)(?:-[Tt]?(\d+))?$")


def parse_distilled_spec(s):
    """'T3-T7, 9, T12' (or '3-7 9 12') into a sorted unique id list.
    Raises ValueError naming the first bad token."""
    ids = set()
    s = re.sub(r"\s*-\s*", "-", (s or "").strip())
    for tok in re.split(r"[,\s]+", s):
        tok = tok.strip()
        if not tok:
            continue
        m = DISTILLED_TOKEN_RE.match(tok)
        if not m:
            raise ValueError(tok)
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        if hi < lo:
            raise ValueError(tok)
        ids.update(range(lo, hi + 1))
    return sorted(ids)


def format_distilled(ids, date=None):
    """One Distilled line, consecutive ids compacted into ranges."""
    ids = sorted(set(int(i) for i in ids))
    date = date or datetime.date.today().isoformat()
    runs = []
    for i in ids:
        if runs and i == runs[-1][1] + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    parts = [f"T{a}" if a == b else f"T{a}-T{b}" for a, b in runs]
    return f"Distilled ({date}): " + ", ".join(parts)


def distilled_ids(text):
    """Every id the Distilled lines in a body name (a bad line counts for
    nothing rather than stopping a close)."""
    ids = set()
    for m in DISTILLED_RE.finditer(text or ""):
        try:
            ids.update(parse_distilled_spec(m.group(1)))
        except ValueError:
            continue
    return ids


def strip_distilled(body):
    """A body without its Distilled paragraphs: for any copy reseed puts on
    the next board, where the ids they name belong to other tasks."""
    paras = [p.strip() for p in re.split(r"\n[ \t]*\n", body or "")]
    return "\n\n".join(p for p in paras
                        if p and not DISTILLED_PARA_RE.match(p))


def distill_coverage_missing(tasks):
    """Ids of done or not-planned non-recurring tasks that no Distilled line
    on the board names — what iteration-close refuses on."""
    covered = set()
    for t in tasks:
        covered |= distilled_ids(t.get("body"))
    return sorted(t["id"] for t in tasks
                  if t.get("status") in ("done", "not-planned")
                  and not is_recurring(t) and t["id"] not in covered)


def distill_close_ids(meta, tasks):
    """What `ran` on a distill sitting covers: the sitting and every task
    that lists it in its deps (the task it filed). An umbrella is left out:
    its deps are its children, so listing the sitting files nothing."""
    return sorted({meta["id"]} | {
        t["id"] for t in tasks
        if meta["id"] in (t.get("deps") or [])
        and (t.get("kind") or "").strip() != "umbrella"})


def distilled_refusal(ids, tasks, self_id):
    """Why a Distilled line may not name this id list, or None. Each id must be
    a non-recurring task on the live board, any status (a sitting lists the
    task it filed, still open), or the sitting itself. A recurring task is
    never distilled: it carries its records across and the gate skips it."""
    if not ids:
        return "no task ids named"
    by_id = {t["id"]: t for t in tasks}
    bad = []
    for i in ids:
        if i == self_id:
            continue
        t = by_id.get(i)
        if t is None:
            bad.append(f"T{i} (not on this board)")
        elif is_recurring(t):
            bad.append(f"T{i} (recurring)")
    if bad:
        return ("a Distilled line names only non-recurring tasks on this "
                "board or the sitting itself; not: " + ", ".join(bad))
    return None


def distilled_verb_line(meta, spec, tasks, date=None):
    """`distilled <sitting> <ids>`: (the Distilled line to append, None) or
    (None, why it is refused)."""
    if not is_distill(meta):
        return None, (f"T{meta['id']} is not a distill sitting (distill: "
                      f"true); only a sitting records what it distilled")
    try:
        ids = parse_distilled_spec(spec)
    except ValueError as e:
        return None, f"bad id or range '{e}' (use e.g. \"T3-T7, T9\")"
    why = distilled_refusal(ids, tasks, meta["id"])
    if why:
        return None, why
    return format_distilled(ids, date), None


def ran_distilled_line(meta, tasks, date):
    """The Distilled line `ran` appends on a distill sitting (the sitting and
    its dependents, the task it filed), as (line, None); (None, None) on any
    other task; (None, why) when a dependent cannot be named."""
    if not is_distill(meta):
        return None, None
    ids = distill_close_ids(meta, tasks)
    why = distilled_refusal(ids, tasks, meta["id"])
    if why:
        return None, (f"T{meta['id']} is a distill sitting, so ran records "
                      f"it and the tasks that depend on it as distilled; "
                      f"{why}")
    return format_distilled(ids, date), None


# ---------- paused record (ops run stopped partway) ----------

# A run that stops mid-flow and will be picked up in a later session, or on
# another machine, records where it stopped and what it has produced:
#   Paused (2026-09-29): [7 send-invoice step 4] invoice drafted on `laptop`…
# It is not an outcome: the task stays `doing`, `ran` still closes it, and
# nothing collects these into log.md — the closing record is the trace that
# outlives the task. Only written on the user's explicit call, or where an
# unattended dev run parks, so an ordinary run that finishes in one sitting
# carries none. On a dev task it also commits and pushes the branch.
def format_paused(text, refs, at, date=None):
    """One pause record, collapsed to a single paragraph."""
    text = " ".join((text or "").split())
    at = " ".join((at or "").split())
    date = date or datetime.date.today().isoformat()
    tag = ", ".join(refs) if refs else "no flow"
    return f"Paused ({date}): [{tag} {at}] {text}"


# ---------- note record (what an ops run's flow did not predict) ----------

# A line of run history the flow could not have told you: a step the user
# did themselves, a step inserted mid-run, a correction.
#   Note (2026-09-29): [7 send-invoice step 4] user phoned the vendor…
# Like a pause it is not an outcome — nothing collects it into log.md — but
# it is what the closing record's deviations, the post-run flow tweak and
# `flow create from <id>` read. Steps that went as written get none.
def format_note(text, refs, at, date=None):
    """One note, collapsed to a single paragraph; the tag is dropped when
    there is neither a flow nor a step to name."""
    text = " ".join((text or "").split())
    at = " ".join((at or "").split())
    date = date or datetime.date.today().isoformat()
    tag = " ".join(x for x in (", ".join(refs), at) if x)
    return f"Note ({date}): [{tag}] {text}" if tag else f"Note ({date}): {text}"


# ---------- waiting record (work awaiting someone outside) ----------

# A run (or a dev task following a flow) that reaches an [external] step,
# or a run that handed a sequence to an agent who reports later — the next
# move belongs to someone outside, days out — records who it waits
# on and when the reply is due:
#   Waiting (2026-10-21): [7 file-permit step 5] on county clerk by
#   2026-11-04 — application submitted via the portal…
# and sets the task's `waiting: <who> by <date>` marker, which is what the
# board reads. Like a pause the task stays doing and nothing collects the
# record into log.md; unlike a pause the marker is board-visible state.
WAITING_RE = re.compile(r"^(.*\S)\s+by\s+(\d{4}-\d{2}-\d{2})$")


def waiting_allowed(t):
    return t.get("status") == "doing"


def task_waiting(t):
    """(who, expected-by date) for a run awaiting someone outside, else None.

    None too for a marker on a task that may not carry one, or one that does
    not parse — the board must never crash on a hand-edited file.
    """
    m = WAITING_RE.match((t.get("waiting") or "").strip())
    if not m or not waiting_allowed(t):
        return None
    try:
        return m.group(1), datetime.date.fromisoformat(m.group(2))
    except ValueError:
        return None


def task_unattended(t):
    """Model id of the unattended run working this task, else ''. Like
    waiting, only a doing task carries one."""
    return (t.get("unattended") or "").strip() if waiting_allowed(t) else ""


def waiting_sort_rank(t):
    """Tiebreak within one status: actionable first, then waiting runs,
    soonest expected-by first."""
    w = task_waiting(t)
    return (0, datetime.date.min) if w is None else (1, w[1])


def format_waiting(text, refs, at, who, by, date=None):
    """One waiting record, collapsed to a single paragraph."""
    text = " ".join((text or "").split())
    at = " ".join((at or "").split())
    date = date or datetime.date.today().isoformat()
    tag = ", ".join(refs) if refs else "no flow"
    return f"Waiting ({date}): [{tag} {at}] on {who} by {by} — {text}"


def ensure_shipped_in_text(text, records):
    """Replace the shipped records in text with `records`, appended at the end.

    Marker-free and idempotent like ensure_dev_batch_in_text: re-shipping
    rewrites the block rather than stacking duplicates onto the PR body.
    """
    text = re.sub(r"\n{3,}", "\n\n", SHIPPED_RE.sub("", text or "")).strip()
    if not records:
        return text + "\n" if text else ""
    block = "\n\n".join(records)
    return (text + "\n\n" + block if text else block) + "\n"


def ship_pr_title(meta, prefix, title=None):
    """PR title a ship writes: `title`, else the task title, prefixed."""
    text = (title or "").strip() or f"{prefix} {meta['title']}"
    return with_title_prefix(text, prefix, meta["id"])


def ship_pr_body(meta, shipped_records, body=None, version_intent=None,
                 batch_ids=(), pr_body=None):
    """PR body a ship writes: `body`, else the task body, then the machine
    lines and the shipped block. On a re-ship `pr_body` is the live PR body,
    whose Dev-batch and Version intent lines carry over unless a flag (or a
    line in `body`) sets them — the opening is rebuilt from the task."""
    text = (body or "").strip() or (meta.get("body") or "").strip() \
        or meta["title"]
    if pr_body is not None:
        if version_intent is None and parse_version_intent(text) is None:
            version_intent = parse_version_intent(pr_body)
        if not batch_ids and not parse_dev_batch(text):
            batch_ids = parse_dev_batch(pr_body)
    if version_intent is not None:
        text = set_version_intent_in_text(text, version_intent)
    if batch_ids:
        text = ensure_dev_batch_in_text(text, batch_ids)
    return ensure_shipped_in_text(text, shipped_records)


def pr_is_open(info):
    if not info:
        return False
    return (info.get("state") or "").upper() == "OPEN" and not pr_is_merged(info)


def load_task_pr_stack_info(root, bw, scope, tid):
    """Return dict: id, branch, pr, base, head, open, body, status, deps."""
    meta = find_task(bw, scope, tid)
    pr = (meta.get("pr") or "").strip()
    branch = task_branch_name(meta)
    info = pr_view(root, pr, soft=True) if pr else None
    base = ((info or {}).get("baseRefName") or "").strip()
    head = ((info or {}).get("headRefName") or "").strip() or branch
    body = (info or {}).get("body") or ""
    return {
        "id": tid,
        "meta": meta,
        "status": meta.get("status") or "",
        "branch": branch,
        "pr": pr,
        "base": base,
        "head": head,
        "open": pr_is_open(info),
        "body": body,
        "deps": list(meta.get("deps") or []),
        "task_body": meta.get("body") or "",
    }


def review_stack_infos(root, bw, scope):
    """PR/stack info for every task with an open PR, keyed by id.

    Draft included: a child in review can be stacked on a draft parent,
    and that is precisely the land order batch-gate must refuse.
    """
    infos = {}
    for t in all_tasks(bw, scope):
        if t["status"] in OPEN_PR:
            infos[t["id"]] = load_task_pr_stack_info(root, bw, scope, t["id"])
    return infos


def batch_gate_missing_parents(selected, infos, parent_map):
    """(child, parent) pairs where an open stack ancestor of a selected task
    is not selected — the hard refuse in batch-gate."""
    selected_set = set(selected)
    missing = []
    for tid in selected:
        cur, seen = tid, {tid}
        while cur in parent_map:
            parent = parent_map[cur]
            if parent in seen:
                break
            seen.add(parent)
            if parent not in selected_set and infos.get(parent, {}).get("open"):
                missing.append((cur, parent))
            cur = parent
    return missing


def batch_gate_missing_members(selected, infos):
    """Open Dev-batch co-members of a selected task left out of the
    selection — the batch-gate advisory. `infos` must hold every selected
    id."""
    selected_set = set(selected)
    missing = set()
    for tid in selected:
        info = infos[tid]
        stamped = parse_dev_batch(info["body"]) or parse_dev_batch(
            info["task_body"])
        for other in stamped:
            if other in selected_set:
                continue
            if infos.get(other, {}).get("open"):
                missing.add(other)
    return missing


def cmd_batch_gate(args):
    """Gate a review selection: refuse a missing stack parent, warn on a
    partial Dev-batch.

    Landing merges without rewriting siblings, so a partial batch is only
    an advisory (they shipped together and share one version bump). The one
    order that still breaks is landing a child before the parent its PR is
    based on — that stays a hard refuse (exit 2).
    """
    root, scope, integration, bw = ctx()
    selected = parse_id_list(args.ids or "")
    if not selected:
        sys.exit("error: batch-gate requires --ids <id,id,…>")

    require_gh(root)
    for tid in selected:
        try:
            find_task(bw, scope, tid)
        except SystemExit:
            sys.exit(f"error: no task with id {tid}")

    infos = review_stack_infos(root, bw, scope)
    parent_map = build_stack_parent_map(infos, integration)
    selected_set = set(selected)
    missing_parents = batch_gate_missing_parents(selected, infos, parent_map)
    if missing_parents:
        print("batch-gate: stack parent missing — a child cannot land "
              "before its parent:")
        for child, parent in missing_parents:
            print(f"  T{child} is stacked on T{parent} "
                  f"(PR base {infos[parent]['branch']})")
        required = sorted(selected_set | {p for _, p in missing_parents})
        print(f"  re-run: /dev review "
              f"{','.join(str(i) for i in required)}")
        sys.exit(2)

    # Deferred past the refuse so that path makes no gh calls; a selected
    # task with no open PR still needs its Dev-batch stamp for the advisory.
    for tid in selected:
        if tid not in infos:
            infos[tid] = load_task_pr_stack_info(root, bw, scope, tid)
    batch_missing = batch_gate_missing_members(selected, infos)
    if batch_missing:
        print("batch-gate: partial batch — these shipped together and share "
              "one version bump:")
        print(f"  not selected: "
              f"{', '.join(f'T{i}' for i in sorted(batch_missing))}")
        print(f"  review the set: /dev review "
              f"{','.join(str(i) for i in sorted(selected_set | batch_missing))}")
        return

    print(f"batch-gate: ok — {', '.join(f'T{i}' for i in selected)}")


def build_stack_parent_map(infos, integration):
    """Map child_id -> parent_id when child's PR base is parent's branch."""
    by_branch = {}
    for tid, inf in infos.items():
        b = (inf.get("branch") or inf.get("head") or "").strip()
        if b:
            by_branch[b] = tid
    parent = {}
    for tid, inf in infos.items():
        base = (inf.get("base") or "").strip()
        if not base or base == integration:
            continue
        p = by_branch.get(base)
        if p is not None and p != tid:
            parent[tid] = p
    return parent


def topo_order_ids(ids, parent_map, dep_edges):
    """Topo order: parents/deps before children. Tie-break lower id."""
    ids = sorted(set(ids))
    # edges: A -> B means A before B (B depends on A)
    preds = {i: set() for i in ids}
    for i in ids:
        p = parent_map.get(i)
        if p in preds:
            preds[i].add(p)
        for d in dep_edges.get(i, []):
            if d in preds:
                preds[i].add(d)
    ordered = []
    ready = sorted(i for i, ps in preds.items() if not ps)
    seen = set()
    while ready:
        n = ready.pop(0)
        if n in seen:
            continue
        seen.add(n)
        ordered.append(n)
        for i, ps in preds.items():
            if n in ps:
                ps.discard(n)
                if not ps and i not in seen:
                    ready.append(i)
        ready.sort()
    if len(ordered) != len(ids):
        cycle = sorted(set(ids) - set(ordered))
        label = ", ".join(f"T{i}" for i in cycle)
        sys.exit(f"error: cycle in restack set among {label}")
    return ordered


def descendants_of(parent_map, root_id, ids):
    """Ids in set that are stack-descendants of root_id (not including root)."""
    children = {i: [] for i in ids}
    for c, p in parent_map.items():
        if c in children and p in children:
            children[p].append(c)
    out = []
    stack = list(children.get(root_id, []))
    seen = set()
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
        stack.extend(children.get(n, []))
    return out


def cmd_restack(args):
    """Fail-closed stack restack for a Dev-batch / stack set.

    Prints a plan, then applies unless --dry-run. force-with-lease only;
    dirty worktrees refuse (except an in-progress rebase); conflicts leave
    the rebase in the worktree and stop (earlier plan steps may already
    be force-pushed — resolve, git add, re-run restack to continue;
    already-up-to-date members no-op). Rewritten local commits that look
    ahead of origin are kept and force-pushed, not refused. When a
    member's stack parent is outside --ids, rebases onto integration and
    auto-retargets the PR base (land-safe default); --onto / --retarget
    still force retarget. --onto rebases every target onto that ref
    (does not cascade children onto restacked parents); omit it to
    preserve in-set stack parents. Moving onto a different ref uses
    `rebase --onto` excluding the old PR base tip so a rewritten parent's
    commits are not replayed.
    """
    root, scope, integration, bw = ctx()
    ids = parse_id_list(args.ids or "")
    if not ids:
        sys.exit("error: restack requires --ids <id,id,…>")
    require_gh(root)
    if not has_remote(root):
        sys.exit("error: no origin remote; cannot restack")

    after = args.after
    onto = (args.onto or "").strip()
    dry = bool(args.dry_run)
    retarget = bool(args.retarget)

    # Never rewrite integration as a task branch.
    for tid in ids:
        meta = find_task(bw, scope, tid)
        b = task_branch_name(meta)
        if b and b == integration:
            sys.exit(f"error: T{tid} branch is integration '{integration}'; "
                     "refusing restack")

    git("fetch", "origin", cwd=root, check=False)
    infos = {tid: load_task_pr_stack_info(root, bw, scope, tid) for tid in ids}
    parent_map = build_stack_parent_map(infos, integration)
    dep_edges = {tid: infos[tid]["deps"] for tid in ids}

    if after is not None:
        if after not in ids:
            sys.exit(f"error: --after {after} is not in --ids")
        targets = descendants_of(parent_map, after, ids)
        if not targets:
            print(f"restack: no stack descendants of T{after} in the set")
            return
    else:
        targets = list(ids)

    order = topo_order_ids(targets, parent_map, dep_edges)

    plan = []
    for tid in order:
        inf = infos[tid]
        branch = inf["branch"]
        if not branch:
            sys.exit(f"error: T{tid} has no branch recorded")
        if onto:
            upstream = onto if onto.startswith("origin/") else (
                f"origin/{onto}" if ref_exists(root, f"origin/{onto}") else onto)
            new_base_for_pr = onto[len("origin/"):] if onto.startswith(
                "origin/") else onto
        else:
            p = parent_map.get(tid)
            if p is not None:
                pbranch = infos[p]["branch"]
                upstream = (f"origin/{pbranch}"
                            if ref_exists(root, f"origin/{pbranch}")
                            else pbranch)
                new_base_for_pr = pbranch
            else:
                upstream = f"origin/{integration}"
                new_base_for_pr = integration
        # Retarget when: explicit --retarget / --onto, or land-safe default —
        # stack parent is outside the set so we rebase onto integration while
        # the PR still targets a sibling (or other non-integration) base.
        old_base = (inf.get("base") or "").strip()
        want_retarget = bool(retarget or onto)
        if (not want_retarget
                and new_base_for_pr == integration
                and old_base and old_base != integration):
            want_retarget = True
        planned_new_base = new_base_for_pr if want_retarget else old_base
        exclude = ""
        if old_base and ref_short_name(old_base) != ref_short_name(upstream):
            exclude = old_base
        plan.append({
            "id": tid,
            "branch": branch,
            "upstream": upstream,
            "pr": inf["pr"],
            "old_base": old_base,
            "exclude": exclude,
            "new_base": planned_new_base,
            "retarget": want_retarget and old_base != planned_new_base,
        })

    print("restack plan:")
    for step in plan:
        rflag = f" retarget-base→{step['new_base']}" if step.get("retarget") else ""
        xflag = f" excluding {step['exclude']}" if step.get("exclude") else ""
        print(f"  T{step['id']}: {step['branch']} onto {step['upstream']}"
              f"{xflag}{rflag}")
    if dry:
        print("restack: dry-run only (no changes)")
        return

    for step in plan:
        tid = step["id"]
        branch = step["branch"]
        upstream = step["upstream"]
        # Dirty check on any checkout of the branch. An in-progress rebase
        # is dirty by definition; restack continues it rather than refusing.
        checkout = branch_checkout_cwd(root, branch)
        if (checkout and worktree_is_dirty(checkout)
                and not rebase_in_progress(checkout)):
            sys.exit(f"error: T{tid} worktree dirty at {checkout}; "
                     "commit/stash before restack")
        exclude = step.get("exclude") or None
        onto = f"{upstream} (excluding {exclude})" if exclude else upstream
        print(f"restack T{tid}: rebase {branch} onto {onto}…")
        try:
            rewritten = rebase_task_onto_ref(
                root, branch, upstream, old_base=exclude)
        except SystemExit:
            raise
        local_sha = git("rev-parse", branch, cwd=root).stdout.strip()
        remote = f"origin/{branch}"
        remote_sha = (git("rev-parse", remote, cwd=root).stdout.strip()
                      if ref_exists(root, remote) else "")
        if rewritten or (remote_sha and local_sha != remote_sha):
            print(f"  rewritten; push --force-with-lease")
            push_task_branch(root, branch, force=True)
        else:
            print(f"  already up to date with {upstream}")
            push_task_branch(root, branch, force=False)
        if step.get("retarget") and step["pr"] and step["new_base"]:
            if step["old_base"] != step["new_base"]:
                r = pr_cmd("edit", step["pr"], "--base", step["new_base"],
                       cwd=root)
                if r.returncode != 0:
                    err = (r.stderr or r.stdout or "").strip()
                    sys.exit(f"error: could not retarget T{tid} PR base to "
                             f"{step['new_base']}:\n{err}")
                print(f"  PR base {step['old_base'] or '?'} → {step['new_base']}")
    print("restack: done")


def derive_stack_base(root, bw, scope, meta, branch, integration, *,
                      soft=False):
    """PR base for a stacked task branch, or '' when it stands alone.

    A collision-driven stack stores nothing: the stack edge is the PR
    base, and before the PR exists git already knows it. Another live task
    branch is this branch's stack parent when its tip is an ancestor of
    this branch but has not reached origin/<integration> — those commits
    can only be here because this branch started on that one. The test is
    directional on purpose: merge-base alone is symmetric and would make a
    parent adopt its own child as base. Once the parent lands, its commits
    become ancestors of integration, the test goes false on its own, and
    ship bases on integration — that is the whole destack-at-ship step,
    with no marker to keep in sync. Deepest match wins, so a three-deep
    stack bases on its direct parent.

    A branch that shares unmerged commits with neither tip based on the
    other (one of them moved after the fork) is ambiguous — git cannot
    tell which side moved, and the error must not blame one — so ship
    refuses and asks for an explicit --base rather than opening a PR
    whose diff silently contains someone else's commits. soft=True (diff,
    which only reads) warns and returns '' instead.
    """
    remote_int = f"origin/{integration}"
    if not ref_exists(root, remote_int):
        return ""
    parents, murky = [], []
    for other in all_tasks(bw, scope):
        if other["id"] == meta["id"]:
            continue
        if other.get("status") not in IN_FLIGHT:
            continue
        obranch = task_branch_name(other)
        if not obranch or obranch == branch:
            continue
        # A stale origin/<obranch> is still correct here: it holds the
        # shared commits, and a landed parent is caught via integration.
        ref = f"origin/{obranch}"
        if not ref_exists(root, ref):
            ref = f"refs/heads/{obranch}"
            if not ref_exists(root, ref):
                continue
        if is_ancestor(root, ref, remote_int):
            continue  # landed, or never left integration
        if is_ancestor(root, ref, branch):
            depth = commits_ahead(root, ref, remote_int) or 0
            parents.append((depth, obranch))
            continue
        if is_ancestor(root, branch, ref):
            continue  # a descendant of this branch, not its parent
        r = git("merge-base", ref, branch, cwd=root, check=False)
        mb = (r.stdout or "").strip() if r.returncode == 0 else ""
        if mb and not is_ancestor(root, mb, remote_int):
            murky.append(obranch)
    if murky:
        names = ", ".join(sorted(murky))
        if soft:
            print(f"warning: '{branch}' shares unmerged commits with {names} "
                  f"but is not based on its current tip; diffing against "
                  f"integration", file=sys.stderr)
            return ""
        sys.exit(f"error: '{branch}' shares unmerged commits with {names}, "
                 f"but neither branch is based on the other's current tip "
                 f"(one of them moved since the stack); cannot derive a PR "
                 f"base — pass --base <branch> explicitly")
    if not parents:
        return ""
    parents.sort()
    best = parents[-1][1]
    print(f"  stack base: {best} (this branch is based on it)")
    return best


def commit_task_work(work, msg):
    """Commit everything in the task worktree `work`; exits on failure.
    Refuses (and unstages) board state, which never rides a code branch."""
    r = git("add", "-A", cwd=work, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        sys.exit(f"error: git add failed in {work}:\n{err}")
    staged = git("diff", "--cached", "--name-only", cwd=work,
                 check=False).stdout.strip()
    if not staged:
        sys.exit(f"error: worktree dirty but nothing staged in {work}")
    board_paths = [ln for ln in staged.splitlines()
                   if path_is_tasks_dir(ln)]
    if board_paths:
        git("reset", "HEAD", cwd=work, check=False)
        listed = "\n".join(f"  {p}" for p in board_paths[:20])
        more = "" if len(board_paths) <= 20 else f"\n  …+{len(board_paths)-20} more"
        sys.exit(f"error: .tasks/ paths staged in {work}; board state "
                 f"must not ship on a code branch:\n{listed}{more}")
    r = git("commit", "-m", msg, cwd=work, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        sys.exit(f"error: commit failed in {work}:\n{err}")
    print(f"  committed: {msg}")


def push_dev_work(root, scope, integration, bw, meta, why):
    """Commit and push a doing dev task's work in progress, so it outlives
    this checkout: an unattended runner is often thrown away once the run
    stops, and the next session may be on another machine. `why` ends the
    commit subject (`paused`, `waiting`). Opens no PR; ship does that."""
    tid = meta["id"]
    branch = task_branch_name(meta)
    if not branch:
        sys.exit(f"error: T{tid} has no branch; nothing to keep (claim first)")
    if not has_remote(root):
        sys.exit("error: no origin remote; cannot push the task branch")
    work = ship_work_cwd(root, scope, meta, branch, integration)
    if worktree_is_dirty(work):
        prefix = title_prefix(iteration_index(read_board_cfg(bw, scope)),
                              tid, scope)
        commit_task_work(work, f"{prefix} {meta['title']} ({why})")
    push_task_branch(root, branch, force=False)
    print(f"  pushed: {branch}")


def cmd_ship(args):
    """Ship end of implement: commit if needed, push, open PR, mark draft.

    A first ship always lands in `draft`: the PR is out, but only the
    user promotes it to `review` (TASKS ready). Re-shipping something
    already in review leaves it there.
    Mirrors hand-rolled implement ship, with stricter guards: never commit
    .tasks/ paths, refuse empty ship, one push via push_task_branch.
    Version intent is agent-owned (optional --version-intent / --body only;
    omitted or none is silent — no PR line, no land print). The flag also
    rewrites the line on a re-ship, so a changed intent can be corrected.
    """
    root, scope, integration, bw = ctx()
    cfg = read_board_cfg(bw, scope)
    idx = iteration_index(cfg)
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    prefix = title_prefix(idx, tid, scope)
    branch = task_branch_name(meta)
    if not branch:
        if meta["status"] in OPEN_PR:
            sys.exit(f"error: T{tid} is in {meta['status']} with no branch")
        sys.exit(f"error: T{tid} has no branch; run claim first")
    # Only a re-ship of already-promoted work stays in review.
    target = "review" if meta["status"] == "review" else "draft"
    if meta["status"] in TERMINAL + ("proposed",):
        sys.exit(f"error: T{tid} is {meta['status']}; cannot ship")
    if is_ops(meta):
        sys.exit(f"error: T{tid} is an ops task; nothing ships — it closes "
                 f"with its run record (/ops run {tid})")

    # A ship without a result record is what leaves the PR body a stale copy
    # of pre-implementation intent. Required on every ship, including re-ship
    # after changes-requested — that is when the record drifts most.
    shipped = (args.shipped or "").strip()
    if not shipped:
        sys.exit(f"error: T{tid} needs --shipped \"<what actually shipped>\"; "
                 "one or two sentences on the result, not the plan "
                 "(re-ship: what changed since the last ship)")
    live = live_ref_refusal("--shipped", shipped)
    if live:
        sys.exit(f"error: {live}")
    shipped_line = format_shipped(shipped)
    shipped_records = collect_shipped(meta.get("body") or "") + [shipped_line]

    require_gh(root)
    if not has_remote(root):
        sys.exit("error: no origin remote; cannot ship")

    work = ship_work_cwd(root, scope, meta, branch, integration)
    print(f"T{tid}: ship from {shown_path(work)} (branch {branch})")

    if worktree_is_dirty(work):
        msg = (args.message or "").strip() or f"{prefix} {meta['title']}"
        commit_task_work(work, with_title_prefix(msg, prefix, tid))

    # PR base is only needed to CREATE a PR: explicit --base wins, else it
    # is derived below once we know there is no open PR on this head. A
    # re-ship must not depend on the derivation — the base is already set
    # on the open PR (and land may have retargeted it).
    git("fetch", "origin", integration, cwd=root, check=False)
    pr_base = (args.base or "").strip()

    batch_ids = parse_id_list(getattr(args, "batch", None) or "")
    if batch_ids and tid not in batch_ids:
        batch_ids = sorted(set(batch_ids) | {tid})

    pr_url = (meta.get("pr") or "").strip()
    if pr_url:
        info = pr_view(root, pr_url, soft=True)
        if info and pr_is_merged(info):
            sys.exit(f"error: T{tid} PR already merged: {pr_url}")
        if not (info and (info.get("state") or "").upper() == "OPEN"):
            # Closed/unknown recorded URL — look for a live open PR.
            # An open PR is reused (its title and body refreshed below);
            # --base applies only when creating.
            pr_url = find_open_pr_for_branch(root, branch, pr_base)
    else:
        pr_url = find_open_pr_for_branch(root, branch, pr_base)

    if not pr_url:
        if not pr_base:
            pr_base = derive_stack_base(
                root, bw, scope, meta, branch, integration) or integration
        # Nothing to open: clean tree and no commits of its own ahead of the
        # PR base. Measured against pr_base, not integration — a stacked
        # child is ahead of integration by its parent's commits alone.
        ahead = commits_ahead(root, branch, f"origin/{pr_base}")
        if ahead is None:
            # Branch may lack remote tracking yet; try the local ref.
            ahead = commits_ahead(root, branch, pr_base)
        if ahead is None or ahead == 0:
            sys.exit(f"error: nothing to ship on '{branch}' (clean worktree, "
                     f"no commits ahead of {pr_base}, no open PR)")

    # One push (same helper as land). Explicit refspec; no -u (skill ship is
    # plain "push"; park-as-PR is the only flow that documents git push -u).
    push_task_branch(root, branch, force=False)

    if not pr_url:
        title = ship_pr_title(meta, prefix, args.title)
        body = ship_pr_body(meta, shipped_records, args.body,
                            args.version_intent, batch_ids)
        create = ["create", "--base", pr_base, "--head", branch,
                  "--title", title, "--body", body]
        argv = create + ["--draft"] if target == "draft" else create
        r = pr_cmd(*argv, cwd=root)
        if r.returncode != 0 and draft_unsupported(r.stderr or r.stdout or ""):
            # The board owns `draft`; the PR's draft bit only mirrors it
            # where GitHub offers one. Never block a ship over the mirror.
            print(f"warning: this repo cannot open draft PRs; opening a "
                  f"normal PR — T{tid} is still draft on the board",
                  file=sys.stderr)
            r = pr_cmd(*create, cwd=root)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            pr_url = find_open_pr_for_branch(root, branch, pr_base)
            if not pr_url:
                sys.exit(f"error: {pr_call_label('create')} failed:\n"
                         f"{err}")
            print(f"  PR appeared during create: {pr_url}")
        else:
            pr_url = (r.stdout or "").strip().splitlines()[-1].strip()
            print(f"  opened PR: {pr_url}")
    else:
        print(f"  PR: {pr_url}")
        # Re-ship: rebuild the PR title and body as create does, so a task
        # retitled or reshaped since the last ship is described as it now
        # is. The PR's Dev-batch and Version intent lines carry over unless
        # a flag sets them (land reads the intent line). The task is the
        # source of truth — hand edits to the PR are overwritten — and a
        # failed edit only costs the mirror, so it warns.
        info = pr_view(root, pr_url, soft=True)
        if info is None:
            # Unread body: carrying nothing over would drop the PR's
            # machine lines. The record lands on the task either way, so
            # leave the mirror.
            print(f"  warning: could not read the PR body; leaving the PR "
                  f"as it is (the task body keeps the record)",
                  file=sys.stderr)
        else:
            body = info.get("body") or ""
            new_title = ship_pr_title(meta, prefix, args.title)
            new_body = ship_pr_body(meta, shipped_records, args.body,
                                    args.version_intent, batch_ids,
                                    pr_body=body)
            edit = []
            if new_title != (info.get("title") or ""):
                edit += ["--title", new_title]
            if new_body.strip() != body.strip():
                edit += ["--body", new_body]
            if edit:
                r = pr_cmd("edit", pr_url, *edit, cwd=root)
                if r.returncode != 0:
                    err = (r.stderr or r.stdout or "").strip()
                    print(f"  warning: could not update the PR: {err}",
                          file=sys.stderr)
                else:
                    if "--title" in edit:
                        print(f"  updated PR title: {new_title}")
                    print(f"  updated PR body: {shipped_line}")

    integration, bw = resolve_board(root, scope)
    meta = find_task(bw, scope, tid)
    changes = []
    if meta["status"] != target:
        meta["status"] = target
        changes.append(f"status={target}")
    if meta.get("pr") != pr_url:
        meta["pr"] = pr_url
        changes.append(f"pr={pr_url}")
    if batch_ids and parse_dev_batch(meta.get("body") or "") != batch_ids:
        meta["body"] = ensure_dev_batch_in_text(meta.get("body") or "",
                                               batch_ids)
        changes.append("batch-stamp")
    meta["body"] = append_body(meta.get("body") or "", shipped_line)
    changes.append("shipped")
    if changes:
        with open(meta["path"], "w", newline="\n") as f:
            f.write(render_task(meta))
        board_commit(root, integration, bw, scope,
                     f"dev: update T{tid} ({', '.join(changes)})")
        print(f"T{tid} updated: {', '.join(changes)}")
    print(f"T{tid}: shipped → {pr_url}")
    if target == "draft":
        print(f"  draft: not asking for review yet — TASKS ready {tid} "
              f"when it is (the user's call)")


def set_task_status(root, scope, integration, bw, meta, status):
    """Write one status change and commit it to the board."""
    meta["status"] = status
    with open(meta["path"], "w", newline="\n") as f:
        f.write(render_task(meta))
    board_commit(root, integration, bw, scope,
                 f"dev: update T{meta['id']} (status={status})")


def cmd_ready(args):
    """draft → review: hand the PR to the integrator.

    Never automatic. Promoting is the user's call (SKILL.md *Humans
    decide; agents draft*) — that gate is the whole point of `draft`.
    """
    root, scope, integration, bw = ctx()
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    if meta["status"] != "draft":
        sys.exit(f"error: T{tid} is {meta['status']}, not draft; only a "
                 f"draft is marked ready for review")
    pr = (meta.get("pr") or "").strip()
    if not pr:
        sys.exit(f"error: T{tid} is draft with no PR URL; ship it first")
    require_gh(root)
    sync_pr_draft_bit(root, pr, False)
    set_task_status(root, scope, integration, bw, meta, "review")
    print(f"T{tid}: ready for review → {pr}")


def cmd_unready(args):
    """review → draft: take a PR back off the integrator's queue.

    The assignee owns the branch, so they may pull their own work back
    (shipped, then spotted more to do); the integrator may pull anything
    back. Nobody else — this moves someone else's work.
    """
    root, scope, integration, bw = ctx()
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    if meta["status"] != "review":
        sys.exit(f"error: T{tid} is {meta['status']}, not review; "
                 f"nothing to take back")
    pr = (meta.get("pr") or "").strip()
    if not pr:
        sys.exit(f"error: T{tid} is in review with no PR URL")
    ident = identity_or_exit(root, scope)
    assignee = (meta.get("assignee") or "").strip()
    integrators = board_integrators(read_board_cfg(bw, scope))
    if ident != assignee and ident not in integrators:
        sys.exit(f"error: only T{tid}'s assignee "
                 f"({assignee or 'unassigned'}) or a board integrator "
                 f"({', '.join(integrators) or 'unset'}) can unready it "
                 f"(whoami='{ident}')")
    require_gh(root)
    sync_pr_draft_bit(root, pr, True)
    set_task_status(root, scope, integration, bw, meta, "draft")
    print(f"T{tid}: back to draft → {pr}")


PR_VIEW_JSON = ("state,mergedAt,reviewDecision,isDraft,url,title,"
                "baseRefName,headRefName,mergeable,author,body,reviews,"
                "comments")


def cmd_pr(args):
    """Read or act on a task's PR: a thin `gh pr` wrapper (pr_cmd), so it
    also works where GraphQL is blocked — flows use this, never gh pr.

    The PR is the open one on --head when given (implement's throw-away of
    a leftover branch the task no longer records), else the task's recorded
    one, else the open PR on its branch. `close` with nothing open is a
    no-op, so the throw-away can run it unconditionally.
    """
    root, scope, integration, bw = ctx()
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    require_gh(root)
    head = (args.head or "").strip()
    pr = "" if head else (meta.get("pr") or "").strip()
    if not pr:
        branch = head or task_branch_name(meta)
        pr = (find_open_pr_for_branch(root, branch, strict=True)
              if branch else "")
    if not pr and args.action == "close":
        print(f"T{tid}: no open PR to close")
        return
    if not pr:
        sys.exit(f"error: T{tid} has no PR (none recorded, none open on its "
                 f"branch)")
    argv = [args.action, pr]
    if args.action == "view" and args.json:
        argv += ["--json", PR_VIEW_JSON]
    if args.action == "review":
        flag = next((f for f in ("approve", "request-changes", "comment")
                     if getattr(args, f.replace("-", "_"))), None)
        if not flag:
            sys.exit("error: pr review needs --approve, --request-changes "
                     "or --comment")
        argv.append(f"--{flag}")
    if args.action == "comment" and not (args.body or "").strip():
        sys.exit("error: pr comment needs --body")
    if args.action in ("comment", "review") and args.body:
        argv += ["--body", args.body]
    r = pr_cmd(*argv, cwd=root)
    if r.returncode != 0:
        sys.exit(f"error: pr {args.action} failed for {pr}:\n"
                 f"{(r.stderr or r.stdout or '').strip()}")
    sys.stdout.write(r.stdout or "")


def scope_path_is_in_scope(scope, path):
    """Whether a repo-relative path is in this board's product scope."""
    norm = path.replace("\\", "/").lstrip("./")
    if scope in (".", ""):
        return True
    prefix = scope.replace("\\", "/").rstrip("/") + "/"
    return (norm == scope.replace("\\", "/").rstrip("/")
            or norm.startswith(prefix))


def local_integration_ahead_state(root, scope, integration):
    """Describe local integration commits ahead of origin.

    Returns dict with ahead, commits, in_scope, out_of_scope path lists.
    Caller should fetch origin first.
    """
    remote_ref = f"origin/{integration}"
    if not ref_exists(root, remote_ref):
        return {"ahead": 0, "commits": [], "in_scope": [], "out_of_scope": [],
                "missing_remote": True}
    if not ref_exists(root, f"refs/heads/{integration}"):
        return {"ahead": 0, "commits": [], "in_scope": [], "out_of_scope": [],
                "missing_local": True}
    n = git("rev-list", "--count", f"{remote_ref}..{integration}",
            cwd=root).stdout.strip()
    ahead = int(n or "0")
    commits = []
    if ahead:
        commits = git(
            "log", "--oneline", f"{remote_ref}..{integration}", cwd=root
        ).stdout.strip().splitlines()
    paths = []
    if ahead:
        paths = git(
            "diff", "--name-only", f"{remote_ref}..{integration}", cwd=root
        ).stdout.strip().splitlines()
    in_scope, out_of_scope = [], []
    for p in paths:
        if not p:
            continue
        if scope_path_is_in_scope(scope, p):
            in_scope.append(p)
        else:
            out_of_scope.append(p)
    return {"ahead": ahead, "commits": commits, "in_scope": in_scope,
            "out_of_scope": out_of_scope}


def cmd_preflight(args):
    """Local integration ahead of origin: check, park-as-PR, or discard.

    Exit 0: clear, or ahead only on out-of-scope paths.
    Exit 2: in-scope ahead in check mode (implement must stop).
    Park/discard require a clean working tree checked out on integration.
    """
    root, scope, integration, bw = ctx()
    # The sign-in gate for implement and unattended runs: their flows run no
    # gh check of their own, so it holds in check mode too, not only for
    # --park.
    require_gh(root)
    mode = "check"
    if args.park:
        mode = "park"
    if args.discard:
        if mode == "park":
            sys.exit("error: pass only one of --park / --discard")
        mode = "discard"

    if not has_remote(root):
        sys.exit("error: no origin remote; cannot preflight")
    git("fetch", "origin", integration, cwd=root, check=False)
    state = local_integration_ahead_state(root, scope, integration)
    if state.get("missing_remote"):
        sys.exit(f"error: origin/{integration} missing after fetch")
    if state.get("missing_local"):
        print(f"preflight: no local branch '{integration}' "
              f"(task branches use origin/{integration}; clear)")
        return

    ahead = state["ahead"]
    if ahead == 0:
        print(f"preflight: local '{integration}' is not ahead of "
              f"origin/{integration}")
        return

    print(f"preflight: local '{integration}' is {ahead} commit(s) ahead of "
          f"origin/{integration}")
    for c in state["commits"]:
        print(f"  {c}")
    if state["in_scope"]:
        print("  in-scope paths:")
        for p in state["in_scope"]:
            print(f"    {p}")
    if state["out_of_scope"]:
        print("  out-of-scope paths:")
        for p in state["out_of_scope"]:
            print(f"    {p}")

    if not state["in_scope"]:
        print("preflight: ahead only on out-of-scope paths — ok to continue")
        return

    if mode == "check":
        print("preflight: in-scope ahead — park-as-PR or discard before "
              "implement (TASKS preflight --park | --discard)")
        sys.exit(2)

    # Park/discard hard-reset the primary clone's integration branch (claim
    # hub). A task worktree on another branch is not enough.
    cur = current_branch_name(root)
    if cur != integration:
        sys.exit(
            f"error: park/discard need primary clone on '{integration}' "
            f"(primary={root}, currently '{cur or 'detached/unknown'}'). "
            f"Checkout '{integration}' there and re-run — task worktrees "
            f"are not enough."
        )
    if worktree_is_dirty(root):
        sys.exit(f"error: working tree on '{integration}' is dirty; "
                 "commit/stash/elsewhere before park or discard")

    if mode == "discard":
        git("reset", "--hard", f"origin/{integration}", cwd=root)
        print(f"preflight: discarded local commits; '{integration}' == "
              f"origin/{integration}")
        return

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%d-%H%M%S")
    park_branch = f"park/{integration}-{stamp}"
    git("branch", park_branch, integration, cwd=root)
    r = git("push", "-u", "origin", park_branch, cwd=root, check=False)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        # Push failed: nothing durable on origin; drop local park ref only.
        # Ahead commits remain on local integration.
        git("branch", "-D", park_branch, cwd=root, check=False)
        sys.exit(f"error: push of park branch failed:\n{err}")

    # Commits are safe on local + remote park/*. Reset local integration to
    # origin so implement can proceed even if PR create fails next.
    # (origin/<integration> is already the desired tip — ahead was local-only.)
    git("reset", "--hard", f"origin/{integration}", cwd=root)
    print(f"preflight: parked on {park_branch}", flush=True)
    print(f"  local '{integration}' reset to origin/{integration}",
          flush=True)

    title = f"park: local {integration} ahead of origin ({stamp})"
    body = (
        "Parked local integration commits that were ahead of origin "
        "before implement.\n\n"
        f"Scope: {scope}\n"
        f"Commits:\n" + "\n".join(f"- {c}" for c in state["commits"])
    )
    pr_err = ""
    pr_url = ""
    for attempt in range(1, 4):
        r = pr_cmd("create", "--base", integration, "--head", park_branch,
               "--title", title, "--body", body, cwd=root)
        if r.returncode == 0:
            pr_url = (r.stdout or "").strip().splitlines()[-1].strip()
            break
        pr_err = (r.stderr or r.stdout or "").strip()
        if attempt < 3:
            print(f"preflight: {pr_call_label('create')} failed (attempt "
                  f"{attempt}/3); "
                  f"retrying…", flush=True)
            time.sleep(1)
    if pr_url:
        print(f"  PR: {pr_url}")
        return
    # Park succeeded (remote park/* + local integration reset). PR create is
    # the happy path but must not block implement — exit 0 and yell so the
    # agent surfaces the failure to the user.
    print(
        f"WARNING: preflight: {pr_call_label('create')} failed after "
        "retries — "
        "SURFACE THIS TO THE USER.\n"
        f"  park branch is safe — do not delete '{park_branch}' "
        f"(local or origin) until reviewed.\n"
        f"  finish PR: "
        f"{pr_hint_create(integration, park_branch, title)}\n"
        f"  local '{integration}' already reset; implement may proceed.\n"
        f"{pr_err}",
        flush=True,
    )


def iteration_close_ready(bw, scope, index, next_cmd="iteration-land"):
    """Return an error string if the board is not closed for land/new, else None.

    Ready means: no live task files, and log.md has a close heading for this
    iteration index (written by iteration-close as ``## {n}`` or
    ``## {n} — {name}``).
    """
    tasks = all_tasks(bw, scope)
    if tasks:
        ids = ", ".join(f"T{t['id']}" for t in tasks)
        return (f"board still has tasks ({ids}); run TASKS iteration-close "
                f"before {next_cmd}")
    log_path = os.path.join(bw, tdir(scope), "log.md")
    rel = f"{tdir(scope)}/log.md"
    if not os.path.isfile(log_path):
        return (f"no {rel} close entry for iteration {index}; "
                f"run TASKS iteration-close first")
    with open(log_path) as f:
        text = f.read()
    if not log_has_close_section(text, index):
        return (f"no log close section for iteration {index} in "
                f"{rel}; run TASKS iteration-close first")
    return None


def live_iteration_closed(bw, scope, cfg):
    """True when the live iteration is closed in log.md and the board is empty."""
    return iteration_close_ready(bw, scope, iteration_index(cfg)) is None


def cmd_iteration_land(args):
    """Open/merge the iteration PR (merge commit) into parent_branch.

    Idempotent when origin/integration is already contained in
    origin/parent (prior land, manual merge, or empty delta). Does not
    auto-approve. Requires a closed board: no task files and a log.md
    close section for the current iteration.
    """
    root, scope, integration, bw = ctx()
    cfg = read_board_cfg(bw, scope)
    parent = (cfg.get("parent_branch") or "").strip()
    if not parent:
        sys.exit("error: no parent_branch configured; iteration-land merges "
                 "into a parent. Close a no-parent board in place: "
                 "TASKS iteration-close, then TASKS iteration-new --name "
                 "<name>")
    if parent == integration:
        sys.exit(f"error: parent_branch equals integration_branch "
                 f"('{integration}')")
    idx = iteration_index(cfg)
    not_ready = iteration_close_ready(bw, scope, idx)
    if not_ready:
        sys.exit(f"error: {not_ready}")
    require_gh(root)
    if not has_remote(root):
        sys.exit("error: no origin remote; cannot iteration-land")

    git("fetch", "origin", parent, integration, cwd=root, check=False)
    if not ref_exists(root, f"origin/{integration}"):
        sys.exit(f"error: origin/{integration} missing; push the integration "
                 "branch before iteration-land")
    if not ref_exists(root, f"origin/{parent}"):
        sys.exit(f"error: origin/{parent} missing after fetch")

    # Prefer an open PR; remember a prior MERGED URL for messaging only.
    # "Already landed" is git ancestry (integration tip in parent), not
    # merely the existence of a past MERGED PR — integration may have
    # advanced after that land and still need a new PR.
    open_url = ""
    merged_url = ""
    r = pr_cmd("list", "--head", integration, "--base", parent,
           "--state", "all", "--json", "url,state,mergedAt,number",
           "--limit", "10", cwd=root)
    if r.returncode == 0:
        try:
            items = json.loads(r.stdout or "[]")
        except json.JSONDecodeError:
            items = []
        for it in items:
            st = (it.get("state") or "").upper()
            if st == "OPEN" and not open_url:
                open_url = (it.get("url") or "").strip()
            elif (st == "MERGED" or it.get("mergedAt")) and not merged_url:
                merged_url = (it.get("url") or "").strip()

    anc = git("merge-base", "--is-ancestor",
              f"origin/{integration}", f"origin/{parent}",
              cwd=root, check=False)
    if anc.returncode == 0:
        note = f" ({merged_url})" if merged_url else ""
        print(f"iteration-land: already merged{note}")
        print("next: TASKS iteration-new <branch> when ready")
        return

    pr_url = open_url
    if not pr_url:
        label = iteration_label(cfg)
        title = (args.title or "").strip() or f"iteration {label}"
        body = (args.body or "").strip() or (
            f"Land iteration {label} (`{integration}` → `{parent}`) "
            f"with a merge commit (not squash).\n")
        r = pr_cmd("create", "--base", parent, "--head", integration,
               "--title", title, "--body", body, cwd=root)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            sys.exit(f"error: {pr_call_label('create')} failed:\n{err}")
        pr_url = (r.stdout or "").strip().splitlines()[-1].strip()
        print(f"iteration-land: opened {pr_url}")
    else:
        print(f"iteration-land: existing open PR {pr_url}")

    if args.create_only:
        print("iteration-land: --create-only set; not merging")
        return

    last_err = ""
    for attempt in range(1, LAND_RETRIES + 1):
        readiness = wait_for_pr_mergeable(root, pr_url)
        if readiness == "MERGED":
            print("iteration-land: PR became merged while waiting")
            print("next: TASKS iteration-new <branch>")
            return
        if readiness == "CONFLICTING":
            sys.exit(f"error: iteration PR is CONFLICTING; resolve and "
                     f"re-run iteration-land:\n{pr_url}")
        r = pr_cmd("merge", pr_url, "--merge", cwd=root)
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode == 0:
            print(f"iteration-land: merged (merge commit) attempt {attempt}")
            print("next: TASKS iteration-new <branch>")
            return
        last_err = out
        low = out.lower()
        if "already merged" in low:
            print("iteration-land: already merged")
            print("next: TASKS iteration-new <branch>")
            return
        info = pr_view(root, pr_url, soft=True)
        if info and pr_is_merged(info):
            print("iteration-land: already merged")
            print("next: TASKS iteration-new <branch>")
            return
        if not merge_error_transient(out):
            sys.exit(merge_fail_permanent_message(out))
        print(f"  merge attempt {attempt} failed (transient); retry…")
        if attempt < LAND_RETRIES:
            time.sleep(min(2 * attempt, 8))
    sys.exit(f"error: could not merge iteration PR after {LAND_RETRIES} "
             f"attempts:\n{last_err}")


# ---------- commands ----------

def cmd_init(args):
    root = repo_root()
    if args.scope:
        scope = os.path.normpath(args.scope)
        if scope != "." and (os.path.isabs(scope) or scope.startswith("..")):
            sys.exit("error: --scope must be a subdir path relative to the repo root")
        scope = scope_form(scope)
    else:
        # Same walk as find_scope (current worktree first).
        try:
            wt = worktree_root()
        except SystemExit:
            wt = root
        scope = nearest_scope(wt) or nearest_scope(root) or "."
    # Before any side effect: a handle is tied to a GitHub login, so no
    # login means no init (never a handle taken on trust).
    login, err = gh_login(root)
    if err:
        sys.exit(f"error: {err}")
    p = os.path.join(root, tdir(scope), "board.yml")
    if args.integration:
        branch = args.integration
    elif os.path.exists(p):
        branch = parse_kv(open(p).read()).get("integration_branch")
    else:
        branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root).stdout.strip()
    write_cache(root, scope, branch)
    # immediate local ignore, without dirtying any branch (.dev/ and TASKS.md
    # match any depth — product-local paths are covered). Viewer ignore is
    # path-anchored and omitted when <product>/board is already a directory.
    dest = viewer_path(root, scope)
    ignore_lines = [".dev/", "TASKS.md"]
    if not os.path.isdir(dest):
        ignore_lines.append(viewer_ignore_line(scope))
    exclude = git_path(root, "info/exclude")
    for line in ignore_lines:
        append_ignore_line(exclude, line)
    branch, bw = resolve_board(root, scope)
    if not os.path.exists(board_yml_path(bw, scope)):
        if args.name is None:
            sys.exit("error: --name <handle> is required to create a board "
                     f"(suggested: {login})")
        entries, name, err = roster_join([], args.name, login)
        if err:
            sys.exit(f"error: {err}")
        os.makedirs(os.path.join(bw, tdir(scope)), exist_ok=True)
        idx = parse_positive_int(
            args.iteration if args.iteration is not None else 1, "iteration")
        started = parse_iso_date(
            args.iteration_started or datetime.date.today().isoformat(),
            "iteration_started")
        iname = (args.iteration_name or "").strip()
        require_schema3_archive_slug(idx, iname)
        cfg = {"schema_version": str(SCHEMA_VERSION),
               "integration_branch": branch, "parent_branch": args.parent or "",
               "iteration": str(idx),
               "iteration_name": iname,
               "iteration_started": started,
               "integrator": name,
               "contributors": format_contributors(entries)}
        write_board_cfg(bw, scope, cfg)
        gi = os.path.join(bw, ".gitignore")
        for line in ignore_lines:
            append_ignore_line(gi, line)
        if not board_commit(root, branch, bw, scope,
                            "dev: init task board"):
            # The board exists only on the private queue; discovery still
            # finds it through boards.json, and any board command flushes it.
            sys.exit(f"error: the new board is queued on "
                     f"{board_branch_name(scope)} but did not reach "
                     f"origin/{branch}. Fix the remote, then re-run init "
                     f"(or any board command) to flush the queue.")
        print(f"initialized board '{scope}' on '{branch}' (integrator: {name})")
    else:
        cfg = read_board_cfg(bw, scope)
        old = board_contributors(cfg)
        entries, name, err = roster_join(old, args.name, login,
                                         board_former_handles(cfg))
        if err:
            sys.exit(f"error: {err}")
        if entries != old:
            cfg["contributors"] = format_contributors(entries)
            write_board_cfg(bw, scope, cfg)
            verb = ("register contributor" if len(entries) > len(old)
                    else "record GitHub login for")
            board_commit(root, branch, bw, scope, f"dev: {verb} {name}")
        print(f"joined board '{scope}' on '{branch}'")
        gi = os.path.join(bw, ".gitignore")
        if (not os.path.isdir(dest)
                and append_ignore_line(gi, viewer_ignore_line(scope))):
            board_commit(root, branch, bw, scope,
                         "dev: ignore local board viewer")
    dest, _wrote = ensure_board_viewer(root, scope)
    if WINDOWS:
        print(f"viewer: none — {WATCH_WINDOWS_HINT}")
    elif os.path.isdir(dest):
        print(f"viewer: skipped ({VIEWER_NAME} is a directory)")
    else:
        print(f"viewer: ./{VIEWER_NAME}  (r refresh, a by area, e expand, l latest, c check, f flows, g registries, q back/quit, arrows scroll, space/b page, type id↵)")
    print(f"identity: {name} (GitHub: {login})")
    if scope != ".":
        print(f"note: commands target this board from inside '{scope}/' "
              f"(or pass --scope {scope})")


def cmd_whoami(args):
    root = repo_root()
    scope = find_scope(root)
    if scope is None:
        sys.exit(f"error: no board found (no {TASKS_DIR}/board.yml from cwd up "
                 "to repo root). Run: tasks.py init --name <you>")
    # --github is kept as an alias: identity always comes from the login.
    ident = identity_or_exit(root, scope)
    if args.role:
        # The board answers "am I an integrator?" so callers never have to
        # compare identities themselves — and so the roster's shape stays
        # the script's business.
        _branch, bw = resolve_board(root, scope)
        cfg = read_board_cfg(bw, scope)
        print("integrator" if is_integrator(ident, cfg) else "contributor")
        return
    print(ident)


def cmd_config(args):
    root, scope, branch, bw = ctx()
    cfg = read_board_cfg(bw, scope)
    if args.key is None:
        print(f"scope: {scope}")
        for k in CONFIG_KEYS:
            print(f"{k}: {cfg.get(k, '')}")
    elif args.value is None:
        if args.key not in CONFIG_KEYS:
            sys.exit(f"error: unknown key '{args.key}' (known: {', '.join(CONFIG_KEYS)})")
        print(cfg.get(args.key, ""))
    else:
        if args.key == "integrator":
            sys.exit("error: the integrator roster is not set via config; "
                     "use TASKS integrator add <name> / rm <name> "
                     "(TASKS integrator list to read it)")
        if args.key not in SETTABLE_KEYS:
            sys.exit(f"error: '{args.key}' is not settable via config "
                     f"(settable: {', '.join(SETTABLE_KEYS)})")
        value = args.value
        if args.key in ("iteration", "iteration_name", "iteration_started"):
            # Land gate matches log.md's "## {n}" heading. Changing identity,
            # display name, or start after close would desync the heading
            # (and, for a renumber, the archive path already written).
            if live_iteration_closed(bw, scope, cfg):
                cur = iteration_index(cfg)
                parent = (cfg.get("parent_branch") or "").strip()
                if parent:
                    sys.exit(f"error: iteration {cur} is already closed in "
                             f"{tdir(scope)}/log.md; changing {args.key} now "
                             "would break iteration-land. Land it, then start "
                             "the next one with iteration-new.")
                sys.exit(f"error: iteration {cur} is already closed in "
                         f"{tdir(scope)}/log.md; changing {args.key} now "
                         "would desync the close heading. Start the next "
                         "one in place: TASKS iteration-new --name <name>")
        if args.key == "iteration":
            new = parse_positive_int(value, "iteration")
            cur = iteration_index(cfg)
            name = iteration_name(cfg)
            require_schema3_archive_slug(new, name)
            if new != cur:
                taken = archive_taken(bw, scope, new, name)
                if taken:
                    sys.exit(f"error: iteration {new} already has an archive "
                             f"at {taken}/; pick another number.")
            value = str(new)
        elif args.key == "iteration_name":
            value = value.strip()
            idx = iteration_index(cfg)
            require_schema3_archive_slug(idx, value)
            taken = archive_taken(bw, scope, idx, value)
            if taken:
                sys.exit(f"error: iteration {idx} already has an archive "
                         f"at {taken}/; pick another name.")
        elif args.key == "iteration_started":
            value = parse_iso_date(value, "iteration_started")
        cfg[args.key] = value
        write_board_cfg(bw, scope, cfg)
        board_commit(root, branch, bw, scope, f"dev: config {args.key}={value}")
        print(f"{args.key}: {value}")


def cmd_integrator(args):
    """CRUD the roster. Ungated on purpose: the board coordinates trusted
    collaborators, and the real merge gate is branch protection — but the
    last integrator cannot be removed, since an empty roster makes land
    impossible for everyone."""
    root, scope, branch, bw = ctx()
    cfg = read_board_cfg(bw, scope)
    roster = board_integrators(cfg)
    if args.action == "list":
        ident, _ = current_identity(root, scope)
        for name in roster:
            print(f"{name}{'  (you)' if name == ident else ''}")
        if not roster:
            print("(no integrator configured; land is blocked until one is "
                  "set: TASKS integrator add <name>)")
        return
    name = args.name.strip()
    if not name or "," in name:
        sys.exit("error: integrator name must be non-empty and comma-free")
    if args.action == "add":
        if name in roster:
            print(f"integrator: {', '.join(roster)} (unchanged)")
            return
        roster.append(name)
    else:
        if name not in roster:
            sys.exit(f"error: '{name}' is not an integrator "
                     f"(integrator: {', '.join(roster) or 'unset'})")
        if len(roster) == 1:
            sys.exit(f"error: '{name}' is the only integrator; removing them "
                     "would block land for everyone. Add a replacement first: "
                     "TASKS integrator add <name>")
        roster.remove(name)
    cfg["integrator"] = ", ".join(roster)
    write_board_cfg(bw, scope, cfg)
    board_commit(root, branch, bw, scope,
                 f"dev: integrator {args.action} {name}")
    print(f"integrator: {', '.join(roster)}")


def contributor_rm_refusal(ident, name, entries, integrators, tasks,
                           registries=()):
    """Why `contributor rm <name>` must not run, or None. Pure.

    Only the contributor themself or an integrator may remove a handle. The
    last integrator stays (an empty integrator roster blocks land for
    everyone), and so does anyone still assigned work that will carry on:
    every status but done and not-planned, since shelved tasks come back
    still assigned. So does the last accessor of an agent or
    environment (`registries`), which would otherwise lead to nobody."""
    if name not in [h for h, _ in entries]:
        return (f"'{name}' is not a contributor "
                f"({', '.join(h for h, _ in entries) or 'none'})")
    if ident != name and ident not in integrators:
        return (f"only '{name}' themself or a board integrator "
                f"({', '.join(integrators) or 'unset'}) can remove them "
                f"(whoami='{ident}')")
    if integrators == [name]:
        return (f"'{name}' is the only integrator; removing them would block "
                "land for everyone. Add a replacement first: "
                "TASKS integrator add <name>")
    held = [t["id"] for t in tasks if t.get("assignee") == name
            and t["status"] not in ("done", "not-planned")]
    if held:
        return (f"'{name}' still holds "
                f"{', '.join(f'T{i}' for i in held)}; reassign or finish "
                "those first (TASKS update <id> --assignee <who>)")
    only = last_accessor_of(registries, name)
    if only:
        return (f"'{name}' is the only accessor of {', '.join(only)}; add "
                "another accessor (TASKS agent|env update <name> "
                "--accessors …) or remove the entry first")
    return None


def cmd_contributor(args):
    """Read the roster, rename a handle, or remove one. Joining is init's
    job, since that is where the GitHub login is read."""
    root, scope, branch, bw = ctx()
    cfg = read_board_cfg(bw, scope)
    entries = board_contributors(cfg)
    integrators = board_integrators(cfg)
    ident, _ = current_identity(root, scope)
    formers = board_former_handles(cfg)
    if args.action == "list":
        for h, l in entries:
            tags = [f"github: {l or 'unknown'}"]
            if h in integrators:
                tags.append("integrator")
            if h == ident:
                tags.append("you")
            was = [o for o, c in formers.items() if c == h]
            if was:
                tags.append(f"formerly {', '.join(was)}")
            print(f"{h}  ({', '.join(tags)})")
        if not entries:
            print("(no contributors registered)")
        return
    name = args.name.strip()
    ident = identity_or_exit(root, scope)
    registries = [e for kind in REGISTRIES
                  for e in all_registry(bw, scope, kind)]
    if args.action == "rename":
        contributor_rename(root, scope, branch, bw, cfg, ident, name,
                           args.new_name.strip(), registries)
        return
    err = contributor_rm_refusal(ident, name, entries, integrators,
                                 all_tasks(bw, scope), registries)
    if err:
        sys.exit(f"error: {err}")
    # Accessors say who can reach an entry now, so a removed contributor
    # leaves every list; the refusal above kept any list from emptying.
    dropped = []
    for e in registries:
        acc = split_names(e.get("accessors"))
        if name in acc:
            e["accessors"] = ", ".join(a for a in acc if a != name)
            write_registry(e)
            dropped.append(f"{REGISTRIES[e['kind']]['label']} {e['name']}")
    cfg["contributors"] = format_contributors(
        [(h, l) for h, l in entries if h != name])
    # rm frees every name the handle held, like a registry entry's.
    set_former_handles(cfg, {o: c for o, c in formers.items() if c != name})
    if name in integrators:
        cfg["integrator"] = ", ".join(n for n in integrators if n != name)
    write_board_cfg(bw, scope, cfg)
    board_commit(root, branch, bw, scope, f"dev: contributor rm {name}")
    print(f"removed contributor '{name}'"
          + (" (and from the integrator roster)" if name in integrators
             else ""))
    if dropped:
        print(f"  dropped as accessor of: {', '.join(dropped)}")
    if name == ident:
        print("note: your GitHub login is no longer on this board's roster; "
              "re-run init to join again")


def contributor_rename(root, scope, branch, bw, cfg, ident, old, new,
                       registries):
    """Rename a handle everywhere it means a person now: the roster, the
    integrator roster, assignees on the live board, and agent/env/routine
    accessors. Archives, run records and flow prose are history and keep
    the old name; former_handles is what still ties it to `new`."""
    entries = board_contributors(cfg)
    integrators = board_integrators(cfg)
    formers = board_former_handles(cfg)
    err = contributor_rename_refusal(ident, old, new, entries, integrators,
                                     formers)
    if err:
        sys.exit(f"error: {err}")
    entries, integrators, formers = roster_rename(entries, integrators,
                                                  formers, old, new)
    reassigned = []
    for t in all_tasks(bw, scope):
        if t.get("assignee") == old:
            t["assignee"] = new
            with open(t["path"], "w", newline="\n") as f:
                f.write(render_task(t))
            reassigned.append(f"T{t['id']}")
    accessed = []
    for e in registries:
        acc = split_names(e.get("accessors"))
        if old in acc:
            e["accessors"] = ", ".join(new if a == old else a for a in acc)
            write_registry(e)
            accessed.append(f"{REGISTRIES[e['kind']]['label']} {e['name']}")
    cfg["contributors"] = format_contributors(entries)
    cfg["integrator"] = ", ".join(integrators)
    set_former_handles(cfg, formers)
    write_board_cfg(bw, scope, cfg)
    board_commit(root, branch, bw, scope,
                 f"dev: contributor rename {old} -> {new}")
    print(f"renamed contributor '{old}' to '{new}' ('{old}' stays reserved)")
    if new in integrators:
        print("  integrator roster updated")
    if reassigned:
        print(f"  assignee on: {', '.join(reassigned)}")
    if accessed:
        print(f"  accessor of: {', '.join(accessed)}")


def cmd_area(args):
    root, scope, branch, bw = ctx()
    mods = read_areas(bw, scope)
    if args.action == "list":
        open_counts = {}
        for t in all_tasks(bw, scope):
            if occupies_area(t):
                for a in split_areas(t.get("area", "")):
                    open_counts[a] = open_counts.get(a, 0) + 1
        for name, desc in mods.items():
            print(f"- {name}: {desc} ({open_counts.pop(name, 0)} open)")
        for name, n in open_counts.items():
            print(f"- {name}: (no entry in areas.md) ({n} open)")
    elif args.action == "set":
        name = args.area_name.strip()
        if ":" in name or "," in name or not name:
            sys.exit("error: area names must be non-empty, no ':' or ','")
        if name.lower() == "all":
            sys.exit("error: 'all' is reserved (a task areaed 'all' touches "
                     "everything; it is never listed in areas.md)")
        mods[name] = args.desc or mods.get(name, "")
        write_areas(bw, scope, mods)
        board_commit(root, branch, bw, scope, f"dev: area set {name}")
        print(f"- {name}: {mods[name]}")
    elif args.action == "rm":
        name = args.area_name.strip()
        if name not in mods:
            sys.exit(f"error: no area '{name}'")
        refs = [t["id"] for t in all_tasks(bw, scope)
                if name in split_areas(t.get("area", "")) and occupies_area(t)]
        if refs and not args.force:
            sys.exit(f"error: open tasks still reference '{name}': "
                     f"{', '.join(f'T{i}' for i in refs)} (use --force to remove anyway)")
        del mods[name]
        write_areas(bw, scope, mods)
        board_commit(root, branch, bw, scope, f"dev: area rm {name}")
        print(f"area '{name}' removed")


ADD_STATUSES = ("proposed", "backlog", "planned", "shelved")


def cmd_add(args):
    if args.status == RETIRED_LATER:
        sys.exit(LATER_RETIRED_ERR)
    if args.status not in ADD_STATUSES:
        sys.exit(f"error: --status must be one of {', '.join(ADD_STATUSES)}")
    if args.reason is not None and args.status != "shelved":
        sys.exit("error: --reason only applies with --status shelved")
    if args.status == "shelved" and not (args.reason or "").strip():
        sys.exit('error: --status shelved requires --reason "<why>" '
                 "(recorded in the task body)")
    live = live_ref_refusal("--reason", args.reason or "")
    if live:
        sys.exit(f"error: {live}")
    root, scope, branch, bw = ctx()
    tasks = all_tasks(bw, scope)
    tid = max((t["id"] for t in tasks), default=0) + 1
    kind = (args.kind or "").strip()
    meta = {
        "id": tid, "title": args.title, "area": args.area or "",
        "status": args.status, "kind": kind,
        "type": (args.type or "").strip() or DEV,
        "assignee": args.assignee or "", "branch": "",
        "deps": [int(x) for x in re.findall(r"\d+", args.deps or "")], "pr": "",
        "needs": "", "created": datetime.date.today().isoformat(),
        "cadence": (args.cadence or "").strip(),
        "schedule": (args.schedule or "").strip(), "last_run": "",
        "next_due": (args.next_due or "").strip(),
        "rehearsal": "true" if args.rehearsal else "",
        "distill": "true" if args.distill else "",
        "routine": (args.routine or "").strip(),
        "body": args.desc or "",
    }
    if args.reason is not None:
        meta["body"] = append_body(
            meta["body"], f"{REASON_STATUSES['shelved']} "
            f"({meta['created']}): {args.reason}")
    validate_recurring(meta)
    validate_type(meta, new=True)
    validate_rehearsal(meta)
    validate_distill(meta)
    notes = point_at_routine(bw, scope, meta, tasks)
    umbrellas = add_umbrella_targets(parse_id_list(args.umbrella), meta["deps"],
                                     tasks)
    known = {t["id"] for t in tasks}
    for d in meta["deps"]:
        if d not in known:
            print(f"warning: dep {d} does not exist", file=sys.stderr)
    known_areas = read_areas(bw, scope)
    for a in split_areas(args.area or ""):
        if a != "all" and a not in known_areas:
            print(f"warning: area '{a}' has no entry in areas.md",
                  file=sys.stderr)
    path = os.path.join(bw, tdir(scope), f"{tid:03d}.md")
    with open(path, "w", newline="\n") as f:
        f.write(render_task(meta))
    for u in umbrellas:
        u["deps"] = u["deps"] + [tid]
        with open(u["path"], "w", newline="\n") as f:
            f.write(render_task(u))
    under = "".join(f" under T{u['id']}" for u in umbrellas)
    board_commit(root, branch, bw, scope, f"dev: add T{tid} {args.title}{under}")
    print(render_task(meta).rstrip())
    for u in umbrellas:
        print(f"T{u['id']} updated: deps={u['deps']}")
    for n in notes:
        print(n, file=sys.stderr)


def point_at_routine(bw, scope, meta, tasks):
    """Check `meta`'s routine field and store the routine's current name;
    returns the notes to print once written. Exits on a refusal."""
    if not meta["routine"]:
        return []
    r, err, notes = routine_pointer_check(
        meta, tasks, all_registry(bw, scope, "routine"), all_flows(bw, scope))
    if err:
        sys.exit(f"error: {err}")
    meta["routine"] = r["name"]
    return notes


def add_umbrella_targets(ids, deps, tasks):
    """The umbrella tasks `add --umbrella` files the new task under; exits on
    an id that is not an umbrella, a closed one (done or not-planned, which
    `related --deps` never offers either), or one the new task also depends
    on (the umbrella would then wait on its own child)."""
    by_id = {t["id"]: t for t in tasks}
    out = []
    for i in ids:
        t = by_id.get(i)
        if t is None:
            sys.exit(f"error: --umbrella: no task with id {i}")
        if not is_umbrella(t):
            sys.exit(f"error: --umbrella: T{i} is not an umbrella")
        if t.get("status") in ("done", "not-planned"):
            sys.exit(f"error: --umbrella: T{i} is {t['status']}; a closed "
                     "umbrella takes no new children")
        if i in deps:
            sys.exit(f"error: --umbrella: T{i} is also in --deps; a task "
                     "cannot both wait on an umbrella and sit under it")
        out.append(t)
    return out


def cmd_update(args):
    root, scope, branch, bw = ctx()
    meta = find_task(bw, scope, args.id)
    old = dict(meta)
    changes = []
    for field in ("title", "area", "status", "kind", "type", "assignee",
                  "branch", "pr", "needs", "desc", "cadence", "schedule",
                  "last_run", "next_due"):
        v = getattr(args, field, None)
        if v is not None:
            key = "body" if field == "desc" else field
            strip = field in ("kind", "type") + OPTIONAL_FIELDS
            meta[key] = v.strip() if strip and isinstance(v, str) else v
            if field == "type":
                meta[key] = v = meta[key] or DEV
            changes.append(f"{field}={v}" if field != "desc" else "desc")
    if args.flow is not None:
        # Names resolve now so the field always holds `<id> <name>` refs.
        meta["flow"] = ", ".join(resolve_flow_refs(bw, scope, args.flow))
        changes.append(f"flow={meta['flow']}")
    if args.routine is not None:
        meta["routine"] = args.routine.strip()
        changes.append(f"routine={meta['routine']}")
    run = None if args.unattended is None else args.unattended.strip()
    if run is not None:
        meta["unattended"] = run
        changes.append(f"unattended={run}")
    if args.deps is not None:
        meta["deps"] = [int(x) for x in re.findall(r"\d+", args.deps)]
        changes.append(f"deps={meta['deps']}")
    if args.status == RETIRED_LATER:
        sys.exit(LATER_RETIRED_ERR)
    if args.reason is not None and args.status not in REASON_STATUSES:
        sys.exit("error: --reason only applies with --status "
                 + " or ".join(REASON_STATUSES))
    if args.status in REASON_STATUSES and not (args.reason or "").strip():
        sys.exit(f"error: --status {args.status} requires --reason \"<why>\" "
                 "(recorded in the task body)")
    live = live_ref_refusal("--reason", args.reason or "")
    if live:
        sys.exit(f"error: {live}")
    strand_err, cleared = off_board_guard(old, meta, args.status)
    if strand_err:
        sys.exit(strand_err)
    today = datetime.date.today().isoformat()
    if args.append is not None:
        for text in args.append:
            meta["body"] = append_body(meta["body"], text)
        changes.append("append")
    if args.reason is not None:
        meta["body"] = append_body(
            meta["body"],
            f"{REASON_STATUSES[args.status]} ({today}): {args.reason}")
    if cleared:
        meta["body"] = append_body(
            meta["body"], f"Cleared on moving to {args.status} ({today}): "
            f"{', '.join(cleared)}.")
    if not changes:
        sys.exit("error: nothing to update")
    if meta["status"] not in STATUSES:
        sys.exit(f"error: status must be one of {STATUSES}")
    if meta.get("needs") not in ("", "decision"):
        sys.exit("error: needs must be 'decision' or empty")
    if old["routine"] and args.routine is None and not is_recurring(meta):
        sys.exit(f"error: T{meta['id']} is started by routine "
                 f"{old['routine']}; clear it first (update {meta['id']} "
                 "--routine \"\") before changing its kind")
    validate_recurring(meta)
    validate_type(meta, set_type=args.type is not None,
                  set_area=args.area is not None)
    validate_rehearsal(meta)
    validate_distill(meta)
    refusal = update_unattended_refusal(old, meta, run, args.status)
    if refusal:
        sys.exit(refusal)
    notes = []
    if [meta.get(k) for k in ("routine", "kind", "flow")] + [task_type(meta)] \
            != [old.get(k) for k in ("routine", "kind", "flow")] \
            + [task_type(old)]:
        notes = point_at_routine(bw, scope, meta, all_tasks(bw, scope))
    if meta["routine"] and any(getattr(args, f) is not None for f in
                               ("cadence", "schedule", "next_due")):
        notes.append(routine_trigger_reminder(meta))
    # Checked on entering the state (start, flow set or type changed while
    # doing), so an unrelated edit to a doing task is never refused.
    if (old["status"], old["flow"], task_type(old)) != \
            (meta["status"], meta["flow"], task_type(meta)):
        clash = rehearsal_clash_refusal(meta, all_tasks(bw, scope))
        if clash:
            sys.exit(clash)
    if is_recurring(meta) and meta["status"] == "done":
        sys.exit(f"error: T{meta['id']} is recurring and never goes done; "
                 f"record a run instead: TASKS recur ran {meta['id']}")
    if is_umbrella(meta) and args.status == "done":
        sys.exit(f"error: T{meta['id']} is an umbrella and never closes on a "
                 f"status flip; record the verification instead: TASKS verify "
                 f"{meta['id']} \"<how the children met the goal>\" "
                 f"(or /dev {meta['id']} to do that pass)")
    if args.status in OPEN_PR and (meta.get("pr") or "").strip():
        sys.exit(f"error: T{meta['id']} has a PR; draft and review are not "
                 f"set by hand — they move with the PR: TASKS ready "
                 f"{meta['id']} / TASKS unready {meta['id']}")
    if meta["status"] == "doing":
        undone = [d for d in meta["deps"]
                  if find_task(bw, scope, d)["status"] != "done"]
        if undone:
            print(f"warning: T{meta['id']} has unfinished deps: {undone}",
                  file=sys.stderr)
    with open(meta["path"], "w", newline="\n") as f:
        f.write(render_task(meta))
    board_commit(root, branch, bw, scope,
                 f"dev: update T{meta['id']} ({', '.join(changes)})")
    print(f"T{meta['id']} updated: {', '.join(changes)}")
    for n in notes:
        print(n, file=sys.stderr)


STOPWORDS = {"the", "and", "for", "with", "that", "this", "add", "use",
             "into", "from", "when", "make", "support", "task", "new"}


def terms(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower())
            if len(w) > 2 and w not in STOPWORDS}


def cmd_related(args):
    """Rank existing tasks against a proposed title/description, so the agent
    can spot duplicates and dependency neighbours before adding."""
    root, scope, branch, bw = ctx()
    tasks = all_tasks(bw, scope)
    hits = related_hits(args.text, tasks)
    if not hits:
        print("(nothing related)")
    for score, t in hits[:8]:
        print(f"{score:.2f} {fmt_line(t, tasks)}")
    for u, under in dep_umbrellas(parse_id_list(args.deps), tasks):
        held = ", ".join(f"T{d}" for d in under)
        print(f"umbrella of {held}: {fmt_line(u, tasks)}")


def dep_umbrellas(dep_ids, tasks):
    """Open umbrellas holding any of `dep_ids` as a direct child, with the
    deps each holds: (umbrella, [ids]) in umbrella-id order. An umbrella that
    is itself one of the deps is left out — the new task waits on it, so it
    cannot also sit under it."""
    want = set(dep_ids)
    out = []
    for t in sorted(tasks, key=lambda t: t["id"]):
        if (not is_umbrella(t) or t["id"] in want
                or t.get("status") in ("done", "not-planned")):
            continue
        under = sorted(d for d in t.get("deps", []) if d in want)
        if under:
            out.append((t, under))
    return out


def related_hits(text, items, fields=("title", "body")):
    """(score, item) for every item related to `text`, best first.

    Shared by `related` and both watch-mode searches, so all rank alike.
    `fields[0]` is the title; every field feeds the shared terms.
    """
    qt = terms(text)
    hits = []
    for t in items:
        words = " ".join(t.get(k, "") for k in fields)
        overlap = len(qt & terms(words)) / len(qt) if qt else 0
        # Character similarity is noisy on short strings — only let it speak
        # when the titles are near-identical; otherwise shared terms decide.
        ratio = difflib.SequenceMatcher(None, text.lower(),
                                        t[fields[0]].lower()).ratio()
        score = max(overlap, ratio if ratio >= 0.55 else 0)
        if score >= 0.3:
            hits.append((score, t))
    return sorted(hits, key=lambda h: -h[0])


def cmd_delete(args):
    root, scope, branch, bw = ctx()
    meta = find_task(bw, scope, args.id)
    os.remove(meta["path"])
    board_commit(root, branch, bw, scope,
                 f"dev: delete T{meta['id']} {meta['title']}")
    print(f"T{meta['id']} deleted")


def cmd_show(args):
    root, scope, branch, bw = ctx()
    meta = find_task(bw, scope, args.id)
    show_file(meta["path"], bw, scope, args.raw)


def cmd_list(args):
    root, scope, branch, bw = ctx()
    tasks = all_tasks(bw, scope)
    flow = find_flow(bw, scope, args.flow) if args.flow else None
    sel = [t for t in tasks
           if (not args.assignee or t.get("assignee") == args.assignee)
           and (flow is None or task_follows_flow(t, flow))
           and (not args.status or t.get("status") == args.status)
           and (not args.needs or t.get("needs") == args.needs)
           and (args.type is None
                or task_type(t) == (args.type.strip() or DEV))]
    if args.json:
        out = [{k: t.get(k, "") for k in FIELDS + ["body"]} for t in sel]
        for o, t in zip(out, sel):
            o["type"] = task_type(t)
        print(json.dumps(out, indent=1))
    elif not sel:
        print("(no matching tasks)")
    else:
        for t in sel:
            print(fmt_line(t, tasks))


def recur_due_sort(t):
    """Overdue first, then by due date; never-run sorts to the very front."""
    due = task_due_date(t)
    return ((0, datetime.date.min, t["id"]) if due is None
            else (1, due_instant(due), t["id"]))


def cmd_recur(args):
    """List recurring tasks with their derived due dates, or record a run."""
    root, scope, branch, bw = ctx()
    tasks = all_tasks(bw, scope)
    if args.recur_cmd == "ran":
        meta = find_task(bw, scope, args.id)
        if not is_recurring(meta):
            sys.exit(f"error: T{meta['id']} is not a recurring task "
                     f"(kind: {meta.get('kind') or 'normal'})")
        if meta["status"] == "proposed":
            # Approving a proposal is a human call; never point at a status
            # flip that would do it.
            sys.exit(f"error: T{meta['id']} is proposed; its clock is stopped "
                     f"until a human approves it")
        if not on_the_clock(meta):
            sys.exit(f"error: T{meta['id']} is {meta['status']}; its clock is "
                     f"stopped — revive it (--status backlog) before "
                     f"recording a run")
        # `recur ran` is the no-PR path. Re-arming clears pr and branch, so
        # running it on an in-flight task would orphan the PR and worktree —
        # land (or cleanup) owns that run instead.
        if (meta.get("pr") or "").strip() or (meta.get("branch") or "").strip():
            sys.exit(f"error: T{meta['id']} has a run in flight "
                     f"(branch/PR set); land it (TASKS land {meta['id']}) or "
                     f"clear it (TASKS cleanup {meta['id']}) — `recur ran` is "
                     f"for runs that never had a PR")
        ran = parse_run_time(args.date, "date") if args.date else None
        meta = rearm_recurring(root, scope, branch, bw, meta, ran_on=ran)
        due = task_due_date(meta)
        print(f"T{meta['id']} ran ({last_run_label(meta)}), re-armed to "
              f"backlog; next due {format_due(due)}")
        return
    sel = [t for t in tasks if on_the_clock(t)]
    if args.due:
        sel = [t for t in sel if task_is_due(t)]
    if not sel:
        print("(no due recurring tasks)" if args.due
              else "(no recurring tasks)")
        return
    for t in sorted(sel, key=recur_due_sort):
        print(fmt_line(t, tasks))


def cmd_verify(args):
    """Close an umbrella by recording how its children met its goal.

    Never a status flip — cmd_update refuses that — because all-children-done
    is a rollup, not a judgment. An umbrella never ships, so this record is
    its only outcome line in log.md. Re-running appends another record.
    """
    root, scope, branch, bw = ctx()
    meta = find_task(bw, scope, args.id)
    if not is_umbrella(meta):
        sys.exit(f"error: T{meta['id']} is not an umbrella "
                 f"(kind: {meta.get('kind') or 'normal'}); verify closes a "
                 f"goal against its children")
    text = " ".join((args.text or "").split())
    if not text:
        sys.exit(f"error: verify needs the record: how T{meta['id']}'s "
                 f"children met its goal")
    live = live_ref_refusal("the verify record", text)
    if live:
        sys.exit(f"error: {live}")
    meta["body"] = append_body(meta["body"], format_verified(text))
    meta["status"] = "done"
    with open(meta["path"], "w", newline="\n") as f:
        f.write(render_task(meta))
    board_commit(root, branch, bw, scope,
                 f"dev: verify T{meta['id']} (closed)")
    print(f"T{meta['id']} closed: {format_verified(text)}")


def cmd_ran(args):
    """Close an ops task with its run record.

    The ops analogue of ship + land in one step: there is no branch and no
    PR, so the record is the whole outcome. Appends `Ran (<date>): …`,
    stamps the task's `flow` field with the flows followed, and closes —
    done for a normal task, re-armed via rearm_recurring for a recurring
    one (same as a landed run). With --rehearsal the record is
    `Rehearsed (<date>): …` instead: the task was a dry run of a flow, its
    own one-off task, so a recurring task never takes one.
    """
    root, scope, branch, bw = ctx()
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    if not is_ops(meta):
        sys.exit(f"error: T{tid} is a dev task; it closes when its PR lands "
                 f"(TASKS land {tid}). Only ops tasks close with a run record")
    if meta["status"] in TERMINAL + ("proposed",):
        sys.exit(f"error: T{tid} is {meta['status']}; nothing to record")
    if (meta.get("pr") or "").strip() or (meta.get("branch") or "").strip():
        sys.exit(f"error: T{tid} has a branch/PR set; an ops task never "
                 f"should — clear them first (update {tid} --branch \"\" --pr \"\")")
    text = " ".join((args.record or "").split())
    if not text:
        sys.exit(f"error: ran needs --record \"<inputs; deviations>\": what "
                 f"the run was given and where it departed from the flow")
    live = live_ref_refusal("--record", text)
    if live:
        sys.exit(f"error: {live}")
    if is_rehearsal(meta) and not args.rehearsal:
        sys.exit(f"error: T{tid} is a rehearsal (rehearsal: true); record it "
                 f"as one so it never counts as a real run: "
                 f"ran {tid} --rehearsal --record \"…\"")
    if args.rehearsal and is_recurring(meta):
        sys.exit(f"error: T{tid} is recurring; a rehearsal is its own one-off "
                 f"ops task on the flow, so this task's clock and run history "
                 f"never take one")
    refs = resolve_flow_refs(bw, scope, args.flow) if args.flow else []
    if not refs and meta.get("flow"):
        refs = [f"{i} {n}" for i, n in parse_flow_refs(meta["flow"])]
    if args.rehearsal and not refs:
        sys.exit(f"error: a rehearsal is of a flow; name it: "
                 f"ran {tid} --rehearsal --flow <name> --record \"…\"")
    ran = parse_run_time(args.date, "date") if args.date else None
    day = run_day(ran) if ran else datetime.date.today()
    record = format_ran(text, refs, day.isoformat(),
                        "Rehearsed" if args.rehearsal else "Ran")
    dline, why = ran_distilled_line(meta, all_tasks(bw, scope),
                                    day.isoformat())
    if why:
        sys.exit(f"error: {why}")
    if dline:
        record += "\n\n" + dline
    meta["flow"] = ", ".join(refs)
    if is_recurring(meta):
        meta = rearm_recurring(root, scope, branch, bw, meta, ran_on=ran,
                               record=record)
        due = task_due_date(meta)
        print(f"T{tid} ran ({last_run_label(meta)}), re-armed to backlog; "
              f"next due {format_due(due)}")
    else:
        meta["status"] = "done"
        meta["body"] = append_body(meta["body"], record)
        with open(meta["path"], "w", newline="\n") as f:
            f.write(render_task(meta))
        verb = "rehearsed" if args.rehearsal else "ran"
        board_commit(root, branch, bw, scope, f"dev: T{tid} {verb} (closed)")
        print(f"T{tid} closed" + (" (rehearsal)" if args.rehearsal else ""))
    for line in record.split("\n\n"):
        print(f"  {line}")


def cmd_distilled(args):
    """Record, on a distill sitting, the tasks whose every candidate the
    user has now dealt with: appends `Distilled (<date>): …` and leaves the
    sitting open. The record iteration-close's coverage gate reads."""
    root, scope, branch, bw = ctx()
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    line, why = distilled_verb_line(meta, args.ids, all_tasks(bw, scope))
    if why:
        sys.exit(f"error: {why}")
    meta["body"] = append_body(meta["body"], line)
    with open(meta["path"], "w", newline="\n") as f:
        f.write(render_task(meta))
    board_commit(root, branch, bw, scope, f"dev: T{tid} distilled")
    print(f"T{tid}: {line}")


def cmd_pause(args):
    """Record where a run stopped so a later session resumes from it.

    The counterpart to `ran`: same shape, but the task stays `doing` and
    keeps its assignee — a paused run is open, not finished, and sending it
    back to `backlog` would throw away the fact that it is half-done. The
    flows followed are stamped on the task now rather than at close, so the
    session that picks it up sees them in the frontmatter. A dev task's
    work in progress lives on its branch, so that is committed and pushed
    first (push_dev_work): the record is written only once the work is safe.
    """
    root, scope, branch, bw = ctx()
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    if meta["status"] != "doing":
        sys.exit(f"error: T{tid} is {meta['status']}; only a run under way "
                 f"(doing) can pause")
    at = " ".join((args.at or "").split())
    if not at:
        sys.exit(f"error: pause needs --at \"<step>\": where the run stopped "
                 f"— the flow's step, or what was last done without one")
    text = " ".join((args.record or "").split())
    if not text:
        sys.exit(f"error: pause needs --record \"<what exists so far>\": what "
                 f"the run produced, and where it lives, so the next session "
                 f"can pick it up")
    live = live_ref_refusal("the pause record", at, text)
    if live:
        sys.exit(f"error: {live}")
    refs = resolve_flow_refs(bw, scope, args.flow) if args.flow else []
    if not refs and meta.get("flow"):
        refs = [f"{i} {n}" for i, n in parse_flow_refs(meta["flow"])]
    if refs:
        meta["flow"] = ", ".join(refs)
    record = format_paused(text, refs, at,
                           iso_date(args.date, "date").isoformat()
                           if args.date else None)
    if not is_ops(meta):
        push_dev_work(root, scope, branch, bw, meta, "paused")
    meta["body"] = append_body(meta["body"], record)
    with open(meta["path"], "w", newline="\n") as f:
        f.write(render_task(meta))
    board_commit(root, branch, bw, scope, f"dev: T{tid} paused")
    print(f"T{tid} paused (still doing, assigned to "
          f"{meta.get('assignee') or 'nobody'})")
    print(f"  {record}")
    resume = f"/ops run {tid}" if is_ops(meta) else f"/dev {tid}"
    print(f"  resume with: {resume}")


def cmd_wait(args):
    """Mark doing work as waiting on someone outside, or clear the mark.

    The work reached an [external] step, or handed a sequence to an agent
    whose report comes later: the task stays `doing` with its
    assignee (a dev task keeps its branch and its area locks), the
    `waiting` marker says who and by when (the board's flag and its
    index 📨 mark), and a `Waiting (<date>): …` record keeps the
    trace after the marker is gone. Re-running it moves the date. `--clear`
    is for the reply arriving mid-run; leaving doing clears it anyway.
    A dev task's branch is committed and pushed first, as pause does: the
    reply may be days out, and the work must not live only in this checkout.
    """
    root, scope, branch, bw = ctx()
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    if meta["status"] != "doing":
        sys.exit(f"error: T{tid} is {meta['status']}; only work under way "
                 f"(doing) can wait")
    if args.clear:
        if args.on or args.by or args.at or args.record or args.flow:
            sys.exit("error: --clear takes no other flags")
        if not (meta.get("waiting") or "").strip():
            sys.exit(f"error: T{tid} is not waiting on anyone")
        meta["waiting"] = ""
        with open(meta["path"], "w", newline="\n") as f:
            f.write(render_task(meta))
        board_commit(root, branch, bw, scope, f"dev: T{tid} waiting cleared")
        print(f"T{tid} no longer waiting (still doing)")
        return
    who = " ".join((args.on or "").split())
    if not who:
        sys.exit(f"error: wait needs --on \"<who>\": the third party or agent "
                 f"the run now waits on")
    if not args.by:
        sys.exit("error: wait needs --by YYYY-MM-DD: when their reply is "
                 "expected")
    by = iso_date(args.by, "--by").isoformat()
    at = " ".join((args.at or "").split())
    if not at:
        sys.exit("error: wait needs --at \"<step>\": the [external] step, or "
                 "the handed-off sequence's last step, the run waits at")
    text = " ".join((args.record or "").split())
    if not text:
        sys.exit(f"error: wait needs --record \"<what was sent, and where>\": "
                 f"what they have, so the resume can pick up their reply")
    live = live_ref_refusal("the wait record", who, at, text)
    if live:
        sys.exit(f"error: {live}")
    refs = resolve_flow_refs(bw, scope, args.flow) if args.flow else []
    if not refs and meta.get("flow"):
        refs = [f"{i} {n}" for i, n in parse_flow_refs(meta["flow"])]
    if refs:
        meta["flow"] = ", ".join(refs)
    record = format_waiting(text, refs, at, who, by,
                            iso_date(args.date, "date").isoformat()
                            if args.date else None)
    if not is_ops(meta) and task_branch_name(meta):
        push_dev_work(root, scope, branch, bw, meta, "waiting")
    meta["waiting"] = f"{who} by {by}"
    meta["body"] = append_body(meta["body"], record)
    with open(meta["path"], "w", newline="\n") as f:
        f.write(render_task(meta))
    board_commit(root, branch, bw, scope, f"dev: T{tid} waiting")
    print(f"T{tid} waiting on {who} by {by} (still doing)")
    print(f"  {record}")
    resume = f"/ops run {tid}" if is_ops(meta) else f"/dev {tid}"
    print(f"  when the reply is in: {resume}")


def note_refusal(meta):
    """Why task `meta` cannot take a note, or None. Any type and any status
    a run has touched or will touch — `done` included, since a forgotten
    note is most often remembered at the post-run flow tweak, after the
    close. `proposed` and `not-planned` never ran. Pure."""
    if meta["status"] in ("proposed", "not-planned"):
        return (f"T{meta['id']} is {meta['status']}; nothing has run to "
                f"note")
    return None


def cmd_note(args):
    """Append a note to a task's run history (ops or dev — a dev wake notes
    a harness refusal). Status, assignee and the `flow` field are left
    alone: a note records, it does not move the task.
    """
    root, scope, branch, bw = ctx()
    meta = find_task(bw, scope, args.id)
    tid = meta["id"]
    refusal = note_refusal(meta)
    if refusal:
        sys.exit(f"error: {refusal}")
    text = " ".join((args.text or "").split())
    if not text:
        sys.exit("error: note needs its text: what the flow did not predict")
    live = live_ref_refusal("the note", args.at or "", text)
    if live:
        sys.exit(f"error: {live}")
    refs = [f"{i} {n}" for i, n in parse_flow_refs(meta.get("flow") or "")]
    record = format_note(text, refs, args.at,
                         iso_date(args.date, "date").isoformat()
                         if args.date else None)
    meta["body"] = append_body(meta["body"], record)
    with open(meta["path"], "w", newline="\n") as f:
        f.write(render_task(meta))
    board_commit(root, branch, bw, scope, f"dev: T{tid} note")
    print(f"T{tid} noted")
    print(f"  {record}")


def inputs_refusal(meta, text):
    """Why `Inputs: <text>` cannot be recorded on task `meta`, or None.
    Inputs are recorded before a run starts or while it is under way, so a
    closed or unapproved task takes none. Pure."""
    if meta["status"] in TERMINAL + ("proposed",):
        return (f"T{meta['id']} is {meta['status']}; inputs are recorded "
                f"for a run about to start or under way")
    if not text:
        return ("inputs needs the values: \"<input>=<value>; …\", under the "
                "flow's input names")
    return live_ref_refusal("the inputs line", text)


def cmd_inputs(args):
    """Record the values a run was given as `Inputs: …`, its own write path
    so the live-reference guard covers it (--append stays live). No date and
    no flow tag: the line shape trim_run_records and resumes already read.
    """
    root, scope, branch, bw = ctx()
    meta = find_task(bw, scope, args.id)
    text = " ".join((args.text or "").split())
    refusal = inputs_refusal(meta, text)
    if refusal:
        sys.exit(f"error: {refusal}")
    record = f"Inputs: {text}"
    meta["body"] = append_body(meta["body"], record)
    with open(meta["path"], "w", newline="\n") as f:
        f.write(render_task(meta))
    board_commit(root, branch, bw, scope, f"dev: T{meta['id']} inputs")
    print(f"T{meta['id']} inputs recorded")
    print(f"  {record}")


def cmd_collisions(args):
    """Area occupancy vs in-flight work. Exit 2 blocked, 3 PR open.

    One id matches watch-mode. Several ids: each vs in-flight *outside*
    the set (batch peers are sequential); then ``set:`` lines for
    in-set area overlap and the watch-mode group's ``parallel:`` verdict
    (both informational, neither fails).

    Exit 3 when every blocker already has a PR open (``draft`` or
    ``review``, any assignee): there is a pushed tip to stack on, so
    implement offers proceed / stack / wait rather than aborting
    (routes/implement.md). Draft counts because a slow draft must not park
    the areas it touches — its PR is out, whether or not its author has
    asked for review yet. A single ``doing`` blocker has nothing pushed to
    build on and is still moving — that stays exit 2, and an unattended run
    skips both.
    """
    root, scope, branch, bw = ctx()
    tasks = all_tasks(bw, scope)
    ids = parse_id_list(" ".join(args.ids))
    if not ids:
        sys.exit("error: collisions needs at least one task id")
    by_id = {t["id"]: t for t in tasks}
    missing = [i for i in ids if i not in by_id]
    if missing:
        sys.exit("error: no task with id " +
                 ",".join(str(i) for i in missing))
    exclude = ids if len(ids) > 1 else None
    blockers = {}
    for tid in ids:
        task = by_id[tid]
        hits = in_flight_area_collisions(task, tasks, exclude_ids=exclude)
        print(format_area_collisions(task, hits))
        for o in hits:
            blockers.setdefault(o["id"], o)
    if len(ids) > 1:
        for a, b in set_area_overlaps(ids, tasks):
            print(f"set: T{a['id']} overlaps T{b['id']}")
        live = [i for i in ids if by_id[i].get("status") not in TERMINAL]
        if len(live) > 1:
            print(parallel_line(group_verdicts(live, tasks)[0]))
    if not blockers:
        return
    all_hits = [blockers[i] for i in sorted(blockers)]
    if all(o.get("status") in OPEN_PR for o in all_hits):
        bits = ", ".join(
            f"T{o['id']} [{o['status']}] ({o.get('assignee') or 'unassigned'})"
            for o in all_hits)
        print(f"pr-open: {bits} — proceed, stack, or wait "
              f"(routes/implement.md)")
        sys.exit(3)
    sys.exit(2)


# 16-color SGR. Paint-time only — never write these into TASKS.md.
_DIM, _OK, _ERR, _NEEDS = "2", "32", "31", "33;1"
_FLOW_NAME = "36"  # cyan: flow names in the flows pane
_STATUS_COLOR = {
    "proposed": "2",      # dim
    "backlog": "34",      # blue
    "planned": "36",      # cyan
    "doing": "33",        # yellow
    "draft": "2;35",      # dim magenta — review's colour, muted
    "review": "35",       # magenta
    "done": "32",         # green
    "shelved": "2",
    "not-planned": "2",
}
_ASSIGNEE_COLORS = (
    "91", "92", "93", "94", "95", "96",
    "31", "32", "33", "34", "35", "36",
)


def _use_color():
    """Color tty stdout unless NO_COLOR is set or TERM is dumb. Never on
    Windows, whose console may not read ANSI escapes."""
    if WINDOWS:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def _ansi(code, text):
    return f"\033[{code}m{text}\033[0m"


def _status_ansi(status, text):
    return _ansi(_STATUS_COLOR.get(status, "0"), text)


def _assignee_ansi(name, text):
    n = 0
    for c in name:
        n = (n * 31 + ord(c)) & 0xFFFFFFFF
    return _ansi(_ASSIGNEE_COLORS[n % len(_ASSIGNEE_COLORS)], text)


def fmt_line(t, tasks, color=False):
    by_id = {x["id"]: x for x in tasks}
    blocked = any(by_id.get(d, {}).get("status") != "done" for d in t["deps"])
    tid, st = f"T{t['id']}", f"[{t['status']}]"
    if color:
        tid, st = _status_ansi(t["status"], tid), _status_ansi(t["status"], st)
    parts = [tid, st]
    if is_ops(t):
        parts.append(_ansi(_DIM, "⚙ops") if color else "⚙ops")
    if t.get("flow"):
        names = ",".join(n for _, n in parse_flow_refs(t["flow"]))
        if names:
            parts.append(_ansi(_DIM, f"⇢{names}") if color else f"⇢{names}")
    if t.get("area"):
        area = f"({t['area']})"
        parts.append(_ansi(_DIM, area) if color else area)
    parts.append(t["title"])
    if t.get("assignee"):
        who = f"@{t['assignee']}"
        parts.append(_assignee_ansi(t["assignee"], who) if color else who)
    if task_unattended(t):
        run = f"unattended:{task_unattended(t)}"
        parts.append(_ansi(_DIM, run) if color else run)
    if t.get("needs"):
        flag = f"❓needs-{t['needs']}"
        parts.append(_ansi(_NEEDS, flag) if color else flag)
    w = task_waiting(t)
    if w:
        flag = f"📨waiting {w[0]} by {w[1].isoformat()}"
        sgr = _ERR if w[1] < datetime.date.today() else _NEEDS
        parts.append(_ansi(sgr, flag) if color else flag)
    if on_the_clock(t):
        mark, sgr = recur_marker(t)
        parts.append(_ansi(sgr, mark) if color else mark)
    stalled = routine_stall_text(t)
    if stalled:
        sgr = _NEEDS if t["routine_stall"][0] == "paused" else _ERR
        parts.append(_ansi(sgr, stalled) if color else stalled)
    if is_umbrella(t):
        roll = umbrella_rollup(t, tasks)
        parts.append(_ansi(_DIM, roll) if color else roll)
    elif blocked and t["status"] not in OPEN_PR + TERMINAL:
        blk = f"⊘blocked-by:{','.join(str(d) for d in t['deps'])}"
        parts.append(_ansi(_ERR, blk) if color else blk)
    return " ".join(parts)


def _status_label(status):
    return STATUS_LABEL.get(status, status.capitalize())


def recur_marker(t, today=None):
    """(text, sgr) for a recurring task's derived due state.

    Due or overdue reads like a blocker (red); armed and waiting is dim, the
    same weight as the area — it is the least actionable thing on the board.
    """
    due = task_due_date(t)
    if due is None:
        return "⏰due now", _ERR
    now = (due_instant(today) if today
           else datetime.datetime.now().astimezone())
    if due_instant(due) <= now:
        return f"⏰due {format_due(due)}", _ERR
    return f"↻{format_due(due)}", _DIM


def _fmt_id(t, color=False):
    """One index id, carrying the same marks as its line: ↻ for a recurring
    task on the clock (⏰ when due, 🚨 when its routine did not start it),
    then ❓ for an open needs, then 📨 for a run waiting on someone else
    (T81↻❓📨). Emoji only for marks that ask for attention (❓ 📨 ⏰ 🚨);
    routine marks stay dimmable text glyphs (↻ ⊘ ⚙ ⇢ ☂).
    Marks are plain text too so TASKS.md shows them; in color a due
    recurring id or an overdue wait is red instead of its status color. A
    stopped clock (RECUR_STOPPED) gets no recurring mark."""
    tid = f"T{t['id']}"
    red = False
    if on_the_clock(t):
        red = task_is_due(t)
        tid += ("🚨" if routine_not_started(t) else "⏰" if red else "↻")
    if t.get("needs"):
        tid += "❓"
    w = task_waiting(t)
    if w:
        tid += "📨"
        red = red or w[1] < datetime.date.today()
    if not color:
        return tid
    return _ansi(_ERR, tid) if red else _status_ansi(t["status"], tid)


def _fmt_ids(col, color=False):
    return " ".join(_fmt_id(t, color=color) for t in col)


def _sort_by_status(col, status_order=None):
    """Hottest-first, then T3 recurrence, then id. Own status only."""
    order = status_order or WATCH_STATUSES
    rank = {s: i for i, s in enumerate(order)}
    return sorted(col, key=lambda t: (rank.get(t["status"], 99),
                                      waiting_sort_rank(t),
                                      recur_sort_rank(t), t["id"]))


def _fmt_count(col):
    return f"({len(col)})"


def _index_block(rows):
    """One line per (label, rhs[, sgr]) row; labels padded to a shared width.

    Optional sgr colors the label only. Width uses the uncolored label so
    ANSI codes do not break the column.
    """
    if not rows:
        return []
    width = max(len(row[0]) for row in rows)
    lines = []
    for row in rows:
        label, rhs = row[0], row[1]
        sgr = row[2] if len(row) > 2 else None
        shown = _ansi(sgr, label) if sgr else label
        lines.append(f"{shown}{' ' * (width - len(label))}  {rhs}".rstrip())
    return lines


def _list_block(tasks, expand=False, color=False, status_order=None):
    """In-play tasks one per line, umbrella children indented under the parent.

    --expand also lists done/shelved/not-planned. A child whose umbrella is
    itself unlisted renders at top level, so nothing drops off the board.
    Umbrellas rank by the hottest of their own status and their listed
    descendants'.
    """
    order = status_order or WATCH_STATUSES
    rank = {s: i for i, s in enumerate(order)}
    listed = [t for t in tasks if expand or t["status"] not in TERMINAL]
    by_id = {t["id"]: t for t in listed}
    parent = {}  # child id -> umbrella id; first umbrella by id wins

    def has_ancestor(node, target):
        seen, cur = set(), parent.get(node)
        while cur is not None and cur not in seen:
            if cur == target:
                return True
            seen.add(cur)
            cur = parent.get(cur)
        return False

    for t in sorted(listed, key=lambda t: t["id"]):
        if not is_umbrella(t):
            continue
        for d in t["deps"]:
            if (d in by_id and d not in parent and d != t["id"]
                    and not has_ancestor(t["id"], d)):
                parent[d] = t["id"]
    children = {}
    for cid, pid in parent.items():
        children.setdefault(pid, []).append(cid)

    def hottest_rank(t):
        # parent is a forest (one parent per child, cycle edges dropped
        # above), so this recursion terminates without a visited set. Own
        # status counts: an in-flight umbrella must not sink below its
        # colder children.
        own = rank.get(t["status"], 99)
        return min([own] + [hottest_rank(by_id[c])
                            for c in children.get(t["id"], [])])

    def in_order(col):
        # (hottest of self and listed descendants, recurrence, id).
        # Recurrence stays a within-rank tiebreak (T3) so this rank can
        # move independently.
        return sorted(col, key=lambda t: (hottest_rank(t),
                                          waiting_sort_rank(t),
                                          recur_sort_rank(t), t["id"]))

    lines = []

    def emit(t, depth):
        lines.append("  " * depth + fmt_line(t, tasks, color=color))
        for kid in in_order([by_id[c] for c in children.get(t["id"], [])]):
            emit(kid, depth + 1)

    for t in in_order([t for t in listed if t["id"] not in parent]):
        emit(t, 0)
    return lines


def _board_by_status(tasks, expand=False, color=False, status_order=None):
    order = status_order or WATCH_STATUSES
    rows = []
    for status in order:
        col = [t for t in tasks if t["status"] == status]
        if not col:
            continue
        fold = status in TERMINAL and not expand
        rhs = _fmt_count(col) if fold else _fmt_ids(col, color=color)
        sgr = _STATUS_COLOR.get(status) if color else None
        rows.append((_status_label(status), rhs, sgr))
    lines = _index_block(rows)
    listed = _list_block(tasks, expand=expand, color=color,
                         status_order=order)
    if listed:
        lines.append("")
        lines.extend(listed)
    return lines


def _board_by_area(bw, scope, tasks, expand=False, color=False,
                   status_order=None):
    """Group tasks by area. Multi-area tasks appear under each area.

    Index order: areas.md order, then other named areas (sorted), then
    reserved `all`, then untagged. Empty named areas from areas.md are kept
    so the cut shows the full map; empty ad-hoc / all / untagged are omitted.
    Default keeps done/shelved/not-planned off area lines (own count rows)
    so open work stays scannable; --expand puts those ids on area lines too.
    Ids on each area line use the same hottest-first status order as the
    default view, so in-flight work sits left of the backlog.
    """
    indexed = tasks if expand else [
        t for t in tasks if t["status"] not in TERMINAL]
    known = list(read_areas(bw, scope).keys())  # insertion order
    buckets = {name: [] for name in known}
    ad_hoc = {}  # area -> [tasks], excluding known and reserved
    all_col = []
    untagged = []
    for t in indexed:
        areas = split_areas(t.get("area", ""))
        if not areas:
            untagged.append(t)
            continue
        for a in areas:
            if a == "all":
                all_col.append(t)
            elif a in buckets:
                buckets[a].append(t)
            else:
                ad_hoc.setdefault(a, []).append(t)

    def ids(col):
        return _fmt_ids(_sort_by_status(col, status_order), color=color)

    rows = [(name, ids(buckets[name])) for name in known]
    rows.extend((name, ids(ad_hoc[name])) for name in sorted(ad_hoc))
    if all_col:
        rows.append(("all", ids(all_col)))
    if untagged:
        rows.append(("(untagged)", ids(untagged)))
    if not expand:
        # Same order as the status board's folded lines (T99).
        for status in [s for s in status_order or WATCH_STATUSES
                       if s in TERMINAL]:
            col = [t for t in tasks if t["status"] == status]
            if col:
                sgr = _STATUS_COLOR.get(status) if color else None
                rows.append((_status_label(status), _fmt_count(col), sgr))
    lines = _index_block(rows)
    listed = _list_block(tasks, expand=expand, color=color,
                         status_order=status_order)
    if listed:
        lines.append("")
        lines.extend(listed)
    return lines


def _board_text(cfg, scope, bw, tasks, expand=False, by_area=False, color=False,
                status_order=None):
    title = f"# Board — iteration {iteration_label(cfg)}"
    if scope != ".":
        title += f" ({scope})"
    if by_area:
        title += " · by area"
    lines = [title, ""]
    if by_area:
        lines.extend(_board_by_area(
            bw, scope, tasks, expand=expand, color=color,
            status_order=status_order))
    else:
        lines.extend(_board_by_status(
            tasks, expand=expand, color=color,
            status_order=status_order))
    return "\n".join(lines)


# The latest list is for recent activity: read only this many board commits
# so the repaint cost stays flat as history grows.
LATEST_COMMITS = 200


def task_touch_times(bw, scope):
    """{task id: unix time of the last board commit touching its file}.

    One `git log` over the board dir, newest first, so the first sighting of
    a file is its latest touch. Only `NNN.md` at the board root counts —
    archived tasks of earlier iterations are not on the live board. Capped
    at LATEST_COMMITS: a task untouched in that window has no entry.
    """
    d = tdir(scope)
    r = git("log", f"-n{LATEST_COMMITS}", "--format=%x01%ct", "--name-only",
            "--", d, cwd=bw, check=False)
    times, ts = {}, None
    for line in (r.stdout or "").splitlines() if r.returncode == 0 else []:
        if line.startswith("\x01"):
            ts = int(line[1:])
            continue
        m = re.fullmatch(r"(\d{3})\.md", os.path.basename(line))
        if (m and ts is not None
                and os.path.normpath(os.path.dirname(line)) == d):
            times.setdefault(int(m.group(1)), ts)
    return times


def _board_latest_text(cfg, scope, bw, tasks, color=False):
    """Every live task, done included, newest board commit first.

    Tasks older than the LATEST_COMMITS window follow undated, by id.
    """
    title = f"# Board — iteration {iteration_label(cfg)}"
    if scope != ".":
        title += f" ({scope})"
    lines = [title + " · latest", ""]
    times = task_touch_times(bw, scope)
    for t in sorted(tasks, key=lambda t: (-times.get(t["id"], 0), -t["id"])):
        ts = times.get(t["id"])
        when = (datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                if ts is not None else " " * 16)
        when = _ansi(_DIM, when) if color else when
        lines.append(f"{when}  {fmt_line(t, tasks, color=color)}")
    return "\n".join(lines)


def _watch_board(args, latest, bw, scope, resolved=None):
    """(display, tasks) for the watch loop: the board, or the latest list.

    bw/scope come from cmd_board's one ctx(); _render_board re-syncs on each
    refresh unless handed `resolved` (the first paint reuses the entry sync).
    """
    _plain, board, tasks = _render_board(args, resolved)
    if latest:
        board = _board_latest_text(read_board_cfg(bw, scope), scope, bw,
                                   tasks, color=_use_color()).rstrip()
    return board, tasks


def _render_board(args, resolved=None):
    """Fetch, write plain TASKS.md, return (plain, display, tasks).

    resolved is a ctx() result the caller already has, so the board is not
    synced a second time; without it this syncs. display is colorized when
    stdout is a color-capable tty. TASKS.md is always the plain text. Watch
    and static share WATCH_STATUSES so hottest work sits above the fold on
    both.
    """
    root, scope, _branch, bw = resolved or ctx()
    cfg = read_board_cfg(bw, scope)
    tasks = all_tasks(bw, scope)
    expand = bool(getattr(args, "expand", False))
    by_area = bool(getattr(args, "by_area", False))
    plain = _board_text(cfg, scope, bw, tasks, expand=expand, by_area=by_area,
                        status_order=WATCH_STATUSES)
    with open(os.path.join(root, scope, "TASKS.md"), "w", newline="\n") as f:
        f.write(plain)
    if _use_color():
        display = _board_text(cfg, scope, bw, tasks, expand=expand,
                              by_area=by_area, color=True,
                              status_order=WATCH_STATUSES)
    else:
        display = plain
    return plain.rstrip(), display.rstrip(), tasks


def _clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


# CSI / SS3 sequences `_read_tty_byte` may return whole. Only up/down
# scroll; anything else stays ESC so it never leaks as a/A/q.
_KEY_SEQS = {
    "\x1b[A": "up", "\x1b[B": "down",
    "\x1bOA": "up", "\x1bOB": "down",
}


def _read_key(cooked=True):
    """One key from a tty; first character of a line otherwise.

    EOF and Ctrl-D both come back as "\x04" (quit), never "q": a prompt
    that takes letters as text must still be able to tell them apart.

    Read the fd directly — sys.stdin's buffer can swallow the key after
    switching the tty out of canonical mode. Escape consumes a following
    CSI/SS3 so arrow keys do not leak as a/A/q (see `_read_tty_byte`).

    Watch mode holds cbreak for the session (`cooked=False`) so digits typed
    during a repaint are not trapped in the line buffer.
    """
    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        return line[:1] if line else "\x04"
    fd = sys.stdin.fileno()
    if cooked:
        try:
            import termios
            import tty
        except ImportError:
            line = input()
            return line[:1] if line else ""
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            ch = _read_tty_byte(fd)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    else:
        ch = _read_tty_byte(fd)
    if not ch:
        return "\x04"
    if ch == b"\x1b":
        return "\x1b"
    if ch.startswith(b"\x1b"):
        return _KEY_SEQS.get(ch.decode("ascii", "replace"), "\x1b")
    return ch.decode("utf-8", "replace")


_tty_unread = None  # one leftover byte after a lone ESC (not a CSI)


def _read_tty_byte(fd):
    """One keystroke as bytes. ESC consumes a queued CSI/SS3.

    Lone Escape is b'\\x1b'. A CSI/SS3 is the full sequence so callers can
    map arrows. Do not time-drain the buffer: that eats the next typed
    digit. A short poll lets a CSI split across an SSH packet still attach;
    a non-CSI byte after ESC is unread for the next call.
    """
    global _tty_unread
    if _tty_unread is not None:
        ch = _tty_unread
        _tty_unread = None
        return ch
    ch = os.read(fd, 1)
    if ch != b"\x1b":
        return ch
    import select
    if not select.select([fd], [], [], 0.025)[0]:
        return ch
    nxt = os.read(fd, 1)
    if nxt not in (b"[", b"O"):
        _tty_unread = nxt
        return ch
    seq = ch + nxt
    # CSI / SS3: optional parameter bytes, then a final byte in 0x40–0x7E.
    while True:
        if not select.select([fd], [], [], 0.025)[0]:
            break
        extra = os.read(fd, 1)
        if not extra:
            break
        seq += extra
        if 0x40 <= extra[0] <= 0x7E:
            break
    return seq


_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _visible_len(s):
    """Terminal columns, not characters: a wide glyph (the ❓ 📨 ⏰ marks)
    takes two, or wrap counts run short and the frame overflows."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in _ANSI_RE.sub("", s or ""))


def _term_size():
    sz = shutil.get_terminal_size(fallback=(80, 24))
    return max(1, sz.lines), max(1, sz.columns)


def _line_rows(s, cols):
    n = _visible_len(s)
    if cols <= 0:
        return 1
    return max(1, (n + cols - 1) // cols) if n else 1


def _rows_of(lines, cols):
    return sum(_line_rows(ln, cols) for ln in lines)


def _watch_help(by_area, expand, more_above=0, more_below=0, check=False,
                history=False, flows=False, search=False, latest=False,
                back=False, registries=False):
    """`history`: the flows pane's h> prompt is open. `back`: q steps back.
    `registries`: True on the pane's index, "entry" while an entry is open
    (its row numbers are off screen, so none is taken)."""
    r_key = "r refresh"
    q_key = "q back" if back else "q quit"
    if search:
        # Every printable key is query text, so no letter shortcut is live.
        return _watch_help_counts("type query↵  esc cancel  arrows",
                                  more_above, more_below)
    if registries:
        return _watch_help_counts(
            f"{r_key}  f flows  g board  {q_key}"
            f"  · {'' if registries == 'entry' else 'type row number↵  '}"
            f"arrows  space/b page",
            more_above, more_below)
    if flows:
        return _watch_help_counts(
            f"{r_key}  s search  f board  g registries  {q_key}"
            f"  · {'history id↵  h close' if history else 'type flow id↵  h history'}"
            f"  arrows  space/b page",
            more_above, more_below)
    other = "by status" if by_area else "by area"
    fold = "collapse" if expand else "expand"
    query = "check id[,id…]↵" if check else "type id↵"
    # While the latest list is up it owns the screen: a/e do not apply.
    views = "l board" if latest else f"a {other}  e {fold}  l latest"
    help_line = (f"{r_key}  {views}  c check  s search  f flows"
                 f"  g registries  {q_key}"
                 f"  · {query}  arrows  space/b page")
    return _watch_help_counts(help_line, more_above, more_below)


def _watch_help_counts(help_line, more_above, more_below):
    """Append the off-screen line counts to a help line."""
    if more_above or more_below:
        bits = []
        if more_above:
            bits.append(f"↑{more_above}")
        if more_below:
            bits.append(f"↓{more_below}")
        help_line += "  · " + " ".join(bits)
    return help_line


def _watch_footer_lines(by_area, expand, buf, result,
                        more_above=0, more_below=0, check=False,
                        history=False, flows=False, search=False,
                        latest=False, back=False, registries=False,
                        notice=""):
    """`notice`: a sync line (syncing, or the local-copy warning), shown
    above the help line."""
    help_line = _watch_help(by_area, expand, more_above, more_below,
                           check=check, history=history, flows=flows,
                           search=search, latest=latest, back=back,
                           registries=registries)
    if _use_color():
        help_line = _ansi(_DIM, help_line)
    lines = [""]
    if notice:
        lines.append(_ansi(_NEEDS, notice) if _use_color() else notice)
    lines.append(help_line)
    if check or search or history or buf:
        if registries:
            lines.append(f"g> {buf}")
        elif search:
            lines.append(f"s> {buf}")
        elif check:
            lines.append(f"c> {buf}".rstrip())
        elif history:
            lines.append(f"h> {buf}".rstrip())
        else:
            lines.append(f"{'f> ' if flows else '> '}{buf}")
    if result:
        lines.extend(result.split("\n"))
    return lines


def _max_watch_offset(body, body_rows, cols):
    """Largest logical start that still fills `body_rows` from the bottom."""
    if not body:
        return 0
    used = 0
    i = len(body)
    while i > 0:
        need = _line_rows(body[i - 1], cols)
        if used + need > body_rows and used > 0:
            break
        i -= 1
        used += need
    return i


def _window_lines(lines, offset, rows, cols):
    """Logical slice of `lines` starting at `offset` that fits `rows`."""
    if not lines or rows <= 0:
        return [], 0, 0
    offset = max(0, min(offset, _max_watch_offset(lines, rows, cols)))
    shown = []
    used = 0
    i = offset
    while i < len(lines):
        need = _line_rows(lines[i], cols)
        if shown and used + need > rows:
            break
        shown.append(lines[i])
        used += need
        i += 1
        if used >= rows:
            break
    return shown, offset, len(lines) - i


def _watch_page_offsets(body, offset, body_rows, cols):
    """Start offsets one viewport up and down from `offset`."""
    shown, offset, _more = _window_lines(body, offset, body_rows, cols)
    return (_max_watch_offset(body[:offset], body_rows, cols),
            offset + len(shown))


def _paint_watch(out, by_area, expand, buf, result, offset, check=False,
                 history=False, flows=False, search=False, latest=False,
                 back=False, registries=False, notice=""):
    """Paint a terminal-height viewport.

    Returns (clamped offset, page-up offset, page-down offset).
    """
    rows, cols = _term_size()
    body = (out or "").splitlines()
    # First pass: footer without counts, so the body budget is stable.
    footer_rows = _rows_of(
        _watch_footer_lines(by_area, expand, buf, result,
                            check=check, history=history, flows=flows,
                            search=search, latest=latest, back=back,
                            registries=registries, notice=notice), cols)
    body_rows = max(1, rows - footer_rows)
    shown, offset, more_below = _window_lines(body, offset, body_rows, cols)
    more_above = offset
    if more_above or more_below:
        # Counts on the help line can wrap an extra row; re-fit if so.
        footer_rows = _rows_of(
            _watch_footer_lines(by_area, expand, buf, result,
                                more_above, more_below, check=check,
                                history=history, flows=flows, search=search,
                                latest=latest, back=back,
                                registries=registries, notice=notice),
            cols)
        body_rows = max(1, rows - footer_rows)
        shown, offset, more_below = _window_lines(
            body, offset, body_rows, cols)
        more_above = offset
    footer = _watch_footer_lines(by_area, expand, buf, result,
                                 more_above, more_below, check=check,
                                 history=history, flows=flows, search=search,
                                 latest=latest, back=back,
                                 registries=registries, notice=notice)
    _clear_screen()
    # No trailing newline: print() on the last row scrolls the first line off.
    frame = shown + footer
    if frame:
        sys.stdout.write("\n".join(frame))
    sys.stdout.flush()
    page_up, page_down = _watch_page_offsets(body, offset, body_rows, cols)
    return offset, page_up, page_down


def cmd_board_refresh_viewer(root, scope):
    """./board update: rewrite the wrapper from this skill's template."""
    if WINDOWS:
        sys.exit(f"error: there is no ./{VIEWER_NAME} viewer on Windows; "
                 f"{WATCH_WINDOWS_HINT}")
    dest = viewer_path(root, scope)
    if os.path.isdir(dest):
        sys.exit(f"error: {VIEWER_NAME} is a directory")
    if skill_path_is_ephemeral(__file__):
        sys.exit(f"error: refusing to point ./{VIEWER_NAME} at "
                 f"{os.path.abspath(__file__)} — that task worktree is "
                 f"deleted at land; run this from the installed skill")
    edited = False
    if os.path.isfile(dest):
        try:
            edited = not viewer_is_stock(open(dest, encoding="utf-8").read())
        except (OSError, UnicodeDecodeError):
            edited = True
    _, wrote = ensure_board_viewer(root, scope, force=True)
    if not wrote:
        print(f"viewer: ./{VIEWER_NAME} already current")
    elif edited:
        print(f"viewer: rewrote edited ./{VIEWER_NAME} from {os.path.realpath(__file__)}")
    else:
        print(f"viewer: refreshed ./{VIEWER_NAME}")


WATCH_WINDOWS_HINT = ("the live viewer does not run on Windows yet; "
                      "'board' without --watch prints the board")


def cmd_board(args):
    if WINDOWS and getattr(args, "watch", False):
        sys.exit(f"error: board --watch: {WATCH_WINDOWS_HINT}")
    watch = bool(getattr(args, "watch", False))
    if watch and sys.stdin.isatty():
        # The first sync runs before the first paint: say what the wait is.
        print(BOARD_SYNCING, flush=True)
    resolved = ctx()
    root, scope, _branch, bw = resolved
    if getattr(args, "refresh_viewer", False):
        cmd_board_refresh_viewer(root, scope)
        return
    _, wrote = ensure_board_viewer(root, scope)
    if wrote and not (watch and sys.stdin.isatty()):
        print(f"viewer: refreshed ./{VIEWER_NAME}")
    if watch and sys.stdin.isatty():
        fd = sys.stdin.fileno()
        old_term = None
        try:
            import termios
            import tty
            old_term = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        except ImportError:
            pass
        buf = ""
        result = ""
        last_tid = None
        last_kind = None  # "show" | "check" | "search" | None
        last_fid = None   # flows pane: the flow being shown
        history_at = 0    # ...and the line its run history starts on
        history_mode = False  # h> prompt: each flow id↵ opens at history
        last_query = ""   # the search last_kind "search" shows
        check_mode = False
        search_mode = False  # s> prompt open: printable keys are query
        flows_mode = False
        regs_mode = False    # g: the registries pane
        reg_rows = []        # ...its rows, (kind, name) per typed number
        last_reg = None      # ...and the (kind, name) being shown
        latest_mode = False  # l: flat latest-first list replaces the board
        offset = 0
        display = None
        frame = {}  # the last frame's mode flags, for the syncing repaint
        try:
            while True:
                by_area = bool(getattr(args, "by_area", False))
                expand = bool(getattr(args, "expand", False))
                if display is not None:
                    # A refresh re-syncs: keep the last frame up, saying so.
                    _paint_watch(display, by_area, expand, buf, result,
                                 offset, notice=BOARD_SYNCING, **frame)
                board, tasks = _watch_board(args, latest_mode, bw, scope,
                                            resolved)
                resolved = None  # every later refresh re-syncs
                notice = BOARD_SYNC_FAILURE
                display = board
                if regs_mode:
                    display, reg_rows = registries_pane(
                        bw, scope, color=_use_color())
                    if last_reg is not None:
                        view = watch_registry_view(
                            bw, scope, *last_reg, tasks=tasks)
                        if view is None:
                            result = watch_missing_reg(
                                *last_reg, color=_use_color())
                            last_reg = None
                        else:
                            display = view
                            result = ""
                elif flows_mode:
                    display = flows_pane_text(bw, scope, color=_use_color())
                    if last_query:
                        display = watch_flow_search_view(
                            last_query, all_flows(bw, scope),
                            color=_use_color())
                    if last_fid is not None:
                        view = watch_flow_view(bw, scope, last_fid)
                        if view is None:
                            result = watch_missing_fid(
                                last_fid, color=_use_color())
                            last_fid = None
                        else:
                            display, history_at = view
                            result = ""
                            if history_mode:
                                offset = history_at
                elif last_kind == "check" and last_tid is not None:
                    result = watch_check_result(
                        last_tid, tasks, color=_use_color())
                elif last_kind == "search":
                    display = watch_search_view(
                        last_query, tasks, expand=expand,
                        color=_use_color())
                    result = ""
                elif last_kind == "show" and last_tid is not None:
                    view = watch_task_view(last_tid, tasks,
                                           catalog_entries(bw, scope))
                    if view is None:
                        result = watch_missing_tid(
                            last_tid, color=_use_color())
                        last_tid = None
                        last_kind = "search" if last_query else None
                        if last_query:
                            display = watch_search_view(
                                last_query, tasks, expand=expand,
                                color=_use_color())
                    else:
                        display = view
                        result = ""
                while True:
                    frame = dict(
                        check=check_mode, flows=flows_mode,
                        search=search_mode, latest=latest_mode,
                        history=history_mode,
                        registries=("entry" if regs_mode and last_reg
                                    else regs_mode),
                        back=bool(flows_mode or regs_mode or latest_mode
                                  or check_mode
                                  or buf or result
                                  or last_kind is not None))
                    offset, page_up, page_down = _paint_watch(
                        display, by_area, expand, buf, result, offset,
                        notice=notice, **frame)
                    key = _read_key(cooked=old_term is None)
                    pane = flows_mode or regs_mode
                    if key == "\x04":  # Ctrl-D / EOF, even mid-query
                        print()
                        return
                    if search_mode:
                        # Before the letter shortcuts: they would steal
                        # from the query.
                        if key == "\x1b":
                            search_mode = False
                            buf = ""
                        elif key in ("\x7f", "\x08"):
                            buf = buf[:-1]
                        elif key in ("\n", "\r"):
                            if buf.strip():
                                last_query = buf.strip()
                                last_kind = "search"
                                last_tid = None
                                last_fid = None
                                search_mode = False
                                buf = ""
                                offset = 0
                                break
                        elif key == "down":
                            offset += 1
                        elif key == "up":
                            offset = max(0, offset - 1)
                        elif (len(key) == 1 and key.isprintable()
                              and len(buf) < 64):
                            buf += key
                        continue
                    if key in ("q", "Q", "\x1b"):
                        # One level back: typed input or a stray message,
                        # then the output, then the pane (flows, latest).
                        # Only q quits, from the plain board; Esc never
                        # does, since an unknown CSI reads as Esc too.
                        if buf or (result and last_kind != "check"):
                            buf = ""
                            result = ""
                            continue
                        if history_mode:
                            history_mode = False  # the page stays up
                            continue
                        offset = 0
                        if regs_mode:
                            if last_reg is not None:
                                last_reg = None
                            else:
                                regs_mode = False
                        elif flows_mode:
                            if last_fid is not None:
                                last_fid = None
                            elif last_query:
                                last_query = ""
                                last_kind = None  # s> set it in this pane
                            else:
                                flows_mode = False
                        elif last_kind == "show" and last_query:
                            # A task opened from the hits: back to them.
                            last_kind = "search"
                            last_tid = None
                        elif last_kind is not None:
                            # A check result clears to its c> prompt.
                            last_kind = None
                            last_tid = None
                            last_query = ""
                            result = ""
                        elif check_mode:
                            check_mode = False
                        elif latest_mode:
                            latest_mode = False
                        elif key == "\x1b":
                            continue
                        else:
                            print()
                            return
                        break
                    if key in ("r", "R"):
                        buf = ""
                        offset = 0
                        break
                    if not buf and (key in "fF" or key in "gG"):
                        # Each pane key toggles its own pane and closes
                        # the other.
                        if key in "fF":
                            flows_mode = not flows_mode
                            regs_mode = False
                        else:
                            regs_mode = not regs_mode
                            flows_mode = False
                        last_reg = None
                        buf = ""
                        result = ""
                        last_tid = None
                        last_kind = None
                        last_fid = None
                        last_query = ""
                        check_mode = False
                        history_mode = False
                        offset = 0
                        break
                    if not buf and key in "lL" and not pane:
                        latest_mode = not latest_mode
                        buf = ""
                        result = ""
                        last_tid = None
                        last_kind = None
                        last_query = ""
                        offset = 0
                        break
                    if (key in ("a", "A") and not pane
                            and not latest_mode):
                        buf = ""
                        offset = 0
                        args.by_area = not by_area
                        break
                    # e still widens a search shown over the latest list.
                    if (key in ("e", "E") and not pane
                            and (not latest_mode or last_kind == "search")):
                        buf = ""
                        offset = 0
                        args.expand = not expand
                        break
                    if key == "down":
                        offset += 1
                        continue
                    if key == "up":
                        offset = max(0, offset - 1)
                        continue
                    if key == " ":
                        offset = page_down
                        continue
                    if key in ("b", "B"):
                        offset = page_up
                        continue
                    if not buf and key in ("s", "S") and not regs_mode:
                        search_mode = True
                        check_mode = False
                        history_mode = False
                        continue
                    if not buf and key in "cC" and not pane:
                        check_mode = not check_mode
                        if check_mode and last_kind in ("show", "search"):
                            last_tid = None
                            last_kind = None
                            last_query = ""
                            result = ""
                            display = board
                            offset = 0
                        continue
                    if key in ("\x7f", "\x08"):
                        buf = buf[:-1]
                        continue
                    if key in ("\n", "\r"):
                        if not buf:
                            continue
                        if regs_mode:
                            row = parse_watch_fid(buf)
                            buf = ""
                            if row is None or not 1 <= row <= len(reg_rows):
                                msg = f"no row {row}"
                                result = (_ansi(_ERR, msg) if _use_color()
                                          else msg)
                                continue
                            last_reg = reg_rows[row - 1]
                            result = ""
                            offset = 0
                            break
                        if flows_mode:
                            fid = parse_watch_fid(buf)
                            buf = ""
                            color = _use_color()
                            offset = 0
                            index = (watch_flow_search_view(
                                last_query, all_flows(bw, scope),
                                color=color) if last_query else
                                flows_pane_text(bw, scope, color=color))
                            view = (watch_flow_view(bw, scope, fid)
                                    if fid is not None else None)
                            if view is None:
                                last_fid = None
                                display = index
                                result = (watch_missing_fid(fid, color=color)
                                          if fid is not None else
                                          (_ansi(_ERR, "not a flow id")
                                           if color else "not a flow id"))
                                continue
                            last_fid = fid
                            result = ""
                            display, history_at = view
                            if history_mode:
                                offset = history_at
                            continue
                        # In check mode tid is a list of ids (a group).
                        tid = (parse_watch_ids(buf) if check_mode
                               else parse_watch_tid(buf))
                        buf = ""
                        color = _use_color()
                        if tid is None:
                            result = (_ansi(_ERR, "not a task id")
                                      if color else "not a task id")
                            last_tid = None
                            last_kind = "search" if last_query else None
                            display = (watch_search_view(
                                last_query, tasks, expand=expand,
                                color=color) if last_query else board)
                            offset = 0
                            continue
                        board, tasks = _watch_board(
                            args, latest_mode, bw, scope)
                        last_tid = tid
                        offset = 0
                        if check_mode:
                            last_kind = "check"
                            result = watch_check_result(
                                tid, tasks, color=color)
                            display = board
                            continue
                        view = watch_task_view(
                            tid, tasks, catalog_entries(bw, scope))
                        if view is None:
                            last_tid = None
                            last_kind = "search" if last_query else None
                            result = watch_missing_tid(tid, color=color)
                            display = (watch_search_view(
                                last_query, tasks, expand=expand,
                                color=color) if last_query else board)
                            continue
                        last_kind = "show"
                        result = ""
                        display = view
                        continue
                    if not buf and key in "hH" and flows_mode:
                        # Like c: a toggle. On an open flow it also jumps.
                        history_mode = not history_mode
                        if history_mode and last_fid is not None:
                            offset = history_at
                        continue
                    if not buf and key in "tT" and not pane:
                        buf = key
                        continue
                    if (key == "," and check_mode and buf
                            and buf[-1] != "," and len(buf) < 64):
                        buf += key
                        continue
                    if regs_mode and last_reg is not None:
                        # The rows are off screen and may have renumbered
                        # on a refresh: no blind jump, q returns to them.
                        continue
                    if key.isdigit() and len(buf) < (64 if check_mode else 8):
                        buf += key
                        continue
        except KeyboardInterrupt:
            print()
        finally:
            if old_term is not None:
                import termios
                termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
        return
    print(_render_board(args, resolved)[1])
    if BOARD_SYNC_FAILURE:
        print(BOARD_SYNC_FAILURE, file=sys.stderr)


# ---------- iterations ----------

def cmd_iteration(args):
    root, scope, branch, bw = ctx()
    cfg = read_board_cfg(bw, scope)
    tasks = all_tasks(bw, scope)
    # shelved is set aside: omit it from the X/Y done denominator.
    in_play = [t for t in tasks if t["status"] != "shelved"]
    done = sum(1 for t in in_play if t["status"] == "done")
    print(f"scope: {scope}")
    print(f"iteration: {iteration_index(cfg)}")
    print(f"iteration_name: {iteration_name(cfg) or '(none)'}")
    print(f"iteration_started: {iteration_started(cfg) or '(none)'}")
    print(f"integration_branch: {cfg.get('integration_branch', '')}")
    print(f"parent_branch: {cfg.get('parent_branch', '') or '(none)'}")
    print(f"tasks: {done}/{len(in_play)} done")


def archive_dir(scope, index, name=""):
    """Where a closed iteration's task files are kept, relative to repo root.

    A subdirectory of the board dir, so it lands with the board and survives
    into later iterations; task_glob only matches NNN.md at the board root,
    so archived files are never live tasks. Path is archive/{n}-{slug} or
    archive/{n} when unnamed.
    """
    return f"{tdir(scope)}/archive/{iteration_archive_slug(index, name)}"


def find_archive_rel(bw, scope, index):
    """Relative archive dir for this index if it exists non-empty, else None.

    Clash is on the integer, not the display-name slug: 3-mvp and 3 are
    the same iteration.
    """
    root = os.path.join(bw, tdir(scope), "archive")
    if not os.path.isdir(root):
        return None
    want = int(index)
    for ent in sorted(os.listdir(root)):
        if archive_dir_index(ent) != want:
            continue
        d = os.path.join(root, ent)
        if os.path.isdir(d) and os.listdir(d):
            return os.path.join(tdir(scope), "archive", ent)
    return None


def archive_taken(bw, scope, index, name=None):
    """Relative archive dir if this index already holds a closed iteration.

    Ids restart each iteration, so archiving onto an existing directory would
    overwrite another iteration's tasks. Checked at numbering time
    (iteration-new, config iteration) and again at close as a last resort.
    The integer scan ignores pre-3 YYYY-MM-DD dirs; when name is given,
    also refuse a non-empty dest at the computed {n}-{slug} path.
    """
    taken = find_archive_rel(bw, scope, index)
    if taken:
        return taken
    if name is None:
        return None
    rel = archive_dir(scope, index, name)
    d = os.path.join(bw, rel)
    if os.path.isdir(d) and os.listdir(d):
        return rel
    return None


def archived_indexes(bw, scope):
    """Set of iteration indexes that already have a non-empty archive dir."""
    root = os.path.join(bw, tdir(scope), "archive")
    if not os.path.isdir(root):
        return set()
    found = set()
    for ent in os.listdir(root):
        idx = archive_dir_index(ent)
        if idx is None:
            continue
        d = os.path.join(root, ent)
        if os.path.isdir(d) and os.listdir(d):
            found.add(idx)
    return found


def next_iteration_index(bw, scope, current):
    taken = archived_indexes(bw, scope)
    taken.add(int(current))
    return max(taken) + 1


def archived_tasks(bw, scope, index):
    """Parse task files from a closed iteration's archive dir (empty if none)."""
    rel = find_archive_rel(bw, scope, index)
    if not rel:
        return []
    d = os.path.join(bw, rel)
    paths = sorted(glob.glob(os.path.join(d, "[0-9][0-9][0-9].md")))
    return [parse_task(p) for p in paths]


def carries_to_next_iteration(t):
    """shelved = set aside, kept until revived; recurring = perpetual.

    not-planned wins over recurrence: retiring a recurring task is how you
    stop it, so it must not be reseeded back onto the next board.
    """
    if t.get("status") == "not-planned":
        return False
    return t.get("status") == "shelved" or is_recurring(t)


CARRIED_TAG_RE = r"\[carried: [a-z-]+\](?: \S+)?$"


def carried_ids(bw, scope, index):
    """Ids `iteration-close --carry` tagged `[carried: <status>]` in this
    iteration's log.md section. The tag is the only record of the choice:
    the archived file is verbatim."""
    log = os.path.join(bw, tdir(scope), "log.md")
    if not os.path.exists(log):
        return set()
    with open(log) as f:
        text = f.read()
    m = re.search(rf"(?m)^## {int(index)}(?: — .*)?$", text)
    if not m:
        return set()
    rest = text[m.end():]
    nxt = re.search(r"(?m)^## ", rest)
    section = rest[:nxt.start()] if nxt else rest
    return {int(x) for x in re.findall(
        rf"(?m)^- {int(index)}/T(\d+) .*{CARRIED_TAG_RE}", section)}


def remap_dev_batch(body, mapping):
    """Renumber a carried task's Dev-batch line. batch-gate, collisions on
    resume and the one-bump rule all read it, so stale ids would name other
    tasks. Members that did not come back are dropped; a batch of one is no
    batch, so the line goes."""
    m = DEV_BATCH_RE.search(body)
    if not m:
        return body
    ids = [mapping[i] for i in parse_id_list(m.group(1)) if i in mapping]
    # Edit only the stamp's own line, so a body paragraph is never merged.
    start = body.rfind("\n", 0, m.start(1)) + 1
    end = body.find("\n", m.end(1))
    end = len(body) if end < 0 else end + 1
    if len(ids) < 2:
        return body[:start] + body[end:].lstrip("\n")
    return body[:start] + format_dev_batch(ids) + "\n" + body[end:]


# Paragraphs that record one run of a recurring task: its outcome (Ran,
# Rehearsed, Shipped), what happened along the way (Note, Paused, Waiting)
# and what it was given (Inputs — one run's values; the flow declares its
# own inputs).
RUN_RECORD_PARA_RE = re.compile(
    r"^(?:Ran \(\d{4}-\d{2}-\d{2}\)[:.]"
    r"|(?:Rehearsed|Shipped|Note|Paused|Waiting) \(\d{4}-\d{2}-\d{2}\):"
    r"|Inputs:)")
CARRIED_FROM_PARA_RE = re.compile(r"^carried from \d+/T\d+$")


def trim_run_records(body, keep_runs=False):
    """A recurring task's body for the copy reseeded onto the next board:
    every `carried from` paragraph dropped (reseed appends the new one) and,
    unless keep_runs, every per-run paragraph too. A shelved task keeps its
    runs, since it may hold a paused run to resume. The archived copy keeps
    everything, so run history still finds each record where it happened,
    and a trimmed copy has nothing left to double."""
    drop = [CARRIED_FROM_PARA_RE] + ([] if keep_runs else [RUN_RECORD_PARA_RE])
    paras = [p.strip() for p in re.split(r"\n[ \t]*\n", body or "")]
    return "\n\n".join(p for p in paras
                        if p and not any(r.match(p) for r in drop))


def reseed_later_tasks(bw, scope, old_index):
    """Copy carried, shelved and recurring tasks onto the live board.

    Only the outgoing iteration's archive (the one just closed). Scanning
    every archive would duplicate a task that stayed shelved across closes.
    Everything reseeded is numbered compactly, 1..N in old-id order.
    Carried tasks (`iteration-close --carry`) otherwise come back as they
    were — status, assignee, branch, pr and body — and find their worktrees
    by branch, not by id. Deps among everything reseeded are remapped; deps
    on anything else (done, not-planned) are dropped, since a missing id
    reads as an unfinished dep forever.
    A recurring task keeps its cadence, last_run and next_due, so its due
    date survives the iteration boundary untouched; its body loses its
    older `carried from` lines and, unless shelved, its per-run records
    (trim_run_records), which stay in the archive.
    Returns (carried, reseeded): each [(new_meta, old_id), ...] in old-id
    order.
    """
    if old_index is None:
        return [], []
    old_index = int(old_index)
    archived = archived_tasks(bw, scope, old_index)
    keep = carried_ids(bw, scope, old_index)
    carried = sorted((t for t in archived if t["id"] in keep),
                     key=lambda x: x["id"])
    rest = [t for t in archived
            if t["id"] not in keep and carries_to_next_iteration(t)]
    if not carried and not rest:
        return [], []
    nid = max((t["id"] for t in all_tasks(bw, scope)), default=0) + 1
    mapping = {}
    for t in sorted(carried + rest, key=lambda x: x["id"]):
        mapping[t["id"]] = nid
        nid += 1
    kept = []
    for t in carried:
        meta = {k: v for k, v in t.items() if k != "path"}
        meta["id"] = mapping[t["id"]]
        meta["deps"] = [mapping[d] for d in t.get("deps", []) if d in mapping]
        # Distilled lines name the old board's ids, now other tasks'.
        meta["body"] = remap_dev_batch(strip_distilled(t.get("body")), mapping)
        # The marker is what keeps flow run history from doubling: this
        # body's Ran records also live in the archived copy.
        meta["body"] = append_body(meta["body"],
                                   f"carried from {old_index}/T{t['id']}")
        path = os.path.join(bw, tdir(scope), f"{meta['id']:03d}.md")
        with open(path, "w", newline="\n") as f:
            f.write(render_task(meta))
        meta["path"] = path
        kept.append((meta, t["id"]))
    written = []
    today = datetime.date.today().isoformat()
    for t in sorted(rest, key=lambda x: x["id"]):
        new_id = mapping[t["id"]]
        new_deps = [mapping[d] for d in t.get("deps", []) if d in mapping]
        # A recurring task at rest sheds its run records so its file stays
        # short. A shelved one keeps them, and a --carry copy (above) stays
        # whole: either may hold a run to resume from its Paused/Waiting/Inputs.
        body = strip_distilled(t.get("body"))
        if is_recurring(t):
            body = trim_run_records(body, keep_runs=t["status"] == "shelved")
        body = append_body(body, f"carried from {old_index}/T{t['id']}")
        meta = {
            "id": new_id,
            "title": t.get("title") or "",
            "area": t.get("area") or "",
            # Only shelved and recurring tasks are carried. shelved stays
            # shelved (a shelved recurring task too: shelving pauses it), and
            # a proposed recurring task stays proposed — a close no longer
            # leaves one behind, but an archive an older script force-closed
            # may hold one, and reseeding must never promote an unapproved
            # proposal. Anything else is a recurring task at rest, which
            # starts the new board armed and unclaimed (one in flight blocks
            # the close unless --carry took it).
            "status": (t["status"]
                       if t.get("status") in ("shelved", "proposed")
                       else "backlog"),
            "kind": t.get("kind") or "",
            # Carry the type: a recurring ops task that came back as a dev
            # task would be refused by `ran` and demand an area it must not
            # have. `flow` is carried so the task keeps naming the flow it
            # follows; run history stays right because a reseeded task with
            # no record of its own is left out, and its inherited records
            # are skipped through the `carried from` note.
            "type": task_type(t),
            "flow": t.get("flow") or "",
            "rehearsal": t.get("rehearsal") or "",
            "distill": t.get("distill") or "",
            "cadence": t.get("cadence") or "",
            "schedule": t.get("schedule") or "",
            "last_run": t.get("last_run") or "",
            "next_due": t.get("next_due") or "",
            "routine": t.get("routine") or "",
            "assignee": "",
            "branch": "",
            "deps": new_deps,
            "pr": "",
            "needs": t.get("needs") or "",
            "created": today,
            "body": body,
        }
        path = os.path.join(bw, tdir(scope), f"{new_id:03d}.md")
        with open(path, "w", newline="\n") as f:
            f.write(render_task(meta))
        meta["path"] = path
        written.append((meta, t["id"]))
    return kept, written


def distill_skipped_line(why):
    """The log.md line an iteration-close --skip-distill writes."""
    return f"[distill skipped: {why}]"


def distill_gate(tasks, skip_distill, skill):
    """iteration-close's coverage gate: (the --skip-distill reason or None,
    None) to go on, or (None, why) to refuse. The refusal never offers the
    skip — that is the user's call, asked for in so many words."""
    if skip_distill is not None:
        why = " ".join(skip_distill.split())
        if not why:
            return None, '--skip-distill needs "<why>" (logged in log.md)'
        return why, None
    missing = distill_coverage_missing(tasks)
    if missing:
        ids = ", ".join(f"T{i}" for i in missing)
        return None, (f"not yet distilled: {ids}. Run a distill sitting "
                      f"first (/{skill} distill); a task counts once the "
                      "user has dealt with all of its candidates, so a "
                      "sitting stopped partway leaves the rest for the "
                      "next one.")
    return None, None


def cmd_iteration_close(args):
    """Archive task files under .tasks/archive/{n}-{slug}/, index them in
    .tasks/log.md, and remove the live files, committing on the integration
    branch. A parented board then lands via iteration-land; a no-parent
    board rolls the next iteration in place via iteration-new --name."""
    root, scope, branch, bw = ctx()
    cfg = read_board_cfg(bw, scope)
    tasks = all_tasks(bw, scope)
    if not tasks:
        sys.exit("error: no tasks on this board; nothing to close")
    # A recurring task at rest is perpetual, never "finished", so it does not
    # block a close: it archives like everything else and iteration-new
    # reseeds it, the same way shelved tasks carry over. One with a run in
    # flight (doing/draft/review) still blocks. There is no way to close
    # past unfinished work: left behind, its branch and PR would be orphaned
    # (land only reads the live board). --carry keeps them: tagged
    # [carried: <status>] in log.md, they come back at iteration-new with a
    # fresh id and status, branch and PR intact.
    unfinished = [t for t in tasks
                  if t["status"] not in TERMINAL and not recur_at_rest(t)]
    if unfinished and not args.carry:
        ids = ", ".join(f"T{t['id']}" for t in unfinished)
        sys.exit(f"error: unfinished tasks: {ids}. Finish them, shelve "
                 "them, drop them (not-planned), delete them, or "
                 "re-run with --carry to carry them into the next iteration "
                 "as they are.")
    # Every finished task's distill candidates are shown to the user before
    # it is archived; recurring tasks carry their records over, so they are
    # exempt.
    # --skip-distill is the user's call for this close only, logged with its
    # reason; the error never offers it.
    skip, why = distill_gate(tasks, args.skip_distill, invoking_skill())
    if why:
        sys.exit(f"error: {why}")
    carry = {t["id"] for t in unfinished} if args.carry else set()
    idx = iteration_index(cfg)
    name = iteration_name(cfg)
    started = iteration_started(cfg)
    today = datetime.date.today().isoformat()
    parent = (cfg.get("parent_branch") or "").strip()
    require_schema3_archive_slug(idx, name)
    arel = archive_dir(scope, idx, name)
    adir = os.path.join(bw, arel)
    # Normally caught at numbering time; reachable only if the archive
    # appeared after this iteration was numbered (a merge from the parent,
    # say). Fail closed — the whole point of the archive is that nothing
    # is lost.
    taken = archive_taken(bw, scope, idx, name)
    if taken:
        sys.exit(f"error: iteration {idx} already has an archive at "
                 f"{taken}/; closing would overwrite it. Renumber first: "
                 f"TASKS config iteration <n>")
    os.makedirs(adir, exist_ok=True)
    entry = [iteration_close_heading(idx, name)]
    if started:
        entry.append(f"started: {started}")
    entry.append(f"closed: {today}")
    extra = f" → {parent}" if parent else ""
    entry.append(f"branch: {branch}{extra}")
    entry.append(f"archive: {arel}/")
    if skip is not None:
        entry.append(distill_skipped_line(skip))
    for t in tasks:
        line = f"- {idx}/T{t['id']} {t['title']}"
        if t.get("assignee"):
            line += f" — {t['assignee']}"
        if t.get("area"):
            line += f" [{t['area']}]"
        if t["status"] == "not-planned":
            line += " [not planned]"
        elif t["status"] == "shelved":
            line += " [shelved]"
        elif is_recurring(t):
            line += f" [recurring {t.get('cadence') or t.get('schedule')}]"
            if not recur_at_rest(t):
                line += f" [carried: {t['status']}]"
        elif t["status"] != "done":
            line += f" [carried: {t['status']}]"
        if t.get("pr"):
            line += f" {t['pr']}"
        entry.append(line)
        # The log is the index; the archived file next to it holds everything.
        # Shipped/Verified records ride along so the result is visible at a
        # skim — an umbrella has no ship, so Verified is its only outcome line.
        body = t.get("body") or ""
        for rec in (collect_shipped(body) + collect_verified(body)
                    + collect_ran(body) + collect_rehearsed(body)):
            entry.append("  - " + " ".join(rec.split()))
    log = os.path.join(bw, tdir(scope), "log.md")
    existing = open(log).read() if os.path.exists(log) else "# Iteration log\n"
    with open(log, "w", newline="\n") as f:
        f.write(existing.rstrip() + "\n\n" + "\n".join(entry) + "\n")
    for t in tasks:
        # Copy verbatim, then remove: frontmatter (area, deps, pr, created)
        # and the full body — Decision:, Shipped:, not-planned reason — are
        # preserved exactly, with no parse/render round-trip to lose them.
        shutil.copyfile(t["path"],
                        os.path.join(adir, os.path.basename(t["path"])))
        os.remove(t["path"])
    board_commit(root, branch, bw, scope, f"dev: close iteration {idx}")
    print(f"iteration {idx} closed: {len(tasks)} tasks archived to "
          f"{arel}/ and indexed in {tdir(scope)}/log.md")
    if carry:
        ids = ", ".join(f"T{i}" for i in sorted(carry))
        print(f"carried to the next iteration: {ids} (iteration-new reseeds "
              "them with fresh ids, status, branch and PR intact)")
    if parent:
        print(f"next: TASKS iteration-land  # merge-commit PR into '{parent}'")
        print(f"      then after merge: TASKS iteration-new <branch>")
    else:
        print(f"next: TASKS iteration-new --name <name>  "
              f"# same branch '{branch}', no land")


def stamp_next_iteration(bw, scope, cfg, old_idx, args):
    """Write the next iteration identity onto cfg. Returns the new index."""
    if args.iteration is not None:
        new_idx = parse_positive_int(args.iteration, "iteration")
    else:
        new_idx = next_iteration_index(bw, scope, old_idx)
    new_name = (args.name or "").strip()
    require_schema3_archive_slug(new_idx, new_name)
    # Visible here (close already wrote the outgoing archive) and free to
    # fix — pick another number rather than discovering it at the next
    # close, with a board full of tasks.
    taken = archive_taken(bw, scope, new_idx, new_name)
    if taken:
        sys.exit(f"error: iteration {new_idx} already has an archive at "
                 f"{taken}/; closing it later would overwrite that "
                 "iteration. Pick another number: iteration-new "
                 "--iteration <n>")
    started = parse_iso_date(
        args.iteration_started or datetime.date.today().isoformat(),
        "iteration_started")
    cfg["iteration"] = str(new_idx)
    cfg["iteration_name"] = new_name
    cfg["iteration_started"] = started
    return new_idx


def report_reseeded(carried, reseeded, old_idx):
    if carried:
        bits = ", ".join(f"T{m['id']} ← {old_idx}/T{oid}"
                         for m, oid in carried)
        print(f"carried {len(carried)} unfinished task(s): {bits}")
    if reseeded:
        bits = ", ".join(f"T{m['id']} ← {old_idx}/T{oid}"
                         for m, oid in reseeded)
        print(f"reseeded {len(reseeded)} shelved/recurring task(s): "
              f"{bits}")


def retarget_carried_prs(root, carried, old_branch, new_branch):
    """Point carried tasks' open PRs at the new integration branch.

    Best-effort: the board is already committed, so a failure warns with
    the command to finish by hand. Only PRs based on the old integration
    branch move — a PR stacked on another task branch keeps its base.
    """
    prs = [m["pr"] for m, _ in carried if m.get("pr")]
    if not prs:
        return
    if not shutil.which("gh"):
        print(f"warning: gh not found; retarget these PRs from "
              f"'{old_branch}' to '{new_branch}' by hand: {' '.join(prs)}",
              file=sys.stderr)
        return
    for url in prs:
        info = pr_view(root, url, soft=True)
        if not info:
            print(f"warning: could not read {url}; if it is based on "
                  f"'{old_branch}', run: {pr_hint_retarget(url, new_branch)}",
                  file=sys.stderr)
            continue
        state = (info.get("state") or "").upper()
        if state == "CLOSED":
            # Deleting a base branch closes the PRs on it, so a repo that
            # deletes merged branches closed these when the iteration landed.
            print(f"warning: {url} is closed — probably when '{old_branch}' "
                  f"was deleted after the iteration landed. Restore that "
                  f"branch, reopen the PR, then run: "
                  f"{pr_hint_retarget(url, new_branch)}", file=sys.stderr)
            continue
        if state != "OPEN":
            continue
        if info.get("baseRefName") != old_branch:
            continue
        r = pr_cmd("edit", url, "--base", new_branch, cwd=root)
        if r.returncode != 0:
            print(f"warning: could not retarget {url} to '{new_branch}'; "
                  f"run: {pr_hint_retarget(url, new_branch)}\n"
                  f"{(r.stderr or r.stdout or '').strip()}", file=sys.stderr)
            continue
        print(f"retarget {url}: {old_branch} → {new_branch}")


def cmd_iteration_new(args):
    root, scope, old_branch, bw = ctx()
    cfg = read_board_cfg(bw, scope)
    old_idx = iteration_index(cfg)
    parent = (args.parent or cfg.get("parent_branch") or "").strip()
    new_branch = (args.branch or "").strip()
    if not parent:
        # No parent to merge into: archive is already on this branch, so
        # roll the next iteration in place. Do not reset — that would
        # drop the close's archive dir and log.md section.
        if new_branch and new_branch != old_branch:
            sys.exit(
                f"error: no parent_branch; in-place iteration-new stays on "
                f"'{old_branch}' — omit the branch. To start a branched "
                "iteration, pass --parent <branch> and a new branch name")
        not_ready = iteration_close_ready(
            bw, scope, old_idx, next_cmd="iteration-new")
        if not_ready:
            sys.exit(f"error: {not_ready}")
        new_idx = stamp_next_iteration(bw, scope, cfg, old_idx, args)
        write_board_cfg(bw, scope, cfg)
        carried, reseeded = reseed_later_tasks(bw, scope, old_idx)
        board_commit(root, old_branch, bw, scope,
                     f"dev: start iteration {new_idx}")
        label = (f" — {cfg['iteration_name']}"
                 if cfg.get("iteration_name") else "")
        print(f"iteration {new_idx}{label} started in place on '{old_branch}'")
        report_reseeded(carried, reseeded, old_idx)
        return
    if not new_branch:
        sys.exit("error: iteration-new on a parented board needs a new "
                 f"integration branch (not '{old_branch}')")
    if new_branch in (old_branch, parent):
        sys.exit(f"error: new iteration branch must differ from '{old_branch}' "
                 f"and parent '{parent}'")
    git("fetch", "origin", parent, old_branch, cwd=bw, check=False)
    start = f"origin/{parent}" if ref_exists(root, f"origin/{parent}") else parent
    if not ref_exists(root, start):
        sys.exit(f"error: parent branch '{parent}' not found locally or on origin")
    # The new board starts from the parent, so anything still sitting on the
    # outgoing branch is invisible to it: its archive dir (missed by the
    # collision check below) and its log.md close section (which the new
    # iteration would then re-append around, conflicting at land). Same
    # predicate iteration-land uses for "already landed" — ancestry, not PR
    # state. Fail closed: land first, then start the next iteration.
    old_ref = (f"origin/{old_branch}" if ref_exists(root, f"origin/{old_branch}")
               else old_branch)
    if not ref_exists(root, old_ref):
        sys.exit(f"error: current integration branch '{old_branch}' not found "
                 "locally or on origin")
    landed = git("merge-base", "--is-ancestor", old_ref, start,
                 cwd=root, check=False)
    if landed.returncode != 0:
        sys.exit(f"error: '{old_branch}' is not yet contained in '{parent}'; "
                 "its archive and log.md close section would be missing from "
                 "the new board. Close and land first: TASKS iteration-land")
    if unpushed_board_commits(bw):
        sys.exit(f"error: board commits are queued on "
                 f"{board_branch_name(scope)} and not yet pushed to "
                 f"'{old_branch}'; starting the new iteration would drop them. "
                 "Re-run once the push goes through.")
    git("reset", "--hard", start, cwd=bw)
    # defensively clear any task files inherited from the parent
    for p in task_glob(bw, scope):
        os.remove(p)
    os.makedirs(os.path.join(bw, tdir(scope)), exist_ok=True)
    cfg["integration_branch"] = new_branch
    cfg["parent_branch"] = parent
    new_idx = stamp_next_iteration(bw, scope, cfg, old_idx, args)
    write_board_cfg(bw, scope, cfg)
    carried, reseeded = reseed_later_tasks(bw, scope, old_idx)
    if not board_commit(root, new_branch, bw, scope,
                        f"dev: start iteration {new_idx}", queue=False):
        git("reset", "--hard", old_ref, cwd=bw)
        sys.exit(f"error: the new board did not reach '{new_branch}'; nothing "
                 "was started. Re-run once the push can go through.")
    write_cache(root, scope, new_branch)
    new_tip = git("rev-parse", "HEAD", cwd=bw).stdout.strip()
    # Point the parent and the old branch at the new one, so a checkout on
    # either resolves to the live board (resolve_board follows it). The
    # parent gets the new board.yml; the old branch keeps its own record and
    # changes only integration_branch.
    for target, ref in ((parent, start), (old_branch, old_ref)):
        git("reset", "--hard", ref, cwd=bw)
        os.makedirs(os.path.join(bw, tdir(scope)), exist_ok=True)
        if target == parent:
            write_board_cfg(bw, scope, cfg)
        else:
            old_cfg = read_board_cfg(bw, scope)
            old_cfg["integration_branch"] = new_branch
            write_board_cfg(bw, scope, old_cfg)
        if not board_commit(root, target, bw, scope,
                            f"dev: point board at iteration {new_idx}",
                            queue=False):
            print(f"warning: '{target}' does not point at '{new_branch}'; "
                  f"a checkout on it needs a one-time: TASKS init "
                  f"--integration {new_branch}", file=sys.stderr)
    # Leave the worktree on the new board, so the next board command has
    # nothing to push.
    git("reset", "--hard", new_tip, cwd=bw)
    print(f"iteration {new_idx} started on new branch "
          f"'{new_branch}' (parent: {parent})")
    report_reseeded(carried, reseeded, old_idx)
    retarget_carried_prs(root, carried, old_branch, new_branch)
    print(f"note: switch your checkout when ready: git checkout {new_branch}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scope", default=None,
                   help="target the board at this subdir (relative to repo root)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create or join a board")
    s.add_argument("--name",
                   help="your handle; omit to join an existing board as the "
                        "handle your GitHub login (gh) is registered under; "
                        "required to create a board")
    s.add_argument("--scope", default=argparse.SUPPRESS,
                   help="subdir (relative to repo root) whose board "
                   "to create/join; default: nearest board at/above cwd, else root")
    s.add_argument("--integration", help="integration branch (default: existing board's, else current)")
    s.add_argument("--parent", help="parent branch this integration branch lands in")
    s.add_argument("--iteration",
                   help="iteration number (default: 1)")
    s.add_argument("--iteration-name",
                   help="optional display name")
    s.add_argument("--iteration-started",
                   help="start date YYYY-MM-DD (default: today)")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("whoami", help="print your handle: the roster handle "
                       "your GitHub login holds")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--role", action="store_true",
                   help="print this identity's board role instead: "
                        "'integrator' or 'contributor'")
    g.add_argument("--github", action="store_true",
                   help="same as plain whoami (kept for compatibility)")
    s.set_defaults(fn=cmd_whoami)

    s = sub.add_parser("config", help="show or set board settings: "
                       "parent_branch, iteration, iteration_name, "
                       "iteration_started (integrator is read-only here: "
                       "use integrator add/rm)")
    s.add_argument("key", nargs="?")
    s.add_argument("value", nargs="?")
    s.set_defaults(fn=cmd_config)

    s = sub.add_parser("integrator", help="manage the board's integrator roster")
    isub = s.add_subparsers(dest="action", required=True)
    m = isub.add_parser("list", help="who may land on this board")
    m = isub.add_parser("add", help="grant the integrator role")
    m.add_argument("name")
    m = isub.add_parser("rm", help="revoke the integrator role; refused "
                                   "for the last one")
    m.add_argument("name")
    s.set_defaults(fn=cmd_integrator)

    s = sub.add_parser("contributor",
                       help="read, rename or prune the board's contributor "
                            "roster")
    csub = s.add_subparsers(dest="action", required=True)
    m = csub.add_parser("list", help="handles with their GitHub logins, "
                                     "integrators and (you) marked")
    m = csub.add_parser("rm", help="remove a handle (yourself, or any as "
                                   "integrator)")
    m.add_argument("name")
    m = csub.add_parser("rename", help="rename a handle (yourself, or any as "
                                       "integrator); the old one stays "
                                       "reserved")
    m.add_argument("name")
    m.add_argument("new_name")
    s.set_defaults(fn=cmd_contributor)

    s = sub.add_parser("area", help="manage the board's area list")
    msub = s.add_subparsers(dest="action", required=True)
    m = msub.add_parser("list", help="areas with descriptions and open counts")
    m = msub.add_parser("set", help="add or update a area")
    m.add_argument("area_name")
    m.add_argument("--desc", help="one-line scope description")
    m = msub.add_parser("rm", help="remove a area")
    m.add_argument("area_name")
    m.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_area)

    s = sub.add_parser("flow", help="the flow store (.flows/): procedures "
                                    "ops tasks run; referred to by name")
    fsub = s.add_subparsers(dest="action", required=True)
    m = fsub.add_parser("list", help="active flows: name — description")
    m.add_argument("--all", action="store_true", help="include retired")
    m.add_argument("--json", action="store_true")
    m = fsub.add_parser("show", help="print one flow file, catalog "
                                     "references resolved")
    m.add_argument("name", help="flow name (closest match is accepted)")
    m.add_argument("--raw", action="store_true", help=RAW_HELP)
    m = fsub.add_parser("runs", help="every recorded run of one flow, "
                                     "newest first")
    m.add_argument("name", help="flow name (closest match is accepted)")
    m.add_argument("--json", action="store_true")
    m = fsub.add_parser("create", help="add a flow")
    m.add_argument("name", help="slug: lowercase letters, digits, hyphens")
    m.add_argument("--desc", help="one line: what it does, when to use it")
    m.add_argument("--inputs", help="comma-separated: what a run must be "
                                    "told, e.g. \"client, amount (USD)\"")
    m.add_argument("--uses", help="comma-separated flows this one follows")
    m.add_argument("--body", help="the procedure")
    m.add_argument("--file", help="read the procedure from a file ('-' = stdin)")
    m = fsub.add_parser("update", help="change a flow's fields or body")
    m.add_argument("name")
    m.add_argument("--desc")
    m.add_argument("--inputs")
    m.add_argument("--uses")
    m.add_argument("--status", help="active | retired")
    m.add_argument("--body", help="replace the procedure")
    m.add_argument("--file", help="replace the procedure from a file ('-' = stdin)")
    m.add_argument("--append", action="append",
                   help="append a paragraph to the procedure (repeatable; "
                        "each one is its own paragraph, in order)")
    m = fsub.add_parser("rename", help="rename a flow; the old name is free "
                                       "at once and kept as a matching hint; "
                                       "other flows' uses follow")
    m.add_argument("name")
    m.add_argument("new_name")
    m = fsub.add_parser("reid", help="give a flow a fresh id when two boards "
                                     "minted the same one")
    m.add_argument("name")
    m = fsub.add_parser("retire", help="mark a flow retired (kept for the "
                                       "record; update --status active "
                                       "revives it)")
    m.add_argument("name")
    s.set_defaults(fn=cmd_flow)

    for kind, r in REGISTRIES.items():
        label = r["label"]
        s = sub.add_parser(kind, help=f"the {label} catalog category "
                                      f"(.catalog/{r['dir']}/): named "
                                      f"{label}s flows can point at")
        rsub = s.add_subparsers(dest="action", required=True)
        m = rsub.add_parser("list", help=f"every {label}")
        m.add_argument("--json", action="store_true")
        for act in ("show", "rm"):
            m = rsub.add_parser(act, help=f"{act} one {label}")
            m.add_argument("name", help="its name or a former one")
            if act == "show":
                m.add_argument("--raw", action="store_true", help=RAW_HELP)
        m = rsub.add_parser("rename", help=f"rename one {label}; the old "
                                           "name stays reserved")
        m.add_argument("name", help="its name or a former one")
        m.add_argument("new_name")
        for act in ("add", "update"):
            m = rsub.add_parser(act, help=f"{act} one {label}")
            m.add_argument("name", help="slug: lowercase letters, digits, "
                                        "hyphens; not project, runner, any, "
                                        "inline"
                                        + ("" if act == "add" else
                                           " (a former name also matches)"))
            m.add_argument("--accessors", help="comma-separated contributor "
                                               "handles who can reach it now"
                                               + ("" if act == "add" else
                                                  " (replaces the list)"))
            if kind == "agent":
                m.add_argument("--desc", help="one line: who it is")
            elif kind == "env":
                m.add_argument("--machine", help="the machine it lives on "
                                                 "(empty string clears)")
                m.add_argument("--expects", help="prose: what a step can "
                                                 "count on there")
            else:
                m.add_argument("--mode", help="attended (one task, the user "
                                              "is reached) | unattended")
                m.add_argument("--environment",
                               help="the registered environment it runs in")
                m.add_argument("--schedule",
                               help="what the trigger is set to: \"<cron> "
                                    "<timezone>\", or one fire time as a "
                                    "timestamp with offset")
                m.add_argument("--trigger", help="one line: what the trigger "
                                                 "is and where, with its "
                                                 "identifier")
                m.add_argument("--manage", help="prose: how to change or "
                                                "remove the trigger at its "
                                                "source")
                if act == "update":
                    m.add_argument("--status", help="active | paused (the "
                                                    "board-side off switch)")
        if kind == "routine":
            m = rsub.add_parser("wake", help="a routine's entry gate: exit 2 "
                                             "with the reason when it is "
                                             "paused or gone, else its due "
                                             "tasks in due order")
            m.add_argument("name", help="its name or a former one")
        s.set_defaults(fn=cmd_registry, registry=kind)

    s = sub.add_parser("catalog", help="the catalog (.catalog/): user "
                                       "categories and their keys, and "
                                       "{key.field} references")
    csub = s.add_subparsers(dest="action", required=True)
    m = csub.add_parser("list", help="every category, or one category's "
                                     "keys")
    m.add_argument("category", nargs="?")
    m.add_argument("--json", action="store_true")
    m = csub.add_parser("show", help="print one key's file, references "
                                     "resolved")
    m.add_argument("name", help="its name or a former one")
    m.add_argument("--raw", action="store_true", help=RAW_HELP)
    m = csub.add_parser("get", help="print the value a reference resolves "
                                    "to: <key>.<field>[.<field>…]")
    m.add_argument("ref")
    m = csub.add_parser("add", help="add a key to a user category")
    m.add_argument("category")
    m.add_argument("name", help="slug, unique across the whole catalog")
    m.add_argument("--set", action="append", help=SET_HELP)
    m = csub.add_parser("update", help="set a key's values")
    m.add_argument("name", help="its name or a former one")
    m.add_argument("--set", action="append", help=SET_HELP)
    m = csub.add_parser("rename", help="rename a key; the old name stays "
                                       "reserved and keeps resolving")
    m.add_argument("name", help="its name or a former one")
    m.add_argument("new_name")
    m = csub.add_parser("rm", help="remove a key (refused while live tasks, "
                                   "flows or keys reference it)")
    m.add_argument("name", help="its name or a former one")
    m = csub.add_parser("category", help="declare a user category and its "
                                         "fields")
    ccsub = m.add_subparsers(dest="category_action", required=True)
    for act in ("add", "update", "show", "rm", "rename"):
        m = ccsub.add_parser(act, help=f"{act} one category")
        m.add_argument("name")
        if act == "rename":
            m.add_argument("new_name")
        if act in ("add", "update"):
            m.add_argument("--field", action="append",
                           help="\"<field>: <one line: what it holds>\", "
                                "optionally ending \"(one of: a, b)\" "
                                "(repeatable; an existing field's "
                                "description is replaced)")
        if act == "update":
            m.add_argument("--drop-field", dest="drop_field",
                           action="append",
                           help="remove a field no key holds a value for "
                                "(repeatable)")
    s.set_defaults(fn=cmd_catalog)

    s = sub.add_parser("add", help="add a task")
    s.add_argument("--title", required=True)
    s.add_argument("--area")
    s.add_argument("--deps", help="comma-separated task ids")
    s.add_argument("--desc")
    s.add_argument("--assignee")
    s.add_argument("--kind", default="",
                   help="optional kind (umbrella, recurring); empty = normal")
    s.add_argument("--type", default="",
                   help="ops = run through /ops flows (no area, no branch, "
                        "no PR); dev (the default) = code work")
    s.add_argument("--cadence",
                   help="recurring tasks only: <N><unit>, unit d/w/m (2w, 1m)")
    s.add_argument("--schedule",
                   help="recurring tasks only, instead of --cadence: a "
                        "5-field cron expression and an IANA timezone "
                        "(\"0 12 * * 3 America/New_York\")")
    s.add_argument("--next-due", dest="next_due",
                   help="recurring tasks only: YYYY-MM-DD of the first run "
                        "(default: due now on a cadence, the first "
                        "scheduled time from the start of today on a "
                        "schedule)")
    s.add_argument("--rehearsal", action="store_true",
                   help="ops tasks only: a dry run of its flow; no real run "
                        "of that flow may be doing while it is")
    s.add_argument("--distill", action="store_true",
                   help="ops tasks only: a distill sitting; takes "
                        "`distilled`, and ran records it and the tasks that "
                        "depend on it as distilled")
    s.add_argument("--routine",
                   help="recurring tasks only: the routine whose trigger "
                        "starts it")
    s.add_argument("--status", default="backlog",
                   help=" | ".join(ADD_STATUSES))
    s.add_argument("--reason", help="why it is set aside; required with "
                                    "--status shelved")
    s.add_argument("--umbrella", help="comma-separated umbrella ids to file "
                                      "the new task under (adds it to their "
                                      "deps in the same board commit)")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("update", help="update task fields")
    s.add_argument("id", type=int)
    for f in ("title", "area", "status", "kind", "type", "assignee", "branch",
              "pr", "needs", "deps", "desc", "cadence", "schedule"):
        s.add_argument(f"--{f}")
    s.add_argument("--last-run", dest="last_run",
                   help="recurring tasks only: YYYY-MM-DD or a timestamp with "
                        "offset (2026-11-11T12:04-05:00) of the last run, "
                        "on a schedule the scheduled time it covered "
                        "(empty string clears; due is derived from it)")
    s.add_argument("--next-due", dest="next_due",
                   help="recurring tasks only: YYYY-MM-DD the next run is due, "
                        "overriding the derived due until a run is "
                        "recorded (empty string clears)")
    s.add_argument("--flow", help="flow name(s) this task runs, comma-"
                                  "separated; stored as `<id> <name>` refs "
                                  "(empty string clears)")
    s.add_argument("--routine", help="recurring tasks only: the routine "
                                     "whose trigger starts it (empty string "
                                     "clears)")
    s.add_argument("--unattended", metavar="MODEL_ID",
                   help="unattended ops runs and audits: mark the doing "
                        "task as worked by this run (refused while any "
                        "run's marker is set; empty string clears)")
    s.add_argument("--append", action="append",
                   help="append a paragraph to the body (leaves existing text "
                        "untouched; repeatable, each in order)")
    s.add_argument("--reason", help="why this task is not being pursued "
                                    "(or not needed for now); required with "
                                    "--status not-planned or shelved")
    s.set_defaults(fn=cmd_update)

    s = sub.add_parser("related", help="existing tasks similar to some text")
    s.add_argument("text", help="proposed title (+ description)")
    s.add_argument("--deps", help="the new task's planned deps: also list "
                                  "the umbrellas they sit under")
    s.set_defaults(fn=cmd_related)

    s = sub.add_parser("delete", help="delete a task")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_delete)

    s = sub.add_parser("show", help="print one task file, catalog "
                                    "references resolved")
    s.add_argument("id", type=int)
    s.add_argument("--raw", action="store_true", help=RAW_HELP)
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("list", help="one-line-per-task, filterable")
    s.add_argument("--assignee")
    s.add_argument("--status")
    s.add_argument("--needs")
    s.add_argument("--type", help="ops, or dev for dev tasks only (untyped "
                                  "tasks count as dev)")
    s.add_argument("--flow", help="tasks whose flow field records this flow "
                                  "(closest name, as flow show)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("recur", help="recurring tasks: list due, record a run")
    rsub = s.add_subparsers(dest="recur_cmd", required=True)
    m = rsub.add_parser("list", help="recurring tasks with derived due dates")
    m.add_argument("--due", action="store_true",
                   help="only tasks that are due now or overdue")
    m = rsub.add_parser("ran", help="record a run: stamp last_run, re-arm")
    m.add_argument("id", type=int)
    m.add_argument("--date", help="run time (default now): YYYY-MM-DD or a "
                                  "timestamp with offset")
    s.set_defaults(fn=cmd_recur)

    s = sub.add_parser("ran", help="close an ops task with its run record "
                                   "(refused on a dev task)")
    s.add_argument("id", type=int)
    s.add_argument("--flow", help="flow name(s) followed, comma-separated; "
                                  "omit to keep the task's flow field, or "
                                  "for a run with no stored flow")
    s.add_argument("--record", help="inputs the run was given; deviations "
                                    "from the flow — recorded as Ran (<date>): …")
    s.add_argument("--date", help="when the run happened (default now): "
                                  "YYYY-MM-DD or a timestamp with offset")
    s.add_argument("--rehearsal", action="store_true",
                   help="the task was a dry run of a flow: record "
                        "Rehearsed (<date>): … so it never counts as a run "
                        "(required on a rehearsal task)")
    s.set_defaults(fn=cmd_ran)

    s = sub.add_parser("distilled",
                       help="on a distill sitting: record the tasks whose "
                            "every candidate the user has dealt with; the "
                            "sitting stays open")
    s.add_argument("id", type=int, help="the sitting (distill: true)")
    s.add_argument("ids", help="task ids, ranges allowed (\"T3-T7, T9\"); "
                               "non-recurring tasks on this board — "
                               "recorded as Distilled (<date>): …")
    s.set_defaults(fn=cmd_distilled)

    s = sub.add_parser("pause",
                       help="record where a run stopped; it stays doing (a "
                            "dev task's branch is committed and pushed)")
    s.add_argument("id", type=int)
    s.add_argument("--at", help="where the run stopped: the flow's step "
                                "(numbered, or its text), or what was last "
                                "done when no flow was followed")
    s.add_argument("--record", help="what the run has produced so far and "
                                    "where it lives — recorded in the body "
                                    "as Paused (<date>): …")
    s.add_argument("--flow", help="flow name(s) being followed, comma-"
                                  "separated; omit to keep the task's flow "
                                  "field")
    s.add_argument("--date", help="YYYY-MM-DD of the pause (default today)")
    s.set_defaults(fn=cmd_pause)

    s = sub.add_parser("wait",
                       help="mark doing work as waiting on a third party "
                            "or a handed-off agent; it stays doing")
    s.add_argument("id", type=int)
    s.add_argument("--on", help="who the run waits on")
    s.add_argument("--by", help="YYYY-MM-DD their reply is expected")
    s.add_argument("--at", help="the [external] step (or the handed-off "
                                "sequence's last step) the run waits at")
    s.add_argument("--record", help="what was sent to them and where it "
                                    "lives — recorded as Waiting (<date>): …")
    s.add_argument("--flow", help="flow name(s) being followed, comma-"
                                  "separated; omit to keep the task's flow "
                                  "field")
    s.add_argument("--date", help="YYYY-MM-DD of the record (default today)")
    s.add_argument("--clear", action="store_true",
                   help="the reply is in: drop the waiting marker, stay doing")
    s.set_defaults(fn=cmd_wait)

    s = sub.add_parser("note",
                       help="note on a task what its flow did not "
                            "predict")
    s.add_argument("id", type=int)
    s.add_argument("text", help="a step the user did, a step inserted, a "
                                "correction — recorded as Note (<date>): …")
    s.add_argument("--at", help="the step it happened at (numbered, or its "
                                "text); omit outside a run")
    s.add_argument("--date", help="YYYY-MM-DD it happened (default today)")
    s.set_defaults(fn=cmd_note)

    s = sub.add_parser("inputs",
                       help="record the values a run was given, as "
                            "Inputs: … (values, never live {key.field})")
    s.add_argument("id", type=int)
    s.add_argument("text", help="\"<input>=<value>; …\" under the flow's "
                                "input names")
    s.set_defaults(fn=cmd_inputs)

    s = sub.add_parser("verify",
                       help="close an umbrella: record how its children met "
                            "its goal")
    s.add_argument("id", type=int)
    s.add_argument("text", help="how the children met the goal; recorded in "
                                "the body as Verified (<date>): …")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("collisions",
                       help="area occupancy vs in-flight work "
                            "(exit 2 blocked, 3 PR open)")
    s.add_argument("ids", nargs="+",
                   help="task id(s), e.g. 12 or 12,15,18")
    s.set_defaults(fn=cmd_collisions)

    s = sub.add_parser("board", help="print board view; regenerate TASKS.md")
    s.add_argument("--expand", action="store_true",
                   help="also list done/shelved/not-planned (default "
                        "folds them to counts)")
    s.add_argument("--by-area", action="store_true",
                   help="index by area instead of status (multi-area tasks "
                        "listed under each area)")
    s.add_argument("--watch", action="store_true",
                   help="interactive: r refresh, a toggle by-area, "
                        "e toggle expand, l latest-first list, c check mode, "
                        "s search, "
                        "f flows pane, g registries pane, "
                        "q (or Esc) back one level, q quits "
                        "from the plain board, "
                        "arrows scroll, space/b page, type id+Enter to "
                        "show a task (used by ./board)")
    s.add_argument("--refresh-viewer", action="store_true",
                   help="rewrite ./board from this skill's template, even if "
                        "edited, then exit (used by ./board update)")
    s.set_defaults(fn=cmd_board)

    s = sub.add_parser("iteration", help="show current iteration")
    s.set_defaults(fn=cmd_iteration)

    s = sub.add_parser("iteration-close", help="log + remove all tasks on the board")
    s.add_argument("--carry", action="store_true",
                   help="carry unfinished tasks into the next iteration "
                        "with status, branch and PR intact (iteration-new "
                        "reseeds them)")
    s.add_argument("--skip-distill", dest="skip_distill", metavar="WHY",
                   help="close although some done or not-planned tasks are "
                        "not distilled, this close only; the reason is "
                        "logged in log.md as [distill skipped: <why>]")
    s.set_defaults(fn=cmd_iteration_close)

    s = sub.add_parser("iteration-new",
                       help="start a fresh board on a new integration branch, "
                            "or in place when there is no parent")
    s.add_argument("branch", nargs="?",
                   help="new integration branch; omit to roll in place on a "
                        "no-parent board")
    s.add_argument("--parent")
    s.add_argument("--name",
                   help="optional display name (not the identity)")
    s.add_argument("--iteration",
                   help="iteration number (default: one more than max of "
                        "live and archived indexes)")
    s.add_argument("--iteration-started",
                   help="start date YYYY-MM-DD (default: today)")
    s.set_defaults(fn=cmd_iteration_new)

    s = sub.add_parser("iteration-land",
                       help="open/merge iteration PR into parent (merge commit, not squash)")
    s.add_argument("--title", help="PR title (default: iteration <n>)")
    s.add_argument("--body", help="PR body")
    s.add_argument("--create-only", action="store_true",
                   help="open the PR but do not merge")
    s.set_defaults(fn=cmd_iteration_land)

    s = sub.add_parser("claim",
                       help="implement setup: branch + linked worktree, status=doing")
    s.add_argument("id", type=int)
    s.add_argument("--assignee",
                   help="assignee (default: your handle)")
    s.add_argument("--branch",
                   help="task branch (default: recorded or dev/<scope?>-<id>-<slug>)")
    s.add_argument("--stack-on", type=int, metavar="ID",
                   help="start on task ID's pushed review tip instead of "
                        "origin/<integration> (collisions exit 3, when this "
                        "task builds on that unmerged code); ship then bases "
                        "the PR on that branch. Refused when that task has "
                        "no branch or it is already in integration")
    s.add_argument("--unattended", metavar="MODEL_ID",
                   help="unattended runs only: mark the task as worked by "
                        "this run until it leaves doing (others' claims "
                        "refuse)")
    s.set_defaults(fn=cmd_claim)

    s = sub.add_parser("diff",
                       help="self-review: location + diff from the task worktree")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_diff)

    s = sub.add_parser("ship",
                       help="implement ship: commit [n/T<id>] (scoped: "
                            "[<scope> n/T<id>]), push, open draft PR, "
                            "status=draft")
    s.add_argument("id", type=int)
    s.add_argument("--message", "-m",
                   help="commit message if worktree dirty "
                        "(default: [n/T<id>] <title>; scoped board: "
                        "[<scope> n/T<id>] <title>)")
    s.add_argument("--title",
                   help="PR title, rewritten on every ship "
                        "(default: [n/T<id>] <task title>; scoped "
                        "board: [<scope> n/T<id>] <task title>)")
    s.add_argument("--body",
                   help="PR body opening, rewritten on every ship "
                        "(default: task body)")
    s.add_argument("--version-intent",
                   help="set the PR body's 'Version intent: …' line, on create "
                        "or re-ship (replaces a stale one; 'none' removes it). "
                        "Agent only; omit when product does not version or "
                        "the intent is unchanged")
    s.add_argument("--base",
                   help="PR base on create only (default: derived — the "
                        "live task branch this one was started on, else "
                        "integration; pass a branch name to override)")
    s.add_argument("--batch",
                   help="implement-batch stamp: comma-separated task ids "
                        "(writes Dev-batch: … on PR body + task body)")
    s.add_argument("--shipped",
                   help="REQUIRED: what actually shipped, in one or two "
                        "sentences (the result, not the plan). Appended to "
                        "the task body as 'Shipped (<date>): …' and mirrored "
                        "onto the PR body on create and every re-ship")
    s.set_defaults(fn=cmd_ship)

    s = sub.add_parser("ready",
                       help="draft → review: mark the PR ready (user's call)")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_ready)

    s = sub.add_parser("unready",
                       help="review → draft: take a PR back "
                            "(assignee or integrator)")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_unready)

    s = sub.add_parser("pr",
                       help="read or act on a task's PR (gh pr, or REST "
                            "where GraphQL is blocked); flows use this")
    s.add_argument("id", type=int)
    s.add_argument("action",
                   choices=("view", "diff", "comment", "review", "close"))
    s.add_argument("--body", help="comment / review text")
    s.add_argument("--head", metavar="BRANCH",
                   help="act on the open PR from this branch instead of "
                        "the task's recorded one (a leftover branch)")
    s.add_argument("--json", action="store_true",
                   help="view: JSON (state, mergedAt, reviewDecision, "
                        "isDraft, author, reviews, comments, …)")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--approve", action="store_true", help="review: approve")
    g.add_argument("--request-changes", action="store_true",
                   help="review: request changes (needs --body)")
    g.add_argument("--comment", action="store_true",
                   help="review: comment only (needs --body)")
    s.set_defaults(fn=cmd_pr)

    s = sub.add_parser("batch-gate",
                       help="exit 2 if --ids omits an open stack parent "
                            "(a partial Dev-batch only warns)")
    s.add_argument("--ids", required=True,
                   help="selected task ids, e.g. 19,20 or 19,20,22,23")
    s.set_defaults(fn=cmd_batch_gate)

    s = sub.add_parser("restack",
                       help="fail-closed rebase of a task stack/batch (plan then apply)")
    s.add_argument("--ids", required=True,
                   help="task ids in the set, e.g. 19,20,22,23")
    s.add_argument("--after", type=int,
                   help="only restack stack descendants of this task id")
    s.add_argument("--onto",
                   help="rebase every target onto this ref (e.g. main or "
                        "origin/main) — does not cascade (children do not "
                        "stay based on restacked parents; default without "
                        "--onto preserves in-set stack parents); implies "
                        "PR base retarget unless base already matches")
    s.add_argument("--retarget", action="store_true",
                   help="retarget the PR base to the new stack parent / --onto")
    s.add_argument("--dry-run", action="store_true",
                   help="print plan only (also land order for the set); "
                        "do not rebase or push")
    s.set_defaults(fn=cmd_restack)

    s = sub.add_parser("preflight",
                       help="local integration ahead of origin: check / park / discard")
    s.add_argument("--park", action="store_true",
                   help="park ahead commits as a PR, reset local integration")
    s.add_argument("--discard", action="store_true",
                   help="reset local integration to origin (drops ahead commits)")
    s.set_defaults(fn=cmd_preflight)

    s = sub.add_parser("land",
                       help="integrator-only: merge task PR (merge commit), "
                            "cleanup, mark done; refuses a draft")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_land)

    s = sub.add_parser("cleanup",
                       help="idempotent: remove task worktree/local branch/"
                            "remote-tracking (branches only once the PR is "
                            "merged)")
    s.add_argument("id", type=int)
    s.set_defaults(fn=cmd_cleanup)

    args = p.parse_args()
    global SCOPE_OVERRIDE
    SCOPE_OVERRIDE = getattr(args, "scope", None)
    args.fn(args)


if __name__ == "__main__":
    # Task text and board marks are UTF-8; a Windows pipe defaults to the
    # ANSI code page, which cannot print them.
    for _stream in (sys.stdout, sys.stderr):
        _stream.reconfigure(encoding="utf-8")
    main()
