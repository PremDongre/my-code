/* Connect - test page: timer, autosave and anti-cheat (fullscreen + "left the page" warnings).
   A web page cannot block other apps. What it CAN do (and does): force full screen, notice when the student
   leaves (tab/app/window/full-screen), warn, record it for the company, and auto-submit after too many warnings. */
(function () {
  var root = document.getElementById('proctor');
  if (!root) return;
  var form = document.getElementById('testform');
  var STRICT = root.dataset.strict === '1';
  var MAXW = parseInt(root.dataset.max, 10) || 3;
  var EVENT_URL = root.dataset.event, RESULT_URL = root.dataset.result;
  var warnings = parseInt(root.dataset.warnings, 10) || 0;
  var endAt = Date.now() + (parseInt(root.dataset.remaining, 10) || 0) * 1000;
  var timerEl = document.getElementById('timer'), badge = document.getElementById('wbadge');
  var gate = document.getElementById('gate'), gateTitle = document.getElementById('gate-title'),
      gateMsg = document.getElementById('gate-msg'), gateBtn = document.getElementById('gate-btn');
  var csrfEl = form.querySelector('input[name=_csrf]'), csrf = csrfEl ? csrfEl.value : '';
  var armed = false, away = false, finishing = false, fsActive = false, lastBlocked = {};

  var REASON = { tab_hidden: 'you switched to another tab or app', window_blur: 'you moved to another window',
                 fullscreen_exit: 'you exited full screen' };

  function collect() {
    var d = {};
    form.querySelectorAll('input[name^=q], textarea[name^=q]').forEach(function (el) {
      if (el.type === 'radio') { if (el.checked) d[el.name] = el.value; }
      else if (el.value) d[el.name] = el.value;
    });
    return d;
  }
  function send(type) {
    var fd = new FormData();
    fd.append('_csrf', csrf); fd.append('type', type || 'save'); fd.append('draft', JSON.stringify(collect()));
    return fetch(EVENT_URL, { method: 'POST', body: fd, credentials: 'same-origin', keepalive: true })
      .then(function (r) { return r.json(); }).catch(function () { return null; });
  }
  function handle(res) {
    if (!res) return;
    if (res.ended) { finishing = true; armed = false; window.location.href = res.url || RESULT_URL; return; }
    if (typeof res.warnings === 'number') { warnings = res.warnings; if (badge) badge.textContent = warnings + ' / ' + MAXW; }
  }

  /* ---------- timer ---------- */
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function tick() {
    var left = Math.max(0, Math.round((endAt - Date.now()) / 1000));
    if (timerEl) { timerEl.textContent = pad(Math.floor(left / 60)) + ':' + pad(left % 60); if (left <= 60) timerEl.classList.add('low'); }
    if (left <= 0) { submitNow(); return; }
    setTimeout(tick, 500);
  }
  function submitNow() { if (finishing) return; finishing = true; armed = false; form.submit(); }
  tick();

  /* ---------- autosave ---------- */
  var saveTimer = null;
  form.addEventListener('input', function () { clearTimeout(saveTimer); saveTimer = setTimeout(function () { send('save').then(handle); }, 1500); });
  setInterval(function () { if (!finishing) send('save').then(handle); }, 15000);

  /* ---------- submit button ---------- */
  form.addEventListener('submit', function (e) {
    if (finishing) return;
    var prev = armed; armed = false;
    if (!window.confirm('Submit your answers? You cannot retake this task.')) { e.preventDefault(); armed = prev; return; }
    finishing = true;
  });

  if (!STRICT) { if (gate) gate.style.display = 'none'; return; }

  /* ---------- strict mode ---------- */
  var wm = document.getElementById('wm');
  if (wm) wm.textContent = new Array(160).join((wm.dataset.text || '') + '     ');
  document.body.classList.add('locked');

  function showGate(mode, kind, shown) {
    document.body.classList.add('locked'); gate.style.display = 'flex';
    if (mode === 'start') {
      gateTitle.textContent = 'Ready to start?';
      gateMsg.textContent = (warnings ? 'You already have ' + warnings + ' warning(s). ' : '') +
        'The timer is running. The test opens in full screen. Do not leave this page until you submit.';
      gateBtn.textContent = 'Enter full screen & continue';
    } else {
      gateTitle.textContent = '\u26A0 Warning ' + shown + ' of ' + MAXW;
      gateMsg.textContent = 'You left the test page (' + (REASON[kind] || 'you left the page') + '). This was recorded and the company can see it. ' +
        (MAXW - shown > 0 ? 'After ' + (MAXW - shown) + ' more warning(s) your test will be submitted automatically.' : 'The next warning submits your test automatically.');
      gateBtn.textContent = 'Return to the test (full screen)';
    }
  }
  function hideGate() { gate.style.display = 'none'; document.body.classList.remove('locked'); }
  function enterFS() {
    var el = document.documentElement, req = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
    if (!req) return Promise.resolve(false);              // e.g. iPhone Safari: no full screen, tab/app switching is still tracked
    try { var p = req.call(el); return p && p.then ? p.then(function () { return true; }, function () { return false; }) : Promise.resolve(true); }
    catch (e) { return Promise.resolve(false); }
  }
  function leave(kind) {
    if (!armed || away || finishing) return;
    away = true;
    showGate('leave', kind, Math.min(warnings + 1, MAXW));
    send(kind).then(function (res) { handle(res); if (!finishing && res && typeof res.warnings === 'number') showGate('leave', kind, res.warnings); });
  }
  gateBtn.addEventListener('click', function () {
    enterFS().then(function (ok) { fsActive = ok; hideGate(); armed = true; away = false; });
  });
  showGate('start');

  document.addEventListener('visibilitychange', function () { if (document.hidden) leave('tab_hidden'); });
  window.addEventListener('blur', function () { setTimeout(function () { if (!document.hasFocus()) leave(document.hidden ? 'tab_hidden' : 'window_blur'); }, 400); });
  ['fullscreenchange', 'webkitfullscreenchange'].forEach(function (ev) {
    document.addEventListener(ev, function () { if (fsActive && !document.fullscreenElement && !document.webkitFullscreenElement) leave('fullscreen_exit'); });
  });

  /* blocked actions: only logged, they do not count as warnings */
  function blocked(name) { var now = Date.now(); if (armed && !finishing && (!lastBlocked[name] || now - lastBlocked[name] > 3000)) { lastBlocked[name] = now; send('blocked_' + name); } }
  ['copy', 'cut', 'paste', 'contextmenu'].forEach(function (ev) { document.addEventListener(ev, function (e) { e.preventDefault(); blocked(ev); }); });
  document.addEventListener('dragstart', function (e) { e.preventDefault(); });
  document.addEventListener('keydown', function (e) {
    var k = (e.key || '').toLowerCase(), ctrl = e.ctrlKey || e.metaKey;
    var bad = (ctrl && 'cvxpsu'.indexOf(k) > -1 && k.length === 1) || k === 'f12' || (ctrl && e.shiftKey && 'ijck'.indexOf(k) > -1) || k === 'printscreen';
    if (bad) { e.preventDefault(); if (k === 'printscreen' && navigator.clipboard) navigator.clipboard.writeText(' ').catch(function () {}); blocked('shortcut'); }
  });
  history.pushState({ t: 1 }, '', window.location.href);
  window.addEventListener('popstate', function () { history.pushState({ t: 1 }, '', window.location.href); blocked('back'); });
  window.addEventListener('beforeunload', function (e) { if (!finishing && armed) { e.preventDefault(); e.returnValue = ''; } });
})();
