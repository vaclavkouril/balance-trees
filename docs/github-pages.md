# Static visualizer build

The static build includes the interactive visualizer, its runtime assets, and
two benchmark reports under `benchmarks/`. **C++ probability benchmarks** opens
`benchmarks/geometric-native/index.html`: the 252-trial comparison of the original
fair-coin and new 3/4 strategies across seven input families, through 16,777,216
keys. The report links back to the visualizer and to the probability PDF.
**Earlier benchmark results** opens the previous comparison at
`benchmarks/index.html`. Both reports include their charts, measurements and
measured source archives. Other historical report bundles remain excluded.

From the repository root, with Python 3.11+:

```sh
PYTHONPATH=src python3 -m balance_trees.showcase.build --output _site
python3 -m http.server --directory _site 8000
```

Use a fresh build directory. Open `http://127.0.0.1:8000`; the build uses browser
simulation and does not require the Python API. Relative module and asset URLs
support hosting under a repository subpath. `_site/` is ignored by Git.

The existing `.github/workflows/pages.yml` compiles
`docs/proofs/geometric-biased-repair.tex`, runs Python and browser model tests,
builds these assets and publishes them from the default branch when GitHub Pages
is configured to use GitHub Actions. It does not run benchmarks or bundle their
raw working directories. The requested benchmark reports and their supporting
downloads are already bundled. Source changes must be committed and pushed
before deployment can occur.

For local Python-backed traces, run
`PYTHONPATH=src python3 -m balance_trees.showcase --port 8000` instead.
See [the visualizer guide](showcase.md) for playback and trace import/export.

The **3/4 strategy proof (PDF)** link opens `geometric-biased-repair.pdf` at the
site root. Changes to `docs/proofs/**` trigger compilation and publication; the
Pages build uses the PDF compiled in that workflow run. The separate
`proofs.yml` workflow also uploads a `geometric-biased-repair-pdf` artifact.
For local builds, compile and copy the PDF first using the commands in
[the proof README](proofs/README.md). The historical fair-coin analysis remains
available through its own link.
