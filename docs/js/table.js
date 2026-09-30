// Small sortable table with a "show more" button. No dependencies.

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/**
 * columns: [{key, label, num?: bool, format?: (value, row) => html, sort?: (row) => value}]
 * Values from `format` are inserted as HTML; plain values are escaped.
 */
export function renderTable(el, { columns, rows, pageSize = 10, empty = 'No games match these filters.' }) {
  let sortIdx = -1;
  let sortDir = 1;
  let shown = pageSize;

  const cell = (c, r) => (c.format ? c.format(r[c.key], r) : esc(r[c.key]));
  const sortVal = (c, r) => (c.sort ? c.sort(r) : r[c.key]);

  function draw() {
    let data = rows;
    if (sortIdx >= 0) {
      const c = columns[sortIdx];
      data = [...rows].sort((a, b) => {
        const x = sortVal(c, a);
        const y = sortVal(c, b);
        return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))) * sortDir;
      });
    }
    if (!rows.length) {
      el.innerHTML = `<p class="empty">${esc(empty)}</p>`;
      return;
    }
    const head = columns.map((c, i) => {
      const aria = i === sortIdx ? ` aria-sort="${sortDir > 0 ? 'ascending' : 'descending'}"` : '';
      const arrow = i === sortIdx ? (sortDir > 0 ? ' ▲' : ' ▼') : '';
      return `<th class="${c.num ? 'num' : ''}"${aria}><button type="button" data-col="${i}">${esc(c.label)}${arrow}</button></th>`;
    }).join('');
    const body = data.slice(0, shown).map((r, i) =>
      `<tr><td class="rank">${i + 1}</td>${columns.map((c) => `<td class="${c.num ? 'num' : ''}">${cell(c, r)}</td>`).join('')}</tr>`).join('');
    const more = rows.length > shown
      ? `<button type="button" class="more">Show more (${rows.length - shown} left)</button>`
      : rows.length > pageSize ? '<button type="button" class="less">Show less</button>' : '';
    el.innerHTML = `<div class="table-wrap"><table><thead><tr><th class="rank">#</th>${head}</tr></thead><tbody>${body}</tbody></table></div>${more}`;
  }

  el.onclick = (e) => {
    const t = e.target.closest('button');
    if (!t) return;
    if (t.dataset.col !== undefined) {
      const i = +t.dataset.col;
      sortDir = i === sortIdx ? -sortDir : (columns[i].num ? -1 : 1);
      sortIdx = i;
    } else if (t.classList.contains('more')) {
      shown += pageSize * 2;
    } else if (t.classList.contains('less')) {
      shown = pageSize;
    }
    draw();
  };
  draw();
}

export { esc };
