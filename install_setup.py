#!/usr/bin/env python3
"""
Script de Instalación Automática para Sistema de Fotogrametría Estéreo CM5
Instala todas las dependencias necesarias en Raspberry Pi CM5 con Bookworm
"""

import os
import sys
import subprocess
import logging
from pathlib import Path

# Configurar logging básico
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def run_command(cmd, check=True, shell=True):
    """Ejecutar comando del sistema con logging"""
    logger.info(f"Ejecutando: {cmd}")
    try:
        result = subprocess.run(cmd, shell=shell, check=check, capture_output=True, text=True)
        if result.stdout:
            logger.info(f"Salida: {result.stdout}")
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Error ejecutando '{cmd}': {e}")
        if e.stderr:
            logger.error(f"Error stderr: {e.stderr}")
        if check:
            raise
        return e

def check_root():
    """Verificar si se ejecuta como root para apt install"""
    return os.geteuid() == 0

def update_system():
    """Actualizar sistema base"""
    logger.info("=== Actualizando sistema ===")
    run_command("sudo apt update")
    run_command("sudo apt upgrade -y")

def install_system_packages():
    """Instalar paquetes del sistema necesarios"""
    logger.info("=== Instalando paquetes del sistema ===")
    
    packages = [
        # Python y PyQt5
        "python3-pyqt5",
        "python3-pyqt5.qtwidgets",
        "python3-pyqt5.qtcore", 
        "python3-pyqt5.qtgui",
        
        # OpenCV y dependencias científicas
        "python3-opencv",
        "python3-numpy",
        "python3-scipy",
        "python3-matplotlib",
        "python3-sklearn",
        "python3-skimage",
        "python3-pil",
        
        # Libcamera y cámaras
        "libcamera-apps",
        "libcamera-dev",
        "python3-picamera2",
        
        # Herramientas adicionales
        "python3-yaml",
        "python3-tqdm",
        "python3-psutil",
        "python3-pandas",
        
        # Herramientas de desarrollo
        "python3-pip",
        "python3-venv",
        "git",
        
        # Dependencias para compilación (si necesarias)
        "build-essential",
        "cmake",
        "pkg-config",
        
        # Qt Designer (opcional para desarrollo GUI)
        "qttools5-dev-tools",
    ]
    
    for package in packages:
        logger.info(f"Instalando {package}...")
        result = run_command(f"sudo apt install -y {package}", check=False)
        if result.returncode != 0:
            logger.warning(f"No se pudo instalar {package}, continuando...")

def install_pip_packages():
    """Instalar paquetes Python adicionales via pip"""
    logger.info("=== Instalando paquetes Python adicionales ===")
    
    # Paquetes que podrían no estar en repos o necesitar versiones más nuevas
    pip_packages = [
        "colorlog",  # Para logging colorizado
        "open3d",    # Para nubes de puntos 3D (podría fallar en ARM)
    ]
    
    for package in pip_packages:
        logger.info(f"Instalando {package} via pip...")
        result = run_command(f"pip3 install {package}", check=False)
        if result.returncode != 0:
            logger.warning(f"No se pudo instalar {package} via pip")

def configure_camera():
    """Configurar cámaras Arducam HQ 477"""
    logger.info("=== Configurando cámaras ===")
    
    config_txt = "/boot/firmware/config.txt"
    
    # Verificar si el archivo de configuración existe
    if not Path(config_txt).exists():
        # Probar ubicación alternativa en sistemas más antiguos
        config_txt = "/boot/config.txt"
        if not Path(config_txt).exists():
            logger.error(f"No se encontró {config_txt}")
            return
    
    logger.info(f"Configurando {config_txt}")
    
    # Configuraciones necesarias para Arducam HQ 477 (IMX477)
    configs_to_add = [
        "# Configuración para Arducam HQ 477 estéreo",
        "camera_auto_detect=0",
        "dtoverlay=imx477,cam0",
        "dtoverlay=imx477,cam1", 
        "",
        "# Optimizaciones para cámaras múltiples",
        "gpu_mem=128",
        "start_x=1",
        "",
    ]
    
    try:
        # Leer configuración actual
        with open(config_txt, 'r') as f:
            current_config = f.read()
        
        # Verificar si ya está configurado
        if "dtoverlay=imx477" in current_config:
            logger.info("Las cámaras ya están configuradas en config.txt")
            return
        
        # Hacer backup
        backup_path = f"{config_txt}.backup"
        run_command(f"sudo cp {config_txt} {backup_path}")
        logger.info(f"Backup creado en {backup_path}")
        
        # Agregar configuraciones
        with open("/tmp/camera_config.txt", 'w') as f:
            f.write(current_config)
            if not current_config.endswith('\n'):
                f.write('\n')
            f.write('\n'.join(configs_to_add))
        
        run_command(f"sudo cp /tmp/camera_config.txt {config_txt}")
        logger.info("Configuración de cámaras agregada a config.txt")
        
        logger.warning("¡REINICIO REQUERIDO! Las cámaras funcionarán después del reinicio.")
        
    except Exception as e:
        logger.error(f"Error configurando cámaras: {e}")

def create_project_structure():
    """Crear estructura de directorios del proyecto"""
    logger.info("=== Creando estructura de directorios ===")
    
    directories = [
        "config",
        "gui", 
        "camera",
        "processing",
        "utils",
        "data/calibration",
        "data/captures",
        "data/results", 
        "resources/icons",
        "resources/styles",
        "logs"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        
        # Crear __init__.py para paquetes Python
        if directory in ["config", "gui", "camera", "processing", "utils"]:
            init_file = Path(directory) / "__init__.py"
            if not init_file.exists():
                init_file.write_text("# Paquete del sistema de fotogrametría estéreo\n")
    
    logger.info("Estructura de directorios creada")

def check_installation():
    """Verificar que la instalación fue exitosa"""
    logger.info("=== Verificando instalación ===")
    
    tests = [
        ("python3 -c 'import PyQt5; print(\"PyQt5 OK\")'", "PyQt5"),
        ("python3 -c 'import cv2; print(\"OpenCV OK\")'", "OpenCV"),
        ("python3 -c 'import numpy; print(\"NumPy OK\")'", "NumPy"),
        ("libcamera-hello --list-cameras", "libcamera"),
    ]
    
    all_ok = True
    for test_cmd, test_name in tests:
        logger.info(f"Verificando {test_name}...")
        result = run_command(test_cmd, check=False)
        if result.returncode == 0:
            logger.info(f"✓ {test_name} funciona correctamente")
        else:
            logger.error(f"✗ {test_name} no funciona")
            all_ok = False
    
    if all_ok:
        logger.info("✓ ¡Instalación completada exitosamente!")
    else:
        logger.warning("⚠ Instalación completada con algunos errores")
    
    return all_ok

def main():
    """Función principal de instalación"""
    logger.info("=== INSTALADOR DE SISTEMA DE FOTOGRAMETRÍA ESTÉREO CM5 ===")
    logger.info("Este script instalará todas las dependencias necesarias")
    
    # Verificar que estamos en Raspberry Pi
    try:
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read()
        if "raspberry" not in cpuinfo.lower():
            logger.warning("No se detectó Raspberry Pi, continuando de todas formas...")
    except:
        pass
    
    try:
        # Pasos de instalación
        update_system()
        install_system_packages()
        install_pip_packages()
        configure_camera()
        create_project_structure()
        
        # Verificación final
        success = check_installation()
        
        logger.info("\n" + "="*60)
        if success:
            logger.info("🎉 INSTALACIÓN COMPLETADA EXITOSAMENTE 🎉")
            logger.info("\nPara continuar:")
            logger.info("1. Reinicia el sistema: sudo reboot")
            logger.info("2. Después del reinicio, ejecuta: python3 main.py")
        else:
            logger.warning("⚠️  INSTALACIÓN COMPLETADA CON ERRORES")
            logger.info("Revisa los errores arriba y ejecuta manualmente los comandos fallidos")
        
        logger.info("="*60)
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        logger.info("\nInstalación cancelada por el usuario")
        return 1
    except Exception as e:
        logger.error(f"Error durante instalación: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())