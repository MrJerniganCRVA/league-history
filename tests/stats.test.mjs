// Run: node --test tests/
// Hand-computed answers for tests/fixture_games.json (10 games, 2 seasons, 1 tie, 2 playoff, 1 consolation).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as S from '../docs/js/stats.js';
import { applyFilters, readFilters, filtersToQuery } from '../docs/js/filters.js';

const games = JSON.parse(readFileSync(new URL('./fixture_games.json', import.meta.url)));
const pick = (rows, ...keys) => rows.map((r) => keys.map((k) => r[k]));

test('highest and lowest scores', () => {
  assert.deepEqual(pick(S.highestScores(games).slice(0, 2), 'manager', 'score'), [['B', 150], ['C', 130]]);
  assert.deepEqual(pick(S.lowestScores(games).slice(0, 2), 'manager', 'score'), [['D', 40], ['C', 50]]);
  assert.deepEqual(pick(S.highestScores(games, 'season'), 'season', 'manager', 'score'), [[2022, 'C', 130], [2021, 'B', 150]]);
  assert.deepEqual(pick(S.highestScores(games, 'manager'), 'manager', 'score'), [['B', 150], ['C', 130], ['A', 110], ['D', 100]]);
  assert.deepEqual(pick(S.lowestScores(games, 'manager'), 'manager', 'score'), [['D', 40], ['C', 50], ['B', 60], ['A', 70]]);
});

test('blowouts and closest games (tie counts as closest)', () => {
  assert.deepEqual(pick(S.blowouts(games).slice(0, 3), 'winner', 'loser', 'margin'), [['B', 'C', 100], ['C', 'D', 90], ['C', 'A', 50]]);
  const close = S.closestGames(games);
  assert.equal(close[0].tie, true);
  assert.deepEqual(pick(close.slice(1, 4), 'season', 'winner', 'margin'), [[2022, 'C', 1], [2021, 'D', 5], [2022, 'B', 5]]);
});

test('highest score in a loss, lowest in a win', () => {
  assert.deepEqual(pick(S.highestScoreInLoss(games).slice(0, 2), 'season', 'manager', 'score'), [[2021, 'D', 100], [2022, 'A', 100]]);
  assert.deepEqual(pick(S.lowestScoreInWin(games).slice(0, 1), 'manager', 'score'), [['D', 65]]);
});

test('weekly low counts (shared low counts for both)', () => {
  assert.deepEqual(S.weeklyLowCounts(games), [{ manager: 'B', count: 2 }, { manager: 'C', count: 2 }, { manager: 'D', count: 2 }]);
});

test('season points for/against', () => {
  const rows = S.seasonPointsForAgainst(games);
  const a21 = rows.find((r) => r.season === 2021 && r.manager === 'A');
  assert.deepEqual([a21.w, a21.l, a21.t, a21.pf, a21.pa], [2, 1, 0, 280, 310]);
  const c21 = rows.find((r) => r.season === 2021 && r.manager === 'C');
  assert.deepEqual([c21.w, c21.l, c21.t, c21.pf, c21.pa], [1, 1, 1, 250, 300]);
});

test('head-to-head matrix and win pct', () => {
  const m = S.h2hMatrix(games);
  const ab = m.get('A').get('B');
  assert.deepEqual([ab.w, ab.l, ab.t, ab.pf, ab.pa], [2, 1, 0, 294, 275]);
  assert.equal(S.formatRecord(ab), '2-1');
  assert.equal(S.formatRecord(m.get('C').get('D')), '1-0-1');
  assert.equal(S.winPct(m.get('C').get('D')), 0.75);
  assert.equal(m.get('A').has('A'), false);
});

test('rivalry', () => {
  const r = S.rivalry(games, 'A', 'C');
  assert.equal(S.formatRecord(r.overall), '0-2');
  assert.equal(S.formatRecord(r.playoff), '0-1');
  assert.deepEqual([r.pointsA, r.pointsB, r.avgMargin], [170, 221, -25.5]);
  assert.equal(r.biggestWinA, null);
  assert.equal(r.biggestWinB.margin, -50);
  assert.deepEqual(r.streak, { holder: 'C', length: 2 });
  assert.deepEqual(pick(r.log, 'season', 'week'), [[2022, 2], [2021, 2]]);
  const ab = S.rivalry(games, 'A', 'B');
  assert.deepEqual(ab.streak, { holder: 'A', length: 1 });
  assert.equal(ab.avgMargin, 6.33);
});

test('did you know', () => {
  const facts = S.didYouKnow(games, 3, () => 0);
  assert.equal(facts.length, 3);
  assert.equal(new Set(facts).size, 3);
  assert.match(S.didYouKnowFacts(games).join(' '), /1 tie/);
});

test('title and Sacko facts need a clear leader', () => {
  const seasons = [
    { season: 2021, champion: 'A', sacko: 'D' },
    { season: 2022, champion: 'A', sacko: 'C' },
    { season: 2023, champion: 'B', sacko: 'D' },
  ];
  const facts = S.didYouKnowFacts(games, (id) => id, seasons).join(' ');
  assert.match(facts, /A has the most titles: 2 championships/);
  assert.match(facts, /D has taken home the Sacko 2 times/);
  const tied = S.didYouKnowFacts(games, (id) => id, seasons.slice(0, 2)).join(' ');
  assert.match(tied, /most titles/);
  assert.doesNotMatch(tied, /Sacko/); // D and C have 1 each: no leader
});

test('filters', () => {
  const seasons = [2021, 2022];
  const f = readFilters('', seasons);
  assert.deepEqual(f, { from: 2021, to: 2022, platform: 'all', type: 'rp' });
  assert.equal(applyFilters(games, f).length, 9);                       // consolation excluded
  assert.equal(applyFilters(games, { ...f, type: 'po' }).length, 2);
  assert.equal(applyFilters(games, { ...f, type: 'all' }).length, 10);
  assert.equal(applyFilters(games, readFilters('from=2022', seasons)).length, 4);
  assert.equal(applyFilters(games, { ...f, platform: 'yahoo' }).length, 5);
  assert.equal(filtersToQuery(f, seasons), '');
  assert.equal(filtersToQuery({ ...f, type: 'po' }, seasons), 'type=po');
  assert.deepEqual(readFilters('from=2022&to=2021&type=bogus', seasons), { from: 2021, to: 2022, platform: 'all', type: 'rp' });
});
