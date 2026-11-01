const toggle = document.querySelector('#menu-toggle');
const sidebar = document.querySelector('#sidebar');
toggle.addEventListener('click', () => {
  const open = toggle.getAttribute('aria-expanded') !== 'true';
  toggle.setAttribute('aria-expanded', String(open));
  sidebar.classList.toggle('open', open);
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    toggle.setAttribute('aria-expanded', 'false');
    sidebar.classList.remove('open');
  }
});
const input = document.querySelector('#search');
const results = document.querySelector('#search-results');
let indexPromise;
let requestNumber = 0;
input.addEventListener('input', async () => {
  const request = ++requestNumber;
  const query = input.value.trim().toLocaleLowerCase();
  results.replaceChildren();
  if (!query) return;
  try {
    indexPromise ??= fetch('/assets/search.json').then(response => {
      if (!response.ok) throw new Error('Search unavailable');
      return response.json();
    });
    const index = await indexPromise;
    if (request !== requestNumber) return;
    const terms = query.split(/\s+/);
    const matches = index.filter(item => terms.every(term => (item.title + ' ' + item.text).toLocaleLowerCase().includes(term)));
    const count = document.createElement('p');
    count.textContent = `${matches.length} matching document${matches.length === 1 ? '' : 's'}`;
    results.append(count);
    for (const item of matches.slice(0, 12)) {
      const link = document.createElement('a');
      link.href = item.url;
      link.textContent = item.title;
      results.append(link);
    }
  } catch {
    if (request === requestNumber) results.textContent = 'Search is unavailable. Browse the sections below.';
    indexPromise = undefined;
  }
});
