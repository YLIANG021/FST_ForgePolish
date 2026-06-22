# FST ForgePolish

FST ForgePolish is a hard-surface polishing toolset for Blender, built for cleaning retopologized meshes, relaxing uneven topology, and preserving crisp mechanical boundaries before beveling, subdivision, or final sculpt cleanup.

The 1.1.0 release adds edge-chain polishing, an interactive polish brush, a simplified selection workflow, and expanded multilingual UI support.

## Installation

FST ForgePolish supports **Blender 4.2 LTS through 5.1**.

1. Download the latest `fst_forgepolish-1.1.0.zip` from the [Releases](../../releases) page.
2. Open Blender and go to **Edit > Preferences > Add-ons** or **Extensions**.
3. Choose **Install from Disk** and select the downloaded `.zip`.
4. Enable **FST ForgePolish**.

## Location

Open the **3D Viewport**, press `N` to show the Sidebar, then go to the **Edit** tab.

The Face Set utility buttons are available in **Edit Mode**. The main **Polish** operator works from Object/Edit workflows, and the brush can be launched from the same panel.

## What Is New In 1.1.0

### Edge Polishing

Select an edge chain in Edit Mode and press **Polish**. ForgePolish now detects that the active selection is an edge chain and relaxes it along its own flow instead of treating it like a face region.

This is useful for:

- straightening wavy panel boundaries
- cleaning bevel support loops
- smoothing hard-surface transition lines
- polishing Face Set borders without changing the whole surface

Masked vertices, locked endpoints, and corner protection are respected.

### Polish Brush

The new brush mode lets you polish locally in the viewport without repeatedly running the full mesh operator.

- **Left Mouse Button** paints local polish.
- **F** adjusts brush size.
- **Shift+F** adjusts hardness.
- **Ctrl+Z / Ctrl+Y** undo and redo brush strokes while the brush is active.
- **Right Mouse Button** or **Esc** exits the brush.

The brush uses the same topology-aware polish data as the main operator, respects Sculpt Mask values, and updates its overlay as you work.

### Simplified Selection Flow

The old separate selection toggle has been removed. ForgePolish now reads the current Edit Mode selection directly:

- selected faces polish as a face region
- selected edge chains polish as edges
- selected vertices polish locally
- no selection polishes the whole mesh

This keeps the workflow simple: select what you want to clean, then press **Polish**.

### Expanded Multilingual UI

The interface now includes built-in translations for:

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

Brush status text, tooltips, reports, panel labels, and the new 1.1.0 controls are included in the translation tables.

## Core Workflow

### 1. Optional Face Set Preparation

Face Sets are useful when you want ForgePolish to preserve surface islands and polish boundaries intelligently.

- **Create FaceSets from Edges**: In Edit Mode, select separator edges and create Face Sets by flood fill.
- **Select FaceSet Boundaries**: Re-select the edges separating neighboring Face Sets.

You do not need Face Sets for every use case. The tool can polish the whole mesh, selected faces, selected vertices, or selected edge chains directly.

### 2. Choose A Mode

- **Standard HC (Volume Preserve)**: Smooths the surface while using HC correction to reduce volume loss.
- **Tension First (Surface Shrink)**: Prioritizes tension reduction for a tighter, sharper polish with more surface shrink.

### 3. Polish

Use **Polish** for a one-shot operation, or use the **Polish Brush** for controlled local cleanup.

## Parameters

- **Polish Strength**: Shared strength for face, edge, and brush polishing.
- **Corner Lock**: Protects sharp boundary corners. Set it to `0` to disable corner protection.
- **Advanced**: Opens lower-level controls.
- **Inner Smooth / Preserve**: Controls smoothing and volume preservation inside Face Set regions.
- **Boundary Smooth / Preserve**: Controls smoothing and volume preservation along Face Set boundaries.
- **Size**: Brush radius in screen pixels.
- **Hardness**: Brush falloff hardness.

## Notes

- Sculpt Mask values are respected by the main polish operator, edge polishing, and the polish brush.
- Face Set boundaries can be used as polish guides without destructively splitting mesh data.
- Topology data is cached and reused where possible for responsive repeated polishing.

## License

GNU General Public License v3.0
