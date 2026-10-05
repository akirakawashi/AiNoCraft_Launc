/**
 * News panel: renders the published news feed delivered in the bootstrap state.
 */

const News = (() => {
  const container = () => document.getElementById('news-list');

  // Full articles live on the site; the launcher shows the feed with previews.
  // The site origin is mode-aware (dev -> localhost:3000, prod -> ainocraft.com).
  function articleUrl(slug) {
    const base = (App.state.webBaseUrl || 'https://ainocraft.com').replace(/\/+$/, '');
    return `${base}/news/${slug}`;
  }

  function formatDate(iso) {
    if (!iso) return '';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
  }

  function newsCard(item) {
    const card = document.createElement('article');
    card.className = 'news-entry';

    if (item.cover_image_url) {
      const cover = document.createElement('div');
      cover.className = 'news-entry__cover';
      const img = document.createElement('img');
      img.src = item.cover_image_url;
      img.alt = '';
      img.loading = 'lazy';
      cover.append(img);
      card.append(cover);
    }

    const body = document.createElement('div');
    body.className = 'news-entry__body';

    const date = formatDate(item.published_at);
    if (date) {
      const time = document.createElement('time');
      time.className = 'news-entry__date';
      time.dateTime = item.published_at;
      time.textContent = date;
      body.append(time);
    }

    const title = document.createElement('h3');
    title.className = 'news-entry__title';
    title.textContent = item.title || '';
    body.append(title);

    if (item.excerpt) {
      const excerpt = document.createElement('p');
      excerpt.className = 'news-entry__excerpt';
      excerpt.textContent = item.excerpt;
      body.append(excerpt);
    }

    if (item.slug) {
      const link = document.createElement('button');
      link.type = 'button';
      link.className = 'news-entry__link';
      link.textContent = 'Читать на сайте →';
      link.addEventListener('click', () => {
        API.openExternalUrl(articleUrl(item.slug)).catch((err) => {
          console.warn('[news] open article failed:', err);
        });
      });
      body.append(link);
    }

    card.append(body);
    return card;
  }

  function render(items) {
    const target = container();
    if (!target) return;
    target.textContent = '';

    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      const empty = document.createElement('p');
      empty.className = 'news-empty';
      empty.textContent = 'Новостей пока нет. Загляните позже!';
      target.append(empty);
      return;
    }

    list.forEach((item) => target.append(newsCard(item)));
  }

  return { render };
})();
