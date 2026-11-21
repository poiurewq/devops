`SKILL_DIR` = the directory containing this file.

`TASKS` = `SKILL_DIR/scripts/tasks.py` (an executable shim — one word, so it survives being stored in a shell variable; never prefix `python3`), run from inside the repo. It targets the nearest board at or above cwd, or `--scope <subdir>`; there is no single-board fallback, so in a repo of several products, work runs from the product directory.

If running a shim (`TASKS` or `SKILL_CMD`) directly fails with `permission denied` (the file modes were lost, e.g. a synced skills dir), that is not a script error: use `python3 SKILL_DIR/scripts/<name>.py …` for that call and every later one this session, spelled out each time, never stored in a shell variable.

On Windows (native Python with Git for Windows), never run a shim directly: run every call as `py SKILL_DIR/scripts/<name>.py …`, spelled out the same way. `board --watch` does not run there; plain `board` prints the board. A board with scheduled recurring tasks needs the timezone database (`py -m pip install tzdata`), which the script names when it is missing.

`SKILL_CMD` = `SKILL_DIR/scripts/skill.py` — acts on the installed skill, not the board (`shared/routes/skill.md`).
