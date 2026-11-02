"""Match coordinator: turn sequencing, movement, collision, cleanup, and victory checks."""

from __future__ import annotations

import math
import re
import uuid
from typing import Any, Collection, Dict, List, Optional, Tuple

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

from .automata import (
    compute_automaton_action_plan,
    compute_automaton_drive,
    get_automaton_action,
    roll_d6,
)
from .collision import detect_collision
from .combat import (
    parse_weapon_spin_and_damage,
    refresh_robot_drive_and_power,
    resolve_collision_combat,
    resolve_weapon_wall_contact,
    start_of_turn_spin_up,
)
from .field import AUTOMATON_START_POSE, PLAYER_START_POSE
from .movement import (
    CURVE_CONFIGS,
    DRIVE_UNIT_MM,
    MINIATURE_RADIUS,
    WHEELBASE_MM,
    compute_movement_steps,
    generate_action_plan_trajectory,
    generate_trajectory,
    get_action_card,
    normalize_action_code,
    synthesize_cards_from_drive,
    validate_action_plan,
)
from .types import (
    CollisionEvent,
    CombatLogEntry,
    ComponentHealth,
    DamageTrainStep,
    MatchState,
    MoveChoice,
    Pose,
    RobotState,
    TrajectoryPoint,
)

_CANONICAL_TEMPLATE_PAIRS = {t.template_id: t.pairs for t in build_all_movement_templates()}


def get_template_metadata(left: int, right: int) -> Dict[str, Any]:
    info = map_permutation_to_template(left, right)
    t_id = info["template_id"]
    pairs = _CANONICAL_TEMPLATE_PAIRS.get(
        t_id,
        [(info["canonical_left"], info["canonical_right"])],
    )
    info["pairs"] = pairs
    info["wheelbase"] = WHEELBASE_MM
    info["drive_unit"] = DRIVE_UNIT_MM
    info["miniature_radius"] = MINIATURE_RADIUS
    info["steps"] = compute_movement_steps(left, right)
    info["total_steps"] = len(info["steps"])

    if t_id in CURVE_CONFIGS:
        cfg = CURVE_CONFIGS[t_id]
        info["nominal_rc"] = cfg["nominal_rc"]
        info["pair_angles"] = {f"{k[0]},{k[1]}": v for k, v in cfg["pair_angles"].items()}
        pair = (info["canonical_left"], info["canonical_right"])
        info["target_angle_deg"] = cfg["pair_angles"].get(pair, 0.0)

    if info["category"] == "asymmetric_counter":
        c_l, c_r = info["canonical_left"], info["canonical_right"]
        k = -c_r
        rem = c_l - k
        info["spin_k"] = k
        info["spin_deg"] = k * 90.0
        info["pivot_rem"] = rem
        info["pivot_deg"] = rem * 45.0

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
            is_reset="reset" in kw or "crushing claw" in str(cdata.get("name", "")).lower(),
            is_resetting=False,
            reset_supplied=False,
            was_used_this_turn=False,
            is_overhead="overhead" in kw,
            is_trigger="trigger" in kw,
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
    max_rounds: int = 20,
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
    (an active or resetting, non-destroyed component with the Self-right keyword)
    and would regain active drive once uninverted.
    """
    if not robot.is_inverted:
        return False

    has_active_sr = any(
        "self-right" in c.keywords.lower() and not c.is_destroyed and c.is_active
        for c in robot.components.values()
    )
    has_resetting_sr = any(
        "self-right" in c.keywords.lower() and not c.is_destroyed and c.is_reset and c.is_resetting
        for c in robot.components.values()
    )

    if not has_active_sr and not has_resetting_sr:
        return False

    orig_inverted = robot.is_inverted
    orig_left = robot.left_drive_max
    orig_right = robot.right_drive_max
    orig_states = {cid: (c.is_resetting, c.is_active) for cid, c in robot.components.items()}

    try:
        if has_resetting_sr and not has_active_sr:
            # Verify that the resetting self-righting component has an intact supply line
            for c in robot.components.values():
                if c.is_resetting:
                    c.is_resetting = False
            refresh_robot_drive_and_power(robot)
            can_be_powered = any(
                "self-right" in c.keywords.lower() and not c.is_destroyed and c.is_active
                for c in robot.components.values()
            )
            if not can_be_powered:
                return False

        robot.is_inverted = False
        for c in robot.components.values():
            if c.is_resetting:
                c.is_resetting = False
        refresh_robot_drive_and_power(robot)
        return (robot.left_drive_max > 0 or robot.right_drive_max > 0)
    finally:
        robot.is_inverted = orig_inverted
        robot.left_drive_max = orig_left
        robot.right_drive_max = orig_right
        for cid, (was_rst, was_act) in orig_states.items():
            robot.components[cid].is_resetting = was_rst
            robot.components[cid].is_active = was_act


def is_robot_knocked_out(robot: RobotState) -> bool:
    """
    Rule: "A robot is knocked out if it has no active drive and no way to uninvert itself to regain drive
    (a self-righting weapon temporarily inactive due to Reset does not cause the robot to be considered knocked out).
    A robot pushed or thrown into a marked Hazard Wall is also immediately knocked out."
    """
    if robot.is_knocked_out or robot.is_eliminated:
        return True

    if robot.left_drive_max > 0 or robot.right_drive_max > 0:
        return False

    if can_robot_uninvert_to_regain_drive(robot):
        return False

    return True


is_robot_defeated = is_robot_knocked_out


def execute_turn(
    match: MatchState,
    player_choice: MoveChoice,
    fixed_automaton_roll: Optional[int] = None,
    player_supplied_components: Optional[Collection[str]] = None,
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

    # Capture poses at the start of the turn
    p_start = Pose(p_bot.pose.x, p_bot.pose.y, p_bot.pose.theta)
    a_start = Pose(a_bot.pose.x, a_bot.pose.y, a_bot.pose.theta)

    # 1. Action Cards selection & planning
    # Determine Player's 3 Action Cards
    if player_choice.cards and len(player_choice.cards) > 0:
        raw_cards = [normalize_action_code(c) for c in player_choice.cards]
        while len(raw_cards) < 3:
            raw_cards.append("Wait")
        raw_cards = raw_cards[:3]

        eff_l = max(1, p_bot.left_drive_max)
        eff_r = max(1, p_bot.right_drive_max)
        is_valid, _, _, _ = validate_action_plan(raw_cards, eff_l, eff_r)
        if is_valid:
            p_cards = raw_cards
        else:
            cur_l, cur_r = 0, 0
            p_cards = []
            for c in raw_cards:
                meta = get_action_card(c) or {"left": 0, "right": 0}
                if cur_l + meta.get("left", 0) <= eff_l and cur_r + meta.get("right", 0) <= eff_r:
                    p_cards.append(c)
                    cur_l += meta.get("left", 0)
                    cur_r += meta.get("right", 0)
                else:
                    p_cards.append("Wait")
    else:
        # Backward compatibility: synthesize from left, right drive values
        p_cards = synthesize_cards_from_drive(player_choice.left, player_choice.right)

    # 1. Automata Planning
    auto_roll = roll_d6(fixed_automaton_roll)
    auto_action = get_automaton_action(match.automaton_type, a_bot, auto_roll, opponent=p_bot)
    a_choice = compute_automaton_action_plan(a_bot, p_bot, auto_action)
    a_cards = a_choice.cards

    # Build normalized MoveChoice objects
    p_left = sum((get_action_card(c) or {}).get("left", 0) for c in p_cards)
    p_right = sum((get_action_card(c) or {}).get("right", 0) for c in p_cards)
    p_choice = MoveChoice(left=p_left, right=p_right, cards=p_cards)

    match.player_choice = p_choice
    match.player_action_cards = p_cards
    match.automaton_roll = auto_roll
    match.automaton_action = auto_action
    match.automaton_choice = a_choice
    match.automaton_action_cards = a_cards

    # Refresh active components taking into account movement and power choices
    p_bot.current_choice = p_choice
    a_bot.current_choice = a_choice
    refresh_robot_drive_and_power(p_bot, p_choice, chosen_components=player_supplied_components)
    refresh_robot_drive_and_power(a_bot, a_choice, is_automaton=True)

    match.log.append(CombatLogEntry(
        round=r_num,
        phase="planning",
        message=(
            f"Planning: {p_bot.name} chooses [{', '.join(p_cards)}] (Drive L:{p_choice.left}, R:{p_choice.right}). "
            f"{a_bot.name} rolls {auto_roll} ({auto_action}) -> chooses [{', '.join(a_cards)}] (Drive L:{a_choice.left}, R:{a_choice.right})."
        ),
    ))

    # Clear damage steps from previous turn
    match.damage_steps = []

    # Movement Template mappings for player and automaton
    match.player_template = get_template_metadata(p_choice.left, p_choice.right)
    match.automaton_template = get_template_metadata(a_choice.left, a_choice.right)

    # 2. Movement Phase
    # Crushing Claw Grab Effect:
    was_grabbed = (p_bot.grabbed_by == a_bot.id or a_bot.grabbed_by == p_bot.id)
    if p_bot.grabbed_by == a_bot.id:
        p_choice = MoveChoice(0, 0, cards=["Wait", "Wait", "Wait"])
        a_traj = generate_trajectory(a_bot.pose, a_choice)
        dx = p_bot.pose.x - a_start.x
        dy = p_bot.pose.y - a_start.y
        p_traj = [Pose(pt.x + dx, pt.y + dy, p_bot.pose.theta) for pt in a_traj]
        p_bot.grabbed_by = None
        a_claw = next((c for c in a_bot.components.values() if "crushing claw" in c.name.lower()), None)
        if a_claw:
            a_claw.was_used_this_turn = True
        match.log.append(CombatLogEntry(
            round=r_num, phase="movement",
            message=f"🗜️ {p_bot.name} is grabbed by {a_bot.name}'s Crushing Claw: moves with {a_bot.name} and contributes 0 motion!",
        ))
        p_bot.pose = Pose(p_traj[-1].x, p_traj[-1].y, p_traj[-1].theta)
        a_bot.pose = Pose(a_traj[-1].x, a_traj[-1].y, a_traj[-1].theta)
        match.player_trajectory = p_traj
        match.automaton_trajectory = a_traj
        match.last_collision = None
        match.action_step_results = []
    elif a_bot.grabbed_by == p_bot.id:
        a_choice = MoveChoice(0, 0, cards=["Wait", "Wait", "Wait"])
        p_traj = generate_trajectory(p_bot.pose, p_choice)
        dx = a_bot.pose.x - p_start.x
        dy = a_bot.pose.y - p_start.y
        a_traj = [Pose(pt.x + dx, pt.y + dy, a_bot.pose.theta) for pt in p_traj]
        a_bot.grabbed_by = None
        p_claw = next((c for c in p_bot.components.values() if "crushing claw" in c.name.lower()), None)
        if p_claw:
            p_claw.was_used_this_turn = True
        match.log.append(CombatLogEntry(
            round=r_num, phase="movement",
            message=f"🗜️ {a_bot.name} is grabbed by {p_bot.name}'s Crushing Claw: moves with {p_bot.name} and contributes 0 motion!",
        ))
        p_bot.pose = Pose(p_traj[-1].x, p_traj[-1].y, p_traj[-1].theta)
        a_bot.pose = Pose(a_traj[-1].x, a_traj[-1].y, a_traj[-1].theta)
        match.player_trajectory = p_traj
        match.automaton_trajectory = a_traj
        match.last_collision = None
        match.action_step_results = []
    else:
        # Step-by-step simultaneous card resolution (Action 1 -> Action 2 -> Action 3)
        action_step_results: List[Dict[str, Any]] = []
        full_p_traj: List[TrajectoryPoint] = [TrajectoryPoint(p_start.x, p_start.y, p_start.theta, t=0.0)]
        full_a_traj: List[TrajectoryPoint] = [TrajectoryPoint(a_start.x, a_start.y, a_start.theta, t=0.0)]
        collision_halted = False
        collision_event: Optional[CollisionEvent] = None

        for act_idx in range(3):
            p_card = p_cards[act_idx]
            a_card = a_cards[act_idx]

            if collision_halted:
                action_step_results.append({
                    "action_index": act_idx,
                    "player_card": p_card,
                    "automaton_card": a_card,
                    "cancelled": True,
                    "reason": "Halted due to previous collision",
                })
                continue

            # Generate trajectory slice for this action card
            p_sub_traj, _ = generate_action_plan_trajectory(
                p_bot.pose, [p_card], num_substeps=10, clamp_to_walls=True, chassis_template=p_bot.chassis_template
            )
            a_sub_traj, _ = generate_action_plan_trajectory(
                a_bot.pose, [a_card], num_substeps=10, clamp_to_walls=True, chassis_template=a_bot.chassis_template
            )

            # Check collision between the two sub-trajectories
            col = detect_collision(p_bot, p_sub_traj, a_bot, a_sub_traj)

            t_start = act_idx / 3.0
            t_span = 1.0 / 3.0

            if col:
                collision_halted = True
                collision_event = col
                col_idx = col.step_index if col.step_index > 0 else max(1, int(col.time_t * len(p_sub_traj)))
                p_col_idx = min(col_idx, len(p_sub_traj) - 1)
                a_col_idx = min(col_idx, len(a_sub_traj) - 1)

                for k in range(1, p_col_idx + 1):
                    pt = p_sub_traj[k]
                    full_p_traj.append(TrajectoryPoint(pt.x, pt.y, pt.theta, t=t_start + pt.t * t_span))
                for k in range(1, a_col_idx + 1):
                    pt = a_sub_traj[k]
                    full_a_traj.append(TrajectoryPoint(pt.x, pt.y, pt.theta, t=t_start + pt.t * t_span))

                p_bot.pose = Pose(p_sub_traj[p_col_idx].x, p_sub_traj[p_col_idx].y, p_sub_traj[p_col_idx].theta)
                a_bot.pose = Pose(a_sub_traj[a_col_idx].x, a_sub_traj[a_col_idx].y, a_sub_traj[a_col_idx].theta)

                match.log.append(CombatLogEntry(
                    round=r_num,
                    phase="collision",
                    message=f"💥 COLLISION during Action {act_idx + 1} ({p_card} vs {a_card})! Movement halts at point of contact.",
                ))

                # Resolve combat
                c_logs = resolve_collision_combat(col, p_bot, a_bot, r_num, steps=match.damage_steps, r1_choice=p_choice, r2_choice=a_choice)
                match.log.extend(c_logs)

                action_step_results.append({
                    "action_index": act_idx,
                    "player_card": p_card,
                    "automaton_card": a_card,
                    "collision": True,
                    "halted": True,
                })
            else:
                for k in range(1, len(p_sub_traj)):
                    pt = p_sub_traj[k]
                    full_p_traj.append(TrajectoryPoint(pt.x, pt.y, pt.theta, t=t_start + pt.t * t_span))
                for k in range(1, len(a_sub_traj)):
                    pt = a_sub_traj[k]
                    full_a_traj.append(TrajectoryPoint(pt.x, pt.y, pt.theta, t=t_start + pt.t * t_span))

                p_bot.pose = Pose(p_sub_traj[-1].x, p_sub_traj[-1].y, p_sub_traj[-1].theta)
                a_bot.pose = Pose(a_sub_traj[-1].x, a_sub_traj[-1].y, a_sub_traj[-1].theta)

                # Check arena wall contact for active weapons during this step
                w_logs_p = resolve_weapon_wall_contact(p_bot, throw_strength=0, round_num=r_num, phase="movement", steps=match.damage_steps)
                w_logs_a = resolve_weapon_wall_contact(a_bot, throw_strength=0, round_num=r_num, phase="movement", steps=match.damage_steps)
                match.log.extend(w_logs_p)
                match.log.extend(w_logs_a)

                action_step_results.append({
                    "action_index": act_idx,
                    "player_card": p_card,
                    "automaton_card": a_card,
                    "collision": False,
                    "halted": False,
                })

        # Pad trajectories to t=1.0 if ended early
        if full_p_traj[-1].t < 1.0:
            full_p_traj.append(TrajectoryPoint(p_bot.pose.x, p_bot.pose.y, p_bot.pose.theta, t=1.0))
        if full_a_traj[-1].t < 1.0:
            full_a_traj.append(TrajectoryPoint(a_bot.pose.x, a_bot.pose.y, a_bot.pose.theta, t=1.0))

        match.player_trajectory = full_p_traj
        match.automaton_trajectory = full_a_traj
        match.last_collision = collision_event
        match.action_step_results = action_step_results

        if not collision_event:
            match.log.append(CombatLogEntry(
                round=r_num, phase="movement", message="Both robots completed all 3 Action Cards without contact."
            ))

    col = match.last_collision

    # 4. Cleanup Phase
    # Self-right check: if round ended without contact and robot is inverted, invert it
    # Rule: Self-righting requires the component to be active (and non-destroyed)
    if not col:
        for robot in [p_bot, a_bot]:
            if robot.is_inverted:
                sr_comp = next((
                    c for c in robot.components.values()
                    if "self-right" in c.keywords.lower() and not c.is_destroyed and c.is_active
                ), None)
                if sr_comp:
                    robot.is_inverted = False
                    match.log.append(CombatLogEntry(
                        round=r_num, phase="cleanup", message=f"🔄 {robot.name} self-rights with {sr_comp.name} and is now UPRIGHT!"
                    ))
                    # Triggered by self-righting with it!
                    sr_comp.was_used_this_turn = True

    # Process Reset transitions for both robots
    for robot in [p_bot, a_bot]:
        # A. Components that were resetting during this round:
        for cid, c in list(robot.components.items()):
            if c.is_resetting:
                if c.reset_supplied:
                    c.is_resetting = False
                    c.reset_supplied = False
                    if cid in robot.resetting_weapons:
                        robot.resetting_weapons.remove(cid)
                    match.log.append(CombatLogEntry(
                        round=r_num, phase="cleanup",
                        message=f"✅ {robot.name}'s {c.name} received supply and finished resetting!",
                    ))
                else:
                    match.log.append(CombatLogEntry(
                        round=r_num, phase="cleanup",
                        message=f"⚠️ {robot.name}'s {c.name} was not supplied this round and could not reset (remains inactive).",
                    ))

        # B. Components with Reset that were used this round (attacking or self-righting):
        for cid, c in list(robot.components.items()):
            if c.was_used_this_turn:
                c.was_used_this_turn = False
                if c.is_reset and not c.is_resetting:
                    c.is_resetting = True
                    c.reset_supplied = False
                    if cid not in robot.resetting_weapons:
                        robot.resetting_weapons.append(cid)
                    match.log.append(CombatLogEntry(
                        round=r_num, phase="cleanup",
                        message=f"⏳ {robot.name}'s {c.name} was used and is now resetting (inactive next round until supplied).",
                    ))

    # Refresh active drive and power
    refresh_robot_drive_and_power(p_bot, chosen_components=player_supplied_components)
    refresh_robot_drive_and_power(a_bot, is_automaton=True)

    # Win Condition Evaluation
    p_knocked_out = is_robot_knocked_out(p_bot)
    a_knocked_out = is_robot_knocked_out(a_bot)

    if (p_bot.is_knocked_out or p_bot.is_eliminated) and (a_bot.is_knocked_out or a_bot.is_eliminated):
        match.winner = "draw"
        match.win_reason = "Both robots were knocked out in hazard zones or marked hazard walls!"
        match.phase = "game_over"
    elif p_bot.is_knocked_out or p_bot.is_eliminated:
        match.winner = "automaton"
        match.win_reason = f"{p_bot.name} was knocked out in a hazard zone or marked hazard wall!"
        match.phase = "game_over"
    elif a_bot.is_knocked_out or a_bot.is_eliminated:
        match.winner = "player"
        match.win_reason = f"{a_bot.name} was knocked out in a hazard zone or marked hazard wall!"
        match.phase = "game_over"
    elif p_knocked_out and a_knocked_out:
        match.winner = "draw"
        match.win_reason = "Both robots are knocked out (no active drive and no way to uninvert to regain drive)!"
        match.phase = "game_over"
    elif p_knocked_out:
        match.winner = "automaton"
        match.win_reason = f"{p_bot.name} is knocked out (no active drive and no way to uninvert to regain drive)!"
        match.phase = "game_over"
    elif a_knocked_out:
        match.winner = "player"
        match.win_reason = f"{a_bot.name} is knocked out (no active drive and no way to uninvert to regain drive)!"
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

    # Record complete round snapshot for match log export
    round_record = {
        "round": r_num,
        "player_start_pose": {"x": p_start.x, "y": p_start.y, "theta": p_start.theta},
        "automaton_start_pose": {"x": a_start.x, "y": a_start.y, "theta": a_start.theta},
        "player_choice": p_choice.to_dict(),
        "player_action_cards": list(match.player_action_cards),
        "automaton_roll": auto_roll,
        "automaton_action": auto_action,
        "automaton_choice": a_choice.to_dict(),
        "automaton_action_cards": list(match.automaton_action_cards),
        "action_step_results": list(match.action_step_results),
        "player_template": match.player_template,
        "automaton_template": match.automaton_template,
        "collision": col.to_dict() if col else None,
        "damage_steps": [s.to_dict() for s in match.damage_steps],
        "player_end_pose": {"x": p_bot.pose.x, "y": p_bot.pose.y, "theta": p_bot.pose.theta},
        "automaton_end_pose": {"x": a_bot.pose.x, "y": a_bot.pose.y, "theta": a_bot.pose.theta},
        "player_components": {
            cid: {
                "name": c.name,
                "current_durability": c.current_durability,
                "max_durability": c.max_durability,
                "is_damaged": c.is_damaged,
                "is_destroyed": c.is_destroyed,
                "is_active": c.is_active,
                "is_resetting": c.is_resetting,
            }
            for cid, c in p_bot.components.items()
        },
        "automaton_components": {
            cid: {
                "name": c.name,
                "current_durability": c.current_durability,
                "max_durability": c.max_durability,
                "is_damaged": c.is_damaged,
                "is_destroyed": c.is_destroyed,
                "is_active": c.is_active,
                "is_resetting": c.is_resetting,
            }
            for cid, c in a_bot.components.items()
        },
        "logs": [entry.to_dict() for entry in match.log if entry.round == r_num],
    }
    match.round_history.append(round_record)

    return match
