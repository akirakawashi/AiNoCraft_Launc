/**
 * login.js — логика экрана авторизации.
 * Вызов App.showMain() происходит после успешного логина.
 */

const LoginPage = (() => {

  // ── DOM-ссылки ──────────────────────────────────────────────────────────────
  const form        = () => document.getElementById('login-form');
  const inputUser   = () => document.getElementById('login-username');
  const inputPass   = () => document.getElementById('login-password');
  const errorBox    = () => document.getElementById('login-error');
  const errorText   = () => document.getElementById('login-error-text');
  const btnLogin    = () => document.getElementById('btn-login');
  const btnText     = () => document.getElementById('btn-login-text');
  const btnSpinner  = () => document.getElementById('btn-login-spinner');
  const btnTogglePw = () => document.getElementById('btn-toggle-pw');
  const btnForgot   = () => document.getElementById('btn-forgot-password');
  const btnRegister = () => document.getElementById('btn-register');

  const RESET_PASSWORD_URL = 'https://ainocraft.com/reset-password';
  const REGISTER_URL = 'https://ainocraft.com/register';

  let _bound = false;

  // Преобразование типичных серверных сообщений об ошибке в удобочитаемые русские строки
  const ERROR_TRANSLATIONS = {
    'Invalid credentials. Invalid username or password.': 'Неверный логин или пароль',
    'Invalid credentials.': 'Неверный логин или пароль',
    'Invalid username or password.': 'Неверный логин или пароль',
    'HTTP 401': 'Неверный логин или пароль',
    'Не удалось открыть ссылку': 'Не удалось открыть ссылку',
  };

  function translateError(msg) {
    if (!msg) return '';
    const s = String(msg).trim();
    if (ERROR_TRANSLATIONS[s]) return ERROR_TRANSLATIONS[s];
    const lower = s.toLowerCase();
    for (const key of Object.keys(ERROR_TRANSLATIONS)) {
      if (lower.includes(key.toLowerCase())) return ERROR_TRANSLATIONS[key];
    }
    if (/[А-Яа-яЁё]/.test(s)) return s;
    if (/invalid|unauthoriz|credentials|password|username/i.test(s)) {
      return 'Неверный логин или пароль';
    }
    return s;
  }

  // ── Состояние UI ────────────────────────────────────────────────────────────
  function setLoading(on) {
    btnLogin().disabled   = on;
    btnText().textContent = on ? 'Входим...' : 'Войти';
    btnSpinner().hidden   = !on;
  }

  function showError(msg) {
    errorText().textContent = translateError(msg);
    errorBox().hidden       = false;
  }

  function clearError() {
    errorBox().hidden = true;
  }

  // ── Обработчики ─────────────────────────────────────────────────────────────
  async function handleSubmit(e) {
    e.preventDefault();
    clearError();

    const username = inputUser().value.trim();
    const password = inputPass().value;

    if (!username || !password) {
      showError('Заполни оба поля');
      return;
    }

    setLoading(true);
    try {
      const result = await API.login(username, password);
      if (result.success) {
        App.showMain(result.username);
      } else {
        showError(result.error || 'Неверный логин или пароль');
        inputPass().value = '';
        inputPass().focus();
      }
    } catch (err) {
      showError('Ошибка соединения с бэкендом');
      console.error('[login] API error:', err);
    } finally {
      setLoading(false);
    }
  }

  function togglePassword() {
    const field  = inputPass();
    const isText = field.type === 'text';
    field.type   = isText ? 'password' : 'text';
  }

  async function openExternal(url) {
    try {
      const result = await API.openExternalUrl(url);
      if (!result || !result.success) {
        showError(result?.error || 'Не удалось открыть ссылку');
      }
    } catch (err) {
      showError('Не удалось открыть браузер');
      console.error('[login] openExternal error:', err);
    }
  }

  // ── Инициализация ───────────────────────────────────────────────────────────
  function init(lastLogin = '') {
    if (!_bound) {
      form().onsubmit = handleSubmit;

      // Enter в полях тоже сабмитит
      [inputUser(), inputPass()].forEach((el) => {
        el.onkeydown = (e) => {
          if (e.key === 'Enter') {
            form().requestSubmit();
          }
        };
      });

      btnTogglePw().onclick = togglePassword;
      btnForgot().onclick = () => openExternal(RESET_PASSWORD_URL);
      btnRegister().onclick = () => openExternal(REGISTER_URL);
      _bound = true;
    }

    // Сброс визуального состояния при каждом открытии страницы
    clearError();
    setLoading(false);
    inputPass().value = '';
    if (lastLogin) {
      inputUser().value = String(lastLogin);
    }
    inputUser().focus();
  }

  return { init };
})();
