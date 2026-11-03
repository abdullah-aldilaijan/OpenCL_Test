# Setup without Anaconda

From CMD in this folder, run:

```bat
Setup.cmd
```

This installs standalone Python 3.14 using WinGet, adds it to your user PATH, creates the application's `.venv`, and installs and verifies the Python dependencies. Anaconda is not used. Open a new terminal afterward to use the updated global `python` command. Internet and WinGet are required. GPU drivers providing OpenCL must already be installed.

Then run:

```bat
Run.cmd
```

The single dropdown is populated at startup with detected CPU models and usable OpenCL GPUs. Refresh devices queries them again. CPU mode remains available if no usable GPU runtime is detected. CPU selection uses the system CPU normally and does not set processor affinity.

The launcher now uses only this folder's standalone `.venv`; older README references to the prepared workspace environment are superseded by these instructions.

Setup checks working standalone Python, the existing application environment, pip, and dependency versions/imports. Existing working components are skipped; missing or incompatible components are installed automatically. No internet is needed when everything already works.
