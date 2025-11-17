<#
.SYNOPSIS
    Sets up virtual environment and continuously runs the Python program located at ./src/main.py, restarting it upon exit.

.DESCRIPTION
    This script:
    1. Creates a virtual environment (.venv) if it doesn't exist
    2. Activates the virtual environment
    3. Installs dependencies from requirements.txt if needed
    4. Enters an infinite loop where it starts the specified Python program
    If the program exits, the script waits for 2 seconds and then restarts it.
    The loop can be interrupted by pressing Ctrl+C, which triggers the catch block to display a stop message and error details.

.NOTES
    - Requires Python to be installed and accessible via the "python" command.
    - Intended for streaming or testing scenarios where automatic restarts are useful.
    - Automatically manages virtual environment and dependencies.

.EXAMPLE
    PS> .\run.ps1
#>

# Function to check if dependencies are installed
function Test-DependenciesInstalled {
    $requirementsPath = "./requirements.txt"
    if (-not (Test-Path $requirementsPath)) {
        Write-Host "requirements.txt not found, skipping dependency check"
        return $true
    }

    try {
        $requirements = Get-Content $requirementsPath | Where-Object { $_ -match "^[^#]" -and $_.Trim() -ne "" }
        foreach ($requirement in $requirements) {
            $packageName = ($requirement -split "==")[0].Trim()
            $result = & ".venv/Scripts/python" -m pip show $packageName 2>$null
            if (-not $result) {
                return $false
            }
        }
        return $true
    }
    catch {
        return $false
    }
}

function Get-PythonSelection {
    $candidates = @(
        @("python3.12"),
        @("python3.11"),
        @("python3.10"),
        @("python3"),
        @("python"),
        @("py", "-3.12"),
        @("py", "-3.11"),
        @("py", "-3.10"),
        @("py", "-3")
    )

    $fallback = $null

    foreach ($candidate in $candidates) {
        try {
            $extra = @()
            if ($candidate.Length -gt 1) { $extra = $candidate[1..($candidate.Length - 1)] }
            $version = & $candidate[0] @extra "-c" "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        }
        catch {
            continue
        }

        if (-not $version) { continue }
        $version = $version.Trim()
        $parts = $version.Split('.')
        $major = [int]$parts[0]
        $minor = [int]$parts[1]

        if ($major -eq 3 -and $minor -ge 10 -and $minor -le 12) {
            return @{ Cmd = $candidate; Version = $version }
        }

        if ($major -eq 3 -and $minor -eq 9 -and -not $fallback) {
            $fallback = @{ Cmd = $candidate; Version = $version }
        }
    }

    return $fallback
}

function Invoke-Python($cmdParts, $args) {
    $extra = @()
    if ($cmdParts.Length -gt 1) { $extra = $cmdParts[1..($cmdParts.Length - 1)] }
    & $cmdParts[0] @extra @args
}

try {
    $selection = Get-PythonSelection
    if (-not $selection) {
        throw "Python 3.10–3.12 not found. Install a supported Python so pygame wheels are available."
    }

    $pythonCmd = $selection.Cmd
    $pyVersion = $selection.Version

    Write-Host "Using Python command '$($pythonCmd -join ' ')" ("(Python $pyVersion)")

    $pyMajor,$pyMinor = $pyVersion.Split('.')
    if ($pyMajor -eq 3 -and [int]$pyMinor -ge 13) {
        throw "Python $pyVersion detected. Install Python 3.10–3.12 so pygame wheels are available. TikTok chat control also requires 3.10+."
    }

    if ($pyMajor -eq 3 -and [int]$pyMinor -le 9) {
        Write-Warning "Python $pyVersion detected. The game will run, but TikTok chat control stays disabled on 3.9."
    }

    # Check if virtual environment exists
    if (-not (Test-Path ".venv")) {
        Write-Host "Creating virtual environment..."
        Invoke-Python $pythonCmd @("-m", "venv", ".venv")
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create virtual environment"
        }
        Write-Host "Virtual environment created successfully."
    }

    # Activate virtual environment
    Write-Host "Activating virtual environment..."
    & ".venv/Scripts/Activate.ps1"

    # Check if dependencies need to be installed
    if (-not (Test-DependenciesInstalled)) {
        Write-Host "Installing dependencies..."
        & ".venv/Scripts/python" -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install dependencies"
        }
        Write-Host "Dependencies installed successfully."
    } else {
        Write-Host "Dependencies already installed."
    }

    # Run the application
    while ($true) {
        Write-Host "Starting program..."
        & ".venv/Scripts/python" "./src/main.py"
        $exitCode = $LASTEXITCODE

        if ($exitCode -eq 0) {
            Write-Host "Program was closed by user. Exiting..."
            break
        } else {
            Write-Host "Program exited with error code $exitCode. Restarting in 2 seconds... Press Ctrl+C to stop."
            Start-Sleep -Seconds 2
        }
    }
}
catch {
    Write-Host "Stopped by user or error occurred."
    Write-Host "Error details:"
    Write-Host $_  # This shows the error that was caught
}
