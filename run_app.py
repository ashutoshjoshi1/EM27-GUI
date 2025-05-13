#!/usr/bin/env python3
import os
import sys
import subprocess
import platform
import glob
import shutil

def setup_environment():
    """Set up environment variables for Qt on different platforms"""
    try:
        import PyQt5
        qt_path = os.path.dirname(PyQt5.__file__)
        
        # Print PyQt5 version for debugging
        try:
            from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
            print(f"Qt version: {QT_VERSION_STR}")
            print(f"PyQt version: {PYQT_VERSION_STR}")
        except:
            print("Could not determine Qt/PyQt versions")
        
        # Platform-specific configurations
        system = platform.system()
        if system == "Darwin":  # macOS
            # Try a more direct approach for macOS
            # First, find all possible plugin paths
            possible_plugin_paths = []
            
            # Method 1: Look in PyQt5 directory
            possible_plugin_paths.append(os.path.join(qt_path, "Qt5", "plugins"))
            possible_plugin_paths.append(os.path.join(qt_path, "Qt", "plugins"))
            
            # Method 2: Look in site-packages
            site_packages = os.path.dirname(qt_path)
            possible_plugin_paths.append(os.path.join(site_packages, "PyQt5_Qt5", "Qt5", "plugins"))
            
            # Method 3: Look for Qt5 directory in parent directories
            parent_dir = os.path.dirname(site_packages)
            possible_plugin_paths.append(os.path.join(parent_dir, "Qt5", "plugins"))
            
            # Method 4: Use glob to find all possible plugin directories
            for path in glob.glob(os.path.join(site_packages, "**/plugins"), recursive=True):
                possible_plugin_paths.append(path)
            
            # Print all possible paths for debugging
            print("Searching for Qt plugins in:")
            for path in possible_plugin_paths:
                print(f"  {path}")
            
            # Try each path and look for the cocoa plugin
            for plugin_path in possible_plugin_paths:
                if os.path.exists(plugin_path):
                    platforms_dir = os.path.join(plugin_path, "platforms")
                    if os.path.exists(platforms_dir):
                        plugins = os.listdir(platforms_dir)
                        print(f"Found platforms directory: {platforms_dir}")
                        print(f"Available platform plugins: {plugins}")
                        
                        if "libqcocoa.dylib" in plugins:
                            print(f"Found macOS cocoa plugin in {platforms_dir}")
                            # Set the path directly to the platforms directory
                            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms_dir
                            print(f"Set QT_QPA_PLATFORM_PLUGIN_PATH to {platforms_dir}")
                            
                            # Try to force the platform
                            os.environ["QT_QPA_PLATFORM"] = "cocoa"
                            break
            
            # Additional macOS-specific settings
            os.environ["QT_MAC_WANTS_LAYER"] = "1"
            
        elif system == "Windows":
            # Windows typically needs less configuration
            plugin_path = os.path.join(qt_path, "Qt5", "plugins")
            if os.path.exists(plugin_path):
                platforms_dir = os.path.join(plugin_path, "platforms")
                if os.path.exists(platforms_dir):
                    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms_dir
                    print(f"Set QT_QPA_PLATFORM_PLUGIN_PATH to {platforms_dir}")
        
        # Common settings for all platforms
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
        
        # Try to use a different platform if cocoa is not available
        if system == "Darwin" and not os.environ.get("QT_QPA_PLATFORM"):
            print("Cocoa platform not found, trying minimal platform")
            os.environ["QT_QPA_PLATFORM"] = "minimal"
        
    except Exception as e:
        print(f"Failed to set up environment: {e}")

# Set up environment before running the application
setup_environment()

# Run the main application
try:
    print("Attempting to run main_gui.py...")
    subprocess.run([sys.executable, "main_gui.py"])
except Exception as e:
    print(f"Error running main_gui.py: {e}")
