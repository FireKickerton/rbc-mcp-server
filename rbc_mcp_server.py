#!/usr/bin/env python3
"""
Reconnaissance Blind Chess MCP Server

This MCP server allows LLM agents to play Reconnaissance Blind Chess (RBC) games
remotely on rbc.jhuapl.edu against various bots in ranked or unranked modes.
"""

import asyncio
import requests
import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import threading
import time
import traceback

# Set up file logging - force configuration even if root logger is already configured
LOG_FILE = "/tmp/rbc_mcp.log"
logger = logging.getLogger("rbc_mcp")
logger.setLevel(logging.DEBUG)

# Remove any existing handlers
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Add file handler
file_handler = logging.FileHandler(LOG_FILE, mode='a')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Add stderr handler
stderr_handler = logging.StreamHandler()
stderr_handler.setLevel(logging.DEBUG)
stderr_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stderr_handler)

# Prevent propagation to root logger
logger.propagate = False

logger.info(f"RBC MCP Server logging initialized, writing to {LOG_FILE}")

import chess
import reconchess
from reconchess import Color, Square, WinReason

from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
)
import mcp.server.stdio

# ============================================================================
# RBC Server Connection - Based on rc_connect.py in reconchess
# ============================================================================

class APIRetryError(Exception):
    """Raised when API calls fail after max retries"""
    def __init__(self, message: str, game_id: int = None):
        super().__init__(message)
        self.game_id = game_id


class RBCServer:
    """
    RBC Server API client based on reconchess server HTTP API.
    See: https://reconchess.readthedocs.io/en/latest/reconchess_server.html
    """
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds

    def __init__(self, server_url, auth, current_game_id: int = None):
        self.server_url = server_url.rstrip('/')
        self.invitations_url = '{}/api/invitations'.format(self.server_url)
        self.user_url = '{}/api/users'.format(self.server_url)
        self.me_url = '{}/api/users/me'.format(self.server_url)
        self.game_url = '{}/api/games'.format(self.server_url)
        self.session = requests.Session()
        self.session.auth = auth
        self.current_game_id = current_game_id

    def _game_url(self, game_id: int, endpoint: str = '') -> str:
        """Build a game-specific API URL"""
        if endpoint:
            return '{}/{}/{}'.format(self.game_url, game_id, endpoint)
        return '{}/{}'.format(self.game_url, game_id)

    def _error_resign(self, game_id: int):
        """Emergency resign when API calls fail repeatedly"""
        try:
            logger.error(f"Attempting error_resign for game {game_id} due to API failures")
            url = self._game_url(game_id, 'error_resign')
            response = self.session.post(url)
            logger.info(f"error_resign for game {game_id} returned status {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to error_resign game {game_id}: {e}")

    def _get(self, url: str, game_id: int = None) -> dict:
        """Make a GET request and return JSON response with retry logic"""
        effective_game_id = game_id or self.current_game_id

        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug(f"GET {url} (attempt {attempt + 1}/{self.MAX_RETRIES})")
                response = self.session.get(url, timeout=30)
                logger.debug(f"GET {url} -> status={response.status_code}")

                if response.status_code >= 500:
                    logger.warning(f"GET {url} returned {response.status_code}, retrying...")
                    time.sleep(self.RETRY_DELAY)
                    continue

                if response.status_code == 401:
                    raise ValueError('Authentication Error: {}'.format(response.text))

                if response.status_code >= 400:
                    logger.error(f"GET {url} returned client error {response.status_code}: {response.text}")
                    raise ValueError(f'API Error {response.status_code}: {response.text}')

                result = response.json()
                logger.debug(f"GET {url} -> {result}")
                return result

            except requests.exceptions.Timeout:
                logger.warning(f"GET {url} timed out (attempt {attempt + 1}/{self.MAX_RETRIES})")
                time.sleep(self.RETRY_DELAY)
            except requests.exceptions.RequestException as e:
                logger.warning(f"GET {url} failed with {e} (attempt {attempt + 1}/{self.MAX_RETRIES})")
                time.sleep(self.RETRY_DELAY)

        # All retries failed
        logger.error(f"GET {url} failed after {self.MAX_RETRIES} retries")
        if effective_game_id:
            self._error_resign(effective_game_id)
        raise APIRetryError(f"GET {url} failed after {self.MAX_RETRIES} retries", effective_game_id)

    def _post(self, url: str, json: dict = None, game_id: int = None) -> dict:
        """Make a POST request and return JSON response with retry logic"""
        effective_game_id = game_id or self.current_game_id

        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug(f"POST {url} with json={json} (attempt {attempt + 1}/{self.MAX_RETRIES})")
                response = self.session.post(url, json=json, timeout=30)
                logger.debug(f"POST {url} -> status={response.status_code}")

                if response.status_code >= 500:
                    logger.warning(f"POST {url} returned {response.status_code}, retrying...")
                    time.sleep(self.RETRY_DELAY)
                    continue

                if response.status_code == 401:
                    raise ValueError('Authentication Error: {}'.format(response.text))

                if response.status_code >= 400:
                    logger.error(f"POST {url} returned client error {response.status_code}: {response.text}")
                    raise ValueError(f'API Error {response.status_code}: {response.text}')

                result = response.json()
                logger.debug(f"POST {url} -> {result}")
                return result

            except requests.exceptions.Timeout:
                logger.warning(f"POST {url} timed out (attempt {attempt + 1}/{self.MAX_RETRIES})")
                time.sleep(self.RETRY_DELAY)
            except requests.exceptions.RequestException as e:
                logger.warning(f"POST {url} failed with {e} (attempt {attempt + 1}/{self.MAX_RETRIES})")
                time.sleep(self.RETRY_DELAY)

        # All retries failed
        logger.error(f"POST {url} failed after {self.MAX_RETRIES} retries")
        if effective_game_id:
            self._error_resign(effective_game_id)
        raise APIRetryError(f"POST {url} failed after {self.MAX_RETRIES} retries", effective_game_id)

    # =========================================================================
    # User Endpoints - /api/users/
    # =========================================================================

    def get_active_users(self) -> list[str]:
        """GET /api/users/ - Returns array of active usernames"""
        return self._get('{}/'.format(self.user_url))['usernames']

    def set_max_games(self, max_games: int):
        """POST /api/users/me/max_games - Set maximum concurrent games"""
        self._post('{}/max_games'.format(self.me_url), json={'max_games': max_games})

    def set_ranked(self, ranked: bool):
        """POST /api/users/me/ranked - Set ranked preference status"""
        self._post('{}/ranked'.format(self.me_url), json={'ranked': ranked})

    def get_bot_version(self) -> int:
        """GET /api/users/me/version - Get current bot version number"""
        return self._get('{}/version'.format(self.me_url))['version']

    def increment_version(self):
        """POST /api/users/me/version - Increment bot version for ranked matches"""
        self._post('{}/version'.format(self.me_url))

    # =========================================================================
    # Invitation Endpoints - /api/invitations/
    # =========================================================================

    def get_invitations(self) -> list:
        """GET /api/invitations/ - Returns array of unaccepted invitation IDs"""
        return self._get('{}/'.format(self.invitations_url))['invitations']

    def send_invitation(self, opponent: str, color: bool) -> int:
        """POST /api/invitations/ - Send invitation to opponent, returns game_id"""
        return self._post('{}/'.format(self.invitations_url), json={
            'opponent': opponent,
            'color': color,
        })['game_id']

    def accept_invitation(self, invitation_id: str) -> int:
        """POST /api/invitations/{invitation_id} - Accept invitation, returns game_id"""
        return self._post('{}/{}'.format(self.invitations_url, invitation_id))['game_id']

    def finish_invitation(self, invitation_id: str):
        """POST /api/invitations/{invitation_id}/finish - Mark invitation as finished"""
        self._post('{}/{}/finish'.format(self.invitations_url, invitation_id))

    # =========================================================================
    # Game Endpoints - /api/games/{game_id}/
    # =========================================================================

    def get_player_color(self, game_id: int) -> bool:
        """GET /api/games/{game_id}/color - Returns player color (true=White, false=Black)"""
        return self._get(self._game_url(game_id, 'color'))['color']

    def get_starting_board(self, game_id: int) -> str:
        """GET /api/games/{game_id}/starting_board - Returns board FEN string"""
        return self._get(self._game_url(game_id, 'starting_board'))['board']

    def get_opponent_name(self, game_id: int) -> str:
        """GET /api/games/{game_id}/opponent_name - Returns opponent's username"""
        return self._get(self._game_url(game_id, 'opponent_name'))['opponent_name']

    def start(self, game_id: int):
        """POST /api/games/{game_id}/ready - Mark player as ready to start"""
        self._post(self._game_url(game_id, 'ready'), {})

    def sense_actions(self, game_id: int) -> list[Square]:
        """GET /api/games/{game_id}/sense_actions - Returns list of sensable squares"""
        return self._get(self._game_url(game_id, 'sense_actions'))['sense_actions']

    def move_actions(self, game_id: int) -> list[chess.Move]:
        """GET /api/games/{game_id}/move_actions - Returns list of legal moves"""
        return self._get(self._game_url(game_id, 'move_actions'))['move_actions']

    def get_seconds_left(self, game_id: int) -> float:
        """GET /api/games/{game_id}/seconds_left - Returns remaining time in seconds"""
        return self._get(self._game_url(game_id, 'seconds_left'))['seconds_left']

    def opponent_move_results(self, game_id: int) -> Optional[Square]:
        """GET /api/games/{game_id}/opponent_move_results - Returns capture square or null"""
        return self._get(self._game_url(game_id, 'opponent_move_results'))['opponent_move_results']

    def sense(self, game_id: int, square: Optional[Square]) -> list[tuple[Square, Optional[chess.Piece]]]:
        """POST /api/games/{game_id}/sense - Sense a square, returns list of [square, piece] pairs"""
        return self._post(self._game_url(game_id, 'sense'), {'square': square})['sense_result']

    def move(self, game_id: int, requested_move: Optional[chess.Move]) -> tuple[
        Optional[chess.Move], Optional[chess.Move], Optional[Square]]:
        """POST /api/games/{game_id}/move - Make a move, returns [requested_move, taken_move, capture_square]"""
        # Convert Move object to the format expected by the RBC server
        if requested_move:
            move_data = {"type": "Move", "value": requested_move.uci()}
        else:
            move_data = None
        return self._post(self._game_url(game_id, 'move'), {'requested_move': move_data})['move_result']

    def end_turn(self, game_id: int):
        """POST /api/games/{game_id}/end_turn - Complete player's turn"""
        self._post(self._game_url(game_id, 'end_turn'), {})

    def is_my_turn(self, game_id: int) -> bool:
        """GET /api/games/{game_id}/is_my_turn - Check if it's player's turn"""
        return self._get(self._game_url(game_id, 'is_my_turn'))['is_my_turn']

    def is_over(self, game_id: int) -> bool:
        """GET /api/games/{game_id}/is_over - Check if game has ended"""
        return self._get(self._game_url(game_id, 'is_over'))['is_over']

    def get_game_status(self, game_id: int) -> dict:
        """GET /api/games/{game_id}/game_status - Returns {is_my_turn, is_over}"""
        return self._get(self._game_url(game_id, 'game_status'))

    def resign(self, game_id: int):
        """POST /api/games/{game_id}/resign - Player resigns during their turn"""
        self._post(self._game_url(game_id, 'resign'))

    def error_resign(self, game_id: int):
        """POST /api/games/{game_id}/error_resign - Report bot error, zeroes remaining time"""
        self._post(self._game_url(game_id, 'error_resign'))

    def get_winner_color(self, game_id: int) -> Optional[Color]:
        """GET /api/games/{game_id}/winner_color - Returns winner color or null for draw"""
        return self._get(self._game_url(game_id, 'winner_color'))['winner_color']

    def get_win_reason(self, game_id: int) -> Optional[str]:
        """GET /api/games/{game_id}/win_reason - Returns win reason string"""
        win_reason = self._get(self._game_url(game_id, 'win_reason'))['win_reason']
        # Handle dict response format: {"type": "WinReason", "value": "KING_CAPTURE"}
        if win_reason is None:
            return None
        if isinstance(win_reason, dict):
            return win_reason.get('value', str(win_reason))
        if hasattr(win_reason, 'name'):
            return win_reason.name
        return str(win_reason)


# Turn phase tracking
class TurnPhase:
    """Tracks which phase of the turn we're in"""
    WAITING_FOR_TURN = "waiting_for_turn"
    NEED_OPPONENT_RESULT = "need_opponent_result"
    NEED_SENSE = "need_sense"
    NEED_MOVE = "need_move"
    TURN_COMPLETE = "turn_complete"

# Game state tracking
@dataclass
class GameState:
    """Tracks the state of an active RBC game"""
    game_id: int
    board: chess.Board
    is_ranked: bool
    turn_phase: str = TurnPhase.WAITING_FOR_TURN
    current_turn: int = 0
    player_color: Optional[bool] = None  # True = White, False = Black
    opponent_name: Optional[str] = None
    last_sense_result: Optional[list] = None
    last_move_result: Optional[dict] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert game state to dictionary"""
        return {
            "game_id": self.game_id,
            "board_fen": self.board.fen(),
            "is_ranked": self.is_ranked,
            "turn_phase": self.turn_phase,
            "current_turn": self.current_turn,
        }

class RBCMCPServer:
    """MCP Server for Reconnaissance Blind Chess"""

    def __init__(self):
        self.server = Server("rbc-mcp-server")
        self.active_games: Dict[int, GameState] = {}
        self.server_url = "https://rbc.jhuapl.edu"

        # Ranked game listener
        self.invitation_listener_thread: Optional[threading.Thread] = None
        self.invitation_games: Dict[str, GameState] = {}  # Track invitation-based games (invitation_id is string)
        self.stop_listening = threading.Event()

        # Register handlers
        self.server.list_resources()(self.list_resources)
        self.server.read_resource()(self.read_resource)
        self.server.list_tools()(self.list_tools)
        self.server.call_tool()(self.call_tool)

    async def list_resources(self) -> List[Resource]:
        """List available game state resources"""
        resources = []
        for game_id, game_state in self.active_games.items():
            resources.append(
                Resource(
                    uri=f"rbc://game/{game_id}",
                    name=f"RBC Game {game_id}",
                    mimeType="application/json",
                    description=f"Game state for {'ranked' if game_state.is_ranked else 'unranked'} game {game_id}",
                )
            )
        return resources

    async def read_resource(self, uri: str) -> str:
        """Read a game state resource"""
        if uri.startswith("rbc://game/"):
            game_id_str = uri.replace("rbc://game/", "")
            try:
                game_id = int(game_id_str)
                if game_id in self.active_games:
                    game_state = self.active_games[game_id]
                    return json.dumps(game_state.to_dict(), indent=2)
            except ValueError:
                raise ValueError(f"Invalid game ID in URI: {game_id_str}")
        raise ValueError(f"Unknown resource: {uri}")

    async def list_tools(self) -> List[Tool]:
        """List available RBC tools"""
        return [
            Tool(
                name="start_unranked_game",
                description="Start an unranked RBC game against a specific bot. Choose opponent and color.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "opponent_bot": {
                            "type": "string",
                            "description": "Bot name (e.g., 'random', 'attacker', 'trout', 'oracle', 'strangefish2')",
                        },
                        "color": {
                            "type": "string",
                            "enum": ["white", "black", "random"],
                            "description": "Color to play as",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["opponent_bot", "color", "username", "password"],
                },
            ),
            Tool(
                name="start_ranked_game",
                description="Start listening for ranked game invitations from the RBC server. Accepts invitations automatically and plays with assigned color.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                        "max_concurrent_games": {
                            "type": "integer",
                            "description": "Maximum number of concurrent ranked games to play (default: 1)",
                            "default": 1,
                        },
                    },
                    "required": ["username", "password"],
                },
            ),
            Tool(
                name="stop_ranked_listener",
                description="Stop listening for ranked game invitations.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="get_board_ascii",
                description="Get ASCII representation of the current board state",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                    },
                    "required": ["game_id"],
                },
            ),
            Tool(
                name="get_game_status",
                description="Get the current status of a game from the server (is_my_turn and is_over)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="handle_opponent_move_result",
                description="Get the opponent's move result from the server. Returns whether your piece was captured and on which square.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="submit_sense",
                description="Submit a sense action for the current turn. Returns the pieces found in the 3x3 region centered on the chosen square.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "square": {
                            "type": "string",
                            "description": "Square to sense (e.g., 'e4', 'd5') or 'pass' to skip sensing",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "square", "username", "password"],
                },
            ),
            Tool(
                name="submit_move",
                description="Submit a move for the current turn. Returns the requested move, actual move taken, and any capture information.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "move": {
                            "type": "string",
                            "description": "Move in UCI format (e.g., 'e2e4', 'e7e8q') or 'pass' to skip moving",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "move", "username", "password"],
                },
            ),
            Tool(
                name="get_sense_actions",
                description="Get the list of valid sense actions (squares) for the current turn. Returns squares that can be sensed (centers of 3x3 regions).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="get_move_actions",
                description="Get the list of valid move actions for the current turn. Returns all legal moves in UCI format.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="is_game_over",
                description="Check if a game is over. Returns whether the game has ended, and if so, the winner and win reason.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="get_bot_version",
                description="Get the current bot version number for your account. Use increment_bot_version to increase it.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["username", "password"],
                },
            ),
            Tool(
                name="increment_bot_version",
                description="Increment the bot version number for your account. Use get_bot_version first to check the current version.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["username", "password"],
                },
            ),
            Tool(
                name="get_winner_color",
                description="Get the winner color of a finished game. Returns 'White', 'Black', or 'None' for draw.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="get_win_reason",
                description="Get the win reason of a finished game. Returns the reason for the game ending (e.g., 'KING_CAPTURE', 'TIMEOUT', 'RESIGN', etc.).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="get_game_state",
                description="Get the current state of a game including board position and is_ranked",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                    },
                    "required": ["game_id"],
                },
            ),
            Tool(
                name="list_active_games",
                description="List all currently active games",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            # =========================================================
            # Additional API Tools
            # =========================================================
            Tool(
                name="get_active_users",
                description="Get a list of all active usernames on the RBC server.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["username", "password"],
                },
            ),
            Tool(
                name="set_max_games",
                description="Set the maximum number of concurrent games you can play.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "max_games": {
                            "type": "integer",
                            "description": "Maximum number of concurrent games",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["max_games", "username", "password"],
                },
            ),
            Tool(
                name="set_ranked",
                description="Set your ranked preference status (whether you want to play ranked games).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "ranked": {
                            "type": "boolean",
                            "description": "True to enable ranked games, false to disable",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["ranked", "username", "password"],
                },
            ),
            Tool(
                name="get_invitations",
                description="Get a list of pending game invitations.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["username", "password"],
                },
            ),
            Tool(
                name="get_player_color",
                description="Get the color you are playing as in a game (White or Black).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="get_starting_board",
                description="Get the starting board position (FEN) for a game.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="get_opponent_name",
                description="Get the opponent's username for a game.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="start_game",
                description="Mark yourself as ready to start a game. Call this after accepting an invitation.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="get_seconds_left",
                description="Get the remaining time in seconds for the current player.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="submit_end_turn",
                description="End the current turn. Call this after submitting your move.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="resign",
                description="Resign from a game during your turn.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
            Tool(
                name="error_resign",
                description="Report a bot error and resign. This zeroes your remaining time.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "integer",
                            "description": "The game ID",
                        },
                        "username": {
                            "type": "string",
                            "description": "Your username on rbc.jhuapl.edu",
                        },
                        "password": {
                            "type": "string",
                            "description": "Your password on rbc.jhuapl.edu",
                        },
                    },
                    "required": ["game_id", "username", "password"],
                },
            ),
        ]

    async def call_tool(self, name: str, arguments: dict) -> List[TextContent]:
        """Handle tool calls"""
        logger.info(f"call_tool called with name={name}, arguments={arguments}")
        try:
            result = await self._call_tool_impl(name, arguments)
            logger.info(f"call_tool {name} returning: {result}")
            return result
        except Exception as e:
            logger.error(f"call_tool {name} failed with error: {e}")
            logger.error(traceback.format_exc())
            raise

    async def _call_tool_impl(self, name: str, arguments: dict) -> List[TextContent]:
        """Implementation of tool calls"""

        if name == "start_unranked_game":
            return await self.start_unranked_game(
                arguments["opponent_bot"],
                arguments["color"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "start_ranked_game":
            max_concurrent = arguments.get("max_concurrent_games", 1)
            return await self.start_ranked_game(
                arguments["username"],
                arguments["password"],
                max_concurrent,
            )

        elif name == "stop_ranked_listener":
            return await self.stop_ranked_listener()

        elif name == "get_board_ascii":
            return await self.get_board_ascii(arguments["game_id"])

        elif name == "get_game_status":
            return await self.get_game_status_tool(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "handle_opponent_move_result":
            return await self.handle_opponent_move_result(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "submit_sense":
            return await self.submit_sense(
                arguments["game_id"],
                arguments["square"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "submit_move":
            return await self.submit_move(
                arguments["game_id"],
                arguments["move"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "get_move_actions":
            return await self.get_move_actions(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "is_game_over":
            return await self.is_game_over(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "get_bot_version":
            return await self.get_bot_version(
                arguments["username"],
                arguments["password"],
            )

        elif name == "increment_bot_version":
            return await self.increment_bot_version(
                arguments["username"],
                arguments["password"],
            )

        elif name == "get_winner_color":
            return await self.get_winner_color(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "get_win_reason":
            return await self.get_win_reason(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "list_active_games":
            return await self.list_active_games()

        elif name == "get_game_state":
            return await self.get_game_state(arguments["game_id"])

        elif name == "get_sense_actions":
            return await self.get_sense_actions(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "get_active_users":
            return await self.get_active_users_tool(
                arguments["username"],
                arguments["password"],
            )

        elif name == "set_max_games":
            return await self.set_max_games_tool(
                arguments["max_games"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "set_ranked":
            return await self.set_ranked_tool(
                arguments["ranked"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "get_invitations":
            return await self.get_invitations_tool(
                arguments["username"],
                arguments["password"],
            )

        elif name == "get_player_color":
            return await self.get_player_color_tool(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "get_starting_board":
            return await self.get_starting_board_tool(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "get_opponent_name":
            return await self.get_opponent_name_tool(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "start_game":
            return await self.start_game_tool(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "get_seconds_left":
            return await self.get_seconds_left_tool(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "submit_end_turn":
            return await self.end_turn_tool(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "resign":
            return await self.resign_tool(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        elif name == "error_resign":
            return await self.error_resign_tool(
                arguments["game_id"],
                arguments["username"],
                arguments["password"],
            )

        else:
            raise ValueError(f"Unknown tool: {name}")

 
    async def start_unranked_game(self, opponent_bot: str, color: str,
                                   username: str, password: str) -> List[TextContent]:
        """
        Start an unranked game against a bot (based on rc_play_on_server.py).
        Uses server.send_invitation() to create the game.
        """
        import random

        # Determine color (following rc_play_on_server.py logic)
        if color == "black" or (color == "random" and random.uniform(0, 1) < 0.5):
            play_color = chess.BLACK
        else:
            play_color = chess.WHITE

        color_str = "white" if play_color == chess.WHITE else "black"
        """
        Play an unranked game against a bot (based on rc_play_on_server.py).
        Runs in a background thread.
        """
        auth = (username, password)
        try:
            # Connect to server and send invitation
            server = RBCServer(self.server_url, auth)

            print(f'[{datetime.now()}] Sending invitation to {opponent_bot} and requesting to play as {"white" if play_color == chess.WHITE else "black"}')

            # Send invitation to the bot and get game ID
            game_id = server.send_invitation(opponent_bot, play_color)

            print(f'[{datetime.now()}] Invitation accepted. Game ID: {game_id}')

            # Create game state
            game_state = GameState(
                game_id=game_id,
                board=chess.Board(),
                is_ranked=False,
                turn_phase=TurnPhase.WAITING_FOR_TURN,
                current_turn=0,
                player_color=(play_color == chess.WHITE),
                opponent_name=opponent_bot,
            )

            # Store in active games
            self.active_games[game_id] = game_state

        except Exception as e:
            print(f'[{datetime.now()}] Error starting unranked game against {opponent_bot}:')
            print(f'Error: {e}')
            traceback.print_exc()

        return [
            TextContent(
                type="text",
                text=f"Sent invitation to {opponent_bot} with request to play as {color_str}...\n\n"
                     f"The game will start when the invitation is accepted.\n"
                     f"Use 'get_game_status' to see when the game begins.\n"
            )
        ]

    def _listen_for_invitations(self, server_url: str, auth: tuple, max_concurrent_games: int):
        """
        Listen for ranked game invitations (based on rc_connect.py).
        Runs in a background thread and accepts invitations automatically.
        """
        #from reconchess.utilities import RBCServer

        server = RBCServer(server_url, auth)
        connected = False
        invitation_threads: Dict[str, threading.Thread] = {}
        finished_invitations: Dict[str, bool] = {}

        while not self.stop_listening.is_set():
            try:
                invitations = server.get_invitations()

                if not connected:
                    print(f'[{datetime.now()}] Connected successfully to server!')
                    connected = True
                    server.set_max_games(max_concurrent_games)

                # Clean up finished games
                finished = []
                for invitation_id in invitation_threads.keys():
                    if not invitation_threads[invitation_id].is_alive() or finished_invitations.get(invitation_id, False):
                        finished.append(invitation_id)

                for invitation_id in finished:
                    print(f'[{datetime.now()}] Terminating process for invitation {invitation_id}')
                    invitation_threads[invitation_id].join(timeout=1)
                    del invitation_threads[invitation_id]
                    if invitation_id in finished_invitations:
                        del finished_invitations[invitation_id]

                # Accept new invitations
                for invitation_id in invitations:
                    if invitation_id not in invitation_threads:
                        print(f'[{datetime.now()}] Received invitation {invitation_id}.')

                        if len(invitation_threads) < max_concurrent_games:
                            # Start thread to accept and play the game
                            thread = threading.Thread(
                                target=self._accept_invitation_and_play,
                                args=(server_url, auth, invitation_id, finished_invitations),
                                daemon=True,
                            )
                            thread.start()
                            invitation_threads[invitation_id] = thread
                        else:
                            print(f'[{datetime.now()}] Not enough game slots to play invitation {invitation_id}.')

            except Exception as e:
                connected = False
                print(f'[{datetime.now()}] Failed to connect to server')
                print(f'Error: {e}')
                traceback.print_exc()

            # Sleep for 5 seconds before checking again
            time.sleep(5)

        print(f'[{datetime.now()}] Stopped listening for invitations')

    def _accept_invitation_and_play(self, server_url: str, auth: tuple,
                                     invitation_id: str, finished_dict: Dict[str, bool]):
        """
        Accept an invitation and play the game (based on rc_connect.py).
        Replaces bot_cls with LLMPlayer instance.
        """
        #from reconchess.utilities import RBCServer

        try:
            print(f'[{datetime.now()}] Accepting invitation {invitation_id}.')

            server = RBCServer(server_url, auth)
            game_id = server.accept_invitation(invitation_id)

            print(f'[{datetime.now()}] Invitation {invitation_id} accepted. Playing game {game_id}.')

            # Create game state
            game_state = GameState(
                game_id=game_id,
                board=chess.Board(),
                is_ranked=True,
            )

            # Create LLMPlayer instance
            #player = LLMPlayer(game_state)

            # Store in active games
            self.active_games[game_id] = game_state
            #self.active_players[game_id] = player
            self.invitation_games[invitation_id] = game_state

            # Play the game
            try:
                #reconchess.play_remote_game(server_url, game_id, auth, player)
                print(f'[{datetime.now()}] Finished game {game_id}')
            except Exception as game_error:
                print(f'[{datetime.now()}] Fatal error in game {game_id}:')
                traceback.print_exc()
                server.error_resign(game_id)
            finally:
                server.finish_invitation(invitation_id)
                finished_dict[invitation_id] = True

        except Exception as e:
            print(f'[{datetime.now()}] Error accepting invitation {invitation_id}:')
            print(f'Error: {e}')
            traceback.print_exc()
            finished_dict[invitation_id] = True

    async def start_ranked_game(self, username: str, password: str,
                                max_concurrent_games: int = 1) -> List[TextContent]:
        """Start listening for ranked game invitations"""

        if self.invitation_listener_thread and self.invitation_listener_thread.is_alive():
            return [
                TextContent(
                    type="text",
                    text="Already listening for ranked game invitations. Use 'stop_ranked_listener' to stop.",
                )
            ]

        # Reset stop flag
        self.stop_listening.clear()

        # Start listener thread
        auth = (username, password)
        self.invitation_listener_thread = threading.Thread(
            target=self._listen_for_invitations,
            args=(self.server_url, auth, max_concurrent_games),
            daemon=True,
        )
        self.invitation_listener_thread.start()

        return [
            TextContent(
                type="text",
                text=f"Started listening for ranked game invitations.\n\n"
                     f"Server: {self.server_url}\n"
                     f"Max concurrent games: {max_concurrent_games}\n"
                     f"Username: {username}\n\n"
                     f"When invitations are received, games will start automatically.\n"
                     f"Use 'list_active_games' to see ongoing games.\n"
                     f"Use 'stop_ranked_listener' to stop listening.",
            )
        ]

    async def stop_ranked_listener(self) -> List[TextContent]:
        """Stop listening for ranked game invitations"""

        if not self.invitation_listener_thread or not self.invitation_listener_thread.is_alive():
            return [
                TextContent(
                    type="text",
                    text="Not currently listening for invitations.",
                )
            ]

        self.stop_listening.set()
        self.invitation_listener_thread.join(timeout=10)

        return [
            TextContent(
                type="text",
                text="Stopped listening for ranked game invitations.\n\n"
                     "Any games already in progress will continue.",
            )
        ]

    async def get_game_state(self, game_id: int) -> List[TextContent]:
        """Get current game state"""
        if game_id not in self.active_games:
            raise ValueError(f"Game {game_id} not found")

        game_state = self.active_games[game_id]
        state_json = json.dumps(game_state.to_dict(), indent=2)

        return [
            TextContent(
                type="text",
                text=f"Game State for {game_id}:\n\n{state_json}",
            )
        ]

    async def get_board_ascii(self, game_id: int) -> List[TextContent]:
        """Get ASCII board representation"""
        if game_id not in self.active_games:
            raise ValueError(f"Game {game_id} not found")

        game_state = self.active_games[game_id]

        # Generate ASCII board
        board_str = str(game_state.board)

        # Add coordinate labels
        lines = board_str.split('\n')
        labeled_lines = []
        for i, line in enumerate(lines):
            rank = 8 - i
            labeled_lines.append(f"{rank} {line}")
        labeled_lines.append("  a b c d e f g h")

        ascii_board = '\n'.join(labeled_lines)

        # Add game info
        game_info = f"\nTurn: {game_state.current_turn}\n"
        game_info += f"Playing as: {'White' if game_state.player_color else 'Black'}\n"
        game_info += f"Opponent: {game_state.opponent_name or 'Unknown'}\n"

        # Add last move/sense info if available
        if game_state.last_move_result:
            game_info += f"\nLast move: {game_state.last_move_result.get('requested', 'N/A')}\n"
            game_info += f"Actual move: {game_state.last_move_result.get('taken', 'N/A')}\n"
            if game_state.last_move_result.get('capture'):
                game_info += f"Captured opponent piece at {game_state.last_move_result.get('capture')}\n"

        if game_state.last_sense_result:
            game_info += f"\nLast sense result:\n"
            for sq, piece in game_state.last_sense_result:
                square_name = chess.square_name(sq) if isinstance(sq, int) else str(sq)
                piece_str = piece.get('type', '?') if isinstance(piece, dict) else (piece.symbol() if piece and hasattr(piece, 'symbol') else ('.' if piece is None else str(piece)))
                game_info += f"  {square_name}: {piece_str}\n"

        return [
            TextContent(
                type="text",
                text=f"{ascii_board}\n{game_info}",
            )
        ]

    async def submit_sense(self, game_id: int, square: str, username: str, password: str) -> List[TextContent]:
        """Submit a sense action and return the sense result"""
        try:
            # Note: We don't strictly enforce turn phase here to allow recovery
            # when MCP state gets out of sync with RBC API state.
            # The API will reject invalid sense actions anyway.

            # Create server connection
            auth = (username, password)
            server = RBCServer(self.server_url, auth, game_id)

            # Parse square
            if square.lower() == "pass":
                parsed_square = None
            else:
                try:
                    parsed_square = chess.parse_square(square)
                except ValueError:
                    raise ValueError(f"Invalid square: {square}")

            # Call server sense method
            try:
                sense_result = server.sense(game_id, parsed_square)
            except ValueError as e:
                error_msg = str(e)
                if "already has a sense action" in error_msg:
                    # Sense was already done - update phase and inform user
                    if game_id in self.active_games:
                        self.active_games[game_id].turn_phase = TurnPhase.NEED_MOVE
                    return [
                        TextContent(
                            type="text",
                            text=f"Sense already submitted for this turn in game {game_id}.\n\n"
                                 f"  The sense action was already performed.\n"
                                 f"  Next step: Use 'submit_move' to make your move.",
                        )
                    ]
                raise

            # Helper function to get piece symbol from API response
            def get_piece_symbol(piece_data):
                if piece_data is None:
                    return None
                if isinstance(piece_data, dict):
                    # API returns {'type': 'p', 'color': True/False} or similar
                    return piece_data.get('type', piece_data.get('symbol', '?'))
                if hasattr(piece_data, 'symbol'):
                    return piece_data.symbol()
                return str(piece_data)

            # Build response message with sense results
            result_msg = f"Sense result for game {game_id} at {square}:\n\n"

            if sense_result:
                # Format the 3x3 grid of sensed squares
                for sq, piece in sense_result:
                    square_name = chess.square_name(sq) if isinstance(sq, int) else str(sq)
                    piece_str = get_piece_symbol(piece) if piece else "."
                    result_msg += f"  {square_name}: {piece_str}\n"
            else:
                result_msg += "  No sensing performed (pass)\n"

            # Update game state turn phase
            if game_id in self.active_games:
                self.active_games[game_id].turn_phase = TurnPhase.NEED_MOVE
                self.active_games[game_id].last_sense_result = sense_result

            result_msg += "\nNow use 'submit_move' to make your move for this turn."

            return [
                TextContent(
                    type="text",
                    text=result_msg,
                )
            ]

        except Exception as e:
            raise ValueError(f"Failed to submit sense: {str(e)}")

    async def submit_move(self, game_id: int, move: str, username: str, password: str) -> List[TextContent]:
        """Submit a move and return the move result"""
        try:
            # Note: We don't strictly enforce turn phase here to allow recovery
            # when MCP state gets out of sync with RBC API state.
            # The API will reject invalid moves anyway.

            # Create server connection
            auth = (username, password)
            server = RBCServer(self.server_url, auth, game_id)

            # Verify it's our turn before attempting to move
            if not server.is_my_turn(game_id):
                logger.warning(f"submit_move called for game {game_id} but it's not our turn")
                raise ValueError(f"Cannot submit move: it is not your turn in game {game_id}")

            # Parse move
            if move.lower() == "pass":
                requested_move = None
            else:
                try:
                    requested_move = chess.Move.from_uci(move)
                except ValueError:
                    raise ValueError(f"Invalid move: {move}")

            # Call server move method
            # Returns: (requested_move, taken_move, capture_square)
            logger.info(f"Submitting move {move} for game {game_id}")
            try:
                move_result = server.move(game_id, requested_move)
            except ValueError as e:
                error_msg = str(e)
                if "already has a move action" in error_msg:
                    # Move was already done - update phase and inform user
                    if game_id in self.active_games:
                        self.active_games[game_id].turn_phase = TurnPhase.WAITING_FOR_TURN
                        self.active_games[game_id].current_turn += 1
                    return [
                        TextContent(
                            type="text",
                            text=f"Move already submitted for this turn in game {game_id}.\n\n"
                                 f"  The move action was already performed.\n"
                                 f"  Next step: Use 'get_game_status' to check if it's your turn again.",
                        )
                    ]
                raise

            # Parse the result - the server returns a tuple/list
            taken_move = move_result[0] if move_result[0] else None
            capture_square = move_result[1] if len(move_result) > 1 else None

            # End the turn after successful move
            #logger.info(f"Move successful, ending turn for game {game_id}")
            #server.end_turn(game_id)

            # Build response message
            result_msg = f"Move result for game {game_id}:\n\n"
            result_msg += f"  Requested move: {move}\n"

            if taken_move:
                taken_move_uci = taken_move.uci() if hasattr(taken_move, 'uci') else str(taken_move)
                result_msg += f"  Taken move: {taken_move_uci}\n"
                if requested_move and taken_move_uci != move:
                    result_msg += f"  Note: Move was modified (possibly blocked by opponent piece)\n"
            else:
                result_msg += f"  Taken move: None (move failed or passed)\n"

            if capture_square:
                capture_name = chess.square_name(capture_square) if isinstance(capture_square, int) else str(capture_square)
                result_msg += f"  Captured opponent piece at: {capture_name}\n"
            else:
                result_msg += f"  No capture\n"

            # Update game state turn phase - turn is complete, waiting for next turn
            if game_id in self.active_games:
                self.active_games[game_id].turn_phase = TurnPhase.WAITING_FOR_TURN
                self.active_games[game_id].current_turn += 1
                self.active_games[game_id].last_move_result = {
                    "requested": move,
                    "taken": str(taken_move) if taken_move else None,
                    "capture": str(capture_square) if capture_square else None,
                }

            result_msg += "\nSend submit_end_turn and then wait for opponent's turn and use 'get_game_status' to check if it's your turn again."

            return [
                TextContent(
                    type="text",
                    text=result_msg,
                )
            ]

        except Exception as e:
            raise ValueError(f"Failed to submit move: {str(e)}")

 
    async def handle_opponent_move_result(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Get the opponent's move result from the server"""
        try:
            # Create server connection
            auth = (username, password)
            server = RBCServer(self.server_url, auth, game_id)

            # First verify it's actually our turn before calling opponent_move_results
            if not server.is_my_turn(game_id):
                return [
                    TextContent(
                        type="text",
                        text=f"Waiting for opponent in game {game_id}:\n\n"
                             f"  It is not your turn yet.\n"
                             f"  Wait and use 'get_game_status' to check when it's your turn.",
                    )
                ]

            # Check if we already called handle_opponent_move_result for this turn
            if game_id in self.active_games:
                game_state = self.active_games[game_id]
                if game_state.turn_phase != TurnPhase.WAITING_FOR_TURN:
                    # Already past this phase - return guidance on what to do next
                    if game_state.turn_phase == TurnPhase.NEED_SENSE:
                        return [
                            TextContent(
                                type="text",
                                text=f"Already retrieved opponent move result for game {game_id}.\n\n"
                                     f"  Current phase: {game_state.turn_phase}\n"
                                     f"  Next step: Use 'submit_sense' to sense a 3x3 region.",
                            )
                        ]
                    elif game_state.turn_phase == TurnPhase.NEED_MOVE:
                        return [
                            TextContent(
                                type="text",
                                text=f"Already retrieved opponent move result and sensed for game {game_id}.\n\n"
                                     f"  Current phase: {game_state.turn_phase}\n"
                                     f"  Next step: Use 'submit_move' to make your move.",
                            )
                        ]

            # Get opponent move result from server
            try:
                capture_square = server.opponent_move_results(game_id)
            except ValueError as e:
                error_msg = str(e)
                if "only call this API endpoint during your own turn" in error_msg:
                    return [
                        TextContent(
                            type="text",
                            text=f"Waiting for opponent in game {game_id}:\n\n"
                                 f"  It is not your turn yet.\n"
                                 f"  Wait and use 'get_game_status' to check when it's your turn.",
                        )
                    ]
                raise

            # Determine if a piece was captured
            captured_my_piece = capture_square is not None

            # Update game state turn phase
            if game_id in self.active_games:
                self.active_games[game_id].turn_phase = TurnPhase.NEED_SENSE

            # Build response message
            result_msg = f"Opponent's move result for game {game_id}:\n\n"
            if captured_my_piece:
                capture_name = chess.square_name(capture_square)
                result_msg += f"  Your piece was captured at: {capture_name}\n"
            else:
                result_msg += f"  No piece was captured\n"

            result_msg += "\nNow use 'submit_sense' to sense a 3x3 region of the board."

            return [
                TextContent(
                    type="text",
                    text=result_msg,
                )
            ]

        except Exception as e:
            raise ValueError(f"Failed to get opponent move result: {str(e)}")

    async def get_game_status_tool(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Get the current status of a game from the server"""
        try:
            # Create server connection
            auth = (username, password)
            server = RBCServer(self.server_url, auth, game_id)

            # Get game status from server
            status = server.get_game_status(game_id)

            # Build response message
            result_msg = f"Game Status for game {game_id}:\n"
            result_msg += f"  Is my turn: {status['is_my_turn']}\n"
            result_msg += f"  Is game over: {status['is_over']}\n"
            if status['is_over']:
                result_msg += f"  The game is over. The winner is {status['winner_color']} and the reason is {status['win_reason']}.\n"
            elif not status['is_over'] and status['is_my_turn']:
                result_msg += f"It is now your turn to play.\n"
            else:
                result_msg += f"It is not your turn. Wait 1 second and use 'get_game_status' again to check if it is your turn.\n"

            return [
                TextContent(
                    type="text",
                    text=result_msg,
                )
            ]

        except Exception as e:
            raise ValueError(f"Failed to get game status: {str(e)}")

    async def get_sense_actions(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Get the list of valid sense actions for the current turn"""
        try:
            # Create server connection
            auth = (username, password)
            server = RBCServer(self.server_url, auth, game_id)

            # Get sense actions from server
            sense_actions = server.sense_actions(game_id)

            # Convert square indices to algebraic notation
            sense_squares = [chess.square_name(sq) for sq in sense_actions]

            # Build response message
            result_msg = f"Valid sense actions for game {game_id}:\n"
            result_msg += f"  Total: {len(sense_squares)} squares\n"
            result_msg += f"  Squares: {', '.join(sense_squares)}\n\n"
            result_msg += "Note: Each sense action reveals a 3x3 region centered on the chosen square.\n"
            result_msg += "Tip: Avoid sensing edge squares (a-file, h-file, rank 1, rank 8) as they reveal fewer squares."

            return [
                TextContent(
                    type="text",
                    text=result_msg,
                )
            ]

        except Exception as e:
            raise ValueError(f"Failed to get sense actions: {str(e)}")

    async def get_move_actions(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Get the list of valid move actions for the current turn"""
        try:
            # Create server connection
            auth = (username, password)
            server = RBCServer(self.server_url, auth, game_id)

            # Get move actions from server
            move_actions = server.move_actions(game_id)

            # Convert moves to UCI notation
            # API returns moves as dicts like {'type': 'Move', 'value': 'e2e4'}
            move_strings = [move['value'] if isinstance(move, dict) else move.uci() for move in move_actions]

            # Build response message
            result_msg = f"Valid move actions for game {game_id}:\n"
            result_msg += f"  Total: {len(move_strings)} moves\n"
            result_msg += f"  Moves: {', '.join(move_strings)}\n\n"
            result_msg += "Note: Moves are in UCI format (e.g., 'e2e4', 'e7e8q' for promotion).\n"
            result_msg += "You can also pass your turn by submitting 'pass' as your move."

            return [
                TextContent(
                    type="text",
                    text=result_msg,
                )
            ]

        except Exception as e:
            raise ValueError(f"Failed to get move actions: {str(e)}")

    async def is_game_over(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Check if a game is over and return the result"""
        try:
            # Create server connection
            auth = (username, password)
            server = RBCServer(self.server_url, auth, game_id)

            # Check if game is over
            game_over = server.is_over(game_id)

            # Build response message
            result_msg = f"Game over status for game {game_id}:\n\n"
            result_msg += f"  Is game over: {game_over}\n"

            if game_over:
                # Get winner and win reason
                winner_color = server.get_winner_color(game_id)
                win_reason = server.get_win_reason(game_id)

                if winner_color is not None:
                    winner_str = "White" if winner_color == chess.WHITE else "Black"
                    result_msg += f"  Winner: {winner_str}\n"
                else:
                    result_msg += f"  Winner: Draw/None\n"

                if win_reason is not None:
                    result_msg += f"  Win reason: {win_reason}\n"
                else:
                    result_msg += f"  Win reason: Unknown\n"
            else:
                result_msg += "\nGame is still in progress. Use 'get_game_status' to check whose turn it is."

            return [
                TextContent(
                    type="text",
                    text=result_msg,
                )
            ]

        except Exception as e:
            raise ValueError(f"Failed to check if game is over: {str(e)}")

    async def get_bot_version(self, username: str, password: str) -> List[TextContent]:
        """Get the current bot version number"""
        try:
            # Create server connection
            auth = (username, password)
            server = RBCServer(self.server_url, auth)

            # Get bot version
            version = server.get_bot_version()

            # Build response message
            result_msg = f"Bot version for {username}:\n\n"
            result_msg += f"  Current version: {version}\n\n"
            result_msg += "Use 'increment_bot_version' if you want to increment the version number."

            return [
                TextContent(
                    type="text",
                    text=result_msg,
                )
            ]

        except Exception as e:
            raise ValueError(f"Failed to get bot version: {str(e)}")

    async def increment_bot_version(self, username: str, password: str) -> List[TextContent]:
        """Increment the bot version number"""
        try:
            # Create server connection
            auth = (username, password)
            server = RBCServer(self.server_url, auth)

            # Get current version first
            old_version = server.get_bot_version()

            # Increment version
            server.increment_version()

            # Get new version to confirm
            new_version = server.get_bot_version()

            # Build response message
            result_msg = f"Bot version incremented for {username}:\n\n"
            result_msg += f"  Previous version: {old_version}\n"
            result_msg += f"  New version: {new_version}\n"

            return [
                TextContent(
                    type="text",
                    text=result_msg,
                )
            ]

        except Exception as e:
            raise ValueError(f"Failed to increment bot version: {str(e)}")

    async def get_winner_color(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Get the winner color of a finished game"""
        try:
            # Create server connection
            auth = (username, password)
            server = RBCServer(self.server_url, auth)

            # Get winner color
            winner_color = server.get_winner_color(game_id)

            # Build response message
            result_msg = f"Winner color for game {game_id}:\n\n"

            if winner_color is not None:
                winner_str = "White" if winner_color == chess.WHITE else "Black"
                result_msg += f"  Winner: {winner_str}\n"
            else:
                result_msg += f"  Winner: None (draw or game not finished)\n"

            return [
                TextContent(
                    type="text",
                    text=result_msg,
                )
            ]

        except Exception as e:
            raise ValueError(f"Failed to get winner color: {str(e)}")

    async def get_win_reason(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Get the win reason of a finished game"""
        try:
            # Create server connection
            auth = (username, password)
            server = RBCServer(self.server_url, auth)

            # Get win reason
            win_reason = server.get_win_reason(game_id)

            # Build response message
            result_msg = f"Win reason for game {game_id}:\n\n"

            if win_reason is not None:
                result_msg += f"  Win reason: {win_reason}\n"
            else:
                result_msg += f"  Win reason: None (game not finished or unknown)\n"

            return [
                TextContent(
                    type="text",
                    text=result_msg,
                )
            ]

        except Exception as e:
            raise ValueError(f"Failed to get win reason: {str(e)}")

    async def list_active_games(self) -> List[TextContent]:
        """List all active games"""
        if not self.active_games:
            return [
                TextContent(
                    type="text",
                    text="No active games",
                )
            ]

        games_list = []
        for game_id, game_state in self.active_games.items():
            game_type = "Ranked" if game_state.is_ranked else "Unranked"
            color_str = "White" if game_state.player_color else "Black"

            games_list.append(
                f"- {game_id}\n"
                f"  Type: {game_type}\n"
                f"  Playing as: {color_str}\n"
                f"  Opponent: {game_state.opponent_name or 'Unknown'}\n"
                f"  Turn: {game_state.current_turn}\n"
                f"  Status: Active\n"
            )

        return [
            TextContent(
                type="text",
                text=f"Active Games:\n\n" + "\n".join(games_list),
            )
        ]

    # =========================================================================
    # Additional API Tool Implementations
    # =========================================================================

    async def get_active_users_tool(self, username: str, password: str) -> List[TextContent]:
        """Get a list of all active usernames on the RBC server"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth)
            users = server.get_active_users()

            result_msg = f"Active users on RBC server:\n\n"
            result_msg += f"  Total: {len(users)} users\n"
            result_msg += f"  Users: {', '.join(users)}\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to get active users: {str(e)}")

    async def set_max_games_tool(self, max_games: int, username: str, password: str) -> List[TextContent]:
        """Set the maximum number of concurrent games"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth)
            server.set_max_games(max_games)

            result_msg = f"Max games setting updated:\n\n"
            result_msg += f"  Max concurrent games: {max_games}\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to set max games: {str(e)}")

    async def set_ranked_tool(self, ranked: bool, username: str, password: str) -> List[TextContent]:
        """Set ranked preference status"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth)
            server.set_ranked(ranked)

            status = "enabled" if ranked else "disabled"
            result_msg = f"Ranked preference updated:\n\n"
            result_msg += f"  Ranked games: {status}\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to set ranked preference: {str(e)}")

    async def get_invitations_tool(self, username: str, password: str) -> List[TextContent]:
        """Get a list of pending game invitations"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth)
            invitations = server.get_invitations()

            result_msg = f"Pending invitations:\n\n"
            if invitations:
                result_msg += f"  Total: {len(invitations)} invitations\n"
                result_msg += f"  Invitation IDs: {', '.join(str(i) for i in invitations)}\n"
            else:
                result_msg += "  No pending invitations\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to get invitations: {str(e)}")

    async def get_player_color_tool(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Get the color you are playing as in a game"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth)
            color = server.get_player_color(game_id)

            color_str = "White" if color else "Black"
            result_msg = f"Player color for game {game_id}:\n\n"
            result_msg += f"  You are playing as: {color_str}\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to get player color: {str(e)}")

    async def get_starting_board_tool(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Get the starting board position for a game"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth)
            board_fen = server.get_starting_board(game_id)

            result_msg = f"Starting board for game {game_id}:\n\n"
            result_msg += f"  FEN: {board_fen}\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to get starting board: {str(e)}")

    async def get_opponent_name_tool(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Get the opponent's username for a game"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth)
            opponent_name = server.get_opponent_name(game_id)

            result_msg = f"Opponent for game {game_id}:\n\n"
            result_msg += f"  Opponent: {opponent_name}\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to get opponent name: {str(e)}")

    async def start_game_tool(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Mark yourself as ready to start a game"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth)
            server.start(game_id)

            result_msg = f"Game {game_id} started:\n\n"
            result_msg += f"  You are now marked as ready.\n"
            result_msg += f"  Use 'get_game_status' to check when it's your turn.\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to start game: {str(e)}")

    async def get_seconds_left_tool(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Get the remaining time in seconds"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth)
            seconds_left = server.get_seconds_left(game_id)

            minutes = int(seconds_left // 60)
            seconds = seconds_left % 60
            result_msg = f"Time remaining for game {game_id}:\n\n"
            result_msg += f"  Seconds left: {seconds_left:.1f}\n"
            result_msg += f"  ({minutes}m {seconds:.1f}s)\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to get seconds left: {str(e)}")

    async def end_turn_tool(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """End the current turn"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth, game_id)
            server.end_turn(game_id)

            result_msg = f"Turn ended for game {game_id}:\n\n"
            result_msg += f"  Your turn has been completed.\n"
            result_msg += f"  Wait for opponent's move, then use 'get_game_status' to check your turn.\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to end turn: {str(e)}")

    async def resign_tool(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Resign from a game"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth)
            server.resign(game_id)

            result_msg = f"Resigned from game {game_id}:\n\n"
            result_msg += f"  You have resigned from the game.\n"
            result_msg += f"  Your opponent wins.\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to resign: {str(e)}")

    async def error_resign_tool(self, game_id: int, username: str, password: str) -> List[TextContent]:
        """Report a bot error and resign"""
        try:
            auth = (username, password)
            server = RBCServer(self.server_url, auth)
            server.error_resign(game_id)

            result_msg = f"Error resign for game {game_id}:\n\n"
            result_msg += f"  Bot error reported.\n"
            result_msg += f"  Your remaining time has been zeroed.\n"

            return [TextContent(type="text", text=result_msg)]

        except Exception as e:
            raise ValueError(f"Failed to error resign: {str(e)}")

    async def run(self):
        """Run the MCP server"""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


async def main():
    """Main entry point"""
    server = RBCMCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
