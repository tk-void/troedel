// ==UserScript==
// @name         Trödel – Ausfüllhilfe
// @namespace    troedel
// @version      __VERSION__
// @description  Füllt Anzeigen bei Kleinanzeigen und Vinted aus Trödel aus. Kategorie wählen und abschicken machst du.
// @match        https://www.kleinanzeigen.de/p-anzeige-aufgeben*
// @match        https://www.kleinanzeigen.de/m-anzeige-aufgeben*
// @match        https://www.vinted.de/items/new*
// @license      MIT
// @grant        GM.xmlHttpRequest
// @grant        GM.setValue
// @grant        GM.getValue
// @connect      __HOST__
// @run-at       document-idle
// @noframes
// ==/UserScript==

/* Trödel fill helper. EXPERIMENTAL.

   Fetches text, price and photos from your Trödel instance and puts them
   into the marketplace's form in your own browser. It never submits:
   category, condition and the final click stay with you. It does not log
   in, does not touch captchas and does not act without you pressing its
   button.

   Using helpers like this may be against a marketplace's terms of use and
   could get an account suspended. That risk is yours; see docs/fill-helper.md.

   This file is a template. Trödel fills in its own address and a token made
   for this one installation when you install the script from its settings.
   The token can read listings and photos and mark an item as listed, nothing
   else. There is no automatic update: install again from Trödel to get a
   newer version.

   Requests go through GM.xmlHttpRequest. That runs in the extension, not in
   the page, so the marketplace's page never sees the token, and the browser
   does not block reaching an http:// address in your home network from an
   https:// page. */

(function () {
  'use strict';

  const BASE = '__BASE__';
  const TOKEN = '__TOKEN__';
  const PLATFORM = location.hostname.includes('kleinanzeigen') ? 'kleinanzeigen' : 'vinted';
  const PLATFORM_NAME = PLATFORM === 'kleinanzeigen' ? 'Kleinanzeigen' : 'Vinted';
  const STORE_KEY = 'item-' + PLATFORM;

  // Interface text, German like the rest of Trödel's interface.
  const T = {
    done: 'Fertig',
    loading: 'Lädt …',
    chooseItem: 'Artikel wählen',
    noItems: 'Keine offenen Artikel in Trödel.',
    unreachable: 'Trödel nicht erreichbar – im selben Netz? (',
    alreadyListed: ' · schon online',
    photos: ' Fotos',
    fill: 'Ausfüllen',
    fillAgain: 'Nochmal ausfüllen',
    markListed: 'Ist online – in Trödel markieren',
    markedListed: 'In Trödel als online markiert ✓',
    otherItem: 'Anderen Artikel wählen',
    toCopy: 'Zum Kopieren',
    copy: 'Kopieren',
    copied: 'Kopiert',
    copyFailed: 'Geht nicht',
    footer: 'Kategorie und Zustand wählst du, abschicken auch.',
    allFilled: 'Ausgefüllt. Jetzt Kategorie und Zustand wählen, prüfen und abschicken.',
    partlyFilled: 'Teilweise ausgefüllt – den Rest unten kopieren.',
    loadingPhotos: 'Fotos laden ',
    uploadingPhoto: 'Foto hochladen ',
    uploadingPhotos: 'Fotos hochladen …',
    textAndPrice: 'Text und Preis …',
    noForm: 'Kein Anzeigenformular gefunden. Bitte erst die Seite „Anzeige aufgeben“ öffnen.',
    title: 'Titel',
    description: 'Beschreibung',
    price: 'Preis ',
    negotiable: ' VB',
    fixed: ' fest',
    error: 'Fehler: ',
    answered: 'Trödel antwortet mit ',
    tokenRejected: 'Trödel kennt dieses Skript nicht mehr. Bitte in Trödel neu installieren.',
  };

  // --- talking to Trödel -----------------------------------------------------

  async function request(method, url, body, kind) {
    const response = await GM.xmlHttpRequest({
      method,
      url: url.startsWith('http') ? url : BASE + url,
      headers: Object.assign({ Authorization: 'Bearer ' + TOKEN }, body ? { 'Content-Type': 'application/json' } : {}),
      data: body ? JSON.stringify(body) : undefined,
      responseType: kind === 'blob' ? 'blob' : 'text',
      timeout: 30000,
    });
    if (response.status === 401 || response.status === 404) throw new Error(T.tokenRejected);
    if (response.status < 200 || response.status >= 300) throw new Error(T.answered + response.status);
    if (kind === 'blob') return response.response instanceof Blob ? response.response : new Blob([response.response], { type: 'image/jpeg' });
    return JSON.parse(response.responseText || 'null');
  }
  const getJson = (path) => request('GET', path);
  // Only ever fetch photos from Trödel itself, whatever address a response names.
  const getPhoto = (url) => {
    if (!url.startsWith(BASE + '/photo/')) throw new Error('unexpected photo address');
    return request('GET', url, null, 'blob');
  };

  // --- form tools ------------------------------------------------------------

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function until(check, ms = 15000) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      const found = check();
      if (found) return found;
      await sleep(200);
    }
    return null;
  }

  function findFirst(selectors) {
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el) return el;
    }
    return null;
  }

  // The page's framework keeps the value itself: the native setter first,
  // then the events, as if someone had typed.
  function setValue(el, value) {
    if (!el) return false;
    el.focus();
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.blur();
    return true;
  }

  function setFiles(input, files) {
    const transfer = new DataTransfer();
    files.forEach((file) => transfer.items.add(file));
    input.files = transfer.files;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  async function loadPhotos(data, report) {
    const files = [];
    for (let i = 0; i < data.photos.length; i++) {
      report(`${T.loadingPhotos}${i + 1}/${data.photos.length} …`);
      const blob = await getPhoto(data.photos[i]);
      files.push(new File([blob], `troedel-${data.id}-${i + 1}.jpg`, { type: 'image/jpeg' }));
    }
    return files;
  }

  const hasPrice = (data) => data.price !== null && data.price !== undefined && data.price !== '';

  // --- Kleinanzeigen ---------------------------------------------------------
  // Element ids as found in the site's listing form. When the site changes
  // them, the affected field is reported as not filled and can be copied.

  const KA_UPLOADED = "input[name^='adImages'][name$='.url']";
  const kaUploaded = () => Array.from(document.querySelectorAll(KA_UPLOADED)).filter((m) => m.value).length;

  async function fillKleinanzeigen(data, report) {
    const result = [];
    if (!document.getElementById('ad-title')) throw new Error(T.noForm);

    // Photos one at a time: the form processes them one after another.
    const files = await loadPhotos(data, report);
    const before = kaUploaded();
    let ok = 0;
    for (let i = 0; i < files.length; i++) {
      report(`${T.uploadingPhoto}${i + 1}/${files.length} …`);
      const input = document.querySelector('input[type=file]');
      if (!input) break;
      setFiles(input, [files[i]]);
      if (await until(() => kaUploaded() >= before + i + 1, 25000)) ok++;
    }
    result.push([`Fotos ${ok}/${files.length}`, ok === files.length]);

    report(T.textAndPrice);
    result.push([T.description, setValue(document.getElementById('ad-description'), data.description)]);

    let priceType = false;
    const typeButton = document.getElementById('ad-price-type');
    if (typeButton) {
      typeButton.click();
      const option = await until(() => document.getElementById('ad-price-type-menu-option-' + (data.negotiable ? 1 : 0)), 3000);
      if (option) { option.click(); priceType = true; }
    }
    if (hasPrice(data)) {
      await sleep(300);
      result.push([`${T.price}${data.price} €${priceType ? (data.negotiable ? T.negotiable : T.fixed) : ''}`,
        setValue(document.getElementById('ad-price-amount'), String(data.price))]);
    }

    // The title last: the page tends to reset it when it redraws.
    await sleep(300);
    result.push([T.title, setValue(document.getElementById('ad-title'), data.title)]);
    return result;
  }

  // After you submitted, the site shows a confirmation page. From then on
  // the item counts as listed in Trödel.
  async function kaConfirmation(panel) {
    if (!location.pathname.includes('bestaetigung')) return false;
    const id = await GM.getValue(STORE_KEY);
    if (!id) return true;
    const adId = new URLSearchParams(location.search).get('adId');
    try {
      await request('PUT', `/api/helper/items/${id}/listed/kleinanzeigen`, {
        url: adId && /^\d+$/.test(adId) ? `https://www.kleinanzeigen.de/s-anzeige/${adId}` : '',
      });
      await GM.setValue(STORE_KEY, '');
      panel.notice(T.markedListed, 'ok');
    } catch (e) {
      panel.notice(e.message, 'error');
    }
    return true;
  }

  // On phones the site may show "get the app" instead of the form, with a
  // link to the web version. Follow it once per session, so there can be no loop.
  function kaWebVersion() {
    if (document.getElementById('ad-title')) return false;
    const link = Array.from(document.querySelectorAll('a')).find((a) => a.textContent.trim() === 'Zur Webversion');
    if (!link) return false;
    try {
      if (sessionStorage.getItem('troedel-web-version')) return false;
      sessionStorage.setItem('troedel-web-version', '1');
    } catch (_) { /* no guard possible */ }
    link.click();
    return true;
  }

  // --- Vinted ----------------------------------------------------------------
  // The form's identifiers are not stable. The lists try the known variants;
  // what does not match is reported and stays available for copying.

  async function fillVinted(data, report) {
    const result = [];
    const files = await loadPhotos(data, report);
    const input = await until(() => document.querySelector('input[type=file]'), 5000);
    if (input && files.length) {
      report(T.uploadingPhotos);
      if (input.multiple) setFiles(input, files);
      else for (const file of files) { setFiles(input, [file]); await sleep(1500); }
      result.push([`Fotos ${files.length}`, true]);
    } else {
      result.push(['Fotos', false]);
    }
    await sleep(800);
    report(T.textAndPrice);
    result.push([T.title, setValue(findFirst([
      '[data-testid="title--input"]', 'input[name="title"]', '#title', 'input[id*="title" i]',
    ]), data.title)]);
    result.push([T.description, setValue(findFirst([
      '[data-testid="description--input"]', 'textarea[name="description"]', '#description', 'textarea[id*="description" i]',
    ]), data.description)]);
    if (hasPrice(data)) {
      result.push([`${T.price}${data.price} €`, setValue(findFirst([
        '[data-testid="price-input--input"]', 'input[name="price"]', '#price', 'input[id*="price" i]',
      ]), String(data.price))]);
    }
    return result;
  }

  // --- panel -----------------------------------------------------------------
  // Lives in a shadow root, so the page's styles and the panel's do not mix.

  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .floating {
      position: fixed; right: 14px; bottom: calc(18px + env(safe-area-inset-bottom, 0px)); z-index: 2147483646;
      display: flex; align-items: center; gap: 8px; height: 48px; padding: 0 18px 0 8px; border: 0; border-radius: 999px;
      background: #1f4a3d; color: #f6f2ea; font-size: 16px; font-weight: 650; cursor: pointer;
      box-shadow: 0 8px 28px -8px rgba(0,0,0,.45);
    }
    .floating .logo { width: 32px; height: 32px; border-radius: 50%; background: #f6f2ea; display: grid; place-items: center; }
    .floating .logo svg { width: 20px; height: 20px; }
    .backdrop { position: fixed; inset: 0; background: rgba(10,8,5,.35); z-index: 2147483646; }
    .panel {
      position: fixed; left: 0; right: 0; bottom: 0; z-index: 2147483647; max-height: 86vh; overflow-y: auto;
      background: #f2f6f8; color: #091015; border-radius: 22px 22px 0 0; padding: 8px 16px calc(18px + env(safe-area-inset-bottom, 0px));
      box-shadow: 0 -10px 40px rgba(0,0,0,.25); -webkit-overflow-scrolling: touch;
    }
    @media (min-width: 700px) { .panel { left: auto; right: 20px; bottom: 20px; width: 400px; border-radius: 22px; } }
    @media (prefers-color-scheme: dark) {
      .panel { background: #0c1014; color: #f3f6f8; }
      .group { background: #141a21 !important; }
      .row + .row::before { border-color: #26303b !important; }
      .button.second { background: rgba(255,255,255,.08) !important; color: #f3f6f8 !important; }
      .copy { background: #143129 !important; color: #3dd6ad !important; }
      .button.primary { background: #3dd6ad !important; color: #04130f !important; }
    }
    .handle { width: 38px; height: 5px; border-radius: 3px; background: #c9d4da; margin: 0 auto 8px; }
    .head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
    .head h2 { margin: 0; font-size: 17px; font-weight: 650; }
    .close { border: 0; background: none; color: #0d7f66; font-size: 16px; font-weight: 600; padding: 6px; cursor: pointer; }
    .group { background: #fff; border-radius: 14px; overflow: hidden; margin-bottom: 12px; }
    .row { display: flex; align-items: center; gap: 12px; padding: 10px 14px; position: relative; font-size: 15px; }
    .row + .row::before { content: ''; position: absolute; top: 0; left: 14px; right: 0; border-top: .5px solid #dde5e9; }
    .row img { width: 52px; height: 52px; border-radius: 10px; object-fit: cover; background: #eee; flex: none; }
    .row .middle { flex: 1; min-width: 0; }
    .row .title { font-weight: 600; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .row .small { font-size: 13px; color: #6f7e89; }
    button.row { width: 100%; border: 0; background: none; text-align: left; color: inherit; cursor: pointer; }
    .buttons { display: grid; gap: 8px; margin-bottom: 12px; }
    .button { height: 50px; border: 0; border-radius: 14px; font-size: 16.5px; font-weight: 650; cursor: pointer; }
    .button.primary { background: #0d7f66; color: #fff; }
    .button.second { background: rgba(10,32,44,.07); color: #091015; }
    .button[disabled] { opacity: .5; }
    .status { font-size: 14.5px; padding: 10px 14px; border-radius: 12px; margin-bottom: 12px; background: #dcf2ec; color: #0d7f66; font-weight: 600; }
    .status.error { background: #f9e1e1; color: #c23f3f; }
    .status.ok { background: #dcf2e8; color: #0d8a5f; }
    .report .row { font-size: 14.5px; }
    .report .yes { color: #0d8a5f; font-weight: 700; }
    .report .no { color: #c23f3f; font-weight: 700; }
    .section { font-size: 12.5px; font-weight: 650; text-transform: uppercase; letter-spacing: .06em; color: #6f7e89; margin: 14px 4px 6px; }
    .value { font-size: 14.5px; white-space: pre-wrap; word-break: break-word; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .copy { flex: none; border: 0; border-radius: 999px; height: 30px; padding: 0 12px; background: #dcf2ec; color: #0d7f66; font-weight: 650; font-size: 13.5px; cursor: pointer; }
    .copy.ok { background: #0d8a5f; color: #fff; }
    .foot { font-size: 12.5px; color: #6f7e89; text-align: center; margin-top: 8px; }
  `;
  const LOGO = '<svg viewBox="0 0 64 64"><g transform="rotate(-32 33 33)"><path d="M14 33 24.5 21H50a4 4 0 0 1 4 4v16a4 4 0 0 1-4 4H24.5Z" fill="#1f4a3d"/><circle cx="23.5" cy="33" r="3.3" fill="#f6f2ea"/><rect x="31" y="28.5" width="17" height="3.2" rx="1.6" fill="#c65d3b"/></g></svg>';

  // Everything that comes from Trödel is text, never markup.
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function buildPanel() {
    const host = document.createElement('div');
    host.id = 'troedel-fill-helper';
    document.documentElement.append(host);
    const root = host.attachShadow({ mode: 'closed' });
    root.innerHTML = `<style>${CSS}</style><button class="floating"><span class="logo">${LOGO}</span>Trödel</button><div class="layer"></div>`;
    const layer = root.querySelector('.layer');
    const floating = root.querySelector('.floating');

    let itemId = null;
    let data = null;
    let noticeText = null;

    const thumbs = {};
    async function thumb(img, url) {
      if (!url) return;
      try {
        thumbs[url] = thumbs[url] || URL.createObjectURL(await getPhoto(url));
        img.src = thumbs[url];
      } catch (_) { /* no thumbnail then */ }
    }

    function close() { layer.innerHTML = ''; floating.hidden = false; }

    function frame(title, content) {
      floating.hidden = true;
      layer.innerHTML = `<div class="backdrop"></div><div class="panel"><div class="handle"></div>
        <div class="head"><h2>${esc(title)}</h2><button class="close">${esc(T.done)}</button></div>${content}</div>`;
      layer.querySelector('.backdrop').onclick = close;
      layer.querySelector('.close').onclick = close;
      return layer.querySelector('.panel');
    }

    function failed(panel, e) {
      const status = panel.querySelector('.status');
      status.className = 'status error';
      status.textContent = e.message === T.tokenRejected ? e.message : T.unreachable + e.message + ')';
    }

    async function choose() {
      const panel = frame(T.chooseItem, `<div class="status">${esc(T.loading)}</div>`);
      try {
        const items = (await getJson('/api/helper/items')).items;
        if (!items.length) { panel.querySelector('.status').textContent = T.noItems; return; }
        panel.querySelector('.status').remove();
        const group = document.createElement('div');
        group.className = 'group';
        group.innerHTML = items.map((it) => `<button class="row" data-id="${esc(it.id)}"><img alt="">
          <div class="middle"><div class="title">${esc(it.title)}</div>
          <div class="small">${it.price != null ? esc(it.price) + ' €' : ''}${it.listed.includes(PLATFORM) ? esc(T.alreadyListed) : ''}</div></div></button>`).join('');
        panel.append(group);
        group.querySelectorAll('.row').forEach((row, i) => {
          thumb(row.querySelector('img'), items[i].thumb);
          row.onclick = async () => { itemId = row.dataset.id; await GM.setValue(STORE_KEY, itemId); data = null; show(); };
        });
      } catch (e) {
        failed(panel, e);
      }
    }

    async function show() {
      if (!itemId) { choose(); return; }
      const loading = `<div class="status">${esc(T.loading)}</div>`;
      const panel = frame(PLATFORM_NAME, loading);
      try {
        data = data || await getJson(`/api/helper/items/${encodeURIComponent(itemId)}?platform=${PLATFORM}`);
      } catch (e) {
        failed(panel, e);
        return;
      }
      const fields = data.fields.map((f, i) => `<div class="row"><div class="middle">
        <div class="small">${esc(f.label)}${f.hint ? ' · ' + esc(f.hint) : ''}</div><div class="value">${esc(f.value || '–')}</div></div>
        ${f.value ? `<button class="copy" data-i="${i}">${esc(T.copy)}</button>` : ''}</div>`).join('');
      panel.querySelector('.status').outerHTML = `
        ${noticeText ? `<div class="status ${noticeText[1] === 'ok' ? 'ok' : 'error'}">${esc(noticeText[0])}</div>` : ''}
        <div class="group"><div class="row"><img alt=""><div class="middle"><div class="title">${esc(data.title)}</div>
          <div class="small">${data.price != null ? esc(data.price) + ' €' : ''} · ${data.photos.length}${esc(T.photos)}${data.listed ? esc(T.alreadyListed) : ''}</div></div></div></div>
        <div class="status" id="running" hidden></div>
        <div class="group report" id="report" hidden></div>
        <div class="buttons">
          <button class="button primary" id="fill">${esc(T.fill)}</button>
          ${PLATFORM === 'vinted' && !data.listed ? `<button class="button second" id="listed">${esc(T.markListed)}</button>` : ''}
          <button class="button second" id="other">${esc(T.otherItem)}</button>
        </div>
        <div class="section">${esc(T.toCopy)}</div><div class="group">${fields}</div>
        <div class="foot">${esc(T.footer)}</div>`;
      thumb(panel.querySelector('.group img'), data.thumb);
      panel.querySelector('#other').onclick = choose;
      panel.querySelectorAll('.copy').forEach((button) => button.onclick = async () => {
        try { await navigator.clipboard.writeText(data.fields[button.dataset.i].value); button.textContent = T.copied; button.classList.add('ok'); }
        catch (_) { button.textContent = T.copyFailed; }
      });
      const listed = panel.querySelector('#listed');
      if (listed) listed.onclick = async () => {
        try { await request('PUT', `/api/helper/items/${encodeURIComponent(itemId)}/listed/${PLATFORM}`, { url: '' }); listed.textContent = T.markedListed; listed.disabled = true; }
        catch (e) { listed.textContent = T.error + e.message; }
      };
      panel.querySelector('#fill').onclick = async () => {
        const button = panel.querySelector('#fill');
        const running = panel.querySelector('#running');
        const reportBox = panel.querySelector('#report');
        button.disabled = true;
        running.hidden = false;
        running.className = 'status';
        const report = (text) => { running.textContent = text; };
        try {
          const result = PLATFORM === 'kleinanzeigen' ? await fillKleinanzeigen(data, report) : await fillVinted(data, report);
          const all = result.every(([, ok]) => ok);
          running.className = 'status ' + (all ? 'ok' : '');
          running.textContent = all ? T.allFilled : T.partlyFilled;
          reportBox.hidden = false;
          reportBox.innerHTML = result.map(([name, ok]) =>
            `<div class="row"><span class="${ok ? 'yes' : 'no'}">${ok ? '✓' : '✗'}</span><span>${esc(name)}</span></div>`).join('');
          if (all) setTimeout(close, 2500);
        } catch (e) {
          running.className = 'status error';
          running.textContent = e.message;
        } finally {
          button.disabled = false;
          button.textContent = T.fillAgain;
        }
      };
    }

    floating.onclick = show;
    return {
      setItem(id) { itemId = id; },
      notice(text, kind) { noticeText = [text, kind]; show(); },
      show,
    };
  }

  // --- start -----------------------------------------------------------------

  async function start() {
    const panel = buildPanel();
    // Coming from Trödel: #troedel=<id>. Remembered, because the site reloads
    // the address when you sign in or change the category.
    const anchor = /troedel=(\d+)/.exec(location.hash);
    if (anchor) await GM.setValue(STORE_KEY, anchor[1]);
    const id = await GM.getValue(STORE_KEY);
    if (id) panel.setItem(id);
    if (PLATFORM === 'kleinanzeigen' && await kaConfirmation(panel)) return;
    if (PLATFORM === 'kleinanzeigen' && kaWebVersion()) return;
    if (anchor) panel.show();
  }

  start();
})();
