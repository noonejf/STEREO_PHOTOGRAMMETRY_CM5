#!/usr/bin/env python3
"""
Script de verificación y demostración del sistema de fotogrametría estéreo CM5
Verifica que todos los componentes estén instalados y funcionando correctamente
"""

import os
import sys
import subprocess
import importlib
from pathlib import Path
from datetime import datetime

def print_header(title):
    """Imprimir encabezado formateado"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def print_status(check_name, status, details=""):
    """Imprimir estado de verificación"""
    status_symbol = "✅" if status else "❌"
    print(f"{status_symbol} {check_name}")
    if details:
        print(f"   └─ {details}")

def check_python_version():
    """Verificar versión de Python"""
    version = sys.version_info
    required_major, required_minor = 3, 9
    
    is_valid = version.major >= required_major and version.minor >= required_minor
    details = f"Versión actual: {version.major}.{version.minor}.{version.micro}"
    if not is_valid:
        details += f" (Requerido: {required_major}.{required_minor}+)"
    
    print_status("Versión de Python", is_valid, details)
    return is_valid

def check_system_commands():
    """Verificar comandos del sistema necesarios"""
    commands = {
        'libcamera-hello': 'libcamera-apps package',
        'python3': 'Python interpreter',
        'pip3': 'Python package installer'
    }
    
    all_good = True
    for cmd, description in commands.items():
        try:
            result = subprocess.run(['which', cmd], capture_output=True, text=True)
            exists = result.returncode == 0
            details = f"{description} - {result.stdout.strip() if exists else 'No encontrado'}"
            print_status(f"Comando: {cmd}", exists, details)
            all_good = all_good and exists
        except Exception as e:
            print_status(f"Comando: {cmd}", False, f"Error verificando: {e}")
            all_good = False
    
    return all_good

def check_python_packages():
    """Verificar paquetes Python necesarios"""
    packages = {
        'PyQt5': 'GUI framework',
        'cv2': 'OpenCV computer vision',
        'numpy': 'Numerical computing',
        'scipy': 'Scientific computing', 
        'sklearn': 'Machine learning (opcional)',
        'matplotlib': 'Plotting (opcional)'
    }
    
    all_critical_good = True
    optional_count = 0
    
    for package, description in packages.items():
        try:
            importlib.import_module(package)
            version = "N/A"
            
            # Intentar obtener versión
            try:
                mod = importlib.import_module(package)
                if hasattr(mod, '__version__'):
                    version = mod.__version__
                elif package == 'cv2':
                    version = mod.__version__
            except:
                pass
            
            print_status(f"Paquete: {package}", True, f"{description} - v{version}")
            
            if package in ['sklearn', 'matplotlib']:
                optional_count += 1
                
        except ImportError:
            is_optional = package in ['sklearn', 'matplotlib']
            print_status(f"Paquete: {package}", is_optional, 
                        f"{description} - {'Opcional' if is_optional else 'REQUERIDO'}")
            
            if not is_optional:
                all_critical_good = False
    
    return all_critical_good

def check_cameras():
    """Verificar cámaras disponibles"""
    try:
        result = subprocess.run(
            ['libcamera-hello', '--list-cameras'],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            output = result.stdout + result.stderr
            
            # Contar cámaras IMX477
            imx477_count = output.lower().count('imx477')
            
            if imx477_count >= 2:
                print_status("Cámaras Arducam HQ 477", True, f"{imx477_count} cámaras IMX477 detectadas")
                
                # Mostrar detalles de cámaras
                lines = output.split('\n')
                for line in lines:
                    if 'imx477' in line.lower():
                        print(f"   └─ {line.strip()}")
                        
                return True
            else:
                print_status("Cámaras Arducam HQ 477", False, 
                           f"Solo {imx477_count} cámaras IMX477 (se necesitan 2)")
                return False
        else:
            print_status("Cámaras Arducam HQ 477", False, 
                       f"Error ejecutando libcamera-hello: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print_status("Cámaras Arducam HQ 477", False, "Timeout verificando cámaras")
        return False
    except Exception as e:
        print_status("Cámaras Arducam HQ 477", False, f"Error: {e}")
        return False

def check_project_structure():
    """Verificar estructura del proyecto"""
    required_dirs = [
        'config',
        'gui', 
        'camera',
        'processing',
        'utils',
        'data',
        'data/calibration',
        'data/captures',
        'data/results'
    ]
    
    required_files = [
        'main.py',
        'requirements.txt',
        'config/camera_config.py',
        'gui/main_window.py',
        'camera/stereo_camera.py'
    ]
    
    all_good = True
    
    # Verificar directorios
    for dir_path in required_dirs:
        path = Path(dir_path)
        exists = path.exists() and path.is_dir()
        print_status(f"Directorio: {dir_path}", exists)
        all_good = all_good and exists
    
    # Verificar archivos
    for file_path in required_files:
        path = Path(file_path)
        exists = path.exists() and path.is_file()
        size = f"{path.stat().st_size} bytes" if exists else "No existe"
        print_status(f"Archivo: {file_path}", exists, size)
        all_good = all_good and exists
    
    return all_good

def check_configuration():
    """Verificar configuración del sistema"""
    config_checks = []
    
    # Verificar config.txt de Raspberry Pi
    config_paths = ['/boot/firmware/config.txt', '/boot/config.txt']
    config_file = None
    
    for path in config_paths:
        if Path(path).exists():
            config_file = path
            break
    
    if config_file:
        try:
            with open(config_file, 'r') as f:
                content = f.read()
            
            # Verificar configuraciones necesarias
            checks = {
                'camera_auto_detect=0': 'Detección automática deshabilitada',
                'dtoverlay=imx477': 'Overlay IMX477 habilitado',
                'start_x=1': 'Cámara habilitada'
            }
            
            all_config_good = True
            for check, description in checks.items():
                found = check in content
                print_status(f"Config: {check}", found, description)
                all_config_good = all_config_good and found
            
            return all_config_good
            
        except Exception as e:
            print_status("Configuración Raspberry Pi", False, f"Error leyendo {config_file}: {e}")
            return False
    else:
        print_status("Configuración Raspberry Pi", False, "config.txt no encontrado")
        return False

def check_system_resources():
    """Verificar recursos del sistema"""
    try:
        import psutil
        
        # Memoria
        memory = psutil.virtual_memory()
        memory_gb = memory.total / (1024**3)
        memory_good = memory_gb >= 2.0  # Mínimo 2GB
        print_status("Memoria RAM", memory_good, 
                    f"{memory_gb:.1f} GB total, {memory.percent}% usado")
        
        # Almacenamiento
        disk = psutil.disk_usage('/')
        disk_free_gb = disk.free / (1024**3)
        disk_good = disk_free_gb >= 5.0  # Mínimo 5GB libres
        print_status("Almacenamiento", disk_good,
                    f"{disk_free_gb:.1f} GB libres de {disk.total/(1024**3):.1f} GB")
        
        # CPU
        cpu_count = psutil.cpu_count()
        cpu_good = cpu_count >= 4  # Mínimo 4 cores
        print_status("CPU", cpu_good, f"{cpu_count} cores disponibles")
        
        return memory_good and disk_good and cpu_good
        
    except ImportError:
        print_status("Recursos del Sistema", False, "psutil no disponible para verificación")
        return False

def test_basic_functionality():
    """Probar funcionalidad básica del sistema"""
    try:
        # Intentar importar módulos principales
        sys.path.insert(0, '.')
        
        from config.camera_config import CameraConfig
        from utils.logger import get_logger
        
        # Test configuración
        config = CameraConfig()
        print_status("Configuración de cámaras", True, "CameraConfig inicializado")
        
        # Test logging
        logger = get_logger("test")
        logger.info("Test de logging")
        print_status("Sistema de logging", True, "Logger funcionando")
        
        return True
        
    except Exception as e:
        print_status("Funcionalidad básica", False, f"Error: {e}")
        return False

def generate_system_report():
    """Generar reporte del sistema"""
    report_path = Path("system_check_report.txt")
    
    with open(report_path, 'w') as f:
        f.write("REPORTE DE VERIFICACIÓN DEL SISTEMA\n")
        f.write("="*50 + "\n")
        f.write(f"Fecha: {datetime.now().isoformat()}\n")
        f.write(f"Sistema: {os.uname().sysname} {os.uname().release}\n")
        f.write(f"Arquitectura: {os.uname().machine}\n")
        f.write(f"Python: {sys.version}\n\n")
        
        # Información de cámaras
        try:
            result = subprocess.run(['libcamera-hello', '--list-cameras'], 
                                  capture_output=True, text=True, timeout=10)
            f.write("CÁMARAS DETECTADAS:\n")
            f.write(result.stdout)
            f.write("\n")
        except:
            f.write("Error obteniendo información de cámaras\n\n")
        
        # Información de paquetes
        f.write("PAQUETES PYTHON INSTALADOS:\n")
        try:
            result = subprocess.run([sys.executable, '-m', 'pip', 'list'], 
                                  capture_output=True, text=True)
            f.write(result.stdout)
        except:
            f.write("Error obteniendo lista de paquetes\n")
    
    print_status("Reporte generado", True, f"Guardado en {report_path}")

def main():
    """Función principal de verificación"""
    print_header("VERIFICACIÓN DEL SISTEMA DE FOTOGRAMETRÍA ESTÉREO CM5")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Directorio: {Path.cwd()}")
    
    # Lista de verificaciones
    checks = [
        ("Versión de Python", check_python_version),
        ("Comandos del Sistema", check_system_commands),
        ("Paquetes Python", check_python_packages),
        ("Estructura del Proyecto", check_project_structure),
        ("Configuración del Sistema", check_configuration),
        ("Recursos del Sistema", check_system_resources),
        ("Cámaras Arducam HQ 477", check_cameras),
        ("Funcionalidad Básica", test_basic_functionality)
    ]
    
    results = []
    
    # Ejecutar verificaciones
    for check_name, check_func in checks:
        print_header(check_name)
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print_status(check_name, False, f"Error inesperado: {e}")
            results.append((check_name, False))
    
    # Resumen final
    print_header("RESUMEN FINAL")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"Verificaciones pasadas: {passed}/{total}")
    print(f"Porcentaje de éxito: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("\n🎉 ¡TODAS LAS VERIFICACIONES PASARON!")
        print("El sistema está listo para usar. Ejecuta: python3 main.py")
    elif passed >= total * 0.8:  # 80% o más
        print("\n⚠️  SISTEMA MAYORMENTE FUNCIONAL")
        print("Hay algunos problemas menores, pero el sistema debería funcionar.")
        print("Revisa los elementos marcados con ❌ arriba.")
    else:
        print("\n❌ SISTEMA NO LISTO")
        print("Hay problemas críticos que deben resolverse antes del uso.")
        print("Revisa la documentación e instala los componentes faltantes.")
    
    # Generar reporte
    print_header("GENERANDO REPORTE")
    generate_system_report()
    
    print("\nPara obtener ayuda adicional:")
    print("1. Revisa README.md")
    print("2. Ejecuta: python3 install_setup.py")
    print("3. Verifica: libcamera-hello --list-cameras")
    
    return passed == total

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nVerificación cancelada por el usuario.")
        sys.exit(1)
    except Exception as e:
        print(f"\nError inesperado: {e}")
        sys.exit(1)