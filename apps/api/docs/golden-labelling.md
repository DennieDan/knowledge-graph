# Golden v1 — second-labeller process (#106)

Two people label independently. `verdicts.json` is a CI check that planted
conflicts stay named — it is **not** a substitute for human labels on the
question set.

## Process

1. **Labeller A** opens each synthetic question (not held-out), sees the
   question text and the top retrieval chunks, and records `label_a` as a list
   of `{doc, quote}` pairs (document title + exact quote). Do not store chunk
   ids; the chunker may change.
2. **Labeller B** (teammate) does the same into `label_b` without looking at
   A's picks.
3. Where `label_a` and `label_b` disagree, write a short reconciliation note and
   set `agreed` to the final quote list. Set `second_human_label` to `"agreed"`.
4. Only after `agreed` is set for the scored forty may nightly answer metrics
   count as a release gate. Until then Health may show harness/fixture stubs
   from `app.golden.fixture_golden_metrics()`.

## Files

- `tests/fixtures/questions.json` — questions + `label_a` / `label_b` / `agreed`
- `tests/fixtures/verdicts.json` — eight planted conflicts (C1–C8)
- `scripts/seed_drive.py` — Studio North corpus; chats aligned with Drive POs
- `scripts/seed_golden.py --check` — chat ↔ Drive agreement (no network)

## Not done on this branch

Live golden cut: re-seed Drive, send WhatsApp chats on the spare number, import,
`golden-v1` tag, and dual human labels. Do not claim those complete from CI alone.
