/* global fetch, window */

const apiBase = "/api";
const grid = document.getElementById("photosGrid");
const paginationInfo = document.getElementById("paginationInfo");

let state = {
  page: 1,
  pageSize: 24,
  filters: {},
};

function getAuthToken() {
  return window.photoAuth?.getAccessToken?.() || "";
}

async function apiGet(url, params) {
  const qp = new URLSearchParams(params || {});
  const full = qp.toString() ? `${url}?${qp.toString()}` : url;
  const token = getAuthToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  return fetch(full, { headers });
}

async function fetchJson(url, params) {
  const resp = await apiGet(url, params);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

async function fetchCategories() {
  const resp = await fetch(`${apiBase}/categories/?page_size=1000`);
  if (!resp.ok) return [];
  const data = await resp.json();
  // DRF pagination
  return data.results || data;
}

function renderPhotos(photos) {
  grid.innerHTML = "";
  if (!photos || photos.length === 0) {
    grid.innerHTML = `<div class="muted">Ничего не найдено.</div>`;
    return;
  }

  for (const p of photos) {
    const card = document.createElement("div");
    card.className = "photo-card";

    const img = document.createElement("img");
    img.alt = p.original_name;
    img.loading = "lazy";
    img.src = `${apiBase}/photos/${p.id}/file/`;

    const meta = document.createElement("div");
    meta.className = "photo-meta";

    const cat = p.category?.name ? `<div>${escapeHtml(p.category.name)}</div>` : "";
    const tags = (p.tags || []).slice(0, 8).map((t) => escapeHtml(t.name)).join(", ");

    meta.innerHTML = `
      <div class="muted small">${escapeHtml(p.original_name)}</div>
      ${cat ? `<div class="small">${cat}</div>` : ""}
      <div class="small muted">${tags ? `Теги: ${tags}` : ""}</div>
    `;

    card.appendChild(img);
    card.appendChild(meta);
    grid.appendChild(card);
  }
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function buildFiltersFromUI() {
  const q = document.getElementById("qInput").value.trim();
  const category = document.getElementById("categorySelect").value;
  const tags = document.getElementById("tagsInput").value.trim();
  const fileType = document.getElementById("fileTypeSelect").value;
  const sort = document.getElementById("sortSelect").value;
  const pageSize = parseInt(document.getElementById("pageSizeInput").value || "24", 10);

  state.pageSize = Math.min(100, Math.max(1, pageSize));

  const filters = {
    ...(q ? { q } : {}),
    ...(category ? { category } : {}),
    ...(tags ? { tags } : {}),
    ...(fileType ? { file_type: fileType } : {}),
    sort,
    page_size: state.pageSize,
  };

  state.filters = filters;
}

async function search(page = 1) {
  state.page = page;
  buildFiltersFromUI();
  const params = { ...state.filters, page };
  const resp = await fetch(`${apiBase}/photos/?${new URLSearchParams(params).toString()}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  renderPhotos(data.results || []);

  const count = data.count || 0;
  paginationInfo.textContent = `Всего: ${count}, страница: ${page}`;

  document.getElementById("btnPrev").disabled = !data.previous;
  document.getElementById("btnNext").disabled = !data.next;
}

function setDropzone() {
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");
  const pickBtn = document.getElementById("btnPickFiles");

  pickBtn.onclick = () => fileInput.click();

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });
  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
  });
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    const files = e.dataTransfer.files;
    fileInput.files = files;
  });
}

async function uploadOne(file) {
  const token = getAuthToken();
  if (!token) throw new Error("Сначала войдите в аккаунт.");

  const form = new FormData();
  form.append("file", file);
  form.append(
    "category",
    document.getElementById("uploadCategorySelect").value
  );

  form.append("tags", document.getElementById("uploadTagsInput").value || "");

  const resp = await fetch(`${apiBase}/photos/upload/`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`;
    try {
      const err = await resp.json();
      msg = err.detail || msg;
    } catch {
      // ignore
    }
    throw new Error(msg);
  }

  return resp.json();
}

function bindUpload() {
  const uploadForm = document.getElementById("uploadForm");
  const fileInput = document.getElementById("fileInput");
  const statusEl = document.getElementById("uploadStatus");

  uploadForm.onsubmit = async (e) => {
    e.preventDefault();
    statusEl.textContent = "";

    const files = fileInput.files;
    if (!files || files.length === 0) {
      statusEl.textContent = "Выберите файлы для загрузки.";
      return;
    }

    const list = Array.from(files);
    for (const f of list) {
      statusEl.textContent = `Загрузка: ${f.name}...`;
      try {
        await uploadOne(f);
      } catch (err) {
        statusEl.textContent = `Ошибка: ${err.message || String(err)}`;
        return;
      }
    }

    statusEl.textContent = "Готово. Обновляю список...";
    await search(state.page);
  };
}

async function init() {
  setDropzone();
  bindUpload();

  try {
    const cats = await fetchCategories();
    const categorySelect = document.getElementById("categorySelect");
    const uploadCategorySelect = document.getElementById("uploadCategorySelect");
    for (const c of cats) {
      const opt = document.createElement("option");
      opt.value = c.slug || c.name || "";
      opt.textContent = c.name;
      categorySelect.appendChild(opt);

      const opt2 = document.createElement("option");
      opt2.value = c.slug || c.name || "";
      opt2.textContent = c.name;
      uploadCategorySelect.appendChild(opt2);
    }
  } catch {
    // ignore
  }

  document.getElementById("btnSearch").onclick = async () => {
    try {
      await search(1);
    } catch (err) {
      alert(err.message || String(err));
    }
  };

  document.getElementById("btnPrev").onclick = async () => {
    if (state.page > 1) search(state.page - 1).catch((e) => alert(e.message || String(e)));
  };
  document.getElementById("btnNext").onclick = async () => {
    search(state.page + 1).catch((e) => alert(e.message || String(e)));
  };

  await search(1);
}

init();

