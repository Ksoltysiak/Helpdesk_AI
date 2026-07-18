// ============================================================
// STATE
// ============================================================
let state = {
  user: null,
  role: 'pracownik',
  currentView: 'dashboard',
  tickets: [], // Pusta tablica - brak gotowych zgłoszeń
  filterStatus: 'wszystkie',
  filterPriority: 'wszystkie',
  nextId: 1, // Nowe zgłoszenia będą zaczynać się od INC-001
};

// ============================================================
// LOGIN / AUTH
// ============================================================
let selectedRole = 'pracownik';

function selectRole(role) {
  selectedRole = role;
  document.querySelectorAll('.role-card').forEach(c => {
    c.classList.toggle('selected', c.dataset.role === role);
  });
}

function doLogin() {
  const name = document.getElementById('loginName').value.trim();
  if (!name) { alert('Proszę wpisać imię i nazwisko.'); return; }
  state.user = name;
  state.role = selectedRole;
  document.getElementById('loginScreen').style.display = 'none';
  document.getElementById('app').classList.add('visible');
  setupSidebar();
  navigate('dashboard');
  lucide.createIcons();
}

function doLogout() {
  document.getElementById('loginScreen').style.display = 'flex';
  document.getElementById('app').classList.remove('visible');
  state.user = null;
}

// ============================================================
// SIDEBAR SETUP
// ============================================================
function setupSidebar() {
  const initials = state.user.split(' ').map(n=>n[0]).join('').toUpperCase().slice(0,2);
  document.getElementById('userAvatarSidebar').textContent = initials;
  document.getElementById('userNameSidebar').textContent = state.user;
  document.getElementById('userRoleSidebar').textContent = state.role === 'technik' ? 'Technik IT' : 'Pracownik';
  document.getElementById('sidebarRoleLabel').textContent = state.role === 'technik' ? 'Konsola IT' : 'Portal Pracownika';

  const nav = document.getElementById('sidebarNav');
  const newCount = state.tickets.filter(t => t.status === 'Nowe').length;
  
  let items = `
    <div class="nav-section-label">Główne</div>
    <a class="nav-item" data-view="dashboard" onclick="navigate('dashboard')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
      Dashboard
    </a>
    <a class="nav-item" data-view="new-ticket" onclick="navigate('new-ticket')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
      Nowe zgłoszenie
    </a>
    <a class="nav-item" data-view="my-tickets" onclick="navigate('my-tickets')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
      Moje zgłoszenia
    </a>
  `;

  if (state.role === 'technik') {
    items += `
      <div class="nav-section-label" style="margin-top:0.5rem">Konsola IT</div>
      <a class="nav-item" data-view="all-tickets" onclick="navigate('all-tickets')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
        Wszystkie zgłoszenia
        ${newCount > 0 ? `<span class="nav-badge">${newCount}</span>` : ''}
      </a>
    `;
  }

  nav.innerHTML = items;
}

// ============================================================
// NAVIGATION / ROUTER
// ============================================================
function navigate(view) {
  state.currentView = view;
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === view);
  });
  const titles = {
    'dashboard': 'Dashboard',
    'new-ticket': 'Nowe zgłoszenie',
    'my-tickets': 'Moje zgłoszenia',
    'all-tickets': 'Wszystkie zgłoszenia',
  };
  document.getElementById('pageTitle').textContent = titles[view] || 'HelpDesk IT';
  renderView(view);
  lucide.createIcons();
}

function renderView(view) {
  const container = document.getElementById('mainContent');
  switch(view) {
    case 'dashboard': container.innerHTML = renderDashboard(); break;
    case 'new-ticket': container.innerHTML = renderNewTicket(); break;
    case 'my-tickets': container.innerHTML = renderMyTickets(); break;
    case 'all-tickets': container.innerHTML = renderAllTickets(); break;
    default: container.innerHTML = renderDashboard();
  }
}

// ============================================================
// AI CATEGORIZER
// ============================================================
function categorizeTicket(title, desc) {
  const text = (title + ' ' + desc).toLowerCase();
  let category = 'Inne';
  let priority = 'Niski';
  
  if (/sieć|internet|vpn|wifi|wi-fi|połącz|serwer|router|ping|lan/.test(text)) {
    category = 'Sieć';
    priority = /nie działa|brak|wszyscy|cały|pilne|zdaln/.test(text) ? 'Wysoki' : 'Średni';
  } else if (/phishing|wirus|malware|haker|atak|nieautoryz|bezpieczeń|podejrzany|suspicious/.test(text)) {
    category = 'Bezpieczeństwo';
    priority = 'Krytyczny';
  } else if (/komputer|laptop|ekran|monitor|dysk|niebieski ekran|bsod|zasilani|pc|stacjon/.test(text)) {
    category = 'Sprzęt';
    priority = /nie włącza|nie działa|niebieski|crash|pada/.test(text) ? 'Wysoki' : 'Średni';
  } else if (/mail|e-mail|outlook|skrzynka|wiadomość|poczta/.test(text)) {
    category = 'Poczta e-mail';
    priority = /nie wysyła|nie odbiera|brak|zablokowa/.test(text) ? 'Wysoki' : 'Niski';
  } else if (/hasło|login|logowanie|dostęp|uprawnienia|konto|zablokowane|403|401|permission/.test(text)) {
    category = 'Dostęp i konta';
    priority = /pilne|ważne|zestawienie|spotkanie|termin|dziś|dzisiaj/.test(text) ? 'Wysoki' : 'Średni';
  } else if (/drukarka|skaner|myszka|klawiatura|kamera|headset|pendrive|usb|peryferi/.test(text)) {
    category = 'Urządzenia peryferyjne';
    priority = /nie działa|całkowicie|produkcja|spotkanie/.test(text) ? 'Średni' : 'Niski';
  } else if (/program|aplikacja|software|system|excel|word|windows|zawiesza|błąd|error|instalacja|aktualizacja/.test(text)) {
    category = 'Oprogramowanie';
    priority = /nie uruchamia|nie otwiera|crash|zamknął|niebieski/.test(text) ? 'Wysoki' : 'Średni';
  }
  
  return { category, priority };
}

// ============================================================
// VIEWS
// ============================================================

function renderDashboard() {
  const myTickets = state.tickets.filter(t => t.author === state.user);
  const myOpen = myTickets.filter(t => t.status !== 'Zamknięte').length;
  const myClosed = myTickets.filter(t => t.status === 'Zamknięte').length;
  
  if (state.role === 'pracownik') {
    const recentTickets = myTickets.slice(0, 5);
    return `
      <div style="margin-bottom:1.5rem">
        <h2 style="font-size:var(--text-lg);font-weight:700;margin-bottom:0.25rem">Witaj, ${state.user.split(' ')[0]}! 👋</h2>
        <p style="color:var(--color-text-muted);font-size:var(--text-sm)">Zarządzaj swoimi zgłoszeniami IT</p>
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
          <div class="kpi-value">${myTickets.length}</div>
          <div class="kpi-sub">wszystkich zgłoszeń</div>
        </div>
      </div>
      <div class="card">
        <div class="section-header">
          <div class="section-title">Ostatnie zgłoszenia</div>
          <button class="btn btn-sm btn-secondary" onclick="navigate('my-tickets')">Zobacz wszystkie</button>
        </div>
        ${recentTickets.length ? renderTicketTable(recentTickets, false) : `<div class="empty-state"><div class="empty-icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div><p>Nie masz jeszcze żadnych zgłoszeń.<br>Kliknij „Nowe zgłoszenie" aby zacząć.</p><button class="btn btn-primary" style="margin-top:1rem" onclick="navigate('new-ticket')">Nowe zgłoszenie</button></div>`}
      </div>
    `;
  } else {
    // Technik dashboard
    const total = state.tickets.length;
    const nowe = state.tickets.filter(t => t.status === 'Nowe').length;
    const wRealizacji = state.tickets.filter(t => t.status === 'W realizacji').length;
    const krytyczne = state.tickets.filter(t => t.priority === 'Krytyczny' && t.status !== 'Zamknięte').length;
    const zamkniete = state.tickets.filter(t => t.status === 'Zamknięte').length;
    const recent = [...state.tickets].sort((a,b) => new Date(b.created) - new Date(a.created)).slice(0, 6);
    return `
      <div style="margin-bottom:1.5rem">
        <h2 style="font-size:var(--text-lg);font-weight:700;margin-bottom:0.25rem">Konsola Obsługi IT</h2>
        <p style="color:var(--color-text-muted);font-size:var(--text-sm)">Dzisiaj: ${new Date().toLocaleDateString('pl-PL', {weekday:'long',year:'numeric',month:'long',day:'numeric'})}</p>
      </div>
      <div class="kpi-grid">
        <div class="card kpi-card">
          <div class="kpi-label">Nowe</div>
          <div class="kpi-value" style="color:var(--color-blue)">${nowe}</div>
          <div class="kpi-sub"><span class="kpi-dot" style="background:var(--color-blue)"></span>oczekują na podjęcie</div>
        </div>
        <div class="card kpi-card">
          <div class="kpi-label">W realizacji</div>
          <div class="kpi-value" style="color:var(--color-primary)">${wRealizacji}</div>
          <div class="kpi-sub"><span class="kpi-dot" style="background:var(--color-primary)"></span>w toku obsługi</div>
        </div>
        <div class="card kpi-card">
          <div class="kpi-label">Krytyczne</div>
          <div class="kpi-value" style="color:var(--color-error)">${krytyczne}</div>
          <div class="kpi-sub"><span class="kpi-dot" style="background:var(--color-error)"></span>wymagają uwagi</div>
        </div>
        <div class="card kpi-card">
          <div class="kpi-label">Zamknięte</div>
          <div class="kpi-value" style="color:var(--color-success)">${zamkniete}</div>
          <div class="kpi-sub"><span class="kpi-dot" style="background:var(--color-success)"></span>rozwiązane łącznie</div>
        </div>
      </div>
      <div class="card">
        <div class="section-header">
          <div class="section-title">Ostatnie zgłoszenia</div>
          <button class="btn btn-sm btn-secondary" onclick="navigate('all-tickets')">Wszystkie zgłoszenia</button>
        </div>
        ${renderTicketTable(recent, true)}
      </div>
    `;
  }
}

function renderMyTickets() {
  const tickets = state.tickets.filter(t => t.author === state.user);
  return `
    <div class="card">
      <div class="section-header">
        <div class="section-title">Moje zgłoszenia</div>
        <button class="btn btn-sm btn-primary" onclick="navigate('new-ticket')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Nowe zgłoszenie
        </button>
      </div>
      ${tickets.length ? renderTicketTable(tickets, false) : `<div class="empty-state"><div class="empty-icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg></div><p>Nie masz jeszcze żadnych zgłoszeń.</p><button class="btn btn-primary" style="margin-top:1rem" onclick="navigate('new-ticket')">Złóż pierwsze zgłoszenie</button></div>`}
    </div>
  `;
}

function renderAllTickets() {
  let tickets = [...state.tickets];
  if (state.filterStatus !== 'wszystkie') tickets = tickets.filter(t => t.status === state.filterStatus);
  if (state.filterPriority !== 'wszystkie') tickets = tickets.filter(t => t.priority === state.filterPriority);
  tickets.sort((a,b) => {
    const pOrder = {'Krytyczny':0,'Wysoki':1,'Średni':2,'Niski':3};
    return (pOrder[a.priority]||3) - (pOrder[b.priority]||3);
  });
  return `
    <div class="card">
      <div class="section-header">
        <div class="section-title">Wszystkie zgłoszenia <span style="color:var(--color-text-muted);font-weight:400;font-size:var(--text-sm)">(${tickets.length})</span></div>
      </div>
      <div class="filters">
        <select class="filter-select" onchange="state.filterStatus=this.value;navigate('all-tickets')">
          <option value="wszystkie">Wszystkie statusy</option>
          <option value="Nowe" ${state.filterStatus==='Nowe'?'selected':''}>Nowe</option>
          <option value="W realizacji" ${state.filterStatus==='W realizacji'?'selected':''}>W realizacji</option>
          <option value="Oczekujące" ${state.filterStatus==='Oczekujące'?'selected':''}>Oczekujące</option>
          <option value="Zamknięte" ${state.filterStatus==='Zamknięte'?'selected':''}>Zamknięte</option>
        </select>
        <select class="filter-select" onchange="state.filterPriority=this.value;navigate('all-tickets')">
          <option value="wszystkie">Wszystkie priorytety</option>
          <option value="Krytyczny" ${state.filterPriority==='Krytyczny'?'selected':''}>Krytyczny</option>
          <option value="Wysoki" ${state.filterPriority==='Wysoki'?'selected':''}>Wysoki</option>
          <option value="Średni" ${state.filterPriority==='Średni'?'selected':''}>Średni</option>
          <option value="Niski" ${state.filterPriority==='Niski'?'selected':''}>Niski</option>
        </select>
      </div>
      ${tickets.length ? renderTicketTable(tickets, true) : `<div class="empty-state"><p>Brak zgłoszeń spełniających wybrane kryteria.</p></div>`}
    </div>
  `;
}

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
        <div class="form-field">
          <label class="form-label">Załącznik (Zdjęcie, opcjonalnie)</label>
          <input class="form-input" type="file" id="ticketFile" accept="image/*" style="padding:0.375rem 0.875rem">
        </div>
        <div id="aiStatus"></div>
        <div style="display:flex;gap:0.75rem;margin-top:1.25rem">
          <button class="btn btn-primary" onclick="submitTicket()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            Wyślij zgłoszenie
          </button>
          <button class="btn btn-secondary" onclick="navigate('dashboard')">Anuluj</button>
        </div>
      </div>
    </div>
  `;
}

// ============================================================
// TABLE RENDERER
// ============================================================
function renderTicketTable(tickets, showAuthor) {
  const rows = tickets.map(t => `
    <tr onclick="openTicket('${t.id}')">
      <td class="td-id">${t.id}</td>
      <td>
        <div style="font-weight:500">${t.title}</div>
        <div class="td-muted">${t.category} ${t.aiCategorized ? '<span class="badge badge-ai">AI</span>' : ''}</div>
      </td>
      <td>${priorityBadge(t.priority)}</td>
      <td>${statusBadge(t.status)}</td>
      ${showAuthor ? `<td class="td-muted">${t.author}</td>` : ''}
      <td class="td-muted">${formatDate(t.created)}</td>
    </tr>
  `).join('');

  return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Zgłoszenie</th>
            <th>Priorytet</th>
            <th>Status</th>
            ${showAuthor ? '<th>Zgłaszający</th>' : ''}
            <th>Data</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

// ============================================================
// TICKET DETAIL MODAL
// ============================================================
function openTicket(id) {
  const t = state.tickets.find(x => x.id === id);
  if (!t) return;
  
  const isTechnik = state.role === 'technik';
  const notes = t.notes.map(n => `
    <div class="note-item">
      <div class="note-meta">
        <span class="note-author">${n.author}</span>
        <span class="note-time">${formatDateTime(n.time)}</span>
      </div>
      <div class="note-text">${n.text}</div>
    </div>
  `).join('') || '<p style="color:var(--color-text-muted);font-size:var(--text-sm)">Brak notatek.</p>';

  const attachmentHtml = t.attachment ? `
    <div class="info-item" style="margin-bottom:1.25rem">
      <div class="info-item-label" style="margin-bottom:0.5rem">Załącznik</div>
      <img src="${t.attachment}" alt="Załączony plik" style="max-width:100%; border-radius:var(--radius-md); border:1px solid var(--color-border); max-height: 400px; object-fit: contain; background: var(--color-surface);">
    </div>
  ` : '';

  const technikActions = isTechnik ? `
    <div class="divider"></div>
    <div class="form-field">
      <label class="form-label">Zmień status</label>
      <select class="form-input filter-select" id="modalStatus" style="width:100%">
        <option ${t.status==='Nowe'?'selected':''}>Nowe</option>
        <option ${t.status==='W realizacji'?'selected':''}>W realizacji</option>
        <option ${t.status==='Oczekujące'?'selected':''}>Oczekujące</option>
        <option ${t.status==='Zamknięte'?'selected':''}>Zamknięte</option>
      </select>
    </div>
    <div class="form-field">
      <label class="form-label">Dodaj notatkę wewnętrzną</label>
      <textarea class="form-input form-textarea" id="modalNote" placeholder="Opisz wykonane działania..." style="min-height:70px"></textarea>
    </div>
  ` : '';

  const deleteBtn = `
    <button class="btn btn-danger" onclick="deleteTicket('${t.id}')" style="margin-right: auto;" title="Usuń zgłoszenie">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
      Usuń
    </button>
  `;

  document.getElementById('ticketModalContent').innerHTML = `
    <div class="modal-header">
      <div>
        <div class="modal-title">${t.title}</div>
        <div class="modal-id">${t.id} · ${formatDateTime(t.created)} · ${t.author}</div>
      </div>
      <div style="display: flex; gap: 0.5rem;">
        <button class="btn btn-ghost modal-close" onclick="editTicket('${t.id}')" title="Edytuj zgłoszenie">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
        </button>
        <button class="btn btn-ghost modal-close" onclick="closeModal()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </div>
    <div class="modal-body">
      <div class="info-grid">
        <div class="info-item">
          <div class="info-item-label">Status</div>
          ${statusBadge(t.status)}
        </div>
        <div class="info-item">
          <div class="info-item-label">Priorytet</div>
          ${priorityBadge(t.priority)}
        </div>
        <div class="info-item">
          <div class="info-item-label">Kategoria</div>
          <div style="font-size:var(--text-sm);display:flex;align-items:center;gap:0.375rem">
            ${t.category}
            ${t.aiCategorized ? '<span class="badge badge-ai">🤖 AI</span>' : ''}
          </div>
        </div>
        <div class="info-item">
          <div class="info-item-label">Przypisano do</div>
          <div style="font-size:var(--text-sm)">${t.assignee || '—'}</div>
        </div>
      </div>
      <div class="info-item" style="margin-bottom:1rem">
        <div class="info-item-label" style="margin-bottom:0.375rem">Opis problemu</div>
        <div class="desc-block">${t.desc}</div>
      </div>
      ${attachmentHtml}
      <div class="notes-section">
        <div class="notes-title">Notatki wewnętrzne</div>
        ${notes}
      </div>
      ${technikActions}
    </div>
    <div class="modal-footer">
      ${deleteBtn}
      <button class="btn btn-secondary" onclick="closeModal()">Zamknij</button>
      ${isTechnik ? `<button class="btn btn-primary" onclick="saveTicketChanges('${t.id}')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
        Zapisz status
      </button>` : ''}
    </div>
  `;
  
  document.getElementById('ticketModal').classList.add('open');
  lucide.createIcons();
}

function closeModal() {
  document.getElementById('ticketModal').classList.remove('open');
}

function saveTicketChanges(id) {
  const ticket = state.tickets.find(t => t.id === id);
  if (!ticket) return;
  const newStatus = document.getElementById('modalStatus').value;
  const noteText = document.getElementById('modalNote').value.trim();
  
  ticket.status = newStatus;
  if (noteText) {
    ticket.notes.push({ author: state.user, text: noteText, time: new Date().toISOString() });
  }
  if (!ticket.assignee && newStatus === 'W realizacji') ticket.assignee = state.user;
  
  closeModal();
  navigate(state.currentView);
  setupSidebar(); // refresh badge count
}

function deleteTicket(id) {
  if (confirm(`Czy na pewno chcesz usunąć zgłoszenie ${id}? Tej operacji nie można cofnąć.`)) {
    state.tickets = state.tickets.filter(t => t.id !== id);
    closeModal();
    navigate(state.currentView);
    setupSidebar();
  }
}

// ============================================================
// SUBMIT TICKET
// ============================================================
function submitTicket() {
  const title = document.getElementById('ticketTitle').value.trim();
  const desc = document.getElementById('ticketDesc').value.trim();
  const fileInput = document.getElementById('ticketFile');
  
  if (!title) { document.getElementById('ticketTitle').focus(); return; }
  if (!desc) { document.getElementById('ticketDesc').focus(); return; }

  // Disable button
  const btn = document.querySelector('#mainContent .btn-primary');
  if (btn) { btn.disabled = true; btn.textContent = 'Wysyłanie...'; }

  // Show AI processing
  document.getElementById('aiStatus').innerHTML = `
    <div class="ai-processing">
      <svg class="ai-spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
      <span>Moduł AI analizuje zgłoszenie...</span>
    </div>
  `;

  const processSubmission = (attachmentBase64) => {
    setTimeout(() => {
      const { category, priority } = categorizeTicket(title, desc);
      const id = `INC-${String(state.nextId++).padStart(3,'0')}`;
      const ticket = {
        id, title, desc, category, priority,
        status: 'Nowe',
        author: state.user,
        assignee: null,
        created: new Date().toISOString(),
        aiCategorized: true,
        notes: [],
        attachment: attachmentBase64
      };
      state.tickets.unshift(ticket);
      
      document.getElementById('aiStatus').innerHTML = `
        <div class="ai-result">
          <div class="ai-result-title">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
            Zgłoszenie ${id} — skategoryzowane przez AI
          </div>
          <div class="ai-result-row">
            <span class="ai-result-label">Kategoria</span>
            <strong style="font-size:var(--text-sm)">${category}</strong>
          </div>
          <div class="ai-result-row">
            <span class="ai-result-label">Priorytet</span>
            ${priorityBadge(priority)}
          </div>
          <div class="ai-result-row">
            <span class="ai-result-label">Status</span>
            ${statusBadge('Nowe')}
          </div>
        </div>
      `;

      setTimeout(() => {
        document.getElementById('mainContent').innerHTML = `
          <div style="max-width:640px">
            <div class="card">
              <div class="success-state">
                <div class="success-icon">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
                <div class="success-title">Zgłoszenie zostało wysłane!</div>
                <div class="success-desc">
                  Twoje zgłoszenie <strong>${id}</strong> zostało zarejestrowane w systemie.<br>
                  AI przypisało kategorię <strong>${category}</strong> z priorytetem <strong>${priority}</strong>.<br>
                  Możesz śledzić postęp w zakładce „Moje zgłoszenia".
                </div>
                <div style="display:flex;gap:0.75rem;justify-content:center;margin-top:1.5rem">
                  <button class="btn btn-primary" onclick="navigate('my-tickets')">Moje zgłoszenia</button>
                  <button class="btn btn-secondary" onclick="navigate('new-ticket')">Nowe zgłoszenie</button>
                </div>
              </div>
            </div>
          </div>
        `;
        setupSidebar();
      }, 1500);
    }, 2000);
  };

  if (fileInput.files && fileInput.files[0]) {
    const reader = new FileReader();
    reader.onload = (e) => processSubmission(e.target.result);
    reader.readAsDataURL(fileInput.files[0]);
  } else {
    processSubmission(null);
  }
}

// ============================================================
// HELPERS
// ============================================================
function priorityBadge(p) {
  const map = { 'Krytyczny':'badge-krityczny','Wysoki':'badge-wysoki','Średni':'badge-sredni','Niski':'badge-niski' };
  const dots = { 'Krytyczny':'var(--color-error)','Wysoki':'var(--color-orange)','Średni':'var(--color-warning)','Niski':'var(--color-success)' };
  return `<span class="badge ${map[p]||''}"><span style="width:6px;height:6px;border-radius:50%;background:${dots[p]||'currentColor'};flex-shrink:0"></span>${p}</span>`;
}

function statusBadge(s) {
  const map = { 'Nowe':'badge-nowe','W realizacji':'badge-wrealizacji','Zamknięte':'badge-zamkniete','Oczekujące':'badge-oczekujace' };
  return `<span class="badge ${map[s]||''}">${s}</span>`;
}

function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('pl-PL', { day:'2-digit', month:'2-digit', year:'numeric' });
}

function formatDateTime(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('pl-PL', { day:'2-digit', month:'2-digit', year:'numeric' }) + ' ' + d.toLocaleTimeString('pl-PL', { hour:'2-digit', minute:'2-digit' });
}

// ============================================================
// EDIT TICKET
// ============================================================
function editTicket(id) {
  const t = state.tickets.find(x => x.id === id);
  if (!t) return;

  const isTechnik = state.role === 'technik';
  const categories = ['Sieć', 'Sprzęt', 'Urządzenia peryferyjne', 'Bezpieczeństwo', 'Dostęp i konta', 'Oprogramowanie', 'Poczta e-mail', 'Inne'];
  const priorities = ['Krytyczny', 'Wysoki', 'Średni', 'Niski'];

  const techFields = isTechnik ? `
    <div class="info-grid">
      <div class="form-field">
        <label class="form-label">Kategoria</label>
        <select class="form-input" id="editCategory">
          ${categories.map(c => `<option value="${c}" ${t.category === c ? 'selected' : ''}>${c}</option>`).join('')}
        </select>
      </div>
      <div class="form-field">
        <label class="form-label">Priorytet</label>
        <select class="form-input" id="editPriority">
          ${priorities.map(p => `<option value="${p}" ${t.priority === p ? 'selected' : ''}>${p}</option>`).join('')}
        </select>
      </div>
    </div>
  ` : '';

  document.getElementById('ticketModalContent').innerHTML = `
    <div class="modal-header">
      <div>
        <div class="modal-title">Edytuj zgłoszenie</div>
        <div class="modal-id">${t.id}</div>
      </div>
      <button class="btn btn-ghost modal-close" onclick="openTicket('${t.id}')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
      </button>
    </div>
    <div class="modal-body">
      <div class="form-field">
        <label class="form-label">Tytuł problemu</label>
        <input class="form-input" type="text" id="editTitle" value="${t.title}">
      </div>
      
      ${techFields}

      <div class="form-field">
        <label class="form-label">Opis</label>
        <textarea class="form-input form-textarea" id="editDesc" style="min-height:150px">${t.desc}</textarea>
      </div>
      
      <div class="form-field">
        <label class="form-label">Załącznik (Zdjęcie)</label>
        ${t.attachment ? `<div style="font-size:var(--text-xs); color:var(--color-text-muted); margin-bottom:0.5rem;">Zostaw puste, aby zachować obecne zdjęcie, lub wybierz nowe, aby je podmienić.</div>` : ''}
        <input class="form-input" type="file" id="editFile" accept="image/*" style="padding:0.375rem 0.875rem">
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="openTicket('${t.id}')">Anuluj</button>
      <button class="btn btn-primary" id="saveEditBtn" onclick="saveEditedTicket('${t.id}')">
        Zapisz zmiany
      </button>
    </div>
  `;
  lucide.createIcons();
}

function saveEditedTicket(id) {
  const t = state.tickets.find(x => x.id === id);
  if (!t) return;

  const isTechnik = state.role === 'technik';
  const btn = document.getElementById('saveEditBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Zapisywanie...'; }

  const newTitle = document.getElementById('editTitle').value.trim();
  const newDesc = document.getElementById('editDesc').value.trim();
  const fileInput = document.getElementById('editFile');

  const processSave = (newAttachment) => {
    t.title = newTitle;
    t.desc = newDesc;
    
    if (isTechnik) {
      const newCategory = document.getElementById('editCategory').value;
      const newPriority = document.getElementById('editPriority').value;
      if (t.category !== newCategory) t.aiCategorized = false; 
      t.category = newCategory;
      t.priority = newPriority;
    }

    if (newAttachment !== undefined) {
      t.attachment = newAttachment;
    }

    navigate(state.currentView);
    openTicket(id);
  };

  if (fileInput.files && fileInput.files[0]) {
    const reader = new FileReader();
    reader.onload = (e) => processSave(e.target.result);
    reader.readAsDataURL(fileInput.files[0]);
  } else {
    processSave(undefined);
  }
}

// ============================================================
// THEME
// ============================================================
(function(){
  const d = matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', d);
})();

function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  const btn = document.getElementById('themeToggle');
  btn.innerHTML = next === 'dark'
    ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
    : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
}

// Close modal on overlay click
document.getElementById('ticketModal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});