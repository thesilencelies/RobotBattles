import json
import pytest
from playtest.engine.combat import detect_supply_shortfall, refresh_robot_drive_and_power
from playtest.engine.match import create_match, execute_turn
from playtest.engine.types import MoveChoice
from builder.server.data import read_saved_robot
from playtest.server.routes import Router


def test_supply_shortfall_detection_intact_vs_damaged():
    csv_text = read_saved_robot("Vyper_Spinner.csv")
    assert csv_text is not None

    match = create_match(csv_text, "Vyper_flipper", "Player Spinner")
    p_bot = match.player_robot

    # Intact: Has 8E (Tattu) + 6E (Galaxy) = 14E. Consumers need 4E (Hubmotor) + 3E (Left Gearmotor) + 3E (Right Gearmotor) = 10E.
    # Supply is sufficient for all connected components.
    refresh_robot_drive_and_power(p_bot)
    assert not p_bot.has_supply_shortfall
    assert p_bot.components["3"].is_active  # Repeat 2207 Hubmotor
    assert p_bot.components["12"].is_active  # Left Gearmotor
    assert p_bot.components["13"].is_active  # Right Gearmotor

    # Destroy battery 14 (Galaxy 300 3S, 6E)
    p_bot.components["14"].is_destroyed = True
    p_bot.components["14"].current_durability = 0
    p_bot.components["14"].is_active = False

    refresh_robot_drive_and_power(p_bot)
    # Remaining battery 6 has 8E. Total demand is 10E > 8E.
    # Shortfall must be detected!
    assert p_bot.has_supply_shortfall
    has_shortfall, competing = detect_supply_shortfall(p_bot)
    assert has_shortfall
    assert len(competing) > 0


def test_player_choice_switches_power_allocation():
    csv_text = read_saved_robot("Vyper_Spinner.csv")
    match = create_match(csv_text, "Vyper_flipper", "Player Spinner")
    p_bot = match.player_robot

    # Destroy battery 14 so there is an 8E shortfall (Hubmotor 4E, Left GM 3E, Right GM 3E)
    p_bot.components["14"].is_destroyed = True
    p_bot.components["14"].current_durability = 0
    p_bot.components["14"].is_active = False

    # Default fallback: weapon gets priority over drive
    refresh_robot_drive_and_power(p_bot, chosen_components=None)
    assert p_bot.components["3"].is_active  # Hubmotor powered (4E)
    assert p_bot.components["12"].is_active  # Left Gearmotor powered (3E)
    assert not p_bot.components["13"].is_active  # Right Gearmotor starved (only 1E left)
    assert p_bot.right_drive_max == 0

    # Player chooses to power both drive motors instead of weapon: chosen_components = ["12", "13"]
    refresh_robot_drive_and_power(p_bot, chosen_components=["12", "13"])
    assert p_bot.components["12"].is_active  # Left GM powered (3E)
    assert p_bot.components["13"].is_active  # Right GM powered (3E)
    assert not p_bot.components["3"].is_active  # Hubmotor starved (needs 4E, only 2E left)
    assert p_bot.left_drive_max > 0
    assert p_bot.right_drive_max > 0

    # Player chooses weapon and right gearmotor: chosen_components = ["3", "13"]
    refresh_robot_drive_and_power(p_bot, chosen_components=["3", "13"])
    assert p_bot.components["3"].is_active
    assert p_bot.components["13"].is_active
    assert not p_bot.components["12"].is_active
    assert p_bot.left_drive_max == 0
    assert p_bot.right_drive_max > 0


def test_turn_execution_with_player_supplied_components():
    csv_text = read_saved_robot("Vyper_Spinner.csv")
    match = create_match(csv_text, "Vyper_flipper", "Player Spinner")
    p_bot = match.player_robot

    p_bot.components["14"].is_destroyed = True
    p_bot.components["14"].current_durability = 0
    p_bot.components["14"].is_active = False

    # Execute turn prioritizing both drive motors
    execute_turn(
        match,
        MoveChoice(left=1, right=1, cards=["Wait", "Wait", "Wait"]),
        fixed_automaton_roll=1,
        player_supplied_components=["12", "13"],
    )

    # After turn, chosen components should be maintained
    assert p_bot.components["12"].is_active
    assert p_bot.components["13"].is_active
    assert not p_bot.components["3"].is_active
    assert p_bot.has_supply_shortfall


def test_api_battle_supply_route():
    router = Router()
    csv_text = read_saved_robot("Vyper_Spinner.csv")
    router.current_match = create_match(csv_text, "Vyper_flipper", "Player Spinner")
    p_bot = router.current_match.player_robot

    # Create shortfall condition
    p_bot.components["14"].is_destroyed = True
    p_bot.components["14"].current_durability = 0
    p_bot.components["14"].is_active = False
    refresh_robot_drive_and_power(p_bot)

    assert p_bot.has_supply_shortfall
    assert not p_bot.components["13"].is_active

    # Call /api/battle/supply choosing components ["12", "13"]
    body = json.dumps({"chosen_components": ["12", "13"]}).encode("utf-8")
    resp = router._api_battle_supply({}, body)
    assert resp.status == 200
    res_data = json.loads(resp.body.decode("utf-8"))
    match_data = res_data["match"]
    assert match_data["player_robot"]["has_supply_shortfall"]
    assert match_data["player_robot"]["components"]["12"]["is_active"]
    assert match_data["player_robot"]["components"]["13"]["is_active"]
    assert not match_data["player_robot"]["components"]["3"]["is_active"]
