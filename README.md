# neoweb

AI 时代全新的文学编程工具。

## 希望解决的问题

AI 写代码的速度已经超过了人读代码的速度，理解的成本已然大到不可接受。neoweb 的解法是重拾文学编程的思想，将代码和叙述结合，写成既能读、又能跑的文档。

## 快速开始

```sh
git clone https://github.com/random25160765-collab/neoweb.git
cd neoweb
```

编译 `nw` 二进制之前需要安装依赖：

Ubuntu / Debian：
```sh
sudo apt-get install build-essential pkg-config \
  libcmark-gfm-dev libcmark-gfm-extensions-dev \
  libsource-highlight-dev python3 graphviz
```
macOS：
```sh
brew install cmark-gfm source-highlight graphviz
```

同时环境里还要安装 Node。VS Code 插件另需三个 npm 依赖（`tm-grammars`、`vscode-oniguruma`、`vscode-textmate`），和 KaTeX 一起处理：

```sh
make deps         # npm install + 把 KaTeX 解到 tangle/vendor/
```

注意没有 KaTeX 的情况下，数学公式不会在输出页面里被渲染。

```sh
make              # 元层种子展开 → 编译 nw → 展开插件与语法 → 渲染整站到 weave/
make install      # 装到 ~/.local；PATH 里没有就把该目录写进 shell 启动文件
nw --version
```

## 编辑器插件

`book/Appendix C/plugin.nw` 展开出完整的 VS Code 插件（`tangle/editor/`）。打包安装：

```sh
make deps
make vsix
code --install-extension tangle/nw-*.vsix
```

也可以在 VS Code 的插件市场中下载扩展。

## 发布

目前仅支持 Linux x86_64 和 macOS，见 GitHub Release：

| 文件 | 内容 |
|---|---|
| `nw-X.Y.Z-linux-x86_64.tar.gz` | `nw`、`nw.1`、`LICENSE`，动态链接发行版的 `libcmark-gfm` 与 `source-highlight` |
| `nw-X.Y.Z-macos-arm64.tar.gz` | 同上，动态链接 Homebrew 的对应库；运行前需要 `brew install cmark-gfm source-highlight` |
| `nw-X.Y.Z.vsix` | 编辑器插件（也可从 VS Code 插件市场安装） |

## License

GPL-3.0-or-later，见 `LICENSE`。
