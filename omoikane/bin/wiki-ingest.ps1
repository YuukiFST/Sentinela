<#
.SYNOPSIS
Ingest every file in omoikane/raw/inbox through the agent, one headless call per file.

Plain sources go through /ingest; captured coding sessions under raw/inbox/sessions go through /distill.
A session file modified less than -QuietMinutes ago may still be growing (Stop fires on every turn), so it waits.
After -SynthesizeEvery distills since the last cross-session pass, /synthesize runs once; 0 turns it off.
-Commit goes through the review gate (review-gate.py, #45): the run happens in a worktree on wiki/auto beside the
repository, one commit per operation, and the branch is pushed as a PR to main. The human's checkout is not touched.

.EXAMPLE
omoikane/bin/wiki-ingest.ps1                      # Claude Code, changes left in the working tree
omoikane/bin/wiki-ingest.ps1 -Agent opencode      # OpenCode
omoikane/bin/wiki-ingest.ps1 -Commit              # through the review gate: commits on wiki/auto, one PR
omoikane/bin/wiki-ingest.ps1 -Commit -NoGate      # commits on the checked-out branch (what the gate runs inside)
#>
param(
    [ValidateSet("claude", "opencode")] [string] $Agent = "claude",
    [switch] $Commit,
    [switch] $NoGate,
    [int] $QuietMinutes = 30,
    [int] $SynthesizeEvery = 5
)
$ErrorActionPreference = "Stop"
$omoikane = Split-Path -Parent $PSScriptRoot
$root = Split-Path -Parent $omoikane
Set-Location $root
$log = Join-Path $omoikane ".wiki-ingest.log"
# Left by a run that changed files outside its scope; every later run refuses until the human has looked.
$blocked = Join-Path $omoikane ".wiki-ingest.blocked"
# The agent runs started here maintain the wiki; the session hooks must neither capture nor inject context for them.
$env:OMOIKANE_NO_CAPTURE = "1"
# The scope check watches ignored files too; a __pycache__ written by lint between two agent calls would read as
# the agent's change.
$env:PYTHONDONTWRITEBYTECODE = "1"
# Lint findings handed back to the agent before the operation is committed as it stands.
$LintRounds = 2
# What -Commit commits for an operation, besides the source it moved.
$WikiPaths = @("omoikane/wiki", "omoikane/log.md", "omoikane/_review.md", "omoikane/index.md")

function Log([string] $msg) { "$(Get-Date -Format s) $msg" | Tee-Object -FilePath $log -Append }

function Stop-Run([string] $reason) {
    Set-Content -Path $blocked -Encoding utf8NoBOM -Value "$(Get-Date -Format s) $reason"
    Log "BLOCKED: $reason. Read the working tree, then delete $blocked to resume."
    throw $reason
}

if (Test-Path $blocked) { Log "blocked since $(Get-Content -Raw $blocked)"; exit 1 }

if ($Commit -and -not $NoGate) {
    # By path: review-gate.py starts gh as a process, which on Windows finds gh.exe only. Looked up first, so a
    # missing gh reaches the log (a scheduled run's stderr reaches nobody) before anything moves.
    $gh = Get-Command gh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $gh) { Log "review gate: gh not found on PATH; install it and run gh auth login"; exit 1 }
    # Named here and passed to both steps, not read back from Python's stdout across code pages.
    $worktree = Join-Path (Split-Path -Parent $root) ((Split-Path -Leaf $root) + "-wiki-auto")
    python omoikane/bin/review-gate.py prepare --worktree $worktree --quiet-minutes $QuietMinutes 2>&1 |
        ForEach-Object { Log "$_" } | Out-Host
    if ($LASTEXITCODE -ne 0) { Log "review gate: prepare failed; nothing ran"; exit 1 }
    # The worktree's own copy runs, at the version just merged from main; its log and block marker live there.
    & pwsh -NoProfile -File (Join-Path $worktree "omoikane/bin/wiki-ingest.ps1") -Agent $Agent -Commit -NoGate `
        -QuietMinutes $QuietMinutes -SynthesizeEvery $SynthesizeEvery | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Log "review gate: the run in $worktree failed; nothing published. See its omoikane/.wiki-ingest.log"
        exit 1
    }
    python omoikane/bin/review-gate.py publish --worktree $worktree --gh $gh.Source 2>&1 | ForEach-Object { Log "$_" } | Out-Host
    if ($LASTEXITCODE -ne 0) { Log "review gate: publish failed"; exit 1 }
    exit 0
}

# The scope check runs from a private copy with `python -I`: the agent writes into this repository, and nothing
# it writes may sit on the checker's path. Per-run temp files: two runs or two repositories must not share them.
$runTmp = New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) ("omoikane-" + [guid]::NewGuid().ToString("N")))
$scopeScript = Join-Path $runTmp "headless-scope.py"
Copy-Item omoikane/bin/headless-scope.py $scopeScript

function Invoke-Scope([string[]] $arguments) {
    $out = python -I $scopeScript --repo $root @arguments
    if ($LASTEXITCODE -ne 0) { throw "headless-scope.py $($arguments[0]) failed" }
    return $out
}

# One headless agent call; returns $true when the agent exited 0. Output goes to the host, not the pipeline,
# or it would become part of the return value. The scope (edit wiki pages, log.md and _review.md; no shell)
# comes from headless-scope.py for both harnesses, so they cannot drift (#39).
function Invoke-Agent([string] $claudePrompt, [string] $message) {
    if ($Agent -eq "claude") {
        $flags = @(Invoke-Scope @("claude") | ConvertFrom-Json)
        claude -p $claudePrompt @flags 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
        return $LASTEXITCODE -eq 0
    }
    # OPENCODE_CONFIG_CONTENT is merged over the global and project config (opencode.ai/docs/config); it defines
    # the agent that carries the scope, under a name no other config can know. The prompt goes in as the message,
    # not through --command: a command's own `agent` overrides --agent (#39). --pure keeps user plugins out.
    $agentName = "omoikane-headless-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
    $saved = $env:OPENCODE_CONFIG_CONTENT
    $env:OPENCODE_CONFIG_CONTENT = Invoke-Scope @("opencode", "--agent-name", $agentName)
    try {
        # The tools OpenCode resolves for the agent, without calling a model: a gpt- model gets apply_patch,
        # which no rule restricts (headless-scope.py unsafe_tools).
        $resolved = Join-Path $runTmp "agent.json"
        # --pure here too: a user plugin's config hook could set a model for the check that the pure run never gets.
        opencode --pure debug agent $agentName | Set-Content -Encoding utf8NoBOM $resolved
        if ($LASTEXITCODE -ne 0) { throw "opencode debug agent failed" }
        python -I $scopeScript opencode-tools --resolved $resolved 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
        if ($LASTEXITCODE -eq 3) { throw "OpenCode offers the agent a tool outside the scope; pin a model that is not gpt-" }
        if ($LASTEXITCODE -ne 0) { throw "headless-scope.py opencode-tools could not read the resolved agent" }
        opencode run --pure --agent $agentName $message 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
    }
    finally { $env:OPENCODE_CONFIG_CONTENT = $saved }
    return $LASTEXITCODE -eq 0
}

# After every agent call: compare the tree with the snapshot, then undo the ticks the agent added (ticking is
# the human's approval). The harness's permission rules have holes of their own; the tree is the ground truth.
# The isolated check comes first: review-ticks.py imports from omoikane/bin/, which must be known clean. A run
# stopped here keeps its ticks; the block makes the human read the tree anyway. Either check failing to give a
# verdict blocks too: a crash once failed open, and the next snapshot absorbed the change (#40).
function Assert-Scope([string] $op, [string] $reviewBefore, [string] $snapshot) {
    python -I $scopeScript --repo $root verify --before $snapshot 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
    if ($LASTEXITCODE -eq 3) { Stop-Run "the $op run changed files outside its scope" }
    if ($LASTEXITCODE -ne 0) { Stop-Run "headless-scope.py verify failed after the $op run" }
    # review-ticks.py also fails when the run deleted or rewrote a bullet: the next review-removals.py would record
    # it as the human's decision (#41).
    python omoikane/bin/review-ticks.py --before $reviewBefore 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Stop-Run "review-ticks.py failed after the $op run: a tick the agent added may stand, or it deleted or rewrote a bullet"
    }
}

# Whether the paths an operation commits hold changes no commit took. With -Commit, they would be swept into the
# next operation's commit under its message: a failed operation's half-written pages once were (#40).
function Test-WikiChanged {
    return [bool](git status --porcelain --untracked-files=all -- @WikiPaths)
}

function Assert-WikiCommitted([string] $what) {
    if (-not $Commit -or -not (Test-WikiChanged)) { return }
    # Logged, not only thrown: a scheduled run's stderr reaches nobody.
    $refusal = "uncommitted changes under the wiki before $what; commit or discard them"
    Log $refusal | Out-Host
    throw $refusal
}

function Invoke-Operation([string] $op, [string] $arg) {
    Assert-WikiCommitted "the $op run"
    $review = Join-Path $omoikane "_review.md"
    $reviewBefore = Join-Path $runTmp "review-before.md"
    if (Test-Path $review) { Copy-Item $review $reviewBefore -Force } else { Set-Content $reviewBefore "" }
    $snapshot = Join-Path $runTmp "scope-before.json"
    Invoke-Scope @("snapshot") | Set-Content -Encoding utf8NoBOM $snapshot
    $message = "Read ``omoikane/prompts/$op.md`` and follow it."
    if ($arg) { $message += " Argument: $arg" }
    $ok = Invoke-Agent ("/$op $arg".TrimEnd()) $message
    Assert-Scope $op $reviewBefore $snapshot
    # The agent has no shell, so it cannot run index and lint itself: run lint here and hand the findings back.
    for ($round = 1; $ok -and $round -le $LintRounds; $round++) {
        $lint = python omoikane/bin/wiki-lint.py 2>&1
        if ($LASTEXITCODE -eq 0) { break }
        # Findings only: warnings need /lint's judgement, and 25 of them once buried the one finding to fix.
        $findings = @($lint | Where-Object { $_ -notmatch "^(warning: |wiki-lint: )" })
        # Out-Host: anything this function writes to the pipeline becomes part of its return value.
        Log "$op lint round ${round}: $($findings.Count) findings handed back" | Out-Host
        $fix = "omoikane/bin/wiki-lint.py reports these findings after the /$op run. Fix each one by editing " +
            "the pages, omoikane/log.md or omoikane/_review.md. You cannot run commands; lint runs again after you.`n`n" +
            ($findings -join "`n")
        $ok = Invoke-Agent $fix $fix
        Assert-Scope $op $reviewBefore $snapshot
    }
    return $ok
}

# $moved: the source and its new place, when the operation had a source; staged by name, not as omoikane/raw,
# which would also take every capture still in the inbox.
function Complete-Operation([string] $op, [string] $name, [string[]] $moved = @()) {
    python omoikane/bin/wiki-index.py 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
    if ($LASTEXITCODE -ne 0) { Stop-Run "wiki-index.py failed after the $op run" }
    # Findings left after the lint rounds are committed as they stand; the next /lint or human sees them.
    python omoikane/bin/wiki-lint.py 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
    if (-not $Commit) { return }
    # Only what an operation may change: anything else in the tree is not the run's to commit. A source never
    # committed has no deletion to stage.
    $paths = $WikiPaths + @($moved | Where-Object { (Test-Path -LiteralPath $_) -or (git ls-files -- $_) })
    git add -- @paths 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
    if ($LASTEXITCODE -ne 0) { Stop-Run "git add failed after the $op run" }
    git diff --cached --quiet -- @paths
    if ($LASTEXITCODE -eq 0) { Log "$op $name changed nothing to commit" | Out-Host; return }
    # `-- @paths` commits those paths only: what the human staged before the run stays staged, not committed.
    git commit -q -m "feat(wiki): $op $name" -- @paths 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
    if ($LASTEXITCODE -ne 0) { Stop-Run "git commit failed after the $op run" }
}

try {
    # OpenCode writes .opencode/ (its .gitignore; plugin deps without --pure) on every start: let it do so before
    # the first snapshot, or the first run in a fresh clone reads the write as the agent's and blocks.
    if ($Agent -eq "opencode") {
        opencode --pure debug config | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "opencode debug config failed" }
    }
    # Before any operation reads the log: proposals the human deleted from _review.md are decided, and /distill
    # must see that before it files the same lesson again (#41). Its log lines are committed on their own, or the
    # first operation would refuse over them. Over uncommitted wiki changes it waits: a deletion counts once the
    # human commits it, and a run with nothing else to do must not fail for it.
    if ($Commit -and (Test-WikiChanged)) {
        Log "uncommitted changes under the wiki: review-removals.py waits for them to be committed" | Out-Host
    } else {
        python omoikane/bin/review-removals.py 2>&1 | Tee-Object -FilePath $log -Append | Out-Host
        # A failure records nothing, which errs towards "still open"; the operations can run all the same.
        if ($LASTEXITCODE -ne 0) { Log "review-removals.py recorded nothing; see its message above" | Out-Host }
        if ($Commit -and (Test-WikiChanged)) {
            git commit -q -m "feat(wiki): record the review items the human removed" -- omoikane/log.md 2>&1 |
                Tee-Object -FilePath $log -Append | Out-Host
            if ($LASTEXITCODE -ne 0) { Stop-Run "git commit of the review-removals.py log lines failed" }
        }
    }
    $inbox = Join-Path $omoikane "raw/inbox"
    $files = Get-ChildItem $inbox -File -Recurse | Where-Object { $_.Name -ne ".gitkeep" }
    if (-not $files) { Log "nothing in inbox" }

    foreach ($f in $files) {
        $isSession = $f.DirectoryName -eq (Join-Path $inbox "sessions")
        if ($isSession -and $f.LastWriteTime -gt (Get-Date).AddMinutes(-$QuietMinutes)) {
            Log "session still active, waiting: $($f.Name)"; continue
        }
        $op = if ($isSession) { "distill" } else { "ingest" }
        $rel = [IO.Path]::GetRelativePath($root, $f.FullName) -replace "\\", "/"
        $dest = Join-Path $omoikane $(if ($isSession) { "raw/sources/sessions" } else { "raw/sources" })
        Log "$op start $rel"
        if (-not (Invoke-Operation $op $rel)) {
            Log "$op FAILED $rel"
            if ($Commit -and (Test-WikiChanged)) { Stop-Run "the $op run of $rel failed and left changes under the wiki" }
            continue
        }
        # The headless agent may not move files (#25): move the source so the next run does not process it again.
        if (Test-Path $f.FullName) { New-Item -ItemType Directory -Force $dest | Out-Null; Move-Item $f.FullName $dest }
        $movedTo = [IO.Path]::GetRelativePath($root, (Join-Path $dest $f.Name)) -replace "\\", "/"
        Complete-Operation $op $f.BaseName @($rel, $movedTo)
        Log "$op done $rel"
    }

    # The cross-session pass reads distilled session pages, so it runs after the inbox, never before.
    if ($SynthesizeEvery -gt 0) {
        python omoikane/bin/synthesize-due.py --every $SynthesizeEvery | Tee-Object -FilePath $log -Append
        if ($LASTEXITCODE -eq 0) {
            Log "synthesize start"
            if (Invoke-Operation "synthesize" "") { Log "synthesize done" } else {
                Log "synthesize FAILED"
                if ($Commit -and (Test-WikiChanged)) { Stop-Run "the synthesize run failed and left changes under the wiki" }
            }
            # The log heading is the counter. A run that did not write it would trigger again on every schedule.
            python omoikane/bin/synthesize-due.py --every $SynthesizeEvery | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Add-Content -Path (Join-Path $omoikane "log.md") -Encoding utf8 -Value "`n## [$(Get-Date -Format yyyy-MM-dd)] synthesize | ended without a log entry"
                Log "synthesize wrote no log entry; heading appended so the next run waits"
            }
            Complete-Operation "synthesize" "sessions"
        }
    }
} finally {
    Remove-Item -LiteralPath $runTmp -Recurse -Force
}
