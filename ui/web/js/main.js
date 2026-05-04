/**
 * main.js — логика главного экрана:
 * - выбор сборки/сервера
 * - запуск игры
 * - загрузка файлов по кнопке Play (если отсутствуют)
 * - RAM на каждую сборку
 */

const MainPage = (() => {

  // ── DOM-ссылки ──────────────────────────────────────────────────────────────
  const el = {
    username:        () => document.getElementById('main-username'),
    buildList:       () => document.getElementById('build-list'),
    badgeText:       () => document.getElementById('server-badge-text'),

    ramSlider:       () => document.getElementById('ram-slider'),
    ramDisplay:      () => document.getElementById('ram-display'),

    btnPlay:         () => document.getElementById('btn-play'),
    playLabel:       () => document.getElementById('play-label'),
    btnIntegrity:    () => document.getElementById('btn-check-integrity'),

    statusText:      () => document.getElementById('status-text'),
    statusWrap:      () => document.getElementById('status-indicator'),

    dlOverlay:       () => document.getElementById('modal-download'),
    dlTitle:         () => document.getElementById('modal-download-title'),
    dlStatus:        () => document.getElementById('modal-download-status'),
    dlBar:           () => document.getElementById('modal-download-bar'),
    dlPercent:       () => document.getElementById('modal-download-percent'),
    dlSpeed:         () => document.getElementById('modal-download-speed'),
    dlSize:          () => document.getElementById('modal-download-size'),
    btnCancelDl:     () => document.getElementById('btn-modal-cancel-download'),
  };

  // ── Состояние ───────────────────────────────────────────────────────────────
  let _saveTimer = null;
  let _builds = [];
  let _selectedBuildId = null;
  let _selectedBuildName = '';
  let _selectedBuildInstalled = null;
  let _selectBuildSeq = 0;
  let _buildProbeSeq = 0;
  let _busy = false;
  let _runtime = {
    ramMin: 1,
    ramMax: 16,
    ramDefault: 2,
  };

  // ── Статусы ─────────────────────────────────────────────────────────────────
  const STATUS = {
    idle:    { cls: 'status-indicator--idle',    text: 'Готов к запуску' },
    busy:    { cls: 'status-indicator--running', text: 'Подготовка файлов' },
    running: { cls: 'status-indicator--running', text: 'Игра запущена' },
    error:   { cls: 'status-indicator--error',   text: 'Ошибка запуска' },
    ok:      { cls: 'status-indicator--ok',      text: 'Игра закрыта нормально' },
    filesReady:   { cls: 'status-indicator--ok',   text: 'Файлы готовы' },
    needDownload: { cls: 'status-indicator--idle', text: 'Сборка не установлена, требуется загрузка' },
  };

  function setStatus(key, extra = '') {
    const s = STATUS[key] || STATUS.idle;
    const wrap = el.statusWrap();
    wrap.className = `status-indicator ${s.cls}`;
    el.statusText().textContent = extra ? `${s.text} — ${extra}` : s.text;
  }

  function defaultPlayLabel() {
    if (_selectedBuildInstalled === false) return 'Скачать и установить';
    return 'Нажми чтобы играть';
  }

  function setPlayState(disabled, labelText) {
    el.btnPlay().disabled = disabled;
    el.playLabel().textContent = labelText || (disabled ? 'Подготовка...' : defaultPlayLabel());
  }

  function setBadgeState(variant, text) {
    const wrap = document.getElementById('server-badge');
    if (!wrap) return;
    wrap.classList.remove('status-badge--ok', 'status-badge--warn', 'status-badge--busy');
    wrap.classList.add(`status-badge--${variant}`);
    el.badgeText().textContent = text;
  }

  function setBuildBadge(variant, stateText = '') {
    if (!_selectedBuildName) {
      setBadgeState('ok', 'Сборка не выбрана');
      return;
    }

    const base = `Сборка: ${_selectedBuildName}`;
    const text = stateText ? `${base} · ${stateText}` : base;
    setBadgeState(variant, text);
  }
  function setBuildControlsDisabled(disabled) {
    const buttons = el.buildList().querySelectorAll('.build-item');
    buttons.forEach((btn) => {
      btn.disabled = disabled;
    });
    el.btnIntegrity().disabled = disabled;
  }

  function updateHeaderBuildName() {
    setBuildBadge('ok');
  }

  async function probeSelectedBuildState() {
    if (!_selectedBuildId) return;

    const buildId = _selectedBuildId;
    const buildName = _selectedBuildName;
    const probeSeq = ++_buildProbeSeq;

    _selectedBuildInstalled = null;
    setPlayState(true, 'Проверка файлов...');
    setBuildBadge('busy', 'проверка файлов');
    setStatus('busy', `Проверяю файлы ${buildName}...`);

    try {
      const check = await API.checkGameInstalled(buildId);
      if (probeSeq !== _buildProbeSeq || buildId !== _selectedBuildId) return;

      if (!check.success) {
        _selectedBuildInstalled = null;
        setBuildBadge('warn', 'ошибка проверки');
        setPlayState(false);
        setStatus('error', check.error || 'Ошибка проверки файлов');
        return;
      }

      if (check.installed) {
        _selectedBuildInstalled = true;
        setBuildBadge('ok', 'готова');
        setPlayState(false);
        setStatus('filesReady');
        return;
      }

      _selectedBuildInstalled = false;
      setBuildBadge('warn', 'требуется загрузка');
      setPlayState(false);
      setStatus('needDownload');
    } catch (err) {
      if (probeSeq !== _buildProbeSeq || buildId !== _selectedBuildId) return;
      _selectedBuildInstalled = null;
      setBuildBadge('warn', 'ошибка проверки');
      setPlayState(false);
      setStatus('error', String(err));
      console.warn('[main] Ошибка первичной проверки файлов:', err);
    }
  }
  function showDownloadOverlay(title) {
    el.dlTitle().textContent = title || `Загрузка ${_selectedBuildName}`;
    el.dlStatus().textContent = 'Подключение к серверу...';
    el.dlBar().style.width = '0%';
    el.dlPercent().textContent = '0.0%';
    el.dlSpeed().textContent = '—';
    el.dlSize().textContent = '';
    el.btnCancelDl().disabled = false;
    el.dlOverlay().hidden = false;
  }

  function hideDownloadOverlay() {
    el.dlOverlay().hidden = true;
  }

  async function requestCancelDownload() {
    el.btnCancelDl().disabled = true;
    el.dlStatus().textContent = 'Отмена загрузки...';
    try {
      await API.cancelDownload();
    } catch (err) {
      console.warn('[main] Ошибка отмены загрузки:', err);
    }
  }

  // ── RAM ─────────────────────────────────────────────────────────────────────
  function updateRamDisplay(val) {
    el.ramDisplay().textContent = `${val} ГБ`;
  }

  function onRamChange() {
    const val = parseInt(el.ramSlider().value, 10);
    updateRamDisplay(val);

    // Debounce: сохраняем через 600ms после последнего движения
    clearTimeout(_saveTimer);
    _saveTimer = setTimeout(() => saveRam(val), 600);
  }

  async function saveRam(val) {
    if (!_selectedBuildId) return;

    try {
      await API.saveSettings({ ram: val }, _selectedBuildId);
      console.log('[main] RAM сохранён:', val, _selectedBuildId);
    } catch (err) {
      console.error('[main] Ошибка сохранения RAM:', err);
    }
  }

  async function loadSettings() {
    if (!_selectedBuildId) return;

    try {
      const s = await API.getSettings(_selectedBuildId);
      const raw = parseInt(s.ram, 10);
      const fallback = _runtime.ramDefault;
      const ram = Number.isFinite(raw)
        ? Math.min(_runtime.ramMax, Math.max(_runtime.ramMin, raw))
        : fallback;
      el.ramSlider().value = ram;
      updateRamDisplay(ram);
    } catch (err) {
      console.error('[main] Ошибка загрузки настроек:', err);
    }
  }

  async function loadRuntimeConfig() {
    try {
      const cfg = await API.getRuntimeConfig();
      if (!cfg || cfg.success === false) return;

      const min = parseInt(cfg.ram_min_gb, 10);
      const max = parseInt(cfg.ram_max_gb, 10);
      const def = parseInt(cfg.ram_default_gb, 10);
      if (!Number.isFinite(min) || !Number.isFinite(max) || min > max) return;

      _runtime = {
        ramMin: min,
        ramMax: max,
        ramDefault: Number.isFinite(def) ? Math.min(max, Math.max(min, def)) : min,
      };

      const slider = el.ramSlider();
      slider.min = String(_runtime.ramMin);
      slider.max = String(_runtime.ramMax);
      if (!slider.value) {
        slider.value = String(_runtime.ramDefault);
      }

      const ticks = document.querySelectorAll('.slider-tick');
      if (ticks.length >= 2) {
        ticks[0].textContent = String(_runtime.ramMin);
        ticks[ticks.length - 1].textContent = String(_runtime.ramMax);
      }
    } catch (err) {
      console.warn('[main] Ошибка получения runtime config:', err);
    }
  }

  // ── Сборки/серверы ─────────────────────────────────────────────────────────
  function markSelectedBuild(buildId) {
    const buttons = el.buildList().querySelectorAll('.build-item');
    buttons.forEach((btn) => {
      btn.classList.toggle('build-item--active', btn.dataset.buildId === buildId);
    });
  }

  async function selectBuild(buildId) {
    const selectSeq = ++_selectBuildSeq;

    try {
      const result = await API.selectBuild(buildId);
      if (selectSeq !== _selectBuildSeq) return;
      if (!result.success) {
        setStatus('error', result.error || 'Не удалось выбрать сборку');
        return;
      }

      _selectedBuildId = result.selected_build_id;
      _selectedBuildName = result.build_name;
      markSelectedBuild(_selectedBuildId);
      updateHeaderBuildName();
      await loadSettings();
      if (selectSeq !== _selectBuildSeq) return;
      await probeSelectedBuildState();
    } catch (err) {
      if (selectSeq !== _selectBuildSeq) return;
      setStatus('error', String(err));
      console.error('[main] Ошибка выбора сборки:', err);
    }
  }

  function renderBuildList(builds, selectedBuildId) {
    const container = el.buildList();
    container.innerHTML = '';

    builds.forEach((build, index) => {
      const buildId = String(build.id || '').toLowerCase();
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = `build-item build-item--${buildId}`;
      btn.dataset.buildId = buildId;
      btn.dataset.tip = build.name;
      btn.setAttribute('aria-label', build.name);
      btn.style.animationDelay = `${index * 70}ms`;

      const glyph = document.createElement('span');
      glyph.className = 'build-item__glyph';
      const glyphText = String(build.glyph || '').trim();
      glyph.textContent = glyphText
        ? glyphText.slice(0, 1).toUpperCase()
        : (
            (buildId || '').replace(/[^A-Za-z0-9]/g, '').slice(0, 1).toUpperCase() ||
            (build.name || '?').replace(/[^A-Za-z0-9]/g, '').slice(0, 1).toUpperCase() ||
            '?'
          );
      if (build.accent_color) {
        glyph.style.color = String(build.accent_color);
      }

      btn.appendChild(glyph);
      btn.onclick = () => {
        if (_busy) return;
        selectBuild(buildId);
      };
      container.appendChild(btn);
    });

    markSelectedBuild(selectedBuildId);
  }

  async function loadBuilds() {
    const result = await API.getBuilds();
    if (!result.success || !Array.isArray(result.builds) || result.builds.length === 0) {
      throw new Error(result.error || 'Список сборок пуст');
    }

    _builds = result.builds;
    const selected = result.selected_build_id || _builds[0].id;
    renderBuildList(_builds, selected);
    await selectBuild(selected);
  }

  // ── Загрузка файлов сборки ──────────────────────────────────────────────────
  function waitDownloadFinish() {
    return new Promise((resolve) => {
      const timer = setInterval(async () => {
        try {
          const status = await API.getDownloadProgress();
          const pct = (status.percent || 0).toFixed(1);

          if (status.state === 'downloading') {
            setStatus('busy', `Загрузка ${_selectedBuildName}: ${pct}%`);
            el.dlStatus().textContent = `Загрузка ${_selectedBuildName}...`;
            el.dlSpeed().textContent = `${(status.speed_mb || 0).toFixed(1)} МБ/с`;
            const dl = (status.downloaded_mb || 0).toFixed(1);
            const total = (status.total_mb || 0).toFixed(1);
            el.dlSize().textContent = `${dl} / ${total} МБ`;
          } else if (status.state === 'extracting') {
            setStatus('busy', `Распаковка ${_selectedBuildName}: ${pct}%`);
            el.dlStatus().textContent = `Распаковка ${_selectedBuildName}...`;
            el.dlSpeed().textContent = '—';
            el.dlSize().textContent = '';
          }
          el.dlBar().style.width = `${pct}%`;
          el.dlPercent().textContent = `${pct}%`;

          if (!status.active) {
            clearInterval(timer);
            hideDownloadOverlay();

            if (status.state === 'done') {
              resolve(true);
              return;
            }

            if (status.state === 'cancelled') {
              setStatus('idle', 'Загрузка отменена');
              resolve(false);
              return;
            }

            setStatus('error', status.error || 'Ошибка загрузки');
            resolve(false);
          }
        } catch (err) {
          clearInterval(timer);
          hideDownloadOverlay();
          setStatus('error', String(err));
          resolve(false);
        }
      }, 400);
    });
  }

  async function ensureBuildInstalled() {
    const check = await API.checkGameInstalled(_selectedBuildId);
    if (!check.success) {
      setStatus('error', check.error || 'Ошибка проверки файлов');
      return false;
    }

    if (check.installed) {
      _selectedBuildInstalled = true;
      setBuildBadge('ok', 'готова');
      return true;
    }

    const agree = await App.showConfirm(
      `Сборка ${_selectedBuildName} не установлена.\nСкачать и установить сейчас?`
    );
    if (!agree) {
      _selectedBuildInstalled = false;
      setBuildBadge('warn', 'требуется загрузка');
      setStatus('idle', `Загрузка ${_selectedBuildName} отменена`);
      return false;
    }

    setStatus('busy', `Файлы ${_selectedBuildName} не найдены, начинаю загрузку`);
    showDownloadOverlay(`Загрузка ${_selectedBuildName}`);
    const start = await API.startDownload(_selectedBuildId);
    if (!start.success) {
      hideDownloadOverlay();
      setStatus('error', start.error || 'Не удалось начать загрузку');
      return false;
    }

    const installed = await waitDownloadFinish();
    _selectedBuildInstalled = installed;
    setBuildBadge(installed ? 'ok' : 'warn', installed ? 'готова' : 'требуется загрузка');
    return installed;
  }

  // ── Запуск игры ─────────────────────────────────────────────────────────────
  async function handlePlay() {
    if (_busy) return;
    if (!_selectedBuildId) {
      setStatus('error', 'Сначала выберите сборку');
      return;
    }

    _busy = true;
    setBuildControlsDisabled(true);
    setPlayState(true, 'Проверка файлов...');

    try {
      const installed = await ensureBuildInstalled();
      if (!installed) {
        setPlayState(false);
        setBuildControlsDisabled(false);
        _busy = false;
        return;
      }

      setStatus('busy', `Запускаю ${_selectedBuildName}...`);
      setPlayState(true, 'Запуск игры...');

      const result = await API.launchGame(_selectedBuildId);
      if (result.success) {
        setStatus('running', `PID ${result.pid}`);
        // Окно лаунчера будет закрыто из Python.
        return;
      }

      setStatus('error', result.error || 'Ошибка запуска');
      setPlayState(false);
      setBuildControlsDisabled(false);
      _busy = false;
    } catch (err) {
      setStatus('error', String(err));
      setPlayState(false);
      setBuildControlsDisabled(false);
      _busy = false;
      console.error('[main] API error:', err);
    }
  }

  // ── Проверка целостности ────────────────────────────────────────────────────
  async function handleIntegrityCheck() {
    if (_busy) return;
    if (!_selectedBuildId) {
      setStatus('error', 'Сначала выберите сборку');
      return;
    }

    const ok = await App.showConfirm(
      `Сборка ${_selectedBuildName} будет удалена и загружена заново.\n` +
      'Убедитесь, что игра не запущена.'
    );
    if (!ok) return;

    _busy = true;
    setBuildControlsDisabled(true);
    setPlayState(true, 'Переустановка файлов...');

    try {
      showDownloadOverlay(`Переустановка ${_selectedBuildName}`);
      const start = await API.startDownload(_selectedBuildId);
      if (!start.success) {
        hideDownloadOverlay();
        setStatus('error', start.error || 'Не удалось начать переустановку');
        setPlayState(false);
        setBuildControlsDisabled(false);
        _busy = false;
        return;
      }

      const done = await waitDownloadFinish();
      if (done) {
        _selectedBuildInstalled = true;
        setBuildBadge('ok', 'готова');
        setStatus('ok', `Сборка ${_selectedBuildName} обновлена`);
      } else {
        _selectedBuildInstalled = false;
        setBuildBadge('warn', 'требуется загрузка');
      }

      setPlayState(false);
      setBuildControlsDisabled(false);
      _busy = false;
    } catch (err) {
      setStatus('error', String(err));
      setPlayState(false);
      setBuildControlsDisabled(false);
      _busy = false;
    }
  }

  // ── Инициализация ───────────────────────────────────────────────────────────
  async function init(username) {
    el.username().textContent = username;

    el.btnPlay().onclick = handlePlay;
    el.ramSlider().oninput = onRamChange;
    el.btnIntegrity().onclick = handleIntegrityCheck;
    el.btnCancelDl().onclick = requestCancelDownload;

    setPlayState(false);
    hideDownloadOverlay();

    try {
      await loadRuntimeConfig();
      await loadBuilds();
    } catch (err) {
      setStatus('error', String(err));
      console.error('[main] Ошибка инициализации сборок:', err);
    }
  }

  return {
    init,
    /** Вызывается из app.js когда игра завершается. */
    onGameExit(rc) {
      _busy = false;
      hideDownloadOverlay();
      setPlayState(false);
      setBuildControlsDisabled(false);

      if (rc === 0) {
        setStatus('ok');
      } else {
        setStatus('error', `код ${rc} — см. java_output.log`);
      }
    },
  };
})();
