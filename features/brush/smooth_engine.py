import numpy as np
from bpy_extras import view3d_utils
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


SPATIAL_INDEX_MIN_SIZE = 5000


def brush_falloff(values, hardness):
    values = np.asarray(values, dtype=np.float32)
    hardness = max(0.0, min(float(hardness), 1.0))
    if hardness >= 1.0:
        return np.ones_like(values, dtype=np.float32)

    soft_width = max(1.0 - hardness, 1e-6)
    softened = np.clip(values / soft_width, 0.0, 1.0)
    result = softened * softened * (3.0 - 2.0 * softened)
    if hardness > 0.0:
        result[values >= soft_width] = 1.0
    return result


def mesh_world_positions(obj):
    mesh = obj.data
    if len(mesh.vertices) == 0:
        return np.zeros((0, 3), dtype=np.float32)

    local = np.empty((len(mesh.vertices), 3), dtype=np.float32)
    mesh.vertices.foreach_get("co", local.reshape(-1))
    matrix = np.array(obj.matrix_world, dtype=np.float32)
    return local @ matrix[:3, :3].T + matrix[:3, 3]


def build_bvh(mesh):
    if len(mesh.vertices) == 0 or len(mesh.polygons) == 0:
        return None

    verts = [vert.co.copy() for vert in mesh.vertices]
    polygons = [tuple(poly.vertices) for poly in mesh.polygons if poly.loop_total >= 3]
    if not polygons:
        return None
    return BVHTree.FromPolygons(verts, polygons)


def build_position_spatial_index(positions, min_size=SPATIAL_INDEX_MIN_SIZE):
    if positions is None or len(positions) < int(min_size):
        return None

    tree = KDTree(len(positions))
    for index, position in enumerate(positions):
        tree.insert((float(position[0]), float(position[1]), float(position[2])), index)
    tree.balance()
    return tree


def build_vertex_neighbors(mesh):
    neighbors = [set() for _ in mesh.vertices]
    for edge in mesh.edges:
        a, b = edge.vertices
        neighbors[a].add(b)
        neighbors[b].add(a)
    return [np.asarray(sorted(item), dtype=np.int32) for item in neighbors]


def _surface_tangent(normal):
    normal = Vector(normal).normalized()
    reference = Vector((0.0, 0.0, 1.0))
    if abs(normal.dot(reference)) > 0.96:
        reference = Vector((1.0, 0.0, 0.0))
    return normal.cross(reference).normalized()


def world_radius_for_screen_radius(region, region_data, center, normal, screen_radius):
    if region is None or region_data is None or center is None or normal is None:
        return 0.0
    screen_radius = max(float(screen_radius), 0.0)
    if screen_radius <= 0.0:
        return 0.0

    center = Vector(center)
    tangent = _surface_tangent(normal)
    center_2d = view3d_utils.location_3d_to_region_2d(region, region_data, center)
    edge_2d = view3d_utils.location_3d_to_region_2d(region, region_data, center + tangent)
    if center_2d is None or edge_2d is None:
        return 0.0

    pixels_per_world_unit = (edge_2d - center_2d).length
    if pixels_per_world_unit <= 1e-6:
        return 0.0
    return max(screen_radius / pixels_per_world_unit, 1e-6)


def view_depth_world_radius_for_screen_radius(region, region_data, center, screen_radius):
    if region is None or region_data is None or center is None:
        return 0.0
    screen_radius = max(float(screen_radius), 0.0)
    if screen_radius <= 0.0:
        return 0.0

    center = Vector(center)
    center_2d = view3d_utils.location_3d_to_region_2d(region, region_data, center)
    if center_2d is None:
        return 0.0

    edge_2d = center_2d + Vector((screen_radius, 0.0))
    edge_world = view3d_utils.region_2d_to_location_3d(region, region_data, edge_2d, center)
    return max((edge_world - center).length, 1e-6)


def world_brush_indices(positions, hit_world, radius, spatial_index=None):
    if hit_world is None or positions.size == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)

    radius = max(float(radius), 1e-6)
    if spatial_index is not None:
        hits = spatial_index.find_range(hit_world, radius)
        if not hits:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)
        local_indices = np.fromiter((item[1] for item in hits), dtype=np.int64, count=len(hits))
        distances = np.fromiter((item[2] for item in hits), dtype=np.float32, count=len(hits))
        return local_indices, distances

    hit = np.array((hit_world.x, hit_world.y, hit_world.z), dtype=np.float32)
    offsets = positions - hit
    distances_sq = np.einsum("ij,ij->i", offsets, offsets)
    active_mask = distances_sq <= radius * radius
    if not np.any(active_mask):
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)

    local_indices = np.flatnonzero(active_mask)
    distances = np.sqrt(distances_sq[local_indices]).astype(np.float32, copy=False)
    return local_indices, distances


def raycast_surface_hit(region, region_data, mouse_x, mouse_y, *, bvh, world_matrix, world_matrix_inv):
    if bvh is None or region is None or region_data is None:
        return None, None

    coord = (mouse_x, mouse_y)
    origin = view3d_utils.region_2d_to_origin_3d(region, region_data, coord)
    direction = view3d_utils.region_2d_to_vector_3d(region, region_data, coord)
    local_origin = world_matrix_inv @ origin
    local_direction = (world_matrix_inv.to_3x3() @ direction).normalized()
    hit_location, hit_normal, _face_index, _distance = bvh.ray_cast(local_origin, local_direction)
    if hit_location is None:
        return None, None

    hit_world = world_matrix @ hit_location
    hit_normal_world = (world_matrix_inv.transposed().to_3x3() @ hit_normal).normalized()
    return hit_world, hit_normal_world


def smooth_vertices_at_hit(
    *,
    coords,
    world_positions,
    neighbors,
    hit_world,
    radius,
    strength,
    hardness,
    spatial_index=None,
):
    local_indices, distances = world_brush_indices(world_positions, hit_world, radius, spatial_index=spatial_index)
    if len(local_indices) == 0:
        return 0

    falloff = 1.0 - np.clip(distances / max(float(radius), 1e-6), 0.0, 1.0)
    factors = brush_falloff(falloff, hardness) * max(0.0, min(float(strength), 1.0))
    changed = 0
    source = coords.copy()

    for vert_index, factor in zip(local_indices, factors):
        if factor <= 1e-6:
            continue
        neighbor_indices = neighbors[int(vert_index)]
        if neighbor_indices.size == 0:
            continue
        target = source[neighbor_indices].mean(axis=0)
        coords[int(vert_index)] = source[int(vert_index)] + (target - source[int(vert_index)]) * factor
        changed += 1

    return changed
