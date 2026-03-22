#!/bin/bash
set -e

echo "Building Flutter Web Client..."
cd frontend
flutter build web --release

echo "Clearing backend static directory..."
cd ..
rm -rf backend/static/*
mkdir -p backend/static

echo "Copying build to backend static folder..."
cp -r frontend/build/web/* backend/static/

echo "Build and copy successful!"
