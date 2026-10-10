"""Exercise real UI workflows against localhost:8765 with installed Edge/Chrome."""
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
import trimesh
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'runtime/qa'
QA.mkdir(parents=True, exist_ok=True)
BASE = 'http://127.0.0.1:8765'
BROWSER = next((str(p) for p in [
    Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'),
    Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'),
] if p.exists()), None)


def ready(page, count=1):
    page.wait_for_function('(count) => document.querySelectorAll(\'canvas[data-loaded="true"]\').length === count', arg=count, timeout=60000)


def post_click(page, endpoint, button):
    with page.expect_response(lambda r: r.url.endswith(endpoint) and r.request.method == 'POST', timeout=60000) as response:
        button.click()
    assert response.value.ok, response.value.text()
    return response.value.json()


def pipeline(page, key):
    diagnosis = post_click(page, '/api/diagnose', page.get_by_role('button', name='开始网格诊断', exact=True))
    assert diagnosis['diagnosis']['boundary_loops'] > 0
    result = post_click(page, '/api/repair', page.get_by_role('button', name='执行局部修复', exact=True))
    page.get_by_text('补后检查通过', exact=True).wait_for()
    ready(page)
    report = result['report']
    assert report['after']['boundary_edges'] == 0 and report['after']['watertight']
    assert report['reference_used'] is False and report['original_uv_preserved']
    page.screenshot(path=str(QA / f'{key}-repaired.png'), full_page=True)
    print(key + ': repaired', flush=True)
    return result


def download(page, label, name):
    with page.expect_download() as item:
        page.get_by_role('link', name=re.compile(label)).first.click()
    target = QA / name
    item.value.save_as(str(target))
    assert target.stat().st_size > 100
    return target


def main():
    errors, result = [], {}
    imported = None
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=BROWSER, headless=True,
                                    args=['--enable-unsafe-swiftshader', '--use-angle=swiftshader'])
        page = browser.new_page(viewport={'width':1440,'height':1000}, device_scale_factor=1)
        # Whole-scene GLBs otherwise evict small API bodies from Chromium's inspector cache.
        page.context.new_cdp_session(page).send('Network.enable', {'maxTotalBufferSize':256*1024*1024,'maxResourceBufferSize':64*1024*1024})
        page.set_default_timeout(30000)
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            page.goto(BASE, wait_until='networkidle')
            ready(page)
            panel = pipeline(page, 'panel')
            result['panel'] = {k:panel['report'][k] for k in ('added_vertices','added_triangles','filled_loops')}
            download(page, '导出修复模型', 'browser-panel-result.glb')
            bundle = download(page, '下载模型与报告包', 'browser-panel-result.zip')
            with zipfile.ZipFile(bundle) as archive:
                assert archive.testzip() is None
                assert {'model.glb','report.json','part-1.stl'}.issubset(archive.namelist())
            page.get_by_role('button', name='前后对比', exact=True).click()
            ready(page, 2)
            page.screenshot(path=str(QA/'comparison.png'), full_page=True)
            page.get_by_role('button', name='完整基准', exact=True).click()
            ready(page)
            page.get_by_role('button', name='补片接缝', exact=True).click()
            assert page.get_by_role('button', name='补片接缝', exact=True).get_attribute('aria-pressed') == 'true'
            measured = post_click(page, '/api/evaluate', page.get_by_role('button', name='与完整基准测量比较'))
            assert measured['comparison_only'] and measured['mean_distance_mm'] >= 0
            result['panel_reference'] = {k:measured[k] for k in ('mean_distance_mm','max_distance_mm')}

            # Rectangle selected through real pointer events, followed by a geometry-preserving image repair.
            page.get_by_role('button', name='纹理补全', exact=True).click()
            canvas = page.get_by_label('框选纹理区域')
            canvas.wait_for()
            canvas.scroll_into_view_if_needed()
            box = canvas.bounding_box()
            page.mouse.move(box['x']+box['width']*.22,box['y']+box['height']*.22)
            page.mouse.down()
            page.mouse.move(box['x']+box['width']*.29,box['y']+box['height']*.29,steps=8)
            page.mouse.up()
            page.screenshot(path=str(QA/'texture-selection.png'), full_page=True)
            texture = post_click(page, '/api/texture/repair', page.get_by_role('button',name='补全选中纹理'))
            assert texture['report']['outside_mask_preserved']
            assert texture['report']['parent_result_id'] == panel['result_id']
            result['texture'] = {'masked_pixels':texture['report']['masked_pixels'],'outside_mask_preserved':True}
            ready(page)
            page.get_by_role('button', name='历史记录', exact=True).click()
            page.locator('.history-list>button').first.wait_for()
            page.locator('.history-list>button').first.click()
            page.get_by_text('纹理补全已生成', exact=True).wait_for()
            assert texture['result_id'] in page.get_by_role('link',name='修复报告',exact=True).get_attribute('href')
            print('texture and history: passed', flush=True)

            page.get_by_role('button', name=re.compile('曲面瓦顶.*曲面补片')).click()
            ready(page)
            roof = pipeline(page, 'roof')
            report = roof['report']
            result['roof_seam'] = {'before':report['seam_before']['mean_angle_deg'], 'after':report['seam_after']['mean_angle_deg'], 'moved_vertices':report['seam_optimization']['moved_vertices']}
            assert result['roof_seam']['after'] <= result['roof_seam']['before']+1e-8
            page.get_by_role('button', name='前后对比', exact=True).click()
            ready(page,2)
            page.screenshot(path=str(QA/'roof-comparison.png'), full_page=True)

            page.get_by_role('button',name=re.compile('樱庭完整场景.*整景浏览')).click()
            ready(page)
            page.get_by_text('整景网格诊断',exact=True).wait_for()
            assert page.get_by_role('button',name='开始网格诊断',exact=True).is_enabled()
            listing = page.request.get(BASE+'/api/models/courtyard/parts').json()['parts']
            targets = [part for part in listing if part['repair_target']]
            courtyard_results = []
            for part in targets:
                page.get_by_label('选择场景构件').select_option(part['id'])
                ready(page)
                courtyard_results.append(pipeline(page,part['name']))
                page.get_by_role('button',name='完整基准',exact=True).click()
                ready(page)
            assert courtyard_results[1]['report']['parent_result_id'] == courtyard_results[0]['result_id']
            page.get_by_label('选择场景构件').select_option('')
            page.get_by_role('button',name='修复结果',exact=True).click()
            ready(page)
            page.screenshot(path=str(QA/'courtyard-repaired.png'),full_page=True)
            result['scene'] = {'parts':len(listing),'chained_repairs':len(courtyard_results)}
            page.get_by_role('button',name='制造准备',exact=True).click()
            page.locator('summary').filter(has_text='参数化燕尾试件').click()
            joint = post_click(page,'/api/manufacturing/sample',page.get_by_role('button',name='生成燕尾试件',exact=True))
            assert len(joint['stl_urls']) == 2 and all(part['watertight'] for part in joint['report']['parts'])
            ready(page)
            page.screenshot(path=str(QA/'joint-sample.png'),full_page=True)
            result['standalone_joint'] = {'parts':2,'measured_gap_mm':joint['report']['measured_gap_mm']}

            # STL file chosen through the actual file input; dimension check detects axis/unit errors.
            fixture = QA/'browser-box-60x30x12.stl'
            fixture.write_bytes(trimesh.creation.box(extents=[60,30,12]).export(file_type='stl'))
            page.get_by_label('导入模型单位').select_option('mm')
            with page.expect_response(lambda r:'/api/models?' in r.url and r.request.method=='POST') as response:
                page.locator('input[type=file]').set_input_files(str(fixture))
            assert response.value.ok,response.value.text()
            page.get_by_role('heading',name=re.compile('browser-box-60x30x12.stl')).wait_for()
            imported = [m for m in page.request.get(BASE+'/api/samples').json()['samples'] if m['title']==fixture.name][-1]
            ready(page)
            checked = post_click(page,'/api/manufacturing/check',page.get_by_role('button',name='运行打印检查',exact=True))
            np.testing.assert_allclose(checked['dimensions_mm'],[60,30,12],rtol=1e-5)
            assert checked['self_intersection']['status']=='checked'
            page.get_by_text('非相邻面自交',exact=True).wait_for()
            split = post_click(page,'/api/manufacturing/split',page.get_by_role('button',name='生成分块与装配',exact=True))
            assert all(part['watertight'] for part in split['report']['parts'])
            assert split['report']['measured_gap_mm'] > 0
            ready(page)
            bundle = download(page,'下载完整装配包','browser-dovetail-assembly.zip')
            with zipfile.ZipFile(bundle) as archive:
                assert archive.testzip() is None
                for filename in ('part-1.stl','part-2.stl'):
                    mesh=trimesh.load(io.BytesIO(archive.read(filename)),file_type='stl')
                    assert mesh.is_watertight
            page.screenshot(path=str(QA/'manufacturing.png'),full_page=True)
            result['manufacturing'] = {'dimensions_mm':checked['dimensions_mm'],'split_parts':2,'measured_gap_mm':split['report']['measured_gap_mm']}
            result['persistence_fixture'] = {'model_id':imported['id'],'result_id':split['result_id']}
            print('scene selection, independent joint, STL import, print check, dovetail split: passed',flush=True)

            page.reload(wait_until='networkidle')
            page.get_by_role('button',name=re.compile('browser-box-60x30x12.stl')).last.click()
            page.get_by_role('button',name='历史记录',exact=True).click()
            page.locator('.history-list>button').first.click()
            ready(page)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(QA/'mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),'horizontal overflow'
            page.get_by_role('button',name='使用说明',exact=True).click()
            page.get_by_role('dialog').wait_for()
            page.get_by_role('button',name='关闭说明',exact=True).click()
            assert not errors,errors
            result.update(status='passed',browser_errors=errors,download_verified=True,mobile_no_horizontal_overflow=True)
        except Exception:
            page.screenshot(path=str(QA/'failure.png'),full_page=True)
            (QA/'failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
            raise
        finally:
            browser.close()
    (QA/'browser-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__ == '__main__':
    main()
