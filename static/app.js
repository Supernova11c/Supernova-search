document.addEventListener('DOMContentLoaded', () => {
  const searchForm = document.querySelector('.search-form');
  const recentContainer = document.getElementById('recent-searches');
  const queryInput = searchForm ? searchForm.querySelector('input[name="q"]') : null;

  const getRecentSearches = () => {
    try {
      return JSON.parse(localStorage.getItem('supernova-search-history') || '[]');
    } catch (error) {
      return [];
    }
  };

  const saveRecentSearch = (value) => {
    if (!value || value.trim().length < 2) return;
    const normalized = value.trim();
    const list = getRecentSearches();
    const next = [normalized, ...list.filter(item => item.toLowerCase() !== normalized.toLowerCase())].slice(0, 6);
    localStorage.setItem('supernova-search-history', JSON.stringify(next));
    renderRecentSearches(next);
  };

  const renderRecentSearches = (items = getRecentSearches()) => {
    if (!recentContainer) return;
    recentContainer.innerHTML = '';
    if (!items.length) {
      const empty = document.createElement('span');
      empty.textContent = 'No recent searches yet';
      empty.className = 'recent-tag';
      recentContainer.appendChild(empty);
      return;
    }
    items.forEach(item => {
      const link = document.createElement('a');
      link.href = `/?q=${encodeURIComponent(item)}`;
      link.className = 'recent-tag';
      link.textContent = item;
      recentContainer.appendChild(link);
    });
  };

  if (searchForm && queryInput) {
    searchForm.addEventListener('submit', (event) => {
      const value = queryInput.value.trim();
      if (!value) {
        event.preventDefault();
        return;
      }
      saveRecentSearch(value);
    });

    const queryValue = queryInput.value.trim();
    if (queryValue) {
      saveRecentSearch(queryValue);
    }
  }

  renderRecentSearches();

  document.querySelectorAll('[data-filter]').forEach(button => {
    button.addEventListener('click', () => {
      const form = document.querySelector('.search-form');
      if (!form) return;
      form.submit();
    });
  });
});
