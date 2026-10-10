import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowDownToLine, ArrowRight, Box, Check, CheckCheck, ChevronRight, CircleHelp, Crosshair, FileJson, FolderOpen, Layers3, Leaf, LoaderCircle, Maximize, RotateCcw, ScanLine, Sparkles, SplitSquareHorizontal, Upload, WandSparkles, X } from 'lucide-react';
import { Viewer } from './Viewer';
import type { Artifact, Diagnosis, Part, Sample, SceneDiagnosis } from './types';
import { RepairPanel } from './RepairPanel';
import { SceneRepairPanel, partTitle } from './SceneRepairPanel';
import { TexturePanel } from './TexturePanel';
import { ManufacturingPanel } from './ManufacturingPanel';
import { HistoryPanel } from './HistoryPanel';
import './style.css';
import './workflow.css';

async function api<T>(url:string,body?:unknown):Promise<T>{
  const response=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'操作失败，请检查输入后重试。');
  return data;
}
const fmt=(n:number)=>n.toLocaleString('zh-CN');
const emptySegments:Diagnosis['boundary_segments']=[];

function App(){
  const [samples,setSamples]=useState<Sample[]>([]),[selected,setSelected]=useState<Sample|null>(null);
  const [diagnosis,setDiagnosis]=useState<Diagnosis|null>(null),[result,setResult]=useState<Artifact|null>(null);
  const [sceneDiagnosis,setSceneDiagnosis]=useState<SceneDiagnosis|null>(null),[sceneSelection,setSceneSelection]=useState<string[]>([]);
  const [mode,setMode]=useState<'original'|'result'|'reference'|'compare'|'artifact'>('original');
  const [busy,setBusy]=useState<'diagnose'|'repair'|'import'|null>(null),[error,setError]=useState('');
  const [wireframe,setWireframe]=useState(false),[boundaries,setBoundaries]=useState(true),[resetKey,setResetKey]=useState(0);
  const [help,setHelp]=useState(false),[initLoading,setInitLoading]=useState(true);
  const [parts,setParts]=useState<Part[]>([]),[partId,setPartId]=useState<string|undefined>(),[partsLoading,setPartsLoading]=useState(false);
  const [tool,setTool]=useState<'repair'|'texture'|'manufacture'|'history'>('repair');
  const [cleanup,setCleanup]=useState(true),[optimize,setOptimize]=useState(true),[units,setUnits]=useState('mm');
  const [external,setExternal]=useState<{url:string;label:string}|null>(null),[showSeam,setShowSeam]=useState(false);
  const input=useRef<HTMLInputElement>(null),stage=useRef<HTMLDivElement>(null);
  const generation=useRef(0);
  useEffect(()=>{let active=true;api<{samples:Sample[]}>('/api/samples').then(d=>{if(active){setSamples(d.samples);setSelected(d.samples[0]);}}).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setInitLoading(false);});return()=>{active=false;};},[]);
  useEffect(()=>{
    if(!help)return;
    const onKey=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){setHelp(false);return;}
      if(event.key==='Tab'){
        const buttons=document.querySelectorAll<HTMLButtonElement>('.help-modal button');
        const first=buttons[0],last=buttons[buttons.length-1];
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
      }
    };
    document.addEventListener('keydown',onKey);
    return()=>{document.removeEventListener('keydown',onKey);document.querySelector<HTMLButtonElement>('[aria-label="使用说明"]')?.focus();};
  },[help]);
  useEffect(()=>{
    if(!selected)return;const abort=new AbortController();setPartsLoading(true);setParts([]);
    fetch('/api/models/'+selected.id+'/parts',{signal:abort.signal}).then(async response=>{const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'构件列表读取失败');return data;}).then(data=>{setParts(data.parts);if(data.warnings?.length)setError(data.warnings.join(' '));}).catch(e=>{if(!abort.signal.aborted)setError(e.message);}).finally(()=>{if(!abort.signal.aborted)setPartsLoading(false);});
    return()=>abort.abort();
  },[selected?.id]);
  const choose=(sample:Sample)=>{generation.current++;setSelected(sample);setDiagnosis(null);setResult(null);setMode('original');setError('');setBusy(null);setPartId(undefined);setExternal(null);setShowSeam(false);setSceneDiagnosis(null);setSceneSelection([]);};
  const diagnose=async()=>{
    if(!selected)return;const current=generation.current;setBusy('diagnose');setError('');
    try{
      if(parts.length>1&&!partId){
        const data=await api<SceneDiagnosis>('/api/scene/diagnose',{model_id:selected.id,result_id:result?.result_id});
        if(current===generation.current){setSceneDiagnosis(data);setSceneSelection(data.recommended_part_ids);setDiagnosis(data.diagnosis);setMode(result?'result':'original');}
      }else{
        const data=await api<{diagnosis:Diagnosis}>('/api/diagnose',{model_id:selected.id,part_id:partId,result_id:result?.result_id});
        if(current===generation.current){setDiagnosis(data.diagnosis);setMode(result?'result':'original');}
      }
    }
    catch(e){if(current===generation.current)setError((e as Error).message);}finally{if(current===generation.current)setBusy(null);}
  };
  const repair=async()=>{
    if(!selected)return;const current=generation.current;setBusy('repair');setError('');
    try{const data=await api<Artifact>(parts.length>1&&!partId?'/api/scene/repair':'/api/repair',{model_id:selected.id,part_id:partId,result_id:result?.result_id,cleanup,optimize,...(parts.length>1&&!partId?{part_ids:sceneSelection}:{})});if(current===generation.current){setResult(data);setDiagnosis(data.report.before);setSceneDiagnosis(data.report.scene_after||null);setSceneSelection([]);setMode('result');}}
    catch(e){if(current===generation.current)setError((e as Error).message);}finally{if(current===generation.current)setBusy(null);}
  };
  const importFile=async(file?:File)=>{
    if(!file)return;setError('');if(!/\.(glb|stl|obj|ply)$/i.test(file.name)){setError('请选择 GLB、STL、OBJ 或 PLY 文件。');return;}
    if(file.size>32*1024*1024){setError('文件超过 32 MB，请先拆分模型。');return;}
    const current=generation.current;setBusy('import');
    try{const response=await fetch('/api/models?filename='+encodeURIComponent(file.name)+'&units='+units,{method:'POST',headers:{'Content-Type':'model/gltf-binary'},body:file});const data=await response.json();if(!response.ok)throw new Error(data.detail||'导入失败。');if(current===generation.current){setSamples(s=>[...s,data]);choose(data);}}
    catch(e){if(current===generation.current)setError((e as Error).message);}finally{if(current===generation.current)setBusy(null);if(input.current)input.current.value='';}
  };
  const currentReport=result&&((result.part_id||undefined)===partId)?result:null;
  const currentDiagnosis=mode==='result'?currentReport?.report.after:mode==='original'?diagnosis:null;
  const sourceLabel=selected?.id==='dovetail'?'分离结构':selected?.id.startsWith('import-')?'原始模型':'人为破损';
  const referenceLabel=selected?.id==='dovetail'?'组合结构':'完整基准';
  const viewUrl=(variant:'original'|'reference'|'result')=>{
    if(!selected)return '';
    if(!partId)return variant==='result'?result?.result_url||selected.original_url:variant==='reference'?selected.reference_url||selected.original_url:selected.original_url;
    const query=new URLSearchParams({part_id:partId,variant:variant==='reference'?'reference':'original',...(variant==='result'&&result?{result_id:result.result_id}:{})});
    return '/api/models/'+selected.id+'/view?'+query;
  };
  const url=mode==='artifact'&&external?external.url:viewUrl(mode==='result'?'result':mode==='reference'?'reference':'original');
  const label=mode==='artifact'&&external?external.label:mode==='result'?(result?.kind==='texture'?'纹理补全结果':'算法修复结果'):mode==='reference'?referenceLabel:sourceLabel;
  const canOperate=!!selected&&!busy&&!partsLoading&&(parts.length===1||!!partId);
  const showResult=!!result&&['result','compare'].includes(mode);
  const changePart=(value:string)=>{generation.current++;setPartId(value||undefined);setDiagnosis(null);setError('');setShowSeam(false);setMode(result?'result':'original');setSceneDiagnosis(null);setSceneSelection([]);};
  const receive=(data:Artifact)=>{setResult(data);setDiagnosis(data.report.before);setSceneDiagnosis(data.report.scene_after||null);setSceneSelection([]);setMode('result');setExternal(null);};
  const preview=(url:string,label:string)=>{setExternal({url,label});setMode('artifact');};
  const restore=(data:Artifact)=>{if(data.kind==='split'||data.kind==='joint'){preview(data.result_url,'历史装配结果');return;}setPartId(data.part_id||undefined);receive(data);setTool('repair');};
  const archive=async()=>{if(!selected?.id.startsWith('import-'))return;try{const response=await fetch('/api/models/'+selected.id,{method:'DELETE'});if(!response.ok)throw new Error('移除失败');setSamples(items=>items.filter(s=>s.id!==selected.id));choose(samples[0]);}catch(e){setError((e as Error).message);}};
  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="/"><span className="brand-mark"><Layers3 size={25}/></span><b>愈缝<span>SeamHeal</span></b><span className="brand-divider"/><span className="app-name">模型修复工作台</span></a><div className="top-actions"><span className="local-status"><i/>本地运行</span><span className="version">Workbench 0.2</span><button className="icon-button" aria-label="使用说明" onClick={()=>setHelp(true)}><CircleHelp size={19}/></button></div></header>
    <div className="workspace">
      <aside className="library"><div className="section-heading"><span>模型资源</span><FolderOpen size={17}/></div><button className="import-button" disabled={!!busy} onClick={()=>input.current?.click()}>{busy==='import'?<LoaderCircle className="spin" size={18}/>:<Upload size={18}/>}导入本地模型<span>3D</span></button><input ref={input} type="file" accept=".glb,.stl,.obj,.ply" hidden onChange={e=>void importFile(e.target.files?.[0])}/><label className="import-units">STL / OBJ / PLY 单位<select aria-label="导入模型单位" value={units} onChange={e=>setUnits(e.target.value)}><option value="mm">毫米 mm</option><option value="cm">厘米 cm</option><option value="m">米 m</option></select></label><div className="library-label">演示与测试样本 <span>{samples.length.toString().padStart(2,'0')}</span></div><div className="sample-list">{samples.map((sample,index)=><button key={sample.id} disabled={!!busy} className={'sample-card '+(selected?.id===sample.id?'selected':'')} onClick={()=>choose(sample)}><div className="sample-image">{sample.preview_url?<img src={sample.preview_url} alt=""/>:<Box size={40}/>}<span className="sample-index">{(index+1).toString().padStart(2,'0')}</span>{selected?.id===sample.id&&<span className="selected-check"><Check size={12}/></span>}</div><strong>{sample.title}</strong><span>{sample.subtitle}</span></button>)}</div><div className="library-footer"><span className="leaf-mark"><Leaf size={18}/></span><div><b>从一处缺口开始</b><p>保留几何，也保留细节。</p></div></div></aside>
      <main className="main"><div className="workspace-title"><div className="breadcrumb">我的工作台 <ChevronRight size={14}/> <span>局部修复</span></div><div className="title-row"><div><h1>{selected?.title||'模型修复工作台'}<span className="file-badge">GLB</span></h1><p>{selected?.can_repair?'检查缺陷，修补几何，让原有纹理继续保持。':'自由浏览模型，观察场景与连接结构。'}</p></div><span className="scope-badge"><span/>{parts.length>1?(partId?'已选构件':'多构件场景'):'独立构件'}</span></div></div>
        <div className="workflow-nav">{([['repair','修复与接缝'],['texture','纹理补全'],['manufacture','制造准备'],['history','历史记录']] as const).map(([key,title])=><button key={key} className={tool===key?'active':''} onClick={()=>setTool(key)}>{title}</button>)}</div>
        <div className="part-selector"><label>处理范围<select aria-label="选择场景构件" disabled={partsLoading||!!busy||parts.length<=1} value={partId||''} onChange={e=>changePart(e.target.value)}><option value="">{partsLoading?'正在读取构件…':parts.length>1?`整景诊断与局部修复 · ${parts.length} 个构件`:'独立构件'}</option>{parts.map(p=><option key={p.id} value={p.id}>{p.repair_target?'★ ':''}{partTitle(p.name)} · {p.triangles.toLocaleString()} 面</option>)}</select></label>{selected?.id.startsWith('import-')&&<button className="archive-model" disabled={!!busy} onClick={()=>void archive()}>从列表移除</button>}{result&&<span className="working-version">处理输入：当前保存版本</span>}</div>
        <div className="stepper"><div className="step done"><span><Check size={13}/></span>载入模型</div><div className="step-line"/><div className={'step '+(diagnosis?'done':'active')}><span>{diagnosis?<Check size={13}/>:2}</span>网格诊断</div><div className="step-line"/><div className={'step '+(result?'done':diagnosis?'active':'')}><span>{result?<Check size={13}/>:3}</span>局部修复</div><div className="step-line"/><div className={'step '+(result?'active':'')}><span>4</span>检查与导出</div></div>
        {error&&<div className="error-banner" role="alert"><span>{error}</span><button aria-label="关闭提示" onClick={()=>setError('')}><X size={16}/></button></div>}
        <div className="model-stage" ref={stage}><div className="stage-toolbar"><div className="view-tabs"><button className={mode==='original'?'active':''} onClick={()=>setMode('original')}>{sourceLabel}</button><button disabled={!result} className={mode==='result'?'active':''} onClick={()=>setMode('result')}>修复结果{result&&<i/>}</button>{selected?.reference_url&&<button className={mode==='reference'?'active':''} onClick={()=>setMode('reference')}>{referenceLabel}</button>}</div><button className={'compare-button '+(mode==='compare'?'active':'')} disabled={!result} onClick={()=>setMode(mode==='compare'?'result':'compare')}><SplitSquareHorizontal size={16}/><span>前后对比</span></button></div>
          <div className={'viewports '+(mode==='compare'?'split':'')} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!busy)void importFile(e.dataTransfer.files[0]);}}>{selected?<><Viewer url={mode==='compare'?viewUrl('original'):url} sampleId={selected.id} wireframe={wireframe} boundaries={mode==='compare'?diagnosis?.boundary_segments||emptySegments:showSeam&&mode==='result'?currentReport?.report.seam_segments||emptySegments:currentDiagnosis?.boundary_segments||emptySegments} showBoundary={showSeam&&mode==='result'||boundaries} resetKey={resetKey} label={mode==='compare'?sourceLabel:label}/>{mode==='compare'&&result&&<Viewer url={viewUrl('result')} sampleId={selected.id} wireframe={wireframe} boundaries={emptySegments} showBoundary={false} resetKey={resetKey} label="算法修复结果"/>}</>:<div className="no-model">{initLoading?<><LoaderCircle className="spin"/>正在连接本地工作台…</>:<>连接失败，请确认服务已启动，再刷新页面。</>}</div>}<div className="viewport-tools"><button title="复位视角" aria-label="复位视角" onClick={()=>setResetKey(k=>k+1)}><RotateCcw size={17}/></button><button title="全屏视图" aria-label="全屏视图" onClick={()=>{if(document.fullscreenElement)void document.exitFullscreen();else void stage.current?.requestFullscreen().catch(()=>setError('浏览器未允许全屏显示。'));}}><Maximize size={17}/></button></div><div className="axis-widget"><span className="axis-y">Y</span><span className="axis-z">Z</span><span className="axis-x">X</span><i/></div></div>
          <div className="stage-bottom"><div className="display-options"><button className={showSeam?'on':''} disabled={!currentReport?.report.seam_segments?.length} aria-pressed={showSeam} onClick={()=>{setShowSeam(v=>!v);setMode('result');}}>补片接缝</button><button className={boundaries?'on':''} aria-pressed={boundaries} onClick={()=>setBoundaries(v=>!v)}><span className="mini-check">{boundaries&&<Check size={10}/>}</span><i className="boundary-dot"/>孔洞边界</button><button className={wireframe?'on':''} aria-pressed={wireframe} onClick={()=>setWireframe(v=>!v)}><span className="mini-check">{wireframe&&<Check size={10}/>}</span>线框</button></div><span className="orbit-hint">{mode==='compare'?'左右可独立旋转 · 滚轮缩放':'拖动旋转 · 滚轮缩放 · 右键平移'}</span></div>
        </div>
        <div className="context-strip"><div className="context-icon">{showResult?<CheckCheck size={20}/>:<Crosshair size={20}/>}</div><div><b>{mode==='artifact'?'装配结果已载入，可下载模型与参数报告':showResult?'修复结果已生成，可与原始模型或完整基准比较':mode==='reference'?'完整基准用于核对形状与纹理':selected?.id==='dovetail'?'燕尾连接结构示例':parts.length>1&&!partId?'整景处理模式':'选择网格诊断，定位真实的开放边界'}</b><p>{mode==='artifact'?'各部件可分别导出毫米 STL，装配间隙与闭合检查记录在报告中。':showResult?'结果由当前破损模型计算得到；修复报告记录新增面片和检查结果。':mode==='reference'?'这是人为破损前保存的模型，不代表算法计算结果。':parts.length>1&&!partId?'点击右侧网格诊断，勾选构件后执行局部修复；也可在上方选择单个构件。':'橙色线条表示孔洞轮廓。已有几何与 UV 在补洞过程中保持不变。'}</p></div></div>
        <div className="workspace-footer"><span><Box size={13}/> {currentDiagnosis?`${fmt(currentDiagnosis.triangles)} 个三角面 · ${fmt(currentDiagnosis.vertices)} 个顶点`:'GLB · 内嵌贴图 · 本地处理'}</span><span>SeamHeal / Geometry comes together.</span></div>
      </main>
      <aside className="inspector"><div className="inspector-heading"><ScanLine size={19}/><h2>{tool==='repair'?'修复面板':tool==='texture'?'纹理工作区':tool==='manufacture'?'制造准备':'处理历史'}</h2><span>0{['repair','texture','manufacture','history'].indexOf(tool)+1}</span></div>
        {selected&&tool==='repair'&&parts.length>1&&!partId&&<SceneRepairPanel diagnosis={sceneDiagnosis||currentReport?.report.scene_after||null} result={currentReport} selection={sceneSelection} busy={busy} ready={!partsLoading} cleanup={cleanup} optimize={optimize} setCleanup={setCleanup} setOptimize={setOptimize} onSelect={setSceneSelection} onDiagnose={()=>void diagnose()} onRepair={()=>void repair()} onInspect={changePart}/>}
        {selected&&tool==='repair'&&!(parts.length>1&&!partId)&&<RepairPanel key={selected.id+partId+result?.result_id} modelId={selected.id} partId={partId} diagnosis={diagnosis} result={currentReport} canOperate={canOperate} busy={busy} hasReference={!!selected.reference_url} cleanup={cleanup} optimize={optimize} setCleanup={setCleanup} setOptimize={setOptimize} onDiagnose={()=>void diagnose()} onRepair={()=>void repair()}/>}
        {selected&&tool==='texture'&&(canOperate?<TexturePanel key={selected.id+partId+result?.result_id} modelId={selected.id} partId={partId} resultId={result?.result_id} disabled={!!busy} onResult={receive}/>:<div className="empty-result">请先选择一个带纹理的构件。</div>)}
        {selected&&tool==='manufacture'&&<ManufacturingPanel key={selected.id+partId+result?.result_id} modelId={selected.id} partId={partId} resultId={result?.result_id} disabled={!canOperate} onPreview={preview}/>}
        {selected&&tool==='history'&&<HistoryPanel key={selected.id} modelId={selected.id} onRestore={restore}/>}
      </aside>
    </div>
    {help&&<div className="modal-overlay" onClick={()=>setHelp(false)}><section className="help-modal" role="dialog" aria-modal="true" aria-label="使用说明" onClick={e=>e.stopPropagation()}><button className="modal-close icon-button" aria-label="关闭说明" onClick={()=>setHelp(false)} autoFocus><X size={20}/></button><span className="section-eyebrow">QUICK START</span><h2>把第一个孔洞修好。</h2><ol><li>选择内置样本，或导入 GLB / STL / OBJ / PLY（≤32 MB），多构件场景可直接进行整景诊断。</li><li>点击「开始网格诊断」，查看开放边界；整景模式下勾选待修复构件。</li><li>执行修复与接缝优化，也可在纹理页框选缺失图像区域。</li><li>检查结果，在制造页检查尺寸、抽样壁厚并分块；导出 GLB、STL 和完整报告包。</li></ol><p>模型在本机处理，操作结果自动保留到历史记录。纹理补全预测选区内的内容；制造检查不等同于强度认证。跨 UV 接缝、严重非流形与大规模重建需专用处理。</p><button className="primary-button" onClick={()=>setHelp(false)}>开始使用<ArrowRight size={16}/></button></section></div>}
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
