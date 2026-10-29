#!/usr/bin/env python3
"""nw3 的用例。跑法：python3 test_nw3.py

v3 的每份源都要有一本书：用例把 t.nw 当成那一篇，另写一份 book.nw 收它。
篇的路径与命令行给的一致（都在临时目录里用相对路径），这是 merge 对号的方式。
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
NW3 = os.path.join(HERE, "nw3.py")

fails = []
passed = 0

# 默认的书：只收 t.nw。
BOOK = """\
book test @
	essay t.nw;
~@
"""


def _files(src, extra, book):
    # src 为 None：这一例不用默认的 t.nw（多篇的用例自己给 extra）。
    files = {"book.nw": book} if src is None else {"t.nw": src, "book.nw": book}
    if extra:
        files.update(extra)
    return files


def _write(d, files):
    for name, text in files.items():
        p = os.path.join(d, name)
        parent = os.path.dirname(p)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)


def _run(args, files):
    """把文件写进临时目录，在那里跑一次，返回 (returncode, stdout+stderr)。"""
    d = tempfile.mkdtemp()
    try:
        _write(d, files)
        names = sorted(files)
        r = subprocess.run([sys.executable, NW3] + args + names,
                           cwd=d, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr
    finally:
        shutil.rmtree(d)


def run(args, src, extra=None, book=BOOK):
    return _run(args, _files(src, extra, book))


def tangle_content(src, relpath, extra=None, book=BOOK):
    """跑 tangle，返回产物的内容（找不到返回 None）。"""
    d = tempfile.mkdtemp()
    try:
        files = _files(src, extra, book)
        _write(d, files)
        outdir = os.path.join(d, "out")
        r = subprocess.run([sys.executable, NW3, "tangle", "-o", outdir] + sorted(files),
                           cwd=d, capture_output=True, text=True)
        if r.returncode:
            raise AssertionError(f"tangle 失败：{r.stdout}{r.stderr}")
        target = os.path.join(outdir, relpath)
        if not os.path.exists(target):
            return None
        with open(target, encoding="utf-8") as f:
            return f.read()
    finally:
        shutil.rmtree(d)


def eq(name, src, relpath, want, extra=None, book=BOOK):
    global passed
    try:
        got = tangle_content(src, relpath, extra, book)
        if got != want:
            fails.append(f"{name}\n  got : {got!r}\n  want: {want!r}")
        else:
            passed += 1
    except AssertionError as e:
        fails.append(f"{name}\n  {e}")


def bad(name, src, needle, extra=None, book=BOOK):
    """check 必须失败，而且输出里有 needle。"""
    global passed
    rc, out = run(["check"], src, extra, book)
    if rc == 0:
        fails.append(f"{name}\n  没有报错")
    elif needle not in out:
        fails.append(f"{name}\n  got : {out.strip()}\n  want 含: {needle}")
    else:
        passed += 1


def ok(name, src, needle="", extra=None, book=BOOK):
    """check 必须通过。"""
    global passed
    rc, out = run(["check"], src, extra, book)
    if rc != 0:
        fails.append(f"{name}\n  不该报错却报了：{out.strip()}")
    elif needle and needle not in out:
        fails.append(f"{name}\n  输出里没有 {needle!r}：{out.strip()}")
    else:
        passed += 1


def warn(name, src, needle, extra=None, book=BOOK):
    """check 通过但有警告。"""
    global passed
    rc, out = run(["check"], src, extra, book)
    if rc != 0:
        fails.append(f"{name}\n  报错了：{out.strip()}")
    elif needle not in out:
        fails.append(f"{name}\n  警告里没有 {needle!r}：{out.strip()}")
    else:
        passed += 1


def ast_json(src, extra=None, book=BOOK):
    import json
    rc, out = run(["parse", "--ast"], src, extra, book)
    if rc != 0:
        raise AssertionError(f"parse --ast 失败：{out.strip()}")
    return json.loads(out)


def ast_case(name, src, check, extra=None, book=BOOK):
    """parse --ast 的 JSON 必须满足 check；check 返回 None 表示通过。"""
    global passed
    try:
        problem = check(ast_json(src, extra, book))
        if problem:
            fails.append(f"{name}\n  {problem}")
        else:
            passed += 1
    except Exception as e:  # noqa: BLE001 - 用例失败要汇总，不要中断
        fails.append(f"{name}\n  {e}")


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

# ================================================================ 追加接线

eq("dir 追加的糖：dir X += dir Y;",
   """\
dir top @
	dir a;
~@
dir a @
	file<c> one;
~@
dir top += dir b;
dir b @
	file<c> two;
~@
file<c> one @
	<< p >>
~@
file<c> two @
	<< q >>
~@
<< p >>= @
	p
~@
<< q >>= @
	q
~@
""",
   "b/two.c", "q\n")

eq("dir 追加的糖：dir X += file<t> Y;",
   """\
dir top @
	dir a;
~@
dir top += file<c> extra;
file<c> extra @
	<< p >>
~@
<< p >>= @
	p
~@
""",
   "extra.c", "p\n")

eq("纯 += ：第一次出现就是创建（dir 与 file）",
   """\
dir top @
~@
dir top += @
	dir sub;
~@
dir sub @
	file<c> a;
~@
file<c> a += @
	<< p >>
~@
<< p >>= @
	p
~@
""",
   "sub/a.c", "p\n")

eq("file 追加的糖：file<t> X += << c >>;",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	<< first >>
~@
file<c> a += << second >>;
<< first >>= @
	one
~@
<< second >>= @
	two
~@
""",
   "a.c", "one\n\ntwo\n")

eq("+= 与 @ 混用：同一对象的体按行号接在后面",
   """\
dir top @
	file<c> a;
~@
file<c> a += @
	<< first >>
~@
file<c> a += @
	<< second >>
~@
<< first >>= @
	one
~@
<< second >>= @
	two
~@
""",
   "a.c", "one\n\ntwo\n")

# ---- 篇序决定拼接顺序：同一批源，换书的次序，产物就跟着换 ----

ORDER_A = """\
dir top @
	file<c> x;
~@
file<c> x @
	<< one >>
~@
<< one >>= @
	A
~@
"""

ORDER_B = """\
file<c> x += @
	<< two >>
~@
<< two >>= @
	B
~@
"""

BOOK_AB = """\
book test @
	essay a.nw;
	essay b.nw;
~@
"""

BOOK_BA = """\
book test @
	essay b.nw;
	essay a.nw;
~@
"""

eq("分片按篇序拼接（a → b）",
   None, "x.c", "A\n\nB\n",
   extra={"a.nw": ORDER_A, "b.nw": ORDER_B}, book=BOOK_AB)

eq("分片按篇序拼接（b → a）",
   None, "x.c", "B\n\nA\n",
   extra={"a.nw": ORDER_A, "b.nw": ORDER_B}, book=BOOK_BA)

# ---- 书的结构 ----

NESTED_BOOK = """\
book test @
	name 测试书;
	part outer;
~@
part outer @
	name 外层;
	part inner;
	essay t.nw;
~@
part inner @
	name 内层;
~@
"""

ok("book / part 嵌套：先序展开通过检查",
   """\
dir top @
	file<c> a;
~@
file<c> a @
	<< p >>
~@
<< p >>= @
	p
~@
""",
   book=NESTED_BOOK)

bad("essay 收了输入里没有的篇",
    """\
dir top @
~@
""",
    "book 收了这一篇，但输入里没有：ghost.nw",
    book="""\
book test @
	essay t.nw;
	essay ghost.nw;
~@
""")

bad("part 引用了没有定义的部",
    """\
dir top @
~@
""",
    "引用了没有定义的 part：ghost",
    book="""\
book test @
	part ghost;
	essay t.nw;
~@
""")

bad("part 成环",
    """\
dir top @
~@
""",
    "part 成环",
    book="""\
book test @
	part a;
	essay t.nw;
~@
part a @
	part b;
~@
part b @
	part a;
~@
""")

bad("同一篇被收了两次",
    """\
dir top @
~@
""",
    "同一篇被收了两次",
    book="""\
book test @
	essay t.nw;
	essay t.nw;
~@
""")

bad("没有 book 定义",
    """\
dir top @
~@
""",
    "没有 book 定义",
    book="")

bad("book 定义两次",
    """\
dir top @
~@
""",
    "book 重复定义",
    book="""\
book test @
	essay t.nw;
~@
book test @
	essay t.nw;
~@
""")

bad("+= 到不存在的 book",
    """\
dir top @
~@
book other += essay t.nw;
""",
    "+= 到不存在的 book：other")

ast_case("未收录的 .nw 不进 AST",
         """\
dir top @
~@
""",
         lambda d: None if d["book"]["order"] == ["t.nw"] and "stray" not in d["chunks"]
         else f"未收录的篇还是进来了：{d['book']['order']} / {list(d['chunks'])}",
         extra={"stray.nw": """\
file<c> stray @
	<< s >>
~@
<< s >>= @
	stray
~@
"""})

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

bad("top 只能由 @ 建立：只写 += 报错",
   """\
dir top += @
	file<c> a;
~@
file<c> a @
	<< x >>
~@
<< x >>= @
	x
~@
""",
   "top 必须先 dir top @")

bad("同一个对象两次 @",
   """\
dir top @
~@
dir top @
~@
""",
   "dir top 重复定义")

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

# ================================================================ parse --ast

ast_case("parse --ast：book 先序与 file 实例",
         """\
dir top @
	file<c> a;
~@
file<c> a @
	<< p >>
~@
<< p >>= @
	p
~@
""",
         lambda d: None if d["book"]["order"] == ["t.nw"]
         and d["files"]["a<c>"]["insts"] == ["p"]
         else f"结构不对：{d['book']} / {d['files']}")

# ================================================================ 汇总

if fails:
    for f in fails:
        print("FAIL " + f)
    print(f"\n{len(fails)} 例失败，{passed} 例通过")
    sys.exit(1)
print(f"全部通过（{passed} 例）")
