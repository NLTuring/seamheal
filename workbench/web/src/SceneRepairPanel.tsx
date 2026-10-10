import { ArrowDownToLine, CheckCheck, LoaderCircle, ScanLine, Sparkles } from 'lucide-react';
import type { Artifact, SceneDiagnosis, ScenePart } from './types';

export const partTitle = (name:string) => name === 'Panel_RepairTarget' ? '花枝彩绘墙板' : name === 'Roof_RepairTarget' ? '曲面瓦顶' : name;
type Props = {
 diagnosis:SceneDiagnosis|null;result:Artifact|null;selection:string[];busy:string|null;ready:boolean;
 cleanup:boolean;optimize:boolean;setCleanup:(v:boolean)=>void;setOptimize:(v:boolean)=>void;
 onSelect:(ids:string[])=>void;onDiagnose:()=>void;onRepair:()=>void;onInspect:(id:string)=>void;
};

export function SceneRepairPanel(p:Props){
 const d=p.diagnosis;
 const sceneResult=p.result?.report.scope_type==='scene'?p.result:null;
 const rows=d?.parts.filter(part=>part.needs_work)||[];
 const row=(part:ScenePart)=><div className="scene-part-row" key={part.id}>
  <label><input type="checkbox" aria-label={`修复${partTitle(part.name)}`} checked={p.selection.includes(part.id)} disabled={!!p.busy||!!part.error||!!part.diagnosis?.nonmanifold_edges} onChange={e=>p.onSelect(e.target.checked?[...p.selection,part.id]:p.selection.filter(id=>id!==part.id))}/><span><b>{partTitle(part.name)}</b><small>{part.error||`边界边 ${part.diagnosis?.boundary_edges} · 非流形边 ${part.diagnosis?.nonmanifold_edges}`}</small></span></label>
  <button disabled={!!p.busy} onClick={()=>p.onInspect(part.id)}>查看构件</button>
 </div>;
 return <>
  <section className="inspect-section scene-panel">
   <div className="section-eyebrow">SCENE<span>整景网格诊断</span></div>
   <div className="diagnosis-card"><ScanLine size={28}/><strong>{d?`已检查 ${d.total_parts} 个构件`:'检查整个场景'}</strong><p>{d?`${d.issue_parts} 个构件存在开放边界或其他拓扑问题`:'逐个检查构件，再选择需要修复的局部。'}</p><button className="outline-button" disabled={!p.ready||!!p.busy} onClick={p.onDiagnose}>{p.busy==='diagnose'?<LoaderCircle className="spin" size={16}/>:<ScanLine size={16}/>} {d?'重新诊断':'开始网格诊断'}</button></div>
   {d&&<div className="scene-parts"><h3>局部修复范围 <span>已选 {p.selection.length} 件</span></h3><p>{rows.some(part=>part.repair_target)?'已优先选中标注的破损墙板与屋面。':'勾选需要修复的构件。'}开放的装饰表面需按用途判断是否封闭。</p>{rows.filter(part=>part.repair_target).map(row)}
    {rows.some(part=>!part.repair_target)&&<details><summary>其他待复核构件（{rows.filter(part=>!part.repair_target).length}）</summary>{rows.filter(part=>!part.repair_target).map(row)}</details>}
    {!rows.length&&<p>本次拓扑检查未发现待修复构件。</p>}
   </div>}
  </section>
  <section className="inspect-section"><div className="section-eyebrow">REPAIR<span>场景局部修复</span></div><div className="repair-options"><label><input type="checkbox" checked={p.cleanup} onChange={e=>p.setCleanup(e.target.checked)}/>清理重复面、退化面与法向</label><label><input type="checkbox" checked={p.optimize} onChange={e=>p.setOptimize(e.target.checked)}/>优化补片接缝连续性</label></div><button className="primary-button" disabled={!p.ready||!!p.busy||!d||!p.selection.length||p.selection.length>32} onClick={p.onRepair}>{p.busy==='repair'?<LoaderCircle className="spin" size={17}/>:<Sparkles size={17}/>} {p.busy==='repair'?'正在修复所选构件…':'执行局部修复'}</button><p className="button-note">{d?`处理勾选的 ${p.selection.length} 个构件，保留整个场景；每次最多 32 件。`:'完成整景诊断后，即可修复所选局部。'}</p></section>
  {sceneResult&&<section className="inspect-section"><div className="section-eyebrow">RESULT<span>整景结果与导出</span></div><div className="success-line"><CheckCheck size={17}/><b>所选 {sceneResult.report.processed_part_ids?.length} 个构件修复完成</b></div><div className="scene-results">{sceneResult.report.part_reports?.map(part=><div key={part.id}><b>{partTitle(part.name)}</b><span>边界边 {part.report.before.boundary_edges} → {part.report.after.boundary_edges}</span></div>)}</div><p className="scene-remaining">整景仍有 {sceneResult.report.scene_after?.issue_parts} 个构件待复核，详情见报告。</p><a className="download-button" href={sceneResult.result_url} download><ArrowDownToLine size={16}/>导出修复场景<span>GLB</span></a><a className="download-button bundle-button" href={sceneResult.bundle_url} download>下载场景与报告包<span>ZIP</span></a><div className="result-file-links"><a href={sceneResult.report_url} download>场景修复报告</a>{sceneResult.stl_urls.map(part=><a key={part.url} href={part.url} download>{partTitle(part.name)} STL</a>)}</div></section>}
 </>;
}
