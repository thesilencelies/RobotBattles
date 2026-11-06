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
from .collision import check_robots_in_contact, check_weapon_template_overlap, detect_collision, get_octant
from .combat import (
    ensure_robots_not_overlapping,
    parse_weapon_spin_and_damage,
    refresh_robot_drive_and_power,
    resolve_collision_combat,
    resolve_weapon_wall_contact,
    start_of_turn_spin_up,
)
from .field import AUTOMATON_START_POSE, PLAYER_START_POSE, get_chassis_grid_cells
from .movement import (
    CURVE_CONFIGS,
    DRIVE_UNIT_MM,
    MINIATURE_RADIUS,
    WHEELBASE_MM,
    apply_joint_step,
    apply_movement_step,
    compute_movement_steps,
    generate_action_plan_trajectory,
    generate_push_trajectory,
    generate_trajectory,
    get_action_card,
    get_action_card_steps,
    normalize_action_code,
    snap_pose_to_grid,
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
    if was_grabbed:
        p_is_active = (a_bot.grabbed_by == p_bot.id)
        active_bot = p_bot if p_is_active else a_bot
        passive_bot = a_bot if p_is_active else p_bot
        active_cards = p_cards if p_is_active else a_cards

        # Reset passive bot choices to stationary
        if p_is_active:
            a_choice = MoveChoice(0, 0, cards=["Wait", "Wait", "Wait"])
            a_cards = ["Wait", "Wait", "Wait"]
            p_claw = next((c for c in p_bot.components.values() if "crushing claw" in c.name.lower()), None)
            if p_claw:
                p_claw.was_used_this_turn = True
        else:
            p_choice = MoveChoice(0, 0, cards=["Wait", "Wait", "Wait"])
            p_cards = ["Wait", "Wait", "Wait"]
            a_claw = next((c for c in a_bot.components.values() if "crushing claw" in c.name.lower()), None)
            if a_claw:
                a_claw.was_used_this_turn = True

        match.log.append(CombatLogEntry(
            round=r_num, phase="movement",
            message=f"🗜️ {passive_bot.name} is grabbed by {active_bot.name}'s Crushing Claw: moves with {active_bot.name} and contributes 0 motion!",
        ))

        # Joint step-by-step trajectory generation
        act_pose = active_bot.pose.clone()
        pas_pose = passive_bot.pose.clone()
        full_act_traj: List[TrajectoryPoint] = [TrajectoryPoint(act_pose.x, act_pose.y, act_pose.theta, t=0.0)]
        full_pas_traj: List[TrajectoryPoint] = [TrajectoryPoint(pas_pose.x, pas_pose.y, pas_pose.theta, t=0.0)]
        action_step_results: List[Dict[str, Any]] = []

        for phase_idx in range(6):
            act_card_idx = phase_idx // 2
            is_active_phase = (phase_idx % 2 == 0) if p_is_active else (phase_idx % 2 != 0)
            t_phase_start = phase_idx / 6.0
            t_phase_span = 1.0 / 6.0

            if not is_active_phase:
                # Passive bot's phase: stationary Wait
                action_step_results.append({
                    "phase_index": phase_idx,
                    "action_index": act_card_idx,
                    "robot_id": passive_bot.id,
                    "robot_name": passive_bot.name,
                    "card": "Wait",
                    "player_card": p_cards[act_card_idx],
                    "automaton_card": a_cards[act_card_idx],
                    "collision": False,
                    "cancelled": True,
                    "reason": "Grabbed by Crushing Claw",
                })
                full_act_traj.append(TrajectoryPoint(act_pose.x, act_pose.y, act_pose.theta, t=t_phase_start + t_phase_span))
                full_pas_traj.append(TrajectoryPoint(pas_pose.x, pas_pose.y, pas_pose.theta, t=t_phase_start + t_phase_span))
                continue

            card = active_cards[act_card_idx] if act_card_idx < len(active_cards) else "Wait"
            steps = get_action_card_steps(card, chassis_template=active_bot.chassis_template)

            if not steps:
                action_step_results.append({
                    "phase_index": phase_idx,
                    "action_index": act_card_idx,
                    "robot_id": active_bot.id,
                    "robot_name": active_bot.name,
                    "card": card,
                    "player_card": p_cards[act_card_idx],
                    "automaton_card": a_cards[act_card_idx],
                    "collision": False,
                    "cancelled": False,
                })
                full_act_traj.append(TrajectoryPoint(act_pose.x, act_pose.y, act_pose.theta, t=t_phase_start + t_phase_span))
                full_pas_traj.append(TrajectoryPoint(pas_pose.x, pas_pose.y, pas_pose.theta, t=t_phase_start + t_phase_span))
                continue

            total_substeps = len(steps) * 4
            curr_substep = 0

            for step in steps:
                prev_a = act_pose.clone()
                prev_p = pas_pose.clone()
                next_a, next_p = apply_joint_step(
                    act_pose, pas_pose, step, clamp_to_walls=True,
                    active_chassis=active_bot.chassis_template,
                    passive_chassis=passive_bot.chassis_template,
                )
                act_pose = snap_pose_to_grid(next_a, active_bot.chassis_template)
                pas_pose = snap_pose_to_grid(next_p, passive_bot.chassis_template)

                for s in range(1, 5):
                    curr_substep += 1
                    alpha = s / 4.0
                    frac = curr_substep / float(total_substeps)
                    t_pt = t_phase_start + frac * t_phase_span

                    ix_a = prev_a.x + (act_pose.x - prev_a.x) * alpha
                    iy_a = prev_a.y + (act_pose.y - prev_a.y) * alpha
                    dth_a = (act_pose.theta - prev_a.theta + 180.0) % 360.0 - 180.0
                    ith_a = (prev_a.theta + dth_a * alpha) % 360.0
                    full_act_traj.append(TrajectoryPoint(ix_a, iy_a, ith_a, t=t_pt))

                    ix_p = prev_p.x + (pas_pose.x - prev_p.x) * alpha
                    iy_p = prev_p.y + (pas_pose.y - prev_p.y) * alpha
                    dth_p = (pas_pose.theta - prev_p.theta + 180.0) % 360.0 - 180.0
                    ith_p = (prev_p.theta + dth_p * alpha) % 360.0
                    full_pas_traj.append(TrajectoryPoint(ix_p, iy_p, ith_p, t=t_pt))

            action_step_results.append({
                "phase_index": phase_idx,
                "action_index": act_card_idx,
                "robot_id": active_bot.id,
                "robot_name": active_bot.name,
                "card": card,
                "player_card": p_cards[act_card_idx],
                "automaton_card": a_cards[act_card_idx],
                "collision": False,
                "cancelled": False,
            })

        active_bot.pose = act_pose
        passive_bot.pose = pas_pose
        p_bot.grabbed_by = None
        a_bot.grabbed_by = None

        if p_is_active:
            match.player_trajectory = full_act_traj
            match.automaton_trajectory = full_pas_traj
        else:
            match.player_trajectory = full_pas_traj
            match.automaton_trajectory = full_act_traj

        match.last_collision = None
        match.action_step_results = action_step_results
    else:
        # Alternating Action Card Resolution (6 phases: Card 1 -> Card 2 -> Card 3)
        # Starting with the robot with higher total active drive (ties broken by youngest player / Player 1).
        p_total_drive = p_bot.left_drive_max + p_bot.right_drive_max
        a_total_drive = a_bot.left_drive_max + a_bot.right_drive_max
        player_first = (p_total_drive >= a_total_drive)

        first_bot = p_bot if player_first else a_bot
        second_bot = a_bot if player_first else p_bot
        first_cards = p_cards if player_first else a_cards
        second_cards = a_cards if player_first else p_cards
        first_choice = p_choice if player_first else a_choice
        second_choice = a_choice if player_first else p_choice

        match.log.append(CombatLogEntry(
            round=r_num,
            phase="movement",
            message=f"⚡ Turn Order: {first_bot.name} (Active Drive {p_total_drive if player_first else a_total_drive}) moves first ahead of {second_bot.name} (Active Drive {a_total_drive if player_first else p_total_drive})!",
        ))

        action_step_results: List[Dict[str, Any]] = []
        full_p_traj: List[TrajectoryPoint] = [TrajectoryPoint(p_start.x, p_start.y, p_start.theta, t=0.0)]
        full_a_traj: List[TrajectoryPoint] = [TrajectoryPoint(a_start.x, a_start.y, a_start.theta, t=0.0)]
        turn_collision: Optional[CollisionEvent] = None

        for phase_idx in range(6):
            act_card_idx = phase_idx // 2
            is_first = (phase_idx % 2 == 0)
            moving_bot = first_bot if is_first else second_bot
            stationary_bot = second_bot if is_first else first_bot
            moving_card = first_cards[act_card_idx] if is_first else second_cards[act_card_idx]
            moving_choice = first_choice if is_first else second_choice
            stationary_choice = second_choice if is_first else first_choice

            t_phase_start = phase_idx / 6.0
            t_phase_span = 1.0 / 6.0

            # 1. Elimination / Knockout Check
            if moving_bot.is_knocked_out or moving_bot.is_eliminated:
                action_step_results.append({
                    "phase_index": phase_idx,
                    "action_index": act_card_idx,
                    "robot_id": moving_bot.id,
                    "robot_name": moving_bot.name,
                    "card": moving_card,
                    "player_card": p_cards[act_card_idx],
                    "automaton_card": a_cards[act_card_idx],
                    "collision": False,
                    "cancelled": True,
                    "reason": "Eliminated / Knocked Out",
                })
                full_p_traj.append(TrajectoryPoint(p_bot.pose.x, p_bot.pose.y, p_bot.pose.theta, t=t_phase_start + t_phase_span))
                full_a_traj.append(TrajectoryPoint(a_bot.pose.x, a_bot.pose.y, a_bot.pose.theta, t=t_phase_start + t_phase_span))
                continue

            # 2. Raised Robot Check:
            # Rule: "If a robot ends up raised in a collision, it loses all remaining actions and stays raised until the end of the turn."
            if moving_bot.is_raised:
                match.log.append(CombatLogEntry(
                    round=r_num,
                    phase="movement",
                    message=f"🔱 {moving_bot.name} is RAISED: Action Card {act_card_idx + 1} ({moving_card}) is cancelled! (Stays raised until end of turn)",
                ))
                action_step_results.append({
                    "phase_index": phase_idx,
                    "action_index": act_card_idx,
                    "robot_id": moving_bot.id,
                    "robot_name": moving_bot.name,
                    "card": moving_card,
                    "player_card": p_cards[act_card_idx],
                    "automaton_card": a_cards[act_card_idx],
                    "collision": False,
                    "cancelled": True,
                    "reason": "Robot is raised",
                })
                full_p_traj.append(TrajectoryPoint(p_bot.pose.x, p_bot.pose.y, p_bot.pose.theta, t=t_phase_start + t_phase_span))
                full_a_traj.append(TrajectoryPoint(a_bot.pose.x, a_bot.pose.y, a_bot.pose.theta, t=t_phase_start + t_phase_span))
                continue

            # 3. Step-by-step movement resolution with grid collision check
            steps = get_action_card_steps(moving_card, chassis_template=moving_bot.chassis_template)
            if not steps:
                # Wait / Stop card
                action_step_results.append({
                    "phase_index": phase_idx,
                    "action_index": act_card_idx,
                    "robot_id": moving_bot.id,
                    "robot_name": moving_bot.name,
                    "card": moving_card,
                    "player_card": p_cards[act_card_idx],
                    "automaton_card": a_cards[act_card_idx],
                    "collision": False,
                    "cancelled": False,
                })
                full_p_traj.append(TrajectoryPoint(p_bot.pose.x, p_bot.pose.y, p_bot.pose.theta, t=t_phase_start + t_phase_span))
                full_a_traj.append(TrajectoryPoint(a_bot.pose.x, a_bot.pose.y, a_bot.pose.theta, t=t_phase_start + t_phase_span))
                continue

            phase_m_pts: List[Pose] = []
            phase_s_pts: List[Pose] = []
            phase_collision = False

            for s_idx, step in enumerate(steps):
                prev_m = moving_bot.pose.clone()
                prev_s = stationary_bot.pose.clone()

                cand_m = apply_movement_step(prev_m, step, clamp_to_walls=True, chassis_template=moving_bot.chassis_template)
                cand_m = snap_pose_to_grid(cand_m, moving_bot.chassis_template)

                # Check if moving bot enters any tile currently occupied by the stationary robot
                stat_cells = get_chassis_grid_cells(stationary_bot.chassis_template, stationary_bot.pose)
                cand_cells = get_chassis_grid_cells(moving_bot.chassis_template, cand_m)
                shared_cells = cand_cells & stat_cells

                # Check contact in the overlapping state
                moving_bot.pose = cand_m
                in_contact = (
                    bool(shared_cells)
                    or check_robots_in_contact(moving_bot, stationary_bot)
                    or check_weapon_template_overlap(moving_bot, stationary_bot)
                )

                if in_contact:
                    phase_collision = True
                    # Place robots in overlapping state to detect collision components & contact type
                    col = detect_collision(
                        moving_bot, [TrajectoryPoint(cand_m.x, cand_m.y, cand_m.theta, 0.0)],
                        stationary_bot, [TrajectoryPoint(stationary_bot.pose.x, stationary_bot.pose.y, stationary_bot.pose.theta, 0.0)],
                    )
                    if col is None:
                        sc = list(shared_cells)[0] if shared_cells else (int(cand_m.x / 40.0), int(cand_m.y / 40.0))
                        c_pt = ((sc[0] + 0.5) * 40.0, (sc[1] + 0.5) * 40.0)
                        oct_m = get_octant(cand_m.x, cand_m.y, c_pt[0], c_pt[1], cand_m.theta)
                        oct_s = get_octant(stationary_bot.pose.x, stationary_bot.pose.y, c_pt[0], c_pt[1], stationary_bot.pose.theta)
                        col = CollisionEvent(
                            time_t=t_phase_start + (s_idx / float(len(steps))) * t_phase_span,
                            step_index=s_idx,
                            contact_point=c_pt,
                            robot1_octant=oct_m,
                            robot2_octant=oct_s,
                            robot1_components=[list(moving_bot.components.keys())[0]] if moving_bot.components else [],
                            robot2_components=[list(stationary_bot.components.keys())[0]] if stationary_bot.components else [],
                            contact_type="INERT",
                            description=f"Inert pushing contact: {moving_bot.name} ({oct_m}) vs {stationary_bot.name} ({oct_s})",
                        )

                    col.time_t = t_phase_start + ((s_idx + 0.5) / float(len(steps))) * t_phase_span
                    turn_collision = col

                    match.log.append(CombatLogEntry(
                        round=r_num,
                        phase="collision",
                        message=f"💥 COLLISION during {moving_bot.name}'s Action {act_card_idx + 1} ({moving_card}) with {stationary_bot.name}! {col.description}",
                    ))

                    if col.contact_type == "ACTIVE":
                        # Rule: "If the weapon template overlaps an opposing robot then there is active contact at that point,
                        # and the rest of the movement for that action does not occur."
                        moving_bot.pose = cand_m
                        stationary_bot.pose = prev_s.clone()

                        # Append substeps moving from prev_m to cand_m
                        for sub in range(1, 5):
                            alpha = sub / 4.0
                            ix_m = prev_m.x + (cand_m.x - prev_m.x) * alpha
                            iy_m = prev_m.y + (cand_m.y - prev_m.y) * alpha
                            d_th = (cand_m.theta - prev_m.theta + 180.0) % 360.0 - 180.0
                            ith = (prev_m.theta + d_th * alpha) % 360.0
                            phase_m_pts.append(Pose(ix_m, iy_m, ith))
                            phase_s_pts.append(prev_s.clone())

                        push_trajs: Dict[str, List[TrajectoryPoint]] = {moving_bot.id: [], stationary_bot.id: []}
                        c_logs = resolve_collision_combat(
                            col, moving_bot, stationary_bot, r_num,
                            steps=match.damage_steps,
                            r1_choice=moving_choice, r2_choice=stationary_choice,
                            moving_robot_id=moving_bot.id,
                            moving_rem_steps=None,
                            push_trajectories=push_trajs,
                        )
                        match.log.extend(c_logs)

                        # Record final positions after throw or adjacent pushback
                        phase_m_pts.append(moving_bot.pose.clone())
                        phase_s_pts.append(stationary_bot.pose.clone())

                        # Active contact at that point halts remaining movement for this action card
                        break

                    else:
                        # Inert contact: moving robot pushes stationary robot along remaining steps of current action card
                        moving_bot.pose = prev_m.clone()
                        stationary_bot.pose = prev_s.clone()

                        rem_steps = steps[s_idx:]
                        push_trajs: Dict[str, List[TrajectoryPoint]] = {moving_bot.id: [], stationary_bot.id: []}

                        c_logs = resolve_collision_combat(
                            col, moving_bot, stationary_bot, r_num,
                            steps=match.damage_steps,
                            r1_choice=moving_choice, r2_choice=stationary_choice,
                            moving_robot_id=moving_bot.id,
                            moving_rem_steps=rem_steps,
                            push_trajectories=push_trajs,
                        )
                        match.log.extend(c_logs)

                        # Add push trajectory points to phase trajectory
                        m_pts = push_trajs.get(moving_bot.id, [])
                        s_pts = push_trajs.get(stationary_bot.id, [])
                        if m_pts and s_pts:
                            for mp, sp in zip(m_pts, s_pts):
                                phase_m_pts.append(Pose(mp.x, mp.y, mp.theta))
                                phase_s_pts.append(Pose(sp.x, sp.y, sp.theta))
                        else:
                            phase_m_pts.append(moving_bot.pose.clone())
                            phase_s_pts.append(stationary_bot.pose.clone())

                        # Inert push finishes the motion for this action card
                        break
                else:
                    # No collision: advance moving robot and record substeps
                    moving_bot.pose = cand_m
                    for sub in range(1, 5):
                        alpha = sub / 4.0
                        ix_m = prev_m.x + (cand_m.x - prev_m.x) * alpha
                        iy_m = prev_m.y + (cand_m.y - prev_m.y) * alpha
                        d_th = (cand_m.theta - prev_m.theta + 180.0) % 360.0 - 180.0
                        ith = (prev_m.theta + d_th * alpha) % 360.0
                        phase_m_pts.append(Pose(ix_m, iy_m, ith))
                        phase_s_pts.append(prev_s.clone())

                    # Check arena wall contact for active weapons during this step
                    w_logs = resolve_weapon_wall_contact(
                        moving_bot, throw_strength=0, round_num=r_num,
                        phase="movement", steps=match.damage_steps,
                    )
                    match.log.extend(w_logs)

            action_step_results.append({
                "phase_index": phase_idx,
                "action_index": act_card_idx,
                "robot_id": moving_bot.id,
                "robot_name": moving_bot.name,
                "card": moving_card,
                "player_card": p_cards[act_card_idx],
                "automaton_card": a_cards[act_card_idx],
                "collision": phase_collision,
                "halted": phase_collision,
            })

            # Append phase trajectories with timestamps
            K = len(phase_m_pts)
            if K == 0:
                full_p_traj.append(TrajectoryPoint(p_bot.pose.x, p_bot.pose.y, p_bot.pose.theta, t=t_phase_start + t_phase_span))
                full_a_traj.append(TrajectoryPoint(a_bot.pose.x, a_bot.pose.y, a_bot.pose.theta, t=t_phase_start + t_phase_span))
            else:
                for k_idx in range(K):
                    pt_m = phase_m_pts[k_idx]
                    pt_s = phase_s_pts[k_idx]
                    t_val = t_phase_start + ((k_idx + 1) / float(K)) * t_phase_span
                    if moving_bot.id == p_bot.id:
                        full_p_traj.append(TrajectoryPoint(pt_m.x, pt_m.y, pt_m.theta, t=t_val))
                        full_a_traj.append(TrajectoryPoint(pt_s.x, pt_s.y, pt_s.theta, t=t_val))
                    else:
                        full_a_traj.append(TrajectoryPoint(pt_m.x, pt_m.y, pt_m.theta, t=t_val))
                        full_p_traj.append(TrajectoryPoint(pt_s.x, pt_s.y, pt_s.theta, t=t_val))

        # Pad trajectories to t=1.0 if ended early
        if full_p_traj[-1].t < 1.0:
            full_p_traj.append(TrajectoryPoint(p_bot.pose.x, p_bot.pose.y, p_bot.pose.theta, t=1.0))
        if full_a_traj[-1].t < 1.0:
            full_a_traj.append(TrajectoryPoint(a_bot.pose.x, a_bot.pose.y, a_bot.pose.theta, t=1.0))

        # Guarantee final poses strictly snapped to 40mm grid
        p_bot.pose = snap_pose_to_grid(p_bot.pose, p_bot.chassis_template)
        a_bot.pose = snap_pose_to_grid(a_bot.pose, a_bot.chassis_template)
        ensure_robots_not_overlapping(p_bot, a_bot, r_num, match.log)

        match.player_trajectory = full_p_traj
        match.automaton_trajectory = full_a_traj
        match.last_collision = turn_collision
        match.action_step_results = action_step_results

        if not turn_collision:
            match.log.append(CombatLogEntry(
                round=r_num, phase="movement", message="Both robots completed all 3 Action Cards without contact."
            ))

    col = match.last_collision

    # 4. Cleanup Phase
    # Reset raised status at end of turn
    p_bot.is_raised = False
    a_bot.is_raised = False

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
