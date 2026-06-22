import math
from collections import defaultdict

import numpy as np


def _to_numpy_int_array(values):
    return np.asarray(values, dtype=np.int32)


def _neighbor_pairs(neighbor_lists):
    vert_count = len(neighbor_lists)
    counts = np.zeros(vert_count, dtype=np.int32)
    target_indices = []
    source_indices = []

    for idx, neighbors in enumerate(neighbor_lists):
        count = len(neighbors)
        counts[idx] = count
        for neighbor in neighbors:
            target_indices.append(idx)
            source_indices.append(neighbor)

    return (
        np.asarray(target_indices, dtype=np.int32),
        np.asarray(source_indices, dtype=np.int32),
        counts,
    )


def build_topology_data(bm, face_set_per_face, feature_angle):
    vert_groups = defaultdict(set)
    for face in bm.faces:
        fset_id = face_set_per_face[face.index]
        for vert in face.verts:
            vert_groups[vert.index].add(fset_id)

    vert_count = len(bm.verts)
    vert_class = [0] * vert_count
    inner_neighbors = [[] for _ in range(vert_count)]
    boundary_neighbors = [[] for _ in range(vert_count)]

    lock_enabled = feature_angle > 0.001
    dot_threshold = -math.cos(feature_angle) if lock_enabled else 2.0

    for vert in bm.verts:
        idx = vert.index

        if any(len(edge.link_faces) > 2 for edge in vert.link_edges):
            continue

        open_edges = [edge for edge in vert.link_edges if len(edge.link_faces) == 1]
        fset_count = len(vert_groups[idx])

        if fset_count >= 3:
            continue

        if open_edges:
            if fset_count >= 2 or len(open_edges) != 2:
                continue
            vert_class[idx] = 3
        else:
            if fset_count == 1:
                vert_class[idx] = 1
            elif fset_count == 2:
                vert_class[idx] = 2
            else:
                continue

    for vert in bm.verts:
        idx = vert.index
        cls = vert_class[idx]

        if cls == 1:
            inner_neighbors[idx] = [edge.other_vert(vert).index for edge in vert.link_edges]

        elif cls == 2:
            boundary_neighbor_verts = []
            for edge in vert.link_edges:
                if len(edge.link_faces) != 2:
                    continue
                fset_a = face_set_per_face[edge.link_faces[0].index]
                fset_b = face_set_per_face[edge.link_faces[1].index]
                if fset_a != fset_b:
                    boundary_neighbor_verts.append(edge.other_vert(vert))

            if len(boundary_neighbor_verts) != 2:
                vert_class[idx] = 0
                continue

            if lock_enabled:
                v1 = (boundary_neighbor_verts[0].co - vert.co).normalized()
                v2 = (boundary_neighbor_verts[1].co - vert.co).normalized()
                if v1.dot(v2) >= dot_threshold:
                    vert_class[idx] = 0
                    continue

            boundary_neighbors[idx] = [boundary_neighbor_verts[0].index, boundary_neighbor_verts[1].index]

        elif cls == 3:
            boundary_neighbor_verts = [edge.other_vert(vert) for edge in vert.link_edges if len(edge.link_faces) == 1]
            if len(boundary_neighbor_verts) != 2:
                vert_class[idx] = 0
                continue

            if lock_enabled:
                v1 = (boundary_neighbor_verts[0].co - vert.co).normalized()
                v2 = (boundary_neighbor_verts[1].co - vert.co).normalized()
                if v1.dot(v2) >= dot_threshold:
                    vert_class[idx] = 0
                    continue

            boundary_neighbors[idx] = [boundary_neighbor_verts[0].index, boundary_neighbor_verts[1].index]

    return (
        _to_numpy_int_array(vert_class),
        _neighbor_pairs(inner_neighbors),
        _neighbor_pairs(boundary_neighbors),
    )


def build_single_faceset_topology_data(bm, feature_angle):
    vert_count = len(bm.verts)
    vert_class = [0] * vert_count
    inner_neighbors = [[] for _ in range(vert_count)]
    boundary_neighbors = [[] for _ in range(vert_count)]

    lock_enabled = feature_angle > 0.001
    dot_threshold = -math.cos(feature_angle) if lock_enabled else 2.0

    for vert in bm.verts:
        idx = vert.index

        if any(len(edge.link_faces) > 2 for edge in vert.link_edges):
            continue

        open_edges = [edge for edge in vert.link_edges if len(edge.link_faces) == 1]
        if open_edges:
            if len(open_edges) != 2:
                continue
            vert_class[idx] = 3
        elif any(edge.link_faces for edge in vert.link_edges):
            vert_class[idx] = 1

    for vert in bm.verts:
        idx = vert.index
        cls = vert_class[idx]

        if cls == 1:
            inner_neighbors[idx] = [edge.other_vert(vert).index for edge in vert.link_edges]

        elif cls == 3:
            boundary_neighbor_verts = [edge.other_vert(vert) for edge in vert.link_edges if len(edge.link_faces) == 1]
            if len(boundary_neighbor_verts) != 2:
                vert_class[idx] = 0
                continue

            if lock_enabled:
                v1 = (boundary_neighbor_verts[0].co - vert.co).normalized()
                v2 = (boundary_neighbor_verts[1].co - vert.co).normalized()
                if v1.dot(v2) >= dot_threshold:
                    vert_class[idx] = 0
                    continue

            boundary_neighbors[idx] = [boundary_neighbor_verts[0].index, boundary_neighbor_verts[1].index]

    return (
        _to_numpy_int_array(vert_class),
        _neighbor_pairs(inner_neighbors),
        _neighbor_pairs(boundary_neighbors),
    )
