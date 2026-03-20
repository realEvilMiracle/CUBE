/* global fetch, window */

const apiBase = "/api";

function getAuthToken() {
  return window.photoAuth?.getAccessToken?.() || "";
}

async function authedGet(url) {
  const token = getAuthToken();
  const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

async function authedPost(url, body) {
  const token = getAuthToken();
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`;
    try {
      const d = await resp.json();
      msg = d.detail || msg;
    } catch {
      // ignore
    }
    throw new Error(msg);
  }
  return resp.json();
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderStats(stats) {
  const cards = document.getElementById("statsCards");
  const topTags = document.getElementById("topTags");
  const byCategory = document.getElementById("byCategory");

  if (cards) {
    cards.innerHTML = [
      { k: "Всего фото", v: stats.total_photos },
      { k: "Пользователей", v: stats.total_users },
      { k: "Категорий", v: stats.total_categories },
      { k: "Тегов", v: stats.total_tags },
    ]
      .map((x) => `<div class="stat-card"><div class="muted small">${escapeHtml(x.k)}</div><div class="stat-value">${escapeHtml(x.v)}</div></div>`)
      .join("");
  }

  if (byCategory) {
    const items = (stats.by_category || [])
      .slice(0, 10)
      .map((x) => `<div class="small">${escapeHtml(x.category)}: <b>${escapeHtml(x.count)}</b></div>`)
      .join("");
    byCategory.innerHTML = items || "—";
  }

  if (topTags) {
    const items = (window.__topTagsCache || [])
      .slice(0, 15)
      .map((x) => `<div class="small">${escapeHtml(x.name)}: <b>${escapeHtml(x.count)}</b></div>`)
      .join("");
    topTags.innerHTML = items || "—";
  }
}

async function loadAll() {
  const access = getAuthToken();
  if (!access) {
    window.location.href = "/login/";
    return;
  }

  // Проверка роли по cached auth (быстрее, чем отдельный endpoint).
  const cached = (() => {
    try {
      return JSON.parse(localStorage.getItem("photoAuth") || "{}");
    } catch {
      return {};
    }
  })();
  if (cached?.user?.role !== "admin") {
    alert("Нет прав администратора.");
    window.location.href = "/";
    return;
  }

  const summary = await authedGet(`${apiBase}/reports/summary/?page_size=24`);
  window.__topTagsCache = (await authedGet(`${apiBase}/reports/top-tags/?limit=50`)).items || [];

  renderStats(summary);

  const usersResp = await authedGet(`${apiBase}/admin/users/?page_size=2000`);
  const usersList = document.getElementById("usersList");
  usersList.innerHTML =
    (usersResp || [])
      .map((u) => `<div class="small">${escapeHtml(u.email)} — ${escapeHtml(u.role)}</div>`)
      .join("") || "—";

  document.getElementById("btnLogoutAdmin").style.display = "";
}

function bindCreateForms() {
  const catForm = document.getElementById("categoryCreateForm");
  const tagForm = document.getElementById("tagCreateForm");

  catForm.onsubmit = async (e) => {
    e.preventDefault();
    const err = document.getElementById("catCreateError");
    err.textContent = "";
    try {
      await authedPost(`${apiBase}/categories/create/`, {
        name: document.getElementById("catName").value,
        slug: document.getElementById("catSlug").value,
      });
      document.getElementById("catName").value = "";
      document.getElementById("catSlug").value = "";
      await loadAll();
    } catch (ex) {
      err.textContent = ex.message || String(ex);
    }
  };

  tagForm.onsubmit = async (e) => {
    e.preventDefault();
    const err = document.getElementById("tagCreateError");
    err.textContent = "";
    try {
      await authedPost(`${apiBase}/tags/create/`, { name: document.getElementById("tagName").value });
      document.getElementById("tagName").value = "";
      await loadAll();
    } catch (ex) {
      err.textContent = ex.message || String(ex);
    }
  };
}

bindCreateForms();
loadAll().catch((e) => alert(e.message || String(e)));

