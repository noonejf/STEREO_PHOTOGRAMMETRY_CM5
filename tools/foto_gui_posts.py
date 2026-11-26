"""Captura la pagina Simulation para el PDF de posts.

Va aparte de ``armar_figuras_posts.py`` porque levanta Qt y la ventana
entera, que es un proceso con su propio ciclo de vida y no conviene meterlo
en un script que solo manipula imagenes.

    python tools/foto_gui_posts.py

Escribe Documentation/Posts_ISSP/figures/fig_gui_sphere.png. En Windows
arranca en Processing Only Mode, asi que no hacen falta camaras.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from PyQt5.QtWidgets import QApplication, QTabWidget   # noqa: E402
from PyQt5.QtCore import QTimer                        # noqa: E402

from gui.theme import APP_QSS                          # noqa: E402
from gui.main_window import PhotogrammetryDashboard    # noqa: E402
from config.camera_config import CameraConfig          # noqa: E402

DEST = os.path.join(ROOT, "Documentation", "Posts_ISSP", "figures")
os.makedirs(DEST, exist_ok=True)

app = QApplication(sys.argv)
app.setStyle("Fusion")
app.setStyleSheet(APP_QSS)
ventana = PhotogrammetryDashboard(CameraConfig())
ventana.resize(1920, 1200)
ventana.show()


def disparar():
    # 5 es la pagina Simulation y 0 su primera pestana, la esfera del sol.
    ventana.stack.setCurrentIndex(5)
    app.processEvents()
    pestanas = ventana.sim_page.findChild(QTabWidget)
    pestanas.setCurrentIndex(0)
    # Dos vueltas: la primera deja la pestana puesta y la segunda la pinta.
    app.processEvents()
    app.processEvents()
    ruta = os.path.join(DEST, "fig_gui_sphere.png")
    ventana.grab().save(ruta)
    print(f"fig_gui_sphere.png  {os.path.getsize(ruta)/1024:.0f} kB")
    app.quit()


# La pagina carga sus CSV y sus vistas al construirse; sin la espera la
# captura sale con las tarjetas vacias.
QTimer.singleShot(2500, disparar)
app.exec_()
