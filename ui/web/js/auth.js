/**
 * Auth gate: login screen, session restore, logout, profile rendering.
 */

const AuthGate = (() => {
  const el = {
    startup: () => document.getElementById('startup-loader'),
    screen: () => document.getElementById('login-screen'),
    form: () => document.getElementById('login-form'),
    username: () => document.getElementById('login-username'),
    password: () => document.getElementById('login-password'),
    error: () => document.getElementById('login-error'),
    submit: () => document.getElementById('login-submit'),
    togglePassword: () => document.getElementById('login-toggle-password'),
    forgot: () => document.getElementById('login-forgot'),
    createAccount: () => document.getElementById('login-create-account'),
    logout: () => document.getElementById('btn-logout'),
    profileName: () => document.getElementById('main-username'),
    profileRole: () => document.getElementById('main-role'),
    profileNode: () => document.querySelector('.player-profile'),
    avatar: () => document.getElementById('main-avatar'),
    avatarFallback: () => document.getElementById('main-avatar-fallback'),
  };

  const RESET_PASSWORD_URL = 'https://ainocraft.com/reset-password';
  const REGISTER_URL = 'https://ainocraft.com/register';
  const MIN_STARTUP_LOADER_MS = 2000;

  const ERROR_TRANSLATIONS = {
    'Invalid credentials. Invalid username or password.': 'Неверный логин или пароль',
    'Invalid credentials.': 'Неверный логин или пароль',
    'Invalid username or password.': 'Неверный логин или пароль',
    'HTTP 401': 'Неверный логин или пароль',
  };

  const protectedSelectors = [
    { selector: '.side-nav', hiddenWhenUnlocked: false },
    { selector: '.settings-side-blur', hiddenWhenUnlocked: true },
    { selector: '.hero', hiddenWhenUnlocked: false },
    { selector: '#settings-panel', hiddenWhenUnlocked: true },
    { selector: '#builds-panel', hiddenWhenUnlocked: true },
  ];

  let submitting = false;
  let startupShownAt = 0;

  function showStartup() {
    startupShownAt = performance.now();
    document.body.classList.add('startup-loading', 'auth-locked');
    const startup = el.startup();
    startup.hidden = false;
    startup.removeAttribute('aria-hidden');
    startup.removeAttribute('inert');
    el.screen().setAttribute('aria-hidden', 'true');
    el.screen().setAttribute('inert', '');
    setProtectedInert(true);
  }

  function waitForStartupMinimum() {
    const elapsed = performance.now() - startupShownAt;
    const remaining = Math.max(0, MIN_STARTUP_LOADER_MS - elapsed);
    return new Promise((resolve) => window.setTimeout(resolve, remaining));
  }

  function finishStartup() {
    const startup = el.startup();
    document.body.classList.remove('startup-loading');
    startup.setAttribute('aria-hidden', 'true');
    startup.setAttribute('inert', '');
    window.setTimeout(() => {
      if (!document.body.classList.contains('startup-loading')) startup.hidden = true;
    }, 320);
  }

  function translateError(message) {
    if (!message) return '';
    const text = String(message).trim();
    if (ERROR_TRANSLATIONS[text]) return ERROR_TRANSLATIONS[text];
    const lower = text.toLowerCase();
    for (const key of Object.keys(ERROR_TRANSLATIONS)) {
      if (lower.includes(key.toLowerCase())) return ERROR_TRANSLATIONS[key];
    }
    if (/[А-Яа-яЁё]/.test(text)) return text;
    if (/invalid|unauthoriz|credentials|password|username/i.test(text)) {
      return 'Неверный логин или пароль';
    }
    return text;
  }

  function showError(message) {
    el.error().textContent = translateError(message) || 'Ошибка авторизации';
    el.error().hidden = false;
  }

  function clearError() {
    el.error().hidden = true;
  }

  function setLoading(on) {
    submitting = on;
    el.submit().disabled = on;
    el.submit().querySelector('span').textContent = on ? 'Входим...' : 'Войти';
  }

  function setProtectedInert(locked) {
    protectedSelectors.forEach(({ selector, hiddenWhenUnlocked }) => {
      const node = document.querySelector(selector);
      if (!node) return;
      const hidden = locked || hiddenWhenUnlocked;
      node.toggleAttribute('inert', hidden);
      node.setAttribute('aria-hidden', String(hidden));
    });
  }

  function closeSidePanels() {
    document.querySelectorAll('.settings-panel').forEach((panel) => {
      panel.classList.remove('settings-panel--open', 'settings-panel--has-above', 'settings-panel--has-below');
      panel.setAttribute('aria-hidden', 'true');
      panel.setAttribute('inert', '');
    });
  }

  function roleSuffix(role) {
    return String(role || '').toLowerCase().replace(/[^a-z0-9_-]/g, '') || 'default';
  }

  function normalizedRingColor(value) {
    const candidate = String(value || '').trim().toLowerCase();
    return /^#[0-9a-f]{6}$/.test(candidate) ? candidate : '';
  }

  function applyRingColor(node, color) {
    if (!node) return;
    const propertyNames = ['--profile-role-color', '--profile-role-color-rgb', '--profile-role-border'];
    if (!color) {
      propertyNames.forEach((property) => node.style.removeProperty(property));
      return;
    }
    const red = Number.parseInt(color.slice(1, 3), 16);
    const green = Number.parseInt(color.slice(3, 5), 16);
    const blue = Number.parseInt(color.slice(5, 7), 16);
    node.style.setProperty('--profile-role-color', color);
    node.style.setProperty('--profile-role-color-rgb', `${red}, ${green}, ${blue}`);
    node.style.setProperty('--profile-role-border', color);
  }

  function renderProfile(user) {
    const username = String(user.username || 'Player').trim() || 'Player';
    const role = roleSuffix(user.role);
    const roleLabel = String(user.role_label || role).trim() || 'Common';
    const ringColor = normalizedRingColor(user.ring_color);
    const avatarUrl = String(user.avatar_url || '').trim();

    el.profileName().textContent = username;
    const profileRole = el.profileRole();
    profileRole.textContent = roleLabel;
    profileRole.className = `role-badge role-badge--${role}`;
    applyRingColor(profileRole, ringColor);
    const profileNode = el.profileNode();
    if (profileNode) {
      profileNode.className = `side-nav__profile player-profile player-profile--${role}`;
      applyRingColor(profileNode, ringColor);
    }

    const avatar = el.avatar();
    const fallback = el.avatarFallback();
    fallback.textContent = (username.slice(0, 1) || 'A').toUpperCase();

    avatar.onload = () => {
      avatar.hidden = false;
      fallback.hidden = true;
    };
    avatar.onerror = () => {
      avatar.hidden = true;
      fallback.hidden = false;
      avatar.removeAttribute('src');
    };

    avatar.hidden = true;
    fallback.hidden = false;
    if (avatarUrl) {
      avatar.src = avatarUrl;
    } else {
      avatar.removeAttribute('src');
    }
  }

  function showLauncher(user) {
    clearError();
    closeSidePanels();
    renderProfile(user || {});
    document.body.classList.remove('auth-locked', 'settings-open');
    document.body.classList.add('auth-ready');
    el.screen().setAttribute('aria-hidden', 'true');
    el.screen().setAttribute('inert', '');
    setProtectedInert(false);
    Shell.startPostStartupWarmup();
  }

  function showLogin(lastLogin = '') {
    closeSidePanels();
    document.body.classList.add('auth-locked');
    document.body.classList.remove('auth-ready', 'settings-open');
    el.screen().removeAttribute('aria-hidden');
    el.screen().removeAttribute('inert');
    setProtectedInert(true);
    clearError();
    setLoading(false);
    el.password().value = '';
    el.password().type = 'password';
    el.togglePassword().setAttribute('aria-pressed', 'false');
    if (lastLogin) el.username().value = lastLogin;
    requestAnimationFrame(() => el.username().focus());
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (submitting) return;

    const username = el.username().value.trim();
    const password = el.password().value;
    if (!username || !password) {
      showError('Заполните логин и пароль');
      return;
    }

    setLoading(true);
    try {
      const result = await API.login(username, password);
      if (result && result.success) {
        await App.prepare();
        await App.enterMain(result);
        showLauncher(result);
        return;
      }
      showError((result && result.error) || 'Неверный логин или пароль');
      el.password().value = '';
      el.password().focus();
    } catch (err) {
      console.error('[auth] login error:', err);
      showError('Ошибка соединения с сервером');
    } finally {
      setLoading(false);
    }
  }

  async function openExternal(url) {
    try {
      const result = await API.openExternalUrl(url);
      if (!result || !result.success) {
        showError((result && result.error) || 'Не удалось открыть ссылку');
      }
    } catch (err) {
      console.error('[auth] openExternal error:', err);
      showError('Не удалось открыть браузер');
    }
  }

  async function handleLogout() {
    const agree = await Modals.confirm('Выйти из аккаунта?', { title: 'Выход', okLabel: 'Выйти' });
    if (!agree) return;
    try {
      await API.logout();
    } catch (err) {
      console.warn('[auth] logout error:', err);
    }
    showLogin(el.username().value.trim());
  }

  async function restoreSession() {
    // These operations are independent. Starting both here removes the serial
    // network wait without issuing more than one refresh request.
    const appStatePromise = App.prepare();
    let user;
    try {
      user = await API.getCurrentUser();
    } catch (err) {
      console.warn('[auth] session restore failed:', err);
      await waitForStartupMinimum();
      showLogin();
      finishStartup();
      return;
    }

    if (user && user.logged_in) {
      await appStatePromise;
      try {
        await App.enterMain(user);
      } catch (err) {
        console.warn('[auth] launcher preparation failed:', err);
      }
      await waitForStartupMinimum();
      showLauncher(user);
      finishStartup();
      return;
    }

    await waitForStartupMinimum();
    showLogin(user && user.last_login ? String(user.last_login) : '');
    finishStartup();
  }

  function init() {
    el.form().addEventListener('submit', handleSubmit);

    el.togglePassword().addEventListener('click', () => {
      const visible = el.password().type === 'password';
      el.password().type = visible ? 'text' : 'password';
      el.togglePassword().setAttribute('aria-pressed', String(visible));
    });

    [el.username(), el.password()].forEach((field) => {
      field.addEventListener('input', clearError);
    });

    el.forgot().addEventListener('click', () => openExternal(RESET_PASSWORD_URL));
    el.createAccount().addEventListener('click', () => openExternal(REGISTER_URL));
    el.logout().addEventListener('click', handleLogout);

    showStartup();
    // App.init() invokes us while the App module is still being assigned.
    // Defer one microtask so App.prepare() is available before startup begins.
    Promise.resolve().then(restoreSession).catch(async (err) => {
      console.error('[auth] unexpected startup error:', err);
      await waitForStartupMinimum();
      showLogin();
      finishStartup();
    });
  }

  return { init, showLogin, showLauncher };
})();
