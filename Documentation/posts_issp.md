# Posts for the ISSP, the camera payload

Four posts in the register of Alvaro's star tracker post: around 150 words,
plain language, one part list, one technical idea explained in a sentence, and
a hook into the next one. English, no em dashes, no numbers that would be a
result.

**Two things to fix before posting.** The opener says *the second of our three
instruments*: change the ordinal if this one goes third. And nothing here
names the university, the studio or the mission partners, on purpose, so add
whatever the group has already agreed to say in public.

**What these posts deliberately leave out**, so the choice can be defended:
no accuracy figures and no contrast or segmentation scores, no calibration
results, no tether length or satellite separation, no baseline between the two
cameras, no part numbers, prices or suppliers, no dates, and no photograph of
the support that would give away how the instrument is built.

**Con imagenes, en PDF:** `Documentation/Posts_ISSP/pdf/Posts_ISSP.pdf`, que
trae cada post con la figura que lo acompana y un pie de foto sugerido. Las
figuras las arma `tools/armar_figuras_posts.py` y se compila con
`.\compilar.ps1 "Documentation\Posts_ISSP"`. What is left is
the problem, the approach and the parts, which is what Alvaro's post gives
about his.

---

## Post 1, what the instrument is

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

## Post 2, why a cable is hard

Stereo vision measures distance the way your eyes do. Find the same point in
both images, see how much it shifted between them, and the shift gives you the
depth. The whole method rests on being able to say *the same point*.

A bare cable will not let you. Slide a few centimetres along it and the image
does not change: same brightness, same width, same everything. The standard
algorithms look for a patch of texture to match and find nothing to hold on
to, so they either fail or quietly return noise. This is well known, and it is
exactly the case our instrument has to work in.

So we stopped trying to match points and started tracing the cable as a curve.
We separate it from the background, find its two ends, follow it through the
places where it crosses in front of itself, and then measure along the curve
instead of across the image.

Next post: teaching software to find a cable that is a few pixels wide.

## Post 3, finding the cable

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

## Post 4, testing in the dark

In orbit this instrument works in the dark, with the Sun as the only lamp and
in a direction nobody gets to choose. That is hard to argue about from a desk,
so we test it in a blacked out television studio, with the cable strung across
the room and professional film fixtures standing in for the Sun.

One thing we did not expect to spend time on: where to point the lamps. A
spotlight aimed at a thin cable across many metres lights a bright patch and
leaves the rest dark, and the direction it comes from decides whether the
camera sees a lit cable or a silhouette. Rather than find that out on the day,
we rebuilt the studio in a renderer, with the real fixtures and their real
beam angles, and tried the arrangements there first.

The session itself is coming. We will report what the instrument measured, and
where the simulation turned out to be wrong.
