## Automata actions
The actions available to the automata are:
- Rush - Drive at the opponent at full speed
- Face - Rotate on the spot to face their opponent
- Retreat - Move away from opponent while facing them

For each automata, there is a set of tables:

## Vyper_flipper
No flow chart - always same table
| Roll | Action |
| 1 | Retreat |
| 2 | Face |
| 3-6 | Rush  |

## Vyper_Spinner
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

