# /<skill> flow review <name> — check a proposed flow write

`/<skill>` is the skill in use. You are reviewing a flow write someone else drafted, with fresh eyes: does it do what its intent says, and does the whole flow still make sense with it in? You report findings, then — on the user's word — apply the agreed fixes to the draft and write the flow from it. This holds whether an editor spawned you (its replies are the user's, relayed as given) or the user started this session themselves.

1. **Read the draft** at `<scope>/.dev/flow-drafts/<name>.md` — its `intent` and the whole proposed flow. No draft → stop and say so: this verb checks a proposed write against its intent, and without a draft there is neither. A review of a flow as it stands is not this verb.
2. **Read what it changes**: `TASKS flow show <name>`, and diff the draft against it. No such flow → a new one, and the whole draft is the change. Read every flow in its `uses` too, and the conventions it is held to: `shared/routes/flows.md` and `shared/routes/flow-create.md` *What makes a good flow*.
3. **Check against the intent.** Does the change do what the intent says — all of it, and nothing it does not say? An unrequested change is a finding, however good.
4. **Reason through the whole flow**, as a runner following it would: each input declared and used, each step given what it needs by an earlier one (or by a flow it uses), outputs left where a later step can reach them, every outward or hard-to-undo step `[user]` or behind a `[confirm]`, sequences' `Returns:` feeding what follows, step numbers continuous and every reference to one still pointing at the right step, the `description` still true. A flow another flow `uses` must still take what that flow passes it.
5. **Report** numbered findings, each marking whether it is **in the edit** or **outside the edit** (a problem the flow already had, or one the edit exposes elsewhere), then a proposal line:

```
Proposed: fix 1, 3 · leave 2 · ask 4
(fix = change the draft · leave = no action · ask = the user's call)
```

Outside-the-edit findings are proposed as `ask`: they go to the user, not into this write. No findings → say so in one line and propose writing it.
6. **Take the user's reply** and apply the agreed fixes to the draft. Two guards:
   - **An outside-the-edit finding the user takes up widens the write**: first extend the draft's `intent` line to cover it, then make the fix.
   - **Structural fixes** (reordered steps, a moved `[confirm]`, a new sequence): say in one line that a fresh review round is worth it and let the user decide. Never review your own fixes as if fresh — a new round is a new reviewer, spawned or in a new session.
7. **Write from the draft** once the user says it is right: its body to a temp file for `--file`, its frontmatter to `--desc`/`--inputs`/`--uses` (`TASKS flow create` for a new flow, `TASKS flow update` otherwise), then delete the draft and the temp file. A write the user drops deletes the draft too.
