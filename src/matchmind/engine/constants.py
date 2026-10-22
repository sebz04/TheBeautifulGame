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
SHAPE_URGENCY_PER_M = 1 / 25  # off-ball urgency grows with the distance to the target
SHAPE_DEADBAND_M = 3.0  # a player keeps his spot until his shape target moves this far
TRANSITION_S = 5.0  # after a turnover, players far from their spot sprint back into shape
TRANSITION_MIN_M = 6.0
TRANSITION_URGENCY = 0.95
SHAPE_URGENCY = (0.05, 0.75)
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
CLEAR_BONUS = 0.01  # under pressure in the own third, clearing is preferred
SHOT_ERR_DEG = 17.0
SHOT_LOFT_DEG = (2.0, 18.0)
BLOCK_REACH_M = 1.6
BLOCK_PROB = 0.7
SAVE_BASE, SAVE_XG, SAVE_SKILL = 0.86, 0.70, 0.25
CATCH_SPEED_MS = 22.0  # slower shots are usually caught, faster ones parried
CATCH_PROB = (0.75, 0.30)  # below / above CATCH_SPEED_MS
SAVE_LEAD_S = 0.1

# ---- duels ------------------------------------------------------------------------------
TACKLE_RANGE_M = 1.5
TACKLE_RATE_PER_TICK = 0.022
FOUL_SHARE = 0.38
TACKLE_WIN = 0.5  # + 0.3 * (defender skill - carrier skill)
TACKLE_LOOSE_SHARE = 0.5  # won tackles that knock the ball loose rather than keep it
PROTECT_S = 1.0  # after receiving, a carrier cannot be tackled for this long
