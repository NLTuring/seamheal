"""Regression: default courtyard diagnosis/repair and readable responsive type."""
import json
import re
import zipfile
from playwright.sync_api import sync_playwright
from browser_smoke import BASE, BROWSER, QA, ready, post_click, download


def main():
    errors=[]
    report={}
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=BROWSER,headless=True,
                                  args=['--enable-unsafe-swiftshader','--use-angle=swiftshader'])
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(60000)
        page.context.new_cdp_session(page).send('Network.enable',{'maxTotalBufferSize':256*1024*1024,'maxResourceBufferSize':64*1024*1024})
        page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(BASE,wait_until='networkidle')
            page.get_by_role('button',name=re.compile('樱庭完整场景')).click()
            page.get_by_text('整景网格诊断',exact=True).wait_for()
            assert page.get_by_label('选择场景构件').input_value()==''
            assert page.get_by_role('button',name='开始网格诊断',exact=True).is_enabled()
            diagnosed=post_click(page,'/api/scene/diagnose',page.get_by_role('button',name='开始网格诊断',exact=True))
            assert diagnosed['total_parts']==56
            assert page.get_by_role('checkbox',name='修复花枝彩绘墙板',exact=True).is_checked()
            assert page.get_by_role('checkbox',name='修复曲面瓦顶',exact=True).is_checked()
            assert page.get_by_role('button',name='执行局部修复',exact=True).is_enabled()
            ready(page)
            page.screenshot(path=str(QA/'courtyard-diagnosis-readable.png'),full_page=True)
            repaired=post_click(page,'/api/scene/repair',page.get_by_role('button',name='执行局部修复',exact=True))
            page.get_by_text('所选 2 个构件修复完成',exact=True).wait_for()
            ready(page)
            assert repaired['report']['scene_after']['issue_parts']==14
            assert all(item['report']['after']['boundary_edges']==0 for item in repaired['report']['part_reports'])
            bundle=download(page,'下载场景与报告包','courtyard-batch-repaired.zip')
            with zipfile.ZipFile(bundle) as archive:
                assert archive.testzip() is None
                assert {'model.glb','report.json','part-1.stl','part-2.stl'}.issubset(archive.namelist())
            page.get_by_role('button',name='前后对比',exact=True).click()
            ready(page,2)
            page.screenshot(path=str(QA/'courtyard-batch-comparison.png'),full_page=True)
            page.get_by_role('button',name='修复结果',exact=True).click()
            ready(page)
            report['scene']={'parts':56,'repaired':2,'other_issues_reported':14,'bundle_verified':True}
            print('Default courtyard: diagnosis, batch repair, complete scene and ZIP verified.',flush=True)
            report['responsive_fonts']={}
            for width in (1440,1280,1024,768,390):
                page.set_viewport_size({'width':width,'height':1000 if width>700 else 844})
                page.wait_for_function('document.documentElement.scrollWidth <= window.innerWidth')
                fonts=page.evaluate('''() => Object.fromEntries(['.primary-button','.scene-parts>p','.sample-card strong','.workflow-nav button','.part-selector select'].map(selector=>[selector,parseFloat(getComputedStyle(document.querySelector(selector)).fontSize)]))''')
                assert min(fonts.values())>=14,fonts
                report['responsive_fonts'][str(width)]=fonts
                page.screenshot(path=str(QA/f'readable-courtyard-{width}.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            roof=next(part for part in diagnosed['parts'] if part['name']=='Roof_RepairTarget')
            page.get_by_label('选择场景构件').select_option(roof['id'])
            individual=post_click(page,'/api/diagnose',page.get_by_role('button',name='开始网格诊断',exact=True))
            assert individual['diagnosis']['boundary_edges']==0
            for tab in ('纹理补全','制造准备','历史记录'):
                page.get_by_role('button',name=tab,exact=True).click()
                page.wait_for_timeout(150)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(QA/f'readable-panel-{tab}.png'),full_page=True)
            page.locator('.history-list>button').first.click()
            page.get_by_text('所选 2 个构件修复完成',exact=True).wait_for()
            ready(page)
            assert page.get_by_label('选择场景构件').input_value()==''
            assert not errors,errors
            report.update(status='passed',browser_errors=errors,history_restored=True,individual_continuation=True)
        except Exception:
            page.screenshot(path=str(QA/'scene-failure.png'),full_page=True)
            raise
        finally:
            browser.close()
    (QA/'scene-readability-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':
    main()
