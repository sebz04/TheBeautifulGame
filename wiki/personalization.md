# Personalization

**Status:** built (TASK-19.1 templates, TASK-19.3 Personalizer). Insights come from the Explainer ([agents.md](agents.md)); the Verifier ([verifier.md](verifier.md)) checks every text in its own language in the workflow (TASK-20).

## Personalizer (`agents/personalizer.py`, TASK-19.3)
- **`variants_for(insight, meta)`** gives `analyst`, `casual`, `club_fan` for each club, and `player_focus` for every match player the claims are about (`/player:` refs). Other favorite players get the `player_focus` template in the UI.
- **`personalize_batch(insight, lang, variants, client, *, names, minutes=(), scores=())`** makes **one model call per (insight, language)** for every variant (`BatchReply.texts`).
- **Code checks each variant:**
  - **numbers:** only the insight's claims, in the language's format (`check_text` with the match's minutes and scores);
  - **length:** the persona's word limit (`WORD_LIMITS`: analyst 90, casual 45, club_fan and player_focus 60);
  - **jargon:** none for casual (`JARGON`);
  - **names:** a `club_fan` text names its club (any distinctive word: "Laureles", not "Atlético"), and a `player_focus` text names its player.
- **Failures:** failing variants are asked for once more, alone, with their problems (`rejected` in the request). Anything still failing gets its template, with a warning logged that gives the reasons.
- **Agent texts are `verified=False`** until the Verifier checks them in the workflow. Templates are `verified=True`. Arabic texts are `dir="rtl"`.
- **The prompt** states Constitution I and II and gives the persona rules, the number formats per language (decimal comma, Arabic-Indic digits, names kept in Latin script), and 2 examples (es, ar). It runs at temperature 0.
- **Live, 2026-10-25:** the goal insight personalized for 5 variants in each of 5 languages took one call per language (3–5 s).
  - 24 of 25 variants were agent-written.
  - The Arabic analyst wrote "in the last 10 minutes" for a 10-minute metric. That's now allowed: `numbers.WINDOWS` accepts the window length of a cited `*_10min` (10) or `momentum` (5) metric, written with a plural "minutes".

## Fallback templates (`agents/templates.py`, TASK-19.1)
- **`render(insight, variant, lang, names) -> PersonalizedText`** is deterministic. It's what a fan sees when an agent text can't be verified: 4 personas × 5 languages, built from the verified claims alone, with `verified=True`.
- **Numbers** come only from claims, in the language's format: decimal comma for es, pt, and fr; Arabic-Indic digits with `٫` and `٪` for ar; ratios with a `%` unit as percentages.
  - Labels contain **no digits or number words**: "PPDA (last 10 min)" would read as a minute mark.
  - Every combination passes `numbers.check_text` (tested).
- **Per persona:**
  - `analyst`: up to 5 claims, plain label plus the standard name ("recent pressing (passes allowed per defensive action, PPDA)").
  - `casual`: 2 claims, plain labels, no team names, and no jargon (`JARGON`: xT, PPDA, field tilt, pitch control).
  - `club_fan` and `player_focus`: up to 3 claims, that club's or player's first.
  - `WORD_LIMITS`: analyst 90, casual 45, club_fan and player_focus 60.
- `PersonalizedText.dir` is `"rtl"` for Arabic (new field, default `"ltr"`).
- **French typography (TASK-25.2):** "de" elides before a vowel ("supporters d'Atlético Chapinero") and colons take a space before them ("Possession : 53,8 %").
- **No subject (TASK-25.2):** when no claim names a team or player, `casual` and `analyst` use `MATCH_HEADLINES` ("What just happened", "Match analysis") instead of "What just happened: the match".
