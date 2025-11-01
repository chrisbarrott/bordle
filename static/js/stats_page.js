async function loadStats() {
  try {
    const response = await fetch("/api/leaderboard");
    const data = await response.json();

    renderLeaderboard("dailyLeaderboardRows", data.daily);
    renderLeaderboard("allTimeLeaderboardRows", data.all_time);
    renderUserStats();
  } catch (err) {
    console.error("Error loading stats:", err);
  }
}

function renderLeaderboard(elementId, rows) {
  const tbody = document.getElementById(elementId);
  tbody.innerHTML = "";

  if (!rows || rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="3" class="text-center py-2 text-gray-500">No data available</td></tr>`;
    return;
  }

  rows.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="py-1">${r.country}</td>
      <td class="py-1 text-right">${r.success_rate.toFixed(1)}%</td>
      <td class="py-1 text-right">${r.plays}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderUserStats() {
  const stats = JSON.parse(localStorage.getItem("bordleStats")) || {};
  const container = document.getElementById("userStats");

  if (!stats.totalGames) {
    container.innerHTML = `<p class="text-gray-500">No games played yet.</p>`;
    return;
  }

  container.innerHTML = `
    <p>Total Games: <strong>${stats.totalGames}</strong></p>
    <p>Wins: <strong>${stats.wins}</strong></p>
    <p>Win Rate: <strong>${((stats.wins / stats.totalGames) * 100).toFixed(1)}%</strong></p>
    <p>Current Streak: <strong>${stats.currentStreak}</strong></p>
    <p>Best Streak: <strong>${stats.bestStreak}</strong></p>
  `;
}

document.addEventListener("DOMContentLoaded", loadStats);
