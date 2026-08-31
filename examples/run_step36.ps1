param(
    [string]$PythonCommand = "python",
    [string]$SdkPath = "",
    [ValidateRange(1, 10)]
    [int]$MaxCases = 10,
    [string]$OutputPath = "evaluation/native_tool_calling_report.json"
)

$ErrorActionPreference = "Stop"
$secureKey = Read-Host "Enter the rotated DEEPSEEK_API_KEY (hidden)" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
$plainKey = $null
$previousPythonPath = $env:PYTHONPATH

try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    if ([string]::IsNullOrWhiteSpace($plainKey)) {
        throw "A non-empty rotated DeepSeek API Key is required."
    }

    $env:DEEPSEEK_API_KEY = $plainKey
    $env:SOFTWARE_AGENT_ENABLE_ONLINE_LLM = "true"
    $env:SOFTWARE_AGENT_LLM_PROVIDER = "deepseek"
    if (-not [string]::IsNullOrWhiteSpace($SdkPath)) {
        $env:PYTHONPATH = $SdkPath
    }

    & $PythonCommand -B evaluation/native_tool_calling_eval.py `
        --confirm-paid-calls `
        --max-cases $MaxCases `
        --output $OutputPath

    if ($LASTEXITCODE -ne 0) {
        throw "Step 36 evaluation failed with exit code $LASTEXITCODE."
    }
}
finally {
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:SOFTWARE_AGENT_ENABLE_ONLINE_LLM -ErrorAction SilentlyContinue
    Remove-Item Env:SOFTWARE_AGENT_LLM_PROVIDER -ErrorAction SilentlyContinue
    if ($null -eq $previousPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONPATH = $previousPythonPath
    }
    $plainKey = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
}
