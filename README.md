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

# 第一次：还没有 Makefile，用破点铺出它
find book -name '*.nw' -exec python3 nw3.py tangle -o . {} +

make              # 编译出 ./nw
make web          # 渲染整站到 weave/
make serve        # 本地预览，默认 http://127.0.0.1:8080
```

`-exec … {} +` 不能换成 `$(find …)`：篇的路径里有空格（`book/Chapter 1/…`），shell 的分词会把它切成两半。

第一次之后，`Makefile` 与 `tangle/` 都有了，改书只要 `make`（会重新 tangle 并编译）或 `make web`（只渲染站点）。

## 命令

| 命令 | 做什么 |
|---|---|
| `make` | tangle 全书 → 编译 `./nw` |
| `make check` | 只查源：重复实现、未实现的引用、挂载冲突、不可达的块 |
| `make test` | 破点的用例（27 个语法与 tangle 用例） |
| `make web` | 把每一篇渲成一页 HTML，按 `tangle/book.yaml` 排目录与上下章 |
| `make serve` | 起一个静态服务器预览 `weave/` |
| `make crosscheck` | 用破点重铺一遍，与自举产物逐字节比对 |
| `make clean` | 删掉全部产物（`tangle/`、`weave/`、`nw`） |

## 仓库里有什么

```
book/       源：散文 + 语法 + 实现，全部由人写
nw3.py      破点：只做 tangle 的 Python 实现，负责第一次
tangle/     产物：C++ 源码与 book.yaml（不入库）
weave/      产物：HTML（不入库）
editor/     产物：VS Code 扩展目录（不入库）
examples/   产物：附录 B 的示例程序（不入库）
docs/       设计笔记，不参与构建
```

`tangle/` 下的东西不要手改：它们由 `book/*.nw` 展开，改源才有效。

## 编辑器插件

```sh
make
node editor/tools/gen-grammar.js                          # 写出语法文件
ln -s "$PWD/editor" ~/.vscode/extensions/neoweb.nw        # 装成扩展目录
```

重启窗口后，`.nw` 文件会有语法着色、语言配置与片段。插件只看着色，不做 tangle、不做跳转——那些交给 `nw` 本身。

## 许可

GPL-3.0-or-later，见 `LICENSE`。
