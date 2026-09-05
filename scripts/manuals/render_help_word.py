"""Use the required DOCX renderer with Word as the Windows PDF conversion backend."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
renderer = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("docx_renderer", renderer)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def word_pdf(doc_path, user_profile, convert_tmp_dir, stem, verbose):
    output = Path(convert_tmp_dir) / (stem + ".pdf")
    env = dict(os.environ, HELP_DOCX=str(Path(doc_path).resolve()), HELP_PDF=str(output))
    command = r'''
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $null
try {
    $doc = $word.Documents.Open($env:HELP_DOCX, $false, $true)
    $doc.ExportAsFixedFormat($env:HELP_PDF, 17)
} finally {
    if ($null -ne $doc) { $doc.Close($false); [Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null }
    $word.Quit()
    [Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
'''
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], env=env, capture_output=True, timeout=180)
    if result.returncode or not output.exists():
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return str(output), "Microsoft Word fixed-format export"


module.convert_to_pdf = word_pdf
for source in sorted((ROOT / "docs/help/dist").glob("*.docx")):
    out = ROOT / ".shots/documents" / source.stem
    module.rasterize(str(source), str(out), dpi=120, verbose=False, emit_pdf=True)
    print(f"Rendered {source.stem}: {len(list(out.glob('page-*.png')))} pages", flush=True)
