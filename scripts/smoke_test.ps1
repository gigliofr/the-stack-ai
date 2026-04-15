param(
    [string]$BaseUrl = "http://127.0.0.1:18000"
)

$ErrorActionPreference = "Stop"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw "[FAIL] $Message"
    }

    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Invoke-JsonPost {
    param(
        [string]$Uri,
        [hashtable]$Body
    )

    return Invoke-RestMethod -Method Post -Uri $Uri -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 10)
}

Write-Host "Running smoke test against $BaseUrl" -ForegroundColor Cyan

$health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health"
Assert-True ($health.status -eq "ok") "Health endpoint returns status=ok"

$query = Invoke-JsonPost -Uri "$BaseUrl/query" -Body @{
    query = "Che cos'e Bloomburrow?"
    top_k = 3
    only_cards = $false
    only_rules = $false
    show_source_text = $true
}
Assert-True (($query.results | Measure-Object).Count -gt 0) "Query endpoint returns at least one result"

$validate = Invoke-JsonPost -Uri "$BaseUrl/validate-deck" -Body @{
    format = "modern"
    deck = @(
        @{ name = "Llanowar Elves"; count = 4 },
        @{ name = "Cultivate"; count = 4 },
        @{ name = "Lightning Bolt"; count = 4 }
    )
    dataset_path = "data/cards_light_en_it.jsonl"
}
Assert-True ($validate.valid -eq $false) "Validate-deck correctly flags undersized deck"
Assert-True (($validate.errors | Measure-Object).Count -gt 0) "Validate-deck returns at least one error"

$synergy = Invoke-JsonPost -Uri "$BaseUrl/suggest-synergies" -Body @{
    format = "modern"
    seed_cards = @("Llanowar Elves", "Cultivate")
    top_k = 3
    dataset_path = "data/cards_light_en_it.jsonl"
}
Assert-True (($synergy.results | Measure-Object).Count -ge 1) "Suggest-synergies returns at least one card"

$build = Invoke-JsonPost -Uri "$BaseUrl/build-deck" -Body @{
    format = "modern"
    seed_cards = @("Llanowar Elves", "Cultivate")
    target_size = 60
    dataset_path = "data/cards_light_en_it.jsonl"
}
Assert-True (($build.deck | Measure-Object).Count -gt 0) "Build-deck returns a non-empty deck"
Assert-True ($build.validation.valid -eq $true) "Build-deck output validates successfully"

Write-Host "Smoke test completed successfully." -ForegroundColor Green
