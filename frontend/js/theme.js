(function () {
  const palettes = {
    winter: {
      primary: "#5cc8ff",
      bg: "#07121f",
      panel: "#0f2536",
    },
    spring: {
      primary: "#6fe37a",
      bg: "#06150f",
      panel: "#0f2c1b",
    },
    summer: {
      primary: "#ffcc66",
      bg: "#140e06",
      panel: "#2a1b10",
    },
    autumn: {
      primary: "#ff7a93",
      bg: "#120606",
      panel: "#2a0f16",
    },
  };

  function getSeason() {
    // 1) URL override
    const url = new URL(window.location.href);
    const fromQuery = (url.searchParams.get("theme") || "").toLowerCase();
    if (fromQuery && palettes[fromQuery]) return fromQuery;

    // 2) Local override
    const stored = (localStorage.getItem("photoTheme") || "").toLowerCase();
    if (stored && palettes[stored]) return stored;

    // 3) Auto by month
    const m = new Date().getMonth() + 1;
    if (m === 12 || m === 1 || m === 2) return "winter";
    if (m >= 3 && m <= 5) return "spring";
    if (m >= 6 && m <= 8) return "summer";
    return "autumn";
  }

  const season = getSeason();
  const p = palettes[season] || palettes.winter;

  const root = document.documentElement;
  root.style.setProperty("--primary", p.primary);
  root.style.setProperty("--bg", p.bg);
  root.style.setProperty("--panel", p.panel);
})();

