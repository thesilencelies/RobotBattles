## Automata actions
The actions available to the automata are:
- Rush - Drive at the opponent at full speed
- Face - Rotate on the spot to face their opponent
- Retreat - Move away from opponent while facing them
- Evade - move forwards and perpendicular to the line between the robots - if both ways are clear choose at random

There are several archetypes, from which automata normally choose.

*Note on weapon spin:* Automata consider themselves at full spin unless they have an active weapon with spin up that is not at max spin (e.g. if their weapons are down or at max spin, they use the charged / full spin action tables).

## Full rush
No flow chart - always same table
| Roll | Action |
| 1 | Retreat |
| 2 | Face |
| 3 | Evade |
| 4-6 | Rush  |

## Spin up
If there are 2 or more spin counters on the weapon:
| Roll | Action |
| 1 | Face |
| 2 | Evade |
| 3-6 | Rush  |
else:
| Roll | Action |
| 1-2 | Retreat |
| 3 | Face |
| 4-5 | Evade |
| 6 | Rush  |

## Balanced
If weapon is at full spin
| Roll | Action |
| 1 | Retreat |
| 2 | Face |
| 3 | Evade |
| 4-6 | Rush  |
else
| Roll | Action |
| 1 | Retreat |
| 2-3 | Evade |
| 4 | Face |
| 5-6 | Rush  |


# Per automata allocation
| Bot | Archetype |
| - | - |
| Vyper_flipper | Full Rush |
| Vyper_spinner | Spin Up |
| Beater_wide | Balanced |
| Nightwing_wide | Balanced |
| Chonk | Spin Up |



