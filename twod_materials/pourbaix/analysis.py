"""
Create pourbaix diagrams for 2D materials against their ions in solution using
the scheme outlined in PHYSICAL REVIEW B 85, 235438 (2012)

Authors:
Michael Ashton
Kiran Mathew
"""

import os

from monty.serialization import loadfn

from pymatgen.core import Composition
from pymatgen.core.ion import Ion
from pymatgen import Element
from pymatgen.analysis.pourbaix.entry import PourbaixEntry, IonEntry
from pymatgen.analysis.pourbaix.maker import PourbaixDiagram
from pymatgen.analysis.pourbaix.plotter import PourbaixPlotter
from pymatgen.analysis.pourbaix.analyzer import PourbaixAnalyzer
from pymatgen.entries.computed_entries import ComputedEntry

import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

import twod_materials


PACKAGE_PATH = twod_materials.__file__.replace('__init__.pyc', '')
PACKAGE_PATH = PACKAGE_PATH.replace('__init__.py', '')
PACKAGE_PATH = os.path.join(PACKAGE_PATH, 'twod_materials/pourbaix')

ION_DATA = loadfn(os.path.join(PACKAGE_PATH, 'ions.yaml'))
END_MEMBERS = loadfn(os.path.join(PACKAGE_PATH, 'end_members.yaml'))
ION_COLORS = loadfn(os.path.join(PACKAGE_PATH, 'ion_colors.yaml'))


def contains_entry(entry_list, entry):
    """
    Function for filtering duplicate entries.
    """
    for ent in entry_list:
        if (ent.entry_id == entry.entry_id
            or (abs(entry.energy_per_atom - ent.energy_per_atom) < 1e-6
                and (entry.composition.reduced_formula ==
                     ent.composition.reduced_formula)
                )):
            return True


class Pourbaix2D():

    def __init__(self, composition, energy, *args, **kwargs):

        # Convert name to Composition object.
        self._composition = Composition(composition)
        self._energy = energy

    def make_plot(self, metastability=0.0, ion_concentration=1e-6):
        """
        args:

          metastability: desired metastable tolerance energy (meV/atom).
                         <=200 is generally a sensible range to use.

          ion_concentration: in mol/kg. Sensible values are between
                             1e-8 and 1.
        """

        # Create a ComputedEntry object for the 2D material.
        cmpd = ComputedEntry(self._composition, self._energy)

        # Define the chemsys that describes the 2D compound.
        chemsys = ['O', 'H'] + [elt.symbol for elt in cmpd.composition.elements
                                if elt.symbol not in ['O', 'H']]

        # Experimental ionic energies
        # See ions.yaml for ion formation energies and references.
        exp_dict = ION_DATA['ExpFormEnergy']
        ion_correction = ION_DATA['IonCorrection']

        # Pick out the ions pertaining to the 2D compound.
        ion_dict = dict()
        for elt in chemsys:
            if elt not in ['O', 'H'] and exp_dict[elt]:
                ion_dict.update(exp_dict[elt])

        elements = [Element(elt) for elt in chemsys if elt not in ['O', 'H']]

        # Add "correction" for metastability
        cmpd.correction -= float(cmpd.composition.num_atoms)\
            * float(metastability)/1000.0

        # Calculate formation energy of the compound from its end
        # members
        form_energy = cmpd.energy
        for elt in self._composition.as_dict():
            form_energy -= END_MEMBERS[elt] * cmpd.composition[elt]

        # Convert the compound entry to a pourbaix entry.
        # Default concentration for solid entries = 1
        pbx_cmpd = PourbaixEntry(cmpd)
        pbx_cmpd.g0_replace(form_energy)
        pbx_cmpd.reduced_entry()

        # Add corrected ionic entries to the pourbaix diagram
        # dft corrections for experimental ionic energies:
        # Persson et.al PHYSICAL REVIEW B 85, 235438 (2012)
        pbx_ion_entries = list()

        # Get PourbaixEntry corresponding to each ion.
        # Default concentration for ionic entries = 1e-6
        # ion_energy = ion_exp_energy + ion_correction * factor
        # where factor = fraction of element el in the ionic entry
        # compared to the reference entry
        for elt in elements:
            for key in ion_dict:
                comp = Ion.from_formula(key)
                if comp.composition[elt] != 0:
                    factor = comp.composition[elt]
                    energy = ion_dict[key]
                    pbx_entry_ion = PourbaixEntry(IonEntry(comp, energy))
                    pbx_entry_ion.correction = ion_correction[elt.symbol]\
                        * factor
                    pbx_entry_ion.conc = ion_concentration
                    pbx_entry_ion.name = key
                    pbx_ion_entries.append(pbx_entry_ion)

        # Generate and plot Pourbaix diagram
        # Each bulk solid/ion has a free energy g of the form:
        # g = g0_ref + 0.0591 * log10(conc) - nO * mu_H2O +
        # (nH - 2nO) * pH + phi * (-nH + 2nO + q)

        all_entries = [pbx_cmpd] + pbx_ion_entries

        pourbaix = PourbaixDiagram(all_entries)

        # Analysis features
        panalyzer = PourbaixAnalyzer(pourbaix)
        instability = panalyzer.get_e_above_hull(pbx_cmpd)

        plotter = PourbaixPlotter(pourbaix)
        plot = plotter.get_pourbaix_plot(limits=[[0, 14], [-2, 2]],
                                         label_domains=True)
        fig = plot.gcf()
        ax1 = fig.gca()

        # Add coloring to highlight the stability region for the 2D
        # material, if one exists.
        stable_entries = plotter.pourbaix_plot_data(
            limits=[[0, 14], [-2, 2]])[0]

        for entry in stable_entries:
            if entry == pbx_cmpd:
                col = plt.cm.Blues(0)
            else:
                col = plt.cm.rainbow(float(
                    ION_COLORS[entry.composition.reduced_formula]))

            vertices = plotter.domain_vertices(entry)
            patch = Polygon(vertices, closed=True, fill=True, color=col)
            ax1.add_patch(patch)

        fig.set_size_inches((11.5, 9))
        plot.tight_layout(pad=1.09)

        # Save plot
        if metastability:
            plot.suptitle('Metastable Tolerance ='
                          ' {} meV/atom'.format(metastability),
                          fontsize=20)
            plot.savefig('{}_{}meV.pdf'.format(
                self._composition.reduced_formula, metastability),
                transparent=True)
        else:
            plot.savefig('{}.pdf'.format(self._composition.reduced_formula),
                         transparent=True)

        plot.close()

        return instability
