# CareerLens AI — Agent Context Document

> This file provides essential architectural context for any AI agent working on this project.

---

## Application Nature

CareerLens AI is an **ATS (Applicant Tracking System) optimizer** that generates tailored, ATS-friendly resume reports. It takes a master resume + job description as input, runs them through an LLM, and produces a fully rendered HTML report with strategic alignment analysis, seniority-calibrated content, and a professional PDF-ready layout.

### Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Backend** | Python 3.11 / FastAPI | Serves both the API and the Flutter web build as static files |
| **Frontend** | Flutter (Dart) | Web + Android targets; single-screen input UI with glassmorphism design |
| **Template Engine** | Jinja2 | Renders `Template4.html` with LLM-generated data |
| **LLM Integration** | OpenAI-compatible API (local) + Google Gemini (cloud) | BYOK (Bring Your Own Key) routing system |
| **Schema Generation** | Pydantic `create_model()` | Dynamically parses HTML template placeholders into typed models at runtime |

---

## Docker Architecture

This is a **Dockerized application** designed to run on many different PCs with varying hardware.

### Multi-Stage Dockerfile (`backend/Dockerfile`)

```
Stage 1: Flutter Web Build
  ├── Uses ghcr.io/cirruslabs/flutter:stable
  ├── Copies frontend/ and runs flutter build web --release
  └── Outputs /app/frontend/build/web/

Stage 2: Python Backend
  ├── Uses python:3.11-slim
  ├── Installs backend/requirements.txt
  ├── Copies backend/, Template4.html, MasterDataMDfileVER-4.md
  ├── Copies Flutter web build into backend/static/
  └── Runs uvicorn backend.main:app on port 8000
```

### Docker Compose (`docker-compose.yml`)

- Single service: `careerlens-backend`
- Maps port `8000:8000`
- Uses `.env` for environment variables (`GOOGLE_API_KEY`, `LLM_PROVIDER`, `CL_API_SECRET`, etc.)
- `extra_hosts: host.docker.internal:host-gateway` — required for the container to reach LM Studio running on the host machine

### Key Docker Considerations

1. **Host LLM Access:** Local LLM calls go to `http://host.docker.internal:1234/v1` — LM Studio must be running on the host with the API server enabled
2. **No local Downloads folder dependencies:** Dockerfile must be self-contained and agnostic to the host filesystem
3. **Multi-hardware deployment:** Users will have different GPUs (RTX 3060, 4070, etc.) running different quantized models. The backend must handle varied LLM capabilities gracefully
4. **Some LLMs will NOT support structured output / GBNF grammars** — any constrained decoding features must degrade gracefully to prompt-based JSON generation

---

## LLM Routing (BYOK System)

The `generate_career_data()` function in `llm_service.py` implements a three-path routing system:

```
User API Key Input
    │
    ├─ Blank/None ──────────► LocalLLMClient (RTX via TailScale/Docker)
    │
    ├─ http://... URL ──────► LocalLLMClient (LM Studio BYOK endpoint)
    │                          Supports: http://url:1234/v1|API_KEY|MODEL_ID
    │
    └─ Google API Key ──────► GoogleLLMClient (Gemini 2.5 Flash)
                                │
                                └─ On BYOKKeyError ──► LocalLLMClient fallback
                                                        + X-BYOK-Error header
```

### Error Handling

- **BYOKKeyError:** Typed exception for user-key failures (invalid, expired, quota exhausted)
- **Retry Loop:** `@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))` for JSON validation failures
- **Single-Request Lock:** `threading.Lock()` with 120s timeout protects GPU from concurrent generation
- **Rate Limiting:** 5 requests/day per IP (exempts localhost/Docker-internal IPs)

---

## Template System

### `Template4.html`

A Tailwind CSS + Font Awesome HTML template with Jinja2 placeholders. Contains:

- **Scalar placeholders:** `{{VARIABLE_NAME}}` — simple string substitution
- **List placeholders:** `{% for item in LIST_NAME %}...{% endfor %}` — iterable blocks
- **Nested lists:** `{% for bullet in exp.BULLETS %}` — arrays within array items

### `dynamic_parsing.py`

Parses `Template4.html` at runtime using regex to extract all placeholder patterns, then dynamically builds a Pydantic model via `create_model()`. This model serves as:

1. The JSON Schema injected into the LLM prompt
2. The validation contract for LLM output
3. The data source for Jinja2 template rendering

### Current Placeholder Categories

| Category | Examples | Type |
|----------|----------|------|
| Contact | `CANDIDATE_NAME`, `CANDIDATE_EMAIL`, `CANDIDATE_LINKEDIN` | `str` (required) |
| Header | `JOB_TITLE`, `JOB_SUBTITLE`, `CONFIDENCE_SCORE` | `Optional[str]` |
| Metrics | `COMMUTE_TIME`, `MARKET_SALARY`, `REALITY_BADGE` | `Optional[str]` |
| Content | `TAILORED_SUMMARY`, `RESUME_HEADLINE` | `Optional[str]` |
| Lists | `MATCHES`, `EXPERIENCES`, `TECHNOLOGIES`, `EXPERTISE`, `EDUCATIONS` | `Optional[List[...]]` |

---

## Flutter Frontend

### Platform Targets

- **Web:** Primary deployment — served as static files from the backend container
- **Android:** Secondary — connects to backend via `http://10.0.2.2:8000` (emulator) or configured URL

### Key Features

- Material 3 with glassmorphism design
- Persistent storage (`SharedPreferences`) for master resume and API key
- Seniority selection dropdown (Executive → Entry)
- BYOK error dialog — blocking modal when user's API key fails, showing the fallback result
- HTML download with dynamic filename extraction from generated content

### Backend URL Resolution

```dart
if (kIsWeb) → "${Uri.base.origin}/api/v1"      // Same-origin (Docker)
if (Android) → "http://10.0.2.2:8000/api/v1"   // Emulator loopback
else → "http://127.0.0.1:8000/api/v1"           // Desktop/fallback
```

### Tailscale Network (Physical Android Devices)

Tailscale is running locally on the host PC, creating a mesh VPN that allows a **physical Android phone** (with the Flutter APK installed) to reach the Docker backend and LM Studio without port forwarding or public exposure.

```
Physical Android Phone (Tailscale client)
    │
    └──► Tailscale Mesh VPN ──► Host PC (Tailscale node)
                                    │
                                    ├─ :8000 ──► Docker container (FastAPI backend)
                                    │               │
                                    │               └─ host.docker.internal:1234 ──► LM Studio
                                    │
                                    └─ :1234 ──► LM Studio API server (direct)
```

- **Tailscale IP:** The Android APK uses the host PC's Tailscale IP (e.g., `http://100.x.x.x:8000/api/v1`) instead of `10.0.2.2`
- **Tailscale Funnel:** Can optionally expose the backend publicly via `tailscale funnel 8000` for sharing/demo purposes
- **No firewall config needed:** Tailscale handles NAT traversal automatically
- **LM Studio access from Docker:** The container reaches LM Studio via `host.docker.internal:1234`, not through Tailscale — Tailscale is only for external device → host connectivity

---

## Development Workflow

### Local Development

```bash
# Start LM Studio with API server on port 1234
# Then:
cd backend
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Build & Run

```bash
docker compose build
docker compose up
# Access at http://localhost:8000
```

### Build Scripts

- `build.ps1` — PowerShell build script for Windows
- `build.sh` — Shell build script for Linux/Mac

---

## Important Rules for Agents

1. **Never hardcode API keys** — use environment variables via `.env`
2. **Always use `cmd /c` prefix** for shell executions on Windows to prevent terminal hangs
3. **Dockerfile must be multi-stage** and must NOT reference host-local paths (e.g., Downloads folder)
4. **If a command fails twice with the same error, STOP and ask the user** — do not self-heal
5. **Do not install system-level software** without explicit user approval
6. **Template changes require re-testing `dynamic_parsing.py`** — the Pydantic model is generated from the HTML
