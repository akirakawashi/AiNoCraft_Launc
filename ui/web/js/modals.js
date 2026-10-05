/**
 * Launcher-styled modal dialogs: confirm, alert, loading, download progress.
 */

const Modals = (() => {
  const el = {
    overlay: () => document.getElementById('modal-overlay'),
    confirm: () => document.getElementById('modal-confirm'),
    confirmTitle: () => document.getElementById('modal-confirm-title'),
    confirmText: () => document.getElementById('modal-confirm-text'),
    confirmOk: () => document.getElementById('modal-confirm-ok'),
    confirmCancel: () => document.getElementById('modal-confirm-cancel'),
    alert: () => document.getElementById('modal-alert'),
    alertTitle: () => document.getElementById('modal-alert-title'),
    alertText: () => document.getElementById('modal-alert-text'),
    alertOk: () => document.getElementById('modal-alert-ok'),
    loading: () => document.getElementById('modal-loading'),
    loadingText: () => document.getElementById('modal-loading-text'),
    progress: () => document.getElementById('modal-progress'),
    progressTitle: () => document.getElementById('modal-progress-title'),
    progressStatus: () => document.getElementById('modal-progress-status'),
    progressBar: () => document.getElementById('modal-progress-bar'),
    progressPercent: () => document.getElementById('modal-progress-percent'),
    progressSpeed: () => document.getElementById('modal-progress-speed'),
    progressSize: () => document.getElementById('modal-progress-size'),
    progressCancel: () => document.getElementById('modal-progress-cancel'),
  };

  function showOnly(name) {
    ['confirm', 'alert', 'loading', 'progress'].forEach((key) => {
      el[key]().hidden = key !== name;
    });
    el.overlay().hidden = !name;
  }

  function hide() {
    showOnly(null);
  }

  function confirm(message, { title = 'Подтверждение', okLabel = 'Да', cancelLabel = 'Отмена', danger = false } = {}) {
    return new Promise((resolve) => {
      el.confirmTitle().textContent = title;
      el.confirmText().textContent = message;
      el.confirmOk().textContent = okLabel;
      el.confirmCancel().textContent = cancelLabel;
      el.confirmOk().classList.toggle('settings-btn--danger', danger);
      el.confirmOk().classList.toggle('settings-btn--primary', !danger);
      showOnly('confirm');

      const cleanup = (result) => {
        hide();
        el.confirmOk().onclick = null;
        el.confirmCancel().onclick = null;
        resolve(result);
      };
      el.confirmOk().onclick = () => cleanup(true);
      el.confirmCancel().onclick = () => cleanup(false);
      el.confirmOk().focus();
    });
  }

  function alert(message, { title = 'Ошибка' } = {}) {
    return new Promise((resolve) => {
      el.alertTitle().textContent = title;
      el.alertText().textContent = message;
      showOnly('alert');

      const cleanup = () => {
        hide();
        el.alertOk().onclick = null;
        resolve();
      };
      el.alertOk().onclick = cleanup;
      el.alertOk().focus();
    });
  }

  function showLoading(message = 'Загрузка данных...') {
    el.loadingText().textContent = message;
    showOnly('loading');
  }

  function showProgress(title, onCancel) {
    el.progressTitle().textContent = title;
    el.progressStatus().textContent = 'Подключение к серверу...';
    el.progressBar().style.width = '0%';
    el.progressPercent().textContent = '0.0%';
    el.progressSpeed().textContent = '-';
    el.progressSize().textContent = '';
    const cancelBtn = el.progressCancel();
    cancelBtn.disabled = false;
    cancelBtn.onclick = () => {
      cancelBtn.disabled = true;
      el.progressStatus().textContent = 'Отмена загрузки...';
      if (onCancel) onCancel();
    };
    showOnly('progress');
  }

  function updateProgress({ status, percent, speed, size }) {
    if (status !== undefined) el.progressStatus().textContent = status;
    if (percent !== undefined) {
      el.progressBar().style.width = `${percent}%`;
      el.progressPercent().textContent = `${percent}%`;
    }
    if (speed !== undefined) el.progressSpeed().textContent = speed;
    if (size !== undefined) el.progressSize().textContent = size;
  }

  return { confirm, alert, showLoading, showProgress, updateProgress, hide };
})();
