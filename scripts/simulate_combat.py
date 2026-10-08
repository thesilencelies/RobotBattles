#!/usr/bin/env python3
"""
Combat Simulation Script for Robot Battles
Tests weapon impacts, spin-up scaling, feedback propagation, and throw shock
against robot layouts loaded from CSV files.
Generates an interactive HTML report and text summary in scripts/output/.
"""

from __future__ import annotations

import argparse
import html
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
    r"""
    Parses weapon keywords and outputs into max spin and a map of {spin_level: damage}.
    Returns (max_spin, damage_map, notation_desc).
    Rules:
      - kXW -> k * X
      - kXWW -> k*X + 1 (X*W + W)
      - XXW -> X^2 * W = X^2
      - W+ -> count of W's
      - (\d+)W with lifter/flipper text -> deals 0 direct component damage, but has throw strength
    """
    keywords = weapon.get("keywords", "")
    outputs = weapon.get("outputs", "").strip().upper()
    text = weapon.get("text", "")

    spin_match = re.search(r"Spin up\s*\(\s*(\d+)", keywords, re.IGNORECASE)
    if spin_match:
        max_spin = int(spin_match.group(1))
    else:
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
            if extra_w > 0:
                formula_desc = f"{k_str} + {extra_w}"
            else:
                formula_desc = f"{k_str}"
        elif re.match(r"^W+$", outputs):
            damage_map[s] = len(outputs)
            formula_desc = f"{len(outputs)} flat ({outputs})"
        elif re.match(r"^(\d+)W$", outputs):
            val = int(re.match(r"^(\d+)W$", outputs).group(1))
            damage_map[s] = val
            formula_desc = f"{val} flat"
        else:
            damage_map[s] = s
            formula_desc = f"{outputs}"

    return max_spin, damage_map, formula_desc


def get_weapon_attack_strength(weapon: Dict[str, Any], spin_level: int) -> int:
    """Returns the attack strength (used for throw strength and feedback)."""
    outputs = weapon.get("outputs", "").strip().upper()
    text = weapon.get("text", "").lower()

    if "deals no damage" in text:
        m = re.search(r"(\d+)W", outputs)
        if m:
            return int(m.group(1))
        return 5

    _, d_map, _ = parse_weapon_spin_and_damage(weapon)
    return d_map.get(spin_level, 0)


def boxes_touch(
    b1: Tuple[float, float, float, float],
    b2: Tuple[float, float, float, float],
    tolerance: float = 3.0,
) -> bool:
    """Checks if bounding boxes touch within tolerance (mm)."""
    x1_min, y1_min, x1_max, y1_max = b1
    x2_min, y2_min, x2_max, y2_max = b2
    if x1_max < x2_min - tolerance or x2_max < x1_min - tolerance:
        return False
    if y1_max < y2_min - tolerance or y2_max < y1_min - tolerance:
        return False
    return True


def build_robot_model(csv_path: Path, catalog: Dict[str, Any], tolerance: float = 3.0) -> RobotModel:
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

        for nid in comp.connections:
            neighbor = components[nid]
            nout = neighbor.outputs.upper()
            can_supply = any(nt in nout for nt in needed_types)
            if can_supply:
                if nid not in supply_graph[cid]:
                    supply_graph[cid].append(nid)
                if cid not in reverse_supply[nid]:
                    reverse_supply[nid].append(cid)

    boxes = {cid: comp.box for cid, comp in components.items()}
    if boxes:
        layout_min_x = min(b[0] for b in boxes.values())
        layout_min_y = min(b[1] for b in boxes.values())
        layout_max_x = max(b[2] for b in boxes.values())
        layout_max_y = max(b[3] for b in boxes.values())
    else:
        layout_min_x = layout_min_y = layout_max_x = layout_max_y = 0.0

    outer_components: List[str] = []
    for cid, comp in components.items():
        is_protective = (
            comp.is_wedge
            or comp.is_forks
            or "armor" in comp.name.lower()
            or "plate" in comp.name.lower()
            or "fork" in comp.name.lower()
        )
        is_outer_mech = "wheel" in comp.name.lower() or comp.card_type == "weapon"
        b = comp.box
        is_boundary = (
            abs(b[0] - layout_min_x) <= 2.0
            or abs(b[1] - layout_min_y) <= 2.0
            or abs(b[2] - layout_max_x) <= 2.0
            or abs(b[3] - layout_max_y) <= 2.0
        )
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
    eff_dur = comp.durability
    if comp.is_fragile and is_weapon_damage:
        eff_dur = 1

    if damage > eff_dur:
        status = "DESTROYED"
        absorbed = float(eff_dur)
        excess = max(0.0, damage - absorbed)
    else:
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
    results: List[DamageStepResult] = []
    if initial_damage <= 0:
        return results

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

            candidate_inward = []
            for nid in robot.adjacency[src_id]:
                if nid not in visited:
                    ncomp = robot.components[nid]
                    n_dist = math.hypot(ncomp.x - cx, ncomp.y - cy)
                    candidate_inward.append((nid, n_dist))

            if not candidate_inward:
                continue

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
    results: List[DamageStepResult] = []
    recoil_feedback = attack_strength // 2
    if recoil_feedback <= 0:
        return results

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
    results: List[DamageStepResult] = []
    if opponent_remaining_distance <= 0:
        return results

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
# FEEDBACK CHAIN SIMULATION LOGIC
# ==============================================================================

@dataclass
class ChainStepResult:
    feedback_in: int
    component_steps: List[Optional[DamageStepResult]]
    category: str  # SAFE, DAMAGE_WITHOUT_FAILURE, SINK_FAILURE, UPSTREAM_FAILURE, ROOT_FAILURE
    summary_text: str


@dataclass
class SubsystemChain:
    name: str
    sink_component: PlacedComponent
    components_path: List[PlacedComponent]  # [End, Intermediate, ..., Root Battery]
    escalation_results: List[ChainStepResult]
    safe_window: Tuple[int, int]  # (min_fb, max_fb)
    damage_without_fail_window: Tuple[Optional[int], Optional[int]]
    sink_failure_threshold: Optional[int]
    upstream_failure_threshold: Optional[int]
    root_failure_threshold: Optional[int]


def extract_robot_subsystem_chains(robot: RobotModel, max_fb: int = 20) -> List[SubsystemChain]:
    """Identifies functional supply chains (Weapons, Lifters, Wheels) and traces feedback."""
    chains: List[SubsystemChain] = []
    seen_sinks = set()

    for cid, comp in robot.components.items():
        is_sink = comp.card_type == "weapon" or "wheel" in comp.name.lower() or "lifter" in comp.name.lower()
        if not is_sink or cid in seen_sinks:
            continue
        seen_sinks.add(cid)

        # Build path up supply tree
        path = [comp]
        curr = cid
        visited_in_path = {cid}
        while True:
            sups = robot.supply_graph.get(curr, [])
            valid_sups = [sid for sid in sups if sid not in visited_in_path]
            if not valid_sups:
                break
            next_sid = valid_sups[0]
            visited_in_path.add(next_sid)
            path.append(robot.components[next_sid])
            curr = next_sid

        # Simulate escalation FB = 1..max_fb
        steps_list: List[ChainStepResult] = []
        safe_fb: List[int] = []
        damage_without_fail_fb: List[int] = []
        first_sink_fail: Optional[int] = None
        first_upstream_fail: Optional[int] = None
        first_root_fail: Optional[int] = None

        for fb in range(1, max_fb + 1):
            curr_dmg = float(fb)
            comp_steps: List[Optional[DamageStepResult]] = []

            for i, c in enumerate(path):
                if curr_dmg > 0:
                    step_res = resolve_single_component_hit(c, curr_dmg, is_weapon_damage=False)
                    comp_steps.append(step_res)
                    curr_dmg = step_res.excess_damage
                else:
                    comp_steps.append(None)

            statuses = [r.status if r else "SAFE" for r in comp_steps]
            any_dest = any(s == "DESTROYED" for s in statuses)
            any_dam = any(s == "DAMAGED" for s in statuses)

            if not any_dest and not any_dam:
                cat = "SAFE"
                safe_fb.append(fb)
                desc = "All components absorbed feedback cleanly (0 Damage)"
            elif any_dam and not any_dest:
                cat = "DAMAGE_WITHOUT_FAILURE"
                damage_without_fail_fb.append(fb)
                damaged_names = [path[i].name for i, s in enumerate(statuses) if s == "DAMAGED"]
                desc = f"Damage without failure: {', '.join(damaged_names)} took damage but survived!"
            elif statuses[0] == "DESTROYED" and all(s != "DESTROYED" for s in statuses[1:]):
                cat = "SINK_FAILURE"
                if first_sink_fail is None:
                    first_sink_fail = fb
                desc = f"End component {path[0].name} destroyed; upstream components survived!"
            elif len(statuses) > 1 and statuses[1] == "DESTROYED" and (len(statuses) <= 2 or statuses[2] != "DESTROYED"):
                cat = "UPSTREAM_FAILURE"
                if first_upstream_fail is None:
                    first_upstream_fail = fb
                desc = f"Upstream failure: {path[1].name} destroyed by passed feedback!"
            elif len(statuses) > 2 and statuses[2] == "DESTROYED":
                cat = "ROOT_FAILURE"
                if first_root_fail is None:
                    first_root_fail = fb
                desc = f"Root battery {path[-1].name} destroyed by passed feedback!"
            else:
                cat = "SINK_FAILURE"
                desc = "Component failure in chain"

            steps_list.append(ChainStepResult(
                feedback_in=fb,
                component_steps=comp_steps,
                category=cat,
                summary_text=desc,
            ))

        safe_window = (min(safe_fb), max(safe_fb)) if safe_fb else (0, 0)
        dwf_window = (min(damage_without_fail_fb), max(damage_without_fail_fb)) if damage_without_fail_fb else (None, None)

        chain_name = f"{comp.name} Subsystem"
        chains.append(SubsystemChain(
            name=chain_name,
            sink_component=comp,
            components_path=path,
            escalation_results=steps_list,
            safe_window=safe_window,
            damage_without_fail_window=dwf_window,
            sink_failure_threshold=first_sink_fail,
            upstream_failure_threshold=first_upstream_fail,
            root_failure_threshold=first_root_fail,
        ))

    return chains


# ==============================================================================
# HTML REPORT GENERATOR
# ==============================================================================

def generate_html_report(robots: List[RobotModel], catalog: Dict[str, Any]) -> str:
    weapons = catalog["weapons"]

    robot_tabs_nav = []
    robot_tabs_content = []

    # Compile list of all weapon attack configurations (Weapon Name @ Spin Level)
    attack_configs = []
    for w in weapons:
        max_s, d_map, formula = parse_weapon_spin_and_damage(w)
        for s, dmg in d_map.items():
            spin_label = f"Spin {s}" if max_s > 0 else "Base"
            label = f"{w['name']} ({spin_label}: {dmg} Dmg)"
            attack_configs.append({
                "weapon_name": w["name"],
                "spin": s,
                "damage": dmg,
                "label": label,
                "formula": formula,
            })

    for idx, robot in enumerate(robots):
        active_cls = "active" if idx == 0 else ""
        slug = re.sub(r"[^a-zA-Z0-9_]", "_", robot.name)

        robot_tabs_nav.append(
            f'<button class="tab-btn {active_cls}" onclick="switchTab(\'{slug}\')">{html.escape(robot.name)}</button>'
        )

        sections = []

        # Robot Header Info
        sections.append(f"""
        <div class="robot-header-card">
          <div class="robot-title-row">
            <h2>{html.escape(robot.name)}</h2>
            <span class="chassis-badge">Chassis: {html.escape(str(robot.chassis.get('name', 'Chassis')))} (Flip Strength: {robot.chassis.get('flip_strength', 'N/A')})</span>
          </div>
          <div class="metrics-grid">
            <div class="metric-box">
              <span class="metric-label">Total Components</span>
              <span class="metric-val">{len(robot.components)}</span>
            </div>
            <div class="metric-box">
              <span class="metric-label">Placement Dimensions</span>
              <span class="metric-val">{robot.chassis.get('template', 'Standard')} Chassis</span>
            </div>
          </div>
        </div>
        """)

        # ----------------------------------------------------------------------
        # SECTION 1: SINGLE UNIFIED DIRECT HIT MATRIX (PERIMETER ONLY)
        # ----------------------------------------------------------------------
        outer_ids = set(robot.outer_components)
        edge_comps = [c for c in robot.components.values() if c.id in outer_ids]
        if not edge_comps:
            edge_comps = list(robot.components.values())

        # Sort spatially: Front -> Back (comp.y), then Left -> Right (comp.x)
        edge_comps.sort(key=lambda c: (c.y, c.x))

        def get_comp_role_tag(c: PlacedComponent) -> str:
            if c.card_type == "weapon":
                return "Weapon"
            if c.is_wedge:
                return "Wedge"
            if c.is_forks:
                return "Forks"
            if "wheel" in c.name.lower():
                return "Wheel"
            if "armor" in c.name.lower() or "plate" in c.name.lower():
                return "Armor"
            return "Perimeter"

        # Header columns: Component Name + Dur/Abs + Role
        matrix_th_cols = "".join(
            f'<th>'
            f'<div class="th-comp-name">{html.escape(c.name)}</div>'
            f'<div class="th-comp-stats">#{c.id} · D:{c.durability} A:{c.absorption}</div>'
            f'<span class="badge-role">{get_comp_role_tag(c)}</span>'
            f'</th>'
            for c in edge_comps
        )

        matrix_rows = []
        for atk in attack_configs:
            dmg = atk["damage"]
            td_cells = []
            for c in edge_comps:
                res = resolve_single_component_hit(c, float(dmg), is_weapon_damage=True)
                if res.status == "DESTROYED":
                    cell_html = f'<span class="matrix-badge destroy" title="{c.name} (#{c.id}): DESTROYED (Hits for {dmg} vs Dur {res.effective_durability})">DESTROY</span>'
                elif res.status == "DAMAGED":
                    cell_html = f'<span class="matrix-badge damaged" title="{c.name} (#{c.id}): DAMAGED (Hits for {dmg}, absorbs {c.absorption})">DAMAGED</span>'
                else:
                    cell_html = f'<span class="matrix-badge safe" title="{c.name} (#{c.id}): SAFE (Absorbed)">SAFE</span>'
                td_cells.append(f"<td>{cell_html}</td>")

            matrix_rows.append(f"""
            <tr>
              <th class="matrix-row-header">
                <span class="atk-name">{html.escape(atk['weapon_name'])}</span>
                <span class="atk-badge">{html.escape(atk['label'].split('(')[-1].rstrip(')'))}</span>
              </th>
              {''.join(td_cells)}
            </tr>
            """)

        num_internal = len(robot.components) - len(edge_comps)
        sections.append(f"""
        <div class="section-container">
          <div class="section-header-flex">
            <div>
              <h3 class="section-title">🎯 Direct Hit Lethality Matrix (Perimeter Components)</h3>
              <p class="section-desc">Direct hit outcomes across exposed perimeter components ({len(edge_comps)} edge components that can receive direct contact on an undamaged robot). Internal components ({num_internal} batteries, ESCs, motors) are shielded behind this perimeter and only take damage via punch-through penetration or feedback.</p>
            </div>
            <div class="legend-box">
              <span class="matrix-badge safe">SAFE</span>
              <span class="matrix-badge damaged">DAMAGED</span>
              <span class="matrix-badge destroy">DESTROYED</span>
            </div>
          </div>
          <div class="table-scroll-container">
            <table class="matrix-table">
              <thead>
                <tr>
                  <th class="matrix-corner">Weapon Impact</th>
                  {matrix_th_cols}
                </tr>
              </thead>
              <tbody>
                {''.join(matrix_rows)}
              </tbody>
            </table>
          </div>
        </div>
        """)

        # ----------------------------------------------------------------------
        # SECTION 2: THE FEEDBACK CHAIN ANALYSIS (CORE FEATURE)
        # ----------------------------------------------------------------------
        subsystem_chains = extract_robot_subsystem_chains(robot, max_fb=20)

        # 2A. Executive Chain Thresholds Summary Table
        summary_rows = []
        for chain in subsystem_chains:
            path_str = " → ".join(f"{c.name} [D:{c.durability}, A:{c.absorption}]" for c in chain.components_path)

            safe_str = f"FB {chain.safe_window[0]}–{chain.safe_window[1]}" if chain.safe_window[1] > 0 else "None"
            dwf_str = f"FB {chain.damage_without_fail_window[0]}–{chain.damage_without_fail_window[1]}" if chain.damage_without_fail_window[0] is not None else "None"
            sink_str = f"FB {chain.sink_failure_threshold}" if chain.sink_failure_threshold is not None else "None"
            up_str = f"FB {chain.upstream_failure_threshold}" if chain.upstream_failure_threshold is not None else "None"
            root_str = f"FB {chain.root_failure_threshold}" if chain.root_failure_threshold is not None else "None"

            summary_rows.append(f"""
            <tr>
              <td><strong>{html.escape(chain.name)}</strong></td>
              <td class="chain-path-cell"><code>{html.escape(path_str)}</code></td>
              <td><span class="badge-safe">{safe_str}</span></td>
              <td><span class="badge-warning">{dwf_str}</span></td>
              <td><span class="badge-danger">{sink_str}</span></td>
              <td><span class="badge-destroy-heavy">{up_str}</span></td>
              <td><span class="badge-destroy-heavy">{root_str}</span></td>
            </tr>
            """)

        # 2B. Step-by-Step Chain Escalation Tables
        chain_detail_blocks = []
        for chain in subsystem_chains:
            step_rows = []
            for item in chain.escalation_results:
                fb = item.feedback_in
                st_cells = []
                for idx_c, st in enumerate(item.component_steps):
                    c_def = chain.components_path[idx_c]
                    if st is None:
                        st_cells.append('<td class="stat-col"><span class="badge-safe">SAFE (0 in)</span></td>')
                    elif st.status == "DESTROYED":
                        st_cells.append(f'<td class="stat-col"><span class="badge-danger">DESTROYED</span> <br><small>Passes {st.excess_damage:.1f}</small></td>')
                    elif st.status == "DAMAGED":
                        st_cells.append(f'<td class="stat-col"><span class="badge-warning">DAMAGED</span> <br><small>Passes {st.excess_damage:.1f}</small></td>')
                    else:
                        st_cells.append(f'<td class="stat-col"><span class="badge-safe">UNDAMAGED</span> <br><small>Passes {st.excess_damage:.1f}</small></td>')

                cat_badge_cls = {
                    "SAFE": "badge-safe",
                    "DAMAGE_WITHOUT_FAILURE": "badge-warning",
                    "SINK_FAILURE": "badge-danger",
                    "UPSTREAM_FAILURE": "badge-destroy-heavy",
                    "ROOT_FAILURE": "badge-destroy-heavy",
                }.get(item.category, "badge-muted")

                step_rows.append(f"""
                <tr>
                  <td class="stat-col"><strong>FB {fb}</strong></td>
                  {''.join(st_cells)}
                  <td><span class="{cat_badge_cls}">{item.category.replace('_', ' ')}</span></td>
                  <td class="desc-cell">{html.escape(item.summary_text)}</td>
                </tr>
                """)

            comp_headers = "".join(f"<th>Level {i}: {html.escape(c.name)} <br><small>[D:{c.durability}, A:{c.absorption}]</small></th>" for i, c in enumerate(chain.components_path))

            chain_detail_blocks.append(f"""
            <div class="chain-card">
              <div class="chain-header">
                <h4>🔗 {html.escape(chain.name)} (Escalation Trace)</h4>
                <div class="chain-tags">
                  <span class="tag-primary">Safe: FB {chain.safe_window[0]}–{chain.safe_window[1]}</span>
                  <span class="tag-warning">Damage Without Fail: FB {chain.damage_without_fail_window[0]}–{chain.damage_without_fail_window[1]}</span>
                  <span class="tag-danger">First Fail: FB {chain.sink_failure_threshold}</span>
                  <span class="tag-danger">Upstream Fail: FB {chain.upstream_failure_threshold}</span>
                </div>
              </div>
              <div class="table-responsive">
                <table class="report-table">
                  <thead>
                    <tr>
                      <th style="width: 70px;">Feedback</th>
                      {comp_headers}
                      <th style="width: 170px;">Chain State</th>
                      <th>Effect Narrative</th>
                    </tr>
                  </thead>
                  <tbody>
                    {''.join(step_rows)}
                  </tbody>
                </table>
              </div>
            </div>
            """)

        sections.append(f"""
        <div class="section-container">
          <h3 class="section-title">⚡ Feedback Chain Escalation & Failure Analysis</h3>
          <p class="section-desc">
            Traces unabsorbed shock/strain traveling backwards from end components up to their supplying motors and batteries.
            Shows exactly at what feedback numbers components take damage without failing, and at what numbers upstream components fail down the line.
          </p>

          <div class="sub-section-title">Summary of Critical Thresholds Across Subsystems</div>
          <div class="table-responsive" style="margin-bottom: 24px;">
            <table class="report-table">
              <thead>
                <tr>
                  <th>Subsystem Chain</th>
                  <th>Supply Path (End → Intermediate → Root)</th>
                  <th>Safe Window (0 Dmg)</th>
                  <th>Damage Without Failure</th>
                  <th>End Component Fails</th>
                  <th>Upstream Motor/Servo Fails</th>
                  <th>Root Battery Fails</th>
                </tr>
              </thead>
              <tbody>
                {''.join(summary_rows)}
              </tbody>
            </table>
          </div>

          <div class="sub-section-title">Step-by-Step Chain Escalation Logs (FB 1 to 20)</div>
          {''.join(chain_detail_blocks)}
        </div>
        """)

        # ----------------------------------------------------------------------
        # SECTION 3: SIMPLIFIED THROW SHOCK CHART (EFFECTIVE THROW STRENGTH)
        # ----------------------------------------------------------------------
        throw_rows = []
        for eff_t in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 20, 24]:
            outcomes = simulate_throw_shock(robot, eff_t, hit_on_wedge=False)
            num_comps = len(robot.components)
            dest_count = 0
            dam_count = 0
            dest_names = []
            dam_names = []

            for cid, steps in outcomes.items():
                if steps:
                    target_res = steps[0]
                    if target_res.status == "DESTROYED":
                        dest_count += 1
                        dest_names.append(target_res.component_name)
                    elif target_res.status == "DAMAGED":
                        dam_count += 1
                        dam_names.append(target_res.component_name)

            pct_dest = (dest_count / num_comps) * 100
            pct_dam = (dam_count / num_comps) * 100
            pct_safe = max(0.0, 100.0 - pct_dest - pct_dam)

            u_dest = list(dict.fromkeys(dest_names))
            dest_str = ", ".join(u_dest[:3])
            if len(u_dest) > 3:
                dest_str += f" (+{len(u_dest)-3} more)"
            dest_html = f'<span class="tag-danger">{html.escape(dest_str)}</span>' if dest_str else '<span class="tag-success">None</span>'

            u_dam = list(dict.fromkeys(dam_names))
            dam_str = ", ".join(u_dam[:3])
            if len(u_dam) > 3:
                dam_str += f" (+{len(u_dam)-3} more)"
            dam_html = f'<span class="tag-warning">{html.escape(dam_str)}</span>' if dam_str else '<span class="tag-success">None</span>'

            bar_html = f"""
            <div class="progress-container">
              <div class="progress-fill {'danger' if pct_dest > 50 else 'warning' if pct_dest > 0 else 'safe'}" style="width: {pct_dest}%;"></div>
              <span class="progress-text">{pct_dest:.1f}% ({dest_count}/{num_comps})</span>
            </div>
            """

            throw_rows.append(f"""
            <tr>
              <td class="stat-col"><strong>Throw {eff_t}</strong></td>
              <td>{bar_html}</td>
              <td class="stat-col">{pct_dam:.1f}% ({dam_count}/{num_comps})</td>
              <td class="stat-col">{pct_safe:.1f}%</td>
              <td>{dest_html}</td>
              <td>{dam_html}</td>
            </tr>
            """)

        sections.append(f"""
        <div class="section-container">
          <h3 class="section-title">🎲 Effective Throw Shock Damage Chart</h3>
          <p class="section-desc">Shows outcomes when throw shock of a given effective strength lands on a randomly chosen component on the robot mat.</p>
          <div class="table-responsive">
            <table class="report-table">
              <thead>
                <tr>
                  <th style="width: 110px;">Effective Throw</th>
                  <th style="min-width: 170px;">% Instant Destruction</th>
                  <th style="width: 120px;">% Damaged</th>
                  <th style="width: 90px;">% Safe</th>
                  <th>Destroyed Targets</th>
                  <th>Damaged Targets</th>
                </tr>
              </thead>
              <tbody>
                {''.join(throw_rows)}
              </tbody>
            </table>
          </div>
        </div>
        """)

        robot_tabs_content.append(f"""
        <div id="tab-{slug}" class="tab-content {active_cls}">
          {''.join(sections)}
        </div>
        """)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Combat Robotics Balance & Feedback Scaling Report</title>
  <style>
    :root {{
      --bg: #0b0f17;
      --surface: #131b2a;
      --surface-card: #182337;
      --surface-hover: #1f2d46;
      --border: #26354a;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-bg: rgba(56, 189, 248, 0.12);
      --danger: #ef4444;
      --danger-bg: rgba(239, 68, 68, 0.18);
      --warning: #f59e0b;
      --warning-bg: rgba(245, 158, 11, 0.18);
      --success: #10b981;
      --success-bg: rgba(16, 185, 129, 0.18);
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px;
    }}

    .container {{
      max-width: 1550px;
      margin: 0 auto;
    }}

    header {{
      margin-bottom: 20px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }}

    h1 {{
      font-size: 26px;
      color: #fff;
      font-weight: 700;
      margin-bottom: 4px;
    }}

    .subtitle {{
      color: var(--text-muted);
      font-size: 13.5px;
    }}

    .nav-tabs {{
      display: flex;
      gap: 8px;
      margin-bottom: 20px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 8px;
    }}

    .tab-btn {{
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 9px 18px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
      font-size: 13.5px;
      transition: all 0.2s ease;
    }}

    .tab-btn:hover {{
      background: var(--surface-hover);
      color: var(--text);
    }}

    .tab-btn.active {{
      background: var(--primary);
      border-color: var(--primary);
      color: #0b0f17;
    }}

    .tab-content {{ display: none; }}
    .tab-content.active {{ display: block; }}

    .robot-header-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 24px;
    }}

    .robot-title-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 10px;
    }}

    .robot-title-row h2 {{
      font-size: 22px;
      color: #fff;
    }}

    .chassis-badge {{
      background: var(--surface-hover);
      border: 1px solid var(--border);
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 12.5px;
      color: var(--primary);
      font-weight: 600;
    }}

    .metrics-grid {{
      display: flex;
      gap: 16px;
    }}

    .metric-box {{
      background: var(--surface-card);
      border: 1px solid var(--border);
      padding: 8px 14px;
      border-radius: 6px;
    }}

    .metric-label {{
      font-size: 10.5px;
      text-transform: uppercase;
      color: var(--text-muted);
      display: block;
    }}

    .metric-val {{
      font-size: 15px;
      font-weight: 700;
      color: #fff;
    }}

    .section-container {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 24px;
    }}

    .section-title {{
      font-size: 18px;
      color: #fff;
      margin-bottom: 4px;
    }}

    .sub-section-title {{
      font-size: 14.5px;
      color: var(--primary);
      font-weight: 600;
      margin: 16px 0 8px 0;
    }}

    .section-desc {{
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 14px;
    }}

    .section-header-flex {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 10px;
    }}

    .legend-box {{
      display: flex;
      gap: 6px;
      align-items: center;
    }}

    .table-scroll-container {{
      overflow-x: auto;
      max-height: 650px;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
    }}

    .matrix-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 11.5px;
      text-align: center;
    }}

    .matrix-table thead th {{
      position: sticky;
      top: 0;
      background: #101726;
      border-bottom: 2px solid var(--border);
      padding: 8px 6px;
      z-index: 10;
      font-weight: 600;
    }}

    .matrix-corner {{
      position: sticky;
      left: 0;
      top: 0;
      z-index: 20 !important;
      background: #0d131f !important;
      min-width: 220px;
      text-align: left !important;
      padding-left: 12px !important;
    }}

    .matrix-row-header {{
      position: sticky;
      left: 0;
      background: #101726;
      border-right: 2px solid var(--border);
      border-bottom: 1px solid var(--border);
      padding: 7px 12px;
      z-index: 5;
      text-align: left;
      white-space: nowrap;
    }}

    .atk-name {{
      font-weight: 700;
      color: #fff;
      display: block;
      font-size: 12px;
    }}

    .atk-badge {{
      font-size: 10.5px;
      color: var(--primary);
    }}

    .th-comp-name {{
      font-weight: 700;
      color: #fff;
      font-size: 11px;
      white-space: nowrap;
    }}

    .th-comp-stats {{
      font-size: 10px;
      color: var(--text-muted);
      font-weight: normal;
    }}

    .badge-role {{
      display: inline-block;
      margin-top: 3px;
      padding: 1px 6px;
      border-radius: 4px;
      font-size: 9px;
      font-weight: 600;
      background: var(--surface-hover);
      color: var(--primary);
      border: 1px solid var(--border);
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }}

    .matrix-table td {{
      padding: 6px 4px;
      border-bottom: 1px solid rgba(38, 53, 74, 0.4);
      border-right: 1px solid rgba(38, 53, 74, 0.4);
      background: var(--surface);
    }}

    .matrix-badge {{
      display: inline-block;
      width: 100%;
      min-width: 58px;
      padding: 3px 0;
      border-radius: 3px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.3px;
    }}

    .matrix-badge.destroy {{
      background: var(--danger-bg);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.4);
    }}

    .matrix-badge.damaged {{
      background: var(--warning-bg);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.4);
    }}

    .matrix-badge.safe {{
      background: var(--success-bg);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }}

    .table-responsive {{
      overflow-x: auto;
    }}

    .report-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      text-align: left;
    }}

    .report-table th {{
      background: var(--surface-card);
      color: var(--text-muted);
      font-weight: 600;
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }}

    .report-table td {{
      padding: 8px 10px;
      border-bottom: 1px solid rgba(38, 53, 74, 0.5);
      vertical-align: middle;
    }}

    .report-table tbody tr:hover {{
      background: var(--surface-hover);
    }}

    .stat-col {{
      text-align: center;
      font-variant-numeric: tabular-nums;
    }}

    .chain-card {{
      background: var(--surface-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 16px;
    }}

    .chain-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .chain-header h4 {{
      color: #38bdf8;
      font-size: 14px;
    }}

    .chain-tags {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }}

    .chain-path-cell code {{
      background: #0f172a;
      padding: 3px 6px;
      border-radius: 4px;
      color: #38bdf8;
      font-size: 11px;
    }}

    .desc-cell {{
      font-size: 11.5px;
      color: var(--text-muted);
    }}

    .badge-safe {{
      background: var(--success-bg);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
      padding: 2px 7px;
      border-radius: 4px;
      font-weight: 600;
      font-size: 11px;
      display: inline-block;
    }}

    .badge-warning {{
      background: var(--warning-bg);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.4);
      padding: 2px 7px;
      border-radius: 4px;
      font-weight: 600;
      font-size: 11px;
      display: inline-block;
    }}

    .badge-danger {{
      background: var(--danger-bg);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.4);
      padding: 2px 7px;
      border-radius: 4px;
      font-weight: 600;
      font-size: 11px;
      display: inline-block;
    }}

    .badge-destroy-heavy {{
      background: #7f1d1d;
      color: #fecaca;
      border: 1px solid #ef4444;
      padding: 2px 7px;
      border-radius: 4px;
      font-weight: 700;
      font-size: 11px;
      display: inline-block;
    }}

    .tag-primary {{
      background: var(--primary-bg);
      color: var(--primary);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
    }}
    .tag-warning {{
      background: var(--warning-bg);
      color: #fbbf24;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
    }}
    .tag-danger {{
      background: var(--danger-bg);
      color: #f87171;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
    }}
    .tag-success {{
      background: var(--success-bg);
      color: #34d399;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
    }}

    .progress-container {{
      width: 100%;
      min-width: 120px;
      background: #0f172a;
      border-radius: 4px;
      overflow: hidden;
      position: relative;
      height: 18px;
    }}

    .progress-fill {{
      height: 100%;
      transition: width 0.3s ease;
    }}
    .progress-fill.danger {{ background: #ef4444; }}
    .progress-fill.warning {{ background: #f59e0b; }}
    .progress-fill.safe {{ background: #10b981; }}

    .progress-text {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 10.5px;
      font-weight: 700;
      color: #fff;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>🤖 Combat Robotics Damage & Feedback Scaling Report</h1>
      <p class="subtitle">Detailed evaluation of weapon damage numbers, supply-chain feedback propagation, and throw shock scaling across robot components.</p>
    </header>

    <div class="nav-tabs">
      {''.join(robot_tabs_nav)}
    </div>

    {''.join(robot_tabs_content)}
  </div>

  <script>
    function switchTab(slug) {{
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
      const target = document.getElementById('tab-' + slug);
      if (target) target.classList.add('active');
      event.target.classList.add('active');
    }}
  </script>
</body>
</html>
"""


def generate_text_report(robot: RobotModel, catalog: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append(f" COMBAT SIMULATION & DAMAGE SCALING REPORT: {robot.name}")
    lines.append(f" Chassis: {robot.chassis.get('name', 'Unknown')} (Flip Strength: {robot.chassis.get('flip_strength', 'N/A')})")
    lines.append("=" * 80)

    # Component Roster
    lines.append("\n[1] COMPONENT ROSTER")
    lines.append(f"{'ID':<3} {'Component Name':<28} {'Dur':<4} {'Abs':<4} {'Suppliers'}")
    lines.append("-" * 75)
    for cid, c in sorted(robot.components.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
        sup_names = [robot.components[sid].name for sid in robot.supply_graph.get(cid, [])]
        sup_str = ", ".join(sup_names) if sup_names else "None (Source)"
        lines.append(f"{cid:<3} {c.name:<28} {c.durability:<4} {c.absorption:<4} {sup_str}")

    # Subsystem Chains
    chains = extract_robot_subsystem_chains(robot, max_fb=20)
    lines.append("\n" + "=" * 80)
    lines.append("[2] FEEDBACK CHAIN THRESHOLDS SUMMARY")
    lines.append("=" * 80)
    lines.append(f"{'Chain':<24} {'Safe Window':<14} {'Damage w/o Fail':<18} {'Sink Fails':<12} {'Upstream Fails'}")
    lines.append("-" * 80)
    for ch in chains:
        safe_str = f"FB {ch.safe_window[0]}-{ch.safe_window[1]}" if ch.safe_window[1] > 0 else "None"
        dwf_str = f"FB {ch.damage_without_fail_window[0]}-{ch.damage_without_fail_window[1]}" if ch.damage_without_fail_window[0] is not None else "None"
        sink_str = f"FB {ch.sink_failure_threshold}" if ch.sink_failure_threshold is not None else "None"
        up_str = f"FB {ch.upstream_failure_threshold}" if ch.upstream_failure_threshold is not None else "None"
        lines.append(f"{ch.name:<24} {safe_str:<14} {dwf_str:<18} {sink_str:<12} {up_str}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Simulate combat robotics damage and feedback scaling.")
    parser.add_argument("robot_csvs", nargs="*", help="Robot layout CSV paths in automata/ or elsewhere")
    parser.add_argument("--tolerance", type=float, default=3.0, help="Physical connection tolerance in mm (default: 3.0)")
    parser.add_argument("--html", type=str, help="Path for HTML report (default: scripts/output/combat_simulation_report.html)")
    parser.add_argument("--text", action="store_true", help="Also output text report to terminal / stdout")
    args = parser.parse_args()

    catalog = load_all_cards()

    if not args.robot_csvs:
        automata_dir = REPO_ROOT / "automata"
        csv_files = sorted(automata_dir.glob("*.csv"))
    else:
        csv_files = [Path(p) for p in args.robot_csvs]

    if not csv_files:
        print("No robot CSV files found to simulate.")
        sys.exit(1)

    robots: List[RobotModel] = []

    for p in csv_files:
        if not p.exists():
            print(f"Warning: {p} does not exist. Skipping.")
            continue
        robot = build_robot_model(p, catalog, tolerance=args.tolerance)
        robots.append(robot)

        if args.text:
            rep = generate_text_report(robot, catalog)
            print(rep)
            print("\n\n")

    # Output directory handling: default to scripts/output/
    output_dir = REPO_ROOT / "scripts" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = Path(args.html) if args.html else (output_dir / "combat_simulation_report.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    html_content = generate_html_report(robots, catalog)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("=" * 80)
    print(" COMBAT SIMULATION COMPLETE")
    print(f" Analyzed Robots: {', '.join(r.name for r in robots)}")
    print(f" HTML Report Generated: {html_path}")
    print(f" File URI: file://{html_path.resolve()}")
    print("=" * 80)


if __name__ == "__main__":
    main()
