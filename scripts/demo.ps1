param([string]$Api = "http://localhost:8000/api")
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
function Invoke-Api($Method, $Path, $Token, $Payload) {
    $args = @{Method=$Method; Uri="$Api$Path"}
    if ($Token) { $args.Headers = @{Authorization="Bearer $Token"} }
    if ($null -ne $Payload) {
        $args.ContentType = "application/json; charset=utf-8"
        $args.Body = [System.Text.Encoding]::UTF8.GetBytes(($Payload | ConvertTo-Json -Depth 12))
    }
    Invoke-RestMethod @args
}
function Login($Role) {
    $password = (Get-Culture).TextInfo.ToTitleCase($Role) + "123!"
    (Invoke-Api POST "/auth/login" $null @{email="$Role@example.local";password=$password}).access_token
}
$admin = Login "admin"
$teacher = Login "teacher"
$student = Login "student"
foreach ($token in @($admin,$teacher,$student)) {
    $user = Invoke-Api GET "/auth/me" $token $null
    Write-Output ("Вход подтверждён: " + $user.role)
}
$draft = Invoke-Api POST "/scenarios/generate" $teacher @{category="ДТП"}
$title = "Демонстрация " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
$scenario = Invoke-Api POST "/scenarios" $teacher @{
    code=("DEMO-RUN-"+[guid]::NewGuid()); title=$title; category="ДТП"
    incident_payload=$draft.incident_payload
    expected_state=@{status="ПРИНЯТО";services=@("ДДС")};published=$false
}
$null = Invoke-Api POST "/scenarios/$($scenario.id)/publish" $teacher $null
$session = Invoke-Api POST "/sessions" $teacher @{title=$title;scenario_ids=@($scenario.id)}
$null = Invoke-Api POST "/sessions/$($session.id)/start" $teacher $null
Write-Output "Сценарий опубликован, занятие запущено."
$call = Invoke-Api POST "/sessions/$($session.id)/calls/start" $student $null
$steps = @(
    @{action_type="SELECT_INCIDENT";payload=@{category="ДТП"}},
    @{action_type="SELECT_STATUS";payload=@{status="ПРИНЯТО"}},
    @{action_type="SELECT_SERVICES";payload=@{services=@("ДДС")}},
    @{action_type="SELECT_TAGS";payload=@{tags=@($draft.incident_payload.tags)}},
    @{action_type="TEXT_INPUT";payload=@{text="Сообщение принято, информация зафиксирована."}}
)
foreach ($step in $steps) { $null=Invoke-Api POST "/sessions/calls/$($call.call_id)/actions" $student $step }
$result = Invoke-Api POST "/sessions/calls/$($call.call_id)/complete" $student $null
if ($result.score -ne 7 -or $result.max_score -ne 7) { throw "Неожиданная оценка" }
Write-Output ("Карточка завершена: " + $result.score + "/" + $result.max_score + ", время " + $result.duration_sec + " сек.")
$reports = Invoke-Api GET "/reports/assessments" $teacher $null
$report = $reports | Where-Object { $_.call_session_id -eq $call.call_id } | Select-Object -First 1
$output = Join-Path $PSScriptRoot "../docs/demo-output"
$null = New-Item -ItemType Directory -Force -Path $output
foreach ($format in @("csv","pdf")) {
    Invoke-WebRequest -UseBasicParsing -Uri "$Api/reports/assessment/$($report.id).$format" -Headers @{Authorization="Bearer $teacher"} -OutFile (Join-Path $output "assessment.$format")
}
$null = Invoke-Api POST "/sessions/$($session.id)/finish" $teacher $null
Write-Output "Отчёты сохранены в docs/demo-output; занятие завершено."
