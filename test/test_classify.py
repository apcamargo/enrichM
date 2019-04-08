#!/usr/bin/env python
###############################################################################
#                                                                             #
#    This program is free software: you can redistribute it and/or modify     #
#    it under the terms of the GNU General Public License as published by     #
#    the Free Software Foundation, either version 3 of the License, or        #
#    (at your option) any later version.                                      #
#                                                                             #
#    This program is distributed in the hope that it will be useful,          #
#    but WITHOUT ANY WARRANTY; without even the implied warranty of           #
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the            #
#    GNU General Public License for more details.                             #
#                                                                             #
#    You should have received a copy of the GNU General Public License        #
#    along with this program. If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
###############################################################################
# Imports
import unittest
import os.path
import sys
import subprocess
import tempfile

###############################################################################

path_to_script 		= os.path.join(os.path.dirname(os.path.realpath(__file__)),'..','bin','enrichm')
path_to_data 		= os.path.join(os.path.dirname(os.path.realpath(__file__)),'data')
path_to_annotate	= os.path.join(path_to_data, 'enrichm_annotate')

sys.path = [os.path.join(os.path.dirname(os.path.realpath(__file__)),'..')]+sys.path

###############################################################################

class Tests(unittest.TestCase):

    def test_classify_from_matrix(self):
        tmp = tempfile.mkdtemp()
        bin = os.path.join(path_to_data, 'test_nucleic_bin')
        ko_matrix = os.path.join(path_to_annotate, 'ko_frequency_table.tsv')
        cmd = '%s classify --genome_and_annotation_matrix %s --output %s --force --verbosity 1' % (path_to_script, ko_matrix, tmp)
        subprocess.call(cmd, shell=True)

    def test_classify_from_lf(self):
        tmp = tempfile.mkdtemp()
        bin = os.path.join(path_to_data, 'test_nucleic_bin')
        ko_matrix = os.path.join(path_to_annotate, 'ko_frequency_file.tsv')
        cmd = '%s classify --genome_and_annotation_file %s --output %s --force --verbosity 1' % (path_to_script, ko_matrix, tmp)
        subprocess.call(cmd, shell=True)

    def test_classify_with_custom_modules(self):
        tmp = tempfile.mkdtemp()
        bin = os.path.join(path_to_data, 'test_nucleic_bin')
        ko_matrix = os.path.join(path_to_annotate, 'ko_frequency_file.tsv')
        cmd = '%s classify --genome_and_annotation_file %s --output %s --force --verbosity 1' % (path_to_script, ko_matrix, tmp)
        subprocess.call(cmd, shell=True)

if __name__ == "__main__":
    unittest.main()