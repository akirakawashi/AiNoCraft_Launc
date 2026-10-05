/**
 * Window chrome and layout: titlebar, drag, side panels, particles, warmup.
 */

const Shell = (() => {
  let playButtonParticlesStarted = false;

  function initWindowControls() {
    const api = () => window.pywebview && window.pywebview.api;
    const titlebar = document.querySelector('.titlebar');
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    let framePending = false;
    let pendingDx = 0;
    let pendingDy = 0;

    document.getElementById('window-minimize').addEventListener('click', () => {
      if (api()) api().minimize_window();
    });

    document.getElementById('window-close').addEventListener('click', () => {
      if (api()) api().close_window();
    });

    titlebar.addEventListener('mousedown', (event) => {
      if (event.button !== 0 || event.target.closest('button')) return;
      dragging = true;
      lastX = event.screenX;
      lastY = event.screenY;
    });

    window.addEventListener('mouseup', () => {
      dragging = false;
    });

    window.addEventListener('mousemove', (event) => {
      if (!dragging || !api()) return;
      pendingDx += event.screenX - lastX;
      pendingDy += event.screenY - lastY;
      lastX = event.screenX;
      lastY = event.screenY;

      if (framePending) return;
      framePending = true;
      requestAnimationFrame(() => {
        framePending = false;
        const dx = pendingDx;
        const dy = pendingDy;
        pendingDx = 0;
        pendingDy = 0;
        if (dx || dy) api().move_window_delta(dx, dy);
      });
    });
  }

  function initPlayButtonParticles() {
    const layer = document.querySelector('.play-button__shine');
    if (!layer || playButtonParticlesStarted) return;
    playButtonParticlesStarted = true;

    const colors = [
      { core: 'rgba(255, 255, 255, 0.96)', glow: 'rgba(255, 255, 255, 0.6)', haze: 'rgba(255, 255, 255, 0.24)' },
      { core: 'rgba(115, 219, 255, 0.92)', glow: 'rgba(82, 194, 255, 0.62)', haze: 'rgba(72, 185, 255, 0.22)' },
      { core: 'rgba(221, 113, 255, 0.9)', glow: 'rgba(205, 83, 255, 0.58)', haze: 'rgba(196, 72, 255, 0.22)' },
      { core: 'rgba(166, 148, 255, 0.9)', glow: 'rgba(130, 116, 255, 0.56)', haze: 'rgba(121, 112, 255, 0.2)' },
    ];
    const particles = [];
    const particleCount = 72;
    let width = 1;
    let height = 1;
    let lastTime = performance.now();

    const random = (min, max) => min + Math.random() * (max - min);
    const pick = (items) => items[Math.floor(Math.random() * items.length)];

    const measure = () => {
      const rect = layer.getBoundingClientRect();
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
    };

    const resetParticle = (particle, anywhere = false) => {
      const color = pick(colors);
      const large = Math.random() < 0.24;
      const size = large ? random(4.5, 8.5) : random(1.2, 4.2);
      const direction = Math.random() < 0.72 ? 1 : -1;

      particle.size = size;
      particle.x = anywhere ? random(-8, width + 8) : (direction > 0 ? random(-22, -6) : random(width + 6, width + 22));
      particle.y = random(4, Math.max(5, height - 4));
      particle.vx = random(8, 28) * direction;
      particle.vy = random(-5, 5);
      particle.float = random(1.5, 6.5);
      particle.phase = random(0, Math.PI * 2);
      particle.twinkle = random(2.2, 5.8);
      particle.alpha = large ? random(0.2, 0.42) : random(0.38, 0.86);
      particle.age = random(0, 10);

      particle.node.style.width = `${size}px`;
      particle.node.style.height = `${size}px`;
      particle.node.style.background = `radial-gradient(circle, ${color.core} 0 34%, ${color.glow} 52%, transparent 74%)`;
      particle.node.style.boxShadow = `0 0 ${random(5, 12)}px ${color.glow}, 0 0 ${random(13, 24)}px ${color.haze}`;
    };

    measure();

    for (let i = 0; i < particleCount; i += 1) {
      const node = document.createElement('span');
      node.className = 'play-button__particle';
      layer.appendChild(node);
      const particle = { node };
      resetParticle(particle, true);
      particles.push(particle);
    }

    const resizeObserver = window.ResizeObserver && new ResizeObserver(measure);
    if (resizeObserver) {
      resizeObserver.observe(layer);
    } else {
      window.addEventListener('resize', measure);
    }

    const render = (time) => {
      const dt = Math.min((time - lastTime) / 1000, 0.04);
      lastTime = time;

      particles.forEach((particle) => {
        particle.age += dt;
        particle.x += particle.vx * dt;
        particle.y += particle.vy * dt;

        const waveY = particle.y + Math.sin(particle.age * 2.1 + particle.phase) * particle.float;
        const pulse = 0.62 + Math.sin(particle.age * particle.twinkle + particle.phase) * 0.38;
        const scale = 0.72 + pulse * 0.5;

        if (
          particle.x < -24 ||
          particle.x > width + 24 ||
          waveY < -18 ||
          waveY > height + 18
        ) {
          resetParticle(particle);
          return;
        }

        particle.node.style.opacity = `${Math.max(0.06, particle.alpha * pulse)}`;
        particle.node.style.transform = `translate3d(${particle.x}px, ${waveY}px, 0) scale(${scale})`;
      });

      requestAnimationFrame(render);
    };

    requestAnimationFrame(render);
  }

  function initSidePanels() {
    const panels = {
      settings: document.getElementById('settings-panel'),
      builds: document.getElementById('builds-panel'),
      news: document.getElementById('news-panel'),
    };

    const updateScrollHint = (panel) => {
      const scroll = panel && panel.querySelector('.settings-panel__scroll');
      if (!scroll) return;
      const hasOverflow = scroll.scrollHeight > scroll.clientHeight + 1;
      const scrollTop = scroll.scrollTop <= 2 ? 0 : scroll.scrollTop;
      const maxTop = Math.max(0, scroll.scrollHeight - scroll.clientHeight);
      const hasAbove = scrollTop > 6;
      const hasBelow = scrollTop < maxTop - 6;
      panel.classList.toggle('settings-panel--has-above', hasOverflow && hasAbove);
      panel.classList.toggle('settings-panel--has-below', hasOverflow && hasBelow);
    };

    const bindSmoothWheel = (scroll) => {
      let targetTop = scroll.scrollTop;
      let frame = 0;

      const tick = () => {
        const delta = targetTop - scroll.scrollTop;
        if (Math.abs(delta) < 0.35) {
          if (targetTop <= 2) targetTop = 0;
          scroll.scrollTop = targetTop;
          frame = 0;
          return;
        }

        scroll.scrollTop += delta * 0.18;
        frame = requestAnimationFrame(tick);
      };

      scroll.addEventListener('wheel', (event) => {
        if (event.ctrlKey) return;

        const maxTop = scroll.scrollHeight - scroll.clientHeight;
        if (maxTop <= 0) return;

        event.preventDefault();
        targetTop = Math.max(0, Math.min(maxTop, targetTop + event.deltaY * 0.82));
        if (targetTop <= 6) targetTop = 0;

        if (!frame) {
          frame = requestAnimationFrame(tick);
        }
      }, { passive: false });

      scroll.addEventListener('scroll', () => {
        if (!frame) targetTop = scroll.scrollTop;
      }, { passive: true });
    };

    const setPanelOpen = (panel, open) => {
      panel.classList.toggle('settings-panel--open', open);
      panel.setAttribute('aria-hidden', String(!open));
      panel.toggleAttribute('inert', !open);
      if (open) requestAnimationFrame(() => updateScrollHint(panel));
    };

    const openOnly = (name) => {
      let anyOpen = false;
      Object.keys(panels).forEach((key) => {
        const panel = panels[key];
        if (!panel) return;
        const open = key === name;
        setPanelOpen(panel, open);
        anyOpen = anyOpen || open;
      });
      document.body.classList.toggle('settings-open', anyOpen);
    };

    Object.values(panels).forEach((panel) => {
      if (!panel) return;
      const scroll = panel.querySelector('.settings-panel__scroll');
      if (!scroll) return;

      scroll.addEventListener('scroll', () => updateScrollHint(panel), { passive: true });
      window.addEventListener('resize', () => updateScrollHint(panel));
      bindSmoothWheel(scroll);

      if (window.ResizeObserver) {
        const observer = new ResizeObserver(() => updateScrollHint(panel));
        observer.observe(scroll);
        Array.from(scroll.children).forEach((child) => observer.observe(child));
      }

      updateScrollHint(panel);
    });

    document.querySelectorAll('.side-nav__item').forEach((item) => {
      item.addEventListener('click', () => {
        openOnly(item.dataset.nav);
      });
    });

    // Dev hook: index.html?panel=settings or ?panel=builds opens a panel for screenshots
    const params = new URLSearchParams(window.location.search);
    const devPanel = params.get('panel');
    if (devPanel && panels[devPanel]) {
      openOnly(devPanel);
    }
  }

  function initSideNavState() {
    const items = document.querySelectorAll('.side-nav__item');
    if (!items.length) return;

    items.forEach((item) => {
      item.addEventListener('click', () => {
        items.forEach((button) => {
          const active = button === item;
          button.classList.toggle('side-nav__item--active', active);
          if (active) {
            button.setAttribute('aria-current', 'page');
          } else {
            button.removeAttribute('aria-current');
          }
        });
      });
    });
  }

  function setNewsVisible(visible) {
    const newsItem = document.querySelector('.side-nav__item[data-nav="news"]');
    if (newsItem) newsItem.hidden = !visible;
  }

  // --------------------------------------------------------------- warmup

  const warmupImages = [
    '../img/logo.png',
    '../img/background.png',
    '../img/crystals.png',
    '../img/testbtn.png',
    '../img/testborder.png',
  ];
  let launcherSurfaceWarmup = null;
  let bridgeWarmupStarted = false;
  let postStartupWarmupScheduled = false;

  function waitForIdle() {
    return new Promise((resolve) => {
      if (window.requestIdleCallback) {
        window.requestIdleCallback(() => resolve(), { timeout: 1200 });
      } else {
        window.setTimeout(resolve, 80);
      }
    });
  }

  function decodeWarmupImage(src) {
    return new Promise((resolve) => {
      const image = new Image();
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        resolve();
      };

      image.onload = () => {
        if (image.decode) {
          image.decode().then(finish).catch(finish);
        } else {
          finish();
        }
      };
      image.onerror = finish;
      image.src = src;
    });
  }

  function warmLauncherSurface() {
    if (launcherSurfaceWarmup) return launcherSurfaceWarmup;

    launcherSurfaceWarmup = (async () => {
      for (const src of warmupImages) {
        await waitForIdle();
        await decodeWarmupImage(src);
      }
      await waitForIdle();
      initPlayButtonParticles();
    })().catch((err) => {
      console.warn('[warmup] render warmup failed:', err);
    });

    return launcherSurfaceWarmup;
  }

  function runBridgeWarmup() {
    if (bridgeWarmupStarted) return;
    bridgeWarmupStarted = true;
    API.warmup().catch((err) => {
      console.warn('[warmup] bridge warmup failed:', err);
    });
  }

  function startPostStartupWarmup() {
    if (postStartupWarmupScheduled) return;
    postStartupWarmupScheduled = true;

    // Let the loader fade out and the main launcher transition finish before
    // decoding large textures. Each image then gets its own idle slice.
    window.setTimeout(() => {
      void warmLauncherSurface();
      runBridgeWarmup();
    }, 450);
  }

  function init() {
    initWindowControls();
    initSideNavState();
    initSidePanels();
  }

  return { init, startPostStartupWarmup, setNewsVisible };
})();
