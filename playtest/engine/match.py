"""Match coordinator: turn sequencing, movement, collision, cleanup, and victory checks."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from builder.server.data import (
    CARD_HEIGHT_MM,
    CARD_WIDTH_MM,
    boxes_touch,
    compute_card_box,
    load_all_cards,
    parse_robot_csv,
    read_saved_robot,
)

from .automata import compute_automaton_drive, get_automaton_action, roll_d6
from .collision import detect_collision
from .combat import (
    parse_weapon_spin_and_damage,
    refresh_robot_drive_and_power,
    resolve_collision_combat,
)
from .field import AUTOMATON_START_POSE, PLAYER_START_POSE
from .movement import generate_trajectory
from .types import (
    CollisionEvent,
    CombatLogEntry,
    ComponentHealth,
    MatchState,
    MoveChoice,
    Pose,
    RobotState,
)


def build_robot_state(
    csv_text: str,
    robot_id: str,
    default_name: str,
    start_pose: Tuple[float, float, float],
    catalog: Optional[Dict[str, Any]] = None,
) -> RobotState:
    """Constructs a live RobotState from a CSV string."""
    if catalog is None:
        catalog = load_all_cards()

    by_name = catalog["by_name"]
    parsed = parse_robot_csv(csv_text)
    chassis = parsed.get("chassis") or {}
    chassis_name = chassis.get("name", "Viper Wedge Chassis")
    chassis_template = chassis.get("template", "Triangle")
    flip_strength = int(chassis.get("flip_strength", 5))

    components: Dict[str, ComponentHealth] = {}
    connections: Dict[str, List[str]] = {}

    for c in parsed.get("placed_cards", []):
        cid = str(c.get("id"))
        cname = c.get("card", "")
        cdata = by_name.get(cname, {})

        x = float(c.get("x", 100.0))
        y = float(c.get("y", 100.0))
        rot = int(c.get("rotation", 0))
        box = compute_card_box(x, y, rot)

        kw = str(cdata.get("keywords", "")).lower()

        dur = int(cdata.get("durability", 5))
        absorb = int(cdata.get("absorption", 0))

        comp = ComponentHealth(
            id=cid,
            name=cname,
            card_type=cdata.get("type", "component"),
            max_durability=dur,
            current_durability=dur,
            absorption=absorb,
            requirements=str(cdata.get("requirements", "")),
            outputs=str(cdata.get("outputs", "")),
            keywords=str(cdata.get("keywords", "")),
            text=str(cdata.get("text", "")),
            x=x,
            y=y,
            rotation=rot,
            box=box,
            is_fragile="fragile" in kw,
            is_wedge="wedge" in kw,
            is_forks="forks" in kw,
            is_invertible="invertible" in kw,
        )
        components[cid] = comp

    # Compute physical connections via touching card boxes
    connections: Dict[str, List[str]] = {cid: [] for cid in components}
    cids = list(components.keys())
    for i in range(len(cids)):
        id_a = cids[i]
        box_a = components[id_a].box
        for j in range(i + 1, len(cids)):
            id_b = cids[j]
            box_b = components[id_b].box
            if boxes_touch(box_a, box_b):
                connections[id_a].append(id_b)
                connections[id_b].append(id_a)

    # Supply graph
    supply_graph: Dict[str, List[str]] = {cid: [] for cid in components}
    reverse_supply: Dict[str, List[str]] = {cid: [] for cid in components}

    for cid, comp in components.items():
        reqs = comp.requirements.upper()
        if not reqs:
            continue
        needed = {ch for ch in ["E", "S", "P", "D", "M"] if ch in reqs}
        for nid in connections.get(cid, []):
            if nid in components:
                nout = components[nid].outputs.upper()
                if any(nt in nout for nt in needed):
                    supply_graph[cid].append(nid)
                    reverse_supply[nid].append(cid)

    # Initial spin counters for weapons
    spin_counters: Dict[str, int] = {}
    for cid, comp in components.items():
        if comp.card_type == "weapon":
            max_s, _, _ = parse_weapon_spin_and_damage(comp.outputs, comp.keywords, comp.text)
            if max_s > 0:
                spin_counters[cid] = 1  # Start with 1 spin counter spun up

    pose = Pose(x=start_pose[0], y=start_pose[1], theta=start_pose[2])

    state = RobotState(
        id=robot_id,
        name=default_name,
        chassis_name=chassis_name,
        chassis_template=chassis_template,
        flip_strength=flip_strength,
        pose=pose,
        components=components,
        connections=connections,
        supply_graph=supply_graph,
        reverse_supply=reverse_supply,
        weapon_spin_counters=spin_counters,
    )

    refresh_robot_drive_and_power(state)
    return state


def create_match(
    player_csv: str,
    automaton_name: str = "Vyper_Spinner",
    player_name: str = "Player 1",
) -> MatchState:
    """Initializes a new match between player robot and chosen automaton."""
    catalog = load_all_cards()

    # Build player
    player_robot = build_robot_state(
        csv_text=player_csv,
        robot_id="player",
        default_name=player_name,
        start_pose=PLAYER_START_POSE,
        catalog=catalog,
    )

    # Load automaton CSV
    auto_csv = read_saved_robot(automaton_name)
    if not auto_csv:
        # Fallback to Vyper_Spinner or Vyper_flipper
        auto_csv = read_saved_robot("Vyper_Spinner.csv") or read_saved_robot("Vyper_flipper.csv")
    if not auto_csv:
        raise ValueError(f"Could not load automaton '{automaton_name}'")

    auto_robot = build_robot_state(
        csv_text=auto_csv,
        robot_id="automaton",
        default_name=automaton_name.replace("_", " "),
        start_pose=AUTOMATON_START_POSE,
        catalog=catalog,
    )

    match = MatchState(
        match_id=str(uuid.uuid4())[:8],
        round=1,
        phase="planning",
        player_robot=player_robot,
        automaton_robot=auto_robot,
        automaton_type=automaton_name,
        log=[
            CombatLogEntry(
                round=1,
                phase="planning",
                message=f"Match initialized: {player_robot.name} vs {auto_robot.name} (10 rounds max)",
            )
        ],
    )
    return match


def execute_turn(
    match: MatchState,
    player_choice: MoveChoice,
    fixed_automaton_roll: Optional[int] = None,
) -> MatchState:
    """
    Executes a complete 4-phase combat turn:
    1. Planning: Rolls automaton action, calculates choices.
    2. Movement: Generates trajectories.
    3. Collision: Detects collisions, resolves damage/feedback/throws.
    4. Cleanup: Checks status, updates spin counters, checks win condition.
    """
    if match.phase == "game_over":
        return match

    r_num = match.round
    p_bot = match.player_robot
    a_bot = match.automaton_robot

    # Clamp player choice to active drive capability
    clamped_l = max(-p_bot.left_drive_max, min(p_bot.left_drive_max, player_choice.left))
    clamped_r = max(-p_bot.right_drive_max, min(p_bot.right_drive_max, player_choice.right))
    p_choice = MoveChoice(left=clamped_l, right=clamped_r)
    match.player_choice = p_choice

    # 1. Automata Planning
    auto_roll = roll_d6(fixed_automaton_roll)
    auto_action = get_automaton_action(match.automaton_type, a_bot, auto_roll)
    a_choice = compute_automaton_drive(a_bot, p_bot, auto_action)
    match.automaton_roll = auto_roll
    match.automaton_action = auto_action
    match.automaton_choice = a_choice

    match.log.append(CombatLogEntry(
        round=r_num,
        phase="planning",
        message=(
            f"Planning: {p_bot.name} chooses ({p_choice.left}, {p_choice.right}). "
            f"{a_bot.name} rolls {auto_roll} ({auto_action}) -> chooses ({a_choice.left}, {a_choice.right})."
        ),
    ))

    # 2. Movement Phase
    p_traj = generate_trajectory(p_bot.pose, p_choice)
    a_traj = generate_trajectory(a_bot.pose, a_choice)
    match.player_trajectory = p_traj
    match.automaton_trajectory = a_traj

    # 3. Collision Check
    col = detect_collision(p_bot, p_traj, a_bot, a_traj)
    match.last_collision = col

    if col:
        # Stop both at collision point
        col_idx = max(1, int(col.time_t * len(p_traj)))
        if col_idx < len(p_traj):
            p_bot.pose = Pose(p_traj[col_idx].x, p_traj[col_idx].y, p_traj[col_idx].theta)
        if col_idx < len(a_traj):
            a_bot.pose = Pose(a_traj[col_idx].x, a_traj[col_idx].y, a_traj[col_idx].theta)

        # Resolve combat
        c_logs = resolve_collision_combat(col, p_bot, a_bot, r_num)
        match.log.extend(c_logs)

    else:
        # Both complete motion to t=1.0
        p_bot.pose = Pose(p_traj[-1].x, p_traj[-1].y, p_traj[-1].theta)
        a_bot.pose = Pose(a_traj[-1].x, a_traj[-1].y, a_traj[-1].theta)
        match.log.append(CombatLogEntry(
            round=r_num, phase="movement", message="Both robots advanced along their paths without contact."
        ))

    # 4. Cleanup Phase
    # Self-righting keyword check if no contact occurred this turn
    if not col:
        for robot in [p_bot, a_bot]:
            if robot.is_inverted:
                has_self_right = any(
                    "self-right" in c.keywords.lower() and not c.is_destroyed
                    for c in robot.components.values()
                )
                if has_self_right:
                    robot.is_inverted = False
                    match.log.append(CombatLogEntry(
                        round=r_num, phase="cleanup", message=f"🔄 {robot.name} self-rights and is now UPRIGHT!"
                    ))

    # Reset raised status at end of round
    p_bot.is_raised = False
    a_bot.is_raised = False

    # Increment spin counters for weapons with Spin up (X, Y)
    for robot in [p_bot, a_bot]:
        for cid, comp in robot.components.items():
            if comp.card_type == "weapon" and not comp.is_destroyed:
                m = re.search(r"Spin up\s*\(\s*(\d+)", comp.keywords, re.IGNORECASE)
                if m:
                    max_spin = int(m.group(1))
                    curr = robot.weapon_spin_counters.get(cid, 0)
                    if curr < max_spin:
                        robot.weapon_spin_counters[cid] = curr + 1

    # Refresh active drive and components
    refresh_robot_drive_and_power(p_bot)
    refresh_robot_drive_and_power(a_bot)

    # Win Condition Evaluation
    p_immobile = (p_bot.left_drive_max == 0 and p_bot.right_drive_max == 0) or p_bot.is_eliminated
    a_immobile = (a_bot.left_drive_max == 0 and a_bot.right_drive_max == 0) or a_bot.is_eliminated

    if p_bot.is_eliminated:
        match.winner = "automaton"
        match.win_reason = f"{p_bot.name} was eliminated in the hazard pit!"
        match.phase = "game_over"
    elif a_bot.is_eliminated:
        match.winner = "player"
        match.win_reason = f"{a_bot.name} was eliminated in the hazard pit!"
        match.phase = "game_over"
    elif p_immobile and a_immobile:
        match.winner = "draw"
        match.win_reason = "Both robots are immobilized!"
        match.phase = "game_over"
    elif p_immobile:
        match.winner = "automaton"
        match.win_reason = f"{p_bot.name} has no active drive remaining!"
        match.phase = "game_over"
    elif a_immobile:
        match.winner = "player"
        match.win_reason = f"{a_bot.name} has no active drive remaining!"
        match.phase = "game_over"
    elif match.round >= 10:
        match.phase = "game_over"
        # Judge's decision: Remaining total durability
        p_dur = sum(c.current_durability for c in p_bot.components.values())
        a_dur = sum(c.current_durability for c in a_bot.components.values())
        if p_dur > a_dur:
            match.winner = "player"
            match.win_reason = f"Judge's Decision: {p_bot.name} has {p_dur} durability remaining vs {a_dur}!"
        elif a_dur > p_dur:
            match.winner = "automaton"
            match.win_reason = f"Judge's Decision: {a_bot.name} has {a_dur} durability remaining vs {p_dur}!"
        else:
            match.winner = "draw"
            match.win_reason = "Judge's Decision: Exact tie on remaining durability!"
    else:
        # Advance to next round
        match.round += 1
        match.phase = "planning"

    if match.phase == "game_over":
        match.log.append(CombatLogEntry(
            round=r_num,
            phase="game_over",
            message=f"🏆 MATCH OVER: Winner is {match.winner.upper()}! ({match.win_reason})",
        ))

    return match
