import { didYouKnow } from '../stats.js';
import { applyFilters, defaultFilters } from '../filters.js';
import { managerLabel } from '../data.js';
import { esc } from '../table.js';
import { boot } from '../ui.js';

boot('', (data) => {
  const who = (id) => (id ? managerLabel(data, id) : '<span class="muted">—</span>');
  const years = data.seasons.map((s) => s.season);
  const t = data.meta.data_through;
  document.getElementById('through').textContent =
    `${years.length} seasons · ${data.games.length} games${t ? ` · through ${t.season} week ${t.week}` : ''}`;

  const rows = [...data.seasons].reverse().map((s) => `
    <tr>
      <th scope="row">${s.season}</th>
      <td>${s.champion ? `<span aria-hidden="true">🏆</span> ${who(s.champion)}` : '<span class="muted">In progress</span>'}</td>
      <td>${s.last_place ? who(s.last_place) : '<span class="muted">—</span>'}</td>
    </tr>`).join('');
  document.getElementById('champions').innerHTML = `
    <div class="table-wrap"><table class="champs">
      <thead><tr><th>Season</th><th>Champion</th><th>Last place</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;

  const games = applyFilters(data.games, defaultFilters(years));
  const list = document.getElementById('facts');
  const draw = () => {
    list.innerHTML = didYouKnow(games, 3, Math.random, data.name).map((f) => `<li>${esc(f)}</li>`).join('');
  };
  document.getElementById('more-facts').addEventListener('click', draw);
  draw();
});
