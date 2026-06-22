import bpy
import bmesh
import math

from ..features.brush.ops_smooth_brush import is_smooth_brush_active

I18N_DEFAULT_CTXT = bpy.app.translations.contexts.default
STATUS_ICON = "KEYTYPE_MOVING_HOLD_VEC"


def has_valid_faceset(mesh, bm=None):
    if bm is not None and bm.faces.layers.int.get(".sculpt_face_set") is not None:
        return True
    face_attr = mesh.attributes.get(".sculpt_face_set")
    return face_attr is not None and face_attr.domain == "FACE"


def has_edit_selection(mesh, bm):
    select_mode = getattr(bm, "select_mode", None)
    if select_mode is None:
        return any(item.select for item in bm.select_history)

    mode = set(select_mode)

    if "VERT" in mode and getattr(mesh, "total_vert_sel", 0) > 0:
        return True
    if "EDGE" in mode and getattr(mesh, "total_edge_sel", 0) > 0:
        return True
    if "FACE" in mode and getattr(mesh, "total_face_sel", 0) > 0:
        return True

    return any(item.select for item in bm.select_history)


def update_algorithm_mode(self, _context):
    if self.algorithm_mode == "STANDARD":
        self.strength = 1.0
        self.hc_blend = 0.5
        self.boundary_strength = 1.0
        self.boundary_hc_blend = 1.0
    elif self.algorithm_mode == "TENSION":
        self.strength = 0.2
        self.boundary_strength = 0.1


class FSTFORGEPOLISH_PG_properties(bpy.types.PropertyGroup):
    algorithm_mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            (
                "STANDARD",
                "Standard HC (Volume Preserve)",
                "Smooth the surface while using HC correction to reduce volume loss",
            ),
            (
                "TENSION",
                "Tension First (Surface Shrink)",
                "Skip volume compensation and prioritize tension reduction for a sharper polish",
            ),
        ],
        default="STANDARD",
        update=update_algorithm_mode,
    )

    iterations: bpy.props.IntProperty(
        name="Polish Strength",
        default=7,
        min=1,
        max=200,
        description="Polish strength shared by face, edge, and brush smoothing",
    )

    feature_angle: bpy.props.FloatProperty(
        name="Corner Lock",
        default=0.0,
        min=0.0,
        max=math.pi,
        subtype="ANGLE",
        description="Lock sharp boundary corners; 0 disables corner protection",
    )

    show_advanced: bpy.props.BoolProperty(
        name="Advanced",
        description="Show low-level polish tuning controls",
        default=False,
    )

    strength: bpy.props.FloatProperty(
        name="Smooth",
        default=1.0,
        min=0.0,
        max=1.0,
        description="Single-step smoothing strength inside each face set",
    )

    hc_blend: bpy.props.FloatProperty(
        name="Preserve",
        default=0.5,
        min=0.0,
        max=1.0,
        description="Volume preservation strength for inner regions",
    )

    boundary_strength: bpy.props.FloatProperty(
        name="Smooth",
        default=1.0,
        min=0.0,
        max=1.0,
        description="Single-step smoothing strength on boundaries",
    )

    boundary_hc_blend: bpy.props.FloatProperty(
        name="Preserve",
        default=1.0,
        min=0.0,
        max=1.0,
        description="Volume preservation strength for boundary regions",
    )

    brush_radius: bpy.props.FloatProperty(
        name="Size",
        default=100.0,
        min=2.0,
        max=500.0,
        description="Polish brush radius in screen pixels",
    )

    brush_hardness: bpy.props.FloatProperty(
        name="Hardness",
        default=0.35,
        min=0.0,
        max=1.0,
        description="Polish brush inner falloff hardness",
    )


class VIEW3D_PT_polish_panel(bpy.types.Panel):
    bl_label = "FST ForgePolish"
    bl_idname = "VIEW3D_PT_polish_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Edit"

    def draw(self, context):
        layout = self.layout

        if not hasattr(context.scene, "fst_forgepolish_props"):
            layout.label(text="Properties are not registered. Reload the add-on.", icon=STATUS_ICON)
            return

        obj = context.active_object
        props = context.scene.fst_forgepolish_props
        in_edit_mode = obj is not None and obj.mode == "EDIT"
        brush_active = is_smooth_brush_active()

        if not obj or obj.type != "MESH":
            layout.label(text="Select a mesh object", text_ctxt=I18N_DEFAULT_CTXT, icon=STATUS_ICON)
            return

        mesh = obj.data
        has_faceset = has_valid_faceset(mesh)
        if in_edit_mode:
            bm = bmesh.from_edit_mesh(mesh)
            has_faceset = has_valid_faceset(mesh, bm=bm)
            has_selection = has_edit_selection(mesh, bm)
        else:
            has_selection = False

        box_mode = layout.box()
        col_mode = box_mode.column(align=True)
        col_mode.prop(props, "algorithm_mode", text="", text_ctxt=I18N_DEFAULT_CTXT)

        box_params = layout.box()
        col_params = box_params.column(align=True)
        col_params.use_property_split = False
        col_params.use_property_decorate = False
        col_params.prop(props, "iterations")
        col_params.prop(props, "feature_angle")
        col_params.separator()

        row = box_params.row(align=True)
        row.alignment = 'LEFT'
        icon = "DISCLOSURE_TRI_DOWN" if props.show_advanced else "DISCLOSURE_TRI_RIGHT"
        row.prop(props, "show_advanced", icon=icon, emboss=False)

        if props.show_advanced:
            adv_box = box_params.box()

            inner_col = adv_box.column(align=True)
            inner_col.use_property_split = False
            inner_col.use_property_decorate = False
            inner_col.label(text="Inner", text_ctxt=I18N_DEFAULT_CTXT)
            inner_col.prop(props, "strength")
            if props.algorithm_mode != "TENSION":
                inner_col.prop(props, "hc_blend")


            bound_col = adv_box.column(align=True)
            bound_col.use_property_split = False
            bound_col.use_property_decorate = False
            bound_col.label(text="Boundary", text_ctxt=I18N_DEFAULT_CTXT)
            bound_col.prop(props, "boundary_strength")
            if props.algorithm_mode != "TENSION":
                bound_col.prop(props, "boundary_hc_blend")

        layout.separator()

        action_box = layout.box()
        row = action_box.row(align=True)

        if has_faceset:
            select_op_row = row.row(align=True)
            select_op_row.enabled = in_edit_mode and not brush_active
            select_op_row.operator(
                "mesh.select_faceset_boundaries",
                icon="RESTRICT_SELECT_OFF",
                text="Select FaceSet Boundaries",
                text_ctxt=I18N_DEFAULT_CTXT,
            )

        create_op_row = row.row(align=True)
        create_op_row.enabled = in_edit_mode and not brush_active
        create_op_row.operator(
            "mesh.create_facesets_from_edges",
            icon="MOD_MASK",
            text="Create FaceSets from Edges",
            text_ctxt=I18N_DEFAULT_CTXT,
        )

        if not in_edit_mode and not has_faceset:
            action_box.label(
                text="Enter Edit Mode, select edges, then create Face Sets",
                text_ctxt=I18N_DEFAULT_CTXT,
                icon=STATUS_ICON,
            )

        if in_edit_mode and has_selection and not brush_active:
            action_box.label(
                text="Polish selected elements only",
                text_ctxt=I18N_DEFAULT_CTXT,
                icon=STATUS_ICON,
            )

        row = action_box.row(align=True)
        row.scale_y = 1.75
        polish_row = row.row(align=True)
        polish_row.enabled = not brush_active
        polish_row.operator(
            "mesh.fst_forgepolish_groups",
            icon="NONE",
            text="Polish",
            text_ctxt=I18N_DEFAULT_CTXT,
        )
        brush_row = row.row(align=True)
        brush_row.operator(
            "mesh.fst_forgepolish_smooth_brush",
            icon="BRUSH_DATA",
            text="",
            text_ctxt=I18N_DEFAULT_CTXT,
            depress=brush_active,
        )

        if brush_active:
            brush_col = action_box.column(align=True)
            brush_col.use_property_split = False
            brush_col.use_property_decorate = False
            brush_col.label(text="F Size  Shift+F Hardness", text_ctxt=I18N_DEFAULT_CTXT, icon=STATUS_ICON)
            brush_col.prop(props, "brush_radius")
            brush_col.prop(props, "brush_hardness")
