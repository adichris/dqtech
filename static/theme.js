(() => {
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = null;
  try { preference = localStorage.getItem('dqtech-theme'); } catch {}
  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    for (const button of document.querySelectorAll('.theme-toggle')) {
      const dark = theme === 'dark';
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
      button.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
      button.querySelector('i').className = 'fa-solid ' + (dark ? 'fa-sun' : 'fa-moon');
    }
  }
  apply(['dark','light'].includes(preference) ? preference : media.matches ? 'dark' : 'light');
  document.addEventListener('DOMContentLoaded', () => apply(document.documentElement.dataset.theme));
  document.addEventListener('click', event => {
    if (!event.target.closest('.theme-toggle')) return;
    preference = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('dqtech-theme', preference); } catch {}
    apply(preference);
  });
  media.addEventListener('change', event => { if (!['dark','light'].includes(preference)) apply(event.matches ? 'dark' : 'light'); });
  window.addEventListener('storage', event => {
    if (event.key === 'dqtech-theme') { preference = event.newValue; apply(['dark','light'].includes(preference) ? preference : media.matches ? 'dark' : 'light'); }
  });
})();
