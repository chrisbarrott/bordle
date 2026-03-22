# Testing Stats Migration Logging

This document explains how to test and verify the player stats migration from client-side localStorage to server-side database.

## Quick Testing Steps

### 1. **Check Current Stats in Browser Console**
Open browser DevTools (F12) and check the logs when the page loads:

```
[CLIENT_MIGRATION] Found local stats: {gamesPlayed: 5, gamesWon: 3, currentStreak: 1, ...}
[CLIENT_MIGRATION] Cookie player_uid: <uuid-here>
[CLIENT_MIGRATION] Posting stats to server...
[CLIENT_MIGRATION] Response status: 200
[CLIENT_MIGRATION] Response body: {status: "ok"}
[CLIENT_MIGRATION] ✅ Migration successful
```

### 2. **Server Logs to Watch**

After visiting `/game` with local stats, check the Flask app logs for:

#### **API Endpoint Logs** (`[API_MIGRATE]`)
```
[API_MIGRATE] Request received from IP: 127.0.0.1
[API_MIGRATE] Player UID from cookie: 550e8400-e29b-41d4-a716-446655440000
[API_MIGRATE] Final player_uid: 550e8400-e29b-41d4-a716-446655440000
[API_MIGRATE] Stats payload: {'gamesPlayed': 5, 'gamesWon': 3, 'currentStreak': 1, ...}
[API_MIGRATE] Starting migration for 550e8400-e29b-41d4-a716-446655440000
```

#### **Migration Logs** (`[MIGRATION]`)
```
[MIGRATION] Starting migration for 550e8400-e29b-41d4-a716-446655440000
[MIGRATION] Client-side stats received: {'gamesPlayed': 5, 'gamesWon': 3, ...}
[MIGRATION] Existing server stats for 550e8400-e29b-41d4-a716-446655440000: None
[MIGRATION] Parsed client stats: played=5, won=3, streak=1, best=1
[MIGRATION] No existing stats found. Creating new record for 550e8400-e29b-41d4-a716-446655440000
[MIGRATION] Inserted new player stats: 550e8400-e29b-41d4-a716-446655440000
[MIGRATION] ✅ Migration complete for player 550e8400-e29b-41d4-a716-446655440000
[API_MIGRATE] ✅ Migration result: {'status': 'ok'}
```

### 3. **Test Already Migrated (Should Skip)**

Reload the page or visit `/game` again:

**Browser Console:**
```
[CLIENT_MIGRATION] ✅ Stats already migrated (flag set)
```

**Server Logs:**
```
[MIGRATION] Starting migration for 550e8400-e29b-41d4-a716-446655440000
[MIGRATION] Client-side stats received: {'gamesPlayed': 5, 'gamesWon': 3, ...}
[MIGRATION] Existing server stats for 550e8400-e29b-41d4-a716-446655440000: {'games_played': 5, 'games_won': 3, ...}
[MIGRATION] ⚠️ Player already migrated. Skipping to prevent double-count.
[API_MIGRATE] ✅ Migration result: {'status': 'skipped', 'reason': 'already_migrated'}
```

### 4. **Check Stats in Database**

Visit `/api/player_stats_debug` endpoint to see current server-side stats:

```bash
curl http://localhost:5000/api/player_stats_debug
```

Response (if stats exist):
```json
{
  "player_uid": "550e8400-e29b-41d4-a716-446655440000",
  "stats": {
    "games_played": 5,
    "games_won": 3,
    "current_streak": 1,
    "best_streak": 1,
    "migrated": true
  },
  "status": "found"
}
```

Server logs from this call:
```
[DEBUG_STATS] Checking stats for player 550e8400-e29b-41d4-a716-446655440000
[DEBUG_STATS] ✅ Found stats: {'games_played': 5, 'games_won': 3, ...}
```

## Troubleshooting Scenarios

### Scenario 1: No Cookie Found
**Browser Console:**
```
[CLIENT_MIGRATION] ❌ No player_uid cookie found
```

**Fix:** Clear site data or use a fresh browser session.

### Scenario 2: Migration Fails (Network Error)
**Browser Console:**
```
[CLIENT_MIGRATION] ❌ Fetch failed: TypeError: Failed to fetch
```

**Fix:** Check Flask server is running, CORS issues, etc.

### Scenario 3: No Local Stats
**Browser Console:**
```
[CLIENT_MIGRATION] ⚠️ No local stats found in localStorage
```

**Fix:** Play a game first to generate local stats, or manually set:
```javascript
localStorage.setItem('bordleStats', JSON.stringify({gamesPlayed: 1, gamesWon: 1, currentStreak: 1, bestStreak: 1}));
```
### Updating Stats on Game End
Prior to March 7, 2026 the game did *not* update `localStorage` when a game finished, which meant the end-game modals showed stale numbers. That has been fixed: the `updateLocalStats(won)` function now runs automatically when a win or loss modal appears.

**Expected flow:**
1. Complete a game (win or lose).
2. Open the browser console; you should see something like:
```
[LOCAL_STATS] updated {gamesPlayed: 7, gamesWon: 4, currentStreak: 2, bestStreak: 3}
[CLIENT_MIGRATION] Posting stats to server...
```
3. The stats table in the modal will show updated numbers immediately.

If the numbers still don't change, ensure no JavaScript errors appear and that `updateLocalStats` is defined (it lives in `index.html`).
### Scenario 4: Stats Not Found on Server
**Debug Endpoint Response:**
```json
{
  "player_uid": "550e8400-e29b-41d4-a716-446655440000",
  "stats": null,
  "status": "not_found"
}
```

**Server Logs:**
```
[DEBUG_STATS] ⚠️ No stats found for 550e8400-e29b-41d4-a716-446655440000
```

**Fix:** Migration may not have run; check browser console for errors.

## Key Takeaways

- **Migration flag** (`bordleStatsMigrated` in localStorage) prevents duplicate migrations
- **`migrated` flag** in `player_stats` table prevents server-side double-counting
- **Idempotent**: Safe to migrate multiple times per player
- **Logs use prefixes** (`[CLIENT_MIGRATION]`, `[API_MIGRATE]`, `[MIGRATION]`, `[DEBUG_STATS]`) for easy filtering
- **Debug endpoint** at `/api/player_stats_debug` shows current server state
