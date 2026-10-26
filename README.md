# neoweb

AI 时代全新的文学编程工具。

## 希望解决的问题

AI 写代码的速度已经超过了人读代码的速度，理解的成本已然大到不可接受。neoweb 的解法是重拾文学编程的思想，将代码和叙述结合，写成既能读、又能跑的文档。

## 快速开始

```sh
git clone https://github.com/random25160765-collab/neoweb.git
cd neoweb
make              # 元层种子展开 → 编译 nw → 展开插件与语法 → 渲染整站到 weave/
make install      # 装 nw 与 man 页到 ~/.local（不在 PATH 上会提示）
nw --help
```

## 环境依赖

编译 `nw` 本体之前需要安装依赖：

```sh
sudo apt-get install build-essential pkg-config \
  libcmark-gfm-dev libsource-highlight-dev libboost-regex-dev python3 graphviz
```

同时环境里还要安装 Node。VS Code 插件另需三个 npm 依赖（`tm-grammars`、`vscode-oniguruma`、`vscode-textmate`），和 Katex 一起处理：

```sh
make deps         # npm install + 把 KaTeX 解到 tangle/tools/vendor/
```

## 编辑器插件

`book/Appendix C/plugin.nw` 展开出完整的 VS Code 插件（`tangle/editor/`）。打包安装：

```sh
make deps
make vsix
code --install-extension tangle/nw-*.vsix
```

也可以在 VS Code 的插件市场中下载扩展。

## License

GPL-3.0-or-later，见 `LICENSE`。
