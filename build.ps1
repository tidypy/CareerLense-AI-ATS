Write-Host "Building Flutter Web Client..."
Set-Location -Path frontend
flutter build web --release

Write-Host "Clearing backend static directory..."
Set-Location -Path ..
if (Test-Path "backend/static") {
    Remove-Item -Recurse -Force "backend/static\*"
} else {
    New-Item -ItemType Directory -Force -Path "backend/static" | Out-Null
}

Write-Host "Copying build to backend static folder..."
Copy-Item -Path "frontend/build/web\*" -Destination "backend/static\" -Recurse -Force

Write-Host "Build and script completion successful!"
