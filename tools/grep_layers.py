# -*- coding: utf-8 -*-
"""检索“四层/五层/架构”相关表述，确保全文口径一致。"""
import io

lines = io.open('tools/build_brief.py', encoding='utf-8').read().split('\n')
for kw in ('四层', '五层', '架构'):
    print('=== 含“%s”的行 ===' % kw)
    for i, l in enumerate(lines, 1):
        if kw in l:
            print('%5d| %s' % (i, l.strip()[:120]))
    print()
