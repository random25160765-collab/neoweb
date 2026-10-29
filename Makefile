# 元层入口。手写，不是产物。
#
# 新用户怎么启动：克隆下来，敲 make。就这样。
#
# 为什么这一层必须手写：tangle 的产物全部落在 tangle/ 下（top 就是 tangle/），
# 而 make 必须在仓库根找到一份 Makefile。根这一份只做三件事——找源、第一次
# 用破点铺出 tangle/Makefile、把目标转发过去。真正的构建规则是 tangle/Makefile，
# 它由书展开（附录 A）。
#
# 不写 .PHONY：make 不为 phony 目标搜索隐含规则，加了下面这条 % 就失效，
# 所有目标都会变成 "Nothing to be done"。

PYTHON ?= python3

.DEFAULT_GOAL := all

# FORCE 让每一条转发都真的跑起来：目标同名目录（tangle/）存在时，
# 没有它 make 会说"已是最新"。
FORCE:

.PHONY: FORCE

# 空规则：阻止 `%` 去"重造 Makefile 自己"（否则每次都多一条 Nothing to be done）
Makefile: ;

# 篇的路径带空格：交给 make 与 sh 之前先转义。
SRC := $(shell find book -name '*.nw' | sort | sed 's/ /\\ /g')

%: FORCE
	@test -f tangle/Makefile || $(PYTHON) bootstrap.py tangle -o tangle $(SRC)
	@$(MAKE) --no-print-directory -f tangle/Makefile $@
