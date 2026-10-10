# -*- coding: utf-8 -*-
"""排查所有文档中涉及团队人数/分工的位置，便于统一修改为 6-8 人。"""
import io
import os
import glob

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYS = ['团队规模', '团队构成', '团队人数', '核心成员', '8–10', '8-10', '10 人',
        '组别', '指导老师', '指导教师不少于', '人数', '团队优势', '团队风险',
        '算法组', '学习组', '工程组', '商业组', '制造与实验组', '团队分工']

targets = [os.path.join(BASE, 'tools', 'build_brief.py'),
           os.path.join(BASE, 'README.md')] + sorted(glob.glob(os.path.join(BASE, 'docs', '*.md')))

for f in targets:
    if not os.path.exists(f):
        continue
    lines = io.open(f, encoding='utf-8').read().split('\n')
    hits = [(i, l.strip()) for i, l in enumerate(lines, 1)
            if any(k in l for k in KEYS)]
    if not hits:
        continue
    print('=' * 70)
    print('文件：%s  （命中 %d 行）' % (os.path.relpath(f, BASE), len(hits)))
    print('=' * 70)
    for i, l in hits:
        print('%5d| %s' % (i, l[:150]))
    print()
