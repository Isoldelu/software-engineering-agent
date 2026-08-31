param(
    [string]$PythonCommand = "python",
    [ValidateRange(1, 10)]
    [int]$MaxCases = 10,
    [string]$OutputPath = "evaluation/native_tool_calling_report.json"
)

$ErrorActionPreference = "Stop"
$secureKey = Read-Host "Enter the rotated DEEPSEEK_API_KEY (hidden)" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
$plainKey = $null

try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    if ([string]::IsNullOrWhiteSpace($plainKey)) {
        throw "A non-empty rotated DeepSeek API Key is required."
    }

    $env:DEEPSEEK_API_KEY = $plainKey
    $env:SOFTWARE_AGENT_ENABLE_ONLINE_LLM = "true"
    $env:SOFTWARE_AGENT_LLM_PROVIDER = "deepseek"

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
    $plainKey = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
}
