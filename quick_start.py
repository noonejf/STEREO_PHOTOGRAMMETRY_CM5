#!/usr/bin/env python3
"""
Script de Inicio Rápido para Sistema de Fotogrametría Estéreo CM5
Guía interactiva para configurar y usar el sistema por primera vez
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

def print_banner():
    """Mostrar banner de bienvenida"""
    banner = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║        🚀 STEREO PHOTOGRAMMETRY SYSTEM CM5 🚀                               ║
║                                                                              ║
║        For Raspberry Pi CM5 + Arducam HQ 477 Cameras                         ║
║        Designed for robust space applications                                ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)

def print_step(step_num, title, description=""):
    """Imprimir paso formateado"""
    print(f"\n📋 STEP {step_num}: {title}")
    if description:
        print(f"   {description}")
    print("-" * 60)

def ask_yes_no(question, default="y"):
    """Preguntar sí/no al usuario"""
    suffix = "[Y/n]" if default.lower() == "y" else "[y/N]"
    response = input(f"{question} {suffix}: ").strip().lower()
    
    if not response:
        return default.lower() == "y"
    
    return response in ["y", "yes", "sí", "si"]

def run_command_with_output(cmd, description=""):
    """Ejecutar comando y mostrar resultado"""
    print(f"🔄 Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    if description:
        print(f"   {description}")
    
    try:
        if isinstance(cmd, str):
            cmd = cmd.split()
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✅ Completed successfully")
            if result.stdout.strip():
                print(f"📄 Output:\n{result.stdout}")
            return True
        else:
            print(f"❌ Error (code {result.returncode})")
            if result.stderr:
                print(f"📄 Error:\n{result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("⏰ Timeout - command took too long")
        return False
    except Exception as e:
        print(f"❌ Error executing command: {e}")
        return False

def check_basic_requirements():
    """Verify basic requirements"""
    print_step(1, "BASIC REQUIREMENTS CHECK")
    
    # Verificar que estamos en Raspberry Pi
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read().lower()
        
        if 'raspberry' in cpuinfo:
            print("✅ Raspberry Pi detected")
        else:
            print("⚠️  Raspberry Pi not detected - continuing anyway")
    except:
        print("⚠️  Could not verify hardware - continuing")
    
    # Verificar Python
    version = sys.version_info
    if version.major == 3 and version.minor >= 9:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro} - Compatible")
    else:
        print(f"❌ Python {version.major}.{version.minor} - Python 3.9+ required")
        return False
    
    # Verificar permisos
    if os.geteuid() == 0:
        print("⚠️  Running as root - not recommended for normal use")
    else:
        print("✅ Running as normal user")
    
    return True

def install_system():
    """Install system"""
    print_step(2, "SYSTEM INSTALLATION")
    
    if not Path("install_setup.py").exists():
        print("❌ File install_setup.py not found")
        print("   Make sure to run this script from the project directory")
        return False
    
    if ask_yes_no("Run automatic installation?"):
        print("\n🚀 Starting automatic installation...")
        print("   This may take several minutes...")
        
        success = run_command_with_output(
            [sys.executable, "install_setup.py"],
            "Install dependencies and configure system"
        )
        
        if success:
            print("\n✅ Installation completed")
            print("⚠️  IMPORTANT: Reboot required to activate cameras")
            
            if ask_yes_no("Reboot now?", "n"):
                print("🔄 Rebooting system...")
                subprocess.run(["sudo", "reboot"])
                return True
            else:
                print("⚠️  Remember to reboot before using cameras")
                return True
        else:
            print("❌ Error during installation")
            return False
    else:
        print("⏭️  Skipping automatic installation")
        return True

def verify_system():
    """Verify system"""
    print_step(3, "SYSTEM VERIFICATION")
    
    if not Path("demo_system_check.py").exists():
        print("⚠️  Verification script not found")
        return True
    
    if ask_yes_no("Run full system verification?"):
        success = run_command_with_output(
            [sys.executable, "demo_system_check.py"],
            "Verify all system components"
        )
        
        if success:
            print("✅ Verification completed - check output above")
        else:
            print("⚠️  Problems detected - check errors above")
        
        return success
    else:
        print("⏭️  Skipping system verification")
        return True

def test_cameras():
    """Probar cámaras"""
    print_step(4, "PRUEBA DE CÁMARAS")
    
    # Verificar listado de cámaras
    print("🔍 Verificando cámaras disponibles...")
    camera_success = run_command_with_output(
        ["libcamera-hello", "--list-cameras"],
        "Listar cámaras detectadas"
    )
    
    if not camera_success:
        print("❌ No se pudieron detectar cámaras")
        print("\n🛠️  SOLUCIONES POSIBLES:")
        print("   1. Verificar conexiones físicas de cables CSI")
        print("   2. Asegurar que las cámaras están en CAM0 y CAM1")
        print("   3. Reiniciar el sistema: sudo reboot")
        print("   4. Verificar /boot/firmware/config.txt")
        return False
    
    # Test quick capture
    if ask_yes_no("Test quick capture with camera 0?"):
        test_success = run_command_with_output(
            ["libcamera-jpeg", "--camera", "0", "-o", "test_cam0.jpg", "-t", "2000"],
            "Capture test image"
        )
        
        if test_success and Path("test_cam0.jpg").exists():
            print("✅ Capture successful - test_cam0.jpg created")
            
            # Clean up test file
            try:
                Path("test_cam0.jpg").unlink()
                print("🗑️  Test file deleted")
            except:
                pass
        else:
            print("❌ Error in test capture")
            return False
    
    return True

def show_usage_guide():
    """Show usage guide"""
    print_step(5, "QUICK START GUIDE")
    
    guide = """
📚 RECOMMENDED WORKFLOW:

1️⃣  FIRST TIME - CALIBRATION:
   • Run: python3 main.py
   • Press "🎯 Calibrate Cameras"
   • Prepare 10x7 checkerboard
   • Follow countdown instructions
   • Move board to different positions during the 25 captures

2️⃣  3D OBJECT CAPTURE:
   • Ensure it shows "✅ System Calibrated"
   • Position your object in field of view
   • Press "📸 Capture for 3D Model"
   • Wait for 10 second countdown

3️⃣  3D PROCESSING:
   • Press "⚙️ Process Last Captures"
   • Select SGBM algorithm (recommended)
   • Choose export formats (PLY recommended)
   • Press "🚀 Start Processing"

4️⃣  RESULTS:
   • Files are saved in data/results/
   • You can view disparity and depth maps
   • Statistics show result quality

⚠️  IMPORTANT:
   • DO NOT move cameras after calibration
   • Use uniform lighting without reflections
   • For best results, objects with visible texture
   • The board must be completely flat
"""
    
    print(guide)
    
    input("\n📖 Press Enter to continue...")

def show_troubleshooting():
    """Show troubleshooting guide"""
    print_step(6, "COMMON TROUBLESHOOTING")
    
    troubleshooting = """
🔧 COMMON PROBLEMS AND SOLUTIONS:

❌ "No cameras detected"
   ✅ Check CSI cables connected firmly
   ✅ Reboot: sudo reboot  
   ✅ Check config.txt: cat /boot/firmware/config.txt | grep imx477

❌ "Error starting preview"
   ✅ Close other apps using cameras
   ✅ Test: libcamera-hello --camera 0 -t 2000
   ✅ Check user permissions

❌ "Calibration fails repeatedly"
   ✅ Use 10x7 checkerboard (9x6 internal corners)
   ✅ Uniform lighting, no reflections
   ✅ Board completely flat
   ✅ Move to different angles and distances

❌ "3D processing very slow"
   ✅ Use BM algorithm instead of SGBM
   ✅ Reduce capture resolution
   ✅ Close unnecessary applications

❌ "PyQt5 not working"
   ✅ Install: sudo apt install python3-pyqt5
   ✅ DO NOT use pip install pyqt5 on Raspberry Pi

📞 GET HELP:
   • Check logs: tail -f logs/stereo_photogrammetry.log
   • Run verification: python3 demo_system_check.py
   • Check README.md for more details
"""
    
    print(troubleshooting)
    input("\n📖 Press Enter to continue...")

def launch_application():
    """Launch main application"""
    print_step(7, "LAUNCH APPLICATION")
    
    if not Path("main.py").exists():
        print("❌ main.py not found")
        print("   Make sure to run from project directory")
        return False
    
    if ask_yes_no("Launch main application now?"):
        print("\n🚀 Launching stereo photogrammetry application...")
        print("   Main system window will open")
        print("   Press Ctrl+C to cancel if there are problems")
        
        try:
            # Run main application
            subprocess.run([sys.executable, "main.py"])
            return True
        except KeyboardInterrupt:
            print("\n⏹️  Application canceled by user")
            return False
        except Exception as e:
            print(f"\n❌ Error launching application: {e}")
            return False
    else:
        print("\n📝 To launch manually later:")
        print("   cd " + str(Path.cwd()))
        print("   python3 main.py")
        return True

def main():
    """Quick start script main function"""
    print_banner()
    
    print("Welcome to the CM5 stereo photogrammetry system!")
    print("This wizard will guide you through the initial configuration.")
    print(f"Current directory: {Path.cwd()}")
    
    if not ask_yes_no("\nContinue with guided configuration?"):
        print("👋 See you later! Run 'python3 main.py' when ready.")
        return 0
    
    # Run steps
    steps = [
        check_basic_requirements,
        install_system,
        verify_system,
        test_cameras,
        show_usage_guide,
        show_troubleshooting,
        launch_application
    ]
    
    try:
        for step_func in steps:
            if not step_func():
                if ask_yes_no("Continue despite error?", "n"):
                    continue
                else:
                    print("\n⏹️  Configuration canceled")
                    print("   You can run this script again later")
                    return 1
        
        print("\n🎉 CONFIGURATION COMPLETED!")
        print("   The system is ready to use")
        print("   Run 'python3 main.py' to start")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Configuration canceled by user")
        print("   You can run this script again later")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print("   Check documentation or run script again")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"Critical error: {e}")
        sys.exit(1)