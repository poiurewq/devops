#!/usr/bin/env python3
"""Build dev/SKILL.md and ops/SKILL.md from src/.

src/<skill>.md is that skill's SKILL.md with `<!-- core: <name> -->` lines,
each replaced by src/core/<name>.md, where `{{skill}}` becomes the skill's
name. The built file gets a one-line header after its frontmatter.

Run from anywhere: python3 src/build.py
"""
import os
import re
import sys

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
SKILLS = ("dev", "ops")
HEADER = "<!-- Built from src/ by src/build.py: edit there, then rebuild. -->"
MARKER = re.compile(r"^<!-- core: ([a-z0-9-]+) -->$")


def build(skill):
    with open(os.path.join(SRC, f"{skill}.md"), encoding="utf-8") as f:
        lines = f.read().split("\n")
    out = []
    for line in lines:
        m = MARKER.match(line)
        if not m:
            out.append(line)
            continue
        path = os.path.join(SRC, "core", f"{m.group(1)}.md")
        with open(path, encoding="utf-8") as f:
            out.append(f.read().rstrip("\n").replace("{{skill}}", skill))
    text = "\n".join(out)
    if not text.startswith("---\n"):
        sys.exit(f"error: src/{skill}.md must start with its frontmatter")
    end = text.index("\n---\n", 4) + len("\n---\n")
    return text[:end] + "\n" + HEADER + "\n" + text[end:]


def main():
    for skill in SKILLS:
        with open(os.path.join(ROOT, skill, "SKILL.md"), "w",
                  encoding="utf-8") as f:
            f.write(build(skill))
        print(f"built {skill}/SKILL.md")


if __name__ == "__main__":
    main()
