/**
 * Home screen: play button state machine, active build info, install status.
 */

const Home = (() => {
  const el = {
    playButton: () => document.getElementById('btn-play'),
    playLabel: () => document.getElementById('play-label'),
    buildName: () => document.getElementById('stat-build-name'),
    buildDesc: () => document.getElementById('stat-build-desc'),
    version: () => document.getElementById('stat-version'),
    versionDesc: () => document.getElementById('stat-version-desc'),
    launchStatus: () => document.getElementById('launch-status'),
    launcherVersion: () => document.getElementById('launcher-version-label'),
  };

  let busy = false;

  function selectedBuild() {
    return App.state.builds.find((build) => build.id === App.state.selectedBuildId) || null;
  }

  function setPlay(label, disabled) {
    el.playLabel().textContent = label;
    el.playButton().disabled = disabled;
    el.playButton().classList.toggle('play-button--disabled', disabled);
  }

  function setFilesStatus(build) {
    const status = el.launchStatus();
    const ready = Boolean(build && build.installed && !build.update_available);
    status.classList.toggle('launch-status--ready', ready);
    status.classList.toggle('launch-status--pending', !ready);

    const readyLabel = status.querySelector('.launch-status__label--ready');
    const pendingLabel = status.querySelector('.launch-status__label--pending');
    if (readyLabel) {
      readyLabel.textContent = build && !build.update_known
        ? 'Сборка установлена · актуальность не проверена'
        : 'Сборка актуальна и готова к игре';
    }
    if (pendingLabel) {
      if (build && build.update_available) pendingLabel.textContent = 'Доступно обновление сборки';
      else if (build && build.damaged) pendingLabel.textContent = 'Требуется переустановка сборки';
      else pendingLabel.textContent = 'Загрузите файлы сборки';
    }
  }

  function render() {
    const build = selectedBuild();
    if (!build) {
      el.buildName().textContent = '—';
      el.buildDesc().textContent = 'Сборка не выбрана';
      setPlay('Недоступно', true);
      setFilesStatus(null);
      return;
    }

    el.buildName().textContent = build.title || build.name;
    el.buildDesc().textContent = build.description || '';
    el.version().textContent = build.minecraft_version || '—';
    const revision = build.remote_revision || build.local_revision || '';
    el.versionDesc().textContent = `Режим: ${build.title || build.name}${revision ? ` · Ревизия: ${revision}` : ''}`;
    el.launcherVersion().textContent = App.state.launcherVersion || '—';

    setFilesStatus(build);
    if (busy) return;
    if (build.update_available) setPlay('Обновить', false);
    else if (build.damaged) setPlay('Переустановить', false);
    else setPlay(build.installed ? 'Играть' : 'Скачать', false);
  }

  async function downloadSelected(title) {
    busy = true;
    setPlay('Загрузка...', true);
    try {
      const done = await App.runDownload(App.state.selectedBuildId, title);
      await App.refreshBuilds();
      return done;
    } finally {
      busy = false;
      render();
    }
  }

  async function launchSelected() {
    busy = true;
    setPlay('Запуск игры...', true);
    try {
      const result = await API.launchGame(App.state.selectedBuildId);
      if (result && result.success) {
        setPlay('Игра запущена', true);
        return;
      }
      await Modals.alert((result && result.error) || 'Не удалось запустить игру', { title: 'Ошибка запуска' });
    } catch (err) {
      console.error('[home] launch error:', err);
      await Modals.alert('Не удалось запустить игру', { title: 'Ошибка запуска' });
    } finally {
      busy = false;
      render();
    }
  }

  async function handlePlay() {
    if (busy) return;
    const build = selectedBuild();
    if (!build) return;

    if (!build.installed || build.update_available) {
      const name = build.title || build.name;
      let message = `Сборка ${name} не установлена.\nСкачать и установить сейчас?`;
      let title = 'Установка сборки';
      let okLabel = 'Скачать';
      let progressTitle = `Загрузка ${name}`;

      if (build.update_available) {
        message = `Для сборки ${name} доступно обновление.\nСкачать и установить его сейчас?`;
        title = 'Обновление сборки';
        okLabel = 'Обновить';
        progressTitle = `Обновление ${name}`;
      } else if (build.damaged) {
        message = `Файлы сборки ${name} неполные или повреждены.\nПереустановить сборку?`;
        title = 'Восстановление сборки';
        okLabel = 'Переустановить';
        progressTitle = `Переустановка ${name}`;
      }

      const agree = await Modals.confirm(message, { title, okLabel });
      if (!agree) return;
      await downloadSelected(progressTitle);
      return;
    }

    await launchSelected();
  }

  function init() {
    el.playButton().addEventListener('click', handlePlay);
  }

  return { init, render };
})();
