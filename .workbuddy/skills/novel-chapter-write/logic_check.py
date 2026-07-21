#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
logic_check.py — 《道士也玩火力覆盖》章节正文·机械逻辑校验
隶属 novel-chapter-write 四阶段流程（阶段三强制机械校验，GATE-3 门槛之一）。

设计目的：把"逻辑自查"从"AI 凭记忆回忆约束"升级为"对照权威索引机械比对"。
覆盖**结构性、可机检**的硬逻辑问题（C1–C6）；空间/位置类（C7）为 WARN 级辅助提示，
不阻断流程，须由流程文档「逻辑一致性防御矩阵 L9」做语义确认。语义类（认知边界/物品
位置/因果链/手法适配）由 AI 矩阵覆盖，本脚本不重复。

捕获项：
  C1 同音/异体陷阱   —— 正文出现 萧凡/柯岚/柯砚/沈砚/苏霜/苏莫凝 等错名
  C2 禁复活/已死出场 —— 正文出现 禁复活名单/已死角色（萧沛/沈括等）
  C3 年号越界        —— 永熙 + 数字 > 37（已定 永熙≤1404=37年）
  C4 占位残留        —— 待统稿定/名号待统稿定/待定 等未回填占位
  C5 写作备注混入    —— （节拍…）/（R数字：…）/（章末钩子…）等作者备注括号行（不含合法的「（本章完）」章末标记）
  C6 FB 编号         —— 正文 FB-xxx 未登记 / 落在空号 FB-104~109 / 超范围 >185
  C7 空间/位置(WARN)—— C7a 空间锚点缺失(全章无已知地点名词，疑违 R11)；C7b 互斥地点冲突(同章无过渡同现 盛京/北境 等互斥对，须 L9 确认)

用法：python logic_check.py <章节md路径> [治理目录]
返回：0=全通过，1=有 FAIL，2=参数错误
"""
import re, sys, os

def _repo_root():
    """脚本位于 <repo_root>/.workbuddy/skills/novel-chapter-write/logic_check.py，
    上溯 3 级定位仓库根；跨盘/跨目录均可移植。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


DEFAULT_GOV = None  # 运行时由 check() 按仓库根自动探测 docs/governance

# 已知地点名词（R11 空间锚点候选；用于 C7a 缺失检测）
KNOWN_LOCS = ["清虚观", "盛京", "京城", "中都", "北境", "赤乌", "玉虚", "玄妙观",
              "边关", "江南", "虞国", "听雨阁", "西市", "狄族", "长生观",
              "镇抚司", "内卫府", "朔州", "云中", "大晟"]

# 互斥地点对（用于 C7b：同章无过渡同现须 L9 确认）
MUTEX_PAIRS = [
    ("盛京", "北境"), ("盛京", "赤乌"), ("京城", "北境"), ("京城", "赤乌"),
    ("中都", "北境"), ("中都", "赤乌"), ("清虚观", "北境"), ("清虚观", "赤乌"),
    ("江南", "北境"), ("虞国", "北境"), ("玉虚", "北境"), ("玉虚", "赤乌"),
]

# 场景切换过渡词（C7b 判定"已交代位移"的白名单）
TRANSITION_WORDS = ["启程", "赶往", "前往", "传讯", "飞书", "次日", "旬后", "经年",
                    "闭关", "一路", "领兵", "出征", "北上", "西去", "南归", "东进",
                    "行了几日", "行了数日", "兼程", "星夜", "旬日", "月余", "次年",
                    "翌日", "半日后", "隔日", "不多时便到", "赶回", "转道"]

# 正名 -> 错误写法（同音/异体陷阱）
WRONG_VARIANTS = {
    "肖凡": ["萧凡"],
    "苏墨凝": ["苏莫凝"],
    "柯铮": ["柯岚"],
    "沈舟": ["柯砚", "沈砚"],
    "苏晚": ["苏霜"],
}
FORBIDDEN_TOKENS = set()
for _v in WRONG_VARIANTS.values():
    FORBIDDEN_TOKENS.update(_v)

# 正文严禁的占位残留
PLACEHOLDER = ["待统稿定", "名号待统稿定", "名号待统稿复核", "待定", "名号待"]

# 禁复活角色的分章阈值：角色仅在「章节号 > 阈值」时才视为已死、提及即违规。
# 萧沛为大晟三皇子，卷一至卷三为在世隐藏大反派，第212章（书院查封）方退场禁复活；
# 此前章节提及其名属正常在世描写，不应误判为复活。
# 漕帮赵管事：第028章首现（肖凡探底漕帮结构），第028/029/037章为在世正常出场，
# 第046章被借官面查办（落网）方退场；故章节号 ≤ 46 的出场/提及均属合法，不应误判为复活。
DEAD_THRESHOLD = {"萧沛": 212, "漕帮赵管事": 46}

# 作者写作备注括号行模式（只应存在于大纲/手法调度表，绝不进正文）
# 注意：合法的章末标记「（本章完）」不在匹配范围内
NOTE_PAT = re.compile(r'（(?:节拍\d*|R\d+|章末钩子|悬念钩子|手法|红线|FB-\d+)[^）]*）')

# 年号越界：永熙 + 数字（阿拉伯或中文）> 37
YEAR_PAT = re.compile(r'永熙\s*?([0-9零一二三四五六七八九十百]+)')

_CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
       '七': 7, '八': 8, '九': 9, '零': 0}


def cn2int(s):
    """简易中文数字转 int（覆盖 1–120，如 八十一/四十三/一百二十）。"""
    r, t = 0, 0
    for ch in s:
        if ch in _CN:
            t = _CN[ch]
        elif ch == '十':
            t = (t * 10) if t else 10
            r += t
            t = 0
        elif ch == '百':
            t = (t if t else 1) * 100
            r += t
            t = 0
    return r + t


def year_value(tok):
    return int(tok) if tok.isdigit() else cn2int(tok)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_dead_chars(char_text):
    """提取禁复活/已死名单：硬编码已知 canon + 动态扫描 IDX_CHARACTER 表中带
    禁复活/已死标记的行（取每行首列角色名），两者取并集。"""
    # 硬编码已知 canon（稳定，若禁复活名单变更须同步此行）
    strong = ["萧沛"]  # 禁复活，仅余党裴琰承线出场
    mention = ["沈括", "黑虎帮二当家", "漕帮赵管事", "钱万山"]
    # 动态：扫描 IDX_CHARACTER 表格行，首列为角色名
    for line in char_text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 3:
            continue
        name = cells[1]
        if not name or name.startswith("角色") or name in ("—", "-"):
            continue
        if "禁复活" in line:
            if name not in strong:
                strong.append(name)
        elif "已死" in line or "已退场" in line:
            if name not in mention and name not in strong:
                mention.append(name)
    return strong, mention


def parse_registered_fb(fb_text):
    return {int(m) for m in re.findall(r'FB-(\d+)', fb_text)}


def check(chapter_path, gov=None):
    if gov is None:
        gov = os.path.join(_repo_root(), "docs", "governance")
    char_text = read_text(os.path.join(gov, "IDX_CHARACTER.md"))
    set_text = read_text(os.path.join(gov, "IDX_SETTING.md"))
    fb_text = read_text(os.path.join(gov, "IDX_FORESHADOW.md"))
    chapter = read_text(chapter_path)
    lines = chapter.splitlines()

    # 当前章节号（用于禁复活分章阈值判断）
    _m = re.search(r'第(\d+)章', os.path.basename(chapter_path))
    cur_ch = int(_m.group(1)) if _m else 0

    fails, passes = [], []

    # C1 同音/异体陷阱
    c1 = [(i, t) for i, ln in enumerate(lines, 1) for t in FORBIDDEN_TOKENS if t in ln]
    if c1:
        fails.append(("C1 同音/异体陷阱", c1))
    else:
        passes.append("C1 同音/异体陷阱：无 萧凡/柯岚/柯砚/沈砚/苏霜/苏莫凝")

    # C2 禁复活/已死出场
    strong, mention = parse_dead_chars(char_text)
    c2 = []
    for i, ln in enumerate(lines, 1):
        for nm in strong + mention:
            if nm and nm in ln:
                # 分章阈值：角色在世章节内提及属正常，不误判为复活
                # （IDX_CHARACTER 角色名列可能带「三皇子」等前缀，故按子串匹配）
                if any(K in nm and cur_ch <= DEAD_THRESHOLD[K] for K in DEAD_THRESHOLD):
                    continue
                tag = "禁复活(强)" if nm in strong else "已死(提及需确认非复活)"
                c2.append((i, f"{nm}（{tag}）"))
    if c2:
        fails.append(("C2 禁复活/已死角色出现", c2))
    else:
        passes.append("C2 禁复活/已死角色：正文未出现")

    # C3 年号越界
    c3 = []
    for i, ln in enumerate(lines, 1):
        for m in YEAR_PAT.finditer(ln):
            tok = m.group(1)
            try:
                n = year_value(tok)
            except Exception:
                continue
            if n > 37:
                c3.append((i, f"永熙{tok}（={n}>37 越界）"))
    if c3:
        fails.append(("C3 年号越界(永熙>37)", c3))
    else:
        passes.append("C3 年号：无 永熙>37 越界")

    # C4 占位残留
    c4 = [(i, ph) for i, ln in enumerate(lines, 1) for ph in PLACEHOLDER if ph in ln]
    if c4:
        fails.append(("C4 占位残留", c4))
    else:
        passes.append("C4 占位残留：无 待统稿定/待定 等")

    # C5 写作备注混入
    c5 = []
    for i, ln in enumerate(lines, 1):
        mm = NOTE_PAT.search(ln)
        if mm:
            c5.append((i, mm.group(0)))
    if c5:
        fails.append(("C5 写作备注混入正文", c5))
    else:
        passes.append("C5 写作备注：正文纯净")

    # C6 FB 编号校验
    registered = parse_registered_fb(fb_text)
    c6 = []
    for i, ln in enumerate(lines, 1):
        for m in re.findall(r'FB-(\d+)', ln):
            num = int(m)
            if num not in registered:
                c6.append((i, f"FB-{num}（未登记）"))
            elif 104 <= num <= 109:
                c6.append((i, f"FB-{num}（空号未定义）"))
            elif num > 185:
                c6.append((i, f"FB-{num}（超范围>185）"))
    if c6:
        fails.append(("C6 FB编号 未登记/空号/超范围", c6))
    else:
        passes.append("C6 FB编号：均登记且在有效号段")

    # C7 空间/位置（WARN 级，不计入硬 FAIL，须 L9 语义确认）
    warns = []
    has_loc = any(any(loc in ln for loc in KNOWN_LOCS) for ln in lines)
    if not has_loc:
        warns.append(("C7a 空间锚点缺失", [(0, "全章未出现任何已知地点名词，疑似违反 R11 空间锚点")]))
    c7b = []
    for i, ln in enumerate(lines, 1):
        for a, b in MUTEX_PAIRS:
            if a in ln and b in ln:
                c7b.append((i, f"{a} 与 {b} 同段出现"))
    if c7b:
        has_trans = any(any(tw in ln for tw in TRANSITION_WORDS) for ln in lines)
        if not has_trans:
            warns.append(("C7b 互斥地点冲突(无过渡词)", c7b))

    # 报告
    print("=" * 64)
    print(f"逻辑机械校验：{os.path.basename(chapter_path)}")
    print("=" * 64)
    for p in passes:
        print(f"  [PASS] {p}")
    for name, items in fails:
        print(f"  [FAIL] {name}：")
        for it in items[:25]:
            if len(it) == 2:
                print(f"      L{it[0]}: {it[1]}")
            else:
                print(f"      L{it[0]}: {it[1]}")
    for name, items in warns:
        print(f"  [WARN] {name}：")
        for it in items[:25]:
            print(f"      L{it[0]}: {it[1]}")
    print("=" * 64)
    total = sum(len(v) for _, v in fails)
    if fails:
        print(f"结论：❌ 发现 {total} 处结构问题，须回阶段二修订后重检")
        return 1
    if warns:
        wtotal = sum(len(v) for _, v in warns)
        print(f"结论：✅ 硬校验通过；⚠️ {wtotal} 处空间 WARN（C7，须 L9 语义确认，不阻断）")
    else:
        print("结论：✅ 机械校验全通过（结构性逻辑无问题；语义类见 AI 矩阵）")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python logic_check.py <章节md路径> [治理目录]")
        sys.exit(2)
    cp = sys.argv[1]
    gv = sys.argv[2] if len(sys.argv) > 2 else None
    sys.exit(check(cp, gv))
