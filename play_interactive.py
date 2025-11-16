#!/usr/bin/env python3
"""
Interactive RBC game player for Claude Code sessions.
Plays a game and outputs JSON for easy parsing.
"""
import sys
import json
import chess
import reconchess
from io import StringIO


class GameState:
    def __init__(self, color, opponent_bot_type='random'):
        self.board = chess.Board()
        self.color = color
        self.my_turn_count = 0

        # Track what we know about the board
        self.known_board = chess.Board()
        for square in chess.SQUARES:
            self.known_board.remove_piece_at(square)

        # Place our own pieces (we can see them)
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == color:
                self.known_board.set_piece_at(square, piece)

        self.last_sense_result = None
        self.last_move_result = None
        self.opponent_move_result = None
        self.game_over = False
        self.winner = None

    def to_dict(self):
        return {
            "turn": self.my_turn_count,
            "color": "white" if self.color == chess.WHITE else "black",
            "board_fen": self.known_board.fen(),
            "game_over": self.game_over,
            "winner": self.winner,
            "last_sense_result": self.last_sense_result,
            "last_move_result": self.last_move_result,
            "opponent_move_result": self.opponent_move_result,
        }


def print_board(board):
    """Print board in a nice format with coordinates."""
    lines = []
    lines.append("  +---+---+---+---+---+---+---+---+")
    for rank in range(7, -1, -1):
        row = f"{rank+1} |"
        for file in range(8):
            square = chess.square(file, rank)
            piece = board.piece_at(square)
            if piece:
                row += f" {piece.symbol()} |"
            else:
                row += "   |"
        lines.append(row)
        lines.append("  +---+---+---+---+---+---+---+---+")
    lines.append("    a   b   c   d   e   f   g   h")
    return "\n".join(lines)


def square_to_name(square):
    """Convert square number to name like 'e4'."""
    if square is None:
        return None
    return chess.square_name(square)


def name_to_square(name):
    """Convert name like 'e4' to square number."""
    if name.lower() == 'pass':
        return None
    try:
        return chess.parse_square(name)
    except:
        return None


def format_sense_result(sense_result):
    """Format sense result as a readable grid."""
    if not sense_result:
        return None

    lines = []
    squares_dict = {sq: piece for sq, piece in sense_result}

    # Get the center square to determine the 3x3 grid
    center = sense_result[0][0] if sense_result else None
    if not center:
        return None

    center_file = chess.square_file(center)
    center_rank = chess.square_rank(center)

    lines.append("  +---+---+---+")
    for rank_offset in [1, 0, -1]:
        rank = center_rank + rank_offset
        if rank < 0 or rank > 7:
            continue
        row = "  |"
        for file_offset in [-1, 0, 1]:
            file = center_file + file_offset
            if file < 0 or file > 7:
                row += "   |"
                continue
            square = chess.square(file, rank)
            piece = squares_dict.get(square)
            if piece:
                row += f" {piece.symbol()} |"
            else:
                row += "   |"
        lines.append(row)
        lines.append("  +---+---+---+")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: play_interactive.py <command> [args...]"}))
        sys.exit(1)

    command = sys.argv[1]

    # For now, just implement a simple status command
    if command == "status":
        # This would load from a saved game state
        print(json.dumps({"status": "ready", "message": "Ready to start a new game"}))
    elif command == "start":
        color_arg = sys.argv[2] if len(sys.argv) > 2 else "white"
        color = chess.WHITE if color_arg.lower() == "white" else chess.BLACK
        bot_type = sys.argv[3] if len(sys.argv) > 3 else "random"

        state = GameState(color, bot_type)
        print(json.dumps({
            "status": "game_started",
            "game_state": state.to_dict(),
            "board": print_board(state.known_board),
            "message": f"Game started! You are playing as {color_arg}."
        }))
    else:
        print(json.dumps({"error": f"Unknown command: {command}"}))


if __name__ == "__main__":
    main()
