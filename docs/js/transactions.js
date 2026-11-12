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
 * What one team got and gave in a trade, as display items:
 * {player: id} | {pick: {season, round, original}} | {faab: amount}.
 * Roster-room releases (extraDrops) aren't "given" to anyone, so they're left out of `gave`.
 */
export function gotGave(side, tx) {
  const released = new Set(extraDrops(side, tx));
  return {
    got: [...side.adds.map((p) => ({ player: p })),
      ...(side.picks_in || []).map((k) => ({ pick: k })),
      ...(side.faab_in ? [{ faab: side.faab_in }] : [])],
    gave: [...side.drops.filter((p) => !released.has(p)).map((p) => ({ player: p })),
      ...(side.picks_out || []).map((k) => ({ pick: k })),
      ...(side.faab_out ? [{ faab: side.faab_out }] : [])],
  };
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

/** Ranking a move by points per week needs a few weeks, or one lucky week dominates. */
export const MIN_WEEKS_PER_WEEK_RANK = 3;
export const RANKS = { total: 'Total points', week: 'Points per week' };

/** Points gained per scored week (0 when no weeks were scored). */
export const perWeek = (side) => (side.n ? side.pts / side.n : 0);

/** Value used to rank a scored side; null when it can't be ranked that way. */
export function rankValue(side, rank) {
  if (rank !== 'week') return side.pts;
  return (side.n ?? 0) >= MIN_WEEKS_PER_WEEK_RANK ? perWeek(side) : null;
}

/**
 * Per-manager counts, score totals and best/worst trade and pickup. season: number | 'all'.
 * rank picks best/worst by total points ('total') or points per week ('week', min 3 weeks).
 */
export function teamSummary(txs, season, rank = 'total') {
  const by = new Map();
  const row = (m) => {
    if (!by.has(m)) {
      by.set(m, {
        manager: m, trades: 0, pickups: 0, drops: 0, faab: 0, topBid: 0,
        tradePts: 0, tradeWins: 0, tradeWeeks: 0, pickupPts: 0, pickupWins: 0, pickupWeeks: 0,
        bestTrade: null, worstTrade: null, bestPickup: null, worstPickup: null,
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
        r[`${k}Weeks`] += side.n ?? 0;
        const v = rankValue(side, rank);
        if (v === null) continue;
        const move = { tx, side, kind, v };
        const K = k === 'trade' ? 'Trade' : 'Pickup';
        if (!r[`best${K}`] || v > r[`best${K}`].v) r[`best${K}`] = move;
        if (!r[`worst${K}`] || v < r[`worst${K}`].v) r[`worst${K}`] = move;
      }
    }
  }
  for (const r of by.values()) {
    for (const k of ['tradePts', 'pickupPts']) r[k] = Math.round(r[k] * 100) / 100;
    r.tradePerWeek = r.tradeWeeks ? Math.round((r.tradePts / r.tradeWeeks) * 100) / 100 : 0;
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
  // both teams are scored over (nearly) the same weeks; use the longer so a playoff bye can't inflate it
  const weeks = Math.max(a.n ?? 0, b.n ?? 0);
  const marginPerWeek = weeks ? Math.round((margin / weeks) * 100) / 100 : 0;
  return { winner: a.manager, loser: b.manager, margin, marginPerWeek, weeks, winSwing: winsOf(a) - winsOf(b), sides: [a, b] };
}

/** Rows for the "top moves" tables, filtered like the page. */
export function topTrades(txs, f) {
  return txs.filter((tx) => (f.season === 'all' || tx.season === f.season)
    && (f.manager === 'all' || tx.sides.some((s) => s.manager === f.manager)))
    .map((tx) => ({ tx, v: tradeVerdict(tx) }))
    .filter((r) => r.v && (f.rank !== 'week' || r.v.weeks >= MIN_WEEKS_PER_WEEK_RANK))
    .sort((a, b) => (f.rank === 'week' ? b.v.marginPerWeek - a.v.marginPerWeek : b.v.margin - a.v.margin));
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
    rank: q.get('rank') === 'week' ? 'week' : 'total',
  };
}

export function stateToQuery(st) {
  const q = new URLSearchParams();
  if (st.manager !== 'all') q.set('m', st.manager);
  if (st.season !== 'all') q.set('season', st.season);
  if (st.kinds.size !== Object.keys(KINDS).length) q.set('kinds', [...st.kinds].join(','));
  if (st.rank === 'week') q.set('rank', 'week');
  return q.toString();
}
