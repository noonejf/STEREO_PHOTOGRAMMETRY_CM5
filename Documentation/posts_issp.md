# Posts for the ISSP, the camera payload

Cinco posts en el registro del que publico Alvaro sobre el star tracker:
alrededor de 150 palabras, lenguaje llano, una idea por post y un gancho al
siguiente. Ingles, sin guiones largos, sin numeros que sean un resultado.

**La version con imagenes es el PDF:**
`Documentation/Posts_ISSP/pdf/Posts_ISSP.pdf`, que trae cada post con la
figura que lo acompana y un pie de foto sugerido. Las figuras las arman
`tools/armar_figuras_posts.py` y `tools/foto_gui_posts.py`, y se compila con
`.\compilar.ps1 "Documentation\Posts_ISSP"`. Este archivo es solo el texto.

**Dos cosas que arreglar antes de publicar.** El primero dice *the second of
our three instruments*: cambia el ordinal si el tuyo va tercero. Y aqui no se
nombra la universidad, el estudio ni los socios, asi que agrega lo que el
grupo haya acordado decir en publico.

**Lo que estos posts dejan fuera a proposito**, para poder defender la
eleccion: ninguna cifra de exactitud, ningun puntaje de contraste ni de
segmentacion, nada de la calibracion, ni el largo del tether, ni la
separacion entre satelites, ni numeros de parte, precios, proveedores ni
fechas. La unica excepcion es la figura del post 1, que es del entregable D5
y trae escritos la base de 100 mm y el campo de vision.

---

## Post 1, que es el instrumento

Hi everyone! Here is the second of our three instruments: the stereo camera
payload.

Its job is to measure a cable. Two satellites fly joined by a thin tether, and
somebody has to know what that tether is actually doing up there: how long it
is, whether it is straight or sagging, how far it reaches away from us. Our
instrument answers that with two cameras and no contact, which is the only way
to measure something you cannot touch and must not disturb.

The prototype is a Raspberry Pi Compute Module 5 with two 12 MP camera
modules, an 8 mm lens on each, and a machined support that holds both cameras
and the computer as one rigid piece. Rigid matters more than it sounds: the
whole measurement comes from the small difference between the two images, so
if the cameras move with respect to each other, the measurement moves with
them.

Next post: why a cable is the hardest thing you can hand to a stereo camera.

## Post 2, por que un cable es dificil

Stereo vision measures distance the way your eyes do. Find the same point in
both images, see how much it shifted between them, and the shift gives you the
depth. The whole method rests on being able to say *the same point*.

A bare cable will not let you. Slide a few centimetres along it and the image
does not change: same brightness, same width, same everything. The two patches
below come from one photograph of ours, hundreds of pixels apart along the
cable, and nothing in either of them says which part of the cable it came
from. Feature-based methods go looking for exactly that kind of distinctive
patch, find nothing to hold on to, and either fail or quietly return noise.

Distance makes it worse. At the ranges we care about the tether is one or two
pixels wide, so there is no shape left to work with, only a faint line on a
dark background.

Next post: what we do instead of matching points.

## Post 3, medir una curva y no puntos

If you cannot match points on a cable, match the cable itself.

Our pipeline treats the tether as one continuous curve instead of a cloud of
features. We separate it from the background in both images, find its two
ends, and trace the path between them, which is the hard part: a hanging
cable crosses in front of itself, and at every crossing the software has to
work out which two branches are the same strand passing through. Then, point
by point along the traced curve, we triangulate. The same place on the cable,
seen from two cameras a known distance apart, gives one position in 3D.

What comes out is not a pretty point cloud. It is a short list of numbers
about the tether: how long it is measured along its own curve, how straight
it is, how far it reaches in depth.

Next post: teaching software to find a cable that is a few pixels wide.

## Post 4, encontrar el cable

Before anything can be measured, the cable has to be separated from
everything else in the frame, and at the distances we work at it is only a few
pixels wide. A hand-tuned threshold does this well in the frame you tuned it
on and badly in the next one.

So we trained a model for it instead. It is not deep learning: it is a
classical machine learning classifier that looks at each pixel through a
handful of descriptors, its colour and how much its neighbourhood looks like a
thin ridge, which is the same kind of detector used to find blood vessels in
medical images. It runs on a laptop in seconds and needs no GPU.

The interesting part was the training data. Hand-labelled frames of a real
cable are slow to produce, so we wrote a generator that draws synthetic
scenes with the cable in a known position, and trained on those plus a few
real ones.

Next post: how we test any of this on the ground.

## Post 5, probarlo en la oscuridad

In orbit this instrument works in the dark, with the Sun as the only lamp and
in a direction nobody gets to choose. That is hard to argue about from a desk,
so we test it in a blacked out television studio, with the cable strung across
the room and professional film fixtures standing in for the Sun.

One thing we did not expect to spend time on: where to point the lamps. A
spotlight aimed at a thin cable across many metres lights a bright patch and
leaves the rest dark, and the direction it comes from decides whether the
camera sees a lit cable or a silhouette. Rather than find that out on the day,
we rebuilt the studio in a renderer, with the real fixtures and their real
beam angles, and tried the arrangements there first. The simulation lives
inside the same application that processes the real frames, so the pictures
and the numbers sit next to each other.

The session itself is coming. We will report what the instrument measured, and
where the simulation turned out to be wrong.

---

## Si hace falta un sexto

Calibracion: que el error de reproyeccion no es una medida de calidad sino el
residuo que el optimizador acaba de minimizar, y que un tablero casi de frente
no permite recuperar la distancia focal por mucho que se repita la toma. La
imagen seria `charuco_board_5x7.png` o una captura de la calibracion guiada
pidiendo la pose siguiente.
