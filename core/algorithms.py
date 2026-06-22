import numpy as np

MAX_SURFACE_STEP_STRENGTH = 0.5


def _stable_surface_strength(strength):
    # Full-strength Jacobi Laplacian steps can flip high-frequency bends back and forth.
    return min(max(float(strength), 0.0), MAX_SURFACE_STEP_STRENGTH)


def _sum_neighbor_vectors(target_indices, source_indices, source_vectors, vert_count):
    if source_indices.size == 0:
        return np.zeros((vert_count, 3), dtype=source_vectors.dtype)

    source = source_vectors[source_indices]
    return np.column_stack(
        (
            np.bincount(target_indices, weights=source[:, 0], minlength=vert_count),
            np.bincount(target_indices, weights=source[:, 1], minlength=vert_count),
            np.bincount(target_indices, weights=source[:, 2], minlength=vert_count),
        )
    ).astype(source_vectors.dtype, copy=False)


def _iteration_scales(iterations):
    iterations = max(float(iterations), 0.0)
    full_iterations = int(iterations)
    for _ in range(full_iterations):
        yield 1.0

    fractional_iteration = iterations - full_iterations
    if fractional_iteration > 1e-6:
        yield fractional_iteration


def _laplacian_step_numpy(active_verts, neighbor_indices, neighbor_counts, source_pos, target_pos, mask_array, strength):
    if active_verts.size == 0:
        return

    target_pos[active_verts] = source_pos[active_verts]
    eff_strength = strength * (1.0 - mask_array[active_verts])
    active_counts = neighbor_counts[active_verts]
    valid_mask = (np.abs(eff_strength) >= 1e-12) & (active_counts > 0)
    if not np.any(valid_mask):
        return

    work_verts = active_verts[valid_mask]
    work_strength = eff_strength[valid_mask][:, None]
    counts = active_counts[valid_mask].astype(np.float32)
    target_indices, source_indices = neighbor_indices
    neigh_sum = _sum_neighbor_vectors(target_indices, source_indices, source_pos, source_pos.shape[0])
    neigh_avg = neigh_sum[work_verts] / counts[:, None]
    src = source_pos[work_verts]
    target_pos[work_verts] = src + (neigh_avg - src) * work_strength


def _hc_correction_step_numpy(active_verts, neighbor_indices, neighbor_counts, next_pos, b_err, cur_pos, beta):
    if active_verts.size == 0:
        return

    cur_pos[active_verts] = next_pos[active_verts]
    counts = neighbor_counts[active_verts]
    valid_mask = counts > 0
    if not np.any(valid_mask):
        return

    work_verts = active_verts[valid_mask]
    counts = counts[valid_mask].astype(np.float32)
    target_indices, source_indices = neighbor_indices
    err_sum = _sum_neighbor_vectors(target_indices, source_indices, b_err, next_pos.shape[0])
    avg_err = err_sum[work_verts] / counts[:, None]
    one_minus_beta = 1.0 - beta
    be = b_err[work_verts]
    cur_pos[work_verts] = next_pos[work_verts] - (be * beta + avg_err * one_minus_beta)


def _laplacian_step(active_verts, neighbor_data, source_pos, target_pos, mask_array, strength):
    target_indices, source_indices, neighbor_counts = neighbor_data
    neighbor_indices = (target_indices, source_indices)
    _laplacian_step_numpy(active_verts, neighbor_indices, neighbor_counts, source_pos, target_pos, mask_array, strength)


def _hc_correction_step(active_verts, neighbor_data, next_pos, b_err, cur_pos, beta):
    target_indices, source_indices, neighbor_counts = neighbor_data
    neighbor_indices = (target_indices, source_indices)
    _hc_correction_step_numpy(active_verts, neighbor_indices, neighbor_counts, next_pos, b_err, cur_pos, beta)


def run_standard_polish(
    iterations,
    strength,
    b_strength,
    hc_blend,
    b_hc_blend,
    beta,
    active_inner,
    active_bound,
    inner_neighbors,
    boundary_neighbors,
    mask_array,
    cur_pos,
    next_pos,
    orig_pos,
    b_err,
):
    step_strength = _stable_surface_strength(strength)
    boundary_step_strength = _stable_surface_strength(b_strength)

    for _ in range(iterations):
        _laplacian_step(active_inner, inner_neighbors, cur_pos, next_pos, mask_array, step_strength)
        _laplacian_step(active_bound, boundary_neighbors, cur_pos, next_pos, mask_array, boundary_step_strength)

        inner_next = next_pos[active_inner]
        inner_cur = cur_pos[active_inner]
        inner_orig = orig_pos[active_inner]
        bound_next = next_pos[active_bound]
        bound_cur = cur_pos[active_bound]
        bound_orig = orig_pos[active_bound]

        b_err[active_inner] = inner_next - (inner_orig * hc_blend + inner_cur * (1.0 - hc_blend))
        b_err[active_bound] = bound_next - (bound_orig * b_hc_blend + bound_cur * (1.0 - b_hc_blend))

        _hc_correction_step(active_inner, inner_neighbors, next_pos, b_err, cur_pos, beta)
        _hc_correction_step(active_bound, boundary_neighbors, next_pos, b_err, cur_pos, beta)


def run_tension_polish(
    iterations,
    strength,
    b_strength,
    active_inner,
    active_bound,
    active_all,
    inner_neighbors,
    boundary_neighbors,
    mask_array,
    cur_pos,
    next_pos,
):
    step_strength = _stable_surface_strength(strength)
    boundary_step_strength = _stable_surface_strength(b_strength)

    for iteration_scale in _iteration_scales(iterations):
        _laplacian_step(active_inner, inner_neighbors, cur_pos, next_pos, mask_array, step_strength * iteration_scale)
        _laplacian_step(active_bound, boundary_neighbors, cur_pos, next_pos, mask_array, boundary_step_strength * iteration_scale)
        cur_pos[active_all] = next_pos[active_all]
