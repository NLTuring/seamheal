# -*- coding: utf-8 -*-
"""检查所有 Markdown 文档中的“域”计数口径，保持与 DOCX 一致。"""
import io
import os
import glob

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
files = [os.path.join(BASE, 'README.md')] + sorted(glob.glob(os.path.join(BASE, 'docs', '*.md')))

for f in files:
    txt = io.open(f, encoding='utf-8').read()
    lines = txt.split('\n')
    for kw in ('四个域', '四域'):
        for i, l in enumerate(lines, 1):
            if kw in l:
                print('%s : %d | %s' % (os.path.basename(f), i, l.strip()[:150]))
print('检查完成')
