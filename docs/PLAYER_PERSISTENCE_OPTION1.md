# Player ID Persistence (Option 1): Multi-Tier Fallback

## Overview

Player stats are now stored persistently using a **3-tier fallback system** to handle cookie loss, browser cache clears, and device switches (with recovery).

### Storage Tiers (Priority Order)

1. **HTTP-only Cookie** (Most secure, server-set)
   - Set by Flask on first visit (`max_age=1 year`)
   - Sent automatically with every request
   - Can be cleared by user or aggressive cache clear

2. **localStorage** (Medium security, user-accessible from JS)
   - Persists across browser refresh
   - Cleared when user manually clears "cookies and site data"
   - Fast access from JavaScript

3. **IndexedDB** (Most persistent, survives aggressive cache clears)
   - Survives most browser cache-clear scenarios
   - Survives OS-level temp file cleanup
   - Fallback when localStorage also cleared

4. **Generate New** (Last resort)
   - UUID v4 generated if all storage methods fail
   - Treated as a new user

## How It Works

### On Page Load

1. **Browser loads** [player_persistence.js](../static/js/player_persistence.js)
2. **`getOrCreatePlayerId()` called** (via stats migration script):
   - Check cookie → success? Done.
   - Check localStorage → success? **Mark as recovered**, use it.
   - Check IndexedDB → success? **Mark as recovered**, use it.
   - Generate new UUID → **Mark as new user**
3. **Replicate** to all 3 storage layers (cookie set by server later, localStorage + IndexedDB set immediately)
4. **Log recovery** event if player_uid came from fallback (not cookie)

### When Cookie is Cleared

**User clears browser cookies manually:**
- ❌ Cookie gone
- ✅ localStorage still present → recovered
- ✅ IndexedDB still present → fallback available

**Browser performs aggressive cache clear:**
- ❌ Cookie gone
- ❌ localStorage gone
- ✅ IndexedDB often survives → recovered
- Generate new UUID if IndexedDB also missing

### Stats Migration Flow (Updated)

```
[Client]
  ↓
localStorage.bordleStats (old client-side stats)
  ↓
PlayerPersistence.getOrCreatePlayerId() 
  → tries: cookie → localStorage → IndexedDB → generate
  → returns: {playerId, source, recovered}
  ↓
POST /api/migrate_stats {player_uid, stats}
  ↓
[Server]
  ↓
migrate_player_stats(player_uid, stats)
  → checks if already migrated (idempotent)
  → updates or creates player_stats row
  → sets migrated=1
```

## Logging & Debugging

### Browser Console (`[PLAYER_PERSISTENCE]` prefix)

```javascript
// On normal visit (cookie present)
[PLAYER_PERSISTENCE] 🔍 Attempting to recover player_uid...
[PLAYER_PERSISTENCE] ✅ Found player_uid in cookie: <uuid>
[PLAYER_PERSISTENCE] 💾 Persisting player_uid to all storage layers...

// On cookie-loss recovery
[PLAYER_PERSISTENCE] 🔍 Attempting to recover player_uid...
[PLAYER_PERSISTENCE] ✅ Recovered player_uid from localStorage: <uuid>
[PLAYER_PERSISTENCE] 💾 Persisting player_uid to all storage layers...
[PLAYER_PERSISTENCE] 🔄 RECOVERY EVENT: Restored player_uid from localStorage
[PLAYER_PERSISTENCE] ✅ Stored player_uid in IndexedDB

// Stats migration uses recovered ID
[CLIENT_MIGRATION] Using player_uid from localStorage: <uuid>
[CLIENT_MIGRATION] 🔄 Player ID was recovered (cookie was missing)
```

### Server Logs (`[PLAYER_RECOVERY]` prefix)

```
[PLAYER_RECOVERY] {"event": "PLAYER_UID_RECOVERY", "player_uid": "uuid", "source": "localStorage", ...}
```

### Debug Endpoint

```bash
curl http://localhost:5000/api/player_stats_debug
# Returns current server-side stats for player_uid (from cookie)
```

## Testing Scenarios

### Scenario 1: Normal Visit (Cookie Present)
**Expected:** Uses cookie, no recovery event
```
1. Open browser → DevTools → Application → Cookies → player_uid present
2. Console shows: "[PLAYER_PERSISTENCE] ✅ Found player_uid in cookie"
3. No recovery event logged
```

### Scenario 2: Cookie Cleared (localStorage Fallback)
**Expected:** Recovers from localStorage, logs recovery
```
1. DevTools → Application → Clear site data (uncheck "Cookies" to keep storage)
2. Hard refresh (Ctrl+Shift+R)
3. Console shows: "[PLAYER_PERSISTENCE] ✅ Recovered player_uid from localStorage"
4. Server logs recovery event
5. Player_uid is **same as before**
```

### Scenario 3: Aggressive Cache Clear (IndexedDB Fallback)
**Expected:** Recovers from IndexedDB
```
1. DevTools → Application → Clear all site data (including IndexedDB)
2. Hard refresh
3. IndexedDB still has data (Edge case: depends on browser implementation)
4. Console shows recovery from IndexedDB
```

### Scenario 4: All Storage Cleared (Generate New)
**Expected:** New UUID generated, treated as new user
```
1. DevTools → Application → Clear all site data
2. Delete IndexedDB manually (if persisted)
3. Hard refresh
4. Console shows: "[PLAYER_PERSISTENCE] 🆕 Generated new player_uid"
5. New row in player_stats table
```

## Current Limitations (Known)

| Scenario | Result | Plan |
|----------|--------|------|
| **Browser A → Browser B** (same device) | ❌ New UUID (different player_uid) | Option 2: Add email-based account linking |
| **Device A → Device B** | ❌ New UUID | Option 2: Email recovery, or Option 3: QR export/import |
| **Private/Incognito mode** | ⚠️ Cookies + storage may not persist | Normal browsers only (acceptable trade-off) |
| **Shared device, multiple users** | ✅ Each user gets unique player_uid via new browser profile | Recommend separate profiles |

## Implementation Details

### Files Modified

1. **[static/js/player_persistence.js]** (new)
   - `getOrCreatePlayerId()` — main function
   - `generateUUID()` — random UUID v4
   - `getCookie()` — read player_uid cookie
   - IndexedDB helpers: `initIndexedDB()`, `getFromIndexedDB()`, `storeInIndexedDB()`

2. **[templates/base.html]**
   - Added script tag to load player_persistence.js on every page

3. **[templates/index.html]**
   - Updated migration script to use `PlayerPersistence.getOrCreatePlayerId()`
   - Now awaits async recovery attempt before POST

4. **[app.py]**
   - New endpoint: `/api/observability/player_recovery` (logs recovery events)

5. **[services/game_database_connections.py]**
   - No changes (already idempotent)

### Database Schema (No Changes)

`player_stats` table already supports this:
- `player_uid` (PRIMARY KEY) — unique identifier
- `migrated` (flag) — prevents double-migration

## Next Steps (Optional)

1. **Monitor recovery events** — Check logs for unexpected recovery patterns
2. **Add Option 2** (email-based account recovery) — if cross-device persistence needed
3. **Add Option 3** (QR export/import) — if users request backup/restore
4. **Test on multiple browsers** — Chrome, Firefox, Safari, Edge
5. **Performance tuning** — IndexedDB access is async; monitor page load time

## Quick Reference: API Functions

```javascript
// In browser console or templates:

// Get/create player ID with fallback
const {playerId, source, recovered} = await window.PlayerPersistence.getOrCreatePlayerId();
// Returns:
// - playerId: string (UUID)
// - source: 'cookie' | 'localStorage' | 'indexeddb' | 'generated'
// - recovered: boolean (true if came from fallback, not cookie)

// Helper functions available:
window.PlayerPersistence.generateUUID() → "xxx-xxx-xxx"
window.PlayerPersistence.getCookie('player_uid') → "xxx-xxx-xxx" or null
```
