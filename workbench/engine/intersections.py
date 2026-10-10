"""Bounded broad-phase and SAT check for non-adjacent triangle intersections."""
import heapq
from time import perf_counter
import numpy as np


def _intersects(a,b,tolerance):
    ea=np.roll(a,-1,axis=0)-a; eb=np.roll(b,-1,axis=0)-b
    na=np.cross(ea[0],ea[1]); nb=np.cross(eb[0],eb[1])
    axes=np.concatenate([[na,nb],np.cross(ea[:,None,:],eb[None,:,:]).reshape(-1,3),
                         np.cross(np.tile(na,(6,1)),np.concatenate([ea,eb]))])
    length=np.linalg.norm(axes,axis=1); axes=axes[length>1e-15]/length[length>1e-15,None]
    pa=a@axes.T; pb=b@axes.T
    return not np.any((pa.max(axis=0)<pb.min(axis=0)-tolerance)|(pb.max(axis=0)<pa.min(axis=0)-tolerance))


def self_intersections(mesh,max_pairs=20000,max_seconds=3):
    report={'status':'checked','intersection_pairs':0,'tested_pairs':0,'examples':[],
            'scope':'不共享位置顶点的三角面相交/接触检测；共享顶点的相邻面重叠不在本项范围内。'}
    if len(mesh.faces)>50000:
        report.update(status='not_checked',reason='本项最多支持 5 万个三角面。'); return report
    triangles=np.asarray(mesh.triangles); low=triangles.min(axis=1); high=triangles.max(axis=1)
    scale=max(float(np.linalg.norm(mesh.extents)),1e-12); tol=scale*1e-9
    _,welded=np.unique(np.round(mesh.vertices/(scale*1e-8)).astype(np.int64),axis=0,return_inverse=True)
    faces=welded[mesh.faces]
    active=set(); heap=[]; started=perf_counter()
    for index in np.argsort(low[:,0]):
        while heap and heap[0][0]<low[index,0]-tol:
            _,expired=heapq.heappop(heap); active.discard(expired)
        if perf_counter()-started>max_seconds:
            report.update(status='partial',reason='到达时间预算，未检查的面不能视为通过。'); break
        if active:
            ids=np.fromiter(active,dtype=int)
            overlap=np.all(high[ids,1:]>=low[index,1:]-tol,axis=1)&np.all(low[ids,1:]<=high[index,1:]+tol,axis=1)
            for other in ids[overlap]:
                if np.any(faces[other,:,None]==faces[index,None,:]): continue
                if report['tested_pairs']>=max_pairs:
                    report.update(status='partial',reason='到达候选面预算，未检查的面不能视为通过。'); return report
                report['tested_pairs']+=1
                if _intersects(triangles[index],triangles[other],tol):
                    report['intersection_pairs']+=1
                    if len(report['examples'])<20: report['examples'].append([int(index),int(other)])
        active.add(int(index)); heapq.heappush(heap,(high[index,0],int(index)))
    return report
