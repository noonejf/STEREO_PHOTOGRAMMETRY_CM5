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
║        🚀 SISTEMA DE FOTOGRAMETRÍA ESTÉREO CM5 🚀                           ║
║                                                                              ║
║        Para Raspberry Pi CM5 + Cámaras Arducam HQ 477                       ║
║        Diseñado para aplicaciones espaciales robustas                       ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)

def print_step(step_num, title, description=""):
    """Imprimir paso formateado"""
    print(f"\n📋 PASO {step_num}: {title}")
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
    print(f"🔄 Ejecutando: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    if description:
        print(f"   {description}")
    
    try:
        if isinstance(cmd, str):
            cmd = cmd.split()
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✅ Completado exitosamente")
            if result.stdout.strip():
                print(f"📄 Salida:\n{result.stdout}")
            return True
        else:
            print(f"❌ Error (código {result.returncode})")
            if result.stderr:
                print(f"📄 Error:\n{result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("⏰ Timeout - el comando tomó demasiado tiempo")
        return False
    except Exception as e:
        print(f"❌ Error ejecutando comando: {e}")
        return False

def check_basic_requirements():
    """Verificar requisitos básicos"""
    print_step(1, "VERIFICACIÓN DE REQUISITOS BÁSICOS")
    
    # Verificar que estamos en Raspberry Pi
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read().lower()
        
        if 'raspberry' in cpuinfo:
            print("✅ Raspberry Pi detectado")
        else:
            print("⚠️  No se detectó Raspberry Pi - continuando de todas formas")
    except:
        print("⚠️  No se pudo verificar hardware - continuando")
    
    # Verificar Python
    version = sys.version_info
    if version.major == 3 and version.minor >= 9:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro} - Compatible")
    else:
        print(f"❌ Python {version.major}.{version.minor} - Se requiere Python 3.9+")
        return False
    
    # Verificar permisos
    if os.geteuid() == 0:
        print("⚠️  Ejecutándose como root - no recomendado para uso normal")
    else:
        print("✅ Ejecutándose como usuario normal")
    
    return True

def install_system():
    """Instalar el sistema"""
    print_step(2, "INSTALACIÓN DEL SISTEMA")
    
    if not Path("install_setup.py").exists():
        print("❌ Archivo install_setup.py no encontrado")
        print("   Asegúrate de ejecutar este script desde el directorio del proyecto")
        return False
    
    if ask_yes_no("¿Ejecutar instalación automática?"):
        print("\n🚀 Iniciando instalación automática...")
        print("   Esto puede tomar varios minutos...")
        
        success = run_command_with_output(
            [sys.executable, "install_setup.py"],
            "Instalar dependencias y configurar sistema"
        )
        
        if success:
            print("\n✅ Instalación completada")
            print("⚠️  IMPORTANTE: Se requiere reinicio para activar las cámaras")
            
            if ask_yes_no("¿Reiniciar ahora?", "n"):
                print("🔄 Reiniciando sistema...")
                subprocess.run(["sudo", "reboot"])
                return True
            else:
                print("⚠️  Recuerda reiniciar antes de usar las cámaras")
                return True
        else:
            print("❌ Error durante la instalación")
            return False
    else:
        print("⏭️  Saltando instalación automática")
        return True

def verify_system():
    """Verificar el sistema"""
    print_step(3, "VERIFICACIÓN DEL SISTEMA")
    
    if not Path("demo_system_check.py").exists():
        print("⚠️  Script de verificación no encontrado")
        return True
    
    if ask_yes_no("¿Ejecutar verificación completa del sistema?"):
        success = run_command_with_output(
            [sys.executable, "demo_system_check.py"],
            "Verificar todos los componentes del sistema"
        )
        
        if success:
            print("✅ Verificación completada - revisa la salida arriba")
        else:
            print("⚠️  Problemas detectados - revisa los errores arriba")
        
        return success
    else:
        print("⏭️  Saltando verificación del sistema")
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
    
    # Probar captura rápida
    if ask_yes_no("¿Probar captura rápida con cámara 0?"):
        test_success = run_command_with_output(
            ["libcamera-jpeg", "--camera", "0", "-o", "test_cam0.jpg", "-t", "2000"],
            "Capturar imagen de prueba"
        )
        
        if test_success and Path("test_cam0.jpg").exists():
            print("✅ Captura exitosa - test_cam0.jpg creado")
            
            # Limpiar archivo de prueba
            try:
                Path("test_cam0.jpg").unlink()
                print("🗑️  Archivo de prueba eliminado")
            except:
                pass
        else:
            print("❌ Error en captura de prueba")
            return False
    
    return True

def show_usage_guide():
    """Mostrar guía de uso"""
    print_step(5, "GUÍA DE USO RÁPIDO")
    
    guide = """
📚 FLUJO DE TRABAJO RECOMENDADO:

1️⃣  PRIMERA VEZ - CALIBRACIÓN:
   • Ejecuta: python3 main.py
   • Presiona "🎯 Calibrar Cámaras"
   • Prepara tablero de ajedrez 10x7 cuadrados
   • Sigue las instrucciones del countdown
   • Mueve el tablero a diferentes posiciones durante las 25 capturas

2️⃣  CAPTURA DE OBJETO 3D:
   • Asegúrate de que muestra "✅ Sistema Calibrado"
   • Posiciona tu objeto en el campo de visión
   • Presiona "📸 Capturar para Modelo 3D"
   • Espera el countdown de 10 segundos

3️⃣  PROCESAMIENTO 3D:
   • Presiona "⚙️ Procesar Últimas Capturas"
   • Selecciona algoritmo SGBM (recomendado)
   • Elige formatos de exportación (PLY recomendado)
   • Presiona "🚀 Iniciar Procesamiento"

4️⃣  RESULTADOS:
   • Los archivos se guardan en data/results/
   • Puedes ver mapas de disparidad y profundidad
   • Las estadísticas muestran calidad del resultado

⚠️  IMPORTANTE:
   • NO muevas las cámaras después de calibrar
   • Usa iluminación uniforme sin reflejos
   • Para mejores resultados, objetos con textura visible
   • El tablero debe estar completamente plano
"""
    
    print(guide)
    
    input("\n📖 Presiona Enter para continuar...")

def show_troubleshooting():
    """Mostrar guía de solución de problemas"""
    print_step(6, "SOLUCIÓN DE PROBLEMAS COMUNES")
    
    troubleshooting = """
🔧 PROBLEMAS COMUNES Y SOLUCIONES:

❌ "No se detectaron cámaras"
   ✅ Verificar cables CSI conectados firmemente
   ✅ Reiniciar: sudo reboot  
   ✅ Verificar config.txt: cat /boot/firmware/config.txt | grep imx477

❌ "Error iniciando vista previa"
   ✅ Cerrar otras aplicaciones que usen cámaras
   ✅ Probar: libcamera-hello --camera 0 -t 2000
   ✅ Verificar permisos de usuario

❌ "Calibración falla repetidamente"
   ✅ Usar tablero 10x7 cuadrados (9x6 esquinas internas)
   ✅ Iluminación uniforme, sin reflejos
   ✅ Tablero completamente plano
   ✅ Mover a diferentes ángulos y distancias

❌ "Procesamiento 3D muy lento"
   ✅ Usar algoritmo BM en lugar de SGBM
   ✅ Reducir resolución de captura
   ✅ Cerrar aplicaciones innecesarias

❌ "PyQt5 no funciona"
   ✅ Instalar: sudo apt install python3-pyqt5
   ✅ NO usar pip install pyqt5 en Raspberry Pi

📞 OBTENER AYUDA:
   • Revisar logs: tail -f logs/stereo_photogrammetry.log
   • Ejecutar verificación: python3 demo_system_check.py
   • Revisar README.md para más detalles
"""
    
    print(troubleshooting)
    input("\n📖 Presiona Enter para continuar...")

def launch_application():
    """Lanzar aplicación principal"""
    print_step(7, "INICIAR APLICACIÓN")
    
    if not Path("main.py").exists():
        print("❌ main.py no encontrado")
        print("   Asegúrate de ejecutar desde el directorio del proyecto")
        return False
    
    if ask_yes_no("¿Iniciar la aplicación principal ahora?"):
        print("\n🚀 Iniciando aplicación de fotogrametría estéreo...")
        print("   Se abrirá la ventana principal del sistema")
        print("   Presiona Ctrl+C para cancelar si hay problemas")
        
        try:
            # Ejecutar aplicación principal
            subprocess.run([sys.executable, "main.py"])
            return True
        except KeyboardInterrupt:
            print("\n⏹️  Aplicación cancelada por el usuario")
            return False
        except Exception as e:
            print(f"\n❌ Error iniciando aplicación: {e}")
            return False
    else:
        print("\n📝 Para iniciar manualmente más tarde:")
        print("   cd " + str(Path.cwd()))
        print("   python3 main.py")
        return True

def main():
    """Función principal del script de inicio rápido"""
    print_banner()
    
    print("¡Bienvenido al sistema de fotogrametría estéreo para CM5!")
    print("Este asistente te guiará through la configuración inicial.")
    print(f"Directorio actual: {Path.cwd()}")
    
    if not ask_yes_no("\n¿Continuar con la configuración guiada?"):
        print("👋 ¡Hasta luego! Ejecuta 'python3 main.py' cuando estés listo.")
        return 0
    
    # Ejecutar pasos
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
                if ask_yes_no("¿Continuar a pesar del error?", "n"):
                    continue
                else:
                    print("\n⏹️  Configuración cancelada")
                    print("   Puedes ejecutar este script nuevamente más tarde")
                    return 1
        
        print("\n🎉 ¡CONFIGURACIÓN COMPLETADA!")
        print("   El sistema está listo para usar")
        print("   Ejecuta 'python3 main.py' para iniciar")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Configuración cancelada por el usuario")
        print("   Puedes ejecutar este script nuevamente más tarde")
        return 1
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        print("   Revisa la documentación o ejecuta el script nuevamente")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        print(f"Error crítico: {e}")
        sys.exit(1)