"""Local scene editing, geometry/texture repair, manufacturing and history."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import threading
from typing import Literal
from uuid import uuid4
import zipfile
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from engine.mesh_repair import diagnose_mesh
from engine.manufacturing import print_check, split_with_joint, make_joint_sample
from engine.texture_repair import repair_texture, texture_image, replace_basecolor, make_mask
from model_io import load_scene, parts, select_part, isolate, replace_part, world_mesh, MAX_UPLOAD, Z_UP_TO_Y_UP

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT.parent/'assets/sakura_courtyard'
RUNTIME = Path(os.environ.get('SEAMHEAL_RUNTIME', ROOT/'runtime'))
UPLOADS, OUTPUTS, CATALOG = RUNTIME/'imports', RUNTIME/'outputs', RUNTIME/'models.json'
for folder in (UPLOADS, OUTPUTS): folder.mkdir(parents=True, exist_ok=True)
WORKER = threading.Semaphore(1)
READ_WORKERS = threading.Semaphore(3)
CATALOG_LOCK = threading.Lock()


def sample(key,title,subtitle,stem,preview,reference=None):
    return dict(id=key,title=title,subtitle=subtitle,kind='repair',can_repair=True,source_format='glb',
                original_url=f'/assets/exports/{stem}.glb',preview_url=f'/assets/previews/{preview}.png',
                reference_url=f'/assets/exports/{reference}.glb' if reference else None)


SAMPLES = [
    sample('panel','花枝彩绘墙板','平面孔洞 · 连续花纹','panel_damaged','panel_damaged_detail','panel_intact'),
    sample('roof','曲面瓦顶','曲面补片 · 瓦片纹理','roof_damaged','roof_damaged_detail','roof_intact'),
    sample('courtyard','樱庭完整场景','整景浏览 · 构件选择','sakura_courtyard_damaged','courtyard_intact','sakura_courtyard_intact'),
    sample('dovetail','燕尾装配示例','互锁结构 · 分离与装配','dovetail_exploded','dovetail_exploded','dovetail_assembled')]
MODELS = {s['id']:{**s,'path':ASSETS/'exports'/Path(s['original_url']).name} for s in SAMPLES}


def restore_catalog():
    if not CATALOG.exists(): return
    try:
        for record in json.loads(CATALOG.read_text(encoding='utf-8')):
            token = record.get('id','')
            if re.fullmatch(r'import-[a-f0-9]{32}',token) and (UPLOADS/(token+'.glb')).exists():
                MODELS[token] = {**record,'path':UPLOADS/(token+'.glb')}
    except (ValueError,OSError): logging.exception('Catalog unreadable; source files remain intact')


def save_catalog():
    with CATALOG_LOCK:
        records = [{k:v for k,v in m.items() if k!='path'} for m in MODELS.values() if m['id'].startswith('import-')]
        temp = CATALOG.with_suffix('.tmp')
        temp.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8'); temp.replace(CATALOG)


restore_catalog()
app = FastAPI(title='愈缝 SeamHeal · 本地工作台',docs_url='/api/docs',redoc_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])


@app.middleware('http')
async def local_requests(request: Request,call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin and origin not in {
        'http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173','http://testserver'}:
        return JSONResponse({'detail':'请从本地工作台发起操作。'},status_code=403)
    response = await call_next(request)
    response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer'})
    return response


class ModelRequest(BaseModel):
    model_id: str = Field(min_length=1,max_length=64,pattern=r'^[a-zA-Z0-9_-]+$')
    part_id: str|None = Field(default=None,pattern=r'^part-\d{1,3}$')
    result_id: str|None = Field(default=None,pattern=r'^[a-f0-9]{32}$')


class RepairRequest(ModelRequest):
    cleanup: bool = True
    optimize: bool = True


class SceneRepairRequest(RepairRequest):
    part_ids: list[str] = Field(min_length=1,max_length=32)


class TextureRequest(ModelRequest):
    rectangle: tuple[int,int,int,int]
    radius: int = Field(default=3,ge=1,le=15)


class PrintRequest(ModelRequest):
    minimum_wall_mm: float = Field(default=1,gt=0,le=100)
    build_volume_mm: tuple[float,float,float] = (220,220,250)


class SplitRequest(ModelRequest):
    axis: Literal['x','y','z'] = 'x'
    fraction: float = Field(default=.5,ge=.1,le=.9)
    joint: Literal['none','dovetail'] = 'dovetail'
    clearance_mm: float = Field(default=.2,ge=0,le=2)


class JointRequest(BaseModel):
    width_mm: float = Field(default=60,gt=0,le=1000)
    depth_mm: float = Field(default=30,gt=0,le=1000)
    height_mm: float = Field(default=12,gt=0,le=1000)
    clearance_mm: float = Field(default=.2,ge=0,le=2)
    angle_deg: float = Field(default=12,ge=3,le=30)


@contextmanager
def job(exclusive=True):
    semaphore = WORKER if exclusive else READ_WORKERS
    if not semaphore.acquire(blocking=not exclusive): raise HTTPException(429,'已有模型正在处理，请稍后再试。')
    try: yield
    except HTTPException: raise
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    except Exception as exc:
        logging.exception('Processing failed')
        raise HTTPException(422,'无法处理此模型或参数，请检查文件、选中的构件与输入范围。') from exc
    finally: semaphore.release()


def checked_scene(data):
    scene,_ = load_scene(data)
    return scene,select_part(scene)[1]


def get_model(model_id):
    model = MODELS.get(model_id)
    if not model: raise HTTPException(404,'未找到该模型，请重新导入。')
    return model


def read_result(result_id):
    if not re.fullmatch(r'[a-f0-9]{32}',result_id): raise HTTPException(404,'未找到结果。')
    path = OUTPUTS/(result_id+'.json')
    if not path.exists(): raise HTTPException(404,'未找到结果文件。')
    return json.loads(path.read_text(encoding='utf-8'))


def source_scene(body):
    model = get_model(body.model_id); path = model['path']
    if body.result_id:
        report = read_result(body.result_id)
        if report.get('model_id')!=body.model_id or report.get('kind','repair') not in ('repair','texture'):
            raise ValueError('该结果不属于当前模型或不是可继续编辑的结果。')
        path = OUTPUTS/(body.result_id+'.glb')
    data = path.read_bytes(); scene,_ = load_scene(data)
    return model,scene,data


def response_for(token,report):
    return {'result_id':token,'model_id':report.get('model_id'),'part_id':report.get('part_id'),
            'kind':report.get('kind','repair'),'result_url':f'/outputs/{token}.glb',
            'report_url':f'/outputs/{token}.json','bundle_url':f'/outputs/{token}.zip','report':report,
            'stl_urls':[{'name':part['name'],'url':f'/outputs/{token}-part-{i+1}.stl'} for i,part in enumerate(report.get('export_parts',[]))]}


def save_result(scene,report,model_id,part_id=None,kind='repair',input_bytes=b'',extra_files=None):
    token = uuid4().hex; data = scene.export(file_type='glb'); exported,_ = load_scene(data)
    report.update({'result_id':token,'model_id':model_id,'part_id':part_id,'kind':kind,
                   'created_at':datetime.now(timezone.utc).isoformat(),'reference_used':False,
                   'model_title':MODELS.get(model_id,{}).get('title','参数化燕尾试件'),
                   'input_sha256':hashlib.sha256(input_bytes).hexdigest() if input_bytes else None,
                   'output_sha256':hashlib.sha256(data).hexdigest(),'export_reloaded_and_verified':True})
    if kind=='repair':
        for checked_id in report.get('processed_part_ids',[part_id]):
            checked = diagnose_mesh(select_part(exported,checked_id)[2])
            if not checked['watertight'] or not checked['winding_consistent'] or checked['degenerate_triangles']:
                raise ValueError('导出构件未通过闭合与法向复核。')
    attachments = dict(extra_files or {}); export_parts = []
    export_ids = [p['id'] for p in parts(exported)] if kind in ('split','joint') else report.get('processed_part_ids',[part_id])
    if len(export_ids)<=32:
        for i,part in enumerate(export_ids):
            mesh = world_mesh(exported,part,print_axes=True); mesh.apply_scale(1000)
            stl = mesh.export(file_type='stl'); attachments[f'part-{i+1}.stl'] = stl
            export_parts.append({'name':select_part(exported,part)[0],'units':'mm','up_axis':'Z'})
            (OUTPUTS/f'{token}-part-{i+1}.stl').write_bytes(stl)
    report['export_parts'] = export_parts
    report['stl_note'] = 'STL 使用毫米、Z 轴朝上，不含颜色和纹理；GLB 使用米、Y 轴朝上。'
    text = json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8')
    (OUTPUTS/(token+'.glb')).write_bytes(data); (OUTPUTS/(token+'.json')).write_bytes(text)
    with zipfile.ZipFile(OUTPUTS/(token+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('model.glb',data); archive.writestr('report.json',text)
        archive.writestr('README.txt','GLB: metres, Y-up, textured. STL: millimetres, Z-up, geometry only.\nSee report.json for checks and limitations.\n')
        for name,content in attachments.items(): archive.writestr(name,content)
    return response_for(token,report)


@app.get('/api/health')
def health(): return {'status':'ok','version':'0.2.0','engine':'local-hole-fill'}


@app.get('/api/samples')
def samples():
    return {'samples':[{k:v for k,v in m.items() if k not in ('path','archived')} for m in MODELS.values() if not m.get('archived')]}


@app.get('/api/models/{model_id}/parts')
def model_parts(model_id: str):
    with job(False):
        model = get_model(model_id); scene,_ = load_scene(model['path'].read_bytes())
        return {'parts':parts(scene),'warnings':model.get('import_warnings',[])}


@app.get('/api/models/{model_id}/view')
def part_view(model_id: str,part_id: str|None=None,variant: Literal['original','reference']='original',result_id: str|None=None):
    with job(False):
        model,scene,_ = source_scene(ModelRequest(model_id=model_id,part_id=part_id,result_id=result_id))
        if variant=='reference':
            if not model.get('reference_url'): raise HTTPException(404,'此模型没有完整基准。')
            reference,_ = load_scene((ASSETS/'exports'/Path(model['reference_url']).name).read_bytes())
            if part_id:
                node = select_part(scene,part_id)[0]
                match = next((p['id'] for p in parts(reference) if p['name']==node),None)
                if match is None: raise ValueError('基准中没有对应构件。')
                scene = isolate(reference,match)
            else: scene = reference
        elif part_id: scene = isolate(scene,part_id)
        return Response(scene.export(file_type='glb'),media_type='model/gltf-binary')


@app.post('/api/models')
async def import_model(request: Request,filename: str='model.glb',units: Literal['mm','cm','m']='mm'):
    name = Path(filename).name[:120]; extension = Path(name).suffix.lower().lstrip('.')
    if extension not in ('glb','stl','obj','ply'): raise HTTPException(415,'请选择 GLB、STL、OBJ 或 PLY 文件。')
    if sum(not m.get('archived') for m in MODELS.values())>=104: raise HTTPException(429,'已达到 100 个导入模型，请先移除列表中不需要的模型。')
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>MAX_UPLOAD: raise HTTPException(413,'文件超过 32 MB，请拆分模型。')
    with job():
        scene,warnings = await run_in_threadpool(load_scene,bytes(content),extension,units)
        token = 'import-'+uuid4().hex
        (UPLOADS/(token+'.original.'+extension)).write_bytes(content)
        path = UPLOADS/(token+'.glb'); path.write_bytes(scene.export(file_type='glb'))
        model = dict(id=token,title=name,subtitle=f'{extension.upper()} · {len(parts(scene))} 个构件',kind='repair',
                     original_url=f'/imports/{token}.glb',reference_url=None,preview_url=None,can_repair=True,
                     source_format=extension,import_units='m' if extension=='glb' else units,import_warnings=warnings,
                     created_at=datetime.now(timezone.utc).isoformat())
        MODELS[token] = {**model,'path':path}; save_catalog(); return model


@app.delete('/api/models/{model_id}')
def archive_model(model_id: str):
    with job():
        model = get_model(model_id)
        if not model_id.startswith('import-'): raise HTTPException(422,'内置样本不能移除。')
        model['archived']=True; save_catalog(); return {'removed_from_list':True,'source_files_preserved':True}


@app.post('/api/diagnose')
def diagnose(body: ModelRequest):
    with job():
        _,scene,_ = source_scene(body)
        return {'model_id':body.model_id,'part_id':body.part_id,'diagnosis':diagnose_mesh(select_part(scene,body.part_id)[2])}


@app.post('/api/repair')
def repair(body: RepairRequest):
    with job():
        from engine.mesh_repair import repair_advanced_mesh
        _,scene,data = source_scene(body); node,_,mesh,_ = select_part(scene,body.part_id)
        output,report = repair_advanced_mesh(mesh,cleanup=body.cleanup,optimize=body.optimize)
        report['parent_result_id'] = body.result_id
        report['scope'] = '缺陷清理、局部补洞与补片接缝优化；制造检查请另行运行。'
        return save_result(replace_part(scene,node,output),report,body.model_id,body.part_id,input_bytes=data)


@app.post('/api/scene/diagnose')
def scene_diagnosis(body: ModelRequest):
    with job():
        from engine.scene_repair import diagnose_scene
        _,scene,_ = source_scene(body)
        return diagnose_scene(scene)


@app.post('/api/scene/repair')
def scene_repair(body: SceneRepairRequest):
    with job():
        from engine.scene_repair import repair_scene_parts
        _,scene,data = source_scene(body)
        output,report = repair_scene_parts(scene,body.part_ids,body.cleanup,body.optimize)
        report['parent_result_id'] = body.result_id
        return save_result(output,report,body.model_id,input_bytes=data)


@app.get('/api/texture')
def get_texture(model_id: str,part_id: str|None=None,result_id: str|None=None):
    with job(False):
        _,scene,_ = source_scene(ModelRequest(model_id=model_id,part_id=part_id,result_id=result_id))
        image=texture_image(select_part(scene,part_id)[2]); buffer=io.BytesIO(); image.save(buffer,format='PNG')
        return Response(buffer.getvalue(),media_type='image/png')


@app.post('/api/texture/repair')
def texture(body: TextureRequest):
    with job():
        _,scene,data=source_scene(body); node,_,mesh,_=select_part(scene,body.part_id)
        image=texture_image(mesh); mask=make_mask(image.size,rectangle=body.rectangle)
        output,report=repair_texture(image,mask,radius=body.radius); edited=replace_basecolor(mesh,output)
        report.update({'before':diagnose_mesh(mesh),'after':diagnose_mesh(edited),'added_vertices':0,'added_triangles':0,
                       'filled_loops':0,'original_vertices_preserved':True,'original_uv_preserved':True,
                       'parent_result_id':body.result_id,'rectangle':body.rectangle,'warnings':[report.get('warning','')]})
        buffer=io.BytesIO(); output.save(buffer,format='PNG')
        return save_result(replace_part(scene,node,edited),report,body.model_id,body.part_id,'texture',data,{'basecolor.png':buffer.getvalue()})


@app.post('/api/manufacturing/check')
def print_inspection(body: PrintRequest):
    with job():
        _,scene,_=source_scene(body)
        report=print_check(world_mesh(scene,body.part_id,print_axes=True),body.minimum_wall_mm,body.build_volume_mm)
        report['coordinate_system']='打印坐标：毫米，Z 朝上（由 GLB 的 Y 朝上转换）'; return report


@app.post('/api/manufacturing/split')
def split(body: SplitRequest):
    with job():
        _,scene,data=source_scene(body)
        output,report=split_with_joint(world_mesh(scene,body.part_id,print_axes=True),axis=body.axis,
                                       fraction=body.fraction,joint=body.joint,clearance_mm=body.clearance_mm)
        report['parent_result_id'] = body.result_id
        output.apply_transform(Z_UP_TO_Y_UP)
        return save_result(output,report,body.model_id,body.part_id,'split',data)


@app.post('/api/manufacturing/sample')
def joint_sample(body: JointRequest):
    with job():
        scene,report=make_joint_sample(**body.model_dump()); scene.apply_transform(Z_UP_TO_Y_UP)
        return save_result(scene,report,'dovetail',kind='joint')


@app.post('/api/evaluate')
def evaluate(body: ModelRequest):
    with job():
        from engine.quality import compare_reference
        model,scene,_=source_scene(body)
        if not body.result_id or not model.get('reference_url'): raise ValueError('请选择有完整基准的已修复结果。')
        reference,_=load_scene((ASSETS/'exports'/Path(model['reference_url']).name).read_bytes())
        node=select_part(scene,body.part_id)[0]
        ref_id=next((p['id'] for p in parts(reference) if p['name']==node),None)
        if ref_id is None: raise ValueError('完整基准缺少对应构件。')
        measured=compare_reference(world_mesh(scene,body.part_id),world_mesh(reference,ref_id))
        for key in ('mean_distance','rms_distance','max_distance','p95_distance'): measured[key+'_mm']=measured[key]*1000
        measured['comparison_only']=True
        measured['note']='固定种子双向抽样点到表面距离；完整基准仅用于事后评价。最大值不是严格 Hausdorff 距离。'
        return measured


@app.get('/api/history')
def history(model_id: str|None=None):
    records=[]
    for path in sorted(OUTPUTS.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        try:
            report=json.loads(path.read_text(encoding='utf-8'))
            if model_id and report.get('model_id')!=model_id: continue
            if not (OUTPUTS/(path.stem+'.glb')).exists(): continue
            records.append(dict(result_id=path.stem,model_id=report.get('model_id'),part_id=report.get('part_id'),
                                kind=report.get('kind','repair'),model_title=report.get('model_title','模型'),
                                created_at=report.get('created_at'),result_url=f'/outputs/{path.stem}.glb'))
            if len(records)>=200: break
        except (ValueError,OSError): continue
    return {'history':records}


@app.get('/api/results/{result_id}')
def result(result_id: str):
    with job():
        report = read_result(result_id)
        # Upgrade early single-mesh results without changing their geometry.
        if 'kind' not in report and not (OUTPUTS/(result_id+'.zip')).exists():
            data = (OUTPUTS/(result_id+'.glb')).read_bytes()
            scene,_ = load_scene(data)
            mesh = world_mesh(scene,report.get('part_id'),print_axes=True)
            mesh.apply_scale(1000)
            stl = mesh.export(file_type='stl')
            report.update(kind='repair',export_parts=[{'name':select_part(scene)[0],'units':'mm','up_axis':'Z'}],
                          stl_note='STL 使用毫米、Z 轴朝上，不含颜色和纹理；GLB 使用米、Y 轴朝上。')
            report_bytes = json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8')
            (OUTPUTS/f'{result_id}-part-1.stl').write_bytes(stl)
            with zipfile.ZipFile(OUTPUTS/(result_id+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('model.glb',data)
                archive.writestr('report.json',report_bytes)
                archive.writestr('part-1.stl',stl)
            (OUTPUTS/(result_id+'.json')).write_bytes(report_bytes)
        return response_for(result_id,report)


app.mount('/assets',StaticFiles(directory=ASSETS),name='assets')
app.mount('/imports',StaticFiles(directory=UPLOADS),name='imports')
app.mount('/outputs',StaticFiles(directory=OUTPUTS),name='outputs')
if (ROOT/'web/dist').exists(): app.mount('/',StaticFiles(directory=ROOT/'web/dist',html=True),name='web')
