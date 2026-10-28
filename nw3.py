#!/usr/bin/env python3
"""neoweb v3 原型：parse → AST（chunk 树 + 代码树）→ check → tangle。

对着 book/Chapter 2/granmmerv3.nw 实现。这是验证语法的原型，不是 C++ 实现。

用法：
    python3 nw3.py check  源.nw
    python3 nw3.py tangle -o 输出目录 源.nw
    python3 nw3.py ast    源.nw
"""

import json
import re
import sys
from dataclasses import dataclass, field

# ---------------------------------------------------------------- 类型 → 后缀

TYPE_SUFFIX = {
    "c": ".c", "h": ".h", "cpp": ".cpp", "hpp": ".hpp", "cc": ".cc",
    "py": ".py", "md": ".md", "nw": ".nw", "json": ".json",
    "yaml": ".yaml", "yml": ".yml", "html": ".html", "css": ".css",
    "js": ".js", "ts": ".ts", "sh": ".sh", "txt": ".txt",
    "cu": ".cu", "svg": ".svg",
    "makefile": "", "license": "", "gitignore": "",
}

# ---------------------------------------------------------------- AST 节点


@dataclass
class Inst:
    """一次 chunk 实例化。"""
    name: str        # 写在 << >> 里的名字（可能是短名，靠 ns 解析）
    ns: tuple        # 实例所在行的命名空间（段元组）
    no: int          # 源行号


@dataclass
class Line:
    """chunk 体里的一行。"""
    kind: str        # code | lit | inst
    text: str        # code/lit 的文本；inst 时空
    no: int
    names: list = field(default_factory=list)   # inst：一行可有多实例
    ns: tuple = ()                              # inst：解析所在 ns
    indent: str = ""                            # inst：行缩进


@dataclass
class Chunk:
    name: str       # 全名（ns 段 + 短名，:: 连接）
    lines: list
    no: int
    mounted: int = 0     # 被实例化次数（check 用）
    todo: bool = False   # 体首行 @todo：还没写完，展开成空


@dataclass
class Mount:
    kind: str       # dir | file
    name: str
    type: str       # file 的类型；dir 为 None
    no: int


@dataclass
class DirNode:
    name: str
    mounts: list = field(default_factory=list)   # Mount，保持文档顺序
    mounted: int = 0


@dataclass
class FileNode:
    name: str
    type: str
    body: list = field(default_factory=list)     # Inst，保持文档顺序
    mounted: int = 0
    no: int = 0


class NWError(Exception):
    def __init__(self, no, msg):
        super().__init__(msg)
        self.no = no
        self.msg = msg


# ---------------------------------------------------------------- 正则

RE_DIR_DEF    = re.compile(r"^dir\s+([\w.-]+)\s*@\s*$")
RE_DIR_MOUNT  = re.compile(r"^dir\s+([\w.-]+)\s*;\s*$")
RE_FILE_DEF   = re.compile(r"^file(?:<([\w-]+)>)?\s+([\w.-]+)\s*@\s*$")
RE_FILE_MOUNT = re.compile(r"^file(?:<([\w-]+)>)?\s+([\w.-]+)\s*;\s*$")
RE_CHUNK_DEF  = re.compile(r"^<<\s*(.+?)\s*>>=\s*@\s*$")
RE_CLOSE      = re.compile(r"^~@\s*$")
RE_NS_DECL    = re.compile(r"^!!\s*((?:[\w.-]+::)+)\s*$")
RE_NS_POP     = re.compile(r"^((?:~::)+)\s*$")
# 行首使用处引入：ident:: 重复若干次，后面可以跟别的东西
RE_NS_USE     = re.compile(r"^((?:[\w.-]+::)+)(.*)$")
# 整行全是实例（可 | 连接）
RE_INSTS      = re.compile(r"^(<<[^>]*>>)(?:\s*\|\s*<<[^>]*>>)*\s*$")
RE_ONE_INST   = re.compile(r"<<\s*([^<>]+?)\s*>>")
RE_FENCE      = re.compile(r"^(`{3,})")


def ns_join(segs, short=""):
    parts = list(segs) + ([short] if short else [])
    return "::".join(parts)


def strip_comment(ln, no):
    """块外注释：成对 %% 之间删掉；反引号里是字面。"""
    out = []
    i = 0
    while i < len(ln):
        if ln[i] == "`":
            e = ln.find("`", i + 1)
            if e == -1:
                out.append(ln[i])
                i += 1
                continue
            out.append(ln[i:e + 1])
            i = e + 1
            continue
        if ln[i:i + 2] == "%%":
            e = ln.find("%%", i + 2)
            if e == -1:
                raise NWError(no, "注释没有闭合：%%")
            i = e + 2
            continue
        out.append(ln[i])
        i += 1
    return "".join(out)


def leading_ws(s):
    n = 0
    for ch in s:
        if ch in " \t":
            n += 1
        else:
            break
    return n


# ---------------------------------------------------------------- 解析器


class Parser:
    def __init__(self, src, fname):
        self.fname = fname
        self.raw = src.split("\n")
        self.chunks = {}          # 全名 → Chunk
        self.dirs = {}            # name → DirNode
        self.files = {}           # (name, type) → FileNode
        self.ns_decls = set()     # 声明过的 ns 全名
        self.errors = []
        self.warnings = []
        self.prose = []           # (行号, 文本)，给 weave 留的
        self.block = []           # ('dir', DirNode) | ('file', FileNode) | ('chunk', Chunk)
        self.ns = []              # 当前命名空间段栈
        self.fence = ""           # 非空 = 围栏内
        self.cur_lines = None     # 正在收的 chunk 体

    def err(self, no, msg):
        self.errors.append(f"{self.fname}:{no}: {msg}")

    def warn(self, no, msg):
        self.warnings.append(f"{self.fname}:{no}: {msg}")

    # ------------------------------------------------ 解析一行

    def feed(self, no, raw):
        # 围栏内：原样。块外结构层与 chunk 体统一处理。
        if self.fence:
            if self._in_chunk():
                self.cur_lines.append(Line("lit", raw, no))
            # else: 结构层围栏里的行忽略（weave 用）
            if raw.strip().startswith(self.fence):
                self.fence = ""
            return
        m = RE_FENCE.match(raw.strip())
        if m and not self._in_file():
            # file 体内不允许围栏
            self.fence = m.group(1)
            return

        if self._in_chunk():
            self._chunk_line(no, raw)
        elif self._in_file():
            self._file_line(no, raw)
        else:
            self._struct_line(no, raw)

    def _in_chunk(self):
        return bool(self.block) and self.block[-1][0] == "chunk"

    def _in_file(self):
        return bool(self.block) and self.block[-1][0] == "file"

    def _in_dir(self):
        return bool(self.block) and self.block[-1][0] == "dir"

    # ------------------------------------------------ 结构层（文档态 / dir 体）

    def _struct_line(self, no, raw):
        try:
            ln = strip_comment(raw, no)
        except NWError as e:
            self.err(no, e.msg)
            ln = raw
        t = ln.strip()
        if not t:
            return

        if RE_CLOSE.match(t):
            self._close_block(no)
            return
        m = RE_NS_POP.match(t)
        if m:
            n = m.group(1).count("~::")
            if n > len(self.ns):
                self.err(no, "~:: 没有对应的开层")
            else:
                del self.ns[len(self.ns) - n:]
            return
        m = RE_NS_DECL.match(t)
        if m:
            if self._in_file():
                self.err(no, "file 体内不能声明命名空间（!! 只在块外）")
                return
            for seg in m.group(1).split("::"):
                if not seg:
                    continue
                self.ns.append(seg)
                self.ns_decls.add(ns_join(self.ns))
            return
        m = RE_NS_USE.match(t)
        if m and m.group(1) and not self._in_file():
            # 结构层出现使用处引入：要么是散文碰巧以 xxx:: 开头，要么是错写
            self.err(no, f"命名空间引入 {m.group(1)!r} 只能写在 file 体或 chunk 体内")
            return

        # 定义与挂载
        m = RE_DIR_DEF.match(t)
        if m:
            if self._in_file():
                self.err(no, "file 体内不能定义 dir")
                return
            name = m.group(1)
            if name == "top" and any(k == "top" for k in self.dirs):
                self.err(no, "top 已经定义过")
                return
            if name in self.dirs:
                self.err(no, f"dir {name} 重复定义")
                return
            self.block.append(("dir", DirNode(name, [])))
            self.dirs[name] = self.block[-1][1]
            return
        m = RE_DIR_MOUNT.match(t)
        if m:
            self._mount(no, "dir", m.group(1), None)
            return
        m = RE_FILE_DEF.match(t)
        if m:
            if self._in_file():
                self.err(no, "file 体内不能定义 file")
                return
            typ, name = m.group(1), m.group(2)
            if typ and typ not in TYPE_SUFFIX:
                self.err(no, f"未知文件类型 <{typ}>")
                return
            key = (name, typ)
            if key in self.files:
                self.err(no, f"file {name}<{typ}> 重复定义")
                return
            node = FileNode(name, typ, [], no=no)
            self.files[key] = node
            self.block.append(("file", node))
            return
        m = RE_FILE_MOUNT.match(t)
        if m:
            self._mount(no, "file", m.group(2), m.group(1))
            return
        m = RE_CHUNK_DEF.match(t)
        if m:
            if self._in_file():
                self.err(no, "file 体内不能定义 chunk（file 体只能实例化）")
                return
            name = m.group(1)
            full = self._chunk_fullname(name, no)
            if full is None:
                return
            if full in self.chunks:
                self.err(no, f"chunk {full} 重复实现")
                return
            ch = Chunk(full, [], no)
            self.chunks[full] = ch
            self.block.append(("chunk", ch))
            self.cur_lines = ch.lines
            return

        # 其余是散文
        self.prose.append((no, ln))

    def _chunk_fullname(self, name, no):
        segs = name.split("::")
        for s in segs:
            if not s.strip():
                self.err(no, f"chunk 名 {name!r} 有空段")
                return None
            if any(c in s for c in "<>:"):
                self.err(no, f"chunk 名 {name!r} 含非法字符（<>:）")
                return None
        return ns_join(self.ns, name) if "::" not in name else name

    def _mount(self, no, kind, name, typ):
        # 挂载必须发生在某个 dir 体内（top 或下层）
        if not self._in_dir():
            self.err(no, f"{'dir' if kind == 'dir' else 'file'} {name} 的挂载必须写在某个 dir 体内")
            return
        if kind == "file":
            if typ and typ not in TYPE_SUFFIX:
                self.err(no, f"未知文件类型 <{typ}>")
                return
        self.block[-1][1].mounts.append(Mount(kind, name, typ, no))

    def _close_block(self, no):
        if not self.block:
            self.err(no, "~@ 没有对应的开层")
            return
        kind, node = self.block.pop()
        if kind == "chunk":
            self._dedent(node)
            self.cur_lines = None

    # ------------------------------------------------ file 体

    @staticmethod
    def _ns_intro(t):
        """判断一行是不是"使用处命名空间引入"。
        必须满足：ns 前缀之后是空、实例串、或实例串+行尾 ~:: 串。
        否则视为普通内容（chunk 体里的 std::cout 这类代码不能被误吞）。"""
        m = RE_NS_USE.match(t)
        if not m or not m.group(1):
            return None
        rest = m.group(2).strip()
        tail = re.search(r"((?:~::)+)\s*$", rest) if rest else None
        core = rest[:tail.start()].strip() if tail else rest
        if core == "" or RE_INSTS.match(core):
            return m.group(1), rest
        return None

    def _file_line(self, no, raw):
        try:
            ln = strip_comment(raw, no)
        except NWError as e:
            self.err(no, e.msg)
            ln = raw
        t = ln.strip()
        if RE_CLOSE.match(t):
            self._close_block(no)
            return
        pushed = 0
        popped = 0
        intro = self._ns_intro(t)
        if intro:
            for seg in intro[0].split("::"):
                if seg:
                    self.ns.append(seg)
                    pushed += 1
            t = intro[1].strip()
        elif RE_NS_POP.match(t):
            popped = t.count("~::")
            t = ""
        if t:
            # 行尾 ~:: 串（紧凑写法：x:: <<a>> ~::）
            tail = re.search(r"((?:~::)+)\s*$", t)
            if tail:
                popped += tail.group(1).count("~::")
                t = t[:tail.start()].strip()
        if t:
            if not RE_INSTS.match(t):
                self.err(no, f"file 体内只能是 chunk 实例，出现：{t!r}")
            else:
                node = self.block[-1][1]
                for nm in RE_ONE_INST.findall(t):
                    node.body.append(Inst(nm, tuple(self.ns), no))
        if popped:
            if popped > len(self.ns):
                self.err(no, "~:: 没有对应的开层")
                popped = len(self.ns)
            del self.ns[len(self.ns) - popped:]

    # ------------------------------------------------ chunk 体（不剥注释）

    def _chunk_line(self, no, raw):
        t = raw.strip()
        if RE_CLOSE.match(t):
            self._close_block(no)
            return
        pushed = 0
        popped = 0
        intro = self._ns_intro(t)
        if intro:
            for seg in intro[0].split("::"):
                if seg:
                    self.ns.append(seg)
                    pushed += 1
            t = intro[1].strip()
        if t:
            tail = re.search(r"((?:~::)+)\s*$", t)
            if tail:
                popped += tail.group(1).count("~::")
                t = t[:tail.start()].strip()
        if t:
            if RE_INSTS.match(t):
                self.cur_lines.append(Line(
                    "inst", "", no,
                    names=RE_ONE_INST.findall(t),
                    ns=tuple(self.ns),
                    indent=raw[:leading_ws(raw)],
                ))
            elif RE_CHUNK_DEF.match(t):
                self.err(no, "chunk 体内不能再定义 chunk")
            else:
                self.cur_lines.append(Line("code", raw.rstrip(), no))
        elif pushed or popped:
            pass  # 只有 ns 开关的行
        else:
            self.cur_lines.append(Line("code", "", no))
        if popped:
            if popped > len(self.ns):
                self.err(no, "~:: 没有对应的开层")
                popped = len(self.ns)
            del self.ns[len(self.ns) - popped:]

    # ------------------------------------------------ chunk 体 dedent

    def _dedent(self, ch):
        lines = ch.lines
        # 体首行 @todo（也认 @todo:）：这块还没写完
        if lines and lines[0].kind == "code" and lines[0].text.strip() in ("@todo", "@todo:"):
            ch.todo = True
            lines.pop(0)
        # 剥首尾空行
        while lines and lines[0].kind == "code" and not lines[0].text.strip():
            lines.pop(0)
        while lines and lines[-1].kind == "code" and not lines[-1].text.strip():
            lines.pop()
        # 最小公共缩进：code/lit/inst 行都参与（inst 按行首缩进算）
        m = -1
        for ln in lines:
            if ln.kind == "inst":
                w = len(ln.indent)
            else:
                if not ln.text.strip():
                    continue
                w = leading_ws(ln.text)
            if m < 0 or w < m:
                m = w
        if m <= 0:
            for ln in lines:
                if ln.kind in ("code", "lit"):
                    ln.text = ln.text.rstrip()
            return
        for ln in lines:
            if ln.kind == "inst":
                ln.indent = ln.indent[m:] if len(ln.indent) >= m else ""
            elif len(ln.text) >= m:
                ln.text = ln.text[m:].rstrip()
            else:
                ln.text = ""

    # ------------------------------------------------ 入口

    def run(self):
        for i, raw in enumerate(self.raw, 1):
            self.feed(i, raw)
        if self.block:
            for kind, node in self.block:
                self.err(0, f"{kind} {getattr(node, 'name', '?')} 没有闭合")
        if self.ns:
            self.err(0, f"命名空间 {ns_join(self.ns)} 没有闭合")
        return self


# ---------------------------------------------------------------- 解析 + 检查


class Document:
    def __init__(self, src, fname):
        self.p = Parser(src, fname).run()
        self.fname = fname
        self.chunks = self.p.chunks
        self.dirs = self.p.dirs
        self.files = self.p.files
        self.errors = list(self.p.errors)
        self.warnings = list(self.p.warnings)

    @classmethod
    def from_files(cls, paths):
        """多篇合并成一份文档：chunk 表、dir/file 树、命名空间表都并起来。"""
        docs = []
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                docs.append(cls(fh.read(), path))
        if len(docs) == 1:
            return docs[0]
        d = cls.__new__(cls)
        d.fname = paths[0]
        d.p = docs[0].p
        d.chunks = {}
        d.dirs = {}
        d.files = {}
        d.errors = []
        d.warnings = []
        for sub in docs:
            for k, v in sub.chunks.items():
                if k in d.chunks:
                    d.errors.append(
                        f"{sub.fname}:{v.no}: chunk {k} 在两篇里都实现了"
                        f"（{d.chunks[k].no} 行也有一个）")
                else:
                    d.chunks[k] = v
            for k, v in sub.dirs.items():
                if k in d.dirs and d.dirs[k].mounts:
                    d.errors.append(f"{sub.fname}:0: dir {k} 在两篇里都定义过")
                else:
                    d.dirs.setdefault(k, v)
            for k, v in sub.files.items():
                if k in d.files and d.files[k].body:
                    d.errors.append(f"{sub.fname}:{v.no}: file {k[0]}<{k[1]}> 在两篇里都定义过")
                else:
                    d.files.setdefault(k, v)
            d.p.ns_decls |= sub.p.ns_decls
            d.errors += sub.errors
            d.warnings += sub.warnings
        return d

    def resolve(self, name, ns):
        """名字解析：显式全名直接查；短名拼当前 ns。不回退。"""
        if "::" in name:
            full = name
        else:
            full = ns_join(ns, name)
        if full not in self.chunks:
            raise KeyError(full)
        return self.chunks[full]

    # ------------------------------------------------ 检查

    def check(self):
        # 1. 挂载解析：未定义的挂载创建空节点（骨架先行的写法）
        for d in list(self.dirs.values()):
            for mt in d.mounts:
                if mt.kind == "dir":
                    if mt.name not in self.dirs:
                        self.dirs[mt.name] = DirNode(mt.name, [])
                else:
                    key = (mt.name, mt.type)
                    if key not in self.files:
                        self.files[key] = FileNode(mt.name, mt.type, [])
        # 2. top 必须存在
        if "top" not in self.dirs:
            self.errors.append(f"{self.fname}:0: 缺少 dir top（tangle 的根）")

        # 3. 挂载唯一性：每个 dir/file 至多挂一次
        for d in self.dirs.values():
            for mt in d.mounts:
                if mt.kind == "dir":
                    if mt.name in self.dirs:
                        self.dirs[mt.name].mounted += 1
                elif (mt.name, mt.type) in self.files:
                    self.files[(mt.name, mt.type)].mounted += 1
        for name, d in self.dirs.items():
            if name == "top":
                continue
            if d.mounted == 0:
                self.warnings.append(f"{self.fname}:0: dir {name} 已定义但未挂载")
            elif d.mounted > 1:
                self.errors.append(
                    f"{self.fname}:0: dir {name} 挂载了 {d.mounted} 次（声明位置唯一）")
        for (name, typ), f in self.files.items():
            if f.mounted == 0:
                self.warnings.append(
                    f"{self.fname}:0: file {name}<{typ or '无类型'}> 已定义但未挂载")
            elif f.mounted > 1:
                self.errors.append(
                    f"{self.fname}:0: file {name}<{typ or '无类型'}> 挂载了 {f.mounted} 次")

        # 4. 实例解析 + 循环检测
        for f in self.files.values():
            for inst in f.body:
                self._check_inst(inst, [])
        for ch in self.chunks.values():
            for ln in ch.lines:
                if ln.kind != "inst":
                    continue
                for nm in ln.names:
                    self._check_inst(Inst(nm, ln.ns, ln.no), [ch.name])

        # 5. 不可达 chunk（无实例化）
        for name, ch in self.chunks.items():
            if ch.mounted == 0:
                self.warnings.append(
                    f"{self.fname}:{ch.no}: chunk {name} 不可达（实现了但没有实例化）")

        # 6. ns 名与 chunk 名冲突（同一全名即同一父作用域下的同名）
        for full in self.p.ns_decls:
            if full in self.chunks:
                self.errors.append(
                    f"{self.fname}:0: 命名空间 {full} 与同名 chunk 冲突")

        # 7. 物理路径唯一
        seen = {}
        self._walk_paths("", self.dirs.get("top"), seen)
        return self.errors, self.warnings

    def _check_inst(self, inst, stack):
        try:
            ch = self.resolve(inst.name, inst.ns)
        except KeyError:
            full = inst.name if "::" in inst.name else ns_join(inst.ns, inst.name)
            msg = f"{self.fname}:{inst.no}: 未定义的 chunk：{full}"
            if msg not in self.errors:
                self.errors.append(msg)
            return
        ch.mounted += 1
        if ch.name in stack:
            self.errors.append(
                f"{self.fname}:{inst.no}: chunk 循环实例化：{' → '.join(stack + [ch.name])}")
            return
        if ch.todo:
            return
        for ln in ch.lines:
            if ln.kind != "inst":
                continue
            for nm in ln.names:
                self._check_inst(Inst(nm, ln.ns, ln.no), stack + [ch.name])

    def _walk_paths(self, prefix, node, seen):
        if node is None:
            return
        for mt in node.mounts:
            if mt.kind == "dir":
                path = f"{prefix}{mt.name}"
                if path in seen:
                    self.errors.append(
                        f"{self.fname}:{mt.no}: 物理路径冲突：{path}")
                seen[path] = True
                if mt.name in self.dirs:
                    self._walk_paths(path + "/", self.dirs[mt.name], seen)
            else:
                base = mt.name + (TYPE_SUFFIX.get(mt.type, "") if mt.type else "")
                path = f"{prefix}{base}"
                if path in seen:
                    self.errors.append(
                        f"{self.fname}:{mt.no}: 物理路径冲突：{path}")
                seen[path] = True

    # ------------------------------------------------ 展开（tangle）

    def expand(self, ch, stack, indent):
        if ch.name in stack:
            raise NWError(ch.no, f"chunk 循环实例化：{ch.name}")
        if ch.todo:
            return []
        out = []
        for ln in ch.lines:
            if ln.kind == "inst":
                for nm in ln.names:
                    target = self.resolve(nm, ln.ns)
                    out.extend(self.expand(target, stack + [ch.name], indent + ln.indent))
            else:
                out.append(indent + ln.text if ln.text else "")
        return out

    def file_text(self, f):
        out = []
        for inst in f.body:
            ch = self.resolve(inst.name, inst.ns)
            part = self.expand(ch, [], "")
            if not part:
                continue                 # 待办块、空块：不产出，也不留一个孤零零的空行
            if out:
                out.append("")           # 实例之间空一行
            out.extend(part)
        return "\n".join(out) + ("\n" if out else "")

    # ------------------------------------------------ tangle 写盘

    def tangle(self, outdir):
        import os
        top = self.dirs.get("top")
        if top is None:
            raise NWError(0, "缺少 dir top")
        written = []
        self._tangle_dir(outdir, top, written)
        return written

    def _tangle_dir(self, path, node, written):
        import os
        os.makedirs(path, exist_ok=True)
        for mt in node.mounts:
            if mt.kind == "dir":
                if mt.name in self.dirs:
                    self._tangle_dir(os.path.join(path, mt.name),
                                     self.dirs[mt.name], written)
            else:
                if (mt.name, mt.type) not in self.files:
                    continue
                f = self.files[(mt.name, mt.type)]
                base = mt.name + (TYPE_SUFFIX.get(mt.type, "") if mt.type else "")
                full = os.path.join(path, base)
                text = self.file_text(f)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(text)
                written.append(full)

    # ------------------------------------------------ ast（给 weave / IDE）

    def ast(self):
        chunks = {}
        for name, ch in self.chunks.items():
            chunks[name] = {
                "line": ch.no,
                "insts": [nm for ln in ch.lines if ln.kind == "inst" for nm in ln.names],
            }

        def dir_json(node):
            return {
                "name": node.name,
                "mounts": [
                    {"kind": mt.kind, "name": mt.name, "type": mt.type, "line": mt.no}
                    for mt in node.mounts
                ],
            }

        files = {
            f"{name}<{typ or ''}>": {"line": f.no, "insts": [i.name for i in f.body]}
            for (name, typ), f in self.files.items()
        }
        return {
            "chunks": chunks,
            "namespaces": sorted(self.p.ns_decls),
            "dirs": {n: dir_json(d) for n, d in self.dirs.items()},
            "files": files,
        }


# ---------------------------------------------------------------- CLI


def main(argv):
    if len(argv) < 3 or argv[1] not in ("check", "tangle", "ast"):
        print(__doc__)
        return 2
    cmd = argv[1]
    rest = argv[2:]
    outdir = None
    if "-o" in rest:
        i = rest.index("-o")
        outdir = rest[i + 1]
        rest = rest[:i] + rest[i + 2:]
    paths = rest
    if cmd == "tangle" and not outdir:
        print("tangle 需要 -o 输出目录")
        return 2
    if not paths:
        print("缺少源文件")
        return 2

    doc = Document.from_files(paths)
    errors, warnings = doc.check()
    for w in warnings:
        print("warn:", w)
    for e in errors:
        print("error:", e)
    if errors:
        return 1

    if cmd == "check":
        n_f = len(doc.files)
        n_c = len(doc.chunks)
        print(f"ok：chunk {n_c} 个，file {n_f} 个，警告 {len(warnings)} 条")
        return 0
    if cmd == "ast":
        print(json.dumps(doc.ast(), ensure_ascii=False, indent=2))
        return 0
    written = doc.tangle(outdir)
    for w in written:
        print("写出", w)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
