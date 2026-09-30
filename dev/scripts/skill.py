#!/usr/bin/env python3
"""Shim: runs the shared devops lib script (../../lib/skill.py).

Resolves its own real path first, so an installed skill dir that is a symlink
into the devops clone still finds lib/. Keep this file free of logic.
"""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
TARGET = os.path.join(os.path.dirname(os.path.dirname(HERE)), "lib", "skill.py")
# execv drops argv[0], so name the skill for lib/skill.py's printed guidance.
os.environ["DEVOPS_SKILL"] = os.path.basename(os.path.dirname(HERE))
os.execv(sys.executable, [sys.executable, TARGET] + sys.argv[1:])
