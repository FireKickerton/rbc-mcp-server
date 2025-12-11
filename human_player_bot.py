#!/usr/bin/env python3
"""
Standalone HumanPlayer bot for use with rc_connect.
This allows interactive play through the MCP server for remote games.
"""

import chess
import logging
import time
import threading
from typing import List, Optional, Tuple, Dict
from reconchess import Player, Color, WinReason, GameHistory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("human-player-bot")

# Global registry for active human player instances
_player_registry: Dict[int, 'HumanPlayer'] = {}
_registry_lock = threading.Lock()
_next_player_id = 1


def get_active_players() -> Dict[int, 'HumanPlayer']:
    """Get all active human player instances"""
    with _registry_lock:
        return dict(_player_registry)


def get_player_by_id(player_id: int) -> Optional['HumanPlayer']:
    """Get a specific player by ID"""
    with _registry_lock:
        return _player_registry.get(player_id)


class HumanPlayer(Player):
    """A human player that interacts through MCP tools"""

    def __init__(self):
        global _next_player_id
        with _registry_lock:
            self.player_id = _next_player_id
            _next_player_id += 1
            _player_registry[self.player_id] = self

        self.color = None
        self.board = None
        self.opponent_name = None
        self.sense_choice = None
        self.move_choice = None
        self.opponent_move_info = None
        self.sense_result_data = None
        self.move_result_data = None
        self.waiting_for_sense = False
        self.waiting_for_move = False
        self.game_over = False

        logger.info(f"HumanPlayer instance created with ID: {self.player_id}")

    def handle_game_start(self, color: Color, board: chess.Board, opponent_name: str):
        self.color = color
        self.board = board.copy()
        self.opponent_name = opponent_name
        logger.info(f"[Player {self.player_id}] Starting as {color} against {opponent_name}")

    def handle_opponent_move_result(self, captured_my_piece: bool, capture_square: Optional[chess.Square]):
        self.opponent_move_info = {
            "captured_my_piece": captured_my_piece,
            "capture_square": chess.square_name(capture_square) if capture_square else None
        }

    def choose_sense(self, sense_actions: List[chess.Square], move_actions: List[chess.Move], seconds_left: float) -> Optional[chess.Square]:
        self.waiting_for_sense = True
        self.sense_choice = None
        logger.info(f"[Player {self.player_id}] Waiting for sense choice... ({seconds_left:.1f}s remaining)")

        # Wait for human input (using time.sleep since this runs in a thread)
        timeout = seconds_left - 1  # Leave 1 second buffer
        elapsed = 0
        while self.sense_choice is None and elapsed < timeout:
            time.sleep(0.1)
            elapsed += 0.1

        self.waiting_for_sense = False

        if self.sense_choice is None:
            logger.warning(f"[Player {self.player_id}] No sense choice received, passing turn")
            return None

        logger.info(f"[Player {self.player_id}] Chose sense: {chess.square_name(self.sense_choice)}")
        return self.sense_choice

    def handle_sense_result(self, sense_result: List[Tuple[chess.Square, Optional[chess.Piece]]]):
        # Update our board knowledge
        for square, piece in sense_result:
            self.board.set_piece_at(square, piece)

        # Store the result for retrieval
        self.sense_result_data = [
            {
                "square": chess.square_name(square),
                "piece": piece.symbol() if piece else None
            }
            for square, piece in sense_result
        ]

    def choose_move(self, move_actions: List[chess.Move], seconds_left: float) -> Optional[chess.Move]:
        self.waiting_for_move = True
        self.move_choice = None
        logger.info(f"[Player {self.player_id}] Waiting for move choice... ({seconds_left:.1f}s remaining)")

        # Wait for human input
        timeout = seconds_left - 1  # Leave 1 second buffer
        elapsed = 0
        while self.move_choice is None and elapsed < timeout:
            time.sleep(0.1)
            elapsed += 0.1

        self.waiting_for_move = False

        if self.move_choice is None:
            logger.warning(f"[Player {self.player_id}] No move choice received, passing turn")
            return None

        logger.info(f"[Player {self.player_id}] Chose move: {self.move_choice.uci() if self.move_choice else 'None'}")
        return self.move_choice

    def handle_move_result(self, requested_move: Optional[chess.Move], taken_move: Optional[chess.Move],
                          captured_opponent_piece: bool, capture_square: Optional[chess.Square]):
        # Store the result for retrieval
        self.move_result_data = {
            "requested_move": requested_move.uci() if requested_move else None,
            "taken_move": taken_move.uci() if taken_move else None,
            "captured_opponent_piece": captured_opponent_piece,
            "capture_square": chess.square_name(capture_square) if capture_square else None
        }

        # Update our board
        if taken_move:
            self.board.push(taken_move)

    def handle_game_end(self, winner_color: Optional[Color], win_reason: Optional[WinReason],
                       game_history: GameHistory):
        self.game_over = True
        logger.info(f"[Player {self.player_id}] Game ended. Winner: {winner_color}, Reason: {win_reason}")

        # Unregister from global registry
        with _registry_lock:
            if self.player_id in _player_registry:
                del _player_registry[self.player_id]
                logger.info(f"[Player {self.player_id}] Unregistered from player registry")


def get_player():
    """Return the HumanPlayer class for reconchess.load_player"""
    return HumanPlayer
