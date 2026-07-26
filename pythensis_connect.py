import os
import time
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import numpy as np
import serial
import serial.tools.list_ports
from mss import mss


# THIS CODE IS 100% AI, as after a week of developing of Pythensis I was really tired.
# Credit Gemini

# --- CONSTANTS ---
TARGET_WIDTH = 128
TARGET_HEIGHT = 64
CLAHE_NIGHT = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))


# ==========================================
# 🛠️ ALGORITHMS & IMAGE PROCESSING
# ==========================================

def apply_floyd_steinberg(img_gray):
    """Applies Floyd-Steinberg dithering to grayscale image."""
    img = img_gray.astype(np.float32)
    h, w = img.shape
    for y in range(h):
        for x in range(w):
            old_pixel = img[y, x]
            new_pixel = 255.0 if old_pixel > 127.0 else 0.0
            img[y, x] = new_pixel
            error = old_pixel - new_pixel

            if x + 1 < w:
                img[y, x + 1] += error * (7 / 16)
            if y + 1 < h:
                if x > 0:
                    img[y + 1, x - 1] += error * (3 / 16)
                img[y + 1, x] += error * (5 / 16)
                if x + 1 < w:
                    img[y + 1, x + 1] += error * (1 / 16)

    return np.clip(img, 0, 255).astype(np.uint8)


def process_frame_auto_canny(gray_img, sigma=0.4):
    """Wireframe / Nightvision algorithm (Auto-Canny)."""
    enhanced = CLAHE_NIGHT.apply(gray_img)
    blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
    v = np.median(blurred)
    lower = int(max(0, (1.0 - sigma) * v))
    upper = int(min(255, (1.0 + sigma) * v))
    return cv2.Canny(blurred, lower, upper)


def process_frame_adaptive(gray_img):
    """Textured algorithm (Adaptive Thresholding)."""
    return cv2.adaptiveThreshold(
        gray_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )


def frame_to_oled_bytes_fast(bw_matrix):
    """Converts 128x64 matrix to OLED page stream."""
    bits = (bw_matrix > 0).astype(np.uint8)
    pages = bits.reshape(8, 8, 128)
    weights = np.array([1, 2, 4, 8, 16, 32, 64, 128], dtype=np.uint8).reshape(1, 8, 1)
    return np.sum(pages * weights, axis=1, dtype=np.uint8)


def resize_aspect_ratio(img, target_w=128, target_h=64, interp=cv2.INTER_LINEAR):
    """Resizes image preserving aspect ratio with letterboxing (black borders)."""
    h, w = img.shape[:2]
    scale = min(target_w / w, target_h / h)
    nw, nh = int(w * scale), int(h * scale)

    resized = cv2.resize(img, (nw, nh), interpolation=interp)
    canvas = np.zeros((target_h, target_w), dtype=np.uint8)

    top = (target_h - nh) // 2
    left = (target_w - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    return canvas


# ==========================================
# 🖥️ MAIN APPLICATION CLASS
# ==========================================

class PythensisConnectApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🐍 Pythensis CONNECT")
        self.root.geometry("680x640")
        self.root.resizable(False, False)

        # Threading & Streaming status
        self.is_streaming = False
        self.stream_thread = None
        self.ser = None

        self._build_ui()
        self.auto_detect_usb()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # --- SERIAL PORT CONNECTION FRAME ---
        conn_frame = ttk.LabelFrame(self.root, text=" 🔌 Serial Port Setup (UART) ")
        conn_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(conn_frame, text="Port:").pack(side="left", padx=5, pady=5)
        self.cb_ports = ttk.Combobox(conn_frame, width=15, state="readonly")
        self.cb_ports.pack(side="left", padx=5, pady=5)

        btn_refresh = ttk.Button(conn_frame, text="🔄 Auto-Detect", command=self.auto_detect_usb)
        btn_refresh.pack(side="left", padx=5, pady=5)

        ttk.Label(conn_frame, text="Baudrate:").pack(side="left", padx=5, pady=5)
        self.ent_baud = ttk.Entry(conn_frame, width=8)
        self.ent_baud.insert(0, "115200")
        self.ent_baud.pack(side="left", padx=5, pady=5)

        # --- TABS / NOTEBOOK ---
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # TAB 1: VIDEO STREAMER
        self.tab_video = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_video, text="🎬 Video Streamer")
        self._build_tab_video()

        # TAB 2: SCREEN STREAMER
        self.tab_screen = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_screen, text="🖥️ Screen Share")
        self._build_tab_screen()

        # TAB 3: CONSOLE
        self.tab_console = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_console, text="💻 Shell Console")
        self._build_tab_console()

        # TAB 4: MICROPYTHON DICTIONARY & WEB DOCS
        self.tab_dict = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_dict, text="📖 MicroPython Cheatsheet")
        self._build_tab_dictionary()

        # --- STATUS BAR & STOP BUTTON ---
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill="x", padx=10, pady=5)

        self.btn_stop = ttk.Button(status_frame, text="⏹ STOP Stream", command=self.stop_stream, state="disabled")
        self.btn_stop.pack(side="right", padx=5)

        self.lbl_status = ttk.Label(status_frame, text="Ready", font=("Helvetica", 10, "bold"), foreground="gray")
        self.lbl_status.pack(side="left", padx=5)

    def _build_tab_video(self):
        frame = ttk.LabelFrame(self.tab_video, text=" Video Stream Options ")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frame, text="Video File:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.ent_video_path = ttk.Entry(frame, width=42)
        self.ent_video_path.grid(row=0, column=1, padx=5, pady=5)
        btn_browse = ttk.Button(frame, text="Browse...", command=self.browse_video)
        btn_browse.grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(frame, text="Rendering Algorithm:").grid(row=1, column=0, sticky="w", padx=5, pady=10)
        self.var_dither = tk.BooleanVar(value=True)
        rb1 = ttk.Radiobutton(frame, text="Floyd-Steinberg Dithering (High Quality)", variable=self.var_dither,
                              value=True)
        rb2 = ttk.Radiobutton(frame, text="Simple Binary Threshold (Fast)", variable=self.var_dither, value=False)
        rb1.grid(row=1, column=1, sticky="w", padx=5)
        rb2.grid(row=2, column=1, sticky="w", padx=5)

        btn_start = ttk.Button(frame, text="▶ Start Video Stream", command=self.start_video_stream)
        btn_start.grid(row=3, column=1, pady=20, sticky="ew")

    def _build_tab_screen(self):
        frame = ttk.LabelFrame(self.tab_screen, text=" Screen Capture Options ")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Processing mode
        ttk.Label(frame, text="Processing Mode:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.var_screen_mode = tk.StringVar(value="wireframe")
        rb_wire = ttk.Radiobutton(frame, text="Wireframe / Nightvision (Auto-Canny - DOOM / Games)",
                                  variable=self.var_screen_mode, value="wireframe")
        rb_text = ttk.Radiobutton(frame, text="Textured Image (Adaptive Threshold - Desktop / Text)",
                                  variable=self.var_screen_mode, value="textured")
        rb_wire.grid(row=0, column=1, columnspan=2, sticky="w", padx=5, pady=2)
        rb_text.grid(row=1, column=1, columnspan=2, sticky="w", padx=5, pady=2)

        # Scaling Quality
        ttk.Label(frame, text="Quality / Scaling:").grid(row=2, column=0, sticky="w", padx=5, pady=10)
        self.var_quality = tk.StringVar(value="nearest")
        cb_qual = ttk.Combobox(frame, textvariable=self.var_quality, state="readonly", width=35)
        cb_qual['values'] = (
            "nearest - Sharp Pixel Art (DOOM / Retro)",
            "linear - Fast Smooth Scaling",
            "aspect - Correct Aspect Ratio (Letterbox)"
        )
        cb_qual.current(0)
        cb_qual.grid(row=2, column=1, columnspan=2, sticky="w", padx=5, pady=10)

        # Custom Resolution Override
        res_frame = ttk.LabelFrame(frame, text=" Optional Source Resolution (px) ")
        res_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=5, pady=10)

        ttk.Label(res_frame, text="Width:").pack(side="left", padx=5, pady=5)
        self.ent_res_w = ttk.Entry(res_frame, width=6)
        self.ent_res_w.pack(side="left", padx=5, pady=5)

        ttk.Label(res_frame, text="Height:").pack(side="left", padx=5, pady=5)
        self.ent_res_h = ttk.Entry(res_frame, width=6)
        self.ent_res_h.pack(side="left", padx=5, pady=5)

        ttk.Label(res_frame, text="(Leave empty for Auto)", font=("Helvetica", 8, "italic"), foreground="gray").pack(
            side="left", padx=10)

        # Monitor Index
        ttk.Label(frame, text="Monitor Index:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.ent_monitor = ttk.Entry(frame, width=5)
        self.ent_monitor.insert(0, "1")
        self.ent_monitor.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        btn_start = ttk.Button(frame, text="▶ Start Screen Stream", command=self.start_screen_stream)
        btn_start.grid(row=5, column=1, pady=15, sticky="ew")

    def _build_tab_console(self):
        frame = ttk.Frame(self.tab_console)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.txt_console = tk.Text(frame, height=14, state="disabled", bg="#1e1e1e", fg="#00ff00",
                                   font=("Consolas", 10))
        self.txt_console.pack(fill="both", expand=True, pady=5)

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill="x", pady=5)

        self.ent_cmd = ttk.Entry(input_frame)
        self.ent_cmd.pack(side="left", fill="x", expand=True, padx=5)
        self.ent_cmd.bind("<Return>", lambda event: self.send_command())

        btn_send = ttk.Button(input_frame, text="Send Command ↵", command=self.send_command)
        btn_send.pack(side="right", padx=5)

    def _build_tab_dictionary(self):
        frame = ttk.Frame(self.tab_dict)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        btn_open_docs = ttk.Button(
            frame,
            text="🌐 Open Official Python Editor & API Docs (python.microbit.org)",
            command=lambda: webbrowser.open("https://python.microbit.org/v/3/api")
        )
        btn_open_docs.pack(fill="x", pady=(0, 10))

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill="both", expand=True)

        txt_dict = tk.Text(text_frame, bg="#f8f9fa", fg="#1e1e1e", font=("Consolas", 9), wrap="word")
        scroll = ttk.Scrollbar(text_frame, command=txt_dict.yview)
        txt_dict.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y")
        txt_dict.pack(side="left", fill="both", expand=True)

        cheatsheet = (
            "📖 EXTENDED MICROPYTHON FOR MICRO:BIT DICTIONARY\n"
            "====================================================\n\n"
            "🔹 SYSTEM & MEMORY (RAM & Flash):\n"
            "  import gc              # Garbage Collector\n"
            "  gc.collect()           # Manually free up unused RAM memory\n"
            "  gc.mem_free()          # Returns available free bytes in RAM\n"
            "  import os              # Operating System / Filesystem interface\n"
            "  os.listdir()           # List all files stored on micro:bit\n"
            "  os.remove('file.py')   # Delete a specific file\n"
            "  os.size('file.py')     # Return size of file in bytes\n\n"

            "🔹 LED MATRIX DISPLAY:\n"
            "  from microbit import display, Image\n"
            "  display.show(Image.HAPPY) # Display built-in icon (HAPPY, HEART, PACMAN...)\n"
            "  display.scroll('TEXT') # Scroll text string across matrix\n"
            "  display.set_pixel(x,y,val) # Set brightness (0-9) of specific LED\n"
            "  display.clear()        # Clear matrix display\n"
            "  display.off()          # Disable LED matrix (saves RAM & power)\n\n"

            "🔹 BUTTONS & PINS:\n"
            "  from microbit import button_a, button_b, pin0\n"
            "  button_a.is_pressed()  # Returns True if Button A is currently held down\n"
            "  button_b.was_pressed() # Returns True if Button B was clicked\n"
            "  pin0.read_digital()    # Read binary signal (0 or 1) on Pin 0\n"
            "  pin0.write_analog(512) # Output PWM signal (0 to 1023)\n\n"

            "🔹 SENSORS & ACCELEROMETER:\n"
            "  from microbit import accelerometer, compass, temperature\n"
            "  accelerometer.get_x()  # Tilt X axis value (-2000 to +2000)\n"
            "  accelerometer.is_gesture('shake') # Detect 'shake', 'freefall', 'face up'\n"
            "  compass.calibrate()    # Calibrate onboard compass\n"
            "  compass.heading()      # Heading angle in degrees (0-360)\n"
            "  temperature()          # Microcontroller internal temperature in °C\n\n"

            "🔹 SOUND & MUSIC (v2 or external speaker):\n"
            "  import music\n"
            "  music.play(music.PYTHON) # Play built-in melody\n"
            "  music.pitch(440, 500)    # Play frequency (440Hz) for 500ms\n\n"

            "🔹 SERIAL / UART STREAMING (PC Connection):\n"
            "  from microbit import uart\n"
            "  uart.init(baudrate=115200) # Configure serial speed\n"
            "  uart.any()                 # Check if bytes are available in buffer\n"
            "  uart.read(1)               # Read 1 byte from UART\n"
            "  uart.write('O')            # Send ACK (acknowledge) byte to PC\n\n"

            "🔹 I2C PROTOCOL (OLED Displays, Sensors):\n"
            "  from microbit import i2c\n"
            "  i2c.init(freq=400000)      # Fast 400kHz I2C bus\n"
            "  i2c.scan()                 # Scan and return list of I2C addresses\n"
            "  i2c.write(0x3C, b'\\x00')   # Write bytes to device at address 0x3C\n"
        )
        txt_dict.insert(tk.END, cheatsheet)
        txt_dict.config(state="disabled")

    # ==========================================
    # ⚙️ LOGIC & USB AUTO-DETECTION
    # ==========================================

    def auto_detect_usb(self):
        ports = list(serial.tools.list_ports.comports())

        options = []
        target_port = None

        for p in ports:
            entry = f"{p.device}"
            options.append(entry)

            desc = p.description.lower()
            hwid = p.hwid.lower()

            is_usb = "usb" in hwid or "usb" in desc or "vid:pid" in hwid
            is_microbit = any(k in desc or k in hwid for k in ["micro:bit", "daplink", "mbed", "interface"])

            if is_usb and is_microbit:
                target_port = entry
                break
            elif is_usb and not target_port:
                target_port = entry

        self.cb_ports['values'] = options

        if target_port:
            self.cb_ports.set(target_port)
            self.lbl_status.config(text=f"Detected USB: {target_port.split()[0]}", foreground="green")
        elif options:
            self.cb_ports.set(options[0])
            self.lbl_status.config(text=f"Selected: {options[0].split()[0]}", foreground="black")
        else:
            self.cb_ports.set("No USB Port Found")
            self.lbl_status.config(text="No USB device found", foreground="red")

    def get_selected_port_code(self):
        val = self.cb_ports.get()
        if not val or "No" in val:
            return None
        return val.split()[0]

    def browse_video(self):
        filename = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.avi *.mkv *.mov"), ("All files", "*.*")])
        if filename:
            self.ent_video_path.delete(0, tk.END)
            self.ent_video_path.insert(0, filename)

    def log_console(self, text):
        self.txt_console.config(state="normal")
        self.txt_console.insert(tk.END, text + "\n")
        self.txt_console.see(tk.END)
        self.txt_console.config(state="disabled")

    def open_serial(self):
        port_code = self.get_selected_port_code()
        baud = self.ent_baud.get()

        if not port_code:
            messagebox.showerror("Error", "Please select a valid COM port!")
            return None

        try:
            ser = serial.Serial(port_code, int(baud), timeout=1.0)
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            time.sleep(1.5)
            return ser
        except Exception as e:
            messagebox.showerror("Port Error", f"Could not open {port_code}:\n{e}")
            return None

    def start_stream_common(self, worker_func):
        if self.is_streaming:
            return

        self.ser = self.open_serial()
        if not self.ser:
            return

        self.is_streaming = True
        self.btn_stop.config(state="normal")
        self.lbl_status.config(text="● STREAMING ACTIVE", foreground="green")

        self.stream_thread = threading.Thread(target=worker_func, daemon=True)
        self.stream_thread.start()

    def stop_stream(self):
        self.is_streaming = False
        self.lbl_status.config(text="Stopping...", foreground="orange")

    def cleanup_after_stream(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        cv2.destroyAllWindows()
        self.is_streaming = False
        self.btn_stop.config(state="disabled")
        self.lbl_status.config(text="Stopped / Ready", foreground="gray")

    # ==========================================
    # 🎥 WORKER: VIDEO STREAMING
    # ==========================================

    def start_video_stream(self):
        video_path = self.ent_video_path.get()
        if not os.path.exists(video_path):
            messagebox.showerror("Error", "Selected video file does not exist!")
            return

        self.start_stream_common(lambda: self._video_worker(video_path, self.var_dither.get()))

    def _video_worker(self, video_path, use_dithering):
        cap = cv2.VideoCapture(video_path)

        while self.is_streaming and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (TARGET_WIDTH, TARGET_HEIGHT), interpolation=cv2.INTER_AREA)

            bw = apply_floyd_steinberg(small) if use_dithering else cv2.threshold(small, 128, 255, cv2.THRESH_BINARY)[1]
            oled_pages = frame_to_oled_bytes_fast(bw)

            for page in range(8):
                if not self.is_streaming:
                    break
                self.ser.write(bytearray(oled_pages[page]))
                ack = self.ser.read(1)
                if ack != b'O':
                    self.ser.read_all()
                    break

            preview = cv2.resize(bw, (256, 128), interpolation=cv2.INTER_NEAREST)
            cv2.imshow("Pythensis CONNECT - Video Stream", preview)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        self.root.after(0, self.cleanup_after_stream)

    # ==========================================
    # 🖥️ WORKER: SCREEN STREAMING
    # ==========================================

    def start_screen_stream(self):
        mode = self.var_screen_mode.get()
        qual = self.var_quality.get()

        try:
            custom_w = int(self.ent_res_w.get()) if self.ent_res_w.get().strip() else None
            custom_h = int(self.ent_res_h.get()) if self.ent_res_h.get().strip() else None
        except ValueError:
            custom_w, custom_h = None, None

        try:
            mon_idx = int(self.ent_monitor.get())
        except ValueError:
            mon_idx = 1

        self.start_stream_common(lambda: self._screen_worker(mode, qual, custom_w, custom_h, mon_idx))

    def _screen_worker(self, mode, qual, custom_w, custom_h, mon_idx):
        with mss() as sct:
            while self.is_streaming:
                try:
                    mon = sct.monitors[mon_idx]
                except IndexError:
                    mon = sct.monitors[1]

                # Handshake custom dimensions vs Auto Monitor grab
                if custom_w and custom_h:
                    bbox = {"top": mon["top"], "left": mon["left"], "width": custom_w, "height": custom_h}
                else:
                    bbox = mon

                sct_img = sct.grab(bbox)
                frame = np.array(sct_img)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)

                # Scaling Logic
                if "nearest" in qual:
                    small = cv2.resize(gray, (TARGET_WIDTH, TARGET_HEIGHT), interpolation=cv2.INTER_NEAREST)
                elif "aspect" in qual:
                    small = resize_aspect_ratio(gray, TARGET_WIDTH, TARGET_HEIGHT, interpolation=cv2.INTER_AREA)
                else:
                    small = cv2.resize(gray, (TARGET_WIDTH, TARGET_HEIGHT), interpolation=cv2.INTER_LINEAR)

                bw = process_frame_auto_canny(small) if mode == "wireframe" else process_frame_adaptive(small)
                oled_pages = frame_to_oled_bytes_fast(bw)

                for page in range(8):
                    if not self.is_streaming:
                        break
                    self.ser.write(bytearray(oled_pages[page]))
                    ack = self.ser.read(1)
                    if ack != b'O':
                        self.ser.read_all()
                        break

                preview = cv2.resize(bw, (256, 128), interpolation=cv2.INTER_NEAREST)
                cv2.imshow("Pythensis CONNECT - Screen Stream", preview)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        self.root.after(0, self.cleanup_after_stream)

    # ==========================================
    # 💻 CONSOLE COMMANDS
    # ==========================================

    def send_command(self):
        cmd = self.ent_cmd.get().strip()
        if not cmd:
            return

        if self.is_streaming:
            messagebox.showwarning("Warning",
                                   "Cannot send console commands during active stream. Please stop stream first!")
            return

        ser = self.open_serial()
        if ser:
            try:
                ser.write((cmd + "\r\n").encode("utf-8"))
                self.log_console(f">>> {cmd}")
                self.ent_cmd.delete(0, tk.END)

                time.sleep(0.2)
                response = ser.read_all().decode("utf-8", errors="ignore")
                if response:
                    self.log_console(response)
            except Exception as e:
                self.log_console(f"[Command Error]: {e}")
            finally:
                ser.close()


if __name__ == "__main__":
    root = tk.Tk()
    app = PythensisConnectApp(root)
    root.mainloop()