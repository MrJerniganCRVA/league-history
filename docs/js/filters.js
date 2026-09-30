// Shared filter bar. State lives in the URL query string so filtered views can be shared
// and carry across pages.

export const GAME_TYPES = {
  rp: { label: 'Regular + Playoffs', types: ['regular', 'playoff'] },
  reg: { label: 'Regular season', types: ['regular'] },
  po: { label: 'Playoffs', types: ['playoff'] },
  all: { label: 'All (incl. consolation)', types: ['regular', 'playoff', 'consolation'] },
};

export function defaultFilters(seasons) {
  return { from: Math.min(...seasons), to: Math.max(...seasons), platform: 'all', type: 'rp' };
}

export function readFilters(search, seasons) {
  const d = defaultFilters(seasons);
  const q = new URLSearchParams(search);
  const num = (k) => (q.has(k) && !Number.isNaN(+q.get(k)) ? +q.get(k) : d[k]);
  const f = {
    from: num('from'),
    to: num('to'),
    platform: ['all', 'yahoo', 'sleeper'].includes(q.get('platform')) ? q.get('platform') : d.platform,
    type: GAME_TYPES[q.get('type')] ? q.get('type') : d.type,
  };
  if (f.from > f.to) [f.from, f.to] = [f.to, f.from];
  return f;
}

/** Query string with only the non-default values (keeps links short). */
export function filtersToQuery(f, seasons) {
  const d = defaultFilters(seasons);
  const q = new URLSearchParams();
  for (const k of ['from', 'to', 'platform', 'type']) if (f[k] !== d[k]) q.set(k, f[k]);
  return q.toString();
}

/** Pure: games matching the filters. */
export function applyFilters(games, f) {
  const types = GAME_TYPES[f.type].types;
  return games.filter((g) => g.season >= f.from && g.season <= f.to
    && (f.platform === 'all' || g.platform === f.platform)
    && types.includes(g.game_type));
}

/**
 * Render the filter bar into `el`. Calls onChange(filters) now and on every change.
 * `keep` lists extra query params (e.g. rivalry's a/b) to preserve in the URL.
 */
export function mountFilters(el, { seasons, platforms }, onChange, keep = []) {
  const years = [...new Set(seasons)].sort((a, b) => a - b);
  let f = readFilters(location.search, years);
  const opts = (vals, cur, label = (v) => v) =>
    vals.map((v) => `<option value="${v}"${String(v) === String(cur) ? ' selected' : ''}>${label(v)}</option>`).join('');
  const showPlatform = platforms.length > 1;
  el.innerHTML = `
    <form class="filters" aria-label="Filters">
      <label>From <select name="from">${opts(years, f.from)}</select></label>
      <label>To <select name="to">${opts(years, f.to)}</select></label>
      ${showPlatform ? `<label>Platform <select name="platform">${opts(['all', ...platforms], f.platform,
        (v) => ({ all: 'All', yahoo: 'Yahoo', sleeper: 'Sleeper' }[v] || v))}</select></label>` : ''}
      <label>Games <select name="type">${opts(Object.keys(GAME_TYPES), f.type, (k) => GAME_TYPES[k].label)}</select></label>
      <button type="button" class="reset">Reset</button>
    </form>`;
  const form = el.querySelector('form');

  const sync = () => {
    const q = new URLSearchParams(filtersToQuery(f, years));
    const cur = new URLSearchParams(location.search);
    for (const k of keep) if (cur.has(k)) q.set(k, cur.get(k));
    const qs = q.toString();
    history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
    updateNavLinks(filtersToQuery(f, years));
    onChange(f);
  };
  form.addEventListener('change', () => {
    const fd = new FormData(form);
    f = readFilters(new URLSearchParams([...fd].map(([k, v]) => [k, String(v)])).toString(), years);
    if (!showPlatform) f.platform = 'all';
    sync();
  });
  form.querySelector('.reset').addEventListener('click', () => {
    f = defaultFilters(years);
    for (const k of ['from', 'to', 'platform', 'type']) if (form.elements[k]) form.elements[k].value = f[k];
    sync();
  });
  sync();
}

/** Nav links carry the current filters between pages. */
export function updateNavLinks(query) {
  for (const a of document.querySelectorAll('a[data-keep-filters]')) {
    const base = a.getAttribute('href').split('?')[0];
    a.setAttribute('href', query ? `${base}?${query}` : base);
  }
}
