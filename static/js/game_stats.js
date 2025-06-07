document.addEventListener("DOMContentLoaded", () => {
  const statsButton = document.getElementById("stats-button");
  const howtoButton = document.getElementById("howto-button");
  const statsModal = document.getElementById("stats-modal");
  const howtoModal = document.getElementById("howto-modal");
  const closeStats = document.getElementById("close-stats");
  const closeHowto = document.getElementById("close-howto");

  // Toggle modal functions
  statsButton.addEventListener("click", () => {
    populateStats();
    statsModal.classList.remove("hidden");
  });
  howtoButton.addEventListener("click", () => {
    howtoModal.classList.remove("hidden");
  });
  closeStats.addEventListener("click", () => {
    statsModal.classList.add("hidden");
  });
  closeHowto.addEventListener("click", () => {
    howtoModal.classList.add("hidden");
  });

  // Close modals on outside click
  window.addEventListener("click", (event) => {
    if (event.target === statsModal) statsModal.classList.add("hidden");
    if (event.target === howtoModal) howtoModal.classList.add("hidden");
  });
});

function populateStats() {
  const statsContainer = document.getElementById("stats-container");
  const stats = JSON.parse(localStorage.getItem("bordleStats")) || {
    gamesPlayed: 0,
    gamesWon: 0,
    currentStreak: 0,
    maxStreak: 0,
  };

  statsContainer.innerHTML = `
    <p>Games Played: ${stats.gamesPlayed}</p>
    <p>Games Won: ${stats.gamesWon}</p>
    <p>Current Streak: ${stats.currentStreak}</p>
    <p>Max Streak: ${stats.maxStreak}</p>
  `;
}




// Attach events once the DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  const openBtn = document.getElementById("showStatsButton");
  const closeBtn = document.getElementById("closeStatsModal");

  if (openBtn) openBtn.addEventListener("click", toggleStatsModal);
  if (closeBtn) closeBtn.addEventListener("click", closeStatsModal);
});

// ✅ Display user stats in modal
function showEndStats() {
  const statsBlock = document.getElementById("statsContainer");
  statsBlock.classList.remove("hidden");

  const rawStats = localStorage.getItem("bordleStats");
  console.log("Raw stats from localStorage:", rawStats);

  if (!rawStats) {
    console.warn("Stats not found in localStorage");
    return;
  }

  let stats;
  try {
    stats = JSON.parse(rawStats);
  } catch (e) {
    console.error("Failed to parse stats:", e);
    return;
  }

  console.log("Parsed stats:", stats);
  if (!stats) return;

  const gamesPlayed = parseInt(stats.gamesPlayed ?? 0);
  const gamesWon = parseInt(stats.gamesWon ?? 0);
  const currentStreak = parseInt(stats.currentStreak ?? 0);
  const maxStreak = parseInt(stats.maxStreak ?? 0);
  const successRate = gamesPlayed > 0 ? Math.round((gamesWon / gamesPlayed) * 100) : 0;

  document.getElementById("gamesPlayed").textContent = gamesPlayed;
  document.getElementById("gamesWon").textContent = gamesWon;
  document.getElementById("currentStreak").textContent = currentStreak;
  document.getElementById("successRate").textContent = `${successRate}%`;
  document.getElementById("maxStreak").textContent = maxStreak;

}

// ✅ Updates stats only once per game
function updateStats(didWin, gameNumber) {
  console.log("starting update stats");

  const statsKey = `bordleStatsUpdated_${gameNumber}`;
  console.log("statskey: ", statsKey);

  // Don't update again if already recorded
  if (localStorage.getItem(statsKey)) {
    console.log("Not recording again")
    return;
  }

  const stats = JSON.parse(localStorage.getItem("bordleStats")) || {
    gamesPlayed: 0,
    gamesWon: 0,
    currentStreak: 0,
    maxStreak: 0,
    successRate: 0,
  };

  stats.gamesPlayed += 1;
  console.log(didWin)
  if (didWin == "Win") {
    stats.gamesWon += 1;
    stats.currentStreak += 1;
    if (stats.currentStreak > stats.maxStreak) {
      stats.maxStreak = stats.currentStreak;
    }
  } else {
    stats.currentStreak = 0;
  }

  localStorage.setItem("bordleStats", JSON.stringify(stats));
  localStorage.setItem(statsKey, "true");
  console.log("Local storage:", localStorage.getItem("bordleStats"));
}

// Call when game ends (success true or false)
function recordGameResult(success) {
  fetch('/api/game-result', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ success })
  })
  .then(res => res.json())
  .then(data => {
    if(data.status === 'success') {
      console.log('Result saved');
      fetchGlobalStats();
    }
  })
  .catch(console.error);
}

function displayLocalStats() {
  const stats = JSON.parse(localStorage.getItem("bordleStats"));
  if (!stats) return;

  console.log("Show end stats: ", stats)

  const successRate = stats.gamesPlayed > 0
    ? Math.round((stats.gamesWon / stats.gamesPlayed) * 100)
    : 0;
  
  document.getElementById("games-played").innerText = stats.gamesPlayed;
  document.getElementById("games-won").innerText = stats.gamesWon;
  document.getElementById("current-streak").innerText = stats.currentStreak;
  document.getElementById("max-streak").innerText = stats.maxStreak;
  document.getElementById("success-rate").innerText = `${successRate}%`;
}

// Fetch and display global stats from server
// function fetchGlobalStats() {
//   fetch('/api/stats')
//     .then(res => res.json())
//     .then(stats => {
//       document.getElementById('total-games').textContent = stats.total_games;
//       document.getElementById('success-rate').textContent = stats.success_rate.toFixed(2);
//       // Update other UI elements as needed
//     })
//     .catch(console.error);
// }

// // Load and display local user stats stored in localStorage
// function displayLocalStats() {
//   const gamesPlayed = localStorage.getItem('bordle_games_played') || 0;
//   const wins = localStorage.getItem('bordle_wins') || 0;
//   const successRate = gamesPlayed > 0 ? ((wins / gamesPlayed) * 100).toFixed(2) : '0.00';

//   document.getElementById('local-games-played').textContent = gamesPlayed;
//   document.getElementById('local-wins').textContent = wins;
//   document.getElementById('local-success-rate').textContent = successRate;
// }

// // Run on page load
// window.addEventListener('DOMContentLoaded', () => {
//   fetchGlobalStats();
//   displayLocalStats();
// });