# MatchMind visual direction

Spec: `docs/superpowers/specs/2026-10-26-frontend-visual-direction-design.md`. Mockups: `web/mockups/broadcast-dark.html` and `web/mockups/editorial-light.html` (open the files in a browser). Both show the same moment with real precomputed content: Atlético Chapinero 3–2 Atlético Laureles at 84', Morejo's hat-trick, for a Chapinero fan.

## The two directions

| | Broadcast-dark | Editorial-light |
|---|---|---|
| Cards | Near-black `#121216`, like TV graphics | White, like print |
| Pitch | Night pitch `#0F1F17` | Chalk pitch `#E9EFE9` |
| Pundit line | *Big Shoulders Display*, condensed signage letters | *Newsreader* serif, like a match report written for you |
| Data | *Schibsted Grotesk*, tabular figures, scoreboard-size numbers | *Schibsted Grotesk*, club-colored numbers in a ruled table |
| Feel | Loud and live: the score is the headline | Calm and authored: the pundit's sentence is the headline |

Shared in both: the club's primary color is the page field, the switches sit under the score, the pitch is left and the pundit right (layout B), and on a phone the pundit comes first. There are no all-caps labels and no copied branding.

## Accessibility checks (2026-10-26)

- **Contrast** (`node web/scripts/contrast.mjs web/mockups/*.html`): all 16 declared text and background pairs pass AA. The lowest is the away-team text on cards: 6.27 (dark) and 6.23 (light).
- **axe** (Playwright, 1280 px and 375 px): no serious or critical violations. The one moderate finding (no `<main>` landmark) is fixed.
- **No horizontal scrolling** at 375 px.
- **Every club's theme** passes AA on both card colors (`web/tests/theme.test.ts`, 43 tests).

## Choice (2026-10-26)

**Broadcast-dark.** The user preferred it "much better". Tokens in `web/src/design/tokens.css`:
- **Surfaces:** cards `--mm-surface` `#121216` (`clubTheme(club, "dark")`), night pitch `--mm-pitch` `#0F1F17`, rules `--mm-rule` `#26262E`.
- **Type:** *Big Shoulders Display* for the score, minutes, and pundit headline; *Schibsted Grotesk* for everything else; tabular figures.
- **Shape and motion:** square panels (`--mm-radius: 0`), pills only for switches and round buttons; one entrance motion for a new insight (`--mm-dur-slow`, 500 ms) and quick switch transitions (`--mm-dur-fast`, 180 ms), both off with reduced motion.

**Switches (the user's request at the checkpoint):** the view is set by two two-position switches and a language menu:
- **Team ⇄ Player**, labeled with the names (for example *Chapinero ⇄ Morejo*);
- **Fan ⇄ Scout**.

Mapping onto the agents' four voices: Team + Fan → `club_fan` (or pick a side when the club isn't playing; `casual` with no club); Team + Scout → `analyst`; Player (either mode) → `player_focus`, falling back to the Team voice when the player isn't in the match. The agents have one player voice, so Fan ⇄ Scout changes nothing while Player is on.
