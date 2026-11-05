document.addEventListener('DOMContentLoaded', function () {
  // mobile menu
  var burger = document.querySelector('.burger'), links = document.querySelector('.links');
  if (burger && links) burger.addEventListener('click', function () { links.classList.toggle('open'); });
  // confirm dialogs: <form data-confirm="Sure?">
  document.querySelectorAll('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (e) { if (!confirm(f.dataset.confirm)) e.preventDefault(); });
  });
  // auto-hide flash messages
  setTimeout(function () { document.querySelectorAll('.flash').forEach(function (f) { f.style.transition = 'opacity .6s'; f.style.opacity = '0'; setTimeout(function () { f.remove(); }, 700); }); }, 5000);
  // password eye button on every password field
  var eye='<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
  var eyeOff='<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
  document.querySelectorAll('input[type=password]').forEach(function (inp) {
    var wrap = document.createElement('div'); wrap.className = 'pw';
    inp.parentNode.insertBefore(wrap, inp); wrap.appendChild(inp);
    var b = document.createElement('button'); b.type = 'button'; b.className = 'pwtoggle'; b.title = 'Show / hide password'; b.setAttribute('aria-label', 'Show password'); b.innerHTML = eye;
    b.addEventListener('click', function () { var show = inp.type === 'password'; inp.type = show ? 'text' : 'password'; b.innerHTML = show ? eyeOff : eye; b.setAttribute('aria-label', show ? 'Hide password' : 'Show password'); });
    wrap.appendChild(b);
  });
  // show/hide password
  document.querySelectorAll('[data-toggle-pw]').forEach(function (b) {
    b.addEventListener('click', function () { var i = b.previousElementSibling; i.type = i.type === 'password' ? 'text' : 'password'; });
  });
  // ---- test builder (admin)
  var qs = document.getElementById('qs'), tpl = document.getElementById('qtpl');
  if (qs && tpl) {
    var sync = function (row) {
      var t = row.querySelector('[name=qtype]').value;
      row.querySelector('.mc').style.display = t === 'mcq' ? '' : 'none';
      row.querySelector('.tx').style.display = t === 'text' ? '' : 'none';
    };
    var renumber = function () { qs.querySelectorAll('.qrow').forEach(function (r, i) { r.querySelector('.qn').textContent = i + 1; sync(r); }); };
    document.getElementById('addq').addEventListener('click', function () { qs.appendChild(tpl.content.cloneNode(true)); renumber(); });
    qs.addEventListener('click', function (e) {
      if (e.target.classList.contains('rm') && qs.querySelectorAll('.qrow').length > 1) { e.target.closest('.qrow').remove(); renumber(); }
    });
    qs.addEventListener('change', function (e) { if (e.target.name === 'qtype') sync(e.target.closest('.qrow')); });
    renumber();
  }
  // ---- tables: on phones every row becomes a card (labels come from the header cells)
  document.querySelectorAll('.tbl table').forEach(function (t) {
    var heads = Array.prototype.map.call(t.querySelectorAll('th'), function (h) { return h.textContent.trim(); });
    if (!heads.length) return;
    t.classList.add('stack');
    Array.prototype.forEach.call(t.querySelectorAll('tr'), function (tr) {
      if (tr.querySelector('th')) { tr.classList.add('hdr'); return; }
      Array.prototype.forEach.call(tr.children, function (td, i) { td.setAttribute('data-label', heads[i] || ''); });
    });
  });
});
