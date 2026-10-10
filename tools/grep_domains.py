# -*- coding: utf-8 -*-
"""排查“域”的计数口径是否一致（应为三个域：几何/纹理/力学）。"""
import io

lines = io.open('tools/build_brief.py', encoding='utf-8').read().split('\n')
KEYS = ['四个域', '四域', '三个域', '三域', '四类接缝', '四个权重', '四项']
for kw in KEYS:
    hits = [(i, l.strip()) for i, l in enumerate(lines, 1) if kw in l]
    print('=== “%s” 命中 %d 处 ===' % (kw, len(hits)))
    for i, l in hits:
        print('%5d| %s' % (i, l[:125]))
    print()
