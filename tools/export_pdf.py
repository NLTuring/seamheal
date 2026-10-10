# -*- coding: utf-8 -*-
"""用 Word COM 把 DOCX 导出为 PDF（Python 版，原生支持中文路径）。"""
import os
import time
import win32com.client as wc

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, '愈缝SeamHeal-项目简介文档.docx')
OUT = os.path.join(BASE, 'preview', 'brief.pdf')
os.makedirs(os.path.dirname(OUT), exist_ok=True)
if os.path.exists(OUT):
    os.remove(OUT)

# wdFormatPDF / wdExportFormatPDF
WD_FORMAT_PDF = 17

app = wc.Dispatch('Word.Application')
app.Visible = False
app.DisplayAlerts = 0

doc = app.Documents.Open(SRC, False, True)
try:
    print('打开成功，页数 =', doc.ComputeStatistics(2))
except Exception as e:
    print('页数统计失败:', e)

ok = False
attempts = [
    ('SaveAs2', lambda: doc.SaveAs2(OUT, WD_FORMAT_PDF)),
    ('SaveAs', lambda: doc.SaveAs(OUT, WD_FORMAT_PDF)),
    ('ExportAsFixedFormat', lambda: doc.ExportAsFixedFormat(OUT, WD_FORMAT_PDF)),
]
for name, fn in attempts:
    if ok:
        break
    try:
        fn()
        if os.path.exists(OUT):
            ok = True
            print('导出方式 =', name)
    except Exception as e:
        print('%s 失败: %s' % (name, str(e)[:110]))

# 兜底：打印到 Microsoft Print to PDF
if not ok:
    try:
        doc.PrintOut(False, False, 0, '', 'Microsoft Print to PDF',
                     True, 0, '', OUT)
        for _ in range(30):
            time.sleep(2)
            if os.path.exists(OUT) and os.path.getsize(OUT) > 0:
                ok = True
                break
        print('导出方式 = PrintOut' if ok else 'PrintOut 未产出文件')
    except Exception as e:
        print('PrintOut 失败: %s' % str(e)[:110])

try:
    doc.Close(0)
except Exception:
    pass
try:
    app.Quit()
except Exception:
    pass

print('结果 =', 'PDF 已生成' if os.path.exists(OUT) else 'PDF 缺失')
if os.path.exists(OUT):
    print('大小 = %.1f KB' % (os.path.getsize(OUT) / 1024.0))
