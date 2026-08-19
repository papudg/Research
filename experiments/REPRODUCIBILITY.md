# Experiments harness

Public branch **`reproducibility-public`**: [github.com/papudg/Research](https://github.com/papudg/Research/tree/reproducibility-public)

**Full instructions:** [../REPRODUCIBILITY.md](../REPRODUCIBILITY.md)

**Library source:** `src/icaa/` (install with `pip install -e .` from the repository root).

**Quick sanity check** (from repository root):

```powershell
$env:PYTHONHASHSEED='0'
.\.venv-icaa\Scripts\python.exe experiments\generate.py
```
