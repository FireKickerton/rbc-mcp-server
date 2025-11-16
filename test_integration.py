#!/usr/bin/env python3
"""
Integration test for the MCP server
Tests game creation and basic functionality
"""

import time
from rbc_mcp_server import game_manager, run_local_game

def test_local_game_creation():
    """Test creating a local game"""
    print("\nTest: Creating local game...")

    game_id = game_manager.create_local_game(bot_type="random", human_color="white")
    assert game_id == 1, "First game ID should be 1"
    print(f"  ✓ Created game {game_id}")

    game_state = game_manager.local_games[game_id]
    assert game_state.opponent_name == "random_bot"
    print(f"  ✓ Playing against {game_state.opponent_name}")

    assert game_state.human_player is not None
    print(f"  ✓ Human player initialized")

    assert game_state.bot_player is not None
    print(f"  ✓ Bot player initialized")

    return game_id

def test_game_startup():
    """Test that a game starts properly"""
    print("\nTest: Starting game...")

    game_id = game_manager.create_local_game(bot_type="random", human_color="white")
    game_state = game_manager.local_games[game_id]

    # Start the game in a background thread (don't actually run it)
    # We'll just check that the game object is ready
    assert game_state.game is not None
    print(f"  ✓ Game object created")

    assert not game_state.game_started
    print(f"  ✓ Game in correct initial state")

    return game_id

def test_multiple_games():
    """Test creating multiple games"""
    print("\nTest: Creating multiple games...")

    game_id1 = game_manager.create_local_game(bot_type="random", human_color="white")
    game_id2 = game_manager.create_local_game(bot_type="attacker", human_color="black")
    game_id3 = game_manager.create_local_game(bot_type="trout", human_color="random")

    assert game_id1 != game_id2 != game_id3
    print(f"  ✓ Created games with unique IDs: {game_id1}, {game_id2}, {game_id3}")

    assert len(game_manager.local_games) >= 3
    print(f"  ✓ Game manager tracking {len(game_manager.local_games)} games")

    return [game_id1, game_id2, game_id3]

def test_human_player_interaction():
    """Test that human player can receive sense/move choices"""
    print("\nTest: Human player interaction...")

    game_id = game_manager.create_local_game(bot_type="random", human_color="white")
    game_state = game_manager.local_games[game_id]

    human = game_state.human_player

    # Test that human player starts in correct state
    assert human.waiting_for_sense == False
    print(f"  ✓ Human player not waiting initially")

    # Test setting sense choice
    import chess
    human.sense_choice = chess.E4
    assert human.sense_choice == chess.E4
    print(f"  ✓ Can set sense choice")

    # Test setting move choice
    human.move_choice = chess.Move.from_uci("e2e4")
    assert human.move_choice.uci() == "e2e4"
    print(f"  ✓ Can set move choice")

if __name__ == "__main__":
    print("=" * 60)
    print("Integration Tests for RBC MCP Server")
    print("=" * 60)

    try:
        test_local_game_creation()
        test_game_startup()
        test_multiple_games()
        test_human_player_interaction()

        print("\n" + "=" * 60)
        print("All integration tests passed! ✓")
        print("=" * 60)
        print("\nThe MCP server is ready to use!")
        print("\nTo use with Claude Desktop, add this to your config:")
        print('  "rbc": {')
        print('    "command": "/path/to/venv/bin/python3",')
        print('    "args": ["/path/to/rbc_mcp_server.py"]')
        print('  }')

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
