# -*- coding: utf-8 -*-
"""转储指定页的原始文本，用于诊断近空白页的成因。"""
import os
import sys
import pymupdf

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(BASE, 'preview', 'brief.pdf')

pages = [int(x) for x in sys.argv[1:]] or [7, 20, 22, 24, 28, 30, 33]
doc = pymupdf.open(PDF)
for n in pages:
    if n < 1 or n > doc.page_count:
        continue
    t = doc[n - 1].get_text()
    print('=' * 58)
    print('第 %d 页  字符数=%d' % (n, len(t.strip())))
    print('-' * 58)
    print(t.strip()[:700] if t.strip() else '（无文本）')
    print()
doc.close()
