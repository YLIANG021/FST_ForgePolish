import math

import numpy as np

EDGE_STRENGTH_SCALE = 0.2
EDGE_FLOW_FALLBACK_SCALE = 1.0
SHRINK_COMPENSATION = -0.53
NORMAL_PROJECTION_SCALE = 0.65
RING_SCALE_EPSILON = 1e-10
MOVED_EPSILON = 1e-12


def _corner_is_locked(index, neighbors, coords, feature_angle):
    if feature_angle <= 0.001 or len(neighbors) != 2:
        return False

    v1 = coords[neighbors[0]] - coords[index]
    v2 = coords[neighbors[1]] - coords[index]
    len1 = float(np.linalg.norm(v1))
    len2 = float(np.linalg.norm(v2))
    if len1 <= 1e-12 or len2 <= 1e-12:
        return True

    dot = float(np.dot(v1 / len1, v2 / len2))
    return dot >= -math.cos(feature_angle)


def _vertex_normal(vert):
    normal = vert.normal
    length = normal.length
    if length <= 1e-12:
        return None
    return np.asarray((normal.x / length, normal.y / length, normal.z / length), dtype=np.float32)


def _build_selected_edge_graph(selected_edges):
    adjacency = {}
    vertex_by_index = {}

    for edge in selected_edges:
        a_vert, b_vert = edge.verts
        a = a_vert.index
        b = b_vert.index
        vertex_by_index[a] = a_vert
        vertex_by_index[b] = b_vert
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)

    return adjacency, vertex_by_index


def _face_side_vert_index(face, center_index, other_index):
    verts = list(face.verts)
    count = len(verts)
    for index, vert in enumerate(verts):
        if vert.index != center_index:
            continue

        prev_vert = verts[(index - 1) % count]
        next_vert = verts[(index + 1) % count]
        if prev_vert.index == other_index:
            return next_vert.index
        if next_vert.index == other_index:
            return prev_vert.index
        return None

    return None


def _edge_flow_specs(selected_edges):
    specs = {}
    vertex_by_index = {}

    for edge in selected_edges:
        if len(edge.link_faces) < 2:
            continue

        a_vert, b_vert = edge.verts
        a = a_vert.index
        b = b_vert.index
        vertex_by_index[a] = a_vert
        vertex_by_index[b] = b_vert

        a_sides = []
        b_sides = []
        for face in edge.link_faces:
            a_side = _face_side_vert_index(face, a, b)
            b_side = _face_side_vert_index(face, b, a)
            if a_side is not None:
                a_sides.append(a_side)
            if b_side is not None:
                b_sides.append(b_side)

        if len(a_sides) >= 2:
            specs.setdefault(a, []).append(tuple(a_sides))
        if len(b_sides) >= 2:
            specs.setdefault(b, []).append(tuple(b_sides))

    return specs, vertex_by_index


def _apply_edge_flow_fallback(selected_edges, coords, mask_array, iterations, strength, locked_indices=None):
    specs, vertex_by_index = _edge_flow_specs(selected_edges)
    if locked_indices:
        specs = {
            vert_index: side_groups
            for vert_index, side_groups in specs.items()
            if vert_index not in locked_indices
        }
    if not specs:
        return coords, 0

    work_coords = coords.copy()
    effective_strength = max(0.0, strength) * EDGE_STRENGTH_SCALE * EDGE_FLOW_FALLBACK_SCALE
    if effective_strength <= 1e-12:
        return coords, 0

    normals = {}
    for vert_index in specs:
        normal = _vertex_normal(vertex_by_index[vert_index])
        if normal is not None:
            normals[vert_index] = normal

    for _ in range(iterations):
        next_coords = work_coords.copy()
        for vert_index, side_groups in specs.items():
            targets = []
            for side_indices in side_groups:
                if len(side_indices) < 2:
                    continue
                p1 = work_coords[side_indices[0]]
                p2 = work_coords[side_indices[1]]
                target = work_coords[vert_index] + ((p1 + p2) * 0.5 - work_coords[vert_index])
                targets.append(target)
            if not targets:
                continue

            target = np.asarray(targets, dtype=np.float32).mean(axis=0)
            delta = target - work_coords[vert_index]

            normal = normals.get(vert_index)
            if normal is not None:
                delta = delta - normal * float(np.dot(delta, normal)) * NORMAL_PROJECTION_SCALE

            masked_strength = effective_strength * (1.0 - mask_array[vert_index])
            next_coords[vert_index] = work_coords[vert_index] + delta * masked_strength

        work_coords = next_coords

    moved_count = _count_moved_vertices(coords, work_coords, specs.keys())
    if moved_count == 0:
        return coords, 0
    return work_coords, moved_count


def _count_moved_vertices(original_coords, result_coords, vert_indices):
    count = 0
    for vert_index in vert_indices:
        delta = result_coords[int(vert_index)] - original_coords[int(vert_index)]
        if float(np.dot(delta, delta)) > MOVED_EPSILON:
            count += 1
    return count


def _edge_key(a, b):
    return tuple(sorted((a, b)))


def _component_from_seed(seed, adjacency, visited_vertices):
    stack = [seed]
    component = []
    visited_vertices.add(seed)

    while stack:
        current = stack.pop()
        component.append(current)
        for neighbor in adjacency[current]:
            if neighbor in visited_vertices:
                continue
            visited_vertices.add(neighbor)
            stack.append(neighbor)

    return component


def _ordered_ring(component, adjacency):
    component_set = set(component)
    start = min(component)
    ordered = [start]
    previous = None
    current = start

    while True:
        candidates = [
            neighbor
            for neighbor in sorted(adjacency[current])
            if neighbor in component_set and neighbor != previous
        ]
        if not candidates:
            return []

        next_index = candidates[0]
        if next_index == start:
            return ordered if len(ordered) == len(component) else []

        if next_index in ordered:
            return []

        ordered.append(next_index)
        previous = current
        current = next_index


def _split_edge_selection(adjacency, coords, feature_angle):
    rings = []
    visited_vertices = set()

    components = []
    for vert_index in adjacency:
        if vert_index not in visited_vertices:
            components.append(_component_from_seed(vert_index, adjacency, visited_vertices))

    for component in components:
        if all(len(adjacency[vert_index]) == 2 for vert_index in component):
            ring = _ordered_ring(component, adjacency)
            if len(ring) >= 3:
                rings.append(ring)

    movable_indices = set()
    for vert_index, neighbors in adjacency.items():
        if len(neighbors) <= 1:
            continue
        sorted_neighbors = sorted(neighbors)
        if not _corner_is_locked(vert_index, sorted_neighbors, coords, feature_angle):
            movable_indices.add(vert_index)

    for ring in rings:
        for vert_index in ring:
            neighbors = sorted(adjacency[vert_index])
            if not _corner_is_locked(vert_index, neighbors, coords, feature_angle):
                movable_indices.add(vert_index)

    return np.asarray(sorted(movable_indices), dtype=np.int32), rings


def _faceset_anchor_indices(selected_edges, boundary_edge_keys, adjacency):
    if not boundary_edge_keys:
        return set()

    selected_edge_keys = {
        _edge_key(edge.verts[0].index, edge.verts[1].index)
        for edge in selected_edges
    }
    anchor_indices = set()

    for key in boundary_edge_keys:
        key = tuple(key)
        if key in selected_edge_keys:
            continue
        for vert_index in key:
            if vert_index in adjacency:
                anchor_indices.add(vert_index)

    return anchor_indices


def _smooth_pass(coords, movable_indices, adjacency, normals, mask_array, strength):
    next_coords = coords.copy()

    for vert_index in movable_indices:
        vert_index = int(vert_index)
        neighbors = np.asarray(sorted(adjacency[vert_index]), dtype=np.int32)
        if neighbors.size == 0:
            continue
        target = coords[neighbors].mean(axis=0)
        delta = target - coords[vert_index]

        normal = normals.get(vert_index)
        if normal is not None:
            delta = delta - normal * float(np.dot(delta, normal)) * NORMAL_PROJECTION_SCALE

        effective_strength = strength * (1.0 - mask_array[vert_index])
        next_coords[vert_index] = coords[vert_index] + delta * effective_strength

    return next_coords


def _ring_scale_data(coords, rings):
    scale_data = []
    for ring in rings:
        ring_indices = np.asarray(ring, dtype=np.int32)
        ring_coords = coords[ring_indices]
        centroid = ring_coords.mean(axis=0)
        offsets = ring_coords - centroid
        rms_radius = float(np.sqrt(np.mean(np.sum(offsets * offsets, axis=1))))
        if rms_radius > RING_SCALE_EPSILON:
            scale_data.append((ring_indices, centroid, rms_radius))
    return scale_data


def _ring_scale_data_without_anchors(coords, rings, anchor_indices):
    if not anchor_indices:
        return _ring_scale_data(coords, rings)

    unlocked_rings = [
        ring
        for ring in rings
        if not any(vert_index in anchor_indices for vert_index in ring)
    ]
    return _ring_scale_data(coords, unlocked_rings)


def _preserve_ring_scale(coords, scale_data):
    adjusted = coords.copy()
    for ring_indices, original_centroid, original_rms_radius in scale_data:
        ring_coords = adjusted[ring_indices]
        current_centroid = ring_coords.mean(axis=0)
        offsets = ring_coords - current_centroid
        current_rms_radius = float(np.sqrt(np.mean(np.sum(offsets * offsets, axis=1))))
        if current_rms_radius <= RING_SCALE_EPSILON:
            continue

        scale = original_rms_radius / current_rms_radius
        adjusted[ring_indices] = original_centroid + offsets * scale

    return adjusted


def polish_selected_edge_chains(
    selected_edges,
    coords,
    mask_array,
    iterations,
    strength,
    feature_angle=0.0,
    boundary_edge_keys=None,
):
    adjacency, vertex_by_index = _build_selected_edge_graph(selected_edges)
    movable_indices, rings = _split_edge_selection(adjacency, coords, feature_angle)
    anchor_indices = _faceset_anchor_indices(selected_edges, boundary_edge_keys, adjacency)
    if anchor_indices and movable_indices.size > 0:
        movable_indices = np.asarray(
            [index for index in movable_indices if int(index) not in anchor_indices],
            dtype=np.int32,
        )

    if movable_indices.size == 0:
        return _apply_edge_flow_fallback(selected_edges, coords, mask_array, iterations, strength, anchor_indices)

    work_coords = coords.copy()
    effective_strength = max(0.0, strength) * EDGE_STRENGTH_SCALE
    if effective_strength <= 1e-12:
        return coords, 0

    normals = {}
    for vert_index in movable_indices:
        normal = _vertex_normal(vertex_by_index[int(vert_index)])
        if normal is not None:
            normals[int(vert_index)] = normal

    ring_scale_data = _ring_scale_data_without_anchors(coords, rings, anchor_indices)

    for _ in range(iterations):
        work_coords = _smooth_pass(
            work_coords,
            movable_indices,
            adjacency,
            normals,
            mask_array,
            effective_strength,
        )
        work_coords = _smooth_pass(
            work_coords,
            movable_indices,
            adjacency,
            normals,
            mask_array,
            effective_strength * SHRINK_COMPENSATION,
        )
        if ring_scale_data:
            work_coords = _preserve_ring_scale(work_coords, ring_scale_data)

    moved_count = _count_moved_vertices(coords, work_coords, movable_indices)
    if moved_count == 0:
        return coords, 0
    return work_coords, moved_count
