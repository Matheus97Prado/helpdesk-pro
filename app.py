from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from werkzeug.security import generate_password_hash
import sqlite3
import imaplib
import email as email_lib
from email.header import decode_header
from email.utils import parseaddr
import threading
import urllib.request
import json
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'helpdesk-secret-key-2024'
DATABASE = os.path.join(os.path.dirname(__file__), 'helpdesk.db')


# ─────────────────────────────────────────────
# Database helpers
# ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT DEFAULT 'PJ',
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            phone2 TEXT,
            company TEXT,
            cnpj TEXT,
            website TEXT,
            cep TEXT,
            street TEXT,
            number TEXT,
            complement TEXT,
            neighborhood TEXT,
            city TEXT,
            state TEXT,
            notes TEXT,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            login TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'atendente',
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            client_id INTEGER,
            status TEXT DEFAULT 'a_fazer',
            priority TEXT DEFAULT 'media',
            category TEXT,
            assigned_to TEXT,
            origin TEXT DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients (id)
        );

        CREATE TABLE IF NOT EXISTS ticket_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            author TEXT,
            content TEXT,
            is_system INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES tickets (id)
        );

        CREATE TABLE IF NOT EXISTS email_config (
            id INTEGER PRIMARY KEY,
            imap_host TEXT DEFAULT '',
            imap_port INTEGER DEFAULT 993,
            email_user TEXT DEFAULT '',
            email_password TEXT DEFAULT '',
            active INTEGER DEFAULT 0,
            check_interval INTEGER DEFAULT 5,
            last_check TIMESTAMP,
            since_uid TEXT DEFAULT NULL,
            activated_at TIMESTAMP DEFAULT NULL
        );
    ''')

    cursor = conn.cursor()

    # Seed email config row
    cursor.execute('SELECT COUNT(*) FROM email_config')
    if cursor.fetchone()[0] == 0:
        conn.execute(
            'INSERT INTO email_config (id, imap_host, imap_port, email_user, email_password, active) VALUES (1, ?, ?, ?, ?, 0)',
            ('imap.gmail.com', 993, 'suporte@intermidiasp.com.br', '')
        )

    # Seed sample data
    cursor.execute('SELECT COUNT(*) FROM clients')
    if cursor.fetchone()[0] == 0:
        clients = [
            ('PJ','João Silva',    'joao@techcorp.com',    '(11) 99999-1111','','TechCorp Ltda',  '12.345.678/0001-90','https://techcorp.com', '01310-100','Av. Paulista','1000','Sala 5','Bela Vista','São Paulo','SP','Cliente VIP'),
            ('PJ','Maria Santos',  'maria@bizsol.com',     '(11) 98888-2222','','BizSolutions',   '98.765.432/0001-10','',                    '20040-020','Av. Rio Branco','200','','Centro','Rio de Janeiro','RJ',''),
            ('PF','Pedro Oliveira','pedro@startup.io',     '(21) 97777-3333','','StartupXYZ',     '321.654.987-00',   '',                    '30130-110','Av. Afonso Pena','500','Ap 3','Centro','Belo Horizonte','MG',''),
            ('PJ','Ana Costa',     'ana@consultoria.com',  '(31) 96666-4444','','ConsultPro',     '11.222.333/0001-44','',                   '80010-010','Rua XV de Novembro','100','','Centro','Curitiba','PR',''),
            ('PJ','Carlos Mendes', 'carlos@empresa.net',   '(41) 95555-5555','','Empresa Net',    '55.444.333/0001-22','https://empresa.net','90010-150','Av. Borges de Medeiros','300','','Centro Histórico','Porto Alegre','RS',''),
        ]
        conn.executemany('''INSERT INTO clients
            (type,name,email,phone,phone2,company,cnpj,website,cep,street,number,complement,neighborhood,city,state,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', clients)

        tickets = [
            ('Problema com Excel',    'Carregamento lento ao abrir planilhas grandes.', 1, 'atendendo', 'alta',  'Suporte Técnico', 'carlos.silva'),
            ('Solicitação de Visita', 'Visita técnica presencial para rede.',           2, 'a_fazer',  'media', 'Visita Técnica',  'ana.souza'),
            ('Lentidão no Sistema',   'Lento após atualização do Windows.',             3, 'pausado',  'alta',  'Suporte Técnico', 'carlos.silva'),
            ('Configuração de E-mail','Outlook não sincroniza.',                        4, 'atendendo','baixa', 'Configuração',    'pedro.m'),
            ('Backup de Dados',       'Backup antes da migração.',                      1, 'a_fazer',  'media', 'Manutenção',      'ana.souza'),
            ('Instalação Office 365', 'Ativação em 5 máquinas.',                        5, 'resolvido','baixa', 'Instalação',      'carlos.silva'),
            ('Impressora offline',    'Impressora da recepção fora da rede.',           2, 'pausado',  'media', 'Hardware',        'pedro.m'),
            ('Acesso VPN',            'Usuário não conecta à VPN.',                     3, 'atendendo','alta',  'Rede',            'ana.souza'),
        ]
        conn.executemany(
            'INSERT INTO tickets (title, description, client_id, status, priority, category, assigned_to) VALUES (?, ?, ?, ?, ?, ?, ?)',
            tickets
        )

        conn.executemany('INSERT INTO ticket_comments (ticket_id, author, content) VALUES (?, ?, ?)', [
            (1, 'carlos.silva', 'Verificado: problema na versão do Excel.'),
            (1, 'João Silva',   'Quando teremos resolução?'),
            (6, 'carlos.silva', 'Concluído. Todas as licenças ativadas.'),
        ])

    # Seed default agents
    cursor.execute('SELECT COUNT(*) FROM agents')
    if cursor.fetchone()[0] == 0:
        agents = [
            ('André Lima', 'andre@intermidiasp.com.br', 'André.lima', generate_password_hash('123456'), 'admin'),
            ('Claudio Derengowski',    'claudio@intermidiasp.com.br',    'Claudio.Derengowski',    generate_password_hash('123456'), 'atendente'),
            ('Felipe Evaristo','felipe@intermidiasp.com.br',  'Felipe.Evaristo',      generate_password_hash('123456'), 'atendente'),
        ]
        conn.executemany(
            'INSERT INTO agents (name, email, login, password_hash, role) VALUES (?, ?, ?, ?, ?)', agents
        )

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# Email helpers
# ─────────────────────────────────────────────
def _decode_header_value(value):
    if not value:
        return ''
    parts = decode_header(value)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or 'utf-8', errors='replace'))
        else:
            result.append(str(part))
    return ' '.join(result)


def _get_body(msg):
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get('Content-Disposition', ''))
            if ct == 'text/plain' and 'attachment' not in cd:
                try:
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or 'utf-8', errors='replace')
                    break
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or 'utf-8', errors='replace')
        except Exception:
            pass
    return body.strip()


def _get_max_uid(mail) -> str:
    """Return the highest UID currently in INBOX as string, or '0'."""
    mail.select('INBOX')
    _, data = mail.uid('search', None, 'ALL')
    uids = data[0].split()
    return uids[-1].decode() if uids else '0'


def _bootstrap_since_uid(config) -> str | None:
    """
    Connect to IMAP, get the current max UID and save it as the bookmark.
    All emails with a lower or equal UID will be skipped by the poller.
    Returns the UID string on success, None on failure.
    """
    try:
        mail = imaplib.IMAP4_SSL(config['imap_host'], config['imap_port'])
        mail.login(config['email_user'], config['email_password'])
        max_uid = _get_max_uid(mail)
        mail.logout()

        conn = get_db()
        conn.execute(
            "UPDATE email_config SET since_uid = ?, activated_at = ? WHERE id = 1",
            (max_uid, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        conn.close()
        return max_uid
    except Exception:
        return None


# ─────────────────────────────────────────────
# Email → Ticket checker
# ─────────────────────────────────────────────
def check_email_inbox():
    conn = get_db()
    config = conn.execute('SELECT * FROM email_config WHERE id = 1').fetchone()

    if not config or not config['active'] or not config['email_user'] or not config['email_password']:
        conn.close()
        return {'success': False, 'message': 'E-mail não configurado ou inativo.', 'count': 0}

    try:
        mail = imaplib.IMAP4_SSL(config['imap_host'], config['imap_port'])
        mail.login(config['email_user'], config['email_password'])
        mail.select('INBOX')

        # If since_uid is not set yet, bootstrap it now (skip all existing emails)
        since_uid_val = config['since_uid']
        if since_uid_val is None:
            max_uid = _get_max_uid(mail)
            conn.execute(
                "UPDATE email_config SET since_uid = ?, activated_at = ? WHERE id = 1",
                (max_uid, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            conn.commit()
            mail.logout()
            conn.execute("UPDATE email_config SET last_check = ? WHERE id = 1",
                         (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))
            conn.commit()
            conn.close()
            return {'success': True, 'count': 0,
                    'message': 'Monitoramento ativado. Somente novos e-mails serão processados.'}

        since_uid_int = int(since_uid_val)

        # Fetch only UNSEEN messages (UID search)
        _, data = mail.uid('search', None, 'UNSEEN')
        all_unseen_uids = data[0].split()

        # Filter: only UIDs strictly greater than our bookmark
        new_uids = [uid for uid in all_unseen_uids if int(uid) > since_uid_int]

        count = 0
        for uid in new_uids:
            _, msg_data = mail.uid('fetch', uid, '(RFC822)')
            if not msg_data or not msg_data[0]:
                continue
            msg = email_lib.message_from_bytes(msg_data[0][1])

            subject  = _decode_header_value(msg.get('Subject', 'Sem assunto'))
            from_raw = msg.get('From', '')
            from_name, from_email = parseaddr(from_raw)
            from_name = (from_name or from_email).strip()
            body     = _get_body(msg)

            if not from_email:
                continue

            # ── Find or create client (no duplicates) ──────────
            client = conn.execute(
                'SELECT id FROM clients WHERE LOWER(email) = LOWER(?)', (from_email,)
            ).fetchone()
            if not client:
                conn.execute(
                    'INSERT INTO clients (name, email, company, type) VALUES (?, ?, ?, ?)',
                    (from_name, from_email.lower(), 'Via E-mail', 'PF')
                )
                conn.commit()
                client = conn.execute(
                    'SELECT id FROM clients WHERE LOWER(email) = LOWER(?)', (from_email,)
                ).fetchone()

            # ── Deduplicate tickets: same subject + client in last 10 min ──
            existing = conn.execute(
                "SELECT id FROM tickets WHERE client_id = ? AND title = ? "
                "AND origin = 'email' AND created_at > datetime('now', '-10 minutes')",
                (client['id'], subject)
            ).fetchone()
            if existing:
                mail.uid('store', uid, '+FLAGS', '\\Seen')
                continue

            conn.execute(
                'INSERT INTO tickets (title, description, client_id, priority, category, status, origin) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (subject, body[:3000], client['id'], 'media', 'E-mail', 'a_fazer', 'email')
            )
            conn.commit()
            mail.uid('store', uid, '+FLAGS', '\\Seen')
            count += 1

        # Update bookmark to max UID we have seen (processed or skipped)
        if new_uids:
            max_seen = max(int(uid) for uid in new_uids)
            if max_seen > since_uid_int:
                conn.execute("UPDATE email_config SET since_uid = ? WHERE id = 1", (str(max_seen),))

        mail.logout()
        conn.execute("UPDATE email_config SET last_check = ? WHERE id = 1",
                     (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))
        conn.commit()
        conn.close()
        return {'success': True, 'count': count,
                'message': f'{count} novo(s) ticket(s) criado(s) via e-mail.' if count
                           else 'Nenhum e-mail novo encontrado.'}

    except imaplib.IMAP4.error as e:
        conn.close()
        return {'success': False, 'count': 0, 'message': f'Erro de autenticação IMAP: {e}'}
    except Exception as e:
        conn.close()
        return {'success': False, 'count': 0, 'message': f'Erro: {e}'}


# Background email polling thread
_stop_email_thread = threading.Event()

def _email_polling_loop():
    while not _stop_email_thread.is_set():
        try:
            conn = get_db()
            config = conn.execute('SELECT active, check_interval FROM email_config WHERE id = 1').fetchone()
            conn.close()
            if config and config['active']:
                check_email_inbox()
            interval = (config['check_interval'] if config else 5) * 60
        except Exception:
            interval = 300
        _stop_email_thread.wait(interval)


# ─────────────────────────────────────────────
# Routes — Dashboard
# ─────────────────────────────────────────────
@app.route('/')
def dashboard():
    conn = get_db()
    tickets_by_status = {}
    for status in ['a_fazer', 'atendendo', 'pausado', 'resolvido']:
        tickets_by_status[status] = conn.execute('''
            SELECT t.*, c.name as client_name, c.company,
                   a.name as agent_name
            FROM tickets t
            LEFT JOIN clients c ON t.client_id = c.id
            LEFT JOIN agents a ON t.assigned_to = a.login
            WHERE t.status = ?
            ORDER BY CASE t.priority
                WHEN 'urgente' THEN 1 WHEN 'alta' THEN 2 WHEN 'media' THEN 3 ELSE 4 END,
                t.created_at DESC
        ''', (status,)).fetchall()

    stats = conn.execute('''
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status='a_fazer'   THEN 1 ELSE 0 END) as a_fazer,
               SUM(CASE WHEN status='atendendo' THEN 1 ELSE 0 END) as atendendo,
               SUM(CASE WHEN status='pausado'   THEN 1 ELSE 0 END) as pausado,
               SUM(CASE WHEN status='resolvido' THEN 1 ELSE 0 END) as resolvido
        FROM tickets
    ''').fetchone()

    email_cfg = conn.execute('SELECT active, last_check FROM email_config WHERE id = 1').fetchone()
    conn.close()
    return render_template('dashboard.html', tickets_by_status=tickets_by_status,
                           stats=stats, email_cfg=email_cfg)


# ─────────────────────────────────────────────
# Routes — Tickets
# ─────────────────────────────────────────────
@app.route('/novo-chamado', methods=['GET', 'POST'])
def novo_chamado():
    conn = get_db()
    clients = conn.execute('SELECT * FROM clients WHERE active = 1 ORDER BY name').fetchall()
    # Only registered agents from the team
    agents  = conn.execute("SELECT id, name, login, role FROM agents WHERE active = 1 ORDER BY name").fetchall()

    if request.method == 'POST':
        assigned = request.form.get('assigned_to', '').strip()
        # Validate that assigned_to is a real agent login (if provided)
        if assigned:
            valid = conn.execute('SELECT id FROM agents WHERE login = ? AND active = 1', (assigned,)).fetchone()
            if not valid:
                assigned = ''

        conn.execute(
            'INSERT INTO tickets (title, description, client_id, priority, category, assigned_to, status) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (request.form['title'], request.form['description'], request.form['client_id'],
             request.form['priority'], request.form.get('category', ''), assigned, 'a_fazer')
        )
        conn.commit()
        conn.close()
        flash('Chamado aberto com sucesso!', 'success')
        return redirect(url_for('dashboard'))

    preselect_client = request.args.get('client', '')
    conn.close()
    return render_template('novo_chamado.html', clients=clients, agents=agents,
                           preselect_client=preselect_client)


@app.route('/chamado/<int:ticket_id>')
def chamado_detalhe(ticket_id):
    conn = get_db()
    ticket = conn.execute('''
        SELECT t.*, c.name as client_name, c.email as client_email,
               c.company, c.phone as client_phone,
               a.name as agent_name
        FROM tickets t
        LEFT JOIN clients c ON t.client_id = c.id
        LEFT JOIN agents a ON t.assigned_to = a.login
        WHERE t.id = ?
    ''', (ticket_id,)).fetchone()

    if not ticket:
        flash('Chamado não encontrado.', 'error')
        return redirect(url_for('dashboard'))

    comments = conn.execute(
        'SELECT * FROM ticket_comments WHERE ticket_id = ? ORDER BY created_at ASC', (ticket_id,)
    ).fetchall()
    agents = conn.execute("SELECT id, name, login FROM agents WHERE active = 1 ORDER BY name").fetchall()
    conn.close()
    return render_template('chamado_detalhe.html', ticket=ticket, comments=comments, agents=agents)


@app.route('/chamado/<int:ticket_id>/status', methods=['POST'])
def update_status(ticket_id):
    data = request.get_json()
    new_status = data.get('status')
    if new_status not in ['a_fazer', 'atendendo', 'pausado', 'resolvido']:
        return jsonify({'success': False}), 400
    conn = get_db()
    conn.execute('UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?',
                 (new_status, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ticket_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/chamado/<int:ticket_id>/comentar', methods=['POST'])
def add_comment(ticket_id):
    conn = get_db()
    conn.execute(
        'INSERT INTO ticket_comments (ticket_id, author, content) VALUES (?, ?, ?)',
        (ticket_id, request.form.get('author', 'Atendente'), request.form['content'])
    )
    conn.commit()
    conn.close()
    flash('Comentário adicionado!', 'success')
    return redirect(url_for('chamado_detalhe', ticket_id=ticket_id))


@app.route('/chamado/<int:ticket_id>/transferir', methods=['POST'])
def transferir_chamado(ticket_id):
    new_login = request.form.get('new_agent', '').strip()
    motivo    = request.form.get('motivo', '').strip()

    conn = get_db()
    ticket    = conn.execute('SELECT assigned_to, title FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
    new_agent = conn.execute('SELECT name, login FROM agents WHERE login = ? AND active = 1',
                             (new_login,)).fetchone()

    if not ticket or not new_agent:
        conn.close()
        flash('Atendente inválido ou chamado não encontrado.', 'error')
        return redirect(url_for('chamado_detalhe', ticket_id=ticket_id))

    old_login = ticket['assigned_to'] or 'Não atribuído'
    old_agent = conn.execute('SELECT name FROM agents WHERE login = ?', (old_login,)).fetchone()
    old_name  = old_agent['name'] if old_agent else old_login

    # Update ticket
    conn.execute(
        'UPDATE tickets SET assigned_to = ?, updated_at = ? WHERE id = ?',
        (new_login, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ticket_id)
    )

    # System comment logging the transfer
    note = f'Chamado transferido de {old_name} → {new_agent["name"]}.'
    if motivo:
        note += f' Motivo: {motivo}'
    conn.execute(
        'INSERT INTO ticket_comments (ticket_id, author, content, is_system) VALUES (?, ?, ?, 1)',
        (ticket_id, 'Sistema', note)
    )
    conn.commit()
    conn.close()
    flash(f'Chamado transferido para {new_agent["name"]}!', 'success')
    return redirect(url_for('chamado_detalhe', ticket_id=ticket_id))


@app.route('/chamado/<int:ticket_id>/deletar', methods=['POST'])
def deletar_chamado(ticket_id):
    conn = get_db()
    conn.execute('DELETE FROM ticket_comments WHERE ticket_id = ?', (ticket_id,))
    conn.execute('DELETE FROM tickets WHERE id = ?', (ticket_id,))
    conn.commit()
    conn.close()
    flash('Chamado removido.', 'success')
    return redirect(url_for('dashboard'))


# ─────────────────────────────────────────────
# Routes — Clients
# ─────────────────────────────────────────────
@app.route('/clientes')
def clientes():
    conn = get_db()
    clients = conn.execute('''
        SELECT c.*, COUNT(t.id) as total_tickets,
               SUM(CASE WHEN t.status != 'resolvido' THEN 1 ELSE 0 END) as open_tickets
        FROM clients c LEFT JOIN tickets t ON c.id = t.client_id
        GROUP BY c.id ORDER BY c.name
    ''').fetchall()
    conn.close()
    return render_template('clientes.html', clients=clients)


@app.route('/novo-cliente', methods=['GET', 'POST'])
def novo_cliente():
    if request.method == 'POST':
        conn = get_db()
        conn.execute('''
            INSERT INTO clients
                (type, name, email, phone, phone2, company, cnpj, website,
                 cep, street, number, complement, neighborhood, city, state, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            request.form.get('type', 'PJ'),
            request.form['name'].strip(),
            request.form['email'].strip().lower(),
            request.form.get('phone', ''),
            request.form.get('phone2', ''),
            request.form.get('company', ''),
            request.form.get('cnpj', ''),
            request.form.get('website', ''),
            request.form.get('cep', ''),
            request.form.get('street', ''),
            request.form.get('number', ''),
            request.form.get('complement', ''),
            request.form.get('neighborhood', ''),
            request.form.get('city', ''),
            request.form.get('state', ''),
            request.form.get('notes', ''),
        ))
        conn.commit()
        conn.close()
        flash('Cliente cadastrado com sucesso!', 'success')
        return redirect(url_for('clientes'))
    return render_template('novo_cliente.html', form={})


@app.route('/cliente/<int:client_id>/editar', methods=['GET', 'POST'])
def editar_cliente(client_id):
    conn = get_db()
    client = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
    if not client:
        conn.close()
        flash('Cliente não encontrado.', 'error')
        return redirect(url_for('clientes'))

    if request.method == 'POST':
        conn.execute('''
            UPDATE clients SET
                type=?, name=?, email=?, phone=?, phone2=?, company=?, cnpj=?, website=?,
                cep=?, street=?, number=?, complement=?, neighborhood=?, city=?, state=?, notes=?
            WHERE id=?
        ''', (
            request.form.get('type', 'PJ'),
            request.form['name'].strip(),
            request.form['email'].strip().lower(),
            request.form.get('phone', ''),
            request.form.get('phone2', ''),
            request.form.get('company', ''),
            request.form.get('cnpj', ''),
            request.form.get('website', ''),
            request.form.get('cep', ''),
            request.form.get('street', ''),
            request.form.get('number', ''),
            request.form.get('complement', ''),
            request.form.get('neighborhood', ''),
            request.form.get('city', ''),
            request.form.get('state', ''),
            request.form.get('notes', ''),
            client_id,
        ))
        conn.commit()
        conn.close()
        flash('Cliente atualizado com sucesso!', 'success')
        return redirect(url_for('clientes'))

    conn.close()
    return render_template('novo_cliente.html', form=dict(client), editing=client_id)


# ─────────────────────────────────────────────
# Routes — Agents
# ─────────────────────────────────────────────
@app.route('/atendentes')
def atendentes():
    conn = get_db()
    agents = conn.execute('''
        SELECT a.*, COUNT(t.id) as ticket_count
        FROM agents a LEFT JOIN tickets t ON t.assigned_to = a.login AND t.status != 'resolvido'
        GROUP BY a.id ORDER BY a.name
    ''').fetchall()
    conn.close()
    return render_template('atendentes.html', agents=agents)


@app.route('/novo-atendente', methods=['GET', 'POST'])
def novo_atendente():
    if request.method == 'POST':
        name     = request.form['name'].strip()
        email    = request.form['email'].strip().lower()
        login    = request.form['login'].strip().lower()
        password = request.form['password']
        role     = request.form.get('role', 'atendente')

        if len(password) < 6:
            flash('A senha deve ter no mínimo 6 caracteres.', 'error')
            return render_template('novo_atendente.html', form=request.form)

        conn = get_db()
        if conn.execute('SELECT id FROM agents WHERE login = ?', (login,)).fetchone():
            conn.close()
            flash(f'Login "{login}" já está em uso.', 'error')
            return render_template('novo_atendente.html', form=request.form)
        if conn.execute('SELECT id FROM agents WHERE email = ?', (email,)).fetchone():
            conn.close()
            flash(f'E-mail "{email}" já está cadastrado.', 'error')
            return render_template('novo_atendente.html', form=request.form)

        conn.execute(
            'INSERT INTO agents (name, email, login, password_hash, role) VALUES (?, ?, ?, ?, ?)',
            (name, email, login, generate_password_hash(password), role)
        )
        conn.commit()
        conn.close()
        flash(f'Atendente "{name}" cadastrado! Login: {login}', 'success')
        return redirect(url_for('atendentes'))

    return render_template('novo_atendente.html', form={})


@app.route('/atendente/<int:agent_id>/toggle', methods=['POST'])
def toggle_agent(agent_id):
    conn = get_db()
    agent = conn.execute('SELECT active FROM agents WHERE id = ?', (agent_id,)).fetchone()
    if agent:
        conn.execute('UPDATE agents SET active = ? WHERE id = ?',
                     (0 if agent['active'] else 1, agent_id))
        conn.commit()
    conn.close()
    flash('Status do atendente atualizado.', 'success')
    return redirect(url_for('atendentes'))


@app.route('/atendente/<int:agent_id>/resetar-senha', methods=['POST'])
def resetar_senha(agent_id):
    nova_senha = request.form.get('nova_senha', '').strip()
    if len(nova_senha) < 6:
        flash('A nova senha deve ter no mínimo 6 caracteres.', 'error')
        return redirect(url_for('atendentes'))
    conn = get_db()
    conn.execute('UPDATE agents SET password_hash = ? WHERE id = ?',
                 (generate_password_hash(nova_senha), agent_id))
    conn.commit()
    conn.close()
    flash('Senha redefinida com sucesso.', 'success')
    return redirect(url_for('atendentes'))


# ─────────────────────────────────────────────
# Routes — Email config & checker
# ─────────────────────────────────────────────
@app.route('/config/email', methods=['GET', 'POST'])
def config_email():
    conn = get_db()
    if request.method == 'POST':
        old_config = conn.execute('SELECT active, since_uid FROM email_config WHERE id = 1').fetchone()
        was_active = old_config['active'] if old_config else 0
        new_active = 1 if request.form.get('active') else 0

        conn.execute('''
            UPDATE email_config SET
                imap_host       = ?,
                imap_port       = ?,
                email_user      = ?,
                email_password  = CASE WHEN ? = '' THEN email_password ELSE ? END,
                active          = ?,
                check_interval  = ?
            WHERE id = 1
        ''', (
            request.form['imap_host'],
            int(request.form.get('imap_port', 993)),
            request.form['email_user'],
            request.form.get('email_password', ''),
            request.form.get('email_password', ''),
            new_active,
            int(request.form.get('check_interval', 5)),
        ))
        conn.commit()

        # Bootstrap UID bookmark when monitoring is first activated
        # (or when credentials changed and re-activated)
        if new_active and (not was_active or not old_config['since_uid']):
            fresh = conn.execute('SELECT * FROM email_config WHERE id = 1').fetchone()
            conn.close()
            uid = _bootstrap_since_uid(fresh)
            if uid is not None:
                flash(f'Monitoramento ativado! E-mails a partir de agora serão processados (UID bookmark: {uid}).', 'success')
            else:
                flash('Configuração salva, mas não foi possível conectar ao IMAP para definir o ponto de partida.', 'error')
        else:
            conn.close()
            flash('Configuração de e-mail salva!', 'success')

        return redirect(url_for('config_email'))

    config = conn.execute('SELECT * FROM email_config WHERE id = 1').fetchone()
    conn.close()
    return render_template('config_email.html', config=config)


@app.route('/verificar-emails', methods=['POST'])
def verificar_emails():
    result = check_email_inbox()
    if result['success']:
        flash(result['message'], 'success')
    else:
        flash(f"Erro: {result['message']}", 'error')
    return redirect(request.referrer or url_for('dashboard'))


# ─────────────────────────────────────────────
# Routes — API
# ─────────────────────────────────────────────
@app.route('/api/cep/<cep>')
def api_cep(cep):
    cep_digits = ''.join(c for c in cep if c.isdigit())[:8]
    if len(cep_digits) != 8:
        return jsonify({'erro': True}), 400
    try:
        url = f'https://viacep.com.br/ws/{cep_digits}/json/'
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        return jsonify(data)
    except Exception as e:
        return jsonify({'erro': True, 'message': str(e)}), 500


@app.route('/api/tickets')
def api_tickets():
    conn = get_db()
    tickets = conn.execute('''
        SELECT t.*, c.name as client_name, a.name as agent_name
        FROM tickets t
        LEFT JOIN clients c ON t.client_id = c.id
        LEFT JOIN agents a ON t.assigned_to = a.login
        ORDER BY t.created_at DESC
    ''').fetchall()
    conn.close()
    return jsonify([dict(t) for t in tickets])


def create_app():
    init_db()
    return app


if __name__ == '__main__':
    init_db()
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        t = threading.Thread(target=_email_polling_loop, daemon=True)
        t.start()
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'development') != 'production'
    print("\n  Sistema Helpdesk iniciado!")
    print(f"  Acesse: http://127.0.0.1:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=debug)
else:
    # Called by gunicorn — initialize DB on first import
    init_db()
    _email_thread = threading.Thread(target=_email_polling_loop, daemon=True)
    _email_thread.start()
