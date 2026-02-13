#!/usr/bin/env python3
"""
Sistema de logging configurado para el proyecto de fotogrametría estéreo
Proporciona logging a archivo y consola con rotación automática
"""

import os
import sys
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime

# Intentar importar colorlog para logging colorizado
try:
    import colorlog
    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False

def setup_logger(name: str = None, level: str = "INFO", 
                log_dir: str = "logs", console_output: bool = True,
                file_output: bool = True) -> logging.Logger:
    """
    Configurar sistema de logging para la aplicación
    
    Args:
        name: Nombre del logger (None para root logger)
        level: Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directorio para archivos de log
        console_output: Habilitar salida a consola
        file_output: Habilitar salida a archivo
        
    Returns:
        Logger configurado
    """
    
    # Crear directorio de logs si no existe
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Obtener o crear logger
    if name is None:
        logger = logging.getLogger()
        logger_name = "stereo_photogrammetry"
    else:
        logger = logging.getLogger(name)
        logger_name = name
    
    # Evitar duplicar handlers si el logger ya está configurado
    if logger.handlers:
        return logger
    
    # Configurar nivel
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    
    # Formato base para logs
    base_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Handler para archivo con rotación
    if file_output:
        log_file = log_path / f"{logger_name}.log"
        
        # Usar RotatingFileHandler para evitar archivos muy grandes
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB máximo por archivo
            backupCount=5,           # Mantener 5 archivos históricos
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        
        # Formato detallado para archivos
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Handler para consola
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        
        if HAS_COLORLOG:
            # Usar colorlog si está disponible
            color_formatter = colorlog.ColoredFormatter(
                '%(log_color)s%(asctime)s - %(name)s - %(levelname)s%(reset)s - %(message)s',
                datefmt='%H:%M:%S',
                log_colors={
                    'DEBUG': 'cyan',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red,bg_white',
                }
            )
            console_handler.setFormatter(color_formatter)
        else:
            # Formato simple sin colores
            console_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
        
        logger.addHandler(console_handler)
    
    # Log inicial
    logger.info(f"Logger '{logger_name}' configurado - Nivel: {level}")
    
    return logger

def get_logger(name: str = None) -> logging.Logger:
    """
    Obtener logger configurado para un módulo específico
    
    Args:
        name: Nombre del módulo (__name__ típicamente)
        
    Returns:
        Logger configurado
    """
    if name is None:
        return logging.getLogger()
    
    logger = logging.getLogger(name)
    
    # Si no tiene handlers, usar configuración por defecto
    if not logger.handlers and not logging.getLogger().handlers:
        setup_logger()
    
    return logger

class PerformanceLogger:
    """Context manager para medir rendimiento de operaciones"""
    
    def __init__(self, operation_name: str, logger: logging.Logger = None):
        self.operation_name = operation_name
        self.logger = logger or get_logger(__name__)
        self.start_time = None
        
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.info(f"Iniciando: {self.operation_name}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            
            if exc_type is None:
                self.logger.info(f"Completado: {self.operation_name} ({duration:.2f}s)")
            else:
                self.logger.error(f"Falló: {self.operation_name} ({duration:.2f}s) - {exc_val}")

class LogCapture:
    """Capturar logs para mostrar en interfaz gráfica"""
    
    def __init__(self, logger_name: str = None, level: str = "INFO"):
        self.logger_name = logger_name
        self.level = getattr(logging, level.upper(), logging.INFO)
        self.captured_logs = []
        self.handler = None
        
    def start_capture(self):
        """Iniciar captura de logs"""
        logger = logging.getLogger(self.logger_name)
        
        # Crear handler personalizado
        self.handler = MemoryHandler(self.captured_logs)
        self.handler.setLevel(self.level)
        
        # Formato simple para captura
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.handler.setFormatter(formatter)
        
        logger.addHandler(self.handler)
        
    def stop_capture(self):
        """Detener captura de logs"""
        if self.handler:
            logger = logging.getLogger(self.logger_name)
            logger.removeHandler(self.handler)
            self.handler = None
            
    def get_logs(self) -> list:
        """Obtener logs capturados"""
        return self.captured_logs.copy()
        
    def clear_logs(self):
        """Limpiar logs capturados"""
        self.captured_logs.clear()

class MemoryHandler(logging.Handler):
    """Handler que almacena logs en memoria"""
    
    def __init__(self, memory_buffer: list):
        super().__init__()
        self.memory_buffer = memory_buffer
        
    def emit(self, record):
        try:
            msg = self.format(record)
            self.memory_buffer.append({
                'timestamp': datetime.fromtimestamp(record.created),
                'level': record.levelname,
                'message': record.getMessage(),
                'formatted': msg
            })
        except Exception:
            self.handleError(record)

def log_system_info():
    """Registrar información del sistema al iniciar"""
    logger = get_logger(__name__)
    
    try:
        import platform
        import psutil
        
        logger.info("=== INFORMACIÓN DEL SISTEMA ===")
        logger.info(f"Sistema: {platform.system()} {platform.release()}")
        logger.info(f"Arquitectura: {platform.machine()}")
        logger.info(f"Python: {platform.python_version()}")
        
        # Información de memoria
        memory = psutil.virtual_memory()
        logger.info(f"RAM Total: {memory.total / (1024**3):.1f} GB")
        logger.info(f"RAM Disponible: {memory.available / (1024**3):.1f} GB")
        
        # Información de almacenamiento
        disk = psutil.disk_usage('/')
        logger.info(f"Almacenamiento: {disk.free / (1024**3):.1f} GB libres de {disk.total / (1024**3):.1f} GB")
        
        # CPU
        logger.info(f"CPU: {psutil.cpu_count()} cores")
        
        # Verificar si es Raspberry Pi
        try:
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo = f.read()
                if 'raspberry' in cpuinfo.lower():
                    logger.info("Plataforma: Raspberry Pi detectado")
        except:
            pass
            
    except ImportError:
        logger.info("Información básica del sistema:")
        logger.info(f"Plataforma: {platform.system()} {platform.release()}")
    except Exception as e:
        logger.warning(f"Error obteniendo información del sistema: {e}")

def configure_opencv_logging():
    """Configurar logging de OpenCV para reducir ruido"""
    try:
        import cv2
        # Reducir verbosidad de OpenCV (solo disponible en algunas versiones)
        if hasattr(cv2, 'setLogLevel'):
            cv2.setLogLevel(0)  # Solo errores críticos

        logger = get_logger(__name__)
        logger.debug(f"OpenCV logging configurado - Versión: {cv2.__version__}")

    except (ImportError, AttributeError):
        pass

# Configuración por defecto al importar el módulo
if __name__ != "__main__":
    # Solo configurar si no estamos ejecutando este archivo directamente
    configure_opencv_logging()

if __name__ == "__main__":
    # Test del sistema de logging
    print("Probando sistema de logging...")
    
    # Configurar logger principal
    logger = setup_logger("test_logger", "DEBUG")
    
    # Probar diferentes niveles
    logger.debug("Mensaje de debug")
    logger.info("Mensaje informativo")
    logger.warning("Mensaje de advertencia")
    logger.error("Mensaje de error")
    
    # Probar performance logger
    with PerformanceLogger("Operación de prueba", logger):
        import time
        time.sleep(1)
    
    # Probar captura de logs
    print("\nProbando captura de logs...")
    capture = LogCapture("test_logger")
    capture.start_capture()
    
    logger.info("Log capturado 1")
    logger.warning("Log capturado 2")
    
    capture.stop_capture()
    
    captured = capture.get_logs()
    print(f"Logs capturados: {len(captured)}")
    for log in captured:
        print(f"  {log['level']}: {log['message']}")
    
    # Info del sistema
    log_system_info()
    
    print("✓ Sistema de logging funcionando correctamente")