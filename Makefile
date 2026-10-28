CXX      ?= g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra
# pkg-config 给出两个库的链接参数。它缺席时整行为空，链接期会报未定义符号——
# 那时缺的是库，不是这几行。
LIBS     := $(shell pkg-config --libs libcmark-gfm source-highlight 2>/dev/null)
# 篇的路径带空格，make 按空白切词：把空格转义，make 与 sh 两边都认这个写法。
SRC      := $(shell find book -name '*.nw' | sort | sed 's/ /\\ /g')
NW       := ./nw
BOOT     := python3 nw3.py

.PHONY: all check test web serve crosscheck clean

all: $(NW)

# 有 nw 就用 nw（自举），没有才退回破点。一次铺整棵树，用一个记号记下。
.tangle-stamp: $(SRC) nw3.py
	@mkdir -p tangle
	@if [ -x $(NW) ]; then \
	  echo "  NW    tangle"; $(NW) tangle -o . $(SRC); \
	else \
	  echo "  BOOT  nw3.py"; $(BOOT) tangle -o . $(SRC); \
	fi
	@touch $@

$(NW): .tangle-stamp
	$(CXX) $(CXXFLAGS) -o $@ tangle/*.cpp $(LIBS)

# 破点也会查：它比 nw 多一条 check，理由在下一篇。
check:
	$(BOOT) check $(SRC)

test:
	python3 test_nw3.py

web: $(NW)
	@$(NW) weave -b tangle/book.yaml -o weave $(SRC)

serve: web
	@$(NW) serve weave

# 破点与自举的产物逐字节相同：否则"哪一份才是对的"就没人答得上来。
crosscheck: $(NW)
	@rm -rf /tmp/nw-boot
	@$(BOOT) tangle -o /tmp/nw-boot $(SRC) > /dev/null
	@diff -r tangle /tmp/nw-boot/tangle && echo "crosscheck ok：破点与自举的产物一致"

clean:
	rm -rf tangle weave $(NW) .tangle-stamp /tmp/nw-boot
