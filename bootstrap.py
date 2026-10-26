#!/usr/bin/env python3
"""元层：从零启动用的最小 tangle 器。

这是整个项目里唯一一段**故意手写**的实现。理由只有一条：
新克隆的目录里还没有任何东西能读 .nw，而构建规则本身要先由 .nw 展开出来。
这个循环必须有一个破点，破点就是这里。

它只做 tangle：
  - 不 weave（那是 tangle/nw.cpp 的正事）
  - 不做色彩、不做 HTML
  - 错误信息只有"第几行、什么错"，不分等级

等 tangle/build/nw 编出来之后，本项目其余部分全部由它生成；这个文件保持手写、
保持小。它的价值是"永远能跑"，不是"功能完整"——所以**功能不要往这里加**。

它与 tangle/nw.cpp 必须对同一份 .nw 给出同样的结果，这一点由 `make crosscheck`
检查（两个实现各自展开 nw.nw，逐字节比对）。改语法时两边都要改，别指望自举会
替你发现分歧。

用法: python3 bootstrap.py <in.nw> <outdir>
"""

import os
import re
import sys

HEAD = re.compile(r"^<<(.+)>>=\s*$")



def _fence_literal(body):
    """体里的围栏：栏本身删掉，栏内每一行加 `\\x02` 前缀。

    围栏里是字面文本——被生成的源码里本来就会有 `~@`、`<< x >>`、花括号，
    它们都不是这份 .nw 的语法。加前缀之后，后面所有扫描（收尾、嵌套、引用、
    剥缩进）都自动跳过这些行；落盘时再把前缀剥掉。
    """
    out, fence = [], None
    for ln in body.split("\n"):
        if fence:
            if re.match(r"^[ \t]*`{%d,}[ \t]*$" % len(fence), ln):
                fence = None
            else:
                out.append("\x02" + ln)
            continue
        m = re.match(r"^[ \t]*(`{3,})", ln)
        if m:
            fence = m.group(1)
            continue
        out.append(ln)
    return "\n".join(out)


def _split_braces(text, start):
    """从 text[start:] 起找配对的 }，跳过字符串与注释。返回 (体, 位置after})。"""
    depth = 1
    quote = None
    blk = False
    i = start
    fence = None
    while i < len(text):
        # 围栏里的花括号不算数：它们是字面文本。
        if i == 0 or text[i - 1] == "\n":
            j = text.find("\n", i)
            line = text[i:j] if j >= 0 else text[i:]
            if fence:
                if re.match(r"^[ \t]*`{%d,}[ \t]*$" % len(fence), line):
                    fence = None
                i = len(text) if j < 0 else j + 1
                continue
            mf = re.match(r"^[ \t]*(`{3,})", line)
            if mf:
                fence = mf.group(1)
                i = len(text) if j < 0 else j + 1
                continue
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif blk:
            if ch == "*" and i + 1 < len(text) and text[i + 1] == "/":
                blk = False
                i += 2
                continue
        elif ch in "\"'":
            quote = ch
        elif ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            j = text.find("\n", i)
            i = len(text) if j < 0 else j
            continue
        elif ch == "/" and i + 1 < len(text) and text[i + 1] == "*":
            blk = True
            i += 2
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
        i += 1
    return None, i




def _find_end_at(text, start):
    """从 start 起找配对的顶格 ~@（体里可以再嵌 `<< x >>= @`）。"""
    depth, i = 0, start
    fence = None
    while True:
        j = text.find("\n", i)
        if j < 0:
            return None, len(text)
        line = text[i:j]
        # 围栏里的 `~@` 与块头都是字面文本，不收尾也不加层。
        if fence:
            if re.match(r"^[ \t]*`{%d,}[ \t]*$" % len(fence), line):
                fence = None
            i = j + 1
            continue
        mf = re.match(r"^[ \t]*(`{3,})", line)
        if mf:
            fence = mf.group(1)
            i = j + 1
            continue
        if re.match(r"^[ \t]*<<.+?>>=[ \t]*@[ \t]*$", line):
            depth += 1
        elif line.strip() == "~@":
            if depth == 0:
                return text[start:i], j
            depth -= 1
        i = j + 1


def _flatten_at(body, sink):
    """体里嵌套的 `<< x >>= @ … ~@`：原处留引用，子块收集进 sink。"""
    lines = body.split("\n")
    out, i = [], 0
    while i < len(lines):
        m = re.match(r"^([ \t]*)<<(.+?)>>=[ \t]*@[ \t]*$", lines[i])
        if not m:
            out.append(lines[i]); i += 1; continue
        rest = "\n".join(lines[i:])
        sub, end = _find_end_at(rest, m.end())
        if sub is None:
            sys.exit("chunk 体没有闭合（缺少顶格的 ~@）：" + m.group(2).strip())
        used = rest[:end]
        deeper = []
        conv = _flatten_at(_flatten_refs(sub), deeper)
        out.append(m.group(1) + "<< " + m.group(2).strip() + " >>")
        sink.append((m.group(2).strip(), conv))
        sink.extend(deeper)
        i += used.count("\n") + 1
    return "\n".join(out)


def _flatten_refs(text):
    """`<< a >> | << b >>` 与分两行写等价：`|` 只是分隔符，拆成一行一个。"""
    out = []
    for ln in text.split("\n"):
        t = ln.strip()
        if "|" in t:
            segs = [x.strip() for x in t.split("|") if x.strip()]
            if segs and all(x.startswith("<<") and x.endswith(">>") for x in segs):
                w = len(ln) - len(ln.lstrip())
                out += [" " * w + x for x in segs]
                continue
        out.append(ln)
    return "\n".join(out)


def _flatten_nested(text, sink):
    """把体里的 `<< x >>= { ... }` 抽出来：原处留一行引用，子块收集进 sink。

    嵌套定义同时也是"放在这里"——原处那条引用就是位置。
    """
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        m = re.match(r"^([ \t]*)<<(.+?)>>=[ \t]*\{", lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        rest = "\n".join(lines[i:])
        body, pos = _split_braces(rest, m.end())
        if body is None:
            sys.exit("chunk 体没有闭合（缺少 }）：" + m.group(2).strip())
        used = rest[:pos]
        deeper = []
        sub = _flatten_nested(_flatten_refs(body), deeper)
        out.append(m.group(1) + "<< " + m.group(2).strip() + " >>")
        sink.append((m.group(2).strip(), sub))
        sink.extend(deeper)
        i += used.count("\n") + 1
    return "\n".join(out)


def to_v1(text):
    """把 v2 写法归一成 v1，喂给下面那台状态机。

    只做三件事：`名 @` → `@ 名`；`<< x >>= { 体 }` → `<<x>>=` + 体 + `@`；
    体内的 `@after X` → `@after: X`。围栏里的东西原样不动。
    """
    out = []
    lines = text.split("\n")
    i = 0
    fence = None
    while i < len(lines):
        ln = lines[i]
        if fence:
            out.append(ln)
            if re.match(r"^`{%d,}[ \t]*$" % len(fence), ln.rstrip()):
                fence = None
            i += 1
            continue
        m = re.match(r"^[ \t]*(`{3,})", ln)
        if m:
            fence = m.group(1)
            out.append(ln)
            i += 1
            continue

        if re.match(r"^[ \t]*<</", ln):
            # 头里带 / 的是写法示例（散文里的反引号内容），不动
            pass

        m = re.match(r"^([ \t]*)<<(.+?)>>=[ \t]*@[ \t]*$", ln)
        if m:
            indent, inner = m.group(1), m.group(2)
            rest = "\n".join(lines[i:])
            body, end = _find_end_at(rest, m.end())
            if body is None:
                sys.exit("chunk 体没有闭合（缺少顶格的 ~@）：" + inner.strip())
            used = rest[:end]
            children = []
            body = _flatten_refs(_flatten_at(_fence_literal(body), children))
            out.append(f"{indent}<<{inner}>>=")
            for l in body.split("\n"):
                st = l.strip()
                if st.startswith("@after ") or st.startswith("@before "):
                    key, _, val = st.partition(" ")
                    out.append(f"{key}: {val}")
                else:
                    out.append(l)
            out.append("@")
            for cname, cbody in children:
                out.append(f"<< {cname} >>=")
                out += cbody.split("\n")
                out.append("@")
            i += used.count("\n") + 1
            continue

        m = re.match(r"^([ \t]*)<<(.+?)>>=[ \t]*\{", ln)
        if m:
            indent, inner = m.group(1), m.group(2)
            body, pos = _split_braces(ln, m.end())
            if body is None:      # 跨行：把剩余行拼进来再找
                chunk = "\n".join(lines[i:])
                body, pos = _split_braces(chunk, m.end())
                if body is None:
                    sys.exit("chunk 体没有闭合（缺少 }）：" + inner.strip())
                used = chunk[:pos]
                rest_of_line = used.split("\n")[-1]
                i += used.count("\n") + 1
            else:
                rest_of_line = ln[pos:]
                i += 1
            children = []
            body = _flatten_nested(_flatten_refs(_fence_literal(body)), children)
            out.append(f"{indent}<<{inner}>>=")
            for l in body.split("\n"):
                st = l.strip()
                if st.startswith("@after ") or st.startswith("@before "):
                    key, _, val = st.partition(" ")
                    out.append(f"{key}: {val}")
                else:
                    out.append(l)
            out.append("@")
            for cname, cbody in children:
                out.append(f"<< {cname} >>=")
                out += cbody.split("\n")
                out.append("@")
            if rest_of_line.strip():
                out.append(rest_of_line)
            continue

        # `名字 @` 与 `@ 名字` 等价：统一成后者，状态机只认后者
        t = ln.strip()
        if t and t[0] not in "@~`<" and t.endswith("@") and " " in t:
            parts = t.split()
            if len(parts) == 2 and parts[1] == "@" and all(c.isalnum() or c in "._/-+~" for c in parts[0]):
                out.append("@ " + parts[0])
                i += 1
                continue

        out.append(ln)
        i += 1
    return "\n".join(out)


def parse(text):
    """切出 chunk：返回 ({名字: (体行列表, 产物路径或 None)}, 出现顺序)。"""
    chunks, order = {}, []
    cur = None
    raw = None
    path = None
    fence = None
    after = []
    ns = []

    text = to_v1(text)

    for no, ln in enumerate(text.split("\n"), 1):
        # 文档态：要么在示例围栏里（豁免），要么在找 chunk 头
        if cur is None:
            if fence:
                if re.match(r"^`{%d,}[ \t]*$" % len(fence), ln):
                    fence = None
                continue
            m = re.match(r"^[ \t]*(`{3,})", ln)
            if m:
                fence = m.group(1)
                continue
            # 文档态的命名空间：`@ 名` 进一层，`~@ [名]` 退一层（必须顶格）
            if ln[:1] in ("@", "~") and not ln.startswith("@todo:"):
                t = ln.rstrip()
                if t == "@":
                    pass  # 单独的 @ 是 chunk 终止符，不属于这里
                else:
                    k = 0
                    while k < len(t):
                        while k < len(t) and t[k] in " \t":
                            k += 1
                        if k >= len(t):
                            break
                        close = t.startswith("~@", k)
                        k += 2 if close else 1
                        while k < len(t) and t[k] in " \t":
                            k += 1
                        b = k
                        while k < len(t) and t[k] not in " \t@~":
                            k += 1
                        name = t[b:k]
                        if close:
                            if not ns:
                                sys.exit(f"{no}: ~@ 时没有打开的命名空间")
                            if name and name != ns[-1]:
                                sys.exit(f"{no}: ~@ 的名字对不上：栈顶是 {ns[-1]}，写的是 {name}")
                            ns.pop()
                        else:
                            if not name:
                                sys.exit(f"{no}: @ 后面缺少命名空间名")
                            check_path(name, no)
                            ns.append(name)
                    continue

            m = HEAD.match(ln)
            if m:
                name = m.group(1).strip()
                cut = -1
                for i, ch in enumerate(name):
                    if ch != ":":
                        continue
                    if i + 1 < len(name) and name[i + 1] == ":":
                        continue
                    if i and name[i - 1] == ":":
                        continue
                    cut = i
                    break
                if cut >= 0:
                    path, cur = name[:cut].strip(), name[cut + 1:].strip()
                    check_path(path, no)
                else:
                    path, cur = ("/".join(ns), name) if ns else ("", name)
                if not cur:
                    sys.exit(f"{no}: chunk 名为空")

                if (path, cur) in chunks:
                    who = f"{path} 的 {cur}" if path else cur
                    sys.exit(f"{no}: chunk 重定义 {who}")
                raw = []
                after = []
            continue

        # chunk 态里的围栏：栏本身不落盘，栏内每一行原样收（不当语法看）。
        # 标记 \x02 与 C++ 那边同义：字面行，落盘时剥掉。
        if fence:
            if re.match(r"^[ \t]*`{%d,}[ \t]*$" % len(fence), ln):
                fence = None
            else:
                raw.append("\x02" + ln)
            continue
        mf = re.match(r"^[ \t]*(`{3,})", ln)
        if mf:
            fence = mf.group(1)
            continue

        # chunk 态：顶格的 @ 收尾，收尾时剥掉最小公共缩进
        if ln.rstrip() == "@" and not ln[:1].isspace():
            # 首尾空行是块头与 @ 带来的，不属于内容
            while raw and not raw[0].strip():
                raw.pop(0)
            while raw and not raw[-1].strip():
                raw.pop()
            # 字面行的 \x02 先摘掉再算缩进，剥完公共缩进放回去（与 C++ 的 dedent 同义）：
            # 标记顶在行首会让这一行显得没有缩进，公共缩进就算成 0 了。
            lit = [k for k, l in enumerate(raw) if l.startswith("\x02")]
            for k in lit:
                raw[k] = raw[k][1:]
            widths = [len(l) - len(l.lstrip(" \t")) for l in raw if l.strip()]
            cut = min(widths) if widths else 0
            if not path and after:
                sys.exit(f"{no}: @after: 只能写在落盘块上（纯片段没有落盘顺序）：{cur}")
            body = [l[cut:].rstrip() for l in raw]
            for k in lit:
                body[k] = "\x02" + body[k]
            chunks[(path, cur)] = {"body": body, "path": path, "after": after}
            order.append((path, cur))
            cur = None
            raw = None
            continue


        # 体里的顶格 @after: 是顺序声明，摘出来不当代码
        if ln.startswith("@after:") and not ln[:1].isspace():
            after += [n.strip() for n in ln[len("@after:"):].split(",") if n.strip()]
            continue

        # 顶格的 @long 是开关式修饰符：只压"块太长"这条警告，不进产物
        if ln.strip() == "@long" and not ln[:1].isspace():
            continue

        raw.append(ln)

    if cur is not None:
        sys.exit(f"chunk 未闭合: {cur}")
    if ns:
        sys.exit(f"命名空间未闭合: {'/'.join(ns)}")
    return chunks, order


def check_path(path, no):
    """产物路径的合法性：写错要当场拒绝，而不是生成一个没人找得到的文件名。"""
    if not path:
        sys.exit(f"{no}: 产物路径不能为空")
    for c in path:
        if ord(c) < 32 or c in '"\'*?<>|':
            sys.exit(f"{no}: 产物路径里有非法字符 {c!r}：{path}")
    if path.startswith("/"):
        sys.exit(f"{no}: 产物路径要相对仓库根，不能以 / 开头：{path}")


def expand(chunks, name, indent="", stack=(), from_path="", from_chunk=""):
    """展开一个引用：按作用域逐级向上找名字，缩进累加到每一行。

    v2 里任何块都能被引用（骨架块引用子块就是最常见的情形），所以不再区分
    "纯片段"与"落盘块"——名字解析和 C++ 那边走同一条路。
    """
    key, p = None, from_path
    sc = from_chunk
    while sc:
        if (from_path, sc + "::" + name) in chunks:
            key = (from_path, sc + "::" + name)
            break
        sc = sc.rsplit("::", 1)[0] if "::" in sc else ""
    while key is None:
        if (p, name) in chunks:
            key = (p, name)
            break
        if not p:
            break
        p = p.rsplit("/", 1)[0] if "/" in p else ""
    if key is None:
        if ("", name) in chunks:
            key = ("", name)
        else:
            sys.exit(f"未定义的 chunk: {name}")
    if name in stack:
        sys.exit(f"chunk 循环引用: {name}")
    out = []
    for ln in chunks[key]["body"]:
        literal = ln.startswith("\x02")
        if literal:
            ln = ln[1:]
        m = None if literal else re.match(r"^([ \t]*)<<(.+)>>[ \t]*$", ln)
        if m:
            out += expand(chunks, m.group(2).strip(), indent + m.group(1), stack + (name,), key[0], key[1])
        else:
            out.append(indent + ln if ln else ln)
    return out


def order_product(chunks, keys, path):
    """把一组 chunk 排成落盘顺序：先满足 @after，其余保持文档顺序。

    拓扑排序：每轮从"前置都排好了"的块里挑文档位置最靠前的一个。
    """
    local = {k[1]: i for i, k in enumerate(keys)}
    nxt = [[] for _ in keys]
    left = [0] * len(keys)
    for i, k in enumerate(keys):
        for nm in chunks[k]["after"]:
            if nm not in local:
                sys.exit(f"@after 找不到同产物里的块: {nm}（产物 {path}）")
            nxt[local[nm]].append(i)
            left[i] += 1
    out, done = [], [False] * len(keys)
    while len(out) < len(keys):
        pick = None
        for i in range(len(keys)):
            if not done[i] and left[i] == 0:
                pick = i
                break
        if pick is None:
            stuck = "、".join(keys[i][1] for i in range(len(keys)) if not done[i])
            sys.exit(f"@after 成环，这些块互相等待: {stuck}")
        done[pick] = True
        out.append(keys[pick])
        for j in nxt[pick]:
            left[j] -= 1
    return out


def main():
    # 参数：[-o 输出目录] <in.nw> [more.nw …]
    # 多篇的意义：一本书可以拆成很多章节，而它们共同 tangle 出一个程序。
    args = sys.argv[1:]
    outdir, inputs = ".", []
    i = 0
    while i < len(args):
        if args[i] == "-o":
            if i + 1 >= len(args):
                sys.exit("用法: bootstrap.py [-o outdir] <in.nw> [more.nw …]")
            outdir = args[i + 1]
            i += 2
        else:
            inputs.append(args[i])
            i += 1
    # 兼容旧写法：bootstrap.py in.nw outdir
    if len(inputs) == 2 and not inputs[1].endswith(".nw"):
        outdir, inputs = inputs[1], inputs[:1]
    if not inputs:
        sys.exit("用法: bootstrap.py [-o outdir] <in.nw> [more.nw …]")

    # 各篇分别解析，再按传入顺序合并；重名必须报错，否则会出现两份定义。
    chunks, order = {}, []
    for src in inputs:
        with open(src, "r", encoding="utf-8") as f:
            c, o = parse(f.read())
        for key in o:
            if key in chunks:
                p, n = key
                who = f"{p} 的 {n}" if p else n
                sys.exit(f"chunk 重定义: {who}（另一篇里已定义过）")
            chunks[key] = c[key]
            order.append(key)

    # 按产物路径分组，组内顺序由 @after 决定，没有约束的保持文档顺序
    groups = {}
    for key in order:
        if key[0]:
            groups.setdefault(key[0], []).append(key)

    # 被别的块引用过的块不单独落盘：它的位置由引用处决定（C++ 那边叫 inside）。
    mentioned = set()
    for key in order:
        for ln in chunks[key]["body"]:
            mt = re.match(r"^[ \t]*<<(.+)>>[ \t]*$", ln)
            if mt:
                # 身份是 (路径, 名字)：只有"同一个产物里的同名块"才算被引用过。
                mentioned.add((key[0], mt.group(1).strip()))

    products = {}
    for path, keys in groups.items():
        products[path] = []
        for key in order_product(chunks, keys, path):
            if "::" in key[1] or (key[0], key[1]) in mentioned:
                continue
            # 块与块之间空一行；片段展开不插（那是"一句话换行"）
            if products[path] and products[path][-1].strip():
                products[path].append("")
            for ln in chunks[key]["body"]:
                literal = ln.startswith("\x02")
                if literal:
                    ln = ln[1:]
                m = None if literal else re.match(r"^([ \t]*)<<(.+)>>[ \t]*$", ln)
                if m:
                    products[path] += expand(chunks, m.group(2).strip(), m.group(1), (key[1],), key[0], key[1])
                else:
                    products[path].append(ln)

    for path, lines in products.items():

        path = path[:-1] if path.endswith("~") else path  # 末尾的 ~ 是"没后缀的文件"的转义，落盘时去掉
        dest = os.path.join(outdir, path)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"写出 {dest}（{len(lines)} 行）")


if __name__ == "__main__":
    main()
