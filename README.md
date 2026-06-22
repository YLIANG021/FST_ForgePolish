# FST ForgePolish

FST ForgePolish is a hard-surface smoothing and polishing toolkit built for Blender. It is designed to clean up remeshed topology, smooth uneven surfaces, refine edge flow, and preserve crisp mechanical boundaries before beveling, subdivision, or final sculpt cleanup.

## Multi-Language Support

FST ForgePolish automatically follows Blender's interface language.
Currently supported languages: 

English, 简体中文, 繁體中文, Deutsch, Espanol, Francais, Italiano, 日本語, 한국어, Polski, Portugues, Русский, Tieng Viet.

## Location

Open the **3D Viewport**, press `N` to open the sidebar, then switch to the **Edit** tab.

## Polish with Face Sets

Face Sets give ForgePolish stronger boundary control, allowing you to isolate panels and hard-surface islands without destructively splitting the mesh, resulting in cleaner polishing.

1. **Create Face Sets from Edges**: In Edit Mode, select separator edges and click **Create Face Sets from Edges** to quickly divide regions using flood fill.
2. **Inspect Face Sets (Optional)**: You can temporarily switch to Sculpt Mode to visually check whether the Face Sets were created correctly.
3. **Polish Directly**: Return to Edit Mode and click **Polish**. The tool will automatically detect and protect Face Set boundaries while smoothing the surface and preserving clean mechanical structure.
<img width="800" height="500" alt="基本流程" src="https://github.com/user-attachments/assets/691cd016-7f04-495f-8e70-a876f05f65e3" />

## Automatic Selection Detection

ForgePolish reads the current mesh context directly. Select the area you want to clean up, then click **Polish**.

- **Face Selection**: Polishes the selected face region.
- **Edge Selection**: Smooths along the edge flow and refines selected edge chains.
- **Vertex Selection**: Polishes only the selected vertices.
- **Nothing Selected**: Polishes the entire mesh.
<img width="800" height="500" alt="部分选择" src="https://github.com/user-attachments/assets/3f5425c9-dede-4656-9937-115643fde7c7" />

No manual selection mode switching is required. The tool automatically determines the polishing target from the current Edit Mode selection.

## Edge Polishing

When the current Edit Mode selection is edges, **Polish** relaxes the selected edges along their own flow instead of treating them as a face region.

The tool also strictly respects masked vertices, locked endpoints, and corner protection.
<img width="800" height="500" alt="抛光边线" src="https://github.com/user-attachments/assets/e5f73c7b-1e67-4fb8-9ea2-57e2a58c353b" />

## Polish Brush

The Polish Brush lets you apply local polishing directly in the viewport without repeatedly running the full mesh operation.

- **F**: Adjust brush size.
- **Shift+F**: Adjust brush hardness.
- **Right Mouse Button or Esc**: Exit brush mode.
<img width="800" height="500" alt="笔刷" src="https://github.com/user-attachments/assets/369ba520-fe1a-4687-adb1-405e4d51eda5" />

## Polish Modes

- **Standard HC Mode**: Smooths the surface while using HC correction to reduce volume loss. This is the default choice for controlled cleanup.
- **Tension First**: Prioritizes tension reduction for a tighter, sharper polished result, with more noticeable surface shrinkage.

## Parameters

- **Polish Strength**: Shared strength control for face, edge, and brush polishing.
- **Corner Lock**: Protects sharp boundary corners. Set it to `0` to disable corner protection.
- **Advanced**: Reveals lower-level tuning controls.
- **Inner Smooth / Preserve**: Controls smoothing and volume preservation inside Face Set regions.
- **Boundary Smooth / Preserve**: Controls smoothing and volume preservation along Face Set boundaries.
- **Size**: Brush radius.
- **Hardness**: Brush falloff hardness.

## Installation

FST ForgePolish supports **Blender 4.2 LTS through 5.2**.

1. Download the latest `fst_forgepolish-1.1.0.zip` from the [Releases](../../releases) page.
2. Open Blender and go to **Edit > Preferences > Add-ons** or **Extensions**.
3. Choose **Install from Disk** and select the downloaded `.zip` file.
4. Enable **FST ForgePolish**.

## License

GNU General Public License v3.0
