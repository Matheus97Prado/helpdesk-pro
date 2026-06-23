// ============================================================
// Sidebar collapse / expand (like Milvus)
// ============================================================
(function () {
  const body          = document.getElementById('appBody');
  const sidebarToggle = document.getElementById('sidebarToggle');
  const topbarToggle  = document.getElementById('topbarToggle');
  const MINI_KEY      = 'hd_sidebar_mini';

  function applyState() {
    const mini = localStorage.getItem(MINI_KEY) === '1';
    body.classList.toggle('sidebar-mini', mini);
    body.classList.toggle('sidebar-expanded', !mini);
  }

  function toggle() {
    const isMini = body.classList.contains('sidebar-mini');
    body.classList.toggle('sidebar-mini', !isMini);
    body.classList.toggle('sidebar-expanded', isMini);
    localStorage.setItem(MINI_KEY, isMini ? '0' : '1');
  }

  if (sidebarToggle) sidebarToggle.addEventListener('click', toggle);
  if (topbarToggle)  topbarToggle.addEventListener('click', toggle);

  applyState();
})();

// ============================================================
// Status update (Kanban dropdown)
// ============================================================
function updateStatus(ticketId, newStatus) {
  fetch(`/chamado/${ticketId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: newStatus })
  })
  .then(r => r.json())
  .then(data => { if (data.success) location.reload(); })
  .catch(() => alert('Erro de conexão.'));
}

// ============================================================
// Priority preview (new ticket form)
// ============================================================
(function () {
  const sel       = document.getElementById('priority');
  const indicator = document.querySelector('.priority-indicator');
  const text      = document.getElementById('priorityText');

  const cfg = {
    baixa:   { color: '#6b7280', label: 'Baixa — Pode aguardar' },
    media:   { color: '#f59e0b', label: 'Média — Atenção moderada' },
    alta:    { color: '#ef4444', label: 'Alta — Precisa de atenção imediata' },
    urgente: { color: '#7f1d1d', label: 'URGENTE — Atender agora!' },
  };

  if (sel && indicator && text) {
    const update = () => {
      const v = cfg[sel.value] || cfg.media;
      indicator.style.background = v.color;
      text.textContent = 'Prioridade: ' + v.label;
    };
    sel.addEventListener('change', update);
    update();
  }
})();

// ============================================================
// Drag & Drop Kanban
// ============================================================
(function () {
  const cards   = document.querySelectorAll('.ticket-card');
  const columns = document.querySelectorAll('.column-body');
  let dragged   = null;

  cards.forEach(card => {
    card.addEventListener('dragstart', () => {
      dragged = card;
      setTimeout(() => card.classList.add('dragging'), 0);
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      columns.forEach(c => c.classList.remove('drag-over'));
    });
  });

  columns.forEach(col => {
    col.addEventListener('dragover',  e => { e.preventDefault(); col.classList.add('drag-over'); });
    col.addEventListener('dragleave', ()  => col.classList.remove('drag-over'));
    col.addEventListener('drop', e => {
      e.preventDefault();
      col.classList.remove('drag-over');
      if (!dragged) return;

      const newStatus = col.id.replace('col-', '');
      const ticketId  = dragged.dataset.id;

      if (dragged.dataset.status === newStatus) { col.appendChild(dragged); return; }

      fetch(`/chamado/${ticketId}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          dragged.dataset.status = newStatus;
          const sel = dragged.querySelector('.status-select');
          if (sel) sel.value = newStatus;
          col.appendChild(dragged);
          updateColumnCounts();
        }
      });
    });
  });

  function updateColumnCounts() {
    document.querySelectorAll('.kanban-column').forEach(colEl => {
      const count = colEl.querySelector('.column-count');
      const body  = colEl.querySelector('.column-body');
      if (count && body) count.textContent = body.querySelectorAll('.ticket-card').length;
    });
  }
})();

// ============================================================
// Global search filter (client-side, instant)
// ============================================================
(function () {
  const input = document.getElementById('globalSearch');
  if (!input) return;

  input.addEventListener('input', () => {
    const q = input.value.toLowerCase().trim();
    document.querySelectorAll('.ticket-card').forEach(card => {
      const text = card.textContent.toLowerCase();
      card.style.display = (!q || text.includes(q)) ? '' : 'none';
    });
  });
})();

// ============================================================
// Auto-dismiss flash messages
// ============================================================
setTimeout(() => {
  document.querySelectorAll('.flash').forEach(el => {
    el.style.transition = 'opacity .4s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 400);
  });
}, 4000);
