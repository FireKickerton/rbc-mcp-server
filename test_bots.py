#!/usr/bin/env python3
"""
Quick test to verify bot implementations work correctly
"""

import chess
from rbc_mcp_server import RandomBot, AttackerBot, TroutBot

def test_bot(bot_class, bot_name):
    """Test a bot's basic functionality"""
    print(f"\nTesting {bot_name}...")

    bot = bot_class()
    board = chess.Board()

    # Test handle_game_start
    bot.handle_game_start(chess.WHITE, board, "test_opponent")
    print(f"  ✓ handle_game_start")

    # Test handle_opponent_move_result
    bot.handle_opponent_move_result(False, None)
    print(f"  ✓ handle_opponent_move_result")

    # Test choose_sense
    sense_actions = list(range(64))  # All squares
    move_actions = list(board.legal_moves)
    sense_square = bot.choose_sense(sense_actions, move_actions, 60.0)
    print(f"  ✓ choose_sense -> {chess.square_name(sense_square) if sense_square else 'None'}")

    # Test handle_sense_result
    if sense_square:
        sense_result = [(sense_square, board.piece_at(sense_square))]
        bot.handle_sense_result(sense_result)
        print(f"  ✓ handle_sense_result")

    # Test choose_move
    move = bot.choose_move(move_actions, 60.0)
    print(f"  ✓ choose_move -> {move.uci() if move else 'None'}")

    # Test handle_move_result
    if move:
        bot.handle_move_result(move, move, False, None)
        print(f"  ✓ handle_move_result")

    # Test handle_game_end
    bot.handle_game_end(chess.WHITE, None, None)
    print(f"  ✓ handle_game_end")

    print(f"  {bot_name}: All tests passed! ✓")

if __name__ == "__main__":
    print("=" * 50)
    print("Testing RBC Bot Implementations")
    print("=" * 50)

    test_bot(RandomBot, "RandomBot")
    test_bot(AttackerBot, "AttackerBot")
    test_bot(TroutBot, "TroutBot")

    print("\n" + "=" * 50)
    print("All bot tests passed! ✓")
    print("=" * 50)
