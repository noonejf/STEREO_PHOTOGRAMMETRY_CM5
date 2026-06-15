#!/usr/bin/env python3
import cv2
import json
import numpy as np
from pathlib import Path
from datetime import datetime


class DatasetManager:
    """Gestiona el dataset de pares (imagen, máscara) para entrenar modelos de IA."""

    def __init__(self, base_dir="data/ai_dataset"):
        self.base_dir = Path(base_dir)
        self.images_dir = self.base_dir / "images"
        self.masks_dir = self.base_dir / "masks"
        self.meta_path = self.base_dir / "metadata.json"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.masks_dir.mkdir(parents=True, exist_ok=True)

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
    # Core operations
    # ------------------------------------------------------------------

    def save_sample(self, image: np.ndarray, mask: np.ndarray,
                    notes: str = "") -> int:
        """Guarda un par (imagen, máscara). Retorna el ID asignado."""
        sample_id = self._next_id()
        stem = f"{sample_id:04d}"

        cv2.imwrite(str(self.images_dir / f"{stem}.jpg"), image,
                    [cv2.IMWRITE_JPEG_QUALITY, 95])
        cv2.imwrite(str(self.masks_dir / f"{stem}.png"), mask)

        self._write_meta(sample_id, notes)
        return sample_id

    def delete_sample(self, sample_id: int):
        """Elimina un par del dataset."""
        stem = f"{sample_id:04d}"
        for path in [self.images_dir / f"{stem}.jpg",
                     self.masks_dir / f"{stem}.png"]:
            if path.exists():
                path.unlink()
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
            info = meta.get(str(sid), {})
            result.append({
                'id': sid,
                'image_path': self.images_dir / f"{stem}.jpg",
                'mask_path': mask_path,
                'has_mask': mask_path.exists(),
                'date': info.get('date', ''),
                'notes': info.get('notes', ''),
            })
        return result

    def get_sample(self, sample_id: int):
        """Carga y retorna (image_bgr, mask_gray) para un ID dado."""
        stem = f"{sample_id:04d}"
        img = cv2.imread(str(self.images_dir / f"{stem}.jpg"))
        mask = cv2.imread(str(self.masks_dir / f"{stem}.png"), cv2.IMREAD_GRAYSCALE)
        return img, mask

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

    def _write_meta(self, sample_id: int, notes: str = ""):
        meta = self._read_meta()
        meta[str(sample_id)] = {
            'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'notes': notes,
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
        lines = [f"Dataset: {self.base_dir}", f"Total: {len(samples)} samples", ""]
        for s in samples:
            ok = "✓" if s['has_mask'] else "✗"
            lines.append(f"  {ok} #{s['id']:04d}  {s['date']}  {s['notes']}")
        return "\n".join(lines)
