| `/{{skill}} flow` / `/{{skill}} flow list` | `TASKS flow list` (`--all` includes retired). |
| `/{{skill}} flow show <name>` | `TASKS flow show <name>`. |
| `/{{skill}} flow runs <name>` | `TASKS flow runs <name>` — every run of it, newest first. |
| `/{{skill}} flow adopt <source>` | Read `shared/routes/flow-create.md` — take a procedure the user already wrote (a doc, a pasted checklist, a file) into the playbook. No name needed up front; it is chosen once the scope is settled. A list of separate things to do is `/{{skill}} absorb` instead. |
| `/{{skill}} flow create [<name>] [from <id>\|from this conversation]` | Read `shared/routes/flow-create.md` — write one from scratch, from a run, or from what was just discussed. |
| `/{{skill}} flow edit <name> [<what to change>]` | Read `shared/routes/flow-create.md` (editing section). A change named in the invocation is made surgically; without one, the same collaborative rounds as create. |
| `/{{skill}} flow rename <name> <new-name>` | `TASKS flow rename <name> <new-name>`; say that the old name is free again and past runs still resolve. |
| `/{{skill}} flow retire <name>` | Confirm, then `TASKS flow retire <name>`. Kept for the record; never delete a flow that runs point at. |
| `/{{skill}} agent [list \| show \| add \| update \| rename \| rm] …` | `TASKS agent …` — the agents flows hand sequences to. `add` asks for the accessors (board contributors who can reach it) and a one-line description; `rm` confirms first. |
| `/{{skill}} env [list \| show \| add \| update \| rename \| rm] …` | `TASKS env …` — the places sequences run. `add` asks for the accessors, the machine if there is one, and what the place must provide (`--expects`); `rm` confirms first. |
| `/{{skill}} routine [list \| show \| add \| update \| rename \| rm] …` | `TASKS routine …` — the scheduled triggers that start recurring tasks (*Routines* below). `add` asks for the accessors, the mode, the environment, what the trigger is set to and where it lives, and how to change or remove it there; `rm` confirms first. |
