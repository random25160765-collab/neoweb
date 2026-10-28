#!/usr/bin/env python3
"""nw3 的用例。跑法：python3 test_nw3.py"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
NW3 = os.path.join(HERE, "nw3.py")

fails = []
passed = 0


def run(args, src):
    """把 src 写进临时目录跑一次，返回 (returncode, stdout)。"""
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "t.nw")
        with open(p, "w", encoding="utf-8") as f:
            f.write(src)
        r = subprocess.run([sys.executable, NW3] + args + [p],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr
    finally:
        shutil.rmtree(d)


def tangle(src, want_path):
    rc, out = run(["tangle", "-o", "OUT"], src)
    return rc, out


def tangle_content(src, relpath):
    """跑 tangle，返回产物的内容（找不到返回 None）。"""
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "t.nw")
        with open(p, "w", encoding="utf-8") as f:
            f.write(src)
        outdir = os.path.join(d, "out")
        r = subprocess.run([sys.executable, NW3, "tangle", "-o", outdir, p],
                           capture_output=True, text=True)
        if r.returncode:
            raise AssertionError(f"tangle 失败：{r.stdout}{r.stderr}")
        target = os.path.join(outdir, relpath)
        if not os.path.exists(target):
            return None
        with open(target, encoding="utf-8") as f:
            return f.read()
    finally:
        shutil.rmtree(d)


def eq(name, src, relpath, want):
    global passed
    try:
        got = tangle_content(src, relpath)
        if got != want:
            fails.append(f"{name}\n  got : {got!r}\n  want: {want!r}")
        else:
            passed += 1
    except AssertionError as e:
        fails.append(f"{name}\n  {e}")


def bad(name, src, needle):
    """check 必须失败，而且输出里有 needle。"""
    global passed
    rc, out = run(["check"], src)
    if rc == 0:
        fails.append(f"{name}\n  没有报错")
    elif needle not in out:
        fails.append(f"{name}\n  got : {out.strip()}\n  want 含: {needle}")
    else:
        passed += 1


def ok(name, src, needle=""):
    """check 必须通过。"""
    global passed
    rc, out = run(["check"], src)
    if rc != 0:
        fails.append(f"{name}\n  不该报错却报了：{out.strip()}")
    elif needle and needle not in out:
        fails.append(f"{name}\n  输出里没有 {needle!r}：{out.strip()}")
    else:
        passed += 1


def warn(name, src, needle):
    """check 通过但有警告。"""
    global passed
    rc, out = run(["check"], src)
    if rc != 0:
        fails.append(f"{name}\n  报错了：{out.strip()}")
    elif needle not in out:
        fails.append(f"{name}\n  警告里没有 {needle!r}：{out.strip()}")
    else:
        passed += 1


# ================================================================ 骨架与 tangle

eq("骨架：草案的例子",
   """\
dir top @
	dir            .github;
	dir            book;
	file           .gitignore;
	file<py>       bootstrap;
	file<license>  LICENSE;
	file<makefile> Makefile;
	file<md>       README;
~@

<< include >>= @
	#include<stdio.h>
~@

<< printer >>= @
	printf("hello world!\\n");
~@

<< main >>= @
	int main() {
		<< printer >>
		return 0;
	}
~@

file<c> hello_world @
	<< include >>
	<< main >>
~@

dir book @
	file<c> hello_world;
~@
""",
   "book/hello_world.c",
   '#include<stdio.h>\n\nint main() {\n\tprintf("hello world!\\n");\n\treturn 0;\n}\n')

# ================================================================ 命名空间

eq("!! 声明 + 全名引用",
   """\
dir top @
	file<c> a;
~@

file<c> a @
	<< x::helper >>
~@

!! x::
<< helper >>= @
	int helper;
~@
~::
""",
   "a.c", "int helper;\n")

eq("!! 嵌套糖",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	<< x::y::z >>
~@
!! x::y::
<< z >>= @
	int z;
~@
~::~::
""",
   "a.c", "int z;\n")

eq("块名自带全名",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	<< d::e::f::g >>
~@
<< d::e::f::g >>= @
	int g;
~@
""",
   "a.c", "int g;\n")

eq("chunk 体内短名在当前 ns 解析",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	<< x::outer >>
~@
!! x::
<< outer >>= @
	<< inner >>
	<< inner >>
~@
<< inner >>= @
	int inner;
~@
~::
""",
   "a.c", "int inner;\nint inner;\n")

eq("使用处引入（file 体，跨行）",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	x::
		<<helper>>
	~::
~@
!! x::
<< helper >>= @
	int helper;
~@
~::
""",
   "a.c", "int helper;\n")

eq("使用处引入（紧凑单行）",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	x:: <<helper>> ~::
~@
!! x::
<< helper >>= @
	int helper;
~@
~::
""",
   "a.c", "int helper;\n")

eq("多层引入 + 嵌套关闭",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	what::the::fuck::  <<c>> ~::~::~::
~@
!! what::
	!! the::
		!! fuck::
			<< c >>= @
				int c;
			~@
		~::
	~::
~::
""",
   "a.c", "int c;\n")

# ================================================================ | 接线

eq("| 等价换行",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	<<one>> | <<two>> | <<three>>
~@
<< one >>= @
	1
~@
<< two >>= @
	2
~@
<< three >>= @
	3
~@
""",
   "a.c", "1\n\n2\n\n3\n")

eq("| 与换行混用",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	<<one>> | <<two>>
	<<three>>
~@
<< one >>= @
	1
~@
<< two >>= @
	2
~@
<< three >>= @
	3
~@
""",
   "a.c", "1\n\n2\n\n3\n")

# ================================================================ 缩进

eq("chunk 体剥公共缩进",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	<< x >>
~@
<< x >>= @
		if (a) {
			b();
		}
~@
""",
   "a.c", "if (a) {\n\tb();\n}\n")

eq("chunk 体内实例缩进叠加",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	<< outer >>
~@
<< outer >>= @
	int outer() {
		<< inner >>
	}
~@
<< inner >>= @
	inner();
~@
""",
   "a.c", "int outer() {\n\tinner();\n}\n")

# ================================================================ 错误

bad("!! 内引用根：不回退",
    """\
dir top @
	file<c> a;
~@
file<c> a @
	<< x::outer >>
~@
<< include >>= @
	#include<stdio.h>
~@
!! x::
<< outer >>= @
	<< include >>
~::
""",
    "未定义的 chunk：x::include")

bad("chunk 重复实现",
    """\
dir top @
	file<c> a;
~@
<< x >>= @
	1
~@
<< x >>= @
	2
~@
""",
    "chunk x 重复实现")

bad("实例化未定义的 chunk",
    """\
dir top @
	file<c> a;
~@
file<c> a @
	<< ghost >>
~@
""",
    "未定义的 chunk：ghost")

bad("循环实例化",
    """\
dir top @
	file<c> a;
~@
file<c> a @
	<< p >>
~@
<< p >>= @
	<< q >>
~@
<< q >>= @
	<< p >>
~@
""",
    "循环实例化")

bad("file 体内非实例内容",
    """\
dir top @
	file<c> a;
~@
file<c> a @
	这是散文，不该出现在 file 体里
~@
""",
    "file 体内只能是 chunk 实例")

bad("chunk 体内定义 chunk",
    """\
dir top @
	file<c> a;
~@
file<c> a @
	<< outer >>
~@
<< outer >>= @
	<< inner >>= @
		x
	~@
~@
""",
    "chunk 体内不能再定义 chunk")

bad("同一 dir 挂载两次",
    """\
dir top @
	dir sub;
~@
dir other @
	dir sub;
~@
dir sub @
~@
""",
    "挂载了 2 次")

bad("物理路径冲突（dir 与无类型 file 同名）",
    """\
dir top @
	dir x;
	file x;
~@
file<c> a @
	<< i >>
~@
<< i >>= @
	i
~@
""",
    "物理路径冲突")

ok("同名不同类型不冲突",
   """\
dir top @
	file<c> x;
	file<py> x;
~@
file<c> x @
	<< a >>
~@
file<py> x @
	<< a >>
~@
<< a >>= @
	a
~@
""")

ok("骨架先行：挂载未定义的 dir/file 是空内容",
   """\
dir top @
	dir placeholder;
	file<md> TODO;
~@
""")

bad("缺少 top",
    """\
file<c> a @
	<< x >>
~@
<< x >>= @
	x
~@
""",
    "缺少 dir top")

bad("命名空间与 chunk 同名",
    """\
dir top @
	file<c> a;
~@
file<c> a @
	<< x >>
~@
<< x >>= @
	body
~@
!! x::
<< y >>= @
	y
~@
~::
""",
    "命名空间 x 与同名 chunk 冲突")

bad("挂载写在 dir 外",
    """\
dir ghost;
""",
    "挂载必须写在某个 dir 体内")

# ================================================================ 警告

warn("不可达 chunk",
     """\
dir top @
	file<c> a;
~@
file<c> a @
	<< used >>
~@
<< used >>= @
	u
~@
<< unused >>= @
	n
~@
""",
     "不可达")

warn("未挂载的 file",
     """\
dir top @
	file<c> a;
~@
file<c> a @
	<< used >>
~@
<< used >>= @
	u
~@
file<md> orphan @
	<< used >>
~@
""",
     "orphan<md> 已定义但未挂载")

# ================================================================ 汇总

if fails:
    for f in fails:
        print("FAIL " + f)
    print(f"\n{len(fails)} 例失败，{passed} 例通过")
    sys.exit(1)
print(f"全部通过（{passed} 例）")
