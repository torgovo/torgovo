# Torgovo Platform - Quick Verification Script
# Run this to verify all services are working correctly

Write-Host "`n╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   TORGOVO PLATFORM - STATUS CHECK      ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝`n" -ForegroundColor Cyan

# Check Docker services
Write-Host "1. Checking Docker Services..." -ForegroundColor Yellow
docker-compose ps --format "table {{.Name}}\t{{.Status}}"

Write-Host "`n2. Checking Django System..." -ForegroundColor Yellow
docker-compose exec -T web python manage.py check

Write-Host "`n3. Testing Admin Panel..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/admin/" -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ Admin panel accessible at http://localhost:8000/admin/" -ForegroundColor Green
    }
} catch {
    Write-Host "   ❌ Admin panel not accessible: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n4. Checking Celery Worker..." -ForegroundColor Yellow
$celeryWorker = docker-compose logs --tail=5 celery-worker 2>&1 | Select-String "ready"
if ($celeryWorker) {
    Write-Host "   ✅ Celery worker is ready" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Check celery worker logs: docker-compose logs celery-worker" -ForegroundColor Yellow
}

Write-Host "`n5. Checking Celery Beat..." -ForegroundColor Yellow
$celeryBeat = docker-compose logs --tail=5 celery-beat 2>&1 | Select-String "beat: Starting"
if ($celeryBeat) {
    Write-Host "   ✅ Celery beat is running" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Check celery beat logs: docker-compose logs celery-beat" -ForegroundColor Yellow
}

Write-Host "`n╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║            ADMIN CREDENTIALS            ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host "URL:      http://localhost:8000/admin/" -ForegroundColor White
Write-Host "Username: admin" -ForegroundColor White
Write-Host "Password: admin123" -ForegroundColor Red
Write-Host "`n⚠️  IMPORTANT: Change the admin password immediately!" -ForegroundColor Red

Write-Host "`n╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║           USEFUL COMMANDS               ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host "View logs:           docker-compose logs -f [service]" -ForegroundColor Gray
Write-Host "Restart service:     docker-compose restart [service]" -ForegroundColor Gray
Write-Host "Stop all:            docker-compose down" -ForegroundColor Gray
Write-Host "Start all:           docker-compose up -d" -ForegroundColor Gray
Write-Host "Create superuser:    docker-compose exec web python manage.py createsuperuser" -ForegroundColor Gray
Write-Host ""
