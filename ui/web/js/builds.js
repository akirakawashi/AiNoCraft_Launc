/**
 * Builds panel: renders build cards from state and handles selection.
 */

const Builds = (() => {
  const container = () => document.getElementById('build-cards');

  function cardStatus(build, isActive) {
    if (build.update_available) return 'Доступно обновление';
    if (build.damaged) return 'Требуется переустановка';
    if (build.installed && !build.update_known) return 'Установлено · без проверки';
    if (build.installed && isActive) return 'Установлено и активно';
    if (build.installed) return 'Установлено';
    return 'Не установлено';
  }

  function buildCard(build) {
    const isActive = build.id === App.state.selectedBuildId;

    const card = document.createElement('article');
    const needsUpdate = Boolean(build.update_available || build.damaged);
    card.className = `build-card${isActive ? ' build-card--active' : ''}${needsUpdate ? ' build-card--update' : ''}`;
    card.dataset.buildId = build.id;

    const top = document.createElement('div');
    top.className = 'build-card__top';

    const logo = document.createElement('span');
    logo.className = 'build-card__logo';
    logo.setAttribute('aria-hidden', 'true');
    logo.textContent = (build.glyph || build.id.slice(0, 1)).toUpperCase();
    if (build.accent_color) logo.style.color = build.accent_color;

    const info = document.createElement('div');
    info.className = 'build-card__info';

    const title = document.createElement('h3');
    title.className = 'build-card__title';
    title.textContent = build.name;

    const meta = document.createElement('p');
    meta.className = 'build-card__meta';
    meta.textContent = `Minecraft ${build.minecraft_version || '—'} · ${build.title || build.name}`;

    const desc = document.createElement('p');
    desc.className = 'build-card__desc';
    desc.textContent = build.description || '';

    info.append(title, meta, desc);
    top.append(logo, info);

    const divider = document.createElement('span');
    divider.className = 'build-card__divider';
    divider.setAttribute('aria-hidden', 'true');

    const footer = document.createElement('div');
    footer.className = 'build-card__footer';

    const status = document.createElement('span');
    status.className = 'build-card__status';
    const mark = document.createElement('span');
    mark.className = 'build-card__status-mark';
    mark.setAttribute('aria-hidden', 'true');
    status.append(mark, document.createTextNode(cardStatus(build, isActive)));

    footer.appendChild(status);

    if (isActive) {
      const badge = document.createElement('span');
      badge.className = 'build-card__badge';
      badge.innerHTML =
        '<svg class="build-card__badge-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"'
        + ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 8.5l3 3 7-7" /></svg>Активна';
      footer.appendChild(badge);
    } else {
      const selectBtn = document.createElement('button');
      selectBtn.type = 'button';
      selectBtn.className = 'settings-btn settings-btn--primary';
      selectBtn.textContent = 'Выбрать';
      selectBtn.addEventListener('click', () => App.selectBuild(build.id));
      footer.appendChild(selectBtn);
    }

    card.append(top, divider, footer);
    return card;
  }

  function render() {
    const root = container();
    if (!root) return;
    root.innerHTML = '';
    App.state.builds.forEach((build) => {
      root.appendChild(buildCard(build));
    });
  }

  return { render };
})();
