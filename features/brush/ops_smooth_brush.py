import math
import time

import bpy
import numpy as np
from bpy.app.translations import pgettext_iface as iface_
from bpy.app.translations import pgettext_rpt as rpt_

from . import brush_context, overlay, polish_engine, smooth_engine


_BRUSH_RADIUS_MIN = 2.0
_BRUSH_RADIUS_ADJUST_PIXELS = 1.0
_BRUSH_HARDNESS_ADJUST_PIXELS = 240.0
_BRUSH_WRITE_INTERVAL = 1.0 / 20.0
_BRUSH_INTERPOLATE_START_FACTOR = 0.45
_BRUSH_INTERPOLATE_STEP_FACTOR = 0.35
_BRUSH_MAX_INTERPOLATED_SAMPLES = 4
_BRUSH_STRENGTH_PER_ITERATION = 0.05
_BRUSH_UNDO_LIMIT = 24
_BRUSH_REOPEN_BLOCK_SECONDS = 0.35

_SMOOTH_BRUSH_ACTIVE = False
_SMOOTH_BRUSH_LAST_PASSTHROUGH_CLOSE_TIME = 0.0
_SMOOTH_BRUSH_STOP_REQUESTED = False
_SMOOTH_BRUSH_LIVE_OPERATORS = set()


def _props(context):
    return context.scene.fst_forgepolish_props


def is_smooth_brush_active():
    return _SMOOTH_BRUSH_ACTIVE


def _set_smooth_brush_active(value):
    global _SMOOTH_BRUSH_ACTIVE
    _SMOOTH_BRUSH_ACTIVE = bool(value)


def _request_smooth_brush_stop():
    global _SMOOTH_BRUSH_STOP_REQUESTED
    _SMOOTH_BRUSH_STOP_REQUESTED = True


def _clear_smooth_brush_stop_request():
    global _SMOOTH_BRUSH_STOP_REQUESTED
    _SMOOTH_BRUSH_STOP_REQUESTED = False


def _consume_smooth_brush_stop_request():
    global _SMOOTH_BRUSH_STOP_REQUESTED
    if not _SMOOTH_BRUSH_STOP_REQUESTED:
        return False
    _SMOOTH_BRUSH_STOP_REQUESTED = False
    return True


def shutdown_active_smooth_brush():
    _request_smooth_brush_stop()
    for operator in tuple(_SMOOTH_BRUSH_LIVE_OPERATORS):
        try:
            operator._force_cleanup(bpy.context)
        except Exception:
            pass
    _SMOOTH_BRUSH_LIVE_OPERATORS.clear()
    _clear_smooth_brush_stop_request()
    _set_smooth_brush_active(False)


def _mark_passthrough_close():
    global _SMOOTH_BRUSH_LAST_PASSTHROUGH_CLOSE_TIME
    _SMOOTH_BRUSH_LAST_PASSTHROUGH_CLOSE_TIME = time.perf_counter()


def _is_reopen_blocked(event):
    if event is None or event.type != "LEFTMOUSE":
        return False
    elapsed = time.perf_counter() - _SMOOTH_BRUSH_LAST_PASSTHROUGH_CLOSE_TIME
    return 0.0 <= elapsed <= _BRUSH_REOPEN_BLOCK_SECONDS


def _brush_strength_from_iterations(context):
    iterations = float(_props(context).iterations)
    return float(np.clip(iterations * _BRUSH_STRENGTH_PER_ITERATION, 0.0, 1.0))


class MESH_OT_fst_forgepolish_smooth_brush(bpy.types.Operator):
    bl_idname = "mesh.fst_forgepolish_smooth_brush"
    bl_label = "Polish Brush"
    bl_description = "Brush local polishing onto the active mesh"
    bl_options = {"REGISTER", "UNDO"}

    _handle = None
    _handle_2d = None

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            context.area is not None
            and context.area.type == "VIEW_3D"
            and obj is not None
            and obj.type == "MESH"
            and obj.mode in {"OBJECT", "EDIT"}
        )

    def invoke(self, context, event):
        if _is_reopen_blocked(event):
            return {"CANCELLED"}

        if is_smooth_brush_active():
            _request_smooth_brush_stop()
            return {"CANCELLED"}

        if context.area is None or context.area.type != "VIEW_3D":
            self.report({"WARNING"}, rpt_("Run this tool in the 3D View."))
            return {"CANCELLED"}

        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"WARNING"}, rpt_("Select a mesh object first."))
            return {"CANCELLED"}

        self._started_mode = obj.mode
        if obj.mode == "EDIT":
            bpy.ops.object.mode_set(mode="OBJECT")
            obj = context.active_object

        mesh = obj.data
        if len(mesh.vertices) == 0 or len(mesh.polygons) == 0:
            self.report({"WARNING"}, rpt_("Active mesh has no smoothable surface."))
            self._restore_started_mode(context)
            return {"CANCELLED"}

        self._obj = obj
        self._mesh = mesh
        self._obj_name = obj.name
        self._obj_ptr = brush_context.safe_pointer(obj)
        self._mesh_ptr = brush_context.safe_pointer(mesh)
        self._coords = self._read_coords(mesh)
        self._world_positions = smooth_engine.mesh_world_positions(obj)
        self._polish_neighbors = polish_engine.build_brush_polish_neighbors(
            mesh,
            _props(context).feature_angle,
        )
        self._mask_array = polish_engine.brush_mask_array(mesh)
        self._spatial_index = smooth_engine.build_position_spatial_index(self._world_positions)
        self._bvh = smooth_engine.build_bvh(mesh)
        self._polish_neighbors_signature = polish_engine.polish_neighbors_signature(
            mesh,
            _props(context).feature_angle,
        )
        if self._bvh is None:
            self.report({"WARNING"}, rpt_("Active mesh has no smoothable surface."))
            self._restore_started_mode(context)
            return {"CANCELLED"}

        self._world_matrix = obj.matrix_world.copy()
        self._world_matrix_inv = self._world_matrix.inverted_safe()
        self._area_ptr = context.area.as_pointer()
        self._is_painting = False
        self._did_smooth = False
        self._stroke_did_smooth = False
        self._stroke_start_coords = None
        self._stroke_undo_stack = []
        self._stroke_redo_stack = []
        self._coords_dirty = False
        self._last_write_time = 0.0
        self._last_hit_world = None
        self._hit_world = None
        self._hit_normal = None
        self._brush_world_radius = 0.0
        self._brush_adjust_mode = None
        self._brush_adjust_start_mouse_x = 0
        self._brush_adjust_start_value = 0.0
        self._draw_state = {
            "visible": False,
            "center": None,
            "normal": None,
            "radius": 0.0,
            "hardness": self._brush_hardness(context),
            "screen_visible": False,
            "screen_center": None,
            "screen_radius": self._screen_brush_radius(context),
            "area_ptr": context.area.as_pointer(),
            "region_ptr": None,
        }
        region, _region_data = brush_context.find_view3d_window(context)
        if region is not None:
            self._draw_state["region_ptr"] = region.as_pointer()

        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            overlay.draw_brush_overlay,
            (self._draw_state,),
            "WINDOW",
            "POST_VIEW",
        )
        self._handle_2d = bpy.types.SpaceView3D.draw_handler_add(
            overlay.draw_brush_overlay_2d,
            (self._draw_state,),
            "WINDOW",
            "POST_PIXEL",
        )
        context.window_manager.modal_handler_add(self)
        _SMOOTH_BRUSH_LIVE_OPERATORS.add(self)
        _set_smooth_brush_active(True)
        self._set_status_text(context, self._status_text())
        self._tag_redraw(context, include_regions=True)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        self._tag_redraw(context)

        if _consume_smooth_brush_stop_request():
            return self._finish_modal_result(context)

        if not self._is_context_valid(context):
            return self._finish_modal_result(context, restore_mode=False)

        if event.value == "PRESS" and event.ctrl and event.type in {"Z", "Y"}:
            if self._is_painting:
                return {"RUNNING_MODAL"}
            if event.type == "Y" or event.shift:
                self._redo_stroke(context)
            else:
                self._undo_stroke(context)
            return {"RUNNING_MODAL"}

        if self._brush_adjust_mode is not None:
            return self._handle_brush_adjust_event(context, event)

        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            return self._finish_modal_result(context)

        inside, region, region_data, mouse_x, mouse_y = self._view3d_window_from_event(context, event)

        if event.type == "LEFTMOUSE" and event.value == "PRESS" and not inside:
            _area, ui_region = brush_context.find_view3d_region_at_mouse(
                context,
                event.mouse_x,
                event.mouse_y,
                area_ptr=getattr(self, "_area_ptr", None),
            )
            if ui_region is not None and getattr(ui_region, "type", None) == "UI":
                self._set_overlay_visible(False)
                return {"PASS_THROUGH"}
            return self._finish_modal_passthrough(context)

        if inside and event.type == "F" and event.value == "PRESS" and not self._is_painting:
            self._begin_brush_adjust(context, event, "HARDNESS" if event.shift else "RADIUS")
            return {"RUNNING_MODAL"}

        if not inside:
            if self._coords_dirty and not self._flush_coords(context):
                return self._finish_modal_result(context)
            self._set_overlay_visible(False)
            return {"PASS_THROUGH"}

        if event.type in {"MOUSEMOVE", "LEFTMOUSE"}:
            self._update_hit(context, region, region_data, mouse_x, mouse_y)

        if event.type == "LEFTMOUSE":
            if event.value == "PRESS":
                self._is_painting = True
                self._stroke_did_smooth = False
                self._stroke_start_coords = self._coords.copy()
                self._last_hit_world = None
                if self._smooth_at_hit(context, force=True) < 0:
                    return self._finish_modal_result(context)
            elif event.value == "RELEASE":
                self._is_painting = False
                self._last_hit_world = None
                if not self._flush_coords(context):
                    return self._finish_modal_result(context)
                self._commit_stroke_undo()
                self._stroke_did_smooth = False
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE" and self._is_painting:
            if self._smooth_at_hit(context) < 0:
                return self._finish_modal_result(context)
            return {"RUNNING_MODAL"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}

        return {"PASS_THROUGH"}

    def _read_coords(self, mesh):
        coords = np.empty((len(mesh.vertices), 3), dtype=np.float32)
        mesh.vertices.foreach_get("co", coords.reshape(-1))
        return coords

    def _write_coords(self, mesh):
        mesh.vertices.foreach_set("co", self._coords.reshape(-1))
        mesh.update()
        mesh.update_tag()

    def _resolve_target(self, context):
        obj = getattr(context, "active_object", None)
        try:
            if obj is None or obj.type != "MESH":
                return None, None
            if obj.mode != "OBJECT":
                return None, None
            if self._obj_ptr and brush_context.safe_pointer(obj) != self._obj_ptr:
                return None, None
            mesh = obj.data
            if brush_context.safe_pointer(mesh) != self._mesh_ptr:
                return None, None
            return obj, mesh
        except ReferenceError:
            return None, None

    def _is_context_valid(self, context):
        obj, mesh = self._resolve_target(context)
        return obj is not None and mesh is not None

    def _view3d_window_from_event(self, context, event):
        _area, region, region_data = brush_context.find_view3d_window_at_mouse(
            context,
            event.mouse_x,
            event.mouse_y,
            area_ptr=getattr(self, "_area_ptr", None),
        )
        if region is None or region_data is None:
            return False, None, None, 0, 0
        mouse_x = event.mouse_x - region.x
        mouse_y = event.mouse_y - region.y
        inside = 0 <= mouse_x <= region.width and 0 <= mouse_y <= region.height
        return inside, region, region_data, mouse_x, mouse_y

    def _update_hit(self, context, region, region_data, mouse_x, mouse_y):
        self._draw_state["screen_center"] = (mouse_x, mouse_y)
        hit_world, hit_normal = smooth_engine.raycast_surface_hit(
            region,
            region_data,
            mouse_x,
            mouse_y,
            bvh=self._bvh,
            world_matrix=self._world_matrix,
            world_matrix_inv=self._world_matrix_inv,
        )
        if hit_world is None:
            self._hit_world = None
            self._hit_normal = None
            self._brush_world_radius = 0.0
            self._set_overlay_visible(False, screen_visible=True)
            self._draw_state["screen_radius"] = self._screen_brush_radius(context)
            self._draw_state["hardness"] = self._brush_hardness(context)
            return

        self._hit_world = hit_world
        self._hit_normal = hit_normal
        world_radius = smooth_engine.view_depth_world_radius_for_screen_radius(
            region,
            region_data,
            self._hit_world,
            _props(context).brush_radius,
        )
        if world_radius <= 0.0:
            world_radius = max(self._brush_world_radius, 1e-6)
        self._brush_world_radius = world_radius
        self._draw_state["visible"] = False
        self._draw_state["screen_visible"] = True
        self._draw_state["center"] = tuple(self._hit_world)
        self._draw_state["normal"] = tuple(self._hit_normal)
        self._draw_state["radius"] = world_radius
        self._draw_state["screen_radius"] = self._screen_brush_radius(context)
        self._draw_state["hardness"] = self._brush_hardness(context)

    def _smooth_at_hit(self, context, force=False):
        if self._hit_world is None:
            return 0
        if not force and self._should_skip_sample():
            return 0

        changed = 0
        for hit_world in self._samples_for_hit():
            result = polish_engine.polish_vertices_at_hit(
                coords=self._coords,
                world_positions=self._world_positions,
                polish_neighbors=self._polish_neighbors,
                mask_array=self._mask_array,
                hit_world=hit_world,
                radius=self._brush_world_radius,
                strength=_brush_strength_from_iterations(context),
                hardness=_props(context).brush_hardness,
                spatial_index=self._spatial_index,
            )
            changed += result

        self._last_hit_world = self._hit_world.copy()
        if changed > 0:
            self._did_smooth = True
            self._stroke_did_smooth = True
            self._coords_dirty = True
            if not self._flush_coords(context, throttled=True):
                return -1
        return changed

    def _samples_for_hit(self):
        last = getattr(self, "_last_hit_world", None)
        if last is None:
            return (self._hit_world,)
        radius = max(float(self._brush_world_radius), 1e-6)
        distance = (self._hit_world - last).length
        if distance <= radius * _BRUSH_INTERPOLATE_START_FACTOR:
            return (self._hit_world,)
        step = max(radius * _BRUSH_INTERPOLATE_STEP_FACTOR, 1e-6)
        sample_count = min(_BRUSH_MAX_INTERPOLATED_SAMPLES, max(0, math.ceil(distance / step) - 1))
        if sample_count <= 0:
            return (self._hit_world,)
        samples = [last.lerp(self._hit_world, index / (sample_count + 1)) for index in range(1, sample_count + 1)]
        samples.append(self._hit_world)
        return samples

    def _should_skip_sample(self):
        if self._hit_world is None or self._last_hit_world is None:
            return False
        radius = max(float(self._brush_world_radius), 1e-6)
        return (self._hit_world - self._last_hit_world).length < radius * 0.08

    def _flush_coords(self, context, throttled=False):
        if not self._coords_dirty:
            return True
        now = time.perf_counter()
        if throttled and now - self._last_write_time < _BRUSH_WRITE_INTERVAL:
            return True
        try:
            obj, mesh = self._resolve_target(context)
            if obj is None or mesh is None:
                return False
            self._obj = obj
            self._mesh = mesh
            self._write_coords(mesh)
            current_signature = polish_engine.polish_neighbors_signature(
                mesh,
                _props(context).feature_angle,
            )
            if current_signature != getattr(self, "_polish_neighbors_signature", None):
                self._polish_neighbors = polish_engine.build_brush_polish_neighbors(
                    mesh,
                    _props(context).feature_angle,
                )
                self._polish_neighbors_signature = current_signature
            self._world_positions = smooth_engine.mesh_world_positions(obj)
            self._mask_array = polish_engine.brush_mask_array(mesh)
            self._spatial_index = smooth_engine.build_position_spatial_index(self._world_positions)
            self._bvh = smooth_engine.build_bvh(mesh)
        except ReferenceError:
            return False
        except Exception as exc:
            self.report({"ERROR"}, f"Polish brush failed: {exc}")
            return False
        self._last_write_time = now
        self._coords_dirty = False
        self._tag_redraw(context, include_regions=True)
        return True

    def _flush_coords_direct(self):
        if not self._coords_dirty:
            return True
        try:
            mesh = getattr(self, "_mesh", None)
            if mesh is None or brush_context.safe_pointer(mesh) != getattr(self, "_mesh_ptr", 0):
                return False
            self._write_coords(mesh)
        except ReferenceError:
            return False
        except Exception:
            return False
        self._coords_dirty = False
        return True

    def _commit_stroke_undo(self):
        if not self._stroke_did_smooth or self._stroke_start_coords is None:
            self._stroke_start_coords = None
            return
        self._stroke_undo_stack.append(self._stroke_start_coords)
        if len(self._stroke_undo_stack) > _BRUSH_UNDO_LIMIT:
            self._stroke_undo_stack.pop(0)
        self._stroke_redo_stack.clear()
        self._stroke_start_coords = None

    def _restore_coords_snapshot(self, context, coords):
        obj, mesh = self._resolve_target(context)
        if obj is None or mesh is None:
            return False
        self._obj = obj
        self._mesh = mesh
        self._coords = coords.copy()
        self._coords_dirty = True
        self._last_hit_world = None
        return self._flush_coords(context)

    def _undo_stroke(self, context):
        if not self._stroke_undo_stack:
            return False
        previous_coords = self._stroke_undo_stack.pop()
        self._stroke_redo_stack.append(self._coords.copy())
        return self._restore_coords_snapshot(context, previous_coords)

    def _redo_stroke(self, context):
        if not self._stroke_redo_stack:
            return False
        next_coords = self._stroke_redo_stack.pop()
        self._stroke_undo_stack.append(self._coords.copy())
        if len(self._stroke_undo_stack) > _BRUSH_UNDO_LIMIT:
            self._stroke_undo_stack.pop(0)
        return self._restore_coords_snapshot(context, next_coords)

    def _begin_brush_adjust(self, context, event, mode):
        self._brush_adjust_mode = mode
        self._brush_adjust_start_mouse_x = event.mouse_x
        if mode == "HARDNESS":
            self._brush_adjust_start_value = float(_props(context).brush_hardness)
        else:
            self._brush_adjust_start_value = float(_props(context).brush_radius)
        self._set_status_text(context, self._adjust_status_text(context))

    def _handle_brush_adjust_event(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish_brush_adjust(context, cancelled=True)
            return {"RUNNING_MODAL"}
        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER", "SPACE"} and event.value == "PRESS":
            self._finish_brush_adjust(context, cancelled=False)
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE":
            self._update_brush_adjust_value(context, event)
            return {"RUNNING_MODAL"}
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    def _update_brush_adjust_value(self, context, event):
        delta = float(event.mouse_x - self._brush_adjust_start_mouse_x)
        if self._brush_adjust_mode == "HARDNESS":
            value = self._brush_adjust_start_value + delta / _BRUSH_HARDNESS_ADJUST_PIXELS
            _props(context).brush_hardness = float(np.clip(value, 0.0, 1.0))
            self._draw_state["hardness"] = self._brush_hardness(context)
        else:
            _props(context).brush_radius = max(
                _BRUSH_RADIUS_MIN,
                self._brush_adjust_start_value + delta * _BRUSH_RADIUS_ADJUST_PIXELS,
            )
            self._refresh_brush_radius(context)
        self._set_status_text(context, self._adjust_status_text(context))
        self._tag_redraw(context, include_regions=True)

    def _finish_brush_adjust(self, context, cancelled):
        if cancelled:
            if self._brush_adjust_mode == "HARDNESS":
                _props(context).brush_hardness = float(self._brush_adjust_start_value)
            elif self._brush_adjust_mode == "RADIUS":
                _props(context).brush_radius = max(_BRUSH_RADIUS_MIN, self._brush_adjust_start_value)
            self._refresh_brush_radius(context)
        self._brush_adjust_mode = None
        self._brush_adjust_start_mouse_x = 0
        self._brush_adjust_start_value = 0.0
        self._set_status_text(context, self._status_text())

    def _refresh_brush_radius(self, context):
        self._draw_state["screen_radius"] = self._screen_brush_radius(context)
        self._draw_state["hardness"] = self._brush_hardness(context)
        if self._hit_world is None:
            return
        region, region_data = brush_context.find_view3d_window(context)
        if region is None or region_data is None:
            self._draw_state["radius"] = self._brush_world_radius
            return
        world_radius = smooth_engine.view_depth_world_radius_for_screen_radius(
            region,
            region_data,
            self._hit_world,
            _props(context).brush_radius,
        )
        if world_radius > 0.0:
            self._brush_world_radius = world_radius
            self._draw_state["radius"] = world_radius

    def _screen_brush_radius(self, context):
        return max(float(_props(context).brush_radius), _BRUSH_RADIUS_MIN)

    def _brush_hardness(self, context):
        return float(np.clip(_props(context).brush_hardness, 0.0, 1.0))

    def _set_overlay_visible(self, visible, screen_visible=False):
        self._draw_state["visible"] = bool(visible)
        self._draw_state["screen_visible"] = bool(screen_visible)
        if not visible:
            self._draw_state["center"] = None
            self._draw_state["normal"] = None
        if not screen_visible:
            self._draw_state["screen_center"] = None

    def _status_text(self):
        return iface_(
            "Polish Brush active. LMB polishes; F adjusts Size; Shift+F adjusts Hardness; RMB or Esc finishes."
        )

    def _adjust_status_text(self, context):
        if self._brush_adjust_mode == "HARDNESS":
            return iface_("Adjust Hardness: %.3f. LMB/Enter confirms; RMB/Esc cancels.") % _props(context).brush_hardness
        return iface_("Adjust Size: %.1f px. LMB/Enter confirms; RMB/Esc cancels.") % _props(context).brush_radius

    def _set_status_text(self, context, text):
        try:
            context.workspace.status_text_set(text)
        except Exception:
            pass

    def _tag_redraw(self, context, include_regions=False):
        area = getattr(context, "area", None)
        if area is None:
            area = brush_context.find_area_by_pointer(context, getattr(self, "_area_ptr", None))
        brush_context.tag_area_redraw(area, include_regions=include_regions)

    def _restore_started_mode(self, context):
        if getattr(self, "_started_mode", "OBJECT") == "EDIT":
            try:
                bpy.ops.object.mode_set(mode="EDIT")
            except Exception:
                pass

    def _finish_modal_result(self, context, restore_mode=True):
        result = {"FINISHED"} if self._did_smooth else {"CANCELLED"}
        self._finish(context, restore_mode=restore_mode)
        return result

    def _finish_modal_passthrough(self, context, restore_mode=True):
        _mark_passthrough_close()
        self._finish(context, restore_mode=restore_mode)
        return {"FINISHED", "PASS_THROUGH"}

    def _finish(self, context, restore_mode=True):
        if self._coords_dirty:
            flushed = False
            if self._is_context_valid(context):
                flushed = self._flush_coords(context)
            if not flushed:
                flushed = self._flush_coords_direct()
            if not flushed:
                self._coords_dirty = False
        else:
            self._coords_dirty = False
        self._commit_stroke_undo()
        if self._handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            except Exception:
                pass
            self._handle = None
        if self._handle_2d is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, "WINDOW")
            except Exception:
                pass
            self._handle_2d = None
        self._set_status_text(context, None)
        if restore_mode:
            self._restore_started_mode(context)
        _SMOOTH_BRUSH_LIVE_OPERATORS.discard(self)
        _set_smooth_brush_active(False)
        self._tag_redraw(context, include_regions=True)

    def _force_cleanup(self, context=None):
        if self._coords_dirty:
            flushed = False
            if context is not None and self._is_context_valid(context):
                flushed = self._flush_coords(context)
            if not flushed:
                flushed = self._flush_coords_direct()
            if not flushed:
                self._coords_dirty = False
        try:
            bpy.context.workspace.status_text_set(None)
        except Exception:
            pass
        try:
            self._restore_started_mode(context or bpy.context)
        except Exception:
            pass
        if self._handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            except Exception:
                pass
            self._handle = None
        if self._handle_2d is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, "WINDOW")
            except Exception:
                pass
            self._handle_2d = None
        _SMOOTH_BRUSH_LIVE_OPERATORS.discard(self)
        if context is not None:
            self._tag_redraw(context, include_regions=True)
