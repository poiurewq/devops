#!/usr/bin/env python3
"""devops installer — one clone per user, symlinked into agent skill roots.

    curl -fsSL https://raw.githubusercontent.com/poiurewq/devops/main/install.py | python3 -

Clones the package to ~/.local/share/devops (XDG_DATA_HOME honoured), asks
which skills (dev, ops) to install and which agent skill roots to install
them into, then points a symlink at each skill directory inside that one
clone. Updating is a pull in the clone, so every agent sees it at once.

Re-running is the supported way to add a root, add a skill, or repair a
link: the clone is fast-forwarded and the plan only lists what changes.

Already-installed skill directories are replaced only with the user's
consent, and never when they hold unsaved work (a dirty or unpushed clone
is skipped, not overwritten). Prompts go to /dev/tty, so they still work
when the script itself is what stdin is feeding; with no terminal at all,
replacing needs an explicit --yes.

Run from inside a package tree (a manual clone, or a copied tree passed via
--source), that tree is used as-is and nothing is cloned — otherwise a
second copy would appear behind the user's back.

CANONICAL_REPO is duplicated in lib/skill.py, which owns the update path.
This file must stay standalone: it runs before any clone exists, so it
cannot import from lib/.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

CANONICAL_REPO = "https://github.com/poiurewq/devops"
CANONICAL_SLUG = "poiurewq/devops"
# The pre-devops skill: a clone of this in a skills root is what migration
# replaces with a symlink.
LEGACY_SLUG = "poiurewq/dev"
# Agent product directories are ~/.claude, ~/.grok and their variants
# (~/.claude-work, …); each keeps its skills in <home>/skills.
AGENT_HOME_GLOBS = (".claude*", ".grok*")
SKILLS_SUBDIR = "skills"


def die(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    sys.stdout.flush()
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, check=False,
    )


def git_out(args: list[str], cwd: Path) -> str:
    r = run(["git", "-C", str(cwd), *args])
    return (r.stdout or "").strip() if r.returncode == 0 else ""


# --- package ---------------------------------------------------------------

def is_package(path: Path) -> bool:
    """True when path is a devops package tree (not merely a git clone)."""
    return (path / "lib" / "tasks.py").is_file() and (path / "VERSION").is_file()


def package_version(pkg: Path) -> str:
    try:
        return (pkg / "VERSION").read_text().strip() or "unknown"
    except OSError:
        return "unknown"


def here_package() -> Path | None:
    """The package this file lives in, if any.

    Piped from curl, __file__ is missing or a placeholder like "<stdin>"
    that resolves against the working directory — so require a real file on
    disk before trusting its parent. A copy outside a package is not one
    either. Both mean "clone it".
    """
    try:
        here = Path(__file__).resolve()
    except NameError:
        return None
    if not here.is_file():
        return None
    return here.parent if is_package(here.parent) else None


def default_home() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "devops"


def normalize_origin(url: str) -> str:
    """owner/repo for a GitHub remote, else "" (scp, https, ssh forms)."""
    u = (url or "").strip().rstrip("/")
    if u.endswith(".git"):
        u = u[: -len(".git")]
    for prefix in ("https://", "http://", "ssh://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
            break
    if "@" in u:
        u = u.split("@", 1)[1]
    for sep in (":", "/"):
        head, _, tail = u.partition(sep)
        if head.lower() in ("github.com", "www.github.com") and tail:
            return tail
    return ""


def git_root(path: Path) -> Path | None:
    """The worktree root when path itself is one, else None."""
    top = git_out(["rev-parse", "--show-toplevel"], path)
    if not top:
        return None
    root = Path(top)
    try:
        return root if root.resolve() == path.resolve() else None
    except OSError:
        return None


def clone_slug(path: Path) -> str:
    if git_root(path) is None:
        return ""
    return normalize_origin(git_out(["remote", "get-url", "origin"], path))


def clone_has_unsaved_work(path: Path) -> str:
    """Reason this clone must not be deleted, or "" when it is reproducible."""
    if git_out(["status", "--porcelain"], path):
        return "uncommitted changes"
    if git_out(["log", "--branches", "--not", "--remotes", "--oneline"], path):
        return "commits not pushed to any remote"
    return ""


def ensure_clone(home: Path, dry_run: bool) -> Path:
    """Clone the canonical repo to home, or fast-forward it if already there."""
    if home.exists():
        slug = clone_slug(home)
        if slug.lower() != CANONICAL_SLUG.lower():
            what = f"a clone of {slug}" if slug else "not a git clone"
            die(f"{home} exists and is {what}; move it aside or pass "
                f"--home <dir>")
        if not is_package(home):
            die(f"{home} is a clone of {CANONICAL_SLUG} but has no lib/ or "
                "VERSION; the clone looks damaged — remove it and re-run")
        if dry_run:
            print(f"would fast-forward the clone at {home}")
            return home
        r = run(["git", "-C", str(home), "pull", "--ff-only", "origin", "main"])
        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "").strip()
            print(f"warning: could not update the clone at {home}: {detail}",
                  file=sys.stderr)
        return home
    if dry_run:
        print(f"would clone {CANONICAL_REPO} to {home}")
        return home
    if shutil.which("git") is None:
        die("git not found; install git and re-run")
    home.parent.mkdir(parents=True, exist_ok=True)
    print(f"cloning {CANONICAL_REPO} → {home}")
    r = run(["git", "clone", f"{CANONICAL_REPO}.git", str(home)])
    if r.returncode != 0:
        die(f"git clone failed: {(r.stderr or r.stdout).strip()}")
    if not is_package(home):
        die(f"cloned {CANONICAL_SLUG} but {home} has no lib/ or VERSION")
    return home


def discover_skills(pkg: Path) -> list[str]:
    """Installable skills: package subdirs holding a SKILL.md.

    Derived rather than hardcoded, so a skill becomes installable the moment
    it has a SKILL.md and a half-written one is never linked.
    """
    return sorted(
        d.name for d in pkg.iterdir()
        if d.is_dir() and not d.name.startswith(".")
        and (d / "SKILL.md").is_file()
    )


# --- skill roots -----------------------------------------------------------

def discover_roots() -> tuple[list[Path], list[Path]]:
    """(in use, unused) skills dirs across every agent product directory.

    An agent home with no skills/ dir has never held a skill, so installing
    there is a guess — several exist on a typical machine (~/.claude alongside
    ~/.claude-work, an archived profile, a bot). They are offered, never
    chosen by default.
    """
    in_use: list[Path] = []
    unused: list[Path] = []
    home = Path.home()
    for pattern in AGENT_HOME_GLOBS:
        for agent_home in sorted(home.glob(pattern)):
            if not agent_home.is_dir():
                continue
            root = agent_home / SKILLS_SUBDIR
            if root in in_use or root in unused:
                continue
            (in_use if root.is_dir() else unused).append(root)
    return in_use, unused


def default_roots(in_use: list[Path], unused: list[Path]) -> list[Path]:
    """What Enter (and --yes) install into: the roots already in use.

    A machine with no skills dir anywhere is a first install and has to go
    somewhere, so there the whole detected set is the default.
    """
    return list(in_use) if in_use else list(unused)


def describe_root(root: Path, skills: list[str], pkg: Path) -> str:
    """One-line summary of what is already installed in this root."""
    if not root.exists():
        return "will be created"
    bits = []
    for name in skills:
        kind, detail, _ = classify(root / name, pkg)
        if kind != "free":
            bits.append(f"{name}: {detail}")
    return ", ".join(bits) if bits else "nothing installed"


# --- targets ---------------------------------------------------------------

def classify(target: Path, pkg: Path) -> tuple[str, str, str]:
    """(kind, human description, blocking reason) for one <root>/<skill>.

    kind is one of: free, linked, link-other, clone-legacy, clone-canonical,
    clone-other, copy, file.
    """
    if target.is_symlink():
        try:
            dest = target.resolve()
        except OSError:
            return "link-other", "broken symlink", ""
        if dest == (pkg / target.name).resolve():
            return "linked", "already linked here", ""
        return "link-other", f"symlink to {dest}", ""
    if not target.exists():
        return "free", "", ""
    if target.is_dir():
        slug = clone_slug(target)
        if slug:
            unsaved = clone_has_unsaved_work(target)
            if slug.lower() == LEGACY_SLUG.lower():
                return "clone-legacy", f"clone of {slug}", unsaved
            if slug.lower() == CANONICAL_SLUG.lower():
                return "clone-canonical", f"clone of {slug}", unsaved
            return "clone-other", f"clone of {slug}", unsaved
        return "copy", "plain copy (no git)", ""
    return "file", "a file, not a directory", "not a directory"


def path_key(path: Path) -> str:
    """Comparison key for a path. Detected roots keep the literal ~/… spelling
    (it is what gets printed), while a typed one is resolved — on macOS that
    alone turns /var into /private/var, so the two forms must never be
    compared directly."""
    try:
        return os.path.realpath(path)
    except OSError:
        return str(path)


def reject_root_inside_package(root: Path, pkg: Path) -> None:
    """A root at or under the package would link a skill dir to itself.

    The installer replaces whatever occupies <root>/<skill>, so a root of
    the package itself makes <pkg>/dev both source and target: the real
    directory is deleted and a symlink to nothing takes its place.
    """
    root_key, pkg_key = path_key(root), path_key(pkg)
    if root_key == pkg_key or root_key.startswith(pkg_key + os.sep):
        die(f"{tilde(root)} is inside the package at {tilde(pkg)}; a skills "
            "root must be somewhere else, or the skill would be linked to "
            "itself")


def plan_for(root: Path, name: str, pkg: Path) -> dict | None:
    """One planned action, or None when nothing needs doing."""
    target = root / name
    kind, detail, blocked = classify(target, pkg)
    if kind == "linked":
        return None
    if kind == "file":
        return {"target": target, "name": name, "verb": "skip",
                "detail": detail, "reason": "not a directory"}
    if blocked:
        return {"target": target, "name": name, "verb": "skip",
                "detail": detail, "reason": blocked}
    if kind == "free":
        return {"target": target, "name": name, "verb": "link", "detail": ""}
    return {"target": target, "name": name, "verb": "replace", "detail": detail}


# --- prompts ---------------------------------------------------------------

# The documented install is `curl … | python3 -`, where stdin is the script
# itself: input() would read the remaining program text, or hit EOF. So every
# prompt goes to the controlling terminal instead. _TTY is the cached handle;
# False means "not looked for yet", None means "there is none" (cron, CI, a
# pipeline with no terminal), which is the only case that runs unattended.
_TTY: object = False

# Typed at any prompt to stop the run. ctrl-C does the same thing through
# KeyboardInterrupt; both land on the one handler in main().
QUIT_WORDS = ("q", "quit", "abort", "cancel")
# Links actually created so far, so a cancellation can say whether the run
# got as far as changing anything rather than always claiming it did not.
_APPLIED = 0


class Cancelled(Exception):
    """The user asked to stop at a prompt."""


def tty_stream():
    """The terminal to prompt on, or None when the run is unattended."""
    global _TTY
    if _TTY is False:
        if sys.stdin.isatty():
            _TTY = sys.stdin
        else:
            try:
                _TTY = open("/dev/tty", encoding="utf-8")
            except OSError:
                _TTY = None
    return _TTY


def ask(prompt: str) -> str:
    """Read one answer, or raise Cancelled if the user wants out.

    Quitting is a first-class answer at every prompt: a quit word, or EOF
    (ctrl-D), which would otherwise read as "take the default" and install
    something nobody asked for.
    """
    stream = tty_stream()
    if stream is None:
        return ""
    if stream is sys.stdin:
        try:
            answer = input(prompt).strip()
        except EOFError:
            raise Cancelled from None
    else:
        print(prompt, end="", flush=True)
        line = stream.readline()
        if not line:
            raise Cancelled
        answer = line.strip()
    if answer.lower() in QUIT_WORDS:
        raise Cancelled
    return answer


def choose_roots(in_use: list[Path], unused: list[Path], skills: list[str],
                 pkg: Path) -> list[Path]:
    """Ask which skill roots to install into.

    One continuous numbering across both groups, so a number means the same
    thing wherever it is used. Answer forms: Enter for the default, numbers
    and paths to set an exact list, and `-N` / `-<path>` to drop from the
    default without having to retype the rest.
    """
    detected = in_use + unused
    default = default_roots(in_use, unused)
    print("\nskill roots:")
    n = 0
    for root in in_use:
        n += 1
        print(f"  {n}) {tilde(root):<28} {describe_root(root, skills, pkg)}")
    if not in_use:
        print("  (none in use yet)")
    if unused:
        print("\nnot used by any skill yet:")
        for root in unused:
            n += 1
            print(f"  {n}) {tilde(root):<28} would be created")
    if default == detected:
        summary = "all of the above"
    elif len(default) == 1:
        summary = f"just {tilde(default[0])}"
    else:
        summary = f"the {len(default)} in use"
    print(f"\nWhich roots? Enter = {summary}; numbers like 1,3 or paths for "
          "an exact list; -2 to drop one from the default; q to quit.")
    answer = ask("> ")
    if not answer:
        return list(default)

    def resolve(token: str) -> Path:
        if token.isdigit():
            idx = int(token)
            if not 1 <= idx <= len(detected):
                die(f"no root numbered {idx}")
            return detected[idx - 1]
        return Path(token).expanduser().resolve()

    added: list[Path] = []
    dropped: set[str] = set()
    seen: set[str] = set()
    for token in (t.strip() for t in answer.replace(" ", ",").split(",")):
        if not token:
            continue
        negated = token[0] in "-!"
        candidate = resolve(token[1:].strip() if negated else token)
        if negated:
            dropped.add(path_key(candidate))
        elif path_key(candidate) not in seen:
            seen.add(path_key(candidate))
            added.append(candidate)
    # Only removals means "the default, less these"; anything added is an
    # exact list (removals then still subtract, so 1,2,3,-2 reads naturally).
    chosen = added if added else list(default)
    return [r for r in chosen if path_key(r) not in dropped]


def choose_skills(available: list[str]) -> list[str]:
    print(f"\nWhich skills? Enter = all ({', '.join(available)}); "
          "q to quit.")
    answer = ask("> ")
    if not answer:
        return list(available)
    chosen = []
    for token in (t.strip() for t in answer.replace(" ", ",").split(",")):
        if not token:
            continue
        if token not in available:
            die(f"unknown skill {token!r}; available: {', '.join(available)}")
        if token not in chosen:
            chosen.append(token)
    return chosen


def confirm(prompt: str) -> bool:
    return ask(f"{prompt} [y/N/q] ").lower() in ("y", "yes")


def tilde(path: Path) -> str:
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


# --- apply -----------------------------------------------------------------

def apply(action: dict, pkg: Path, dry_run: bool) -> bool:
    """Perform one planned action. Returns True on success.

    Replacing a real directory moves it aside first and restores it if the
    symlink cannot be created, so a failure never leaves the skill missing.
    The rename is within one directory, so it is atomic and cheap; a crash
    at worst leaves a visible <name>.devops-old beside the link.
    """
    target: Path = action["target"]
    source = pkg / action["name"]
    if dry_run:
        return True
    backup: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if action["verb"] == "replace":
            if target.is_symlink() or target.is_file():
                target.unlink()
            else:
                backup = target.with_name(target.name + ".devops-old")
                if backup.is_symlink() or backup.is_file():
                    backup.unlink()
                elif backup.is_dir():
                    shutil.rmtree(backup)
                os.rename(target, backup)
        target.symlink_to(source, target_is_directory=True)
    except OSError as e:
        print(f"error: {tilde(target)}: {e}", file=sys.stderr)
        if backup is not None:
            try:
                if not target.exists() and not target.is_symlink():
                    os.rename(backup, target)
            except OSError as restore_err:
                # Never delete it on the way out: that directory is now the
                # only copy of whatever was installed here.
                print(f"error: {tilde(target)} could not be restored; the "
                      f"previous install is at {tilde(backup)} "
                      f"({restore_err})", file=sys.stderr)
        return False
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)
    global _APPLIED
    _APPLIED += 1
    return True


# --- main ------------------------------------------------------------------

def cancel_note() -> str:
    """What to say on the way out, without overclaiming."""
    if _APPLIED:
        return (f"cancelled — {_APPLIED} link(s) were already created; "
                "re-run to finish, nothing is half-written.")
    return "cancelled — nothing changed."


def main(argv: list[str] | None = None) -> int:
    """Entry point. Cancelling is handled once, here, rather than at each
    prompt: ctrl-C at any point (including during the clone) and a typed
    quit word leave by the same door."""
    try:
        return install(argv)
    except Cancelled:
        print(f"\n{cancel_note()}")
        return 1
    except KeyboardInterrupt:
        print(f"\n{cancel_note()}")
        return 130


def install(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="install.py",
        description="Install the devops skills (dev, ops) from one clone.",
    )
    p.add_argument("--home", metavar="DIR",
                   help="where the clone lives "
                        "(default: $XDG_DATA_HOME/devops or ~/.local/share/devops)")
    p.add_argument("--source", metavar="DIR",
                   help="link from this package tree instead of cloning")
    p.add_argument("--skills", metavar="LIST",
                   help="comma-separated skills, or 'all' (default: ask)")
    p.add_argument("--root", metavar="PATH", action="append", default=[],
                   help="skills root to install into (repeatable; default: ask)")
    p.add_argument("--yes", action="store_true",
                   help="no prompts: every skill, every root already in use")
    p.add_argument("--dry-run", action="store_true",
                   help="print the plan and change nothing")
    args = p.parse_args(argv)

    # 1. the package: --source, else the tree this file lives in, else clone.
    local_pkg = None
    if args.source:
        local_pkg = Path(args.source).expanduser().resolve()
        if not is_package(local_pkg):
            die(f"--source {local_pkg} is not a devops package "
                "(no lib/tasks.py)")
    elif here_package() is not None:
        local_pkg = here_package()
    if local_pkg is not None:
        # --home only says where a clone would go; with a package in hand
        # nothing is cloned, so honouring it would be a silent no-op.
        if args.home:
            die(f"--home applies only when cloning; this run installs the "
                f"package already at {local_pkg}")
        pkg = local_pkg
    else:
        home = (Path(args.home).expanduser().resolve() if args.home
                else default_home())
        pkg = ensure_clone(home, args.dry_run)
        if args.dry_run and not is_package(pkg):
            print("\n(dry run stops here: the plan needs the cloned package)")
            return 0

    available = discover_skills(pkg)
    if not available:
        die(f"{pkg} has no installable skill (a subdir with a SKILL.md)")

    print(f"\npackage: {tilde(pkg)}  (v{package_version(pkg)})")
    print(f"skills:  {', '.join(available)}")

    # A terminal, not stdin: the documented install pipes the script in.
    interactive = tty_stream() is not None and not args.yes

    # 2. skills
    if args.skills:
        if args.skills.strip().lower() == "all":
            skills = list(available)
        else:
            skills = []
            for token in (t.strip() for t in args.skills.split(",")):
                if not token:
                    continue
                if token not in available:
                    die(f"unknown skill {token!r}; available: "
                        f"{', '.join(available)}")
                if token not in skills:
                    skills.append(token)
    elif interactive:
        skills = choose_skills(available)
    else:
        skills = list(available)

    # 3. roots
    if args.root:
        roots = []
        for raw in args.root:
            # "" resolves to the working directory — never install there.
            if not raw.strip():
                die("--root was given an empty path")
            candidate = Path(raw).expanduser().resolve()
            if candidate not in roots:
                roots.append(candidate)
    else:
        in_use, unused = discover_roots()
        if interactive:
            roots = choose_roots(in_use, unused, skills, pkg)
        else:
            roots = default_roots(in_use, unused)
    if not roots:
        die("no skill roots to install into; pass --root <path>")
    for root in roots:
        reject_root_inside_package(root, pkg)

    # 4. plan
    actions = []
    for root in roots:
        for name in skills:
            action = plan_for(root, name, pkg)
            if action:
                actions.append(action)
    if not actions:
        print("\nnothing to do — every selected skill is already linked here.")
        return 0

    # No terminal and no --yes: nobody can consent to a deletion, so the
    # replacements become skips rather than happening silently. Linking into
    # free paths still proceeds — nothing is lost that way.
    if tty_stream() is None and not args.yes:
        for a in actions:
            if a["verb"] == "replace":
                a["verb"] = "skip"
                a["reason"] = ("would replace an existing install; re-run "
                               "from a terminal, or pass --yes")

    print("\nplan:")
    for a in actions:
        if a["verb"] == "skip":
            print(f"  skip     {tilde(a['target'])}  ({a['reason']})")
        elif a["verb"] == "replace":
            print(f"  replace  {tilde(a['target'])}  ({a['detail']} → symlink)")
        else:
            print(f"  link     {tilde(a['target'])}")

    replacing = [a for a in actions if a["verb"] == "replace"]
    skipping = [a for a in actions if a["verb"] == "skip"]
    doing = [a for a in actions if a["verb"] in ("link", "replace")]
    if replacing and interactive:
        print(f"\n{len(replacing)} existing install(s) will be deleted and "
              "replaced by a symlink.")
        if not confirm("Proceed?"):
            print("nothing changed.")
            return 1
    if args.dry_run:
        print("\n(dry run: nothing changed)")
        return 0

    # 5. apply
    failed = 0
    for a in doing:
        if not apply(a, pkg, args.dry_run):
            failed += 1
    linked = len(doing) - failed
    print(f"\ninstalled {linked} skill link(s) from {tilde(pkg)}")
    sys.stdout.flush()
    for a in skipping:
        print(f"skipped {tilde(a['target'])}: {a['reason']}", file=sys.stderr)

    print("\nupdate both skills with: /dev skill update  (or git pull in "
          f"{tilde(pkg)})")
    print("note: an existing ./board viewer in a repo keeps working; it is "
          "rewritten to point at this install the next time you run "
          "/dev board.")
    return 1 if (failed or skipping) else 0


if __name__ == "__main__":
    raise SystemExit(main())
