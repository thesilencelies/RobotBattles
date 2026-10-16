"""Core types and data models for Robot Battles playtest engine."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Pose:
    x: float
    y: float
    theta: float  # Degrees: 0 = North (Up, -y), 90 = East (+x), 180 = South (+y), 270 = West (-x)

    def heading_rad(self) -> float:
        # 0 deg = -y (North) -> in math standard coords: angle from +x is 90 - theta
        # Alternatively: dx = sin(theta), dy = -cos(theta)
        return math.radians(self.theta)

    def forward_vec(self) -> Tuple[float, float]:
        r = self.heading_rad()
        return (math.sin(r), -math.cos(r))

    def right_vec(self) -> Tuple[float, float]:
        r = self.heading_rad()
        return (math.cos(r), math.sin(r))

    def clone(self) -> Pose:
        return Pose(x=self.x, y=self.y, theta=self.theta % 360.0)


@dataclass
class TrajectoryPoint:
    x: float
    y: float
    theta: float
    t: float  # 0.0 to 1.0


@dataclass
class ComponentHealth:
    id: str
    name: str
    card_type: str  # component, weapon
    max_durability: int
    current_durability: int
    absorption: int
    requirements: str
    outputs: str
    keywords: str
    text: str
    x: float
    y: float
    rotation: int
    box: Tuple[float, float, float, float]
    is_damaged: bool = False
    is_destroyed: bool = False
    is_active: bool = True
    is_fragile: bool = False
    is_wedge: bool = False
    is_forks: bool = False
    is_invertible: bool = False
    is_reset: bool = False
    is_resetting: bool = False
    reset_supplied: bool = False
    was_used_this_turn: bool = False
    template: str = ""
    spin_counters: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "card_type": self.card_type,
            "max_durability": self.max_durability,
            "current_durability": self.current_durability,
            "absorption": self.absorption,
            "requirements": self.requirements,
            "outputs": self.outputs,
            "keywords": self.keywords,
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "rotation": self.rotation,
            "box": list(self.box),
            "is_damaged": self.is_damaged,
            "is_destroyed": self.is_destroyed,
            "is_active": self.is_active,
            "is_fragile": self.is_fragile,
            "is_wedge": self.is_wedge,
            "is_forks": self.is_forks,
            "is_invertible": self.is_invertible,
            "is_reset": self.is_reset,
            "is_resetting": self.is_resetting,
            "reset_supplied": self.reset_supplied,
            "template": self.template,
            "spin_counters": self.spin_counters,
        }


@dataclass
class MoveChoice:
    left: int
    right: int

    def to_dict(self) -> Dict[str, Any]:
        return {"left": self.left, "right": self.right}


@dataclass
class CollisionEvent:
    time_t: float
    contact_point: Tuple[float, float]
    robot1_octant: str
    robot2_octant: str
    robot1_components: List[str]
    robot2_components: List[str]
    contact_type: str  # "ACTIVE" or "INERT"
    description: str
    r1_remaining_dist: float = 0.0
    r2_remaining_dist: float = 0.0
    push_vector: Tuple[float, float] = (0.0, 0.0)
    r1_rem_vector: Tuple[float, float] = (0.0, 0.0)
    r2_rem_vector: Tuple[float, float] = (0.0, 0.0)
    step_index: int = 0
    r1_active_hit: bool = False
    r2_active_hit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time_t": self.time_t,
            "step_index": self.step_index,
            "contact_point": list(self.contact_point),
            "robot1_octant": self.robot1_octant,
            "robot2_octant": self.robot2_octant,
            "robot1_components": self.robot1_components,
            "robot2_components": self.robot2_components,
            "contact_type": self.contact_type,
            "description": self.description,
            "r1_remaining_dist": self.r1_remaining_dist,
            "r2_remaining_dist": self.r2_remaining_dist,
            "r1_rem_vector": list(self.r1_rem_vector),
            "r2_rem_vector": list(self.r2_rem_vector),
            "push_vector": list(self.push_vector),
            "r1_active_hit": self.r1_active_hit,
            "r2_active_hit": self.r2_active_hit,
        }


@dataclass
class CombatLogEntry:
    round: int
    phase: str
    message: str
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round": self.round,
            "phase": self.phase,
            "message": self.message,
            "details": self.details or {},
        }


@dataclass
class DamageTrainStep:
    phase: str  # "damage", "recoil_feedback", "shock_feedback", "push_feedback", "wall_feedback"
    robot_id: str  # "player" or "automaton"
    target_cid: str
    from_cid: Optional[str] = None
    amount: int = 0
    absorbed: int = 0
    excess: int = 0
    new_status: str = "UNDAMAGED"  # "UNDAMAGED", "DAMAGED", "DESTROYED"
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "robot_id": self.robot_id,
            "target_cid": self.target_cid,
            "from_cid": self.from_cid,
            "amount": self.amount,
            "absorbed": self.absorbed,
            "excess": self.excess,
            "new_status": self.new_status,
            "message": self.message,
        }



@dataclass
class RobotState:
    id: str
    name: str
    chassis_name: str
    chassis_template: str  # "Square", "Triangle", "Wide"
    flip_strength: int
    pose: Pose
    components: Dict[str, ComponentHealth]
    connections: Dict[str, List[str]]
    supply_graph: Dict[str, List[str]]  # comp_id -> list of supplier comp_ids
    reverse_supply: Dict[str, List[str]]
    weapon_spin_counters: Dict[str, int] = field(default_factory=dict)
    resetting_weapons: List[str] = field(default_factory=list)
    is_inverted: bool = False
    is_raised: bool = False
    is_eliminated: bool = False
    is_knocked_out: bool = False
    left_drive_max: int = 0
    right_drive_max: int = 0
    total_weight: int = 0
    total_cost: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "chassis_name": self.chassis_name,
            "chassis_template": self.chassis_template,
            "flip_strength": self.flip_strength,
            "pose": {"x": self.pose.x, "y": self.pose.y, "theta": self.pose.theta},
            "components": {cid: c.to_dict() for cid, c in self.components.items()},
            "connections": self.connections,
            "supply_graph": self.supply_graph,
            "weapon_spin_counters": self.weapon_spin_counters,
            "resetting_weapons": list(self.resetting_weapons),
            "is_inverted": self.is_inverted,
            "is_raised": self.is_raised,
            "is_eliminated": self.is_eliminated or self.is_knocked_out,
            "is_knocked_out": self.is_knocked_out or self.is_eliminated,
            "left_drive_max": self.left_drive_max,
            "right_drive_max": self.right_drive_max,
            "total_weight": self.total_weight,
            "total_cost": self.total_cost,
        }


@dataclass
class MatchState:
    match_id: str
    round: int  # Current round, 1 to max_rounds
    phase: str  # "planning", "movement", "collision", "cleanup", "game_over"
    player_robot: RobotState
    automaton_robot: RobotState
    automaton_type: str
    max_rounds: int = 20
    player_choice: Optional[MoveChoice] = None
    automaton_choice: Optional[MoveChoice] = None
    automaton_roll: Optional[int] = None
    automaton_action: Optional[str] = None
    player_trajectory: List[TrajectoryPoint] = field(default_factory=list)
    automaton_trajectory: List[TrajectoryPoint] = field(default_factory=list)
    player_template: Optional[Dict[str, Any]] = None
    automaton_template: Optional[Dict[str, Any]] = None
    damage_steps: List[DamageTrainStep] = field(default_factory=list)
    last_collision: Optional[CollisionEvent] = None
    log: List[CombatLogEntry] = field(default_factory=list)
    winner: Optional[str] = None  # "player", "automaton", "draw", None
    win_reason: Optional[str] = None
    round_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_id": self.match_id,
            "round": self.round,
            "max_rounds": self.max_rounds,
            "phase": self.phase,
            "player_robot": self.player_robot.to_dict(),
            "automaton_robot": self.automaton_robot.to_dict(),
            "automaton_type": self.automaton_type,
            "player_choice": self.player_choice.to_dict() if self.player_choice else None,
            "automaton_choice": self.automaton_choice.to_dict() if self.automaton_choice else None,
            "automaton_roll": self.automaton_roll,
            "automaton_action": self.automaton_action,
            "player_trajectory": [
                {"x": p.x, "y": p.y, "theta": p.theta, "t": p.t}
                for p in self.player_trajectory
            ],
            "automaton_trajectory": [
                {"x": p.x, "y": p.y, "theta": p.theta, "t": p.t}
                for p in self.automaton_trajectory
            ],
            "player_template": self.player_template,
            "automaton_template": self.automaton_template,
            "damage_steps": [s.to_dict() for s in self.damage_steps],
            "last_collision": self.last_collision.to_dict() if self.last_collision else None,
            "log": [entry.to_dict() for entry in self.log],
            "winner": self.winner,
            "win_reason": self.win_reason,
            "round_history": self.round_history,
        }

