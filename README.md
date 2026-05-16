# EdNet AI-Enabled Framework

An AI-powered management framework for international education and training networks, integrating multilingual communication, data analytics, and ethical governance into a single deployable system.

> **Thesis prototype** — Master's thesis, Computer Science, 2025–2026.

---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Running the System](#running-the-system)
- [Using the Gradio UI](#using-the-gradio-ui)
- [Using the Superset Dashboards](#using-the-superset-dashboards)
- [Running the Ethics Audit](#running-the-ethics-audit)
- [Running the Test Suite](#running-the-test-suite)
- [Switching LLM Providers](#switching-llm-providers)
- [Stopping and Resetting](#stopping-and-resetting)
- [Troubleshooting](#troubleshooting)

---

## Overview

The framework consists of three modules running as a Docker Compose stack:

| Module | Purpose | Interface |
|---|---|---|
| **Communication** | Multilingual document generation via prompt templates | Gradio web app (`localhost:7860`) |
| **Analytics & BI** | KPI computation and network performance dashboards | Apache Superset (`localhost:8088`) |
| **Ethical Governance** | Ethics auditing, human-in-the-loop review, audit logging | Gradio Review Queue tab + CLI |

All three modules share a single PostgreSQL database and are orchestrated through a Python coordinator layer.

---

## Prerequisites

Before starting, ensure the following are installed on your machine:

| Tool | Minimum Version | Check Command |
|---|---|---|
| Docker | 24.0 | `docker --version` |
| Docker Compose | 2.20 | `docker compose version` |
| Git | any | `git --version` |

You also need API keys for at least one LLM provider:

- **Anthropic** (primary): obtain at [console.anthropic.com](https://console.anthropic.com)
- **OpenAI** (secondary, for comparative evaluation): obtain at [platform.openai.com](https://platform.openai.com)

The system runs entirely locally. The only outbound network calls are to the LLM APIs.

**Hardware.** The stack has been tested on a machine with 8 GB RAM. Minimum recommended is 4 GB free RAM. No GPU is required.

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/ednet-framework.git
cd ednet-framework

# 2. Set up environment variables
cp .env.example .env
# Open .env in any text editor and fill in your API keys (see Configuration section)

# 3. Build and start all services
docker compose up --build -d

# 4. Wait ~30 seconds for services to initialize, then seed the database
docker compose exec app python data/seed_data.py

# 5. Compute initial KPI values
docker compose exec app python -c \
  "from modules.analytics.kpi_engine import KPIEngine; \
   from datetime import date; \
   KPIEngine().compute_all(network_id=1, \
   period_start=date(2023,1,1), period_end=date(2024,12,31))"

# 6. Access the services
#    Gradio UI  → http://localhost:7860
#    Superset   → http://localhost:8088
```

That's it. The system is running.

---

## Project Structure

```
ednet-framework/
│
├── docker-compose.yml          # Container orchestration
├── Dockerfile                  # Shared image for app + scheduler
├── .env.example                # Environment variable template
├── requirements.txt            # Python dependencies
├── README.md                   # This file
│
├── app/
│   └── main.py                 # Gradio UI entry point
│
├── orchestrator/
│   ├── coordinator.py          # Main task routing logic
│   ├── session.py              # Session state management
│   └── llm_client.py          # Provider-agnostic LLM abstraction
│
├── modules/
│   ├── communication/
│   │   ├── prompt_engine.py    # YAML template loader and renderer
│   │   ├── language_router.py  # Language detection and fallback
│   │   └── templates/          # YAML prompt templates (5 files)
│   │
│   ├── analytics/
│   │   ├── kpi_engine.py       # KPI computation (10 indicators)
│   │   ├── kpi_definitions.py  # KPI catalog constants
│   │   └── db_connector.py     # SQLAlchemy session factory
│   │
│   └── governance/
│       ├── audit_logger.py     # LLM interaction logging
│       ├── ethics_auditor.py   # Ethics checklist evaluation
│       ├── hitl_controller.py  # Human review queue management
│       ├── ethics_audit_runner.py  # Batch audit CLI tool
│       └── ai_card_registry.py # AI Card loader
│
├── data/
│   ├── schema.sql              # PostgreSQL schema (run automatically on first start)
│   ├── seed_data.py            # Synthetic dataset generator
│   └── retention_policy.yaml  # Data retention configuration
│
├── scheduler/
│   └── jobs.py                 # Scheduled KPI computation (daily 02:00)
│
├── superset/
│   └── superset_config.py      # Superset configuration
│
└── tests/
    ├── test_communication.py
    ├── test_analytics.py
    └── test_governance.py
```

---

## Configuration

All configuration is done through the `.env` file. Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

Then open `.env` and set:

```bash
# ── Required ──────────────────────────────────────────────────────

# Primary LLM provider API key (Anthropic Claude)
ANTHROPIC_API_KEY=sk-ant-...

# Secondary LLM provider API key (OpenAI GPT-4o, used for evaluation)
OPENAI_API_KEY=sk-...

# Which provider to use for all tasks (change to "openai" to switch)
LLM_PRIMARY_PROVIDER=anthropic

# ── Database (defaults work fine, change only if port 5432 is taken) ──

POSTGRES_USER=ednet
POSTGRES_PASSWORD=ednet_secret
POSTGRES_DB=ednet_db
DATABASE_URL=postgresql://ednet:ednet_secret@postgres:5432/ednet_db

# ── Application ───────────────────────────────────────────────────

SESSION_RETENTION_HOURS=24
APP_PORT=7860

# ── Superset ──────────────────────────────────────────────────────

# Generate any random string for this key, e.g.:
# python -c "import secrets; print(secrets.token_hex(32))"
SUPERSET_SECRET_KEY=change_me_to_a_random_string
SUPERSET_PORT=8088
```

**Minimum viable configuration:** You need at least `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) and `SUPERSET_SECRET_KEY` filled in. All other values can remain as defaults.

---

## Running the System

### Starting

```bash
# Start all services in the background
docker compose up -d

# Start and watch logs (useful for debugging)
docker compose up
```

### Checking service health

```bash
# View status of all containers
docker compose ps

# Expected output — all containers should show "running" or "healthy":
# ednet_postgres    running (healthy)
# ednet_app         running
# ednet_scheduler   running
# ednet_superset    running
```

### Viewing logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f app
docker compose logs -f scheduler
docker compose logs -f superset
```

### First-time database setup

The database schema is applied automatically from `data/schema.sql` when the PostgreSQL container starts for the first time. You only need to seed the data manually:

```bash
# Seed synthetic dataset (run once after first startup)
docker compose exec app python data/seed_data.py

# Expected output:
# 🌱 Seeding EdNet synthetic dataset...
#   ✔ Network created (id=1)
#   ✔ 8 institutions created
#   ✔ 10 staff members created
#   ✔ 5 programs created
#   ✔ 120 students + enrollments created
#   ✔ Mobility records created
#   ✔ Events and participants created
#   ✔ KPI definitions seeded
# ✅ Dataset ready.
```

### Computing KPIs

KPIs are computed automatically by the scheduler daily at 02:00. To compute them immediately (required after first seeding):

```bash
docker compose exec app python -c \
  "from modules.analytics.kpi_engine import KPIEngine; \
   from datetime import date; \
   KPIEngine().compute_all(network_id=1, \
   period_start=date(2023,1,1), period_end=date(2024,12,31))"

# Expected output:
# Computing KPIs for network 1 (2023-01-01 → 2024-12-31)...
#   K01: 87.5000
#   K02: 31.1111
#   K03: 19.1667
#   ...
# ✔ KPI computation complete. 10 indicators updated.
```

---

## Using the Gradio UI

Open [http://localhost:7860](http://localhost:7860) in your browser.

The UI has three tabs:

---

### Tab 1 — Communication Tasks

Use this tab to generate AI-assisted documents.

**Step-by-step:**

1. **Select a Task** from the dropdown:
   - `Meeting Minutes` — generates formal minutes from a raw transcript
   - `Document Summarizer` — summarizes any institutional document
   - `Curriculum Designer` — drafts a joint curriculum framework
   - `Lecture Generator` — creates lecture content from a topic and objectives
   - `Collaboration Framework` — drafts an MOU/partnership outline

2. **Select Output Language**: `en` (English), `vi` (Vietnamese), or `fr` (French, meeting minutes only)

3. **Fill in the Input Text** — paste your transcript or document into the text box

4. **Fill in Task-specific Fields** — additional fields appear depending on the selected task:

   | Task | Additional Fields Required |
   |---|---|
   | Meeting Minutes | Network Name, Meeting Date |
   | Document Summarizer | *(none — input text only)* |
   | Curriculum Designer | Program Name, Institutions, Goals, Audience, Duration, Constraints |
   | Lecture Generator | Course Name, Topic, Objectives, Audience Level, Duration |
   | Collaboration Framework | Institutions, Purpose, Period, Activities, Constraints |

5. **Click "▶ Run Task"**

**Understanding the response:**

| Status | Meaning | Next Step |
|---|---|---|
| ✅ Delivered | Output ready, medium/low consequence | Copy output from the text box |
| ⏳ Pending Human Review | Output queued, high consequence | Go to Review Queue tab |
| 🚫 Blocked by Ethics Check | Output failed a safety check | Read the reason, revise input if needed |

**High-consequence tasks** (Meeting Minutes, Curriculum Designer, Collaboration Framework) always go to the Review Queue before delivery. This is by design.

---

### Tab 2 — Review Queue

Use this tab to review and approve AI-generated outputs that are pending human review.

**Step-by-step:**

1. Click **🔄 Refresh Queue** to load pending items
2. Select an item from the **Pending Outputs** dropdown
3. Read the **AI-Generated Draft** on the left
4. On the right, fill in your **Reviewer ID** (e.g. `staff_001`)
5. Choose a **Decision**:
   - `Approve` — accept the draft as-is
   - `Approve with Edits` — paste your corrected version in the Edited Output box
   - `Reject` — discard the output
6. Optionally add a **Review Note** (reason for edit or rejection)
7. Click **Submit Review**

After submission, the audit log is updated and the final output is retrievable.

---

### Tab 3 — Template Reference

A read-only reference showing all available prompt templates, their task types, consequence levels, and supported languages. No interaction required.

---

## Using the Superset Dashboards

Open [http://localhost:8088](http://localhost:8088) in your browser.

### First-time setup (one-time, ~3 minutes)

Superset requires a one-time manual configuration on first launch:

**1. Log in**
```
Username: admin
Password: admin
```

**2. Change the admin password** (recommended)
- Click the profile icon (top right) → Profile → Change Password

**3. Connect to the PostgreSQL database**
- Go to **Settings** (top right gear icon) → **Database Connections**
- Click **+ Database**
- Select **PostgreSQL**
- Fill in the connection details:
  ```
  Host:     postgres
  Port:     5432
  Database: ednet_db
  Username: ednet
  Password: ednet_secret
  ```
- Click **Test Connection** — should show "Connection looks good!"
- Click **Connect**

**4. Create the two dashboards**

Dashboard creation in Superset involves creating Charts and assembling them into Dashboards. Follow the chart specifications in Appendix B of the thesis report, or use the quick setup below:

**Quick setup via SQL Lab:**
- Go to **SQL Lab** (top menu)
- Select the `ednet_db` database and `public` schema
- Run a test query to verify data is present:
  ```sql
  SELECT kpi_id, name, value, period_start, period_end
  FROM kpi_values
  JOIN kpi_definitions USING (kpi_id)
  ORDER BY period_start;
  ```
  You should see 10 rows with the computed KPI values.

- Use **Charts** (top menu) → **+ Chart** to build individual charts using the `kpi_values`, `institutions`, `events`, and `enrollments` tables as datasets.

> **Note:** Full dashboard JSON export files will be added to the `superset/` directory in a future update, enabling one-click dashboard import.

---

## Running the Ethics Audit

The Ethics Audit Runner evaluates all logged LLM interactions against the ethics checklist and produces a compliance report.

```bash
# Text report to stdout
docker compose exec app python -m modules.governance.ethics_audit_runner \
  --period 2024-01-01 2024-12-31

# JSON report saved to file
docker compose exec app python -m modules.governance.ethics_audit_runner \
  --period 2024-01-01 2024-12-31 \
  --format json \
  --output /app/reports/audit_2024.json

# View the saved report
docker compose exec app cat /app/reports/audit_2024.json
```

> **Note:** If no LLM interactions have been logged yet (i.e. you haven't used the Communication Tasks tab), the report will show 0 entries evaluated with 100% compliance. Use the Communication Tasks tab first to generate some audit log entries.

---

## Running the Test Suite

```bash
# Run all tests
docker compose exec app pytest tests/ -v

# Run tests for a specific module
docker compose exec app pytest tests/test_communication.py -v
docker compose exec app pytest tests/test_analytics.py -v
docker compose exec app pytest tests/test_governance.py -v

# Run with coverage report
docker compose exec app pytest tests/ --cov=modules --cov=orchestrator --cov-report=term-missing
```

Expected result: all tests pass. Test coverage is approximately 84% of the source modules.

---

## Switching LLM Providers

To switch from Claude to GPT-4o:

1. Edit `.env`:
   ```bash
   LLM_PRIMARY_PROVIDER=openai
   ```

2. Restart the app container:
   ```bash
   docker compose restart app
   ```

No code changes are required. The provider abstraction in `orchestrator/llm_client.py` handles the switch transparently.

To switch back to Claude:
```bash
# Edit .env: LLM_PRIMARY_PROVIDER=anthropic
docker compose restart app
```

---

## Stopping and Resetting

### Stop the stack (preserve data)
```bash
docker compose down
```

### Start again (data preserved)
```bash
docker compose up -d
```

### Full reset (delete all data and start fresh)
```bash
# Stop all containers and delete volumes
docker compose down -v

# Rebuild and start
docker compose up --build -d

# Re-seed data
docker compose exec app python data/seed_data.py

# Recompute KPIs
docker compose exec app python -c \
  "from modules.analytics.kpi_engine import KPIEngine; \
   from datetime import date; \
   KPIEngine().compute_all(network_id=1, \
   period_start=date(2023,1,1), period_end=date(2024,12,31))"
```

> ⚠️ `docker compose down -v` permanently deletes the PostgreSQL volume. All seeded data, audit logs, and KPI values will be lost.

---

## Troubleshooting

### Container fails to start

```bash
# Check which container is failing
docker compose ps

# View its logs
docker compose logs <container_name>
```

---

### `postgres` container is unhealthy

**Symptom:** `docker compose ps` shows `ednet_postgres` as `unhealthy`.

**Cause:** Port 5432 may already be in use by a local PostgreSQL installation.

**Fix:** Change the exposed port in `docker-compose.yml`:
```yaml
postgres:
  ports:
    - "5433:5432"   # map to 5433 on host instead of 5432
```
Then update `DATABASE_URL` in `.env`:
```bash
DATABASE_URL=postgresql://ednet:ednet_secret@postgres:5432/ednet_db
# Note: keep the internal port as 5432 — only the host mapping changes
```

---

### `app` container crashes on startup with `RuntimeError: DATABASE_URL not set`

**Cause:** The `.env` file is missing or not found.

**Fix:**
```bash
# Verify .env exists
ls -la .env

# If missing, recreate it
cp .env.example .env
# Then fill in your API keys
```

---

### Gradio UI shows `Error` when running a task

**Possible causes:**

1. **Invalid API key** — verify your `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env`
   ```bash
   # Quick test for Anthropic key
   docker compose exec app python -c \
     "from anthropic import Anthropic; \
      c = Anthropic(); \
      r = c.messages.create(model='claude-haiku-4-5-20251001', max_tokens=10, \
      messages=[{'role':'user','content':'hi'}]); \
      print('Key valid:', r.content[0].text)"
   ```

2. **Empty input text** — the input text box must not be blank before clicking Run Task

3. **Missing required fields** — ensure all visible task-specific fields are filled in

---

### Superset shows no data in charts

**Cause:** KPI values have not been computed yet.

**Fix:** Run the KPI computation command:
```bash
docker compose exec app python -c \
  "from modules.analytics.kpi_engine import KPIEngine; \
   from datetime import date; \
   KPIEngine().compute_all(network_id=1, \
   period_start=date(2023,1,1), period_end=date(2024,12,31))"
```

---

### Superset login fails with `Invalid login credentials`

**Cause:** Superset admin account was not initialized.

**Fix:**
```bash
# Initialize Superset admin user manually
docker compose exec superset superset fab create-admin \
  --username admin \
  --firstname Admin \
  --lastname User \
  --email admin@ednet.local \
  --password admin

# Then run database upgrade
docker compose exec superset superset db upgrade
docker compose exec superset superset init
```

---

### `seed_data.py` fails with `duplicate key` error

**Cause:** The script has already been run on this database.

**Fix:** Either reset the database (see [Full reset](#stopping-and-resetting)) or skip re-seeding — the data is already there.

---

### Tests fail with `sqlalchemy.exc.OperationalError`

**Cause:** Tests that touch the database require the PostgreSQL container to be running.

**Fix:** Ensure the stack is up before running tests:
```bash
docker compose up -d
# Wait for postgres to be healthy
docker compose exec app pytest tests/ -v
```

Tests in `test_analytics.py` that use mock sessions do not require a live database and will pass regardless.

---

## Environment Summary

| Service | URL | Default Credentials |
|---|---|---|
| Gradio UI | http://localhost:7860 | None (open access) |
| Apache Superset | http://localhost:8088 | admin / admin |
| PostgreSQL | localhost:5432 | ednet / ednet_secret |

---

## License

This project is developed as a Master's thesis prototype. All code is for academic and research purposes.
