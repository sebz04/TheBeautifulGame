# Verifier

**Status:** built (TASK-16.2 number checking, TASK-18 Verifier and evaluation). The agents that feed it are on [agents.md](agents.md).

## Verifier (`agents/verifier.py`, TASK-18.1)
`verify(insight, lang, text, facts, client, *, tracer=None) -> Verdict(ok, failures, fixed_claims)`. `text` is the insight (`insight_text`: headline, why, recommendation) or its translation into `lang`.
1. **Numbers come first, and the model can't override them.**
   - Every claim is looked up by its ref.
   - Every number in the text must match a verified claim, a real event minute, a scoreline the match passed through, or a formation actually used. This is `numbers.check_text`, run in the text's own language.
   - If anything fails, the model isn't asked at all.
   - Failures name the claim's text, its value, and the stored value. An unclaimed number is quoted in its sentence ("in “…5 shots and a 41% pass accuracy…”"), with a note that every number needs its own claim. `fixed_claims` carries the stored values.
   - **Which half** is the agent's call, not the code's. A phrase match flagged "extend their lead in the second half", which is advice about later. The prompt says a half the moment happened in must be its events' half, and a half named for the future or the past is fine.
2. **Wording (the Verifier agent, temperature 0).** It reads the text against:
   - the cited events, each shown with its minute label, type, team and player names, outcome, `third` (attacking, middle, or defensive, worked out for the acting team), and `just_before` (the 3 events before it, for checking stated causes);
   - the claims, shown as `facts` (each claim's statement with its numbers blanked to `#`, and whose it is, `about`, by name). Without values the model can't re-check rounding: it flagged "43%" against 42.5%, and "54%" against 53.8%.
   - **It replies one statement at a time** (`checks: [{statement, verdict, reason}]`, with verdicts `supported`, `not_covered`, `contradicted`, or `invented`). `contradicted` and `invented` become `qualitative: '<statement>': <reason>` failures.
   - A malformed reply or an empty check list is retried once. After that the text fails, so the Verifier fails closed.
- **`verify_loop(decision, moment, client, tools, facts, *, max_regenerations=2, on_attempt=None)`** runs Explainer → Verifier and feeds the failures back (`explain(..., feedback=...)`).
  - It returns the insight with `verified=True`, or None after 2 regenerations or an `ExplainerError`. On None, TASK-20 shows a template.
  - `on_attempt(insight, verdict)` sees every draft.
- **`Facts`** is a protocol: `names`, `minutes`, `scores`, `formations`, `lookup(claim)`, `events(ids)`, and `third(event)`.
  - **`StatsFacts(StatsService, match_id)`** is the production version. It uses the same event-exact snapshot as the tools, so a claim copied from a tool verifies against itself. It handles:
    - `metric:` refs, where the claim metric must equal the ref's name;
    - `deviation:` refs, with metrics `<stat>`, `<stat>_expected`, `<stat>_baseline_per90`, and `<stat>_p_value`;
    - event refs: `counterfactual_*` through `get_counterfactual`, event fields and extras, 1 for the event itself (a `goal` claim on a goal event), and ball speed in m/s or km/h.
- **Metric refs say whose value it is:** `metric:<name>@<period>:<t>/<team|player>:<id>`. Before this, both teams' PPDA had the same ref.
- **New team metric `players`**: 11 minus red cards, so "down to ten men" can be claimed.
- **Evaluation (TASK-18.2, `docs/evals.md`):** on the 40-insight golden set, 3 runs with gpt-4.1-mini:
  - recall 0.95 on planted errors (numbers 1.00, wording 0.88);
  - precision 1.00, with 0 false alarms on 60 correct checks;
  - about 2 s per model check.
- **Live loop (final recording, 3 moments):** all 3 verified on the first try, 12–21 s each. Earlier runs needed up to 2 regenerations. The Verifier caught unclaimed counts ("5 shots", "10 men") and a wrong value (63% field tilt where the stats say 38.5%), and the feedback fixed them.
- **Known gaps** (also in `docs/evals.md`):
  - ~~Numbers are matched to claims by value, not meaning~~: team numbers are now tied to the team named (below, TASK-25.2).
  - Interpretation slips pass, such as PPDA read as pressure faced.

## Lead wording (`agents/scoreline.py`, TASK-24.4)
- **Why:** the Verifier checked numbers, not who was winning, so "Morejo gives Chapinero the lead" passed at 1–1 and reached the live site.
- **Check:** `lead_failures(text, lang, teams, score)` finds phrases that tie a lead to a named club in all 5 languages ("gives X the lead", "puts X ahead", "da ventaja a X", "garante vantagem para X", "X prend l'avantage", "يمنح X التقدم") and fails them unless that club is strictly ahead at the moment's end. Other meanings ("leads the press", "ventaja numérica") don't match. `team_variants` gives each club's full name and the words no other club shares.
- **In the Verifier:** deterministic, before the model; `StatsFacts.lead_context(moment_id)` supplies the names and the score at the moment's end (facts without it skip the check).
- **Sweep:** `scripts/fix_scoreline.py [--apply] [--db URL]` replaces stored insights (and all their texts and live line) and fan texts that fail with their templates. Found 1 insight and 26 fan texts (most French "prend l'avantage" at a level score). Since TASK-25.2 it also applies the team-number check and re-renders template texts.

## Team numbers (`agents/owners.py`, TASK-25.2)
- **Why:** numbers were matched by value, so "Atlético Chapinero allow 8.7 passes per defensive action" passed with Laureles' PPDA (golden `e19`, missed by the model 3/3).
- **Check:** `owner_failures(text, lang, claims, teams)` ties each number that matches only team claims to the one team named before it in its clause (at most 8 words, no comma between); it fails if that team owns none of them. Skipped when the owner is named after the number, after "by", "vs", "frente a", "مقابل", "our"/"nuestro" (a fan's own club), after "outshot", for PPDA told from the passing side ("allowing Getsemaní 5.76"), and for "the last 10 minutes".
- **Measured** on all 3,702 stored agent texts: 19 flags, 18 real (such as "Laureles enjoy 60% of final-third passes" with San Antonio's 60%) and 1 false alarm ("forçou 3 impedimentos"). On the golden set it catches `e18` and `e19` and passes all 20 correct lines.
- **In the Verifier:** deterministic, before the model, with `Facts.clubs`. The local sweep replaced 1 insight and 16 fan texts and re-rendered 655 templates.

## Golden set and evaluation (TASK-18.2)
- **`scripts/build_verifier_golden.py`** writes `evals/verifier_golden.jsonl`, and the output is deterministic. It holds 40 insights written by code from the stats and events of 3 built matches:
  - **20 correct:** team pressing, goals, red cards, missed chances, and ball regains by third, in all 5 languages (es, pt, fr, and ar with Arabic-Indic digits).
  - **20 planted errors, 12 numeric:** wrong value, invented number, the other team's stat, wrong minute, wrong score, derived number, wrong formation, unverifiable ref, wrong value in Spanish and in Arabic, wrong precision, and a number word.
  - **8 wording errors:** wrong team, wrong player, wrong place, wrong outcome, wrong order, red card given to the wrong team, stat given to the wrong team, and an invented cause.
  - Each line carries its facts (`DictFacts`), so it runs without the database.
- **`tests/agents/test_golden.py`** (CI) runs the number stage with a judge that passes everything. It checks that all 12 numeric errors are caught, that all 20 correct insights pass, and that all 8 wording errors get past the number stage, which proves those need the model.
- **`scripts/run_foundry_eval.py [--runs 3]`** runs the full `verify` with the live deployment and writes `docs/evals.md`: recall overall and per stage, precision, false alarms, misses, and time. Notes below the `<!-- notes -->` marker are kept between runs.
- **Rulings:**
  - Foundry's built-in evaluators (`agent_framework.foundry.FoundryEvals`: relevance, coherence, groundedness) don't measure catching planted errors. So "the Foundry evaluation" means our `verify` on the Foundry deployment, scored locally.
  - Uploading results to the Foundry portal's Evaluations page is deferred: the API is experimental.

## Number checking (`agents/numbers.py`, TASK-16.2)
The Verifier's deterministic rule: every number an agent writes must match a verified stat, a real event minute, the real score, or a formation actually used. Nothing is skipped.

- `extract_numbers(text, lang) -> list[ExtractedNumber]` reads numbers the way each language writes them:
  - decimal commas (`es`, `pt`, `fr`: "1,5");
  - thousands separators ("12.000", "12 000" including narrow spaces, "12,000");
  - Arabic-Indic digits with Arabic separators ("١٢٬٠٠٠", "٣٫٥");
  - number words 0–20 in all 5 languages, including Arabic teens ("ثلاثة عشر") and prefixes ("و", "ال").
- **Units:** `%` (and "por ciento", "pour cent"), `km/h`, `m/s`, `km`, `m`.
- **Minute marks:** "62'", "62nd minute", "minuto 62", "62e minute", "الدقيقة ٦٢", and "90+3'" (read as 93).
- **Scorelines** ("2-1", "2 a 1") and **formations** ("4-2-3-1") are read as one token each.
- A separator that isn't a 3-digit group is read as a decimal point in any language ("1.5" in Spanish is 1.5).
- Words for 1 (un, una, um, une, one, واحد) are not numbers: they double as articles.
- `check_text(text, lang, claims, lookup, rel_tol=0.01, abs_tol=0.05, *, minutes, scores, formations) -> NumberCheck(ok, failures)`:
  - Each claim must agree with its stored value, compared at the claim's own precision.
  - Each number in the text must match a verified claim. Unit conversion is allowed (km/h ↔ m/s, m ↔ km, ratio ↔ %), and so is rounding to the written precision ("12" for 11.6, but not "12.0").
  - Minutes, scores (either order) and formations must be in the sets passed in.
