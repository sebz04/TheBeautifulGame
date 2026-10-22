import numpy as np
import pytest

from matchmind.engine.kinematics import (
    A_MAX,
    DECEL_MAX,
    PlayerState,
    max_speed,
    step_player,
    v_max,
)
from matchmind.schemas import Player


def _player(pace: float = 0.5, stamina: float = 0.5) -> Player:
    return Player(player_id="p", name="P", club_id="c", number=9, position="MF", pace=pace,
                  skill=0.5, stamina=stamina)  # fmt: skip


def _run(state: PlayerState, target: tuple[float, float], steps: int, urgency: float = 1.0,
         player: Player | None = None) -> list[PlayerState]:  # fmt: skip
    player = player or _player()
    out = [state]
    for _ in range(steps):
        out.append(step_player(out[-1], np.array(target), urgency, player))
    return out


def _start(x: float = 10.0, y: float = 34.0, energy: float = 1.0) -> PlayerState:
    return PlayerState(pos=np.array([x, y]), vel=np.zeros(2), energy=energy)


def test_v_max_range() -> None:
    assert v_max(0.0) == pytest.approx(8.0) and v_max(1.0) == pytest.approx(10.0)


def test_speed_cap() -> None:
    states = _run(_start(), (100.0, 34.0), 100, player=_player(pace=1.0))
    speeds = [float(np.hypot(*s.vel)) for s in states]
    assert max(speeds) <= v_max(1.0) + 1e-9
    assert max(speeds) > 0.95 * max_speed(_player(pace=1.0), states[-1].energy)  # reaches it


def test_accel_cap() -> None:
    states = _run(_start(), (100.0, 34.0), 30) + _run(
        PlayerState(pos=np.array([50.0, 34.0]), vel=np.array([9.0, 0.0]), energy=1.0),
        (10.0, 34.0), 30,
    )  # fmt: skip
    for a, b in zip(states, states[1:], strict=False):
        dv = float(np.hypot(*(b.vel - a.vel)))
        assert dv <= DECEL_MAX * 0.1 + 1e-9
        if np.hypot(*b.vel) > np.hypot(*a.vel) + 1e-12:
            assert dv <= A_MAX * 0.1 + 1e-9


def test_arrives_and_stops() -> None:
    final = _run(_start(), (30.0, 40.0), 150)[-1]
    assert np.hypot(*(final.pos - np.array([30.0, 40.0]))) < 0.3
    assert np.hypot(*final.vel) < 0.3


def test_urgency_sets_pace() -> None:
    def speed_after(urgency: float) -> float:
        return float(np.hypot(*_run(_start(), (100.0, 34.0), 60, urgency)[-1].vel))

    assert speed_after(1.0) > speed_after(0.5) > speed_after(0.1) > 0


def test_fatigue_reduces_top_speed() -> None:
    p = _player()
    assert max_speed(p, 0.2) < max_speed(p, 1.0)
    tired = _run(_start(energy=0.2), (100.0, 34.0), 80, player=p)
    fresh = _run(_start(energy=1.0), (100.0, 34.0), 80, player=p)
    assert max(np.hypot(*s.vel) for s in tired) < max(np.hypot(*s.vel) for s in fresh)


def test_energy_drains_with_speed_and_stays_bounded() -> None:
    sprint = _run(_start(), (105.0, 34.0), 100)[-1].energy
    walk = _run(_start(), (105.0, 34.0), 100, urgency=0.1)[-1].energy
    assert 0.0 <= sprint < walk <= 1.0
    low_stamina = _run(_start(), (105.0, 34.0), 100, player=_player(stamina=0.1))[-1].energy
    high_stamina = _run(_start(), (105.0, 34.0), 100, player=_player(stamina=0.9))[-1].energy
    assert low_stamina < high_stamina


def test_full_match_energy_is_plausible() -> None:
    """A realistic workload (about 10.6 km, a 4 s sprint every minute) ends tired, not empty;
    better stamina ends fresher."""

    def final_energy(stamina: float) -> tuple[float, float]:
        rng = np.random.default_rng(0)
        state, p = _start(52.5, 34.0), _player(stamina=stamina)
        target, dist = np.array([52.5, 34.0]), 0.0
        for k in range(54000):
            if k % 80 == 0:
                target = np.array([52.5, 34.0]) + rng.uniform(-15, 15, 2)
            new = step_player(state, target, 1.0 if k % 600 < 40 else 0.2, p)
            dist += float(np.hypot(*(new.pos - state.pos)))
            state = new
        return state.energy, dist / 1000

    energy, km = final_energy(0.5)
    assert 9.5 <= km <= 12.0
    assert 0.35 <= energy <= 0.6
    assert final_energy(0.2)[0] < energy < final_energy(0.8)[0]


def test_step_players_matches_step_player() -> None:
    from matchmind.engine.kinematics import step_players

    rng = np.random.default_rng(9)
    n = 22
    players = [_player(pace=float(p), stamina=float(s))
               for p, s in rng.uniform(0, 1, (n, 2))]  # fmt: skip
    pos = rng.uniform([0, 0], [105, 68], (n, 2))
    vel = rng.normal(0, 3, (n, 2))
    vel[3] = 0.0  # standing still
    energy = rng.uniform(0.2, 1.0, n)
    energy[5] = 0.95  # recovering while slow
    targets = rng.uniform([0, 0], [105, 68], (n, 2))
    targets[7] = pos[7]  # already there
    urgency = rng.uniform(0, 1, n)
    drain = rng.uniform(0.94, 1.06, n)
    pace = np.array([p.pace for p in players])
    stamina = np.array([p.stamina for p in players])
    for _ in range(30):
        new_pos, new_vel, new_energy = step_players(pos, vel, energy, targets, urgency, pace,
                                                    stamina, drain)  # fmt: skip
        for i, p in enumerate(players):
            ref = step_player(PlayerState(pos[i], vel[i], float(energy[i])), targets[i],
                              float(urgency[i]), p, drain_mult=float(drain[i]))  # fmt: skip
            assert new_pos[i] == pytest.approx(ref.pos, abs=1e-9)
            assert new_vel[i] == pytest.approx(ref.vel, abs=1e-9)
            assert new_energy[i] == pytest.approx(ref.energy, abs=1e-12)
        pos, vel, energy = new_pos, new_vel, new_energy


def test_drain_multiplier_drains_faster() -> None:
    p = _player()
    fast = PlayerState(np.array([10.0, 34.0]), np.array([7.0, 0.0]), 1.0)
    calm = step_player(fast, np.array([90.0, 34.0]), 1.0, p, drain_mult=0.94)
    keen = step_player(fast, np.array([90.0, 34.0]), 1.0, p, drain_mult=1.06)
    assert keen.energy < calm.energy
