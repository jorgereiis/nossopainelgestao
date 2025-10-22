# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Django-based customer management system for IPTV/streaming services. The application manages customer subscriptions, payments, automated WhatsApp notifications, content monitoring, and integrations with external APIs (WhatsApp, Telegram, OpenAI).

**Tech Stack:**
- Django (Python web framework)
- SQLite database (configured for MySQL as alternative)
- WhatsApp integration via WPPConnect API
- Telegram bot integration
- OpenAI integration
- Schedule-based task automation
- Plotly/Matplotlib for data visualization

## Development Commands

### Environment Setup
```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Apply migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic --noinput
```

### Running the Application
```bash
# Development server
python manage.py runserver

# Production server (with gunicorn)
gunicorn setup.wsgi:application

# Run scheduler for automated tasks
python scripts/agendamentos.py
```

### Database Operations
```bash
# Create migrations after model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Backup database (uses backup_db.sh script)
./backup_db.sh
```

### Testing & Code Quality
```bash
# Run tests
python manage.py test

# Format code with Black
black . --line-length 88 --skip-string-normalization
```

## Architecture & Key Concepts

### Application Structure

**`cadastros/`** - Core application module containing all business logic
- `models.py` - Domain models (Cliente, Mensalidade, Plano, etc.)
- `views.py` - HTTP request handlers (dashboard, CRUD operations)
- `signals.py` - Database triggers for automatic data synchronization
- `services/` - Business logic layer (WhatsApp operations, logging)
- `utils.py` - Helper functions and data processing utilities

**`setup/`** - Django project configuration
- `settings.py` - Application settings (security, database, middleware)
- `urls.py` - Root URL routing
- `middleware.py` - Custom middleware (user authentication checks)
- `context_processors.py` - Global template context (notifications)
- `static/` - Static assets (CSS, JS, images)

**`scripts/`** - Standalone automation scripts
- `agendamentos.py` - Main scheduler orchestrating all automated tasks
- `mensagens_wpp.py` - WhatsApp message automation (billing reminders, notifications)
- `check_canais_dns.py` - DNS/channel availability monitoring
- `upload_status_wpp.py` - Telegram content synchronization
- `comparar_m3u8.py` - M3U8 playlist comparison and updates
- `mensagem_gp_wpp.py` - WhatsApp group messages (sales, football)

**`wpp/`** - WhatsApp API integration layer
- `api_connection.py` - WPPConnect API client wrapper

**`integracoes/`** - External service integrations
- `telegram_connection.py` - Telegram bot integration
- `openai_chat.py` - OpenAI API wrapper

**`templates/`** - Django HTML templates
- `dashboard.html` - Main dashboard with charts and metrics
- `base.html` - Base template with navigation
- `partials/` - Reusable template components

### Domain Model Relationships

```
User (Django Auth)
  └─→ Cliente (Customer)
       ├─→ Mensalidade (Monthly Payment) - tracks billing cycles
       ├─→ ClientePlanoHistorico (Plan History) - for revenue calculation
       ├─→ ContaDoAplicativo (App Credentials) - streaming app access
       └─→ indicado_por (self-referential) - referral tracking

Cliente references:
  - Servidor (Server: CLUB, PLAY, ALPHA, etc.)
  - Plano (Plan: Mensal, Trimestral, etc.)
  - Tipos_pgto (Payment Method: PIX, Credit Card, Boleto)
  - Dispositivo (Device type)
  - Aplicativo (Streaming app)
```

### Signal-Driven Business Logic

The `signals.py` module implements critical automatic behaviors:

1. **Payment → New Billing Cycle**: When `Mensalidade.pgto=True`, automatically creates next billing cycle based on plan type (monthly/quarterly/annual)
2. **Last Payment Tracking**: Updates `Cliente.ultimo_pagamento` when payment recorded
3. **WhatsApp Label Sync**: After customer status changes (active/cancelled), updates WhatsApp contact labels via WPPConnect API

### Task Scheduler System

`scripts/agendamentos.py` orchestrates all automated operations:

**Daily Tasks:**
- `08:00` - Football group messages
- `10:00` & `20:00` - Sales group messages
- `12:00` - Scheduled message sends (billing reminders)
- `17:00` - Cancelled subscriptions cleanup
- `23:00` - Telegram content sync (async)
- `23:50` - Upload images from Telegram

**Recurring Tasks:**
- Every 1 minute - Check for scheduled message sends (`executar_envios_agendados`)
- Every 60 minutes - Database backup

The scheduler uses `threading` for sync tasks and dedicated `asyncio` event loops for async tasks (Telegram).

### WhatsApp Automation System

**Message Types:**
- **Vencimentos (Due Date Reminders)**: Sent 2 days before billing due date
- **Atrasos (Late Payment Notices)**: Sent 2 days after due date
- **Cancelamentos (Cancellation Notices)**: When subscription cancelled
- **Indicações (Referral Bonuses)**: When referral program applies

**Configuration:**
- `HorarioEnvios` model defines when automated messages are sent
- `PlanoIndicacao` model configures referral/loyalty discounts
- Messages only sent if customer has `nao_enviar_msgs=False`

**Integration:**
- Uses WPPConnect API (self-hosted WhatsApp Web API)
- Session management via `SessaoWpp` model
- Label-based contact organization for filtering

### Revenue & Analytics

**Dashboard Metrics:**
- Total active customers by server
- Monthly revenue tracking
- Geographic distribution (via DDD → UF mapping)
- Payment history charts (Plotly.js)
- Customer acquisition/churn trends
- "Patrimônio" (net worth) calculation from `ClientePlanoHistorico`

**Key Views:**
- `TabelaDashboard` - Main dashboard with all metrics
- `evolucao_patrimonio` - Revenue evolution over time
- `adesoes_cancelamentos_api` - Customer growth/churn API
- `mapa_clientes_data` - Geographic distribution (GeoJSON)

### Notification System

Real-time notifications for billing events:
- `NotificationRead` tracks which notifications user has seen
- `context_processors.notifications` provides unread count globally
- Notifications appear in dropdown (AJAX polling)
- Integrates with `Mensalidade` model for payment reminders

### User Action Logging

`UserActionLog` model records all manual operations:
- Create/Update/Delete operations
- Customer cancellations/reactivations
- Payment registrations
- Import operations
- Includes IP address, request path, and JSON extras

## Configuration & Environment

**Required `.env` variables:**
- `SECRET_KEY` - Django secret key (required)
- `RECAPTCHA_PUBLIC_KEY` / `RECAPTCHA_PRIVATE_KEY` - Google reCAPTCHA
- `URL_API_WPP` - WPPConnect API base URL
- `MEU_NUM_CLARO` - WhatsApp number for sending
- `DJANGO_ALLOWED_HOSTS` - Comma-separated allowed hosts
- `SECURE_SSL_REDIRECT` - Enable HTTPS redirect (0/1)
- `SECURE_HSTS_SECONDS` - HSTS header duration

**Database:**
- Default: SQLite (`db.sqlite3`)
- MySQL option commented out in `settings.py`

**Static Files:**
- Served via WhiteNoise middleware
- Source: `setup/static/`
- Collected to: `staticfiles/`

**Timezone:** `America/Recife` (BRT)

**Session:** 2-hour timeout (`SESSION_COOKIE_AGE = 7200`)

## Important Implementation Notes

### Phone Number Format
All phone numbers stored in E.164 format: `+55DDDNUMBER`
- `Cliente.telefone` auto-converts on save
- `DadosBancarios.wpp` normalizes via `formatar_telefone()`

### UF (State) Auto-Detection
`Cliente.definir_uf()` automatically sets state based on DDD (area code) from phone number using `DDD_UF_MAP` constant.

### MAC Address Normalization
`ContaDoAplicativo` normalizes device IDs to MAC format (`AA:BB:CC:DD:EE:FF`) when applicable.

### Plan Change Tracking
When customer changes plan:
1. Close current `ClientePlanoHistorico` record (set `fim` date)
2. Create new record with new plan details
3. Used for accurate "patrimônio" calculations over time

### Cancellation Flow
When cancelling customer:
1. Set `Cliente.cancelado=True` and `data_cancelamento`
2. Cancel all unpaid `Mensalidade` records
3. Remove WhatsApp labels via signal
4. Log action in `UserActionLog`

### Reactivation Flow
When reactivating cancelled customer:
1. Set `Cliente.cancelado=False`, clear `data_cancelamento`
2. Create new `Mensalidade` for next cycle
3. Create new `ClientePlanoHistorico` entry
4. Restore WhatsApp labels via signal

## Admin Interface

Accessible at `/painel-configs/` (Django admin)

Custom admin configurations in `cadastros/admin.py`:
- Inline editing for related models
- Custom list displays and filters
- Search functionality across multiple fields

## Common Development Patterns

### Adding a New Automated Message Type
1. Add choice to `HorarioEnvios.TITULO`
2. Add description/example to `DESCRICOES`/`EXEMPLOS` dicts
3. Implement message logic in `scripts/mensagens_wpp.py`
4. Register in scheduler (`scripts/agendamentos.py`)

### Creating New Customer Actions
1. Add view in `cadastros/views.py`
2. Add URL pattern in `cadastros/urls.py`
3. Log action via `UserActionLog.objects.create()`
4. Add signal if automatic side effects needed

### Working with Logs
- All logs stored in `logs/` directory by category
- Use `cadastros.services.logging.append_line()` for custom logs
- Scheduler logs: `logs/Scheduler/scheduler.log`
- WhatsApp logs: `logs/UploadStatusWpp/`, `logs/Envios indicacoes realizadas/`
- DNS check logs: `logs/DNS/`

## Security Considerations

- reCAPTCHA v3 on login (score threshold: 0.85)
- CSRF protection enabled
- Secure cookie flags (Secure, HttpOnly, SameSite=Lax)
- `CheckUserLoggedInMiddleware` validates user state
- API authentication via `SecretTokenAPI` model
- `.env` file excluded from git (sensitive credentials)
- Admin interface at non-standard URL (`/painel-configs/`)
