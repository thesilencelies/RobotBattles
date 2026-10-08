"""Combat resolution: damage progression, feedback propagation, throws, and status effects."""

from __future__ import annotations

import math
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .field import WALL_BOTTOM, WALL_LEFT, WALL_RIGHT, WALL_TOP, is_in_hazard
from .types import CollisionEvent, CombatLogEntry, ComponentHealth, Pose, RobotState


def parse_weapon_spin_and_damage(outputs: str, keywords: str, text: str) -> Tuple[int, Dict[int, int], str]:
    """
    Parses weapon keywords and outputs into max spin and a map of {spin_level: damage}.
    Reused from verified simulate_combat.py implementation.
    """
    spin_match = re.search(r"Spin up\s*\(\s*(\d+)", keywords, re.IGNORECASE)
    max_spin = int(spin_match.group(1)) if spin_match else 0

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

    return max_spin, damage_map, formula_desc


def get_weapon_attack_strength(comp: ComponentHealth, spin_level: int) -> int:
    """Returns total attack strength (for damage, throw strength, and feedback)."""
    text_lower = comp.text.lower()
    if "deals no damage" in text_lower:
        m = re.search(r"(\d+)W", comp.outputs.upper())
        if m:
            return int(m.group(1))
        return 5

    _, d_map, _ = parse_weapon_spin_and_damage(comp.outputs, comp.keywords, comp.text)
    return d_map.get(spin_level, 0)


def apply_damage_to_component(
    comp: ComponentHealth,
    incoming: float,
    is_weapon_damage: bool = True,
) -> Tuple[str, float, float]:
    """
    Applies incoming damage to a component.
    Returns (status, absorbed_amount, excess_amount).
    """
    eff_dur = comp.max_durability
    if comp.is_fragile and is_weapon_damage:
        eff_dur = 1

    if incoming > eff_dur:
        # Destroyed
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
            # Repeated damage destroys it
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
    Returns human-readable step logs.
    """
    logs: List[str] = []
    if damage <= 0 or initial_target_id not in robot.components:
        return logs

    target = robot.components[initial_target_id]
    status, absorbed, excess = apply_damage_to_component(target, damage, is_weapon_damage)
    logs.append(f"{target.name} (#{target.id}) takes {damage:.1f} dmg -> {status} (absorbed {absorbed:.1f}, excess {excess:.1f})")

    visited: Set[str] = {initial_target_id}
    current_front = [(initial_target_id, excess)]

    # Chassis center is (210, 150)
    cx, cy = 210.0, 150.0

    while current_front:
        next_front = []
        for src_id, rem_dmg in current_front:
            if rem_dmg <= 0.05:
                continue

            candidates = []
            for nid in robot.connections.get(src_id, []):
                if nid not in visited and nid in robot.components and not robot.components[nid].is_destroyed:
                    ncomp = robot.components[nid]
                    dist = math.hypot(ncomp.x - cx, ncomp.y - cy)
                    candidates.append((nid, dist))

            if not candidates:
                continue

            # Sort inwards (closer to center first)
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
    Propagates feedback backwards along supply graph (to motors, ESCs, batteries).
    """
    logs: List[str] = []
    if feedback_amount <= 0 or source_id not in robot.components:
        return logs

    src_comp = robot.components[source_id]
    status, absorbed, excess = apply_damage_to_component(src_comp, feedback_amount, is_weapon_damage=False)
    logs.append(f"Feedback on {src_comp.name} (#{src_comp.id}): {feedback_amount:.1f} -> {status}")

    current_layer = [(source_id, excess)]
    visited = {source_id}

    while current_layer:
        next_layer = []
        for cid, rem_dmg in current_layer:
            if rem_dmg <= 0.05:
                continue

            suppliers = [sid for sid in robot.supply_graph.get(cid, []) if sid not in visited and sid in robot.components]
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


def refresh_robot_drive_and_power(robot: RobotState) -> None:
    """
    Recomputes active components and left/right drive max counts based on current health.
    """
    # 1. Topological / connected activation: batteries are self-supplying
    # Components requiring inputs must have an undamaged, active supplier
    active_set: Set[str] = set()

    # Pass 1: Batteries (no requirements)
    for cid, c in robot.components.items():
        if not c.is_destroyed:
            reqs = c.requirements.strip().upper()
            if not reqs:
                c.is_active = True
                active_set.add(cid)
            else:
                c.is_active = False

    # Pass 2: Propagate along supply graph
    changed = True
    iterations = 0
    while changed and iterations < 10:
        changed = False
        iterations += 1
        for cid, c in robot.components.items():
            if c.is_destroyed or c.is_active:
                continue
            suppliers = robot.supply_graph.get(cid, [])
            if any(sid in active_set for sid in suppliers):
                c.is_active = True
                active_set.add(cid)
                changed = True

    # Compute drive strength on left and right sides
    chassis_cx = 210.0
    left_drive = 0
    right_drive = 0

    for cid, c in robot.components.items():
        if not c.is_active or c.is_destroyed:
            continue
        out = c.outputs.upper()
        if "D" in out or "M" in out:
            # Count D's or M's
            count = out.count("D") + out.count("M")
            # If inverted, wheels without invertible keyword don't work
            if robot.is_inverted and not c.is_invertible:
                continue

            card_cx = c.x + (c.box[2] - c.box[0]) / 2.0
            if card_cx < chassis_cx:
                left_drive += count
            else:
                right_drive += count

    # If raised, drive strength is halved
    if robot.is_raised:
        left_drive = max(0, left_drive // 2)
        right_drive = max(0, right_drive // 2)

    robot.left_drive_max = left_drive
    robot.right_drive_max = right_drive


def resolve_collision_combat(
    col: CollisionEvent,
    r1: RobotState,
    r2: RobotState,
    round_num: int,
) -> List[CombatLogEntry]:
    """
    Executes full combat and physics collision resolution according to Robot Battles rules.
    """
    logs: List[CombatLogEntry] = []

    # Identify weapons and components
    w1_list = [
        r1.components[cid] for cid in col.robot1_components
        if cid in r1.components and r1.components[cid].card_type == "weapon" and not r1.components[cid].is_destroyed
    ]
    w2_list = [
        r2.components[cid] for cid in col.robot2_components
        if cid in r2.components and r2.components[cid].card_type == "weapon" and not r2.components[cid].is_destroyed
    ]

    is_active_hit = (col.contact_type == "ACTIVE") and (bool(w1_list) or bool(w2_list))

    if is_active_hit:
        # ACTIVE CONTACT (Weapon Strikes)
        logs.append(CombatLogEntry(
            round=round_num,
            phase="collision",
            message=f"⚔️ ACTIVE WEAPON HIT between {r1.name} and {r2.name}!",
        ))

        # Check ground game: Forks
        r1_forks = any(r1.components[cid].is_forks for cid in col.robot1_components if cid in r1.components)
        r2_forks = any(r2.components[cid].is_forks for cid in col.robot2_components if cid in r2.components)
        if r1_forks and not r2_forks:
            r2.is_raised = True
            logs.append(CombatLogEntry(
                round=round_num, phase="collision", message=f"🔱 {r1.name}'s Forks lift {r2.name}! ({r2.name} is RAISED: drive & flip halved)"
            ))
        elif r2_forks and not r1_forks:
            r1.is_raised = True
            logs.append(CombatLogEntry(
                round=round_num, phase="collision", message=f"🔱 {r2.name}'s Forks lift {r1.name}! ({r1.name} is RAISED: drive & flip halved)"
            ))

        # Attacker 1 -> Defender 2
        throw_str_2 = 0
        if w1_list:
            w1 = w1_list[0]
            spin1 = r1.weapon_spin_counters.get(w1.id, 0)
            atk_str_1 = get_weapon_attack_strength(w1, spin1)
            dmg_1 = atk_str_1
            if "deals no damage" in w1.text.lower():
                dmg_1 = 0

            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"💥 {r1.name} attacks with {w1.name} at Spin {spin1} dealing {dmg_1} damage (Attack Strength {atk_str_1})!"
            ))

            # Apply damage to R2's contacted component
            target_id_2 = col.robot2_components[0] if col.robot2_components else list(r2.components.keys())[0]
            dmg_logs = resolve_inward_damage_progression(r2, target_id_2, float(dmg_1), is_weapon_damage=True)
            for dlog in dmg_logs:
                logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Damage] {dlog}"))

            # Recoil feedback on R1 weapon: half attack strength
            fb1 = atk_str_1 // 2
            if fb1 > 0:
                fb_logs = resolve_feedback_propagation(r1, w1.id, float(fb1))
                for flog in fb_logs:
                    logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Recoil FB] {flog}"))

            # Reset spin counters
            r1.weapon_spin_counters[w1.id] = 0

            # Base throw strength
            throw_str_2 = atk_str_1
            if "double the throw strength" in w1.text.lower():
                throw_str_2 *= 2
            if "always inverts" in w1.text.lower():
                r2.is_inverted = not r2.is_inverted
                logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"🔄 {w1.name} always inverts: {r2.name} is now INVERTED!"))

        # Attacker 2 -> Defender 1
        throw_str_1 = 0
        if w2_list:
            w2 = w2_list[0]
            spin2 = r2.weapon_spin_counters.get(w2.id, 0)
            atk_str_2 = get_weapon_attack_strength(w2, spin2)
            dmg_2 = atk_str_2
            if "deals no damage" in w2.text.lower():
                dmg_2 = 0

            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"💥 {r2.name} attacks with {w2.name} at Spin {spin2} dealing {dmg_2} damage (Attack Strength {atk_str_2})!"
            ))

            target_id_1 = col.robot1_components[0] if col.robot1_components else list(r1.components.keys())[0]
            dmg_logs = resolve_inward_damage_progression(r1, target_id_1, float(dmg_2), is_weapon_damage=True)
            for dlog in dmg_logs:
                logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Damage] {dlog}"))

            fb2 = atk_str_2 // 2
            if fb2 > 0:
                fb_logs = resolve_feedback_propagation(r2, w2.id, float(fb2))
                for flog in fb_logs:
                    logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"  [Recoil FB] {flog}"))

            r2.weapon_spin_counters[w2.id] = 0

            throw_str_1 = atk_str_2
            if "double the throw strength" in w2.text.lower():
                throw_str_1 *= 2
            if "always inverts" in w2.text.lower():
                r1.is_inverted = not r1.is_inverted
                logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"🔄 {w2.name} always inverts: {r1.name} is now INVERTED!"))

        # Check Wedge throw reflection
        r1_wedge = any(r1.components[cid].is_wedge for cid in col.robot1_components if cid in r1.components)
        r2_wedge = any(r2.components[cid].is_wedge for cid in col.robot2_components if cid in r2.components)
        if r1_wedge and throw_str_1 > 0:
            reflected = throw_str_1 // 2
            throw_str_1 -= reflected
            throw_str_2 += reflected
            logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"🛡️ {r1.name}'s Wedge reflects {reflected} throw strength to {r2.name}!"))
        if r2_wedge and throw_str_2 > 0:
            reflected = throw_str_2 // 2
            throw_str_2 -= reflected
            throw_str_1 += reflected
            logs.append(CombatLogEntry(round=round_num, phase="collision", message=f"🛡️ {r2.name}'s Wedge reflects {reflected} throw strength to {r1.name}!"))

        # Execute throws for both robots
        for robot, throw_str, opp in [(r1, throw_str_1, r2), (r2, throw_str_2, r1)]:
            if throw_str <= 0:
                continue

            roll_2d6 = random.randint(1, 6) + random.randint(1, 6)
            throw_dist = min(throw_str, roll_2d6) * 12.0  # scaled to arena mm

            # Vector away from contact point
            dx = robot.pose.x - col.contact_point[0]
            dy = robot.pose.y - col.contact_point[1]
            dist = math.hypot(dx, dy)
            if dist < 1e-4:
                dx, dy = 1.0, 0.0
                dist = 1.0

            throw_nx = dx / dist
            throw_ny = dy / dist

            robot.pose.x = max(WALL_LEFT + 20, min(WALL_RIGHT - 20, robot.pose.x + throw_nx * throw_dist))
            robot.pose.y = max(WALL_TOP + 20, min(WALL_BOTTOM - 20, robot.pose.y + throw_ny * throw_dist))
            # Random model spin rotation
            spin_rot = random.choice([45.0, 90.0, 135.0, 180.0])
            robot.pose.theta = (robot.pose.theta + spin_rot) % 360.0

            logs.append(CombatLogEntry(
                round=round_num, phase="collision",
                message=f"🚀 {robot.name} is THROWN! (Strength {throw_str}, 2d6 Roll {roll_2d6} -> {throw_dist:.0f}mm away)"
            ))

            # Flip / Inversion check
            eff_flip = robot.flip_strength
            if robot.is_raised:
                eff_flip = max(1, eff_flip // 2)

            excess_throw = throw_str - (throw_dist / 12.0)
            if excess_throw > eff_flip:
                robot.is_inverted = not robot.is_inverted
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"🔄 FLIP! (Remaining throw {excess_throw:.1f} > Flip {eff_flip}) -> {robot.name} is now {'INVERTED' if robot.is_inverted else 'UPRIGHT'}!"
                ))

            # Throw shock feedback at a randomly chosen component
            active_cids = [cid for cid, c in robot.components.items() if not c.is_destroyed]
            if active_cids:
                shock_target_id = random.choice(active_cids)
                shock_target = robot.components[shock_target_id]
                shock_logs = resolve_feedback_propagation(robot, shock_target_id, float(throw_str))
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"⚡ Throw shock of {throw_str} hits {shock_target.name} (#{shock_target.id})!"
                ))

            # Hazard pit elimination check
            if is_in_hazard(robot.pose.x, robot.pose.y):
                robot.is_eliminated = True
                logs.append(CombatLogEntry(
                    round=round_num, phase="collision",
                    message=f"☠️ {robot.name} fell into the HAZARD PIT / out of the arena! ELIMINATED!"
                ))

    else:
        # INERT CONTACT (Pushing Match)
        logs.append(CombatLogEntry(
            round=round_num,
            phase="collision",
            message=f"🛡️ Inert contact pushing match between {r1.name} and {r2.name}!",
        ))

        # Line between centers through contact point
        dx = r2.pose.x - r1.pose.x
        dy = r2.pose.y - r1.pose.y
        dist = math.hypot(dx, dy)
        if dist < 1e-4:
            dx, dy = 1.0, 0.0
            dist = 1.0
        nx, ny = dx / dist, dy / dist

        # Separate them slightly to avoid overlap
        sep = 30.0
        r1.pose.x -= nx * (sep / 2)
        r1.pose.y -= ny * (sep / 2)
        r2.pose.x += nx * (sep / 2)
        r2.pose.y += ny * (sep / 2)

        # Drive feedback from pushing: 2 drive feedback to both
        fb_push = 2.0
        for robot in [r1, r2]:
            wheels = [cid for cid, c in robot.components.items() if "wheel" in c.name.lower() and not c.is_destroyed]
            if wheels:
                resolve_feedback_propagation(robot, wheels[0], fb_push)
        logs.append(CombatLogEntry(
            round=round_num, phase="collision",
            message=f"Drive strains in pushing match: drive components absorb feedback."
        ))

    # Re-check drive and power supplies on both robots
    refresh_robot_drive_and_power(r1)
    refresh_robot_drive_and_power(r2)

    return logs
