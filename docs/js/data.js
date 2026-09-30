// Loads the generated JSON (relative paths: the site is served from /<repo>/ on GitHub Pages).
import { esc } from './table.js';

let cache;

export async function loadData() {
  if (!cache) {
    cache = Promise.all(['games', 'seasons', 'managers'].map((n) =>
      fetch(`./data/${n}.json`).then((r) => {
        if (!r.ok) throw new Error(`Could not load data/${n}.json (${r.status})`);
        return r.json();
      }))).then(([games, seasonsDoc, managers]) => {
      const byId = new Map(managers.map((m) => [m.manager_id, m]));
      return {
        games,
        meta: seasonsDoc.meta,
        seasons: seasonsDoc.seasons,
        managers,
        byId,
        name: (id) => byId.get(id)?.display_name ?? id,
      };
    });
  }
  return cache;
}

/** Manager name with a "(former)" tag for people no longer in the league. */
export function managerLabel(data, id) {
  const m = data.byId.get(id);
  const name = esc(m?.display_name ?? id);
  return m && !m.active ? `${name} <span class="former">(former)</span>` : name;
}

export function setTitle(data, page) {
  document.title = page ? `${page} · ${data.meta.site_title}` : data.meta.site_title;
  for (const h of document.querySelectorAll('[data-site-title]')) h.textContent = data.meta.site_title;
}

export function showError(err) {
  const main = document.querySelector('main');
  main.insertAdjacentHTML('afterbegin', `<p class="error">Couldn't load league data: ${esc(err.message)}</p>`);
  console.error(err);
}
