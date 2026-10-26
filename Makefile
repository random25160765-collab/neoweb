# 元层入口。手写，不是产物。
#
# 新用户怎么启动：克隆下来，敲 make。就这样。
#
# 为什么这一层必须手写：新克隆的目录里还没有任何东西能读 .nw，而构建规则
# 本身要先由 .nw 展开出来。破点是 bootstrap.py（也手写，见它的头注释），
# 这里只负责在规则缺失时先跑它，再把目标转发过去。
#
# 不写 .PHONY：make 不为 phony 目标搜索隐含规则，加了下面这条 % 就失效，
# 所有目标都会变成 "Nothing to be done"。

PYTHON ?= python3

.DEFAULT_GOAL := all

# FORCE 让每一条转发都真的跑起来：仓库里存在与目标同名的目录（tools/），
# 没有它 make 会说"已是最新"，而那个"文件"其实是个目录。
FORCE:

.PHONY: FORCE

# 空规则：阻止 `%` 去"重造 Makefile 自己"（否则每次都多一条 Nothing to be done）
Makefile: ;

%: FORCE
	@test -f bootstrap.py || { echo "缺少 bootstrap.py：它是元层文件，必须随仓库一起存在"; exit 1; }
	@test -f tangle/Makefile || $(PYTHON) bootstrap.py "book/Appendix A/construct.nw" .
	@$(MAKE) --no-print-directory -f tangle/Makefile $@
