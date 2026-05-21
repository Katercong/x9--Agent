<#
  test_api_local.ps1  —  X9 Desktop backend (:8000) API connectivity harness.

  Audits every /api/local/* + app-level + /api/v1/* (proxied to core) endpoint
  that powers https://usx9.us/portal/dashboard. Auth-aware (logs in, reuses the
  x9_session cookie). Read paths are called for real; mutating paths are either
  exercised reversibly (create->delete, claim->release) or probed with a
  non-existent id / invalid body so the route + auth are proven WITHOUT changing
  real data.

  GUARDRAILS — these are never invoked, only recorded as SKIPPED:
    POST /api/local/app/restart            (kills the server)
    POST /api/local/db/migrate             (schema mutation on a live DB)
    POST /api/local/process/*              (heavy full-dataset re-scoring)
    POST /api/local/outreach/send/{id}     (sends a real Gmail)
    POST /api/local/outreach/gmail/disconnect (breaks the live Gmail link)
    POST /api/local/auth/logout            (would drop our own session)

  Usage:
    .\test_api_local.ps1
    .\test_api_local.ps1 -BaseUrl https://usx9.us -User superadmin -Pass 'X9@2026'
    .\test_api_local.ps1 -OutFile F:\X9_AI_system\docs\api_health_2026-05-18.md
#>
param(
  [string]$BaseUrl = "https://usx9.us",
  [string]$User    = "superadmin",
  [string]$Pass    = "X9@2026",
  [string]$OutFile = ""
)

$ErrorActionPreference = "SilentlyContinue"
$ProgressPreference   = "SilentlyContinue"
$results = New-Object System.Collections.ArrayList

function Rec($group, $method, $path, $status, $ms, $cls, $note) {
  [void]$results.Add([pscustomobject]@{
    Group = $group; Method = $method; Path = $path
    Status = $status; Ms = $ms; Class = $cls; Note = $note
  })
}

function Call($method, $path, $session, $body, $ctype) {
  $url = $BaseUrl + $path
  $sw  = [System.Diagnostics.Stopwatch]::StartNew()
  try {
    $p = @{ Uri = $url; Method = $method; UseBasicParsing = $true; TimeoutSec = 25; MaximumRedirection = 0 }
    if ($session) { $p.WebSession = $session }
    if ($null -ne $body) { $p.Body = $body; $p.ContentType = $ctype }
    $r = Invoke-WebRequest @p
    $sw.Stop()
    return @{ code = [int]$r.StatusCode; ms = $sw.ElapsedMilliseconds; body = [string]$r.Content }
  } catch {
    $sw.Stop()
    $resp = $_.Exception.Response
    if ($resp) { return @{ code = [int]$resp.StatusCode; ms = $sw.ElapsedMilliseconds; body = "" } }
    return @{ code = -1; ms = $sw.ElapsedMilliseconds; body = [string]$_.Exception.Message }
  }
}

# Classify a read/GET (authenticated) result.
function ClsGet($code) {
  if ($code -ge 200 -and $code -lt 300) { return "PASS" }
  if ($code -eq 304) { return "PASS" }
  if ($code -eq 401 -or $code -eq 403) { return "FAIL-AUTH" }   # we are super_admin: should not happen
  if ($code -eq 404) { return "WARN-404" }
  if ($code -eq 503) { return "FAIL-PROXY" }
  if ($code -ge 500) { return "FAIL-5XX" }
  if ($code -eq -1)  { return "FAIL-CONN" }
  return "WARN"
}
# Classify a non-destructive probe of a mutating route (fake id / bad body).
# A 4xx here means the route exists and validation/auth ran => alive.
function ClsProbe($code) {
  if ($code -ge 200 -and $code -lt 300) { return "PASS" }
  if ($code -eq 400 -or $code -eq 404 -or $code -eq 409 -or $code -eq 422) { return "PASS-ALIVE" }
  if ($code -eq 401 -or $code -eq 403) { return "FAIL-AUTH" }
  if ($code -eq 503) { return "FAIL-PROXY" }
  if ($code -ge 500) { return "FAIL-5XX" }
  if ($code -eq -1)  { return "FAIL-CONN" }
  return "WARN"
}

Write-Host "X9 API harness -> $BaseUrl" -ForegroundColor Cyan

# ---------- 1. health (public) ----------
$h = Call GET "/health" $null $null $null
Rec "app" "GET" "/health" $h.code $h.ms (ClsGet $h.code) "public"

# ---------- 2. login ----------
$loginBody = @{ username = $User; password = $Pass } | ConvertTo-Json
$sw = [System.Diagnostics.Stopwatch]::StartNew()
try {
  $lr = Invoke-WebRequest -Uri "$BaseUrl/api/local/auth/login" -Method POST -Body $loginBody `
        -ContentType "application/json" -SessionVariable S -UseBasicParsing -TimeoutSec 15
  $sw.Stop()
  Rec "auth" "POST" "/api/local/auth/login" ([int]$lr.StatusCode) $sw.ElapsedMilliseconds "PASS" "session established as $User"
} catch {
  $sw.Stop()
  $code = -1; if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
  Rec "auth" "POST" "/api/local/auth/login" $code $sw.ElapsedMilliseconds "FAIL-AUTH" "login failed; aborting authed tests"
  Write-Host "LOGIN FAILED ($code) - cannot continue authed tests" -ForegroundColor Red
}

# ---------- 3. harvest ids for parameterized routes ----------
$creatorId = $null; $draftId = $null
if ($S) {
  $cr = Call GET "/api/local/creators?limit=5" $S $null $null
  if ($cr.code -eq 200) {
    try {
      $j = $cr.body | ConvertFrom-Json
      $arr = $null
      if ($j -is [array]) { $arr = $j } elseif ($j.items) { $arr = $j.items } elseif ($j.data) { $arr = $j.data }
      if ($arr -and $arr.Count -gt 0) {
        $creatorId = $arr[0].id
        if (-not $creatorId) { $creatorId = $arr[0].creator_id }
      }
    } catch {}
  }
  $dr = Call GET "/api/local/outreach/drafts" $S $null $null
  if ($dr.code -eq 200) {
    try {
      $j = $dr.body | ConvertFrom-Json
      $arr = $null
      if ($j.items) { $arr = $j.items } elseif ($j -is [array]) { $arr = $j }
      if ($arr -and $arr.Count -gt 0) { $draftId = $arr[0].id }
    } catch {}
  }
}
$cidPath = "__no_creator__"; if ($creatorId) { $cidPath = "$creatorId" }
Write-Host "harvested creatorId=$creatorId draftId=$draftId" -ForegroundColor DarkGray

# ---------- 4. authenticated GET endpoints ----------
$gets = @(
  @("app","/api/local/app/status"),
  @("admin","/api/local/admin/overview"),
  @("admin","/api/local/admin/departments"),
  @("admin","/api/local/admin/business-dashboard"),
  @("admin","/api/local/admin/system-settings"),
  @("admin","/api/local/admin/trends"),
  @("admin","/api/local/admin/extensions"),
  @("auth","/api/local/auth/me"),
  @("auth","/api/local/auth/users"),
  @("db","/api/local/db/status"),
  @("db","/api/local/db/stats"),
  @("extension","/api/local/extension/download"),
  @("extension","/api/local/extension/status"),
  @("extension","/api/local/extension/commands/pending"),
  @("extension","/api/local/extension/commands"),
  @("extension","/api/local/extension/run-progress"),
  @("collector","/api/local/collector/recent-observations"),
  @("collector","/api/local/collector/source-stats"),
  @("collector","/api/local/collector/observations-feed"),
  @("creators","/api/local/creators?limit=5"),
  @("creators","/api/local/creators/recommended"),
  @("creators","/api/local/creators/by-tag/all"),
  @("creators","/api/local/creators/by-queue/default"),
  @("creators","/api/local/creators/by-product/all"),
  @("creators","/api/local/creators/by-collab/all"),
  @("review","/api/local/review-tasks"),
  @("export","/api/local/export/recommended-creators.csv"),
  @("import","/api/local/import/creators/template.csv"),
  @("outreach","/api/local/outreach/templates"),
  @("outreach","/api/local/outreach/drafts"),
  @("outreach","/api/local/outreach/gmail/status"),
  @("outreach","/api/local/outreach/gmail/client-info"),
  @("outreach","/api/local/outreach/gmail/accounts"),
  @("outreach","/api/local/outreach/gmail/auth-url"),
  @("shared","/api/local/shared/keywords/dashboard"),
  @("shared","/api/local/shared/assistant/info")
)
foreach ($g in $gets) {
  $r = Call GET $g[1] $S $null $null
  Rec $g[0] "GET" $g[1] $r.code $r.ms (ClsGet $r.code) ""
}
# parameterized GETs with harvested ids
if ($creatorId) {
  $r = Call GET "/api/local/creators/$cidPath" $S $null $null
  Rec "creators" "GET" "/api/local/creators/{id}" $r.code $r.ms (ClsGet $r.code) "id=$creatorId"
  $r = Call GET "/api/local/outreach/history/$cidPath" $S $null $null
  Rec "outreach" "GET" "/api/local/outreach/history/{creator_id}" $r.code $r.ms (ClsGet $r.code) "id=$creatorId"
} else {
  Rec "creators" "GET" "/api/local/creators/{id}" "-" 0 "SKIP" "no creator id harvested"
  Rec "outreach" "GET" "/api/local/outreach/history/{creator_id}" "-" 0 "SKIP" "no creator id harvested"
}
# generic data resources (read-only router)
foreach ($res in @("creators","outreach","products","staff","departments","system_logs","business_metrics_daily")) {
  $r = Call GET "/api/local/data/$res?limit=1" $S $null $null
  Rec "data" "GET" "/api/local/data/$res" $r.code $r.ms (ClsGet $r.code) "limit=1"
}

# ---------- 5. /api/v1/* proxy -> core :18765 (part of live portal path) ----------
foreach ($v in @("/api/v1/","/api/v1/version","/api/v1/resources","/api/v1/queries",
                  "/api/v1/data/creators?limit=1","/api/v1/data/products?limit=1",
                  "/api/v1/llm/providers","/api/v1/llm/active")) {
  $r = Call GET $v $S $null $null
  Rec "proxy-v1" "GET" $v $r.code $r.ms (ClsGet $r.code) "desktop -> core proxy"
}

# ---------- 6. reversible writes ----------
# 6a. outreach template create -> delete
$tplBody = @{ name = "x9_audit_tmp"; subject = "audit"; body = "audit body {{handle}}"; channel = "email"; language = "en" } | ConvertTo-Json
$ct = Call POST "/api/local/outreach/templates" $S $tplBody "application/json"
$tplId = $null
if ($ct.code -ge 200 -and $ct.code -lt 300) {
  try { $tplId = ($ct.body | ConvertFrom-Json).id } catch {}
  if (-not $tplId) { try { $tplId = ($ct.body | ConvertFrom-Json).item.id } catch {} }
}
Rec "outreach" "POST" "/api/local/outreach/templates" $ct.code $ct.ms (ClsProbe $ct.code) "create disposable template"
if ($tplId) {
  $pt = Call PATCH "/api/local/outreach/templates/$tplId" $S (@{ subject = "audit2" } | ConvertTo-Json) "application/json"
  Rec "outreach" "PATCH" "/api/local/outreach/templates/{id}" $pt.code $pt.ms (ClsProbe $pt.code) "id=$tplId"
  $dt = Call DELETE "/api/local/outreach/templates/$tplId" $S $null $null
  Rec "outreach" "DELETE" "/api/local/outreach/templates/{id}" $dt.code $dt.ms (ClsProbe $dt.code) "cleanup id=$tplId"
} else {
  Rec "outreach" "PATCH" "/api/local/outreach/templates/{id}" "-" 0 "SKIP" "no template id (create did not return id)"
  Rec "outreach" "DELETE" "/api/local/outreach/templates/{id}" "-" 0 "SKIP" "no template id"
}
# 6b. creator claim -> release (reversible) on a harvested creator
if ($creatorId) {
  $cl = Call POST "/api/local/creators/$cidPath/claim" $S "{}" "application/json"
  Rec "creators" "POST" "/api/local/creators/{id}/claim" $cl.code $cl.ms (ClsProbe $cl.code) "id=$creatorId"
  $rl = Call POST "/api/local/creators/$cidPath/release" $S "{}" "application/json"
  Rec "creators" "POST" "/api/local/creators/{id}/release" $rl.code $rl.ms (ClsProbe $rl.code) "revert claim id=$creatorId"
} else {
  Rec "creators" "POST" "/api/local/creators/{id}/claim" "-" 0 "SKIP" "no creator id"
  Rec "creators" "POST" "/api/local/creators/{id}/release" "-" 0 "SKIP" "no creator id"
}

# ---------- 7. non-destructive probes of mutating routes (fake id / bad body) ----------
$FAKE = "x9_no_such_id_zzz"
$probes = @(
  @("auth","POST","/api/local/auth/register",        (@{ username="x"; password="x" } | ConvertTo-Json)),
  @("auth","POST","/api/local/auth/change-password", (@{ old_password="__wrong__"; new_password="abcdef" } | ConvertTo-Json)),
  @("auth","POST","/api/local/auth/users",           (@{ username="" } | ConvertTo-Json)),
  @("auth","PATCH","/api/local/auth/users/$FAKE",    (@{ role="department_user" } | ConvertTo-Json)),
  @("auth","POST","/api/local/auth/users/$FAKE/approve", "{}"),
  @("auth","POST","/api/local/auth/users/$FAKE/reject",  "{}"),
  @("auth","POST","/api/local/auth/users/$FAKE/reset-password", (@{ new_password="abcdef" } | ConvertTo-Json)),
  @("creators","PATCH","/api/local/creators/$FAKE/assignment", (@{ owner="x" } | ConvertTo-Json)),
  @("review","PATCH","/api/local/review-tasks/$FAKE", (@{ status="approved" } | ConvertTo-Json)),
  @("outreach","POST","/api/local/outreach/preview/$FAKE", "{}"),
  @("outreach","POST","/api/local/outreach/draft", (@{ creator_id=$FAKE } | ConvertTo-Json)),
  @("outreach","PATCH","/api/local/outreach/draft/$FAKE", (@{ body="x" } | ConvertTo-Json)),
  @("outreach","DELETE","/api/local/outreach/draft/$FAKE", $null),
  @("outreach","POST","/api/local/outreach/drafts/$FAKE/rollback", "{}"),
  @("outreach","DELETE","/api/local/outreach/gmail/accounts/$FAKE", $null),
  @("outreach","POST","/api/local/outreach/gmail/accounts/$FAKE/default", "{}"),
  @("outreach","POST","/api/local/outreach/gmail/exchange", (@{ code="__bad__" } | ConvertTo-Json)),
  @("import","POST","/api/local/import/creators/table", (@{ rows=@() } | ConvertTo-Json)),
  @("shared","POST","/api/local/shared/assistant/chat", (@{ message="" } | ConvertTo-Json))
)
foreach ($pr in $probes) {
  $ctype = "application/json"; if ($null -eq $pr[3]) { $ctype = $null }
  $r = Call $pr[1] $pr[2] $S $pr[3] $ctype
  Rec $pr[0] $pr[1] $pr[2] $r.code $r.ms (ClsProbe $r.code) "non-destructive probe (fake id / bad body)"
}

# ---------- 8. public (unauthenticated) endpoints + auth-gate spot check ----------
$pub = @(
  @("extension","POST","/api/local/extension/heartbeat", "{}"),
  @("extension","POST","/api/local/extension/launcher-heartbeat", "{}"),
  @("extension","POST","/api/local/extension/run-progress", "{}"),
  @("extension","POST","/api/local/extension/x9-compat/ingest-creators", (@{ creators=@() } | ConvertTo-Json)),
  @("extension","POST","/api/local/extension/commands/$FAKE/ack", "{}"),
  @("collector","POST","/api/local/collector/observations", (@{ } | ConvertTo-Json)),
  @("extension","GET","/api/local/extension/commands/pending", $null)
)
foreach ($pp in $pub) {
  $ctype = "application/json"; if ($null -eq $pp[3]) { $ctype = $null }
  $r = Call $pp[1] $pp[2] $null $pp[3] $ctype   # NO session on purpose
  $cls = ClsProbe $r.code
  if ($r.code -eq 401) { $cls = "FAIL-GATE(should be public)" }
  Rec ($pp[0]+"/PUBLIC") $pp[1] $pp[2] $r.code $r.ms $cls "no-session: confirms PUBLIC allowlist"
}
# auth-gate must REJECT these without a session
foreach ($ng in @("/api/local/db/stats","/api/local/admin/overview","/api/v1/data/creators")) {
  $r = Call GET $ng $null $null $null
  $cls = "PASS"; if ($r.code -ne 401) { $cls = "FAIL-GATE(should be 401)" }
  Rec "auth-gate" "GET" $ng $r.code $r.ms $cls "no-session: must be 401"
}

# ---------- 9. app-level / SPA routes ----------
$app = @(
  @("GET","/portal/"),@("GET","/portal/dashboard"),@("GET","/login"),
  @("GET","/landing"),@("GET","/ui/app.js"),@("GET","/favicon.svg"),
  @("GET","/workspace/cross-border/"),@("GET","/")
)
foreach ($a in $app) {
  $r = Call $a[0] $a[1] $S $null $null
  $cls = "PASS"
  if ($r.code -ge 500 -or $r.code -eq -1) { $cls = "FAIL" }
  elseif ($r.code -ge 300 -and $r.code -lt 400) { $cls = "PASS-REDIRECT($($r.code))" }
  elseif ($r.code -ge 400) { $cls = "WARN-$($r.code)" }
  Rec "spa" $a[0] $a[1] $r.code $r.ms $cls ""
}

# ---------- 10. guardrail endpoints — recorded, never called ----------
foreach ($sk in @(
  @("app","POST","/api/local/app/restart","kills server"),
  @("db","POST","/api/local/db/migrate","schema mutation on live DB"),
  @("process","POST","/api/local/process/score-creators","heavy full-dataset rescore"),
  @("process","POST","/api/local/process/tag-creators","heavy full-dataset retag"),
  @("process","POST","/api/local/process/recommend-creators","heavy recompute"),
  @("process","POST","/api/local/process/run-full-pipeline","heavy: all of the above"),
  @("outreach","POST","/api/local/outreach/send/{draft_id}","sends a real Gmail"),
  @("outreach","POST","/api/local/outreach/gmail/disconnect","breaks live Gmail link"),
  @("auth","POST","/api/local/auth/logout","would drop our own session"))) {
  Rec $sk[0] $sk[1] $sk[2] "-" 0 "SKIPPED-GUARDRAIL" $sk[3]
}

# ---------- 11. report ----------
$total = $results.Count
$fails = @($results | Where-Object { $_.Class -match '^FAIL' })
$warns = @($results | Where-Object { $_.Class -match '^WARN' })
$passed = @($results | Where-Object { $_.Class -match '^PASS' })
$skip  = @($results | Where-Object { $_.Class -match '^SKIP' })

$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("# X9 Desktop API connectivity report")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("- Base: ``$BaseUrl``  | user: ``$User``  | $(Get-Date -Format s)")
[void]$sb.AppendLine("- Total checks: $total | PASS: $($passed.Count) | FAIL: $($fails.Count) | WARN: $($warns.Count) | SKIPPED: $($skip.Count)")
[void]$sb.AppendLine("")
if ($fails.Count -gt 0) {
  [void]$sb.AppendLine("## FAIL")
  [void]$sb.AppendLine("")
  [void]$sb.AppendLine("| Group | Method | Path | Status | ms | Note |")
  [void]$sb.AppendLine("|---|---|---|---|---|---|")
  foreach ($x in $fails) { [void]$sb.AppendLine("| $($x.Group) | $($x.Method) | $($x.Path) | **$($x.Status) $($x.Class)** | $($x.Ms) | $($x.Note) |") }
  [void]$sb.AppendLine("")
}
[void]$sb.AppendLine("## All checks")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("| Group | Method | Path | Status | ms | Class | Note |")
[void]$sb.AppendLine("|---|---|---|---|---|---|---|")
foreach ($x in $results) { [void]$sb.AppendLine("| $($x.Group) | $($x.Method) | $($x.Path) | $($x.Status) | $($x.Ms) | $($x.Class) | $($x.Note) |") }
$md = $sb.ToString()

if ($OutFile) { $md | Out-File -FilePath $OutFile -Encoding utf8; Write-Host "report -> $OutFile" -ForegroundColor Green }

$results | Format-Table Group,Method,Path,Status,Ms,Class -AutoSize | Out-String -Width 200 | Write-Host
Write-Host ""
Write-Host "TOTAL $total | PASS $($passed.Count) | FAIL $($fails.Count) | WARN $($warns.Count) | SKIPPED $($skip.Count)" -ForegroundColor Cyan
if ($fails.Count -gt 0) {
  Write-Host "FAILURES:" -ForegroundColor Red
  foreach ($x in $fails) { Write-Host ("  {0,-6} {1,-48} {2} {3}" -f $x.Method,$x.Path,$x.Status,$x.Class) -ForegroundColor Red }
}
