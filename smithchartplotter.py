

"""
Project: CNC Plotter Image Processor
Description: creates smith charts for the plotter.
Author: ryan
Date: 2026-03-06
"""

import os
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from tqdm import tqdm

# --- CONFIGURATION / CONSTANTS ---
# Using a dictionary or constants makes it easy to tweak settings in one place
SETTINGS = {
    "mode": "spiral",      # Options: "lines" or "spiral"
    "amplitude": 6,
    "frequency": 0.8,       # Higher freq looks better on spirals
    "spiral_density": 2.8, # Distance between rings
    "feedrate": 4000,      # CNC movement speed (mm/min)
    "output_dir": "output_gcode"
}

# --- HARDWARE CONFIGURATION ---
PEN_SETTINGS = {
    "up_height": 5,        # Z-coordinate for UP (or Servo Angle)
    "down_height": 0,      # Z-coordinate for DOWN (or Servo Angle)
    "lift_delay": 0.2,     # Seconds to wait for the physical motor to move
    "use_servo": False      # Set to False if using Z-axis coordinates
}

# --- PHYSICAL MACHINE SETTINGS ---
MACHINE = {
    "paper_width_mm": 210,   # A4 Width
    "paper_height_mm": 297,  # A4 Height
    "margin_mm": 10,         # Buffer to avoid drawing on the very edge
    "units": "mm"
}

def get_pen_up_cmd():
    if PEN_SETTINGS["use_servo"]:
        return f"M5 ; Pen Up\nG4 P{PEN_SETTINGS['lift_delay']}\n"
    else:
        return f"G1 Z{PEN_SETTINGS['up_height']} F3000 ; Lift Z\n"

def get_pen_down_cmd():
    if PEN_SETTINGS["use_servo"]:
        return f"M3 ; Pen Down\nG4 P{PEN_SETTINGS['lift_delay']}\n"
    else:
        return f"G1 Z{PEN_SETTINGS['down_height']} F1000 ; Lower Z\n"
    
def get_scaling_factor(img_w, img_h):
    """Calculates how much to shrink the pixels to fit the paper."""
    safe_w = MACHINE["paper_width_mm"] - (2 * MACHINE["margin_mm"])
    safe_h = MACHINE["paper_height_mm"] - (2 * MACHINE["margin_mm"])
    
    # Calculate scale for both dimensions
    scale_w = safe_w / img_w
    scale_h = safe_h / img_h
    
    # Use the smaller scale to ensure it fits entirely on the page
    return min(scale_w, scale_h)    

def load_and_preprocess(path):
    """Loads an image and converts it to a grayscale numpy array."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Could not find image at {path}")
    
    with Image.open(path) as img:
        return np.array(img.convert('L'))

def svg_to_plotter_paths(svg_filepath, target_width_mm):
    # 1. Load the paths and attributes from the SVG
    paths, attributes = svg2paths(svg_filepath)
    
    # Get original SVG dimensions to calculate scale
    # (Handling SVGs can be tricky if 'viewBox' isn't set, but this is a solid start)
    doc_width = float(attributes[0].get('width', '500').replace('px', ''))
    scale = target_width_mm / doc_width
    
    all_paths = []
    
    for path in paths:
        current_path = []
        # 2. Sample the path. 'num_steps' controls the resolution of the curves.
        # For a Smith Chart, 100-200 steps per path keeps curves smooth.
        num_steps = int(path.length() * 0.5) # Dynamic resolution based on length
        num_steps = max(10, min(num_steps, 300)) 
        
        for i in range(num_steps + 1):
            point = path.point(i / num_steps)
            # svgpathtools uses complex numbers (x + iy) for coordinates
            x_mm = point.real * scale
            y_mm = point.imag * scale
            current_path.append((x_mm, y_mm))
            
        all_paths.append(current_path)
        
    return all_paths
    
    return paths

def sort_svg_paths(paths):
    """
    Greedy nearest-neighbor sort for a list of coordinate paths.
    """
    if not paths:
        return paths

    sorted_paths = []
    # Start with the first path in the original list
    current_path = paths.pop(0)
    sorted_paths.append(current_path)
    
    while paths:
        # The end point of the path we just added
        last_point = np.array(sorted_paths[-1][-1])
        
        # Find the index of the path with the closest start point
        # We calculate the Euclidean distance to every remaining path's start
        distances = [np.linalg.norm(last_point - np.array(p[0])) for p in paths]
        closest_idx = np.argmin(distances)
        
        sorted_paths.append(paths.pop(closest_idx))
        
    return sorted_paths


def generate_gcode(paths, filename):
    filepath = os.path.join(SETTINGS['output_dir'], filename)
    
    with open(filepath, 'w') as f:
        # 1. Header
        f.write("G21 ; Units: mm\nG90 ; Absolute\n")
        f.write(get_pen_up_cmd()) # Start with pen UP
        
        for path in paths:
            # 2. RAPID MOVE to start of line (Pen is already UP)
            start_x, start_y = path[0]
            f.write(f"G0 X{start_x:.2f} Y{start_y:.2f}\n")
            
            # 3. LOWER PEN
            f.write(get_pen_down_cmd())
            
            # 4. DRAW LINE
            for x, y in path:
                f.write(f"G1 X{x:.2f} Y{y:.2f} F{SETTINGS['feedrate']}\n")
            
            # 5. LIFT PEN before moving to the next row
            f.write(get_pen_up_cmd())
            
        f.write("G0 X0 Y0 ; Return Home\n")
    print(f"Success! G-code saved to: {filepath}")
    
def visualize_paths(paths, height, width):
    """
    Creates a digital preview of the plotter paths.
    """
    plt.figure(figsize=(10, (height/width)*10), facecolor='white')
    
    for path in paths:
        # Zip (*path) separates [(x1,y1), (x2,y2)] into [x1, x2] and [y1, y2]
        x_coords, y_coords = zip(*path)
        
        # We invert the Y axis (-np.array) because image coordinates (0,0) 
        # are top-left, but Matplotlib (0,0) is bottom-left.
        plt.plot(x_coords, -np.array(y_coords), color='black', lw=0.8)

    plt.title("Plotter Preview")
    plt.axis('off') # Hide the graph axes for a cleaner look
    plt.gca().set_aspect('equal', adjustable='box')
    plt.savefig("echo spiral.png", dpi=300, bbox_inches='tight', pad_inches=0)
    plt.show()    

def main():
    """Main execution block."""
    try:
        # Set the radius of your chart in millimeters (e.g., 90mm for A4)
        target_size = 180 
        
        # 1. Extract raw coordinates
        print("Extracting vector data from SVG...")
        raw_paths = svg_to_plotter_paths("smith_chart.svg", target_size)
        
        # 2. Optimize the order for the plotter
        print(f"Sorting {len(raw_paths)} paths for efficiency...")
        sorted_paths = sort_svg_paths(raw_paths)
        
        # 3. Center and generate G-code
        offset_x = (MACHINE["paper_width_mm"] - target_size) / 2
        offset_y = (MACHINE["paper_height_mm"] - target_size) / 2
        
        final_paths = []
        for path in sorted_paths:
            final_paths.append([(p[0] + offset_x, p[1] + offset_y) for p in path])

        # Visualize to confirm the sequence looks logical
        visualize_paths(final_paths, 297, 210)
        

        # 4. Export G-code
        # Only generates if you want to proceed
        # confirm = input("Generate G-code? (y/n): ")
        # if confirm.lower() == 'y':
        #     generate_gcode(all_paths, "smith plot.nc")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()