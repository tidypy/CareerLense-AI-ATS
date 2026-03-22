# Stage 1: Build the Flutter Frontend
FROM ghcr.io/cirruslabs/flutter:stable AS frontend-build

WORKDIR /app
COPY frontend/ /app/frontend/
WORKDIR /app/frontend

# Fetch dependencies and build the web artefact
RUN flutter pub get
RUN flutter build web --release

# Stage 2: Create the Python Backend Image
FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ /app/backend/

# Copy the generated models and root level assets needed for runtime
COPY generate_models.py /app/
COPY Template4.html /app/
COPY MasterDataMDfileVER-4.md /app/

# Copy the built Flutter app from the first stage into the backend static folder
COPY --from=frontend-build /app/frontend/build/web/ /app/backend/static/

# Generate the pydantic model during the build
RUN python generate_models.py

EXPOSE 8000

# Using python -m uvicorn allows import from backend.main
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
