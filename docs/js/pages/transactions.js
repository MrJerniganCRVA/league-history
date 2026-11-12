import { loadTransactions, managerLabel } from '../data.js';
import { updateNavLinks } from '../filters.js';
import { renderTable, esc } from '../table.js';
import { boot } from '../ui.js';
import * as T from '../transactions.js';

const fmtDate = (ts) => new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
const KIND_BADGE = { trade: 'Trade', pickup: 'Pickup', drop: 'Drop' };

boot('Transactions', async (data) => {
  const { players, transactions } = await loadTransactions();
  const root = document.getElementById('transactions');
  const form = document.getElementById('tx-filters');
  const who = (id) => managerLabel(data, id);
  const seasons = T.txSeasons(transactions);
  const ids = data.managers.map((m) => m.manager_id);
  let st = T.readState(location.search, { managers: ids, seasons });
  // this page's own filters don't apply elsewhere; nav links go to the default views
  updateNavLinks('');

  const player = (pid) => {
    const p = players[pid] || { name: pid, pos: '?' };
    return `${esc(p.name)} <span class="pos">${esc(p.pos)}${p.team ? ` · ${esc(p.team)}` : ''}</span>`;
  };
  const list = (pids, cls, sign) => pids.map((p) => `<li class="${cls}"><span class="sign" aria-hidden="true">${sign}</span>${player(p)}</li>`).join('');
  const picks = (ps) => ps.map((p) => `${p.season} round ${p.round}${p.original ? ` (${who(p.original)})` : ''}`).join(', ');

  const tradeSide = (tx) => (s) => `
    <div class="trade-side">
      <div class="trade-who">${who(s.manager)} got</div>
      <ul class="moves">${list(s.adds, 'add', '+')}
        ${s.picks_in ? `<li class="add"><span class="sign">+</span>Pick: ${picks(s.picks_in)}</li>` : ''}
        ${s.faab_in ? `<li class="add"><span class="sign">+</span>$${s.faab_in} FAAB</li>` : ''}
        ${!s.adds.length && !s.picks_in && !s.faab_in ? '<li class="muted">Nothing</li>' : ''}
        ${list(T.extraDrops(s, tx), 'drop', '−')}
      </ul>
    </div>`;

  const item = ({ tx, side, kind, others }) => {
    const head = `<span class="when">${fmtDate(tx.ts)}</span> <span class="badge k-${kind}">${KIND_BADGE[kind]}</span>`
      + `${tx.type === 'commissioner' ? ' <span class="badge">Commish</span>' : ''}`
      + `${side.bid != null ? ` <span class="bid">$${side.bid}</span>` : ''}`
      + `${tx.type === 'free_agent' && kind === 'pickup' ? ' <span class="muted">free agent</span>' : ''}`;
    if (kind === 'trade') {
      const sides = st.manager === 'all' ? tx.sides : [side, ...others];
      return `<li class="tx">${head}<div class="trade">${sides.map(tradeSide(tx)).join('')}</div></li>`;
    }
    return `<li class="tx">${st.manager === 'all' ? `<span class="tx-who">${who(side.manager)}</span> · ` : ''}${head}
      <ul class="moves">${list(side.adds, 'add', '+')}${list(side.drops, 'drop', '−')}</ul></li>`;
  };

  const drawTimeline = (el) => {
    const rows = T.timeline(transactions, st);
    if (!rows.length) {
      el.innerHTML = `<p class="empty">No moves${st.manager === 'all' ? '' : ` for ${who(st.manager)}`}${st.season === 'all' ? '' : ` in ${st.season}`} with these filters.</p>`;
      return;
    }
    // newest season first, then oldest-to-newest within the season
    const bySeason = new Map();
    for (const r of rows) {
      const k = r.tx.season;
      if (!bySeason.has(k)) bySeason.set(k, new Map());
      const weeks = bySeason.get(k);
      if (!weeks.has(r.tx.week)) weeks.set(r.tx.week, []);
      weeks.get(r.tx.week).push(r);
    }
    const limit = 150;
    let shown = 0;
    let html = '';
    for (const season of [...bySeason.keys()].sort((a, b) => b - a)) {
      html += `<h3 class="tl-season">${season}</h3>`;
      for (const [week, items] of bySeason.get(season)) {
        if (shown >= limit) break;
        html += `<div class="tl-week"><div class="tl-wk">Week ${week}</div><ol class="tl">${items.map(item).join('')}</ol></div>`;
        shown += items.length;
      }
      if (shown >= limit) break;
    }
    const more = rows.length > shown ? `<p class="fine">Showing the first ${shown} of ${rows.length}. Pick a team or season to narrow it down.</p>` : '';
    el.innerHTML = html + more;
  };

  const draw = () => {
    const qs = T.stateToQuery(st);
    history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
    const summary = T.teamSummary(transactions, st.season)
      .filter((r) => st.manager === 'all' || r.manager === st.manager);
    const scope = st.season === 'all' ? 'all Sleeper seasons' : `${st.season}`;
    root.innerHTML = `
      <section class="card">
        <h2>Team summary</h2>
        <p class="desc">Moves per team, ${esc(scope)}. Pickups count players added; FAAB is winning waiver bids only.</p>
        <div id="summary"></div>
      </section>
      <section class="card">
        <h2>${st.manager === 'all' ? 'All transactions' : `${who(st.manager)}'s transactions`}</h2>
        <div id="timeline"></div>
      </section>`;
    renderTable(document.getElementById('summary'), {
      rows: summary,
      pageSize: 20,
      empty: 'No transactions match these filters.',
      columns: [
        { key: 'manager', label: 'Manager', format: (v) => `<a href="?${new URLSearchParams({ ...Object.fromEntries(new URLSearchParams(T.stateToQuery(st))), m: v })}" data-m="${esc(v)}">${who(v)}</a>`, sort: (r) => data.name(r.manager) },
        { key: 'trades', label: 'Trades', num: true },
        { key: 'pickups', label: 'Pickups', num: true },
        { key: 'drops', label: 'Drops', num: true },
        { key: 'faab', label: 'FAAB spent', num: true, format: (v) => `$${v}` },
        { key: 'topBid', label: 'Top bid', num: true, format: (v) => (v ? `$${v}` : '—') },
      ],
    });
    drawTimeline(document.getElementById('timeline'));
  };

  const fill = () => {
    const opt = (v, label, cur) => `<option value="${esc(v)}"${String(v) === String(cur) ? ' selected' : ''}>${esc(label)}</option>`;
    form.m.innerHTML = opt('all', 'All managers', st.manager)
      + data.managers.map((m) => opt(m.manager_id, `${m.display_name}${m.active ? '' : ' (former)'}`, st.manager)).join('');
    form.season.innerHTML = opt('all', 'All Sleeper seasons', st.season) + seasons.map((s) => opt(s, s, st.season)).join('');
    for (const k of Object.keys(T.KINDS)) form.elements[`k-${k}`].checked = st.kinds.has(k);
  };

  form.addEventListener('change', () => {
    const kinds = Object.keys(T.KINDS).filter((k) => form.elements[`k-${k}`].checked);
    st = {
      manager: form.m.value,
      season: form.season.value === 'all' ? 'all' : Number(form.season.value),
      kinds: new Set(kinds),
    };
    draw();
  });
  root.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-m]');
    if (!a) return;
    e.preventDefault();
    st = { ...st, manager: a.dataset.m };
    fill();
    draw();
    document.getElementById('timeline').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  form.querySelector('.reset').addEventListener('click', () => {
    st = T.readState('', { managers: ids, seasons });
    fill();
    draw();
  });

  fill();
  draw();
});
