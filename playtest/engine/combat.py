"""Combat resolution, damage progression, recoil feedback, pushing matches, and throws."""

from __future__ import annotations

import math
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .field import (
    ARENA_HEIGHT,
    ARENA_WIDTH,
    MAT_CENTER_X,
    MAT_CENTER_Y,
    WALL_BOTTOM,
    WALL_LEFT,
    WALL_RIGHT,
    WALL_TOP,
    is_in_hazard,
)
from .movement import DRIVE_UNIT_MM, MINIATURE_RADIUS
from .types import CollisionEvent, CombatLogEntry, ComponentHealth, Pose, RobotState


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
        return 5

    _, _, d_map, _ = parse_weapon_spin_and_damage(comp.outputs, comp.keywords, comp.text)
    return d_map.get(spin_level, 0)


def apply_damage_to_component(
    comp: ComponentHealth,
    incoming: float,
    is_weapon_damage: bool = True,
) -> Tuple[str, float, float]:
    """
    Applies incoming damage according to the canonical rules:
    - Exceeds durability -> Destroyed, absorbs durability, excess continues.
    - Exceeds 1/2 durability after absorption -> Damaged (or destroyed if already damaged).
    - Otherwise -> absorbs absorption, excess continues.
    Returns (status, absorbed_amount, excess_amount).
    """
    eff_dur = comp.max_durability
    if comp.is_fragile and is_weapon_damage:
        eff_dur = 1

    if incoming > eff_dur:
        comp.is_destroyed = True
        comp.current_durability = 0
        comp.is_active = False
        absorbed = float(eff_dur)
        excess = max(0.0, incoming - absorbed)
        return "DESTROYED", absorbed, excess

    net_after_abs = max(0.0, incoming - comp.absorption)
    half_dur = eff_dur / 2.0

    if net_after_abs > half_dur:
        if comp.is_damaged:
            comp.is_destroyed = True
            comp.current_durability = 0
            comp.is_active = False
            absorbed = float(eff_dur)
            excess = max(0.0, incoming - absorbed)
            return "DESTROYED", absorbed, excess
        else:
            comp.is_damaged = True
            comp.current_durability = max(1, eff_dur - int(net_after_abs))
            absorbed = min(incoming, float(comp.absorption))
            excess = net_after_abs
            return "DAMAGED", absorbed, excess
    else:
        absorbed = min(incoming, float(comp.absorption))
        excess = net_after_abs
        return "UNDAMAGED", absorbed, excess


def resolve_inward_damage_progression(
    robot: RobotState,
    initial_target_id: str,
    damage: float,
    is_weapon_damage: bool = True,
) -> List[str]:
    """
    Propagates damage from the initial contacted component inwards.
    """
    logs: List[str] = []
    if damage <= 0 or initial_target_id not in robot.components:
        return logs

    target = robot.components[initial_target_id]
    status, absorbed, excess = apply_damage_to_component(target, damage, is_weapon_damage)
    logs.append(f"{target.name} (#{target.id}) takes {damage:.1f} dmg -> {status} (absorbed {absorbed:.1f}, excess {excess:.1f})")

    visited: Set[str] = {initial_target_id}
    current_front = [(initial_target_id, excess)]

    while current_front:
        next_front = []
        for src_id, rem_dmg in current_front:
            if rem_dmg <= 0.05:
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
            split_dmg = rem_dmg / len(candidates)

            for nid, _ in candidates:
                visited.add(nid)
                ncomp = robot.components[nid]
                nstatus, nabsorbed, nexcess = apply_damage_to_component(ncomp, split_dmg, is_weapon_damage)
                logs.append(f"{ncomp.name} (#{ncomp.id}) takes {split_dmg:.1f} excess dmg -> {nstatus} (absorbed {nabsorbed:.1f})")
                if nexcess > 0:
                    next_front.append((nid, nexcess))

        current_front = next_front

    return logs


def resolve_feedback_propagation(
    robot: RobotState,
    source_id: str,
    feedback_amount: float,
) -> List[str]:
    """
    Propagates feedback backwards along the supply graph
    (from weapon/drive back to motors, ESCs, batteries).
    """
    logs: List[str] = []
    if feedback_amount <= 0 or source_id not in robot.components:
        return logs

    src_comp = robot.components[source_id]
    status, absorbed, excess = apply_damage_to_component(src_comp, feedback_amount, is_weapon_damage=False)
    logs.append(f"Feedback on {src_comp.name} (#{src_comp.id}): {feedback_amount:.1f} -> {status} (absorbed {absorbed:.1f})")

    current_layer = [(source_id, excess)]
    visited = {source_id}

    while current_layer:
        next_layer = []
        for cid, rem_dmg in current_layer:
            if rem_dmg <= 0.05:
                continue

            suppliers = [sid for sid in robot.supply_graph.get(cid, []) if sid not in visited and sid in robot.components and not robot.components[sid].is_destroyed]
            if not suppliers:
                continue

            split_dmg = rem_dmg / len(suppliers)
            for sid in suppliers:
                visited.add(sid)
                scomp = robot.components[sid]
                sstatus, sabsorbed, sexcess = apply_damage_to_component(scomp, split_dmg, is_weapon_damage=False)
                logs.append(f"Feedback passed to supplier {scomp.name} (#{scomp.id}): {split_dmg:.1f} -> {sstatus}")
                if sexcess > 0:
                    next_layer.append((sid, sexcess))

        current_layer = next_layer

    return logs


def simulate_dropping_card(robot: RobotState) -> Optional[str]:
    """
    Simulates randomly dropping a card on the A3 chassis sheet
    to determine which component takes throw shock.
    """
    active_comps = [c for c in robot.components.values() if not c.is_destroyed]
    if not active_comps:
        return None

    # Drop card at random position on the A3 mat (420 x 297 mm)
    drop_x = random.uniform(80.0, 340.0)
    drop_y = random.uniform(40.0, 260.0)
    card_w, card_h = 44.0, 64.0
    if random.choice([True, False]):
        card_w, card_h = 64.0, 44.0
    drop_box = (drop_x, drop_y, drop_x + card_w, drop_y + card_h)

    # Check which placed components overlap the dropped card
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

    # If dropped card missed placed cards, pick nearest active component
    nearest_cid = min(
        active_comps,
        key=lambda c: math.hypot(
            (c.box[0] + c.box[2]) / 2.0 - drop_x,
            (c.box[1] + c.box[3]) / 2.0 - drop_y
        )
    ).id
    return nearest_cid


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
    Returns the set of endpoint categories ('left_drive', 'right_drive', 'weapon', 'other')
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


def refresh_robot_drive_and_power(robot: RobotState, current_move: Optional[MoveChoice] = None) -> None:
    """
    Recomputes active components and left/right drive max counts based on current health,
    enforcing resource supply and split supply rules:
    - If a component supplying multiple components can supply all of their needs between them,
      then they are all supplied fine.
    - If it cannot, then it supplies components based on their connected endpoint:
      drive first, then weapons, unless the robot chose not to use that side's drive this turn (drive = 0).
    - Within the same category, it supplies from the largest requirement going down.
    - If multiple components supply the same multiple components, sum up the supply and distribute as above.
    """
    left_drive_active = current_move is None or current_move.left != 0
    right_drive_active = current_move is None or current_move.right != 0

    # Initialize all components to inactive
    for cid, c in robot.components.items():
        c.is_active = False

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

    # Pass 2: Iteratively propagate and allocate supply along the supply graph
    changed = True
    iterations = 0
    while changed and iterations < 15:
        changed = False
        iterations += 1

        # Group components whose suppliers are in active_set
        eligible_cids = [
            cid for cid, c in robot.components.items()
            if not c.is_destroyed and not c.is_active and any(sid in active_set for sid in robot.supply_graph.get(cid, []))
        ]

        if not eligible_cids:
            break

        # Collect suppliers providing to these eligible components
        # To handle 'multiple components supply the same multiple components, sum up supply':
        # Group components by their active supplier set
        supplier_clusters: Dict[Tuple[str, ...], List[str]] = {}
        for cid in eligible_cids:
            active_sups = tuple(sorted([sid for sid in robot.supply_graph.get(cid, []) if sid in active_set]))
            if active_sups:
                supplier_clusters.setdefault(active_sups, []).append(cid)

        for sups, consumers in supplier_clusters.items():
            # Sum up available supply from these suppliers for each resource type
            cluster_supply: Dict[str, int] = {}
            for sid in sups:
                s_counts = avail_supply.get(sid, {})
                for res, count in s_counts.items():
                    if count == -1:  # Pass-through unlimited
                        cluster_supply[res] = cluster_supply.get(res, 0) + 9999
                    else:
                        cluster_supply[res] = cluster_supply.get(res, 0) + count

            # Priority sorting for consumers based on connected endpoint:
            # 1. Drive first (unless drive side is not used this turn)
            # 2. Weapons second
            # 3. Other / unused drive
            # Within same category: largest requirement going down
            def consumer_sort_key(cid: str):
                c = robot.components[cid]
                endpoints = _get_downstream_endpoints(cid, robot)
                is_active_drive = (
                    ("left_drive" in endpoints and left_drive_active) or
                    ("right_drive" in endpoints and right_drive_active)
                )
                is_weapon = "weapon" in endpoints

                if is_active_drive:
                    cat_pri = 0
                elif is_weapon:
                    cat_pri = 1
                else:
                    cat_pri = 2

                req_counts = parse_resource_counts(c.requirements)
                total_req = sum(v for v in req_counts.values() if v > 0)
                # Sort by (cat_pri asc, total_req desc)
                return (cat_pri, -total_req, cid)

            sorted_consumers = sorted(consumers, key=consumer_sort_key)

            # Check if total available supply can supply all needs between them
            total_reqs: Dict[str, int] = {}
            for cid in sorted_consumers:
                for res, req_val in parse_resource_counts(robot.components[cid].requirements).items():
                    if req_val > 0:
                        total_reqs[res] = total_reqs.get(res, 0) + req_val

            def deduct_from_suppliers(res: str, amount: int):
                rem = amount
                for sid in sups:
                    if rem <= 0:
                        break
                    s_cnt = avail_supply.get(sid, {}).get(res, 0)
                    if s_cnt == -1:  # pass-through unlimited
                        continue
                    take = min(rem, s_cnt)
                    avail_supply[sid][res] = s_cnt - take
                    rem -= take

            can_supply_all = all(cluster_supply.get(res, 0) >= req_tot for res, req_tot in total_reqs.items())

            if can_supply_all:
                for cid in sorted_consumers:
                    c = robot.components[cid]
                    if not c.is_active:
                        # Deduct from suppliers
                        for res, req_val in parse_resource_counts(c.requirements).items():
                            if req_val > 0:
                                cluster_supply[res] = cluster_supply.get(res, 0) - req_val
                                deduct_from_suppliers(res, req_val)

                        c.is_active = True
                        active_set.add(cid)
                        # Compute its available outputs
                        out_counts = parse_resource_counts(c.outputs)
                        # Pass-through handling (XE / XS)
                        for r, cnt in out_counts.items():
                            if cnt == -1:
                                req_in = parse_resource_counts(c.requirements).get(r, 0)
                                out_counts[r] = req_in if req_in > 0 else 9999
                        avail_supply[cid] = out_counts
                        changed = True
            else:
                # Distribute according to priority
                for cid in sorted_consumers:
                    c = robot.components[cid]
                    if c.is_active:
                        continue
                    req_counts = parse_resource_counts(c.requirements)
                    # Check if current cluster_supply can satisfy this component
                    can_satisfy = True
                    for res, req_val in req_counts.items():
                        if req_val > 0 and cluster_supply.get(res, 0) < req_val:
                            can_satisfy = False
                            break

                    if can_satisfy:
                        # Deduct requirement from cluster and individual suppliers
                        for res, req_val in req_counts.items():
                            if req_val > 0:
                                cluster_supply[res] = cluster_supply.get(res, 0) - req_val
                                deduct_from_suppliers(res, req_val)

                        c.is_active = True
                        active_set.add(cid)
                        out_counts = parse_resource_counts(c.outputs)
                        for r, cnt in out_counts.items():
                            if cnt == -1:
                                req_in = req_counts.get(r, 0)
                                out_counts[r] = req_in if req_in > 0 else 9999
                        avail_supply[cid] = out_counts
                        changed = True

    # Count drive outputs on left and right sides
    left_drive = 0
    right_drive = 0

    for cid, c in robot.components.items():
        # Keep spin counter synced on component
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

    # If raised, drive strength is halved
    if robot.is_raised:
        left_drive = max(0, left_drive // 2)
        right_drive = max(0, right_drive // 2)

    robot.left_drive_max = left_drive
    robot.right_drive_max = right_drive


def start_of_turn_spin_up(robot: RobotState) -> List[str]:
    """
    Executes Spin up (X, Y) keyword at the start of turn:
    Add X spin counters up to max Y.
    """
    logs: List[str] = []
    for cid, comp in robot.components.items():
        if comp.card_type != "weapon" or comp.is_destroyed or not comp.is_active:
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


def resolve_collision_combat(
    col: CollisionEvent,
    r1: RobotState,
    r2: RobotState,
    round_num: int,
) -> List[CombatLogEntry]:
    """
    Executes combat resolution adhering strictly to combat_robotics_game.tex.
    """
    logs: List[CombatLogEntry] = []

    if col.contact_type == "ACTIVE":
        # ======================================================================
        # ACTIVE WEAPON CONTACT
        # ======================================================================
        logs.append(CombatLogEntry(
            round=round_num,
            phase="collision",
            message=f"⚔️ ACTIVE WEAPON HIT: {col.description}",
        ))

        # Check Ground Game: Forks keyword
        r1_forks = any(r1.components[cid].is_forks for cid in col.robot1_components if cid in r1.components)
        r2_forks = any(r2.components[cid].is_forks for cid in col.robot2_components if cid in r2.components)
        if r1_forks and not r2_forks:
            r2.is_raised = True
            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"🔱 {r1.name}'s Forks lift {r2.name}! ({r2.name} is RAISED: drive & flip strength halved)",
            ))
        elif r2_forks and not r1_forks:
            r1.is_raised = True
            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"🔱 {r2.name}'s Forks lift {r1.name}! ({r1.name} is RAISED: drive & flip strength halved)",
            ))

        # Identify attacking weapons involved
        w1_attacking = [
            r1.components[cid] for cid in col.robot1_components
            if cid in r1.components and r1.components[cid].card_type == "weapon" and not r1.components[cid].is_destroyed
            and col.r1_active_hit
        ]
        w2_attacking = [
            r2.components[cid] for cid in col.robot2_components
            if cid in r2.components and r2.components[cid].card_type == "weapon" and not r2.components[cid].is_destroyed
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
        if w1_comp:
            spin1 = r1.weapon_spin_counters.get(w1_comp.id, 0)
            dmg1 = 0 if "deals no damage" in w1_comp.text.lower() else atk_str_1
            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"💥 {r1.name} attacks with {w1_comp.name} at Spin {spin1} dealing {dmg1} dmg (Attack Strength {atk_str_1})!",
            ))

            target2_id = col.robot2_components[0] if col.robot2_components else list(r2.components.keys())[0]
            dmg_logs = resolve_inward_damage_progression(r2, target2_id, float(dmg1), is_weapon_damage=True)
            for dl in dmg_logs:
                logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Damage] {dl}"))

            # Remove spin counters after attack
            r1.weapon_spin_counters[w1_comp.id] = 0
            w1_comp.spin_counters = 0

            # Base throw strength
            throw_str_2 = atk_str_1
            if "double the throw strength" in w1_comp.text.lower():
                throw_str_2 *= 2
            if "always inverts" in w1_comp.text.lower():
                r2.is_inverted = not r2.is_inverted
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"🔄 {w1_comp.name} always inverts: {r2.name} is now {'INVERTED' if r2.is_inverted else 'UPRIGHT'}!",
                ))

        # 2. Apply Weapon 2 damage to Robot 1
        throw_str_1 = 0
        if w2_comp:
            spin2 = r2.weapon_spin_counters.get(w2_comp.id, 0)
            dmg2 = 0 if "deals no damage" in w2_comp.text.lower() else atk_str_2
            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"💥 {r2.name} attacks with {w2_comp.name} at Spin {spin2} dealing {dmg2} dmg (Attack Strength {atk_str_2})!",
            ))

            target1_id = col.robot1_components[0] if col.robot1_components else list(r1.components.keys())[0]
            dmg_logs = resolve_inward_damage_progression(r1, target1_id, float(dmg2), is_weapon_damage=True)
            for dl in dmg_logs:
                logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Damage] {dl}"))

            r2.weapon_spin_counters[w2_comp.id] = 0
            w2_comp.spin_counters = 0

            throw_str_1 = atk_str_2
            if "double the throw strength" in w2_comp.text.lower():
                throw_str_1 *= 2
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
                fb_logs = resolve_feedback_propagation(r1, w1_comp.id, float(recoil_fb))
                for fl in fb_logs:
                    logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Recoil Feedback] {fl}"))
            if w2_comp and recoil_fb > 0:
                fb_logs = resolve_feedback_propagation(r2, w2_comp.id, float(recoil_fb))
                for fl in fb_logs:
                    logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Recoil Feedback] {fl}"))

        # 4. Check Wedge keyword throw reflection
        r1_wedge = any(r1.components[cid].is_wedge for cid in col.robot1_components if cid in r1.components)
        r2_wedge = any(r2.components[cid].is_wedge for cid in col.robot2_components if cid in r2.components)
        if r1_wedge and throw_str_1 > 0:
            reflected = throw_str_1 // 2
            throw_str_1 -= reflected
            throw_str_2 += reflected
            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"🛡️ {r1.name}'s Wedge reflects {reflected} throw strength to {r2.name}!",
            ))
        if r2_wedge and throw_str_2 > 0:
            reflected = throw_str_2 // 2
            throw_str_2 -= reflected
            throw_str_1 += reflected
            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"🛡️ {r2.name}'s Wedge reflects {reflected} throw strength to {r1.name}!",
            ))

        # 5. Execute Throws away from contact point
        for robot, throw_str, opp in [(r1, throw_str_1, r2), (r2, throw_str_2, r1)]:
            if throw_str <= 0:
                continue

            roll_2d6 = random.randint(1, 6) + random.randint(1, 6)
            thrown_units = min(throw_str, roll_2d6)
            displacement_mm = thrown_units * DRIVE_UNIT_MM

            # Vector away from contact point
            dx = robot.pose.x - col.contact_point[0]
            dy = robot.pose.y - col.contact_point[1]
            dist = math.hypot(dx, dy)
            if dist < 1e-4:
                dx, dy = 1.0, 0.0
                dist = 1.0
            nx, ny = dx / dist, dy / dist

            robot.pose.x = max(WALL_LEFT + 20, min(WALL_RIGHT - 20, robot.pose.x + nx * displacement_mm))
            robot.pose.y = max(WALL_TOP + 20, min(WALL_BOTTOM - 20, robot.pose.y + ny * displacement_mm))
            # Model rotated by spinning
            spin_rot = random.choice([45.0, 90.0, 135.0, 180.0])
            robot.pose.theta = (robot.pose.theta + spin_rot) % 360.0

            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"🚀 {robot.name} is THROWN! (Strength {throw_str}, 2d6 Roll {roll_2d6} -> {thrown_units} units / {displacement_mm:.0f}mm away)",
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
            shock_cid = simulate_dropping_card(robot)
            if shock_cid and shock_cid in robot.components:
                shock_comp = robot.components[shock_cid]
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"⚡ Dropping card: throw shock of {throw_str} hits {shock_comp.name} (#{shock_comp.id})!",
                ))
                shock_logs = resolve_feedback_propagation(robot, shock_cid, float(throw_str))
                for sl in shock_logs:
                    logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Shock Feedback] {sl}"))

            # Hazard pit elimination check
            if is_in_hazard(robot.pose.x, robot.pose.y):
                robot.is_eliminated = True
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"☠️ {robot.name} fell into the HAZARD PIT / out of the arena! ELIMINATED!",
                ))

    else:
        # ======================================================================
        # INERT CONTACT (Pushing Match)
        # ======================================================================
        logs.append(CombatLogEntry(
            round=round_num,
            phase="collision",
            message=f"🛡️ PUSHING MATCH: {col.description}",
        ))

        # Pair moves along the line drawn between centers by net remaining motion
        push_dx, push_dy = col.push_vector
        net_dist = math.hypot(push_dx, push_dy)

        # Check if either robot is pushed into a wall
        # Determine target positions
        new_r1_x = r1.pose.x + push_dx
        new_r1_y = r1.pose.y + push_dy
        new_r2_x = r2.pose.x + push_dx
        new_r2_y = r2.pose.y + push_dy

        pushed_into_wall_robot = None
        excess_wall_dist = 0.0

        for r_target, r_curr, robot_obj in [
            (new_r1_x, r1.pose.x, r1),
            (new_r2_x, r2.pose.x, r2),
        ]:
            clamped_x = max(WALL_LEFT + MINIATURE_RADIUS, min(WALL_RIGHT - MINIATURE_RADIUS, new_r1_x))
            clamped_y = max(WALL_TOP + MINIATURE_RADIUS, min(WALL_BOTTOM - MINIATURE_RADIUS, new_r1_y))
            lost_x = abs(new_r1_x - clamped_x)
            lost_y = abs(new_r1_y - clamped_y)
            if lost_x > 2.0 or lost_y > 2.0:
                pushed_into_wall_robot = robot_obj
                excess_wall_dist = math.hypot(lost_x, lost_y)

        # Displace pair
        r1.pose.x = max(WALL_LEFT + 20, min(WALL_RIGHT - 20, new_r1_x))
        r1.pose.y = max(WALL_TOP + 20, min(WALL_BOTTOM - 20, new_r1_y))
        r2.pose.x = max(WALL_LEFT + 20, min(WALL_RIGHT - 20, new_r2_x))
        r2.pose.y = max(WALL_TOP + 20, min(WALL_BOTTOM - 20, new_r2_y))

        logs.append(CombatLogEntry(
            round=round_num, phase="collision",
            message=f"Robots push together along line between centers: displacement {net_dist / DRIVE_UNIT_MM:.1f} units ({net_dist:.0f}mm).",
        ))

        # Wall throw check
        if pushed_into_wall_robot and excess_wall_dist > 5.0:
            wall_throw_str = int(round(excess_wall_dist / DRIVE_UNIT_MM))
            if wall_throw_str > 0:
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"💥 {pushed_into_wall_robot.name} was pushed into the wall! THROWN with throw strength {wall_throw_str}!",
                ))
                # Resolve throw away from wall
                # Shock feedback equal to throw strength
                shock_cid = simulate_dropping_card(pushed_into_wall_robot)
                if shock_cid:
                    resolve_feedback_propagation(pushed_into_wall_robot, shock_cid, float(wall_throw_str))

        # Drive feedback: each robot takes feedback shared equally between active drive equal to opponent remaining distance
        opp_rem_1 = col.r2_remaining_dist / DRIVE_UNIT_MM  # What R2 had before contact
        opp_rem_2 = col.r1_remaining_dist / DRIVE_UNIT_MM  # What R1 had before contact

        for robot, opp_rem in [(r1, opp_rem_1), (r2, opp_rem_2)]:
            if opp_rem <= 0.1:
                continue
            active_drives = [
                c for c in robot.components.values()
                if not c.is_destroyed and c.is_active and ("D" in c.outputs.upper() or "M" in c.outputs.upper())
            ]
            if active_drives:
                fb_per_drive = opp_rem / len(active_drives)
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"{robot.name}'s active drive absorbs {opp_rem:.1f} feedback from opponent's remaining momentum ({fb_per_drive:.1f} per drive).",
                ))
                for dcomp in active_drives:
                    resolve_feedback_propagation(robot, dcomp.id, fb_per_drive)

    # After contact, robots are pushed or thrown apart -> clear raised status
    r1.is_raised = False
    r2.is_raised = False

    # Refresh drive capabilities and power
    refresh_robot_drive_and_power(r1)
    refresh_robot_drive_and_power(r2)

    return logs
