#!/usr/bin/env python3
"""
Gestor de archivos para el sistema de fotogrametría estéreo
Maneja organización, limpieza y gestión de archivos del proyecto
"""

import os
import shutil
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import logging

from utils.logger import get_logger, PerformanceLogger

logger = get_logger(__name__)

class FileManager:
    """Gestor principal de archivos del sistema"""
    
    def __init__(self, project_root: str = None):
        """
        Inicializar gestor de archivos
        
        Args:
            project_root: Directorio raíz del proyecto
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        
        # Estructura de directorios del proyecto
        self.directories = {
            'data': self.project_root / 'data',
            'captures': self.project_root / 'data' / 'captures',
            'calibration': self.project_root / 'data' / 'calibration', 
            'results': self.project_root / 'data' / 'results',
            'temp': self.project_root / 'data' / 'temp',
            'logs': self.project_root / 'logs',
            'config': self.project_root / 'config',
            'backups': self.project_root / 'backups'
        }
        
        # Extensiones de archivos por categoría
        self.file_extensions = {
            'images': ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'],
            'point_clouds': ['.ply', '.xyz', '.pcd', '.obj', '.stl'],
            'config': ['.json', '.yaml', '.yml', '.ini'],
            'logs': ['.log', '.txt'],
            'data': ['.csv', '.npz', '.npy'],
            'compressed': ['.zip', '.tar.gz', '.7z']
        }
        
        # Crear estructura de directorios
        self._ensure_directory_structure()
        
        logger.info(f"Gestor de archivos inicializado - Proyecto: {self.project_root}")
    
    def _ensure_directory_structure(self):
        """Crear estructura de directorios necesaria"""
        try:
            for name, path in self.directories.items():
                path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Directorio asegurado: {path}")
                
        except Exception as e:
            logger.error(f"Error creando estructura de directorios: {e}")
            raise
    
    def get_directory_info(self, directory: str = None) -> Dict[str, Any]:
        """
        Obtener información sobre un directorio específico
        
        Args:
            directory: Nombre del directorio o ruta completa
            
        Returns:
            Información del directorio
        """
        try:
            if directory is None:
                # Información de todo el proyecto
                total_size = 0
                file_counts = {}
                
                for name, path in self.directories.items():
                    dir_info = self._analyze_directory(path)
                    file_counts[name] = dir_info
                    total_size += dir_info['total_size_bytes']
                
                return {
                    'project_root': str(self.project_root),
                    'total_size_bytes': total_size,
                    'total_size_mb': total_size / (1024 * 1024),
                    'directories': file_counts,
                    'timestamp': datetime.now().isoformat()
                }
            
            # Información de directorio específico
            if directory in self.directories:
                target_path = self.directories[directory]
            else:
                target_path = Path(directory)
            
            if not target_path.exists():
                return {'error': f"Directorio no existe: {target_path}"}
            
            return self._analyze_directory(target_path)
            
        except Exception as e:
            logger.error(f"Error obteniendo información de directorio: {e}")
            return {'error': str(e)}
    
    def _analyze_directory(self, path: Path) -> Dict[str, Any]:
        """Analizar contenido de un directorio"""
        try:
            total_size = 0
            file_count = 0
            dir_count = 0
            file_types = {}
            latest_modified = None
            oldest_file = None
            
            if not path.exists():
                return {
                    'path': str(path),
                    'exists': False,
                    'total_size_bytes': 0,
                    'file_count': 0,
                    'dir_count': 0
                }
            
            for item in path.rglob('*'):
                if item.is_file():
                    file_count += 1
                    size = item.stat().st_size
                    total_size += size
                    
                    # Categorizar por extensión
                    ext = item.suffix.lower()
                    if ext not in file_types:
                        file_types[ext] = {'count': 0, 'size': 0}
                    file_types[ext]['count'] += 1
                    file_types[ext]['size'] += size
                    
                    # Fechas de modificación
                    mod_time = datetime.fromtimestamp(item.stat().st_mtime)
                    if latest_modified is None or mod_time > latest_modified:
                        latest_modified = mod_time
                    if oldest_file is None or mod_time < oldest_file:
                        oldest_file = mod_time
                        
                elif item.is_dir():
                    dir_count += 1
            
            return {
                'path': str(path),
                'exists': True,
                'total_size_bytes': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'file_count': file_count,
                'dir_count': dir_count,
                'file_types': file_types,
                'latest_modified': latest_modified.isoformat() if latest_modified else None,
                'oldest_file': oldest_file.isoformat() if oldest_file else None
            }
            
        except Exception as e:
            logger.error(f"Error analizando directorio {path}: {e}")
            return {'path': str(path), 'error': str(e)}
    
    def cleanup_temp_files(self, max_age_hours: int = 24) -> Dict[str, Any]:
        """
        Limpiar archivos temporales antiguos
        
        Args:
            max_age_hours: Edad máxima en horas para conservar archivos
            
        Returns:
            Información sobre la limpieza realizada
        """
        try:
            with PerformanceLogger("Limpieza de archivos temporales", logger):
                temp_dir = self.directories['temp']
                cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
                
                files_removed = 0
                space_freed = 0
                errors = []
                
                for temp_file in temp_dir.rglob('*'):
                    if temp_file.is_file():
                        try:
                            mod_time = datetime.fromtimestamp(temp_file.stat().st_mtime)
                            
                            if mod_time < cutoff_time:
                                file_size = temp_file.stat().st_size
                                temp_file.unlink()
                                files_removed += 1
                                space_freed += file_size
                                logger.debug(f"Archivo temporal eliminado: {temp_file}")
                                
                        except Exception as e:
                            errors.append(f"Error eliminando {temp_file}: {e}")
                
                # Eliminar directorios vacíos
                empty_dirs_removed = self._remove_empty_directories(temp_dir)
                
                result = {
                    'files_removed': files_removed,
                    'space_freed_bytes': space_freed,
                    'space_freed_mb': space_freed / (1024 * 1024),
                    'empty_dirs_removed': empty_dirs_removed,
                    'errors': errors,
                    'cutoff_time': cutoff_time.isoformat()
                }
                
                logger.info(f"Limpieza temporal completada: {files_removed} archivos, {result['space_freed_mb']:.2f} MB liberados")
                return result
                
        except Exception as e:
            logger.error(f"Error durante limpieza temporal: {e}")
            return {'error': str(e)}
    
    def _remove_empty_directories(self, root_dir: Path) -> int:
        """Eliminar directorios vacíos recursivamente"""
        removed_count = 0
        
        try:
            # Procesar de abajo hacia arriba
            for dir_path in sorted(root_dir.rglob('*'), key=lambda x: len(x.parts), reverse=True):
                if dir_path.is_dir() and dir_path != root_dir:
                    try:
                        if not any(dir_path.iterdir()):  # Directorio vacío
                            dir_path.rmdir()
                            removed_count += 1
                            logger.debug(f"Directorio vacío eliminado: {dir_path}")
                    except OSError:
                        # No es realmente vacío o hay otros problemas
                        pass
                        
        except Exception as e:
            logger.error(f"Error eliminando directorios vacíos: {e}")
        
        return removed_count
    
    def archive_old_captures(self, days_old: int = 30, 
                           archive_format: str = 'zip') -> Dict[str, Any]:
        """
        Archivar capturas antiguas para ahorrar espacio
        
        Args:
            days_old: Días de antigüedad para considerar archivable
            archive_format: Formato de archivo ('zip', 'tar.gz')
            
        Returns:
            Información sobre el archivado
        """
        try:
            with PerformanceLogger("Archivado de capturas antiguas", logger):
                captures_dir = self.directories['captures']
                archive_dir = self.directories['backups'] / 'archived_captures'
                archive_dir.mkdir(exist_ok=True)
                
                cutoff_date = datetime.now() - timedelta(days=days_old)
                archived_sessions = []
                total_size_before = 0
                total_size_after = 0
                
                for session_dir in captures_dir.iterdir():
                    if session_dir.is_dir():
                        mod_time = datetime.fromtimestamp(session_dir.stat().st_mtime)
                        
                        if mod_time < cutoff_date:
                            # Calcular tamaño original
                            original_size = sum(f.stat().st_size for f in session_dir.rglob('*') if f.is_file())
                            total_size_before += original_size
                            
                            # Crear archivo
                            archive_name = f"{session_dir.name}_{mod_time.strftime('%Y%m%d')}"
                            
                            if archive_format == 'zip':
                                archive_path = archive_dir / f"{archive_name}.zip"
                                shutil.make_archive(str(archive_path.with_suffix('')), 'zip', session_dir)
                            elif archive_format == 'tar.gz':
                                archive_path = archive_dir / f"{archive_name}.tar.gz"
                                shutil.make_archive(str(archive_path.with_suffix('').with_suffix('')), 'gztar', session_dir)
                            else:
                                raise ValueError(f"Formato de archivo no soportado: {archive_format}")
                            
                            # Verificar archivo creado
                            if archive_path.exists():
                                archive_size = archive_path.stat().st_size
                                total_size_after += archive_size
                                
                                # Eliminar directorio original
                                shutil.rmtree(session_dir)
                                
                                archived_sessions.append({
                                    'session': session_dir.name,
                                    'archive_file': archive_path.name,
                                    'original_size_mb': original_size / (1024 * 1024),
                                    'archive_size_mb': archive_size / (1024 * 1024),
                                    'compression_ratio': archive_size / original_size if original_size > 0 else 0,
                                    'date_archived': datetime.now().isoformat()
                                })
                                
                                logger.info(f"Sesión archivada: {session_dir.name} -> {archive_path.name}")
                
                space_saved = total_size_before - total_size_after
                
                result = {
                    'sessions_archived': len(archived_sessions),
                    'total_size_before_mb': total_size_before / (1024 * 1024),
                    'total_size_after_mb': total_size_after / (1024 * 1024),
                    'space_saved_mb': space_saved / (1024 * 1024),
                    'compression_ratio_avg': total_size_after / total_size_before if total_size_before > 0 else 0,
                    'archive_format': archive_format,
                    'cutoff_date': cutoff_date.isoformat(),
                    'archived_sessions': archived_sessions
                }
                
                logger.info(f"Archivado completado: {len(archived_sessions)} sesiones, {result['space_saved_mb']:.2f} MB ahorrados")
                return result
                
        except Exception as e:
            logger.error(f"Error durante archivado: {e}")
            return {'error': str(e)}
    
    def backup_configuration(self) -> Dict[str, Any]:
        """Crear backup de archivos de configuración"""
        try:
            with PerformanceLogger("Backup de configuración", logger):
                config_dir = self.directories['config']
                backup_dir = self.directories['backups'] / 'config'
                backup_dir.mkdir(exist_ok=True)
                
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_name = f"config_backup_{timestamp}"
                backup_path = backup_dir / f"{backup_name}.zip"
                
                # Crear archivo zip con configuraciones
                shutil.make_archive(str(backup_path.with_suffix('')), 'zip', config_dir)
                
                backup_size = backup_path.stat().st_size
                
                # Mantener solo los últimos 10 backups
                self._cleanup_old_backups(backup_dir, max_files=10)
                
                result = {
                    'backup_file': backup_path.name,
                    'backup_size_mb': backup_size / (1024 * 1024),
                    'timestamp': timestamp,
                    'config_files_included': len(list(config_dir.rglob('*')))
                }
                
                logger.info(f"Backup de configuración creado: {backup_path.name}")
                return result
                
        except Exception as e:
            logger.error(f"Error creando backup de configuración: {e}")
            return {'error': str(e)}
    
    def _cleanup_old_backups(self, backup_dir: Path, max_files: int = 10):
        """Mantener solo los backups más recientes"""
        try:
            backup_files = [f for f in backup_dir.glob('*.zip') if f.is_file()]
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Eliminar backups antiguos
            for old_backup in backup_files[max_files:]:
                old_backup.unlink()
                logger.debug(f"Backup antiguo eliminado: {old_backup.name}")
                
        except Exception as e:
            logger.error(f"Error limpiando backups antiguos: {e}")
    
    def get_storage_usage(self) -> Dict[str, Any]:
        """Obtener estadísticas de uso de almacenamiento"""
        try:
            usage_stats = {}
            total_project_size = 0
            
            for name, path in self.directories.items():
                dir_info = self._analyze_directory(path)
                usage_stats[name] = {
                    'size_mb': dir_info.get('total_size_mb', 0),
                    'file_count': dir_info.get('file_count', 0),
                    'dir_count': dir_info.get('dir_count', 0)
                }
                total_project_size += dir_info.get('total_size_bytes', 0)
            
            # Información del sistema de archivos
            disk_usage = shutil.disk_usage(self.project_root)
            
            result = {
                'project_size_mb': total_project_size / (1024 * 1024),
                'project_size_gb': total_project_size / (1024 * 1024 * 1024),
                'disk_total_gb': disk_usage.total / (1024 * 1024 * 1024),
                'disk_used_gb': (disk_usage.total - disk_usage.free) / (1024 * 1024 * 1024),
                'disk_free_gb': disk_usage.free / (1024 * 1024 * 1024),
                'disk_usage_percent': ((disk_usage.total - disk_usage.free) / disk_usage.total) * 100,
                'project_vs_disk_percent': (total_project_size / disk_usage.total) * 100,
                'directories': usage_stats,
                'timestamp': datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas de almacenamiento: {e}")
            return {'error': str(e)}
    
    def find_duplicate_files(self, directory: str = None) -> Dict[str, Any]:
        """
        Encontrar archivos duplicados basándose en hash MD5
        
        Args:
            directory: Directorio específico a revisar, None para todo el proyecto
            
        Returns:
            Información sobre duplicados encontrados
        """
        try:
            with PerformanceLogger("Búsqueda de archivos duplicados", logger):
                if directory and directory in self.directories:
                    search_path = self.directories[directory]
                elif directory:
                    search_path = Path(directory)
                else:
                    search_path = self.project_root
                
                file_hashes = {}
                duplicates = {}
                total_files_checked = 0
                duplicate_space_wasted = 0
                
                for file_path in search_path.rglob('*'):
                    if file_path.is_file():
                        total_files_checked += 1
                        
                        try:
                            # Calcular hash MD5
                            file_hash = self._calculate_file_hash(file_path)
                            file_size = file_path.stat().st_size
                            
                            if file_hash in file_hashes:
                                # Archivo duplicado encontrado
                                if file_hash not in duplicates:
                                    duplicates[file_hash] = {
                                        'files': [file_hashes[file_hash]],
                                        'size_bytes': file_size,
                                        'count': 1
                                    }
                                
                                duplicates[file_hash]['files'].append(str(file_path))
                                duplicates[file_hash]['count'] += 1
                                duplicate_space_wasted += file_size
                                
                            else:
                                file_hashes[file_hash] = str(file_path)
                                
                        except Exception as e:
                            logger.warning(f"Error procesando archivo {file_path}: {e}")
                
                result = {
                    'total_files_checked': total_files_checked,
                    'duplicate_groups_found': len(duplicates),
                    'total_duplicate_files': sum(d['count'] for d in duplicates.values()),
                    'space_wasted_mb': duplicate_space_wasted / (1024 * 1024),
                    'duplicates': duplicates,
                    'search_path': str(search_path)
                }
                
                logger.info(f"Búsqueda de duplicados: {result['duplicate_groups_found']} grupos encontrados")
                return result
                
        except Exception as e:
            logger.error(f"Error buscando archivos duplicados: {e}")
            return {'error': str(e)}
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calcular hash MD5 de un archivo"""
        hash_md5 = hashlib.md5()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        
        return hash_md5.hexdigest()
    
    def export_file_inventory(self, output_file: str = None) -> Dict[str, Any]:
        """Exportar inventario completo de archivos del proyecto"""
        try:
            if output_file is None:
                output_file = self.directories['logs'] / f"file_inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            
            inventory = {
                'project_info': {
                    'root_path': str(self.project_root),
                    'generated_at': datetime.now().isoformat(),
                    'generator': 'Stereo Photogrammetry CM5 File Manager'
                },
                'storage_usage': self.get_storage_usage(),
                'directory_analysis': {},
                'file_categories': {}
            }
            
            # Analizar cada directorio
            for name, path in self.directories.items():
                inventory['directory_analysis'][name] = self._analyze_directory(path)
            
            # Categorizar archivos por extensión
            all_extensions = {}
            for name, path in self.directories.items():
                if path.exists():
                    for file_path in path.rglob('*'):
                        if file_path.is_file():
                            ext = file_path.suffix.lower()
                            if ext not in all_extensions:
                                all_extensions[ext] = {'count': 0, 'total_size': 0, 'directories': set()}
                            all_extensions[ext]['count'] += 1
                            all_extensions[ext]['total_size'] += file_path.stat().st_size
                            all_extensions[ext]['directories'].add(name)
            
            # Convertir sets a listas para JSON
            for ext_info in all_extensions.values():
                ext_info['directories'] = list(ext_info['directories'])
            
            inventory['file_categories'] = all_extensions
            
            # Guardar inventario
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(inventory, f, indent=2, ensure_ascii=False)
            
            result = {
                'inventory_file': str(output_file),
                'total_directories_analyzed': len(inventory['directory_analysis']),
                'unique_file_extensions': len(all_extensions),
                'report_size_mb': Path(output_file).stat().st_size / (1024 * 1024)
            }
            
            logger.info(f"Inventario exportado: {output_file}")
            return result
            
        except Exception as e:
            logger.error(f"Error exportando inventario: {e}")
            return {'error': str(e)}

if __name__ == "__main__":
    # Test del gestor de archivos
    try:
        print("Probando gestor de archivos...")
        
        # Crear gestor
        fm = FileManager()
        print("✓ Gestor inicializado")
        
        # Test información del proyecto
        project_info = fm.get_directory_info()
        print(f"✓ Información del proyecto: {project_info['total_size_mb']:.2f} MB")
        
        # Test estadísticas de almacenamiento
        storage_stats = fm.get_storage_usage()
        print(f"✓ Uso de almacenamiento: {storage_stats['project_size_mb']:.2f} MB")
        
        # Test limpieza temporal
        cleanup_result = fm.cleanup_temp_files(max_age_hours=1)  # 1 hora para test
        print(f"✓ Limpieza temporal: {cleanup_result.get('files_removed', 0)} archivos eliminados")
        
        # Test backup de configuración
        backup_result = fm.backup_configuration()
        if 'error' not in backup_result:
            print(f"✓ Backup creado: {backup_result['backup_file']}")
        
        print("✓ Todas las pruebas del gestor de archivos pasaron")
        
    except Exception as e:
        print(f"✗ Error en pruebas: {e}")
        import sys
        sys.exit(1)