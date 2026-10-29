#!/usr/bin/env python3
"""破点的基准：三种形状 × 两个命令，打一张表。

跑法：
    python3 bench_bootstrap.py                # 量同目录的 bootstrap.py
    python3 bench_bootstrap.py --nw old.py    # 量另一份实现（比如 git show HEAD:bootstrap.py > old.py）

三种形状各对应一种会退化的病：

    wide     一个文件挂 8000 块       —— 常态，必须一直是 150 ms 量级
    chain    2000 层一条引用链        —— 递归实现在这里撞栈
    diamond  22 层、每层三个出口      —— 按路径走图的实现在这里指数爆炸

它不是 make 目标：基准给的是"这一次的数字"，没有过与不过。判回归交给
test_bootstrap.py 的规模用例——那里有超时，慢到不像话就是失败。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))

BOOK = """\
book bench @
	essay t.nw;
~@
"""


def wide(n):
    """一个文件挂 n 块，每块三行：宽而不深。"""
    s = ["dir top @", "\tfile<c> a;", "~@", "file<c> a @"]
    s += [f"\t<< w{i} >>" for i in range(n)]
    s.append("~@")
    for i in range(n):
        s += [f"<< w{i} >>= @", f"\tint v{i} = {i};", "\t<< tail >>", "~@"]
    s += ["<< tail >>= @", "\treturn 0;", "~@"]
    return "\n".join(s) + "\n"


def chain(n):
    """n 层一条链：c0 → c1 → … → c(n-1)，每层一行字。"""
    s = ["dir top @", "\tfile<c> a;", "~@", "file<c> a @", "\t<< c0 >>", "~@"]
    for i in range(n):
        s.append(f"<< c{i} >>= @")
        s.append(f"\tl{i}")
        if i < n - 1:
            s.append(f"\t<< c{i + 1} >>")
        s.append("~@")
    return "\n".join(s) + "\n"


def diamond(n, exits=3):
    """n 层、每层 exits 个出口：块数只有 n，路径数是 exits^(n-1)。"""
    s = ["dir top @", "\tfile<c> a;", "~@", "file<c> a @", "\t<< d0 >>", "~@"]
    for i in range(n):
        s.append(f"<< d{i} >>= @")
        s += [f"\t<< d{i + 1} >>"] * exits if i < n - 1 else ["\tx"]
        s.append("~@")
    return "\n".join(s) + "\n"


# 形状、块数、生成器、tangle 那列要不要测（diamond 的展开本身是指数行数）
CASES = [
    ("wide", 8000, wide, ""),
    ("chain", 2000, chain, ""),
    ("diamond", 22, diamond, "不测（产物 3^21 行）"),
]


def timed(nw, args, cwd, timeout):
    """跑一次，返回 (毫秒, 说明)。崩了或超时则毫秒为 None，说明里写原因。"""
    t0 = time.perf_counter()
    try:
        r = subprocess.run([sys.executable, nw] + args, cwd=cwd,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f">{timeout:g}s"
    ms = (time.perf_counter() - t0) * 1000
    if r.returncode != 0:
        lines = (r.stdout + r.stderr).strip().splitlines()
        return None, (lines[-1][:48] if lines else f"rc={r.returncode}")
    return ms, ""


def cell(ms, note):
    if note:
        return note
    return f"{ms:.0f} ms"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--nw", default=os.path.join(HERE, "bootstrap.py"),
                    help="要量的实现（默认：同目录的 bootstrap.py）")
    ap.add_argument("--timeout", type=float, default=30,
                    help="单次上限，秒（默认 30）；旧实现在 chain 上会崩，在两处会超时")
    o = ap.parse_args(argv[1:])

    print(f"nw: {o.nw}")
    print(f"{'形状':<9}{'块数':>6}{'check':>12}{'tangle':>22}")
    for name, n, gen, tangle_note in CASES:
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "t.nw"), "w", encoding="utf-8") as f:
                f.write(gen(n))
            with open(os.path.join(d, "book.nw"), "w", encoding="utf-8") as f:
                f.write(BOOK)
            src = ["book.nw", "t.nw"]
            c_ms, c_note = timed(o.nw, ["check"] + src, d, o.timeout)
            if tangle_note:
                t_cell = tangle_note
            else:
                t_ms, t_note = timed(o.nw, ["tangle", "-o", "out"] + src, d, o.timeout)
                t_cell = cell(t_ms, t_note)
        finally:
            shutil.rmtree(d)
        print(f"{name:<9}{n:>6}{cell(c_ms, c_note):>12}{t_cell:>22}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
