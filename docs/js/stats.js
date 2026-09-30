// Pure record calculations. Every function takes the (already filtered) games array.
// A game: {season, week, platform, game_type, team_a, score_a, team_b, score_b, winner}

const r2 = (x) => Math.round(x * 100) / 100;

/** Two rows per game, one from each manager's point of view. */
export function performances(games) {
  const out = [];
  for (const g of games) {
    for (const [me, opp, s, os] of [
      [g.team_a, g.team_b, g.score_a, g.score_b],
      [g.team_b, g.team_a, g.score_b, g.score_a],
    ]) {
      out.push({
        season: g.season, week: g.week, game_type: g.game_type, platform: g.platform,
        manager: me, opponent: opp, score: s, opp_score: os,
        result: g.winner === 'tie' ? 'T' : g.winner === me ? 'W' : 'L',
        margin: r2(s - os),
      });
    }
  }
  return out;
}

const chrono = (a, b) => a.season - b.season || a.week - b.week;
const newestFirst = (a, b) => b.season - a.season || b.week - a.week;

function bestPer(rows, keyFn, better) {
  const best = new Map();
  for (const r of rows) {
    const k = keyFn(r);
    const cur = best.get(k);
    if (!cur || better(r, cur)) best.set(k, r);
  }
  return [...best.values()];
}

function scoreRecords(games, dir, by) {
  const cmp = (a, b) => dir * (b.score - a.score) || chrono(a, b);
  const rows = performances(games);
  if (by === 'season') {
    return bestPer(rows, (r) => r.season, (a, b) => cmp(a, b) < 0).sort((a, b) => b.season - a.season);
  }
  if (by === 'manager') return bestPer(rows, (r) => r.manager, (a, b) => cmp(a, b) < 0).sort(cmp);
  return rows.sort(cmp);
}

/** by: 'all' | 'season' (best per season) | 'manager' (each manager's personal best) */
export const highestScores = (games, by = 'all') => scoreRecords(games, 1, by);
export const lowestScores = (games, by = 'all') => scoreRecords(games, -1, by);

function marginRows(games) {
  return games.map((g) => {
    const aWon = g.score_a >= g.score_b;
    return {
      season: g.season, week: g.week, game_type: g.game_type,
      winner: aWon ? g.team_a : g.team_b, loser: aWon ? g.team_b : g.team_a,
      winner_score: aWon ? g.score_a : g.score_b, loser_score: aWon ? g.score_b : g.score_a,
      margin: r2(Math.abs(g.score_a - g.score_b)), tie: g.winner === 'tie',
    };
  });
}

export const blowouts = (games) =>
  marginRows(games).filter((r) => !r.tie).sort((a, b) => b.margin - a.margin || chrono(a, b));

/** Includes ties (margin 0) — they're the closest games of all. */
export const closestGames = (games) =>
  marginRows(games).sort((a, b) => a.margin - b.margin || chrono(a, b));

export const highestScoreInLoss = (games) =>
  performances(games).filter((p) => p.result === 'L').sort((a, b) => b.score - a.score || chrono(a, b));

export const lowestScoreInWin = (games) =>
  performances(games).filter((p) => p.result === 'W').sort((a, b) => a.score - b.score || chrono(a, b));

/** How often each manager was the lowest scorer of a week (shared lows count for everyone tied). */
export function weeklyLowCounts(games) {
  const weeks = new Map();
  for (const p of performances(games)) {
    const k = `${p.season}-${p.week}`;
    if (!weeks.has(k)) weeks.set(k, []);
    weeks.get(k).push(p);
  }
  const counts = new Map();
  for (const rows of weeks.values()) {
    const low = Math.min(...rows.map((r) => r.score));
    for (const r of rows) if (r.score === low) counts.set(r.manager, (counts.get(r.manager) || 0) + 1);
  }
  return [...counts].map(([manager, count]) => ({ manager, count }))
    .sort((a, b) => b.count - a.count || a.manager.localeCompare(b.manager));
}

/** One row per (season, manager): record, points for/against. */
export function seasonPointsForAgainst(games) {
  const rows = new Map();
  for (const p of performances(games)) {
    const k = `${p.season}|${p.manager}`;
    if (!rows.has(k)) rows.set(k, { season: p.season, manager: p.manager, games: 0, w: 0, l: 0, t: 0, pf: 0, pa: 0 });
    const r = rows.get(k);
    r.games += 1;
    r[p.result.toLowerCase()] += 1;
    r.pf = r2(r.pf + p.score);
    r.pa = r2(r.pa + p.opp_score);
  }
  return [...rows.values()].sort((a, b) => b.season - a.season || b.pf - a.pf);
}

const emptyRec = () => ({ w: 0, l: 0, t: 0, pf: 0, pa: 0, games: 0 });
function addPerf(rec, p) {
  rec.games += 1;
  rec[p.result.toLowerCase()] += 1;
  rec.pf = r2(rec.pf + p.score);
  rec.pa = r2(rec.pa + p.opp_score);
}

/** matrix.get(a).get(b) = a's record against b. */
export function h2hMatrix(games) {
  const m = new Map();
  for (const p of performances(games)) {
    if (!m.has(p.manager)) m.set(p.manager, new Map());
    const row = m.get(p.manager);
    if (!row.has(p.opponent)) row.set(p.opponent, emptyRec());
    addPerf(row.get(p.opponent), p);
  }
  return m;
}

export const winPct = (rec) => (rec.games ? (rec.w + rec.t / 2) / rec.games : 0);

export const formatRecord = (rec) => `${rec.w}-${rec.l}${rec.t ? `-${rec.t}` : ''}`;

/** Everything about a vs b, from a's point of view. */
export function rivalry(games, a, b) {
  const log = performances(games)
    .filter((p) => p.manager === a && p.opponent === b)
    .sort(newestFirst);
  const overall = emptyRec();
  const playoff = emptyRec();
  for (const p of log) {
    addPerf(overall, p);
    if (p.game_type === 'playoff') addPerf(playoff, p);
  }
  const wins = log.filter((p) => p.result === 'W');
  const losses = log.filter((p) => p.result === 'L');
  const biggest = (rows) => rows.reduce((best, p) => (!best || Math.abs(p.margin) > Math.abs(best.margin) ? p : best), null);

  let streak = null;
  if (log.length) {
    const first = log[0].result;
    let n = 0;
    while (n < log.length && log[n].result === first) n += 1;
    streak = { holder: first === 'W' ? a : first === 'L' ? b : 'tie', length: n };
  }
  return {
    a, b, overall, playoff,
    pointsA: overall.pf, pointsB: overall.pa,
    avgMargin: log.length ? r2(log.reduce((s, p) => s + p.margin, 0) / log.length) : 0,
    biggestWinA: biggest(wins), biggestWinB: biggest(losses),
    streak, log,
  };
}

/** Candidate trivia lines; `name` maps manager_id -> display name. */
export function didYouKnowFacts(games, name = (id) => id) {
  if (!games.length) return [];
  const facts = [];
  const hi = highestScores(games)[0];
  facts.push(`The highest score ever is ${hi.score} by ${name(hi.manager)} (${hi.season}, week ${hi.week}).`);
  const lo = lowestScores(games)[0];
  facts.push(`The lowest score ever is ${lo.score} by ${name(lo.manager)} (${lo.season}, week ${lo.week}).`);
  const bl = blowouts(games)[0];
  if (bl) facts.push(`The biggest blowout: ${name(bl.winner)} beat ${name(bl.loser)} by ${bl.margin} in ${bl.season}, week ${bl.week}.`);
  const cl = closestGames(games).find((g) => !g.tie);
  if (cl) facts.push(`The closest game: ${name(cl.winner)} edged ${name(cl.loser)} by just ${cl.margin} in ${cl.season}, week ${cl.week}.`);
  const ties = games.filter((g) => g.winner === 'tie').length;
  if (ties) facts.push(`There ${ties === 1 ? 'has been 1 tie' : `have been ${ties} ties`} in league history.`);
  const hl = highestScoreInLoss(games)[0];
  if (hl) facts.push(`Toughest luck: ${name(hl.manager)} scored ${hl.score} and still lost to ${name(hl.opponent)} (${hl.season}, week ${hl.week}).`);
  const lw = lowestScoreInWin(games)[0];
  if (lw) facts.push(`Luckiest win: ${name(lw.manager)} won with only ${lw.score} against ${name(lw.opponent)} (${lw.season}, week ${lw.week}).`);
  const low = weeklyLowCounts(games)[0];
  if (low) facts.push(`${name(low.manager)} has been the week's lowest scorer ${low.count} times — more than anyone.`);
  let top = null;
  for (const [m, row] of h2hMatrix(games)) {
    for (const [o, rec] of row) if (rec.games >= 3 && (!top || rec.w - rec.l > top.rec.w - top.rec.l)) top = { m, o, rec };
  }
  if (top) facts.push(`${name(top.m)} owns ${name(top.o)}: ${formatRecord(top.rec)} all-time.`);
  return facts;
}

/** Pick n distinct facts using rng() in [0, 1). */
export function didYouKnow(games, n = 3, rng = Math.random, name) {
  const facts = didYouKnowFacts(games, name);
  const picked = [];
  while (picked.length < n && facts.length) picked.push(facts.splice(Math.floor(rng() * facts.length), 1)[0]);
  return picked;
}
