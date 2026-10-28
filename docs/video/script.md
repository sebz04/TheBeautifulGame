# MatchMind demo video: script and shot list

Target **1:50** (the limit is 2:00). About 200 spoken words (about 90 s at a calm pace), leaving room for the action to breathe. Every line also
works as an on-screen caption if you don't narrate. Slides: `architecture-slide.png` and
`end-card.png` (1920×1080, in this folder).

## Before recording
- Chrome, one window, no other tabs, bookmarks bar hidden (Cmd+Shift+B), zoom 100%, window about 1600×1000. Do Not Disturb on.
- Open the live site in a **private window** (Cmd+Shift+N) so it starts at the welcome page.
- Record each shot as its own clip (Cmd+Shift+5 → Record Selected Portion → the browser window; Options: Show Mouse Clicks). Start a second early, stop a second late.
- Record at 1× and speed up waiting in iMovie, so the cards stay readable.

## Shots

| # | Time | On screen (what you do) | Narration / caption |
|---|---|---|---|
| 1 | 0:00–0:12 | Welcome page; slowly move over the club grid. | "Football is told the same way to everyone. MatchMind is a team of AI agents that watches with you and explains every moment your way." |
| 2 | 0:12–0:20 | Click **Atlético Chapinero** (the page turns purple), then **Start watching**: it opens their match. | "Pick your club, and it all becomes yours: a fictional league, simulated down to every player's movement." |
| 3 | 0:20–0:32 | Click the **Goal, 45+2'** marker on the timeline. It rewinds 5 seconds and plays: Balero scores, then the card **"Chapinero struggles as Balero scores"** arrives. | "Press play, and your pundit explains each key moment as it happens, written for a Chapinero fan." |
| 4 | 0:32–0:42 | Click **Scout**: the same card gains **The numbers** and **What they should do**. Hover over them. | "A fan gets the story. A scout gets the evidence: every number, and what the team should do next." |
| 5 | 0:42–0:50 | Language → **العربية**: the page flips right to left. | "In five languages, each one checked again in its own words." |
| 6 | 0:50–1:05 | Back to English. On a card with **Show best play** (e.g. 36' "We must press harder"), click **Ask why**: the numbers, the cited moments, and the pitch with the real pass (dashed) against the best option (arrow). | "Ask why, and it shows its work: the numbers it rests on, the moments it cites, and the better pass it saw." |
| 7 | 1:05–1:20 | Open **How the agents made it**: "Tactical Analyst agent", "Explainer agent", "Verifier agent", the trace id. | "Five agents on Microsoft Foundry. The Analyst picks the moments, the Explainer writes, and the Verifier recomputes every number in code before a model checks the wording. It caught twenty of twenty planted errors." |
| 8 | 1:20–1:25 | Click **Ask the pundit live**; cut the wait; show the fresh answer and its trace id. | "And it runs live, right now, on demand." |
| 9 | 1:25–1:38 | **architecture-slide.png** (hold it). | "Built on Microsoft Agent Framework and Foundry, with an MCP stats server, Azure Container Apps, Azure SQL, Blob Storage, and Application Insights, deployed by GitHub Actions, with no keys." |
| 10 | 1:38–1:46 | Language → **Español**. Drag to about 89', press **8×**, play to the whistle: the recap **"El hat-trick de Morejo sella la emocionante victoria 3-2 de Chapinero"** takes over. | "At full time, the story of your match, in your language." |
| 11 | 1:46–1:50 | **end-card.png**. | "Every number verified. Try it live." |

## Notes for each shot
- **Shot 3:** if the name tags or speed alerts don't appear in the take, record it again; they appear at fixed moments.
- **Shot 4:** Scout's extra sections are English only, so stay in English for this shot.
- **Shot 6:** Ask why only draws the pitch for cards with a decision ("Show best play" button).
- **Shot 8:** limited to 5 live questions an hour per visitor. If it falls back to the standard summary, use the take where it worked or drop the shot; the trace id in shot 7 still proves the agents ran.
- **Shot 10:** the recap appears only when playback reaches the final whistle, not when you drag to the end.

## Assembling in iMovie
1. New Project → Movie. Drag in the clips in order, then the two PNGs (set each to the time above: right-click → Adjust Duration, or drag the edge).
2. Trim each clip to its time; speed up waits (select → speedometer → Fast).
3. **Narration:** play the timeline and press the microphone button under the viewer, one shot at a time. **Captions:** Titles → "Lower Third", paste the line.
4. Music: Audio & Video → Soundtracks (royalty-free for your projects), volume about 10–15% under the voice.
5. Check the length is under 2:00, then File → Share → File → 1080p.
6. Upload to YouTube as Unlisted or Public; open the link in a private window to check it plays.
