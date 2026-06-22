import bpy
import bmesh
import hashlib
import traceback
from collections import OrderedDict
from enum import Enum

import numpy as np
from bpy.app.translations import pgettext_rpt as rpt_

from ..core.algorithms import run_standard_polish, run_tension_polish
from ..core.edge_algorithms import polish_selected_edge_chains
from ..core.topology_rules import build_single_faceset_topology_data, build_topology_data


class PolishResult(Enum):
    SUCCESS = "success"
    WHOLE_MESH = "whole_mesh"
    SELECTED_FACES = "selected_faces"
    SELECTED_EDGES = "selected_edges"
    SELECTED_EDGES_LOCKED = "selected_edges_locked"
    SELECTED_VERTS = "selected_verts"
    NO_FACE_SET = "no_face_set"
    SINGLE_GROUP = "single_group"


_topo_cache = OrderedDict()
_TOPO_CACHE_LIMIT = 12
_mesh_topology_versions = {}
EDGE_POLISH_ITERATION_SCALE = 1.5


def _cache_key_prefix(mesh_ptr):
    return f"{mesh_ptr}:"


def _invalidate_mesh_cache(mesh):
    mesh_ptr = int(mesh.as_pointer())
    _mesh_topology_versions[mesh_ptr] = _mesh_topology_versions.get(mesh_ptr, 0) + 1
    prefix = _cache_key_prefix(mesh_ptr)
    stale_keys = [key for key in _topo_cache if key.startswith(prefix)]
    for key in stale_keys:
        _topo_cache.pop(key, None)


def _hash_int_sequence(values):
    if not values:
        return 0

    array = np.asarray(values, dtype=np.int64)
    digest = hashlib.blake2b(np.ascontiguousarray(array).tobytes(), digest_size=8).digest()
    return int.from_bytes(digest, "little", signed=False)


def _mesh_shape_signature(mesh):
    coords = [0.0] * (len(mesh.vertices) * 3)
    if coords:
        mesh.vertices.foreach_get("co", coords)
    quantized = [int(round(value * 100000.0)) for value in coords]
    return _hash_int_sequence(quantized)


def _mesh_topology_signature(mesh):
    edge_pairs = [0] * (len(mesh.edges) * 2)
    if edge_pairs:
        mesh.edges.foreach_get("vertices", edge_pairs)
    return _hash_int_sequence(edge_pairs)


def _bmesh_shape_signature(bm):
    quantized = []
    for vert in bm.verts:
        quantized.extend(
            (
                int(round(vert.co.x * 100000.0)),
                int(round(vert.co.y * 100000.0)),
                int(round(vert.co.z * 100000.0)),
            )
        )
    return _hash_int_sequence(quantized)


def _bmesh_topology_signature(bm):
    edge_pairs = []
    for edge in bm.edges:
        edge_pairs.extend(
            (
                min(edge.verts[0].index, edge.verts[1].index),
                max(edge.verts[0].index, edge.verts[1].index),
            )
        )
    return _hash_int_sequence(edge_pairs)


def _faceset_signature(face_sets):
    return _hash_int_sequence(face_sets)


def _get_face_set_data_source(mesh, bm=None):
    if bm is not None:
        layer = bm.faces.layers.int.get(".sculpt_face_set")
        if layer is not None:
            return "BMESH", layer

    face_attr = mesh.attributes.get(".sculpt_face_set")
    if face_attr and face_attr.domain == "FACE":
        return "MESH", face_attr

    return None, None


def _uses_whole_mesh(face_sets):
    if not face_sets:
        return True
    return len(set(face_sets)) <= 1


def get_mesh_attributes(mesh, bm=None):
    face_sets = None

    source_kind, source = _get_face_set_data_source(mesh, bm)
    if source_kind == "BMESH":
        face_sets = [0] * len(bm.faces)
        for face in bm.faces:
            face_sets[face.index] = face[source]
    elif source_kind == "MESH":
        face_count = len(mesh.polygons)
        face_sets = [0] * face_count
        if face_count > 0:
            source.data.foreach_get("value", face_sets)

    vert_count = len(bm.verts) if bm is not None else len(mesh.vertices)
    masks = [0.0] * vert_count
    if bm is not None:
        mask_layer = bm.verts.layers.float.get(".sculpt_mask")
        if mask_layer is not None:
            for vert in bm.verts:
                masks[vert.index] = vert[mask_layer]
        else:
            mask_attr = mesh.attributes.get(".sculpt_mask")
            if (
                mask_attr
                and mask_attr.domain == "POINT"
                and vert_count > 0
                and len(mesh.vertices) == vert_count
            ):
                mask_attr.data.foreach_get("value", masks)
    else:
        mask_attr = mesh.attributes.get(".sculpt_mask")
        if mask_attr and mask_attr.domain == "POINT" and vert_count > 0:
            mask_attr.data.foreach_get("value", masks)

    return face_sets, masks


def get_or_build_topology(mesh, face_set_per_face, feature_angle, bm=None, single_faceset=False):
    shape_signature = 0
    topology_signature = _bmesh_topology_signature(bm) if bm is not None else _mesh_topology_signature(mesh)
    vert_count = len(bm.verts) if bm is not None else len(mesh.vertices)
    edge_count = len(bm.edges) if bm is not None else len(mesh.edges)
    face_count = len(bm.faces) if bm is not None else len(mesh.polygons)
    if feature_angle > 0.001:
        shape_signature = _bmesh_shape_signature(bm) if bm is not None else _mesh_shape_signature(mesh)

    cache_key = (
        f"{_cache_key_prefix(int(mesh.as_pointer()))}"
        f"{vert_count}:"
        f"{edge_count}:"
        f"{face_count}:"
        f"{round(feature_angle, 6)}:"
        f"{int(single_faceset)}:"
        f"{0 if single_faceset else _faceset_signature(face_set_per_face)}:"
        f"{_mesh_topology_versions.get(int(mesh.as_pointer()), 0)}:"
        f"{topology_signature}:"
        f"{shape_signature}"
    )

    cached = _topo_cache.get(cache_key)
    if cached is not None:
        _topo_cache.move_to_end(cache_key)
        return cached

    owns_bmesh = bm is None
    work_bm = bm if bm is not None else bmesh.new()

    try:
        if owns_bmesh:
            work_bm.from_mesh(mesh)
        work_bm.verts.ensure_lookup_table()
        work_bm.faces.ensure_lookup_table()
        if single_faceset:
            data = build_single_faceset_topology_data(work_bm, feature_angle)
        else:
            data = build_topology_data(work_bm, face_set_per_face, feature_angle)
    finally:
        if owns_bmesh:
            work_bm.free()

    _topo_cache[cache_key] = data
    _topo_cache.move_to_end(cache_key)
    while len(_topo_cache) > _TOPO_CACHE_LIMIT:
        _topo_cache.popitem(last=False)

    return data


def _active_mesh_and_bmesh(obj):
    mesh = obj.data
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        return mesh, bm
    return mesh, None


def _face_count(mesh, bm=None):
    return len(bm.faces) if bm is not None else len(mesh.polygons)


def _validate_runtime_arrays(vert_class, mask_array, cur_pos):
    vert_count = len(vert_class)
    issues = []

    if mask_array.shape[0] != vert_count:
        issues.append(f"mask count {mask_array.shape[0]} does not match vertex count {vert_count}")

    if cur_pos.shape[0] != vert_count:
        issues.append(f"coordinate count {cur_pos.shape[0]} does not match vertex count {vert_count}")

    if issues:
        raise RuntimeError("FST ForgePolish data mismatch: " + "; ".join(issues))


def _complete_selected_faces(bm, allow_inferred=False):
    selected_faces = [
        face
        for face in bm.faces
        if face.select and all(edge.select for edge in face.edges)
    ]
    if selected_faces or not allow_inferred:
        return selected_faces

    return [face for face in bm.faces if all(vert.select for vert in face.verts)]


def _selected_edges_from_selection(bm, allow_inferred=False):
    selected_edges = [edge for edge in bm.edges if edge.select]
    if selected_edges or not allow_inferred:
        return selected_edges

    return [edge for edge in bm.edges if all(vert.select for vert in edge.verts)]


def _select_history_items(bm, item_type):
    return [item for item in bm.select_history if isinstance(item, item_type) and item.select]


def _selected_edges_form_complete_selected_faces(selected_edges, selected_faces):
    if not selected_edges or not selected_faces:
        return False

    face_edges = {edge for face in selected_faces for edge in face.edges}
    return set(selected_edges).issubset(face_edges)


def _selected_vertices(bm):
    return [vert for vert in bm.verts if vert.select]


def _selected_face_mask(bm, selected_faces):
    mask_list = [1.0] * len(bm.verts)
    for face in selected_faces:
        for vert in face.verts:
            mask_list[vert.index] = 0.0
    return mask_list


def _selected_vert_mask(bm, selected_verts):
    mask_list = [1.0] * len(bm.verts)
    for vert in selected_verts:
        mask_list[vert.index] = 0.0
    return mask_list


def _edge_vertex_key(edge):
    return tuple(sorted((edge.verts[0].index, edge.verts[1].index)))


def _faceset_boundary_edge_keys(selected_edges, face_sets):
    if face_sets is None:
        return None

    selected_edge_keys = {_edge_vertex_key(edge) for edge in selected_edges}
    boundary_edge_keys = set()

    for edge in selected_edges:
        if len(edge.link_faces) != 2:
            continue

        fset_a = face_sets[edge.link_faces[0].index]
        fset_b = face_sets[edge.link_faces[1].index]
        if fset_a != fset_b:
            boundary_edge_keys.add(_edge_vertex_key(edge))

    for edge in selected_edges:
        for vert in edge.verts:
            for linked_edge in vert.link_edges:
                key = _edge_vertex_key(linked_edge)
                if key in selected_edge_keys or len(linked_edge.link_faces) != 2:
                    continue

                fset_a = face_sets[linked_edge.link_faces[0].index]
                fset_b = face_sets[linked_edge.link_faces[1].index]
                if fset_a != fset_b:
                    boundary_edge_keys.add(key)

    return boundary_edge_keys


def _get_coordinates(mesh, bm=None):
    if bm is None:
        coords = [0.0] * (len(mesh.vertices) * 3)
        if coords:
            mesh.vertices.foreach_get("co", coords)
        return np.asarray(coords, dtype=np.float32).reshape((-1, 3))

    return np.asarray([(vert.co.x, vert.co.y, vert.co.z) for vert in bm.verts], dtype=np.float32)


def _tag_view3d_redraw(context):
    screen = getattr(context, "screen", None)
    if screen is None:
        return

    for area in screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()


def _write_coordinates(mesh, coords, bm=None, context=None):
    if bm is None:
        flat_coords = coords.reshape(-1).tolist()
        if flat_coords:
            mesh.vertices.foreach_set("co", flat_coords)
        mesh.update()
        mesh.update_tag()
        if context is not None:
            _tag_view3d_redraw(context)
        return

    for index, vert in enumerate(bm.verts):
        co = coords[index]
        vert.co.x = float(co[0])
        vert.co.y = float(co[1])
        vert.co.z = float(co[2])

    bm.normal_update()
    bmesh.update_edit_mesh(mesh, loop_triangles=True, destructive=False)
    mesh.update()
    mesh.update_tag()
    if context is not None:
        _tag_view3d_redraw(context)


def _execute_surface_polish(context, mesh, bm=None, mask_override=None):
    props = context.scene.fst_forgepolish_props
    face_set_per_face, mask_list = get_mesh_attributes(mesh, bm)
    single_faceset = _uses_whole_mesh(face_set_per_face)
    if _uses_whole_mesh(face_set_per_face):
        face_set_per_face = [1] * _face_count(mesh, bm)

    if mask_override is not None:
        mask_list = mask_override

    vert_class, inner_neighbors, boundary_neighbors = get_or_build_topology(
        mesh,
        face_set_per_face,
        props.feature_angle,
        bm=bm,
        single_faceset=single_faceset,
    )

    cur_pos = _get_coordinates(mesh, bm=bm).copy()
    mask_array = np.asarray(mask_list, dtype=np.float32)
    _validate_runtime_arrays(vert_class, mask_array, cur_pos)

    active_inner = np.flatnonzero((vert_class == 1) & (mask_array < 1.0)).astype(np.int32)
    active_bound = np.flatnonzero(((vert_class == 2) | (vert_class == 3)) & (mask_array < 1.0)).astype(np.int32)
    active_all = np.concatenate((active_inner, active_bound)).astype(np.int32)
    next_pos = cur_pos.copy()
    if props.algorithm_mode == "STANDARD":
        orig_pos = cur_pos.copy()
        b_err = np.zeros_like(cur_pos)
    else:
        orig_pos = None
        b_err = None

    if props.algorithm_mode == "TENSION":
        run_tension_polish(
            props.iterations * 0.5,
            props.strength,
            props.boundary_strength,
            active_inner,
            active_bound,
            active_all,
            inner_neighbors,
            boundary_neighbors,
            mask_array,
            cur_pos,
            next_pos,
        )
    else:
        run_standard_polish(
            props.iterations,
            props.strength,
            props.boundary_strength,
            props.hc_blend,
            props.boundary_hc_blend,
            0.5,
            active_inner,
            active_bound,
            inner_neighbors,
            boundary_neighbors,
            mask_array,
            cur_pos,
            next_pos,
            orig_pos,
            b_err,
        )

    _write_coordinates(mesh, cur_pos, bm=bm, context=context)


def _execute_edge_polish(context, mesh, bm, selected_edges):
    props = context.scene.fst_forgepolish_props
    if not selected_edges:
        return 0

    face_sets, mask_list = get_mesh_attributes(mesh, bm)
    mask_array = np.asarray(mask_list, dtype=np.float32)
    coords = _get_coordinates(mesh, bm=bm).copy()
    boundary_edge_keys = _faceset_boundary_edge_keys(selected_edges, face_sets)

    result_coords, moved_count = polish_selected_edge_chains(
        selected_edges,
        coords,
        mask_array,
        max(1, int((props.iterations * EDGE_POLISH_ITERATION_SCALE) + 0.5)),
        props.boundary_strength,
        feature_angle=props.feature_angle,
        boundary_edge_keys=boundary_edge_keys,
    )

    if moved_count > 0:
        _write_coordinates(mesh, result_coords, bm=bm, context=context)
    return moved_count


def execute_polish(context):
    obj = context.active_object
    mesh, bm = _active_mesh_and_bmesh(obj)

    if bm is None:
        _execute_surface_polish(context, mesh, bm=None)
        return PolishResult.WHOLE_MESH

    history_edges = _select_history_items(bm, bmesh.types.BMEdge)
    history_faces = _select_history_items(bm, bmesh.types.BMFace)
    selected_faces = _complete_selected_faces(bm)
    selected_edges = _selected_edges_from_selection(bm)

    edge_candidates = selected_edges or history_edges
    if edge_candidates and not _selected_edges_form_complete_selected_faces(edge_candidates, selected_faces):
        moved_count = _execute_edge_polish(context, mesh, bm, edge_candidates)
        if moved_count > 0:
            return PolishResult.SELECTED_EDGES
        return PolishResult.SELECTED_EDGES_LOCKED

    if history_faces and not history_edges:
        _execute_surface_polish(
            context,
            mesh,
            bm=bm,
            mask_override=_selected_face_mask(bm, history_faces),
        )
        return PolishResult.SELECTED_FACES

    if selected_faces:
        _execute_surface_polish(
            context,
            mesh,
            bm=bm,
            mask_override=_selected_face_mask(bm, selected_faces),
        )
        return PolishResult.SELECTED_FACES

    if selected_edges:
        moved_count = _execute_edge_polish(context, mesh, bm, selected_edges)
        if moved_count > 0:
            return PolishResult.SELECTED_EDGES
        return PolishResult.SELECTED_EDGES_LOCKED

    selected_faces = _complete_selected_faces(bm, allow_inferred=True)
    if selected_faces:
        _execute_surface_polish(
            context,
            mesh,
            bm=bm,
            mask_override=_selected_face_mask(bm, selected_faces),
        )
        return PolishResult.SELECTED_FACES

    selected_edges = _selected_edges_from_selection(bm, allow_inferred=True)
    if selected_edges:
        moved_count = _execute_edge_polish(context, mesh, bm, selected_edges)
        if moved_count > 0:
            return PolishResult.SELECTED_EDGES
        return PolishResult.SELECTED_EDGES_LOCKED

    selected_verts = _selected_vertices(bm)
    if selected_verts:
        _execute_surface_polish(
            context,
            mesh,
            bm=bm,
            mask_override=_selected_vert_mask(bm, selected_verts),
        )
        return PolishResult.SELECTED_VERTS

    _execute_surface_polish(context, mesh, bm=bm)
    return PolishResult.WHOLE_MESH


class _MeshOperatorMixin:
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode in {"OBJECT", "EDIT", "SCULPT"}


class _EditMeshOperatorMixin:
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"


class MESH_OT_create_facesets_from_edges(_EditMeshOperatorMixin, bpy.types.Operator):
    bl_idname = "mesh.create_facesets_from_edges"
    bl_label = "Create Face Sets from Edges"
    bl_description = "Use selected edges as separators and create face sets by flood fill"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        mesh, edit_bm = _active_mesh_and_bmesh(obj)
        owns_bmesh = edit_bm is None
        bm = edit_bm if edit_bm is not None else bmesh.new()

        try:
            if owns_bmesh:
                bm.from_mesh(mesh)
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            selected_edges = {edge.index for edge in bm.edges if edge.select}
            if not selected_edges:
                self.report(
                    {"WARNING"},
                    rpt_("No selected edges found. Select separator edges in Edit Mode first."),
                )
                return {"CANCELLED"}

            visited_faces = set()
            face_to_set = {}
            current_set_id = 1

            for face in bm.faces:
                if face.index in visited_faces:
                    continue

                stack = [face]
                visited_faces.add(face.index)

                while stack:
                    curr_face = stack.pop()
                    face_to_set[curr_face.index] = current_set_id

                    for edge in curr_face.edges:
                        if edge.index in selected_edges:
                            continue
                        for link_face in edge.link_faces:
                            if link_face.index not in visited_faces:
                                visited_faces.add(link_face.index)
                                stack.append(link_face)

                current_set_id += 1

            if edit_bm is not None:
                layer = bm.faces.layers.int.get(".sculpt_face_set")
                if layer is None:
                    layer = bm.faces.layers.int.new(".sculpt_face_set")
                for face in bm.faces:
                    face[layer] = face_to_set.get(face.index, 1)
                bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
            else:
                attr = mesh.attributes.get(".sculpt_face_set")
                if attr is not None and attr.domain != "FACE":
                    self.report(
                        {"ERROR"},
                        rpt_(".sculpt_face_set exists but is not a FACE domain attribute."),
                    )
                    return {"CANCELLED"}
                if attr is None:
                    attr = mesh.attributes.new(name=".sculpt_face_set", type="INT", domain="FACE")

                values = [1] * len(mesh.polygons)
                for face_index, set_id in face_to_set.items():
                    values[face_index] = set_id

                attr.data.foreach_set("value", values)
                mesh.update()

            _invalidate_mesh_cache(mesh)
            self.report(
                {"INFO"},
                rpt_("Created %d face sets from the selected edges.") % (current_set_id - 1),
            )
            return {"FINISHED"}

        finally:
            if owns_bmesh:
                bm.free()


class MESH_OT_select_faceset_boundaries(_EditMeshOperatorMixin, bpy.types.Operator):
    bl_idname = "mesh.select_faceset_boundaries"
    bl_label = "Select Face Set Boundaries"
    bl_description = "Select the edges that separate neighboring face sets"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        mesh, bm = _active_mesh_and_bmesh(obj)
        face_sets, _mask_list = get_mesh_attributes(mesh, bm)
        if face_sets is None:
            self.report({"WARNING"}, rpt_("No face sets were found on the active mesh."))
            return {"CANCELLED"}

        if bm is not None:
            for vert in bm.verts:
                vert.select = False
            for edge in bm.edges:
                edge.select = False
            for face in bm.faces:
                face.select = False

            for edge in bm.edges:
                if len(edge.link_faces) != 2:
                    continue
                fset_a = face_sets[edge.link_faces[0].index]
                fset_b = face_sets[edge.link_faces[1].index]
                if fset_a == fset_b:
                    continue
                edge.select = True
                edge.verts[0].select = True
                edge.verts[1].select = True

            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
            return {"FINISHED"}

        for vert in mesh.vertices:
            vert.select = False
        for edge in mesh.edges:
            edge.select = False
        for poly in mesh.polygons:
            poly.select = False

        edge_first_fset = [-1] * len(mesh.edges)
        edge_is_boundary = [False] * len(mesh.edges)
        loops = mesh.loops

        for poly in mesh.polygons:
            fset_id = face_sets[poly.index]
            for loop_index in poly.loop_indices:
                edge_index = loops[loop_index].edge_index
                first = edge_first_fset[edge_index]
                if first == -1:
                    edge_first_fset[edge_index] = fset_id
                elif first != fset_id:
                    edge_is_boundary[edge_index] = True

        for edge_index, is_boundary in enumerate(edge_is_boundary):
            if not is_boundary:
                continue
            edge = mesh.edges[edge_index]
            edge.select = True
            mesh.vertices[edge.vertices[0]].select = True
            mesh.vertices[edge.vertices[1]].select = True

        mesh.update()
        return {"FINISHED"}


class MESH_OT_fst_forgepolish_groups(_MeshOperatorMixin, bpy.types.Operator):
    bl_idname = "mesh.fst_forgepolish_groups"
    bl_label = "Execute Polish"
    bl_description = "Apply FST ForgePolish to the active mesh using the current settings"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            result = execute_polish(context)
        except Exception as exc:
            traceback.print_exc()
            self.report(
                {"ERROR"},
                rpt_("Execution failed. See the console for details: %s") % exc,
            )
            return {"CANCELLED"}

        messages = {
            PolishResult.WHOLE_MESH: "Polished the whole mesh.",
            PolishResult.SELECTED_FACES: "Polished the selected face area.",
            PolishResult.SELECTED_EDGES: "Polished the selected edge chain.",
            PolishResult.SELECTED_EDGES_LOCKED: "Selected edge chain did not move. Endpoints, masks, or strength may be locking it.",
            PolishResult.SELECTED_VERTS: "Polished the selected vertices.",
        }
        message = messages.get(result)
        if message:
            self.report({"INFO"}, rpt_(message))

        return {"FINISHED"}
