# -*- coding: utf-8 -*-
"""通用文档后处理流水线。

用法：
    python tools/postprocess.py "文档名.docx"

依次完成：
    1) Word 更新目录与全部域并保存（使目录直接显示条目与页码）
    2) XML 层级字体归一化为宋体（含目录条目这类藏在 w:hyperlink 内的 run）
    3) 重新开启 updateFields
    4) 字体审计
    5) 导出 PDF
    6) 逐页渲染 PNG（供视觉验收）
    7) 输出页数与页密度诊断
"""
import io
import os
import sys
import zipfile

import lxml.etree as ET
import win32com.client as wc

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SONG = '宋体'
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = '愈缝SeamHeal-项目简介文档.docx'

name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
DOCX = name if os.path.isabs(name) else os.path.join(BASE, name)
stem = os.path.splitext(os.path.basename(DOCX))[0]
PREVIEW = os.path.join(BASE, 'preview')
os.makedirs(PREVIEW, exist_ok=True)
PDF = os.path.join(PREVIEW, stem + '.pdf')
PAGES = os.path.join(PREVIEW, stem + '-pages')

if not os.path.exists(DOCX):
    raise SystemExit('找不到文档：' + DOCX)
print('处理文档：%s' % os.path.basename(DOCX))


def open_word():
    app = wc.Dispatch('Word.Application')
    app.Visible = False
    app.DisplayAlerts = 0
    return app


def quit_word(app):
    try:
        app.Quit()
    except Exception:
        pass


# ---------------------------------------------------------------- 1) 更新域
print('\n[1/6] 更新目录与全部域 …')
app = open_word()
doc = app.Documents.Open(DOCX, False, False)
try:
    n = doc.TablesOfContents.Count
    for i in range(1, n + 1):
        doc.TablesOfContents(i).Update()
    print('    目录域数量 =', n)
except Exception as e:
    print('    更新目录异常:', str(e)[:120])
try:
    doc.Fields.Update()
    print('    全部域已更新')
except Exception as e:
    print('    更新全部域异常:', str(e)[:120])
doc.Repaginate()
pages = doc.ComputeStatistics(2)
print('    Word 统计页数 =', pages)
doc.Save()
try:
    doc.Close(0)
except Exception:
    pass
quit_word(app)

# ---------------------------------------------------------------- 2) 字体归一化
print('\n[2/6] 字体归一化为宋体 …')


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
            rFonts.set('{%s}%s' % (W[1:-1], a.split(':')[1]), SONG)
        n += 1
    return n


from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402

doc = Document(DOCX)
total = fix_runs(doc.element)
print('    document.xml 处理 run 数 =', total)
for i, s in enumerate(doc.sections):
    for part in (s.header, s.footer, s.first_page_header, s.first_page_footer,
                 s.even_page_header, s.even_page_footer):
        try:
            fix_runs(part._element)
        except Exception:
            pass
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
print('    样式处理数 =', styled)
try:
    dd = doc.styles.element.find(W + 'docDefaults')
    rpr = dd.find(W + 'rPrDefault/' + W + 'rPr') if dd is not None else None
    if rpr is not None:
        rFonts = rpr.find(W + 'rFonts')
        if rFonts is None:
            rFonts = rpr.makeelement(W + 'rFonts', {})
            rpr.insert(0, rFonts)
        for a in ('w:ascii', 'w:hAnsi', 'w:eastAsia', 'w:cs'):
            rFonts.set(qn(a), SONG)
        print('    docDefaults 已设为宋体')
except Exception as e:
    print('    docDefaults 处理跳过:', str(e)[:80])

# ---------------------------------------------------------------- 3) updateFields
settings = doc.settings.element
uf = settings.find(W + 'updateFields')
if uf is None:
    uf = OxmlElement('w:updateFields')
    settings.append(uf)
uf.set(qn('w:val'), 'true')
print('\n[3/6] updateFields 已设为 true')
doc.save(DOCX)

# ---------------------------------------------------------------- 4) 字体审计
print('\n[4/6] 字体审计 …')
z = zipfile.ZipFile(DOCX)
tot = bad = 0
badmap = {}
for part in z.namelist():
    if not part.endswith('.xml'):
        continue
    root = ET.fromstring(z.read(part))
    for r in root.iter(W + 'r'):
        tot += 1
        rf = r.find(W + 'rPr/' + W + 'rFonts')
        ea = rf.get(qn('w:eastAsia')) if rf is not None else None
        asc = rf.get(qn('w:ascii')) if rf is not None else None
        if ea != SONG or asc != SONG:
            bad += 1
            k = (part, 'eastAsia=%s' % ea, 'ascii=%s' % asc)
            badmap[k] = badmap.get(k, 0) + 1
print('    w:r 总数 = %d，非宋体 = %d' % (tot, bad))
for k, v in sorted(badmap.items(), key=lambda x: -x[1])[:8]:
    print('      ', k, '->', v)

xmlall = ''.join(z.read(n).decode('utf-8', 'ignore')
                 for n in z.namelist() if n.endswith('.xml'))
for f in ('宋体', '黑体', '微软雅黑', '等线', 'Calibri'):
    print('    %-10s 出现 %d 次' % (f, xmlall.count(f)))

# ---------------------------------------------------------------- 5) 导出 PDF
print('\n[5/6] 导出 PDF …')
if os.path.exists(PDF):
    os.remove(PDF)
app = open_word()
doc = app.Documents.Open(DOCX, False, True)
ok = False
for label, fn in (('SaveAs2', lambda: doc.SaveAs2(PDF, 17)),
                  ('SaveAs', lambda: doc.SaveAs(PDF, 17)),
                  ('ExportAsFixedFormat', lambda: doc.ExportAsFixedFormat(PDF, 17))):
    if ok:
        break
    try:
        fn()
        if os.path.exists(PDF):
            ok = True
            print('    导出方式 =', label)
    except Exception as e:
        print('    %s 失败: %s' % (label, str(e)[:90]))
try:
    doc.Close(0)
except Exception:
    pass
quit_word(app)
if not os.path.exists(PDF):
    raise SystemExit('PDF 导出失败')
print('    PDF 大小 = %.1f KB' % (os.path.getsize(PDF) / 1024.0))

# ---------------------------------------------------------------- 6) 渲染与诊断
print('\n[6/6] 渲染页面与页密度诊断 …')
import pymupdf  # noqa: E402

os.makedirs(PAGES, exist_ok=True)
pdf = pymupdf.open(PDF)
texts = []
for i, page in enumerate(pdf, start=1):
    texts.append(page.get_text())
    pdf[i - 1].get_pixmap(dpi=130).save(os.path.join(PAGES, 'page-%02d.png' % i))
print('    总页数 = %d，已渲染 %d 张' % (pdf.page_count, len(texts)))
pdf.close()

print('\n    页密度（字数）：')
sparse = []
for i, t in enumerate(texts, 1):
    n = len(t.strip().replace('\n', ''))
    if n < 250:
        sparse.append(i)
    print('      第 %2d 页：%4d 字%s' % (i, n, '   <== 偏少' if n < 250 else ''))
print('\n    偏少页 =', sparse if sparse else '无')
print('\n完成。PDF：%s' % PDF)
print('页面图片目录：%s' % PAGES)
