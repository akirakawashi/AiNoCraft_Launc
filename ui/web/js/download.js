/**
 * download.js — экран загрузки и установки игровых файлов.
 *
 * Три состояния-секции:
 *   idle     — ожидание, кнопка «Скачать»
 *   progress — идёт загрузка или распаковка
 *   error    — ошибка, кнопка «Повторить»
 */

const DownloadPage = (() => {

  let _pollTimer = null;
  let _onDone = null;     // callback() когда установка завершена успешно
  let _onCancel = null;   // callback() когда загрузка отменена
  let _buildId = null;    // выбранная сборка

  // ── DOM-ссылки ──────────────────────────────────────────────────────────────
  const el = {
    subtitle:  () => document.getElementById('dl-subtitle'),
    sIdle:     () => document.getElementById('dl-section-idle'),
    sProgress: () => document.getElementById('dl-section-progress'),
    sError:    () => document.getElementById('dl-section-error'),

    statusText: () => document.getElementById('dl-status-text'),
    bar:        () => document.getElementById('dl-bar'),
    percent:    () => document.getElementById('dl-percent'),
    speed:      () => document.getElementById('dl-speed'),
    size:       () => document.getElementById('dl-size'),
    errorText:  () => document.getElementById('dl-error-text'),

    btnStart:   () => document.getElementById('btn-start-download'),
    btnCancel:  () => document.getElementById('btn-cancel-download'),
    btnRetry:   () => document.getElementById('btn-retry-download'),
  };

  // ── Переключение секций ─────────────────────────────────────────────────────
  function showSection(name) {
    el.sIdle().hidden     = (name !== 'idle');
    el.sProgress().hidden = (name !== 'progress');
    el.sError().hidden    = (name !== 'error');
  }

  // ── Обновление прогресс-бара ────────────────────────────────────────────────
  function applyProgress(status) {
    const pct = status.percent || 0;
    el.bar().style.width     = pct + '%';
    el.percent().textContent = pct.toFixed(1) + '%';

    if (status.state === 'extracting') {
      el.statusText().textContent = 'Распаковка файлов...';
      el.speed().textContent      = '—';
      el.size().textContent       = '';
    } else {
      el.statusText().textContent = 'Загрузка...';
      el.speed().textContent      = (status.speed_mb || 0).toFixed(1) + ' МБ/с';
      const dl    = (status.downloaded_mb || 0).toFixed(1);
      const total = (status.total_mb || 0).toFixed(1);
      el.size().textContent = `${dl} / ${total} МБ`;
    }
  }

  // ── Поллинг прогресса ───────────────────────────────────────────────────────
  function startPolling() {
    stopPolling();
    _pollTimer = setInterval(async () => {
      try {
        const status = await API.getDownloadProgress();
        applyProgress(status);

        if (!status.active) {
          stopPolling();
          switch (status.state) {
            case 'done':
              _onDone && _onDone();
              break;
            case 'cancelled':
              showSection('idle');
              el.subtitle().textContent = 'Загрузка отменена';
              _onCancel && _onCancel();
              break;
            case 'error':
              showSection('error');
              el.errorText().textContent = status.error || 'Неизвестная ошибка';
              break;
          }
        }
      } catch (err) {
        console.error('[download] Ошибка поллинга:', err);
      }
    }, 400);
  }

  function stopPolling() {
    if (_pollTimer) {
      clearInterval(_pollTimer);
      _pollTimer = null;
    }
  }

  // ── Действия ────────────────────────────────────────────────────────────────
  async function startDownload() {
    showSection('progress');
    el.statusText().textContent = 'Подключение к серверу...';
    el.bar().style.width        = '0%';
    el.percent().textContent    = '0%';
    el.speed().textContent      = '—';
    el.size().textContent       = '';
    el.btnCancel().disabled     = false;

    const result = await API.startDownload(_buildId);
    if (!result.success) {
      showSection('error');
      el.errorText().textContent = result.error || 'Не удалось начать загрузку';
      return;
    }
    startPolling();
  }

  async function cancelDownload() {
    el.btnCancel().disabled     = true;
    el.statusText().textContent = 'Отмена...';
    await API.cancelDownload();
    // дальше поллинг поймает state=cancelled
  }

  // ── Инициализация ───────────────────────────────────────────────────────────
  /**
   * @param {object}   opts
   * @param {string}   [opts.subtitle]   — текст под логотипом
   * @param {boolean}  [opts.autoStart]  — автоматически начать загрузку
   * @param {string}   [opts.buildId]    — id сборки
   * @param {function} [opts.onDone]     — callback после успешной установки
   * @param {function} [opts.onCancel]   — callback после отмены
   */
  async function init({ subtitle, autoStart, buildId, onDone, onCancel } = {}) {
    stopPolling();
    _onDone   = onDone   || null;
    _onCancel = onCancel || null;
    _buildId  = buildId  || null;

    el.subtitle().textContent = subtitle || 'Игровые файлы не найдены';
    showSection('idle');

    el.btnStart().onclick  = startDownload;
    el.btnCancel().onclick = cancelDownload;
    el.btnRetry().onclick  = startDownload;

    if (autoStart) {
      await startDownload();
    }
  }

  return { init, stopPolling };
})();
