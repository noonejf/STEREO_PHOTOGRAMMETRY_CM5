#!/usr/bin/env python3
import cv2
import hashlib
import json
import numpy as np
from pathlib import Path
from datetime import datetime


class DatasetManager:
    """
    Gestiona el dataset de pares (imagen, máscara, path) para entrenar modelos IA.

    Estructura en disco:
        data/ai_dataset/
            images/   0001.jpg  0002.jpg  ...
            masks/    0001.png  0002.png  ...
            paths/    0001.json 0002.json ...   (opcional, wire paths)
            metadata.json
    """

    def __init__(self, base_dir="data/ai_dataset"):
        self.base_dir = Path(base_dir)
        self.images_dir = self.base_dir / "images"
        self.masks_dir  = self.base_dir / "masks"
        self.paths_dir  = self.base_dir / "paths"
        self.meta_path  = self.base_dir / "metadata.json"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.masks_dir.mkdir(parents=True, exist_ok=True)
        self.paths_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # ID management
    # ------------------------------------------------------------------

    def _all_ids(self):
        ids = []
        for f in self.images_dir.glob("*.jpg"):
            try:
                ids.append(int(f.stem))
            except ValueError:
                pass
        return sorted(ids)

    def _next_id(self) -> int:
        ids = self._all_ids()
        return (max(ids) + 1) if ids else 1

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def _image_hash(self, image: np.ndarray) -> str:
        """
        Hash perceptual robusto: redimensionar a 64x64 en gris y hacer MD5.
        Detecta la misma imagen aunque cambie la compresión JPEG.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        small = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
        return hashlib.md5(small.tobytes()).hexdigest()

    def is_duplicate(self, image: np.ndarray):
        """
        Retorna (True, existing_id) si la imagen ya está en el dataset,
        o (False, None) si es nueva.
        """
        h = self._image_hash(image)
        meta = self._read_meta()
        for sid, info in meta.items():
            if info.get('image_hash') == h:
                return True, int(sid)
        return False, None

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def save_sample(self, image: np.ndarray, mask: np.ndarray,
                    notes: str = "", wire_paths: dict = None) -> int:
        """
        Guarda imagen + máscara y opcionalmente wire_paths.
        wire_paths debe ser {'left': [[x,y],...], 'right': [[x,y],...]}
        Retorna el ID asignado.
        """
        sample_id = self._next_id()
        stem = f"{sample_id:04d}"

        cv2.imwrite(str(self.images_dir / f"{stem}.jpg"), image,
                    [cv2.IMWRITE_JPEG_QUALITY, 95])
        cv2.imwrite(str(self.masks_dir / f"{stem}.png"), mask)

        if wire_paths is not None:
            # Convertir numpy int64 a int nativo para que json pueda serializarlos
            serializable = {
                side: [[int(x), int(y)] for x, y in pts]
                for side, pts in wire_paths.items()
            }
            with open(self.paths_dir / f"{stem}.json", 'w') as f:
                json.dump(serializable, f)

        self._write_meta(sample_id, notes, image_hash=self._image_hash(image))
        return sample_id

    def delete_sample(self, sample_id: int):
        """Elimina un par (y su path si existe) del dataset."""
        stem = f"{sample_id:04d}"
        for p in [self.images_dir / f"{stem}.jpg",
                  self.masks_dir  / f"{stem}.png",
                  self.paths_dir  / f"{stem}.json"]:
            if p.exists():
                p.unlink()
        self._delete_meta(sample_id)

    def count(self) -> int:
        return len(self._all_ids())

    def list_samples(self):
        """Retorna lista de dicts con info de cada muestra."""
        meta = self._read_meta()
        result = []
        for sid in self._all_ids():
            stem = f"{sid:04d}"
            mask_path = self.masks_dir / f"{stem}.png"
            path_path = self.paths_dir / f"{stem}.json"
            info = meta.get(str(sid), {})
            result.append({
                'id': sid,
                'image_path': self.images_dir / f"{stem}.jpg",
                'mask_path':  mask_path,
                'path_file':  path_path,
                'has_mask':   mask_path.exists(),
                'has_path':   path_path.exists(),
                'date':       info.get('date', ''),
                'notes':      info.get('notes', ''),
            })
        return result

    def get_sample(self, sample_id: int):
        """Carga y retorna (image_bgr, mask_gray, wire_paths_or_None)."""
        stem = f"{sample_id:04d}"
        img  = cv2.imread(str(self.images_dir / f"{stem}.jpg"))
        mask = cv2.imread(str(self.masks_dir  / f"{stem}.png"), cv2.IMREAD_GRAYSCALE)
        path_file = self.paths_dir / f"{stem}.json"
        paths = None
        if path_file.exists():
            with open(path_file, 'r') as f:
                paths = json.load(f)
        return img, mask, paths

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _read_meta(self) -> dict:
        if self.meta_path.exists():
            try:
                with open(self.meta_path, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _write_meta(self, sample_id: int, notes: str = "", image_hash: str = ""):
        meta = self._read_meta()
        meta[str(sample_id)] = {
            'date':       datetime.now().strftime("%Y-%m-%d %H:%M"),
            'notes':      notes,
            'image_hash': image_hash,
        }
        with open(self.meta_path, 'w') as f:
            json.dump(meta, f, indent=2)

    def _delete_meta(self, sample_id: int):
        meta = self._read_meta()
        meta.pop(str(sample_id), None)
        with open(self.meta_path, 'w') as f:
            json.dump(meta, f, indent=2)

    def export_summary(self) -> str:
        samples = self.list_samples()
        lines = [f"Dataset: {self.base_dir}", f"Total: {len(samples)} muestras", ""]
        for s in samples:
            mask_ok = "M" if s['has_mask'] else "-"
            path_ok = "P" if s['has_path'] else "-"
            lines.append(
                f"  [{mask_ok}{path_ok}] #{s['id']:04d}  {s['date']}  {s['notes']}"
            )
        return "\n".join(lines)
