# Example MCP Tool Usage

This document shows example MCP tool calls and their responses.

## Creating a Local Game

**Tool Call**:
```json
{
  "name": "create_local_game",
  "arguments": {
    "bot_type": "trout",
    "color": "white"
  }
}
```

**Response**:
```json
{
  "success": true,
  "game_id": 1,
  "bot_type": "trout",
  "your_color": "white",
  "opponent": "trout_bot",
  "message": "Created game 1. Playing as white against trout bot."
}
```

## Turn 1: Check Status

**Tool Call**:
```json
{
  "name": "get_game_status",
  "arguments": {
    "game_id": 1
  }
}
```

**Response**:
```json
{
  "game_id": 1,
  "your_color": "white",
  "opponent": "trout_bot",
  "turn": 0,
  "game_started": true,
  "game_over": false,
  "waiting_for_sense": true,
  "waiting_for_move": false
}
```

The game is waiting for you to sense!

## Turn 1: Sense

**Tool Call**:
```json
{
  "name": "choose_sense",
  "arguments": {
    "game_id": 1,
    "square": "e7"
  }
}
```

**Response**:
```json
{
  "success": true,
  "sense_square": "e7",
  "message": "Sense choice set to e7"
}
```

**Get Sense Result**:
```json
{
  "name": "get_sense_result",
  "arguments": {
    "game_id": 1
  }
}
```

**Response**:
```json
{
  "sense_result": [
    {"square": "d8", "piece": "q", "color": "black"},
    {"square": "e8", "piece": "k", "color": "black"},
    {"square": "f8", "piece": "b", "color": "black"},
    {"square": "d7", "piece": "p", "color": "black"},
    {"square": "e7", "piece": "p", "color": "black"},
    {"square": "f7", "piece": "p", "color": "black"},
    {"square": "d6", "piece": null, "color": null},
    {"square": "e6", "piece": null, "color": null},
    {"square": "f6", "piece": null, "color": null}
  ]
}
```

Found the black king at e8!

## Turn 1: Check Board State

**Tool Call**:
```json
{
  "name": "get_board_state",
  "arguments": {
    "game_id": 1
  }
}
```

**Response**:
```json
{
  "board_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "board_unicode": "r n b q k b n r\np p p p p p p p\n. . . . . . . .\n. . . . . . . .\n. . . . . . . .\n. . . . . . . .\nP P P P P P P P\nR N B Q K B N R",
  "your_color": "white"
}
```

## Turn 1: Move

**Tool Call**:
```json
{
  "name": "choose_move",
  "arguments": {
    "game_id": 1,
    "move": "e2e4"
  }
}
```

**Response**:
```json
{
  "success": true,
  "move": "e2e4",
  "message": "Move choice set to e2e4"
}
```

**Get Move Result**:
```json
{
  "name": "get_move_result",
  "arguments": {
    "game_id": 1
  }
}
```

**Response**:
```json
{
  "move_result": {
    "requested_move": "e2e4",
    "taken_move": "e2e4",
    "captured_opponent_piece": false,
    "capture_square": null
  }
}
```

## Turn 2: Check Opponent Move

**Tool Call**:
```json
{
  "name": "get_opponent_move_info",
  "arguments": {
    "game_id": 1
  }
}
```

**Response**:
```json
{
  "opponent_move_info": {
    "captured_my_piece": false,
    "capture_square": null
  }
}
```

Opponent didn't capture anything. Now repeat the sense/move cycle!

## Creating a Remote Game

**Tool Call**:
```json
{
  "name": "create_remote_game",
  "arguments": {
    "server_url": "https://rbc.jhuapl.edu",
    "auth_token": "bWNwX3JiYzpCZWF6ZXJCMzNz",
    "remote_game_id": "abc123"
  }
}
```

**Response**:
```json
{
  "success": true,
  "game_id": 1,
  "server_url": "https://rbc.jhuapl.edu",
  "remote_game_id": "abc123",
  "message": "Created remote game 1"
}
```

Remote games use the same sense/move tools as local games!

## Listing Games

**Tool Call**:
```json
{
  "name": "list_local_games",
  "arguments": {}
}
```

**Response**:
```json
{
  "local_games": [1, 2, 3]
}
```

## End Game Status

When the game ends, `get_game_status` will show:

```json
{
  "game_id": 1,
  "your_color": "white",
  "opponent": "trout_bot",
  "turn": 15,
  "game_started": true,
  "game_over": true,
  "waiting_for_sense": false,
  "waiting_for_move": false,
  "winner": "white",
  "win_reason": "WinReason.KING_CAPTURE"
}
```

## Complete Game Flow

```
1. create_local_game()          → game_id: 1
2. Loop until game_over:
   a. get_game_status()         → waiting_for_sense: true
   b. choose_sense()            → square: "e4"
   c. get_sense_result()        → see 3x3 area
   d. get_game_status()         → waiting_for_move: true
   e. choose_move()             → move: "e2e4"
   f. get_move_result()         → move result
   g. get_opponent_move_info()  → opponent capture info
3. get_game_status()            → game_over: true, winner: "white"
```

## Error Handling

**Invalid Move**:
```json
{
  "name": "choose_move",
  "arguments": {
    "game_id": 1,
    "move": "invalid"
  }
}
```

**Response**:
```json
{
  "error": "Invalid move: invalid"
}
```

**Game Not Found**:
```json
{
  "name": "get_game_status",
  "arguments": {
    "game_id": 999
  }
}
```

**Response**:
```json
{
  "error": "Game 999 not found"
}
```

**Not Waiting for Input**:
```json
{
  "name": "choose_sense",
  "arguments": {
    "game_id": 1,
    "square": "e4"
  }
}
```

**Response**:
```json
{
  "error": "Not waiting for sense choice"
}
```

Always check `waiting_for_sense` and `waiting_for_move` before calling those tools!
