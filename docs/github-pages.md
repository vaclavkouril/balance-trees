# Static visualizer build

The old report pages, graph collections and benchmark downloads have been
removed. Only the interactive visualizer and its runtime assets are currently
built. A replacement website will be added separately.

From the repository root, with Python 3.11+:

```sh
PYTHONPATH=src python3 -m balance_trees.showcase.build --output _site
python3 -m http.server --directory _site 8000
```

Use a fresh build directory. Open `http://127.0.0.1:8000`; the build uses browser
simulation and does not require the Python API. Relative module and asset URLs
support hosting under a repository subpath. `_site/` is ignored by Git.

The existing `.github/workflows/pages.yml` runs Python and browser model tests,
builds these assets and publishes them from the default branch when GitHub Pages
is configured to use GitHub Actions. It does not run benchmarks or bundle their
output. Source changes must be committed and pushed before deployment can occur.

For local Python-backed traces, run
`PYTHONPATH=src python3 -m balance_trees.showcase --port 8000` instead.
See [the visualizer guide](showcase.md) for playback and trace import/export.
