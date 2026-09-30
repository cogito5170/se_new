"""DFT (GPAW, PBE, plane waves): Delta G_H* on Ru(0001) and, as a control, Pt(111).
Delta G_H* = E(slab+H) - E(slab) - 1/2 E(H2) + 0.24 eV   (Norskov 2005 ZPE/entropy correction)
Small, cheap settings: 2x2 cell (1/4 ML), 4 layers (bottom 2 fixed), 350 eV, 4x4x1 k.
"""
import json, sys, time
from ase.build import hcp0001, fcc111, add_adsorbate
from ase.constraints import FixAtoms
from ase.optimize import BFGS
from ase import Atoms
from gpaw import GPAW, PW, FermiDirac

ECUT, K = 350, (4, 4, 1)
out = {}
from gpaw.mpi import world
log = open("out/dft_log.txt", "a") if world.rank == 0 else open("/dev/null", "w")


def calc(name, kpts=K):
    return GPAW(mode=PW(ECUT), xc="PBE", kpts=kpts, occupations=FermiDirac(0.1),
                txt=f"out/gpaw_{name}.txt", symmetry={"point_group": False})


def energy(atoms, name, relax=True):
    atoms.calc = calc(name, K if atoms.pbc[0] else (1, 1, 1))
    if relax:
        BFGS(atoms, logfile=f"out/bfgs_{name}.txt").run(fmax=0.05, steps=60)
    e = atoms.get_potential_energy()
    print(name, e, time.strftime("%X"), file=log, flush=True)
    return e


h2 = Atoms("H2", positions=[(0, 0, 0), (0, 0, 0.75)], cell=(8, 8.2, 8.4), pbc=False)
h2.center()
h2.calc = GPAW(mode=PW(ECUT), xc="PBE", txt="out/gpaw_H2.txt")
BFGS(h2, logfile="out/bfgs_H2.txt").run(fmax=0.02)
eH2 = h2.get_potential_energy()
print("H2", eH2, file=log, flush=True)

systems = dict(
    Ru=lambda: hcp0001("Ru", size=(2, 2, 4), a=2.706, c=4.282, vacuum=7.0),
    Pt=lambda: fcc111("Pt", size=(2, 2, 4), a=3.924, vacuum=7.0),
)
for el, build in systems.items():
    slab = build()
    slab.set_constraint(FixAtoms(indices=[a.index for a in slab if a.tag >= 3]))
    e_slab = energy(slab.copy(), f"{el}_slab", relax=True)
    res = {}
    for site in ("fcc", "hcp"):
        s = build()
        s.set_constraint(FixAtoms(indices=[a.index for a in s if a.tag >= 3]))
        add_adsorbate(s, "H", 1.0, site)
        e = energy(s, f"{el}_H_{site}")
        dE = e - e_slab - 0.5 * eH2
        res[site] = dict(dE=dE, dG=dE + 0.24)
    out[el] = res
    print(el, res, file=log, flush=True)
    json.dump(dict(E_H2=eH2, results=out, settings=dict(ecut=ECUT, k=K, cell="2x2 (1/4 ML)", layers=4)),
              open("out/dft.json", "w"), indent=1)
print("done", file=log, flush=True)
