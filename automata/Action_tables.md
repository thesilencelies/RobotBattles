## Automata actions
The actions available to the automata are:
- Rush - Drive at the opponent at full speed
- Face - Rotate on the spot to face their opponent
- Retreat - Move away from opponent while facing them


There are several archetypes, from which automata normally choose:

## Full rush
No flow chart - always same table
| Roll | Action |
| 1 | Retreat |
| 2 | Face |
| 3-6 | Rush  |

## Spin up
If there are 2 or more spin counters on the weapon:
| Roll | Action |
| 1 | Retreat |
| 2 | Face |
| 3-6 | Rush  |
else:
| Roll | Action |
| 1-3 | Retreat |
| 4-5 | Face |
| 6 | Rush  |

## Balanced
If weapon is at full spin
| Roll | Action |
| 1 | Retreat |
| 2-3 | Face |
| 4-6 | Rush  |
else
| Roll | Action |
| 1-2 | Retreat |
| 3-4 | Face |
| 5-6 | Rush  |


# Per automata allocation
| Bot | Archetype |
| - | - |
| Vyper_flipper | Full Rush |
| Vyper_spinner | Spin Up |
| Beater_wide | Balanced |
| Nightwing_wide | Balanced |
| Chonk | Spin Up |



