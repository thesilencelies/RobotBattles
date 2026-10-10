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

from generate_movement_templates import build_all_movement_templates, map_permutation_to_template

from .automata import compute_automaton_drive, get_automaton_action, roll_d6
from .collision import detect_collision
from .combat import (
    parse_weapon_spin_and_damage,
    refresh_robot_drive_and_power,
    resolve_collision_combat,
    start_of_turn_spin_up,
)
from .field import AUTOMATON_START_POSE, PLAYER_START_POSE
from .movement import generate_trajectory
from .types import (
    CollisionEvent,
    CombatLogEntry,
    ComponentHealth,
    DamageTrainStep,
    MatchState,
    MoveChoice,
    Pose,
    RobotState,
)

_CANONICAL_TEMPLATE_PAIRS = {t.template_id: t.pairs for t in build_all_movement_templates()}


def get_template_metadata(left: int, right: int) -> Dict[str, Any]:
    info = map_permutation_to_template(left, right)
    info["pairs"] = _CANONICAL_TEMPLATE_PAIRS.get(
        info["template_id"],
        [(info["canonical_left"], info["canonical_right"])],
    )
    return info



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
    chassis_template = chassis.get("template", "Square")
    flip_strength = int(chassis.get("flip_strength", 5))

    components: Dict[str, ComponentHealth] = {}

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
            template=str(cdata.get("template", "")),
            spin_counters=0,
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

    # Weapons start at 0 spin counters
    spin_counters: Dict[str, int] = {}
    for cid, comp in components.items():
        if comp.card_type == "weapon":
            spin_counters[cid] = 0

    total_weight = int(chassis.get("weight", 0))
    total_cost = int(chassis.get("cost", 0))
    for c in parsed.get("placed_cards", []):
        cname = c.get("card", "")
        cdata = by_name.get(cname, {})
        total_weight += int(cdata.get("weight", 0))
        total_cost += int(cdata.get("cost", 0))

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
        total_weight=total_weight,
        total_cost=total_cost,
    )

    refresh_robot_drive_and_power(state)
    return state


def create_match(
    player_csv: str,
    automaton_name: str = "Vyper_Spinner",
    player_name: str = "Player 1",
    max_rounds: int = 10,
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

    # Start of Turn (Round 1) Spin Up
    p_spin_logs = start_of_turn_spin_up(player_robot)
    a_spin_logs = start_of_turn_spin_up(auto_robot)

    logs: List[CombatLogEntry] = [
        CombatLogEntry(
            round=1,
            phase="planning",
            message=f"Match initialized: {player_robot.name} vs {auto_robot.name} ({max_rounds} rounds max)",
        )
    ]
    for smsg in p_spin_logs + a_spin_logs:
        logs.append(CombatLogEntry(round=1, phase="planning", message=smsg))

    match = MatchState(
        match_id=str(uuid.uuid4())[:8],
        round=1,
        max_rounds=max_rounds,
        phase="planning",
        player_robot=player_robot,
        automaton_robot=auto_robot,
        automaton_type=automaton_name,
        log=logs,
    )
    return match


def can_robot_uninvert_to_regain_drive(robot: RobotState) -> bool:
    """
    Checks if an inverted robot has a mechanism to uninvert itself
    (an active, non-destroyed component with the Self-right keyword)
    and would regain active drive once uninverted.
    """
    if not robot.is_inverted:
        return False

    has_self_right = any(
        "self-right" in c.keywords.lower() and not c.is_destroyed and c.is_active
        for c in robot.components.values()
    )
    if not has_self_right:
        return False

    orig_inverted = robot.is_inverted
    orig_left = robot.left_drive_max
    orig_right = robot.right_drive_max
    try:
        robot.is_inverted = False
        refresh_robot_drive_and_power(robot)
        return (robot.left_drive_max > 0 or robot.right_drive_max > 0)
    finally:
        robot.is_inverted = orig_inverted
        robot.left_drive_max = orig_left
        robot.right_drive_max = orig_right


def is_robot_defeated(robot: RobotState) -> bool:
    """
    Rule: "A robot is defeated if it has no active drive and no way to uninvert itself to regain drive"
    Also defeated if eliminated (e.g. pushed into hazard pit).
    """
    if robot.is_eliminated:
        return True

    if robot.left_drive_max > 0 or robot.right_drive_max > 0:
        return False

    if can_robot_uninvert_to_regain_drive(robot):
        return False

    return True


def execute_turn(
    match: MatchState,
    player_choice: MoveChoice,
    fixed_automaton_roll: Optional[int] = None,
) -> MatchState:
    """
    Executes a complete 4-phase combat turn:
    1. Planning: Automaton d6 roll & action table lookup -> template drive choice.
    2. Movement: Generate trajectories along templates.
    3. Collision: Check collision & resolve active strikes or inert pushing match.
    4. Cleanup: Self-right check, status reset, win conditions, and advance to next round.
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

    # Refresh active components taking into account movement choices (e.g. drive = 0 frees up power for weapons/other drive)
    refresh_robot_drive_and_power(p_bot, p_choice)
    refresh_robot_drive_and_power(a_bot, a_choice)

    match.log.append(CombatLogEntry(
        round=r_num,
        phase="planning",
        message=(
            f"Planning: {p_bot.name} chooses ({p_choice.left}, {p_choice.right}). "
            f"{a_bot.name} rolls {auto_roll} ({auto_action}) -> chooses ({a_choice.left}, {a_choice.right})."
        ),
    ))

    # Clear damage steps from previous turn
    match.damage_steps = []

    # Movement Template mappings for player and automaton
    match.player_template = get_template_metadata(p_choice.left, p_choice.right)
    match.automaton_template = get_template_metadata(a_choice.left, a_choice.right)

    # 2. Movement Phase
    p_traj = generate_trajectory(p_bot.pose, p_choice)
    a_traj = generate_trajectory(a_bot.pose, a_choice)
    match.player_trajectory = p_traj
    match.automaton_trajectory = a_traj

    # 3. Collision Phase
    col = detect_collision(p_bot, p_traj, a_bot, a_traj)
    match.last_collision = col

    if col:
        # Move both to contact point
        col_idx = max(1, int(col.time_t * len(p_traj)))
        if col_idx < len(p_traj):
            p_bot.pose = Pose(p_traj[col_idx].x, p_traj[col_idx].y, p_traj[col_idx].theta)
        if col_idx < len(a_traj):
            a_bot.pose = Pose(a_traj[col_idx].x, a_traj[col_idx].y, a_traj[col_idx].theta)

        # Resolve combat and record structured damage steps
        c_logs = resolve_collision_combat(col, p_bot, a_bot, r_num, steps=match.damage_steps)
        match.log.extend(c_logs)


    else:
        # Both complete motion to t=1.0
        p_bot.pose = Pose(p_traj[-1].x, p_traj[-1].y, p_traj[-1].theta)
        a_bot.pose = Pose(a_traj[-1].x, a_traj[-1].y, a_traj[-1].theta)
        match.log.append(CombatLogEntry(
            round=r_num, phase="movement", message="Both robots advanced along their template tracks without contact."
        ))

    # 4. Cleanup Phase
    # Self-right check: if round ended without contact and robot is inverted, invert it
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

    # Refresh active drive and power
    refresh_robot_drive_and_power(p_bot)
    refresh_robot_drive_and_power(a_bot)

    # Win Condition Evaluation
    p_defeated = is_robot_defeated(p_bot)
    a_defeated = is_robot_defeated(a_bot)

    if p_bot.is_eliminated and a_bot.is_eliminated:
        match.winner = "draw"
        match.win_reason = "Both robots were eliminated in the hazard pit!"
        match.phase = "game_over"
    elif p_bot.is_eliminated:
        match.winner = "automaton"
        match.win_reason = f"{p_bot.name} was eliminated in the hazard pit!"
        match.phase = "game_over"
    elif a_bot.is_eliminated:
        match.winner = "player"
        match.win_reason = f"{a_bot.name} was eliminated in the hazard pit!"
        match.phase = "game_over"
    elif p_defeated and a_defeated:
        match.winner = "draw"
        match.win_reason = "Both robots are defeated (no active drive and no way to uninvert to regain drive)!"
        match.phase = "game_over"
    elif p_defeated:
        match.winner = "automaton"
        match.win_reason = f"{p_bot.name} is defeated (no active drive and no way to uninvert to regain drive)!"
        match.phase = "game_over"
    elif a_defeated:
        match.winner = "player"
        match.win_reason = f"{a_bot.name} is defeated (no active drive and no way to uninvert to regain drive)!"
        match.phase = "game_over"
    elif match.round >= match.max_rounds:
        match.phase = "game_over"
        p_destroyed = sum(1 for c in p_bot.components.values() if c.is_destroyed)
        p_damaged = sum(1 for c in p_bot.components.values() if c.is_damaged and not c.is_destroyed)
        a_destroyed = sum(1 for c in a_bot.components.values() if c.is_destroyed)
        a_damaged = sum(1 for c in a_bot.components.values() if c.is_damaged and not c.is_destroyed)

        # Fewer destroyed cards wins; if tied, fewer damaged cards wins.
        if (p_destroyed, p_damaged) < (a_destroyed, a_damaged):
            match.winner = "player"
            match.win_reason = (
                f"Judge's Decision: {p_bot.name} took less damage "
                f"({p_destroyed} destroyed, {p_damaged} damaged vs "
                f"{a_destroyed} destroyed, {a_damaged} damaged)!"
            )
        elif (a_destroyed, a_damaged) < (p_destroyed, p_damaged):
            match.winner = "automaton"
            match.win_reason = (
                f"Judge's Decision: {a_bot.name} took less damage "
                f"({a_destroyed} destroyed, {a_damaged} damaged vs "
                f"{p_destroyed} destroyed, {p_damaged} damaged)!"
            )
        else:
            match.winner = "draw"
            match.win_reason = (
                f"Judge's Decision: Exact tie on damage "
                f"({p_destroyed} destroyed, {p_damaged} damaged each)!"
            )
    else:
        # Advance to next round
        match.round += 1
        match.phase = "planning"

        # Start of Next Round: Spin Up keyword
        p_spin = start_of_turn_spin_up(p_bot)
        a_spin = start_of_turn_spin_up(a_bot)
        for smsg in p_spin + a_spin:
            match.log.append(CombatLogEntry(round=match.round, phase="planning", message=smsg))

    if match.phase == "game_over":
        match.log.append(CombatLogEntry(
            round=r_num,
            phase="game_over",
            message=f"🏆 MATCH OVER: Winner is {match.winner.upper()}! ({match.win_reason})",
        ))

    return match
