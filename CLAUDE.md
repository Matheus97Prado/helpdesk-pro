# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run locally:**
```
python app.py
```
Acessa em `http://127.0.0.1:5000`. A porta pode ser alterada via variável `PORT`.

**Instalar dependências:**
```
pip install -r requirements.txt
```

**Produção (Render):**
```
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

## Arquitetura

Aplicação Flask de página única (`app.py`) com banco SQLite (`helpdesk.db`). Toda a lógica de negócio, rotas e helpers estão em `app.py`. Não há blueprints nem módulos separados.

### Banco de dados

SQLite com 5 tabelas, criadas e populadas com dados de exemplo em `init_db()`:

- `clients` — clientes PF/PJ com endereço completo
- `agents` — atendentes com login/senha (hash Werkzeug), papel `admin` ou `atendente`
- `tickets` — chamados com status (`a_fazer`, `atendendo`, `pausado`, `resolvido`), prioridade e categoria
- `ticket_comments` — comentários de chamados; `is_system=1` indica nota automática do sistema
- `email_config` — linha única (id=1) com credenciais IMAP e estado do monitoramento

`get_db()` abre uma nova conexão por chamada; todas as rotas fecham a conexão explicitamente. Não há ORM.

### Monitoramento de e-mail

Uma thread daemon (`_email_polling_loop`) checa a caixa IMAP no intervalo configurado (padrão: 5 min). Ao ativar o monitoramento pela primeira vez, `_bootstrap_since_uid` salva o maior UID atual como bookmark para ignorar e-mails antigos. Novos e-mails criam clientes e chamados automaticamente; deduplicação por assunto + cliente nos últimos 10 minutos.

### Templates

Jinja2 em `templates/`. `base.html` é o layout raiz com navegação lateral. Todas as outras páginas estendem `base.html`.

### Deploy

Configurado para Render via `render.yaml`. O `Procfile` contém o mesmo comando gunicorn para plataformas Heroku-compatíveis. A variável `FLASK_ENV=production` desativa o modo debug.

### API

- `GET /api/tickets` — lista todos os chamados em JSON
- `GET /api/cep/<cep>` — proxy para ViaCEP (preenchimento automático de endereço no cadastro de clientes)
