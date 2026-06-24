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
// Kanban status change — requires description via modal
// ============================================================
const _STATUS_LABELS = {
  'a_fazer': 'A Fazer', 'atendendo': 'Atendendo',
  'pausado':  'Pausado', 'resolvido': 'Resolvido'
};

let _pendingChange = null; // { ticketId, newStatus, oldStatus, selectEl, dragCard, sourceCol, targetCol }

function updateStatus(ticketId, newStatus, selectEl) {
  const oldStatus = selectEl.dataset.prevValue || selectEl.value;
  if (oldStatus === newStatus) return;

  _pendingChange = { ticketId, newStatus, oldStatus, selectEl, dragCard: null };
  _openKanbanModal(newStatus);
}

function _openKanbanModal(newStatus) {
  const modal = document.getElementById('kanbanStatusModal');
  if (!modal) return;
  document.getElementById('ksmStatusLabel').textContent = _STATUS_LABELS[newStatus] || newStatus;
  document.getElementById('ksmDescription').value = '';
  document.getElementById('ksmDescCount').textContent = '0';
  const resGroup = document.getElementById('ksmResolutionGroup');
  if (resGroup) resGroup.style.display = newStatus === 'resolvido' ? 'block' : 'none';
  const btn = document.getElementById('ksmConfirmBtn');
  if (btn) { btn.disabled = false; btn.textContent = 'Confirmar'; }
  modal.classList.add('open');
  setTimeout(() => { const el = document.getElementById('ksmDescription'); if (el) el.focus(); }, 50);
}

function cancelKanbanModal() {
  if (_pendingChange) {
    // Revert select dropdown
    if (_pendingChange.selectEl) {
      _pendingChange.selectEl.value = _pendingChange.oldStatus;
    }
    // Return drag card to original column
    if (_pendingChange.dragCard && _pendingChange.sourceCol) {
      _pendingChange.sourceCol.appendChild(_pendingChange.dragCard);
      _pendingChange.dragCard.dataset.status = _pendingChange.oldStatus;
      const sel = _pendingChange.dragCard.querySelector('.status-select');
      if (sel) { sel.value = _pendingChange.oldStatus; sel.dataset.prevValue = _pendingChange.oldStatus; }
      updateColumnCounts();
    }
  }
  _pendingChange = null;
  const modal = document.getElementById('kanbanStatusModal');
  if (modal) modal.classList.remove('open');
}

function submitKanbanStatusChange() {
  if (!_pendingChange) return;

  const description = (document.getElementById('ksmDescription').value || '').trim();
  if (!description) {
    const el = document.getElementById('ksmDescription');
    el.style.borderColor = 'var(--danger)';
    el.focus();
    return;
  }
  document.getElementById('ksmDescription').style.borderColor = '';

  const { ticketId, newStatus, selectEl, dragCard, targetCol } = _pendingChange;
  const resolutionType = (document.getElementById('ksmResolutionType') || {}).value || '';

  const payload = { status: newStatus, description };
  if (newStatus === 'resolvido' && resolutionType) payload.resolution_type = resolutionType;

  const btn = document.getElementById('ksmConfirmBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Salvando...'; }

  fetch(`/chamado/${ticketId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) {
      // Update card state without full reload
      if (dragCard && targetCol) {
        dragCard.dataset.status = newStatus;
        const sel = dragCard.querySelector('.status-select');
        if (sel) { sel.value = newStatus; sel.dataset.prevValue = newStatus; }
        targetCol.appendChild(dragCard);
        updateColumnCounts();
      } else if (selectEl) {
        selectEl.dataset.prevValue = newStatus;
      }
      document.getElementById('kanbanStatusModal').classList.remove('open');
      _pendingChange = null;
      // Reload to show updated counts and system comment
      location.reload();
    } else {
      alert(data.error || 'Erro ao atualizar status.');
      cancelKanbanModal();
    }
  })
  .catch(() => {
    alert('Erro de conexão.');
    cancelKanbanModal();
  });
}

// Kanban description counter
(function () {
  const el = document.getElementById('ksmDescription');
  if (!el) return;
  el.addEventListener('input', function () {
    const counter = document.getElementById('ksmDescCount');
    if (counter) counter.textContent = this.value.length;
  });
  document.getElementById('kanbanStatusModal')?.addEventListener('click', function (e) {
    if (e.target === this) cancelKanbanModal();
  });
})();

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
// Drag & Drop Kanban — shows description modal before updating
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
      const oldStatus = dragged.dataset.status;

      if (oldStatus === newStatus) { col.appendChild(dragged); dragged = null; return; }

      const sourceCol = document.getElementById('col-' + oldStatus);
      _pendingChange  = {
        ticketId, newStatus, oldStatus,
        selectEl:  dragged.querySelector('.status-select'),
        dragCard:  dragged,
        sourceCol, targetCol: col
      };
      dragged = null;
      _openKanbanModal(newStatus);
    });
  });
})();

function updateColumnCounts() {
  document.querySelectorAll('.kanban-column').forEach(colEl => {
    const count = colEl.querySelector('.column-count');
    const body  = colEl.querySelector('.column-body');
    if (count && body) count.textContent = body.querySelectorAll('.ticket-card').length;
  });
}

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
