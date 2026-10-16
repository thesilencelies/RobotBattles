"""Combat resolution, damage progression, recoil feedback, pushing matches, and throws."""

from __future__ import annotations

import collections
import math
import random
import re
from typing import Any, Collection, Dict, List, Optional, Set, Tuple

from .field import (
    ARENA_HEIGHT,
    ARENA_WIDTH,
    MAT_CENTER_X,
    MAT_CENTER_Y,
    WALL_BOTTOM,
    WALL_LEFT,
    WALL_RIGHT,
    WALL_TOP,
    is_hazard_wall_contact,
    is_in_hazard,
)
from .collision import check_robot_forks_in_line, check_robots_in_contact, get_weapon_wall_contacts
from .movement import DRIVE_UNIT_MM, MINIATURE_RADIUS
from .types import (
    CollisionEvent,
    CombatLogEntry,
    ComponentHealth,
    DamageTrainStep,
    Pose,
    RobotState,
)


def parse_weapon_spin_and_damage(outputs: str, keywords: str, text: str) -> Tuple[int, int, Dict[int, int], str]:
    """
    Parses weapon keywords and outputs into:
    (spin_up_rate, max_spin, {spin_level: damage}, formula_description).
    """
    spin_match = re.search(r"Spin up\s*\(\s*(\d+)(?:\s*,\s*(\d+))?", keywords, re.IGNORECASE)
    if spin_match:
        if spin_match.group(2):
            spin_rate = int(spin_match.group(1))
            max_spin = int(spin_match.group(2))
        else:
            spin_rate = 1
            max_spin = int(spin_match.group(1))
    else:
        spin_rate = 0
        max_spin = 0

    damage_map: Dict[int, int] = {}
    is_pure_throw = "deals no damage" in text.lower() or ("throws" in text.lower() and "no damage" in text.lower())

    formula_desc = outputs
    min_spin = 1 if max_spin > 0 else 0
    spin_levels = list(range(min_spin, max_spin + 1)) if max_spin > 0 else [0]

    for s in spin_levels:
        if is_pure_throw:
            damage_map[s] = 0
            formula_desc = f"{outputs} (Deals 0 weapon damage; Throws only)"
        elif outputs.upper() in ("XXW", "XXXW", "X*XW"):
            damage_map[s] = s ** 2
            formula_desc = "X^2 (XxX * W)"
        elif re.match(r"^(\d*)X(W+)$", outputs):
            m = re.match(r"^(\d*)X(W+)$", outputs)
            k = int(m.group(1)) if m.group(1) else 1
            w_count = len(m.group(2))
            extra_w = w_count - 1
            damage_map[s] = k * s + extra_w
            k_str = f"{k}X" if k > 1 else "X"
            formula_desc = f"{k_str} + {extra_w}" if extra_w > 0 else k_str
        elif re.match(r"^W+$", outputs):
            damage_map[s] = len(outputs)
            formula_desc = f"{len(outputs)} flat ({outputs})"
        elif re.match(r"^(\d+)W$", outputs):
            val = int(re.match(r"^(\d+)W$", outputs).group(1))
            damage_map[s] = val
            formula_desc = f"{val} flat"
        else:
            damage_map[s] = s
            formula_desc = outputs

    return spin_rate, max_spin, damage_map, formula_desc


def get_weapon_attack_strength(comp: ComponentHealth, spin_level: int) -> int:
    """Returns total attack strength (for damage, throw strength, and feedback)."""
    text_lower = comp.text.lower()
    if "deals no damage" in text_lower:
        m = re.search(r"(\d+)W", comp.outputs.upper())
        if m:
            return int(m.group(1))
        w_cnt = comp.outputs.upper().count("W")
        if w_cnt > 0:
            return w_cnt
        return 5

    _, _, d_map, _ = parse_weapon_spin_and_damage(comp.outputs, comp.keywords, comp.text)
    return d_map.get(spin_level, 0)


def apply_damage_to_component(
    comp: ComponentHealth,
    incoming: int,
    is_weapon_damage: bool = True,
) -> Tuple[str, int, int]:
    """
    Applies incoming integer damage according to the canonical rules:
    - All damage numbers are integers; when sharing or dividing, round down.
    - Equal to or greater than durability (ignoring absorption) -> Destroyed, absorbs durability, excess continues.
    - Exceeds 1/2 durability after absorption -> Damaged (or destroyed if already damaged).
    - Otherwise -> absorbs absorption, excess continues.
    Returns (status, absorbed_amount, excess_amount).
    """
    incoming = int(incoming)
    eff_dur = comp.max_durability
    if comp.is_fragile and is_weapon_damage:
        eff_dur = 1

    if incoming >= eff_dur:
        comp.is_destroyed = True
        comp.current_durability = 0
        comp.is_active = False
        absorbed = eff_dur
        excess = max(0, incoming - absorbed)
        return "DESTROYED", absorbed, excess

    half_dur = eff_dur / 2.0
    net_after_abs = max(0, incoming - comp.absorption)

    if incoming >= half_dur:
        if comp.is_damaged:
            comp.is_destroyed = True
            comp.current_durability = 0
            comp.is_active = False
            absorbed = eff_dur
            excess = max(0, incoming - absorbed)
            return "DESTROYED", absorbed, excess
        else:
            comp.is_damaged = True
            comp.current_durability = max(1, eff_dur - net_after_abs)
            absorbed = min(incoming, comp.absorption)
            excess = net_after_abs
            return "DAMAGED", absorbed, excess
    else:
        absorbed = min(incoming, comp.absorption)
        excess = net_after_abs
        return "UNDAMAGED", absorbed, excess


def resolve_inward_damage_progression(
    robot: RobotState,
    initial_target_id: str,
    damage: int,
    is_weapon_damage: bool = True,
    steps: Optional[List[DamageTrainStep]] = None,
) -> List[str]:
    """
    Propagates integer damage from the initial contacted component inwards.
    When sharing damage among connected components, round down.
    """
    logs: List[str] = []
    damage = int(damage)
    if damage <= 0 or initial_target_id not in robot.components:
        return logs

    target = robot.components[initial_target_id]
    status, absorbed, excess = apply_damage_to_component(target, damage, is_weapon_damage)
    msg = f"{target.name} (#{target.id}) takes {damage} dmg -> {status} (absorbed {absorbed}, excess {excess})"
    logs.append(msg)
    if steps is not None:
        steps.append(DamageTrainStep(
            phase="damage",
            robot_id=robot.id,
            target_cid=target.id,
            from_cid=None,
            amount=damage,
            absorbed=absorbed,
            excess=excess,
            new_status=status,
            message=msg,
        ))

    visited: Set[str] = {initial_target_id}
    current_front: List[Tuple[str, int]] = [(initial_target_id, excess)]

    while current_front:
        next_front: List[Tuple[str, int]] = []
        for src_id, rem_dmg in current_front:
            if rem_dmg <= 0:
                continue

            candidates = []
            for nid in robot.connections.get(src_id, []):
                if nid not in visited and nid in robot.components and not robot.components[nid].is_destroyed:
                    ncomp = robot.components[nid]
                    dist = math.hypot(ncomp.x - MAT_CENTER_X, ncomp.y - MAT_CENTER_Y)
                    candidates.append((nid, dist))

            if not candidates:
                continue

            # Prioritize inward path closer to chassis center
            candidates.sort(key=lambda c: c[1])
            split_dmg = rem_dmg // len(candidates)
            if split_dmg <= 0:
                continue

            for nid, _ in candidates:
                visited.add(nid)
                ncomp = robot.components[nid]
                nstatus, nabsorbed, nexcess = apply_damage_to_component(ncomp, split_dmg, is_weapon_damage)
                nmsg = f"{ncomp.name} (#{ncomp.id}) takes {split_dmg} excess dmg -> {nstatus} (absorbed {nabsorbed})"
                logs.append(nmsg)
                if steps is not None:
                    steps.append(DamageTrainStep(
                        phase="damage",
                        robot_id=robot.id,
                        target_cid=ncomp.id,
                        from_cid=src_id,
                        amount=split_dmg,
                        absorbed=nabsorbed,
                        excess=nexcess,
                        new_status=nstatus,
                        message=nmsg,
                    ))
                if nexcess > 0:
                    next_front.append((nid, nexcess))

        current_front = next_front

    return logs


def resolve_feedback_propagation(
    robot: RobotState,
    source_id: str,
    feedback_amount: int,
    phase: str = "recoil_feedback",
    steps: Optional[List[DamageTrainStep]] = None,
) -> List[str]:
    """
    Propagates feedback backwards along the supply graph
    (from weapon/drive back to motors, ESCs, batteries).
    When sharing among suppliers, shared equally (rounding up).
    """
    logs: List[str] = []
    feedback_amount = int(feedback_amount)
    if feedback_amount <= 0 or source_id not in robot.components:
        return logs

    src_comp = robot.components[source_id]
    status, absorbed, excess = apply_damage_to_component(src_comp, feedback_amount, is_weapon_damage=False)
    msg = f"Feedback on {src_comp.name} (#{src_comp.id}): {feedback_amount} -> {status} (absorbed {absorbed})"
    logs.append(msg)
    if steps is not None:
        steps.append(DamageTrainStep(
            phase=phase,
            robot_id=robot.id,
            target_cid=src_comp.id,
            from_cid=None,
            amount=feedback_amount,
            absorbed=absorbed,
            excess=excess,
            new_status=status,
            message=msg,
        ))

    current_layer: List[Tuple[str, int]] = [(source_id, excess)]
    visited = {source_id}

    while current_layer:
        next_layer: List[Tuple[str, int]] = []
        for cid, rem_dmg in current_layer:
            if rem_dmg <= 0:
                continue

            suppliers = [sid for sid in robot.supply_graph.get(cid, []) if sid not in visited and sid in robot.components and not robot.components[sid].is_destroyed]
            if not suppliers:
                continue

            # Rule: shared equally if there are multiple components (rounding up)
            split_dmg = (rem_dmg + len(suppliers) - 1) // len(suppliers)
            if split_dmg <= 0:
                continue

            for sid in suppliers:
                visited.add(sid)
                scomp = robot.components[sid]
                sstatus, sabsorbed, sexcess = apply_damage_to_component(scomp, split_dmg, is_weapon_damage=False)
                smsg = f"Feedback passed to supplier {scomp.name} (#{scomp.id}): {split_dmg} -> {sstatus}"
                logs.append(smsg)
                if steps is not None:
                    steps.append(DamageTrainStep(
                        phase=phase,
                        robot_id=robot.id,
                        target_cid=scomp.id,
                        from_cid=cid,
                        amount=split_dmg,
                        absorbed=sabsorbed,
                        excess=sexcess,
                        new_status=sstatus,
                        message=smsg,
                    ))
                if sexcess > 0:
                    next_layer.append((sid, sexcess))

        current_layer = next_layer

    return logs


def resolve_weapon_wall_contact(
    robot: RobotState,
    throw_strength: int = 0,
    round_num: int = 1,
    phase: str = "collision",
    steps: Optional[List[DamageTrainStep]] = None,
) -> List[CombatLogEntry]:
    """
    Checks if any weapon on the robot contacts an arena wall at its current pose.
    When a weapon contacts a wall:
    - It loses all spin counters.
    - Suffers feedback = (weapon attack strength + throw strength) // 2.
    """
    logs: List[CombatLogEntry] = []
    contacting_cids = get_weapon_wall_contacts(robot, robot.pose)
    for cid in contacting_cids:
        if cid in robot.components:
            w_comp = robot.components[cid]
            spin = robot.weapon_spin_counters.get(cid, 0)
            w_atk = get_weapon_attack_strength(w_comp, spin)
            feedback = (w_atk + throw_strength) // 2

            # Reset spin counters
            robot.weapon_spin_counters[cid] = 0
            w_comp.spin_counters = 0

            logs.append(CombatLogEntry(
                round=round_num, phase=phase,
                message=(
                    f"💥 {robot.name}'s weapon {w_comp.name} contacted the wall! "
                    f"Lost all spin counters (was {spin}) and suffered {feedback} feedback "
                    f"((weapon strength {w_atk} + throw strength {throw_strength}) // 2)."
                ),
            ))
            if feedback > 0:
                fb_logs = resolve_feedback_propagation(
                    robot, cid, feedback, phase="wall_feedback", steps=steps
                )
                for fl in fb_logs:
                    logs.append(CombatLogEntry(round=round_num, phase=phase, message=f"  [Wall Feedback] {fl}"))
    return logs


def simulate_dropping_card(robot: RobotState) -> Optional[str]:
    """
    Simulates randomly dropping a dice onto the A3 chassis sheet
    to determine which component takes throw shock.
    (Rule: 'The component is chosen randomly by dropping a dice onto the robot and seeing which component it lands on.')
    """
    active_comps = [c for c in robot.components.values() if not c.is_destroyed]
    if not active_comps:
        return None

    # Drop dice (standard 16mm x 16mm) at random position on the A3 mat (420 x 297 mm)
    drop_x = random.uniform(80.0, 340.0)
    drop_y = random.uniform(40.0, 260.0)
    dice_w, dice_h = 16.0, 16.0
    drop_box = (drop_x, drop_y, drop_x + dice_w, drop_y + dice_h)

    # Check which placed components overlap the dropped dice
    hit_ids = []
    for comp in active_comps:
        b = comp.box
        overlap = not (
            b[2] < drop_box[0] or
            b[0] > drop_box[2] or
            b[3] < drop_box[1] or
            b[1] > drop_box[3]
        )
        if overlap:
            hit_ids.append(comp.id)

    if hit_ids:
        return random.choice(hit_ids)

    # If dropped dice missed placed components, pick nearest active component
    nearest_cid = min(
        active_comps,
        key=lambda c: math.hypot(
            (c.box[0] + c.box[2]) / 2.0 - drop_x,
            (c.box[1] + c.box[3]) / 2.0 - drop_y
        )
    ).id
    return nearest_cid


simulate_dropping_dice = simulate_dropping_card


def parse_resource_counts(res_str: str) -> Dict[str, int]:
    """
    Parses a requirements or outputs string like 'EE', '6E', 'SSS', '4P', 'DD'
    into resource counts, e.g. {'E': 2}, {'E': 6}, {'S': 3}, {'P': 4}.
    XE or XS represents pass-through capacity (-1).
    """
    counts: Dict[str, int] = {}
    if not res_str:
        return counts
    res_str = res_str.strip().upper()
    tokens = res_str.split() if " " in res_str else [res_str]
    for token in tokens:
        m_num = re.match(r"^(\d+)([ESP])$", token)
        if m_num:
            r = m_num.group(2)
            counts[r] = counts.get(r, 0) + int(m_num.group(1))
            continue
        m_x = re.match(r"^X([ESP])$", token)
        if m_x:
            r = m_x.group(1)
            counts[r] = -1
            continue
        for ch in ["E", "S", "P", "D", "M"]:
            c = token.count(ch)
            if c > 0:
                counts[ch] = counts.get(ch, 0) + c
    return counts


def _get_downstream_endpoints(cid: str, robot: RobotState) -> Set[str]:
    """
    Returns the set of endpoint categories ('left_drive', 'right_drive', 'weapon', 'self_right', 'other')
    reachable downstream from component cid.
    """
    endpoints: Set[str] = set()
    visited: Set[str] = set()
    queue = [cid]
    while queue:
        curr_id = queue.pop(0)
        if curr_id in visited:
            continue
        visited.add(curr_id)
        comp = robot.components.get(curr_id)
        if not comp:
            continue

        if "self-right" in comp.keywords.lower():
            endpoints.add("self_right")

        out = comp.outputs.upper()
        if "D" in out or "M" in out:
            card_cx = (comp.box[0] + comp.box[2]) / 2.0
            if card_cx < MAT_CENTER_X:
                endpoints.add("left_drive")
            else:
                endpoints.add("right_drive")
        if comp.card_type == "weapon" or "W" in out or "spin up" in comp.keywords.lower():
            endpoints.add("weapon")

        # Downstream consumers have curr_id in their supply_graph
        for other_id, c_suppliers in robot.supply_graph.items():
            if curr_id in c_suppliers and other_id not in visited:
                queue.append(other_id)

    if not endpoints:
        endpoints.add("other")
    return endpoints


def _get_downstream_cids(cid: str, robot: RobotState) -> Set[str]:
    """Returns the set of all component IDs reachable downstream from cid in the supply graph."""
    descendants: Set[str] = set()
    queue = [cid]
    while queue:
        curr = queue.pop(0)
        for other_id, c_suppliers in robot.supply_graph.items():
            if curr in c_suppliers and other_id not in descendants:
                descendants.add(other_id)
                queue.append(other_id)
    return descendants


def _edmonds_karp(
    capacities: Dict[Tuple[str, str], int],
    adj: Dict[str, Set[str]],
    source: str,
    sink: str,
) -> Tuple[int, Dict[Tuple[str, str], int]]:
    """
    Edmonds-Karp algorithm for maximum flow in a directed network.
    Returns (total_flow, flow_map).
    """
    flow: Dict[Tuple[str, str], int] = collections.defaultdict(int)
    total_flow = 0

    while True:
        parent: Dict[str, Optional[str]] = {source: None}
        queue = collections.deque([source])
        while queue:
            u = queue.popleft()
            if u == sink:
                break
            for v in adj.get(u, ()):
                residual = capacities.get((u, v), 0) - flow[(u, v)]
                if v not in parent and residual > 0:
                    parent[v] = u
                    queue.append(v)

        if sink not in parent:
            break

        path_flow = 999999999
        curr = sink
        while curr != source:
            prev = parent[curr]
            assert prev is not None
            residual = capacities.get((prev, curr), 0) - flow[(prev, curr)]
            path_flow = min(path_flow, residual)
            curr = prev

        curr = sink
        while curr != source:
            prev = parent[curr]
            assert prev is not None
            flow[(prev, curr)] += path_flow
            flow[(curr, prev)] -= path_flow
            curr = prev

        total_flow += path_flow

    return total_flow, flow


def refresh_robot_drive_and_power(
    robot: RobotState,
    current_move: Optional[MoveChoice] = None,
    chosen_components: Optional[Collection[str]] = None,
    is_automaton: bool = False,
) -> None:
    """
    Recomputes active components and left/right drive max counts based on current health,
    enforcing resource supply and split supply rules:
    - A component is only active if its requirements are supplied by connected components.
    - If multiple components supply multiple components, sum up and distribute available supply across connected components.
    - When supply is insufficient to power all connected components:
      - The player can choose which components get supplied during planning phase each turn.
      - The automaton chooses in order: self-righting if it is inverted, then weapons then drive.
    """
    left_drive_active = current_move is None or current_move.left != 0
    right_drive_active = current_move is None or current_move.right != 0

    # Initialize all components to inactive
    for cid, c in robot.components.items():
        c.is_active = False
        c.reset_supplied = False

    # Pass 1: Identify root components (batteries with no requirements)
    active_set: Set[str] = set()
    avail_supply: Dict[str, Dict[str, int]] = {}  # cid -> {resource: available_amount}

    for cid, c in robot.components.items():
        if not c.is_destroyed:
            reqs = c.requirements.strip().upper()
            if not reqs:
                c.is_active = True
                active_set.add(cid)
                avail_supply[cid] = parse_resource_counts(c.outputs)

    def deduct_supply(sup_id: str, res: str, amt: int, visited: Optional[Set[str]] = None) -> None:
        if visited is None:
            visited = set()
        if sup_id in visited or amt <= 0:
            return
        visited.add(sup_id)
        cur = avail_supply.get(sup_id, {}).get(res, 0)
        if cur == -1:
            # Pass-through node: propagate deduction upstream
            rem = amt
            for usup in robot.supply_graph.get(sup_id, []):
                if usup in active_set and rem > 0:
                    u_cur = avail_supply.get(usup, {}).get(res, 0)
                    if u_cur > 0:
                        take = min(rem, u_cur)
                        deduct_supply(usup, res, take, visited)
                        rem -= take
        elif cur > 0:
            avail_supply[sup_id][res] = max(0, cur - amt)

    # Pass 2: Iteratively propagate and allocate supply along the supply graph
    changed = True
    iterations = 0
    while changed and iterations < 15:
        changed = False
        iterations += 1

        for res_type in ["E", "S", "P", "D", "M"]:
            # 1. Collect active suppliers that provide res_type
            suppliers = [
                sid for sid in active_set
                if avail_supply.get(sid, {}).get(res_type, 0) > 0 or avail_supply.get(sid, {}).get(res_type, 0) == -1
            ]
            if not suppliers:
                continue

            # 2. Collect eligible unpowered consumers requiring res_type connected to these suppliers
            candidate_cids = [
                cid for cid, c in robot.components.items()
                if not c.is_destroyed
                and not c.is_active
                and not (c.is_resetting and c.reset_supplied)
                and (parse_resource_counts(c.requirements).get(res_type, 0) > 0
                     or parse_resource_counts(c.requirements).get(res_type, 0) == -1)
                and any(sid in suppliers for sid in robot.supply_graph.get(cid, []))
            ]
            if not candidate_cids:
                continue

            # 3. Sort candidates according to canonical rules:
            # - Player explicit choice if provided
            # - Automaton (or default fallback): self-righting (if inverted), then weapons, then drive
            # - Within same category, largest requirement first
            # - Stable tie-breaker by cid
            def consumer_sort_key(cid: str):
                c = robot.components[cid]
                endpoints = _get_downstream_endpoints(cid, robot)

                if chosen_components is not None:
                    desc = _get_downstream_cids(cid, robot)
                    is_chosen = (cid in chosen_components) or any(d in chosen_components for d in desc)
                    cat_pri = 0 if is_chosen else 10
                else:
                    is_self_right = "self_right" in endpoints
                    is_weapon = "weapon" in endpoints
                    is_drive = (
                        ("left_drive" in endpoints and left_drive_active) or
                        ("right_drive" in endpoints and right_drive_active)
                    )

                    if robot.is_inverted and is_self_right:
                        cat_pri = 0
                    elif is_weapon:
                        cat_pri = 1
                    elif is_drive:
                        cat_pri = 2
                    else:
                        cat_pri = 3

                req_counts = parse_resource_counts(c.requirements)
                req_val = req_counts.get(res_type, 0)
                if req_val == -1:
                    req_val = 0
                return (cat_pri, -req_val, cid)

            sorted_candidates = sorted(candidate_cids, key=consumer_sort_key)

            # 4. Helper to construct flow network and test feasibility
            def solve_flow_network(test_consumers: List[str]) -> Tuple[bool, int, Dict[Tuple[str, str], int]]:
                SRC = "__SRC__"
                DST = "__DST__"
                capacities: Dict[Tuple[str, str], int] = {}
                adj: Dict[str, Set[str]] = collections.defaultdict(set)

                def add_edge(u: str, v: str, cap: int):
                    if cap > 0:
                        capacities[(u, v)] = cap
                        adj[u].add(v)
                        adj[v].add(u)

                for sid in suppliers:
                    s_cap = avail_supply.get(sid, {}).get(res_type, 0)
                    if s_cap == -1:
                        s_cap = 9999
                    add_edge(SRC, sid, s_cap)

                target = 0
                for cid in test_consumers:
                    c = robot.components[cid]
                    req_val = parse_resource_counts(c.requirements).get(res_type, 0)
                    if req_val == -1:
                        req_val = 0
                    target += req_val
                    if req_val > 0:
                        add_edge(cid, DST, req_val)

                    for sid in robot.supply_graph.get(cid, []):
                        if sid in suppliers:
                            add_edge(sid, cid, 9999)

                if target == 0:
                    return True, 0, {}

                total_flow, flow_map = _edmonds_karp(capacities, adj, SRC, DST)
                return (total_flow == target), total_flow, flow_map

            # 5. Best-effort greedy selection using max-flow feasibility:
            # A component is supplied unless doing so would make a higher-priority component inactive
            selected_consumers: List[str] = []
            for cand in sorted_candidates:
                feasible, _, _ = solve_flow_network(selected_consumers + [cand])
                if feasible:
                    selected_consumers.append(cand)

            if not selected_consumers:
                continue

            # 6. Extract exact flows for the accepted consumer set
            _, _, final_flows = solve_flow_network(selected_consumers)

            # Deduct flows from suppliers
            for sid in suppliers:
                for cid in selected_consumers:
                    f = final_flows.get((sid, cid), 0)
                    if f > 0:
                        deduct_supply(sid, res_type, f)

            # 7. Activate selected components and expose their outputs
            for cid in selected_consumers:
                c = robot.components[cid]
                if c.is_resetting:
                    c.reset_supplied = True
                    c.is_active = False
                    avail_supply[cid] = {}
                else:
                    c.is_active = True
                    active_set.add(cid)
                    out_counts = parse_resource_counts(c.outputs)
                    # Pass-through handling (XE / XS)
                    for r, cnt in out_counts.items():
                        if cnt == -1:
                            req_in = parse_resource_counts(c.requirements).get(r, 0)
                            out_counts[r] = req_in if req_in > 0 else 9999
                    avail_supply[cid] = out_counts
                changed = True

    # Count drive outputs on left and right sides
    left_drive = 0
    right_drive = 0

    for cid, c in robot.components.items():
        # Spin up keyword: if the weapon becomes inactive (or is destroyed), all counters are removed
        is_spin_weapon = (c.card_type == "weapon" or cid in robot.weapon_spin_counters or "spin up" in c.keywords.lower())
        if is_spin_weapon:
            if not c.is_active or c.is_destroyed:
                if cid in robot.weapon_spin_counters:
                    robot.weapon_spin_counters[cid] = 0
                c.spin_counters = 0
            else:
                c.spin_counters = robot.weapon_spin_counters.get(cid, 0)
        else:
            c.spin_counters = robot.weapon_spin_counters.get(cid, 0)

        if not c.is_active or c.is_destroyed:
            continue
        out = c.outputs.upper()
        if "D" in out or "M" in out:
            count = out.count("D") + out.count("M")
            # Inverted check: non-invertible wheels stop functioning
            if robot.is_inverted and not c.is_invertible:
                continue

            card_cx = (c.box[0] + c.box[2]) / 2.0
            if card_cx < MAT_CENTER_X:
                left_drive += count
            else:
                right_drive += count

    robot.left_drive_max = left_drive
    robot.right_drive_max = right_drive


def start_of_turn_spin_up(robot: RobotState) -> List[str]:
    """
    Executes Spin up (X, Y) keyword at the start of turn:
    Add X spin counters up to max Y.
    If the weapon becomes inactive, all counters are removed.
    """
    logs: List[str] = []
    for cid, comp in robot.components.items():
        if comp.card_type != "weapon" or comp.is_destroyed or not comp.is_active:
            if cid in robot.weapon_spin_counters:
                robot.weapon_spin_counters[cid] = 0
            comp.spin_counters = 0
            continue
        spin_rate, max_spin, _, _ = parse_weapon_spin_and_damage(comp.outputs, comp.keywords, comp.text)
        if max_spin > 0:
            curr = robot.weapon_spin_counters.get(cid, 0)
            if curr < max_spin:
                new_val = min(max_spin, curr + spin_rate)
                robot.weapon_spin_counters[cid] = new_val
                comp.spin_counters = new_val
                logs.append(f"🌀 {robot.name}'s {comp.name} spins up (+{spin_rate} -> {new_val}/{max_spin} spin counters)")
    return logs


def separate_robots_full_unit(
    r1: RobotState,
    r2: RobotState,
    round_num: int,
    log_prefix: str = "Inertial separation",
) -> List[CombatLogEntry]:
    """
    Separates two robots that are touching by moving both robots back a full unit
    (DRIVE_UNIT_MM) away from contact, clamped to arena boundaries.
    """
    logs: List[CombatLogEntry] = []
    if check_robots_in_contact(r1, r2):
        d_sep = math.hypot(r2.pose.x - r1.pose.x, r2.pose.y - r1.pose.y)
        if d_sep < 1e-4:
            nx, ny = 1.0, 0.0
        else:
            nx, ny = (r2.pose.x - r1.pose.x) / d_sep, (r2.pose.y - r1.pose.y) / d_sep

        # Move each robot back a full unit away from contact
        overlap = max(0.0, (2.0 * MINIATURE_RADIUS) - d_sep)
        step_mm = overlap / 2.0 + DRIVE_UNIT_MM

        target_r1_x = r1.pose.x - nx * step_mm
        target_r1_y = r1.pose.y - ny * step_mm
        target_r2_x = r2.pose.x + nx * step_mm
        target_r2_y = r2.pose.y + ny * step_mm

        new_r1_x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, target_r1_x))
        new_r1_y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, target_r1_y))
        new_r2_x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, target_r2_x))
        new_r2_y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, target_r2_y))

        actual_step1 = math.hypot(new_r1_x - r1.pose.x, new_r1_y - r1.pose.y)
        actual_step2 = math.hypot(new_r2_x - r2.pose.x, new_r2_y - r2.pose.y)

        r1.pose.x = new_r1_x
        r1.pose.y = new_r1_y
        r2.pose.x = new_r2_x
        r2.pose.y = new_r2_y

        logs.append(CombatLogEntry(
            round=round_num, phase="collision",
            message=f"↔️ {log_prefix}: robots were touching and both moved back a full unit to separate ({r1.name}: {actual_step1:.0f}mm, {r2.name}: {actual_step2:.0f}mm).",
        ))
    return logs


def resolve_inert_contact(
    col: CollisionEvent,
    r1: RobotState,
    r2: RobotState,
    round_num: int,
    steps: Optional[List[DamageTrainStep]] = None,
) -> List[CombatLogEntry]:
    """
    Executes inert contact (pushing match) resolution adhering to combat_robotics_game.tex:
    - Move along templates until contact (already at contact poses).
    - Displace the remainder of robot A's template to the end of robot B's template.
    - Move both robots along the straight line from the initial contact point to the end of A's displaced template.
    - If a robot is raised, its motion does not contribute to the inertial displacement.
    - If a robot hits a wall, throw the robot that hits a wall away from the wall.
    - If the robots are still touching, both robots are moved back a full unit to separate them.
    - Inertial drive feedback is removed.
    """
    logs: List[CombatLogEntry] = []
    logs.append(CombatLogEntry(
        round=round_num,
        phase="collision",
        message=f"🛡️ PUSHING MATCH (Inert Contact): {col.description}",
    ))

    # Calculate remaining motion contribution of each robot
    # Rule: "a raised robot's motion does not contribute in inertial contact"
    if r1.is_raised:
        v1_rem_x, v1_rem_y = 0.0, 0.0
        logs.append(CombatLogEntry(
            round=round_num, phase="collision",
            message=f"⬆️ {r1.name} is RAISED — motion does not contribute to inertial pushing!",
        ))
    elif col.r1_rem_vector != (0.0, 0.0):
        v1_rem_x, v1_rem_y = col.r1_rem_vector
    else:
        v1_rem_x, v1_rem_y = col.push_vector[0] * 0.5, col.push_vector[1] * 0.5

    if r2.is_raised:
        v2_rem_x, v2_rem_y = 0.0, 0.0
        logs.append(CombatLogEntry(
            round=round_num, phase="collision",
            message=f"⬆️ {r2.name} is RAISED — motion does not contribute to inertial pushing!",
        ))
    elif col.r2_rem_vector != (0.0, 0.0):
        v2_rem_x, v2_rem_y = col.r2_rem_vector
    else:
        v2_rem_x, v2_rem_y = col.push_vector[0] * 0.5, col.push_vector[1] * 0.5

    # Net displacement along the straight line from contact to end of displaced template
    push_dx = v1_rem_x + v2_rem_x
    push_dy = v1_rem_y + v2_rem_y
    net_dist = math.hypot(push_dx, push_dy)

    # Displace both robots along the line from initial contact point to end of displaced template
    new_r1_x = r1.pose.x + push_dx
    new_r1_y = r1.pose.y + push_dy
    new_r2_x = r2.pose.x + push_dx
    new_r2_y = r2.pose.y + push_dy

    # Check if either robot is pushed into a wall
    pushed_into_wall_robot = None
    excess_wall_dist = 0.0

    for new_rx, new_ry, robot_obj in [
        (new_r1_x, new_r1_y, r1),
        (new_r2_x, new_r2_y, r2),
    ]:
        clamped_x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, new_rx))
        clamped_y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, new_ry))
        lost_x = abs(new_rx - clamped_x)
        lost_y = abs(new_ry - clamped_y)
        if lost_x > 2.0 or lost_y > 2.0:
            pushed_into_wall_robot = robot_obj
            excess_wall_dist = max(excess_wall_dist, math.hypot(lost_x, lost_y))

    # Displace pair (clamped to walls)
    r1.pose.x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, new_r1_x))
    r1.pose.y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, new_r1_y))
    r2.pose.x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, new_r2_x))
    r2.pose.y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, new_r2_y))

    logs.append(CombatLogEntry(
        round=round_num, phase="collision",
        message=f"Robots push together along displaced template line: displacement {net_dist / DRIVE_UNIT_MM:.1f} units ({net_dist:.0f}mm).",
    ))

    # Wall throw check: If you hit a wall, throw the robot that hits a wall away from the wall
    wall_throw_str = 0
    if pushed_into_wall_robot and excess_wall_dist > 5.0:
        wall_throw_str = int(round(excess_wall_dist / DRIVE_UNIT_MM))
        if wall_throw_str > 0:
            # Check marked Hazard Wall knockout
            if is_hazard_wall_contact(pushed_into_wall_robot.pose.x, pushed_into_wall_robot.pose.y):
                pushed_into_wall_robot.is_knocked_out = True
                pushed_into_wall_robot.is_eliminated = True
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"☠️ {pushed_into_wall_robot.name} was pushed into a marked HAZARD WALL! KNOCKED OUT!",
                ))

            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"💥 {pushed_into_wall_robot.name} was pushed into the wall! THROWN with throw strength {wall_throw_str}! (Takes throw damage {wall_throw_str})",
            ))
            shock_cid = simulate_dropping_card(pushed_into_wall_robot)
            if shock_cid:
                resolve_feedback_propagation(pushed_into_wall_robot, shock_cid, wall_throw_str, phase="wall_feedback", steps=steps)

            # Execute throw away from wall towards arena center
            roll_d6 = random.randint(1, 6)
            thrown_units = min(wall_throw_str, roll_d6)
            displacement_mm = thrown_units * DRIVE_UNIT_MM
            dx = 400.0 - pushed_into_wall_robot.pose.x
            dy = 400.0 - pushed_into_wall_robot.pose.y
            dist = math.hypot(dx, dy)
            if dist < 1e-4:
                dx, dy = 1.0, 0.0
                dist = 1.0
            nx, ny = dx / dist, dy / dist

            pushed_into_wall_robot.pose.x += nx * displacement_mm
            pushed_into_wall_robot.pose.y += ny * displacement_mm
            orientation_roll = random.randint(1, 6)
            spin_rot = orientation_roll * 60.0
            pushed_into_wall_robot.pose.theta = (pushed_into_wall_robot.pose.theta + spin_rot) % 360.0
            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"🧭 Thrown orientation: {pushed_into_wall_robot.name} rolled {orientation_roll} -> rotated {int(spin_rot)}° clockwise (now {pushed_into_wall_robot.pose.theta:.0f}°).",
            ))

            eff_flip = pushed_into_wall_robot.flip_strength // 2 if pushed_into_wall_robot.is_raised else pushed_into_wall_robot.flip_strength
            excess_throw = wall_throw_str - thrown_units
            if excess_throw > eff_flip:
                pushed_into_wall_robot.is_inverted = not pushed_into_wall_robot.is_inverted
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"🔄 FLIP! (Remaining throw {excess_throw} > Flip value {eff_flip}) -> {pushed_into_wall_robot.name} is now {'INVERTED' if pushed_into_wall_robot.is_inverted else 'UPRIGHT'}!",
                ))

    # Weapon wall contact check: when a weapon contacts a wall it loses all spin counters and suffers feedback
    for rob in (r1, r2):
        t_str = wall_throw_str if (rob == pushed_into_wall_robot) else 0
        w_logs = resolve_weapon_wall_contact(rob, throw_strength=t_str, round_num=round_num, phase="collision", steps=steps)
        logs.extend(w_logs)

    # Separation rule: If the robots are still touching, both robots are moved back a full unit to separate them
    sep_logs = separate_robots_full_unit(r1, r2, round_num, log_prefix="Inertial separation")
    logs.extend(sep_logs)

    # Hazard pit / out of arena knockout check
    for robot in (r1, r2):
        if is_in_hazard(robot.pose.x, robot.pose.y):
            robot.is_knocked_out = True
            robot.is_eliminated = True
            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"☠️ {robot.name} fell into the HAZARD PIT during inertial contact! KNOCKED OUT!",
            ))

    return logs


def resolve_collision_combat(
    col: CollisionEvent,
    r1: RobotState,
    r2: RobotState,
    round_num: int,
    steps: Optional[List[DamageTrainStep]] = None,
) -> List[CombatLogEntry]:
    """
    Executes combat resolution adhering strictly to combat_robotics_game.tex.
    """
    logs: List[CombatLogEntry] = []

    # Check Ground Game: Forks keyword (applies to both active and inert contact)
    # Rule: "If any part of the opposing robot is in line with the forks during contact, they become raised for this contact"
    r1_forks_in_line = check_robot_forks_in_line(
        r1, r2, col.contact_point, (r1.pose.x, r1.pose.y, r1.pose.theta), col.robot1_components, opp_pose=r2.pose
    )
    r2_forks_in_line = check_robot_forks_in_line(
        r2, r1, col.contact_point, (r2.pose.x, r2.pose.y, r2.pose.theta), col.robot2_components, opp_pose=r1.pose
    )
    if r1_forks_in_line:
        r2.is_raised = True
        logs.append(CombatLogEntry(
            round=round_num, phase="collision",
            message=f"🔱 {r1.name}'s Forks lift {r2.name}! ({r2.name} is RAISED: flip strength halved, throw strength of attacks reduced by 2, motion does not contribute in inertial contact)",
        ))
    if r2_forks_in_line:
        r1.is_raised = True
        logs.append(CombatLogEntry(
            round=round_num, phase="collision",
            message=f"🔱 {r2.name}'s Forks lift {r1.name}! ({r1.name} is RAISED: flip strength halved, throw strength of attacks reduced by 2, motion does not contribute in inertial contact)",
        ))

    # Check Ground Game: Wedge keyword (applies to both active and inert contact)
    # Rule: "If this component makes contact, the opponent becomes raised for this contact and this component has double absorption against weapon contact (does not work while inverted)"
    r1_wedge_in_contact = any(
        cid in r1.components
        and r1.components[cid].is_wedge
        and not r1.components[cid].is_destroyed
        and (not r1.is_inverted or r1.components[cid].is_invertible)
        for cid in col.robot1_components
    )
    r2_wedge_in_contact = any(
        cid in r2.components
        and r2.components[cid].is_wedge
        and not r2.components[cid].is_destroyed
        and (not r2.is_inverted or r2.components[cid].is_invertible)
        for cid in col.robot2_components
    )
    r1_inverted_wedge_contact = any(
        cid in r1.components
        and r1.components[cid].is_wedge
        and not r1.components[cid].is_destroyed
        and r1.is_inverted and not r1.components[cid].is_invertible
        for cid in col.robot1_components
    )
    r2_inverted_wedge_contact = any(
        cid in r2.components
        and r2.components[cid].is_wedge
        and not r2.components[cid].is_destroyed
        and r2.is_inverted and not r2.components[cid].is_invertible
        for cid in col.robot2_components
    )
    if r1_inverted_wedge_contact:
        logs.append(CombatLogEntry(
            round=round_num, phase="collision",
            message=f"🛡️ {r1.name}'s Wedge made contact, but does not function while INVERTED!",
        ))
    if r2_inverted_wedge_contact:
        logs.append(CombatLogEntry(
            round=round_num, phase="collision",
            message=f"🛡️ {r2.name}'s Wedge made contact, but does not function while INVERTED!",
        ))
    if r1_wedge_in_contact:
        r2.is_raised = True
        logs.append(CombatLogEntry(
            round=round_num, phase="collision",
            message=f"🛡️ {r1.name}'s Wedge makes contact — {r2.name} is RAISED! (flip strength halved, throw strength of attacks reduced by 2, motion does not contribute in inertial contact)",
        ))
    if r2_wedge_in_contact:
        r1.is_raised = True
        logs.append(CombatLogEntry(
            round=round_num, phase="collision",
            message=f"🛡️ {r2.name}'s Wedge makes contact — {r1.name} is RAISED! (flip strength halved, throw strength of attacks reduced by 2, motion does not contribute in inertial contact)",
        ))

    if col.contact_type == "ACTIVE":
        # ======================================================================
        # ACTIVE WEAPON CONTACT
        # ======================================================================
        logs.append(CombatLogEntry(
            round=round_num,
            phase="collision",
            message=f"⚔️ ACTIVE WEAPON HIT: {col.description}",
        ))

        # Identify attacking weapons involved
        w1_attacking = [
            r1.components[cid] for cid in col.robot1_components
            if cid in r1.components and r1.components[cid].card_type == "weapon" and not r1.components[cid].is_destroyed
            and r1.components[cid].is_active
            and col.r1_active_hit
        ]
        w2_attacking = [
            r2.components[cid] for cid in col.robot2_components
            if cid in r2.components and r2.components[cid].card_type == "weapon" and not r2.components[cid].is_destroyed
            and r2.components[cid].is_active
            and col.r2_active_hit
        ]

        atk_str_1 = 0
        w1_comp = None
        if w1_attacking:
            w1_comp = w1_attacking[0]
            spin1 = r1.weapon_spin_counters.get(w1_comp.id, 0)
            atk_str_1 = get_weapon_attack_strength(w1_comp, spin1)

        atk_str_2 = 0
        w2_comp = None
        if w2_attacking:
            w2_comp = w2_attacking[0]
            spin2 = r2.weapon_spin_counters.get(w2_comp.id, 0)
            atk_str_2 = get_weapon_attack_strength(w2_comp, spin2)

        # Total attack strength in the contact
        total_contact_atk = atk_str_1 + atk_str_2

        # 1. Apply Weapon 1 damage to Robot 2
        throw_str_2 = 0
        target2_id = None
        if w1_comp:
            w1_comp.was_used_this_turn = True
            spin1 = r1.weapon_spin_counters.get(w1_comp.id, 0)
            dmg1 = 0 if "deals no damage" in w1_comp.text.lower() else atk_str_1
            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"💥 {r1.name} attacks with {w1_comp.name} at Spin {spin1} dealing {dmg1} dmg (Attack Strength {atk_str_1})!",
            ))

            target2_id = col.robot2_components[0] if col.robot2_components else list(r2.components.keys())[0]
            t2_comp = r2.components.get(target2_id)
            if dmg1 > 0 and t2_comp:
                status, absorbed, excess = apply_damage_to_component(t2_comp, dmg1, is_weapon_damage=True)
                msg = f"{t2_comp.name} (#{t2_comp.id}) takes {dmg1} dmg -> {status} (absorbed {absorbed}, excess {excess})"
                logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Damage] {msg}"))
                if steps is not None:
                    steps.append(DamageTrainStep(
                        phase="damage",
                        robot_id=r2.id,
                        target_cid=t2_comp.id,
                        from_cid=None,
                        amount=dmg1,
                        absorbed=absorbed,
                        excess=excess,
                        new_status=status,
                        message=msg,
                    ))

            # Remove spin counters after attack
            r1.weapon_spin_counters[w1_comp.id] = 0
            w1_comp.spin_counters = 0

            # Base throw strength = attack damage minus absorption of hit component (minimum 0)
            # Rule: If a component is destroyed, it absorbs damage equal to its durability instead of its absorption.
            # Rule: Wedge has double absorption against weapon contact (does not work while inverted).
            is_wedge_2 = False
            if t2_comp:
                if t2_comp.is_destroyed:
                    eff_abs_2 = t2_comp.max_durability
                else:
                    is_wedge_2 = t2_comp.is_wedge and (not r2.is_inverted or t2_comp.is_invertible)
                    if t2_comp.is_wedge and (r2.is_inverted and not t2_comp.is_invertible):
                        logs.append(CombatLogEntry(
                            round=round_num, phase="collision",
                            message=f"🛡️ {r2.name}'s {t2_comp.name} was hit, but does not function while INVERTED!",
                        ))
                    eff_abs_2 = t2_comp.absorption * 2 if is_wedge_2 else t2_comp.absorption
            else:
                eff_abs_2 = 0

            throw_str_2 = max(0, atk_str_1 - eff_abs_2)
            if eff_abs_2 > 0 and atk_str_1 > 0 and t2_comp:
                if is_wedge_2:
                    logs.append(CombatLogEntry(
                        round=round_num, phase="collision",
                        message=f"🛡️ {r2.name}'s Wedge was hit — double absorption ({eff_abs_2} vs attack {atk_str_1}) reduces base throw strength to {throw_str_2}!",
                    ))
                    if throw_str_2 == 0:
                        logs.append(CombatLogEntry(
                            round=round_num, phase="collision",
                            message=f"🛡️ {r2.name}'s Wedge was hit — {r2.name} is not thrown!",
                        ))
                else:
                    logs.append(CombatLogEntry(
                        round=round_num, phase="collision",
                        message=f"  [Absorption] {t2_comp.name} absorbs {eff_abs_2} to reduce base throw strength (was {atk_str_1}, now {throw_str_2}).",
                    ))

            m_throw_1 = re.search(r"increase[s]?\s+throw\s+strength\s+by\s+(\d+)", w1_comp.text, re.IGNORECASE)
            if m_throw_1:
                throw_str_2 += int(m_throw_1.group(1))
            elif "double the throw strength" in w1_comp.text.lower():
                throw_str_2 *= 2
            if r1.is_raised and throw_str_2 > 0:
                throw_str_2 = max(0, throw_str_2 - 2)
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"  [Raised] {r1.name} is raised: throw strength of attack reduced by 2 (now {throw_str_2}).",
                ))
            if "always inverts" in w1_comp.text.lower():
                r2.is_inverted = not r2.is_inverted
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"🔄 {w1_comp.name} always inverts: {r2.name} is now {'INVERTED' if r2.is_inverted else 'UPRIGHT'}!",
                ))

        # 2. Apply Weapon 2 damage to Robot 1
        throw_str_1 = 0
        target1_id = None
        if w2_comp:
            w2_comp.was_used_this_turn = True
            spin2 = r2.weapon_spin_counters.get(w2_comp.id, 0)
            dmg2 = 0 if "deals no damage" in w2_comp.text.lower() else atk_str_2
            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"💥 {r2.name} attacks with {w2_comp.name} at Spin {spin2} dealing {dmg2} dmg (Attack Strength {atk_str_2})!",
            ))

            target1_id = col.robot1_components[0] if col.robot1_components else list(r1.components.keys())[0]
            t1_comp = r1.components.get(target1_id)
            if dmg2 > 0 and t1_comp:
                status, absorbed, excess = apply_damage_to_component(t1_comp, dmg2, is_weapon_damage=True)
                msg = f"{t1_comp.name} (#{t1_comp.id}) takes {dmg2} dmg -> {status} (absorbed {absorbed}, excess {excess})"
                logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Damage] {msg}"))
                if steps is not None:
                    steps.append(DamageTrainStep(
                        phase="damage",
                        robot_id=r1.id,
                        target_cid=t1_comp.id,
                        from_cid=None,
                        amount=dmg2,
                        absorbed=absorbed,
                        excess=excess,
                        new_status=status,
                        message=msg,
                    ))

            r2.weapon_spin_counters[w2_comp.id] = 0
            w2_comp.spin_counters = 0

            # Base throw strength = attack damage minus absorption of hit component (minimum 0)
            # Rule: If a component is destroyed, it absorbs damage equal to its durability instead of its absorption.
            # Rule: Wedge has double absorption against weapon contact (does not work while inverted).
            is_wedge_1 = False
            if t1_comp:
                if t1_comp.is_destroyed:
                    eff_abs_1 = t1_comp.max_durability
                else:
                    is_wedge_1 = t1_comp.is_wedge and (not r1.is_inverted or t1_comp.is_invertible)
                    if t1_comp.is_wedge and (r1.is_inverted and not t1_comp.is_invertible):
                        logs.append(CombatLogEntry(
                            round=round_num, phase="collision",
                            message=f"🛡️ {r1.name}'s {t1_comp.name} was hit, but does not function while INVERTED!",
                        ))
                    eff_abs_1 = t1_comp.absorption * 2 if is_wedge_1 else t1_comp.absorption
            else:
                eff_abs_1 = 0

            throw_str_1 = max(0, atk_str_2 - eff_abs_1)
            if eff_abs_1 > 0 and atk_str_2 > 0 and t1_comp:
                if is_wedge_1:
                    logs.append(CombatLogEntry(
                        round=round_num, phase="collision",
                        message=f"🛡️ {r1.name}'s Wedge was hit — double absorption ({eff_abs_1} vs attack {atk_str_2}) reduces base throw strength to {throw_str_1}!",
                    ))
                    if throw_str_1 == 0:
                        logs.append(CombatLogEntry(
                            round=round_num, phase="collision",
                            message=f"🛡️ {r1.name}'s Wedge was hit — {r1.name} is not thrown!",
                        ))
                else:
                    logs.append(CombatLogEntry(
                        round=round_num, phase="collision",
                        message=f"  [Absorption] {t1_comp.name} absorbs {eff_abs_1} to reduce base throw strength (was {atk_str_2}, now {throw_str_1}).",
                    ))

            m_throw_2 = re.search(r"increase[s]?\s+throw\s+strength\s+by\s+(\d+)", w2_comp.text, re.IGNORECASE)
            if m_throw_2:
                throw_str_1 += int(m_throw_2.group(1))
            elif "double the throw strength" in w2_comp.text.lower():
                throw_str_1 *= 2
            if r2.is_raised and throw_str_1 > 0:
                throw_str_1 = max(0, throw_str_1 - 2)
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"  [Raised] {r2.name} is raised: throw strength of attack reduced by 2 (now {throw_str_1}).",
                ))
            if "always inverts" in w2_comp.text.lower():
                r1.is_inverted = not r1.is_inverted
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"🔄 {w2_comp.name} always inverts: {r1.name} is now {'INVERTED' if r1.is_inverted else 'UPRIGHT'}!",
                ))

        # 3. Weapons receive feedback equal to half the total attack strength in the contact
        if total_contact_atk > 0:
            recoil_fb = total_contact_atk // 2
            if w1_comp and recoil_fb > 0:
                fb_logs = resolve_feedback_propagation(r1, w1_comp.id, recoil_fb, phase="recoil_feedback", steps=steps)
                for fl in fb_logs:
                    logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Recoil Feedback] {fl}"))
            if w2_comp and recoil_fb > 0:
                fb_logs = resolve_feedback_propagation(r2, w2_comp.id, recoil_fb, phase="recoil_feedback", steps=steps)
                for fl in fb_logs:
                    logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Recoil Feedback] {fl}"))

        # 4. Execute Throws away from contact point
        for robot, throw_str, opp in [(r1, throw_str_1, r2), (r2, throw_str_2, r1)]:
            if throw_str <= 0:
                continue

            roll_d6 = random.randint(1, 6)
            thrown_units = min(throw_str, roll_d6)
            displacement_mm = thrown_units * DRIVE_UNIT_MM

            # Vector away from contact point
            dx = robot.pose.x - col.contact_point[0]
            dy = robot.pose.y - col.contact_point[1]
            dist = math.hypot(dx, dy)
            if dist < 1e-4:
                dx, dy = 1.0, 0.0
                dist = 1.0
            nx, ny = dx / dist, dy / dist

            target_x = robot.pose.x + nx * displacement_mm
            target_y = robot.pose.y + ny * displacement_mm

            # Check if throw hits a wall
            hit_wall = (
                target_x <= (WALL_LEFT + 20)
                or target_x >= (WALL_RIGHT - 20)
                or target_y <= (WALL_TOP + 20)
                or target_y >= (WALL_BOTTOM - 20)
            )

            robot.pose.x = max(WALL_LEFT + 20, min(WALL_RIGHT - 20, target_x))
            robot.pose.y = max(WALL_TOP + 20, min(WALL_BOTTOM - 20, target_y))

            # Robot orientation after active contact: decided by throwing a dice and rotating that many 60 degree steps clockwise (only applies to thrown robots)
            orientation_roll = random.randint(1, 6)
            spin_rot = orientation_roll * 60.0
            robot.pose.theta = (robot.pose.theta + spin_rot) % 360.0

            # Throw damage rule: always equal to throw strength
            throw_dmg = throw_str

            if hit_wall:
                # Check marked Hazard Wall knockout
                if is_hazard_wall_contact(robot.pose.x, robot.pose.y):
                    robot.is_knocked_out = True
                    robot.is_eliminated = True
                    logs.append(CombatLogEntry(
                        round=round_num, phase="collision",
                        message=f"☠️ {robot.name} was thrown into a marked HAZARD WALL! KNOCKED OUT!",
                    ))
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"🚀 {robot.name} is THROWN into a WALL! (Strength {throw_str}, d6 Roll {roll_d6} -> hit wall, takes throw damage {throw_dmg})",
                ))
                w_wall_logs = resolve_weapon_wall_contact(robot, throw_strength=throw_str, round_num=round_num, phase="collision", steps=steps)
                logs.extend(w_wall_logs)
            else:
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"🚀 {robot.name} is THROWN! (Strength {throw_str}, d6 Roll {roll_d6} -> {thrown_units} units / {displacement_mm:.0f}mm away, takes throw damage {throw_dmg})",
                ))

            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"🧭 Thrown orientation: {robot.name} rolled {orientation_roll} -> rotated {int(spin_rot)}° clockwise (now {robot.pose.theta:.0f}°).",
            ))

            # Flip check: if throw strength - thrown distance > flip value of chassis
            eff_flip = robot.flip_strength // 2 if robot.is_raised else robot.flip_strength
            excess_throw = throw_str - thrown_units
            if excess_throw > eff_flip:
                robot.is_inverted = not robot.is_inverted
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"🔄 FLIP! (Remaining throw {excess_throw} > Flip value {eff_flip}) -> {robot.name} is now {'INVERTED' if robot.is_inverted else 'UPRIGHT'}!",
                ))

            # Throw shock feedback: at a randomly chosen component (dropping a card)
            if throw_dmg > 0:
                shock_cid = simulate_dropping_card(robot)
                if shock_cid and shock_cid in robot.components:
                    shock_comp = robot.components[shock_cid]
                    logs.append(CombatLogEntry(
                        round=round_num, phase="collision",
                        message=f"⚡ Dropping card: throw shock of {throw_dmg} hits {shock_comp.name} (#{shock_comp.id})!",
                    ))
                    shock_logs = resolve_feedback_propagation(robot, shock_cid, throw_dmg, phase="shock_feedback", steps=steps)
                    for sl in shock_logs:
                        logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Shock Feedback] {sl}"))

            # Hazard pit knockout check
            if is_in_hazard(robot.pose.x, robot.pose.y):
                robot.is_knocked_out = True
                robot.is_eliminated = True
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"☠️ {robot.name} fell into the HAZARD PIT / out of the arena! KNOCKED OUT!",
                ))

        # Rule: if after active contact the robots are still in contact,
        # then proceed with inertial contact. If still touching, both robots are moved back a full unit to separate them.
        if not (r1.is_knocked_out or r1.is_eliminated) and not (r2.is_knocked_out or r2.is_eliminated):
            if check_robots_in_contact(r1, r2):
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message="⚡ Robots are still in contact after active clash — proceeding with inertial contact!",
                ))
                inert_logs = resolve_inert_contact(col, r1, r2, round_num, steps=steps)
                logs.extend(inert_logs)
            if check_robots_in_contact(r1, r2):
                sep_logs = separate_robots_full_unit(r1, r2, round_num, log_prefix="Active contact separation")
                logs.extend(sep_logs)

    else:
        # Standard inert pushing contact
        inert_logs = resolve_inert_contact(col, r1, r2, round_num, steps=steps)
        logs.extend(inert_logs)


    # After contact, robots are pushed or thrown apart -> clear raised status
    r1.is_raised = False
    r2.is_raised = False

    # Refresh drive capabilities and power
    refresh_robot_drive_and_power(r1)
    refresh_robot_drive_and_power(r2)

    return logs
