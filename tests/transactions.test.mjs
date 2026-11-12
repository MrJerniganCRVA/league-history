// Run: node --test tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as T from '../docs/js/transactions.js';

const tx = (id, season, ts, type, sides) => ({ id, season, week: 1, ts, type, sides });
const side = (manager, adds = [], drops = [], extra = {}) => ({ manager, adds, drops, ...extra });
const TXS = [
  tx('a', 2024, 10, 'waiver', [side('A', ['p1'], ['p2'], { bid: 7 })]),
  tx('b', 2024, 20, 'trade', [side('A', ['p3'], ['p4', 'p9']), side('B', ['p4'], ['p3'])]),
  tx('c', 2024, 5, 'free_agent', [side('B', [], ['p5'])]),
  tx('d', 2025, 1, 'waiver', [side('A', ['p6'], [], { bid: 20 })]),
  tx('e', 2025, 2, 'free_agent', [side('B', ['p7', 'p8'], [])]),
];
const all = new Set(Object.keys(T.KINDS));

test('sideKind', () => {
  assert.equal(T.sideKind(TXS[1], TXS[1].sides[0]), 'trade');
  assert.equal(T.sideKind(TXS[0], TXS[0].sides[0]), 'pickup');
  assert.equal(T.sideKind(TXS[2], TXS[2].sides[0]), 'drop');
});

test('timeline: one team, oldest first, trade from that team\'s side', () => {
  const rows = T.timeline(TXS, { manager: 'B', season: 2024, kinds: all });
  assert.deepEqual(rows.map((r) => r.tx.id), ['c', 'b']);
  assert.equal(rows[1].side.manager, 'B');
  assert.equal(rows[1].others[0].manager, 'A');
});

test('timeline: league feed shows each trade once; kinds filter', () => {
  const rows = T.timeline(TXS, { manager: 'all', season: 'all', kinds: all });
  assert.deepEqual(rows.map((r) => r.tx.id), ['c', 'a', 'b', 'd', 'e']);
  const onlyTrades = T.timeline(TXS, { manager: 'all', season: 'all', kinds: new Set(['trade']) });
  assert.deepEqual(onlyTrades.map((r) => r.tx.id), ['b']);
});

test('teamSummary per season and all seasons add up', () => {
  const pick = (rows) => Object.fromEntries(rows.map((r) => [r.manager, [r.trades, r.pickups, r.drops, r.faab, r.topBid]]));
  assert.deepEqual(pick(T.teamSummary(TXS, 2024)), { A: [1, 1, 1, 7, 7], B: [1, 0, 1, 0, 0] });
  assert.deepEqual(pick(T.teamSummary(TXS, 'all')), { A: [1, 2, 1, 27, 20], B: [1, 2, 1, 0, 0] });
});

test('extraDrops: released for roster room, not sent in the trade', () => {
  assert.deepEqual(T.extraDrops(TXS[1].sides[0], TXS[1]), ['p9']);
  assert.deepEqual(T.extraDrops(TXS[1].sides[1], TXS[1]), []);
});

test('state round-trips through the URL and ignores junk', () => {
  const ctx = { managers: ['A', 'B'], seasons: [2025, 2024] };
  const st = T.readState('?m=B&season=2024&kinds=trade,drop', ctx);
  assert.deepEqual([st.manager, st.season, [...st.kinds]], ['B', 2024, ['trade', 'drop']]);
  assert.equal(T.stateToQuery(st), 'm=B&season=2024&kinds=trade%2Cdrop');
  const junk = T.readState('?m=Z&season=1999&kinds=nope', ctx);
  assert.deepEqual([junk.manager, junk.season, junk.kinds.size], ['all', 'all', 3]);
  assert.equal(T.stateToQuery(junk), '');
});

const SCORED = [
  tx('t1', 2024, 1, 'trade', [side('A', ['p1'], ['p2'], { pts: 13, wins: 1, po_wins: 0 }), side('B', ['p2'], ['p1'], { pts: -4, wins: -1, po_wins: 0 })]),
  tx('t2', 2025, 2, 'trade', [side('A', ['p3'], ['p4'], { pts: -2, wins: 0, po_wins: 0 }), side('C', ['p4'], ['p3'], { pts: 30, wins: 1, po_wins: 1 })]),
  tx('w1', 2025, 3, 'waiver', [side('A', ['p5'], ['p6'], { bid: 3, pts: 18, wins: 0, po_wins: 0 })]),
  tx('w2', 2025, 4, 'free_agent', [side('B', ['p7'], [], { pts: -5, wins: 0, po_wins: 0 })]),
  tx('d1', 2025, 5, 'free_agent', [side('B', [], ['p7'])]),
];

test('tradeVerdict: winner by points, swing counts playoff wins', () => {
  const v = T.tradeVerdict(SCORED[1]);
  assert.deepEqual([v.winner, v.loser, v.margin, v.winSwing], ['C', 'A', 32, 2]);
  assert.equal(T.tradeVerdict(SCORED[2]), null);
  assert.equal(T.tradeVerdict(TXS[1]), null); // unscored
});

test('teamSummary totals scores and finds best/worst trade and pickup', () => {
  const a = T.teamSummary(SCORED, 'all').find((r) => r.manager === 'A');
  assert.deepEqual([a.tradePts, a.tradeWins, a.pickupPts, a.pickupWins], [11, 1, 18, 0]);
  assert.deepEqual([a.bestTrade.tx.id, a.worstTrade.tx.id], ['t1', 't2']);
  assert.deepEqual([a.bestPickup.tx.id, a.worstPickup.tx.id], ['w1', 'w1']);
  const b = T.teamSummary(SCORED, 'all').find((r) => r.manager === 'B');
  assert.deepEqual([b.bestTrade.tx.id, b.worstPickup.tx.id], ['t1', 'w2']);
});

test('topTrades and topPickups follow the filters', () => {
  const f = { manager: 'all', season: 'all', kinds: all };
  assert.deepEqual(T.topTrades(SCORED, f).map((r) => r.tx.id), ['t2', 't1']);
  assert.deepEqual(T.topTrades(SCORED, { ...f, manager: 'B' }).map((r) => r.tx.id), ['t1']);
  assert.deepEqual(T.topPickups(SCORED, f).map((r) => r.tx.id), ['w1', 'w2']);
  assert.deepEqual(T.topPickups(SCORED, { ...f, season: 2024 }), []);
});

test('gotGave lists players, picks and FAAB both ways, minus roster-room drops', () => {
  const t = tx('g', 2026, 1, 'trade', [
    side('A', [], ['p1', 'p9'], { faab_in: 11, picks_out: [{ season: 2027, round: 2 }] }),
    side('B', ['p1'], [], { faab_out: 11, picks_in: [{ season: 2027, round: 2 }] }),
  ]);
  assert.deepEqual(T.gotGave(t.sides[0], t), { got: [{ faab: 11 }], gave: [{ player: 'p1' }, { pick: { season: 2027, round: 2 } }] });
  assert.deepEqual(T.gotGave(t.sides[1], t), { got: [{ player: 'p1' }, { pick: { season: 2027, round: 2 } }], gave: [{ faab: 11 }] });
});

test('points per week: verdict, ranking, and the minimum-weeks rule', () => {
  const t = (id, week, aPts, aN, bPts, bN) => tx(id, 2025, week, 'trade', [
    side('A', ['x'], ['y'], { pts: aPts, n: aN, wins: 0, po_wins: 0 }),
    side('B', ['y'], ['x'], { pts: bPts, n: bN, wins: 0, po_wins: 0 })]);
  const early = t('early', 1, 30, 12, -18, 12); // margin 48 over 12 wks = 4/wk
  const late = t('late', 11, 20, 4, -20, 4); // margin 40 over 4 wks = 10/wk
  const blip = t('blip', 14, 15, 1, -15, 1); // 30 in 1 wk: too short to rank per week
  const v = T.tradeVerdict(late);
  assert.deepEqual([v.margin, v.weeks, v.marginPerWeek], [40, 4, 10]);
  const f = { manager: 'all', season: 'all', kinds: all };
  assert.deepEqual(T.topTrades([early, late, blip], f).map((r) => r.tx.id), ['early', 'late', 'blip']);
  assert.deepEqual(T.topTrades([early, late, blip], { ...f, rank: 'week' }).map((r) => r.tx.id), ['late', 'early']);
  const byTotal = T.teamSummary([early, late, blip], 'all').find((r) => r.manager === 'B');
  const byWeek = T.teamSummary([early, late, blip], 'all', 'week').find((r) => r.manager === 'B');
  assert.equal(byTotal.worstTrade.tx.id, 'late'); // -20 total beats -18 and -15
  assert.equal(byWeek.worstTrade.tx.id, 'late'); // -5/wk; blip excluded
  assert.equal(byWeek.bestTrade.tx.id, 'early');
  assert.equal(byTotal.tradePerWeek, Math.round((-53 / 17) * 100) / 100);
  assert.equal(T.readState('?rank=week', { managers: [], seasons: [] }).rank, 'week');
  assert.equal(T.stateToQuery({ manager: 'all', season: 'all', kinds: all, rank: 'week' }), 'rank=week');
});
