import math

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector


def _matches_active_region(draw_state):
    target_area_ptr = draw_state.get("area_ptr")
    target_region_ptr = draw_state.get("region_ptr")
    if not target_area_ptr and not target_region_ptr:
        return True

    area = getattr(bpy.context, "area", None)
    region = getattr(bpy.context, "region", None)
    area_ptr = area.as_pointer() if area is not None else None
    region_ptr = region.as_pointer() if region is not None else None
    if target_area_ptr and area_ptr != target_area_ptr:
        return False
    if target_region_ptr and region_ptr != target_region_ptr:
        return False
    return True


def _surface_basis(normal):
    normal = Vector(normal).normalized()
    reference = Vector((0.0, 0.0, 1.0))
    if abs(normal.dot(reference)) > 0.96:
        reference = Vector((1.0, 0.0, 0.0))
    tangent = normal.cross(reference).normalized()
    bitangent = normal.cross(tangent).normalized()
    return tangent, bitangent


def _circle_points(center, normal, radius, segments):
    tangent, bitangent = _surface_basis(normal)
    return [
        center + (tangent * math.cos(math.tau * index / segments) + bitangent * math.sin(math.tau * index / segments)) * radius
        for index in range(segments + 1)
    ]


def _screen_circle_points(center, radius, segments):
    x, y = center
    return [
        (x + math.cos(math.tau * index / segments) * radius, y + math.sin(math.tau * index / segments) * radius)
        for index in range(segments + 1)
    ]


def _inner_radius(radius, hardness):
    hardness = max(0.0, min(float(hardness), 1.0))
    return radius * (0.05 + hardness * 0.90)


def draw_brush_overlay_2d(draw_state):
    if not draw_state or not draw_state.get("screen_visible", False):
        return
    if not _matches_active_region(draw_state):
        return

    center = draw_state.get("screen_center")
    radius = float(draw_state.get("screen_radius", 0.0))
    if center is None or radius <= 0.0:
        return

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    shader.bind()

    gpu.state.line_width_set(1.5)
    shader.uniform_float("color", (1.0, 1.0, 1.0, 0.88))
    batch_for_shader(shader, "LINE_STRIP", {"pos": _screen_circle_points(center, radius, 72)}).draw(shader)

    inner = _inner_radius(radius, draw_state.get("hardness", 0.0))
    if inner > 0.0:
        gpu.state.line_width_set(1.0)
        shader.uniform_float("color", (1.0, 1.0, 1.0, 0.28))
        batch_for_shader(shader, "LINE_STRIP", {"pos": _screen_circle_points(center, inner, 48)}).draw(shader)

    gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")


def draw_brush_overlay(draw_state):
    if not draw_state or not draw_state.get("visible", False):
        return
    if not _matches_active_region(draw_state):
        return

    center = draw_state.get("center")
    normal = draw_state.get("normal")
    radius = float(draw_state.get("radius", 0.0))
    if center is None or normal is None or radius <= 0.0:
        return

    center = Vector(center)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    try:
        gpu.state.depth_test_set("LESS_EQUAL")
    except Exception:
        pass

    shader.bind()
    gpu.state.line_width_set(1.6)
    shader.uniform_float("color", (1.0, 1.0, 1.0, 0.95))
    batch_for_shader(shader, "LINE_STRIP", {"pos": _circle_points(center, normal, radius, 80)}).draw(shader)

    inner = _inner_radius(radius, draw_state.get("hardness", 0.0))
    if inner > 0.0:
        gpu.state.line_width_set(1.0)
        shader.uniform_float("color", (1.0, 1.0, 1.0, 0.35))
        batch_for_shader(shader, "LINE_STRIP", {"pos": _circle_points(center, normal, inner, 48)}).draw(shader)

    try:
        gpu.state.depth_test_set("NONE")
    except Exception:
        pass
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")
