import bpy

from . import i18n
from .features.brush import MESH_OT_fst_forgepolish_smooth_brush
from .features.brush.ops_smooth_brush import shutdown_active_smooth_brush
from .operators.polish import (
    MESH_OT_create_facesets_from_edges,
    MESH_OT_fst_forgepolish_groups,
    MESH_OT_select_faceset_boundaries,
)
from .ui.panel import FSTFORGEPOLISH_PG_properties, VIEW3D_PT_polish_panel

classes = [
    FSTFORGEPOLISH_PG_properties,
    MESH_OT_create_facesets_from_edges,
    MESH_OT_select_faceset_boundaries,
    MESH_OT_fst_forgepolish_groups,
    MESH_OT_fst_forgepolish_smooth_brush,
    VIEW3D_PT_polish_panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    i18n.register()
    bpy.types.Scene.fst_forgepolish_props = bpy.props.PointerProperty(
        type=FSTFORGEPOLISH_PG_properties
    )


def unregister():
    shutdown_active_smooth_brush()

    if hasattr(bpy.types.Scene, "fst_forgepolish_props"):
        del bpy.types.Scene.fst_forgepolish_props

    i18n.unregister()

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
