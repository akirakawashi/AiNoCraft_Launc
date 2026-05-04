/**
 * updater.js - auto-update at startup.
 * Usage: await Updater.checkAndApply()
 */
const Updater = (() => {
  const el = {
    page:    () => document.getElementById('page-update'),
    status:  () => document.getElementById('upd-status'),
    bar:     () => document.getElementById('upd-bar'),
    percent: () => document.getElementById('upd-percent'),
    speed:   () => document.getElementById('upd-speed'),
    size:    () => document.getElementById('upd-size'),
    version: () => document.getElementById('upd-version'),
    errBox:  () => document.getElementById('upd-error'),
    errText: () => document.getElementById('upd-error-text'),
  };
  function setStatus(t) { const e=el.status(); if(e) e.textContent=t; }
  function showPage(s) {
    // Hide all pages, show only page-update
    document.querySelectorAll('.page').forEach(p => p.hidden = true);
    const p = el.page(); if (!p) return;
    p.hidden = false;
    const v = el.version(); if (v && s) v.textContent = s;
  }
  function hidePage() { const p=el.page(); if(p) p.hidden=true; }
  function showError(msg) { const b=el.errBox(),t=el.errText(); if(b)b.hidden=false; if(t)t.textContent=msg; }
  function pollUntilDone() {
    return new Promise((resolve) => {
      const timer = setInterval(async () => {
        try {
          const s = await API.getLauncherUpdateProgress();
          _applyProgress(s);
          if (s.state==='done')   { clearInterval(timer); setTimeout(resolve,3000); }
          if (s.state==='error')  { clearInterval(timer); resolve(); }
        } catch(e) { clearInterval(timer); resolve(); }
      }, 400);
    });
  }
  function _applyProgress(s) {
    if (s.state==='downloading') {
      const pct=s.percent||0;
      const bar=el.bar(); if(bar) bar.style.width=pct+'%';
      const pEl=el.percent(); if(pEl) pEl.textContent=pct.toFixed(1)+'%';
      const spEl=el.speed(); if(spEl) spEl.textContent=s.speed_mb>0?s.speed_mb.toFixed(1)+' MB/s':'';
      const szEl=el.size(); if(szEl) szEl.textContent=s.total_mb>0?s.downloaded_mb.toFixed(1)+' / '+s.total_mb.toFixed(1)+' MB':s.downloaded_mb.toFixed(1)+' MB';
      setStatus('Загрузка обновления...');
    } else if (s.state==='applying') {
      const bar=el.bar(); if(bar) bar.style.width='100%';
      const pEl=el.percent(); if(pEl) pEl.textContent='100%';
      setStatus('Установка обновления...');
    } else if (s.state==='error') {
      showError(s.error||'Ошибка обновления');
    }
  }
  async function checkAndApply() {
    showPage('Проверка обновлений...');
    setStatus('Подключение к серверу...');
    let res;
    try { res = await API.checkLauncherUpdate(); } catch(e) { hidePage(); return; }
    if (!res.available) { hidePage(); return; }
    showPage('Обновление до v' + res.remote_version);
    setStatus('Начинаем загрузку...');
    try {
      const sr = await API.startLauncherUpdate(res.download_url, res.sha256 || null);
      if (!sr.success) { showError(sr.error||'Не удалось запустить загрузку'); await new Promise(r=>setTimeout(r,3000)); hidePage(); return; }
    } catch(e) { hidePage(); return; }
    await pollUntilDone();
    hidePage();
  }
  return { checkAndApply };
})();

