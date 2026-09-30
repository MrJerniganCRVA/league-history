import * as S from '../stats.js';
import { applyFilters, mountFilters } from '../filters.js';
import { managerLabel } from '../data.js';
import { renderTable, esc } from '../table.js';
import { boot, pts, typeBadge } from '../ui.js';

boot('Records', (data) => {
  const root = document.getElementById('records');
  const who = (id) => managerLabel(data, id);
  const num = (key, label = 'Score') => ({ key, label, num: true, format: pts });
  const when = [
    { key: 'season', label: 'Season', num: true },
    { key: 'week', label: 'Wk', num: true, format: (v, r) => `${v}${typeBadge(r.game_type)}` },
  ];
  const perfCols = [...when,
    { key: 'manager', label: 'Manager', format: who },
    { key: 'opponent', label: 'Opponent', format: who },
    num('score'), num('opp_score', 'Opp')];
  const marginCols = [...when,
    { key: 'winner', label: 'Winner', format: (v, r) => (r.tie ? `${who(v)} <span class="badge">Tie</span>` : who(v)) },
    { key: 'loser', label: 'Loser', format: who },
    { key: 'winner_score', label: 'Score', num: true, format: (v, r) => `${pts(v)}–${pts(r.loser_score)}`, sort: (r) => r.winner_score },
    num('margin', 'Margin')];

  // [id, title, description, columns, (games, scope) => rows, scoped?]
  const sections = [
    ['highest', 'Highest single-game score', 'The biggest weeks in league history.', perfCols, S.highestScores, true],
    ['lowest', 'Lowest single-game score', 'The weeks everyone would like to forget.', perfCols, S.lowestScores, true],
    ['blowouts', 'Biggest blowouts', 'Largest margin of victory.', marginCols, S.blowouts],
    ['closest', 'Closest games', 'Smallest margins, ties included.', marginCols, S.closestGames],
    ['highloss', 'Highest score in a loss', 'Scored big, lost anyway.', perfCols, S.highestScoreInLoss],
    ['lowwin', 'Lowest score in a win', 'Won ugly.', perfCols, S.lowestScoreInWin],
    ['weeklylow', "Weekly lowest scorer", "How many times each manager had the week's lowest score (shared lows count for everyone tied).",
      [{ key: 'manager', label: 'Manager', format: who }, { key: 'count', label: 'Times', num: true }], S.weeklyLowCounts],
    ['seasonpts', 'Season points for & against', 'Every manager, every season. Tap a column header to sort.',
      [{ key: 'season', label: 'Season', num: true }, { key: 'manager', label: 'Manager', format: who },
        { key: 'w', label: 'Record', format: (v, r) => S.formatRecord(r), sort: (r) => S.winPct(r) },
        num('pf', 'PF'), num('pa', 'PA')], S.seasonPointsForAgainst],
  ];
  const scopes = { all: 'All-time', season: 'By season', manager: 'By manager' };
  const scopeState = {};

  root.innerHTML = `<nav class="jump" aria-label="Jump to record">${sections.map(([id, t]) => `<a href="#${id}">${esc(t)}</a>`).join('')}</nav>`
    + sections.map(([id, title, desc, , , scoped]) => `
    <section class="card" id="${id}">
      <h2>${esc(title)}</h2>
      <p class="desc">${esc(desc)}</p>
      ${scoped ? `<div class="seg" role="tablist">${Object.entries(scopes).map(([k, l]) =>
        `<button type="button" role="tab" data-scope="${k}" aria-selected="${k === 'all'}">${l}</button>`).join('')}</div>` : ''}
      <div class="extra"></div>
      <div class="tbl"></div>
    </section>`).join('');

  let games = [];
  const drawSection = ([id, , , columns, fn, scoped]) => {
    const sec = document.getElementById(id);
    const scope = scopeState[id] || 'all';
    sec.querySelectorAll('[data-scope]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.scope === scope)));
    const rows = scoped ? fn(games, scope) : fn(games);
    if (id === 'seasonpts' && rows.length) {
      const complete = rows.filter((r) => r.games > 0);
      const hi = complete.reduce((a, b) => (b.pf > a.pf ? b : a));
      const lo = complete.reduce((a, b) => (b.pf < a.pf ? b : a));
      sec.querySelector('.extra').innerHTML = `<p class="callouts">
        <span><b>Most points in a season:</b> ${who(hi.manager)}, ${pts(hi.pf)} (${hi.season})</span>
        <span><b>Fewest:</b> ${who(lo.manager)}, ${pts(lo.pf)} (${lo.season})</span></p>
        <p class="fine">Totals follow the filters above, so the current season is only partly counted.</p>`;
    } else {
      sec.querySelector('.extra').innerHTML = '';
    }
    renderTable(sec.querySelector('.tbl'), { columns, rows });
  };

  root.addEventListener('click', (e) => {
    const b = e.target.closest('[data-scope]');
    if (!b) return;
    const sec = b.closest('section');
    scopeState[sec.id] = b.dataset.scope;
    drawSection(sections.find((s) => s[0] === sec.id));
  });

  mountFilters(document.getElementById('filters'),
    { seasons: data.seasons.map((s) => s.season), platforms: data.meta.platforms },
    (f) => {
      games = applyFilters(data.games, f);
      sections.forEach(drawSection);
    });
});
