# dev tour cards

The dev-only cards of the tour (`shared/routes/tour.md` says how to give them).

8. **Areas.** Each task is tagged with the regions of code it will touch, and dev keeps two contributors out of the same area at once — that is what prevents merge conflicts. — See it: `TASKS area list`, or `TASKS board --by-area`.
9. **Branch, PR, land.** Four steps take a task to done: `claim` gives it its own branch and worktree, `ship` opens a draft PR, `ready` hands it to review, and `land` is the integrator merging it — two more statuses, `draft` and `review`, between `doing` and `done`. `/dev <id>` drives a task through all four for you, stopping wherever a person has to decide. — See it: `TASKS whoami --role` says whether you can land.
10. **Intent and umbrellas.** Each task carries an `Intent:` line — what you want out of it, in your words — and finished work is judged against it; a big goal becomes an umbrella whose children do the work and which you close only once the goal holds. — See it: the `Intent:` line in `TASKS show <id>`.
