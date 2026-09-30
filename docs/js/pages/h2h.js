import * as S from '../stats.js';
import { applyFilters, mountFilters } from '../filters.js';
import { esc } from '../table.js';
import { boot, pts, rivalryHref } from '../ui.js';

boot('Head-to-head', (data) => {
  const grid = document.getElementById('grid');
  const info = document.getElementById('cell-info');
  const shortName = (id) => data.name(id);

  const draw = (f) => {
    const games = applyFilters(data.games, f);
    const m = S.h2hMatrix(games);
    const ids = [...m.keys()].sort((a, b) => shortName(a).localeCompare(shortName(b), undefined, { sensitivity: 'base' }));
    if (!ids.length) {
      grid.innerHTML = '<p class="empty">No games match these filters.</p>';
      return;
    }
    const head = ids.map((id) => {
      const man = data.byId.get(id);
      return `<th scope="col"><span class="col-name" title="${esc(shortName(id))}">${esc(shortName(id))}${man && !man.active ? '*' : ''}</span></th>`;
    }).join('');
    const body = ids.map((a) => {
      const man = data.byId.get(a);
      const cells = ids.map((b) => {
        if (a === b) return '<td class="diag" aria-hidden="true"></td>';
        const rec = m.get(a).get(b);
        if (!rec) return '<td class="none">—</td>';
        const pct = S.winPct(rec);
        // -1 (always lost) .. +1 (always won); drives the background tint
        const lean = ((pct - 0.5) * 2).toFixed(2);
        const tip = `${shortName(a)} vs ${shortName(b)}: ${S.formatRecord(rec)} in ${rec.games} game${rec.games === 1 ? '' : 's'} · points ${pts(rec.pf)}–${pts(rec.pa)}`;
        return `<td class="rec" style="--lean:${lean}"><a href="${rivalryHref(a, b)}" title="${esc(tip)}" data-tip="${esc(tip)}">${S.formatRecord(rec)}</a></td>`;
      }).join('');
      return `<tr><th scope="row">${esc(shortName(a))}${man && !man.active ? '<span class="former">*</span>' : ''}</th>${cells}</tr>`;
    }).join('');
    const anyFormer = ids.some((id) => data.byId.get(id) && !data.byId.get(id).active);
    grid.innerHTML = `<div class="table-wrap h2h-wrap"><table class="h2h"><thead><tr><th class="corner"></th>${head}</tr></thead><tbody>${body}</tbody></table></div>
      ${anyFormer ? '<p class="fine">* former member</p>' : ''}`;
  };

  const show = (e) => {
    const a = e.target.closest('a[data-tip]');
    if (a) info.textContent = a.dataset.tip;
  };
  grid.addEventListener('mouseover', show);
  grid.addEventListener('focusin', show);

  mountFilters(document.getElementById('filters'),
    { seasons: data.seasons.map((s) => s.season), platforms: data.meta.platforms }, draw);
});
