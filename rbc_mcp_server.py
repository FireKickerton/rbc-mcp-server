#!/usr/bin/env python3
"""
Reconnaissance Blind Chess MCP Server

This MCP server allows humans or LLMs to play Reconnaissance Blind Chess
both locally (using reconchess.LocalGame) and against bots on the official
RBC server at rbc.jhuapl.edu (using reconchess.RemoteGame).
"""

import asyncio
import chess
import json
import logging
import random
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from reconchess import Player, LocalGame, GameHistory, play_local_game, WinReason, Color
from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rbc-mcp-server")


# ============================================================================
# Bot Implementations - Using official reconchess bots
# ============================================================================

# Import official bots from reconchess.bots
from reconchess.bots.random_bot import RandomBot
from reconchess.bots.attacker_bot import AttackerBot

# TroutBot from reconchess requires Stockfish, import but provide fallback
try:
    from reconchess.bots.trout_bot import TroutBot as OfficialTroutBot
    OFFICIAL_TROUT_AVAILABLE = True
except ImportError:
    OFFICIAL_TROUT_AVAILABLE = False
    logger.warning("Could not import official TroutBot")

# Fallback TroutBot that doesn't require Stockfish
class TroutBot(Player):
    """
    TroutBot implementation that seeks the opponent's king.
    This is a fallback version that doesn't require Stockfish.
    If Stockfish is available via STOCKFISH_EXECUTABLE env var, the official version will be used instead.
    """
    def __init__(self):
        self.board = None
        self.color = None
        self.opponent_king_square = None
        self.using_official = False

        # Try to use official TroutBot if Stockfish is available
        if OFFICIAL_TROUT_AVAILABLE:
            try:
                import os
                if 'STOCKFISH_EXECUTABLE' in os.environ and os.path.exists(os.environ['STOCKFISH_EXECUTABLE']):
                    self.official_bot = OfficialTroutBot()
                    self.using_official = True
                    logger.info("Using official TroutBot with Stockfish")
            except Exception as e:
                logger.info(f"Stockfish not available, using fallback TroutBot: {e}")

    def handle_game_start(self, color: Color, board: chess.Board, opponent_name: str):
        if self.using_official:
            self.official_bot.handle_game_start(color, board, opponent_name)
        else:
            self.board = board.copy()
            self.color = color

    def handle_opponent_move_result(self, captured_my_piece: bool, capture_square: Optional[chess.Square]):
        if self.using_official:
            self.official_bot.handle_opponent_move_result(captured_my_piece, capture_square)
        elif captured_my_piece and capture_square:
            self.board.remove_piece_at(capture_square)

    def choose_sense(self, sense_actions: List[chess.Square], move_actions: List[chess.Move], seconds_left: float) -> Optional[chess.Square]:
        if self.using_official:
            return self.official_bot.choose_sense(sense_actions, move_actions, seconds_left)

        # If we know where the king was, sense there
        if self.opponent_king_square and self.opponent_king_square in sense_actions:
            return self.opponent_king_square

        # Otherwise sense where we might capture or in opponent territory
        for move in move_actions:
            if move.to_square in sense_actions and self.board.piece_at(move.to_square):
                return move.to_square

        # Sense in opponent's back rank
        if self.color == chess.WHITE:
            back_rank = [sq for sq in sense_actions if chess.square_rank(sq) >= 6]
        else:
            back_rank = [sq for sq in sense_actions if chess.square_rank(sq) <= 1]

        return random.choice(back_rank) if back_rank else random.choice(sense_actions)

    def handle_sense_result(self, sense_result: List[Tuple[chess.Square, Optional[chess.Piece]]]):
        if self.using_official:
            self.official_bot.handle_sense_result(sense_result)
        else:
            for square, piece in sense_result:
                self.board.set_piece_at(square, piece)
                # Track opponent king
                if piece and piece.piece_type == chess.KING and piece.color != self.color:
                    self.opponent_king_square = square

    def choose_move(self, move_actions: List[chess.Move], seconds_left: float) -> Optional[chess.Move]:
        if self.using_official:
            return self.official_bot.choose_move(move_actions, seconds_left)

        # Try to capture the enemy king
        enemy_king_square = self.board.king(not self.color)
        if enemy_king_square:
            king_attackers = self.board.attackers(self.color, enemy_king_square)
            if king_attackers:
                attacker_square = king_attackers.pop()
                king_capture_move = chess.Move(attacker_square, enemy_king_square)
                if king_capture_move in move_actions:
                    return king_capture_move

        # Otherwise prefer captures
        captures = [move for move in move_actions if self.board.is_capture(move)]
        if captures:
            return random.choice(captures)

        # Otherwise random move
        return random.choice(move_actions + [None])

    def handle_move_result(self, requested_move: Optional[chess.Move], taken_move: Optional[chess.Move],
                          captured_opponent_piece: bool, capture_square: Optional[chess.Square]):
        if self.using_official:
            self.official_bot.handle_move_result(requested_move, taken_move, captured_opponent_piece, capture_square)
        elif taken_move:
            self.board.push(taken_move)

    def handle_game_end(self, winner_color: Optional[Color], win_reason: Optional[WinReason],
                       game_history: GameHistory):
        if self.using_official:
            self.official_bot.handle_game_end(winner_color, win_reason, game_history)


# ============================================================================
# Human Player - Interactive through MCP
# ============================================================================

class HumanPlayer(Player):
    """A human player that interacts through MCP tools"""

    def __init__(self):
        self.color = None
        self.board = None
        self.sense_choice = None
        self.move_choice = None
        self.opponent_move_info = None
        self.sense_result_data = None
        self.move_result_data = None
        self.waiting_for_sense = False
        self.waiting_for_move = False

    def handle_game_start(self, color: Color, board: chess.Board, opponent_name: str):
        self.color = color
        self.board = board.copy()
        logger.info(f"Human player starting as {color} against {opponent_name}")

    def handle_opponent_move_result(self, captured_my_piece: bool, capture_square: Optional[chess.Square]):
        self.opponent_move_info = {
            "captured_my_piece": captured_my_piece,
            "capture_square": chess.square_name(capture_square) if capture_square else None
        }

    def choose_sense(self, sense_actions: List[chess.Square], move_actions: List[chess.Move], seconds_left: float) -> Optional[chess.Square]:
        self.waiting_for_sense = True
        self.sense_choice = None
        logger.info("Waiting for human to choose sense square...")

        # Wait for human input (using time.sleep since this runs in a thread)
        import time
        while self.sense_choice is None and seconds_left > 1:
            time.sleep(0.1)
            seconds_left -= 0.1

        self.waiting_for_sense = False
        return self.sense_choice

    def handle_sense_result(self, sense_result: List[Tuple[chess.Square, Optional[chess.Piece]]]):
        # Update our board knowledge
        for square, piece in sense_result:
            self.board.set_piece_at(square, piece)

        self.sense_result_data = [
            {
                "square": chess.square_name(square),
                "piece": str(piece) if piece else None,
                "color": "white" if piece and piece.color == chess.WHITE else "black" if piece else None
            }
            for square, piece in sense_result
        ]

    def choose_move(self, move_actions: List[chess.Move], seconds_left: float) -> Optional[chess.Move]:
        self.waiting_for_move = True
        self.move_choice = None
        logger.info("Waiting for human to choose move...")

        # Wait for human input (using time.sleep since this runs in a thread)
        import time
        while self.move_choice is None and seconds_left > 1:
            time.sleep(0.1)
            seconds_left -= 0.1

        self.waiting_for_move = False
        return self.move_choice

    def handle_move_result(self, requested_move: Optional[chess.Move], taken_move: Optional[chess.Move],
                          captured_opponent_piece: bool, capture_square: Optional[chess.Square]):
        if taken_move:
            self.board.push(taken_move)

        self.move_result_data = {
            "requested_move": requested_move.uci() if requested_move else None,
            "taken_move": taken_move.uci() if taken_move else None,
            "captured_opponent_piece": captured_opponent_piece,
            "capture_square": chess.square_name(capture_square) if capture_square else None
        }

    def handle_game_end(self, winner_color: Optional[Color], win_reason: Optional[WinReason],
                       game_history: GameHistory):
        logger.info(f"Game ended. Winner: {winner_color}, Reason: {win_reason}")


# ============================================================================
# Game State Management
# ============================================================================

class GamePhase(Enum):
    """Phase of the game turn"""
    WAITING = "waiting"
    OPPONENT_MOVE_NOTIFICATION = "opponent_move_notification"
    SENSE = "sense"
    MOVE = "move"
    OPPONENT_TURN = "opponent_turn"
    GAME_OVER = "game_over"


@dataclass
class LocalGameState:
    """State for a local RBC game"""
    game_id: int
    game: LocalGame
    human_player: HumanPlayer
    bot_player: Player
    color: Color  # Human's color
    opponent_name: str
    turn: int = 0
    phase: GamePhase = GamePhase.WAITING
    game_thread: Optional[threading.Thread] = None
    game_started: bool = False
    game_over: bool = False
    winner: Optional[Color] = None
    win_reason: Optional[WinReason] = None
    game_history: Optional[GameHistory] = None


@dataclass
class RemoteGameState:
    """State for a remote RBC game on rbc.jhuapl.edu"""
    game_id: int
    server_url: str
    auth_token: str
    remote_game_id: str
    human_player: HumanPlayer
    color: Optional[Color] = None
    phase: GamePhase = GamePhase.WAITING
    game_thread: Optional[threading.Thread] = None
    game_started: bool = False
    game_over: bool = False
    winner: Optional[Color] = None
    win_reason: Optional[WinReason] = None
    error: Optional[str] = None


class GameManager:
    """Manages both local and remote RBC games"""

    def __init__(self):
        self.local_games: Dict[int, LocalGameState] = {}
        self.remote_games: Dict[int, RemoteGameState] = {}
        self.next_game_id = 1

    def create_local_game(self, bot_type: str = "random", human_color: Optional[str] = None) -> int:
        """Create a new local game"""
        game_id = self.next_game_id
        self.next_game_id += 1

        # Create bot
        bot_classes = {
            "random": RandomBot,
            "attacker": AttackerBot,
            "trout": TroutBot
        }

        if bot_type not in bot_classes:
            raise ValueError(f"Unknown bot type: {bot_type}. Available: {list(bot_classes.keys())}")

        bot_player = bot_classes[bot_type]()

        # Determine colors
        if human_color is None or human_color == "random":
            human_color_enum = random.choice([chess.WHITE, chess.BLACK])
        else:
            human_color_enum = chess.WHITE if human_color == "white" else chess.BLACK

        # Create human player
        human_player = HumanPlayer()

        # Create game
        game = LocalGame(seconds_per_player=900)

        self.local_games[game_id] = LocalGameState(
            game_id=game_id,
            game=game,
            human_player=human_player,
            bot_player=bot_player,
            color=human_color_enum,
            opponent_name=f"{bot_type}_bot"
        )

        return game_id

    def create_remote_game(self, server_url: str, auth_token: str, remote_game_id: str) -> int:
        """Create a new remote game session"""
        game_id = self.next_game_id
        self.next_game_id += 1

        human_player = HumanPlayer()

        self.remote_games[game_id] = RemoteGameState(
            game_id=game_id,
            server_url=server_url.rstrip('/'),
            auth_token=auth_token,
            remote_game_id=remote_game_id,
            human_player=human_player
        )

        return game_id


game_manager = GameManager()


# ============================================================================
# Local Game Execution
# ============================================================================

def run_local_game(game_state: LocalGameState):
    """Run a local game in a separate thread"""
    try:
        logger.info(f"Starting local game {game_state.game_id}")
        game_state.game_started = True

        # Determine player order
        if game_state.color == chess.WHITE:
            white_player = game_state.human_player
            black_player = game_state.bot_player
        else:
            white_player = game_state.bot_player
            black_player = game_state.human_player

        # Play the game
        winner_color, win_reason, game_history = play_local_game(
            white_player,
            black_player,
            game=game_state.game,
            seconds_per_player=900.0
        )

        game_state.game_over = True
        game_state.winner = winner_color
        game_state.win_reason = win_reason
        game_state.game_history = game_history
        game_state.phase = GamePhase.GAME_OVER

        logger.info(f"Game {game_state.game_id} finished. Winner: {winner_color}, Reason: {win_reason}")

    except Exception as e:
        logger.error(f"Error in local game {game_state.game_id}: {e}", exc_info=True)
        game_state.game_over = True
        game_state.phase = GamePhase.GAME_OVER


# ============================================================================
# Remote Game Execution
# ============================================================================

def run_remote_game(game_state: RemoteGameState):
    """Run a remote game using reconchess.play_remote_game"""
    try:
        logger.info(f"Starting remote game {game_state.game_id}")
        game_state.game_started = True

        from reconchess import play_remote_game

        # Play remote game
        winner_color, win_reason, game_history = play_remote_game(
            server_url=game_state.server_url,
            game_id=game_state.remote_game_id,
            auth=game_state.auth_token,
            player=game_state.human_player
        )

        game_state.game_over = True
        game_state.winner = winner_color
        game_state.win_reason = win_reason
        game_state.phase = GamePhase.GAME_OVER

        logger.info(f"Remote game {game_state.game_id} finished. Winner: {winner_color}, Reason: {win_reason}")

    except Exception as e:
        logger.error(f"Error in remote game {game_state.game_id}: {e}", exc_info=True)
        game_state.error = str(e)
        game_state.game_over = True
        game_state.phase = GamePhase.GAME_OVER


# ============================================================================
# MCP Server Setup
# ============================================================================

server = Server("reconnaissance-blind-chess")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available RBC tools"""
    return [
        # Local game tools
        Tool(
            name="create_local_game",
            description="Create and start a new local Reconnaissance Blind Chess game against a bot. Returns a game ID. The game will run in a background thread.",
            inputSchema={
                "type": "object",
                "properties": {
                    "bot_type": {
                        "type": "string",
                        "enum": ["random", "attacker", "trout"],
                        "description": "Type of bot opponent: 'random' (plays randomly), 'attacker' (prefers captures), 'trout' (seeks king)",
                        "default": "random"
                    },
                    "color": {
                        "type": "string",
                        "enum": ["white", "black", "random"],
                        "description": "Your color. Use 'random' to let the system choose.",
                        "default": "random"
                    }
                }
            }
        ),
        Tool(
            name="get_game_status",
            description="Get the current status of a local game including phase, turn, and whether it's waiting for your input",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_id": {
                        "type": "integer",
                        "description": "The game ID"
                    }
                },
                "required": ["game_id"]
            }
        ),
        Tool(
            name="get_board_state",
            description="Get your current knowledge of the board in a local game. In RBC, you only see your own pieces and squares you've sensed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_id": {
                        "type": "integer",
                        "description": "The game ID"
                    }
                },
                "required": ["game_id"]
            }
        ),
        Tool(
            name="choose_sense",
            description="Choose a square to sense (reveals 3x3 area). Call this when the game is waiting for your sense choice.",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_id": {
                        "type": "integer",
                        "description": "The game ID"
                    },
                    "square": {
                        "type": "string",
                        "description": "Center square of 3x3 sensing area (e.g., 'e4', 'd5') or 'pass' to skip"
                    }
                },
                "required": ["game_id", "square"]
            }
        ),
        Tool(
            name="choose_move",
            description="Choose a move to make. Call this when the game is waiting for your move choice. Use UCI format (e.g., 'e2e4').",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_id": {
                        "type": "integer",
                        "description": "The game ID"
                    },
                    "move": {
                        "type": "string",
                        "description": "Move in UCI format (e.g., 'e2e4') or 'pass' to skip"
                    }
                },
                "required": ["game_id", "move"]
            }
        ),
        Tool(
            name="get_move_result",
            description="Get the result of your last move (whether it was taken, what you captured)",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_id": {
                        "type": "integer",
                        "description": "The game ID"
                    }
                },
                "required": ["game_id"]
            }
        ),
        Tool(
            name="get_sense_result",
            description="Get the result of your last sense action",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_id": {
                        "type": "integer",
                        "description": "The game ID"
                    }
                },
                "required": ["game_id"]
            }
        ),
        Tool(
            name="get_opponent_move_info",
            description="Get information about opponent's last move (whether they captured your piece)",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_id": {
                        "type": "integer",
                        "description": "The game ID"
                    }
                },
                "required": ["game_id"]
            }
        ),
        Tool(
            name="list_local_games",
            description="List all active local game IDs",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="delete_local_game",
            description="Delete a local game and free its resources",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_id": {
                        "type": "integer",
                        "description": "The game ID to delete"
                    }
                },
                "required": ["game_id"]
            }
        ),
        # Remote game tools
        Tool(
            name="create_remote_game",
            description="Create and start a new remote game session on rbc.jhuapl.edu. The game will run in a background thread.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_url": {
                        "type": "string",
                        "description": "URL of the RBC server (default: https://rbc.jhuapl.edu)",
                        "default": "https://rbc.jhuapl.edu"
                    },
                    "auth_token": {
                        "type": "string",
                        "description": "Authentication token (base64 encoded credentials)"
                    },
                    "remote_game_id": {
                        "type": "string",
                        "description": "Game ID on the remote server"
                    }
                },
                "required": ["auth_token", "remote_game_id"]
            }
        ),
        Tool(
            name="get_remote_game_status",
            description="Get the status of a remote game",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_id": {
                        "type": "integer",
                        "description": "The game ID"
                    }
                },
                "required": ["game_id"]
            }
        ),
        Tool(
            name="list_remote_games",
            description="List all active remote game IDs",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="delete_remote_game",
            description="Delete a remote game session",
            inputSchema={
                "type": "object",
                "properties": {
                    "game_id": {
                        "type": "integer",
                        "description": "The game ID to delete"
                    }
                },
                "required": ["game_id"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    try:
        # Local game tools
        if name == "create_local_game":
            bot_type = arguments.get("bot_type", "random")
            color = arguments.get("color", "random")

            game_id = game_manager.create_local_game(bot_type, color)
            game_state = game_manager.local_games[game_id]

            # Start game in background thread
            game_state.game_thread = threading.Thread(target=run_local_game, args=(game_state,))
            game_state.game_thread.daemon = True
            game_state.game_thread.start()

            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "game_id": game_id,
                    "bot_type": bot_type,
                    "your_color": "white" if game_state.color == chess.WHITE else "black",
                    "opponent": game_state.opponent_name,
                    "message": f"Created game {game_id}. Playing as {'white' if game_state.color == chess.WHITE else 'black'} against {bot_type} bot."
                }, indent=2)
            )]

        elif name == "get_game_status":
            game_id = arguments["game_id"]

            if game_id not in game_manager.local_games:
                return [TextContent(type="text", text=json.dumps({"error": f"Game {game_id} not found"}))]

            game_state = game_manager.local_games[game_id]

            status = {
                "game_id": game_id,
                "your_color": "white" if game_state.color == chess.WHITE else "black",
                "opponent": game_state.opponent_name,
                "turn": game_state.turn,
                "game_started": game_state.game_started,
                "game_over": game_state.game_over,
                "waiting_for_sense": game_state.human_player.waiting_for_sense,
                "waiting_for_move": game_state.human_player.waiting_for_move,
            }

            if game_state.game_over:
                status["winner"] = "white" if game_state.winner == chess.WHITE else "black" if game_state.winner == chess.BLACK else "draw"
                status["win_reason"] = str(game_state.win_reason) if game_state.win_reason else None

            return [TextContent(type="text", text=json.dumps(status, indent=2))]

        elif name == "get_board_state":
            game_id = arguments["game_id"]

            if game_id not in game_manager.local_games:
                return [TextContent(type="text", text=json.dumps({"error": f"Game {game_id} not found"}))]

            game_state = game_manager.local_games[game_id]
            board = game_state.human_player.board

            if board is None:
                return [TextContent(type="text", text=json.dumps({"error": "Board not initialized yet"}))]

            return [TextContent(
                type="text",
                text=json.dumps({
                    "board_fen": board.fen(),
                    "board_unicode": str(board),
                    "your_color": "white" if game_state.color == chess.WHITE else "black"
                }, indent=2)
            )]

        elif name == "choose_sense":
            game_id = arguments["game_id"]
            square_str = arguments["square"]

            if game_id not in game_manager.local_games:
                return [TextContent(type="text", text=json.dumps({"error": f"Game {game_id} not found"}))]

            game_state = game_manager.local_games[game_id]

            if not game_state.human_player.waiting_for_sense:
                return [TextContent(type="text", text=json.dumps({"error": "Not waiting for sense choice"}))]

            if square_str.lower() == "pass":
                game_state.human_player.sense_choice = None
            else:
                try:
                    game_state.human_player.sense_choice = chess.parse_square(square_str)
                except:
                    return [TextContent(type="text", text=json.dumps({"error": f"Invalid square: {square_str}"}))]

            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "sense_square": square_str,
                    "message": f"Sense choice set to {square_str}"
                }, indent=2)
            )]

        elif name == "choose_move":
            game_id = arguments["game_id"]
            move_str = arguments["move"]

            if game_id not in game_manager.local_games:
                return [TextContent(type="text", text=json.dumps({"error": f"Game {game_id} not found"}))]

            game_state = game_manager.local_games[game_id]

            if not game_state.human_player.waiting_for_move:
                return [TextContent(type="text", text=json.dumps({"error": "Not waiting for move choice"}))]

            if move_str.lower() == "pass":
                game_state.human_player.move_choice = None
            else:
                try:
                    game_state.human_player.move_choice = chess.Move.from_uci(move_str)
                except:
                    return [TextContent(type="text", text=json.dumps({"error": f"Invalid move: {move_str}"}))]

            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "move": move_str,
                    "message": f"Move choice set to {move_str}"
                }, indent=2)
            )]

        elif name == "get_sense_result":
            game_id = arguments["game_id"]

            if game_id not in game_manager.local_games:
                return [TextContent(type="text", text=json.dumps({"error": f"Game {game_id} not found"}))]

            game_state = game_manager.local_games[game_id]

            if game_state.human_player.sense_result_data is None:
                return [TextContent(type="text", text=json.dumps({"error": "No sense result available yet"}))]

            return [TextContent(
                type="text",
                text=json.dumps({
                    "sense_result": game_state.human_player.sense_result_data
                }, indent=2)
            )]

        elif name == "get_move_result":
            game_id = arguments["game_id"]

            if game_id not in game_manager.local_games:
                return [TextContent(type="text", text=json.dumps({"error": f"Game {game_id} not found"}))]

            game_state = game_manager.local_games[game_id]

            if game_state.human_player.move_result_data is None:
                return [TextContent(type="text", text=json.dumps({"error": "No move result available yet"}))]

            return [TextContent(
                type="text",
                text=json.dumps({
                    "move_result": game_state.human_player.move_result_data
                }, indent=2)
            )]

        elif name == "get_opponent_move_info":
            game_id = arguments["game_id"]

            if game_id not in game_manager.local_games:
                return [TextContent(type="text", text=json.dumps({"error": f"Game {game_id} not found"}))]

            game_state = game_manager.local_games[game_id]

            if game_state.human_player.opponent_move_info is None:
                return [TextContent(type="text", text=json.dumps({"error": "No opponent move info available yet"}))]

            return [TextContent(
                type="text",
                text=json.dumps({
                    "opponent_move_info": game_state.human_player.opponent_move_info
                }, indent=2)
            )]

        elif name == "list_local_games":
            return [TextContent(
                type="text",
                text=json.dumps({
                    "local_games": list(game_manager.local_games.keys())
                }, indent=2)
            )]

        elif name == "delete_local_game":
            game_id = arguments["game_id"]
            if game_id in game_manager.local_games:
                del game_manager.local_games[game_id]
                return [TextContent(type="text", text=json.dumps({"success": True, "message": f"Deleted game {game_id}"}))]
            return [TextContent(type="text", text=json.dumps({"error": f"Game {game_id} not found"}))]

        # Remote game tools
        elif name == "create_remote_game":
            server_url = arguments.get("server_url", "https://rbc.jhuapl.edu")
            auth_token = arguments["auth_token"]
            remote_game_id = arguments["remote_game_id"]

            game_id = game_manager.create_remote_game(server_url, auth_token, remote_game_id)
            game_state = game_manager.remote_games[game_id]

            # Start game in background thread
            game_state.game_thread = threading.Thread(target=run_remote_game, args=(game_state,))
            game_state.game_thread.daemon = True
            game_state.game_thread.start()

            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "game_id": game_id,
                    "server_url": server_url,
                    "remote_game_id": remote_game_id,
                    "message": f"Created remote game {game_id}"
                }, indent=2)
            )]

        elif name == "get_remote_game_status":
            game_id = arguments["game_id"]

            if game_id not in game_manager.remote_games:
                return [TextContent(type="text", text=json.dumps({"error": f"Remote game {game_id} not found"}))]

            game_state = game_manager.remote_games[game_id]

            status = {
                "game_id": game_id,
                "server_url": game_state.server_url,
                "remote_game_id": game_state.remote_game_id,
                "game_started": game_state.game_started,
                "game_over": game_state.game_over,
                "waiting_for_sense": game_state.human_player.waiting_for_sense,
                "waiting_for_move": game_state.human_player.waiting_for_move,
            }

            if game_state.color is not None:
                status["your_color"] = "white" if game_state.color == chess.WHITE else "black"

            if game_state.error:
                status["error"] = game_state.error

            if game_state.game_over:
                status["winner"] = "white" if game_state.winner == chess.WHITE else "black" if game_state.winner == chess.BLACK else "draw"
                status["win_reason"] = str(game_state.win_reason) if game_state.win_reason else None

            return [TextContent(type="text", text=json.dumps(status, indent=2))]

        elif name == "list_remote_games":
            return [TextContent(
                type="text",
                text=json.dumps({
                    "remote_games": list(game_manager.remote_games.keys())
                }, indent=2)
            )]

        elif name == "delete_remote_game":
            game_id = arguments["game_id"]
            if game_id in game_manager.remote_games:
                del game_manager.remote_games[game_id]
                return [TextContent(type="text", text=json.dumps({"success": True, "message": f"Deleted remote game {game_id}"}))]
            return [TextContent(type="text", text=json.dumps({"error": f"Remote game {game_id} not found"}))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        logger.error(f"Error in tool {name}: {e}", exc_info=True)
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)}, indent=2)
        )]


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Main entry point for the MCP server"""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
