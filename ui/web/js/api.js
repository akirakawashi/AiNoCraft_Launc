/**
 * Thin wrapper around window.pywebview.api (the Python bridge).
 */

const API = (() => {
  let currentUserRequest = null;

  function ready() {
    return new Promise((resolve) => {
      if (window.pywebview && window.pywebview.api) {
        resolve();
      } else {
        window.addEventListener('pywebviewready', resolve, { once: true });
      }
    });
  }

  async function call(method, ...args) {
    await ready();
    return window.pywebview.api[method](...args);
  }

  function getCurrentUser() {
    if (!currentUserRequest) {
      currentUserRequest = call('get_current_user').finally(() => {
        currentUserRequest = null;
      });
    }
    return currentUserRequest;
  }

  return {
    ready,
    warmup: () => call('warmup'),
    getAppState: () => call('get_app_state'),

    login: (username, password) => call('login', username, password),
    logout: () => call('logout'),
    getCurrentUser,
    openExternalUrl: (url) => call('open_external_url', url),

    minimizeWindow: () => call('minimize_window'),
    closeWindow: () => call('close_window'),
    moveWindowDelta: (dx, dy) => call('move_window_delta', dx, dy),

    getBuilds: () => call('get_builds'),
    selectBuild: (buildId) => call('select_build', buildId),
    getSelectedBuild: () => call('get_selected_build'),

    getSettings: (buildId = null) => call('get_settings', buildId),
    saveSettings: (data, buildId = null) => call('save_settings', data, buildId),

    launchGame: (buildId = null) => call('launch_game', buildId),
    getGameStatus: () => call('get_game_status'),

    checkGameInstalled: (buildId = null) => call('check_game_installed', buildId),
    startDownload: (buildId = null) => call('start_download', buildId),
    cancelDownload: () => call('cancel_download'),
    getDownloadProgress: () => call('get_download_progress'),
    deleteBuildFiles: (buildId = null) => call('delete_build_files', buildId),

    checkLauncherUpdate: () => call('check_launcher_update'),
    startLauncherUpdate: () => call('start_launcher_update'),
    getLauncherUpdateProgress: () => call('get_launcher_update_progress'),
  };
})();
