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

// Highlight today in hours tables
const days = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];
const todayName = days[new Date().getDay()];
document.querySelectorAll('[data-day]').forEach(el => {
  if (el.dataset.day === todayName) el.classList.add('today');
});
document.querySelectorAll('.contact-hours-row[data-day]').forEach(el => {
  if (el.dataset.day === todayName) el.classList.add('today');
});

// Cookie banner
function acceptCookies() {
  localStorage.setItem('cookies_ok', '1');
  document.getElementById('cookieBanner').style.display = 'none';
}
window.addEventListener('DOMContentLoaded', () => {
  if (!localStorage.getItem('cookies_ok')) {
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
