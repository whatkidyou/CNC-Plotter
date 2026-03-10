"""
Project: CNC Plotter Image Processor (Refactored)
Description: High-efficiency SVG to G-code converter. originally for smith charts but
    made (hopefully) to accomidate any SVG file. there's no contrast optimization so 
    black and white is best for this one
Author: ryan
Date: 2026-03-08
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from svgpathtools import svg2paths
from tqdm import tqdm
from scipy.spatial import KDTree

# --- GLOBAL SETTINGS (The Source of Truth) ---
CONFIG = {
    "machine_limit_x": 1200,    # 4 feet ~ 1219mm
    "machine_limit_y": 1200,
    "paper_width_mm": 432,      # Current paper (e.g., Letter width)
    "paper_height_mm": 356,     # Current paper (e.g., A4/Letter height)
    "margin_mm": 10,            # Safe distance from paper edge
    "target_width_mm": 345,     # Used if scale_to_fit is False
    "scale_to_fit": False,
    
    "feedrate": 4500,
    "z_safe": 5.0,
    "z_draw": 0.0,
    "output_dir": "output_gcode"
}


def get_svg_paths(filepath, final_width_mm):
    """Extracts paths and scales them so the 'ink' matches the target width."""
    paths, attributes = svg2paths(filepath)
    
    # 1. Filter out empty paths before doing ANY math
    valid_paths = [p for p in paths if p.length() > 0.1]
    if not valid_paths:
        raise ValueError("No valid paths found in SVG.")

    # 2. Find the raw bounding box of the SVG 'ink' to calculate scale
    raw_pts = []
    for p in valid_paths:
        # Sample start and end to get a bounding box estimate
        p0 = p.point(0)
        p1 = p.point(1)
        raw_pts.append([p0.real, p0.imag])
        raw_pts.append([p1.real, p1.imag])
    
    raw_pts = np.array(raw_pts)
    ink_width_units = np.max(raw_pts[:, 0]) - np.min(raw_pts[:, 0])
    
    # Calculate exactly how many mm per SVG unit
    unit_to_mm_scale = final_width_mm / ink_width_units
    
    processed = []
    for path in tqdm(valid_paths, desc="Vectorizing SVG", unit="path"):
        # Adaptive resolution
        num_steps = 100 if path.length() < 50.0 else max(2, int(path.length() * 0.5))
        num_steps = min(num_steps, 400) 
        
        points = []
        for i in range(num_steps + 1):
            pt = path.point(i / num_steps)
            points.append([pt.real * unit_to_mm_scale, pt.imag * unit_to_mm_scale])
            
        processed.append(np.array(points))
    
    return processed

def process_geometry(paths):
    """Flips Y-axis and centers the drawing on the paper."""
    all_pts = np.vstack(paths)
    min_x, min_y = np.min(all_pts, axis=0)
    max_x, max_y = np.max(all_pts, axis=0)
    
    ink_w = max_x - min_x
    ink_h = max_y - min_y
    
    # 1. Flip Y (SVG top-left (0,0) -> CNC bottom-left (0,0))
    for p in paths:
        p[:, 1] = max_y - p[:, 1]
    
    # 2. Re-calculate bounds after flip to center properly
    all_pts_flipped = np.vstack(paths)
    f_min_x, f_min_y = np.min(all_pts_flipped, axis=0)
    
    # 3. Calculate offsets to center 'ink' on the paper
    offset_x = (CONFIG["paper_width_mm"] / 2) - (ink_w / 2) - f_min_x
    offset_y = (CONFIG["paper_height_mm"] / 2) - (ink_h / 2) - f_min_y
    
    for p in paths:
        p[:, 0] += offset_x
        p[:, 1] += offset_y
        
    return paths

def sort_paths_kdtree(paths):
    """Spatial sorting to minimize pen-up travel distance."""
    if not paths: return []
    remaining = list(range(len(paths)))
    sorted_indices = [remaining.pop(0)]
    
    with tqdm(total=len(paths), desc="Sorting Paths") as pbar:
        while remaining:
            current_end = paths[sorted_indices[-1]][-1]
            starts = np.array([paths[i][0] for i in remaining])
            tree = KDTree(starts)
            _, nearest_idx = tree.query(current_end)
            sorted_indices.append(remaining.pop(nearest_idx))
            pbar.update(1)
            
    return [paths[i] for i in sorted_indices]

def generate_gcode_stream(paths, filename):
    """Writes G-code using Servo commands (M3 S[XX]) instead of Z-axis moves."""
    os.makedirs(CONFIG['output_dir'], exist_ok=True)
    filepath = os.path.join(CONFIG['output_dir'], filename)
    
    # Servo settings
    PEN_DOWN = 125
    PEN_UP = 51
    
    with open(filepath, "w") as f:
        # Initialize
        f.write("G21 ; mm units\nG90 ; Absolute positioning\n")
        f.write(f"M3 S{PEN_UP} ; Ensure pen is up at start\n")
        
        for path in tqdm(paths, desc="Generating G-Code"):
            # Move to start (Pen Up)
            f.write(f"G0 X{path[0][0]:.3f} Y{path[0][1]:.3f} F{CONFIG['feedrate']}\n")
            
            # Lower the Pen (Servo Down)
            f.write(f"M3 S{PEN_DOWN} ; Pen Down\n")
            
            # Draw Path
            for i in range(1, len(path)):
                f.write(f"G1 X{path[i][0]:.3f} Y{path[i][1]:.3f} F{CONFIG['feedrate']}\n")
            
            # Lift the Pen (Servo Up)
            f.write(f"M3 S{PEN_UP} ; Pen Up\n")
            # Add a 0.2 second pause for the physical arm to lift
            f.write("G4 P0.2 ; Dwell for servo lift\n")
            
        f.write("G0 X0 Y0 ; Return Home\nM3 ; Ensure pen up at end\nM30\n")
    print(f"\nSaved G-code with Servo Control: {filepath}")

def preview_plot(paths):
    """Proportional Matplotlib preview based on paper size."""
    ratio = CONFIG["paper_height_mm"] / CONFIG["paper_width_mm"]
    fig_w = 7
    fig, ax = plt.subplots(figsize=(fig_w, fig_w * ratio))
    
    # Draw Paper Outline
    ax.add_patch(plt.Rectangle((0, 0), CONFIG["paper_width_mm"], CONFIG["paper_height_mm"], 
                                fill=False, color='blue', lw=2, label="Paper"))

    for p in paths:
        ax.plot(p[:, 0], p[:, 1], 'g-', lw=0.6)
    
    ax.set_aspect('equal')
    ax.set_xlim(-10, CONFIG["paper_width_mm"] + 10)
    ax.set_ylim(-10, CONFIG["paper_height_mm"] + 10)
    plt.title(f"Preview ({CONFIG['paper_width_mm']}x{CONFIG['paper_height_mm']}mm)")
    plt.savefig("simulation output.png", dpi=300, bbox_inches='tight', pad_inches=0)
    plt.show()

def main():
    try:
        # Determine target width
        if CONFIG["scale_to_fit"]:
            width = CONFIG["paper_width_mm"] - (2 * CONFIG["margin_mm"])
        else:
            width = CONFIG["target_width_mm"]

        # 1. Load & Scale
        raw_paths = get_svg_paths("no scale smith chart.svg", width)
        
        # 2. Flip & Center
        centered_paths = process_geometry(raw_paths)
        
        # 3. Sort
        sorted_paths = sort_paths_kdtree(centered_paths)
        
        # 4. Preview
        preview_plot(sorted_paths)
        
        # 5. Export
        if input("Generate G-Code? (y/n): ").lower() == 'y':
            generate_gcode_stream(sorted_paths, "smith_chart_final.nc")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()