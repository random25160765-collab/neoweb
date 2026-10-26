# neoweb

AI 时代全新的文学编程工具。

## 我希望解决的问题

AI 写代码的速度已经超过了人读代码的速度，理解的成本已然大到不可接受。neoweb 的解法是重拾文学编程的思想，将代码和叙述结合，写成既能读、又能跑的文档。

## 快速开始

```sh
git clone https://github.com/random25160765-collab/neoweb.git
cd neoweb
make              # 元层种子展开 → 编译 nw → 展开插件与语法 → 渲染整站到 weave/
make install      # 装 nw 与 man 页到 ~/.local（不在 PATH 上会提示）
nw --help
```

第一次 `make` 之后：

- 整站HTML 在 `weave/index.html`，直接用浏览器打开即可；
- `make serve` 起一个本地服务（8000 端口）边改边看；
- `nw tutorial` 给出交互式入门，`man nw` 是完整命令手册。

## 环境依赖

编译 `nw` 本体之前需要安装依赖：

```sh
sudo apt-get install build-essential pkg-config \
  libcmark-gfm-dev libsource-highlight-dev libboost-regex-dev python3
```

VS Code 插件另需 Node 与 npm，以及三个 npm 依赖（`tm-grammars`、`vscode-oniguruma`、`vscode-textmate`）：

```sh
make deps         # npm install + 把 KaTeX 解到 tangle/tools/vendor/
```

`make` 的最后一步会跑 `tangle/build/enhance`，它另需两样外部工具：`graphviz` 的 `dot` 把 `dot` 围栏画成内联 SVG，`node` + KaTeX 把 `$…$` 转成 MathML。两样都是可选的，缺了只降级——图显示成源码，公式显示成原文，构建不失败：

```sh
sudo apt-get install graphviz
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
