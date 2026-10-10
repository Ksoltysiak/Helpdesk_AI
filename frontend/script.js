// ============================================================
// STATE & CONFIG
// ============================================================
const API = '/api';

let state = {
  userId: null,
  token:  null,
  user:   null,
  role:   null,
  clientName: null,     // firma pracownika; null dla technika i administratora
  currentView: 'dashboard',
  filterStatus: '',
  filterPriority: '',
  filterClient: '',
  filterCategory: '',
  filterSkrot: '',      // skrót z pulpitu: aktywne / nieprzypisane / moje / po_terminie
  klienci: null,        // lista klientów do filtra — pobierana raz na sesję
  raport: { klient: '', zakres: '30', od: '', do: '' },   // ostatnie ustawienia raportu
  ostatniRaport: null,
  page: 1,
};

const TRANSITIONS = {
  'Nowe':       ['W trakcie'],
  'W trakcie':  ['Rozwiazane', 'Wstrzymane'],
  'Wstrzymane': ['W trakcie'],
  'Rozwiazane': ['Zamkniete', 'W trakcie'],
  'Zamkniete':  [],
};

// ============================================================
// API HELPERS
// ============================================================
function apiHeaders() {
  return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${state.token}` };
}

async function apiFetch(url, options = {}) {
  options.headers = { ...apiHeaders(), ...(options.headers || {}) };
  const res = await fetch(API + url, options);
  const data = await res.json().catch(() => ({ error: res.statusText }));
  if (!res.ok) throw { status: res.status, message: data.error || res.statusText };
  return data;
}

function showError(msg) {
  const el = document.getElementById('globalError');
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
  clearTimeout(showError._t);
  showError._t = setTimeout(() => { el.style.display = 'none'; }, 5000);
}

// ============================================================
// LOGIN / AUTH
// ============================================================
async function doLogin() {
  const username = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value;
  if (!username || !password) { showLoginError('Wpisz nazwę użytkownika i hasło.'); return; }

  const btn = document.getElementById('loginBtn');
  btn.disabled = true;
  btn.textContent = 'Logowanie...';

  try {
    const res = await fetch(API + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) { showLoginError(data.error || 'Błąd logowania'); return; }

    state.userId = data.id;
    state.token  = data.token;
    state.user   = data.name;
    state.role   = data.role;
    state.clientName = data.client_name;
    sessionStorage.setItem('helpdesk_token', data.token);

    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('app').classList.add('visible');
    setupSidebar();
    navigate('dashboard');
  } catch {
    showLoginError('Nie można połączyć z serwerem.');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Zaloguj się';
    const svg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>';
    btn.innerHTML = svg + ' Zaloguj się';
  }
}

function showLoginError(msg) {
  const el = document.getElementById('loginError');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}

function doLogout() {
  state.userId = null; state.token = null; state.user = null; state.role = null;
  state.clientName = null; state.klienci = null; state.ostatniRaport = null;
  state.raport = { klient: '', zakres: '30', od: '', do: '' };
  state.filterStatus = ''; state.filterPriority = ''; state.filterClient = ''; state.page = 1;
  state.filterCategory = ''; state.filterSkrot = '';
  zatrzymajOdswiezanie();
  pulpit.poprzednie = null; pulpit.znaneWpisy = null; pulpit.zakladka = 'najnowsze';
  sessionStorage.removeItem('helpdesk_token');
  document.getElementById('loginScreen').style.display = 'flex';
  document.getElementById('app').classList.remove('visible');
  document.getElementById('loginUsername').value = '';
  document.getElementById('loginPassword').value = '';
  const err = document.getElementById('loginError');
  if (err) err.style.display = 'none';
}

// ============================================================
// SIDEBAR SETUP
// ============================================================
function setupSidebar() {
  const initials = state.user.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  document.getElementById('userAvatarSidebar').textContent = initials;
  document.getElementById('userNameSidebar').textContent = state.user;

  const isTechnik = state.role === 'technik' || state.role === 'admin';
  document.getElementById('userRoleSidebar').textContent =
    state.role === 'admin' ? 'Administrator' : isTechnik ? 'Technik IT'
    : state.clientName ? `Pracownik · ${state.clientName}` : 'Pracownik';
  document.getElementById('sidebarRoleLabel').textContent =
    isTechnik ? 'Konsola IT' : 'Portal Pracownika';

  const nav = document.getElementById('sidebarNav');
  let items = `
    <div class="nav-section-label">Główne</div>
    <a class="nav-item" data-view="dashboard" onclick="navigate('dashboard')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
      Dashboard
    </a>`;

  if (!isTechnik) {
    items += `
      <a class="nav-item" data-view="new-ticket" onclick="navigate('new-ticket')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
        Nowe zgłoszenie
      </a>
      <a class="nav-item" data-view="my-tickets" onclick="navigate('my-tickets')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
        Moje zgłoszenia
      </a>`;
  } else {
    items += `
      <div class="nav-section-label" style="margin-top:0.5rem">Konsola IT</div>
      <a class="nav-item" data-view="all-tickets" onclick="navigate('all-tickets')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
        Wszystkie zgłoszenia
      </a>
      <a class="nav-item" data-view="clients" onclick="navigate('clients')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/><path d="M9 9h1M14 9h1M9 13h1M14 13h1M9 17h1M14 17h1"/></svg>
        Klienci
      </a>
      <a class="nav-item" data-view="reports" onclick="navigate('reports')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
        Raporty
      </a>`;
  }

  nav.innerHTML = items;
}

// ============================================================
// NAVIGATION
// ============================================================
function navigate(view) {
  // Zmiana widoku zawsze zaczyna od pierwszej strony.
  if (state.currentView !== view) state.page = 1;
  state.currentView = view;
  if (view === 'dashboard') uruchomOdswiezanie(); else zatrzymajOdswiezanie();
  document.querySelectorAll('.nav-item').forEach(el =>
    el.classList.toggle('active', el.dataset.view === view)
  );
  const titles = {
    'dashboard':   'Dashboard',
    'new-ticket':  'Nowe zgłoszenie',
    'my-tickets':  'Moje zgłoszenia',
    'all-tickets': 'Wszystkie zgłoszenia',
    'clients':     'Klienci',
    'reports':     'Raporty',
  };
  document.getElementById('pageTitle').textContent = titles[view] || 'HelpDesk IT';
  renderView(view);
}

function renderView(view) {
  const c = document.getElementById('mainContent');
  c.innerHTML = spinner();
  switch (view) {
    case 'dashboard':   renderDashboard(); break;
    case 'new-ticket':  c.innerHTML = renderNewTicket(); break;
    case 'my-tickets':  renderMyTickets(); break;
    case 'all-tickets': renderAllTickets(); break;
    case 'clients':     renderClients(); break;
    case 'reports':     renderReports(); break;
    default:            renderDashboard();
  }
}

// ============================================================
// STRONICOWANIE
// ============================================================
function zmienStrone(nowa) {
  state.page = nowa;
  renderView(state.currentView);
}

function renderPaginacja(dane) {
  if (dane.pages <= 1) return '';

  const od = (dane.page - 1) * dane.per_page + 1;
  const do_ = Math.min(dane.page * dane.per_page, dane.total);

  return `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:1rem;
                padding-top:1rem;margin-top:0.5rem;border-top:1px solid var(--color-border);
                flex-wrap:wrap">
      <div style="color:var(--color-text-muted);font-size:var(--text-sm)">
        ${od}–${do_} z ${dane.total}
      </div>
      <div style="display:flex;align-items:center;gap:0.5rem">
        <button class="btn btn-sm btn-secondary" ${dane.page <= 1 ? 'disabled' : ''}
                onclick="zmienStrone(${dane.page - 1})">Poprzednia</button>
        <span style="font-size:var(--text-sm);color:var(--color-text-muted)">
          Strona ${dane.page} z ${dane.pages}
        </span>
        <button class="btn btn-sm btn-secondary" ${dane.page >= dane.pages ? 'disabled' : ''}
                onclick="zmienStrone(${dane.page + 1})">Następna</button>
      </div>
    </div>`;
}

function spinner() {
  return `<div style="display:flex;align-items:center;justify-content:center;padding:3rem;color:var(--color-text-muted);gap:0.5rem">
    <svg class="ai-spinner" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
    Ładowanie...
  </div>`;
}

// ============================================================
// DASHBOARD
// ============================================================
// Pulpit odświeża się sam, dopóki jest na ekranie. Karta w tle nie odpytuje
// serwera — dane doczytują się od razu, gdy użytkownik do niej wróci.
const ODSWIEZANIE_MS = 30000;

const pulpit = {
  timer: null,
  auto: (() => { try { return localStorage.getItem('helpdesk_auto') !== '0'; } catch { return true; } })(),
  poprzednie: null,     // liczniki z poprzedniego odświeżenia — do pokazania zmian
  znaneWpisy: null,     // klucze wpisów aktywności — nowe dostają wyróżnienie
  zakladka: 'najnowsze',
};

const ZAKLADKI_PULPITU = {
  najnowsze:     { nazwa: 'Najnowsze',     query: '' },
  nieprzypisane: { nazwa: 'Nieprzypisane', query: '&przypisane=brak&aktywne=1' },
  moje:          { nazwa: 'Moje',          query: '&przypisane=ja&aktywne=1' },
  krytyczne:     { nazwa: 'Krytyczne',     query: '&priority=Krytyczny&aktywne=1' },
  sla:           { nazwa: 'Po terminie',   query: '&sla=przekroczone' },
};

const KATEGORIE_PL = {
  'Sprzet': 'Sprzęt', 'Siec': 'Sieć', 'Konta i dostep': 'Konta i dostęp',
  'Bezpieczenstwo': 'Bezpieczeństwo',
};
const kategoriaPL = k => KATEGORIE_PL[k] || k;

const BEZ_ANIMACJI = matchMedia('(prefers-reduced-motion: reduce)').matches;

function uruchomOdswiezanie() {
  zatrzymajOdswiezanie();
  if (!pulpit.auto) return;
  pulpit.timer = setInterval(() => {
    const modalOtwarty = document.getElementById('ticketModal').classList.contains('open');
    if (!document.hidden && !modalOtwarty && state.currentView === 'dashboard') renderDashboard(true);
  }, ODSWIEZANIE_MS);
}

function zatrzymajOdswiezanie() {
  clearInterval(pulpit.timer);
  pulpit.timer = null;
}

function przelaczAuto() {
  pulpit.auto = !pulpit.auto;
  try { localStorage.setItem('helpdesk_auto', pulpit.auto ? '1' : '0'); } catch { /* tryb prywatny */ }
  uruchomOdswiezanie();
  renderDashboard(true);
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden && state.token && state.currentView === 'dashboard' && pulpit.auto) renderDashboard(true);
});

// Kliknięcie w kafelek albo wykres prowadzi do listy z gotowym filtrem.
function przejdzDoListy(f) {
  state.filterStatus = f.status || '';
  state.filterPriority = f.priority || '';
  state.filterCategory = f.category || '';
  state.filterClient = '';
  state.filterSkrot = f.skrot || '';
  state.page = 1;
  navigate('all-tickets');
}

function linkListy(f) {
  return `przejdzDoListy(${escHtml(JSON.stringify(f))})`;
}

async function renderDashboard(odswiezenie = false) {
  const c = document.getElementById('mainContent');
  const isTechnik = state.role === 'technik' || state.role === 'admin';
  try {
    if (isTechnik) await pulpitTechnika(c, odswiezenie);
    else await pulpitPracownika(c, odswiezenie);
  } catch (e) {
    // Chwilowy błąd przy odświeżeniu nie kasuje pulpitu — pokazujemy go w pasku.
    const pasek = document.getElementById('liveStatus');
    if (odswiezenie && pasek) { pasek.textContent = 'Brak połączenia — ponowię próbę'; return; }
    c.innerHTML = errorCard(e.message || 'Błąd ładowania danych.');
  }
}

// --- Pasek „na żywo" ------------------------------------------------------
function pasekNaZywo() {
  return `
    <div class="live-bar">
      <span class="live-dot ${pulpit.auto ? 'on' : ''}"></span>
      <span id="liveStatus">${pulpit.auto ? 'Na żywo' : 'Wstrzymano'} · aktualizacja
        <span data-od="${new Date().toISOString()}">przed chwilą</span></span>
      <button class="btn btn-sm btn-secondary" onclick="przelaczAuto()"
              title="${pulpit.auto ? 'Wstrzymaj' : 'Wznów'} automatyczne odświeżanie co ${ODSWIEZANIE_MS / 1000} s">
        ${pulpit.auto ? 'Pauza' : 'Wznów'}</button>
      <button class="icon-btn" onclick="renderDashboard(true)" title="Odśwież teraz" aria-label="Odśwież teraz">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
      </button>
    </div>`;
}

// --- Kafelki ---------------------------------------------------------------
function kafelki(lista, odswiezenie) {
  const poprzednie = pulpit.poprzednie || {};
  const html = lista.map(k => {
    const przed = poprzednie[k.klucz];
    const roznica = odswiezenie && przed !== undefined ? k.wartosc - przed : 0;
    const akcja = k.filtr ? linkListy(k.filtr) : (k.akcja || '');
    return `
      <${akcja ? 'button type="button"' : 'div'} class="card kpi-card ${akcja ? 'kpi-link' : ''} ${k.alarm ? 'kpi-alarm' : ''} ${roznica ? 'kpi-zmiana' : ''}"
           ${akcja ? `onclick="${akcja}"` : ''} title="${escHtml(k.tytul || '')}">
        <div class="kpi-label">${k.etykieta}</div>
        <div class="kpi-value" style="color:${k.kolor || 'inherit'}" data-licznik="${k.wartosc}">${odswiezenie ? k.wartosc : 0}</div>
        <div class="kpi-sub"><span class="kpi-dot" style="background:${k.kolor || 'var(--color-text-muted)'}"></span>${k.podpis}
          ${roznica ? `<span class="kpi-delta ${roznica > 0 ? 'delta-up' : 'delta-down'}">${roznica > 0 ? '+' : '−'}${Math.abs(roznica)}</span>` : ''}</div>
      </${akcja ? 'button' : 'div'}>`;
  }).join('');
  pulpit.poprzednie = Object.fromEntries(lista.map(k => [k.klucz, k.wartosc]));
  return `<div class="kpi-grid kpi-grid-pulpit">${html}</div>`;
}

// Liczniki „dobiegają" do wartości tylko przy pierwszym wejściu na pulpit —
// przy cichym odświeżeniu animacja co 30 s byłaby męcząca.
function animujLiczniki(korzen) {
  const el = korzen.querySelectorAll('[data-licznik]');
  if (BEZ_ANIMACJI) { el.forEach(e => { e.textContent = e.dataset.licznik; }); return; }
  const start = performance.now(), CZAS = 700;
  const krok = t => {
    const p = Math.min(1, (t - start) / CZAS), e = 1 - Math.pow(1 - p, 3);
    el.forEach(x => { x.textContent = Math.round(+x.dataset.licznik * e); });
    if (p < 1) requestAnimationFrame(krok);
  };
  requestAnimationFrame(krok);
}

// --- Czas: odliczanie SLA i „x minut temu" ---------------------------------
function czasTrwania(ms) {
  const s = Math.floor(ms / 1000), m = Math.floor(s / 60), h = Math.floor(m / 60), d = Math.floor(h / 24);
  if (d >= 1) return `${d} d ${h % 24} h`;
  if (h >= 1) return `${h} h ${String(m % 60).padStart(2, '0')} min`;
  return `${m} min ${String(s % 60).padStart(2, '0')} s`;
}

function odliczanie(iso) {
  const roznica = new Date(iso) - Date.now();
  return roznica < 0 ? `po terminie ${czasTrwania(-roznica)}` : `zostało ${czasTrwania(roznica)}`;
}

function ileTemu(iso) {
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso)) / 1000));
  if (s < 10) return 'przed chwilą';
  if (s < 60) return `${s} s temu`;
  if (s < 3600) return `${Math.floor(s / 60)} min temu`;
  if (s < 86400) return `${Math.floor(s / 3600)} h temu`;
  const dni = Math.floor(s / 86400);
  if (dni === 1) return 'wczoraj';
  if (dni < 7) return `${dni} dni temu`;
  return formatDate(iso);
}

// Jeden zegar dla całej strony aktualizuje wszystkie liczniki czasu.
setInterval(() => {
  document.querySelectorAll('[data-termin]').forEach(el => {
    el.textContent = odliczanie(el.dataset.termin);
    el.classList.toggle('sla-po', new Date(el.dataset.termin) < Date.now());
  });
  document.querySelectorAll('[data-od]').forEach(el => { el.textContent = ileTemu(el.dataset.od); });
}, 1000);

function licznikSla(iso) {
  if (!iso) return '';
  const po = new Date(iso) < Date.now();
  return `<span class="sla-timer ${po ? 'sla-po' : ''}" data-termin="${iso}">${odliczanie(iso)}</span>`;
}

// --- Wykresy ----------------------------------------------------------------
function szerokoscWykresu(udzial) {
  const obszar = document.getElementById('mainContent');
  const dostepne = (obszar ? obszar.clientWidth : 700) - 48;
  return Math.round(Math.min(900, Math.max(280, dostepne > 900 ? dostepne * udzial - 40 : dostepne - 40)));
}

function wykresRuchu(trend, animuj) {
  const W = szerokoscWykresu(2 / 3), H = 240, L = 28, P = 6, G = 8, D = 24;
  const n = trend.length;
  const max = Math.max(1, ...trend.map(t => Math.max(t.nowe, t.zamkniete)));
  const krok = (W - L - P) / n, szer = Math.max(2, krok * 0.34);
  const y = v => G + (H - G - D) * (1 - v / max);
  const wys = v => (H - G - D) * (v / max);
  const co = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(W / 60))));

  const siatka = [0, Math.round(max / 2), max].filter((v, i, a) => a.indexOf(v) === i).map(v => `
    <line class="trend-grid" x1="${L}" x2="${W - P}" y1="${y(v)}" y2="${y(v)}"/>
    <text class="trend-label" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`).join('');

  const slupki = trend.map((t, i) => {
    const x = L + krok * i + krok / 2;
    const dzien = formatDzien(t.data);
    return `
      <g class="trend-dzien" style="--i:${i}">
        <rect class="bar-nowe" x="${x - szer - 1}" y="${H - D - wys(t.nowe)}" width="${szer}" height="${wys(t.nowe)}" rx="1.5"/>
        <rect class="bar-zamk" x="${x + 1}" y="${H - D - wys(t.zamkniete)}" width="${szer}" height="${wys(t.zamkniete)}" rx="1.5"/>
        <rect x="${L + krok * i}" y="${G}" width="${krok}" height="${H - G - D}" fill="transparent">
          <title>${dzien}: ${t.nowe} nowych, ${t.zamkniete} zamkniętych</title></rect>
        ${(i % co === 0 || i === n - 1) && !(i !== n - 1 && n - 1 - i < co / 2)
          ? `<text class="trend-label" x="${x}" y="${H - 6}" text-anchor="middle">${dzien.slice(0, 5)}</text>` : ''}
      </g>`;
  }).join('');

  const nowe = trend.reduce((s, t) => s + t.nowe, 0), zamk = trend.reduce((s, t) => s + t.zamkniete, 0);
  return `
    <svg class="trend-chart ${animuj && !BEZ_ANIMACJI ? 'anim' : ''}" viewBox="0 0 ${W} ${H}" role="img"
         aria-label="Ostatnie ${n} dni: ${nowe} nowych i ${zamk} zamkniętych zgłoszeń">${siatka}${slupki}</svg>
    <div class="chart-legend">
      <span><span class="legend-swatch"></span>nowe (${nowe})</span>
      <span><span class="legend-swatch" style="background:var(--color-success)"></span>zamknięte (${zamk})</span>
    </div>`;
}

const PRIORYTETY = ['Krytyczny', 'Wysoki', 'Sredni', 'Niski'];

function donutPriorytetow(wg) {
  const razem = PRIORYTETY.reduce((s, p) => s + (wg[p] || 0), 0);
  if (!razem) return emptyState('Brak aktywnych zgłoszeń — kolejka jest pusta.');
  const R = 42, O = 2 * Math.PI * R, przerwa = PRIORYTETY.filter(p => wg[p]).length > 1 ? 1.5 : 0;
  let przesuniecie = 0;
  const luki = PRIORYTETY.filter(p => wg[p]).map(p => {
    const dl = wg[p] / razem * O;
    const luk = `<circle class="donut-luk" r="${R}" cx="60" cy="60" stroke="${KOLORY_PRIORYTETOW[p]}"
      stroke-dasharray="${Math.max(0.5, dl - przerwa)} ${O - dl + przerwa}" stroke-dashoffset="${-przesuniecie}"
      onclick="${linkListy({ priority: p, skrot: 'aktywne' })}"><title>${p}: ${wg[p]}</title></circle>`;
    przesuniecie += dl;
    return luk;
  }).join('');
  const legenda = PRIORYTETY.map(p => `
    <button type="button" class="donut-row" onclick="${linkListy({ priority: p, skrot: 'aktywne' })}">
      ${priorityBadge(p)}<span class="donut-num">${wg[p] || 0}</span>
      <small>${Math.round((wg[p] || 0) / razem * 100)}%</small>
    </button>`).join('');
  return `
    <div class="donut-wrap">
      <svg class="donut" viewBox="0 0 120 120" role="img" aria-label="Aktywne zgłoszenia wg priorytetu, razem ${razem}">
        <g transform="rotate(-90 60 60)">
          <circle r="${R}" cx="60" cy="60" fill="none" stroke="var(--color-surface-offset)" stroke-width="16"/>${luki}
        </g>
        <text x="60" y="60" class="donut-value" text-anchor="middle">${razem}</text>
        <text x="60" y="76" class="donut-label" text-anchor="middle">aktywnych</text>
      </svg>
      <div class="donut-legend">${legenda}</div>
    </div>`;
}

function slupkiKategorii(wiersze) {
  if (!wiersze.length) return emptyState('Brak zgłoszeń.');
  const max = wiersze[0].liczba;
  return wiersze.map(w => `
    <button type="button" class="bar-row bar-link" onclick="${linkListy({ category: w.kategoria })}"
            title="Pokaż zgłoszenia: ${escHtml(kategoriaPL(w.kategoria))}">
      <div class="bar-label">${escHtml(kategoriaPL(w.kategoria))}</div>
      <div class="bar-track"><div class="bar-fill grow" style="width:${w.liczba / max * 100}%"></div></div>
      <div class="bar-value">${w.liczba}</div>
    </button>`).join('');
}

function obciazenieZespolu(osoby) {
  if (!osoby.length) return emptyState('Brak techników w systemie.');
  const max = Math.max(1, ...osoby.map(o => o.aktywne));
  return osoby.map(o => {
    const ja = o.id === state.userId;
    const kolor = o.aktywne >= 5 ? 'var(--color-error)' : o.aktywne >= 3 ? 'var(--color-orange)' : 'var(--color-success)';
    return `
      <div class="bar-row bar-row-osoba ${ja ? 'bar-link' : ''}" ${ja ? `onclick="${linkListy({ skrot: 'moje' })}" style="cursor:pointer"` : ''}>
        <div class="bar-label"><span class="avatar-mini">${escHtml(o.name.split(' ').map(x => x[0]).join('').slice(0, 2))}</span>
          ${escHtml(o.name)}${ja ? ' <small>(Ty)</small>' : ''}</div>
        <div class="bar-track">${o.aktywne ? `<div class="bar-fill grow" style="width:${o.aktywne / max * 100}%;background:${kolor}"></div>` : ''}</div>
        <div class="bar-value">${o.aktywne} ${o.krytyczne ? `<small style="color:var(--color-error)" title="w tym krytyczne">⚑${o.krytyczne}</small>` : ''}</div>
      </div>`;
  }).join('');
}

// --- Kanał aktywności -------------------------------------------------------
const IKONY_AKCJI = {
  'Utworzenie':       ['+', 'var(--color-blue)'],
  'Zmiana statusu':   ['→', 'var(--color-primary)'],
  'Kategoryzacja AI': ['AI', 'var(--color-orange)'],
  'Zmiana kategorii': ['#', 'var(--color-warning)'],
  'Przypisanie':      ['@', 'var(--color-success)'],
  'Notatka':          ['✎', 'var(--color-text-muted)'],
};

function opisAkcji(a) {
  switch (a.action) {
    case 'Utworzenie': return a.ai ? `nowe zgłoszenie <span class="badge badge-ai">AI</span> ${opisAkcji(a.ai)}` : 'nowe zgłoszenie';
    case 'Zmiana statusu': return `${statusLabel(a.old)} → <b>${statusLabel(a.new)}</b>`;
    case 'Zmiana kategorii': return `kategoria ${escHtml(kategoriaPL(a.old || '—'))} → <b>${escHtml(kategoriaPL(a.new))}</b>`;
    case 'Przypisanie': return 'zmiana przypisania';
    case 'Notatka': return `notatka: „${escHtml(a.new)}”`;
    case 'Kategoryzacja AI':
      try {
        const w = JSON.parse(a.new);
        return `${escHtml(kategoriaPL(w.kategoria))} · ${escHtml(w.priorytet)} <small>(${Math.round(w.pewnosc * 100)}%)</small>`;
      } catch { return 'kategoryzacja'; }
    default: return escHtml(a.action);
  }
}

function kluczWpisu(a) { return `${a.timestamp}|${a.ticket_id}|${a.action}|${a.new}`; }

// Utworzenie zgłoszenia i jego kategoryzacja przez AI dzieją się w tej samej
// chwili — w kanale pokazujemy je jako jedno zdarzenie zamiast dwóch.
function scalWpisy(wpisy) {
  const ai = new Map(wpisy.filter(a => a.action === 'Kategoryzacja AI').map(a => [a.ticket_id, a]));
  const zUtworzeniem = new Set(wpisy.filter(a => a.action === 'Utworzenie').map(a => a.ticket_id));
  return wpisy
    .filter(a => !(a.action === 'Kategoryzacja AI' && zUtworzeniem.has(a.ticket_id)))
    .map(a => a.action === 'Utworzenie' && ai.has(a.ticket_id) ? { ...a, ai: ai.get(a.ticket_id) } : a);
}

function kanalAktywnosci(wpisyZBazy, odswiezenie) {
  const wpisy = scalWpisy(wpisyZBazy);
  const znane = pulpit.znaneWpisy;
  const nowe = odswiezenie && znane ? wpisy.filter(a => !znane.has(kluczWpisu(a))) : [];
  pulpit.znaneWpisy = new Set(wpisy.map(kluczWpisu));

  // Technik dostaje powiadomienie o każdym nowym zgłoszeniu, które wpadło od ostatniego odświeżenia.
  if (state.role !== 'pracownik') {
    nowe.filter(a => a.action === 'Utworzenie').forEach(a => pokazPowiadomienie(`Nowe zgłoszenie #${a.ticket_id}: ${a.title}`, a.ticket_id));
  }
  if (!wpisy.length) return emptyState('Jeszcze nic się nie wydarzyło.');
  return `<ul class="feed">${wpisy.map(a => {
    const [ikona, kolor] = IKONY_AKCJI[a.action] || ['•', 'var(--color-text-muted)'];
    return `
      <li class="feed-item ${nowe.includes(a) ? 'feed-nowy' : ''}" onclick="openTicket(${a.ticket_id})">
        <span class="feed-icon" style="color:${kolor};background:color-mix(in srgb, ${kolor} 14%, transparent)">${ikona}</span>
        <div class="feed-body">
          <div class="feed-title"><span class="td-id">#${a.ticket_id}</span> ${escHtml(a.title)}</div>
          <div class="feed-meta"><b>${escHtml(a.user)}</b> · ${opisAkcji(a)}</div>
        </div>
        <span class="feed-time" data-od="${a.timestamp}">${ileTemu(a.timestamp)}</span>
      </li>`;
  }).join('')}</ul>`;
}

function pokazPowiadomienie(tekst, ticketId) {
  let box = document.getElementById('toasty');
  if (!box) {
    box = document.createElement('div');
    box.id = 'toasty';
    box.className = 'toasty';
    box.setAttribute('aria-live', 'polite');
    document.body.appendChild(box);
  }
  const t = document.createElement('button');
  t.type = 'button';
  t.className = 'toast';
  t.innerHTML = `<span class="live-dot on"></span>${escHtml(tekst)}`;
  t.onclick = () => { t.remove(); if (ticketId) openTicket(ticketId); };
  box.appendChild(t);
  setTimeout(() => t.classList.add('toast-out'), 6000);
  setTimeout(() => t.remove(), 6500);
}

// --- Panel SLA ---------------------------------------------------------------
function panelSla(lista) {
  if (!lista.length) {
    return `<div class="empty-state sla-ok"><div class="sla-ok-icon">✓</div><p>Wszystkie terminy SLA pod kontrolą.</p></div>`;
  }
  return `<ul class="sla-list">${lista.map(t => `
    <li class="sla-item" onclick="openTicket(${t.id})">
      <div class="sla-main">
        <div class="feed-title"><span class="td-id">#${t.id}</span> ${escHtml(t.title)}</div>
        <div class="feed-meta">${priorityBadge(t.priority)} ${statusBadge(t.status)}
          · ${t.assigned_to_name ? escHtml(t.assigned_to_name) : '<span style="color:var(--color-orange)">nieprzypisane</span>'}</div>
      </div>
      ${licznikSla(t.sla_deadline)}
    </li>`).join('')}</ul>`;
}

function kartaAI(ai) {
  if (!ai || !ai.zgloszen_z_ai) return '';
  const proc = Math.round((ai.skutecznosc ?? 0) * 100);
  const kolor = proc >= 90 ? 'var(--color-success)' : proc >= 75 ? 'var(--color-warning)' : 'var(--color-error)';
  const pomylka = ai.najczestsze_pomylki && ai.najczestsze_pomylki[0];
  return `
    <div class="card">
      <div class="section-header"><div class="section-title">Moduł AI</div><span class="badge badge-ai">na żywo</span></div>
      <div class="ai-gauge">
        <div class="ai-gauge-value" style="color:${kolor}">${proc}%</div>
        <div class="ai-gauge-sub">trafnych kategorii<br><small>${ai.poprawionych_recznie} z ${ai.zgloszen_z_ai} poprawionych ręcznie</small></div>
      </div>
      <div class="bar-track" style="margin:0.75rem 0 1rem"><div class="bar-fill grow" style="width:${proc}%;background:${kolor}"></div></div>
      <div class="ai-stats">
        <div><span>Średnia pewność</span><b>${ai.srednia_pewnosc !== null ? Math.round(ai.srednia_pewnosc * 100) + '%' : '—'}</b></div>
        <div><span>Do weryfikacji</span><b style="color:${ai.wymaga_weryfikacji ? 'var(--color-orange)' : 'inherit'}">${ai.wymaga_weryfikacji}</b></div>
        ${pomylka ? `<div><span>Najczęstsza pomyłka</span><b>${escHtml(kategoriaPL(pomylka.z))} → ${escHtml(kategoriaPL(pomylka.na))}</b></div>` : ''}
      </div>
    </div>`;
}

// --- Pulpit technika ---------------------------------------------------------
async function pulpitTechnika(c, odswiezenie) {
  const zakladka = ZAKLADKI_PULPITU[pulpit.zakladka] || ZAKLADKI_PULPITU.najnowsze;
  const [d, lista, ai] = await Promise.all([
    apiFetch('/dashboard'),
    apiFetch('/tickets?per_page=6' + zakladka.query),
    apiFetch('/ai/skutecznosc').catch(() => null),   // pulpit działa też bez tej karty
  ]);
  if (state.currentView !== 'dashboard') return;     // użytkownik zdążył przejść gdzie indziej

  const s = d.statystyki, p = d.puls;
  const naglowek = `
    <div class="pulpit-naglowek">
      <div>
        <h2>Konsola Obsługi IT</h2>
        <p>${new Date().toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long' })}
          · dziś <b>+${p.dzis_nowe}</b> nowych, <b>${p.dzis_zamkniete}</b> zamkniętych</p>
      </div>
      ${pasekNaZywo()}
    </div>`;

  const kpi = kafelki([
    { klucz: 'aktywne', etykieta: 'Aktywne', wartosc: s.otwarte - s.rozwiazane, podpis: `${s.w_trakcie} w trakcie`,
      kolor: 'var(--color-blue)', filtr: { skrot: 'aktywne' }, tytul: 'Zgłoszenia, nad którymi trwa praca' },
    { klucz: 'nieprzypisane', etykieta: 'Nieprzypisane', wartosc: p.nieprzypisane, podpis: 'czekają na technika',
      kolor: 'var(--color-orange)', filtr: { skrot: 'nieprzypisane' } },
    { klucz: 'po_terminie', etykieta: 'Po terminie SLA', wartosc: p.po_terminie, podpis: 'przekroczony czas',
      kolor: 'var(--color-error)', filtr: { skrot: 'po_terminie' }, alarm: p.po_terminie > 0 },
    { klucz: 'zagrozone', etykieta: 'Zagrożone SLA', wartosc: p.zagrozone, podpis: 'termin w ciągu 2 h',
      kolor: 'var(--color-warning)', akcja: "document.getElementById('panelSla').scrollIntoView({behavior:'smooth'})" },
    { klucz: 'krytyczne', etykieta: 'Krytyczne', wartosc: d.wg_priorytetu.Krytyczny || 0, podpis: 'aktywne, priorytet 1',
      kolor: 'var(--color-error)', filtr: { priority: 'Krytyczny', skrot: 'aktywne' } },
    { klucz: 'moje', etykieta: 'Moje', wartosc: p.moje, podpis: 'przypisane do Ciebie',
      kolor: 'var(--color-primary)', filtr: { skrot: 'moje' } },
    { klucz: 'rozwiazane', etykieta: 'Do zamknięcia', wartosc: s.rozwiazane, podpis: 'rozwiązane, czekają',
      kolor: 'var(--color-success)', filtr: { status: 'Rozwiazane' } },
  ], odswiezenie);

  const zakladki = Object.entries(ZAKLADKI_PULPITU).map(([k, z]) => `
    <button type="button" class="tab ${k === pulpit.zakladka ? 'active' : ''}" onclick="pulpit.zakladka='${k}';renderDashboard(true)">${z.nazwa}</button>`).join('');

  c.innerHTML = `
    ${naglowek}
    ${kpi}
    <div class="pulpit-grid">
      <div class="card">
        <div class="section-header"><div class="section-title">Ruch w zgłoszeniach</div><small class="muted">ostatnie ${d.trend.length} dni</small></div>
        ${wykresRuchu(d.trend, !odswiezenie)}
      </div>
      <div class="card">
        <div class="section-header"><div class="section-title">Kolejka wg priorytetu</div></div>
        ${donutPriorytetow(d.wg_priorytetu)}
      </div>
    </div>
    <div class="pulpit-grid pulpit-grid-rowne">
      <div class="card" id="panelSla">
        <div class="section-header"><div class="section-title">Pilnuj SLA</div>
          ${p.po_terminie ? `<button class="btn btn-sm btn-secondary" onclick="${linkListy({ skrot: 'po_terminie' })}">Wszystkie po terminie (${p.po_terminie})</button>` : ''}</div>
        ${panelSla(d.pilne_sla)}
      </div>
      <div class="card">
        <div class="section-header"><div class="section-title">Ostatnia aktywność</div><span class="live-dot ${pulpit.auto ? 'on' : ''}"></span></div>
        ${kanalAktywnosci(d.aktywnosc, odswiezenie)}
      </div>
    </div>
    <div class="pulpit-grid pulpit-grid-trzy">
      <div class="card">
        <div class="section-header"><div class="section-title">Obciążenie zespołu</div><small class="muted">aktywne zgłoszenia</small></div>
        ${obciazenieZespolu(d.obciazenie)}
      </div>
      <div class="card">
        <div class="section-header"><div class="section-title">Kategorie</div><small class="muted">kliknij, aby filtrować</small></div>
        ${slupkiKategorii(d.wg_kategorii)}
      </div>
      ${kartaAI(ai)}
    </div>
    <div class="card">
      <div class="section-header">
        <div class="tabs">${zakladki}</div>
        <button class="btn btn-sm btn-secondary" onclick="navigate('all-tickets')">Wszystkie zgłoszenia</button>
      </div>
      ${lista.tickets.length ? renderTicketTable(lista.tickets, true) : emptyState('Brak zgłoszeń w tym widoku.')}
    </div>`;

  if (!odswiezenie) animujLiczniki(c);
}

// --- Pulpit pracownika -------------------------------------------------------
const SZABLONY_ZGLOSZEN = [
  { ikona: '🌐', tytul: 'Brak dostępu do internetu',
    opis: 'Od [godzina] nie mam dostępu do internetu na komputerze. Inne osoby w pokoju [mają / nie mają] ten sam problem.' },
  { ikona: '🔑', tytul: 'Nie mogę się zalogować',
    opis: 'Nie mogę zalogować się do [nazwa systemu]. Komunikat błędu: [treść komunikatu].' },
  { ikona: '🖨️', tytul: 'Drukarka nie drukuje',
    opis: 'Drukarka [nazwa / pokój] nie drukuje. Objawy: [np. zacina papier, brak reakcji, błąd na wyświetlaczu].' },
  { ikona: '📧', tytul: 'Problem z pocztą',
    opis: 'Nie mogę [wysłać / odebrać] wiadomości w Outlooku. Komunikat: [treść komunikatu].' },
  { ikona: '💻', tytul: 'Komputer działa nieprawidłowo',
    opis: 'Mój komputer [nie włącza się / zawiesza się / wyświetla niebieski ekran]. Problem występuje od [kiedy].' },
  { ikona: '⚠️', tytul: 'Podejrzany e-mail',
    opis: 'Przyszła podejrzana wiadomość od [nadawca] — wygląda na phishing. Nadawca prosi o [podanie hasła / kliknięcie w link].' },
];

function nowyZSzablonu(i) {
  navigate('new-ticket');
  const s = SZABLONY_ZGLOSZEN[i];
  document.getElementById('ticketTitle').value = s.tytul;
  const opis = document.getElementById('ticketDesc');
  opis.value = s.opis;
  opis.focus();
  // Zaznacz pierwszy fragment do uzupełnienia, żeby od razu go nadpisać.
  const od = s.opis.indexOf('['), doo = s.opis.indexOf(']');
  if (od >= 0) opis.setSelectionRange(od, doo + 1);
  podpowiedzAI();
}

function chipySzablonow() {
  return `<div class="chips">${SZABLONY_ZGLOSZEN.map((s, i) => `
    <button type="button" class="chip" onclick="nowyZSzablonu(${i})"><span>${s.ikona}</span>${escHtml(s.tytul)}</button>`).join('')}</div>`;
}

const KROKI_STATUSU = ['Nowe', 'W trakcie', 'Rozwiazane', 'Zamkniete'];

function postepZgloszenia(t) {
  const wstrzymane = t.status === 'Wstrzymane';
  const biezacy = wstrzymane ? 1 : KROKI_STATUSU.indexOf(t.status);
  return `<div class="stepper">${KROKI_STATUSU.map((k, i) => `
    <div class="step ${i < biezacy ? 'done' : ''} ${i === biezacy ? 'current' : ''} ${wstrzymane && i === 1 ? 'paused' : ''}">
      <span class="step-dot"></span><span class="step-label">${wstrzymane && i === 1 ? 'Wstrzymane' : statusLabel(k)}</span>
    </div>`).join('')}</div>`;
}

function kartaZgloszenia(t) {
  return `
    <div class="ticket-card" onclick="openTicket(${t.id})">
      <div class="ticket-card-head">
        <div><span class="td-id">#${t.id}</span> <b>${escHtml(t.title)}</b></div>
        ${priorityBadge(t.priority)}
      </div>
      <div class="feed-meta">${escHtml(kategoriaPL(t.category || '—'))} ${znacznikAI(t)}
        · ${t.assigned_to_name ? `zajmuje się: <b>${escHtml(t.assigned_to_name)}</b>` : 'czeka na technika'}</div>
      ${postepZgloszenia(t)}
      ${t.status !== 'Rozwiazane' ? `<div class="feed-meta">Czas obsługi wg SLA: ${licznikSla(t.sla_deadline)}</div>` : ''}
    </div>`;
}

async function pulpitPracownika(c, odswiezenie) {
  // Liczniki pochodzą z backendu (zakres: własne zgłoszenia pracownika).
  // Liczenie ich z pobranej listy dawałoby błędne wyniki, bo lista jest stronicowana.
  const [d, aktywne, ostatnie] = await Promise.all([
    apiFetch('/dashboard'),
    apiFetch('/tickets?per_page=6&aktywne=1'),
    apiFetch('/tickets?per_page=5'),
  ]);
  if (state.currentView !== 'dashboard') return;
  const s = d.statystyki;

  const kpi = kafelki([
    { klucz: 'w_toku', etykieta: 'W obsłudze', wartosc: s.otwarte - s.rozwiazane, podpis: 'aktywne zgłoszenia',
      kolor: 'var(--color-primary)', akcja: "navigate('my-tickets')" },
    { klucz: 'rozwiazane', etykieta: 'Rozwiązane', wartosc: s.rozwiazane, podpis: 'czekają na zamknięcie',
      kolor: 'var(--color-warning)', akcja: "navigate('my-tickets')" },
    { klucz: 'zamkniete', etykieta: 'Zamknięte', wartosc: s.zamkniete, podpis: 'sprawy zakończone',
      kolor: 'var(--color-success)', akcja: "navigate('my-tickets')" },
    { klucz: 'wszystkie', etykieta: 'Łącznie', wartosc: s.wszystkie, podpis: 'wszystkich zgłoszeń', akcja: "navigate('my-tickets')" },
  ], odswiezenie);

  c.innerHTML = `
    <div class="pulpit-naglowek">
      <div>
        <h2>Witaj, ${escHtml(state.user.split(' ')[0])}! 👋</h2>
        <p>${state.clientName ? escHtml(state.clientName) + ' · ' : ''}Zarządzaj swoimi zgłoszeniami IT</p>
      </div>
      ${pasekNaZywo()}
    </div>
    ${kpi}
    <div class="card cta-card">
      <div>
        <div class="section-title">Coś nie działa?</div>
        <p class="muted">Wybierz gotowy szablon albo opisz problem własnymi słowami — moduł AI sam nada kategorię i priorytet.</p>
      </div>
      <button class="btn btn-primary" onclick="navigate('new-ticket')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
        Nowe zgłoszenie</button>
      ${chipySzablonow()}
    </div>
    <div class="pulpit-grid">
      <div class="card">
        <div class="section-header"><div class="section-title">Moje sprawy w toku</div>
          <button class="btn btn-sm btn-secondary" onclick="navigate('my-tickets')">Wszystkie</button></div>
        ${aktywne.tickets.length
          ? `<div class="ticket-cards">${aktywne.tickets.map(kartaZgloszenia).join('')}</div>`
          : emptyState('Nie masz otwartych spraw — wszystko działa. 🎉')}
      </div>
      <div class="card">
        <div class="section-header"><div class="section-title">Co się zmieniło</div><span class="live-dot ${pulpit.auto ? 'on' : ''}"></span></div>
        ${kanalAktywnosci(d.aktywnosc, odswiezenie)}
      </div>
    </div>
    <div class="card">
      <div class="section-header"><div class="section-title">Ostatnie zgłoszenia</div>
        <button class="btn btn-sm btn-secondary" onclick="navigate('my-tickets')">Zobacz wszystkie</button></div>
      ${ostatnie.tickets.length ? renderTicketTable(ostatnie.tickets, false) : emptyState('Nie masz jeszcze żadnych zgłoszeń.')}
    </div>`;

  if (!odswiezenie) animujLiczniki(c);
}

// ============================================================
// MY TICKETS
// ============================================================
async function renderMyTickets() {
  const c = document.getElementById('mainContent');
  try {
    const data = await apiFetch(`/tickets?page=${state.page}`);
    c.innerHTML = `
      <div class="card">
        <div class="section-header">
          <div class="section-title">Moje zgłoszenia <span style="color:var(--color-text-muted);font-weight:400;font-size:var(--text-sm)">(${data.total})</span></div>
          <button class="btn btn-sm btn-primary" onclick="navigate('new-ticket')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Nowe zgłoszenie
          </button>
        </div>
        ${data.tickets.length
          ? renderTicketTable(data.tickets, false) + renderPaginacja(data)
          : `<div class="empty-state">
              <div class="empty-icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg></div>
              <p>Nie masz jeszcze żadnych zgłoszeń.</p>
              <button class="btn btn-primary" style="margin-top:1rem" onclick="navigate('new-ticket')">Złóż pierwsze zgłoszenie</button>
            </div>`}
      </div>`;
  } catch (e) {
    c.innerHTML = errorCard(e.message);
  }
}

// ============================================================
// ALL TICKETS (technik/admin)
// ============================================================
// Skróty, którymi pulpit otwiera listę (kliknięcie w kafelek).
const SKROTY_LISTY = {
  aktywne:       { nazwa: 'Tylko aktywne',     query: '&aktywne=1' },
  nieprzypisane: { nazwa: 'Nieprzypisane',     query: '&przypisane=brak&aktywne=1' },
  moje:          { nazwa: 'Przypisane do mnie', query: '&przypisane=ja&aktywne=1' },
  po_terminie:   { nazwa: 'Po terminie SLA',   query: '&sla=przekroczone' },
};

const KATEGORIE = ['Sprzet', 'Oprogramowanie', 'Siec', 'Poczta', 'Konta i dostep', 'Bezpieczenstwo', 'Peryferia'];

async function renderAllTickets() {
  const c = document.getElementById('mainContent');
  try {
    let url = `/tickets?page=${state.page}`;
    if (state.filterStatus)   url += `&status=${encodeURIComponent(state.filterStatus)}`;
    if (state.filterPriority) url += `&priority=${encodeURIComponent(state.filterPriority)}`;
    if (state.filterClient)   url += `&client_id=${encodeURIComponent(state.filterClient)}`;
    if (state.filterCategory) url += `&category=${encodeURIComponent(state.filterCategory)}`;
    const skrot = SKROTY_LISTY[state.filterSkrot];
    if (skrot) url += skrot.query;
    const [data, klienci] = await Promise.all([apiFetch(url), pobierzKlientow()]);

    c.innerHTML = `
      <div class="card">
        <div class="section-header">
          <div class="section-title">Wszystkie zgłoszenia <span style="color:var(--color-text-muted);font-weight:400;font-size:var(--text-sm)">(${data.total})</span></div>
        </div>
        <div class="filters">
          <select class="filter-select" onchange="state.filterStatus=this.value;state.page=1;renderView('all-tickets')">
            <option value="">Wszystkie statusy</option>
            <option value="Nowe"       ${state.filterStatus==='Nowe'      ?'selected':''}>Nowe</option>
            <option value="W trakcie"  ${state.filterStatus==='W trakcie' ?'selected':''}>W trakcie</option>
            <option value="Wstrzymane" ${state.filterStatus==='Wstrzymane'?'selected':''}>Wstrzymane</option>
            <option value="Rozwiazane" ${state.filterStatus==='Rozwiazane'?'selected':''}>Rozwiązane</option>
            <option value="Zamkniete"  ${state.filterStatus==='Zamkniete' ?'selected':''}>Zamknięte</option>
          </select>
          <select class="filter-select" onchange="state.filterPriority=this.value;state.page=1;renderView('all-tickets')">
            <option value="">Wszystkie priorytety</option>
            <option value="Krytyczny" ${state.filterPriority==='Krytyczny'?'selected':''}>Krytyczny</option>
            <option value="Wysoki"    ${state.filterPriority==='Wysoki'   ?'selected':''}>Wysoki</option>
            <option value="Sredni"    ${state.filterPriority==='Sredni'   ?'selected':''}>Średni</option>
            <option value="Niski"     ${state.filterPriority==='Niski'    ?'selected':''}>Niski</option>
          </select>
          <select class="filter-select" onchange="state.filterCategory=this.value;state.page=1;renderView('all-tickets')">
            <option value="">Wszystkie kategorie</option>
            ${KATEGORIE.map(k => `<option value="${k}" ${state.filterCategory===k?'selected':''}>${escHtml(kategoriaPL(k))}</option>`).join('')}
          </select>
          <select class="filter-select" onchange="state.filterClient=this.value;state.page=1;renderView('all-tickets')">
            <option value="">Wszyscy klienci</option>
            ${klienci.map(k => `<option value="${k.id}" ${String(k.id)===String(state.filterClient)?'selected':''}>${escHtml(k.name)}</option>`).join('')}
          </select>
          ${skrot ? `<button type="button" class="chip chip-active" onclick="state.filterSkrot='';state.page=1;renderView('all-tickets')"
                      title="Usuń filtr">${skrot.nazwa} <span aria-hidden="true">×</span></button>` : ''}
        </div>
        ${data.tickets.length
          ? renderTicketTable(data.tickets, true) + renderPaginacja(data)
          : emptyState('Brak zgłoszeń spełniających wybrane kryteria.')}
      </div>`;
  } catch (e) {
    c.innerHTML = errorCard(e.message);
  }
}

// ============================================================
// CLIENTS (technik/admin)
// ============================================================
// Lista klientów zmienia się rzadko, a filtr potrzebuje jej przy każdym
// przełączeniu strony listy — pobieramy ją raz i trzymamy w stanie.
async function pobierzKlientow(odswiez = false) {
  if (!state.klienci || odswiez) state.klienci = await apiFetch('/clients');
  return state.klienci;
}

async function renderClients() {
  const c = document.getElementById('mainContent');
  try {
    // Widok klientów pokazuje liczniki — zawsze aktualne, nie z pamięci.
    const klienci = await pobierzKlientow(true);
    const rows = klienci.map(k => `
      <tr onclick="pokazZgloszeniaKlienta(${k.id})" style="cursor:pointer" title="Pokaż zgłoszenia klienta">
        <td style="font-weight:500">${escHtml(k.name)}</td>
        <td class="td-muted">${k.pracownikow}</td>
        <td>${k.zgloszen}</td>
        <td>${k.otwartych
          ? `<span class="badge badge-wrealizacji">${k.otwartych}</span>`
          : '<span class="td-muted">0</span>'}</td>
        <td style="text-align:right">
          <button class="btn btn-sm btn-secondary" onclick="event.stopPropagation();pokazRaportKlienta(${k.id})">Raport</button>
        </td>
      </tr>`).join('');

    c.innerHTML = `
      <div class="card">
        <div class="section-header">
          <div class="section-title">Klienci <span style="color:var(--color-text-muted);font-weight:400;font-size:var(--text-sm)">(${klienci.length})</span></div>
        </div>
        ${klienci.length ? `
          <div class="table-wrap">
            <table>
              <thead><tr><th>Firma</th><th>Pracownicy</th><th>Zgłoszenia</th><th>Otwarte</th><th></th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>` : emptyState('Brak klientów w systemie.')}
      </div>`;
  } catch (e) {
    c.innerHTML = errorCard(e.message);
  }
}

function pokazRaportKlienta(id) {
  state.raport.klient = String(id);
  navigate('reports');
}

function pokazZgloszeniaKlienta(id) {
  state.filterClient = String(id);
  state.filterStatus = '';
  state.filterPriority = '';
  navigate('all-tickets');
}

// ============================================================
// REPORTS (technik/admin)
// ============================================================
// Doby raportu to doby UTC (tak liczy backend), więc „dziś" też w UTC.
function dataUTC(dniWstecz = 0) {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - dniWstecz);
  return d.toISOString().slice(0, 10);
}

// Daty RRRR-MM-DD formatujemy z tekstu, a nie przez new Date(): ten
// zinterpretowałby je jako północ UTC i w strefach na zachód od Greenwich
// pokazał poprzedni dzień.
function formatDzien(iso) {
  const [r, m, d] = iso.split('-');
  return `${d}.${m}.${r}`;
}
function formatMiesiac(iso) {
  const [r, m] = iso.split('-');
  return `${m}.${r}`;
}
function formatLiczba(x) {
  return x.toLocaleString('pl-PL', { maximumFractionDigits: 1 });
}
function formatProcent(x) {
  return x === null ? '—' : `${formatLiczba(x)}%`;
}
function formatCzas(godzin) {
  if (godzin === null) return '—';
  if (godzin < 1)  return `${Math.round(godzin * 60)} min`;
  if (godzin < 48) return `${formatLiczba(godzin)} h`;
  return `${formatLiczba(godzin / 24)} dni`;
}

const ZAKRESY_RAPORTU = [
  ['7', 'Ostatnie 7 dni'], ['30', 'Ostatnie 30 dni'], ['90', 'Ostatnie 90 dni'],
  ['365', 'Ostatnie 12 miesięcy'], ['wlasny', 'Własny zakres'],
];

async function renderReports() {
  const c = document.getElementById('mainContent');
  try {
    const klienci = await pobierzKlientow();
    const r = state.raport;
    const ukryj = r.zakres === 'wlasny' ? '' : 'hidden';
    c.innerHTML = `
      <div class="card no-print">
        <div class="report-controls">
          <div class="form-field">
            <label class="form-label" for="raportKlient">Klient</label>
            <select class="form-input" id="raportKlient">
              <option value="">Wszyscy klienci</option>
              ${klienci.map(k => `<option value="${k.id}" ${String(k.id) === r.klient ? 'selected' : ''}>${escHtml(k.name)}</option>`).join('')}
            </select>
          </div>
          <div class="form-field">
            <label class="form-label" for="raportZakres">Okres</label>
            <select class="form-input" id="raportZakres" onchange="przelaczZakresRaportu()">
              ${ZAKRESY_RAPORTU.map(([v, l]) => `<option value="${v}" ${v === r.zakres ? 'selected' : ''}>${l}</option>`).join('')}
            </select>
          </div>
          <div class="form-field raport-daty" ${ukryj}>
            <label class="form-label" for="raportOd">Od</label>
            <input class="form-input" type="date" id="raportOd" value="${escHtml(r.od)}" max="${dataUTC()}">
          </div>
          <div class="form-field raport-daty" ${ukryj}>
            <label class="form-label" for="raportDo">Do</label>
            <input class="form-input" type="date" id="raportDo" value="${escHtml(r.do)}">
          </div>
          <div class="report-actions">
            <button class="btn btn-primary" onclick="wygenerujRaport()">Generuj raport</button>
            <button class="btn btn-secondary" id="raportDrukuj" onclick="drukujRaport()" disabled>Drukuj / PDF</button>
          </div>
        </div>
      </div>
      <div id="raportWynik"></div>`;
    wygenerujRaport();
  } catch (e) {
    c.innerHTML = errorCard(e.message);
  }
}

function przelaczZakresRaportu() {
  const wlasny = document.getElementById('raportZakres').value === 'wlasny';
  document.querySelectorAll('.raport-daty').forEach(el => { el.hidden = !wlasny; });
  if (wlasny && !document.getElementById('raportOd').value) {
    document.getElementById('raportOd').value = dataUTC(29);
    document.getElementById('raportDo').value = dataUTC();
  }
}

async function wygenerujRaport() {
  const r = state.raport;
  r.klient = document.getElementById('raportKlient').value;
  r.zakres = document.getElementById('raportZakres').value;

  const params = new URLSearchParams();
  if (r.klient) params.set('client_id', r.klient);
  if (r.zakres === 'wlasny') {
    r.od = document.getElementById('raportOd').value;
    r.do = document.getElementById('raportDo').value;
    if (r.od) params.set('od', r.od);
    if (r.do) params.set('do', r.do);
  } else {
    params.set('od', dataUTC(Number(r.zakres) - 1));   // „od … do dziś"
  }

  // Szybkie kolejne kliknięcia: wynik starszego zapytania, który przyszedł
  // później, nie może nadpisać nowszego raportu.
  const numer = wygenerujRaport.numer = (wygenerujRaport.numer || 0) + 1;
  document.getElementById('raportDrukuj').disabled = true;
  document.getElementById('raportWynik').innerHTML = spinner();
  state.ostatniRaport = null;

  let html;
  try {
    const dane = await apiFetch(`/reports?${params}`);
    if (numer !== wygenerujRaport.numer) return;
    state.ostatniRaport = dane;
    html = renderRaport(dane);
  } catch (e) {
    if (numer !== wygenerujRaport.numer) return;
    html = `<div style="margin-top:1rem">${errorCard(e.message)}</div>`;
  }
  // Użytkownik mógł w międzyczasie przejść do innego widoku.
  const wynik = document.getElementById('raportWynik');
  if (!wynik) return;
  wynik.innerHTML = html;
  document.getElementById('raportDrukuj').disabled = !state.ostatniRaport;
}

function kpiRaportu(etykieta, wartosc, podpis, kolor = '', dodatek = '') {
  return `
    <div class="card kpi-card">
      <div class="kpi-label">${etykieta}</div>
      <div class="kpi-value" ${kolor ? `style="color:${kolor}"` : ''}>${wartosc}${dodatek}</div>
      <div class="kpi-sub">${podpis}</div>
    </div>`;
}

// Więcej zgłoszeń to dla klienta gorzej — wzrost na czerwono, spadek na zielono.
function zmianaHtml(zmiana, teraz, poprzednio, klasa = 'kpi-delta') {
  if (zmiana === null) {
    return teraz > 0 && poprzednio === 0 ? `<span class="${klasa} delta-none">nowe</span>` : '';
  }
  if (zmiana === 0) return `<span class="${klasa} delta-none">bez zmian</span>`;
  const wzrost = zmiana > 0;
  return `<span class="${klasa} ${wzrost ? 'delta-up' : 'delta-down'}">${wzrost ? '▲' : '▼'} ${formatLiczba(Math.abs(zmiana))}%</span>`;
}

function wykresKategorii(wiersze) {
  if (!wiersze.length) return emptyState('Brak zgłoszeń w tym okresie.');
  const max = Math.max(1, ...wiersze.map(w => Math.max(w.liczba, w.poprzednio)));
  const slupki = wiersze.map(w => {
    const nazwa = escHtml(w.etykieta);
    return `
      <div class="bar-row" title="${nazwa}: ${w.liczba} (poprzedni okres: ${w.poprzednio})">
        <div class="bar-label">${nazwa}</div>
        <div class="bar-track">
          ${w.liczba ? `<div class="bar-fill" style="width:${w.liczba / max * 100}%"></div>` : ''}
          ${w.poprzednio ? `<div class="bar-prev" style="left:${w.poprzednio / max * 100}%"></div>` : ''}
        </div>
        <div class="bar-value">${w.liczba} ${zmianaHtml(w.zmiana_proc, w.liczba, w.poprzednio, '')}</div>
      </div>`;
  }).join('');
  return slupki + `
    <div class="chart-legend">
      <span><span class="legend-swatch"></span>wybrany okres</span>
      <span><span class="legend-line"></span>poprzedni okres</span>
    </div>`;
}

const KOLORY_PRIORYTETOW = {
  'Krytyczny': 'var(--color-error)', 'Wysoki': 'var(--color-orange)',
  'Sredni': 'var(--color-warning)', 'Niski': 'var(--color-success)',
};

function wykresPriorytetow(wiersze, razem) {
  if (!razem) return emptyState('Brak zgłoszeń w tym okresie.');
  const max = Math.max(1, ...wiersze.map(w => w.liczba));
  return wiersze.map(w => `
    <div class="bar-row">
      <div class="bar-label">${priorityBadge(w.priorytet)}</div>
      <div class="bar-track">
        ${w.liczba ? `<div class="bar-fill" style="width:${w.liczba / max * 100}%;background:${KOLORY_PRIORYTETOW[w.priorytet] || 'var(--color-text-muted)'}"></div>` : ''}
      </div>
      <div class="bar-value">${w.liczba} <small>${formatProcent(Math.round(w.liczba / razem * 1000) / 10)}</small></div>
    </div>`).join('');
}

function wykresProblemow(problemy) {
  if (!problemy.length) return emptyState('Moduł AI nie rozpoznał powtarzających się słów kluczowych.');
  const max = problemy[0].liczba;
  return problemy.map(p => `
    <div class="bar-row">
      <div class="bar-label" title="${escHtml(p.problem)}">${escHtml(p.problem)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${p.liczba / max * 100}%"></div></div>
      <div class="bar-value">${p.liczba} <small>zgł.</small></div>
    </div>`).join('') + `
    <p style="font-size:var(--text-xs);color:var(--color-text-muted);margin-top:0.75rem">
      Problemy rozpoznane przez moduł AI w treści zgłoszeń.
    </p>`;
}

// Szerokość rysunku odpowiada miejscu na ekranie, a nie stałej wartości —
// inaczej na telefonie przeskalowany wykres miał podpisy wielkości 6 px.
function wykresTrendu(trend, grupowanie) {
  const obszar = document.getElementById('mainContent');
  const W = Math.round(Math.min(960, Math.max(300, (obszar ? obszar.clientWidth : 700) - 90)));
  const H = 200, L = 34, P = 6, G = 8, D = 24;
  const n = trend.length;
  const max = Math.max(1, ...trend.map(t => t.liczba));
  const krok = (W - L - P) / n;
  const szer = Math.max(1, krok * 0.72);
  const y = v => G + (H - G - D) * (1 - v / max);
  const etykieta = t => grupowanie === 'miesiac' ? formatMiesiac(t.okres) : formatDzien(t.okres).slice(0, 5);

  // Podpisy osi X: przy wielu słupkach co kilka, zawsze pierwszy i ostatni.
  // Jeden podpis potrzebuje ok. 70 px szerokości.
  const co = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(W / 70))));
  const podpisy = trend.map((t, i) => (i % co === 0 || i === n - 1) && !(i !== n - 1 && n - 1 - i < co / 2)
    ? `<text class="trend-label" x="${L + krok * i + krok / 2}" y="${H - 6}" text-anchor="middle">${etykieta(t)}</text>` : '').join('');

  const polowa = Math.round(max / 2);
  const linie = [0, polowa, max].filter((v, i, a) => a.indexOf(v) === i).map(v => `
    <line class="trend-grid" x1="${L}" x2="${W - P}" y1="${y(v)}" y2="${y(v)}"/>
    <text class="trend-label" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`).join('');

  const slupki = trend.map((t, i) => {
    const wys = (H - G - D) * (t.liczba / max);
    return `<rect class="trend-bar" x="${L + krok * i + (krok - szer) / 2}" y="${H - D - wys}" width="${szer}" height="${wys}" rx="1.5">
      <title>${grupowanie === 'miesiac' ? formatMiesiac(t.okres) : formatDzien(t.okres)}${grupowanie === 'tydzien' ? ' (tydzień)' : ''}: ${t.liczba}</title></rect>`;
  }).join('');

  const suma = trend.reduce((s, t) => s + t.liczba, 0);
  return `<svg class="trend-chart" viewBox="0 0 ${W} ${H}" role="img"
               aria-label="Trend zgłoszeń: ${suma} zgłoszeń w ${n} przedziałach, najwięcej ${max} w jednym">
    ${linie}${slupki}${podpisy}</svg>`;
}

function renderRaport(d) {
  const p = d.podsumowanie;
  const pop = d.poprzedni_okres;
  const nazwa = d.klient ? d.klient.name : 'Wszyscy klienci';
  const grup = { dzien: 'dziennie', tydzien: 'tygodniowo', miesiac: 'miesięcznie' }[d.okres.grupowanie];
  const kolorSla = p.procent_w_terminie_sla === null ? ''
    : p.procent_w_terminie_sla >= 80 ? 'var(--color-success)' : 'var(--color-error)';

  return `
    <div class="report-header">
      <div>
        <div class="report-title">Raport zgłoszeń — ${escHtml(nazwa)}</div>
        <div class="report-meta">
          Okres: ${formatDzien(d.okres.od)} – ${formatDzien(d.okres.do)} (${d.okres.dni} dni) ·
          porównanie z okresem ${formatDzien(pop.od)} – ${formatDzien(pop.do)}
        </div>
      </div>
      <div class="report-meta">Wygenerowano: ${new Date().toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' })}</div>
    </div>

    <div class="report-grid report-kpis">
      ${kpiRaportu('Zgłoszenia', p.zgloszen, `poprzednio: ${pop.zgloszen}`, '',
                   zmianaHtml(pop.zmiana_proc, p.zgloszen, pop.zgloszen))}
      ${kpiRaportu('Rozwiązane', formatProcent(p.procent_rozwiazanych), `${p.rozwiazanych} z ${p.zgloszen}`)}
      ${kpiRaportu('Średni czas rozwiązania', formatCzas(p.sredni_czas_rozwiazania_h), 'od zgłoszenia do rozwiązania')}
      ${kpiRaportu('W terminie SLA', formatProcent(p.procent_w_terminie_sla),
                   `${p.w_terminie_sla} z ${p.rozwiazanych_z_terminem} rozwiązanych`, kolorSla)}
      ${kpiRaportu('Po terminie', p.otwartych_po_terminie, `z ${p.otwartych} otwartych`,
                   p.otwartych_po_terminie ? 'var(--color-error)' : '')}
    </div>

    <div class="report-grid">
      <div class="card">
        <div class="section-header"><div class="section-title">Zgłoszenia według kategorii</div></div>
        ${wykresKategorii(d.wg_kategorii)}
      </div>
      <div class="card">
        <div class="section-header"><div class="section-title">Priorytety</div></div>
        ${wykresPriorytetow(d.wg_priorytetu, p.zgloszen)}
      </div>
    </div>

    <div class="card" style="margin-bottom:1rem">
      <div class="section-header"><div class="section-title">Trend zgłoszeń (${grup})</div></div>
      ${p.zgloszen ? wykresTrendu(d.trend, d.okres.grupowanie) : emptyState('Brak zgłoszeń w tym okresie.')}
    </div>

    <div class="report-grid">
      <div class="card">
        <div class="section-header"><div class="section-title">Najczęstsze problemy</div></div>
        ${wykresProblemow(d.najczestsze_problemy)}
      </div>
      <div class="card">
        <div class="section-header"><div class="section-title">Wnioski i rekomendacje</div></div>
        <ul class="recommendations">${d.rekomendacje.map(t => `<li>${escHtml(t)}</li>`).join('')}</ul>
      </div>
    </div>`;
}

// Nazwa pliku PDF w oknie drukowania pochodzi z tytułu strony.
function drukujRaport() {
  const d = state.ostatniRaport;
  if (!d) return;
  drukujRaport.tytul = document.title;
  document.title = `Raport ${d.klient ? d.klient.name : 'wszyscy klienci'} ${d.okres.od} - ${d.okres.do}`;
  window.print();
}

// Wydruk zawsze w jasnym motywie (także z Ctrl+P) — ciemne tło na papierze
// jest nieczytelne i zużywa toner. Tytuł wracamy dopiero po wydruku, bo
// część przeglądarek otwiera okno drukowania asynchronicznie.
let motywPrzedWydrukiem = null;
window.addEventListener('beforeprint', () => {
  motywPrzedWydrukiem = document.documentElement.getAttribute('data-theme');
  document.documentElement.setAttribute('data-theme', 'light');
});
window.addEventListener('afterprint', () => {
  if (motywPrzedWydrukiem) document.documentElement.setAttribute('data-theme', motywPrzedWydrukiem);
  if (drukujRaport.tytul) { document.title = drukujRaport.tytul; drukujRaport.tytul = null; }
});

// ============================================================
// NEW TICKET FORM
// ============================================================
function renderNewTicket() {
  return `
    <div style="max-width:640px">
      <div class="card">
        <h2 style="font-size:var(--text-base);font-weight:600;margin-bottom:0.75rem">Zgłoś problem IT</h2>
        <div class="form-label" style="margin-bottom:0.25rem">Szybki start</div>
        ${chipySzablonow()}
        <div class="form-field" style="margin-top:1rem">
          <label class="form-label" for="ticketTitle">Tytuł problemu *</label>
          <input class="form-input" type="text" id="ticketTitle" oninput="podpowiedzAI()" placeholder="Krótki opis problemu, np. Brak dostępu do internetu">
        </div>
        <div class="form-field">
          <label class="form-label" for="ticketDesc">Szczegółowy opis *</label>
          <textarea class="form-input form-textarea" id="ticketDesc" oninput="podpowiedzAI()" placeholder="Opisz szczegółowo problem — kiedy wystąpił, co robiłeś, jakie komunikaty błędów widzisz..."></textarea>
        </div>
        <div id="aiPodpowiedz" class="ai-hint" aria-live="polite"></div>
        <div id="aiStatus"></div>
        <div style="display:flex;gap:0.75rem;margin-top:1.25rem">
          <button class="btn btn-primary" id="submitBtn" onclick="submitTicket()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            Wyślij zgłoszenie
          </button>
          <button class="btn btn-secondary" onclick="navigate('dashboard')">Anuluj</button>
        </div>
      </div>
    </div>`;
}

// Podgląd na żywo: w trakcie pisania pokazujemy, jak moduł AI oceni
// zgłoszenie. Zapytanie idzie dopiero po chwili bez pisania, żeby nie
// wysyłać go po każdym znaku.
function podpowiedzAI() {
  clearTimeout(podpowiedzAI._t);
  podpowiedzAI._t = setTimeout(async () => {
    const box = document.getElementById('aiPodpowiedz');
    if (!box) return;
    const title = document.getElementById('ticketTitle').value.trim();
    const description = document.getElementById('ticketDesc').value.trim();
    if (title.length + description.length < 8) { box.innerHTML = ''; return; }
    try {
      const ai = await apiFetch('/ai/categorize', { method: 'POST', body: JSON.stringify({ title, description }) });
      if (!document.getElementById('aiPodpowiedz')) return;
      box.innerHTML = ai.wymaga_weryfikacji
        ? `<span class="badge badge-ai">AI</span> Opisz problem dokładniej — na razie nie umiem go przypisać do kategorii.`
        : `<span class="badge badge-ai">AI</span> Wygląda na: <b>${escHtml(kategoriaPL(ai.kategoria))}</b> ${priorityBadge(ai.priorytet)}
           <small class="muted">pewność ${Math.round(ai.pewnosc * 100)}% · SLA ${{ Krytyczny: '1 h', Wysoki: '4 h', Sredni: '8 h', Niski: '24 h' }[ai.priorytet] || ''}</small>`;
    } catch { box.innerHTML = ''; }
  }, 500);
}

// ============================================================
// TABLE RENDERER
// ============================================================
function renderTicketTable(tickets, showAuthor) {
  const rows = tickets.map(t => `
    <tr onclick="openTicket(${t.id})" style="cursor:pointer">
      <td class="td-id">#${t.id}</td>
      <td>
        <div style="font-weight:500">${escHtml(t.title)}</div>
        <div class="td-muted">${escHtml(t.category || '—')} ${znacznikAI(t)}</div>
      </td>
      <td>${priorityBadge(t.priority)}</td>
      <td>${statusBadge(t.status)}</td>
      ${showAuthor ? `<td class="td-muted">
        ${escHtml(t.created_by_name || '#' + t.created_by)}
        ${t.client_name ? `<div style="font-size:var(--text-xs)">${escHtml(t.client_name)}</div>` : ''}
      </td>` : ''}
      <td class="td-muted">${formatDate(t.created_at)}</td>
    </tr>`).join('');

  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>ID</th><th>Zgłoszenie</th><th>Priorytet</th><th>Status</th>
            ${showAuthor ? '<th>Zgłaszający</th>' : ''}
            <th>Data</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ============================================================
// TICKET DETAIL MODAL
// ============================================================
async function openTicket(id) {
  const modal   = document.getElementById('ticketModal');
  const content = document.getElementById('ticketModalContent');
  content.innerHTML = `<div style="padding:3rem;text-align:center">${spinner()}</div>`;
  modal.classList.add('open');

  try {
    const t = await apiFetch(`/tickets/${id}`);
    const isTechnik = state.role === 'technik' || state.role === 'admin';
    const allowed   = TRANSITIONS[t.status] || [];

    const notesList = t.notes.length
      ? t.notes.map(n => `
          <div class="note-item">
            <div class="note-meta">
              <span class="note-author">${escHtml(n.author)}</span>
              <span class="note-time">${formatDateTime(n.created_at)}</span>
              ${n.internal ? '<span class="badge badge-ai" style="font-size:10px">wewn.</span>' : ''}
            </div>
            <div class="note-text">${escHtml(n.content)}</div>
          </div>`).join('')
      : '<p style="color:var(--color-text-muted);font-size:var(--text-sm)">Brak notatek.</p>';

    const techActions = isTechnik ? `
      <div class="divider"></div>
      ${allowed.length ? `
        <div class="form-field">
          <label class="form-label">Zmień status</label>
          <select class="form-input filter-select" id="modalStatus" style="width:100%">
            ${allowed.map(s => `<option value="${s}">${statusLabel(s)}</option>`).join('')}
          </select>
        </div>` : `<p style="font-size:var(--text-sm);color:var(--color-text-muted);margin-bottom:0.75rem">Zgłoszenie zamknięte — brak dostępnych zmian statusu.</p>`}
      <div class="form-field">
        <label class="form-label">Dodaj notatkę wewnętrzną</label>
        <textarea class="form-input form-textarea" id="modalNote" placeholder="Opisz wykonane działania..." style="min-height:70px"></textarea>
      </div>` : '';

    content.innerHTML = `
      <div class="modal-header">
        <div>
          <div class="modal-title">${escHtml(t.title)}</div>
          <div class="modal-id">#${t.id} · ${formatDateTime(t.created_at)}</div>
        </div>
        <button class="btn btn-ghost modal-close" onclick="closeModal()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
      <div class="modal-body">
        <div class="info-grid">
          <div class="info-item"><div class="info-item-label">Status</div>${statusBadge(t.status)}</div>
          <div class="info-item"><div class="info-item-label">Priorytet</div>${priorityBadge(t.priority)}</div>
          <div class="info-item">
            <div class="info-item-label">Kategoria</div>
            <div style="font-size:var(--text-sm);display:flex;align-items:center;gap:0.375rem;flex-wrap:wrap">
              ${escHtml(t.category || '—')}
              ${znacznikAI(t)}
            </div>
            ${t.ai_categorized && t.ai_pewnosc !== null && t.ai_pewnosc < PROG_PEWNOSCI
              ? `<div style="font-size:var(--text-xs);color:var(--color-error);margin-top:0.25rem">
                   Niska pewność — sprawdź, czy kategoria jest właściwa
                 </div>` : ''}
          </div>
          ${t.sla_deadline ? `<div class="info-item"><div class="info-item-label">Termin SLA</div><div style="font-size:var(--text-sm)">${formatDateTime(t.sla_deadline)}</div></div>` : ''}
          <div class="info-item">
            <div class="info-item-label">Zgłaszający</div>
            <div style="font-size:var(--text-sm)">${escHtml(t.created_by_name || '#' + t.created_by)}</div>
          </div>
          <div class="info-item">
            <div class="info-item-label">Klient</div>
            <div style="font-size:var(--text-sm)">${escHtml(t.client_name || '—')}</div>
          </div>
          <div class="info-item">
            <div class="info-item-label">Przypisano do</div>
            <div style="font-size:var(--text-sm)">${escHtml(t.assigned_to_name || '—')}</div>
          </div>
        </div>
        <div class="info-item" style="margin-bottom:1rem">
          <div class="info-item-label" style="margin-bottom:0.375rem">Opis problemu</div>
          <div class="desc-block">${escHtml(t.description)}</div>
        </div>
        <div class="notes-section">
          <div class="notes-title">Notatki</div>
          ${notesList}
        </div>
        ${techActions}
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeModal()">Zamknij</button>
        ${isTechnik ? `<button class="btn btn-primary" id="saveModalBtn" onclick="saveTicketChanges(${t.id}, ${allowed.length > 0})">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
          ${allowed.length ? 'Zapisz' : 'Dodaj notatkę'}
        </button>` : ''}
      </div>`;
  } catch (e) {
    content.innerHTML = `<div style="padding:2rem">${errorCard(e.message)}<br><button class="btn btn-secondary" style="margin-top:1rem" onclick="closeModal()">Zamknij</button></div>`;
  }
}

function closeModal() {
  document.getElementById('ticketModal').classList.remove('open');
}

async function saveTicketChanges(id, changeStatus) {
  const btn      = document.getElementById('saveModalBtn');
  const noteText = (document.getElementById('modalNote')?.value || '').trim();
  const newStatus = changeStatus ? document.getElementById('modalStatus')?.value : null;

  if (!newStatus && !noteText) { closeModal(); return; }

  if (btn) { btn.disabled = true; btn.textContent = 'Zapisywanie...'; }

  try {
    if (newStatus) {
      await apiFetch(`/tickets/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: newStatus }),
      });
    }
    if (noteText) {
      await apiFetch(`/tickets/${id}/notes`, {
        method: 'POST',
        body: JSON.stringify({ content: noteText, internal: true }),
      });
    }
    closeModal();
    renderView(state.currentView);
  } catch (e) {
    showError(e.message);
    if (btn) { btn.disabled = false; btn.textContent = changeStatus ? 'Zapisz' : 'Dodaj notatkę'; }
  }
}

// ============================================================
// SUBMIT TICKET
// ============================================================
async function submitTicket() {
  const title = document.getElementById('ticketTitle').value.trim();
  const desc  = document.getElementById('ticketDesc').value.trim();
  if (!title) { document.getElementById('ticketTitle').focus(); return; }
  if (!desc)  { document.getElementById('ticketDesc').focus(); return; }

  const btn = document.getElementById('submitBtn');
  btn.disabled = true; btn.textContent = 'Wysyłanie...';

  document.getElementById('aiStatus').innerHTML = `
    <div class="ai-processing">
      <svg class="ai-spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
      <span>Moduł AI analizuje zgłoszenie...</span>
    </div>`;

  try {
    const res = await apiFetch('/tickets', {
      method: 'POST',
      body: JSON.stringify({ title, description: desc }),
    });
    const ai = res.kategoryzacja_ai;

    document.getElementById('aiStatus').innerHTML = `
      <div class="ai-result">
        <div class="ai-result-title">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
          Zgłoszenie #${res.id} — skategoryzowane przez AI
        </div>
        <div class="ai-result-row"><span class="ai-result-label">Kategoria</span><strong style="font-size:var(--text-sm)">${escHtml(ai.kategoria)}</strong></div>
        <div class="ai-result-row"><span class="ai-result-label">Priorytet</span>${priorityBadge(ai.priorytet)}</div>
        <div class="ai-result-row"><span class="ai-result-label">Status</span>${statusBadge('Nowe')}</div>
      </div>`;

    setTimeout(() => {
      document.getElementById('mainContent').innerHTML = `
        <div style="max-width:640px"><div class="card">
          <div class="success-state">
            <div class="success-icon">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <div class="success-title">Zgłoszenie zostało wysłane!</div>
            <div class="success-desc">
              Twoje zgłoszenie <strong>#${res.id}</strong> zostało zarejestrowane w systemie.<br>
              AI przypisało kategorię <strong>${escHtml(ai.kategoria)}</strong> z priorytetem <strong>${escHtml(ai.priorytet)}</strong>.
            </div>
            <div style="display:flex;gap:0.75rem;justify-content:center;margin-top:1.5rem">
              <button class="btn btn-primary" onclick="navigate('my-tickets')">Moje zgłoszenia</button>
              <button class="btn btn-secondary" onclick="navigate('new-ticket')">Nowe zgłoszenie</button>
            </div>
          </div>
        </div></div>`;
    }, 1500);
  } catch (e) {
    document.getElementById('aiStatus').innerHTML = '';
    showError(e.message || 'Błąd podczas tworzenia zgłoszenia.');
    btn.disabled = false;
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg> Wyślij zgłoszenie';
  }
}

// ============================================================
// HELPERS
// ============================================================
const STATUS_LABELS = {
  'Nowe':'Nowe', 'W trakcie':'W trakcie', 'Wstrzymane':'Wstrzymane',
  'Rozwiazane':'Rozwiązane', 'Zamkniete':'Zamknięte',
};
function statusLabel(s) { return STATUS_LABELS[s] || s; }

function priorityBadge(p) {
  const cls  = { 'Krytyczny':'badge-krityczny','Wysoki':'badge-wysoki','Sredni':'badge-sredni','Niski':'badge-niski' };
  const dots = { 'Krytyczny':'var(--color-error)','Wysoki':'var(--color-orange)','Sredni':'var(--color-warning)','Niski':'var(--color-success)' };
  return `<span class="badge ${cls[p]||''}"><span style="width:6px;height:6px;border-radius:50%;background:${dots[p]||'currentColor'};flex-shrink:0"></span>${escHtml(p||'—')}</span>`;
}

// Próg zgodny z PROG_PEWNOSCI w ai.py — poniżej niego moduł sam sygnalizuje,
// że zgadywał, a nie rozpoznał.
const PROG_PEWNOSCI = 0.4;

function znacznikAI(t) {
  if (!t.ai_categorized) return '';
  const p = t.ai_pewnosc;
  if (p !== null && p !== undefined && p < PROG_PEWNOSCI) {
    return `<span class="badge badge-krityczny" title="Moduł AI nie był pewny (${Math.round(p * 100)}%) — warto sprawdzić kategorię">AI ?</span>`;
  }
  const opis = (p === null || p === undefined) ? 'Kategoria nadana przez AI'
             : `Kategoria nadana przez AI (pewność ${Math.round(p * 100)}%)`;
  return `<span class="badge badge-ai" title="${opis}">AI</span>`;
}

function statusBadge(s) {
  const cls = { 'Nowe':'badge-nowe','W trakcie':'badge-wrealizacji','Zamkniete':'badge-zamkniete','Wstrzymane':'badge-oczekujace','Rozwiazane':'badge-sredni' };
  return `<span class="badge ${cls[s]||''}">${statusLabel(s)}</span>`;
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('pl-PL', { day:'2-digit', month:'2-digit', year:'numeric' });
}

function formatDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('pl-PL', { day:'2-digit', month:'2-digit', year:'numeric' })
    + ' ' + d.toLocaleTimeString('pl-PL', { hour:'2-digit', minute:'2-digit' });
}

function escHtml(str) {
  if (str == null) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function emptyState(msg) {
  return `<div class="empty-state"><p>${escHtml(msg)}</p></div>`;
}

function errorCard(msg) {
  return `<div style="padding:1rem;border:1px solid var(--color-error);border-radius:var(--radius-md);color:var(--color-error);font-size:var(--text-sm)">⚠ ${escHtml(msg)}</div>`;
}

// ============================================================
// THEME
// ============================================================
(function() {
  const d = matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', d);
})();

function toggleTheme() {
  const html = document.documentElement;
  const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  const btn = document.getElementById('themeToggle');
  btn.innerHTML = next === 'dark'
    ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
    : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
}

// ============================================================
// SESSION RESTORE
// ============================================================
// Po odswiezeniu strony token jest nadal w sessionStorage — sprawdzamy go
// w backendzie, zamiast ufac danym z przegladarki.
async function restoreSession() {
  const token = sessionStorage.getItem('helpdesk_token');
  if (!token) return;

  state.token = token;
  try {
    const data = await apiFetch('/auth/me');
    state.userId = data.id;
    state.user   = data.name;
    state.role   = data.role;
    state.clientName = data.client_name;

    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('app').classList.add('visible');
    setupSidebar();
    navigate('dashboard');
  } catch {
    // Token wygasl lub jest nieprawidlowy — zostajemy na ekranie logowania.
    state.token = null;
    sessionStorage.removeItem('helpdesk_token');
  }
}

// Close modal on backdrop click
document.getElementById('ticketModal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});

restoreSession();

// Enter key on password field
document.getElementById('loginPassword').addEventListener('keydown', e => {
  if (e.key === 'Enter') doLogin();
});
