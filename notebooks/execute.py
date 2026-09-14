"""Execute the compact notebook against existing artifacts; never run benchmarks."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import nbformat
from nbclient import NotebookClient
from jupyter_client.kernelspec import KernelSpecManager

root = Path(__file__).resolve().parents[1]
path = root / "notebooks/numerical-validation.ipynb"
if not (root / "artifacts/standard/observations.json").exists():
    raise SystemExit("Run the standard benchmark first; see README.md.")
nb = nbformat.read(path, as_version=4)
# A temporary public kernelspec uses this environment without changing user settings.
with TemporaryDirectory(prefix="ginseng-kernel-") as directory:
    spec_dir = Path(directory) / "ginseng"
    spec_dir.mkdir()
    (spec_dir / "kernel.json").write_text(
        json.dumps(
            {
                "argv": [
                    sys.executable,
                    "-m",
                    "ipykernel_launcher",
                    "-f",
                    "{connection_file}",
                ],
                "display_name": "Ginseng Python",
                "language": "python",
            }
        )
    )
    client = NotebookClient(
        nb,
        timeout=120,
        kernel_name="ginseng",
        resources={"metadata": {"path": str(root)}},
    )
    client.create_kernel_manager()
    client.km.kernel_spec_manager = KernelSpecManager(kernel_dirs=[directory])
    client.execute()
nbformat.write(nb, path)
print(f"Executed {path}")
