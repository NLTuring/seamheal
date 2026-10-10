# -*- coding: utf-8 -*-
"""定位修复内容所在页码（宽松关键词），并列出疑似近空白页。"""
import os
import pymupdf

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(BASE, 'preview', 'brief.pdf')

KEYS = [
    ('目录页', '目'),
    ('价格-核心数据卡', '25,000+'),
    ('价格-失败模式五', '失败模式五'),
    ('公式-式中四项', '式中四项'),
    ('架构-管线五层', '整条管线自上而下'),
    ('飞轮-免费插件', '免费插件触达创客'),
    ('飞轮-加速运转', '飞轮加速运转'),
    ('壁垒-四层', '四层壁垒'),
    ('附录C-Q5', 'Q5'),
]

doc = pymupdf.open(PDF)
pages = [p.get_text() for p in doc]
print('总页数 =', doc.page_count)
print()
for label, k in KEYS:
    hits = [i + 1 for i, t in enumerate(pages) if k in t]
    print('%-18s %-14s -> 页 %s' % (label, k, hits if hits else '未找到'))

print()
print('=== 每页文字量 ===')
sparse = []
for i, t in enumerate(pages, 1):
    n = len(t.strip().replace('\n', ''))
    if n < 250:
        sparse.append(i)
    print('第 %2d 页：%4d 字%s' % (i, n, '   <== 偏少' if n < 250 else ''))
print()
print('偏少页 =', sparse)
doc.close()
