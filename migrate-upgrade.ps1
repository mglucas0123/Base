$env:PYTHONPATH = "."
$env:FLASK_APP = "main:create_app"

if (-Not (Test-Path -Path "migrations")) {
	Write-Host "Inicializando diretório de migrações..."
	flask db init
}

flask migrate-upgrade