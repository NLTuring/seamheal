import { useEffect, useRef, useState } from 'react';
import { ArrowDownToLine, Clock3, LoaderCircle, RefreshCw } from 'lucide-react';
import type { Artifact } from './types';

type Item={result_id:string;model_id:string;part_id:string|null;kind:string;model_title:string;created_at:string|null};
const names:Record<string,string>={repair:'几何修复',texture:'纹理补全',split:'分块装配',joint:'燕尾试件'};

export function HistoryPanel({modelId,onRestore}:{modelId:string;onRestore:(item:Artifact)=>void}){
 const [items,setItems]=useState<Item[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
 const [restored,setRestored]=useState<Artifact|null>(null);
 const restoreRequest=useRef<AbortController|null>(null);
 useEffect(()=>()=>restoreRequest.current?.abort(),[]);
 useEffect(()=>{
  const abort=new AbortController();setBusy(true);setError('');
  fetch('/api/history?model_id='+modelId,{signal:abort.signal})
   .then(r=>{if(!r.ok)throw new Error('历史记录读取失败');return r.json();})
   .then(d=>setItems(d.history))
   .catch(e=>{if(!abort.signal.aborted)setError(e.message);})
   .finally(()=>{if(!abort.signal.aborted)setBusy(false);});
  return()=>abort.abort();
 },[modelId,refresh]);
 const restore=async(item:Item)=>{
  setBusy(true);setError('');const abort=new AbortController();restoreRequest.current=abort;
  try{
   const response=await fetch('/api/results/'+item.result_id,{signal:abort.signal});
   if(!response.ok)throw new Error('结果文件无法读取');
   const data=await response.json();
   if(!abort.signal.aborted){setRestored(data);onRestore(data);}
  }catch(e){if(!abort.signal.aborted)setError((e as Error).message);}
  finally{if(!abort.signal.aborted)setBusy(false);}
 };
 return <div className="history-panel">
  <div className="section-eyebrow">HISTORY<span>已保存的处理结果</span></div>
  <p>每次处理独立保存，原模型始终保留。显示此模型最近 200 条记录；选择记录可恢复查看与继续处理。</p>
  <button className="outline-button" disabled={busy} onClick={()=>setRefresh(v=>v+1)}><RefreshCw size={14}/>刷新记录</button>
  {busy&&<LoaderCircle className="spin history-spinner" size={19}/>}
  {restored&&<section className="history-downloads" aria-label="历史结果下载">
   <p>{names[restored.kind]} · 已恢复</p>
   <a className="download-button" href={restored.bundle_url} download><ArrowDownToLine size={15}/>下载历史结果包<span>ZIP</span></a>
   <div className="result-file-links"><a href={restored.result_url} download>GLB 模型</a><a href={restored.report_url} download>参数报告</a></div>
   <div className="result-file-links">{restored.stl_urls.map((part,index)=><a key={part.url} href={part.url} download title={part.name}>部件 {index+1} · STL</a>)}</div>
  </section>}
  <div className="history-list">{items.map(item=><button key={item.result_id} disabled={busy} onClick={()=>void restore(item)}>
   <Clock3 size={17}/><div><b>{names[item.kind]||item.kind}</b><span>{item.created_at?new Date(item.created_at).toLocaleString('zh-CN'):'早期版本记录'}</span><small>{item.part_id||'独立构件'}</small></div>
  </button>)}</div>
  {!busy&&!items.length&&<div className="empty-result">此模型还没有处理记录</div>}
  {error&&<div className="inline-error">{error}</div>}
 </div>;
}
