"""Diagnose a scene by component and repair only explicitly selected components."""
from time import perf_counter

from model_io import parts, select_part, replace_part
from .mesh_repair import diagnose_mesh, repair_advanced_mesh


def diagnose_scene(scene):
    records = []
    for part in parts(scene):
        try:
            diagnosis = diagnose_mesh(select_part(scene, part['id'])[2])
            diagnosis['boundary_segments'] = []  # Mesh-local lines cannot be drawn in the whole scene.
            needs_work = (not diagnosis['watertight'] or not diagnosis['winding_consistent']
                          or diagnosis['degenerate_triangles'] > 0)
            records.append({**part, 'diagnosis': diagnosis, 'needs_work': needs_work, 'error': None})
        except ValueError as exc:
            records.append({**part, 'diagnosis': None, 'needs_work': True, 'error': str(exc)})
    known = [p['diagnosis'] for p in records if p['diagnosis'] is not None]
    aggregate = {key: sum(d[key] for d in known) for key in
                 ('vertices', 'triangles', 'boundary_edges', 'boundary_loops', 'nonmanifold_edges', 'degenerate_triangles')}
    aggregate.update({key: len(known) == len(records) and all(d[key] for d in known)
                      for key in ('watertight', 'winding_consistent', 'has_uv')})
    aggregate['boundary_segments'] = []
    return {'parts': records, 'total_parts': len(records),
            'issue_parts': sum(p['needs_work'] for p in records),
            'recommended_part_ids': [p['id'] for p in records if p['repair_target'] and p['needs_work'] and not p['error']],
            'diagnosis': aggregate}


def repair_scene_parts(scene, part_ids, cleanup=True, optimize=True):
    started = perf_counter()
    listing = {p['id']: p for p in parts(scene)}
    if not part_ids or len(part_ids) > 32 or len(set(part_ids)) != len(part_ids):
        raise ValueError('请选择 1–32 个不同构件。')
    if any(part_id not in listing for part_id in part_ids):
        raise ValueError('选择中含有不存在的构件，请重新诊断。')
    before = diagnose_scene(scene)
    output = scene.copy()
    reports = []
    # All-or-nothing: never save an incomplete batch under a successful repair label.
    for part_id in part_ids:
        node, _, mesh, _ = select_part(output, part_id)
        try:
            repaired, report = repair_advanced_mesh(mesh, cleanup=cleanup, optimize=optimize)
        except ValueError as exc:
            raise ValueError(f'构件 {node} 无法自动修复：{exc} 本次场景结果未保存，请取消该构件后重试。') from exc
        output = replace_part(output, node, repaired)
        reports.append({'id': part_id, 'name': node, 'report': report})
    after = diagnose_scene(output)
    report = {
        'scope_type': 'scene', 'method': 'selected_component_local_repair',
        'scope': '整景诊断后逐一修复明确选中的构件；其他构件保持不变。',
        'before': before['diagnosis'], 'after': after['diagnosis'],
        'scene_before': before, 'scene_after': after,
        'processed_part_ids': list(part_ids), 'part_reports': reports,
        'original_vertices_preserved': all(p['report']['original_vertices_preserved'] for p in reports),
        'original_uv_preserved': all(p['report']['original_uv_preserved'] is not False for p in reports),
        'elapsed_ms': round((perf_counter() - started) * 1000, 2),
        'warnings': [f"所选 {len(reports)} 个构件已复核；整景仍有 {after['issue_parts']} 个构件存在开放边界或其他拓扑问题。"],
    }
    for key in ('added_vertices', 'added_triangles', 'filled_loops'):
        report[key] = sum(p['report'][key] for p in reports)
    return output, report
