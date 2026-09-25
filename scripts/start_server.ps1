$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Project virtual environment not found at $python"
}

Push-Location $projectRoot
try {
    $engine = (& $python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])" | Select-Object -Last 1).Trim()
    if ($engine -ne "django.db.backends.postgresql") {
        throw "Refusing to start: Django is not configured for PostgreSQL. Check .env."
    }

    & $python manage.py migrate
    & $python manage.py runserver 127.0.0.1:8000
}
finally {
    Pop-Location
}
