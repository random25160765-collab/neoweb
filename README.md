# neoweb

Literate programming rebuilt for the age of AI: one `.nw` source, `tangle` for compilable code, `weave` for the page you are reading.

The book *is* the tool — every file under `book/` is a chapter and, at the same time, the source of a file under `tangle/`.

**中文版：[README-zh.md](README-zh.md)**

## Requirements

Ubuntu / Debian:

```sh
sudo apt-get install build-essential pkg-config \
  libcmark-gfm-dev libcmark-gfm-extensions-dev \
  libsource-highlight-dev python3
```

macOS:

```sh
brew install pkg-config cmark-gfm source-highlight
```

`libcmark-gfm` is required — without it there is no prose. `source-highlight` is optional: pages still render, code just loses its colours. `graphviz` and KaTeX (fetched by `make deps`) are optional too: without them `dot` fences and `$…$` math stay on the page as source text, and nothing else breaks.

## Quick start

```sh
git clone https://github.com/random25160765-collab/neoweb.git
cd neoweb
make              # expand tangle/, build tangle/build/nw
make web          # render the whole book into weave/
make serve        # preview at http://127.0.0.1:8080
```

`make` on a fresh clone is all you need. The hand-written `Makefile` at the repo root does exactly three things: find the sources, bootstrap `tangle/Makefile` with the Python port on first run, and forward every target. The real rules live in `tangle/Makefile`, which is itself a product of the book.

## Commands

| Command | What it does |
|---|---|
| `make` | tangle the book, then compile `tangle/build/nw` |
| `make check` | source checks only: duplicate definitions, unresolvable references, mount conflicts, unreachable chunks |
| `make test` | the Python port's test suite (46 syntax, book and tangle cases) |
| `make web` | render one HTML page per chapter, ordered by the `book` structure in the source |
| `make md` | export the same source as Markdown, mirroring the book's directory layout |
| `make serve` | kill any running preview, then serve `weave/` (another port: `make serve PORT=8081`) |
| `make crosscheck` | re-expand with the Python port and diff byte-for-byte against the self-hosted output |
| `make deps` | install the editor plugin's three Node packages and fetch KaTeX into `tangle/vendor/` |
| `make ext` | symlink the plugin into your extensions directory (dev install) |
| `make vsix` | package the plugin as `tangle/nw-<version>.vsix` |
| `make clean` | remove all build products (`tangle/`, `weave/`, `weave-md/`) |

Behind a mainland-China mirror, point npm somewhere reachable:

```sh
make deps NPMFLAGS=--registry=https://registry.npmmirror.com
```

## What is in the repo

```
book/            source: prose, grammar and implementation, all hand-written
bootstrap.py     the bootstrap port: first run and crosscheck reference
Makefile         hand-written meta layer: find sources, bootstrap once, forward
tangle/          products: sources, Makefile, examples/, editor/, build/nw
weave/           products: HTML (one page per chapter + index.html + tree.html)
weave-md/        products: Markdown, mirroring the book's directory layout
docs/            design notes, not part of the build
```

**Everything generated lives under `tangle/`; the repo root holds only hand-written files** — `ls` tells you which is which. Never edit `tangle/` by hand: it is expanded from `book/*.nw`, so the source is the only place where a change sticks.

## Editor plugin

```sh
make vsix                                                        # build the package
make ext                                                         # or: symlink it straight in
make ext VSCODE=$HOME/.vscode-server/extensions                  # remote/server install
```

The plugin only colours and completes; tangling and navigation belong to `tangle/build/nw` itself.

## License

GPL-3.0-or-later, see `LICENSE`.
