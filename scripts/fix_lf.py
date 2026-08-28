# -*- coding: utf-8 -*-
"""把 shell 脚本规整成「无 BOM + LF」。

为什么需要它：本机是 Windows，编辑器与 PowerShell 都可能给文件塞上 UTF-8 BOM
或 CRLF。这两样对要在 Linux 上执行的脚本都是硬故障 ——
  BOM  → `#!/usr/bin/env` 前面多三个字节，内核找不到解释器
  CRLF → 每一行末尾多一个 \r，`if [ "$x" = "y" ]` 里的比较值凭空多一个字符
`.gitattributes` 里的 `*.sh text eol=lf` 只管**入库与签出**，管不了工作区里
这份文件现在长什么样 —— 而 scp 是二进制拷贝，工作区什么样，服务器上就什么样。

用法：python scripts/fix_lf.py ops/verify.sh [更多文件...]
"""
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for arg in sys.argv[1:]:
        p = Path(arg)
        raw = p.read_bytes()
        fixed = raw
        notes = []
        if fixed.startswith(b"\xef\xbb\xbf"):
            fixed = fixed[3:]
            notes.append("去掉 BOM")
        if b"\r\n" in fixed:
            fixed = fixed.replace(b"\r\n", b"\n")
            notes.append("CRLF → LF")
        if fixed != raw:
            p.write_bytes(fixed)
        print(f"  {p}: {'、'.join(notes) if notes else '本来就干净'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
