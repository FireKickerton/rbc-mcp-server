# Reconnaissance Blind Chess MCP Server

A Model Context Protocol (MCP) server that enables humans and LLMs to play Reconnaissance Blind Chess (RBC) both locally against AI bots and remotely on the official RBC server at rbc.jhuapl.edu.

## What is Reconnaissance Blind Chess?

Reconnaissance Blind Chess is a variant of chess where you can only see your own pieces. Key rules:

- **Limited Vision**: You only see your own pieces, not your opponent's
- **Sensing Phase**: Each turn, you can sense a 3x3 area to discover opponent pieces
- **Move Phase**: Make a move based on your incomplete knowledge
- **Capture to Win**: The goal is to capture the opponent's king (not checkmate)
- **Check Rules Removed**: You can move into check, castle through check, etc.

For complete rules, see: https://reconchess.readthedocs.io/en/latest/rules.html

## Features

- Play local games against three different AI bots:
  - **RandomBot**: Plays random legal moves
  - **AttackerBot**: Prefers capturing moves and senses in opponent territory
  - **TroutBot**: Actively seeks and tracks the opponent's king
- Connect to remote games on rbc.jhuapl.edu
- Full MCP tool integration for Claude and other LLM clients
- Game state tracking with turn-by-turn information
- Asynchronous game execution in background threads

## Installation

### Prerequisites

- Python 3.9 or higher
- pip or pip3

### Setup

1. Clone or download this repository

2. Create a virtual environment and install dependencies:

```bash
cd rbc_mcp_server
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Verify installation:

```bash
python3 rbc_mcp_server.py --version
```

## Usage

### Running the MCP Server

The MCP server communicates via stdio and is designed to be used with MCP clients like Claude Desktop.

To run standalone (for testing):

```bash
source venv/bin/activate
python3 rbc_mcp_server.py
```

### Configuring with Claude Desktop

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "rbc": {
      "command": "/Users/YOUR_USERNAME/projects/rbc_mcp_server/venv/bin/python3",
      "args": ["/Users/YOUR_USERNAME/projects/rbc_mcp_server/rbc_mcp_server.py"]
    }
  }
}
```

Replace `/Users/YOUR_USERNAME/projects/rbc_mcp_server` with your actual path.

## MCP Tools

### Local Game Tools

#### `create_local_game`
Create and start a new local game against a bot.

Parameters:
- `bot_type` (optional): "random", "attacker", or "trout" (default: "random")
- `color` (optional): "white", "black", or "random" (default: "random")

Returns: Game ID and initial game information

#### `get_game_status`
Get the current status of a game.

Parameters:
- `game_id`: The game ID

Returns: Game status including whether it's waiting for your input

#### `get_board_state`
Get your current view of the board (only pieces you can see).

Parameters:
- `game_id`: The game ID

Returns: Board FEN and unicode representation

#### `choose_sense`
Choose a square to sense (reveals 3x3 area).

Parameters:
- `game_id`: The game ID
- `square`: Square name (e.g., "e4", "d5") or "pass"

#### `choose_move`
Choose a move to make.

Parameters:
- `game_id`: The game ID
- `move`: Move in UCI format (e.g., "e2e4") or "pass"

#### `get_sense_result`
Get the result of your last sense action.

#### `get_move_result`
Get the result of your last move.

#### `get_opponent_move_info`
Get information about opponent's last move.

#### `list_local_games`
List all active local game IDs.

#### `delete_local_game`
Delete a game and free its resources.

### Remote Game Tools

#### `create_remote_game`
Connect to a game on rbc.jhuapl.edu.

Parameters:
- `server_url` (optional): Server URL (default: "https://rbc.jhuapl.edu")
- `auth_token`: Base64 encoded authentication token
- `remote_game_id`: Game ID on the remote server

#### `get_remote_game_status`
Get the status of a remote game.

#### `list_remote_games`
List all active remote game sessions.

#### `delete_remote_game`
Delete a remote game session.

## Example Game Flow

Here's how a typical game works:

1. **Create a game**:
```
create_local_game(bot_type="trout", color="white")
→ Returns game_id: 1
```

2. **Check status** (repeat until waiting_for_sense is true):
```
get_game_status(game_id=1)
→ waiting_for_sense: true
```

3. **Sense the board**:
```
choose_sense(game_id=1, square="e4")
get_sense_result(game_id=1)
→ Shows 3x3 area around e4
```

4. **Check status** (repeat until waiting_for_move is true):
```
get_game_status(game_id=1)
→ waiting_for_move: true
```

5. **Make a move**:
```
choose_move(game_id=1, move="e2e4")
get_move_result(game_id=1)
→ Shows if move succeeded and if you captured anything
```

6. **Repeat steps 2-5** until game is over

## Playing on Remote Server

To play on the official RBC server at rbc.jhuapl.edu:

1. **Authentication**: Use the provided token: `bWNwX3JiYzpCZWF6ZXJCMzNz`

2. **Get a game ID**: You'll need to create or join a game on the RBC server (outside of this MCP)

3. **Connect**:
```
create_remote_game(
  auth_token="bWNwX3JiYzpCZWF6ZXJCMzNz",
  remote_game_id="YOUR_GAME_ID"
)
```

4. **Play**: Use the same sense/move flow as local games

## Architecture

The server is structured as follows:

- **Bot Players**: Three AI opponents implementing the reconchess Player interface
- **Human Player**: Interactive player that waits for MCP tool calls
- **Game Manager**: Manages multiple concurrent games (local and remote)
- **Background Threads**: Games run asynchronously to avoid blocking the MCP server
- **MCP Server**: Provides tools for game interaction

## Dependencies

- `reconchess>=1.0.0` - Official Reconnaissance Blind Chess library
- `python-chess>=1.0.0` - Chess logic and board representation
- `mcp>=0.1.0` - Model Context Protocol SDK
- `httpx>=0.24.0` - HTTP client for remote games

## Game Rules Reference

From the official documentation:

### Turn Structure
Each turn has three phases:
1. **Opponent Move Notification**: Learn if opponent captured your piece
2. **Sense Phase**: Choose a square to sense (3x3 area)
3. **Move Phase**: Make your move

### Move Execution
- Moves must be legal on the true board
- Sliding pieces (Q, R, B) capture if blocked by opponent
- Pawns moving 2 squares move 1 if blocked
- Illegal moves result in passing

### Winning
- Capture the opponent's king to win
- No checkmate rules
- Games can end by timeout or other conditions

## Troubleshooting

### "reconchess could not be resolved"
Make sure you've activated the virtual environment:
```bash
source venv/bin/activate
```

### Game not responding
Check the game status to see if it's waiting for your input:
```
get_game_status(game_id=1)
```

### Remote game connection issues
Verify:
1. You have the correct authentication token
2. The game ID exists on the server
3. The game hasn't already started or finished

## License

This project uses the reconchess library and follows its licensing terms.

## References

- [Reconchess Documentation](https://reconchess.readthedocs.io/)
- [Reconchess Rules](https://reconchess.readthedocs.io/en/latest/rules.html)
- [RBC Server](https://rbc.jhuapl.edu)
- [Model Context Protocol](https://modelcontextprotocol.io/)
