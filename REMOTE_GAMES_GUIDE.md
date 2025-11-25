# Remote Games Guide - RBC MCP Server

This guide explains how to use the RBC MCP Server to connect bots to the official Reconnaissance Blind Chess server at rbc.jhuapl.edu and play remote games.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Bot Connection Tools](#bot-connection-tools)
3. [Server Utility Tools](#server-utility-tools)
4. [Invitation Management](#invitation-management)
5. [Ranked vs Unranked Games](#ranked-vs-unranked-games)
6. [Usage Examples](#usage-examples)

## Prerequisites

Before connecting to the remote server, you must:

1. **Register an account** at https://rbc.jhuapl.edu/register
2. **Confirm your email** via the verification link sent to your address
3. Have a bot implementation ready (either a Python file or module)

## Bot Connection Tools

### connect_bot

Connect a bot to the RBC server to automatically listen for and accept game invitations.

**Parameters:**
- `username` (required): Your RBC server username
- `password` (required): Your RBC server password
- `bot_path` (required): Path to bot source or module name
  - Examples: `"reconchess.bots.random_bot"`, `"src/my_bot.py"`
- `server_url` (optional): Server URL (default: "https://rbc.jhuapl.edu")
- `ranked` (optional): Whether to play ranked matches (default: false)
- `max_concurrent_games` (optional): Maximum concurrent games (default: 4)

**Returns:**
- `connection_id`: ID for managing this bot connection
- Connection status and configuration details

**Example:**
```json
{
  "username": "myusername",
  "password": "mypassword",
  "bot_path": "reconchess.bots.random_bot",
  "ranked": false,
  "max_concurrent_games": 2
}
```

### disconnect_bot

Stop a bot from accepting new invitations and disconnect from the server.

**Parameters:**
- `connection_id` (required): The connection ID to disconnect

**Note:** Active games will continue to completion before fully disconnecting.

### get_bot_connection_status

Get the current status of a bot connection.

**Parameters:**
- `connection_id` (required): The connection ID

**Returns:**
- `active`: Whether the connection is active
- `connected`: Whether successfully connected to server
- `games_played`: Number of games completed
- `bot_version`: Current bot version (for ranked games)
- Configuration details (server URL, ranked mode, etc.)

### list_bot_connections

List all active bot connections.

**Returns:**
- Array of connection IDs

### increment_bot_version

Manually increment the version number for a ranked bot. This is useful when you've updated your bot and want the server to track the new version's ELO separately.

**Parameters:**
- `connection_id` (required): The connection ID (must be ranked)

**Note:** Only works for ranked connections. Version is auto-incremented on first ranked connection.

## Server Utility Tools

### check_server_version

Check if your local reconchess package version matches the server's required version.

**Parameters:**
- `username` (required): Your username
- `password` (required): Your password
- `server_url` (optional): Server URL (default: "https://rbc.jhuapl.edu")

**Returns:**
- `server_version`: Version required by server
- `local_version`: Your installed version
- `match`: Boolean indicating if versions match
- Update instructions if versions don't match

### get_active_users

Get a list of users currently active on the server.

**Parameters:**
- `username` (required): Your username
- `password` (required): Your password
- `server_url` (optional): Server URL (default: "https://rbc.jhuapl.edu")

**Returns:**
- `active_users`: Array of active usernames
- `count`: Number of active users

### send_invitation

Send a game invitation to another user.

**Parameters:**
- `username` (required): Your username
- `password` (required): Your password
- `opponent` (required): Username of opponent to invite
- `color` (required): Color you want to play ("white", "black", or "random")
- `server_url` (optional): Server URL (default: "https://rbc.jhuapl.edu")

**Returns:**
- `game_id`: ID of the created game
- Invitation details

### get_invitations

Get your pending game invitations.

**Parameters:**
- `username` (required): Your username
- `password` (required): Your password
- `server_url` (optional): Server URL (default: "https://rbc.jhuapl.edu")

**Returns:**
- `invitations`: Array of invitation IDs
- `count`: Number of pending invitations

## Ranked vs Unranked Games

### Unranked Mode (Default)

- No ELO rating impact
- Good for testing and practice
- Can play against any active user
- Simply connect with `ranked: false`

### Ranked Mode

- Affects your ELO rating
- Each bot version has separate ELO
- Server prompts for version on first connection
- Version auto-increments to 1 on first ranked connection
- Use `ranked: true` when connecting

**Version Management:**

The server tracks ELO separately for each version of your bot:
- When connecting for the first time (version 0), it auto-increments to version 1
- Update your bot and use `increment_bot_version` to start fresh ELO tracking
- Old versions' ratings don't affect new versions

## Usage Examples

### Example 1: Connect a Bot for Unranked Games

```json
{
  "tool": "connect_bot",
  "arguments": {
    "username": "alice",
    "password": "secure_password",
    "bot_path": "reconchess.bots.trout_bot",
    "ranked": false,
    "max_concurrent_games": 4
  }
}
```

**Response:**
```json
{
  "success": true,
  "connection_id": 1,
  "server_url": "https://rbc.jhuapl.edu",
  "ranked": false,
  "max_concurrent_games": 4,
  "message": "Bot connected successfully. Connection ID: 1. Bot is now listening for invitations."
}
```

### Example 2: Connect a Bot for Ranked Games

```json
{
  "tool": "connect_bot",
  "arguments": {
    "username": "bob",
    "password": "password123",
    "bot_path": "/path/to/my_bot.py",
    "ranked": true,
    "max_concurrent_games": 2
  }
}
```

The bot will automatically:
1. Connect to the server
2. Set ranked mode
3. Increment version (if first time, from 0 to 1)
4. Start listening for ranked game invitations

### Example 3: Check Active Users and Send Invitation

```json
// First, check who's online
{
  "tool": "get_active_users",
  "arguments": {
    "username": "alice",
    "password": "secure_password"
  }
}

// Response: { "active_users": ["bob", "charlie", "alice"], "count": 3 }

// Then send an invitation
{
  "tool": "send_invitation",
  "arguments": {
    "username": "alice",
    "password": "secure_password",
    "opponent": "bob",
    "color": "white"
  }
}
```

### Example 4: Monitor Bot Connection Status

```json
{
  "tool": "get_bot_connection_status",
  "arguments": {
    "connection_id": 1
  }
}
```

**Response:**
```json
{
  "connection_id": 1,
  "server_url": "https://rbc.jhuapl.edu",
  "ranked": true,
  "max_concurrent_games": 4,
  "active": true,
  "connected": true,
  "games_played": 5,
  "bot_version": 2
}
```

### Example 5: Update Bot Version (Ranked Only)

After updating your bot's code:

```json
{
  "tool": "increment_bot_version",
  "arguments": {
    "connection_id": 1
  }
}
```

**Response:**
```json
{
  "success": true,
  "new_version": 3,
  "message": "Bot version incremented to 3"
}
```

Your new version will start with a fresh ELO rating.

### Example 6: Graceful Shutdown

```json
{
  "tool": "disconnect_bot",
  "arguments": {
    "connection_id": 1
  }
}
```

The bot will:
1. Stop accepting new invitations
2. Set unranked mode on server
3. Wait for active games to complete
4. Then fully disconnect

## Workflow: Complete Bot Connection Lifecycle

```
1. Check server version compatibility
   → check_server_version

2. See who's online (optional)
   → get_active_users

3. Connect your bot
   → connect_bot (with ranked: true or false)

4. Bot automatically:
   - Listens for invitations
   - Accepts up to max_concurrent_games
   - Plays games automatically

5. Monitor progress
   → get_bot_connection_status

6. Update bot version (if ranked)
   → increment_bot_version

7. Disconnect when done
   → disconnect_bot
```

## Important Notes

1. **Authentication:** Keep your credentials secure. Never share them.

2. **Version Compatibility:** Always check server version before connecting:
   ```bash
   pip install --upgrade reconchess
   ```

3. **Concurrent Games:** The server limits concurrent games. Start with 2-4 for testing.

4. **Ranked Games:**
   - Can't switch between ranked/unranked without reconnecting
   - Each version has separate ELO
   - Version increments are permanent

5. **Connection Stability:** The bot will retry on server errors (5xx) and reconnect if network fails.

6. **Bot Paths:** Can be:
   - Module name: `"reconchess.bots.random_bot"`
   - File path: `"src/my_bot.py"` or `"/absolute/path/to/bot.py"`

## Troubleshooting

**"Authentication Error"**
- Verify username and password
- Check that email is confirmed

**"Version mismatch"**
- Run: `pip install --upgrade reconchess`
- Restart the MCP server

**"Connection timeout"**
- Check internet connection
- Verify server URL is correct
- Check server status at https://rbc.jhuapl.edu

**"Bot not accepting games"**
- Check connection status
- Verify `active: true` and `connected: true`
- Check server for pending invitations with `get_invitations`

## Resources

- Official Documentation: https://reconchess.readthedocs.io
- Server Website: https://rbc.jhuapl.edu
- GitHub Repository: https://github.com/reconnaissanceblindchess/reconchess
