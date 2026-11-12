// Pure helpers for the Transactions page (no DOM), so they can be unit-tested with node --test.

export const KINDS = {
  trade: 'Trades',
  pickup: 'Pickups',
  drop: 'Drops',
};

/** What a move was for one team: a trade, a pickup (added someone) or a plain drop. */
export function sideKind(tx, side) {
  if (tx.type === 'trade') return 'trade';
  return side.adds.length ? 'pickup' : 'drop';
}

/** Players a team released in a trade to make roster room (dropped, but not sent to anyone). */
export function extraDrops(side, tx) {
  const sent = new Set(tx.sides.filter((s) => s !== side).flatMap((s) => s.adds));
  return side.drops.filter((p) => !sent.has(p));
}

/**
 * One row per (transaction, team) matching the filters, oldest first.
 * f = { manager: id | 'all', season: number | 'all', kinds: Set of KINDS keys }
 */
export function timeline(txs, f) {
  const rows = [];
  for (const tx of txs) {
    if (f.season !== 'all' && tx.season !== f.season) continue;
    tx.sides.forEach((side, i) => {
      if (f.manager !== 'all' && side.manager !== f.manager) return;
      const kind = sideKind(tx, side);
      if (!f.kinds.has(kind)) return;
      // a trade shows once in the league-wide feed, from its first side
      if (f.manager === 'all' && kind === 'trade' && i > 0) return;
      rows.push({ tx, side, kind, others: tx.sides.filter((s) => s !== side) });
    });
  }
  return rows.sort((a, b) => a.tx.season - b.tx.season || a.tx.ts - b.tx.ts);
}

/** Wins gained, regular season plus playoffs. */
export const winsOf = (side) => (side.wins ?? 0) + (side.po_wins ?? 0);
export const isScored = (side) => side.pts !== undefined;

/** Per-manager counts and score totals for the summary table. season: number | 'all'. */
export function teamSummary(txs, season) {
  const by = new Map();
  const row = (m) => {
    if (!by.has(m)) {
      by.set(m, {
        manager: m, trades: 0, pickups: 0, drops: 0, faab: 0, topBid: 0,
        tradePts: 0, tradeWins: 0, pickupPts: 0, pickupWins: 0, best: null, worst: null,
      });
    }
    return by.get(m);
  };
  for (const tx of txs) {
    if (season !== 'all' && tx.season !== season) continue;
    for (const side of tx.sides) {
      const r = row(side.manager);
      const kind = sideKind(tx, side);
      if (kind === 'trade') r.trades += 1;
      else if (kind === 'pickup') r.pickups += side.adds.length;
      r.drops += kind === 'trade' ? 0 : side.drops.length;
      if (side.bid) {
        r.faab += side.bid;
        r.topBid = Math.max(r.topBid, side.bid);
      }
      if (isScored(side)) {
        const k = kind === 'trade' ? 'trade' : 'pickup';
        r[`${k}Pts`] += side.pts;
        r[`${k}Wins`] += winsOf(side);
        const move = { tx, side, kind };
        if (!r.best || side.pts > r.best.side.pts) r.best = move;
        if (!r.worst || side.pts < r.worst.side.pts) r.worst = move;
      }
    }
  }
  for (const r of by.values()) {
    for (const k of ['tradePts', 'pickupPts']) r[k] = Math.round(r[k] * 100) / 100;
  }
  return [...by.values()];
}

/** Who came out ahead in a scored two-team trade, by points gained. null if not scored or even. */
export function tradeVerdict(tx) {
  const scored = tx.sides.filter(isScored);
  if (tx.type !== 'trade' || scored.length < 2) return null;
  const [a, b] = [...scored].sort((x, y) => y.pts - x.pts);
  const margin = Math.round((a.pts - b.pts) * 100) / 100;
  if (margin === 0) return null;
  return { winner: a.manager, loser: b.manager, margin, winSwing: winsOf(a) - winsOf(b), sides: [a, b] };
}

/** Rows for the "top moves" tables, filtered like the page. */
export function topTrades(txs, f) {
  return txs.filter((tx) => (f.season === 'all' || tx.season === f.season)
    && (f.manager === 'all' || tx.sides.some((s) => s.manager === f.manager)))
    .map((tx) => ({ tx, v: tradeVerdict(tx) }))
    .filter((r) => r.v)
    .sort((a, b) => b.v.margin - a.v.margin);
}

export function topPickups(txs, f) {
  const rows = [];
  for (const tx of txs) {
    if (f.season !== 'all' && tx.season !== f.season) continue;
    for (const side of tx.sides) {
      if (f.manager !== 'all' && side.manager !== f.manager) continue;
      if (sideKind(tx, side) === 'pickup' && isScored(side)) rows.push({ tx, side });
    }
  }
  return rows.sort((a, b) => b.side.pts - a.side.pts);
}

export function txSeasons(txs) {
  return [...new Set(txs.map((t) => t.season))].sort((a, b) => b - a);
}

/** Read page state from the query string; unknown values fall back to defaults. */
export function readState(search, { managers, seasons }) {
  const q = new URLSearchParams(search);
  const m = q.get('m');
  const s = Number(q.get('season'));
  const kinds = (q.get('kinds') || '').split(',').filter((k) => k in KINDS);
  return {
    manager: managers.includes(m) ? m : 'all',
    season: seasons.includes(s) ? s : 'all',
    kinds: new Set(kinds.length ? kinds : Object.keys(KINDS)),
  };
}

export function stateToQuery(st) {
  const q = new URLSearchParams();
  if (st.manager !== 'all') q.set('m', st.manager);
  if (st.season !== 'all') q.set('season', st.season);
  if (st.kinds.size !== Object.keys(KINDS).length) q.set('kinds', [...st.kinds].join(','));
  return q.toString();
}
