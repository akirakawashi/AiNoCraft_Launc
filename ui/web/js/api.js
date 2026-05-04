/**
 * api.js — обёртка над window.pywebview.api
 *
 * Все методы возвращают Promise.
 * Ждём готовности pywebview перед первым вызовом (window.pywebviewready).
 */

const API = (() => {
  /** Возвращает Promise который резолвится когда pywebview готов. */
  function ready() {
    return new Promise((resolve) => {
      if (window.pywebview && window.pywebview.api) {
        resolve();
      } else {
        window.addEventListener('pywebviewready', resolve, { once: true });
      }
    });
  }

  /** Универсальный вызов метода Python API. */
  async function call(method, ...args) {
    await ready();
    return window.pywebview.api[method](...args);
  }

  return {
    // Авторизация
    login:          (username, password) => call('login', username, password),
    logout:         ()                   => call('logout'),
    getCurrentUser: ()                   => call('get_current_user'),
    openExternalUrl:(url)                => call('open_external_url', url),

    // Сборки/серверы
    getBuilds:        ()           => call('get_builds'),
    selectBuild:      (buildId)    => call('select_build', buildId),
    getSelectedBuild: ()           => call('get_selected_build'),

    // Настройки
    getSettings:    (buildId = null)         => call('get_settings', buildId),
    saveSettings:   (data, buildId = null)   => call('save_settings', data, buildId),
    getRuntimeConfig: ()                      => call('get_runtime_config'),

    // Игра
    launchGame:     (buildId = null) => call('launch_game', buildId),
    getGameStatus:  ()                => call('get_game_status'),

    // Установка / загрузка
    checkGameInstalled:  (buildId = null) => call('check_game_installed', buildId),
    startDownload:       (buildId = null) => call('start_download', buildId),
    cancelDownload:      ()               => call('cancel_download'),
    getDownloadProgress: ()               => call('get_download_progress'),

    // Обновление лаунчера
    checkLauncherUpdate:        ()              => call('check_launcher_update'),
    startLauncherUpdate:        (downloadUrl, sha256 = null) => call('start_launcher_update', downloadUrl, sha256),
    getLauncherUpdateProgress:  ()              => call('get_launcher_update_progress'),
  };
})();

