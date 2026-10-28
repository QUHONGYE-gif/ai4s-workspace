# Run from the repository root with the committed R001 evidence:
# pymol -cq experiments/R001-protein-design-smoke/visualize.pml

load experiments/R001-protein-design-smoke/evidence/backbone.pdb, rfd_backbone
load experiments/R001-protein-design-smoke/evidence/prediction.pdb, boltz_prediction

python
from pathlib import Path
Path("runs/R001-visualization").mkdir(parents=True, exist_ok=True)
python end

# Both structures have one chain and 80 residues. Pair the C-alpha atoms in residue order.
pair_fit boltz_prediction and chain A and name CA, rfd_backbone and chain A and name CA

hide everything
show cartoon, rfd_backbone or boltz_prediction
set cartoon_fancy_helices, 1
set cartoon_transparency, 0.45, rfd_backbone
color marine, rfd_backbone
color orange, boltz_prediction
bg_color white
set ray_opaque_background, 1
set ray_shadows, 0
set specular, 0
set orthoscopic, 1
set antialias, 2
orient rfd_backbone or boltz_prediction
zoom rfd_backbone or boltz_prediction, 1
turn y, 25
turn x, -10
scene overlay, store
png runs/R001-visualization/overlay.png, 1600, 1200, 300, 1

# Boltz writes per-residue pLDDT (0–100) into the PDB B-factor column.
disable rfd_backbone
spectrum b, red_yellow_green, boltz_prediction, 50, 100
scene confidence, store
png runs/R001-visualization/boltz-plddt.png, 1600, 1200, 300, 1
scene overlay, recall
save runs/R001-visualization/overlay-and-confidence.pse
