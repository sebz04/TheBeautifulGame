"""Tunable constants of the level-3 engine (`engine/coupled.py`).

Tuning changes numbers here only, never logic. Units: metres, seconds, m/s.
"""

# ---- timing ---------------------------------------------------------------------------
DT = 0.1
HALF_S = 2700.0
PERCEPTION_LAG_TICKS = 3  # decisions see the pitch as it was 0.3 s ago
DECIDE_DELAY_S = (0.8, 2.0)  # from receiving the ball to the next decision
RESTART_DECIDE_S = 0.3
GOAL_PAUSE_S = 45.0
HALF_TIME_RECOVERY = 0.15  # energy regained at half time
PAUSE_S = {  # dead-ball pauses (lo, hi)
    "throw_in": (5.0, 8.0),
    "goal_kick": (8.0, 12.0),
    "corner": (15.0, 22.0),
    "free_kick": (6.0, 12.0),
}

# ---- shape and movement -----------------------------------------------------------------
BLOCK_SHIFT = 0.35  # the block follows the ball's depth
BALL_SIDE_SHIFT = 0.30  # ... and its width
ATTACK_PUSH_M = 6.0
DEFEND_DROP_M = 3.0
ATTACK_WIDTH = 1.1
DEFEND_WIDTH = 0.75
SHAPE_URGENCY_PER_M = 1 / 45  # off-ball urgency grows with the distance to the target
SHAPE_DEADBAND_M = 5.0  # a player keeps his spot until his shape target moves this far
TRANSITION_S = 5.0  # after a turnover, players far from their spot sprint back into shape
TRANSITION_MIN_M = 6.0
TRANSITION_URGENCY = 0.85
SHAPE_URGENCY = (0.05, 0.5)
SUPPORT_URGENCY = 0.7
CHASE_URGENCY = 1.0
DRIBBLE_URGENCY = 0.5
HOLD_URGENCY = 0.15
TAKER_URGENCY = 0.7
DRIBBLE_MAX_MS = 7.0
BALL_AHEAD_M = 0.4  # a dribbled ball sits this far ahead of the carrier
GK_DEPTH_IN_POSSESSION = 12.0

# ---- pressing -------------------------------------------------------------------------
PRESS_BASE_M = 45.0  # press when the ball is within BASE + press_intensity * ZONE of goal
PRESS_ZONE_M = 60.0
PRESS_URGENCY = (0.55, 1.0)  # at press_intensity 0 and 1
CONTAIN_M = 4.0  # not pressing: stand this far goal-side of the ball

# ---- runs in behind -------------------------------------------------------------------
RUN_BALL_DEPTH_M = 40.0  # runners only make runs once the ball is past this depth
RUN_MAX_S = 2.5

# ---- ball control -----------------------------------------------------------------------
CONTROL_RANGE_M = 1.2
CONTROL_HEIGHT_M = 1.8
GK_CONTROL_RANGE_M = 2.0  # keepers in their own box
BOX_DEPTH_M, BOX_HALF_WIDTH_M = 16.5, 20.16
BOX_DEFLECT_SHARE = 0.5  # defenders winning the ball near their goal often just get a touch
DEFLECT_DEPTH_M = 25.0
SAFE_TOUCH_LINE_WEIGHT = 0.8  # how much a safe touch aims at the own goal line
SAFE_TOUCH_SPEED_MS = (8.0, 15.0)
FREE_AFTER_S = 0.6  # after the planned arrival, anyone may collect the ball
INTERCEPT_REACT_S = 0.3
INTERCEPT_SPEED_MS = 6.5
LOFT_MIN_M = 30.0  # passes this long (or longer) are lofted
THROW_SPEED_MS = 12.0
THROW_MAX_M = 30.0
HEAVY_TOUCH_SPEED = (3.0, 6.0)

# ---- passing ----------------------------------------------------------------------------
PASS_ERR_DEG = 3.5  # angle error SD at skill 0.5 = PASS_ERR_DEG
LOFT_LENGTH_ERR = 0.06  # relative distance error of lofted balls
CLEAR_ERR_DEG = 14.0
PC_EXP = 0.55  # completion = pc ** PC_EXP * execution
EXEC_BASE, EXEC_SKILL = 0.90, 0.10

# ---- shooting ---------------------------------------------------------------------------
SHOT_AIM_INSIDE_M = 0.6  # aim this far inside a post, at most
SHOT_COST = 0.03  # a shot must beat keeping the ball by this much xT
SHOT_KEEP_WEIGHT = 0.55  # keeping the ball in a crowded box is worth half its xT
CLEAR_BONUS = 0.01  # under pressure in the own third, clearing is preferred
SHOT_ERR_DEG = 17.0
SHOT_LOFT_DEG = (2.0, 18.0)
BLOCK_REACH_M = 1.6
BLOCK_PROB = 0.5
SAVE_XG, SAVE_SKILL = 3.0, 0.15  # save = 1 - 3 xg (+ keeper skill), about 1 / on-target share
SAVE_RANGE = (0.3, 0.97)
CATCH_SPEED_MS = 22.0  # slower shots are usually caught, faster ones parried
CATCH_PROB = (0.75, 0.30)  # below / above CATCH_SPEED_MS
SAVE_LEAD_S = 0.1

# ---- duels ------------------------------------------------------------------------------
TACKLE_RANGE_M = 1.5
TACKLE_RATE_PER_TICK = 0.026
FOUL_SHARE = 0.45
BOX_FOUL_FACTOR = 0.18  # defenders are careful in their own box
TACKLE_WIN = 0.5  # + 0.3 * (defender skill - carrier skill)
TACKLE_LOOSE_SHARE = 0.5  # won tackles that knock the ball loose rather than keep it
PROTECT_S = 1.0  # after receiving, a carrier cannot be tackled for this long

# ---- level 4: phases (tactics.py) ---------------------------------------------------------
# phase: (depth offset m, depth spread scale, width scale, keeper depth m), applied to the
# formation anchors around SHAPE_PIVOT_M.
SHAPE_PIVOT_M = 46.0
PHASE_SHAPE: dict[str, tuple[float, float, float, float]] = {
    "build_up": (4.0, 1.15, 1.15, 10.0),
    "counter": (12.0, 1.3, 1.0, 12.0),
    "mid_block": (-4.0, 0.8, 0.8, 8.0),
    "low_block": (-16.0, 0.6, 0.7, 4.0),
    "high_press": (10.0, 0.8, 0.85, 16.0),
    "set_piece": (-28.0, 0.3, 0.55, 2.0),  # defending a corner or a free kick near goal
}
COUNTER_S = 6.0  # after winning the ball, the team counters for this long
HIGH_PRESS_DEPTH_M = 70.0  # ball this far from the defending team's goal (and intense press)
HIGH_PRESS_MIN_INTENSITY = 0.55
LOW_BLOCK_DEPTH_M = 35.0
DEEP_TEAM_INTENSITY = 0.35  # teams pressing less than this sit in a low block sooner
DEEP_TEAM_LOW_BLOCK_M = 55.0

# ---- level 4: pressing triggers ---------------------------------------------------------
BACK_PASS_M = 6.0  # a pass losing this much depth is a back pass ...
BACK_PASS_ZONE_M = 40.0  # ... into the passer's last 40 m
ONSIDE_MARGIN_M = 1.0  # players in possession (but the runner) stay this far onside
FACING_OWN_GOAL_MS = 2.5  # a receiver moving toward his own goal this fast faces it
TRIGGER_S = 3.0  # a triggered press lasts this long
TRIGGER_RANGE_M = 10.0  # only a defender this close can jump on the cue
TRIGGER_COVER_URGENCY = 0.9

# ---- level 4: runs in behind ------------------------------------------------------------
RUN_RATE_BASE = 0.7  # runs per minute in possession for a neutral runner and opponent
ROLE_RUN_FACTOR: dict[str, float] = {
    "poacher": 1.35,
    "pressing_forward": 1.2,
    "inside_forward": 1.2,
    "winger": 1.1,
    "shadow_striker": 1.0,
    "false_nine": 0.8,
    "target_man": 0.6,
}
OTHER_ROLE_RUN_FACTOR = 0.7

# ---- level 4: match flow (cards, subs, beats) ---------------------------------------------
DEFAULT_HEIGHT_CM = 182.0  # without profiles
YELLOW_SHARE = 0.20  # of fouls (x the fouler's foul_rate modifier)
RED_SHARE = 0.006
PENDING_RED_TACKLE_MULT = 3.0  # a red-card beat: the team tackles more until it fouls
OFF_PITCH = (-10.0, -10.0)  # parked spot of a sent-off player (left out of frames)
MAX_SUBS = 5
AUTO_SUB_MINUTES = (60.0, 68.0, 76.0, 84.0)  # managers' changes, made at the next stoppage
MOD_UPDATE_S = 300.0  # modifiers follow minute, score, and energy every 5 minutes
STORYLINE_WINDOW_S = 900.0  # a beat's team plays under the storyline cap for 15 minutes
GOAL_BEAT_WINDOW_S = 900.0
GOAL_BEAT_XG_MULT = 4.0  # a goal beat lifts the team's chance quality ...
GOAL_BEAT_SHOT_COST, GOAL_BEAT_KEEP_WEIGHT = 0.0, 0.3  # ... and its appetite to shoot
GOAL_BEAT_AIM, GOAL_BEAT_SAVE = 0.5, 0.4  # sharper finishing, weaker saves in the window
FATIGUE_SPIKE = 0.2

# ---- level 4: set pieces ----------------------------------------------------------------
PENALTY_PAUSE_S = (40.0, 70.0)
PENALTY_SAVE_SHARE = 0.65  # of missed penalties (the rest go wide)
SHORT_CORNER_SHARE = 0.1
DIRECT_FK_SHARE = 0.55  # free kicks in the 17-30 m band struck at goal
CORNER_ATTACKERS = 5
CORNER_SPOTS = ((99.0, 31.0), (98.5, 37.5), (96.0, 34.0), (94.0, 28.5), (93.0, 40.0))
HEADER_REACH_M = 2.0
HEADER_SPEED_MS = 14.0
HEADER_HEIGHT_M = 2.8
PENALTY_SPEED_MS = (21.0, 27.0)
FREE_KICK_LOFT_DEG = (8.0, 14.0)
