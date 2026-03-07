function showStatsContainter() {
    const container = document.getElementById('statsContainer');
    container.classList.toggle('hidden');

    const stats = JSON.parse(localStorage.getItem("bordleStats"));

    if (!stats) return 
    const gamesPlayed = parseInt(stats.gamesPlayed ?? 0);
    const gamesWon = parseInt(stats.gamesWon ?? 0);
    const currentStreak = parseInt(stats.currentStreak ?? 0);
    const successRate = gamesPlayed > 0 ? Math.round((gamesWon / gamesPlayed) * 100) : 0;

    document.getElementById("game_played").innerText = stats.gamesPlayed;
    document.getElementById("game_won").innerText = stats.gamesWon;
    document.getElementById("local_current_streak").innerText = stats.currentStreak;
    document.getElementById("local_success_rate").innerText = `${successRate}%`;
}
