#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI para ajustar parámetros de detección de bordes en tiempo real
Permite encontrar la configuración óptima visualmente
"""

import sys
import cv2
import numpy as np
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QSlider, QPushButton, QComboBox,
                             QGroupBox, QGridLayout, QFileDialog)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap


class EdgeDetectionTuner(QDialog):
    """GUI para ajustar parámetros de detección de bordes"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cable Edge Detection Tuner")
        self.setGeometry(100, 100, 1400, 900)

        # Cargar imagen por defecto
        default_path = Path("data/results/debug/01_left_original.jpg")
        if default_path.exists():
            self.original_img = cv2.imread(str(default_path))
        else:
            self.original_img = None

        # Configuración por defecto (Top-Hat optimizado)
        self.default_config = {
            'method': 'Top-Hat',
            'tophat_ksize': 25,
            'tophat_thresh': 40,
            'dilate': 3,
            'erode': 0,
            'close': 0,
            'cleanup_area_percent': 10
        }

        # Variables de control
        self.mask_result = None  # Máscara resultante para usar en procesamiento
        self.processing_mode = False  # True cuando se llama desde el procesamiento
        self._preview_img = None
        self._preview_scale = 1.0

        # Debounce timer: evita recalcular mientras el usuario arrastra el slider
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self.update_detection)

        self.setup_ui()
        self.refresh_config_list()
        self.load_default_config()

        # Preparar preview y actualizar visualización inicial
        self._prepare_preview()
        if self.original_img is not None:
            self.update_detection()

    def setup_ui(self):
        """Configurar interfaz de usuario"""
        main_layout = QHBoxLayout(self)

        # Panel izquierdo - Controles
        controls_panel = self.create_controls_panel()
        main_layout.addWidget(controls_panel, stretch=1)

        # Panel derecho - Visualización
        viz_panel = self.create_visualization_panel()
        main_layout.addWidget(viz_panel, stretch=2)

    def create_controls_panel(self):
        """Crear panel de controles"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Botón para cargar imagen
        btn_load = QPushButton("Load Image")
        btn_load.clicked.connect(self.load_image)
        layout.addWidget(btn_load)

        # Selector de método
        method_group = QGroupBox("Detection Method")
        method_layout = QVBoxLayout()
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Canny",
            "Sobel",
            "Laplacian",
            "Morphological Gradient",
            "Top-Hat"
        ])
        self.method_combo.currentTextChanged.connect(self.on_method_changed)
        method_layout.addWidget(self.method_combo)
        method_group.setLayout(method_layout)
        layout.addWidget(method_group)

        # === PARÁMETROS CANNY ===
        self.canny_group = QGroupBox("Canny Parameters")
        canny_layout = QGridLayout()

        # Threshold 1
        canny_layout.addWidget(QLabel("Threshold Low:"), 0, 0)
        self.canny_low_slider = QSlider(Qt.Horizontal)
        self.canny_low_slider.setRange(1, 100)
        self.canny_low_slider.setValue(10)
        self.canny_low_slider.valueChanged.connect(self._schedule_update)
        canny_layout.addWidget(self.canny_low_slider, 0, 1)
        self.canny_low_label = QLabel("10")
        canny_layout.addWidget(self.canny_low_label, 0, 2)

        # Threshold 2
        canny_layout.addWidget(QLabel("Threshold High:"), 1, 0)
        self.canny_high_slider = QSlider(Qt.Horizontal)
        self.canny_high_slider.setRange(1, 200)
        self.canny_high_slider.setValue(30)
        self.canny_high_slider.valueChanged.connect(self._schedule_update)
        canny_layout.addWidget(self.canny_high_slider, 1, 1)
        self.canny_high_label = QLabel("30")
        canny_layout.addWidget(self.canny_high_label, 1, 2)

        # Aperture size
        canny_layout.addWidget(QLabel("Aperture Size:"), 2, 0)
        self.canny_aperture_combo = QComboBox()
        self.canny_aperture_combo.addItems(["3", "5", "7"])
        self.canny_aperture_combo.currentTextChanged.connect(self._schedule_update)
        canny_layout.addWidget(self.canny_aperture_combo, 2, 1, 1, 2)

        self.canny_group.setLayout(canny_layout)
        layout.addWidget(self.canny_group)

        # === PARÁMETROS SOBEL ===
        self.sobel_group = QGroupBox("Sobel Parameters")
        sobel_layout = QGridLayout()

        sobel_layout.addWidget(QLabel("Kernel Size:"), 0, 0)
        self.sobel_ksize_combo = QComboBox()
        self.sobel_ksize_combo.addItems(["1", "3", "5", "7"])
        self.sobel_ksize_combo.setCurrentText("3")
        self.sobel_ksize_combo.currentTextChanged.connect(self._schedule_update)
        sobel_layout.addWidget(self.sobel_ksize_combo, 0, 1, 1, 2)

        sobel_layout.addWidget(QLabel("Threshold:"), 1, 0)
        self.sobel_thresh_slider = QSlider(Qt.Horizontal)
        self.sobel_thresh_slider.setRange(1, 100)
        self.sobel_thresh_slider.setValue(20)
        self.sobel_thresh_slider.valueChanged.connect(self._schedule_update)
        sobel_layout.addWidget(self.sobel_thresh_slider, 1, 1)
        self.sobel_thresh_label = QLabel("20")
        sobel_layout.addWidget(self.sobel_thresh_label, 1, 2)

        self.sobel_group.setLayout(sobel_layout)
        self.sobel_group.hide()
        layout.addWidget(self.sobel_group)

        # === PARÁMETROS LAPLACIAN ===
        self.laplacian_group = QGroupBox("Laplacian Parameters")
        laplacian_layout = QGridLayout()

        laplacian_layout.addWidget(QLabel("Kernel Size:"), 0, 0)
        self.laplacian_ksize_combo = QComboBox()
        self.laplacian_ksize_combo.addItems(["1", "3", "5", "7"])
        self.laplacian_ksize_combo.setCurrentText("3")
        self.laplacian_ksize_combo.currentTextChanged.connect(self._schedule_update)
        laplacian_layout.addWidget(self.laplacian_ksize_combo, 0, 1, 1, 2)

        laplacian_layout.addWidget(QLabel("Threshold:"), 1, 0)
        self.laplacian_thresh_slider = QSlider(Qt.Horizontal)
        self.laplacian_thresh_slider.setRange(1, 100)
        self.laplacian_thresh_slider.setValue(20)
        self.laplacian_thresh_slider.valueChanged.connect(self._schedule_update)
        laplacian_layout.addWidget(self.laplacian_thresh_slider, 1, 1)
        self.laplacian_thresh_label = QLabel("20")
        laplacian_layout.addWidget(self.laplacian_thresh_label, 1, 2)

        self.laplacian_group.setLayout(laplacian_layout)
        self.laplacian_group.hide()
        layout.addWidget(self.laplacian_group)

        # === PARÁMETROS MORPHOLOGICAL GRADIENT ===
        self.morphgrad_group = QGroupBox("Morphological Gradient Parameters")
        morphgrad_layout = QGridLayout()

        morphgrad_layout.addWidget(QLabel("Kernel Size:"), 0, 0)
        self.morphgrad_ksize_slider = QSlider(Qt.Horizontal)
        self.morphgrad_ksize_slider.setRange(3, 21)
        self.morphgrad_ksize_slider.setSingleStep(2)
        self.morphgrad_ksize_slider.setValue(5)
        self.morphgrad_ksize_slider.valueChanged.connect(self._schedule_update)
        morphgrad_layout.addWidget(self.morphgrad_ksize_slider, 0, 1)
        self.morphgrad_ksize_label = QLabel("5")
        morphgrad_layout.addWidget(self.morphgrad_ksize_label, 0, 2)

        morphgrad_layout.addWidget(QLabel("Threshold:"), 1, 0)
        self.morphgrad_thresh_slider = QSlider(Qt.Horizontal)
        self.morphgrad_thresh_slider.setRange(1, 100)
        self.morphgrad_thresh_slider.setValue(20)
        self.morphgrad_thresh_slider.valueChanged.connect(self._schedule_update)
        morphgrad_layout.addWidget(self.morphgrad_thresh_slider, 1, 1)
        self.morphgrad_thresh_label = QLabel("20")
        morphgrad_layout.addWidget(self.morphgrad_thresh_label, 1, 2)

        self.morphgrad_group.setLayout(morphgrad_layout)
        self.morphgrad_group.hide()
        layout.addWidget(self.morphgrad_group)

        # === PARÁMETROS TOP-HAT ===
        self.tophat_group = QGroupBox("Top-Hat Parameters")
        tophat_layout = QGridLayout()

        tophat_layout.addWidget(QLabel("Kernel Size:"), 0, 0)
        self.tophat_ksize_slider = QSlider(Qt.Horizontal)
        self.tophat_ksize_slider.setRange(3, 51)
        self.tophat_ksize_slider.setSingleStep(2)
        self.tophat_ksize_slider.setValue(11)
        self.tophat_ksize_slider.valueChanged.connect(self._schedule_update)
        tophat_layout.addWidget(self.tophat_ksize_slider, 0, 1)
        self.tophat_ksize_label = QLabel("11")
        tophat_layout.addWidget(self.tophat_ksize_label, 0, 2)

        tophat_layout.addWidget(QLabel("Threshold:"), 1, 0)
        self.tophat_thresh_slider = QSlider(Qt.Horizontal)
        self.tophat_thresh_slider.setRange(1, 100)
        self.tophat_thresh_slider.setValue(20)
        self.tophat_thresh_slider.valueChanged.connect(self._schedule_update)
        tophat_layout.addWidget(self.tophat_thresh_slider, 1, 1)
        self.tophat_thresh_label = QLabel("20")
        tophat_layout.addWidget(self.tophat_thresh_label, 1, 2)

        self.tophat_group.setLayout(tophat_layout)
        self.tophat_group.hide()
        layout.addWidget(self.tophat_group)

        # === POST-PROCESAMIENTO COMÚN ===
        postproc_group = QGroupBox("Post-processing")
        postproc_layout = QGridLayout()

        # Dilatación
        postproc_layout.addWidget(QLabel("Dilate Iterations:"), 0, 0)
        self.dilate_slider = QSlider(Qt.Horizontal)
        self.dilate_slider.setRange(0, 10)
        self.dilate_slider.setValue(1)
        self.dilate_slider.valueChanged.connect(self._schedule_update)
        postproc_layout.addWidget(self.dilate_slider, 0, 1)
        self.dilate_label = QLabel("1")
        postproc_layout.addWidget(self.dilate_label, 0, 2)

        # Erosión
        postproc_layout.addWidget(QLabel("Erode Iterations:"), 1, 0)
        self.erode_slider = QSlider(Qt.Horizontal)
        self.erode_slider.setRange(0, 10)
        self.erode_slider.setValue(0)
        self.erode_slider.valueChanged.connect(self._schedule_update)
        postproc_layout.addWidget(self.erode_slider, 1, 1)
        self.erode_label = QLabel("0")
        postproc_layout.addWidget(self.erode_label, 1, 2)

        # Close
        postproc_layout.addWidget(QLabel("Close Iterations:"), 2, 0)
        self.close_slider = QSlider(Qt.Horizontal)
        self.close_slider.setRange(0, 10)
        self.close_slider.setValue(0)
        self.close_slider.valueChanged.connect(self._schedule_update)
        postproc_layout.addWidget(self.close_slider, 2, 1)
        self.close_label = QLabel("0")
        postproc_layout.addWidget(self.close_label, 2, 2)

        postproc_group.setLayout(postproc_layout)
        layout.addWidget(postproc_group)

        # === LIMPIEZA INTELIGENTE ===
        cleanup_group = QGroupBox("Smart Cleanup")
        cleanup_layout = QGridLayout()

        # Área mínima para componentes
        cleanup_layout.addWidget(QLabel("Min Area (% of largest):"), 0, 0)
        self.cleanup_area_slider = QSlider(Qt.Horizontal)
        self.cleanup_area_slider.setRange(1, 50)
        self.cleanup_area_slider.setValue(10)
        self.cleanup_area_slider.valueChanged.connect(self._schedule_update)
        cleanup_layout.addWidget(self.cleanup_area_slider, 0, 1)
        self.cleanup_area_label = QLabel("10%")
        cleanup_layout.addWidget(self.cleanup_area_label, 0, 2)

        # Checkbox para activar limpieza
        from PyQt5.QtWidgets import QCheckBox
        self.cleanup_enable = QCheckBox("Enable Smart Cleanup")
        self.cleanup_enable.setChecked(True)
        self.cleanup_enable.stateChanged.connect(self._schedule_update)
        cleanup_layout.addWidget(self.cleanup_enable, 1, 0, 1, 3)

        cleanup_group.setLayout(cleanup_layout)
        layout.addWidget(cleanup_group)

        # Estadísticas
        self.stats_label = QLabel("Pixels detected: 0 (0.00%)")
        layout.addWidget(self.stats_label)

        # === GESTIÓN DE CONFIGURACIONES ===
        config_group = QGroupBox("Saved Configurations")
        config_layout = QVBoxLayout()

        # Selector de configuraciones
        config_select_layout = QHBoxLayout()
        config_select_layout.addWidget(QLabel("Load:"))
        self.config_selector = QComboBox()
        self.config_selector.currentTextChanged.connect(self.load_saved_config)
        config_select_layout.addWidget(self.config_selector)
        config_layout.addLayout(config_select_layout)

        # Nombre para nueva configuración
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        from PyQt5.QtWidgets import QLineEdit
        self.config_name_input = QLineEdit()
        self.config_name_input.setPlaceholderText("New configuration...")
        name_layout.addWidget(self.config_name_input)
        config_layout.addLayout(name_layout)

        # Botones
        buttons_layout = QHBoxLayout()
        btn_save = QPushButton("💾 Save As...")
        btn_save.clicked.connect(self.save_config_with_name)
        buttons_layout.addWidget(btn_save)

        btn_delete = QPushButton("🗑️ Delete")
        btn_delete.clicked.connect(self.delete_config)
        buttons_layout.addWidget(btn_delete)

        btn_refresh = QPushButton("🔄")
        btn_refresh.clicked.connect(self.refresh_config_list)
        buttons_layout.addWidget(btn_refresh)
        config_layout.addLayout(buttons_layout)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # Botón para aplicar y cerrar (cuando se usa desde procesamiento)
        self.btn_apply_close = QPushButton("✓ Apply and Continue Processing")
        self.btn_apply_close.clicked.connect(self.apply_and_close)
        self.btn_apply_close.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        self.btn_apply_close.hide()  # Solo visible cuando se llama desde procesamiento
        layout.addWidget(self.btn_apply_close)

        layout.addStretch()

        return panel

    def create_visualization_panel(self):
        """Crear panel de visualización"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Imagen original
        layout.addWidget(QLabel("Original Image:"))
        self.original_label = QLabel()
        self.original_label.setMinimumSize(600, 400)
        self.original_label.setScaledContents(True)
        layout.addWidget(self.original_label)

        # Imagen con detección
        layout.addWidget(QLabel("Detected Edges:"))
        self.detection_label = QLabel()
        self.detection_label.setMinimumSize(600, 400)
        self.detection_label.setScaledContents(True)
        layout.addWidget(self.detection_label)

        return panel

    def on_method_changed(self, method):
        """Cambiar método de detección"""
        # Ocultar todos los grupos
        self.canny_group.hide()
        self.sobel_group.hide()
        self.laplacian_group.hide()
        self.morphgrad_group.hide()
        self.tophat_group.hide()

        # Mostrar grupo correspondiente
        if method == "Canny":
            self.canny_group.show()
        elif method == "Sobel":
            self.sobel_group.show()
        elif method == "Laplacian":
            self.laplacian_group.show()
        elif method == "Morphological Gradient":
            self.morphgrad_group.show()
        elif method == "Top-Hat":
            self.tophat_group.show()

        self._schedule_update()

    def load_image(self):
        """Cargar imagen desde archivo"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Imagen", "",
            "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            self.original_img = cv2.imread(file_path)
            self._prepare_preview()
            self.update_detection()

    def _prepare_preview(self):
        """Generar imagen reducida para procesamiento rápido en tiempo real"""
        if self.original_img is None:
            self._preview_img = None
            self._preview_scale = 1.0
            return

        h, w = self.original_img.shape[:2]
        max_dim = 1280

        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            new_w = int(w * scale)
            new_h = int(h * scale)
            self._preview_img = cv2.resize(self.original_img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            self._preview_scale = scale
        else:
            self._preview_img = self.original_img
            self._preview_scale = 1.0

    def _schedule_update(self):
        """Debounce: espera 200ms tras el último cambio antes de recalcular"""
        self._update_timer.start(200)

    def update_detection(self):
        """Actualizar detección de bordes"""
        if self.original_img is None:
            return

        img = self._preview_img if self._preview_img is not None else self.original_img

        # Convertir a escala de grises
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        # Aplicar método seleccionado
        method = self.method_combo.currentText()

        if method == "Canny":
            edges = self.apply_canny(gray)
        elif method == "Sobel":
            edges = self.apply_sobel(gray)
        elif method == "Laplacian":
            edges = self.apply_laplacian(gray)
        elif method == "Morphological Gradient":
            edges = self.apply_morphgrad(gray)
        elif method == "Top-Hat":
            edges = self.apply_tophat(gray)
        else:
            edges = np.zeros_like(gray)

        # Post-procesamiento
        edges = self.apply_postprocessing(edges)

        # Limpieza inteligente
        edges_before_cleanup = edges.copy()
        num_components_before = 0
        if self.cleanup_enable.isChecked():
            # Contar componentes antes de limpieza
            num_labels_before, _, _, _ = cv2.connectedComponentsWithStats(edges_before_cleanup, connectivity=8)
            num_components_before = num_labels_before - 1  # Restar fondo

            edges = self.apply_intelligent_cleanup(edges)

            # Contar componentes después de limpieza
            num_labels_after, _, _, _ = cv2.connectedComponentsWithStats(edges, connectivity=8)
            num_components_after = num_labels_after - 1

            # Actualizar estadísticas con info de limpieza
            pixels_detected = np.sum(edges > 0)
            percentage = 100 * pixels_detected / edges.size
            self.stats_label.setText(
                f"Pixels: {pixels_detected} ({percentage:.2f}%)\n"
                f"Components: {num_components_after} (before: {num_components_before}, removed: {num_components_before - num_components_after})"
            )
        else:
            # Actualizar estadísticas sin limpieza
            pixels_detected = np.sum(edges > 0)
            percentage = 100 * pixels_detected / edges.size
            self.stats_label.setText(f"Pixels detected: {pixels_detected} ({percentage:.2f}%)")

        # Guardar máscara escalada a resolución completa para uso externo
        if self._preview_scale < 1.0:
            h_full, w_full = self.original_img.shape[:2]
            self.mask_result = cv2.resize(edges, (w_full, h_full), interpolation=cv2.INTER_NEAREST)
        else:
            self.mask_result = edges

        # Visualizar (sobre imagen de preview para mayor velocidad)
        self.display_results(edges)

    def apply_canny(self, gray):
        """Aplicar Canny"""
        low = self.canny_low_slider.value()
        high = self.canny_high_slider.value()
        aperture = int(self.canny_aperture_combo.currentText())

        self.canny_low_label.setText(str(low))
        self.canny_high_label.setText(str(high))

        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, low, high, apertureSize=aperture, L2gradient=True)
        return edges

    def apply_sobel(self, gray):
        """Aplicar Sobel"""
        ksize = int(self.sobel_ksize_combo.currentText())
        thresh = self.sobel_thresh_slider.value()

        self.sobel_thresh_label.setText(str(thresh))

        sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=ksize)
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=ksize)
        gradient_mag = np.sqrt(sobel_x**2 + sobel_y**2)

        mean_grad = np.mean(gradient_mag)
        std_grad = np.std(gradient_mag)
        threshold = mean_grad + (thresh/10.0) * std_grad

        edges = (gradient_mag > threshold).astype(np.uint8) * 255
        return edges

    def apply_laplacian(self, gray):
        """Aplicar Laplacian"""
        ksize = int(self.laplacian_ksize_combo.currentText())
        thresh = self.laplacian_thresh_slider.value()

        self.laplacian_thresh_label.setText(str(thresh))

        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        laplacian = cv2.Laplacian(blurred, cv2.CV_64F, ksize=ksize)
        laplacian_abs = np.abs(laplacian)

        mean_lap = np.mean(laplacian_abs)
        std_lap = np.std(laplacian_abs)
        threshold = mean_lap + (thresh/10.0) * std_lap

        edges = (laplacian_abs > threshold).astype(np.uint8) * 255
        return edges

    def apply_morphgrad(self, gray):
        """Aplicar Morphological Gradient"""
        ksize = self.morphgrad_ksize_slider.value()
        if ksize % 2 == 0:
            ksize += 1
        thresh = self.morphgrad_thresh_slider.value()

        self.morphgrad_ksize_label.setText(str(ksize))
        self.morphgrad_thresh_label.setText(str(thresh))

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)

        mean_val = np.mean(gradient)
        std_val = np.std(gradient)
        threshold = mean_val + (thresh/10.0) * std_val

        edges = (gradient > threshold).astype(np.uint8) * 255
        return edges

    def apply_tophat(self, gray):
        """Aplicar Top-Hat"""
        ksize = self.tophat_ksize_slider.value()
        if ksize % 2 == 0:
            ksize += 1
        thresh = self.tophat_thresh_slider.value()

        self.tophat_ksize_label.setText(str(ksize))
        self.tophat_thresh_label.setText(str(thresh))

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)

        mean_val = np.mean(tophat)
        std_val = np.std(tophat)
        threshold = mean_val + (thresh/10.0) * std_val

        edges = (tophat > threshold).astype(np.uint8) * 255
        return edges

    def apply_postprocessing(self, edges):
        """Aplicar post-procesamiento"""
        dilate_iter = self.dilate_slider.value()
        erode_iter = self.erode_slider.value()
        close_iter = self.close_slider.value()

        self.dilate_label.setText(str(dilate_iter))
        self.erode_label.setText(str(erode_iter))
        self.close_label.setText(str(close_iter))

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

        result = edges.copy()

        if dilate_iter > 0:
            result = cv2.dilate(result, kernel, iterations=dilate_iter)

        if erode_iter > 0:
            result = cv2.erode(result, kernel, iterations=erode_iter)

        if close_iter > 0:
            result = cv2.morphologyEx(result, cv2.MORPH_CLOSE, kernel, iterations=close_iter)

        return result

    def apply_intelligent_cleanup(self, edges):
        """
        Limpieza inteligente de componentes:
        - Identifica componentes conectados
        - Encuentra los componentes GRANDES (cable)
        - Elimina componentes pequeños (ruido)
        - Si hay múltiples grandes = cable partido, los mantiene todos
        """
        area_percent = self.cleanup_area_slider.value()
        self.cleanup_area_label.setText(f"{area_percent}%")

        # Analizar componentes conectados
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(edges, connectivity=8)

        if num_labels <= 1:  # Solo fondo
            return edges

        # Obtener áreas de todos los componentes (ignorar fondo en índice 0)
        areas = stats[1:, cv2.CC_STAT_AREA]

        if len(areas) == 0:
            return edges

        # Encontrar el componente más grande
        max_area = np.max(areas)

        # Umbral: mantener componentes >= X% del más grande
        threshold_area = max_area * (area_percent / 100.0)

        # Crear máscara limpia
        clean_mask = np.zeros_like(edges)

        # Mantener componentes grandes
        for i in range(1, num_labels):  # Empezar en 1 para ignorar fondo
            area = stats[i, cv2.CC_STAT_AREA]
            if area >= threshold_area:
                clean_mask[labels == i] = 255

        return clean_mask

    def load_default_config(self):
        """Cargar configuración por defecto optimizada"""
        config = self.default_config

        # Seleccionar método
        method = config.get('method', 'Top-Hat')
        index = self.method_combo.findText(method)
        if index >= 0:
            self.method_combo.setCurrentIndex(index)

        # Configurar Top-Hat
        if method == 'Top-Hat':
            self.tophat_ksize_slider.setValue(config.get('tophat_ksize', 25))
            self.tophat_thresh_slider.setValue(config.get('tophat_thresh', 40))

        # Post-procesamiento
        self.dilate_slider.setValue(config.get('dilate', 3))
        self.erode_slider.setValue(config.get('erode', 0))
        self.close_slider.setValue(config.get('close', 0))

        # Limpieza
        self.cleanup_area_slider.setValue(config.get('cleanup_area_percent', 10))

    def display_results(self, edges):
        """Mostrar resultados usando imagen de preview para mayor velocidad"""
        disp_img = self._preview_img if self._preview_img is not None else self.original_img

        # Mostrar imagen original (preview)
        original_rgb = cv2.cvtColor(disp_img, cv2.COLOR_BGR2RGB)
        h, w = original_rgb.shape[:2]
        bytes_per_line = 3 * w
        qimg_original = QImage(bytes(original_rgb.data), w, h, bytes_per_line, QImage.Format_RGB888)
        self.original_label.setPixmap(QPixmap.fromImage(qimg_original))

        # Crear overlay con bordes detectados
        overlay = disp_img.copy()
        overlay[edges > 0] = [0, 255, 0]
        result = cv2.addWeighted(disp_img, 0.7, overlay, 0.3, 0)
        result_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)

        qimg_detection = QImage(bytes(result_rgb.data), w, h, bytes_per_line, QImage.Format_RGB888)
        self.detection_label.setPixmap(QPixmap.fromImage(qimg_detection))

    def save_config(self):
        """Guardar configuración actual"""
        method = self.method_combo.currentText()

        config = {
            'method': method,
            'dilate': self.dilate_slider.value(),
            'erode': self.erode_slider.value(),
            'close': self.close_slider.value(),
            'cleanup_enabled': self.cleanup_enable.isChecked(),
            'cleanup_area_percent': self.cleanup_area_slider.value()
        }

        if method == "Canny":
            config['canny_low'] = self.canny_low_slider.value()
            config['canny_high'] = self.canny_high_slider.value()
            config['canny_aperture'] = int(self.canny_aperture_combo.currentText())
        elif method == "Sobel":
            config['sobel_ksize'] = int(self.sobel_ksize_combo.currentText())
            config['sobel_thresh'] = self.sobel_thresh_slider.value()
        elif method == "Laplacian":
            config['laplacian_ksize'] = int(self.laplacian_ksize_combo.currentText())
            config['laplacian_thresh'] = self.laplacian_thresh_slider.value()
        elif method == "Morphological Gradient":
            config['morphgrad_ksize'] = self.morphgrad_ksize_slider.value()
            config['morphgrad_thresh'] = self.morphgrad_thresh_slider.value()
        elif method == "Top-Hat":
            config['tophat_ksize'] = self.tophat_ksize_slider.value()
            config['tophat_thresh'] = self.tophat_thresh_slider.value()

        # Guardar en archivo
        config_path = Path("edge_detection_config.txt")
        with open(config_path, 'w') as f:
            f.write(f"Cable Edge Detection Configuration\n")
            f.write(f"="*50 + "\n\n")
            f.write(f"# Detection method\n")
            f.write(f"method: {config['method']}\n\n")

            f.write(f"# Method specific parameters\n")
            for key, value in config.items():
                if key not in ['method', 'dilate', 'erode', 'close', 'cleanup_enabled', 'cleanup_area_percent']:
                    f.write(f"{key}: {value}\n")

            f.write(f"\n# Post-processing\n")
            f.write(f"dilate: {config['dilate']}\n")
            f.write(f"erode: {config['erode']}\n")
            f.write(f"close: {config['close']}\n")

            f.write(f"\n# Smart cleanup\n")
            f.write(f"cleanup_enabled: {config['cleanup_enabled']}\n")
            f.write(f"cleanup_area_percent: {config['cleanup_area_percent']}\n")

        print(f"✓ Configuration saved to {config_path}")
        print("\nCurrent configuration:")
        print(config)

    def get_config_dir(self):
        """Obtener directorio de configuraciones"""
        config_dir = Path("config/edge_detection_presets")
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def save_config_with_name(self):
        """Guardar configuración con nombre personalizado"""
        name = self.config_name_input.text().strip()
        if not name:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Please enter a name for the configuration")
            return

        method = self.method_combo.currentText()

        config = {
            'method': method,
            'dilate': self.dilate_slider.value(),
            'erode': self.erode_slider.value(),
            'close': self.close_slider.value(),
            'cleanup_enabled': self.cleanup_enable.isChecked(),
            'cleanup_area_percent': self.cleanup_area_slider.value()
        }

        if method == "Canny":
            config['canny_low'] = self.canny_low_slider.value()
            config['canny_high'] = self.canny_high_slider.value()
            config['canny_aperture'] = int(self.canny_aperture_combo.currentText())
        elif method == "Sobel":
            config['sobel_ksize'] = int(self.sobel_ksize_combo.currentText())
            config['sobel_thresh'] = self.sobel_thresh_slider.value()
        elif method == "Laplacian":
            config['laplacian_ksize'] = int(self.laplacian_ksize_combo.currentText())
            config['laplacian_thresh'] = self.laplacian_thresh_slider.value()
        elif method == "Morphological Gradient":
            config['morphgrad_ksize'] = self.morphgrad_ksize_slider.value()
            config['morphgrad_thresh'] = self.morphgrad_thresh_slider.value()
        elif method == "Top-Hat":
            config['tophat_ksize'] = self.tophat_ksize_slider.value()
            config['tophat_thresh'] = self.tophat_thresh_slider.value()

        # Guardar como JSON
        config_path = self.get_config_dir() / f"{name}.json"
        import json
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        # Guardar también como "last_used" (configuración por defecto)
        last_used_path = self.get_config_dir() / "last_used.json"
        with open(last_used_path, 'w') as f:
            json.dump({'config_name': name}, f)

        print(f"✓ Configuration '{name}' saved")
        self.config_name_input.clear()
        self.refresh_config_list()

        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(self, "Saved", f"Configuration '{name}' saved successfully")

    def refresh_config_list(self):
        """Actualizar lista de configuraciones guardadas"""
        self.config_selector.blockSignals(True)  # Evitar trigger de load mientras actualizamos
        self.config_selector.clear()

        config_dir = self.get_config_dir()
        configs = sorted([f.stem for f in config_dir.glob("*.json") if f.stem != "last_used"])

        self.config_selector.addItem("-- Default (Top-Hat) --")
        for config_name in configs:
            self.config_selector.addItem(config_name)

        # Cargar última usada
        last_used_path = config_dir / "last_used.json"
        if last_used_path.exists():
            import json
            with open(last_used_path, 'r') as f:
                last_used = json.load(f)
                last_name = last_used.get('config_name')
                index = self.config_selector.findText(last_name)
                if index >= 0:
                    self.config_selector.setCurrentIndex(index)

        self.config_selector.blockSignals(False)

    def load_saved_config(self, config_name):
        """Cargar configuración guardada"""
        if not config_name or config_name == "-- Default (Top-Hat) --":
            self.load_default_config()
            return

        config_path = self.get_config_dir() / f"{config_name}.json"
        if not config_path.exists():
            return

        import json
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Aplicar configuración
        method = config.get('method', 'Top-Hat')
        index = self.method_combo.findText(method)
        if index >= 0:
            self.method_combo.setCurrentIndex(index)

        # Cargar parámetros específicos del método
        if method == "Canny":
            self.canny_low_slider.setValue(config.get('canny_low', 10))
            self.canny_high_slider.setValue(config.get('canny_high', 30))
            aperture_index = self.canny_aperture_combo.findText(str(config.get('canny_aperture', 3)))
            if aperture_index >= 0:
                self.canny_aperture_combo.setCurrentIndex(aperture_index)
        elif method == "Sobel":
            ksize_index = self.sobel_ksize_combo.findText(str(config.get('sobel_ksize', 3)))
            if ksize_index >= 0:
                self.sobel_ksize_combo.setCurrentIndex(ksize_index)
            self.sobel_thresh_slider.setValue(config.get('sobel_thresh', 20))
        elif method == "Laplacian":
            ksize_index = self.laplacian_ksize_combo.findText(str(config.get('laplacian_ksize', 3)))
            if ksize_index >= 0:
                self.laplacian_ksize_combo.setCurrentIndex(ksize_index)
            self.laplacian_thresh_slider.setValue(config.get('laplacian_thresh', 20))
        elif method == "Morphological Gradient":
            self.morphgrad_ksize_slider.setValue(config.get('morphgrad_ksize', 5))
            self.morphgrad_thresh_slider.setValue(config.get('morphgrad_thresh', 20))
        elif method == "Top-Hat":
            self.tophat_ksize_slider.setValue(config.get('tophat_ksize', 25))
            self.tophat_thresh_slider.setValue(config.get('tophat_thresh', 40))

        # Post-procesamiento
        self.dilate_slider.setValue(config.get('dilate', 3))
        self.erode_slider.setValue(config.get('erode', 0))
        self.close_slider.setValue(config.get('close', 0))

        # Limpieza
        self.cleanup_enable.setChecked(config.get('cleanup_enabled', True))
        self.cleanup_area_slider.setValue(config.get('cleanup_area_percent', 10))

        print(f"✓ Configuration '{config_name}' loaded")

    def delete_config(self):
        """Eliminar configuración seleccionada"""
        config_name = self.config_selector.currentText()
        if not config_name or config_name == "-- Default (Top-Hat) --":
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Cannot delete default configuration")
            return

        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.question(self, "Confirm",
                                     f"Delete configuration '{config_name}'?",
                                     QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            config_path = self.get_config_dir() / f"{config_name}.json"
            if config_path.exists():
                config_path.unlink()
                print(f"✓ Configuration '{config_name}' deleted")
                self.refresh_config_list()
                QMessageBox.information(self, "Deleted", f"Configuration '{config_name}' deleted")

    def apply_and_close(self):
        """Aplicar configuración actual y cerrar (para modo procesamiento)"""
        # Guardar la máscara actual
        if self.original_img is not None:
            # Recalcular máscara con configuración actual
            self.update_detection()
            # La máscara ya está en self.mask_result

            # NUEVO: Guardar máscaras a disco para poder usarlas en tests
            try:
                from pathlib import Path
                mask_dir = Path("data/results/debug")
                mask_dir.mkdir(parents=True, exist_ok=True)

                # Guardar máscara actual (dependiendo de qué imagen se esté mostrando)
                if self.processing_mode:
                    # Guardar máscara de la imagen actual (left o right)
                    current_name = "left" if self.current_view == "left" else "right"
                    mask_path = mask_dir / f"cable_mask_{current_name}.png"
                    cv2.imwrite(str(mask_path), self.mask_result)
                    print(f"✓ Mask saved: {mask_path}")
                else:
                    # Modo normal (una sola imagen)
                    mask_path = mask_dir / "cable_mask.png"
                    cv2.imwrite(str(mask_path), self.mask_result)
                    print(f"✓ Mask saved: {mask_path}")
            except Exception as e:
                print(f"⚠️ Could not save mask: {e}")

        self.accept()  # Cerrar ventana con éxito

    def get_current_mask(self):
        """Obtener máscara actual (para usar desde procesamiento)"""
        return self.mask_result

    def set_processing_mode(self, left_img, right_img, left_path="", right_path=""):
        """Configurar para modo procesamiento (mostrar ambas imágenes)"""
        self.processing_mode = True
        self.original_img = left_img
        self._prepare_preview()
        self.left_img_data = left_img
        self.right_img_data = right_img
        self.left_path = left_path
        self.right_path = right_path
        self.current_view = "left"  # "left" o "right"

        self.btn_apply_close.show()
        self.setWindowTitle(f"Tune Cable Detection - LEFT Image")

        # Añadir botón de switch si hay imagen derecha
        if right_img is not None:
            self.btn_switch = QPushButton("↔️ Switch to RIGHT Image")
            self.btn_switch.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    font-weight: bold;
                    padding: 8px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
            """)
            self.btn_switch.clicked.connect(self.switch_image_view)

            # Insertar botón antes del botón "Aplicar y Continuar"
            layout = self.layout()
            # Encontrar el layout de controles
            controls_widget = layout.itemAt(0).widget()
            controls_layout = controls_widget.layout()

            # Insertar antes del botón de aplicar
            btn_apply_index = controls_layout.indexOf(self.btn_apply_close)
            controls_layout.insertWidget(btn_apply_index, self.btn_switch)

    def switch_image_view(self):
        """Cambiar entre vista de imagen izquierda y derecha"""
        if self.current_view == "left":
            # Cambiar a imagen derecha
            self.current_view = "right"
            self.original_img = self.right_img_data
            self.setWindowTitle("Tune Cable Detection - RIGHT Image")
            self.btn_switch.setText("↔️ Switch to LEFT Image")
        else:
            # Cambiar a imagen izquierda
            self.current_view = "left"
            self.original_img = self.left_img_data
            self.setWindowTitle("Tune Cable Detection - LEFT Image")
            self.btn_switch.setText("↔️ Switch to RIGHT Image")

        # Actualizar detección con la nueva imagen
        self._prepare_preview()
        self.update_detection()


def open_cable_detection_tuner(left_img, right_img=None):
    """
    Abrir GUI de ajuste de detección de cable desde procesamiento

    Args:
        left_img: Imagen izquierda (numpy array)
        right_img: Imagen derecha (opcional, para procesamiento estéreo)

    Returns:
        tuple: (mask_left, mask_right) o None si se cancela
    """
    from PyQt5.QtWidgets import QDialog

    # Crear aplicación Qt si no existe
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # Crear GUI para imagen izquierda
    tuner = EdgeDetectionTuner()
    tuner.set_processing_mode(left_img, right_img)

    result = tuner.exec_()  # Modo diálogo (bloquea hasta que se cierre)

    if result == QDialog.Accepted:
        mask_left = tuner.get_current_mask()

        # Si hay imagen derecha, abrir GUI también para ella
        if right_img is not None:
            tuner_right = EdgeDetectionTuner()
            tuner_right.set_processing_mode(right_img, None)
            tuner_right.setWindowTitle("Tune Cable Detection - RIGHT Image")

            result_right = tuner_right.exec_()

            if result_right == QDialog.Accepted:
                mask_right = tuner_right.get_current_mask()
                return mask_left, mask_right
            else:
                return None  # Usuario canceló en imagen derecha

        return mask_left, mask_left  # Solo una imagen o usar misma config

    return None  # Usuario canceló


def open_cable_detection_tuner_with_switch(left_img, right_img, left_path="", right_path=""):
    """
    Abrir GUI de ajuste con switch entre imagen izquierda y derecha

    Args:
        left_img: Imagen izquierda (numpy array)
        right_img: Imagen derecha (numpy array)
        left_path: Ruta de imagen izquierda (para display)
        right_path: Ruta de imagen derecha (para display)

    Returns:
        tuple: (mask_left, mask_right) - máscaras para ambas imágenes
        None si se cancela
    """
    from PyQt5.QtWidgets import QDialog

    # Crear aplicación Qt si no existe
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # Variables para guardar máscaras
    mask_left = None
    mask_right = None

    # Crear GUI con capacidad de switch
    tuner = EdgeDetectionTuner()
    tuner.set_processing_mode(left_img, right_img, left_path, right_path)

    # Indicar que debe configurar ambas
    tuner.setWindowTitle("Configure Filter - Adjust for both images (use ↔️)")

    result = tuner.exec_()

    if result == QDialog.Accepted:
        # Usuario configuró para la imagen que estaba viendo
        # Necesitamos obtener máscaras para AMBAS imágenes

        # Guardar configuración actual
        current_config = {
            'method': tuner.method_combo.currentText(),
            'dilate': tuner.dilate_slider.value(),
            'erode': tuner.erode_slider.value(),
            'close': tuner.close_slider.value(),
            'cleanup_enabled': tuner.cleanup_enable.isChecked(),
            'cleanup_area_percent': tuner.cleanup_area_slider.value()
        }

        # Obtener parámetros específicos del método
        method = current_config['method']
        if method == "Canny":
            current_config['canny_low'] = tuner.canny_low_slider.value()
            current_config['canny_high'] = tuner.canny_high_slider.value()
            current_config['canny_aperture'] = int(tuner.canny_aperture_combo.currentText())
        elif method == "Sobel":
            current_config['sobel_ksize'] = int(tuner.sobel_ksize_combo.currentText())
            current_config['sobel_thresh'] = tuner.sobel_thresh_slider.value()
        elif method == "Laplacian":
            current_config['laplacian_ksize'] = int(tuner.laplacian_ksize_combo.currentText())
            current_config['laplacian_thresh'] = tuner.laplacian_thresh_slider.value()
        elif method == "Morphological Gradient":
            current_config['morphgrad_ksize'] = tuner.morphgrad_ksize_slider.value()
            current_config['morphgrad_thresh'] = tuner.morphgrad_thresh_slider.value()
        elif method == "Top-Hat":
            current_config['tophat_ksize'] = tuner.tophat_ksize_slider.value()
            current_config['tophat_thresh'] = tuner.tophat_thresh_slider.value()

        # Reusar el tuner (ya tiene los parámetros correctos) para computar
        # las máscaras finales a la misma escala que el usuario vio.
        # IMPORTANTE: _prepare_preview() debe llamarse cada vez que cambia la imagen
        # para que el threshold se calcule sobre el histograma correcto.

        tuner.original_img = left_img
        tuner._prepare_preview()
        tuner.update_detection()
        mask_left = tuner.get_current_mask()

        tuner.original_img = right_img
        tuner._prepare_preview()
        tuner.update_detection()
        mask_right = tuner.get_current_mask()

        # NUEVO: Guardar máscaras a disco para tests
        try:
            from pathlib import Path
            mask_dir = Path("data/results/debug")
            mask_dir.mkdir(parents=True, exist_ok=True)

            cv2.imwrite(str(mask_dir / "cable_mask_left.png"), mask_left)
            cv2.imwrite(str(mask_dir / "cable_mask_right.png"), mask_right)
            print(f"✓ Masks saved:")
            print(f"  - {mask_dir / 'cable_mask_left.png'}")
            print(f"  - {mask_dir / 'cable_mask_right.png'}")
        except Exception as e:
            print(f"⚠️ Could not save masks: {e}")

        return mask_left, mask_right

    return None


def main():
    app = QApplication(sys.argv)
    window = EdgeDetectionTuner()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
