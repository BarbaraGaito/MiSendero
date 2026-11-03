$ErrorActionPreference = 'Stop'
$cleanupRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$trainingRoot = [IO.Path]::GetFullPath((Join-Path $cleanupRoot 'training'))
$manifestPath = Join-Path $cleanupRoot 'docs\training-cleanup-2026-10-29-retired-sources-plan.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$allowedRoots = @('data\raw\wesad', 'data\raw\pamap2', 'data\raw\bidmc', 'data\raw\unimib-shar\extracted') | ForEach-Object { [IO.Path]::GetFullPath((Join-Path $trainingRoot $_)) }
$researchRoot = [IO.Path]::GetFullPath((Join-Path $trainingRoot 'data\fatigue-research')) + '\'
$retainedHashes = @{}
$deleted = [Collections.Generic.List[object]]::new()
$failed = [Collections.Generic.List[object]]::new()

function Assert-LocalPath([string]$candidate) {
    $resolved = [IO.Path]::GetFullPath($candidate)
    if (-not $resolved.StartsWith($trainingRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Path outside training directory' }
    $item = Get-Item -LiteralPath $resolved -Force
    while ($null -ne $item -and $item.FullName -ne $cleanupRoot) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Refusing reparse point or ancestor' }
        $item = if ($item.PSIsContainer) { $item.Parent } else { $item.Directory }
    }
    return $resolved
}

if ($manifest.workspace -ne $cleanupRoot) { throw 'Workspace differs from inspected manifest' }
foreach ($entry in $manifest.files) {
    $targetPath = Assert-LocalPath $entry.path
    $insideNamedRoot = @($allowedRoots | Where-Object { $targetPath.StartsWith($_ + '\', [StringComparison]::OrdinalIgnoreCase) }).Count -gt 0
    $isTemporary = $targetPath.StartsWith($researchRoot, [StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($targetPath) -eq 'selection.tmp'
    if (-not ($insideNamedRoot -or $isTemporary)) { throw 'Target outside explicitly inspected cleanup locations' }
    if ((Get-Item -LiteralPath $targetPath).Length -ne $entry.bytes) { throw 'Planned file size changed' }
    if ((Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw 'Planned file contents changed' }
    if ($entry.retained_copy) {
        $retained = Assert-LocalPath $entry.retained_copy
        if (-not $retainedHashes.ContainsKey($retained)) { $retainedHashes[$retained] = (Get-FileHash -LiteralPath $retained -Algorithm SHA256).Hash.ToLowerInvariant() }
        if ($retainedHashes[$retained] -ne $entry.retained_sha256) { throw 'Retained original changed' }
    }
    if ($isTemporary) {
        $temporaryJson = Get-Content -LiteralPath $targetPath -Raw | ConvertFrom-Json -AsHashtable
        $completeJson = Get-Content -LiteralPath $entry.retained_copy -Raw | ConvertFrom-Json -AsHashtable
        if ($temporaryJson.status -ne 'running' -or $completeJson.status -ne 'complete') { throw 'Selection states changed' }
    }
}
Write-Output ('Verified all {0} planned files before deletion' -f $manifest.file_count)

foreach ($entry in $manifest.files) {
    try {
        $targetPath = Assert-LocalPath $entry.path
        Remove-Item -LiteralPath $targetPath -Force
        $deleted.Add([pscustomobject]@{path=$targetPath;bytes=$entry.bytes;sha256=$entry.sha256;reason=$entry.reason;retained_copy=$entry.retained_copy})
    } catch {
        $failed.Add([pscustomobject]@{path=$entry.path;error=$_.Exception.Message})
    }
}
foreach ($namedRoot in $allowedRoots) {
    if (-not (Test-Path -LiteralPath $namedRoot)) { continue }
    $resolvedRoot = Assert-LocalPath $namedRoot
    if ($resolvedRoot -ne $namedRoot) { throw 'Unexpected cleanup root' }
    $directories = @(Get-ChildItem -LiteralPath $resolvedRoot -Directory -Recurse -Force | Sort-Object { $_.FullName.Length } -Descending)
    foreach ($directory in $directories) {
        $resolvedDirectory = Assert-LocalPath $directory.FullName
        if (-not $resolvedDirectory.StartsWith($resolvedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Directory outside named root' }
        if (@(Get-ChildItem -LiteralPath $resolvedDirectory -Force).Count -eq 0) { Remove-Item -LiteralPath $resolvedDirectory -Force }
    }
    if (@(Get-ChildItem -LiteralPath $resolvedRoot -Force).Count -eq 0) { Remove-Item -LiteralPath $resolvedRoot -Force }
}

$changedProtected = [Collections.Generic.List[object]]::new()
$verifiedContentHashes = 0
foreach ($protected in $manifest.protected_files) {
    if (-not (Test-Path -LiteralPath $protected.path -PathType Leaf)) {
        $changedProtected.Add([pscustomobject]@{path=$protected.path;reason='missing'})
        continue
    }
    if ((Get-Item -LiteralPath $protected.path).Length -ne $protected.bytes) {
        $changedProtected.Add([pscustomobject]@{path=$protected.path;reason='size_changed'})
        continue
    }
    if ($protected.sha256) {
        if ((Get-FileHash -LiteralPath $protected.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $protected.sha256) {
            $changedProtected.Add([pscustomobject]@{path=$protected.path;reason='hash_changed'})
        } else { $verifiedContentHashes++ }
    }
}
$remaining = @($deleted | Where-Object { Test-Path -LiteralPath $_.path })
$bytesFreed = ($deleted | Measure-Object -Property bytes -Sum).Sum
$previous = Get-Content -LiteralPath (Join-Path $cleanupRoot 'docs\training-cleanup-2026-10-29-followup-result.json') -Raw | ConvertFrom-Json
$result = [ordered]@{
    completed_at=[DateTime]::UtcNow.ToString('o'); scope=$trainingRoot; manifest=$manifestPath
    deleted_files=$deleted; deleted_file_count=$deleted.Count; bytes_freed=$bytesFreed
    failures=$failed; deleted_paths_still_present=$remaining.Count
    protected_file_count=$manifest.protected_file_count; verified_protected_content_hashes=$verifiedContentHashes
    protected_files_missing_or_changed=$changedProtected
    preserved_datasets='All current training originals, admitted public source datasets, fitted models and final results; original UniMiB ZIP retained'
    retired_source_evidence='docs/ai-real-data-audit.md; no current code/source-lock dependencies on WESAD/PAMAP2/BIDMC'
    previous_cleanup_bytes=$previous.combined_bytes_freed
    combined_bytes_freed=$previous.combined_bytes_freed+$bytesFreed
}
$resultPath = Join-Path $cleanupRoot 'docs\training-cleanup-2026-10-29-retired-sources-result.json'
$result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $resultPath -Encoding UTF8
[pscustomobject]@{report=$resultPath;deleted_files=$deleted.Count;bytes_freed=$bytesFreed;failures=$failed.Count;deleted_paths_still_present=$remaining.Count;protected_files_missing_or_changed=$changedProtected.Count;verified_protected_content_hashes=$verifiedContentHashes} | ConvertTo-Json
if ($failed.Count -gt 0 -or $remaining.Count -gt 0 -or $changedProtected.Count -gt 0) { exit 1 }
