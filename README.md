# FST ForgePolish

FST ForgePolish is a hard-surface polishing toolset for Blender. It is built for cleaning retopologized meshes, relaxing uneven topology, polishing edge flow, and preserving crisp mechanical boundaries before beveling, subdivision, or final sculpt cleanup.

## Installation

FST ForgePolish supports **Blender 4.2 LTS through 5.1**.

1. Download the latest `fst_forgepolish-1.1.0.zip` from the [Releases](../../releases) page.
2. Open Blender and go to **Edit > Preferences > Add-ons** or **Extensions**.
3. Choose **Install from Disk** and select the downloaded `.zip`.
4. Enable **FST ForgePolish**.

## Location

Open the **3D Viewport**, press `N` to show the Sidebar, then go to the **Edit** tab.

The Face Set utility buttons are available in **Edit Mode**. The main **Polish** operator and **Polish Brush** are launched from the same panel.

## Core Workflow

ForgePolish reads your current mesh context directly. Select what you want to clean, then press **Polish**.

- Select faces to polish a face region.
- Select an edge chain to polish edge flow.
- Select vertices to polish only those vertices.
- Leave nothing selected to polish the whole mesh.

No extra selection toggle is required. The tool decides the polish target from the current Edit Mode selection.

## Face Set Preparation

Face Sets are optional, but they give ForgePolish stronger surface boundaries and cleaner hard-surface results.

- **Create FaceSets from Edges**: Select separator edges in Edit Mode, then create Face Sets by flood fill.
- **Select FaceSet Boundaries**: Re-select the edges separating neighboring Face Sets.

This lets you isolate panels, curved transitions, and hard-surface islands without destructively splitting mesh data.

## Polishing Modes

- **Standard HC (Volume Preserve)**: Smooths the surface while using HC correction to reduce volume loss. This is the default choice for controlled cleanup.
- **Tension First (Surface Shrink)**: Prioritizes tension reduction for a tighter, sharper polish with more surface shrink.

## Edge Polishing

When the active Edit Mode selection is an edge chain, **Polish** relaxes the selected edges along their own flow instead of treating them like a face region.

Edge polishing is useful for:

- straightening wavy panel boundaries
- cleaning bevel support loops
- smoothing hard-surface transition lines
- polishing Face Set borders without changing the whole surface

Masked vertices, locked endpoints, and corner protection are respected.

## Polish Brush

The **Polish Brush** lets you polish locally in the viewport without repeatedly running a full mesh operation.

- **Left Mouse Button** paints local polish.
- **F** adjusts brush size.
- **Shift+F** adjusts hardness.
- **Ctrl+Z / Ctrl+Y** undo and redo brush strokes while the brush is active.
- **Right Mouse Button** or **Esc** exits the brush.

The brush uses the same topology-aware polish data as the main operator, respects Sculpt Mask values, and updates its overlay as you work.

## Parameters

- **Polish Strength**: Shared strength for face, edge, and brush polishing.
- **Corner Lock**: Protects sharp boundary corners. Set it to `0` to disable corner protection.
- **Advanced**: Opens lower-level controls.
- **Inner Smooth / Preserve**: Controls smoothing and volume preservation inside Face Set regions.
- **Boundary Smooth / Preserve**: Controls smoothing and volume preservation along Face Set boundaries.
- **Size**: Brush radius in screen pixels.
- **Hardness**: Brush falloff hardness.

## Multilingual Support

FST ForgePolish follows Blender's interface language when a translation is available.

Built-in languages:

- English
- Chinese Simplified
- Chinese Traditional
- German
- Spanish
- French
- Italian
- Japanese
- Korean
- Polish
- Portuguese (Brazil)
- Russian
- Vietnamese

Brush status text, tooltips, reports, panel labels, and operator names are included in the translation tables.

## Notes

- Sculpt Mask values are respected by the main polish operator, edge polishing, and the polish brush.
- Face Set boundaries can be used as polish guides without destructively splitting mesh data.
- Topology data is cached and reused where possible for responsive repeated polishing.

## License

GNU General Public License v3.0
