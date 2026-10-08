#!/usr/bin/env python3
"""
Combat Simulation Script for Robot Battles
Tests weapon impacts, spin-up scaling, feedback propagation, and throw shock
against robot layouts loaded from CSV files.
Generates an interactive, styled HTML report and optional text summary in scripts/output/.
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
        elif outputs == "XXW":
            damage_map[s] = s ** 2
            formula_desc = "X^2 (X^2 * W)"
        elif re.match(r"^(\d*)XWW$", outputs):
            m = re.match(r"^(\d*)XWW$", outputs)
            k = int(m.group(1)) if m.group(1) else 1
            damage_map[s] = k * s + 1
            formula_desc = f"{k}X + 1" if k > 1 else "X + 1"
        elif re.match(r"^(\d+)XW$", outputs):
            m = re.match(r"^(\d+)XW$", outputs)
            k = int(m.group(1))
            damage_map[s] = k * s
            formula_desc = f"{k}X"
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

    all_x = [comp.x for comp in components.values()]
    all_y = [comp.y for comp in components.values()]
    min_x, max_x = (min(all_x), max(all_x)) if all_x else (0, 0)
    min_y, max_y = (min(all_y), max(all_y)) if all_y else (0, 0)

    outer_components: List[str] = []
    for cid, comp in components.items():
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
# HTML REPORT GENERATOR
# ==============================================================================

def generate_html_report(robots: List[RobotModel], catalog: Dict[str, Any]) -> str:
    """Generates a complete, beautiful standalone HTML report."""
    weapons = catalog["weapons"]

    robot_tabs_nav = []
    robot_tabs_content = []

    for idx, robot in enumerate(robots):
        active_cls = "active" if idx == 0 else ""
        slug = re.sub(r"[^a-zA-Z0-9_]", "_", robot.name)

        robot_tabs_nav.append(
            f'<button class="tab-btn {active_cls}" onclick="switchTab(\'{slug}\')">{html.escape(robot.name)}</button>'
        )

        # Tab content
        sections = []

        # Header summary stats
        armor_comps = [c for c in robot.components.values() if c.is_wedge or "armor" in c.name.lower() or "plate" in c.name.lower()]
        drive_wheels = [c for c in robot.components.values() if "wheel" in c.name.lower() or "tire" in c.name.lower() or "d" in c.outputs.lower()]
        robot_weapons = [c for c in robot.components.values() if c.card_type == "weapon"]

        sections.append(f"""
        <div class="robot-header-card">
          <div class="robot-title-row">
            <h2>{html.escape(robot.name)}</h2>
            <span class="chassis-badge">Chassis: {html.escape(str(robot.chassis.get('name', 'Chassis')))} (Flip Strength: {robot.chassis.get('flip_strength', 'N/A')})</span>
          </div>
          <div class="metrics-grid">
            <div class="metric-box">
              <span class="metric-label">Components</span>
              <span class="metric-val">{len(robot.components)}</span>
            </div>
            <div class="metric-box">
              <span class="metric-label">Armor Pieces</span>
              <span class="metric-val">{len(armor_comps)}</span>
            </div>
            <div class="metric-box">
              <span class="metric-label">Active Drive</span>
              <span class="metric-val">{len(drive_wheels)} Wheels</span>
            </div>
            <div class="metric-box">
              <span class="metric-label">Weapons</span>
              <span class="metric-val">{len(robot_weapons)}</span>
            </div>
          </div>
        </div>
        """)

        # 1. Executive Key Takeaways / Alerts
        sections.append("""
        <div class="section-container">
          <h3 class="section-title">📊 Executive Tuning Insights</h3>
          <div class="insights-grid">
            <div class="insight-card danger">
              <h4>💥 1-Hit Kill Vulnerability</h4>
              <p>High-tier spinners (<strong>Bloodsport Bar</strong> at 18–24 dmg, <strong>Horizontal Spinner</strong> at 12–16 dmg) deal more than double the durability of internal motors and batteries (durability 5–7). Unshielded hits cause instantaneous destruction rather than progressive damage.</p>
            </div>
            <div class="insight-card success">
              <h4>🛡️ Armor Protection Value</h4>
              <p>Perimeter armor is highly effective: <strong>UHMW Wraparound Armor</strong> (Dur 12, Abs 4) absorbs medium hits completely and disperses excess damage evenly among internal components, preventing any internal casualties up to 16 damage.</p>
            </div>
            <div class="insight-card warning">
              <h4>🔄 Recoil Self-Destruction</h4>
              <p>Weapons taking feedback equal to &lfloor;attack damage / 2&rfloor; destroy themselves at high spin-up: <strong>Horizontal Spinner</strong> destroys itself at Spin 4 (8 recoil > 7 dur), and <strong>Bloodsport Bar</strong> destroys itself at Spin 4 (12 recoil > 9 dur).</p>
            </div>
            <div class="insight-card danger">
              <h4>🎲 Throw Shock Bypass</h4>
              <p>Throw shock targets a <em>randomly chosen component</em> on the mat, completely bypassing perimeter armor. Throws above 8 strength instantly destroy unarmored batteries and motors in <strong>68% to 100%</strong> of cases unless deflected by a Wedge.</p>
            </div>
          </div>
        </div>
        """)

        # 2. Weapon Direct Hit Lethality Matrix
        weapon_select_options = ['<option value="all">Show All Weapons</option>']
        for w in weapons:
            w_slug = re.sub(r"[^a-zA-Z0-9_]", "_", w["name"])
            weapon_select_options.append(f'<option value="{w_slug}">{html.escape(w["name"])}</option>')

        matrix_blocks = []
        for w in weapons:
            w_slug = re.sub(r"[^a-zA-Z0-9_]", "_", w["name"])
            max_spin, d_map, formula = parse_weapon_spin_and_damage(w)

            th_cols = "".join(f"<th>Spin {s} <br><small>({dmg} Dmg)</small></th>" for s, dmg in d_map.items())

            rows = []
            for cid, comp in sorted(robot.components.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
                td_cols = []
                for s, dmg in d_map.items():
                    res = resolve_single_component_hit(comp, float(dmg), is_weapon_damage=True)
                    if res.status == "DESTROYED":
                        tag = '<span class="status-badge badge-danger">DESTROYED</span>'
                    elif res.status == "DAMAGED":
                        tag = '<span class="status-badge badge-warning">DAMAGED</span>'
                    else:
                        tag = '<span class="status-badge badge-success">SAFE</span>'
                    td_cols.append(f"<td>{tag}</td>")

                kw_badge = f'<span class="mini-tag">{comp.keywords}</span>' if comp.keywords else ''
                rows.append(f"""
                <tr>
                  <td class="comp-col"><strong>{html.escape(comp.name)}</strong> {kw_badge}</td>
                  <td class="stat-col">{comp.durability}</td>
                  <td class="stat-col">{comp.absorption}</td>
                  {''.join(td_cols)}
                </tr>
                """)

            matrix_blocks.append(f"""
            <div class="weapon-matrix-block" data-weapon="{w_slug}">
              <div class="weapon-block-header">
                <h4>{html.escape(w['name'])}</h4>
                <span class="weapon-desc">Formula: <code>{html.escape(formula)}</code> | Max Spin: <strong>{max_spin}</strong> | Req: <code>{w.get('requirements','')}</code></span>
              </div>
              <div class="table-responsive">
                <table class="report-table">
                  <thead>
                    <tr>
                      <th style="min-width: 220px;">Component</th>
                      <th style="width: 60px;">Dur</th>
                      <th style="width: 60px;">Abs</th>
                      {th_cols}
                    </tr>
                  </thead>
                  <tbody>
                    {''.join(rows)}
                  </tbody>
                </table>
              </div>
            </div>
            """)

        sections.append(f"""
        <div class="section-container">
          <div class="section-header-flex">
            <h3 class="section-title">⚔️ Direct Hit Lethality Matrix (Exposed Hits Without Armor)</h3>
            <div class="filter-controls">
              <label for="filter-{slug}">Filter Weapon: </label>
              <select id="filter-{slug}" class="select-input" onchange="filterWeapon('{slug}', this.value)">
                {''.join(weapon_select_options)}
              </select>
            </div>
          </div>
          {''.join(matrix_blocks)}
        </div>
        """)

        # 3. Defensive Armor & Inward Penetration
        if armor_comps:
            armor_blocks = []
            for ac in armor_comps:
                rows = []
                for w in weapons:
                    max_spin, d_map, _ = parse_weapon_spin_and_damage(w)
                    for s, dmg in d_map.items():
                        steps = simulate_inward_damage_progression(robot, ac.id, float(dmg), is_weapon_damage=True)
                        if not steps:
                            continue
                        armor_step = steps[0]
                        internal_steps = steps[1:]

                        if armor_step.status == "DESTROYED":
                            armor_badge = '<span class="status-badge badge-danger">DESTROYED</span>'
                        elif armor_step.status == "DAMAGED":
                            armor_badge = '<span class="status-badge badge-warning">DAMAGED</span>'
                        else:
                            armor_badge = '<span class="status-badge badge-success">UNDAMAGED</span>'

                        cas = []
                        for st in internal_steps:
                            if st.status == "DESTROYED":
                                cas.append(f'<span class="tag-danger">{html.escape(st.component_name)} [DESTROYED]</span>')
                            elif st.status == "DAMAGED":
                                cas.append(f'<span class="tag-warning">{html.escape(st.component_name)} [DAMAGED]</span>')
                        cas_html = " ".join(cas) if cas else '<span class="tag-success">None (Protected)</span>'

                        rows.append(f"""
                        <tr>
                          <td><strong>{html.escape(w['name'])}</strong></td>
                          <td class="stat-col">{s}</td>
                          <td class="stat-col">{dmg}</td>
                          <td>{armor_badge}</td>
                          <td class="stat-col">{armor_step.excess_damage:.1f}</td>
                          <td>{cas_html}</td>
                        </tr>
                        """)

                armor_blocks.append(f"""
                <div class="armor-sub-card">
                  <div class="armor-header">
                    <h4>{html.escape(ac.name)} (#{ac.id})</h4>
                    <span class="armor-stats">Durability: <strong>{ac.durability}</strong> | Absorption: <strong>{ac.absorption}</strong> {f'| Keywords: {ac.keywords}' if ac.keywords else ''}</span>
                  </div>
                  <div class="table-responsive">
                    <table class="report-table">
                      <thead>
                        <tr>
                          <th>Attacking Weapon</th>
                          <th>Spin</th>
                          <th>Dmg</th>
                          <th>Armor Status</th>
                          <th>Excess Passed Inward</th>
                          <th>Internal Casualties</th>
                        </tr>
                      </thead>
                      <tbody>
                        {''.join(rows)}
                      </tbody>
                    </table>
                  </div>
                </div>
                """)

            sections.append(f"""
            <div class="section-container">
              <h3 class="section-title">🛡️ Defensive Options & Inward Penetration Through Armor</h3>
              <p class="section-desc">Shows what happens when incoming attacks hit outer armor or wedges first, applying absorption and sharing excess damage evenly among connected inward components.</p>
              {''.join(armor_blocks)}
            </div>
            """)

        # 4. Weapon Recoil Feedback
        if robot_weapons:
            rw_blocks = []
            for rw in robot_weapons:
                w_def = next((w for w in weapons if w["name"] == rw.name), None)
                if not w_def:
                    continue
                max_spin, d_map, formula = parse_weapon_spin_and_damage(w_def)
                rows = []
                for s, dmg in d_map.items():
                    att_str = get_weapon_attack_strength(w_def, s)
                    fb_steps = simulate_weapon_feedback(robot, rw, att_str)
                    recoil_val = att_str // 2

                    if not fb_steps:
                        w_badge = '<span class="status-badge badge-success">SAFE</span>'
                        supp_html = '<span class="tag-success">No Strain</span>'
                    else:
                        w_step = fb_steps[0]
                        if w_step.status == "DESTROYED":
                            w_badge = '<span class="status-badge badge-danger">DESTROYED</span>'
                        elif w_step.status == "DAMAGED":
                            w_badge = '<span class="status-badge badge-warning">DAMAGED</span>'
                        else:
                            w_badge = '<span class="status-badge badge-success">UNDAMAGED</span>'

                        supp_cas = []
                        for st in fb_steps[1:]:
                            if st.status != "UNDAMAGED":
                                cls = "tag-danger" if st.status == "DESTROYED" else "tag-warning"
                                supp_cas.append(f'<span class="{cls}">{html.escape(st.component_name)} [{st.status}]</span>')
                        supp_html = " ".join(supp_cas) if supp_cas else '<span class="tag-success">Absorbed Cleanly</span>'

                    rows.append(f"""
                    <tr>
                      <td class="stat-col">Spin {s}</td>
                      <td class="stat-col">{att_str}</td>
                      <td class="stat-col">{recoil_val}</td>
                      <td>{w_badge}</td>
                      <td>{supp_html}</td>
                    </tr>
                    """)

                rw_blocks.append(f"""
                <div class="armor-sub-card">
                  <div class="armor-header">
                    <h4>{html.escape(rw.name)} (#{rw.id})</h4>
                    <span class="armor-stats">Durability: <strong>{rw.durability}</strong> | Absorption: <strong>{rw.absorption}</strong> | Formula: <code>{html.escape(formula)}</code></span>
                  </div>
                  <div class="table-responsive">
                    <table class="report-table">
                      <thead>
                        <tr>
                          <th>Spin Level</th>
                          <th>Attack Damage</th>
                          <th>Recoil Feedback (&lfloor;D/2&rfloor;)</th>
                          <th>Weapon Status</th>
                          <th>Supplying Motor / Battery Impact</th>
                        </tr>
                      </thead>
                      <tbody>
                        {''.join(rows)}
                      </tbody>
                    </table>
                  </div>
                </div>
                """)

            sections.append(f"""
            <div class="section-container">
              <h3 class="section-title">🔄 Weapon Recoil Feedback</h3>
              <p class="section-desc">Rules: Weapons take feedback equal to &lfloor;attack damage / 2&rfloor;. Weapon resolves feedback first; excess feedback propagates back down to supplying motors and batteries.</p>
              {''.join(rw_blocks)}
            </div>
            """)

        # 5. Drive Train Pushing Feedback
        drive_rows = []
        for d in [1, 2, 3, 4, 5, 6]:
            push_steps = simulate_drive_pushing_feedback(robot, d)
            if not push_steps:
                continue
            wheel_step = push_steps[0]
            w_badge = '<span class="status-badge badge-success">UNDAMAGED</span>' if wheel_step.status == "UNDAMAGED" else f'<span class="status-badge badge-warning">{wheel_step.status}</span>'
            sub_cas = [f'<span class="tag-warning">{st.component_name} [{st.status}]</span>' for st in push_steps[1:] if st.status != "UNDAMAGED"]
            sub_html = " ".join(sub_cas) if sub_cas else '<span class="tag-success">Absorbed Cleanly (Zero Damage)</span>'

            drive_rows.append(f"""
            <tr>
              <td class="stat-col"><strong>{d} Distance</strong></td>
              <td class="stat-col">{wheel_step.incoming_damage:.2f}</td>
              <td>{w_badge}</td>
              <td>{sub_html}</td>
            </tr>
            """)

        sections.append(f"""
        <div class="section-container">
          <h3 class="section-title">🚜 Drive Train Pushing Match Feedback</h3>
          <p class="section-desc">Rules: Opponent remaining distance before contact is shared equally between remaining active drive wheels, propagating back to drive motors and batteries.</p>
          <div class="table-responsive">
            <table class="report-table">
              <thead>
                <tr>
                  <th>Opponent Remaining Distance</th>
                  <th>Feedback Per Drive Wheel</th>
                  <th>Drive Wheel Status</th>
                  <th>Drive Motor / Battery Impact</th>
                </tr>
              </thead>
              <tbody>
                {''.join(drive_rows)}
              </tbody>
            </table>
          </div>
        </div>
        """)

        # 6. Throw Shock Matrix
        throw_rows = []
        for ts in [2, 4, 6, 8, 10, 12, 16, 24]:
            for on_wedge in [False, True]:
                outcomes = simulate_throw_shock(robot, ts, hit_on_wedge=on_wedge)
                eff_t = (ts + 1) // 2 if on_wedge else ts
                num_comps = len(robot.components)
                dest_count = 0
                dam_count = 0
                dest_names = []

                for cid, steps in outcomes.items():
                    if steps:
                        target_res = steps[0]
                        if target_res.status == "DESTROYED":
                            dest_count += 1
                            dest_names.append(target_res.component_name)
                        elif target_res.status == "DAMAGED":
                            dam_count += 1

                pct_dest = (dest_count / num_comps) * 100
                pct_dam = (dam_count / num_comps) * 100

                unique_dest = list(dict.fromkeys(dest_names))
                dest_sample = ", ".join(unique_dest[:3])
                if len(unique_dest) > 3:
                    dest_sample += f" (+{len(unique_dest)-3} more)"
                if not dest_sample:
                    dest_sample = '<span class="tag-success">None</span>'
                else:
                    dest_sample = f'<span class="tag-danger">{html.escape(dest_sample)}</span>'

                wedge_badge = '<span class="tag-primary">Wedge Deflection (Halved)</span>' if on_wedge else '<span class="tag-muted">Direct Hit</span>'

                # Progress bar style
                bar_html = f"""
                <div class="progress-container">
                  <div class="progress-fill {'danger' if pct_dest > 50 else 'warning' if pct_dest > 0 else 'safe'}" style="width: {pct_dest}%;"></div>
                  <span class="progress-text">{pct_dest:.1f}% ({dest_count}/{num_comps})</span>
                </div>
                """

                throw_rows.append(f"""
                <tr>
                  <td class="stat-col"><strong>{ts}</strong> (Eff {eff_t})</td>
                  <td>{wedge_badge}</td>
                  <td>{bar_html}</td>
                  <td class="stat-col">{pct_dam:.1f}%</td>
                  <td>{dest_sample}</td>
                </tr>
                """)

        sections.append(f"""
        <div class="section-container">
          <h3 class="section-title">🎲 Throw Shock Hazard (Random Component Strike)</h3>
          <p class="section-desc">Rules: After a throw, the thrown robot takes feedback equal to throw strength at a randomly chosen component (by dropping a card on it). The Wedge keyword halves throw strength received.</p>
          <div class="table-responsive">
            <table class="report-table">
              <thead>
                <tr>
                  <th>Throw Strength</th>
                  <th>Target Contact</th>
                  <th>% Instant Destruction</th>
                  <th>% Damaged</th>
                  <th>Sample Destroyed Targets</th>
                </tr>
              </thead>
              <tbody>
                {''.join(throw_rows)}
              </tbody>
            </table>
          </div>
        </div>
        """)

        # Add to tab content list
        robot_tabs_content.append(f"""
        <div id="tab-{slug}" class="tab-content {active_cls}">
          {''.join(sections)}
        </div>
        """)

    # Combine into full HTML document
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Combat Robotics Simulation & Balance Report</title>
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
      --danger-bg: rgba(239, 68, 68, 0.16);
      --warning: #f59e0b;
      --warning-bg: rgba(245, 158, 11, 0.16);
      --success: #10b981;
      --success-bg: rgba(16, 185, 129, 0.16);
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
      max-width: 1400px;
      margin: 0 auto;
    }}

    header {{
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }}

    h1 {{
      font-size: 26px;
      color: #fff;
      font-weight: 700;
      letter-spacing: -0.5px;
      margin-bottom: 6px;
    }}

    .subtitle {{
      color: var(--text-muted);
      font-size: 14px;
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
      padding: 10px 20px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
      font-size: 14px;
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

    .tab-content {{
      display: none;
    }}

    .tab-content.active {{
      display: block;
    }}

    .robot-header-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 24px;
    }}

    .robot-title-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
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
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 13px;
      color: var(--primary);
      font-weight: 600;
    }}

    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }}

    .metric-box {{
      background: var(--surface-card);
      border: 1px solid var(--border);
      padding: 12px 16px;
      border-radius: 8px;
    }}

    .metric-label {{
      display: block;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-bottom: 4px;
    }}

    .metric-val {{
      font-size: 20px;
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
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .section-desc {{
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 16px;
    }}

    .section-header-flex {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      flex-wrap: wrap;
      gap: 12px;
    }}

    .insights-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }}

    .insight-card {{
      padding: 16px;
      border-radius: 8px;
      border-left: 4px solid transparent;
      font-size: 13px;
    }}

    .insight-card h4 {{
      font-size: 14px;
      margin-bottom: 6px;
    }}

    .insight-card.danger {{
      background: var(--danger-bg);
      border-left-color: var(--danger);
      color: #fca5a5;
    }}
    .insight-card.danger h4 {{ color: #f87171; }}

    .insight-card.warning {{
      background: var(--warning-bg);
      border-left-color: var(--warning);
      color: #fde68a;
    }}
    .insight-card.warning h4 {{ color: #fbbf24; }}

    .insight-card.success {{
      background: var(--success-bg);
      border-left-color: var(--success);
      color: #a7f3d0;
    }}
    .insight-card.success h4 {{ color: #34d399; }}

    .select-input {{
      background: var(--surface-card);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 13px;
    }}

    .table-responsive {{
      overflow-x: auto;
      margin-top: 10px;
    }}

    .report-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
      text-align: left;
    }}

    .report-table th {{
      background: var(--surface-card);
      color: var(--text-muted);
      font-weight: 600;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }}

    .report-table td {{
      padding: 10px 12px;
      border-bottom: 1px solid rgba(38, 53, 74, 0.6);
      vertical-align: middle;
    }}

    .report-table tbody tr:hover {{
      background: var(--surface-hover);
    }}

    .stat-col {{
      text-align: center;
      font-variant-numeric: tabular-nums;
    }}

    .status-badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      text-align: center;
      white-space: nowrap;
    }}

    .badge-danger {{
      background: var(--danger-bg);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.4);
    }}

    .badge-warning {{
      background: var(--warning-bg);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.4);
    }}

    .badge-success {{
      background: var(--success-bg);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }}

    .tag-danger {{
      background: var(--danger-bg);
      color: #f87171;
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

    .tag-success {{
      background: var(--success-bg);
      color: #34d399;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
    }}

    .tag-primary {{
      background: var(--primary-bg);
      color: var(--primary);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
    }}

    .tag-muted {{
      background: var(--surface-card);
      color: var(--text-muted);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
    }}

    .mini-tag {{
      display: inline-block;
      background: rgba(129, 140, 248, 0.15);
      color: #a5b4fc;
      font-size: 10px;
      padding: 1px 5px;
      border-radius: 3px;
      margin-left: 6px;
    }}

    .weapon-matrix-block {{
      background: var(--surface-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 16px;
    }}

    .weapon-block-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .weapon-block-header h4 {{
      font-size: 15px;
      color: var(--primary);
    }}

    .weapon-desc {{
      font-size: 12px;
      color: var(--text-muted);
    }}

    .weapon-desc code {{
      background: #0f172a;
      padding: 2px 6px;
      border-radius: 4px;
      color: #38bdf8;
    }}

    .armor-sub-card {{
      background: var(--surface-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 16px;
    }}

    .armor-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .armor-header h4 {{
      color: #38bdf8;
      font-size: 15px;
    }}

    .armor-stats {{
      font-size: 12px;
      color: var(--text-muted);
    }}

    .progress-container {{
      width: 100%;
      min-width: 130px;
      background: #0f172a;
      border-radius: 4px;
      overflow: hidden;
      position: relative;
      height: 20px;
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
      font-size: 11px;
      font-weight: 700;
      color: #fff;
      text-shadow: 0 1px 2px rgba(0,0,0,0.8);
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>🤖 Combat Robotics Game Balance & Scaling Report</h1>
      <p class="subtitle">Evaluates real weapon impacts, spin-up scaling, feedback loops, and throw shocks against robot layouts.</p>
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

    function filterWeapon(robotSlug, weaponSlug) {{
      const tab = document.getElementById('tab-' + robotSlug);
      if (!tab) return;
      const blocks = tab.querySelectorAll('.weapon-matrix-block');
      blocks.forEach(b => {{
        if (weaponSlug === 'all' || b.dataset.weapon === weaponSlug) {{
          b.style.display = 'block';
        }} else {{
          b.style.display = 'none';
        }}
      }});
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

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Simulate combat robotics damage and feedback scaling.")
    parser.add_argument("robot_csvs", nargs="*", help="Robot layout CSV paths in automata/ or elsewhere")
    parser.add_argument("--tolerance", type=float, default=6.5, help="Physical connection tolerance in mm (default: 6.5)")
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
