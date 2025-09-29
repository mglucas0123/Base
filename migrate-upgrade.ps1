$env:PYTHONPATH = "."
$env:FLASK_APP = "main:create_app"

if (-Not (Test-Path -Path "migrations")) {
	Write-Host "Inicializando diretório de migrações..."
	.\venv\Scripts\flask db init
}

.\venv\Scripts\flask migrate-upgrade