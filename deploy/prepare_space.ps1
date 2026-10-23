# Copies the files the Hugging Face Space needs into a local clone of the Space
# repository, ready to commit and push. Run from the project root:
#
#   .\deploy\prepare_space.ps1 -SpaceDir ..\loanmate-backend
#
# Secrets (.env), the virtual environment, tests and the frontend are left out.

param(
    [Parameter(Mandatory = $true)]
    [string]$SpaceDir
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path (Join-Path $SpaceDir ".git"))) {
    throw "$SpaceDir is not a git clone. Clone your Space first: git clone https://huggingface.co/spaces/<user>/<space>"
}

# Free Gradio-SDK Space: it pip-installs requirements.txt and runs app.py.
Copy-Item (Join-Path $root "requirements-deploy.txt") -Destination (Join-Path $SpaceDir "requirements.txt") -Force
Copy-Item (Join-Path $root "deploy\space_app.py") -Destination (Join-Path $SpaceDir "app.py") -Force

# Space-specific attributes: LF for scripts, Git LFS for the binary FAISS index.
Copy-Item (Join-Path $root "deploy\hf_space_gitattributes") -Destination (Join-Path $SpaceDir ".gitattributes") -Force

# Spaces read their settings (SDK, Python version, app file) from README.md front matter.
Copy-Item (Join-Path $root "deploy\hf_space_README.md") -Destination (Join-Path $SpaceDir "README.md") -Force

foreach ($dir in "backend", "prompts") {
    robocopy (Join-Path $root $dir) (Join-Path $SpaceDir $dir) /MIR /XD __pycache__ /XF call_records.jsonl *.pyc /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Copying $dir failed (robocopy exit $LASTEXITCODE)" }
}

Write-Host "Space files ready in $SpaceDir. Next: cd $SpaceDir; git add -A; git commit -m 'Deploy LoanMate backend'; git push"
exit 0  # robocopy's "files copied" code (1) is success; don't leak it as a failure
