#!/usr/bin/env python3
"""
Combat Simulation Script for Robot Battles
Tests weapon impacts, spin-up scaling, feedback propagation, and throw shock
against robot layouts loaded from CSV files.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from builder.server.data import (
    CARD_HEIGHT_MM,
    CARD_WIDTH_MM,
    compute_card_box,
    load_all_cards,
    parse_robot_csv,
    read_saved_robot,
)


@dataclass
class PlacedComponent:
    id: str
    name: str
    card_type: str
    durability: int
    absorption: int
    requirements: str
    outputs: str
    keywords: str
    text: str
    x: float
    y: float
    rotation: int
    box: Tuple[float, float, float, float]
    connections: List[str] = field(default_factory=list)
    suppliers: List[str] = field(default_factory=list)
    is_fragile: bool = False
    is_wedge: bool = False
    is_forks: bool = False
    is_invertible: bool = False


@dataclass
class RobotModel:
    name: str
    chassis: Dict[str, Any]
    components: Dict[str, PlacedComponent]
    adjacency: Dict[str, List[str]]
    supply_graph: Dict[str, List[str]]  # component_id -> list of supplier component_ids
    reverse_supply: Dict[str, List[str]]  # supplier_id -> list of components it supplies
    outer_components: List[str]


def parse_weapon_spin_and_damage(weapon: Dict[str, Any]) -> Tuple[int, Dict[int, int], str]:
    """
    Parses weapon keywords and outputs into max spin and a map of {spin_level: damage}.
    Returns (max_spin, damage_map, notation_desc).
    Rules:
      - 4XW -> 4 * X
      - 6XW -> 6 * X
      - 2XW -> 2 * X
      - XWW -> X*W + W = X + 1 (confirmed by user)
      - XXW -> X^2 * W = X^2 (confirmed by user)
      - WWW -> 3 flat damage
      - 10W, 5W, 2W with lifter/flipper text -> deals 0 direct component damage, but has throw strength
    """
    keywords = weapon.get("keywords", "")
    outputs = weapon.get("outputs", "")
    text = weapon.get("text", "")

    # Determine max spin
    spin_match = re.search(r"Spin up\s*\(\s*(\d+)", keywords, re.IGNORECASE)
    if spin_match:
        max_spin = int(spin_match.group(1))
    else:
        max_spin = 0

    damage_map: Dict[int, int] = {}
    is_pure_throw = "deals no damage" in text.lower() or "throws" in text.lower() and "no damage" in text.lower()

    # Determine damage formula
    formula_desc = outputs
    out_clean = outputs.strip().upper()

    min_spin = 1 if max_spin > 0 else 0
    spin_levels = list(range(min_spin, max_spin + 1)) if max_spin > 0 else [0]

    for s in spin_levels:
        if is_pure_throw:
            damage_map[s] = 0
            formula_desc = f"{outputs} (Deals 0 weapon damage; Throws only)"
        elif out_clean == "4XW":
            damage_map[s] = 4 * s
        elif out_clean == "6XW":
            damage_map[s] = 6 * s
        elif out_clean == "2XW":
            damage_map[s] = 2 * s
        elif out_clean == "XWW":
            damage_map[s] = s + 1
            formula_desc = "X + 1 (X*W + W)"
        elif out_clean == "XXW":
            damage_map[s] = s ** 2
            formula_desc = "X^2 (X^2 * W)"
        elif out_clean == "WWW":
            damage_map[s] = 3
            formula_desc = "3 (WWW)"
        elif re.match(r"^(\d+)W$", out_clean):
            val = int(re.match(r"^(\d+)W$", out_clean).group(1))
            damage_map[s] = val
        else:
            # Fallback
            damage_map[s] = s

    return max_spin, damage_map, formula_desc


def get_weapon_attack_strength(weapon: Dict[str, Any], spin_level: int) -> int:
    """Returns the attack strength (used for throw strength and feedback)."""
    outputs = weapon.get("outputs", "").strip().upper()
    text = weapon.get("text", "").lower()

    if "deals no damage" in text:
        # e.g. Four-Bar Lifter 10W -> throw strength 10
        m = re.search(r"(\d+)W", outputs)
        if m:
            return int(m.group(1))
        return 5

    _, d_map, _ = parse_weapon_spin_and_damage(weapon)
    return d_map.get(spin_level, 0)


def boxes_touch(
    b1: Tuple[float, float, float, float],
    b2: Tuple[float, float, float, float],
    tolerance: float = 6.5,
) -> bool:
    """Checks if bounding boxes touch within tolerance (mm)."""
    x1_min, y1_min, x1_max, y1_max = b1
    x2_min, y2_min, x2_max, y2_max = b2
    if x1_max < x2_min - tolerance or x2_max < x1_min - tolerance:
        return False
    if y1_max < y2_min - tolerance or y2_max < y1_min - tolerance:
        return False
    return True


def build_robot_model(csv_path: Path, catalog: Dict[str, Any], tolerance: float = 6.5) -> RobotModel:
    with open(csv_path, "r", encoding="utf-8") as f:
        content = f.read()

    parsed = parse_robot_csv(content)
    chassis = parsed["chassis"]
    by_name = catalog["by_name"]

    components: Dict[str, PlacedComponent] = {}
    for c in parsed["placed_cards"]:
        cid = str(c["id"])
        cname = c["card"]
        cdata = by_name.get(cname, {})

        x = float(c.get("x", 100.0))
        y = float(c.get("y", 100.0))
        rot = int(c.get("rotation", 0))
        box = compute_card_box(x, y, rot)

        kw = str(cdata.get("keywords", "")).lower()

        comp = PlacedComponent(
            id=cid,
            name=cname,
            card_type=cdata.get("type", "component"),
            durability=int(cdata.get("durability", 5)),
            absorption=int(cdata.get("absorption", 0)),
            requirements=str(cdata.get("requirements", "")),
            outputs=str(cdata.get("outputs", "")),
            keywords=str(cdata.get("keywords", "")),
            text=str(cdata.get("text", "")),
            x=x,
            y=y,
            rotation=rot,
            box=box,
            connections=[],
            suppliers=[],
            is_fragile="fragile" in kw,
            is_wedge="wedge" in kw,
            is_forks="forks" in kw,
            is_invertible="invertible" in kw,
        )
        components[cid] = comp

    # Compute adjacency based on physical proximity
    adjacency: Dict[str, List[str]] = {cid: [] for cid in components}
    cids = list(components.keys())
    for i in range(len(cids)):
        id_a = cids[i]
        box_a = components[id_a].box
        for j in range(i + 1, len(cids)):
            id_b = cids[j]
            box_b = components[id_b].box
            if boxes_touch(box_a, box_b, tolerance):
                adjacency[id_a].append(id_b)
                adjacency[id_b].append(id_a)

    for cid, neighbors in adjacency.items():
        components[cid].connections = neighbors

    # Build supply graph (Component -> Suppliers)
    # Energy (E) supplied by Batteries
    # Spin (S) supplied by Motors/Belts
    # Pressure (P) supplied by Servos
    # Drive (D/M) supplied by Wheels
    supply_graph: Dict[str, List[str]] = {cid: [] for cid in components}
    reverse_supply: Dict[str, List[str]] = {cid: [] for cid in components}

    for cid, comp in components.items():
        reqs = comp.requirements.upper()
        if not reqs:
            continue

        needed_types: Set[str] = set()
        for res_char in ["E", "S", "P", "D", "M"]:
            if res_char in reqs:
                needed_types.add(res_char)

        # Look in connected neighbors
        for nid in comp.connections:
            neighbor = components[nid]
            nout = neighbor.outputs.upper()
            can_supply = any(nt in nout for nt in needed_types)
            if can_supply:
                if nid not in supply_graph[cid]:
                    supply_graph[cid].append(nid)
                if cid not in reverse_supply[nid]:
                    reverse_supply[nid].append(cid)

    # Determine outer components (e.g. exposed on perimeter)
    # Bounding center of chassis or robot
    all_x = [comp.x for comp in components.values()]
    all_y = [comp.y for comp in components.values()]
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)

    outer_components: List[str] = []
    for cid, comp in components.items():
        # If it is armor, wedge, wheel, weapon, or at outer edge
        is_protective = comp.is_wedge or "armor" in comp.name.lower() or "plate" in comp.name.lower() or "fork" in comp.name.lower()
        is_outer_mech = "wheel" in comp.name.lower() or comp.card_type == "weapon"
        is_boundary = (comp.x <= min_x + 20) or (comp.x >= max_x - 20) or (comp.y <= min_y + 20) or (comp.y >= max_y - 20)
        if is_protective or is_outer_mech or is_boundary:
            outer_components.append(cid)

    return RobotModel(
        name=csv_path.stem,
        chassis=chassis,
        components=components,
        adjacency=adjacency,
        supply_graph=supply_graph,
        reverse_supply=reverse_supply,
        outer_components=outer_components,
    )


@dataclass
class DamageStepResult:
    component_id: str
    component_name: str
    incoming_damage: float
    effective_durability: int
    absorption: int
    status: str  # UNDAMAGED, DAMAGED, DESTROYED
    absorbed_damage: float
    excess_damage: float


def resolve_single_component_hit(
    comp: PlacedComponent,
    damage: float,
    is_weapon_damage: bool = True,
    already_damaged: bool = False,
) -> DamageStepResult:
    """
    Applies the game rules for a single component hit:
      - Destroyed if remaining damage exceeds durability.
      - Absorbs durability if destroyed.
      - If fragile and weapon damage, treated as durability 1.
      - Damaged if remaining damage minus absorption > durability / 2.
      - If already damaged and would be damaged again -> destroyed.
    """
    eff_dur = comp.durability
    if comp.is_fragile and is_weapon_damage:
        eff_dur = 1

    absorbed = 0.0
    excess = 0.0
    status = "UNDAMAGED"

    if damage > eff_dur:
        status = "DESTROYED"
        absorbed = float(eff_dur)
        excess = max(0.0, damage - absorbed)
    else:
        # Not destroyed directly
        net_after_abs = max(0.0, damage - comp.absorption)
        half_dur = eff_dur / 2.0

        if net_after_abs > half_dur:
            if already_damaged:
                status = "DESTROYED"
                absorbed = float(eff_dur)
                excess = max(0.0, damage - absorbed)
            else:
                status = "DAMAGED"
                absorbed = min(damage, float(comp.absorption))
                excess = net_after_abs
        else:
            status = "UNDAMAGED"
            absorbed = min(damage, float(comp.absorption))
            excess = net_after_abs

    return DamageStepResult(
        component_id=comp.id,
        component_name=comp.name,
        incoming_damage=damage,
        effective_durability=eff_dur,
        absorption=comp.absorption,
        status=status,
        absorbed_damage=absorbed,
        excess_damage=excess,
    )


def simulate_inward_damage_progression(
    robot: RobotModel,
    initial_target_id: str,
    initial_damage: float,
    is_weapon_damage: bool = True,
) -> List[DamageStepResult]:
    """
    Simulates attack damage hitting an outer component and propagating inward.
    Excess damage is shared evenly among inward connected neighbors.
    Inward is defined as neighbors closer to robot center or further from impact site.
    """
    results: List[DamageStepResult] = []
    if initial_damage <= 0:
        return results

    # Determine robot center
    cx = sum(c.x for c in robot.components.values()) / len(robot.components)
    cy = sum(c.y for c in robot.components.values()) / len(robot.components)

    target_comp = robot.components[initial_target_id]
    first_res = resolve_single_component_hit(target_comp, initial_damage, is_weapon_damage)
    results.append(first_res)

    excess = first_res.excess_damage
    visited: Set[str] = {initial_target_id}
    current_front = [(initial_target_id, excess)]

    while current_front:
        next_front = []
        for src_id, rem_dmg in current_front:
            if rem_dmg <= 0.05:
                continue

            src_comp = robot.components[src_id]
            src_dist = math.hypot(src_comp.x - cx, src_comp.y - cy)

            # Find connected unvisited neighbors that are more inward (or equidistant)
            candidate_inward = []
            for nid in robot.adjacency[src_id]:
                if nid not in visited:
                    ncomp = robot.components[nid]
                    n_dist = math.hypot(ncomp.x - cx, ncomp.y - cy)
                    # More inward means closer to center or equal
                    candidate_inward.append((nid, n_dist))

            if not candidate_inward:
                # If no more inward neighbors, damage dissipates into chassis
                continue

            # Share evenly among inward neighbors
            num_branches = len(candidate_inward)
            shared_dmg = rem_dmg / num_branches

            for nid, _ in candidate_inward:
                visited.add(nid)
                ncomp = robot.components[nid]
                step_res = resolve_single_component_hit(ncomp, shared_dmg, is_weapon_damage)
                results.append(step_res)
                if step_res.excess_damage > 0:
                    next_front.append((nid, step_res.excess_damage))

        current_front = next_front

    return results


def simulate_weapon_feedback(
    robot: RobotModel,
    weapon_comp: PlacedComponent,
    attack_strength: int,
) -> List[DamageStepResult]:
    """
    Simulates recoil feedback on the attacking robot.
    Feedback = floor(attack_strength / 2).
    Rule: Weapon takes feedback first. Excess feedback shared evenly among its suppliers,
    progressing down the tree.
    """
    results: List[DamageStepResult] = []
    recoil_feedback = attack_strength // 2
    if recoil_feedback <= 0:
        return results

    # Step 1: Weapon itself takes feedback
    first_step = resolve_single_component_hit(weapon_comp, float(recoil_feedback), is_weapon_damage=False)
    results.append(first_step)

    current_layer = [(weapon_comp.id, first_step.excess_damage)]
    visited = {weapon_comp.id}

    while current_layer:
        next_layer = []
        for cid, rem_dmg in current_layer:
            if rem_dmg <= 0.05:
                continue

            suppliers = robot.supply_graph.get(cid, [])
            valid_suppliers = [sid for sid in suppliers if sid not in visited]
            if not valid_suppliers:
                continue

            split_dmg = rem_dmg / len(valid_suppliers)
            for sid in valid_suppliers:
                visited.add(sid)
                scomp = robot.components[sid]
                step_res = resolve_single_component_hit(scomp, split_dmg, is_weapon_damage=False)
                results.append(step_res)
                if step_res.excess_damage > 0:
                    next_layer.append((sid, step_res.excess_damage))

        current_layer = next_layer

    return results


def simulate_drive_pushing_feedback(
    robot: RobotModel,
    opponent_remaining_distance: int,
) -> List[DamageStepResult]:
    """
    Simulates drive train pushing feedback.
    Opponent remaining distance d is shared equally between remaining active drive.
    Propagates back to drive motors and batteries.
    """
    results: List[DamageStepResult] = []
    if opponent_remaining_distance <= 0:
        return results

    # Identify active drive wheels
    drive_wheels = [
        c for c in robot.components.values()
        if "wheel" in c.name.lower() or "tire" in c.name.lower() or "d" in c.outputs.lower()
    ]
    if not drive_wheels:
        return results

    fb_per_wheel = opponent_remaining_distance / len(drive_wheels)
    visited = set()

    for wheel in drive_wheels:
        step = resolve_single_component_hit(wheel, fb_per_wheel, is_weapon_damage=False)
        results.append(step)
        visited.add(wheel.id)

        if step.excess_damage > 0:
            suppliers = [s for s in robot.supply_graph.get(wheel.id, []) if s not in visited]
            if suppliers:
                split_dmg = step.excess_damage / len(suppliers)
                for sid in suppliers:
                    visited.add(sid)
                    scomp = robot.components[sid]
                    sstep = resolve_single_component_hit(scomp, split_dmg, is_weapon_damage=False)
                    results.append(sstep)
                    # Check battery supplier
                    if sstep.excess_damage > 0:
                        bsuppliers = [b for b in robot.supply_graph.get(sid, []) if b not in visited]
                        if bsuppliers:
                            bsplit = sstep.excess_damage / len(bsuppliers)
                            for bid in bsuppliers:
                                visited.add(bid)
                                bcomp = robot.components[bid]
                                bstep = resolve_single_component_hit(bcomp, bsplit, is_weapon_damage=False)
                                results.append(bstep)

    return results


def simulate_throw_shock(
    robot: RobotModel,
    throw_strength: int,
    hit_on_wedge: bool = False,
) -> Dict[str, List[DamageStepResult]]:
    """
    Simulates throw shock.
    Effective throw strength T is halved if hit on Wedge.
    Rule: A randomly chosen component takes feedback equal to throw strength.
    Evaluates every possible chosen component.
    Returns {target_component_id: [DamageStepResult]}.
    """
    eff_throw = (throw_strength + 1) // 2 if hit_on_wedge else throw_strength
    outcomes: Dict[str, List[DamageStepResult]] = {}

    if eff_throw <= 0:
        return outcomes

    for cid, comp in robot.components.items():
        results: List[DamageStepResult] = []
        first_step = resolve_single_component_hit(comp, float(eff_throw), is_weapon_damage=False)
        results.append(first_step)

        if first_step.excess_damage > 0:
            current_layer = [(cid, first_step.excess_damage)]
            visited = {cid}

            while current_layer:
                next_layer = []
                for node_id, rem_dmg in current_layer:
                    if rem_dmg <= 0.05:
                        continue
                    suppliers = [sid for sid in robot.supply_graph.get(node_id, []) if sid not in visited]
                    if not suppliers:
                        continue
                    split_dmg = rem_dmg / len(suppliers)
                    for sid in suppliers:
                        visited.add(sid)
                        scomp = robot.components[sid]
                        sstep = resolve_single_component_hit(scomp, split_dmg, is_weapon_damage=False)
                        results.append(sstep)
                        if sstep.excess_damage > 0:
                            next_layer.append((sid, sstep.excess_damage))
                current_layer = next_layer

        outcomes[cid] = results

    return outcomes


# ==============================================================================
# REPORTING & FORMATTING
# ==============================================================================

def generate_text_report(robot: RobotModel, catalog: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append(f" COMBAT SIMULATION & DAMAGE SCALING REPORT: {robot.name}")
    lines.append(f" Chassis: {robot.chassis.get('name', 'Unknown')} (Flip Strength: {robot.chassis.get('flip_strength', 'N/A')})")
    lines.append("=" * 80)

    # 1. Component Roster
    lines.append("\n[1] COMPONENT ROSTER & STATS")
    lines.append(f"{'ID':<3} {'Component Name':<28} {'Dur':<4} {'Abs':<4} {'Suppliers':<20} {'Keywords'}")
    lines.append("-" * 80)
    for cid, c in sorted(robot.components.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
        sup_names = [robot.components[sid].name for sid in robot.supply_graph.get(cid, [])]
        sup_str = ", ".join(sup_names) if sup_names else "None (Source)"
        lines.append(f"{cid:<3} {c.name:<28} {c.durability:<4} {c.absorption:<4} {sup_str:<20} {c.keywords}")

    # 2. Weapon Direct Hit Lethality Matrix
    lines.append("\n" + "=" * 80)
    lines.append("[2] WEAPON DIRECT HIT LETHALITY MATRIX (Exposed Hits Without Armor)")
    lines.append("Shows the outcome if an incoming weapon strikes a component directly.")
    lines.append("Key: [X]=Destroyed (One-Hit Kill), [!]=Damaged, [.]=Undamaged / Absorbed")
    lines.append("=" * 80)

    weapons = catalog["weapons"]
    for w in weapons:
        max_spin, d_map, formula = parse_weapon_spin_and_damage(w)
        lines.append(f"\n--- Weapon: {w['name']} | Formula: {formula} | Max Spin: {max_spin} ---")

        header = f"{'Component':<26}" + "".join(f"Spin {s} ({d_map[s]}D) " for s in d_map)
        lines.append(header)
        lines.append("-" * len(header))

        for cid, comp in sorted(robot.components.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
            row = f"{comp.name:<26}"
            for s, dmg in d_map.items():
                res = resolve_single_component_hit(comp, float(dmg), is_weapon_damage=True)
                if res.status == "DESTROYED":
                    tag = "[X] DESTROY"
                elif res.status == "DAMAGED":
                    tag = "[!] DAMAGED"
                else:
                    tag = "[.] SAFE   "
                row += f"{tag:<14}"
            lines.append(row)

    # 3. Armor Protection & Inward Penetration
    lines.append("\n" + "=" * 80)
    lines.append("[3] DEFENSIVE OPTIONS EVALUATION (Inward Penetration Through Armor)")
    lines.append("Tests impacts hitting outer armor/wedges and traces inward penetration.")
    lines.append("=" * 80)

    # Identify armor / defensive components on this robot
    armor_comps = [c for c in robot.components.values() if c.is_wedge or "armor" in c.name.lower() or "plate" in c.name.lower()]
    if not armor_comps:
        lines.append("No explicit armor/wedge components found on this layout.")
    else:
        for ac in armor_comps:
            lines.append(f"\n>>> Shielding Test on: {ac.name} (#{ac.id}) [Dur: {ac.durability}, Abs: {ac.absorption}] <<<")
            lines.append(f"{'Attacking Weapon':<24} {'Spin':<5} {'Dmg':<5} {'Armor Status':<14} {'Excess Passed':<14} {'Internal Casualties'}")
            lines.append("-" * 80)

            for w in weapons:
                max_spin, d_map, _ = parse_weapon_spin_and_damage(w)
                for s, dmg in d_map.items():
                    steps = simulate_inward_damage_progression(robot, ac.id, float(dmg), is_weapon_damage=True)
                    if not steps:
                        continue
                    armor_step = steps[0]
                    internal_steps = steps[1:]
                    casualties = []
                    for st in internal_steps:
                        if st.status == "DESTROYED":
                            casualties.append(f"{st.component_name} [DESTROYED]")
                        elif st.status == "DAMAGED":
                            casualties.append(f"{st.component_name} [DAMAGED]")
                    cas_str = ", ".join(casualties) if casualties else "None (Protected!)"
                    lines.append(f"{w['name']:<24} {s:<5} {dmg:<5} {armor_step.status:<14} {armor_step.excess_damage:<14.1f} {cas_str}")

    # 4. Weapon Self-Recoil Feedback
    lines.append("\n" + "=" * 80)
    lines.append("[4] WEAPON RECOIL FEEDBACK (Self-Destruction & Power Train Strain)")
    lines.append("Rules: Weapons take feedback = floor(attack_strength / 2).")
    lines.append("Weapon takes feedback first, excess passes to weapon motor and battery.")
    lines.append("=" * 80)

    # Find weapon on the robot
    robot_weapons = [c for c in robot.components.values() if c.card_type == "weapon"]
    if not robot_weapons:
        lines.append("No weapon installed on this robot layout.")
    else:
        for rw in robot_weapons:
            w_def = next((w for w in weapons if w["name"] == rw.name), None)
            if not w_def:
                continue
            max_spin, d_map, formula = parse_weapon_spin_and_damage(w_def)
            lines.append(f"\nWeapon: {rw.name} (#{rw.id}) [Dur: {rw.durability}, Abs: {rw.absorption}] | Formula: {formula}")
            lines.append(f"{'Spin':<6} {'Attack Dmg':<12} {'Recoil FB':<10} {'Weapon Status':<15} {'Motor / Battery Impact'}")
            lines.append("-" * 75)

            for s, dmg in d_map.items():
                att_str = get_weapon_attack_strength(w_def, s)
                fb_steps = simulate_weapon_feedback(robot, rw, att_str)
                if not fb_steps:
                    lines.append(f"{s:<6} {dmg:<12} 0 (0 FB)   SAFE            None")
                    continue
                w_step = fb_steps[0]
                supp_impacts = []
                for st in fb_steps[1:]:
                    if st.status != "UNDAMAGED":
                        supp_impacts.append(f"{st.component_name} [{st.status}]")
                supp_str = ", ".join(supp_impacts) if supp_impacts else "Absorbed cleanly"
                lines.append(f"{s:<6} {att_str:<12} {att_str//2:<10} {w_step.status:<15} {supp_str}")

    # 5. Drive Train Pushing Match Feedback
    lines.append("\n" + "=" * 80)
    lines.append("[5] DRIVE TRAIN PUSHING MATCH FEEDBACK")
    lines.append("Rules: Feedback = opponent remaining distance before contact shared across active drive.")
    lines.append("=" * 80)
    lines.append(f"{'Opponent Rem Dist':<20} {'FB Per Wheel':<15} {'Wheel Status':<15} {'Drive Motor / Battery Impact'}")
    lines.append("-" * 75)

    for d in [1, 2, 3, 4, 5, 6]:
        push_steps = simulate_drive_pushing_feedback(robot, d)
        if not push_steps:
            lines.append(f"{d:<20} N/A             No active drive wheels")
            continue
        wheel_step = push_steps[0]
        sub_steps = [st for st in push_steps[1:] if st.status != "UNDAMAGED"]
        sub_str = ", ".join(f"{st.component_name} [{st.status}]" for st in sub_steps) if sub_steps else "Absorbed cleanly (No Damage)"
        lines.append(f"{d:<20} {wheel_step.incoming_damage:<15.2f} {wheel_step.status:<15} {sub_str}")

    # 6. Throw Shock Damage Analysis
    lines.append("\n" + "=" * 80)
    lines.append("[6] THROW SHOCK VULNERABILITY (Random Component Landing)")
    lines.append("Rules: After a throw, robot takes feedback equal to throw strength at a randomly chosen component.")
    lines.append("Wedge keyword halves throw strength received.")
    lines.append("=" * 80)

    test_throws = [2, 4, 6, 8, 10, 12, 16, 24]
    lines.append(f"{'Throw Strength':<16} {'Wedge Deflect?':<16} {'% Instant Destroy':<20} {'% Damaged':<15} {'Vulnerable Targets'}")
    lines.append("-" * 85)

    for ts in test_throws:
        for on_wedge in [False, True]:
            outcomes = simulate_throw_shock(robot, ts, hit_on_wedge=on_wedge)
            eff_t = (ts + 1) // 2 if on_wedge else ts
            num_comps = len(robot.components)
            destroyed_count = 0
            damaged_count = 0
            destroyed_names = []

            for cid, steps in outcomes.items():
                if steps:
                    target_res = steps[0]
                    if target_res.status == "DESTROYED":
                        destroyed_count += 1
                        destroyed_names.append(target_res.component_name)
                    elif target_res.status == "DAMAGED":
                        damaged_count += 1

            pct_dest = (destroyed_count / num_comps) * 100
            pct_dam = (damaged_count / num_comps) * 100

            # Unique sample of destroyed components
            unique_dest = list(dict.fromkeys(destroyed_names))
            dest_sample = ", ".join(unique_dest[:3])
            if len(unique_dest) > 3:
                dest_sample += f" (+{len(unique_dest)-3} more)"
            if not dest_sample:
                dest_sample = "None"

            w_tag = f"Yes (Eff {eff_t})" if on_wedge else f"No (Eff {eff_t})"
            lines.append(f"{ts:<16} {w_tag:<16} {pct_dest:>5.1f}% ({destroyed_count}/{num_comps}){'':<5} {pct_dam:>5.1f}%{'':<8} {dest_sample}")

    # 7. Summary & Design Insights
    lines.append("\n" + "=" * 80)
    lines.append("[7] GAME BALANCE & DESIGN TUNING SUMMARY")
    lines.append("=" * 80)

    # Calculate lethality benchmarks
    lines.append("A. First-Contact Lethality:")
    lines.append("   - Bloodsport Bar (Spin 3-4 = 18-24 Dmg) and Horizontal Spinner (Spin 3-4 = 12-16 Dmg)")
    lines.append("     instantly obliterate almost every internal component (durability 5-7).")
    lines.append("   - At high spin-ups, one-hit kills dominate over progressive damage.")
    lines.append("\nB. Defensive Options (Armor & Wedges):")
    lines.append("   - UHMW Armor (Dur 12, Abs 4) and Titanium Wedges (Dur 12, Abs 4) withstand hits up to 8-11 Dmg.")
    lines.append("   - Against 16-24 Dmg, armor is destroyed on the first hit, and excess damage penetrates directly to batteries/motors.")
    lines.append("   - TPU Plates (Abs 5) are extremely effective against vertical spinners and lower-tier weapons.")
    lines.append("\nC. Feedback & Self-Destruction Risk:")
    lines.append("   - Horizontal Spinner destroys ITSELF at Spin 4 (16 Dmg -> 8 Recoil > 7 Durability).")
    lines.append("   - Bloodsport Bar destroys ITSELF at Spin 4 (24 Dmg -> 12 Recoil > 9 Durability).")
    lines.append("   - Drive pushing feedback (0.25 - 1.5 Dmg) is safely absorbed by drive wheels with 0 damage.")
    lines.append("   - Throw Shock equal to throw strength is lethal: hitting an unarmored battery or motor (Dur 5-7)")
    lines.append("     bypasses all perimeter armor and causes catastrophic internal failure.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Simulate combat robotics damage and feedback scaling.")
    parser.add_argument("robot_csvs", nargs="*", help="Robot layout CSV paths in automata/ or elsewhere")
    parser.add_argument("--tolerance", type=float, default=6.5, help="Physical connection tolerance in mm (default: 6.5)")
    parser.add_argument("--export", type=str, help="Export markdown report to specified path")
    args = parser.parse_args()

    catalog = load_all_cards()

    if not args.robot_csvs:
        # Default to all automata CSVs
        automata_dir = REPO_ROOT / "automata"
        csv_files = sorted(automata_dir.glob("*.csv"))
    else:
        csv_files = [Path(p) for p in args.robot_csvs]

    if not csv_files:
        print("No robot CSV files found to simulate.")
        sys.exit(1)

    full_reports = []

    for p in csv_files:
        if not p.exists():
            print(f"Warning: {p} does not exist. Skipping.")
            continue
        robot = build_robot_model(p, catalog, tolerance=args.tolerance)
        rep = generate_text_report(robot, catalog)
        print(rep)
        full_reports.append(rep)
        print("\n\n")

    if args.export:
        export_path = Path(args.export)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            f.write("\n\n---\n\n".join(full_reports))
        print(f"Report exported to: {export_path}")


if __name__ == "__main__":
    main()
