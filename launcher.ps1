$createdNew = $false
$mutex = New-Object System.Threading.Mutex(
    $true,
    "Local\Mythic3QuizServer",
    [ref]$createdNew
)

# Jika launcher sudah berjalan, hentikan klik berikutnya
if (-not $createdNew) {
    exit
}

Set-Location $PSScriptRoot

# Buka browser setelah server sempat menyala
$browserJob = Start-Job {
    Start-Sleep -Seconds 3
    Start-Process "http://127.0.0.1:5000"
}

try {
    & ".\venv\Scripts\python.exe" "app.py"
}
finally {
    Remove-Job $browserJob -Force -ErrorAction SilentlyContinue
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
