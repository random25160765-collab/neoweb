# neoweb

AI 时代重做文学编程：一份 `.nw` 源，tangle 出可编译的源码，weave 出你正在读的页面。

这本书本身就是这个工具——`book/` 里的每一篇既是章节，也是 `tangle/` 下源码的来源。

## 依赖

Ubuntu / Debian：

```sh
sudo apt-get install build-essential pkg-config \
  libcmark-gfm-dev libcmark-gfm-extensions-dev \
  libsource-highlight-dev python3
```

macOS：

```sh
brew install pkg-config cmark-gfm source-highlight
```

`libcmark-gfm` 是硬依赖：没有它就没有散文。`source-highlight` 是软依赖：缺了它页面照出，只是代码块不着色。编辑器插件只用 Node 跑一次语法生成，不装 npm 依赖。

## 快速开始

```sh
git clone https://github.com/random25160765-collab/neoweb.git
cd neoweb
make              # 铺出 tangle/，编译出 tangle/build/nw
make web          # 渲染整站到 weave/
make serve        # 本地预览，默认 http://127.0.0.1:8080
```

克隆下来直接 `make` 就行。仓库根那份手写 `Makefile` 只做三件事：找源、第一次用破点铺出 `tangle/Makefile`、把目标转发过去；真正的规则在 `tangle/Makefile` 里。

## 命令

| 命令 | 做什么 |
|---|---|
| `make` | tangle 全书 → 编译 `tangle/build/nw` |
| `make check` | 只查源：重复实现、未实现的引用、挂载冲突、不可达的块 |
| `make test` | 破点的用例（27 个语法与 tangle 用例） |
| `make web` | 把每一篇渲成一页 HTML，按 `tangle/book.yaml` 排目录与上下章 |
| `make serve` | 起一个静态服务器预览 `weave/` |
| `make crosscheck` | 用破点重铺一遍，与自举产物逐字节比对 |
| `make clean` | 删掉全部产物（`tangle/`、`weave/`） |

## 仓库里有什么

```
book/            源：散文 + 语法 + 实现，全部由人写
nw3.py           破点：只做 tangle 的 Python 实现，负责第一次
Makefile         手写元层：找源、首次 bootstrap、转发
tangle/          产物：源码、book.yaml、Makefile、examples/、editor/、build/nw
weave/           产物：HTML
docs/            设计笔记，不参与构建
```

**生成的都在 `tangle/` 下，仓库根只放手写的**——`ls` 一眼就能分出哪些是写的、哪些是铺的。`tangle/` 里的东西不要手改：它们由 `book/*.nw` 展开，改源才有效。

## 编辑器插件

```sh
make
node tangle/editor/tools/gen-grammar.js                    # 写出语法文件
ln -s "$PWD/tangle/editor" ~/.vscode/extensions/neoweb.nw  # 装成扩展目录
```

重启窗口后，`.nw` 文件会有语法着色、语言配置与片段。插件只看着色，不做 tangle、不做跳转——那些交给 `tangle/build/nw` 本身。

## 许可

GPL-3.0-or-later，见 `LICENSE`。
