# MatchMind frontend: experience and visual direction

**Date:** 2026-10-26 · **For:** TASK-22 (visual direction) and TASK-23 (frontend) · **Status:** agreed in conversation; the TASK-22 checkpoint still picks dark or light.

Sketches from the conversation (wireframes, not styling) are in `.superpowers/brainstorm/` (git-ignored): `layout.html` (option B chosen), `welcome.html`, `best-play-tab.html`.

## Intent

MatchMind is a website where a fan watches a synthetic football match with an AI pundit that explains every key moment **in their own way**: their club, their player, their language, their depth. The personalized AI insight is the heart of the product and of the demo. The players moving on the pitch and the live stats matter a lot, but they support the insight; they never upstage it.

The feeling: **fun and bold, yet sophisticated and mature.** It should look like something a serious football publisher would ship, closer in polish to the Premier League website than to a game or a toy. A judge should see within seconds that the page is about *them* (their club's colors everywhere) and that an AI is talking to *them*.

## Goals

- The personalized insight is the most prominent, most legible thing on the match screen.
- Personalization is visible at a glance: the chosen club's colors take over the whole page.
- Changing club, player, Fan/Scout, or language is instant and always within reach.
- "Best play possible": any decision moment can be opened to compare what the player did with the best option, without stopping the live match.
- Looks sophisticated: confident typography, strict grid, restraint.

## Non-goals

- A full simulated "what would have happened next" after the best play. We show where the best ball would go, how likely it was to work, and how much danger it added (the counterfactual data), not a new match continuation.
- Accounts or sign-in. Preferences live in the browser.
- A mobile app. It's a website that also works on phones.

## Anti-goals (failure even if it works)

- **Dreamlike or surreal** visuals: soft glows, floaty motion, haze, pastel gradients.
- **Toy-like or garish**: club colors so loud that text is hard to read, cartoon styling, decoration for its own sake.
- **Generic dashboard**: a template look where the insight is one small card among many charts.
- **Imitating a real organization**: no Premier League purple, lion, typefaces, logos, or layouts copied as-is; no real club names or crests (the clubs are fictional, Constitution and hackathon rules).

## Constraints

- **Stack (fixed by the project):** React + Vite + TypeScript + Tailwind; Zustand for state; visx for the momentum chart and small stat charts; Vitest, Playwright, axe-core for tests. Nothing else without adding it to the Adopt list in `docs/research/open-source-review.md`.
- **Accessibility (Constitution):** WCAG 2.1 AA contrast, full keyboard use, usable down to 375 px wide. This applies under *every* club's colors, so the theme must compute readable text colors per club, not assume them.
- **Languages:** English, Spanish, Portuguese, French, Arabic (Arabic is right-to-left; `dir="rtl"`).
- **Data:** only the API from TASK-21 (`wiki/api-frontend.md`). Insights, fan texts, and recaps are precomputed and verified, so switching persona or language never waits on a model.
- **Design tool:** the frontend-design plugin guides TASK-22 (direction and tokens) and TASK-23 (components) so the result doesn't read as a template.
- **TASK-22 checkpoint stays:** two mockups of the same match screen, broadcast-dark and editorial-light, both following this document; the user picks one (or a mix), recorded in `docs/design.md` and `tokens.css`.

## Decisions made with the user

### 1. Welcome page (first visit)
A page that introduces MatchMind (an AI pundit that watches with you and explains every key moment your way) and sets up the experience:
- **Pick your club** (the 20 clubs as color tiles).
- **Favorite player** (optional) and **language**.
- **How do you watch: Fan or Scout.**

Choices are saved in the browser; a returning visitor goes straight to the match picker or match.

### 2. Switches always available
On the match screen, the choices sit along the top as switches: **club, player, Fan ⇄ Scout, language**. Changing any of them re-voices the insights instantly; changing club recolors the whole page.

**Fan and Scout map onto the agents' four voices** (the user saw and accepted this mapping in the sketch):
- **Fan** → `club_fan` for the chosen club; `casual` when no club is chosen.
- **A Fan watching a match their club isn't in** (the user's choice): the page asks them to **pick a side for this match**; that side's colors take over and its `club_fan` voice is used. The choice is remembered per match. The match picker always lists the fan's own club's matches first (only 11 of the 20 clubs appear in the 8 demo matches).
- **Scout** → `player_focus` for the chosen player when that player is in the match; otherwise `analyst`.

### 3. Club colors take over the page
The chosen club's **primary color fills the page background**; content sits on white or near-black cards so text stays readable. The **secondary color is for accents** (live dot, the best-play arrow, active switches). Every club's pair is in `GET /api/league` (`primary_color`, `secondary_color`). A neutral theme is used only before a club is chosen (on the welcome page and before picking a side).

### 4. Match screen: layout B, "co-commentator"
Like a TV broadcast with your own pundit beside it:
- **Score and clock** across the top, then the switches.
- **Live pitch** (left, larger) and the **insight panel** (right): the newest personalized insight is big and bold, with earlier ones listed underneath by minute.
- **Stats strip** below (a few key numbers: xG, possession, PPDA, …), and the moment timeline and momentum chart beneath.
- The insight card has the confidence label, an **Ask why** button (claims, cited events, agent trace), and **Show best play** when the moment has a decision.
- **Ask the pundit live** (the user's choice): a button in the Ask why panel calls `POST /api/matches/{id}/regenerate` for that moment in the fan's voice and language. It's the one place the agents visibly work in real time, so it shows progress while they run (about 26 s) and then the fresh insight, its agent runs, and its trace id beside the precomputed one. Over the limit (5 an hour per visitor, 100 a day), it shows a plain message with when to try again (`retry_after`); a timeout (504) or other error says so without breaking the panel.
- The Game / Team / Player tabs from the plan stay (the Player tab compares each stat with the season average).

### 5. Best Plays tab (inside the site)
The live match never pauses. **Show best play** opens a **Best Plays** tab:
- A **live strip** at the top keeps the score and clock running, with one tap back to the live match (the stream keeps playing in the background).
- A **list of best-play moments so far** on the side.
- The main area is a **freeze-frame** at the decision: the pitch-control surface glows where the team controls space; the real pass as a dashed line; the best option as a bold arrow in the club's accent color; a scorecard comparing them (chance it works, danger added); the other options one tap away; and a line from the pundit in the fan's voice.

### 6. Visual language (what "sophisticated" means here)
Drawn from the user's reference (the Premier League website) as inspiration, not imitation:
- **Typography:** large, confident, condensed display type for headlines and numbers; a clean, highly readable body face. Scores and key stats set big, like a scoreboard.
- **Layout:** strict grid, generous space, crisp cards, little decoration; content carries the design.
- **Color:** one strong field color (the club's), neutral cards, a single accent. Bold through scale and contrast, not through many colors.
- **Motion:** quick and purposeful: insight cards slide in, the page recolors when the club changes, the best-play arrow draws itself. Nothing floaty.

## Calls made after the review (Claude's, for the user to check)

- **Dark vs light in TASK-22:** both mockups keep the club color as the page field. *Broadcast-dark* puts content on near-black cards with a dark pitch and lit stats, like a TV graphics package; *editorial-light* uses white cards, more white space, and print-like type. In `tokens.css`, `--mm-bg` is the club field and `--mm-surface` the card color the chosen direction sets.
- **Best play availability:** the insights list gains one small field, the id of the insight's first cited decision event (or null), so the card knows whether to show **Show best play** and the Best Plays list can be built without calling `/why` for every insight. This is a small API addition with its own test and wiki line, made in TASK-23.
- **Playback:** each visitor gets their own replay from kickoff, with play, pause, speed, and seek (plan TASK-23.2). "So far" lists (earlier insights, best-play moments) mean up to the current replay time.
- **Recap and realism:** at the final whistle the full-time recap takes the insight panel. The realism report lives behind an "About this match" link on the match screen (the synthetic data's checks, explained plainly, since a single match passes 22–28 of 30 checks).
- **Scope:** TASK-23 gets two extra subtasks for the welcome page and the Best Plays tab, each with its own tests and commit.

## Left to the builder

- Exact typefaces (open-licensed, e.g. from Google Fonts), the spacing scale, radii, and shadows, within the direction above.
- How the theme derives readable text and card colors from each club's pair (for example, darkening a light primary like `#FFD700` for backgrounds, or switching text to near-black), as long as every club passes AA.
- The neutral theme's palette.
- The exact stats in the stats strip and how many earlier insights are listed.
- Small-screen arrangement (at 375 px the insight panel likely stacks above the pitch, since the insight comes first).
- Transition timings.
