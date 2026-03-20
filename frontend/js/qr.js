/* global fetch */

async function generateQr() {
  const dataInput = document.getElementById("qrData");
  const seasonSelect = document.getElementById("qrSeason");
  const err = document.getElementById("qrErr");
  const img = document.getElementById("qrImg");

  err.textContent = "";
  img.style.display = "none";

  const data = (dataInput.value || "").trim();
  const season = seasonSelect.value || "auto";
  if (!data) {
    err.textContent = "Введите ссылку для QR.";
    return;
  }

  const url = `/api/qr/?data=${encodeURIComponent(data)}&season=${encodeURIComponent(season)}`;
  const resp = await fetch(url);
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`;
    try {
      const j = await resp.json();
      msg = j.detail || msg;
    } catch {
      // ignore
    }
    err.textContent = msg;
    return;
  }

  const blob = await resp.blob();
  const objUrl = URL.createObjectURL(blob);
  img.src = objUrl;
  img.style.display = "block";
}

document.getElementById("btnQr").onclick = () => {
  generateQr().catch((e) => {
    const err = document.getElementById("qrErr");
    err.textContent = e.message || String(e);
  });
};

