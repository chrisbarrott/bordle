function shareEndResults() {
    window.open(whatsappUrl, "_blank");
    // shareResults();  // shows updated numbers
}

// function countryToFlagEmoji(country) {
//     const isoUrl = "{{ url_for('static', filename='map_data/iso_country_codes.json') }}";
//     const isoMap = {{ iso_map | tojson }};
//     const code = isoMap[country.trim()];

//     if (!code) return ""; // fallback: no flag

//     return code
//         .toUpperCase()
//         .split("")
//         .map(char => String.fromCodePoint(127397 + char.charCodeAt(0)))
//         .join("");
// }

// function shareResults() {
//     const country = "{{ country_name }}";
//     const correct = {{ correct_count }};
//     const total = {{ border_count }};
//     const hardMode = {{ 'true' if hard_mode else 'false' }};
//     const date = new Date().toLocaleDateString('en-GB');
//     const gameNumber = {{ game_number }}

//     const guessHistory = {{ guess_history | default([]) | tojson }};
//     const correctGuesses = {{ correct_guesses | default([]) | tojson }};
//     const wrongGuesses = {{ wrong_guesses | default([]) | tojson }};
//     const flatGuessHistory = guessHistory.flat();

//     let resultEmojis = [];

//     for (let guess of flatGuessHistory) {
//         if (correctGuesses.includes(guess)) {
//         resultEmojis.push("🟩");
//         } else if (wrongGuesses.includes(guess)) {
//         resultEmojis.push("🟥");
//         } else {
//         resultEmojis.push("⬜");
//         }
//     }

//     const flag = countryToFlagEmoji(country);
//     const result = `Bordle 🌍 - ${date} - (#${gameNumber})
//     Country: ${hardMode === 'true' ? '???' : `${country} ${flag}`}
//     ${resultEmojis.join('')} (${correct}/${total})
//     https://bordle.world`;

//     const encodedMessage = encodeURIComponent(result);
//     const whatsappUrl = `https://wa.me/?text=${encodedMessage}`;
//     window.open(whatsappUrl, "_blank");
// }