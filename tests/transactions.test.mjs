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
