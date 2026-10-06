<#
.SYNOPSIS
Register a Windows Task Scheduler job that runs wiki-ingest.ps1 -Commit every N minutes.

-Commit goes through the review gate (review-gate.py): each run works in the worktree <repo>-wiki-auto on branch
wiki/auto, never on this checkout, and pushes one PR to main that the human merges. Needs a remote `origin` and a
`gh auth login` session; a blocked run leaves <repo>-wiki-auto/omoikane/.wiki-ingest.blocked.

.EXAMPLE
omoikane/bin/install-schedule.ps1                 # every 30 min, Claude Code, through the review gate
omoikane/bin/install-schedule.ps1 -Minutes 60 -Agent opencode
omoikane/bin/install-schedule.ps1 -Remove
#>
param(
    [int] $Minutes = 30,
    [ValidateSet("claude", "opencode")] [string] $Agent = "claude",
    [switch] $Remove
)
$name = "OmoikaneIngest"
if ($Remove) { Unregister-ScheduledTask -TaskName $name -Confirm:$false; "removed $name"; exit 0 }

$script = Join-Path (Split-Path -Parent $PSScriptRoot) "bin/wiki-ingest.ps1"
$action = New-ScheduledTaskAction -Execute "pwsh.exe" -Argument "-NoProfile -File `"$script`" -Agent $Agent -Commit"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $Minutes)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Force | Out-Null
"registered ${name}: every $Minutes min via $Agent"
