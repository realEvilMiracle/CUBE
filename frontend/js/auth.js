/* global fetch, window */

const AUTH_KEY = "photoAuth";

function getAuth() {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function setAuth(auth) {
  localStorage.setItem(AUTH_KEY, JSON.stringify(auth));
}

function clearAuth() {
  localStorage.removeItem(AUTH_KEY);
}

function getAccessToken() {
  const auth = getAuth();
  return auth?.access || "";
}

function setNavState() {
  const navLogin = document.getElementById("navLogin");
  const navAdmin = document.getElementById("navAdmin");
  const btnLogout = document.getElementById("btnLogout");
  const btnLogoutAdmin = document.getElementById("btnLogoutAdmin");

  const auth = getAuth();
  const isLoggedIn = !!auth?.access;
  const role = auth?.user?.role || "";

  if (navLogin) navLogin.style.display = isLoggedIn ? "none" : "";
  if (btnLogout) btnLogout.style.display = isLoggedIn ? "" : "none";
  if (btnLogoutAdmin) btnLogoutAdmin.style.display = isLoggedIn ? "" : "none";
  if (navAdmin) navAdmin.style.display = role === "admin" ? "" : "none";

  if (btnLogout) {
    btnLogout.onclick = () => {
      clearAuth();
      window.location.reload();
    };
  }
  if (btnLogoutAdmin) {
    btnLogoutAdmin.onclick = () => {
      clearAuth();
      window.location.href = "/";
    };
  }
}

async function postJson(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let err = "Ошибка запроса";
    try {
      const data = await resp.json();
      err = data.detail || data.error || err;
    } catch {
      // ignore
    }
    throw new Error(err);
  }
  return resp.json();
}

async function handleLogin({ email, password }) {
  const data = await postJson("/api/auth/login/", { email, password });
  setAuth(data);
  return data;
}

async function handleRegister({ email, password }) {
  const data = await postJson("/api/auth/register/", { email, password });
  // При успехе просто переключаем на форму входа.
  return data;
}

function bindLoginPage() {
  const page = window.__PAGE__ || "";
  if (page !== "login") return;

  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");
  const loginError = document.getElementById("loginError");
  const registerError = document.getElementById("registerError");

  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");

  const regEmailInput = document.getElementById("regEmail");
  const regPasswordInput = document.getElementById("regPassword");

  document.getElementById("btnGoRegister").onclick = (e) => {
    e.preventDefault();
    loginForm.style.display = "none";
    registerForm.style.display = "";
  };
  document.getElementById("btnGoLogin").onclick = (e) => {
    e.preventDefault();
    registerForm.style.display = "none";
    loginForm.style.display = "";
  };

  loginForm.onsubmit = async (e) => {
    e.preventDefault();
    loginError.textContent = "";
    try {
      await handleLogin({ email: emailInput.value, password: passwordInput.value });
      window.location.href = "/";
    } catch (err) {
      loginError.textContent = err.message || String(err);
    }
  };

  registerForm.onsubmit = async (e) => {
    e.preventDefault();
    registerError.textContent = "";
    try {
      await handleRegister({ email: regEmailInput.value, password: regPasswordInput.value });
      // После регистрации показываем форму логина.
      registerForm.style.display = "none";
      loginForm.style.display = "";
    } catch (err) {
      registerError.textContent = err.message || String(err);
    }
  };
}

setNavState();
bindLoginPage();

// Экспорт для app/admin скриптов.
window.photoAuth = { getAccessToken };

