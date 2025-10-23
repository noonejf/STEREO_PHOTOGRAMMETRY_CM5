#!/usr/bin/env python3
"""
Sistema de cámaras estéreo para Arducam HQ 477 (IMX477)
Maneja captura sincronizada y operaciones estéreo en Raspberry Pi CM5
"""

import os
import cv2
import numpy as np
import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

from utils.logger import get_logger

logger = get_logger(__name__)

class StereoCamera:
    """Sistema principal de cámaras estéreo"""
    
    def __init__(self, camera_config):
        """Inicializar sistema de cámaras estéreo"""
        self.config = camera_config
        self.left_camera_id = camera_config.left_camera.camera_id
        self.right_camera_id = camera_config.right_camera.camera_id
        
        # Estado del sistema
        self.is_initialized = False
        self.capture_in_progress = False
        
        # Directorios de captura
        self.capture_dir = Path("data/captures")
        self.calibration_dir = Path("data/calibration")
        self.results_dir = Path("data/results")
        
        # Crear directorios si no existen
        for directory in [self.capture_dir, self.calibration_dir, self.results_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Verificar disponibilidad de cámaras
        self.verify_cameras()
        
        # Configuraciones de captura
        self.capture_settings = self.config.get_capture_settings()
        
        self.is_initialized = True
        logger.info("Sistema de cámaras estéreo inicializado")
    
    def verify_cameras(self):
        """Verificar que las cámaras estén disponibles"""
        try:
            result = subprocess.run(
                ["libcamera-hello", "--list-cameras"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            output = result.stdout + result.stderr
            
            if result.returncode != 0:
                raise RuntimeError(f"Error ejecutando libcamera-hello: {output}")
            
            if "No cameras available" in output:
                raise RuntimeError("No se detectaron cámaras")
            
            # Verificar cámaras específicas
            cameras_found = []
            lines = output.split('\n')
            for line in lines:
                if f": imx477" in line.lower() or f": IMX477" in line.lower():
                    # Extraer ID de cámara
                    if line.strip().startswith(str(self.left_camera_id)):
                        cameras_found.append(self.left_camera_id)
                    elif line.strip().startswith(str(self.right_camera_id)):
                        cameras_found.append(self.right_camera_id)
            
            missing_cameras = []
            if self.left_camera_id not in cameras_found:
                missing_cameras.append(f"CAM{self.left_camera_id}")
            if self.right_camera_id not in cameras_found:
                missing_cameras.append(f"CAM{self.right_camera_id}")
            
            if missing_cameras:
                raise RuntimeError(f"Cámaras no encontradas: {', '.join(missing_cameras)}")
            
            logger.info(f"Cámaras verificadas: CAM{self.left_camera_id}, CAM{self.right_camera_id}")
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("Timeout verificando cámaras")
        except Exception as e:
            raise RuntimeError(f"Error verificando cámaras: {e}")

    def create_calibration_session_dir(self):
        """Crea un nuevo directorio de sesión de calibración y devuelve la ruta."""
        session_dir = Path(self.config.stereo.calibration_data_path) / f"calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Directorio de sesión de calibración creado: {session_dir}")
        self.current_session_dir = session_dir  # Guardar para referencia
        return str(session_dir)

    def capture_single_calibration_pair(self, session_dir, pair_index):
        """Captura y guarda un solo par de imágenes de calibración en alta calidad."""
        try:
            # 1. Definir nombres de archivo finales (donde queremos las fotos)
            left_path = Path(session_dir) / f"left_{pair_index:03d}.jpg"
            right_path = Path(session_dir) / f"right_{pair_index:03d}.jpg"

            # 2. Definir el nombre para capture_stereo_pair (que crea un subdirectorio)
            # Extraer el nombre de la sesión (ej: "calibration_20251020_184000")
            session_name = Path(session_dir).name
            pair_sub_name = f"calib_pair_{pair_index:03d}"
            # El nombre completo de la captura será ej: "calibration_20251020_184000/calib_pair_000"
            full_capture_name = f"{session_name}/{pair_sub_name}"

            # 3. Llamar a tu función de captura estéreo existente (pasando _internal_call=True)
            logger.info(f"Llamando a capture_stereo_pair(name={full_capture_name}, _internal_call=True)")
            result = self.capture_stereo_pair(full_capture_name, _internal_call=True)

            if not result['success']:
                raise Exception(f"capture_stereo_pair falló: {result.get('error', 'Error desconocido')}")

            # 4. Copiar los archivos desde el subdirectorio (ej: .../calib_pair_000/left.jpg)
            #    al directorio raíz de la sesión (ej: .../calibration_20251020_184000/left_000.jpg)
            import shutil
            shutil.copy2(result['left_file'], left_path)
            shutil.copy2(result['right_file'], right_path)

            logger.info(f"Par {pair_index} copiado a {session_dir}")
            return True
        
        except Exception as e:
            logger.error(f"Error capturando par {pair_index}: {e}")
            raise e  # Re-lanzar para que el diálogo lo atrape
    
    def capture_single_image(self, camera_id: int, output_file: str,
                           delay_ms: int = 2000, operation: str = "capture") -> bool: # <--- AÑADIDO operation="capture"
        """Capturar una sola imagen de una cámara específica"""
        try:
            # Crear comando libcamera-jpeg USANDO el parámetro 'operation'
            cmd = self.config.get_libcamera_cmd(
                camera_id=camera_id,
                operation=operation, # <--- USAR EL PARÁMETRO operation
                duration_ms=delay_ms,
                output_file=output_file
            )

            # --- El resto de la función sigue igual ---
            logger.info(f"Capturando CAM{camera_id} (Op: {operation}): {cmd}") # Log modificado para ver la operación

            # Ejecutar comando
            result = subprocess.run(
                cmd.split(),
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.error(f"Error capturando CAM{camera_id}: {result.stderr}")
                return False

            # Verificar que el archivo se creó
            if not Path(output_file).exists():
                logger.error(f"Archivo de captura no creado: {output_file}")
                return False

            # Verificar que el archivo tiene contenido
            file_size = Path(output_file).stat().st_size
            if file_size < 1000:  # Menos de 1KB probablemente es error
                logger.error(f"Archivo de captura muy pequeño: {file_size} bytes")
                return False

            logger.info(f"Captura exitosa CAM{camera_id}: {output_file} ({file_size} bytes)")
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout capturando CAM{camera_id}")
            return False
        except Exception as e:
            logger.error(f"Error capturando CAM{camera_id}: {e}")
            return False
        
    def capture_stereo_pair(self, capture_name: Optional[str] = None, _internal_call: bool = False) -> Dict[str, Any]:
        """Capturar par estéreo sincronizado"""

        # DEBUG: Estado inicial
        logger.info(f"🔍 DEBUG capture_stereo_pair - INICIO:")
        logger.info(f"🔍   capture_name: {capture_name}")
        logger.info(f"🔍   _internal_call: {_internal_call}")
        logger.info(f"🔍   capture_in_progress ANTES: {self.capture_in_progress}")

        # SOLO verificar si NO es llamada interna
        if not _internal_call and self.capture_in_progress:
            logger.error(f"🚨 DEBUG: Rechazando captura - capture_in_progress=True y _internal_call=False")
            raise RuntimeError("Captura ya en progreso")

        # SOLO poner la bandera si NO es llamada interna
        if not _internal_call:
            self.capture_in_progress = True
            logger.info(f"🔧 DEBUG: Bandera capture_in_progress puesta a TRUE (external call)")
        else:
            logger.info(f"🔧 DEBUG: NO poniendo bandera - es llamada interna")

        # DETERMINAR LA OPERACIÓN BASADO EN LA LLAMADA
        current_operation = "calibration" if _internal_call else "capture"
        logger.info(f"⚙️ DEBUG: Operación determinada: {current_operation}")

        try:
            # Generar nombre de captura si no se proporciona
            if not capture_name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                capture_name = f"stereo_{timestamp}"

            logger.info(f"🎯 DEBUG: Nombre final de captura: {capture_name}")

            # FIX: Determinar directorio base según el tipo de llamada
            if _internal_call:
                 # Necesitamos manejar tanto el nombre de sesión como el nombre de par individual
                 # Si capture_name contiene '/', es un par individual dentro de una sesión
                 if '/' in capture_name:
                     # Caso: "calibration_YYYYMMDD_HHMMSS/calib_pair_XXX"
                     # El directorio base es el nombre de la sesión
                     session_name = capture_name.split('/')[0]
                     if session_name.startswith("calibration_"):
                         base_dir = self.calibration_dir
                     else:
                          # Si no empieza con calibration_, usar captures (aunque no debería pasar)
                          base_dir = self.capture_dir
                     # El directorio completo incluye el subdirectorio del par
                     capture_session_dir = base_dir / capture_name

                 else:
                     # Caso: "calibration_YYYYMMDD_HHMMSS" (raro que se llame así con _internal_call=True)
                     # Asumimos que es el directorio de sesión completo
                     capture_session_dir = self.calibration_dir / capture_name
                 logger.info(f"🗂️ DEBUG (Internal Call): Usando directorio: {capture_session_dir}")

            else:
                # Para capturas normales, usar directorio captures
                capture_session_dir = self.capture_dir / capture_name
                logger.info(f"🗂️ DEBUG (External Call): Usando directorio captures: {capture_session_dir}")


            # Crear directorio (con parents=True para crear subdirectorios si es necesario)
            capture_session_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"🗂️ DEBUG: Directorio creado/asegurado: {capture_session_dir}")

            # Archivos de salida
            left_file = capture_session_dir / "left.jpg"
            # ----- LA CORRECCIÓN DE LA COMILLA YA ESTÁ AQUÍ -----
            right_file = capture_session_dir / "right.jpg" # <--- Comilla añadida

            logger.info(f"Iniciando captura estéreo: {capture_name}")
            logger.info(f"🗂️ DEBUG: Archivos de salida:")
            logger.info(f"🗂️   Left: {left_file}")
            logger.info(f"🗂️   Right: {right_file}")

            # Captura casi-simultánea usando hilos
            capture_results = {}

            # MODIFICACIÓN: El wrapper ahora necesita aceptar 'operation'
            def capture_wrapper(camera_id, output_file, results_dict, operation): # <--- AÑADIDO operation
                """Wrapper para captura en hilo"""
                logger.info(f"🏃 DEBUG: Iniciando hilo captura CAM{camera_id} (Op: {operation})")
                start_time = time.time()
                # Pasar la operation a capture_single_image
                # Usamos un timeout corto (delay_ms=2000) por defecto en capture_single_image
                success = self.capture_single_image(camera_id, str(output_file), delay_ms=2000, operation=operation) # <--- PASAR operation
                end_time = time.time()

                results_dict[camera_id] = {
                    'success': success,
                    'file': str(output_file),
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': end_time - start_time
                }
                logger.info(f"✅ DEBUG: Hilo CAM{camera_id} terminado - Success: {success}")

            # Crear hilos de captura, pasando la 'current_operation'
            left_thread = threading.Thread(
                target=capture_wrapper,
                args=(self.left_camera_id, left_file, capture_results, current_operation) # <--- PASAR current_operation
            )
            right_thread = threading.Thread(
                target=capture_wrapper,
                args=(self.right_camera_id, right_file, capture_results, current_operation) # <--- PASAR current_operation
            )

            # Iniciar capturas de forma muy cercana en tiempo
            start_capture_time = time.time()
            logger.info(f"🚀 DEBUG: Iniciando hilos de captura...")
            left_thread.start()
            time.sleep(0.01)  # Delay mínimo para evitar conflicto de recursos
            right_thread.start()

            # Esperar a que terminen ambas capturas
            logger.info(f"⏳ DEBUG: Esperando hilos...")
            left_thread.join(timeout=40)
            right_thread.join(timeout=40)

            # Verificar resultados
            if self.left_camera_id not in capture_results:
                 # Añadir logs extra para depurar timeout
                 logger.error(f"🚨 DEBUG: Hilo CAM{self.left_camera_id} no completó. ¿Timeout?")
                 if left_thread.is_alive():
                     logger.warning(f" Hilo CAM{self.left_camera_id} todavía está vivo.")
                 raise RuntimeError("Captura de cámara izquierda no completada (posible timeout)")

            if self.right_camera_id not in capture_results:
                 logger.error(f"🚨 DEBUG: Hilo CAM{self.right_camera_id} no completó. ¿Timeout?")
                 if right_thread.is_alive():
                     logger.warning(f" Hilo CAM{self.right_camera_id} todavía está vivo.")
                 raise RuntimeError("Captura de cámara derecha no completada (posible timeout)")


            left_result = capture_results[self.left_camera_id]
            right_result = capture_results[self.right_camera_id]

            logger.info(f"📊 DEBUG: Resultados de captura:")
            logger.info(f"📊   Left success: {left_result['success']}")
            logger.info(f"📊   Right success: {right_result['success']}")

            if not (left_result['success'] and right_result['success']):
                failed_cameras = []
                if not left_result['success']:
                    failed_cameras.append("izquierda")
                if not right_result['success']:
                    failed_cameras.append("derecha")
                # Añadir más detalles al error
                error_detail = f"Falló captura. Left: {left_result['success']}, Right: {right_result['success']}"
                logger.error(f"🚨 DEBUG: {error_detail}")
                raise RuntimeError(f"Falló captura de cámara(s): {', '.join(failed_cameras)}. Detalles: {error_detail}")


            # Calcular sincronización
            time_diff = abs(left_result['start_time'] - right_result['start_time'])
            sync_quality = "EXCELENTE" if time_diff < 0.05 else "BUENA" if time_diff < 0.1 else "ACEPTABLE"

            logger.info(f"⏱️ DEBUG: Sincronización: {time_diff*1000:.1f}ms ({sync_quality})")

            # Verificar y cargar imágenes
            left_image = cv2.imread(str(left_file))
            right_image = cv2.imread(str(right_file))

            if left_image is None:
                 # Intentar verificar si el archivo existe y tiene tamaño > 0
                 if Path(left_file).exists() and Path(left_file).stat().st_size > 0:
                      logger.error(f"🚨 DEBUG: Archivo left.jpg existe ({Path(left_file).stat().st_size} bytes) pero cv2.imread falló.")
                      raise RuntimeError(f"No se pudo cargar imagen izquierda (archivo existe pero no se pudo decodificar): {left_file}")
                 else:
                      logger.error(f"🚨 DEBUG: Archivo left.jpg NO existe o está vacío.")
                      raise RuntimeError(f"No se pudo cargar imagen izquierda (archivo no existe o vacío): {left_file}")

            if right_image is None:
                 if Path(right_file).exists() and Path(right_file).stat().st_size > 0:
                      logger.error(f"🚨 DEBUG: Archivo right.jpg existe ({Path(right_file).stat().st_size} bytes) pero cv2.imread falló.")
                      raise RuntimeError(f"No se pudo cargar imagen derecha (archivo existe pero no se pudo decodificar): {right_file}")
                 else:
                      logger.error(f"🚨 DEBUG: Archivo right.jpg NO existe o está vacío.")
                      raise RuntimeError(f"No se pudo cargar imagen derecha (archivo no existe o vacío): {right_file}")


            # Verificar resoluciones
            left_shape = left_image.shape
            right_shape = right_image.shape

            if left_shape != right_shape:
                logger.warning(f"Resoluciones diferentes: Izq{left_shape} != Der{right_shape}")

            # Crear metadata de captura
            metadata = {
                'capture_name': capture_name,
                'timestamp': datetime.now().isoformat(),
                'left_camera': {
                    'id': self.left_camera_id,
                    'file': str(left_file),
                     # Convertir shape a lista para JSON
                    'resolution': list(left_shape),
                    'size_bytes': Path(left_file).stat().st_size,
                    'capture_time': left_result['duration']
                },
                'right_camera': {
                    'id': self.right_camera_id,
                    'file': str(right_file),
                     # Convertir shape a lista para JSON
                    'resolution': list(right_shape),
                    'size_bytes': Path(right_file).stat().st_size,
                    'capture_time': right_result['duration']
                },
                'synchronization': {
                    'time_difference_ms': time_diff * 1000,
                    'quality': sync_quality,
                    'acceptable': time_diff < self.config.stereo.sync_tolerance_ms / 1000
                },
                'camera_config': {
                    'baseline_mm': self.config.stereo.baseline_mm,
                    # ----- LA CORRECCIÓN ESTÁ AQUÍ -----
                    # Usar la función que acabamos de añadir en CameraConfig
                    'capture_resolution_used': self.config.get_capture_settings_for_op(current_operation)['resolution']
                }
            }


            # Guardar metadata
            metadata_file = capture_session_dir / "metadata.json"
            try:
                 with open(metadata_file, 'w') as f:
                     import json
                     # Usar default=str para manejar tipos no serializables si surgen
                     json.dump(metadata, f, indent=4, default=str)
                 logger.info(f"📝 DEBUG: Metadata guardada en {metadata_file}")
            except Exception as json_err:
                 logger.error(f"🚨 DEBUG: ¡Error al guardar metadata.json!: {json_err}")
                 # Continuar de todas formas, pero registrar el error


            logger.info(f"Captura estéreo completada: {capture_name}")
            logger.info(f"Sincronización: {time_diff*1000:.1f}ms ({sync_quality})")
            logger.info(f"Archivos: {left_file.name}, {right_file.name}")

            return {
                'success': True,
                'capture_name': capture_name,
                'session_dir': str(capture_session_dir),
                'left_file': str(left_file),
                'right_file': str(right_file),
                'metadata': metadata,
                'left_image': left_image,
                'right_image': right_image
            }

        except Exception as e:
            logger.error(f"🚨 DEBUG: Error en captura estéreo: {e}", exc_info=True) # exc_info=True para traceback completo
            # Construir un mensaje de error más detallado
            error_type = type(e).__name__
            error_message = f"{error_type}: {e}"
            logger.error(f" Detalle del error: {error_message}")
            return {
                'success': False,
                'error': error_message # Devolver el mensaje detallado
            }


        finally:
            # SOLO limpiar bandera si NO es llamada interna
            if not _internal_call:
                self.capture_in_progress = False
                logger.info(f"🧹 DEBUG: Bandera capture_in_progress puesta a FALSE (external call)")
            else:
                logger.info(f"🧹 DEBUG: NO limpiando bandera - es llamada interna")

            logger.info(f"🔍 DEBUG capture_stereo_pair - FIN:")
            logger.info(f"🔍   capture_in_progress DESPUÉS: {self.capture_in_progress}")
            
    
    def capture_calibration_images(self, num_images: int = 25, 
                                delay_between_captures: float = 2.0) -> Dict[str, Any]:
        """Capturar serie de imágenes para calibración"""
        
        # 🐛 DEBUG: Estado inicial
        logger.info(f"🔍 DEBUG capture_calibration_images - INICIO:")
        logger.info(f"🔍   num_images: {num_images}")
        logger.info(f"🔍   delay_between_captures: {delay_between_captures}")
        logger.info(f"🔍   capture_in_progress ANTES: {self.capture_in_progress}")
        
        if self.capture_in_progress:
            logger.error(f"🚨 DEBUG: Rechazando calibración - capture_in_progress=True")
            raise RuntimeError("Captura ya en progreso")
        
        self.capture_in_progress = True
        logger.info(f"🔧 DEBUG: Bandera capture_in_progress puesta a TRUE para calibración")
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            calibration_session = f"calibration_{timestamp}"
            
            logger.info(f"🎯 DEBUG: Sesión de calibración: {calibration_session}")
            
            # Crear directorio para calibración
            calib_dir = self.calibration_dir / calibration_session
            calib_dir.mkdir(exist_ok=True)
            
            logger.info(f"🗂️ DEBUG: Directorio calibración: {calib_dir}")
            logger.info(f"Iniciando captura de calibración: {num_images} imágenes")
            
            captured_pairs = []
            failed_captures = 0
            
            for i in range(num_images):
                try:
                    logger.info(f"🔄 DEBUG: === LOOP {i+1}/{num_images} ===")
                    logger.info(f"Capturando par de calibración {i+1}/{num_images}")
                    
                    # Nombres de archivos para este par
                    left_file = calib_dir / f"left_{i:03d}.jpg"
                    right_file = calib_dir / f"right_{i:03d}.jpg"
                    
                    logger.info(f"🗂️ DEBUG: Archivos par {i+1}:")
                    logger.info(f"🗂️   Left: {left_file}")
                    logger.info(f"🗂️   Right: {right_file}")
                    
                    # Capturar par - ✅ CAMBIO CRÍTICO: _internal_call=True
                    pair_name = f"calib_pair_{i:03d}"
                    full_pair_name = f"{calibration_session}/{pair_name}"
                    
                    logger.info(f"🎯 DEBUG: Llamando capture_stereo_pair con _internal_call=True")
                    logger.info(f"🎯   Nombre completo: {full_pair_name}")
                    
                    # ✅ LÍNEA CRÍTICA MODIFICADA
                    result = self.capture_stereo_pair(full_pair_name, _internal_call=True)
                    
                    logger.info(f"📊 DEBUG: Resultado captura par {i+1}: {result.get('success', False)}")
                    
                    if result['success']:
                        # Copiar archivos al directorio de calibración con nombres secuenciales
                        import shutil
                        logger.info(f"📁 DEBUG: Copiando archivos...")
                        logger.info(f"📁   From: {result['left_file']} -> To: {left_file}")
                        logger.info(f"📁   From: {result['right_file']} -> To: {right_file}")
                        
                        shutil.copy2(result['left_file'], left_file)
                        shutil.copy2(result['right_file'], right_file)
                        
                        captured_pairs.append({
                            'index': i,
                            'left_file': str(left_file),
                            'right_file': str(right_file),
                            'metadata': result['metadata']
                        })
                        
                        logger.info(f"✅ DEBUG: Par {i+1} capturado exitosamente")
                    else:
                        failed_captures += 1
                        logger.error(f"❌ DEBUG: Error capturando par {i+1}: {result.get('error', 'Desconocido')}")
                        
                        # Si fallan muchas capturas consecutivas, abortar
                        if failed_captures >= 3:
                            logger.error(f"🚨 DEBUG: Demasiadas capturas fallidas ({failed_captures}) - ABORTANDO")
                            raise RuntimeError("Demasiadas capturas fallidas consecutivas")
                    
                    # Pausa entre capturas si no es la última
                    if i < num_images - 1:
                        logger.info(f"⏳ DEBUG: Pausa entre capturas: {delay_between_captures}s")
                        time.sleep(delay_between_captures)
                        
                except KeyboardInterrupt:
                    logger.info("🛑 DEBUG: Captura de calibración interrumpida por usuario")
                    break
                except Exception as e:
                    failed_captures += 1
                    logger.error(f"🚨 DEBUG: Error en par {i+1}: {e}")
                    
                    if failed_captures >= 3:
                        logger.error(f"🚨 DEBUG: Demasiados errores - RE-RAISING")
                        raise
            
            # Crear resumen de calibración
            calibration_summary = {
                'session': calibration_session,
                'timestamp': datetime.now().isoformat(),
                'total_requested': num_images,
                'total_captured': len(captured_pairs),
                'failed_captures': failed_captures,
                'success_rate': len(captured_pairs) / num_images * 100,
                'session_dir': str(calib_dir),
                'captured_pairs': captured_pairs,
                'camera_config': {
                    'left_camera_id': self.left_camera_id,
                    'right_camera_id': self.right_camera_id,
                    'baseline_mm': self.config.stereo.baseline_mm,
                    'capture_resolution': self.capture_settings['left_resolution']
                }
            }
            
            logger.info(f"📋 DEBUG: Resumen final de calibración:")
            logger.info(f"📋   Solicitadas: {num_images}")
            logger.info(f"📋   Capturadas: {len(captured_pairs)}")
            logger.info(f"📋   Fallidas: {failed_captures}")
            logger.info(f"📋   Tasa éxito: {calibration_summary['success_rate']:.1f}%")
            
            # Guardar resumen
            summary_file = calib_dir / "calibration_summary.json"
            with open(summary_file, 'w') as f:
                import json
                json.dump(calibration_summary, f, indent=4)
            
            success = len(captured_pairs) >= self.config.stereo.min_calibration_images
            
            logger.info(f"Captura de calibración completada:")
            logger.info(f"  Pares capturados: {len(captured_pairs)}/{num_images}")
            logger.info(f"  Tasa de éxito: {calibration_summary['success_rate']:.1f}%")
            logger.info(f"  Calibración viable: {'SÍ' if success else 'NO'}")
            
            return {
                'success': success,
                'session': calibration_session,
                'session_dir': str(calib_dir),
                'summary': calibration_summary,
                'message': f"Capturados {len(captured_pairs)} de {num_images} pares necesarios"
            }
            
        except Exception as e:
            logger.error(f"🚨 DEBUG: Error en captura de calibración: {e}")
            return {
                'success': False,
                'error': str(e)
            }
        
        finally:
            self.capture_in_progress = False
            logger.info(f"🧹 DEBUG: Bandera capture_in_progress puesta a FALSE al final de calibración")
            logger.info(f"🔍 DEBUG capture_calibration_images - FIN:")
            logger.info(f"🔍   capture_in_progress DESPUÉS: {self.capture_in_progress}")
    
    def get_last_capture_info(self) -> Optional[Dict[str, Any]]:
        """Obtener información de la última captura realizada"""
        try:
            # Buscar directorios de captura más recientes
            capture_dirs = [d for d in self.capture_dir.iterdir() if d.is_dir()]
            
            if not capture_dirs:
                return None
            
            # Ordenar por tiempo de modificación
            latest_dir = max(capture_dirs, key=lambda d: d.stat().st_mtime)
            
            # Buscar metadata
            metadata_file = latest_dir / "metadata.json"
            if not metadata_file.exists():
                return None
            
            with open(metadata_file, 'r') as f:
                import json
                metadata = json.load(f)
            
            return {
                'session_dir': str(latest_dir),
                'capture_name': metadata.get('capture_name'),
                'timestamp': metadata.get('timestamp'),
                'metadata': metadata
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo información de última captura: {e}")
            return None
    
    def cleanup(self):
        """Limpiar recursos del sistema"""
        try:
            if self.capture_in_progress:
                logger.warning("Cerrando sistema durante captura en progreso")
            
            # Aquí se podrían limpiar recursos adicionales si fuera necesario
            logger.info("Sistema de cámaras estéreo cerrado")
            
        except Exception as e:
            logger.error(f"Error durante limpieza: {e}")
    
    def test_cameras(self) -> Dict[str, Any]:
        """Realizar test básico de las cámaras"""
        test_results = {
            'left_camera': {'available': False, 'test_capture': False},
            'right_camera': {'available': False, 'test_capture': False},
            'stereo_sync': {'success': False, 'time_diff_ms': None}
        }
        
        try:
            # Test de disponibilidad
            self.verify_cameras()
            test_results['left_camera']['available'] = True
            test_results['right_camera']['available'] = True
            
            # Test de captura individual
            test_dir = Path("data/test")
            test_dir.mkdir(exist_ok=True)
            
            left_test_file = test_dir / "test_left.jpg"
            right_test_file = test_dir / "test_right.jpg"
            
            # Test cámara izquierda
            if self.capture_single_image(self.left_camera_id, str(left_test_file), 1000):
                test_results['left_camera']['test_capture'] = True
            
            # Test cámara derecha
            if self.capture_single_image(self.right_camera_id, str(right_test_file), 1000):
                test_results['right_camera']['test_capture'] = True
            
            # Test de sincronización
            if (test_results['left_camera']['test_capture'] and 
                test_results['right_camera']['test_capture']):
                
                sync_result = self.capture_stereo_pair("test_sync")
                if sync_result['success']:
                    test_results['stereo_sync']['success'] = True
                    sync_info = sync_result['metadata']['synchronization']
                    test_results['stereo_sync']['time_diff_ms'] = sync_info['time_difference_ms']
            
            # Limpiar archivos de test
            for test_file in [left_test_file, right_test_file]:
                if test_file.exists():
                    test_file.unlink()
            
            return test_results
            
        except Exception as e:
            logger.error(f"Error en test de cámaras: {e}")
            return test_results

if __name__ == "__main__":
    # Test del sistema de cámaras
    from config.camera_config import CameraConfig
    
    try:
        print("Probando sistema de cámaras estéreo...")
        
        # Crear configuración
        config = CameraConfig()
        
        # Crear sistema estéreo
        stereo = StereoCamera(config)
        
        print("✓ Sistema inicializado")
        
        # Test básico
        test_results = stereo.test_cameras()
        print("✓ Test completado:")
        print(f"  Cámara izquierda: {test_results['left_camera']}")
        print(f"  Cámara derecha: {test_results['right_camera']}")
        print(f"  Sincronización: {test_results['stereo_sync']}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import sys
        sys.exit(1)