# CareerLens AI Sovereign SaaS

CareerLens AI is a robust sovereign application that customizes high-fidelity HTML document generation utilizing multi-model architectures.

## Architecture
- **Backend:** FastAPI, Pydantic, Uvicorn, Python 3.11
- **Frontend:** Flutter Web/Android (Dart)
- **Deployment:** Docker & Docker Compose

> [!WARNING]
> **Beware of Aggressive Browser Caching:** Flutter Web applications compile into massive Javascript bundles (`main.dart.js`) that modern browsers (especially Chrome) aggressively cache. If you successfully build the `main.dart` UI and spin up the Docker container but see no changes on the page, you MUST perform a Hard Refresh (`Ctrl+F5` or `Cmd+Shift+R`) to force the browser to dump the cached DOM payload.

## Prerequisites
- **Flutter SDK:** Must be installed and accessible in your PATH (`flutter`).
- **Docker & Docker Compose:** For running the isolated backend container.
- **LM Studio (Optional):** Required only if utilizing the `local` LLM provider. Must be running on port 1234 (`http://localhost:1234/v1`).
- **Python 3.11:** Required for local development.

## Setup Steps

### 1. Configure Environment
Rename `.env.template` to `.env` and fill in your Gemini key:
```bash
cp .env.template .env
```

### 2. Frontend Build
Compile the Flutter Web client and migrate it to the FastAPI static folder:
```bash
# This will execute `flutter build web --release` and copy the artifacts automagically.
chmod +x build.sh
./build.sh
```

### 3. Start Application
```bash
docker-compose up --build
```
Navigate to `http://localhost:8000` to interact with the frontend. Ensure LM Studio server is running if `LLM_PROVIDER=local` or `auto` is failing back.

## API Reference

### Health Check
```bash
curl http://localhost:8000/api/v1/health
```

### Document Generation
```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{
    "job_description": "We are seeking a Senior Data Engineer...",
    "master_resume": "Jane Doe. 10 years experience building scalable pipelines..."
  }'
```
Returns a fully sanitized `text/html` document tailored for exactly the 79 dynamic placements.
