import * as S from '../stats.js';
import { applyFilters, mountFilters } from '../filters.js';
import { managerLabel } from '../data.js';
import { renderTable, esc } from '../table.js';
import { boot, pts, typeBadge } from '../ui.js';

boot('Rivalry', (data) => {
  const root = document.getElementById('rivalry');
  const form = document.getElementById('pickers');
  const who = (id) => managerLabel(data, id);
  const ids = data.managers.map((m) => m.manager_id);
  const q = new URLSearchParams(location.search);
  let a = ids.includes(q.get('a')) ? q.get('a') : ids[0];
  let b = ids.includes(q.get('b')) && q.get('b') !== a ? q.get('b') : ids.find((id) => id !== a);
  let filters;

  const options = (cur) => data.managers.map((m) =>
    `<option value="${esc(m.manager_id)}"${m.manager_id === cur ? ' selected' : ''}>${esc(m.display_name)}${m.active ? '' : ' (former)'}</option>`).join('');

  const winLine = (p, winner, loser) => (p
    ? `${pts(Math.abs(p.margin))} pts — ${who(winner)} ${pts(Math.max(p.score, p.opp_score))}, ${who(loser)} ${pts(Math.min(p.score, p.opp_score))} <span class="when">(${p.season}, wk ${p.week}${p.game_type === 'playoff' ? ', playoffs' : ''})</span>`
    : '<span class="muted">Never</span>');

  const draw = () => {
    form.a.innerHTML = options(a);
    form.b.innerHTML = options(b);
    const u = new URLSearchParams(location.search);
    u.set('a', a);
    u.set('b', b);
    history.replaceState(null, '', `?${u}`);
    document.title = `${data.name(a)} vs ${data.name(b)} · ${data.meta.site_title}`;

    if (a === b) {
      root.innerHTML = '<p class="empty">Pick two different managers.</p>';
      return;
    }
    const r = S.rivalry(applyFilters(data.games, filters), a, b);
    if (!r.log.length) {
      root.innerHTML = `<p class="empty">${who(a)} and ${who(b)} haven't played each other with these filters.</p>`;
      return;
    }
    const lead = r.overall.w > r.overall.l ? a : r.overall.l > r.overall.w ? b : null;
    const streak = r.streak.holder === 'tie'
      ? `${r.streak.length} straight tie${r.streak.length > 1 ? 's' : ''}`
      : `${who(r.streak.holder)} has won ${r.streak.length} straight`;
    const avg = r.avgMargin === 0 ? 'Dead even'
      : `${who(r.avgMargin > 0 ? a : b)} by ${pts(Math.abs(r.avgMargin))}`;
    root.innerHTML = `
      <section class="card score-card">
        <div class="side"><span class="nm">${who(a)}</span><span class="big">${r.overall.w}</span></div>
        <div class="mid"><span class="big dash">–</span>${r.overall.t ? `<span class="ties">${r.overall.t} tie${r.overall.t > 1 ? 's' : ''}</span>` : ''}</div>
        <div class="side"><span class="nm">${who(b)}</span><span class="big">${r.overall.l}</span></div>
        <p class="lead-line">${lead ? `${who(lead)} leads the series` : 'Series is tied'} · ${r.overall.games} game${r.overall.games > 1 ? 's' : ''}</p>
      </section>
      <section class="card">
        <dl class="facts-grid">
          <div><dt>Playoff record</dt><dd>${r.playoff.games ? `${who(a)} ${S.formatRecord(r.playoff)}` : '<span class="muted">Never met in the playoffs</span>'}</dd></div>
          <div><dt>Total points</dt><dd>${who(a)} ${pts(r.pointsA)} · ${who(b)} ${pts(r.pointsB)}</dd></div>
          <div><dt>Average margin</dt><dd>${avg}</dd></div>
          <div><dt>Current streak</dt><dd>${streak}</dd></div>
          <div><dt>Biggest ${esc(data.name(a))} win</dt><dd>${winLine(r.biggestWinA, a, b)}</dd></div>
          <div><dt>Biggest ${esc(data.name(b))} win</dt><dd>${winLine(r.biggestWinB, b, a)}</dd></div>
        </dl>
      </section>
      <section class="card"><h2>Game log</h2><div id="log"></div></section>`;
    renderTable(document.getElementById('log'), {
      rows: r.log,
      pageSize: 20,
      columns: [
        { key: 'season', label: 'Season', num: true },
        { key: 'week', label: 'Wk', num: true, format: (v, row) => `${v}${typeBadge(row.game_type)}` },
        { key: 'result', label: 'Winner', format: (v) => (v === 'W' ? who(a) : v === 'L' ? who(b) : '<span class="badge">Tie</span>') },
        { key: 'score', label: data.name(a), num: true, format: pts },
        { key: 'opp_score', label: data.name(b), num: true, format: pts },
        { key: 'margin', label: 'Margin', num: true, format: (v) => pts(Math.abs(v)), sort: (row) => Math.abs(row.margin) },
      ],
    });
  };

  form.addEventListener('change', () => {
    a = form.a.value;
    b = form.b.value;
    draw();
  });

  mountFilters(document.getElementById('filters'),
    { seasons: data.seasons.map((s) => s.season), platforms: data.meta.platforms },
    (f) => { filters = f; draw(); }, ['a', 'b']);
});
