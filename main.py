import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pymem
import pymem.process
import struct
import threading
import time
import json
import os
import sys
import ctypes
from datetime import datetime, timedelta

class LoadlessTimer:
    """Accurate loadless timer for speedrunning"""
    def __init__(self):
        self.running_time = timedelta()
        self.loading_time = timedelta()
        self.is_loading = False
        self.timer_running = False
        self.last_update = None
        self.split_times = []
        self._lock = threading.Lock()  # Thread safety
        
    def start(self):
        with self._lock:
            self.timer_running = True
            self.last_update = datetime.now()
            self.running_time = timedelta()
            self.loading_time = timedelta()
            self.split_times = []
        
    def stop(self):
        with self._lock:
            self.timer_running = False
            self.last_update = None  # Reset last update time
        
    def update(self, is_loading, has_control):
        if not self.timer_running:
            return
            
        now = datetime.now()
        with self._lock:
            if self.last_update:
                try:
                    delta = now - self.last_update
                    
                    # Sanity check for negative time or extremely large deltas
                    if delta.total_seconds() < 0 or delta.total_seconds() > 1.0:
                        self.last_update = now
                        return
                    
                    if is_loading or not has_control:
                        self.loading_time += delta
                        self.is_loading = True
                    else:
                        self.running_time += delta
                        self.is_loading = False
                except Exception as e:
                    print(f"Timer update error: {e}")
                    
            self.last_update = now
        
    def split(self, checkpoint_name):
        if self.timer_running:
            self.split_times.append({
                'name': checkpoint_name,
                'time': str(self.running_time),
                'timestamp': datetime.now()
            })
            
    def get_time_str(self):
        total_seconds = self.running_time.total_seconds()
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int((total_seconds * 1000) % 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
        
    def export_splits(self, filename):
        with open(filename, 'w') as f:
            json.dump({
                'running_time': str(self.running_time),
                'loading_time': str(self.loading_time),
                'splits': self.split_times
            }, f, indent=2)

class VehicleCustomizer:
    """Interface for easy vehicle customization"""
    def __init__(self, parent, pm, base_address):
        self.window = tk.Toplevel(parent)
        self.window.title("Vehicle Customizer")
        self.window.geometry("700x600")
        
        # Validate parameters
        if not pm or not base_address:
            messagebox.showerror("Error", "Invalid game process or memory address")
            self.window.destroy()
            return
            
        self.pm = pm
        self.base = base_address
        self._lock = threading.Lock()  # Thread safety for memory operations
        
        # Set up window close handler
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Vehicle database
        self.vehicles = {
            'Porsche 911 GT3 RS 4.0': '0xA998E13D',
            'Nissan GT-R R35': '0xCE5A5DEB',
            'Lamborghini Gallardo': '0xFB1C95C1',
            'BMW M3 GTS': '0x2012C92C',
            'Ford Mustang Boss 302': '0xDE2611F3',
            'Chevrolet Camaro SS': '0x9121385E',
            'Audi R8': '0xCED5A7B6',
        }
        
        self.bodykits = {
            'Stock': 0x00,
            'Time Attack': 0x01,
            'Aero Pack': 0x02,
            'Circuit Racer': 0x03,
        }
        
        self.spoilers = {
            'Stock': '0xC2FB407D',
            'Evo X Time Attack': '0x6AB96D26',
            'GT3RS RSR Replica': '0x29671D94',
        }
        
        self.paints = {
            'Metallic Blue': '0x257F2512',
            'Matte Black': '0x4E9BBE75',
            'Glossy White': '0xC494BC78',
            'Carbon Fiber': '0x1780E1',
        }
        
        self.setup_ui()
        
    def setup_ui(self):
        notebook = ttk.Notebook(self.window)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Vehicle Selection Tab
        vehicle_frame = ttk.Frame(notebook)
        notebook.add(vehicle_frame, text='Vehicle')
        
        ttk.Label(vehicle_frame, text="Select Vehicle:", font=('Arial', 10, 'bold')).pack(pady=10)
        self.vehicle_var = tk.StringVar()
        vehicle_menu = ttk.Combobox(vehicle_frame, textvariable=self.vehicle_var, 
                                     values=list(self.vehicles.keys()), state='readonly', width=30)
        vehicle_menu.pack(pady=5)
        vehicle_menu.current(0)
        
        ttk.Button(vehicle_frame, text="Apply Vehicle", 
                   command=self.apply_vehicle).pack(pady=10)
        
        # Bodykit Tab
        bodykit_frame = ttk.Frame(notebook)
        notebook.add(bodykit_frame, text='Bodykit')
        
        ttk.Label(bodykit_frame, text="Bodykit:", font=('Arial', 10, 'bold')).pack(pady=10)
        self.bodykit_var = tk.StringVar()
        for name in self.bodykits.keys():
            ttk.Radiobutton(bodykit_frame, text=name, variable=self.bodykit_var, 
                           value=name).pack(anchor='w', padx=20)
        self.bodykit_var.set('Stock')
        
        ttk.Button(bodykit_frame, text="Apply Bodykit", 
                   command=self.apply_bodykit).pack(pady=10)
        
        # Paint Tab
        paint_frame = ttk.Frame(notebook)
        notebook.add(paint_frame, text='Paint')
        
        ttk.Label(paint_frame, text="Paint Color:", font=('Arial', 10, 'bold')).pack(pady=10)
        self.paint_var = tk.StringVar()
        paint_menu = ttk.Combobox(paint_frame, textvariable=self.paint_var,
                                   values=list(self.paints.keys()), state='readonly', width=30)
        paint_menu.pack(pady=5)
        paint_menu.current(0)
        
        ttk.Button(paint_frame, text="Apply Paint", 
                   command=self.apply_paint).pack(pady=10)
        
        # Performance Tab
        perf_frame = ttk.Frame(notebook)
        notebook.add(perf_frame, text='Performance')
        
        ttk.Label(perf_frame, text="Performance Level:", font=('Arial', 10, 'bold')).pack(pady=10)
        self.perf_var = tk.IntVar(value=5)
        ttk.Scale(perf_frame, from_=1, to=6, orient='horizontal', 
                 variable=self.perf_var, length=300).pack(pady=5)
        ttk.Label(perf_frame, textvariable=self.perf_var).pack()
        
        ttk.Button(perf_frame, text="Apply Performance", 
                   command=self.apply_performance).pack(pady=10)
        
        # Preset Manager
        preset_frame = ttk.LabelFrame(self.window, text="Preset Manager", padding=10)
        preset_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(preset_frame, text="Save Preset", 
                   command=self.save_preset).pack(side='left', padx=5)
        ttk.Button(preset_frame, text="Load Preset", 
                   command=self.load_preset).pack(side='left', padx=5)
        
    def safe_memory_write(self, offset, buffer, size):
        """Thread-safe memory write with error handling"""
        with self._lock:
            try:
                addr = self.base + offset
                return self.pm.write_bytes(addr, buffer, size)
            except Exception as e:
                print(f"Memory write error at {hex(offset)}: {e}")
                return False
                
    def on_closing(self):
        """Clean up resources when window is closed"""
        try:
            # Reset any active modifications if needed
            pass
        finally:
            self.window.destroy()
            
    def apply_vehicle(self):
        try:
            vehicle_hash = int(self.vehicles[self.vehicle_var.get()], 16)
            if self.safe_memory_write(0x1391D40, vehicle_hash.to_bytes(4, 'little'), 4):
                messagebox.showinfo("Success", f"Applied: {self.vehicle_var.get()}")
            else:
                messagebox.showerror("Error", "Failed to apply vehicle change")
        except Exception as e:
            messagebox.showerror("Error", f"Vehicle application error: {e}")
        
    def apply_bodykit(self):
        try:
            bodykit_id = self.bodykits[self.bodykit_var.get()]
            if self.safe_memory_write(0x1391E20, bodykit_id.to_bytes(1, 'little'), 1):
                messagebox.showinfo("Success", f"Applied bodykit: {self.bodykit_var.get()}")
            else:
                messagebox.showerror("Error", "Failed to apply bodykit")
        except Exception as e:
            messagebox.showerror("Error", f"Bodykit application error: {e}")
        
    def apply_paint(self):
        try:
            paint_hash = int(self.paints[self.paint_var.get()], 16)
            if self.safe_memory_write(0x1391E40, paint_hash.to_bytes(4, 'little'), 4):
                messagebox.showinfo("Success", f"Applied paint: {self.paint_var.get()}")
            else:
                messagebox.showerror("Error", "Failed to apply paint")
        except Exception as e:
            messagebox.showerror("Error", f"Paint application error: {e}")
        
    def apply_performance(self):
        try:
            perf_level = self.perf_var.get()
            if 1 <= perf_level <= 6 and self.safe_memory_write(0x1391E60, perf_level.to_bytes(1, 'little'), 1):
                messagebox.showinfo("Success", f"Set performance to Tier {perf_level}")
            else:
                messagebox.showerror("Error", "Failed to apply performance level")
        except Exception as e:
            messagebox.showerror("Error", f"Performance application error: {e}")
        
    def save_preset(self):
        preset = {
            'vehicle': self.vehicle_var.get(),
            'bodykit': self.bodykit_var.get(),
            'paint': self.paint_var.get(),
            'performance': self.perf_var.get()
        }
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")]
        )
        if filename:
            with open(filename, 'w') as f:
                json.dump(preset, f, indent=2)
            messagebox.showinfo("Success", "Preset saved!")
            
    def load_preset(self):
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")]
        )
        if filename:
            with open(filename, 'r') as f:
                preset = json.load(f)
            self.vehicle_var.set(preset.get('vehicle', ''))
            self.bodykit_var.set(preset.get('bodykit', 'Stock'))
            self.paint_var.set(preset.get('paint', ''))
            self.perf_var.set(preset.get('performance', 5))
            messagebox.showinfo("Success", "Preset loaded!")

class NFSModSuite:
    def __init__(self, root):
        self.root = root
        self.root.title("NFS The Run - Advanced Mod Suite v2.0")
        self.root.geometry("800x900")
        self.root.resizable(False, False)
        
        # Initialize core components
        self.pm = None
        self.base_address = None
        self.connected = False
        self.timer = LoadlessTimer()
        self.monitor_thread = None
        self.monitoring = False
        self._lock = threading.Lock()
        
        # Set up shutdown handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Add error handler for unhandled exceptions
        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            print("Uncaught exception:", exc_type, exc_value)
            messagebox.showerror("Error", f"An error occurred: {str(exc_value)}")
        
        sys.excepthook = handle_exception
        
        # Register cleanup on interpreter shutdown
        import atexit
        atexit.register(self.cleanup_resources)
        
        # Complete offsets
        self.offsets = {
            # Core
            'world_speed': 0x11359,
            'game_time_max_fps': 0xA607F7,
            'menu_fps_limit': 0xA607DF,  # Menu FPS limiter
            'loading_fps_limit': 0xA607E7,  # Loading screen FPS limiter
            'framerate_unlocker': [0x4106F8, 0x4106FF, 0x410706, 0x41070B, 0x410710, 0x410717, 0x41076F],
            'loading_vsync': [
                {'offset': 0x410706, 'original': b'\xE9\x8B\x01\x00\x00', 'nop': b'\x90\x90\x90\x90\x90'},
                {'offset': 0x41070B, 'original': b'\xE9\x86\x01\x00\x00', 'nop': b'\x90\x90\x90\x90\x90'},
                {'offset': 0x410715, 'original': b'\xE9\x81\x01\x00\x00', 'nop': b'\x90\x90\x90\x90\x90'}
            ],
            
            # Timer & Control
            'player_has_control': 0x3F6C73,
            'checkpoint_timer_1': 0x8FBF06,
            'checkpoint_timer_2': 0x13DB998,
            
            # Vehicle
            'vehicle_coords': 0x1391D22,
            'vehicle_damage': [0xBDF4B0, 0xBDF4C0, 0xBDF4D0],  # Multiple damage offsets
            'nos_amount': [0x1391E80, 0x1391E88],  # NOS tank and consumption rate
            'nos_active': 0x1391E90,  # NOS activation state
            'disable_assists': [0x1819981, 0x18199A6, 0x1819AB1, 0x181AA64, 0x1828E73, 0x69B167, 0x69B5E2],
            
            # Visual
            'headlights': [0xF8E41B, 0xF8B149, 0xF8E42C, 0xF8AA6D, 0xF86BB4],
            'tod_career': 0x59BF25,
            'world_render_light': 0x1E3B13B,
            'light_exposure': 0x1F620B8,
            'sun_rotation_x': 0x1F620B0,
            'sun_rotation_y': 0x1F620A8,
            
            # Traffic
            'traffic_density': 0xE5EEF6,
            
            # Crash fixes
            'tunnel_pain': 0x121D23B,
            'chicago_crash': [0xE4EB60, 0xE50F0E],
        }
        
        self.setup_ui()
        self.check_game_connection()
        
    def setup_ui(self):
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Connection Status (always visible)
        status_frame = ttk.LabelFrame(self.root, text="Status", padding=5)
        status_frame.pack(fill="x", padx=5, pady=5, before=notebook)
        
        self.status_label = ttk.Label(status_frame, text="Not Connected", foreground="red")
        self.status_label.pack(side="left", padx=10)
        ttk.Button(status_frame, text="Reconnect", command=self.check_game_connection).pack(side="left")
        
        # Tab 1: Performance & Graphics
        perf_tab = ttk.Frame(notebook)
        notebook.add(perf_tab, text='Performance')
        self.setup_performance_tab(perf_tab)
        
        # Tab 2: Speedrun Tools
        speedrun_tab = ttk.Frame(notebook)
        notebook.add(speedrun_tab, text='Speedrun Tools')
        self.setup_speedrun_tab(speedrun_tab)
        
        # Tab 3: Vehicle Mods
        vehicle_tab = ttk.Frame(notebook)
        notebook.add(vehicle_tab, text='Vehicle Mods')
        self.setup_vehicle_tab(vehicle_tab)
        
        # Tab 4: Visual Enhancements
        visual_tab = ttk.Frame(notebook)
        notebook.add(visual_tab, text='Visual Enhancements')
        self.setup_visual_tab(visual_tab)
        
        # Tab 5: Game Tweaks
        tweaks_tab = ttk.Frame(notebook)
        notebook.add(tweaks_tab, text='Game Tweaks')
        self.setup_tweaks_tab(tweaks_tab)
        
    def setup_performance_tab(self, parent):
        # FPS Unlocker
        fps_frame = ttk.LabelFrame(parent, text="Framerate Control", padding=10)
        fps_frame.pack(fill='x', padx=10, pady=5)
        
        self.unlock_fps = tk.BooleanVar(value=False)
        ttk.Checkbutton(fps_frame, text="Unlock Framerate (Story Mode & Gameplay)", 
                       variable=self.unlock_fps, command=self.toggle_framerate).pack(anchor='w')
        
        self.unlock_cutscene_fps = tk.BooleanVar(value=False)
        ttk.Checkbutton(fps_frame, text="Unlock Cutscene Framerate (Experimental)", 
                       variable=self.unlock_cutscene_fps, command=self.toggle_cutscene_fps).pack(anchor='w')
        
        ttk.Separator(fps_frame, orient='horizontal').pack(fill='x', pady=5)
        
        ttk.Label(fps_frame, text="Menu Smoothness (MaxSimFps):").pack(anchor='w')
        self.menu_fps = tk.DoubleVar(value=60.0)  # Use DoubleVar for more precise control
        
        # Create a frame for the FPS controls
        fps_control_frame = ttk.Frame(fps_frame)
        fps_control_frame.pack(fill='x', padx=5)
        
        # Add manual entry for precise values
        fps_entry = ttk.Entry(fps_control_frame, width=6, 
                            textvariable=self.menu_fps)
        fps_entry.pack(side='right', padx=5)
        
        # Add slider with more conservative limits
        menu_scale = ttk.Scale(fps_frame, from_=30, to=60, orient='horizontal',
                              variable=self.menu_fps)
        menu_scale.pack(fill='x', padx=5)
        
        # Add warning label
        self.menu_fps_label = ttk.Label(fps_frame, text="60 Hz")
        self.menu_fps_label.pack()
        
        warning_label = ttk.Label(fps_frame, 
            text="⚠️ Default is 60Hz - Change with caution",
            foreground='red')
        warning_label.pack()
        
        # Create a frame for precise control
        precise_frame = ttk.Frame(fps_frame)
        precise_frame.pack(fill='x', padx=5, pady=5)
        
        # Add spinbox for precise FPS control
        ttk.Label(precise_frame, text="Precise FPS:").pack(side='left', padx=5)
        self.precise_fps = ttk.Spinbox(precise_frame, 
                                     from_=30, to=60,
                                     increment=1,
                                     width=5,
                                     command=self.validate_precise_fps)
        self.precise_fps.set("60")
        self.precise_fps.pack(side='left', padx=5)
        
        # Add apply button with safety check
        apply_frame = ttk.Frame(fps_frame)
        apply_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(apply_frame, text="Test FPS Change", 
                  command=self.test_menu_fps).pack(side='left', padx=5)
        
        self.apply_fps_btn = ttk.Button(apply_frame, text="Apply FPS Change", 
                  command=self.apply_menu_fps_change,
                  state='disabled')
        self.apply_fps_btn.pack(side='left', padx=5)
        
        # Bind validation to the entry
        def validate_fps_entry(*args):
            try:
                value = float(self.menu_fps.get())
                if value < 30:
                    self.menu_fps.set(30)
                elif value > 120:
                    self.menu_fps.set(120)
                self.menu_fps_label.config(text=f"{int(self.menu_fps.get())} Hz")
            except ValueError:
                self.menu_fps.set(60)
            
        self.menu_fps.trace('w', validate_fps_entry)
        
        # Loading Speed Boost
        loading_frame = ttk.LabelFrame(parent, text="Loading Speed Enhancement", padding=10)
        loading_frame.pack(fill='x', padx=10, pady=5)
        
        self.disable_loading_vsync = tk.BooleanVar(value=False)
        ttk.Checkbutton(loading_frame, text="Disable V-Sync During Loading (Faster Loading)", 
                       variable=self.disable_loading_vsync, 
                       command=self.toggle_loading_vsync).pack(anchor='w')
        
        ttk.Label(loading_frame, text="⚠️ Higher FPS = Faster loading times", 
                 foreground='blue').pack(anchor='w', pady=5)
        
        # Graphics Enhancements
        graphics_frame = ttk.LabelFrame(parent, text="Graphics Enhancements", padding=10)
        graphics_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(graphics_frame, text="Launch RenderDoc Integration", 
                  command=self.launch_renderdoc).pack(fill='x', pady=5)
        
        self.enhanced_motion_blur = tk.BooleanVar(value=False)
        ttk.Checkbutton(graphics_frame, text="Enhanced Motion Blur Quality", 
                       variable=self.enhanced_motion_blur).pack(anchor='w')
        
        self.enhanced_shadows = tk.BooleanVar(value=False)
        ttk.Checkbutton(graphics_frame, text="Higher Quality Shadows", 
                       variable=self.enhanced_shadows).pack(anchor='w')
        
        self.enhanced_reflections = tk.BooleanVar(value=False)
        ttk.Checkbutton(graphics_frame, text="Enhanced Reflections", 
                       variable=self.enhanced_reflections).pack(anchor='w')
        
        ttk.Button(graphics_frame, text="Apply Graphics Settings", 
                  command=self.apply_graphics).pack(fill='x', pady=5)
        
    def setup_speedrun_tab(self, parent):
        # Loadless Timer
        timer_frame = ttk.LabelFrame(parent, text="Loadless Timer", padding=10)
        timer_frame.pack(fill='x', padx=10, pady=5)
        
        self.timer_display = ttk.Label(timer_frame, text="00:00:00.000", 
                                       font=('Courier', 24, 'bold'))
        self.timer_display.pack(pady=10)
        
        timer_controls = ttk.Frame(timer_frame)
        timer_controls.pack()
        
        ttk.Button(timer_controls, text="Start", 
                  command=self.start_timer, width=12).pack(side='left', padx=5)
        ttk.Button(timer_controls, text="Split", 
                  command=self.split_timer, width=12).pack(side='left', padx=5)
        ttk.Button(timer_controls, text="Stop", 
                  command=self.stop_timer, width=12).pack(side='left', padx=5)
        ttk.Button(timer_controls, text="Reset", 
                  command=self.reset_timer, width=12).pack(side='left', padx=5)
        
        # Timer Info
        info_frame = ttk.Frame(timer_frame)
        info_frame.pack(fill='x', pady=10)
        
        self.loading_time_label = ttk.Label(info_frame, text="Loading Time: 00:00:00.000")
        self.loading_time_label.pack()
        
        self.is_loading_label = ttk.Label(info_frame, text="Status: Not Loading", 
                                          foreground='green')
        self.is_loading_label.pack()
        
        # Splits Display
        splits_frame = ttk.LabelFrame(parent, text="Splits", padding=10)
        splits_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.splits_text = tk.Text(splits_frame, height=10, width=60)
        self.splits_text.pack(fill='both', expand=True)
        
        # Export
        export_frame = ttk.Frame(parent)
        export_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(export_frame, text="Export Splits to JSON", 
                  command=self.export_splits).pack(side='left', padx=5)
        ttk.Button(export_frame, text="Copy Time to Clipboard", 
                  command=self.copy_time).pack(side='left', padx=5)
        
        # Auto-split Configuration
        autosplit_frame = ttk.LabelFrame(parent, text="Auto-Split Configuration", padding=10)
        autosplit_frame.pack(fill='x', padx=10, pady=5)
        
        self.auto_split_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(autosplit_frame, text="Enable Auto-Split on Checkpoints", 
                       variable=self.auto_split_enabled).pack(anchor='w')
        
    def setup_vehicle_tab(self, parent):
        # Quick Vehicle Mods
        quick_frame = ttk.LabelFrame(parent, text="Quick Vehicle Modifications", padding=10)
        quick_frame.pack(fill='x', padx=10, pady=5)
        
        self.disable_assists = tk.BooleanVar(value=False)
        ttk.Checkbutton(quick_frame, text="Disable All Vehicle Assists", 
                       variable=self.disable_assists, command=self.toggle_assists).pack(anchor='w')
        
        self.infinite_nos = tk.BooleanVar(value=False)
        ttk.Checkbutton(quick_frame, text="Infinite NOS", 
                       variable=self.infinite_nos, 
                       command=self.toggle_infinite_nos).pack(anchor='w')
        
        self.no_damage = tk.BooleanVar(value=False)
        ttk.Checkbutton(quick_frame, text="No Vehicle Damage", 
                       variable=self.no_damage,
                       command=self.toggle_no_damage).pack(anchor='w')
        
        # Vehicle Customizer
        custom_frame = ttk.LabelFrame(parent, text="Vehicle Customization Interface", padding=10)
        custom_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(custom_frame, text="Easy vehicle customization with presets").pack()
        ttk.Button(custom_frame, text="Open Vehicle Customizer", 
                  command=self.open_customizer, width=30).pack(pady=10)
        
    def setup_visual_tab(self, parent):
        # Lighting
        lighting_frame = ttk.LabelFrame(parent, text="Lighting & Time of Day", padding=10)
        lighting_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(lighting_frame, text="World Render Light Intensity:").pack(anchor='w')
        self.light_intensity = tk.DoubleVar(value=1.0)
        ttk.Scale(lighting_frame, from_=0.0, to=3.0, orient='horizontal',
                 variable=self.light_intensity, command=self.update_lighting).pack(fill='x')
        
        ttk.Label(lighting_frame, text="Sun Position X:").pack(anchor='w')
        self.sun_x = tk.DoubleVar(value=0.0)
        ttk.Scale(lighting_frame, from_=-180, to=180, orient='horizontal',
                 variable=self.sun_x, command=self.update_sun).pack(fill='x')
        
        ttk.Label(lighting_frame, text="Sun Position Y:").pack(anchor='w')
        self.sun_y = tk.DoubleVar(value=0.0)
        ttk.Scale(lighting_frame, from_=-180, to=180, orient='horizontal',
                 variable=self.sun_y, command=self.update_sun).pack(fill='x')
        
        # Effects
        effects_frame = ttk.LabelFrame(parent, text="Visual Effects", padding=10)
        effects_frame.pack(fill='x', padx=10, pady=5)
        
        self.headlights = tk.BooleanVar(value=False)
        ttk.Checkbutton(effects_frame, text="Force Headlights On", 
                       variable=self.headlights, command=self.toggle_headlights).pack(anchor='w')
        
    def setup_tweaks_tab(self, parent):
        # Game Unlocks
        unlocks_frame = ttk.LabelFrame(parent, text="Unlocks", padding=10)
        unlocks_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(unlocks_frame, text="Unlock All Vehicles", 
                  command=self.unlock_vehicles).pack(fill='x', pady=2)
        ttk.Button(unlocks_frame, text="Unlock All Challenges", 
                  command=self.unlock_challenges).pack(fill='x', pady=2)
        
        # Fixes
        fixes_frame = ttk.LabelFrame(parent, text="Stability Fixes", padding=10)
        fixes_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(fixes_frame, text="Apply All Crash Bypasses", 
                  command=self.apply_crash_fixes).pack(fill='x', pady=2)
        ttk.Button(fixes_frame, text="Disable Reset Triggers", 
                  command=self.disable_resets).pack(fill='x', pady=2)
        
    def check_game_connection(self):
        try:
            # Check if we're already connected
            if self.connected and self.pm and pymem.process.is_process_running(self.pm.process_id):
                return
                
            # Try to connect to the game process
            self.pm = pymem.Pymem("Need for Speed The Run.exe")
            
            # Verify the process is valid
            if not self.pm or not self.pm.process_handle:
                raise Exception("Invalid process handle")
                
            # Get base address with retry
            retries = 3
            while retries > 0:
                try:
                    module = pymem.process.module_from_name(
                        self.pm.process_handle, "Need for Speed The Run.exe")
                    if module:
                        self.base_address = module.lpBaseOfDll
                        break
                except Exception:
                    retries -= 1
                    time.sleep(0.5)
                    
            if not self.base_address:
                raise Exception("Could not get base address")
                
            # Test a memory read
            test_addr = self.base_address + self.offsets['player_has_control']
            if not self.safe_read_memory(test_addr, 1):
                raise Exception("Memory read test failed")
                
            self.connected = True
            self.status_label.config(text="✓ Connected", foreground="green")
            self.start_monitoring()
            
        except Exception as e:
            self.connected = False
            self.status_label.config(text=f"✗ Not Connected: {str(e)}", foreground="red")
            if hasattr(self, 'pm') and self.pm:
                try:
                    self.pm.close_process()
                except:
                    pass
            self.pm = None
            self.base_address = None
            
    def start_monitoring(self):
        """Start background thread to monitor game state"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self.monitor_game_state, daemon=True)
            self.monitor_thread.start()

    def get_vehicle_address(self):
        """Get the current vehicle's memory address using the chain from ReClass.NET"""
        try:
            # Base pointer chain: [[[[02A8598C]+0x1B8]+0x38]+0xD0]
            base_ptr = self.safe_read_memory(self.base_address + 0x2A8598C, 4)
            if not base_ptr:
                return None
            
            addr = int.from_bytes(base_ptr, 'little')
            # Follow pointer chain with offsets
            for offset in [0x1B8, 0x38, 0xD0]:
                read = self.safe_read_memory(addr + offset, 4)
                if not read:
                    return None
                addr = int.from_bytes(read, 'little')
            
            # Validate final address
            if addr and addr > 0x10000:  # Basic sanity check
                return addr
                
        except Exception as e:
            print(f"Error getting vehicle address: {e}")
            
        return None
            
    def is_process_alive(self):
        """Check if the game process is still running"""
        try:
            import psutil
            return psutil.pid_exists(self.pm.process_id)
        except:
            # Fallback method if psutil is not available
            try:
                self.pm.read_bytes(self.base_address, 1)
                return True
            except:
                return False

    def get_vehicle_address(self):
        """Get the current vehicle's memory address using the chain from ReClass.NET"""
        try:
            # Base pointer chain: [[[[02A8598C]+0x1B8]+0x38]+0xD0]
            base_ptr = self.safe_read_memory(self.base_address + 0x2A8598C, 4)
            if not base_ptr:
                return None
            
            addr = int.from_bytes(base_ptr, 'little')
            # Follow pointer chain with offsets
            for offset in [0x1B8, 0x38, 0xD0]:
                read = self.safe_read_memory(addr + offset, 4)
                if not read:
                    return None
                addr = int.from_bytes(read, 'little')
            
            # Validate final address
            if addr and addr > 0x10000:  # Basic sanity check
                return addr
                
        except Exception as e:
            print(f"Error getting vehicle address: {e}")
            
        return None
            
    def monitor_game_state(self):
        """Monitor vehicle and game state for accurate timer and features"""
        consecutive_errors = 0
        base_sleep_time = 1.0 / 30  # Start with 30Hz to be safer
        max_sleep_time = 1.0 / 15   # Don't go lower than 15Hz
        current_sleep = base_sleep_time
        backoff_factor = 1.5  # Use a gentler backoff multiplier
        
        # Vehicle state enum values from ReClass.NET
        VEHICLE_STATE = {
            0: "OnGround",
            1: "InAir",
            2: "Landing",
            3: "Tumbling",
            4: "Collided",
            5: "Totalled",
            6: "StartTumble",
            7: "Dead"
        }
        
        while self.monitoring and self.connected:
            try:
                # Check if process is still alive
                if not self.is_process_alive():
                    self.connected = False
                    break
                    
                # Check if player has control (not loading, not cutscene)
                control_addr = self.base_address + self.offsets['player_has_control']
                
                # Get vehicle state from fb::NFSVehicle
                vehicle_base = self.get_vehicle_address()
                if vehicle_base:
                    try:
                        vehicle_state = self.safe_read_memory(vehicle_base + 0x4A0, 4)  # Vehicle state offset
                        if vehicle_state:
                            state_value = int.from_bytes(vehicle_state, 'little')
                            current_state = VEHICLE_STATE.get(state_value, "Unknown")
                            
                            # Use vehicle state to determine control
                            has_control = state_value == 0  # OnGround
                            is_loading = not has_control or state_value in [5, 7]  # Totalled or Dead
                        else:
                            has_control = False
                            is_loading = True
                    except Exception:
                        has_control = False
                        is_loading = True
                else:
                    # Fallback to basic control check if vehicle not found
                    try:
                        has_control = self.pm.read_bytes(control_addr + 0x04, 1)[0]
                    except Exception:
                        has_control = 0
                    is_loading = has_control == 0
                
                # Update timer
                self.timer.update(is_loading, has_control == 1)
                
                # Update UI (must be thread-safe)
                self.root.after(0, self.update_timer_display)
                
                # Reset error counter and sleep time on successful read
                consecutive_errors = 0
                current_sleep = base_sleep_time
                
            except Exception as e:
                consecutive_errors = min(consecutive_errors + 1, 10)  # Cap the error counter
                # Use a gentler backoff calculation
                current_sleep = min(base_sleep_time * (backoff_factor ** consecutive_errors), max_sleep_time)
                print(f"Monitor error: {e} - Backing off for {current_sleep:.3f}s")
                
            finally:
                time.sleep(current_sleep)
                
    def update_timer_display(self):
        """Update timer display in UI"""
        if self.timer.timer_running:
            self.timer_display.config(text=self.timer.get_time_str())
            loading_str = str(self.timer.loading_time).split('.')[0]
            self.loading_time_label.config(text=f"Loading Time: {loading_str}")
            
            if self.timer.is_loading:
                self.is_loading_label.config(text="Status: Loading...", foreground='red')
            else:
                self.is_loading_label.config(text="Status: Running", foreground='green')
                
    def start_timer(self):
        self.timer.start()
        self.splits_text.delete(1.0, tk.END)
        
    def split_timer(self):
        checkpoint = f"Split {len(self.timer.split_times) + 1}"
        self.timer.split(checkpoint)
        self.splits_text.insert(tk.END, f"{checkpoint}: {self.timer.get_time_str()}\n")
        
    def stop_timer(self):
        self.timer.stop()
        
    def reset_timer(self):
        self.timer = LoadlessTimer()
        self.timer_display.config(text="00:00:00.000")
        self.splits_text.delete(1.0, tk.END)
        
    def export_splits(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            self.timer.export_splits(filename)
            messagebox.showinfo("Success", "Splits exported!")
            
    def copy_time(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.timer.get_time_str())
        messagebox.showinfo("Success", "Time copied to clipboard!")
        
    def safe_write_memory(self, address, buffer, length):
        """Safely write to memory with validation and error handling"""
        try:
            # Validate address is within game's memory space
            if not isinstance(address, int) or address < 0x400000:
                print(f"Invalid memory address: {hex(address) if isinstance(address, int) else address}")
                return False
                
            # Thread safety for memory operations
            with self._lock:
                # Validate we can read the target location first
                if self.pm.read_bytes(address, 1):
                    self.pm.write_bytes(address, buffer, length)
                    return True
                return False
                
        except Exception as e:
            # Check for specific Windows errors
            if isinstance(e, WindowsError):
                if e.winerror == 299:  # ERROR_PARTIAL_COPY
                    # Memory protection issue - try with protection override
                    try:
                        return self.safe_write_with_protection(address, buffer, length)
                    except:
                        pass
            print(f"Memory write error at {hex(address)}: {e}")
            return False
            
    def safe_read_memory(self, address, length):
        """Safely read from memory with validation and thread safety"""
        try:
            # Validate address is within game's memory space
            if not isinstance(address, int) or address < 0x400000:
                print(f"Invalid memory address: {hex(address) if isinstance(address, int) else address}")
                return None
                
            # Thread safety for memory operations
            with self._lock:
                data = self.pm.read_bytes(address, length)
                # Validate data was read correctly
                if data and len(data) == length:
                    return data
                return None
                
        except Exception as e:
            # Handle specific memory errors
            if isinstance(e, WindowsError):
                if e.winerror == 299:  # ERROR_PARTIAL_COPY
                    # Memory protection issue - try with protection override
                    success, old_protect = self.set_memory_protection(address, length, 0x40)  # PAGE_EXECUTE_READWRITE
                    if success:
                        try:
                            data = self.pm.read_bytes(address, length)
                            self.set_memory_protection(address, length, old_protect)
                            return data
                        except:
                            pass
            print(f"Memory read error at {hex(address)}: {e}")
            return None

    def set_memory_protection(self, address, size, new_protect):
        """Change memory protection flags"""
        try:
            import ctypes
            from ctypes import windll, c_long, c_size_t, c_void_p, byref, sizeof
            
            # Constants for memory protection
            PAGE_EXECUTE_READWRITE = 0x40
            
            # Get process handle
            process_handle = self.pm.process_handle
            
            # Allocate buffer for old protection
            old_protect = c_long(0)
            
            # Change protection
            if windll.kernel32.VirtualProtectEx(
                process_handle,
                c_void_p(address),
                c_size_t(size),
                c_long(new_protect),
                byref(old_protect)
            ):
                return True, old_protect.value
            return False, None
        except Exception as e:
            print(f"Error setting memory protection: {e}")
            return False, None

    def safe_write_with_protection(self, address, buffer, size):
        """Write to memory with proper protection handling"""
        try:
            # Constants
            PAGE_EXECUTE_READWRITE = 0x40
            
            # Set memory to EXECUTE_READWRITE
            success, old_protect = self.set_memory_protection(address, size, PAGE_EXECUTE_READWRITE)
            if not success:
                print(f"Failed to set memory protection at {hex(address)}")
                return False
                
            # Write the bytes
            result = self.safe_write_memory(address, buffer, size)
            
            # Restore original protection
            if old_protect is not None:
                self.set_memory_protection(address, size, old_protect)
                
            return result
        except Exception as e:
            print(f"Error in protected write: {e}")
            return False

    def toggle_framerate(self):
        """Toggle framerate unlock with proper memory protection"""
        if not self.connected:
            return
            
        try:
            success = True
            protection_errors = []
            write_errors = []
            
            for offset in self.offsets['framerate_unlocker']:
                addr = self.base_address + offset
                
                # Attempt write with protection handling
                if not self.safe_write_with_protection(addr, 
                    b'\x90' if self.unlock_fps.get() else b'\x01', 1):
                    success = False
                    write_errors.append(hex(offset))
                    
            if not success:
                error_msg = "Failed to apply some FPS unlock patches:\n"
                if protection_errors:
                    error_msg += f"Protection errors at: {', '.join(protection_errors)}\n"
                if write_errors:
                    error_msg += f"Write errors at: {', '.join(write_errors)}"
                    
                messagebox.showwarning("Warning", 
                    f"{error_msg}\n\nTry running the application as administrator.")
                
                # Revert changes if partial application
                self.unlock_fps.set(False)
                
        except Exception as e:
            print(f"Error in toggle_framerate: {e}")
            messagebox.showerror("Error", 
                "Failed to modify FPS settings.\n"
                "Try running the application as administrator.")
                
    def toggle_cutscene_fps(self):
        if not self.connected:
            return
            
        try:
            # Known cutscene FPS limiter addresses
            cutscene_addresses = [
                0x410720,  # Main cutscene limiter
                0x410725,  # Secondary limiter
                0x41072A   # Tertiary limiter
            ]
            
            success = True
            for offset in cutscene_addresses:
                addr = self.base_address + offset
                # NOP out the FPS cap instructions
                if not self.safe_write_memory(addr, b'\x90' * 5 if self.unlock_cutscene_fps.get() else b'\x89\x86\xE8\x00\x00', 5):
                    success = False
                    
            if success:
                messagebox.showinfo("Info", 
                    "Cutscene FPS unlock applied. If you experience crashes:\n"
                    "1. Try lowering the menu FPS first\n"
                    "2. Disable cutscene FPS unlock during loading screens\n"
                    "3. Keep menu FPS below 150Hz for stability")
            else:
                messagebox.showwarning("Warning", 
                    "Could not fully apply cutscene FPS unlock.\n"
                    "The game may be unstable.")
                
        except Exception as e:
            print(f"Error toggling cutscene FPS: {e}")
            messagebox.showerror("Error", 
                "Failed to modify cutscene FPS settings.\n"
                "Try restarting the game.")
        
    def validate_game_state(self):
        """Check if it's safe to modify game memory"""
        try:
            if not self.connected or not self.pm:
                return False
            test_addr = self.base_address + self.offsets['player_has_control']
            test_read = self.safe_read_memory(test_addr, 1)
            return test_read is not None
        except:
            return False

    def validate_precise_fps(self):
        """Validate the precise FPS input"""
        try:
            value = float(self.precise_fps.get())
            if value < 30:
                self.precise_fps.set("30")
            elif value > 60:
                self.precise_fps.set("60")
            self.menu_fps_label.config(text=f"{int(float(self.precise_fps.get()))} Hz")
        except ValueError:
            self.precise_fps.set("60")
            
    def test_menu_fps(self):
        """Test the FPS change in a safe way"""
        try:
            fps_value = float(self.precise_fps.get())
            
            # First, try to read the current value
            addr = self.base_address + 0xA607F7  # Original MaxSimFps address
            current = self.safe_read_memory(addr, 4)
            if current is None:
                messagebox.showerror("Error", "Could not read current FPS value")
                return
                
            # Try writing the test value
            if not self.safe_write_with_protection(addr, struct.pack('f', fps_value), 4):
                messagebox.showerror("Error", "Could not write test FPS value")
                return
                
            # Wait a very short time and verify
            time.sleep(0.1)
            
            # If we're still running, it's probably safe
            self.apply_fps_btn.config(state='normal')
            messagebox.showinfo("Success", 
                "Test successful! You can now apply the FPS change.\n"
                "If the game crashes, try a lower value.")
                
        except Exception as e:
            print(f"Error testing FPS: {e}")
            messagebox.showerror("Error", "FPS test failed")
            
    def apply_menu_fps_change(self):
        """Apply the FPS change after testing"""
        try:
            fps_value = float(self.precise_fps.get())
            
            # Original MaxSimFps address
            addr = self.base_address + 0xA607F7
            
            # Write the new value with a float that specifies exactly one frame interval
            frame_interval = 1.0 / fps_value
            if not self.safe_write_with_protection(addr, struct.pack('f', frame_interval), 4):
                messagebox.showerror("Error", "Failed to apply FPS change")
                return
                
            # Disable the apply button until next test
            self.apply_fps_btn.config(state='disabled')
            messagebox.showinfo("Success", f"FPS changed to {int(fps_value)}")
            
        except Exception as e:
            print(f"Error applying FPS: {e}")
            messagebox.showerror("Error", "Failed to apply FPS change")
            
    def toggle_loading_vsync(self):
        """Toggle vsync during loading with proper memory protection"""
        if not self.connected:
            return
            
        try:
            # Original vsync bytes
            original_vsync = b'\xE9\x8B\x01\x00\x00'
            
            success = True
            protection_errors = []
            write_errors = []
            
            for vsync_offset in ['loading_vsync_1', 'loading_vsync_2']:
                addr = self.base_address + self.offsets[vsync_offset]
                
                # Prepare the bytes to write
                if self.disable_loading_vsync.get():
                    new_bytes = b'\x90' * 5  # NOP instructions
                else:
                    new_bytes = original_vsync
                    
                # Attempt write with protection handling
                if not self.safe_write_with_protection(addr, new_bytes, len(new_bytes)):
                    success = False
                    write_errors.append(hex(self.offsets[vsync_offset]))
                    
            if not success:
                error_msg = "Failed to modify some vsync settings:\n"
                if protection_errors:
                    error_msg += f"Protection errors at: {', '.join(protection_errors)}\n"
                if write_errors:
                    error_msg += f"Write errors at: {', '.join(write_errors)}"
                    
                messagebox.showwarning("Warning", 
                    f"{error_msg}\n\nTry running the application as administrator.")
                
                # Revert changes if partial application
                self.disable_loading_vsync.set(False)
                
        except Exception as e:
            print(f"Error in toggle_loading_vsync: {e}")
            messagebox.showerror("Error", 
                "Failed to modify vsync settings.\n"
                "Try running the application as administrator.")
    def launch_renderdoc(self):
        """Launch RenderDoc for graphics analysis"""
        try:
            import subprocess
            renderdoc_path = "C:\\Program Files\\RenderDoc\\qrenderdoc.exe"
            if os.path.exists(renderdoc_path):
                subprocess.Popen([renderdoc_path])
                messagebox.showinfo("RenderDoc", 
                    "RenderDoc launched!\n\n"
                    "Instructions:\n"
                    "1. Click 'File -> Attach to Running Instance'\n"
                    "2. Select 'Need for Speed The Run.exe'\n"
                    "3. Press F12 in-game to capture a frame\n"
                    "4. Analyze motion blur, shadows, reflections in the frame\n"
                    "5. Use shader editor to enhance visual quality")
            else:
                messagebox.showerror("Error", 
                    "RenderDoc not found!\n"
                    "Download from: https://renderdoc.org/\n"
                    f"Expected path: {renderdoc_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch RenderDoc: {e}")
            
    def apply_graphics(self):
        """Apply enhanced graphics settings"""
        if not self.connected:
            return
            
        try:
            # These would require shader modifications or post-processing hooks
            # For now, we'll modify available visual parameters
            
            if self.enhanced_motion_blur.get():
                # Motion blur quality typically controlled by shader constants
                messagebox.showinfo("Info", "Motion blur enhancement requires shader injection")
                
            if self.enhanced_shadows.get():
                # Shadow map resolution and filter quality
                messagebox.showinfo("Info", "Shadow enhancement requires render target modification")
                
            if self.enhanced_reflections.get():
                # Reflection probe resolution and update frequency
                messagebox.showinfo("Info", "Reflection enhancement requires dynamic env-map modification")
                
        except Exception as e:
            messagebox.showerror("Error", f"Graphics application failed: {e}")
            
    def toggle_assists(self):
        """Disable all vehicle assists"""
        if not self.connected:
            return
            
        try:
            if self.disable_assists.get():
                # AlignToRoad
                self.pm.write_bytes(self.base_address + 0x69B167, b'\x74\x3E', 2)
                # OverrideDriftIntent  
                self.pm.write_bytes(self.base_address + 0x69B5E2, b'\x75\x2B', 2)
                # RaceLineAssist
                for offset in self.offsets['disable_assists']:
                    addr = self.base_address + offset
                    self.pm.write_bytes(addr, b'\x90' * 5, 5)
            else:
                # Restore original bytes
                self.pm.write_bytes(self.base_address + 0x69B167, b'\x75\x3E', 2)
                self.pm.write_bytes(self.base_address + 0x69B5E2, b'\x74\x2B', 2)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to toggle assists: {e}")
            
    def toggle_headlights(self):
        """Force headlights on/off"""
        if not self.connected:
            return
            
        try:
            for offset in self.offsets['headlights']:
                addr = self.base_address + offset
                if self.headlights.get():
                    self.pm.write_bytes(addr, b'\x90' * 6, 6)
                else:
                    # Restore original mov instruction
                    self.pm.write_bytes(addr, b'\x88\x86\xE7\x01\x00\x00', 6)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to toggle headlights: {e}")
            
    def update_lighting(self, value):
        """Update world lighting intensity"""
        if not self.connected:
            return
            
        try:
            # Validate input
            light_value = max(0.0, min(float(value), 3.0))
            addr = self.base_address + self.offsets['world_render_light']
            
            # Use safe memory write
            if not self.safe_write_memory(addr + 0x18, struct.pack('f', light_value), 4):
                print("Failed to update lighting intensity")
        except Exception as e:
            print(f"Error updating lighting: {e}")
            
    def update_sun(self, value):
        """Update sun position"""
        if not self.connected:
            return
            
        try:
            # Validate input values
            x_value = max(-180.0, min(float(self.sun_x.get()), 180.0))
            y_value = max(-180.0, min(float(self.sun_y.get()), 180.0))
            
            # Update X rotation
            addr_x = self.base_address + self.offsets['sun_rotation_x']
            if not self.safe_write_memory(addr_x + 0x58, struct.pack('f', x_value), 4):
                print("Failed to update sun X rotation")
                
            # Update Y rotation
            addr_y = self.base_address + self.offsets['sun_rotation_y']
            if not self.safe_write_memory(addr_y + 0x54, struct.pack('f', y_value), 4):
                print("Failed to update sun Y rotation")
                
        except Exception as e:
            print(f"Error updating sun position: {e}")
            
    def unlock_vehicles(self):
        """Unlock all vehicles"""
        if not self.connected:
            return
        try:
            addr = self.base_address + 0x53D629
            self.pm.write_bytes(addr, b'\xC7\x40\x18\x01\x00\x00\x00', 7)
            messagebox.showinfo("Success", "All vehicles unlocked!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to unlock vehicles: {e}")
            
    def unlock_challenges(self):
        """Unlock all challenges"""
        if not self.connected:
            return
        try:
            addr = self.base_address + 0x45B162
            self.pm.write_bytes(addr, b'\xC6\x45\x18\x01', 4)
            messagebox.showinfo("Success", "All challenges unlocked!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to unlock challenges: {e}")
            
    def apply_crash_fixes(self):
        """Apply all crash bypasses"""
        if not self.connected:
            return
        try:
            # Tunnel of Pain
            self.pm.write_bytes(self.base_address + self.offsets['tunnel_pain'], b'\x90\x90\x90', 3)
            # Chicago crashes
            for offset in self.offsets['chicago_crash']:
                self.pm.write_bytes(self.base_address + offset, b'\x90' * 6, 6)
            messagebox.showinfo("Success", "Crash bypasses applied!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply crash fixes: {e}")
            
    def disable_resets(self):
        """Disable out of bounds and wrong way resets"""
        if not self.connected:
            return
        try:
            # Reset OOB
            self.pm.write_bytes(self.base_address + 0x7FAA8C, b'\x90\x90\x90', 3)
            # Wrong way respawn
            self.pm.write_bytes(self.base_address + 0x408915, b'\x90' * 6, 6)
            # Rival getting away
            self.pm.write_bytes(self.base_address + 0x8CFB6E, b'\x90' * 5, 5)
            messagebox.showinfo("Success", "Reset triggers disabled!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to disable resets: {e}")
            
    def cleanup_resources(self):
        """Clean up all resources when shutting down"""
        try:
            # Stop monitoring thread
            self.monitoring = False
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=1.0)
                
    def get_vehicle_address(self):
        """Get the current vehicle's memory address using the chain from ReClass.NET"""
        try:
            # Base pointer chain: [[[[02A8598C]+0x1B8]+0x38]+0xD0]
            base_ptr = self.safe_read_memory(self.base_address + 0x2A8598C, 4)
            if not base_ptr:
                return None
            
            addr = int.from_bytes(base_ptr, 'little')
            # Follow pointer chain with offsets
            for offset in [0x1B8, 0x38, 0xD0]:
                read = self.safe_read_memory(addr + offset, 4)
                if not read:
                    return None
                addr = int.from_bytes(read, 'little')
            
            # Validate final address
            if addr and addr > 0x10000:  # Basic sanity check
                return addr
                
        except Exception as e:
            print(f"Error getting vehicle address: {e}")
            
        return None
                
            # Restore any modified memory
            if self.connected and self.pm:
                try:
                    # Restore FPS settings
                    if hasattr(self, 'unlock_fps') and self.unlock_fps.get():
                        self.unlock_fps.set(False)
                        self.toggle_framerate()
                        
                    # Restore vsync settings
                    if hasattr(self, 'disable_loading_vsync') and self.disable_loading_vsync.get():
                        self.disable_loading_vsync.set(False)
                        self.toggle_loading_vsync()
                except:
                    pass
                    
            # Close process handle
            if self.pm:
                try:
                    self.pm.close_process()
                except:
                    pass
                    
    def get_vehicle_address(self):
        """Get the current vehicle's memory address using the chain from ReClass.NET"""
        try:
            # Base pointer chain: [[[[02A8598C]+0x1B8]+0x38]+0xD0]
            base_ptr = self.safe_read_memory(self.base_address + 0x2A8598C, 4)
            if not base_ptr:
                return None
            
            addr = int.from_bytes(base_ptr, 'little')
            # Follow pointer chain with offsets
            for offset in [0x1B8, 0x38, 0xD0]:
                read = self.safe_read_memory(addr + offset, 4)
                if not read:
                    return None
                addr = int.from_bytes(read, 'little')
            
            # Validate final address
            if addr and addr > 0x10000:  # Basic sanity check
                return addr
                
        except Exception as e:
            print(f"Error getting vehicle address: {e}")
            
        return None
                    
        except Exception as e:
            print(f"Error during cleanup: {e}")
            
    def on_closing(self):
        """Handle window close event"""
        try:
            self.cleanup_resources()
        finally:
            self.root.destroy()
            
    def toggle_infinite_nos(self):
        """Toggle infinite NOS using correct vehicle memory structure"""
        if not self.connected:
            return
            
        try:
            # Get vehicle base address using pointer chain
            vehicle_base = self.get_vehicle_address()
            if not vehicle_base:
                messagebox.showerror("Error", "Could not find vehicle in memory")
                self.infinite_nos.set(False)
                return
                
            success = True
            if self.infinite_nos.get():
                # Update NOS tank capacity (offset 0x4C8)
                if not self.safe_write_with_protection(vehicle_base + 0x4C8, struct.pack('f', 999999.0), 4):
                    success = False
                    
                # Set current NOS amount (offset 0x4CC)
                if not self.safe_write_with_protection(vehicle_base + 0x4CC, struct.pack('f', 999999.0), 4):
                    success = False
                    
                # Set NOS regen rate to max (offset 0x4D0)
                if not self.safe_write_with_protection(vehicle_base + 0x4D0, struct.pack('f', 100.0), 4):
                    success = False
                    
                # Disable NOS consumption (offset 0x4D4)
                if not self.safe_write_with_protection(vehicle_base + 0x4D4, struct.pack('f', 0.0), 4):
                    success = False
                    
                # Set NOS power multiplier (offset 0x4D8)
                if not self.safe_write_with_protection(vehicle_base + 0x4D8, struct.pack('f', 2.0), 4):
                    success = False
                    
                # Enable NOS state (offset 0x4E0)
                if not self.safe_write_with_protection(vehicle_base + 0x4E0, struct.pack('B', 1), 1):
                    success = False
            else:
                # Restore default values
                defaults = {
                    0x4C8: 100.0,  # Normal tank capacity
                    0x4CC: 100.0,  # Current NOS amount
                    0x4D0: 0.0,    # Default regen rate
                    0x4D4: 1.0,    # Normal consumption rate
                    0x4D8: 1.0,    # Normal power multiplier
                }
                
                for offset, value in defaults.items():
                    if not self.safe_write_with_protection(vehicle_base + offset, struct.pack('f', value), 4):
                        success = False
                        
                # Disable NOS state
                if not self.safe_write_with_protection(vehicle_base + 0x4E0, struct.pack('B', 0), 1):
                    success = False
            
            if not success:
                messagebox.showwarning("Warning", "Could not fully apply NOS modifications")
                self.infinite_nos.set(False)
                
        except Exception as e:
            print(f"Error toggling NOS: {e}")
            self.infinite_nos.set(False)
            
    def toggle_no_damage(self):
        """Toggle vehicle damage"""
        if not self.connected:
            return
            
        try:
            success = True
            if self.no_damage.get():
                # Disable damage by writing to multiple damage-related addresses
                for offset in self.offsets['vehicle_damage']:
                    addr = self.base_address + offset
                    # Zero out damage values and multipliers
                    if not self.safe_write_with_protection(addr, struct.pack('f', 0.0), 4):
                        success = False
                    # Disable damage accumulation
                    if not self.safe_write_with_protection(addr + 0x8, struct.pack('f', 0.0), 4):
                        success = False
            else:
                # Restore default damage values
                for offset in self.offsets['vehicle_damage']:
                    addr = self.base_address + offset
                    # Restore normal damage values
                    if not self.safe_write_with_protection(addr, struct.pack('f', 1.0), 4):
                        success = False
                    # Restore damage accumulation
                    if not self.safe_write_with_protection(addr + 0x8, struct.pack('f', 1.0), 4):
                        success = False
            
            if not success:
                messagebox.showwarning("Warning", "Could not fully apply damage modifications")
                
        except Exception as e:
            print(f"Error toggling damage: {e}")
            self.no_damage.set(False)
            
    def open_customizer(self):
        """Open vehicle customization interface"""
        if not self.connected:
            messagebox.showerror("Error", "Not connected to game!")
            return
        VehicleCustomizer(self.root, self.pm, self.base_address)

def is_admin():
    """Check if the application is running with admin privileges"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Re-run the script with admin privileges"""
    try:
        import ctypes
        import sys
        
        if sys.argv[-1] != 'asadmin':
            script = os.path.abspath(sys.argv[0])
            params = f'"{script}" asadmin'
            
            # Get Python executable path
            python_exe = sys.executable
            
            # Create the elevated process
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                python_exe,
                params,
                None,
                1  # SW_SHOWNORMAL
            )
            
            # ShellExecute returns a value greater than 32 if successful
            if ret <= 32:
                raise Exception(f"Failed to elevate process: error {ret}")
                
            return True
    except Exception as e:
        print(f"Error during elevation: {e}")
        return False
    
    return False

if __name__ == "__main__":
    # Check for admin rights
    if not is_admin():
        # If elevation was requested but failed, show error
        if len(sys.argv) > 1 and sys.argv[-1] == 'asadmin':
            messagebox.showerror("Error", 
                "Failed to obtain administrator privileges.\n"
                "Please try running the application as administrator manually.")
            sys.exit(1)
            
        print("Requesting administrator privileges...")
        # Try to elevate privileges
        if run_as_admin():
            print("Elevation successful, restarting with admin rights...")
            sys.exit(0)
        else:
            print("Failed to elevate privileges")
            # If elevation failed, warn user and continue with limited functionality
            messagebox.showwarning("Warning", 
                "Could not obtain administrator privileges.\n"
                "Some features may not work correctly.")
    
    root = tk.Tk()
    try:
        app = NFSModSuite(root)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("Fatal Error", f"Application failed to start: {e}")
    finally:
        # Ensure cleanup happens even on crash
        if 'app' in locals():
            app.cleanup_resources()