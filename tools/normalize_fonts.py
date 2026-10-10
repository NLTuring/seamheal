# -*- coding: utf-8 -*-
"""在 XML 层级把所有 run 的字体归一化为宋体。

Word 更新目录后会新建 TOC 条目与页码 run，这些 run 位于 w:hyperlink 内部，
python-docx 的 paragraph.runs 无法枚举，因此必须直接在 XML 树上处理。
"""
import os
from docx import Document
from docx.oxml.ns import qn

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SONG = '宋体'

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(BASE, '愈缝SeamHeal-项目简介文档.docx')

doc = Document(PATH)


def fix_runs(root):
    n = 0
    for r in root.iter(W + 'r'):
        rPr = r.find(W + 'rPr')
        if rPr is None:
            rPr = r.makeelement(W + 'rPr', {})
            r.insert(0, rPr)
        rFonts = rPr.find(W + 'rFonts')
        if rFonts is None:
            rFonts = rPr.makeelement(W + 'rFonts', {})
            rStyle = rPr.find(W + 'rStyle')
            if rStyle is not None:
                rStyle.addnext(rFonts)
            else:
                rPr.insert(0, rFonts)
        for a in ('w:ascii', 'w:hAnsi', 'w:eastAsia', 'w:cs'):
            rFonts.set(qn(a), SONG)
        n += 1
    return n


# 1) 正文 / 页眉页脚 / 脚注等主文档部件
total = fix_runs(doc.element)
print('document.xml 处理 run 数 =', total)

for i, s in enumerate(doc.sections):
    for part in (s.header, s.footer, s.first_page_header, s.first_page_footer,
                 s.even_page_header, s.even_page_footer):
        try:
            c = fix_runs(part._element)
            if c:
                print('  第%d节 %s run 数 = %d' % (i + 1, type(part).__name__, c))
        except Exception as e:
            print('  第%d节 部件处理跳过: %s' % (i + 1, str(e)[:60]))

# 2) 样式层：所有样式 + docDefaults 默认字体
styled = 0
for st in doc.styles:
    try:
        st.font.name = SONG
        rPr = st.element.get_or_add_rPr()
        rFonts = rPr.get_or_add_rFonts()
        for a in ('w:ascii', 'w:hAnsi', 'w:eastAsia', 'w:cs'):
            rFonts.set(qn(a), SONG)
        styled += 1
    except Exception:
        pass
print('样式处理数 =', styled)

# 3) 样式表的 docDefaults
try:
    styles_el = doc.styles.element
    dd = styles_el.find(W + 'docDefaults')
    if dd is not None:
        rpr_def = dd.find(W + 'rPrDefault')
        if rpr_def is not None:
            rPr = rpr_def.find(W + 'rPr')
            if rPr is None:
                rPr = rpr_def.makeelement(W + 'rPr', {})
                rpr_def.append(rPr)
            rFonts = rPr.find(W + 'rFonts')
            if rFonts is None:
                rFonts = rPr.makeelement(W + 'rFonts', {})
                rPr.insert(0, rFonts)
            for a in ('w:ascii', 'w:hAnsi', 'w:eastAsia', 'w:cs'):
                rFonts.set(qn(a), SONG)
            print('docDefaults 已设为宋体')
except Exception as e:
    print('docDefaults 处理失败:', str(e)[:80])

doc.save(PATH)
print('字体归一化完成并已保存')
