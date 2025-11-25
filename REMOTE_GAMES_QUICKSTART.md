# Remote Games Quick Start

Quick reference for connecting bots to rbc.jhuapl.edu.

## Prerequisites

1. **Register**: https://rbc.jhuapl.edu/register
2. **Confirm email** from the verification link
3. **Install dependencies**: `pip install -r requirements.txt`

## Quick Commands

### Connect Bot (Unranked)

```json
{
  "tool": "connect_bot",
  "arguments": {
    "username": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD",
    "bot_path": "reconchess.bots.random_bot",
    "ranked": false,
    "max_concurrent_games": 4
  }
}
```

**Returns**: `connection_id` (use this for all other commands)

### Check Status

```json
{
  "tool": "get_bot_connection_status",
  "arguments": {
    "connection_id": 1
  }
}
```

### Disconnect

```json
{
  "tool": "disconnect_bot",
  "arguments": {
    "connection_id": 1
  }
}
```

## Bot Paths

### Built-in Bots
- `"reconchess.bots.random_bot"` - Random moves
- `"reconchess.bots.attacker_bot"` - Aggressive play
- `"reconchess.bots.trout_bot"` - King-seeking (requires Stockfish)

### Custom Bots
- Module: `"my_package.my_bot"`
- File: `"src/my_bot.py"` or `"/absolute/path/to/bot.py"`

## Ranked Games

```json
{
  "tool": "connect_bot",
  "arguments": {
    "username": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD",
    "bot_path": "reconchess.bots.trout_bot",
    "ranked": true,
    "max_concurrent_games": 2
  }
}
```

**Version Management**:
- First connection: Version auto-increments from 0 → 1
- Update bot: Use `increment_bot_version` to start fresh ELO
- Each version has separate rating

## Server Utilities

### See Who's Online

```json
{
  "tool": "get_active_users",
  "arguments": {
    "username": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
  }
}
```

### Challenge Someone

```json
{
  "tool": "send_invitation",
  "arguments": {
    "username": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD",
    "opponent": "opponent_username",
    "color": "white"
  }
}
```

### Check Your Invitations

```json
{
  "tool": "get_invitations",
  "arguments": {
    "username": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
  }
}
```

### Verify Version

```json
{
  "tool": "check_server_version",
  "arguments": {
    "username": "YOUR_USERNAME",
    "password": "YOUR_PASSWORD"
  }
}
```

If versions don't match: `pip install --upgrade reconchess`

## Typical Workflow

```
1. check_server_version      # Verify compatibility
2. get_active_users          # See who's online (optional)
3. connect_bot               # Start bot → get connection_id
4. get_bot_connection_status # Monitor progress
   ... bot plays games automatically ...
5. disconnect_bot            # Stop when done
```

## Status Fields

When you call `get_bot_connection_status`, you'll see:

```json
{
  "connection_id": 1,
  "server_url": "https://rbc.jhuapl.edu",
  "ranked": true,
  "max_concurrent_games": 4,
  "active": true,           // Still accepting games
  "connected": true,        // Connected to server
  "games_played": 7,        // Total games completed
  "bot_version": 2          // Current version (ranked only)
}
```

## Common Issues

**"Authentication Error"**
→ Check username/password, verify email is confirmed

**"Version mismatch"**
→ Run `pip install --upgrade reconchess`

**Bot not playing games**
→ Check `active: true` and `connected: true` in status

**Too many concurrent games**
→ Reduce `max_concurrent_games` to 2-4

## More Information

- **Detailed Guide**: See [REMOTE_GAMES_GUIDE.md](REMOTE_GAMES_GUIDE.md)
- **Official Docs**: https://reconchess.readthedocs.io
- **Server**: https://rbc.jhuapl.edu
