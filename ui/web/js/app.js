/**
 * app.js — роутер и точка входа.
 *
 * Новый поток:
 *   1. pywebview готов
 *   2. Восстанавливаем сессию
 *   3. Если нет сессии — логин
 *   4. Проверка/скачивание происходит только после авторизации (по нажатию Play)
 */

const App = (() => {
  let _started = false;

  // ── Страницы ────────────────────────────────────────────────────────────────
  const pages = {
    update:   document.getElementById('page-update'),
    login:    document.getElementById('page-login'),
    download: document.getElementById('page-download'),
    main:     document.getElementById('page-main'),
  };

  function showPage(name) {
    Object.entries(pages).forEach(([key, el]) => {
      el.hidden = key !== name;
    });
  }

  // ── Переходы ────────────────────────────────────────────────────────────────
  function showLogin(lastLogin = '') {
    showPage('login');
    LoginPage.init(lastLogin);
  }

  /**
   * Переход на экран загрузки.
   * @param {object}  [opts]
   * @param {string}  [opts.subtitle]
   * @param {boolean} [opts.autoStart]
   * @param {string}  [opts.buildId]
   * @param {function}[opts.onDone]
   * @param {function}[opts.onCancel]
   */
  function showDownload({ subtitle, autoStart = false, buildId = null, onDone = null, onCancel = null } = {}) {
    showPage('download');
    DownloadPage.init({
      subtitle,
      autoStart,
      buildId,
      onDone:   onDone || _onDownloadDone,
      onCancel: onCancel,
    });
  }

  /** Возвращает на главный экран (используется после отмены операции). */
  async function restoreMain() {
    try {
      const user = await API.getCurrentUser();
      if (user.logged_in) {
        await showMain(user.username);
        return;
      }
      showLogin(user.last_login || '');
      return;
    } catch (e) {}
    showLogin();
  }

  /**
   * Показывает стилизованный диалог подтверждения.
   * Возвращает Promise<boolean>.
   */
  function showConfirm(message) {
    return new Promise(resolve => {
      const overlay   = document.getElementById('modal-confirm');
      const msgEl     = document.getElementById('modal-message');
      const okBtn     = document.getElementById('modal-ok-btn');
      const cancelBtn = document.getElementById('modal-cancel-btn');

      msgEl.textContent = message;
      overlay.hidden = false;

      function cleanup() {
        overlay.hidden = true;
        okBtn.onclick     = null;
        cancelBtn.onclick = null;
      }

      okBtn.onclick     = () => { cleanup(); resolve(true);  };
      cancelBtn.onclick = () => { cleanup(); resolve(false); };
    });
  }

  async function showMain(username) {
    showPage('main');
    await MainPage.init(username);
  }

  // ── Выход ───────────────────────────────────────────────────────────────────
  async function logout() {
    await API.logout();
    showLogin();
  }

  // ── Колбэк завершения игры (вызывается из Python через evaluate_js) ─────────
  function onGameExit(rc) {
    MainPage.onGameExit(rc);
  }

  // ── После успешной загрузки игры ────────────────────────────────────────────
  async function _onDownloadDone() {
    try {
      const user = await API.getCurrentUser();
      if (user.logged_in) {
        await showMain(user.username);
        return;
      }
      showLogin(user.last_login || '');
      return;
    } catch (e) {}
    showLogin();
  }

  // ── Старт ───────────────────────────────────────────────────────────────────
  async function init() {
    if (_started) return;
    _started = true;

    document.getElementById('btn-logout').onclick = logout;

    // 1. Проверяем обновление ДО любого интерфейса.
    // Если есть обновление — процесс завершится сам (os._exit).
    // Если обновлений нет — резолвится и идём дальше.
    await Updater.checkAndApply();

    // 2. Восстановление сессии / логин
    try {
      const user = await API.getCurrentUser();
      if (user.logged_in) {
        await showMain(user.username);
        return;
      }
      showLogin(user.last_login || '');
      return;
    } catch (e) {
      console.warn('[app] Ошибка восстановления сессии:', e);
    }

    showLogin();
  }

  window.addEventListener('pywebviewready', init, { once: true });
  if (window.pywebview && window.pywebview.api) init();

  return { showLogin, showDownload, showMain, onGameExit, restoreMain, showConfirm };
})();
