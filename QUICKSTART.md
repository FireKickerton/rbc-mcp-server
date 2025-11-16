# Quick Start Guide

## Installation (5 minutes)

1. **Install dependencies**:
```bash
cd rbc_mcp_server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **Verify installation**:
```bash
python3 test_bots.py
python3 test_integration.py
```

Both tests should pass with ✓ marks.

## Configure Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or equivalent on your system:

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

**Important**: Replace `/Users/YOUR_USERNAME/projects/rbc_mcp_server` with your actual path!

## Playing Your First Game

Restart Claude Desktop, then ask:

```
"I want to play Reconnaissance Blind Chess against the random bot.
Create a game where I play as white."
```

Claude will:
1. Create a local game
2. Wait for you to make sense and move choices
3. Guide you through the game turn by turn

## Example Conversation Flow

**You**: "Create an RBC game against the trout bot as white"

**Claude**: Uses `create_local_game(bot_type="trout", color="white")`
→ Returns game_id: 1

**Claude**: "Game created! It's your turn to sense. Where would you like to sense?"

**You**: "Sense at e7"

**Claude**: Uses `choose_sense(game_id=1, square="e7")`
Then uses `get_sense_result(game_id=1)` to show you what pieces are there

**Claude**: "I can see [pieces]. Now choose a move."

**You**: "Move e2e4"

**Claude**: Uses `choose_move(game_id=1, move="e2e4")`
Then shows the result and continues...

## Game Rules Cheat Sheet

### Each Turn:
1. **Opponent Notification**: Did they capture your piece?
2. **Sense Phase**: Choose a square, see 3x3 area
3. **Move Phase**: Make your move

### Key Differences from Chess:
- ❌ No checkmate - must capture king
- ❌ Can't see opponent pieces (until you sense them)
- ✓ Can move into check
- ✓ Can castle through check
- ✓ Illegal moves = pass turn

### Bots:
- **random**: Random moves (easiest)
- **attacker**: Prefers captures, senses forward
- **trout**: Hunts your king (hardest)

## Remote Play

To play on rbc.jhuapl.edu:

```
"Connect me to remote game XYZ on rbc.jhuapl.edu
using auth token bWNwX3JiYzpCZWF6ZXJCMzNz"
```

Claude will use `create_remote_game()` with your credentials.

## Troubleshooting

### "Game not responding"
Check status: `get_game_status(game_id=1)`
Look for `waiting_for_sense` or `waiting_for_move`

### "Board looks wrong"
Remember: You only see YOUR pieces and sensed squares!
Use `get_board_state()` to see your current knowledge

### "Move was illegal"
In RBC, illegal moves just pass your turn. Check:
- Did you sense that square?
- Is the path clear (as far as you know)?

## Tips for Playing

1. **Sense strategically**: Sense where you think opponent pieces are
2. **Track the king**: Once you find it, track its movements
3. **Protect your king**: It can be captured in one move!
4. **Use uncertainty**: Make moves that work even if you're wrong
5. **Sense before critical moves**: Verify the path is clear

## Need Help?

See [README.md](README.md) for complete documentation including:
- Full rules explanation
- All MCP tools reference
- Architecture details
- Remote game setup

Happy hunting! 🎯
