# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# (C) British Crown Copyright 2017-2018 Met Office.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
"""Unit tests for the uv_index function."""

import unittest
import numpy as np

from cf_units import Unit
from iris.tests import IrisTest

from improver.tests.set_up_test_cubes import set_up_variable_cube
from improver.uv_index import calculate_uv_index


class Test_uv_index(IrisTest):
    """ Tests that the uv_index plugin calculates the UV index
    correctly. """

    def setUp(self):
        """Set up the cubes for upward and downward uv fluxes, 
        and also one with different units."""
        data_up = np.array([[0.2, 0.2, 0.2], [0.2, 0.2, 0.2]],
                           dtype=np.float32)
        self.cube_uv_up = set_up_variable_cube(data_up,
                                               name='radiation flux in '
                                               'UV upward at surface',
                                               units='W/m^2')
        data_down = np.array([[0.1, 0.1, 0.1], [0.1, 0.1, 0.1]],
                             dtype=np.float32)
        self.cube_uv_down = set_up_variable_cube(data_down,
                                                 name='radiation flux in '
                                                 'downward at surface',
                                                 units='W/m^2')
        data_down_diff_units = np.array([[0.1, 0.1, 0.1], [0.1, 0.1, 0.1]],
                             dtype=np.float32)
        self.cube_diff_units = set_up_variable_cube(data_down,
                                                 name='radiation flux in '
                                                 'downward at surface',
                                                 units='m')        

    def test_basic(self):
        """ Test that the a basic uv calculation works, using the
        default scaling factor. Make sure the output is a cube
        with the expected data."""
        expected = np.array([[0.3, 0.3, 0.3], [0.3, 0.3, 0.3]],
                            dtype=np.float32)
        result = calculate_uv_index(self.cube_uv_down, self.cube_uv_up)
        self.assertArrayEqual(result.data, expected)

    def test_scale_factor(self):
        """ Test the uv calculation works when changing the scale factor. Make
        sure the output is a cube with the expected data."""
        expected = np.array([[3.0, 3.0, 3.0], [3.0, 3.0, 3.0]],
                            dtype=np.float32)
        result = calculate_uv_index(self.cube_uv_down, self.cube_uv_up,
                                    scale_factor=10)
        self.assertArrayEqual(result.data, expected)

    def test_metadata(self):
        """ Tests that the uv index output has the correct metadata (no units,
        and name = uv index)."""
        result = calculate_uv_index(self.cube_uv_down, self.cube_uv_up)
        self.assertEqual(str(result.standard_name), 'ultraviolet_index')
        self.assertEqual((result.units), Unit("1"))

    def test_diff_units(self):
        """Tests that there is an Error if the input uv files have difference
        units. """
        msg = 'The input uv files do not have the same units.'
        with self.assertRaisesRegex(ValueError, msg):
            calculate_uv_index(self.cube_uv_down, self.cube_diff_units)


if __name__ == '__main__':
    unittest.main()
