[CmdletBinding()]
param(
    [string]$Port = "55432",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"
$projectName = "x9-replychat-test"
$composeFile = "compose.postgres-test.yaml"
$previousAdminUrl = $env:POSTGRES_TEST_ADMIN_URL
$hadPreviousAdminUrl = Test-Path Env:POSTGRES_TEST_ADMIN_URL
$previousTestPort = $env:POSTGRES_TEST_PORT
$hadPreviousTestPort = Test-Path Env:POSTGRES_TEST_PORT
$exitCode = 1

try {
    $env:POSTGRES_TEST_PORT = $Port
    docker compose --project-name $projectName --file $composeFile up --detach --wait
    $env:POSTGRES_TEST_ADMIN_URL = "postgresql+psycopg://x9_test:x9_test_only@127.0.0.1:$Port/postgres"
    python scripts/run_postgres_tests.py @PytestArgs
    $exitCode = $LASTEXITCODE
}
finally {
    if ($hadPreviousAdminUrl) {
        $env:POSTGRES_TEST_ADMIN_URL = $previousAdminUrl
    }
    else {
        Remove-Item Env:POSTGRES_TEST_ADMIN_URL -ErrorAction SilentlyContinue
    }
    if ($hadPreviousTestPort) {
        $env:POSTGRES_TEST_PORT = $previousTestPort
    }
    else {
        Remove-Item Env:POSTGRES_TEST_PORT -ErrorAction SilentlyContinue
    }
    docker compose --project-name $projectName --file $composeFile down --volumes --remove-orphans
}

exit $exitCode
