#!/usr/bin/env python3
"""neoweb v3 原型：parse → AST（chunk 树 + 代码树 + 书）→ check → tangle。

对着 docs/granmmerv3.nw 实现。这是验证语法的原型，不是 C++ 实现。

用法：
    python3 nw3.py check  源.nw
    python3 nw3.py tangle -o 输出目录 源.nw
    python3 nw3.py parse  [--ast] 源.nw
    python3 nw3.py ast    源.nw          # 等价于 parse --ast
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
    fname: str = ""  # 它写在哪一篇里（ast 的出处，不是合并后的主篇）


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
    declared: bool = False   # 有过 dir X @：只能一次
    touched: bool = False    # 有过 @ 或 +=：决定是否落盘
    mounted: int = 0
    no: int = 0


@dataclass
class FileNode:
    name: str
    type: str
    body: list = field(default_factory=list)     # Inst，保持文档顺序
    declared: bool = False
    touched: bool = False
    mounted: int = 0
    no: int = 0


@dataclass
class Kid:
    """清单里的一项：一个子部，或一篇散篇。"""
    is_part: bool
    key: str
    no: int = 0
    fname: str = ""


@dataclass
class PartDef:
    name: str
    title: str = ""
    declared: bool = False
    touched: bool = False
    kids: list = field(default_factory=list)
    no: int = 0
    end_no: int = 0


@dataclass
class BookDef:
    name: str = ""
    title: str = ""
    declared: bool = False
    touched: bool = False
    kids: list = field(default_factory=list)
    no: int = 0
    end_no: int = 0


class NWError(Exception):
    def __init__(self, no, msg):
        super().__init__(msg)
        self.no = no
        self.msg = msg


# ---------------------------------------------------------------- 正则

RE_DIR_DEF    = re.compile(r"^dir\s+([\w.-]+)\s*@\s*$")
RE_DIR_ADD    = re.compile(r"^dir\s+([\w.-]+)\s*\+=\s*@\s*$")
RE_DIR_MOUNT  = re.compile(r"^dir\s+([\w.-]+)\s*;\s*$")
RE_FILE_DEF   = re.compile(r"^file(?:<([\w-]+)>)?\s+([\w.-]+)\s*@\s*$")
RE_FILE_ADD   = re.compile(r"^file(?:<([\w-]+)>)?\s+([\w.-]+)\s*\+=\s*@\s*$")
RE_FILE_MOUNT = re.compile(r"^file(?:<([\w-]+)>)?\s+([\w.-]+)\s*;\s*$")
RE_BOOK_DEF   = re.compile(r"^book\s+([\w.-]+)\s*@\s*$")
RE_BOOK_ADD   = re.compile(r"^book\s+([\w.-]+)\s*\+=\s*@\s*$")
RE_PART_DEF   = re.compile(r"^part\s+([\w.-]+)\s*@\s*$")
RE_PART_ADD   = re.compile(r"^part\s+([\w.-]+)\s*\+=\s*@\s*$")

# 糖：+= 只接一个目标，父恒为左侧对象
RE_DIR_SUGAR  = re.compile(r"^dir\s+([\w.-]+)\s*\+=\s*(dir\s+[\w.-]+|file(?:<[\w-]+>)?\s+[\w.-]+)\s*;\s*$")
RE_FILE_SUGAR = re.compile(r"^file(?:<([\w-]+)>)?\s+([\w.-]+)\s*\+=\s*(<<[^<>]*>>)\s*;\s*$")
RE_BOOK_SUGAR = re.compile(r"^book\s+([\w.-]+)\s*\+=\s*(part|essay)\s+(.+?)\s*;\s*$")
RE_PART_SUGAR = re.compile(r"^part\s+([\w.-]+)\s*\+=\s*(part|essay)\s+(.+?)\s*;\s*$")

# 清单体里的一行：part / essay / name
RE_KID        = re.compile(r"^(part|essay|name)\s+(.+?)\s*;\s*$")

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
        self.parts = {}           # name → PartDef
        self.book = BookDef()
        self.ns_decls = set()     # 声明过的 ns 全名
        self.errors = []
        self.warnings = []
        self.prose = []           # (行号, 文本)，给 weave 留的
        self.block = []           # (kind, node)，kind ∈ dir/file/chunk/book/part
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
        elif self._in_list():
            self._list_line(no, raw)
        else:
            self._struct_line(no, raw)

    def _in_chunk(self):
        return bool(self.block) and self.block[-1][0] == "chunk"

    def _in_file(self):
        return bool(self.block) and self.block[-1][0] == "file"

    def _in_dir(self):
        return bool(self.block) and self.block[-1][0] == "dir"

    def _in_list(self):
        return bool(self.block) and self.block[-1][0] in ("book", "part")

    def _strip(self, no, raw):
        try:
            return strip_comment(raw, no).strip()
        except NWError as e:
            self.err(no, e.msg)
            return raw.strip()

    # ------------------------------------------------ 结构层（文档态 / dir 体）

    def _struct_line(self, no, raw):
        t = self._strip(no, raw)
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

        # ---- 定义与追加（带体）----
        m = RE_DIR_DEF.match(t) or RE_DIR_ADD.match(t)
        if m:
            if self._in_file():
                self.err(no, "file 体内不能定义 dir")
                return
            self._open_dir(no, m.group(1), "+=" in t)
            return
        m = RE_FILE_DEF.match(t) or RE_FILE_ADD.match(t)
        if m:
            if self._in_file():
                self.err(no, "file 体内不能定义 file")
                return
            typ, name = m.group(1), m.group(2)
            if typ and typ not in TYPE_SUFFIX:
                self.err(no, f"未知文件类型 <{typ}>")
                return
            self._open_file(no, name, typ, "+=" in t)
            return
        m = RE_BOOK_DEF.match(t) or RE_BOOK_ADD.match(t)
        if m:
            self._open_book(no, m.group(1), "+=" in t)
            return
        m = RE_PART_DEF.match(t) or RE_PART_ADD.match(t)
        if m:
            self._open_part(no, m.group(1), "+=" in t)
            return

        # ---- 追加的糖：一行一个目标 ----
        m = RE_DIR_SUGAR.match(t)
        if m:
            self._append_dir(no, m.group(1), m.group(2))
            return
        m = RE_FILE_SUGAR.match(t)
        if m:
            typ, name, stmt = m.group(1), m.group(2), m.group(3)
            if typ and typ not in TYPE_SUFFIX:
                self.err(no, f"未知文件类型 <{typ}>")
                return
            self._append_file(no, name, typ, stmt)
            return
        m = RE_BOOK_SUGAR.match(t)
        if m:
            self._append_book(no, m.group(1), m.group(2), m.group(3))
            return
        m = RE_PART_SUGAR.match(t)
        if m:
            self._append_part(no, m.group(1), m.group(2), m.group(3))
            return

        # ---- 挂载 ----
        m = RE_DIR_MOUNT.match(t)
        if m:
            self._mount(no, "dir", m.group(1), None)
            return
        m = RE_FILE_MOUNT.match(t)
        if m:
            self._mount(no, "file", m.group(2), m.group(1))
            return

        # ---- chunk 定义 ----
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
        self.prose.append((no, raw))

    # ------------------------------------------------ 开块

    def _dir_node(self, name, no):
        d = self.dirs.get(name)
        if d is None:
            d = DirNode(name=name, no=no)
            self.dirs[name] = d
        return d

    def _file_node(self, name, typ, no):
        key = (name, typ)
        f = self.files.get(key)
        if f is None:
            f = FileNode(name, typ, no=no)
            self.files[key] = f
        return f

    def _part_node(self, name, no):
        p = self.parts.get(name)
        if p is None:
            p = PartDef(name=name, no=no)
            self.parts[name] = p
        return p

    def _open_dir(self, no, name, append):
        d = self._dir_node(name, no)
        if not append:
            if d.declared:
                self.err(no, f"dir {name} 重复定义")
                return
            d.declared = True
        d.touched = True
        self.block.append(("dir", d))

    def _open_file(self, no, name, typ, append):
        f = self._file_node(name, typ, no)
        if not append:
            if f.declared:
                self.err(no, f"file {name}<{typ or ''}> 重复定义")
                return
            f.declared = True
        f.touched = True
        self.block.append(("file", f))

    def _open_book(self, no, name, append):
        b = self.book
        if b.name and b.name != name:
            self.err(no, f"一本书只能有一个 book 定义：{b.name} 与 {name}")
            return
        if not append:
            if b.declared:
                self.err(no, f"book 重复定义：{name}")
                return
            b.declared = True
        if not b.name:
            b.name = name
            b.no = no
        b.touched = True
        self.block.append(("book", b))

    def _open_part(self, no, name, append):
        p = self._part_node(name, no)
        if not append:
            if p.declared:
                self.err(no, f"part {name} 重复定义")
                return
            p.declared = True
        p.touched = True
        self.block.append(("part", p))

    # ------------------------------------------------ 追加的糖

    def _append_dir(self, no, parent, stmt):
        d = self._dir_node(parent, no)
        d.touched = True
        m = re.match(r"^dir\s+([\w.-]+)$", stmt)
        if m:
            d.mounts.append(Mount("dir", m.group(1), None, no))
            return
        m = re.match(r"^file(?:<([\w-]+)>)?\s+([\w.-]+)$", stmt)
        if m:
            typ, name = m.group(1), m.group(2)
            if typ and typ not in TYPE_SUFFIX:
                self.err(no, f"未知文件类型 <{typ}>")
                return
            d.mounts.append(Mount("file", name, typ, no))
            return
        self.err(no, f"dir 只能追加 dir 或 file：{stmt}")

    def _append_file(self, no, name, typ, stmt):
        f = self._file_node(name, typ, no)
        f.touched = True
        names = RE_ONE_INST.findall(stmt)
        if not RE_INSTS.match(stmt) or len(names) != 1:
            self.err(no, f"file 的 += 只接一个 chunk 实例：{stmt}")
            return
        f.body.append(Inst(names[0], tuple(self.ns), no, self.fname))

    def _append_book(self, no, name, kw, key):
        if self.book.name != name:
            self.err(no, f"+= 到不存在的 book：{name}")
            return
        self._append_kid(self.book.kids, no, kw, key)

    def _append_part(self, no, name, kw, key):
        p = self._part_node(name, no)
        p.touched = True
        self._append_kid(p.kids, no, kw, key)

    def _append_kid(self, kids, no, kw, key):
        key = key.strip()
        if kw not in ("part", "essay") or not key:
            self.err(no, f"只能追加 part 或 essay：{kw} {key}")
            return
        kids.append(Kid(kw == "part", key, no, self.fname))

    # ------------------------------------------------ 清单体

    def _list_line(self, no, raw):
        t = self._strip(no, raw)
        if not t:
            return
        if RE_CLOSE.match(t):
            self._close_block(no)
            return
        kind, node = self.block[-1]
        m = RE_KID.match(t)
        if not m:
            self.err(no, f"清单里只能写 part / essay / name：{t}")
            return
        kw, val = m.group(1), m.group(2).strip()
        if kw == "name":
            node.title = val
            return
        node.kids.append(Kid(kw == "part", val, no, self.fname))

    # ------------------------------------------------ 挂载

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
            return
        if kind in ("book", "part"):
            node.end_no = no

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
        t = self._strip(no, raw)
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
                    node.body.append(Inst(nm, tuple(self.ns), no, self.fname))
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
        self.parts = self.p.parts
        self.book = self.p.book
        self.order = []
        self.errors = list(self.p.errors)
        self.warnings = list(self.p.warnings)

    @classmethod
    def from_files(cls, paths):
        """两遍：每篇独立 parse，再按书的先序并成一份文档。"""
        docs = []
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                docs.append(cls(fh.read(), path))
        d = cls.__new__(cls)
        d.fname = docs[0].fname if docs else ""
        d.p = docs[0].p if docs else None
        d.chunks, d.dirs, d.files = {}, {}, {}
        d.parts = {}
        d.book = BookDef()
        d.order = []
        d.errors, d.warnings = [], []
        # 一、清单先合：书只能一本，部按名字合并，kids 按篇序接在后面。
        for sub in docs:
            d.errors += sub.errors
            d.warnings += sub.warnings
            b = sub.book
            if b.name:
                if not d.book.name:
                    d.book = b
                elif d.book.name != b.name:
                    d.errors.append(
                        f"{sub.fname}:{b.no}: 一本书只能有一个 book 定义：{d.book.name} 与 {b.name}")
                elif d.book.declared and b.declared:
                    d.errors.append(f"{sub.fname}:{b.no}: book 重复定义：{b.name}")
                else:
                    d.book.declared = d.book.declared or b.declared
                    d.book.touched = True
                    d.book.kids += b.kids
                    if not d.book.title:
                        d.book.title = b.title
                    if not d.book.end_no:
                        d.book.end_no = b.end_no
            for name, p in sub.parts.items():
                slot = d.parts.get(name)
                if slot is None:
                    d.parts[name] = p
                    continue
                if slot.declared and p.declared:
                    d.errors.append(f"{sub.fname}:{p.no}: part 重复定义：{name}")
                slot.declared = slot.declared or p.declared
                slot.touched = True
                if not slot.title:
                    slot.title = p.title
                slot.kids += p.kids
                if p.end_no:
                    slot.end_no = p.end_no
        if not d.book.name:
            d.errors.append(f"{d.fname}:0: 没有 book 定义：一本书从 book 开始")
            return d
        # 二、先序展开成唯一的 order。
        d.order = d._expand_book()
        # 三、按篇序并物理树。没被书收的篇不进 AST：它不属于这本书。
        by_file = {sub.fname: sub for sub in docs}
        seen = set()
        for src in d.order:
            if src in seen:
                d.errors.append(f"{d.book.no}: 同一篇被收了两次：{src}")
                continue
            seen.add(src)
            sub = by_file.get(src)
            if sub is None:
                d.errors.append(f"{d.book.no}: book 收了这一篇，但输入里没有：{src}")
                continue
            d._merge_one(sub)
        return d

    def _expand_book(self):
        order = []
        open_names = set()

        def walk(kids):
            for k in kids:
                if not k.is_part:
                    order.append(k.key)
                    continue
                p = self.parts.get(k.key)
                if p is None:
                    self.errors.append(f"{k.fname or self.fname}:{k.no}: 引用了没有定义的 part：{k.key}")
                    continue
                if k.key in open_names:
                    self.errors.append(f"{k.fname or self.fname}:{k.no}: part 成环：{k.key}")
                    continue
                open_names.add(k.key)
                walk(p.kids)
                open_names.discard(k.key)

        walk(self.book.kids)
        return order

    def _merge_one(self, sub):
        for k, v in sub.chunks.items():
            if k in self.chunks:
                self.errors.append(
                    f"{sub.fname}:{v.no}: chunk {k} 在两篇里都实现了")
            else:
                self.chunks[k] = v
        for k, v in sub.dirs.items():
            slot = self.dirs.get(k)
            if slot is None:
                self.dirs[k] = v
                continue
            if slot.declared and v.declared:
                self.errors.append(f"{sub.fname}:{v.no}: dir {k} 在两篇里都定义了")
            slot.declared = slot.declared or v.declared
            slot.touched = True
            slot.mounts += v.mounts
        for k, v in sub.files.items():
            slot = self.files.get(k)
            if slot is None:
                self.files[k] = v
                continue
            if slot.declared and v.declared:
                self.errors.append(f"{sub.fname}:{v.no}: file {k[0]}<{k[1] or ''}> 在两篇里都定义了")
            slot.declared = slot.declared or v.declared
            slot.touched = True
            slot.body += v.body
        if self.p is not None and sub.p is not None:
            self.p.ns_decls |= sub.p.ns_decls

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
                        self.dirs[mt.name] = DirNode(mt.name)
                else:
                    key = (mt.name, mt.type)
                    if key not in self.files:
                        self.files[key] = FileNode(mt.name, mt.type, [])
        # 2. top 必须存在，而且必须由 @ 建立
        top = self.dirs.get("top")
        if top is None:
            self.errors.append(f"{self.fname}:0: 缺少 dir top @（tangle 的根只能由 @ 建立）")
        elif not top.declared:
            self.errors.append(
                f"{self.fname}:0: top 必须先 dir top @（tangle 的根只能由 @ 建立）")

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
            if d.mounted == 0 and d.touched:
                self.warnings.append(f"{self.fname}:0: dir {name} 已定义但未挂载")
            elif d.mounted > 1:
                self.errors.append(
                    f"{self.fname}:0: dir {name} 挂载了 {d.mounted} 次（声明位置唯一）")
        for (name, typ), f in self.files.items():
            if f.mounted == 0 and f.touched:
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
        if top is None or not top.declared:
            raise NWError(0, "缺少 dir top @（tangle 的根只能由 @ 建立）")
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
                continue
            f = self.files.get((mt.name, mt.type))
            if f is None or not f.touched:
                continue                 # 没写内容：不落盘
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
        parts = {
            name: {
                "title": p.title,
                "kids": [
                    {"kind": "part" if k.is_part else "essay", "name": k.key}
                    for k in p.kids
                ],
            }
            for name, p in self.parts.items()
        }
        instances = []
        for (name, typ), f in self.files.items():
            label = name + (f"<{typ}>" if typ else "")
            nth = {}
            for inst in f.body:
                k = nth.get(inst.no, 0)
                nth[inst.no] = k + 1
                instances.append({
                    "id": f"{label}#{inst.no}.{k}",
                    "name": inst.name,
                    "file": inst.fname or self.fname,
                    "line": inst.no,
                })
        return {
            "book": {
                "name": self.book.name,
                "title": self.book.title or self.book.name,
                "order": self.order,
            },
            "parts": parts,
            "chunks": chunks,
            "namespaces": sorted(self.p.ns_decls),
            "dirs": {n: dir_json(d) for n, d in self.dirs.items()},
            "files": files,
            "instances": instances,
        }


# ---------------------------------------------------------------- CLI


def main(argv):
    if len(argv) < 3 or argv[1] not in ("check", "tangle", "parse", "ast"):
        print(__doc__)
        return 2
    cmd = argv[1]
    rest = argv[2:]
    outdir = None
    if "-o" in rest:
        i = rest.index("-o")
        if i + 1 >= len(rest):
            print("-o 后面要跟一个目录")
            return 2
        outdir = rest[i + 1]
        rest = rest[:i] + rest[i + 2:]
    ast = cmd == "ast"
    if "--ast" in rest:
        ast = True
        rest = [a for a in rest if a != "--ast"]
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
    if cmd == "parse" or cmd == "ast":
        if ast:
            print(json.dumps(doc.ast(), ensure_ascii=False, indent=2))
        else:
            title = doc.book.title or doc.book.name
            print(f"书：{title}，收录 {len(doc.order)} 篇（输入 {len(paths)} 篇）")
        return 0
    written = doc.tangle(outdir)
    for w in written:
        print("写出", w)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
