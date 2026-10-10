/* Trödel - behaviour of the pages. No build step, no library.

   Patterns as on iOS: sheets from the bottom instead of new pages, feedback
   as a short toast with "undo", gestures instead of switches (holding a photo
   shows the original). */
(function () {
  'use strict';

  // All interface text this file produces. German only for now.
  const STRINGS = {
    cancel: 'Abbrechen',
    removePhoto: 'Foto entfernen',
    cover: 'Titelbild',
    uploading: 'Lädt hoch …',
    uploadFailed: 'Hochladen fehlgeschlagen: ',
    started: 'Läuft. Gleich das nächste? ',
    view: 'Ansehen',
    beingMade: 'wird erzeugt',
    original: 'Original',
    confirmRemovePhoto: 'Das Foto wird aus der Anzeige entfernt.',
    confirmDeleteItem: 'Artikel und Fotos werden endgültig gelöscht.',
    deleteItem: 'Artikel löschen',
    allChecked: 'alles erledigt',
    of: 'von',
    revised: 'Angepasst: ',
    undo: 'Rückgängig',
    copied: ' Kopiert',
    copyFailed: 'Kopieren ging nicht – bitte von Hand markieren',
    listed: 'online',
    nowListed: ': online',
    noLongerListed: ': nicht mehr online',
    saved: 'Gespeichert',
    testing: 'Frage den Anbieter …',
    testOk: 'Verbindung steht',
    sessionExpired: 'Bitte neu anmelden',
    technicalMessage: 'Technische Meldung',
  };

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const ICON_WARNING = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9.5"/><path d="M12 7.5v5.5M12 16.5h.01"/></svg>';
  const ICON_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
  const PHOTO_VERSION = '?v=1';

  // --- small things ----------------------------------------------------------

  function remember(key, value) { try { sessionStorage.setItem('troedel.' + key, JSON.stringify(value)); } catch (_) { /* private mode */ } }
  function recall(key) { try { return JSON.parse(sessionStorage.getItem('troedel.' + key)); } catch (_) { return null; } }
  function forget(key) { try { sessionStorage.removeItem('troedel.' + key); } catch (_) { /* private mode */ } }

  let toastTimer;
  /** Short message. With `action` ({text, run}) it gets a button. */
  function toast(text, { action = null, duration = 2800, link = null, onEnd = null, kind = 'ok' } = {}) {
    const t = $('#toast');
    t.classList.toggle('error', kind === 'error');
    t.innerHTML = kind === 'error' ? ICON_WARNING : ICON_CHECK;
    const span = document.createElement('span');
    span.textContent = text;
    if (link) {
      const a = document.createElement('a');
      a.href = link.href;
      a.textContent = link.text;
      span.append(a);
    }
    t.append(span);
    let pressed = false;
    if (action) {
      const b = document.createElement('button');
      b.textContent = action.text;
      b.onclick = () => { pressed = true; t.classList.remove('show'); action.run(); };
      t.append(b);
    }
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.classList.remove('show'); if (!pressed && onEnd) onEnd(); }, duration);
  }

  function showError(text) { toast(text, { kind: 'error', duration: 4500 }); }

  /** Lock a button while its work runs: no double trigger. */
  async function whileBusy(button, run) {
    if (button.classList.contains('working')) return;
    button.classList.add('working');
    try { await run(); } catch (e) { showError(e.message); }
    finally { button.classList.remove('working'); }
  }

  /** Confirmation as a sheet, like an iOS action sheet. Resolves true/false. */
  function confirmSheet(text, buttonText, { danger = true } = {}) {
    return new Promise((done) => {
      let s = $('#sheet-confirm');
      if (!s) {
        s = document.createElement('div');
        s.className = 'sheet';
        s.id = 'sheet-confirm';
        s.setAttribute('role', 'alertdialog');
        s.innerHTML = '<div class="sheet-handle"></div><div class="sheet-content" style="padding-top:18px">'
          + '<p class="confirm-text"></p><div class="confirm-buttons">'
          + '<button class="button" data-yes></button><button class="button" data-no></button></div></div>';
        document.body.append(s);
      }
      $('.confirm-text', s).textContent = text;
      const yes = $('[data-yes]', s);
      yes.textContent = buttonText;
      yes.className = 'button ' + (danger ? 'danger-solid' : 'primary');
      $('[data-no]', s).textContent = STRINGS.cancel;
      const finish = (value) => { closeSheet(); done(value); };
      yes.onclick = () => finish(true);
      $('[data-no]', s).onclick = () => finish(false);
      onSheetClose = () => done(false);
      openSheet('confirm');
    });
  }

  async function api(method, path, body) {
    const options = { method, headers: {}, credentials: 'same-origin' };
    if (body instanceof FormData) options.body = body;
    else if (body !== undefined) {
      options.body = JSON.stringify(body);
      options.headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(path, options);
    if (response.status === 401) {
      // The session ended while the page was open.
      location.href = '/login';
      throw new Error(STRINGS.sessionExpired);
    }
    if (!response.ok) {
      let text = response.statusText;
      try { text = (await response.json()).detail || text; } catch (_) { /* no body */ }
      throw new Error(typeof text === 'string' ? text : response.statusText);
    }
    return response.json();
  }

  // The clipboard API only exists in a secure context. Over plain HTTP in a
  // home network the old way through an invisible text field still works,
  // on iOS too.
  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try { await navigator.clipboard.writeText(text); return true; } catch (_) { /* fall through */ }
    }
    const field = document.createElement('textarea');
    field.value = text;
    field.setAttribute('readonly', '');
    field.style.cssText = 'position:fixed;top:0;left:0;opacity:0;font-size:16px';
    document.body.appendChild(field);
    field.focus();
    field.select();
    field.setSelectionRange(0, text.length);
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
    field.remove();
    return ok;
  }

  function reload(sheet) {
    if (sheet) remember('sheet', sheet);
    location.reload();
  }

  // --- navigation bar --------------------------------------------------------

  // The title in the bar only appears once the large title has scrolled out
  // of view, like large titles on iOS.
  function nav() {
    const bar = $('#nav');
    if (!bar) return;
    const anchor = $('[data-large-title]') || $('#f-title');
    if (anchor && 'IntersectionObserver' in window) {
      new IntersectionObserver(([e]) => {
        bar.classList.toggle('scrolled', !e.isIntersecting && e.boundingClientRect.top < 80);
      }, { rootMargin: '-60px 0px 0px 0px' }).observe(anchor);
    } else {
      const check = () => bar.classList.toggle('scrolled', window.scrollY > 4);
      window.addEventListener('scroll', check, { passive: true });
      check();
    }
  }

  // --- sheets ----------------------------------------------------------------

  let openedSheet = null;
  let onSheetClose = null;

  function openSheet(name, pageName) {
    const s = $('#sheet-' + name);
    if (!s) return;
    if (openedSheet && openedSheet !== s && name !== 'confirm') onSheetClose = null;
    if (openedSheet && openedSheet !== s) openedSheet.classList.remove('open');
    openedSheet = s;
    showSheetPage(s, pageName || 'start');
    $('#sheet-backdrop').classList.add('open');
    s.classList.add('open');
    document.documentElement.style.overflow = 'hidden';
    const focus = $('textarea.ai-field', s);
    if (focus && name === 'revise') setTimeout(() => focus.focus(), 350);
  }

  function closeSheet() {
    if (!openedSheet) return;
    const callback = onSheetClose;
    onSheetClose = null;
    if (callback) setTimeout(callback, 0);
    openedSheet.classList.remove('open');
    openedSheet.style.transform = '';
    openedSheet = null;
    $('#sheet-backdrop').classList.remove('open');
    document.documentElement.style.overflow = '';
  }

  function showSheetPage(sheet, pageName) {
    const pages = $$('.sheet-page', sheet);
    if (!pages.length) return;
    if (!pages.some((x) => x.dataset.pageName === pageName)) pageName = 'start';
    pages.forEach((x) => { x.hidden = x.dataset.pageName !== pageName; });
    const content = $('.sheet-page:not([hidden]) .sheet-content', sheet);
    if (content) content.scrollTop = 0;
  }

  // iOS puts the keyboard over fixed elements. The sheet moves up by its
  // height so that the input stays visible.
  function keyboard() {
    const vv = window.visualViewport;
    if (!vv) return;
    const adjust = () => {
      const h = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      document.documentElement.style.setProperty('--keyboard', h > 60 ? h + 'px' : '0px');
    };
    vv.addEventListener('resize', adjust);
    vv.addEventListener('scroll', adjust);
  }

  function sheets() {
    document.addEventListener('click', (ev) => {
      const opener = ev.target.closest('[data-sheet]');
      if (opener) { ev.preventDefault(); openSheet(opener.dataset.sheet); return; }
      if (ev.target.closest('[data-close]') || ev.target.id === 'sheet-backdrop') { closeSheet(); return; }
      const pageLink = ev.target.closest('[data-open-page]');
      if (pageLink) { showSheetPage(pageLink.closest('.sheet'), pageLink.dataset.openPage); }
    });
    document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') closeSheet(); });

    // Dragging down closes, on the handle and on the head.
    $$('.sheet').forEach((s) => {
      let start = null;
      let dy = 0;
      $$('.sheet-head, .sheet-handle', s).forEach((grip) => {
        grip.addEventListener('touchstart', (ev) => { start = ev.touches[0].clientY; dy = 0; s.style.transition = 'none'; }, { passive: true });
        grip.addEventListener('touchmove', (ev) => {
          if (start === null) return;
          dy = Math.max(0, ev.touches[0].clientY - start);
          s.style.transform = `translateY(${dy}px)`;
        }, { passive: true });
        grip.addEventListener('touchend', () => {
          s.style.transition = '';
          if (dy > 90) closeSheet(); else s.style.transform = '';
          start = null;
        });
      });
    });
  }

  // --- list ------------------------------------------------------------------

  function list() {
    const busyIds = () => $$('.card[data-busy="1"]').map((c) => c.dataset.id);
    if (!busyIds().length) return;
    const round = async () => {
      const ids = busyIds();
      if (!ids.length) return;
      try {
        const state = await api('GET', '/api/status?ids=' + ids.join(','));
        if (ids.some((id) => !state[id] || !state[id].in_progress)) { location.reload(); return; }
      } catch (_) { /* next round */ }
      setTimeout(round, 3000);
    };
    setTimeout(round, 3000);
  }

  // --- new item --------------------------------------------------------------

  function newItem(maxPhotos) {
    const input = $('#files');
    const area = $('#capture');
    const previews = $('#previews');
    const submit = $('#submit');
    let files = [];

    function draw() {
      previews.innerHTML = '';
      files.forEach((file, i) => {
        const tile = document.createElement('div');
        tile.className = 'preview';
        const img = document.createElement('img');
        img.src = URL.createObjectURL(file);
        img.onload = () => URL.revokeObjectURL(img.src);
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.setAttribute('aria-label', STRINGS.removePhoto);
        remove.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';
        remove.onclick = () => { files.splice(i, 1); draw(); };
        tile.append(img, remove);
        if (i === 0) { const label = document.createElement('span'); label.className = 'number'; label.textContent = STRINGS.cover; tile.append(label); }
        previews.append(tile);
      });
      if (files.length && files.length < maxPhotos) {
        const more = document.createElement('label');
        more.className = 'preview add';
        more.htmlFor = 'files';
        more.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>';
        previews.append(more);
      }
      previews.hidden = !files.length;
      area.hidden = !!files.length;
      submit.disabled = !files.length;
    }

    function add(fileList) {
      const images = Array.from(fileList).filter((f) => f.type.startsWith('image/') || /\.hei[cf]$/i.test(f.name));
      files = files.concat(images).slice(0, maxPhotos);
      draw();
    }

    input.addEventListener('change', () => { add(input.files); input.value = ''; });
    ['dragenter', 'dragover'].forEach((e) => area.addEventListener(e, (ev) => { ev.preventDefault(); area.classList.add('dragover'); }));
    ['dragleave', 'drop'].forEach((e) => area.addEventListener(e, (ev) => { ev.preventDefault(); area.classList.remove('dragover'); }));
    area.addEventListener('drop', (ev) => add(ev.dataTransfer.files));

    $('#new-item').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      if (!files.length) return;
      const form = new FormData();
      files.forEach((f) => form.append('photos', f, f.name));
      form.append('keywords', $('#keywords').value);
      form.append('product', $('#product').value);
      submit.disabled = true;
      const before = submit.innerHTML;
      submit.textContent = STRINGS.uploading;
      try {
        const created = await api('POST', '/api/items', form);
        files = [];
        $('#keywords').value = '';
        $('#product').value = '';
        draw();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        toast(STRINGS.started, { link: { href: '/items/' + created.id, text: STRINGS.view }, duration: 5000 });
      } catch (e) {
        showError(STRINGS.uploadFailed + e.message);
      } finally {
        submit.innerHTML = before;
        submit.disabled = !files.length;
      }
    });
    draw();
  }

  // --- item ------------------------------------------------------------------

  function item(cfg) {
    const id = cfg.id;
    const photos = cfg.photos;
    const carousel = $('#carousel');
    const stage = $('#stage');
    let index = 0;

    const photoUrl = (p, shown, thumb) => {
      const look = shown || p.shown;
      const variant = look !== 'original' && p.state === 'done' ? '-' + look : '';
      return '/photo/' + p.file + variant + (thumb ? '-t' : '') + '.jpg' + PHOTO_VERSION;
    };

    const viewer = photoViewer({
      source: () => $$('.slide img', carousel).map((img) => ({
        image: img.dataset.edited || img.getAttribute('src'), original: img.dataset.original,
      })),
      onClose: (i) => { if (carousel) carousel.scrollTo({ left: i * carousel.clientWidth, behavior: 'auto' }); },
    });
    $$('[data-viewer]').forEach((b) => b.addEventListener('click', () => viewer.open(index)));
    if (location.hash === '#viewer') setTimeout(() => viewer.open(0), 50);

    // Carousel: the dots follow the swipe
    if (carousel) {
      const count = $$('.slide', carousel).length;
      const arrows = () => $$('[data-page]').forEach((b) => {
        b.disabled = (+b.dataset.page < 0 && index === 0) || (+b.dataset.page > 0 && index >= count - 1);
      });
      carousel.addEventListener('scroll', () => {
        const i = Math.round(carousel.scrollLeft / carousel.clientWidth);
        if (i === index) return;
        index = i;
        $$('#dots span').forEach((dot, j) => dot.classList.toggle('active', j === i));
        arrows();
        lookPreview();
      }, { passive: true });
      // With mouse and keyboard: arrows, dots, ← →
      const goTo = (i) => {
        const target = Math.max(0, Math.min(count - 1, i));
        carousel.scrollTo({ left: target * carousel.clientWidth, behavior: 'smooth' });
      };
      $$('[data-page]').forEach((b) => b.addEventListener('click', () => goTo(index + +b.dataset.page)));
      $$('[data-dot]').forEach((dot) => dot.addEventListener('click', () => goTo(+dot.dataset.dot)));
      document.addEventListener('keydown', (ev) => {
        if (openedSheet || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;
        const step = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
        if (viewer.isOpen()) {
          if (ev.key === 'Escape') viewer.close();
          else if (step) viewer.goTo(viewer.index() + step);
          return;
        }
        if (step) goTo(index + step);
      });
      arrows();

      // Holding shows the original, like "before" in a photo app
      let hold = null;
      let startX = 0;
      const release = () => {
        clearTimeout(hold);
        hold = null;
        if (!stage.classList.contains('showing-original')) return;
        stage.classList.remove('showing-original');
        $$('.slide img', carousel).forEach((img) => { if (img.dataset.edited) img.src = img.dataset.edited; });
      };
      carousel.addEventListener('pointerdown', (ev) => {
        startX = ev.clientX;
        hold = setTimeout(() => {
          const img = $$('.slide img', carousel)[index];
          if (!img || img.src.endsWith(img.dataset.original)) return;
          img.dataset.edited = img.getAttribute('src');
          img.src = img.dataset.original;
          stage.classList.add('showing-original');
        }, 230);
      });
      carousel.addEventListener('pointermove', (ev) => { if (hold && Math.abs(ev.clientX - startX) > 8) release(); });
      // A short tap opens the viewer. Holding stays "show the original".
      carousel.addEventListener('pointerup', (ev) => {
        if (hold && ev.button === 0 && Math.abs(ev.clientX - startX) < 8) viewer.open(index);
      });
      ['pointerup', 'pointercancel', 'pointerleave'].forEach((e) => carousel.addEventListener(e, release));
      carousel.addEventListener('contextmenu', (ev) => ev.preventDefault());
    }

    // Look sheet: the photo currently shown, previewed in every look
    function lookPreview() {
      const p = photos[index] || photos[0];
      if (!p) return;
      $$('#look-grid .look-tile').forEach((tile) => {
        const look = tile.dataset.look;
        const box = $('.image', tile);
        const img = document.createElement('img');
        img.alt = '';
        box.textContent = '';
        if (look === 'original') {
          img.src = '/photo/' + p.file + '-t.jpg' + PHOTO_VERSION;
          box.append(img);
        } else if ((p.looks || []).includes(look)) {
          img.src = '/photo/' + p.file + '-' + look + '-t.jpg' + PHOTO_VERSION;
          box.append(img);
        } else {
          img.src = '/photo/' + p.file + '-t.jpg' + PHOTO_VERSION;
          const wrap = document.createElement('div');
          wrap.className = 'empty';
          const note = document.createElement('span');
          note.textContent = STRINGS.beingMade;
          wrap.append(img, note);
          box.append(wrap);
        }
      });
    }
    $$('[data-sheet="look"]').forEach((b) => b.addEventListener('click', lookPreview));
    lookPreview();
    $$('.look-tile[data-look]').forEach((tile) => tile.addEventListener('click', () => {
      if (tile.dataset.look === cfg.look) { closeSheet(); return; }
      whileBusy(tile, async () => { await api('POST', '/api/items/' + id + '/look', { look: tile.dataset.look }); reload(); });
    }));
    $$('[data-look-again]').forEach((b) => b.addEventListener('click', () => whileBusy(b, async () => {
      await api('POST', '/api/items/' + id + '/look', { look: cfg.look, again: true }); reload();
    })));

    // Photos sheet
    $$('[data-photo-look]').forEach((sw) => sw.addEventListener('change', async () => {
      const shown = sw.checked ? sw.dataset.lookName : 'original';
      try {
        const state = await api('PATCH', '/api/photos/' + sw.dataset.photoLook, { shown });
        updatePhotos(state);
        const label = $('.small', sw.closest('.photo-row'));
        if (label) label.textContent = sw.checked ? cfg.lookNames[sw.dataset.lookName] : STRINGS.original;
      } catch (e) { showError(e.message); sw.checked = !sw.checked; }
    }));
    $$('[data-move-photo]').forEach((b) => b.addEventListener('click', async () => {
      try { await api('PATCH', '/api/photos/' + b.dataset.movePhoto, { move: -1 }); reload('photos'); }
      catch (e) { showError(e.message); }
    }));
    $$('[data-delete-photo]').forEach((b) => b.addEventListener('click', async () => {
      if (!await confirmSheet(STRINGS.confirmRemovePhoto, STRINGS.removePhoto)) return;
      try { await api('DELETE', '/api/photos/' + b.dataset.deletePhoto); reload('photos'); }
      catch (e) { showError(e.message); }
    }));
    $$('[data-retry-photo]').forEach((b) => b.addEventListener('click', async () => {
      try { await api('PATCH', '/api/photos/' + b.dataset.retryPhoto, { retry: true }); reload('photos'); }
      catch (e) { showError(e.message); }
    }));
    const more = $('#more-photos');
    if (more) more.addEventListener('change', async () => {
      const form = new FormData();
      Array.from(more.files).forEach((f) => form.append('photos', f, f.name));
      closeSheet();
      toast(STRINGS.uploading, { duration: 20000 });
      try { await api('POST', '/api/items/' + id + '/photos', form); reload(); }
      catch (e) { showError(e.message); }
    });

    function updatePhotos(state) {
      state.photos.forEach((fresh) => {
        const known = photos.find((p) => p.id === fresh.id);
        if (!known) return;
        const becameDone = known.state !== 'done' && fresh.state === 'done';
        const shownChanged = known.shown !== fresh.shown;
        Object.assign(known, fresh);
        if (becameDone && !(known.looks || []).includes(known.look)) known.looks = (known.looks || []).concat([known.look]);
        if (becameDone || shownChanged || fresh.state !== 'pending') {
          const slide = $('.slide[data-photo="' + fresh.id + '"]');
          if (!slide) return;
          const img = $('img', slide);
          if (becameDone || shownChanged) img.src = photoUrl(known) + (becameDone ? '&t=' + Date.now() : '');
          if (fresh.state !== 'pending') { const running = $('.running', slide); if (running) running.remove(); }
        }
      });
    }

    // Fields save themselves, shortly after typing and when left.
    const timers = {};
    async function save(field) {
      clearTimeout(timers[field.dataset.field]);
      if (field.value === field.dataset.saved) return;
      try {
        await api('PATCH', '/api/items/' + id, { data: { [field.dataset.field]: field.value } });
        field.dataset.saved = field.value;
      } catch (e) { showError(e.message); }
    }
    const grow = (ta) => { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; };
    $$('textarea[data-field], textarea.title-input').forEach((ta) => { grow(ta); ta.addEventListener('input', () => grow(ta)); });
    window.addEventListener('resize', () => $$('textarea[data-field]').forEach(grow));
    $$('[data-field]').forEach((field) => {
      field.dataset.saved = field.value;
      field.addEventListener('input', () => {
        clearTimeout(timers[field.dataset.field]);
        timers[field.dataset.field] = setTimeout(() => save(field), 800);
      });
      field.addEventListener('change', () => save(field));
      field.addEventListener('blur', () => save(field));
    });
    // Title: Enter ends editing instead of adding a line
    const title = $('#f-title');
    const counter = $('#title-counter');
    if (title) {
      const max = +counter.dataset.max;
      title.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); title.blur(); } });
      // The counter only while editing, or when the title is too long.
      const count = () => {
        const n = title.value.length;
        const show = document.activeElement === title || n > max;
        counter.textContent = show ? n + ' / ' + max : '';
        counter.classList.toggle('too-long', n > max);
      };
      ['input', 'focus', 'blur'].forEach((e) => title.addEventListener(e, count));
      count();
    }
    // Price field as wide as the number
    const price = $('[data-field="price"]');
    if (price) {
      const width = () => { price.style.width = Math.max(2, price.value.length + 0.6) + 'ch'; };
      price.addEventListener('input', width);
      width();
    }
    const chip = $('#price-chip');
    if (chip && $('#price-info')) chip.addEventListener('click', () => { $('#price-info').hidden = !$('#price-info').hidden; });

    // "Please check": tick off
    const checkState = () => {
      const all = $$('[data-check]');
      const done = all.filter((row) => row.classList.contains('done')).length;
      if ($('#check-state')) $('#check-state').textContent = done === all.length ? STRINGS.allChecked : `${done} ${STRINGS.of} ${all.length}`;
    };
    $$('[data-check]').forEach((row) => row.addEventListener('click', async () => {
      row.classList.toggle('done');
      checkState();
      const checked = $$('[data-check].done').map((x) => x.dataset.check);
      try { await api('PATCH', '/api/items/' + id, { data: { checked } }); }
      catch (e) { showError(e.message); }
    }));
    checkState();

    // After a revision: a toast with undo. Without an answer it counts as
    // accepted, and the highlights are gone the next time.
    if (cfg.changed.length) {
      toast(STRINGS.revised + cfg.changed.join(', '), {
        duration: 9000,
        action: { text: STRINGS.undo, run: async () => { await api('POST', '/api/items/' + id + '/undo'); location.reload(); } },
        onEnd: () => api('POST', '/api/items/' + id + '/keep').catch(() => {}),
      });
    }

    // Revise sheet
    const reviseForm = $('#revise-form');
    if (reviseForm) {
      const ta = reviseForm.instruction;
      $$('[data-suggestion]').forEach((c) => c.addEventListener('click', () => {
        ta.value = ta.value.trim() ? ta.value.trim().replace(/[.,]?$/, ', ') + c.dataset.suggestion.toLowerCase() : c.dataset.suggestion;
        ta.focus();
      }));
      ta.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); reviseForm.requestSubmit(); }
      });
      reviseForm.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const instruction = ta.value.trim();
        if (!instruction) { ta.focus(); return; }
        const button = $('#sheet-revise .right .sheet-text-button');
        whileBusy(button, async () => {
          // Save open manual edits first: the revision builds on them.
          await Promise.all($$('[data-field]').map((f) => save(f)));
          await api('POST', '/api/items/' + id + '/revise', { instruction });
          location.reload();
        });
      });
    }

    $$('[data-rewrite]').forEach((b) => b.addEventListener('click', () => whileBusy(b, async () => {
      const note = $('#note') ? $('#note').value : '';
      await api('POST', '/api/items/' + id + '/rewrite', { note });
      location.reload();
    })));

    // Publish: tick off the steps, remembered per item
    const steps = new Set(recall('steps-' + id) || []);
    const stepDone = (el) => {
      el.classList.add('complete');
      steps.add(el.dataset.step);
      remember('steps-' + id, Array.from(steps));
    };
    $$('[data-step]').forEach((el) => { if (steps.has(el.dataset.step)) el.classList.add('complete'); });
    $$('[data-step-done]').forEach((a) => a.addEventListener('click', () => stepDone(a.closest('[data-step]'))));
    $$('[data-copy]').forEach((button) => button.addEventListener('click', async () => {
      const step = button.closest('[data-step]');
      const value = $('[data-copy-source]', step).innerText;
      if (await copyText(value)) {
        stepDone(step);
        const before = button.innerHTML;
        button.classList.add('ok');
        button.innerHTML = ICON_CHECK + STRINGS.copied;
        setTimeout(() => { button.classList.remove('ok'); button.innerHTML = before; }, 1500);
      } else {
        showError(STRINGS.copyFailed);
      }
    }));
    $$('.step .value.long').forEach((v) => v.addEventListener('click', () => v.classList.toggle('expanded')));

    // Listed switch: one tap, no detour through the platform page.
    let listingChanged = false;
    $$('[data-listed]').forEach((sw) => sw.addEventListener('change', async () => {
      const platform = sw.dataset.listed;
      const on = sw.checked;
      const name = (sw.getAttribute('aria-label') || platform).split(':')[0];
      const all = $$('[data-listed="' + platform + '"]');
      all.forEach((x) => { x.checked = on; x.disabled = true; });
      try {
        if (on) await api('PUT', '/api/items/' + id + '/listed/' + platform, { url: '' });
        else await api('DELETE', '/api/items/' + id + '/listed/' + platform);
        listingChanged = true;
        $$('[data-listed-text="' + platform + '"]').forEach((t) => { t.textContent = on ? STRINGS.listed : ''; });
        toast(name + (on ? STRINGS.nowListed : STRINGS.noLongerListed));
      } catch (e) {
        all.forEach((x) => { x.checked = !on; });
        showError(e.message);
      } finally {
        all.forEach((x) => { x.disabled = false; });
      }
    }));
    // Refresh the state at the top (badge, chips) only after closing
    $$('#sheet-publish [data-close]').forEach((b) => b.addEventListener('click', () => {
      if (listingChanged) setTimeout(() => location.reload(), 300);
    }));
    $('#sheet-backdrop').addEventListener('click', () => { if (listingChanged) setTimeout(() => location.reload(), 300); });

    // Sold: amount and platform, for the statistics
    const sale = $('#sale-form');
    if (sale) {
      sale.addEventListener('submit', (ev) => {
        ev.preventDefault();
        whileBusy($('button.primary', sale), async () => {
          const via = (sale.querySelector('input[name=via]:checked') || {}).value || '';
          await api('POST', '/api/items/' + id + '/sold', { price: sale.price.value, via });
          location.reload();
        });
      });
      // Tapping the chosen platform again clears the choice.
      $$('input[name=via]', sale).forEach((radio) => {
        let was = false;
        radio.closest('label').addEventListener('pointerdown', () => { was = radio.checked; });
        radio.addEventListener('click', () => { if (was) { radio.checked = false; was = false; } });
      });
      $$('[data-sheet="sold"]').forEach((b) => b.addEventListener('click', () => {
        if (window.matchMedia('(pointer: fine)').matches) setTimeout(() => sale.price.select(), 300);
      }));
    }

    // More menu
    $$('[data-status]').forEach((b) => b.addEventListener('click', () => whileBusy(b, async () => {
      await api('PATCH', '/api/items/' + id, { status: b.dataset.status }); location.reload();
    })));
    $$('[data-delete]').forEach((b) => b.addEventListener('click', async () => {
      if (!await confirmSheet(STRINGS.confirmDeleteItem, STRINGS.deleteItem)) return;
      try { await api('DELETE', '/api/items/' + id); location.href = '/'; }
      catch (e) { showError(e.message); }
    }));

    // Open the sheet again if a reload happened in the middle of something
    let again = recall('sheet');
    forget('sheet');
    // Direct link: #sheet=publish/vinted
    const anchor = /^#sheet=([a-z]+)(?:\/([a-z]+))?/.exec(location.hash);
    if (anchor) again = { name: anchor[1], page: anchor[2] };
    if (again) {
      const target = typeof again === 'string' ? { name: again } : again;
      setTimeout(() => openSheet(target.name, target.page), 50);
    }

    // While the text is written or photos are edited: look again.
    if (cfg.inProgress) {
      const round = async () => {
        try {
          const state = await api('GET', '/api/items/' + id);
          if (state.status !== cfg.status) { location.reload(); return; }
          updatePhotos(state);
          if (openedSheet && openedSheet.id === 'sheet-look') lookPreview();
          if (!state.in_progress) return;
        } catch (_) { /* next round */ }
        setTimeout(round, 2500);
      };
      setTimeout(round, 2500);
    }
  }

  // --- photo viewer ----------------------------------------------------------

  /* Look at photos large, as in a photo app: swiping pages, two fingers or a
     double tap zoom, zoomed in one finger pans, dragging down closes, a
     single tap hides the buttons. With a mouse: a click zooms, the pointer
     steers the visible part, arrows and ← →. */
  function photoViewer({ source, onClose }) {
    const box = $('#viewer');
    const none = { open() {}, close() {}, isOpen: () => false, goTo() {}, index: () => 0 };
    if (!box) return none;
    const track = $('#viewer-track');
    const slides = $$('.viewer-slide', track);
    const counter = $('#viewer-counter');
    const mouse = window.matchMedia('(hover: hover) and (pointer: fine)');
    let index = 0;
    let z = { s: 1, x: 0, y: 0 };
    let lastTouch = 0;
    let urls = [];
    let showingOriginal = false;
    const originalButton = $('[data-viewer-original]', box);

    const width = () => track.clientWidth;
    const img = (i = index) => $('img', slides[i]);

    // Before/after applies to all photos until switched back. The button
    // only exists for photos that have been edited.
    function showOriginal(on) {
      showingOriginal = on;
      slides.forEach((slide, j) => {
        const picture = $('img', slide);
        const target = on ? urls[j].original : urls[j].image;
        if (picture.getAttribute('src') !== target) picture.src = target;
      });
      originalButton.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    originalButton.addEventListener('click', () => showOriginal(!showingOriginal));

    function refresh() {
      const u = urls[index];
      originalButton.hidden = !u || !u.original || u.original === u.image;
      counter.textContent = slides.length > 1 ? (index + 1) + ' ' + STRINGS.of + ' ' + slides.length : '';
      $$('[data-viewer-page]', box).forEach((b) => {
        b.disabled = (+b.dataset.viewerPage < 0 && index === 0) || (+b.dataset.viewerPage > 0 && index >= slides.length - 1);
      });
    }

    // How far the zoomed picture can be moved: to its own edge, not to the
    // edge of the black area.
    function limits(s) {
      const picture = img();
      const w = slides[index].clientWidth;
      const h = slides[index].clientHeight;
      const ratio = picture.naturalWidth && picture.naturalHeight ? picture.naturalWidth / picture.naturalHeight : 1;
      const pw = Math.min(w, h * ratio);
      const ph = pw / ratio;
      return { mx: Math.max(0, (pw * s - w) / 2), my: Math.max(0, (ph * s - h) / 2) };
    }

    function zoom(s, x, y, smooth) {
      s = Math.min(5, Math.max(1, s));
      const lim = limits(s);
      z = { s, x: Math.max(-lim.mx, Math.min(lim.mx, x)), y: Math.max(-lim.my, Math.min(lim.my, y)) };
      if (s === 1) z = { s: 1, x: 0, y: 0 };
      const picture = img();
      picture.style.transition = smooth ? 'transform .25s cubic-bezier(.2, .9, .3, 1)' : 'none';
      picture.style.transform = z.s === 1 ? '' : `translate(${z.x}px, ${z.y}px) scale(${z.s})`;
      slides[index].classList.toggle('zoomed', z.s > 1);
      track.classList.toggle('locked', z.s > 1);
    }

    // The point (relative to the picture's centre) stays under the finger
    // or the pointer while zooming.
    function zoomAround(s, px, py, smooth) {
      const f = s / z.s;
      zoom(s, px - (px - z.x) * f, py - (py - z.y) * f, smooth);
    }

    function centre(ev) {
      const r = slides[index].getBoundingClientRect();
      return { x: ev.clientX - r.left - r.width / 2, y: ev.clientY - r.top - r.height / 2 };
    }

    function open(i) {
      urls = source();
      showOriginal(false);
      slides.forEach((slide) => { $('img', slide).style.transform = ''; });
      // The click that opened it should not zoom right away.
      lastTouch = Date.now();
      box.hidden = false;
      document.documentElement.style.overflow = 'hidden';
      box.classList.remove('quiet');
      requestAnimationFrame(() => {
        track.scrollLeft = i * width();
        index = i;
        refresh();
        box.classList.add('open');
      });
    }

    function close() {
      if (box.hidden) return;
      zoom(1, 0, 0);
      onClose(index);
      box.classList.remove('open');
      document.documentElement.style.overflow = '';
      setTimeout(() => { box.hidden = true; slides.forEach((slide) => { $('img', slide).style.transform = ''; }); box.style.background = ''; }, 220);
    }

    function goTo(i) {
      i = Math.max(0, Math.min(slides.length - 1, i));
      if (z.s > 1) zoom(1, 0, 0);
      track.scrollTo({ left: i * width(), behavior: 'smooth' });
    }

    track.addEventListener('scroll', () => {
      const i = Math.round(track.scrollLeft / width());
      if (i === index || i < 0 || i >= slides.length) return;
      img().style.transform = '';
      slides[index].classList.remove('zoomed');
      z = { s: 1, x: 0, y: 0 };
      index = i;
      refresh();
    }, { passive: true });

    $('[data-viewer-close]', box).addEventListener('click', close);
    $$('[data-viewer-page]', box).forEach((b) => b.addEventListener('click', () => goTo(index + +b.dataset.viewerPage)));
    window.addEventListener('resize', () => { if (!box.hidden) { zoom(1, 0, 0); track.scrollLeft = index * width(); } });

    // --- fingers
    let gesture = null;
    let tapTime = 0;
    let tapPlace = null;
    let tapWait = null;
    const distance = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
    const midpoint = (t) => centre({ clientX: (t[0].clientX + t[1].clientX) / 2, clientY: (t[0].clientY + t[1].clientY) / 2 });

    track.addEventListener('touchstart', (ev) => {
      lastTouch = Date.now();
      const t = ev.touches;
      if (t.length === 2) {
        gesture = { kind: 'two', d: distance(t), m: midpoint(t), s: z.s, x: z.x, y: z.y };
      } else if (t.length === 1) {
        gesture = { kind: 'one', x0: t[0].clientX, y0: t[0].clientY, x: z.x, y: z.y, time: Date.now(), moved: false, direction: null };
      }
    }, { passive: true });

    track.addEventListener('touchmove', (ev) => {
      if (!gesture) return;
      const t = ev.touches;
      if (gesture.kind === 'two' && t.length === 2) {
        ev.preventDefault();
        const m = midpoint(t);
        const s = Math.min(5, Math.max(.8, gesture.s * distance(t) / gesture.d));
        const f = s / gesture.s;
        // Below 1 only give way visually, back on release
        const picture = img();
        if (s < 1) { picture.style.transition = 'none'; picture.style.transform = `scale(${s})`; z = { s: 1, x: 0, y: 0 }; return; }
        zoom(s, m.x - (gesture.m.x - gesture.x) * f, m.y - (gesture.m.y - gesture.y) * f);
        return;
      }
      if (gesture.kind !== 'one' || t.length !== 1) return;
      const dx = t[0].clientX - gesture.x0;
      const dy = t[0].clientY - gesture.y0;
      if (Math.abs(dx) > 6 || Math.abs(dy) > 6) gesture.moved = true;
      if (z.s > 1) {
        ev.preventDefault();
        zoom(z.s, gesture.x + dx, gesture.y + dy);
        return;
      }
      if (!gesture.direction && gesture.moved) gesture.direction = Math.abs(dy) > Math.abs(dx) ? 'vertical' : 'horizontal';
      if (gesture.direction === 'vertical') {
        ev.preventDefault();
        const picture = img();
        picture.style.transition = 'none';
        picture.style.transform = `translate(${dx * .4}px, ${dy}px) scale(${1 - Math.min(.25, Math.abs(dy) / 1600)})`;
        box.style.background = `rgba(0, 0, 0, ${Math.max(.25, 1 - Math.abs(dy) / 400)})`;
        gesture.dy = dy;
      }
    }, { passive: false });

    track.addEventListener('touchend', (ev) => {
      lastTouch = Date.now();
      if (!gesture) return;
      const g = gesture;
      if (g.kind === 'two') {
        if (ev.touches.length) return;
        gesture = null;
        if (z.s < 1.05) zoom(1, 0, 0, true);
        return;
      }
      gesture = null;
      if (g.direction === 'vertical') {
        if (Math.abs(g.dy || 0) > 110) { close(); return; }
        const picture = img();
        picture.style.transition = 'transform .25s cubic-bezier(.2, .9, .3, 1)';
        picture.style.transform = '';
        box.style.background = '';
        return;
      }
      if (g.moved || Date.now() - g.time > 300) return;
      // Tapping: twice zooms, once toggles the buttons
      const place = centre({ clientX: g.x0, clientY: g.y0 });
      if (Date.now() - tapTime < 300 && tapPlace && Math.hypot(place.x - tapPlace.x, place.y - tapPlace.y) < 40) {
        clearTimeout(tapWait);
        tapTime = 0;
        if (z.s > 1) zoom(1, 0, 0, true); else zoomAround(2.5, place.x, place.y, true);
        return;
      }
      tapTime = Date.now();
      tapPlace = place;
      tapWait = setTimeout(() => box.classList.toggle('quiet'), 300);
    });

    // Safari would otherwise zoom the whole page along.
    box.addEventListener('gesturestart', (ev) => ev.preventDefault());

    // --- mouse
    track.addEventListener('click', (ev) => {
      if (Date.now() - lastTouch < 800 || !mouse.matches) return;
      if (z.s > 1) { zoom(1, 0, 0, true); return; }
      const p = centre(ev);
      zoomAround(2.5, p.x, p.y, true);
    });
    track.addEventListener('mousemove', (ev) => {
      if (z.s <= 1 || !mouse.matches) return;
      // The pointer steers the visible part: top left shows the top left corner.
      const r = slides[index].getBoundingClientRect();
      const lim = limits(z.s);
      const fx = (ev.clientX - r.left) / r.width - .5;
      const fy = (ev.clientY - r.top) / r.height - .5;
      zoom(z.s, -fx * 2 * lim.mx, -fy * 2 * lim.my);
    });
    track.addEventListener('wheel', (ev) => {
      if (!mouse.matches || !ev.ctrlKey) return;
      ev.preventDefault();
      const p = centre(ev);
      zoomAround(z.s * Math.exp(-ev.deltaY / 200), p.x, p.y);
    }, { passive: false });

    return { open, close, goTo, isOpen: () => !box.hidden, index: () => index };
  }

  // --- settings --------------------------------------------------------------

  function settings({ saved }) {
    if (saved) toast(STRINGS.saved);

    // Switches and selects in the general form save at once, as in the iOS
    // settings; the button stays for keyboards.
    $$('#settings select, #settings input[type=checkbox]').forEach((el) =>
      el.addEventListener('change', () => $('#settings').submit()));

    const provider = $('#provider');
    const model = $('#model');
    const baseUrl = $('#base-url');
    function adapt(changed) {
      const option = provider.selectedOptions[0];
      const chosen = !!provider.value;
      $('#row-key').hidden = !chosen || option.dataset.key !== '1';
      $('#row-url').hidden = !chosen || option.dataset.customUrl !== '1';
      $('#key-note').hidden = $('#row-key').hidden;
      $('#provider-note').textContent = chosen ? option.dataset.note : '';
      model.placeholder = chosen && option.dataset.model ? option.dataset.model : '';
      baseUrl.placeholder = chosen ? option.dataset.url : '';
      if (changed) {
        // The model and address of one provider mean nothing to another.
        model.value = '';
        baseUrl.value = '';
      }
    }
    provider.addEventListener('change', () => adapt(true));
    adapt(false);

    const test = $('#test-provider');
    const result = $('#test-result');
    test.addEventListener('click', () => whileBusy(test, async () => {
      result.className = 'status-line';
      result.textContent = STRINGS.testing;
      $$('#provider-form .error-detail').forEach((old) => old.remove());
      const answer = await api('POST', '/settings/provider/test');
      result.classList.add(answer.ok ? 'ok' : 'error');
      result.textContent = answer.ok ? STRINGS.testOk + (answer.model ? ' · ' + answer.model : '') : answer.message;
      if (!answer.ok && answer.detail) {
        const detail = document.createElement('details');
        detail.className = 'error-detail';
        const summary = document.createElement('summary');
        summary.textContent = STRINGS.technicalMessage;
        detail.append(summary, answer.detail);
        result.after(detail);
      }
    }));
  }

  // --- fill helper page --------------------------------------------------------

  // Four browsers need four different extensions. Put the one for the
  // browser in use first and mark it, so nobody has to work out which line
  // is theirs.
  function fillHelper() {
    const ua = navigator.userAgent;
    let browser = '';
    if (/iPhone|iPad|iPod/.test(ua)) browser = 'safari';           // every iOS browser is Safari underneath
    else if (/Firefox\//.test(ua)) browser = 'firefox';
    else if (/Edg\//.test(ua)) browser = 'edge';
    else if (/Chrome\//.test(ua)) browser = 'chrome';
    else if (/Safari\//.test(ua)) browser = 'safari';
    const copy = $('#copy-script-url');
    if (copy) copy.addEventListener('click', async () => {
      if (await copyText($('#script-url').textContent)) toast(STRINGS.copied.trim());
      else showError(STRINGS.copyFailed);
    });
    const mine = $('.manager[data-browser="' + browser + '"]');
    if (!mine) return;
    $('.this-browser', mine).hidden = false;
    const first = $('.manager');
    if (first !== mine) first.before(mine);
  }

  // Browser extensions (the fill helper) only run in Safari itself, not in
  // the embedded browser of a home screen app. x-safari-https:// opens the
  // address in Safari for certain (from iOS 17).
  function safariLinks() {
    if (!/iPhone|iPad|iPod/.test(navigator.userAgent)) return;
    $$('a[data-safari]').forEach((a) => {
      a.href = 'x-safari-' + a.href;
      a.target = '_top';
    });
  }

  document.addEventListener('DOMContentLoaded', () => { nav(); sheets(); keyboard(); safariLinks(); });
  window.Troedel = { newItem, item, list, settings, fillHelper, toast, copyText };
})();
