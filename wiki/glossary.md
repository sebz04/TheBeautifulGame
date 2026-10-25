# Glossary

- **xG (expected goals):** how likely a shot is to be scored, from 0 to 1. Not the same as xT.
- **Minute label:** the minute fans read. 55:38 elapsed is `56'`, and stoppage time is `45+2'` or `90+3'` (`clock.minute_label`).
- **xT (expected threat):** how much moving the ball from one zone to another raises the chance of scoring soon. A 16×12 grid of probabilities.
- **Pitch control:** the probability that a team would win the ball if it were played to a given point, based on where every player is and how fast they can get there.
- **PPDA (passes per defensive action):** opponent passes allowed per tackle, interception, or foul in the opponent's part of the pitch. Lower = more intense pressing.
- **Field tilt:** a team's share of passes in the final third. It shows territorial dominance.
- **Momentum:** rolling difference in threat (xT added plus chance quality) between the teams over 5 minutes.
- **Control vs. chaos:** our index from 0 (calm, long possessions) to 1 (frequent turnovers, direct play, volatile control).
- **Counterfactual:** the best alternative pass the player had, scored by the same pitch control × xT model the engine uses.
- **Moment:** a time window flagged by a deterministic rule (momentum swing, pressing collapse, formation shift, big chance, goal, red card).
- **Insight:** an agent's verified explanation of a moment, with cited claims and a confidence label.
- **Fast lane / insight lane:** deterministic overlays (≤ 1 s) vs. verified agent text (≤ 10 s).
- **Barrio:** a city neighborhood in Colombia. Each of our 20 fictional clubs is named after one (e.g. Atlético Chapinero, Bogotá).
- **Clásico / derby:** a match between two clubs from the same city (5 pairs, see `league.md`).
