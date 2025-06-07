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

// // Fetch and display global stats from server
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

// Load and display local user stats stored in localStorage
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
//   // fetchGlobalStats();
//   displayLocalStats();
// });
