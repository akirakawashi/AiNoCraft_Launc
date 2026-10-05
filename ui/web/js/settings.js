/**
 * Settings panel: RAM, file verification, build deletion.
 */

const Settings = (() => {
  const el = {
    ramSlider: () => document.getElementById('ram-slider'),
    ramValue: () => document.getElementById('ram-value'),
    ramScaleMin: () => document.getElementById('ram-scale-min'),
    ramScaleMax: () => document.getElementById('ram-scale-max'),
    clientState: () => document.getElementById('client-state-text'),
    filesState: () => document.getElementById('files-state'),
    verifyBtn: () => document.getElementById('btn-verify-files'),
    deleteBtn: () => document.getElementById('btn-delete-build'),
  };

  let saveTimer = null;
  let busy = false;

  function selectedBuild() {
    return App.state.builds.find((build) => build.id === App.state.selectedBuildId) || null;
  }

  function syncRamVisual() {
    const slider = el.ramSlider();
    const min = Number(slider.min);
    const max = Number(slider.max);
    const value = Number(slider.value);
    const range = Math.max(1, max - min);
    slider.style.setProperty('--fill', `${((value - min) / range) * 100}%`);
    el.ramValue().textContent = `${value} GB`;
  }

  function onRamInput() {
    syncRamVisual();
    clearTimeout(saveTimer);
    const value = parseInt(el.ramSlider().value, 10);
    saveTimer = setTimeout(async () => {
      try {
        await API.saveSettings({ ram: value }, App.state.selectedBuildId);
      } catch (err) {
        console.error('[settings] RAM save error:', err);
      }
    }, 600);
  }

  function renderRamBounds() {
    const slider = el.ramSlider();
    slider.min = String(App.state.ramMin);
    slider.max = String(App.state.ramMax);
    el.ramScaleMin().textContent = `${App.state.ramMin} GB`;
    el.ramScaleMax().textContent = `${App.state.ramMax} GB`;
  }

  async function renderRamValue() {
    try {
      const settings = await API.getSettings(App.state.selectedBuildId);
      const raw = parseInt(settings.ram, 10);
      const value = Number.isFinite(raw)
        ? Math.min(App.state.ramMax, Math.max(App.state.ramMin, raw))
        : App.state.ramDefault;
      el.ramSlider().value = String(value);
    } catch (err) {
      console.warn('[settings] settings load error:', err);
      el.ramSlider().value = String(App.state.ramDefault);
    }
    syncRamVisual();
  }

  function renderClientState() {
    const build = selectedBuild();
    const installed = Boolean(build && build.installed);
    el.clientState().innerHTML = installed
      ? 'Состояние клиента: <b>готов к запуску</b>'
      : 'Состояние клиента: <b>сборка не установлена</b>';
    el.filesState().hidden = !installed;
  }

  async function handleVerify() {
    if (busy) return;
    const build = selectedBuild();
    if (!build) return;
    const name = build.title || build.name;

    const agree = await Modals.confirm(
      `Файлы сборки ${name} будут удалены и загружены заново.\nУбедитесь, что игра не запущена.`,
      { title: 'Проверка файлов', okLabel: 'Продолжить' }
    );
    if (!agree) return;

    busy = true;
    try {
      await App.runDownload(build.id, `Переустановка ${name}`);
      await App.refreshBuilds();
    } finally {
      busy = false;
    }
  }

  async function handleDelete() {
    if (busy) return;
    const build = selectedBuild();
    if (!build) return;
    const name = build.title || build.name;

    if (!build.installed) {
      await Modals.alert(`Сборка ${name} не установлена.`, { title: 'Удаление сборки' });
      return;
    }

    const agree = await Modals.confirm(
      `Удалить все файлы сборки ${name} с устройства?\nАккаунт и прогресс на сервере сохранятся.`,
      { title: 'Удаление сборки', okLabel: 'Удалить', danger: true }
    );
    if (!agree) return;

    busy = true;
    Modals.showLoading('Удаление файлов...');
    try {
      const result = await API.deleteBuildFiles(build.id);
      Modals.hide();
      if (!result || !result.success) {
        await Modals.alert((result && result.error) || 'Не удалось удалить файлы', { title: 'Ошибка' });
        return;
      }
      await App.refreshBuilds();
    } catch (err) {
      Modals.hide();
      console.error('[settings] delete error:', err);
      await Modals.alert('Не удалось удалить файлы', { title: 'Ошибка' });
    } finally {
      busy = false;
    }
  }

  function render() {
    renderRamBounds();
    void renderRamValue();
    renderClientState();
  }

  function init() {
    el.ramSlider().addEventListener('input', onRamInput);
    el.verifyBtn().addEventListener('click', handleVerify);
    el.deleteBtn().addEventListener('click', handleDelete);
  }

  return { init, render };
})();
