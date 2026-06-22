def safe_pointer(item):
    try:
        return item.as_pointer() if item is not None else 0
    except (AttributeError, ReferenceError):
        return 0


def tag_area_redraw(area, include_regions=False):
    if area is None:
        return
    try:
        area.tag_redraw()
    except Exception:
        pass
    if not include_regions:
        return
    for region in getattr(area, "regions", []):
        try:
            region.tag_redraw()
        except Exception:
            pass


def find_area_region(area, region_type):
    if area is None:
        return None
    for region in getattr(area, "regions", []):
        if getattr(region, "type", None) == region_type:
            return region
    return None


def find_view3d_window(context):
    area = getattr(context, "area", None)
    if area is None or getattr(area, "type", None) != "VIEW_3D":
        return None, None

    region = find_area_region(area, "WINDOW")
    region_data = getattr(context, "region_data", None)
    if region_data is None:
        active_space = getattr(getattr(area, "spaces", None), "active", None)
        region_data = getattr(active_space, "region_3d", None)

    if region is None or region_data is None:
        return None, None
    return region, region_data


def _screen_from_context(context):
    screen = getattr(context, "screen", None)
    if screen is not None:
        return screen
    window = getattr(context, "window", None)
    return getattr(window, "screen", None) if window is not None else None


def _area_matches(area, mouse_x, mouse_y, area_ptr=None):
    if area_ptr is not None:
        try:
            if area.as_pointer() != area_ptr:
                return False
        except Exception:
            pass
    return (
        getattr(area, "type", None) == "VIEW_3D"
        and area.x <= mouse_x <= area.x + area.width
        and area.y <= mouse_y <= area.y + area.height
    )


def find_view3d_window_at_mouse(context, mouse_x, mouse_y, area_ptr=None):
    screen = _screen_from_context(context)
    if screen is None:
        return None, None, None

    for area in getattr(screen, "areas", []):
        if not _area_matches(area, mouse_x, mouse_y, area_ptr=area_ptr):
            continue

        for item in getattr(area, "regions", []):
            if getattr(item, "type", None) == "WINDOW":
                continue
            if item.x <= mouse_x <= item.x + item.width and item.y <= mouse_y <= item.y + item.height:
                return None, None, None

        for region in getattr(area, "regions", []):
            if getattr(region, "type", None) != "WINDOW":
                continue
            if not (region.x <= mouse_x <= region.x + region.width and region.y <= mouse_y <= region.y + region.height):
                continue
            active_space = getattr(getattr(area, "spaces", None), "active", None)
            region_data = getattr(active_space, "region_3d", None)
            if region_data is None:
                return None, None, None
            return area, region, region_data

    return None, None, None


def find_view3d_region_at_mouse(context, mouse_x, mouse_y, area_ptr=None):
    screen = _screen_from_context(context)
    if screen is None:
        return None, None

    for area in getattr(screen, "areas", []):
        if not _area_matches(area, mouse_x, mouse_y, area_ptr=area_ptr):
            continue

        for region in getattr(area, "regions", []):
            if region.x <= mouse_x <= region.x + region.width and region.y <= mouse_y <= region.y + region.height:
                return area, region

    return None, None


def find_area_by_pointer(context, area_ptr):
    if not area_ptr:
        return None

    screen = _screen_from_context(context)
    if screen is None:
        return None

    for area in getattr(screen, "areas", []):
        try:
            if area.as_pointer() == area_ptr:
                return area
        except Exception:
            continue

    return None
