import { loadTransactions, managerLabel } from '../data.js';
import { updateNavLinks } from '../filters.js';
import { renderTable, esc } from '../table.js';
import { boot } from '../ui.js';
import * as T from '../transactions.js';

const fmtDate = (ts) => new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
const KIND_BADGE = { trade: 'Trade', pickup: 'Pickup', drop: 'Drop' };
const signed = (x, d = 1) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(x).toFixed(d)}`;
const winsText = (w) => `${signed(w, w % 1 ? 1 : 0)} W`;
const tone = (x) => (x > 0 ? 'up' : x < 0 ? 'down' : 'flat');

/** "+13.0 pts · +1 W" chip for a scored side; empty for moves that aren't scored. */
function scoreChip(side) {
  if (!T.isScored(side)) return '';
  const w = T.winsOf(side);
  const po = side.po_wins ? ` <span class="po-note">(${signed(side.po_wins, 0)} in playoffs)</span>` : '';
  return `<span class="score ${tone(side.pts)}" title="Points and wins gained from the best possible lineup in the weeks after this move">${signed(side.pts)} pts · <span class="${tone(w)}">${winsText(w)}</span>${po}</span>`;
}

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
      <div class="trade-who">${who(s.manager)} got ${scoreChip(s)}</div>
      <ul class="moves">${list(s.adds, 'add', '+')}
        ${s.picks_in ? `<li class="add"><span class="sign">+</span>Pick: ${picks(s.picks_in)}</li>` : ''}
        ${s.faab_in ? `<li class="add"><span class="sign">+</span>$${s.faab_in} FAAB</li>` : ''}
        ${!s.adds.length && !s.picks_in && !s.faab_in ? '<li class="muted">Nothing</li>' : ''}
        ${list(T.extraDrops(s, tx), 'drop', '−')}
      </ul>
      ${T.isScored(s) && s.adds.length ? `<div class="fine">Started for ${who(s.manager)}: ${s.started.toFixed(1)} pts</div>` : ''}
    </div>`;

  const weekStrip = (tx) => {
    const scored = tx.sides.filter((s) => s.weeks?.length);
    if (!scored.length) return '';
    const weeks = [...new Set(scored.flatMap((s) => s.weeks.map(([w]) => w)))].sort((a, b) => a - b);
    const cell = (s, w) => {
      const g = s.weeks.find(([x]) => x === w)?.[1];
      return g === undefined ? '<td class="muted">–</td>' : `<td class="num ${tone(g)}">${signed(g)}</td>`;
    };
    return `<details class="wk-strip"><summary>Week by week</summary><div class="table-wrap"><table>
      <thead><tr><th>Team</th>${weeks.map((w) => `<th class="num">Wk ${w}</th>`).join('')}</tr></thead>
      <tbody>${scored.map((s) => `<tr><td>${who(s.manager)}</td>${weeks.map((w) => cell(s, w)).join('')}</tr>`).join('')}</tbody>
    </table></div></details>`;
  };

  const verdictLine = (tx) => {
    const v = T.tradeVerdict(tx);
    if (!v) return tx.sides.some(T.isScored) ? '<p class="verdict">Dead even.</p>' : '';
    const sw = Math.abs(v.winSwing);
    return `<p class="verdict">${who(v.winner)} won this trade by <strong>${v.margin.toFixed(1)} pts</strong>${sw ? ` and ${sw} win${sw === 1 ? '' : 's'}` : ''}.</p>`;
  };

  const item = ({ tx, side, kind, others }) => {
    const head = `<span class="when">${fmtDate(tx.ts)}</span> <span class="badge k-${kind}">${KIND_BADGE[kind]}</span>`
      + `${tx.type === 'commissioner' ? ' <span class="badge">Commish</span>' : ''}`
      + `${side.bid != null ? ` <span class="bid">$${side.bid}</span>` : ''}`
      + `${tx.type === 'free_agent' && kind === 'pickup' ? ' <span class="muted">free agent</span>' : ''}`;
    if (kind === 'trade') {
      const sides = st.manager === 'all' ? tx.sides : [side, ...others];
      return `<li class="tx">${head}<div class="trade">${sides.map(tradeSide(tx)).join('')}</div>${verdictLine(tx)}${weekStrip(tx)}</li>`;
    }
    return `<li class="tx">${st.manager === 'all' ? `<span class="tx-who">${who(side.manager)}</span> · ` : ''}${head} ${scoreChip(side)}
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
    const scope = st.season === 'all' ? 'All Sleeper seasons' : `${st.season} season`;
    root.innerHTML = `
      <details class="card how">
        <summary>How the scores work</summary>
        <p>Each trade and pickup is scored for every week after it that the team played (regular season and playoffs).
        We fill the <strong>best possible lineup</strong> from the team's real roster, then again from the roster without the move:
        players it brought in are taken out, and players it sent away or dropped are put back. The difference is the
        <strong>points gained</strong>. Lineups are filled slot by slot, so a running back only helps if he beats the RB or FLEX he'd replace.</p>
        <p><strong>Wins gained</strong> counts weeks where the result flips once that difference is taken away (in a trade with that
        week's opponent, from both teams). Who actually started is shown as context only. Draft picks and FAAB in trades aren't scored.
        Players on waivers are scored from their weekly stats.</p>
      </details>
      <section class="card">
        <h2>Trades by team</h2>
        <p class="desc">${esc(scope)}. Pts and W are gained from best possible lineups in the weeks after each trade.</p>
        <div id="summary"></div>
      </section>
      <section class="card">
        <h2>Trades, most lopsided first</h2>
        <p class="desc">Margin is the gap between the two teams' points gained. Tap a column to sort.</p>
        <div id="top-trades"></div>
      </section>
      <section class="card">
        <h2>Pickups by team</h2>
        <p class="desc">${esc(scope)}. Pickups count players added; FAAB is winning waiver bids only.</p>
        <div id="pickup-summary"></div>
      </section>
      <section class="card">
        <h2>Pickups, best first</h2>
        <p class="desc">Sort by Pts the other way for the worst ones.</p>
        <div id="top-pickups"></div>
      </section>
      <section class="card">
        <h2>${st.manager === 'all' ? 'All transactions' : `${who(st.manager)}'s transactions`}</h2>
        <div id="timeline"></div>
      </section>`;
    const ptsCol = (key, label) => ({ key, label, num: true, format: (v) => `<span class="${tone(v)}">${signed(v)}</span>` });
    const winCol = (key, label) => ({ key, label, num: true, format: (v) => `<span class="${tone(v)}">${signed(v, v % 1 ? 1 : 0)}</span>` });
    const names = (s) => esc(s.adds.map((p) => players[p]?.name ?? p).join(', ') || 'picks/FAAB');
    const moveText = (m) => (m ? `<span class="move">${m.tx.season} wk ${m.tx.week}: ${names(m.side)} <span class="${tone(m.side.pts)}">(${signed(m.side.pts)})</span></span>` : '—');
    const managerCol = { key: 'manager', label: 'Team', format: (v) => `<a href="?${new URLSearchParams({ ...Object.fromEntries(new URLSearchParams(T.stateToQuery(st))), m: v })}" data-m="${esc(v)}">${who(v)}</a>`, sort: (r) => data.name(r.manager) };
    const moveCol = (key, label) => ({ key, label, format: moveText, sort: (r) => r[key]?.side.pts ?? 0 });
    renderTable(document.getElementById('summary'), {
      rows: summary.filter((r) => r.trades).sort((a, b) => b.tradePts - a.tradePts),
      pageSize: 20,
      empty: 'No trades match these filters.',
      columns: [
        managerCol,
        { key: 'trades', label: 'Trades', num: true },
        ptsCol('tradePts', 'Trade pts'),
        winCol('tradeWins', 'Trade W'),
        moveCol('bestTrade', 'Best trade'),
        moveCol('worstTrade', 'Worst trade'),
      ],
    });
    renderTable(document.getElementById('pickup-summary'), {
      rows: summary.filter((r) => r.pickups || r.drops).sort((a, b) => b.pickupPts - a.pickupPts),
      pageSize: 20,
      empty: 'No pickups match these filters.',
      columns: [
        managerCol,
        { key: 'pickups', label: 'Pickups', num: true },
        ptsCol('pickupPts', 'Pickup pts'),
        winCol('pickupWins', 'Pickup W'),
        { key: 'drops', label: 'Drops', num: true },
        { key: 'faab', label: 'FAAB', num: true, format: (v) => `$${v}` },
        moveCol('bestPickup', 'Best pickup'),
      ],
    });
    renderTable(document.getElementById('top-trades'), {
      rows: T.topTrades(transactions, st).map(({ tx, v }) => ({
        season: tx.season, week: tx.week, winner: v.winner, loser: v.loser, margin: v.margin, swing: v.winSwing,
        wGot: names(v.sides[0]), lGot: names(v.sides[1]),
      })),
      pageSize: 10,
      empty: 'No scored trades match these filters.',
      columns: [
        { key: 'season', label: 'Season', num: true },
        { key: 'week', label: 'Wk', num: true },
        { key: 'winner', label: 'Won', format: (v, r) => `${who(v)} <span class="fine">got ${r.wGot}</span>`, sort: (r) => data.name(r.winner) },
        { key: 'loser', label: 'Lost', format: (v, r) => `${who(v)} <span class="fine">got ${r.lGot}</span>`, sort: (r) => data.name(r.loser) },
        { key: 'margin', label: 'Margin', num: true, format: (v) => v.toFixed(1) },
        winCol('swing', 'Win swing'),
      ],
    });
    renderTable(document.getElementById('top-pickups'), {
      rows: T.topPickups(transactions, st).map(({ tx, side }) => ({
        season: tx.season, week: tx.week, manager: side.manager, player: names(side), bid: side.bid,
        pts: side.pts, wins: T.winsOf(side),
      })),
      pageSize: 10,
      empty: 'No scored pickups match these filters.',
      columns: [
        { key: 'season', label: 'Season', num: true },
        { key: 'week', label: 'Wk', num: true },
        { key: 'manager', label: 'Manager', format: who, sort: (r) => data.name(r.manager) },
        { key: 'player', label: 'Added', format: (v) => v },
        { key: 'bid', label: 'Bid', num: true, format: (v) => (v == null ? 'FA' : `$${v}`), sort: (r) => r.bid ?? -1 },
        ptsCol('pts', 'Pts'),
        winCol('wins', 'W'),
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
