// Page bootstrapping and small formatting helpers shared by every page.
import { loadData, setTitle, showError } from './data.js';
import { updateNavLinks } from './filters.js';

export async function boot(pageTitle, render) {
  try {
    const data = await loadData();
    setTitle(data, pageTitle);
    const t = data.meta.data_through;
    const note = document.getElementById('footer-note');
    if (note && t) note.textContent = `Data through ${t.season}, week ${t.week} · Sleeper${data.meta.platforms.includes('yahoo') ? ' + Yahoo' : ''}`;
    updateNavLinks(location.search.replace(/^\?/, '').split('&').filter((p) => !/^(a|b)=/.test(p)).join('&'));
    await render(data);
  } catch (err) {
    showError(err);
  }
}

export const pts = (x) => (x ?? 0).toFixed(2);

export const typeBadge = (t) => (t === 'playoff' ? ' <span class="badge po">Playoffs</span>'
  : t === 'consolation' ? ' <span class="badge cons">Consolation</span>' : '');

export const rivalryHref = (a, b) => {
  const q = new URLSearchParams(location.search);
  q.set('a', a);
  q.set('b', b);
  return `rivalry.html?${q}`;
};
