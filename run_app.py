#!/usr/bin/env python3
import os
import sys
import subprocess

# Try to find the Qt plugins directory
try:
    import PyQt5
    qt_path = os.path.dirname(PyQt5.__file__)
    plugin_path = os.path.join(qt_path, "Qt5", "plugins")
    if os.path.exists(plugin_path):
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path
        print(f"Set QT_QPA_PLATFORM_PLUGIN_PATH to {plugin_path}")
        
        # Debug: Check if the platforms directory exists
        platforms_dir = os.path.join(plugin_path, "platforms")
        print(f"Platforms directory exists: {os.path.exists(platforms_dir)}")
        if os.path.exists(platforms_dir):
            print(f"Contents of platforms directory: {os.listdir(platforms_dir)}")
    else:
        print(f"Plugin path does not exist: {plugin_path}")
except Exception as e:
    print(f"Failed to set plugin path: {e}")

# Run the main application
subprocess.run([sys.executable, "main_gui.py"])
