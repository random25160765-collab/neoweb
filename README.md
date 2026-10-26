# neoweb

AI 时代全新的文学编程工具。

## 希望解决的问题

AI 写代码的速度已经超过了人读代码的速度，理解的成本已然大到不可接受。neoweb 的解法是重拾文学编程的思想，将代码和叙述结合，写成既能读、又能跑的文档。

## 快速开始

```sh
git clone https://github.com/random25160765-collab/neoweb.git
cd neoweb
make              # 元层种子展开 → 编译 nw → 展开插件与语法 → 渲染整站到 weave/
make install      # 装到 ~/.local；PATH 里没有就把该目录写进 shell 启动文件
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
make deps         # npm install + 把 KaTeX 解到 tangle/vendor/
```

不跑 `make deps` 也能构建、也能出页面，代价是公式：`enhance` 找不到 KaTeX 时把 LaTeX 原样留在页面里，`$L(c)$` 就是字面的 `$L(c)$`（页面不报错，所以更容易被忽略）。

## 编辑器插件

`book/Appendix C/plugin.nw` 展开出完整的 VS Code 插件（`tangle/editor/`）。打包安装：

```sh
make deps
make vsix
code --install-extension tangle/nw-*.vsix
```

也可以在 VS Code 的插件市场中下载扩展。

## 发布

发布件只有一种：Linux x86_64、动态链接 `libcmark-gfm` 与 `source-highlight` 的二进制（`v0.1.0` 起）。别的平台没有预编译包，只能从源码构建——依赖就是上面那几行 apt。

发布是手工的：`git tag vX.Y.Z`，`make vsix`，把 `tangle/nw-*.tar.gz` 与 vsix 传上去。`.github/workflows/ci.yml` 只跑"能不能构建、产物对不对得上"，不产出发布件。

## License

GPL-3.0-or-later，见 `LICENSE`。
