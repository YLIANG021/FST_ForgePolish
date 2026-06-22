import numpy as np

from ...operators.polish import get_mesh_attributes, get_or_build_topology
from . import smooth_engine


_EMPTY_NEIGHBORS = np.zeros(0, dtype=np.int32)


def _hash_int_sequence(values):
    if not values:
        return 0
    array = np.asarray(values, dtype=np.int64)
    return hash(np.ascontiguousarray(array).tobytes())


def _mesh_topology_signature(mesh):
    edge_pairs = [0] * (len(mesh.edges) * 2)
    if edge_pairs:
        mesh.edges.foreach_get("vertices", edge_pairs)
    return _hash_int_sequence(edge_pairs)


def _mesh_shape_signature(mesh):
    coords = [0.0] * (len(mesh.vertices) * 3)
    if coords:
        mesh.vertices.foreach_get("co", coords)
    quantized = [int(round(value * 100000.0)) for value in coords]
    return _hash_int_sequence(quantized)


def _uses_single_group(face_sets):
    if not face_sets:
        return True
    return len(set(face_sets)) <= 1


def _neighbor_lists_from_pairs(neighbor_data):
    _target_indices, source_indices, neighbor_counts = neighbor_data
    result = []
    cursor = 0
    for count in neighbor_counts:
        next_cursor = cursor + int(count)
        if next_cursor > cursor:
            result.append(source_indices[cursor:next_cursor].astype(np.int32, copy=False))
        else:
            result.append(_EMPTY_NEIGHBORS)
        cursor = next_cursor
    return result


def build_brush_polish_neighbors(mesh, feature_angle):
    face_sets, _mask_list = get_mesh_attributes(mesh)
    single_group = _uses_single_group(face_sets)
    if single_group:
        face_sets = [1] * len(mesh.polygons)

    vert_class, inner_neighbors, boundary_neighbors = get_or_build_topology(
        mesh,
        face_sets,
        feature_angle,
        single_faceset=single_group,
    )

    inner_lists = _neighbor_lists_from_pairs(inner_neighbors)
    boundary_lists = _neighbor_lists_from_pairs(boundary_neighbors)
    polish_neighbors = [_EMPTY_NEIGHBORS] * len(vert_class)

    for vert_index, cls in enumerate(vert_class):
        if cls == 1:
            polish_neighbors[vert_index] = inner_lists[vert_index]
        elif cls in {2, 3}:
            polish_neighbors[vert_index] = boundary_lists[vert_index]

    return polish_neighbors


def polish_neighbors_signature(mesh, feature_angle):
    face_sets, _mask_list = get_mesh_attributes(mesh)
    single_group = _uses_single_group(face_sets)
    if single_group:
        face_sets = [1] * len(mesh.polygons)
    return (
        len(mesh.vertices),
        len(mesh.edges),
        len(mesh.polygons),
        round(float(feature_angle), 6),
        int(single_group),
        _hash_int_sequence(face_sets),
        _mesh_topology_signature(mesh),
        _mesh_shape_signature(mesh) if float(feature_angle) > 0.001 else 0,
    )


def brush_mask_array(mesh):
    _face_sets, mask_list = get_mesh_attributes(mesh)
    return np.asarray(mask_list, dtype=np.float32)


def polish_vertices_at_hit(
    *,
    coords,
    world_positions,
    polish_neighbors,
    mask_array,
    hit_world,
    radius,
    strength,
    hardness,
    spatial_index=None,
):
    local_indices, distances = smooth_engine.world_brush_indices(
        world_positions,
        hit_world,
        radius,
        spatial_index=spatial_index,
    )
    if len(local_indices) == 0:
        return 0

    falloff = 1.0 - np.clip(distances / max(float(radius), 1e-6), 0.0, 1.0)
    factors = smooth_engine.brush_falloff(falloff, hardness) * max(0.0, min(float(strength), 1.0))
    source = coords.copy()
    changed = 0

    for vert_index, factor in zip(local_indices, factors):
        vert_index = int(vert_index)
        factor *= max(0.0, 1.0 - float(mask_array[vert_index]))
        if factor <= 1e-6:
            continue
        neighbors = polish_neighbors[vert_index]
        if neighbors.size == 0:
            continue
        target = source[neighbors].mean(axis=0)
        coords[vert_index] = source[vert_index] + (target - source[vert_index]) * factor
        changed += 1

    return changed
