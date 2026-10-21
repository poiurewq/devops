#!/usr/bin/env python3
"""Shim: runs this skill's lib script (../lib/skill.py).

Resolves its own real path once, so an installed skill dir that is a symlink
into the devops clone still finds its skill dir, then execs <skill>/lib/
without resolving it: lib/ anchors on the skill dir it was reached through.
In the clone <skill>/lib is a link to the shared lib/; in a self-contained
copy it is a real directory. Keep this file free of logic.
"""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "lib", "skill.py")
os.execv(sys.executable, [sys.executable, TARGET] + sys.argv[1:])
