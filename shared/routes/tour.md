# /<skill> tour — the key concepts, one card at a time

A walk-through for someone new to the skill in use (`/<skill>`). Never start it on your own: it runs only when the user asks (`/<skill> tour`, or yes to the offer at the end of init). Five core cards, then this skill's own cards in `routes/tour-cards.md`.

## How to give it

- **One card per message.** Say the card's sentence in your own words, then show it on their board: run the card's read-only command and quote a line or two of real output (a real task id, a real name). If that comes back empty, say what will show up there once there is work. Never write to the board during the tour.
- End each card with `next, or stop?`. Any reply but stop moves on; a question is answered first, then the tour continues. Stop ends it on the spot, with the last line below.
- No board here yet: give the cards anyway, pointers as "once it is set up, `<command>` shows this", and end on the init offer instead of add.
- Any term the tour has not introduced yet — in a card or in output you quote — gets a one-line aside where it first comes up. A newcomer should never meet a word they cannot place.
- Keep each card short. The tour is the map, not the manual — details are learned when a command first needs them.

## Core cards

1. **The board.** One board lives inside the repo: every task is a small file under `.tasks/`, synced through git, so every contributor on any machine sees the same thing. Its header names the current iteration: a stretch of work that is closed out and archived together, after which the next one starts. Being git history, the board is exactly as private as the repo and every clone keeps it for good: identifiers such as a username or an account number belong on it, but passwords, one-time codes, API keys and session tokens never do — sign-in stays in the environment that uses it (a browser session, the keychain). — See it: suggest `./board`, run in their own terminal rather than in the agent session (it is a live view driven by keys); here, show `TASKS board`, the same board as a snapshot.
2. **Tasks and statuses.** A task is a few sentences of aim, not a spec, and it moves `proposed` → `backlog` → `planned` → `doing` → `done`, with `shelved` and `not-planned` off to the side. — See it: `TASKS show <id>` on one of theirs.
3. **Identity.** Your GitHub login is who you are on this board (it maps to your handle on the roster), so the tasks you pick and run carry your name, and roles attach to it — the integrator, for one, is whoever merges finished work and closes iterations. — See it: `TASKS whoami`.
4. **The script writes the board.** Nobody hand-edits `.tasks/`: every change goes through the skill's script, which commits and pushes it on the board's branch — that is what keeps a shared board free of conflicts. — See it: `git log --oneline` on the board's branch, one commit per change.
5. **Agents draft, you decide.** Reviews, design questions, approvals and closing calls always come back to a person; an agent surfaces them and waits. Most come up right in the session, while an agent is building or reviewing with you; the list commands catch the ones left on the board, mostly by agents working unattended. — See it: `TASKS list --needs decision` and `TASKS list --status proposed`.

## This skill's cards

Read `routes/tour-cards.md` and give its cards, numbered on from 6, the same way.

## The other skill

After this skill's last card, ask once whether they want the other skill's side too, naming it ("want the ops side too?"). On a yes, read `../<other skill>/routes/tour-cards.md` from this skill's directory and give its cards, numbered on. On anything else, end.

## Ending

After the last card (or a stop), one line: `/<skill> add <task-or-goal>` files the first piece of work, or `/<skill> help` has the full map.
