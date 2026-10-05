/**
 * Application state and startup orchestration.
 */

const App = (() => {
  const state = {
    builds: [],
    selectedBuildId: null,
    ramMin: 2,
    ramMax: 16,
    ramDefault: 6,
    launcherVersion: '',
    mode: 'prod',
    dev: false,
    features: { news_enabled: false },
    news: [],
    webBaseUrl: '',
    backendAvailable: false,
    loaded: false,
  };
  let stateLoadPromise = null;

  function applyAppState(payload) {
    state.builds = Array.isArray(payload.builds) ? payload.builds : [];
    state.selectedBuildId = payload.selected_build_id || (state.builds[0] && state.builds[0].id) || null;
    state.ramMin = payload.ram_min_gb || state.ramMin;
    state.ramMax = payload.ram_max_gb || state.ramMax;
    state.ramDefault = payload.ram_default_gb || state.ramDefault;
    state.launcherVersion = payload.launcher_version || '';
    state.mode = payload.mode || 'prod';
    state.dev = Boolean(payload.dev);
    state.backendAvailable = Boolean(payload.backend_available);
    if (payload.features && typeof payload.features === 'object') {
      state.features = payload.features;
    }
    state.news = Array.isArray(payload.news) ? payload.news : [];
    state.webBaseUrl = payload.web_base_url || '';
  }

  function renderAll() {
    Shell.setNewsVisible(Boolean(state.features.news_enabled));
    Home.render();
    Builds.render();
    Settings.render();
    News.render(state.news);
  }

  function prepare() {
    if (state.loaded) return Promise.resolve(true);
    if (stateLoadPromise) return stateLoadPromise;

    stateLoadPromise = (async () => {
      try {
        const payload = await API.getAppState();
        applyAppState(payload || {});
        return true;
      } catch (err) {
        console.error('[app] app state load failed:', err);
        return false;
      } finally {
        // The startup attempt is complete even when the backend is unavailable;
        // the launcher can still render its local fallback state.
        state.loaded = true;
        stateLoadPromise = null;
      }
    })();

    return stateLoadPromise;
  }

  async function enterMain() {
    if (!state.loaded) {
      Modals.showLoading('Загрузка данных...');
      try {
        await prepare();
      } finally {
        Modals.hide();
      }
    }
    renderAll();
  }

  async function refreshBuilds() {
    try {
      const result = await API.getBuilds();
      if (result && result.success) {
        state.builds = result.builds || [];
        state.selectedBuildId = result.selected_build_id || state.selectedBuildId;
      }
    } catch (err) {
      console.warn('[app] builds refresh failed:', err);
    }
    renderAll();
  }

  async function selectBuild(buildId) {
    try {
      const result = await API.selectBuild(buildId);
      if (!result || !result.success) {
        await Modals.alert((result && result.error) || 'Не удалось выбрать сборку', { title: 'Сборки' });
        return;
      }
      state.selectedBuildId = result.selected_build_id;
      await refreshBuilds();
    } catch (err) {
      console.error('[app] select build failed:', err);
    }
  }

  function formatMb(value) {
    return (value || 0).toFixed(1);
  }

  function pollDownloadFinish() {
    return new Promise((resolve) => {
      const timer = setInterval(async () => {
        let status;
        try {
          status = await API.getDownloadProgress();
        } catch (err) {
          clearInterval(timer);
          resolve({ done: false, error: String(err) });
          return;
        }

        const pct = (status.percent || 0).toFixed(1);
        if (status.state === 'extracting') {
          Modals.updateProgress({ status: 'Распаковка файлов...', percent: pct, speed: '-', size: '' });
        } else {
          Modals.updateProgress({
            status: 'Загрузка файлов...',
            percent: pct,
            speed: `${formatMb(status.speed_mb)} МБ/с`,
            size: `${formatMb(status.downloaded_mb)} / ${formatMb(status.total_mb)} МБ`,
          });
        }

        if (!status.active) {
          clearInterval(timer);
          if (status.state === 'done') {
            resolve({ done: true });
          } else if (status.state === 'cancelled') {
            resolve({ done: false, cancelled: true });
          } else {
            resolve({ done: false, error: status.error || 'Неизвестная ошибка загрузки' });
          }
        }
      }, 400);
    });
  }

  /**
   * Start a build download and poll progress into the shared progress modal.
   * Resolves true when the download and extraction finished successfully.
   */
  async function runDownload(buildId, title) {
    Modals.showProgress(title, () => {
      API.cancelDownload().catch((err) => console.warn('[app] cancel failed:', err));
    });

    let started;
    try {
      started = await API.startDownload(buildId);
    } catch (err) {
      console.error('[app] download start failed:', err);
      started = null;
    }
    if (!started || !started.success) {
      Modals.hide();
      await Modals.alert((started && started.error) || 'Не удалось начать загрузку', { title: 'Ошибка загрузки' });
      return false;
    }

    const result = await pollDownloadFinish();
    Modals.hide();
    if (result.error) {
      await Modals.alert(result.error, { title: 'Ошибка загрузки' });
    }
    return Boolean(result.done);
  }

  function init() {
    Shell.init();
    Home.init();
    Settings.init();
    AuthGate.init();
  }

  // Scripts load at the end of <body>, so the DOM is ready; bridge-dependent
  // calls await the pywebviewready event internally through API.ready().
  init();

  return { state, prepare, enterMain, refreshBuilds, selectBuild, runDownload };
})();
