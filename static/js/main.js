// Mobile nav toggle
const navToggle  = document.getElementById('navToggle');
const navMenu    = document.getElementById('navMenu'); // ul.nav-menu-mobile hors du header
if (navToggle && navMenu) {
  navToggle.addEventListener('click', () => {
    const isOpen = navMenu.classList.toggle('open');
    navToggle.classList.toggle('open', isOpen);
    document.body.style.overflow = isOpen ? 'hidden' : '';
  });
  navMenu.querySelectorAll('a').forEach(a => {
    a.addEventListener('click', () => {
      navMenu.classList.remove('open');
      navToggle.classList.remove('open');
      document.body.style.overflow = '';
    });
  });
}

// Header scroll shadow
const header = document.getElementById('header');
if (header) {
  window.addEventListener('scroll', () => {
    header.classList.toggle('scrolled', window.scrollY > 10);
  }, { passive: true });
}

// Menu category tab filtering
const tabs = document.querySelectorAll('.menu-tab');
const sections = document.querySelectorAll('.menu-category');
if (tabs.length && sections.length) {
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const target = tab.dataset.target;
      sections.forEach(sec => {
        sec.style.display = (target === 'all' || sec.dataset.cat === target) ? '' : 'none';
      });
    });
  });
}

// ── Horaires dynamiques : jour courant surligné + statut ouvert/fermé en temps réel ──
(function(){
  const DAYS_JS = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];
  const ORDER = ['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'];
  const TZ = 'Europe/Brussels';

  function brussels(){
    const now = new Date();
    try {
      let d = new Intl.DateTimeFormat('fr-FR', {timeZone:TZ, weekday:'long'}).format(now);
      d = d.charAt(0).toUpperCase() + d.slice(1);
      const t = new Intl.DateTimeFormat('en-GB', {timeZone:TZ, hour:'2-digit', minute:'2-digit', hour12:false}).format(now);
      return { dayName: d, time: t };
    } catch(e){
      return { dayName: DAYS_JS[now.getDay()], time: now.toTimeString().slice(0,5) };
    }
  }

  const HOURS = Array.isArray(window.CANTINA_HOURS) ? window.CANTINA_HOURS : [];
  const byName = {};
  HOURS.forEach(h => { byName[h.day_name] = h; });

  function nextOpening(fromName){
    const start = ORDER.indexOf(fromName);
    for (let i = 1; i <= 7; i++){
      const name = ORDER[(start + i) % 7];
      const d = byName[name];
      if (d && !Number(d.is_closed)){
        const t = d.lunch_open || d.dinner_open;
        if (t) return { dayName: name, time: t };
      }
    }
    return null;
  }

  function computeStatus(dayName, t){
    const h = byName[dayName];
    const nx = () => { const n = nextOpening(dayName); return n ? `Fermé · ouvre ${n.dayName.toLowerCase()} à ${n.time}` : "Fermé aujourd'hui"; };
    if (!h || Number(h.is_closed)) return { state:'closed', label: nx() };
    if (h.lunch_open && h.lunch_close && h.lunch_open <= t && t < h.lunch_close)  return { state:'open',  label:`Ouvert · ferme à ${h.lunch_close}` };
    if (h.dinner_open && h.dinner_close && h.dinner_open <= t && t < h.dinner_close) return { state:'open',  label:`Ouvert · ferme à ${h.dinner_close}` };
    if (h.lunch_close && h.dinner_open && h.lunch_close <= t && t < h.dinner_open) return { state:'soon',  label:`Fermé · rouvre à ${h.dinner_open}` };
    if (h.lunch_open && t < h.lunch_open)                                          return { state:'soon',  label:`Ouvre à ${h.lunch_open}` };
    if (!h.lunch_open && h.dinner_open && t < h.dinner_open)                       return { state:'soon',  label:`Ouvre à ${h.dinner_open}` };
    return { state:'closed', label: nx() };
  }

  const COLORS = {
    open:  { bg:'rgba(63,143,79,.14)',  dot:'#3f8f4f', fg:'#2e7d40' },
    soon:  { bg:'rgba(201,152,74,.16)', dot:'#c9984a', fg:'#a9781f' },
    closed:{ bg:'rgba(192,60,60,.12)',  dot:'#c03c3c', fg:'#b23b3b' }
  };

  function render(){
    const { dayName, time } = brussels();
    document.querySelectorAll('[data-day]').forEach(el => {
      el.classList.toggle('today', el.dataset.day === dayName);
    });
    if (!HOURS.length) return;
    const st = computeStatus(dayName, time);

    // Badge natif du hero (conserve son style propre)
    document.querySelectorAll('.hero-status').forEach(el => {
      el.classList.remove('hero-status--open', 'hero-status--soon', 'hero-status--closed');
      el.classList.add('hero-status--' + st.state);
      el.innerHTML = '<span class="hero-status-dot"></span>' + st.label;
    });

    // Badges "pilule" (section horaires accueil + contact)
    const c = COLORS[st.state] || COLORS.closed;
    document.querySelectorAll('.js-hours-status').forEach(b => {
      b.style.cssText = 'display:inline-flex;align-items:center;gap:.5rem;padding:.45rem .95rem;'
        + 'border-radius:99px;font-size:.85rem;font-weight:700;background:'+c.bg+';color:'+c.fg+';';
      b.innerHTML = '<span style="width:8px;height:8px;border-radius:50%;background:'+c.dot+';'
        + 'box-shadow:0 0 0 3px '+c.bg+';"></span>' + st.label;
    });
  }

  render();
  setInterval(render, 60000);
})();

// Cookie consent
function _setConsent(v) {
  try { localStorage.setItem('cookies_ok', v); } catch (e) {}
  const b = document.getElementById('cookieBanner');
  if (b) b.style.display = 'none';
  if (v === 'granted' && typeof window.__loadFB === 'function') window.__loadFB();
  if (v === 'denied'  && typeof window.__denyFB === 'function') window.__denyFB();
}
function acceptCookies()  { _setConsent('granted'); }
function declineCookies() { _setConsent('denied'); }
window.addEventListener('DOMContentLoaded', () => {
  let c = null;
  try { c = localStorage.getItem('cookies_ok'); } catch (e) {}
  if (c !== 'granted' && c !== 'denied' && c !== '1') {
    setTimeout(() => {
      const b = document.getElementById('cookieBanner');
      if (b) b.style.display = 'block';
    }, 1200);
  }
});

// Back to top button
const backToTop = document.getElementById('backToTop');
if (backToTop) {
  window.addEventListener('scroll', () => {
    backToTop.classList.toggle('visible', window.scrollY > 400);
  }, { passive: true });
}

// Fade-up on scroll
const fadeEls = document.querySelectorAll('.fade-up');
if ('IntersectionObserver' in window && fadeEls.length) {
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.style.opacity = '1'; obs.unobserve(e.target); } });
  }, { threshold: .15 });
  fadeEls.forEach(el => { el.style.opacity = '0'; obs.observe(el); });
}

/* ── Réservation : bloque les jours de fermeture et les heures hors service ── */
(function () {
  var sched = window.CF_SCHEDULE;
  if (!sched) return;

  function dayOrder(dateStr) {          // "YYYY-MM-DD" -> 1=lundi … 7=dimanche
    var p = dateStr.split('-');
    var wd = new Date(+p[0], +p[1] - 1, +p[2]).getDay(); // 0=dim … 6=sam
    return wd === 0 ? 7 : wd;
  }
  function toMin(s) { var a = s.split(':'); return (+a[0]) * 60 + (+a[1]); }
  function toStr(m) { var h = Math.floor(m / 60), mm = m % 60; return (h < 10 ? '0' : '') + h + ':' + (mm < 10 ? '0' : '') + mm; }
  function slots(open, close) {          // créneaux de 30 min, dernier service = fermeture - 30 min
    var out = [], m = toMin(open), end = toMin(close) - 30;
    for (; m <= end; m += 30) out.push(toStr(m));
    return out;
  }

  function wire(dateId, timeId) {
    var dateEl = document.getElementById(dateId);
    var timeEl = document.getElementById(timeId);
    if (!dateEl || !timeEl) return;

    var msg = document.getElementById(dateId + '-msg');
    if (!msg) {
      msg = document.createElement('p');
      msg.id = dateId + '-msg';
      msg.className = 'resa-closed-msg';
      msg.hidden = true;
      dateEl.parentNode.appendChild(msg);
    }

    function rebuild() {
      var v = dateEl.value;
      if (!v) {
        timeEl.innerHTML = '<option value="">Choisissez d\'abord une date</option>';
        msg.hidden = true; dateEl.setCustomValidity(''); return;
      }
      var day = sched[dayOrder(v)];
      if (!day || day.closed) {
        var nom = day && day.name ? day.name.toLowerCase() : 'ce jour-là';
        msg.textContent = 'Fermé le ' + nom + ' - merci de choisir un autre jour.';
        msg.hidden = false;
        dateEl.setCustomValidity('Le restaurant est fermé ce jour-là.');
        timeEl.innerHTML = '<option value="">Fermé ce jour</option>';
        timeEl.value = '';
        return;
      }
      msg.hidden = true;
      dateEl.setCustomValidity('');
      var prev = timeEl.value;
      var out = '<option value="">Choisir une heure</option>';
      if (day.lunch) {
        out += '<optgroup label="Midi (' + day.lunch[0] + '-' + day.lunch[1] + ')">';
        slots(day.lunch[0], day.lunch[1]).forEach(function (t) { out += '<option>' + t + '</option>'; });
        out += '</optgroup>';
      }
      if (day.dinner) {
        out += '<optgroup label="Soir (' + day.dinner[0] + '-' + day.dinner[1] + ')">';
        slots(day.dinner[0], day.dinner[1]).forEach(function (t) { out += '<option>' + t + '</option>'; });
        out += '</optgroup>';
      }
      timeEl.innerHTML = out;
      if (prev) {
        var keep = Array.prototype.some.call(timeEl.options, function (o) { return o.value === prev; });
        if (keep) timeEl.value = prev;
      }
    }

    dateEl.addEventListener('change', rebuild);
    dateEl.addEventListener('input', rebuild);
    rebuild();
  }

  wire('r-date', 'r-time');   // page Réservation
  wire('hr-date', 'hr-time'); // formulaire d'accueil
})();
