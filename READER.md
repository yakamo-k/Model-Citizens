# Website reader

The public reader is at https://unrelated.info. Documents are edited and reviewed here on GitHub.

## Build from the latest published documents

Use Python 3.10 or later and Git:

```sh
python3 -m venv .venv-reader
.venv-reader/bin/pip install -r tools/requirements-reader.txt
.venv-reader/bin/python tools/build_reader.py --output /tmp/model-citizens-site
```

The output directory must not already exist. The default build fetches `main` from the public repository, reads Markdown document blobs, builds navigation and search, and validates internal links and headings before producing the site. It never runs code from the fetched repository. Raw HTML and embedded Markdown images are disabled.

To preview local document edits instead:

```sh
.venv-reader/bin/python tools/build_reader.py --source . --output /tmp/model-citizens-preview
python3 -m http.server 8080 --directory /tmp/model-citizens-preview --bind 127.0.0.1
```

Open http://127.0.0.1:8080. Each page links to its source editor and to discussions through GitHub issues. Visitors need a GitHub account to propose changes; reading the website requires no account.

Changes appear on the website after its maintainer runs an update. Publishing is manual; it is not triggered by opening a pull request. Only merged content from `main` is used by the normal update command.

The renderer reads `README.md`, `CONTRIBUTING.md`, and Markdown files under `docs/`, `proposals/`, `critiques/`, `experiments/`, `decisions/`, and `templates/`. Other files and deployment records are not published. Empty sections receive collection pages so readers can explore the structure before contributions arrive.
