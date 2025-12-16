# Claude Agent Workflow: Reconnaissance Blind Chess

This document provides a comprehensive guide for Claude to play strong Reconnaissance Blind Chess (RBC) games using the MCP server tools.

## Game Overview

Reconnaissance Blind Chess is a chess variant where:

- **You cannot see opponent pieces** - The opponent's pieces are hidden from view
- **Sensing phase** - Before each move, you choose a 3x3 region to "sense" and see what pieces occupy those 9 squares
- **Move phase** - After sensing, you make your move
- **Win condition** - Capture the opponent's king (not checkmate)
- **No check rules** - Check does not exist; you can castle through check, move into check, etc.
- **Time limit** - 15 minutes per player with 5-second increment per turn

### Key Rule Differences from Standard Chess

1. **Sliding piece captures**: If you try to move a sliding piece (bishop, rook, queen) through an opponent's piece, your piece stops at that square and captures it
2. **Illegal moves**: If you attempt an illegal move (e.g., pawn diagonal to empty square), you forfeit your move and are notified
3. **Pass option**: You may pass your turn without moving
4. **Capture notifications**: When capturing or being captured, you learn the square but not the piece type
5. **50-move rule**: Games draw after 50 turns without pawn moves or captures

## Game Workflow When Playing Unranked or Ranked Game of Reconnaissance using MCP:

1. **Ask the user's RBC username and password**
2. **Start a new game**: Use the MCP tool: start_unranked_game or start_ranked_game
3. **Play all turns until the game is over**: Repeat steps 4 through 12 until the game is over
4. **Check if the game is over once per second**: Use the MCP tool is_game_over
5. **Wait for is_my-turn=true**: Use the MCP tool: get_game_status
6. **If is_my_turn=true, then process the Opponent player's move. Otherwise,continue to wait for your turn**: Use the MCP tool handle_opponent_move_result
7. **Find the valid squares to sense**: Use the MCP tool get_sense_actions
8. **Anticipate the square where the opponent have moved to and submit sense on that square**: Use the MCP tool submit_sense
9. **Review the current Board positions**: Use the MCP tool: get_board_ascii
10. **Find the valid moves**: Use the MCP tool get_move_actions
11. **Determine the best and valid chess move to capture the enemy king and submit the move**: Use the MCP tool submit_move
12. **End your turn**: Use the MCP tool submit_end_turn
13. **Repeat this Game Workflow from step number 4 until the game is over**
14. **Report the winner and the win_reason**: Use the MCP tools get_winner_color and get_win_reason
15. **If an expected API error occurs during the game, stop the game**: Use the MCP tool error_resign


## Strategic Framework

### Phase 1: Opening (Turns 1-10)

**Primary Goals:**
- Develop pieces toward the center
- Establish control over key squares (e4, d4, e5, d5)
- Castle early to protect your king
- Keep track of opponent's likely development patterns

**Sensing Strategy (Opening):**
- Sense central squares (d4, d5, e4, e5) to understand opponent's center control
- Track where opponent pieces are developing
- On the first few turns, sense to verify standard opening moves

**Recommended Opening Moves:**
- As White: 1. e4 or 1. d4 (control center immediately)
- As Black: 1...e5, 1...d5, or 1...c5 (contest the center)
- Develop knights before bishops (Nc3, Nf3, Nc6, Nf6)
- Castle kingside when safe (or queenside if opponent's pieces suggest kingside threats)

### Phase 2: Middle Game (Turns 10-35)

**Primary Goals:**
- Locate the opponent's king
- Create attacking opportunities
- Defend your own king from capture
- Reduce uncertainty about opponent piece positions

**Sensing Strategy (Middle Game):**
- **King hunting**: Once you have attacking pieces developed, start sensing around the opponent's likely king positions (g8/g1 after castling, or e8/e1 if not castled)
- **Threat assessment**: Before moving, sense squares where opponent pieces could threaten your king
- **Attack validation**: Sense where you plan to move to verify the position is safe or confirm a capture opportunity
- **Never sense edge squares**: Sensing at the board edge wastes information (you only see 6 squares instead of 9)

**Move Selection (Middle Game):**
- Prioritize moves that could capture the king if the opponent hasn't castled or moved their king
- Use sliding pieces to probe: A rook move down an open file might unexpectedly capture
- Keep your king protected - assume the opponent is looking for it
- Make "safe" moves that work regardless of opponent piece positions

### Phase 3: Endgame (Turn 35+)

**Primary Goals:**
- Locate and capture the opponent's king
- Advance pawns for promotion
- Simplify the position by trading pieces

**Sensing Strategy (Endgame):**
- Focus sensing almost entirely on finding the king
- Sense systematically across the board if king location is unknown
- Once king is located, sense around it each turn to track movement

**Move Selection (Endgame):**
- Coordinate multiple pieces to attack the king's likely squares
- Use rooks and queens to control files and ranks the king might flee along
- Promote pawns when safe to gain attacking material

## Information State Management

### Tracking What You Know

Maintain mental model of:

1. **Confirmed pieces**: Squares you've sensed and know the contents of
2. **Inferred pieces**: Likely piece positions based on:
   - Capture notifications
   - Opponent's original piece placement
   - Legal move constraints
3. **Unknown regions**: Areas you haven't sensed recently

### Handling Uncertainty

**High Certainty Moves:**
- Moves to squares you've just sensed
- Pawn advances (pawns can only move forward)
- Captures on squares where you know an opponent piece exists

**Medium Certainty Moves:**
- Development moves to likely-empty squares
- Castling (verify no pieces block the path)

**Low Certainty Moves:**
- Long sliding piece moves through unsensed areas
- Attacks on inferred king positions

### Opponent Modeling

Consider what the opponent knows:
- They've seen your pieces where they've sensed
- They know capture locations (but not piece types)
- They're likely tracking your king position

Defensive implications:
- Move your king occasionally to avoid predictability
- Don't leave your king on sensed squares
- Protect your king with pawns and pieces

## Turn-by-Turn Workflow

### Each Turn Sequence

```
1. Check game status (get_game_status)
2. Handle opponent move result (handle_opponent_move_result)
   - Note if piece was captured and where
3. View current board state (get_board_ascii)
4. Decide where to sense based on strategy
5. Submit sense action (submit_sense)
6. Analyze sense results
7. Update mental model of opponent positions
8. Select move based on updated information
9. Submit move (submit_move)
10. Repeat until game ends
```

### Sensing Decision Algorithm

```
Priority order for sensing:
1. If opponent might capture your king next turn -> sense around your king
2. If you have a potential king capture -> sense target area to confirm
3. If opponent king location is uncertain -> sense likely king regions
4. If building an attack -> sense the attack target area
5. Default: sense central or strategically important squares
```

### Move Decision Algorithm

```
Priority order for moves:
1. Capture opponent king if possible (instant win)
2. Escape if your king is under immediate threat
3. Make a move that's safe across all possible board states
4. Develop pieces toward attacking the king
5. Improve position while maintaining king safety
```

## Specific Tactics

### King Hunting

The goal is to capture the king, so develop "king hunting" skills:

1. **Track castling**: If opponent castled kingside, king is likely on g8 or nearby
2. **Systematic search**: If unsure, sense methodically: g1-g8 corridor, then f1-f8, etc.
3. **Convergent attack**: Once king is found, bring multiple pieces to attack simultaneously
4. **Cut off escape**: Use rooks to control files/ranks the king might escape along

### Defensive Principles

1. **King mobility**: Keep escape squares open for your king
2. **Piece coordination**: Keep pieces defending each other
3. **Avoid patterns**: Don't leave king in predictable locations
4. **Castle early**: But consider that opponent expects this

### Sliding Piece Probes

Use sliding pieces to gather information through movement:

1. **Rook probe**: Move a rook down an open file - if it stops unexpectedly, you found an opponent piece
2. **Bishop probe**: Similar with diagonal moves
3. **Queen probe**: Maximum coverage but risks losing your queen

The move result tells you:
- Requested move vs. taken move (different if blocked)
- Whether you captured
- Capture square location

### Pawn Advances

Pawns are reliable information sources:

1. Forward pawn moves succeed unless square is occupied
2. Diagonal captures only work if opponent piece present
3. Use pawns to probe for hidden pieces

## Common Mistakes to Avoid

1. **Sensing edges/corners**: You lose sensing coverage; always sense inner squares (b2-g7)
2. **Ignoring king safety**: You can lose instantly if your king is captured
3. **Overconfidence**: Don't assume opponent pieces are where you expect
4. **Forgetting captures**: Your sliding pieces can capture unexpectedly - pay attention to move results
5. **Predictable play**: Vary your approach; skilled opponents will exploit patterns
6. **Time pressure**: Don't spend too long on decisions; the 15-minute clock is real

## MCP Tool Usage

### Starting a Game

```
start_unranked_game(
  opponent_bot: "trout" | "random" | "attacker" | "oracle" | "strangefish2",
  color: "white" | "black" | "random",
  username: "your_username",
  password: "your_password"
)
```

Bot difficulty (approximate):
- `random`: Random moves (easiest)
- `attacker`: Aggressive but simple
- `trout`: Uses Stockfish evaluation
- `oracle`: Strong baseline
- `strangefish2`: Tournament winner (hardest)

### Game Loop Tools

```
is_game_over(game_id, username, password)
  -> Check if the game has ended
  -> Returns game over status, winner, and win reason

get_game_status(game_id, username, password)
  -> Check if it's your turn (is_my_turn) or game is over (is_over)
  -> Wait for is_my_turn=true before playing your turn

handle_opponent_move_result(game_id, username, password)
  -> Get opponent's move result from the server
  -> Returns whether your piece was captured and on which square

get_sense_actions(game_id, username, password)
  -> Get list of valid squares to sense
  -> Returns all possible sense square centers

submit_sense(game_id, square, username, password)
  -> Choose 3x3 region center (e.g., "d5") or "pass" to skip
  -> Returns what pieces are in that region

get_board_ascii(game_id)
  -> View current known board state
  -> Shows your pieces and any sensed opponent pieces

get_move_actions(game_id, username, password)
  -> Get list of valid moves for the current turn
  -> Returns all legal moves in UCI format

submit_move(game_id, move, username, password)
  -> Make a move in UCI format (e.g., "e2e4") or "pass" to skip
  -> Returns requested move, actual move taken, and capture info

get_winner_color(game_id, username, password)
  -> Get the winner color of a finished game
  -> Returns "White", "Black", or "None" for draw

get_win_reason(game_id, username, password)
  -> Get the reason the game ended
  -> Returns "KING_CAPTURE", "TIMEOUT", "RESIGN", etc.
```

### Example Game Flow

```
# 1. Start game
start_unranked_game("trout", "white", "user", "pass")

# 2. Check status until your turn
get_game_status(game_id, "user", "pass")

# 3. On your turn (as white, first move):
handle_opponent_move_result(game_id, false, null)  # No capture on turn 1
get_board_ascii(game_id)                            # See your pieces
submit_sense(game_id, "e5")                         # Sense center
submit_move(game_id, "e2e4")                        # King's pawn opening

# 4. Wait for opponent, then repeat from step 2
```

## Advanced Strategies

### Board State Estimation

Like the tournament-winning StrangeFish bot, track possible board states:

1. Start with known opening position for opponent
2. After each turn, expand possibilities by all legal opponent moves
3. After sensing, eliminate impossible states
4. After move results, eliminate more impossible states

### Expected Value Move Selection

When uncertain, evaluate moves across possible board states:

1. For each candidate move, calculate outcome in each possible state
2. Weight by probability of each state
3. Consider both mean outcome and worst-case outcome
4. Select move with best weighted score

### Sensing for Move Optimization

StrangeFish's key insight: sense where it most affects your next move decision:

1. Calculate your best move for current information
2. For each potential sense square, calculate best move given that info
3. Choose sense that most improves your move decision
4. This couples sensing directly to tactical benefit

## References

- [RBC Official Rules](https://rbc.jhuapl.edu/gameRules)
- [StrangeFish Bot (NeurIPS 2019 Winner)](https://github.com/ginop/reconchess-strangefish)
- [On the Complexity of RBC](https://arxiv.org/abs/1811.03119)
- [First International RBC Competition](https://proceedings.mlr.press/v123/gardner20a.html)
- [Newman 2016: RBC Platform Paper](https://rbc.jhuapl.edu/newman_2016)
