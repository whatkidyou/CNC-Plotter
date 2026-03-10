

"""
Project: CNC Plotter Image Processor
Description: Converts images to G-code using stippling patterns
Author: ryan
Date: 2026-03-04
"""

import os
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from tqdm import tqdm
import random

# --- CONFIGURATION / CONSTANTS ---
# Using a dictionary or constants makes it easy to tweak settings in one place
SETTINGS = {
    "mode": "stipple",
    "stipple_step": 5,      # How many pixels to skip (Resolution)
    "feedrate": 8000,       # High feedrate is better for stippling
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

def generate_stipple_path(image_data, scale, cfg):
    h, w = image_data.shape
    all_dots = []
    
    # Increase stipple_density to check more pixels (e.g., step=2 or 1)
    # Decrease it to speed up the plot (e.g., step=5)
    step = cfg.get("stipple_step", 3)
    
    print("Calculating stipple points...")
    for y_px in range(0, h, step):
        for x_px in range(0, w, step):
            brightness = image_data[y_px, x_px]
            
            # Probability: 0.0 (white) to 1.0 (black)
            intensity = (255 - brightness) / 255.0
            
            # Add a 'contrast' boost to intensity to sharpen the image
            intensity = np.power(intensity, 1.5) 
            
            # Roll the dice!
            if random.random() < intensity:
                x_mm = (x_px * scale) + MACHINE["margin_mm"]
                y_mm = (y_px * scale) + MACHINE["margin_mm"]
                
                # In stippling, each "path" is just one single dot
                all_dots.append([(x_mm, y_mm)])
                
    return all_dots

def sort_stipple_paths(paths):
    """
    Sorts points into a snake pattern to minimize travel distance.
    Assumes paths are generated in a grid (row by row).
    """
    if not paths:
        return paths

    # 1. Group dots by their Y-coordinate (rows)
    # We round the Y to handle tiny floating point differences
    rows = {}
    for p in paths:
        y = round(p[0][1], 2)
        if y not in rows:
            rows[y] = []
        rows[y].append(p)
    
    sorted_rows = sorted(rows.keys())
    final_paths = []
    
    # 2. Iterate through rows and flip every second one
    for i, y in enumerate(sorted_rows):
        row_dots = sorted(rows[y], key=lambda p: p[0][0]) # Sort by X
        if i % 2 != 0:
            row_dots.reverse() # Snake back the other way
        final_paths.extend(row_dots)
        
    return final_paths

def generate_stipple_gcode(dots, filename):
    os.makedirs(SETTINGS['output_dir'], exist_ok=True)
    filepath = os.path.join(SETTINGS['output_dir'], filename)
    
    with open(filepath, 'w') as f:
        f.write("G21 ; mm\nG90 ; Absolute\n")
        f.write(f"F{SETTINGS['feedrate']}\n")
        
        for dot in dots:
            x, y = dot[0]
            # 1. Rapid move to coordinate
            f.write(f"G0 X{x:.2f} Y{y:.2f}\n")
            # 2. Quick tap down and up
            f.write(get_pen_down_cmd())
            f.write(get_pen_up_cmd())
            
        f.write("G0 X0 Y0\n")
    
def visualize_paths(paths, height, width):
    plt.figure(figsize=(10, (height/width)*10))
    
    if SETTINGS["mode"] == "stipple":
        # Extract the single point from each dot-path
        x_coords = [p[0][0] for p in paths]
        y_coords = [-p[0][1] for p in paths]
        plt.scatter(x_coords, y_coords, s=1, c='black') # 's' is the dot size
    else:
        for path in paths:
            x_coords, y_coords = zip(*path)
            plt.plot(x_coords, -np.array(y_coords), color='black', lw=0.8)

    plt.axis('off')
    plt.gca().set_aspect('equal')
    plt.savefig("stippling.png", dpi=300, bbox_inches='tight', pad_inches=0)
    plt.show()  

def main():
    """Main execution block."""
    try:
        # 1. Load data
        # Replace with your actual image filename
        image_data = load_and_preprocess("echo square.PNG")
        # Rescale the image so the darkest pixel is 0 and the brightest is 255
        image_data = ((image_data - image_data.min()) * (255 / (image_data.max() - image_data.min()))).astype(np.uint8)
        # Raise to a power (e.g., 1.5) to make shadows deeper
        # Normalize to 0.0-1.0 first, then push back to 0-255
        #image_data = (np.power(image_data / 255.0, 1.6) * 255).astype(np.uint8)
        
        h_px, w_px = image_data.shape
        scale = get_scaling_factor(w_px, h_px)
        print(f"Scaling image by {scale:.4f} to fit {MACHINE['units']} paper.")
    

        all_paths = []
        
        
        print(f"Generating Stipple Pattern (Step: {SETTINGS['stipple_step']})...")
        all_paths = generate_stipple_path(image_data, scale, SETTINGS)
        print("Optimizing path for travel distance...")
        all_paths = sort_stipple_paths(all_paths)
        print(f"Total Dots to Plot: {len(all_paths)}")
        
        
        # --- NEW: RAW IMAGE PREVIEW ---
        # plt.figure(figsize=(6, 6))
        # plt.imshow(image_data, cmap='gray')
        # plt.title("Original Grayscale Input")
        # plt.axis('off')
        # plt.show()
        # # ------------------------------

        # 3. Preview (Always look before you plot!)
        visualize_paths(all_paths, h_px, w_px)


        # 4. Export G-code
        # Only generates if you want to proceed
        # confirm = input("Generate G-code? (y/n): ")
        # if confirm.lower() == 'y':
        #     generate_gcode(all_paths, "sine_wave_plot.nc")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()