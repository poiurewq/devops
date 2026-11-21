#!/usr/bin/env python3
"""devops installer — one clone per user, symlinked into agent skill roots.

    curl -fsSL https://raw.githubusercontent.com/poiurewq/devops/main/install.py | python3 -

Clones the package to ~/.local/share/devops (XDG_DATA_HOME honoured), asks
which agent skill roots to install into, then points a symlink at each skill
directory (dev and ops, always both) inside that one clone — a directory
junction on Windows, which needs no admin rights or Developer Mode. Updating
is a pull in the clone, so every agent sees it at once.

Re-running is the supported way to add a root, repair a link, or fill in a
root that holds only one of the skills: the clone is fast-forwarded and the
plan only lists what changes.

Already-installed skill directories are replaced only with the user's
consent, and never when they hold unsaved work (a dirty or unpushed clone
is skipped, not overwritten). Prompts go to the terminal (/dev/tty), so
they still work when the script itself is what stdin is feeding; on Windows
they come only from a console on stdin. With no terminal at all, replacing
needs an explicit --yes.

Run from inside a package tree (a manual clone, or a copied tree passed via
--source), that tree is used as-is and nothing is cloned — otherwise a
second copy would appear behind the user's back.

--copy-to DIR is the second install shape: self-contained skill copies in
DIR/<skill>/, with no symlinks and no files outside each skill dir, for
anywhere a link into one clone will not do (an uploaded folder, say). It
builds from the package in hand, else from a temporary clone it deletes
afterwards, so it never touches the linked install. Each copy carries a
BUILD record, which is how a rebuild knows it may replace that dir and how
the default install knows to leave it alone.

A package comes in two layouts. In the source tree each skill links to one
shared lib/, shared/ and VERSION at the top (<skill>/lib -> ../lib). The
published tree, which is what gets cloned, holds no links at all: each skill
dir carries its own copies and there is no top-level lib/ or shared/, so a
Windows checkout needs no symlink support. Everything here accepts either
layout.

--uninstall reverses the linked install: every link in a skills root that
points into the package, then the clone (only a clean clone of the
canonical repo; a --source tree is never deleted), then, on consent, the
prefs. Copies and the boards in the user's repos are never touched.

CANONICAL_REPO is duplicated in lib/skill.py, which owns the update path.
This file must stay standalone: it runs before any clone exists, so it
cannot import from lib/.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CANONICAL_REPO = "https://github.com/poiurewq/devops"
CANONICAL_SLUG = "poiurewq/devops"
# The pre-devops skill: a clone of this in a skills root is what migration
# replaces with a symlink.
LEGACY_SLUG = "poiurewq/dev"
# Agent product directories are ~/.claude, ~/.grok and their variants
# (~/.claude-work, …); each keeps its skills in <home>/skills. Duplicated in
# lib/skill.py, which links a skill missing beside its sibling.
AGENT_HOME_GLOBS = (".claude*", ".grok*")
SKILLS_SUBDIR = "skills"
# Build record in each --copy-to copy; lib/skill.py reads the same name.
BUILD_RECORD = "BUILD"
# Package-level paths each skill links to in the source layout
# (<skill>/<name> -> ../<name>); a copy and the published tree expand them
# into real files.
PACKAGE_LINKS = ("lib", "VERSION", "shared")
# git's file mode for a symlink (ls-files -s).
GIT_SYMLINK_MODE = "120000"
WINDOWS = os.name == "nt"
# What the installer makes at <root>/<skill>, as printed (make_dir_link).
LINK_KIND = "junction" if WINDOWS else "symlink"


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
    """True when path is a devops package tree (not merely a git clone):
    VERSION plus lib/tasks.py, at the top (source layout) or inside a skill
    dir (the link-free published layout)."""
    if not (path / "VERSION").is_file():
        return False
    return (path / "lib" / "tasks.py").is_file() or any(
        (path / name / "lib" / "tasks.py").is_file()
        for name in discover_skills(path))


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
    if git_out(["stash", "list"], path):
        return "stashed changes"
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
            die(f"{home} is a clone of {CANONICAL_SLUG} but has no "
                "lib/tasks.py or VERSION; the clone looks damaged — remove it "
                "and re-run")
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
        die(f"cloned {CANONICAL_SLUG} but {home} has no lib/tasks.py or "
            "VERSION")
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
    """One-line summary of what is already installed in this root.

    The skills install together, so a root holding only some of them reads
    as incomplete: this run fills in the rest.
    """
    if not root.exists():
        return "will be created"
    found = {name: classify(root / name, pkg)[:2] for name in skills}
    if all(kind == "linked" for kind, _ in found.values()):
        return "installed"
    missing = [n for n, (kind, _) in found.items() if kind == "free"]
    if len(missing) == len(skills):
        return "nothing installed"
    if missing:
        return f"incomplete: {', '.join(missing)} missing"
    return ", ".join(f"{n}: {detail}" for n, (kind, detail) in found.items()
                     if kind != "linked")


# --- targets ---------------------------------------------------------------

def classify(target: Path, pkg: Path) -> tuple[str, str, str]:
    """(kind, human description, blocking reason) for one <root>/<skill>.

    kind is one of: free, linked, link-other, built-copy, clone-legacy,
    clone-canonical, clone-other, copy, file. A built copy is always
    blocked: someone chose that shape for that path, so no answer and no
    --yes turns it into a symlink.
    """
    if is_link(target):
        kind = "symlink" if target.is_symlink() else "junction"
        try:
            dest = target.resolve()
        except OSError:
            return "link-other", f"broken {kind}", ""
        if dest == (pkg / target.name).resolve():
            return "linked", "already linked here", ""
        return "link-other", f"{kind} to {tilde(dest)}", ""
    if not target.exists():
        return "free", "", ""
    if target.is_dir():
        if (target / BUILD_RECORD).is_file():
            return ("built-copy", "self-contained copy",
                    "self-contained copy (--copy-to); left in place")
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
        return os.path.normcase(os.path.realpath(path))
    except OSError:
        return os.path.normcase(str(path))


def reject_root_inside_package(root: Path, pkg: Path,
                               what: str = "a skills root") -> None:
    """A root at or under the package would link a skill dir to itself.

    The installer replaces whatever occupies <root>/<skill>, so a root of
    the package itself makes <pkg>/dev both source and target: the real
    directory is deleted and a symlink to nothing takes its place.
    """
    root_key, pkg_key = path_key(root), path_key(pkg)
    if root_key == pkg_key or root_key.startswith(pkg_key + os.sep):
        die(f"{tilde(root)} is inside the package at {tilde(pkg)}; {what} "
            "must be somewhere else, or the skill would be written over "
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
# prompt goes to the controlling terminal instead. Windows has no reliable
# equivalent: CONIN$ opens even with nobody at it, and its readline() then
# blocks forever, so there a prompt comes only from a real console on stdin
# (windows_console) and a piped run is unattended. _TTY is the cached handle;
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


def windows_console() -> bool:
    """stdin is a Windows console someone can type at. isatty() is not
    enough: it is True for NUL (what </dev/null becomes), so stdin must be a
    console input buffer, and one with a window — a console created without
    one (an agent's or a service's shell) has nobody typing at it."""
    import ctypes
    import msvcrt
    from ctypes import wintypes
    try:
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
    except (AttributeError, OSError, ValueError):
        return False
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetConsoleMode.argtypes = (wintypes.HANDLE,
                                        ctypes.POINTER(wintypes.DWORD))
    kernel32.GetConsoleWindow.restype = wintypes.HWND
    mode = wintypes.DWORD()
    return (bool(kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
            and bool(kernel32.GetConsoleWindow()))


def tty_stream():
    """The terminal to prompt on, or None when the run is unattended."""
    global _TTY
    if _TTY is False:
        if WINDOWS:
            _TTY = sys.stdin if windows_console() else None
        elif sys.stdin.isatty():
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


def confirm(prompt: str) -> bool:
    return ask(f"{prompt} [y/N/q] ").lower() in ("y", "yes")


def tilde(path: Path) -> str:
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return path.as_posix()


# --- apply -----------------------------------------------------------------

def is_link(path: Path) -> bool:
    """A symlink, or a directory junction (what Windows installs make)."""
    if path.is_symlink():
        return True
    try:
        tag = getattr(os.lstat(path), "st_reparse_tag", 0)
    except OSError:
        return False
    # IO_REPARSE_TAG_MOUNT_POINT; the stat module defines it on Windows only.
    return tag == 0xA0000003


def make_dir_link(target: Path, source: Path) -> None:
    """Point target at the directory source. On Windows a junction: a
    symlink there needs admin rights or Developer Mode, a junction does not.
    Duplicated in lib/skill.py."""
    if not WINDOWS:
        target.symlink_to(source, target_is_directory=True)
        return
    r = run(["cmd", "/c", "mklink", "/J", str(target), str(source)])
    if r.returncode != 0:
        raise OSError((r.stderr or r.stdout or "").strip()
                      or "mklink /J failed")


def remove_link(path: Path) -> None:
    """Remove a link (or file) itself, never what it points at. A Windows
    junction or directory symlink is removed with rmdir, which leaves its
    target alone."""
    if WINDOWS and path.is_dir():
        os.rmdir(path)
    else:
        path.unlink()


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
            if is_link(target) or target.is_file():
                remove_link(target)
            else:
                backup = target.with_name(target.name + ".devops-old")
                if is_link(backup) or backup.is_file():
                    remove_link(backup)
                elif backup.is_dir():
                    shutil.rmtree(backup)
                os.rename(target, backup)
        make_dir_link(target, source)
    except OSError as e:
        print(f"error: {tilde(target)}: {e}", file=sys.stderr)
        if backup is not None:
            try:
                if not target.exists() and not is_link(target):
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


# --- copies ----------------------------------------------------------------

def temp_clone(tmp: Path) -> Path:
    """Shallow clone into tmp: copy mode must not create the linked install."""
    if shutil.which("git") is None:
        die("git not found; install git and re-run")
    dest = tmp / "devops"
    print(f"fetching {CANONICAL_REPO} (temporary clone)")
    r = run(["git", "clone", "--depth", "1", f"{CANONICAL_REPO}.git", str(dest)])
    if r.returncode != 0:
        die(f"git clone failed: {(r.stderr or r.stdout).strip()}")
    if not is_package(dest):
        die(f"cloned {CANONICAL_SLUG} but it has no lib/tasks.py or VERSION")
    return dest


def copy_plan(target: Path) -> tuple[str, str]:
    """(verb, reason) for one <out>/<skill>: build, rebuild, or skip.

    Only a previous copy is replaced; anything else at that path is someone
    else's and is reported, never deleted.
    """
    if is_link(target):
        return "skip", "a symlink (a linked install?); move it aside"
    if not target.exists():
        return "build", ""
    if target.is_dir() and (target / BUILD_RECORD).is_file():
        return "rebuild", ""
    return "skip", "not a previous self-contained copy; move it aside"


def tracked_entries(pkg: Path, pathspecs) -> dict[str, str] | None:
    """{path relative to pkg: git mode} for each file git tracks under
    pathspecs; None when it tracks none (not a work tree, or untracked).
    Relative to pkg, which may be nested in another repo."""
    r = run(["git", "-C", str(pkg), "ls-files", "-s", "-z", "--",
             *pathspecs])
    entries: dict[str, str] = {}
    if r.returncode == 0:
        for record in (r.stdout or "").split("\0"):
            meta, _, rel = record.partition("\t")
            if rel:
                entries[rel] = meta.split(" ", 1)[0]
    return entries or None


def tracked_copy_files(pkg: Path, name: str) -> list[tuple[Path, str]] | None:
    """(source, path in the copy) for every file git tracks in skill name.

    In the source layout <name>/lib, <name>/VERSION and <name>/shared are
    tracked symlinks, each expanded from the package's own lib/, VERSION and
    shared/; in the published layout they are already real files. A link is
    told by its git mode, not the work tree, so a checkout without symlink
    support (the link a plain text file) still builds right. A tracked file
    missing from the work tree is skipped. None when git tracks nothing
    here: the caller copies the tree.
    """
    entries = tracked_entries(pkg, [name, *PACKAGE_LINKS])
    if entries is None:
        return None
    links = {f"{name}/{link}" for link in PACKAGE_LINKS
             if entries.get(f"{name}/{link}") == GIT_SYMLINK_MODE}
    files = []
    for rel in entries:
        if rel in links or not (pkg / rel).is_file():
            continue
        if rel.startswith(f"{name}/"):
            dest = rel[len(name) + 1:]
        elif f"{name}/{rel.split('/')[0]}" in links:
            # Package files only where the skill links them: an older
            # skill without the links must fail the predates check, not
            # get a copy whose shims still reach outside it.
            dest = rel
        else:
            continue
        files.append((pkg / rel, dest))
    return files


def stage_skill(pkg: Path, name: str, staging: Path) -> None:
    """Write skill name into staging as real files, or die if it cannot
    stand alone. From a git work tree only tracked files are copied, so the
    result matches one from a clean clone."""
    files = tracked_copy_files(pkg, name)
    if files is None:
        shutil.copytree(pkg / name, staging, symlinks=False,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        for src, rel in files:
            (staging / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, staging / rel)
    if not ((staging / "lib" / "tasks.py").is_file()
            and (staging / "VERSION").is_file()):
        shutil.rmtree(staging, ignore_errors=True)
        die(f"{tilde(pkg / name)} has no lib/ or VERSION of its own; this "
            "package predates self-contained copies")


def build_copy(pkg: Path, name: str, out: Path) -> None:
    """Write out/<name> as real files, replacing a previous copy last.

    The skill's lib/, VERSION and shared/ links are followed, which is what
    makes it self-contained (stage_skill). The new tree is built beside the
    target and swapped in by rename, so a failed build never leaves the old
    copy half-replaced.
    """
    target = out / name
    staging = out / f"{name}.devops-new"
    if staging.exists():
        shutil.rmtree(staging)
    stage_skill(pkg, name, staging)
    (staging / BUILD_RECORD).write_text(
        f"version: {package_version(pkg)}\n"
        f"output: {out}\n", encoding="utf-8")
    old = out / f"{name}.devops-old"
    if target.exists():
        if old.exists():
            shutil.rmtree(old)
        os.rename(target, old)
    os.rename(staging, target)
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)


def install_copies(pkg: Path, skills: list[str], out: Path,
                   dry_run: bool) -> int:
    reject_root_inside_package(out, pkg, "the --copy-to dir")
    plans = [(name, *copy_plan(out / name)) for name in skills]
    print(f"\ncopies into {tilde(out)}:")
    for name, verb, reason in plans:
        detail = f"  ({reason})" if reason else ""
        print(f"  {verb:<8} {tilde(out / name)}{detail}")
    if dry_run:
        print("\n(dry run: nothing changed)")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    built = [n for n, verb, _ in plans if verb != "skip"]
    for name in built:
        build_copy(pkg, name, out)
    print(f"\nbuilt {len(built)} self-contained skill copy(ies) in "
          f"{tilde(out)} (v{package_version(pkg)})")
    sys.stdout.flush()
    skipped = [(n, r) for n, verb, r in plans if verb == "skip"]
    for name, reason in skipped:
        print(f"skipped {tilde(out / name)}: {reason}", file=sys.stderr)
    if built:
        print("each skill folder stands on its own. A copy does not update "
              "itself: re-run this command to rebuild, then put the new copy "
              "wherever the old one went.")
    return 1 if skipped else 0


def tzdata_warning() -> str:
    """On Windows, how to install the timezone database when this Python
    lacks one, else "". Windows ships none, and without it every board
    command on a board with a scheduled task stops."""
    if not WINDOWS:
        return ""
    try:
        import zoneinfo
        zoneinfo.ZoneInfo("America/New_York")
        return ""
    except Exception:
        return ("warning: this Python has no timezone database, which any "
                "board with a scheduled task needs; install it with:\n"
                "  py -m pip install --user tzdata")


def warn_tzdata() -> None:
    """Print tzdata_warning, if any, after what stdout has so far."""
    warning = tzdata_warning()
    if warning:
        sys.stdout.flush()
        print(warning, file=sys.stderr)


# --- uninstall -------------------------------------------------------------

def config_files() -> list[Path]:
    """The user's prefs files that exist: the current path and the one read
    as a fallback before dev and ops shared a package. Both are duplicated
    from lib/skill.py (CONFIG_PATH, LEGACY_CONFIG_PATH)."""
    config = Path.home() / ".config"
    return [p for p in (config / "devops-skill" / "config.yml",
                        config / "dev-skill" / "config.yml") if p.is_file()]


def path_is_inside(path: Path, parent: Path) -> bool:
    key, parent_key = path_key(path), path_key(parent)
    return key == parent_key or key.startswith(parent_key + os.sep)


def links_into(roots: list[Path], pkg: Path) -> list[Path]:
    """Every entry in roots that is a link into pkg — whatever its name, and
    even when pkg is already gone (a broken link still names its target).
    Anything else in a root, a self-contained copy included, is not ours."""
    found = []
    for root in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if is_link(entry) and path_is_inside(entry, pkg):
                found.append(entry)
    return found


def clone_verdict(pkg: Path, is_source: bool) -> str:
    """"" when pkg may be deleted, else why it stays. Only a clean clone of
    the canonical repo is reproducible by a re-install; a --source tree, a
    tree nested in another repo or a fork is someone's own work."""
    if is_source:
        return "a --source tree; never deleted"
    if git_root(pkg) is None:
        return "not a git clone of its own; delete it by hand if you mean to"
    slug = clone_slug(pkg)
    if slug.lower() != CANONICAL_SLUG.lower():
        return f"a clone of {slug or 'no GitHub remote'}, not {CANONICAL_SLUG}"
    return clone_has_unsaved_work(pkg)


def remove_tree(path: Path) -> None:
    """rmtree that also clears read-only files, which git leaves under
    .git/objects on Windows and which os.remove there refuses."""
    import stat

    def retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def uninstall(args: argparse.Namespace) -> int:
    """Remove the linked install: the links in every skills root that point
    into the package, then the clone, then (on consent) the prefs. Boards
    live in the user's repos and are never touched."""
    if args.source and args.home:
        die("--source and --home name the package two ways; pass one")
    is_source = bool(args.source)
    if args.source:
        pkg = Path(args.source).expanduser().resolve()
    elif args.home:
        pkg = Path(args.home).expanduser().resolve()
    else:
        pkg = here_package() or default_home()
    if args.root:
        if any(not raw.strip() for raw in args.root):
            die("--root was given an empty path")
        roots = [Path(raw).expanduser().resolve() for raw in args.root]
    else:
        roots, _unused = discover_roots()
    links = links_into(roots, pkg)
    keep = clone_verdict(pkg, is_source) if pkg.exists() else ""
    delete_pkg = pkg.exists() and not keep
    configs = config_files()
    if not links and not pkg.exists() and not configs:
        print(f"nothing to uninstall: no clone at {tilde(pkg)} and no links "
              "into it.")
        return 0

    print("\nuninstall plan:")
    for link in links:
        print(f"  unlink   {tilde(link)}")
    if delete_pkg:
        print(f"  delete   {tilde(pkg)}  (the clone)")
    elif pkg.exists():
        print(f"  keep     {tilde(pkg)}  ({keep})")
    interactive = tty_stream() is not None and not args.yes
    for path in configs:
        how = ("delete" if args.remove_config else "ask" if interactive
               else "keep")
        print(f"  {how:<8} {tilde(path)}  (your prefs)")
    print("never touched: self-contained copies (--copy-to), and the boards "
          "in your repos (.tasks/, .flows/, .dev/, ./board)")

    remove_config = args.remove_config
    if args.dry_run:
        print("\n(dry run: nothing changed)")
        return 0
    if interactive:
        if not confirm("\nUninstall?"):
            print("nothing changed.")
            return 1
        if configs and not remove_config:
            remove_config = confirm("Remove your prefs too?")
    elif not args.yes:
        die("nothing changed: uninstalling needs consent; re-run from a "
            "terminal, or pass --yes")

    failed = unlinked = 0
    for link in links:
        try:
            remove_link(link)
            unlinked += 1
        except OSError as e:
            print(f"error: {tilde(link)}: {e}", file=sys.stderr)
            failed += 1
    if delete_pkg:
        if path_is_inside(Path.cwd(), pkg):
            # Windows will not delete a directory some process sits in.
            os.chdir(pkg.parent)
        try:
            remove_tree(pkg)
        except OSError as e:
            print(f"error: could not delete {tilde(pkg)}: {e}",
                  file=sys.stderr)
            failed += 1
    if remove_config:
        for path in configs:
            try:
                path.unlink()
            except OSError as e:
                print(f"error: could not delete {tilde(path)}: {e}",
                      file=sys.stderr)
                failed += 1
                continue
            with contextlib.suppress(OSError):
                path.parent.rmdir()  # only when nothing else is in it

    gone = delete_pkg and not pkg.exists()
    print(f"\nremoved {unlinked} skill link(s)"
          + (f" and the clone at {tilde(pkg)}" if gone else ""))
    sys.stdout.flush()
    if pkg.exists() and keep:
        print(f"kept {tilde(pkg)}: {keep}", file=sys.stderr)
    if configs and not remove_config:
        print(f"kept your prefs: {', '.join(tilde(p) for p in configs)}")
    print("your boards are untouched; a repo's ./board viewer stops working "
          "and can be deleted.")
    return 1 if failed or (pkg.exists() and keep) else 0


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


def package_skills(args: argparse.Namespace, pkg: Path) -> list[str]:
    """Every skill in the package: they always install together."""
    available = discover_skills(pkg)
    if not available:
        die(f"{pkg} has no installable skill (a subdir with a SKILL.md)")

    print(f"\npackage: {tilde(pkg)}  (v{package_version(pkg)})")
    print(f"skills:  {', '.join(available)}")
    if args.skills is not None:
        print("note: --skills is ignored; the skills always install together")
    return available


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
    # Deprecated and ignored. Older copies print a rebuild command carrying
    # it, which must still run rather than fail on an unknown argument.
    p.add_argument("--skills", metavar="LIST", help=argparse.SUPPRESS)
    p.add_argument("--root", metavar="PATH", action="append", default=[],
                   help="skills root to install into (repeatable; default: ask)")
    p.add_argument("--yes", action="store_true",
                   help="no prompts: every root already in use")
    p.add_argument("--dry-run", action="store_true",
                   help="print the plan and change nothing")
    p.add_argument("--copy-to", metavar="DIR",
                   help="instead of linking, build self-contained skill "
                        "copies in DIR/<skill>/")
    p.add_argument("--uninstall", action="store_true",
                   help="remove the skill links into the clone, then the "
                        "clone (--home / --source say which package)")
    p.add_argument("--remove-config", action="store_true",
                   help="with --uninstall: also delete your prefs "
                        "(otherwise asked, or kept under --yes)")
    args = p.parse_args(argv)
    if args.remove_config and not args.uninstall:
        die("--remove-config applies only with --uninstall")
    if args.uninstall:
        if args.copy_to is not None:
            die("--uninstall and --copy-to do opposite things; pass one. "
                "A self-contained copy is removed by deleting its folder")
        return uninstall(args)
    if args.copy_to is not None:
        if not args.copy_to.strip():
            die("--copy-to was given an empty path")
        # Copies never land in a skills root of their own accord, and are
        # built from a package in hand or a throwaway clone, never --home.
        if args.root:
            die("--root applies only to linking; --copy-to says where "
                "copies go")
        if args.home:
            die("--home applies only to the linked install; --copy-to "
                "builds from a temporary clone")

    # 1. the package: --source, else the tree this file lives in, else clone.
    local_pkg = None
    if args.source:
        local_pkg = Path(args.source).expanduser().resolve()
        if not is_package(local_pkg):
            die(f"--source {local_pkg} is not a devops package "
                "(no lib/tasks.py)")
    elif here_package() is not None:
        local_pkg = here_package()
    if args.copy_to is not None:
        out = Path(args.copy_to).expanduser().resolve()
        with tempfile.TemporaryDirectory(prefix="devops-copy-") as tmp:
            pkg = local_pkg or temp_clone(Path(tmp))
            skills = package_skills(args, pkg)
            warn_tzdata()
            return install_copies(pkg, skills, out, args.dry_run)
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

    # 2. skills
    skills = package_skills(args, pkg)
    warn_tzdata()
    interactive = tty_stream() is not None and not args.yes

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
        print("\nnothing to do — every skill is already linked in every root.")
        return 0

    # No terminal and no --yes: nobody can consent to a deletion, so the
    # replacements become skips rather than happening silently. Linking into
    # free paths still proceeds — nothing is lost that way.
    if tty_stream() is None and not args.yes:
        # On Windows a Git Bash run is seldom a console either, so name a
        # window that is, and the clone's own install.py to run there.
        where = (f"run py {pkg / 'install.py'} from a cmd or PowerShell "
                 "window to choose" if WINDOWS
                 else "re-run from a terminal")
        for a in actions:
            if a["verb"] == "replace":
                a["verb"] = "skip"
                a["reason"] = (f"would replace an existing install; {where}, "
                               "or pass --yes")

    print("\nplan:")
    for a in actions:
        if a["verb"] == "skip":
            print(f"  skip     {tilde(a['target'])}  ({a['reason']})")
        elif a["verb"] == "replace":
            print(f"  replace  {tilde(a['target'])}  ({a['detail']} → {LINK_KIND})")
        else:
            print(f"  link     {tilde(a['target'])}")

    replacing = [a for a in actions if a["verb"] == "replace"]
    skipping = [a for a in actions if a["verb"] == "skip"]
    doing = [a for a in actions if a["verb"] in ("link", "replace")]
    if replacing and interactive:
        print(f"\n{len(replacing)} existing install(s) will be deleted and "
              f"replaced by a {LINK_KIND}.")
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
    if not WINDOWS:  # no ./board viewer is written there
        print("note: an existing ./board viewer in a repo is rewritten to "
              "point at this install the next time you run /dev board; "
              "until then one from an older install may say it is stale.")
    return 1 if (failed or skipping) else 0


if __name__ == "__main__":
    # Plans and paths print arrows and dashes; a Windows pipe defaults to
    # the ANSI code page, which cannot print them.
    for _stream in (sys.stdout, sys.stderr):
        _stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
