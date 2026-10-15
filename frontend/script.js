// ============================================================
// STATE & CONFIG
// ============================================================
const API = '/api';

let state = {
  userId: null,
  token:  null,
  user:   null,
  role:   null,
  clientName: null,     // firma pracownika; null dla technika i kierownika
  currentView: 'dashboard',
  filterStatus: '',
  filterPriority: '',
  filterClient: '',
  klienci: null,        // lista klientów do filtra — pobierana raz na sesję
  raport: { klient: '', zakres: '30', od: '', do: '' },   // ostatnie ustawienia raportu
  ostatniRaport: null,
  zespol: { zakres: '30', od: '', do: '' },        // okres raportu zespołu (kierownik)
  statystyki: { zakres: '30', od: '', do: '' },    // okres raportu technika
  wybranyTechnik: null,                            // technik oglądany przez kierownika
  personel: null,                                  // technicy do listy przypisania
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

// Personel helpdesku to technicy i kierownik; kierownik dodatkowo przydziela
// pracę, widzi statystyki zespołu i zmienia czasy SLA. Serwer egzekwuje te
// uprawnienia niezależnie — interfejs tylko nie pokazuje niedostępnych opcji.
function jestPersonelem() { return state.role === 'technik' || state.role === 'kierownik'; }
function jestKierownikiem() { return state.role === 'kierownik'; }

function showInfo(msg) {
  showError(msg);
  document.getElementById('globalError').style.background = 'var(--color-success)';
}

function showError(msg) {
  const el = document.getElementById('globalError');
  if (!el) return;
  el.style.background = 'var(--color-error)';
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
  state.zespol = { zakres: '30', od: '', do: '' };
  state.statystyki = { zakres: '30', od: '', do: '' };
  state.wybranyTechnik = null; state.personel = null;
  state.filterStatus = ''; state.filterPriority = ''; state.filterClient = ''; state.page = 1;
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

  const isTechnik = jestPersonelem();
  document.getElementById('userRoleSidebar').textContent =
    jestKierownikiem() ? 'Kierownik IT' : isTechnik ? 'Technik IT'
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
    if (jestKierownikiem()) {
      items += `
      <div class="nav-section-label" style="margin-top:0.5rem">Zarządzanie</div>
      <a class="nav-item" data-view="team" onclick="navigate('team')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        Zespół
      </a>
      <a class="nav-item" data-view="settings" onclick="navigate('settings')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        Ustawienia SLA
      </a>`;
    } else {
      items += `
      <a class="nav-item" data-view="my-stats" onclick="navigate('my-stats')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        Moje statystyki
      </a>`;
    }
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
  // Raport technika otwierany z widoku zespołu podświetla „Zespół".
  const wMenu = view === 'technician' ? 'team' : view;
  document.querySelectorAll('.nav-item').forEach(el =>
    el.classList.toggle('active', el.dataset.view === wMenu)
  );
  const titles = {
    'dashboard':   'Dashboard',
    'new-ticket':  'Nowe zgłoszenie',
    'my-tickets':  'Moje zgłoszenia',
    'all-tickets': 'Wszystkie zgłoszenia',
    'clients':     'Klienci',
    'reports':     'Raporty',
    'team':        'Zespół',
    'technician':  'Statystyki technika',
    'my-stats':    'Moje statystyki',
    'settings':    'Ustawienia SLA',
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
    case 'team':        renderTeam(); break;
    case 'technician':  renderTechnician(state.wybranyTechnik); break;
    case 'my-stats':    renderTechnician(state.userId); break;
    case 'settings':    renderSettings(); break;
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
async function renderDashboard() {
  const c = document.getElementById('mainContent');
  const isTechnik = jestPersonelem();
  try {
    if (isTechnik) {
      const [dash, ticketData, kolejka] = await Promise.all([
        apiFetch('/dashboard'),
        apiFetch('/tickets?per_page=6'),   // pulpit pokazuje tylko ostatnie
        jestKierownikiem() ? apiFetch('/queue') : null,
      ]);
      const s = dash.statystyki;
      const recent = ticketData.tickets;
      c.innerHTML = `
        <div style="margin-bottom:1.5rem">
          <h2 style="font-size:var(--text-lg);font-weight:700;margin-bottom:0.25rem">Konsola Obsługi IT</h2>
          <p style="color:var(--color-text-muted);font-size:var(--text-sm)">Dzisiaj: ${new Date().toLocaleDateString('pl-PL',{weekday:'long',year:'numeric',month:'long',day:'numeric'})}</p>
        </div>
        <div class="kpi-grid">
          <div class="card kpi-card">
            <div class="kpi-label">Otwarte</div>
            <div class="kpi-value" style="color:var(--color-blue)">${s.otwarte}</div>
            <div class="kpi-sub"><span class="kpi-dot" style="background:var(--color-blue)"></span>aktywne zgłoszenia</div>
          </div>
          <div class="card kpi-card">
            <div class="kpi-label">W trakcie</div>
            <div class="kpi-value" style="color:var(--color-primary)">${s.w_trakcie}</div>
            <div class="kpi-sub"><span class="kpi-dot" style="background:var(--color-primary)"></span>w toku obsługi</div>
          </div>
          <div class="card kpi-card">
            <div class="kpi-label">Krytyczne</div>
            <div class="kpi-value" style="color:var(--color-error)">${s.krytyczne}</div>
            <div class="kpi-sub"><span class="kpi-dot" style="background:var(--color-error)"></span>wymagają uwagi</div>
          </div>
          <div class="card kpi-card">
            <div class="kpi-label">Rozwiązane</div>
            <div class="kpi-value" style="color:var(--color-success)">${s.rozwiazane}</div>
            <div class="kpi-sub"><span class="kpi-dot" style="background:var(--color-success)"></span>do zamknięcia</div>
          </div>
        </div>
        ${kolejka ? renderKolejka(kolejka) : ''}
        <div class="card">
          <div class="section-header">
            <div class="section-title">Ostatnie zgłoszenia</div>
            <button class="btn btn-sm btn-secondary" onclick="navigate('all-tickets')">Wszystkie zgłoszenia</button>
          </div>
          ${recent.length ? renderTicketTable(recent, true) : emptyState('Brak zgłoszeń w systemie.')}
        </div>`;
    } else {
      // Liczniki pochodzą z backendu (zakres: własne zgłoszenia pracownika).
      // Liczenie ich z pobranej listy dawałoby błędne wyniki, bo lista jest
      // stronicowana i zawiera tylko pierwszą stronę.
      const [dash, ticketData] = await Promise.all([
        apiFetch('/dashboard'),
        apiFetch('/tickets?per_page=5'),
      ]);
      const tickets  = ticketData.tickets;
      const myOpen   = dash.statystyki.otwarte;
      const myClosed = dash.statystyki.zamkniete;
      const myTotal  = dash.statystyki.wszystkie;
      c.innerHTML = `
        <div style="margin-bottom:1.5rem">
          <h2 style="font-size:var(--text-lg);font-weight:700;margin-bottom:0.25rem">Witaj, ${escHtml(state.user.split(' ')[0])}! 👋</h2>
          <p style="color:var(--color-text-muted);font-size:var(--text-sm)">${state.clientName ? escHtml(state.clientName) + ' · ' : ''}Zarządzaj swoimi zgłoszeniami IT</p>
        </div>
        <div class="kpi-grid">
          <div class="card kpi-card">
            <div class="kpi-label">Moje otwarte</div>
            <div class="kpi-value" style="color:var(--color-primary)">${myOpen}</div>
            <div class="kpi-sub">aktywne zgłoszenia</div>
          </div>
          <div class="card kpi-card">
            <div class="kpi-label">Zamknięte</div>
            <div class="kpi-value" style="color:var(--color-success)">${myClosed}</div>
            <div class="kpi-sub">rozwiązane sprawy</div>
          </div>
          <div class="card kpi-card">
            <div class="kpi-label">Łącznie</div>
            <div class="kpi-value">${myTotal}</div>
            <div class="kpi-sub">wszystkich zgłoszeń</div>
          </div>
        </div>
        <div class="card">
          <div class="section-header">
            <div class="section-title">Ostatnie zgłoszenia</div>
            <button class="btn btn-sm btn-secondary" onclick="navigate('my-tickets')">Zobacz wszystkie</button>
          </div>
          ${tickets.length
            ? renderTicketTable(tickets, false)
            : `<div class="empty-state">
                <div class="empty-icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>
                <p>Nie masz jeszcze żadnych zgłoszeń.<br>Kliknij „Nowe zgłoszenie" aby zacząć.</p>
                <button class="btn btn-primary" style="margin-top:1rem" onclick="navigate('new-ticket')">Nowe zgłoszenie</button>
              </div>`}
        </div>`;
    }
  } catch (e) {
    c.innerHTML = errorCard(e.message || 'Błąd ładowania danych.');
  }
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
// ALL TICKETS (technik/kierownik)
// ============================================================
async function renderAllTickets() {
  const c = document.getElementById('mainContent');
  try {
    let url = `/tickets?page=${state.page}`;
    if (state.filterStatus)   url += `&status=${encodeURIComponent(state.filterStatus)}`;
    if (state.filterPriority) url += `&priority=${encodeURIComponent(state.filterPriority)}`;
    if (state.filterClient)   url += `&client_id=${encodeURIComponent(state.filterClient)}`;
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
          <select class="filter-select" onchange="state.filterClient=this.value;state.page=1;renderView('all-tickets')">
            <option value="">Wszyscy klienci</option>
            ${klienci.map(k => `<option value="${k.id}" ${String(k.id)===String(state.filterClient)?'selected':''}>${escHtml(k.name)}</option>`).join('')}
          </select>
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
// CLIENTS (technik/kierownik)
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
          ${k.obslugiwany ? `<button class="btn btn-sm btn-secondary" onclick="event.stopPropagation();pokazRaportKlienta(${k.id})">Raport</button>` : ''}
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
// REPORTS (technik/kierownik)
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

// Wybór okresu — ten sam w raportach klientów, zespołu i technika.
// `prefiks` rozróżnia pola na stronie, `ust` to zapamiętane ustawienia widoku.
function kontrolkiOkresu(prefiks, ust) {
  const ukryj = ust.zakres === 'wlasny' ? '' : 'hidden';
  return `
    <div class="form-field">
      <label class="form-label" for="${prefiks}Zakres">Okres</label>
      <select class="form-input" id="${prefiks}Zakres" onchange="przelaczZakres('${prefiks}')">
        ${ZAKRESY_RAPORTU.map(([v, l]) => `<option value="${v}" ${v === ust.zakres ? 'selected' : ''}>${l}</option>`).join('')}
      </select>
    </div>
    <div class="form-field ${prefiks}-daty" ${ukryj}>
      <label class="form-label" for="${prefiks}Od">Od</label>
      <input class="form-input" type="date" id="${prefiks}Od" value="${escHtml(ust.od)}" max="${dataUTC()}">
    </div>
    <div class="form-field ${prefiks}-daty" ${ukryj}>
      <label class="form-label" for="${prefiks}Do">Do</label>
      <input class="form-input" type="date" id="${prefiks}Do" value="${escHtml(ust.do)}">
    </div>`;
}

function przelaczZakres(prefiks) {
  const wlasny = document.getElementById(`${prefiks}Zakres`).value === 'wlasny';
  document.querySelectorAll(`.${prefiks}-daty`).forEach(el => { el.hidden = !wlasny; });
  if (wlasny && !document.getElementById(`${prefiks}Od`).value) {
    document.getElementById(`${prefiks}Od`).value = dataUTC(29);
    document.getElementById(`${prefiks}Do`).value = dataUTC();
  }
}

// Odczytuje okres z pól, zapamiętuje go w `ust` i dopisuje do zapytania.
function parametryOkresu(prefiks, ust, params) {
  ust.zakres = document.getElementById(`${prefiks}Zakres`).value;
  if (ust.zakres === 'wlasny') {
    ust.od = document.getElementById(`${prefiks}Od`).value;
    ust.do = document.getElementById(`${prefiks}Do`).value;
    if (ust.od) params.set('od', ust.od);
    if (ust.do) params.set('do', ust.do);
  } else {
    params.set('od', dataUTC(Number(ust.zakres) - 1));   // „od … do dziś"
  }
  return params;
}

// Pobiera i wyświetla wynik w kontenerze. Szybkie kolejne kliknięcia:
// odpowiedź starszego zapytania, która przyszła później, nie może nadpisać
// nowszej; użytkownik mógł też w międzyczasie przejść do innego widoku.
async function wygenerujWidok(klucz, url, kontener, przycisk, renderuj) {
  const numer = wygenerujWidok[klucz] = (wygenerujWidok[klucz] || 0) + 1;
  document.getElementById(przycisk).disabled = true;
  document.getElementById(kontener).innerHTML = spinner();
  state.ostatniRaport = null;

  let html, dane = null;
  try {
    dane = await apiFetch(url);
    if (numer !== wygenerujWidok[klucz]) return null;
    html = renderuj(dane);
  } catch (e) {
    if (numer !== wygenerujWidok[klucz]) return null;
    html = `<div style="margin-top:1rem">${errorCard(e.message)}</div>`;
    dane = null;
  }
  const wynik = document.getElementById(kontener);
  if (!wynik) return null;
  wynik.innerHTML = html;
  state.ostatniRaport = dane;
  document.getElementById(przycisk).disabled = !dane;
  return dane;
}

async function renderReports() {
  const c = document.getElementById('mainContent');
  try {
    const klienci = await pobierzKlientow();
    const r = state.raport;
    // Technik tworzy raporty tylko dla obsługiwanych firm (serwer to egzekwuje);
    // kierownik — dla każdej firmy i zbiorczo.
    const dostepni = jestKierownikiem() ? klienci : klienci.filter(k => k.obslugiwany);
    if (!dostepni.length) {
      c.innerHTML = `<div class="card">${emptyState('Nie obsługujesz jeszcze żadnej firmy — raport może utworzyć kierownik.')}</div>`;
      return;
    }
    if (!jestKierownikiem() && !dostepni.some(k => String(k.id) === r.klient)) {
      r.klient = String(dostepni[0].id);
    }
    c.innerHTML = `
      <div class="card no-print">
        <div class="report-controls">
          <div class="form-field">
            <label class="form-label" for="raportKlient">Klient</label>
            <select class="form-input" id="raportKlient">
              ${jestKierownikiem() ? '<option value="">Wszyscy klienci</option>' : ''}
              ${dostepni.map(k => `<option value="${k.id}" ${String(k.id) === r.klient ? 'selected' : ''}>${escHtml(k.name)}</option>`).join('')}
            </select>
          </div>
          ${kontrolkiOkresu('raport', r)}
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

async function wygenerujRaport() {
  const r = state.raport;
  r.klient = document.getElementById('raportKlient').value;
  const params = parametryOkresu('raport', r, new URLSearchParams());
  if (r.klient) params.set('client_id', r.klient);
  await wygenerujWidok('raport', `/reports?${params}`, 'raportWynik', 'raportDrukuj', renderRaport);
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
function drukuj(tytul) {
  drukuj.poprzedni = document.title;
  document.title = tytul;
  window.print();
}

function drukujRaport() {
  const d = state.ostatniRaport;
  if (!d) return;
  drukuj(`Raport ${d.klient ? d.klient.name : 'wszyscy klienci'} ${d.okres.od} - ${d.okres.do}`);
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
  if (drukuj.poprzedni) { document.title = drukuj.poprzedni; drukuj.poprzedni = null; }
});

// ============================================================
// TEAM (kierownik) — kolejka, statystyki zespołu i techników
// ============================================================
// Technicy do listy przypisania w szczegółach zgłoszenia — z tej samej
// odpowiedzi co statystyki zespołu, pobierane raz na sesję.
async function pobierzPersonel() {
  if (!state.personel) {
    const dane = await apiFetch('/team');
    state.personel = dane.technicy.map(t => ({ id: t.id, name: t.name, role: t.role }));
  }
  return state.personel;
}

// Ile zostało do terminu SLA albo jak dawno minął — to decyduje o kolejności
// działań kierownika, więc jest ważniejsze niż sama data.
function czasDoTerminu(iso) {
  if (!iso) return '<span class="td-muted">bez terminu</span>';
  const godzin = (new Date(iso) - Date.now()) / 3600000;
  return godzin < 0
    ? `<span style="color:var(--color-error);font-weight:500">po terminie ${formatCzas(-godzin)}</span>`
    : `za ${formatCzas(godzin)}`;
}

function listaKolejki(zgloszenia, pokazOpiekuna) {
  if (!zgloszenia.length) return emptyState('Brak — wszystko pod kontrolą.');
  const wiersze = zgloszenia.slice(0, 5).map(t => `
    <tr onclick="openTicket(${t.id})" style="cursor:pointer">
      <td>
        <div style="font-weight:500">${escHtml(t.title)}</div>
        <div class="td-muted" style="font-size:var(--text-xs)">#${t.id} · ${escHtml(t.client_name || '—')}</div>
      </td>
      <td>${priorityBadge(t.priority)}</td>
      <td style="font-size:var(--text-sm);white-space:nowrap">
        ${czasDoTerminu(t.sla_deadline)}
        ${pokazOpiekuna ? `<div class="td-muted" style="font-size:var(--text-xs)">${escHtml(t.assigned_to_name || 'bez opiekuna')}</div>` : ''}
      </td>
    </tr>`).join('');
  return `<div class="table-wrap"><table><tbody>${wiersze}</tbody></table></div>`;
}

function renderKolejka(k) {
  const karta = (tytul, opis, czesc, klasa, pokazOpiekuna) => `
    <div class="card">
      <div class="section-header">
        <div class="section-title">${tytul} <span class="badge ${klasa}">${czesc.liczba}</span></div>
      </div>
      <p style="font-size:var(--text-xs);color:var(--color-text-muted);margin:-0.5rem 0 0.5rem">${opis}</p>
      ${listaKolejki(czesc.zgloszenia, pokazOpiekuna)}
    </div>`;
  return `
    <div class="report-grid">
      ${karta('Bez opiekuna', 'Otwarte zgłoszenia, których nikt nie prowadzi — kliknij, aby przydzielić.',
              k.nieprzypisane, 'badge-nowe', false)}
      ${karta('Zagrożone SLA', `Termin mija w ciągu ${k.prog_godzin} h albo już minął.`,
              k.zagrozone, 'badge-krityczny', true)}
    </div>`;
}

async function renderTeam() {
  const c = document.getElementById('mainContent');
  c.innerHTML = `
    <div class="card no-print">
      <div class="report-controls">
        ${kontrolkiOkresu('zespol', state.zespol)}
        <div class="report-actions">
          <button class="btn btn-primary" onclick="wygenerujZespol()">Generuj raport</button>
          <button class="btn btn-secondary" id="zespolDrukuj" onclick="drukujZespol()" disabled>Drukuj / PDF</button>
        </div>
      </div>
    </div>
    <div id="zespolWynik"></div>`;
  wygenerujZespol();
}

async function wygenerujZespol() {
  const params = parametryOkresu('zespol', state.zespol, new URLSearchParams());
  const dane = await wygenerujWidok('zespol', `/team?${params}`, 'zespolWynik', 'zespolDrukuj', renderZespol);
  if (dane) state.personel = dane.technicy.map(t => ({ id: t.id, name: t.name, role: t.role }));
}

function drukujZespol() {
  const d = state.ostatniRaport;
  if (d) drukuj(`Raport zespolu ${d.okres.od} - ${d.okres.do}`);
}

function pokazTechnika(id) {
  state.wybranyTechnik = id;
  navigate('technician');
}

function etykietaRoli(rola) {
  return rola === 'kierownik' ? '<span class="badge badge-ai">kierownik</span>' : '';
}

// Wspólne kafelki statystyk — zespół i pojedynczy technik.
function kafelkiStatystyk(s) {
  const kolorSla = s.procent_w_terminie_sla === null ? ''
    : s.procent_w_terminie_sla >= 80 ? 'var(--color-success)' : 'var(--color-error)';
  return `
    <div class="report-grid report-kpis">
      ${kpiRaportu('Rozwiązane', s.rozwiazanych, `poprzednio: ${s.rozwiazanych_poprzednio}`, '',
                   zmianaPracy(s.zmiana_proc, s.rozwiazanych, s.rozwiazanych_poprzednio))}
      ${kpiRaportu('Średni czas reakcji', formatCzas(s.sredni_czas_reakcji_h), `${s.podjetych} podjętych zgłoszeń`)}
      ${kpiRaportu('Średni czas rozwiązania', formatCzas(s.sredni_czas_rozwiazania_h), 'od zgłoszenia do rozwiązania')}
      ${kpiRaportu('W terminie SLA', formatProcent(s.procent_w_terminie_sla),
                   `${s.w_terminie_sla} z ${s.rozwiazanych_z_terminem} rozwiązanych`, kolorSla)}
      ${kpiRaportu('Otwarte teraz', s.otwartych, `${s.otwartych_po_terminie} po terminie`,
                   s.otwartych_po_terminie ? 'var(--color-error)' : '')}
    </div>`;
}

// Więcej ROZWIĄZANYCH zgłoszeń to dobrze — kolory odwrotnie niż w raporcie
// klienta, gdzie więcej zgłoszeń oznacza więcej awarii.
function zmianaPracy(zmiana, teraz, poprzednio) {
  return zmianaHtml(zmiana, teraz, poprzednio)
    .replace('delta-up', 'delta-tmp').replace('delta-down', 'delta-up').replace('delta-tmp', 'delta-down');
}

function renderZespol(d) {
  const z = d.zespol;
  const max = Math.max(1, ...d.technicy.map(t => Math.max(t.rozwiazanych, t.rozwiazanych_poprzednio)));
  const wiersze = d.technicy.map(t => `
    <tr onclick="pokazTechnika(${t.id})" style="cursor:pointer" title="Raport technika">
      <td style="font-weight:500">${escHtml(t.name)} ${etykietaRoli(t.role)}</td>
      <td>${t.otwartych}${t.otwartych_po_terminie ? ` <span class="badge badge-krityczny">${t.otwartych_po_terminie} po terminie</span>` : ''}</td>
      <td>${t.podjetych}</td>
      <td class="td-muted">${formatCzas(t.sredni_czas_reakcji_h)}</td>
      <td>${t.rozwiazanych} ${zmianaPracy(t.zmiana_proc, t.rozwiazanych, t.rozwiazanych_poprzednio)}</td>
      <td class="td-muted">${formatCzas(t.sredni_czas_rozwiazania_h)}</td>
      <td>${formatProcent(t.procent_w_terminie_sla)}</td>
      <td class="td-muted">${t.notatek}</td>
    </tr>`).join('');
  const slupki = d.technicy.map(t => `
    <div class="bar-row" title="${escHtml(t.name)}: ${t.rozwiazanych} (poprzedni okres: ${t.rozwiazanych_poprzednio})">
      <div class="bar-label">${escHtml(t.name)}</div>
      <div class="bar-track">
        ${t.rozwiazanych ? `<div class="bar-fill" style="width:${t.rozwiazanych / max * 100}%"></div>` : ''}
        ${t.rozwiazanych_poprzednio ? `<div class="bar-prev" style="left:${t.rozwiazanych_poprzednio / max * 100}%"></div>` : ''}
      </div>
      <div class="bar-value">${t.rozwiazanych}</div>
    </div>`).join('');

  return `
    <div class="report-header">
      <div>
        <div class="report-title">Raport zespołu</div>
        <div class="report-meta">
          Okres: ${formatDzien(d.okres.od)} – ${formatDzien(d.okres.do)} (${d.okres.dni} dni) ·
          porównanie z okresem ${formatDzien(d.poprzedni_okres.od)} – ${formatDzien(d.poprzedni_okres.do)}
        </div>
      </div>
      <div class="report-meta">Wygenerowano: ${new Date().toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' })}</div>
    </div>
    ${kafelkiStatystyk(z)}
    <div class="card" style="margin-bottom:1rem">
      <div class="section-header"><div class="section-title">Technicy</div></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Technik</th><th>Otwarte teraz</th><th>Podjęte</th><th>Śr. reakcja</th>
            <th>Rozwiązane</th><th>Śr. rozwiązanie</th><th>W terminie SLA</th><th>Notatki</th></tr></thead>
          <tbody>${wiersze}</tbody>
        </table>
      </div>
      <p style="font-size:var(--text-xs);color:var(--color-text-muted);margin-top:0.75rem">
        Kolejność alfabetyczna — statystyki opisują obciążenie i tempo pracy, a nie ranking.
        Kliknij technika, aby zobaczyć jego raport.
      </p>
    </div>
    <div class="card" style="margin-bottom:1rem">
      <div class="section-header"><div class="section-title">Rozwiązane zgłoszenia</div></div>
      ${slupki}
      <div class="chart-legend">
        <span><span class="legend-swatch"></span>wybrany okres</span>
        <span><span class="legend-line"></span>poprzedni okres</span>
      </div>
    </div>`;
}

async function renderTechnician(id) {
  const c = document.getElementById('mainContent');
  if (!id) { navigate(jestKierownikiem() ? 'team' : 'dashboard'); return; }
  const powrot = jestKierownikiem()
    ? `<button class="btn btn-secondary" onclick="navigate('team')">← Zespół</button>` : '';
  c.innerHTML = `
    <div class="card no-print">
      <div class="report-controls">
        ${kontrolkiOkresu('technik', state.statystyki)}
        <div class="report-actions">
          ${powrot}
          <button class="btn btn-primary" onclick="wygenerujTechnika(${Number(id)})">Generuj raport</button>
          <button class="btn btn-secondary" id="technikDrukuj" onclick="drukujTechnika()" disabled>Drukuj / PDF</button>
        </div>
      </div>
    </div>
    <div id="technikWynik"></div>`;
  wygenerujTechnika(id);
}

async function wygenerujTechnika(id) {
  const params = parametryOkresu('technik', state.statystyki, new URLSearchParams());
  await wygenerujWidok('technik', `/team/${Number(id)}?${params}`, 'technikWynik', 'technikDrukuj',
                       renderRaportTechnika);
}

function drukujTechnika() {
  const d = state.ostatniRaport;
  if (d) drukuj(`Raport ${d.technik.name} ${d.okres.od} - ${d.okres.do}`);
}

function renderRaportTechnika(d) {
  const s = d.statystyki;
  const grup = { dzien: 'dziennie', tydzien: 'tygodniowo', miesiac: 'miesięcznie' }[d.okres.grupowanie];
  const max = Math.max(1, ...d.wg_kategorii.map(k => k.liczba));
  const kategorie = d.wg_kategorii.map(k => `
    <div class="bar-row">
      <div class="bar-label">${escHtml(k.etykieta)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${k.liczba / max * 100}%"></div></div>
      <div class="bar-value">${k.liczba}</div>
    </div>`).join('');
  return `
    <div class="report-header">
      <div>
        <div class="report-title">Statystyki — ${escHtml(d.technik.name)} ${etykietaRoli(d.technik.role)}</div>
        <div class="report-meta">
          Okres: ${formatDzien(d.okres.od)} – ${formatDzien(d.okres.do)} (${d.okres.dni} dni) ·
          porównanie z okresem ${formatDzien(d.poprzedni_okres.od)} – ${formatDzien(d.poprzedni_okres.do)}
        </div>
      </div>
      <div class="report-meta">Notatki w okresie: ${s.notatek}</div>
    </div>
    ${kafelkiStatystyk(s)}
    <div class="report-grid">
      <div class="card">
        <div class="section-header"><div class="section-title">Rozwiązane zgłoszenia (${grup})</div></div>
        ${s.rozwiazanych ? wykresTrendu(d.trend, d.okres.grupowanie) : emptyState('Brak rozwiązanych zgłoszeń w tym okresie.')}
      </div>
      <div class="card">
        <div class="section-header"><div class="section-title">Kategorie rozwiązanych</div></div>
        ${kategorie || emptyState('Brak rozwiązanych zgłoszeń w tym okresie.')}
      </div>
    </div>
    <div class="card">
      <div class="section-header"><div class="section-title">Otwarte zgłoszenia (${s.otwartych})</div></div>
      ${d.otwarte.length ? renderTicketTable(d.otwarte, true) : emptyState('Brak otwartych zgłoszeń.')}
    </div>`;
}

// ------------------------------------------------------------ ustawienia SLA
const PRIORYTETY = ['Krytyczny', 'Wysoki', 'Sredni', 'Niski'];

async function renderSettings() {
  const c = document.getElementById('mainContent');
  try {
    const d = await apiFetch('/settings/sla');
    const pola = PRIORYTETY.map(p => `
      <div class="bar-row" style="grid-template-columns:8rem 8rem 1fr">
        <div>${priorityBadge(p)}</div>
        <input class="form-input" type="number" id="sla-${p}" value="${d.godziny[p]}"
               min="${d.zakres.min}" max="${d.zakres.max}" step="1" style="text-align:right">
        <div class="td-muted">godzin ${d.godziny[p] !== d.domyslne[p] ? `(domyślnie ${d.domyslne[p]})` : '(domyślnie)'}</div>
      </div>`).join('');
    const historia = d.historia.map(h => `
      <tr><td class="td-muted">${formatDateTime(h.kiedy)}</td><td>${escHtml(h.kto || '—')}</td>
          <td>${escHtml(h.ustawienie)}</td><td>${escHtml(h.stara)} → <strong>${escHtml(h.nowa)}</strong> h</td></tr>`).join('');
    c.innerHTML = `
      <div style="max-width:760px">
        <div class="card" style="margin-bottom:1rem">
          <div class="section-header"><div class="section-title">Czas na rozwiązanie zgłoszenia</div></div>
          <p style="font-size:var(--text-sm);color:var(--color-text-muted);margin-bottom:1rem">
            Priorytet nadaje moduł AI, a od niego zależy termin SLA. Zmiana dotyczy
            <strong>tylko nowych zgłoszeń</strong> — terminy istniejących się nie przesuwają.
          </p>
          ${pola}
          <button class="btn btn-primary" id="slaZapisz" style="margin-top:0.5rem" onclick="zapiszSla()">Zapisz zmiany</button>
        </div>
        <div class="card">
          <div class="section-header"><div class="section-title">Historia zmian</div></div>
          ${historia ? `<div class="table-wrap"><table>
            <thead><tr><th>Kiedy</th><th>Kto</th><th>Ustawienie</th><th>Zmiana</th></tr></thead>
            <tbody>${historia}</tbody></table></div>` : emptyState('Czasy SLA nie były jeszcze zmieniane.')}
        </div>
      </div>`;
    renderSettings.obecne = d.godziny;
  } catch (e) {
    c.innerHTML = errorCard(e.message);
  }
}

async function zapiszSla() {
  const zmiany = {};
  for (const p of PRIORYTETY) {
    const wartosc = Number(document.getElementById(`sla-${p}`).value);
    if (wartosc !== renderSettings.obecne[p]) zmiany[p] = wartosc;
  }
  if (!Object.keys(zmiany).length) { showInfo('Brak zmian do zapisania.'); return; }
  const btn = document.getElementById('slaZapisz');
  btn.disabled = true;
  try {
    // Walidację (liczba całkowita, zakres) wykonuje serwer — komunikat
    // błędu pochodzi wprost z jego odpowiedzi.
    await apiFetch('/settings/sla', { method: 'PUT', body: JSON.stringify({ godziny: zmiany }) });
    showInfo('Zapisano nowe czasy SLA.');
    renderSettings();
  } catch (e) {
    showError(e.message);
    btn.disabled = false;
  }
}

// ============================================================
// NEW TICKET FORM
// ============================================================
function renderNewTicket() {
  return `
    <div style="max-width:640px">
      <div class="card">
        <h2 style="font-size:var(--text-base);font-weight:600;margin-bottom:1.25rem">Zgłoś problem IT</h2>
        <div class="form-field">
          <label class="form-label" for="ticketTitle">Tytuł problemu *</label>
          <input class="form-input" type="text" id="ticketTitle" placeholder="Krótki opis problemu, np. Brak dostępu do internetu">
        </div>
        <div class="form-field">
          <label class="form-label" for="ticketDesc">Szczegółowy opis *</label>
          <textarea class="form-input form-textarea" id="ticketDesc" placeholder="Opisz szczegółowo problem — kiedy wystąpił, co robiłeś, jakie komunikaty błędów widzisz..."></textarea>
        </div>
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
    const [t, personel] = await Promise.all([
      apiFetch(`/tickets/${id}`),
      jestKierownikiem() ? pobierzPersonel() : null,
    ]);
    const isTechnik = jestPersonelem();
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

    // Przypisanie: kierownik przydziela i przenosi zgłoszenia; technik może
    // wziąć wolne zgłoszenie dla siebie.
    let przypisanie = '';
    if (personel) {
      przypisanie = `
        <div class="form-field">
          <label class="form-label" for="modalPrzypisz">Przypisz do</label>
          <select class="form-input filter-select" id="modalPrzypisz" style="width:100%">
            <option value="">— bez opiekuna —</option>
            ${personel.map(o => `<option value="${o.id}" ${o.id === t.assigned_to ? 'selected' : ''}>${escHtml(o.name)}${o.role === 'kierownik' ? ' (kierownik)' : ''}</option>`).join('')}
          </select>
        </div>`;
    } else if (isTechnik && t.assigned_to === null && t.status !== 'Zamkniete') {
      przypisanie = `
        <label class="form-field" style="display:flex;align-items:center;gap:0.5rem;font-size:var(--text-sm);cursor:pointer">
          <input type="checkbox" id="modalPrzypiszMnie"> Przypisz to zgłoszenie do mnie
        </label>`;
    }

    // Pierwsza opcja „bez zmiany": zapis samej notatki albo przypisania nie
    // może przy okazji przesuwać zgłoszenia do kolejnego statusu.
    const techActions = isTechnik ? `
      <div class="divider"></div>
      ${allowed.length ? `
        <div class="form-field">
          <label class="form-label">Zmień status</label>
          <select class="form-input filter-select" id="modalStatus" style="width:100%">
            <option value="">— bez zmiany —</option>
            ${allowed.map(s => `<option value="${s}">${statusLabel(s)}</option>`).join('')}
          </select>
        </div>` : `<p style="font-size:var(--text-sm);color:var(--color-text-muted);margin-bottom:0.75rem">Zgłoszenie zamknięte — brak dostępnych zmian statusu.</p>`}
      ${przypisanie}
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
        ${isTechnik ? `<button class="btn btn-primary" id="saveModalBtn" onclick="saveTicketChanges(${t.id}, ${t.assigned_to === null ? 'null' : t.assigned_to})">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
          Zapisz
        </button>` : ''}
      </div>`;
  } catch (e) {
    content.innerHTML = `<div style="padding:2rem">${errorCard(e.message)}<br><button class="btn btn-secondary" style="margin-top:1rem" onclick="closeModal()">Zamknij</button></div>`;
  }
}

function closeModal() {
  document.getElementById('ticketModal').classList.remove('open');
}

async function saveTicketChanges(id, obecnyOpiekun) {
  const btn      = document.getElementById('saveModalBtn');
  const noteText = (document.getElementById('modalNote')?.value || '').trim();

  // Status i przypisanie idą jednym żądaniem — serwer zapisuje je razem
  // albo wcale, więc konflikt nie zostawi zgłoszenia w połowie zmiany.
  const zmiany = {};
  const newStatus = document.getElementById('modalStatus')?.value;
  if (newStatus) zmiany.status = newStatus;
  const wybor = document.getElementById('modalPrzypisz');
  if (wybor) {
    const opiekun = wybor.value === '' ? null : Number(wybor.value);
    if (opiekun !== obecnyOpiekun) zmiany.assigned_to = opiekun;
  }
  if (document.getElementById('modalPrzypiszMnie')?.checked) zmiany.assigned_to = state.userId;

  if (!Object.keys(zmiany).length && !noteText) { closeModal(); return; }

  if (btn) { btn.disabled = true; btn.textContent = 'Zapisywanie...'; }

  try {
    if (Object.keys(zmiany).length) {
      await apiFetch(`/tickets/${id}`, { method: 'PATCH', body: JSON.stringify(zmiany) });
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
    if (btn) { btn.disabled = false; btn.textContent = 'Zapisz'; }
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
