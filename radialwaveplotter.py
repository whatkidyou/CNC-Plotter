

"""
Project: CNC Plotter Image Processor
Description: Converts images to G-code using sine wave amplitude modulation.
Author: ryan
Date: 2026-03-04
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

def calculate_wave_point(x, y_base, brightness, cfg):
    """
    The Core Algorithm. 
    Modify this function to change the 'art style'.
    """
    intensity = (255 - brightness) / 255.0  # Invert: Darker = Higher intensity
    offset = (intensity * cfg['amplitude']) * np.sin(x * cfg['frequency'])
    return y_base + offset

def generate_spiral_path(image_data, scale, cfg):
    h, w = image_data.shape
    center_x, center_y = w // 2, h // 2
    max_radius = min(center_x, center_y)
    
    path = []
    theta = 0
    distance_traveled = 0.0  # Tracks linear distance along the path
    last_pos_px = None
    
    growth_rate = cfg.get("spiral_density", 0.5)
    
    # Lower value = higher precision, but we increment theta dynamically
    # to keep the spacing consistent
    while True:
        r_base = theta * growth_rate
        if r_base > max_radius:
            break
            
        # 1. Current position in pixels (without the wobble)
        px_x = center_x + r_base * np.cos(theta)
        px_y = center_y + r_base * np.sin(theta)
        
        # 2. Update distance traveled
        if last_pos_px is not None:
            # Distance formula between last point and current base point
            step_dist = np.sqrt((px_x - last_pos_px[0])**2 + (px_y - last_pos_px[1])**2)
            distance_traveled += step_dist
            
        last_pos_px = (px_x, px_y)

        # 3. Apply Wiggle based on distance_traveled (not theta!)
        if 0 <= int(px_x) < w and 0 <= int(px_y) < h:
            brightness = image_data[int(px_y), int(px_x)]
            intensity = (255 - brightness) / 255.0
            
            # Now the frequency is 'waves per pixel'
            wobble = (intensity * cfg['amplitude']) * np.sin(distance_traveled * cfg['frequency'])
            r_final = r_base + wobble
            
            # Convert to MM for plotter
            x_mm = ((center_x + r_final * np.cos(theta)) * scale) + MACHINE["margin_mm"]
            y_mm = ((center_y + r_final * np.sin(theta)) * scale) + MACHINE["margin_mm"]
            
            path.append((x_mm, y_mm))
        
        # --- DYNAMIC THETA STEP ---
        # As the radius (r_base) gets larger, we need smaller theta steps
        # to maintain the same resolution along the path.
        # This keeps the 'point density' consistent.
        if r_base > 0:
            theta += 0.5 / r_base # Adjust 0.5 to control point density
        else:
            theta += 0.1
            
    return [path]


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
        # 1. Load data
        # Replace with your actual image filename
        image_data = load_and_preprocess("echo square.PNG")
        # Rescale the image so the darkest pixel is 0 and the brightest is 255
        image_data = ((image_data - image_data.min()) * (255 / (image_data.max() - image_data.min()))).astype(np.uint8)
        # Raise to a power (e.g., 1.5) to make shadows deeper
        # Normalize to 0.0-1.0 first, then push back to 0-255
        image_data = (np.power(image_data / 255.0, 1.5) * 255).astype(np.uint8)
        
        h_px, w_px = image_data.shape
        scale = get_scaling_factor(w_px, h_px)
        print(f"Scaling image by {scale:.4f} to fit {MACHINE['units']} paper.")
    

        all_paths = []
        if SETTINGS["mode"] == "spiral":
            
            #center crop: make the image a circle since we're doing a spiral
            side = min(h_px, w_px)
            start_h = (h_px - side) // 2
            start_w = (w_px - side) // 2
            image_data = image_data[start_h:start_h+side, start_w:start_w+side]
            h_px, w_px = image_data.shape # Update dimensions
            
            
            print("Processing Outward Spiral...")
            # The function returns a list containing one long path
            all_paths = generate_spiral_path(image_data, scale, SETTINGS)
            
        else:
            print("Processing Horizontal Lines...")
            for y_px in tqdm(range(0, h_px, SETTINGS['line_spacing']), desc="Lines"):
                current_path = []
                for x_px in range(0, w_px, 2):
                    brightness = image_data[y_px, x_px]
                    y_wave_px = calculate_wave_point(x_px, y_px, brightness, SETTINGS)
                    
                    x_mm = (x_px * scale) + MACHINE["margin_mm"]
                    y_mm = (y_wave_px * scale) + MACHINE["margin_mm"]
                    current_path.append((x_mm, y_mm))
                all_paths.append(current_path)
        
        
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
        confirm = input("Generate G-code? (y/n): ")
        if confirm.lower() == 'y':
            generate_gcode(all_paths, "sine_wave_plot.nc")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()