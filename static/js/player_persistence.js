/**
 * Player ID Persistence Manager
 * 
 * Ensures player_uid is stored in multiple locations for maximum resilience:
 * 1. HTTP-only cookie (secure, not accessible to JS but sent with requests)
 * 2. localStorage (survives browser refresh, cleared on aggressive cache clear)
 * 3. IndexedDB (survives most cache clears, restored on new visits)
 * 
 * Fallback chain: Cookie → localStorage → IndexedDB → Generate new UUID
 */

const PLAYER_ID_DB = 'BordlePlayerDB';
const PLAYER_ID_STORE = 'playerIdStore';
const PLAYER_ID_KEY = 'player_uid';
const STORAGE_LOG_PREFIX = '[PLAYER_PERSISTENCE]';

/**
 * Generate a UUID v4
 */
function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Read a cookie value by name
 */
function getCookie(name) {
  const nameEQ = name + '=';
  const cookies = document.cookie.split(';');
  for (let i = 0; i < cookies.length; i++) {
    const cookie = cookies[i].trim();
    if (cookie.startsWith(nameEQ)) {
      return cookie.substring(nameEQ.length);
    }
  }
  return null;
}

/**
 * Initialize IndexedDB for player ID storage
 */
async function initIndexedDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(PLAYER_ID_DB, 1);
    
    request.onerror = () => {
      console.warn(`${STORAGE_LOG_PREFIX} ❌ IndexedDB failed to open`);
      reject(request.error);
    };
    
    request.onsuccess = () => {
      resolve(request.result);
    };
    
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains(PLAYER_ID_STORE)) {
        db.createObjectStore(PLAYER_ID_STORE);
        console.log(`${STORAGE_LOG_PREFIX} Created IndexedDB store: ${PLAYER_ID_STORE}`);
      }
    };
  });
}

/**
 * Get player_uid from IndexedDB
 */
async function getFromIndexedDB() {
  try {
    const db = await initIndexedDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction([PLAYER_ID_STORE], 'readonly');
      const store = transaction.objectStore(PLAYER_ID_STORE);
      const request = store.get(PLAYER_ID_KEY);
      
      request.onsuccess = () => {
        resolve(request.result);
      };
      
      request.onerror = () => {
        reject(request.error);
      };
    });
  } catch (e) {
    console.warn(`${STORAGE_LOG_PREFIX} ⚠️ Could not read from IndexedDB:`, e.message);
    return null;
  }
}

/**
 * Store player_uid in IndexedDB
 */
async function storeInIndexedDB(value) {
  try {
    const db = await initIndexedDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction([PLAYER_ID_STORE], 'readwrite');
      const store = transaction.objectStore(PLAYER_ID_STORE);
      const request = store.put(value, PLAYER_ID_KEY);
      
      request.onsuccess = () => {
        console.log(`${STORAGE_LOG_PREFIX} ✅ Stored player_uid in IndexedDB`);
        resolve();
      };
      
      request.onerror = () => {
        reject(request.error);
      };
    });
  } catch (e) {
    console.warn(`${STORAGE_LOG_PREFIX} ⚠️ Could not store in IndexedDB:`, e.message);
  }
}

/**
 * Main function: Get or create player ID with multi-tier fallback
 * Returns: { playerId: string, source: 'cookie' | 'localStorage' | 'indexeddb' | 'generated', recovered: boolean }
 */
async function getOrCreatePlayerId() {
  let playerId = null;
  let source = null;
  let recovered = false;

  console.log(`${STORAGE_LOG_PREFIX} 🔍 Attempting to recover player_uid...`);

  // 1. Try cookie (most reliable, set by server)
  const cookieId = getCookie('player_uid');
  if (cookieId) {
    playerId = cookieId;
    source = 'cookie';
    console.log(`${STORAGE_LOG_PREFIX} ✅ Found player_uid in cookie: ${playerId}`);
  }

  // 2. Try localStorage (survives refresh, can be cleared)
  if (!playerId) {
    const localStorageId = localStorage.getItem(PLAYER_ID_KEY);
    if (localStorageId) {
      playerId = localStorageId;
      source = 'localStorage';
      recovered = true;
      console.log(`${STORAGE_LOG_PREFIX} ✅ Recovered player_uid from localStorage: ${playerId}`);
    }
  }

  // 3. Try IndexedDB (survives aggressive cache clear)
  if (!playerId) {
    try {
      const indexedDBId = await getFromIndexedDB();
      if (indexedDBId) {
        playerId = indexedDBId;
        source = 'indexeddb';
        recovered = true;
        console.log(`${STORAGE_LOG_PREFIX} ✅ Recovered player_uid from IndexedDB: ${playerId}`);
      }
    } catch (e) {
      console.warn(`${STORAGE_LOG_PREFIX} ⚠️ IndexedDB recovery failed:`, e.message);
    }
  }

  // 4. Generate new if all fail
  if (!playerId) {
    playerId = generateUUID();
    source = 'generated';
    console.log(`${STORAGE_LOG_PREFIX} 🆕 Generated new player_uid: ${playerId}`);
  }

  // Store in all persistent locations
  console.log(`${STORAGE_LOG_PREFIX} 💾 Persisting player_uid to all storage layers...`);
  localStorage.setItem(PLAYER_ID_KEY, playerId);
  await storeInIndexedDB(playerId);

  // Log recovery event if applicable
  if (recovered) {
    console.log(`${STORAGE_LOG_PREFIX} 🔄 RECOVERY EVENT: Restored player_uid from ${source}`);
    // Send telemetry if desired
    fetch('/api/observability/player_recovery', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        player_uid: playerId,
        source: source,
        timestamp: new Date().toISOString()
      })
    }).catch(() => {
      // Silent fail - telemetry is non-critical
    });
  }

  return {
    playerId,
    source,
    recovered
  };
}

/**
 * Expose for manual use in templates/scripts
 */
window.PlayerPersistence = {
  getOrCreatePlayerId,
  generateUUID,
  getCookie,
  STORAGE_LOG_PREFIX
};
