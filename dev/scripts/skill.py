#!/usr/bin/env python3
"""Shim: runs this skill's lib script (../lib/skill.py).

Resolves its own real path once, so an installed skill dir that is a symlink
into the devops clone still finds its skill dir, then execs <skill>/lib/
without resolving it: lib/ anchors on the skill dir it was reached through.
In the source tree <skill>/lib is a link to the shared lib/; in the
published clone and in a self-contained copy it is a real directory. Keep
this file free of logic.

Windows has no real exec: os.execv starts the child and exits at once, so
the caller sees exit 0 before the command has run. There the lib script runs
as a child in UTF-8 mode (file, pipe and git output all UTF-8) and its exit
code is passed through.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "lib", "skill.py")
if os.name == "nt":
    try:
        sys.exit(subprocess.call(
            [sys.executable, "-X", "utf8", TARGET] + sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
os.execv(sys.executable, [sys.executable, TARGET] + sys.argv[1:])
