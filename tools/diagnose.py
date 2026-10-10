# -*- coding: utf-8 -*-
"""完整诊断：输出每页首尾文本，并追踪特定表格的位置。"""
import os
import pymupdf

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(BASE, 'preview', 'brief.pdf')
doc = pymupdf.open(PDF)
pages = [p.get_text() for p in doc]

MARKERS = ['成果类型', '发明专利', '软件著作权', 'SeamBench 公开数据集',
           '第十三章', '附录A', '第十二章', '赛事荣誉']

print('=== 标记词所在页 ===')
for m in MARKERS:
    hits = [i + 1 for i, t in enumerate(pages) if m in t]
    print('%-22s -> %s' % (m, hits if hits else '未找到'))

print()
print('=== 第 28-33 页首尾文本 ===')
for n in range(28, 34):
    if n > doc.page_count:
        break
    t = pages[n - 1].strip()
    head = t[:90].replace('\n', ' | ')
    tail = t[-90:].replace('\n', ' | ')
    print('--- 第 %d 页  共 %d 字 ---' % (n, len(t)))
    print('  首: %s' % head)
    print('  尾: %s' % tail)
doc.close()
