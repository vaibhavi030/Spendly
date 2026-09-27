document.addEventListener("DOMContentLoaded", function () {

    const themeToggle = document.getElementById("themeToggle");

    if (themeToggle) {
        themeToggle.addEventListener("click", async function () {
            const isDark = document.body.classList.toggle("dark-mode");

            themeToggle.textContent = isDark ? "☀️" : "🌙";

            try {
                await fetch("/settings", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    body: "theme=" + encodeURIComponent(isDark ? "dark" : "light")
                });
            } catch (error) {
                console.log("Theme preference could not be saved.");
            }
        });
    }

});
