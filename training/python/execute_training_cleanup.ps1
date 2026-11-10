$ErrorActionPreference = 'Stop'
$cleanupRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$trainingRoot = [IO.Path]::GetFullPath((Join-Path $cleanupRoot 'training')) + '\'
$manifestPath = Join-Path $cleanupRoot 'docs\training-cleanup-2026-10-29.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$deleted = @()
$failed = @()
foreach ($entry in $manifest.files) {
    try {
        $targetPath = [IO.Path]::GetFullPath($entry.path)
        if (-not $targetPath.StartsWith($trainingRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Target outside training directory' }
        if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) { throw 'Planned file no longer exists' }
        $item = Get-Item -LiteralPath $targetPath -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Refusing reparse point' }
        if ($item.Length -ne $entry.bytes) { throw 'File changed after inspection' }
        if ($entry.reason -eq 'exact_temporary_copy_of_completed_selection') {
            $retainedHash = (Get-FileHash -LiteralPath $entry.retained_identical_copy -Algorithm SHA256).Hash.ToLowerInvariant()
            $temporaryHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($temporaryHash -ne $entry.sha256 -or $retainedHash -ne $entry.sha256) { throw 'Checkpoint copies changed' }
        } elseif ($entry.reason -eq 'installer_download_cache') {
            if ($targetPath -notmatch '\\pip-cache\\') { throw 'Invalid installer cache location' }
        } elseif ($entry.reason -eq 'regenerable_python_bytecode') {
            if ($targetPath -notmatch '\\__pycache__\\') { throw 'Invalid bytecode cache location' }
        } else { throw 'Unknown cleanup category' }
        Remove-Item -LiteralPath $targetPath -Force
        $deleted += [pscustomobject]@{path=$targetPath;bytes=$entry.bytes;reason=$entry.reason}
    } catch {
        $failed += [pscustomobject]@{path=$entry.path;error=$_.Exception.Message}
    }
}
$totalBytes = ($deleted | Measure-Object -Property bytes -Sum).Sum
$remaining = @($deleted | Where-Object { Test-Path -LiteralPath $_.path })
$result = [ordered]@{completed_at=[DateTime]::UtcNow.ToString('o');deleted_files=$deleted;deleted_file_count=$deleted.Count;bytes_freed=$totalBytes;failures=$failed;deleted_paths_still_present=$remaining.Count;datasets_models_and_final_results_deleted=$false}
$resultPath = Join-Path $cleanupRoot 'docs\training-cleanup-2026-10-29-result.json'
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $resultPath -Encoding UTF8
[pscustomobject]@{deleted_files=$deleted.Count;bytes_freed=$totalBytes;failures=$failed.Count;deleted_paths_still_present=$remaining.Count;report=$resultPath} | ConvertTo-Json
if ($failed.Count -gt 0 -or $remaining.Count -gt 0) { exit 1 }
