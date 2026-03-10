# CNC Smith Chart Pen Plotter 🖊️📈

A Python-based toolchain to convert SVG Smith Charts into G-code optimized for a custom 4-foot CNC plotter using a servo-based pen actuator.

## 🚀 Features
* **Adaptive Path Resolution:** High-point density for small text/curves, low-density for long grid lines.
* **KDTree Path Optimization:** Minimizes travel time by solving a "Nearest Neighbor" path sequence.
* **Memory Efficient:** Streams G-code directly to disk to handle complex vector files without maxing out RAM.
* **Servo Integration:** Uses `M3/M5` commands with configurable delays for an MG90S servo actuator.

## 🛠️ Hardware Configuration
* **Machine Bed:** 1200mm x 1200mm (4ft)
* **Default Paper:** 215mm x 297mm (Letter/A4)
* **Pen Actuator:** MG90S Servo
  * **Pen Down:** `M3 S51`
  * **Pen Up:** `M5 S125`
  * **Lift Delay:** 0.2s (`G4 P0.2`)



## 💻 Software Setup
1. **Clone the repo:**
   ```bash
   git clone [https://github.com/YOUR_USERNAME/YOUR_REPO.git](https://github.com/YOUR_USERNAME/YOUR_REPO.git)


2. **install dependencies:**
   ```bash
   pip install numpy matplotlib svgpathtools tqdm scipy

## 📖 Usage
1. **Place your image in the input_images folder**
2. **Adjust 'CONFIG' in 'main.py' for your current paper size and target width.**
3. **Run the script:**
   ```bash
   python main.py
4. **Verify the output using the 'gcode_visualizer.py' script before sending it to the plotter.**