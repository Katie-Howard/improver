# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# (C) British Crown Copyright 2017-2020 Met Office.
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
"""Unit tests for the utilities.OccurrenceWithinVicinity plugin."""

import unittest

import iris
import numpy as np
from cf_units import Unit
from iris.coords import DimCoord
from iris.cube import Cube
from iris.tests import IrisTest

from improver.utilities.spatial import OccurrenceWithinVicinity

from improver_tests.set_up_test_cubes import (
    add_coordinate,
    set_up_variable_cube,
)


def set_up_cube():
    timestep = np.array([402192.5])
    cube = set_up_variable_cube(
        np.zeros((1, 5, 5), dtype=np.float32),
        "lwe_precipitation_rate",
        "m s-1",
        "equalarea",
        )
    cube = add_coordinate(
        cube,
        timestep,
        "time",
    )
    cube = iris.util.new_axis(cube, 'time')   
    cube.transpose([1, 0, 2, 3])
    return cube


class Test__repr__(IrisTest):

    """Test the repr method."""

    def test_basic(self):
        """Test that the __repr__ returns the expected string."""
        result = str(OccurrenceWithinVicinity(10000))
        msg = "<OccurrenceWithinVicinity: distance: 10000>"
        self.assertEqual(result, msg)


class Test_maximum_within_vicinity(IrisTest):

    """Test the maximum_within_vicinity method."""

    def setUp(self):
        """Set up distance."""
        self.distance = 2000
        self.grid_values = np.arange(0.0, 10000.0, 2000.0)

    def test_basic(self):
        """Test for binary events to determine where there is an occurrence
        within the vicinity."""
        expected = np.array(
            [
                [1.0, 1.0, 1.0, 0.0, 0.0],
                [1.0, 1.0, 1.0, 1.0, 1.0],
                [0.0, 0.0, 1.0, 1.0, 1.0],
                [0.0, 0.0, 1.0, 1.0, 1.0],
                [0.0, 0.0, 0.0, 0.0, 0.0],
            ]
        )
        data = np.zeros((1, 1, 5, 5))
        data[0, 0, 0, 1] = 1.0
        data[0, 0, 2, 3] = 1.0
        cube = set_up_cube()
        cube.data = data
        cube = cube[0, 0, :, :]
        cube.coord('projection_y_coordinate').points = self.grid_values
        cube.coord('projection_x_coordinate').points = self.grid_values
        result = OccurrenceWithinVicinity(self.distance).maximum_within_vicinity(cube)
        self.assertIsInstance(result, Cube)
        self.assertArrayAlmostEqual(result.data, expected)

    def test_fuzzy(self):
        """Test for non-binary events to determine where there is an occurrence
        within the vicinity."""
        expected = np.array(
            [
                [1.0, 1.0, 1.0, 0.0, 0.0],
                [1.0, 1.0, 1.0, 0.5, 0.5],
                [0.0, 0.0, 0.5, 0.5, 0.5],
                [0.0, 0.0, 0.5, 0.5, 0.5],
                [0.0, 0.0, 0.0, 0.0, 0.0],
            ]
        )
        data = np.zeros((1, 1, 5, 5))
        data[0, 0, 0, 1] = 1.0
        data[0, 0, 2, 3] = 0.5
        cube = set_up_cube()
        cube.data = data
        cube = cube[0, 0, :, :]
        cube.coord('projection_y_coordinate').points = self.grid_values
        cube.coord('projection_x_coordinate').points = self.grid_values        
        result = OccurrenceWithinVicinity(self.distance).maximum_within_vicinity(cube)
        self.assertIsInstance(result, Cube)
        self.assertArrayAlmostEqual(result.data, expected)

    def test_different_distance(self):
        """Test for binary events to determine where there is an occurrence
        within the vicinity for an alternative distance."""
        expected = np.array(
            [
                [1.0, 1.0, 1.0, 1.0, 1.0],
                [1.0, 1.0, 1.0, 1.0, 1.0],
                [1.0, 1.0, 1.0, 1.0, 1.0],
                [0.0, 1.0, 1.0, 1.0, 1.0],
                [0.0, 1.0, 1.0, 1.0, 1.0],
            ]
        )
        data = np.zeros((1, 1, 5, 5))
        data[0, 0, 0, 1] = 1.0
        data[0, 0, 2, 3] = 1.0
        cube = set_up_cube()
        cube.data = data
        cube = cube[0, 0, :, :]
        cube.coord('projection_y_coordinate').points = self.grid_values
        cube.coord('projection_x_coordinate').points = self.grid_values 
        distance = 4000.0
        result = OccurrenceWithinVicinity(distance).maximum_within_vicinity(cube)
        self.assertIsInstance(result, Cube)
        self.assertArrayAlmostEqual(result.data, expected)

    def test_masked_data(self):
        """Test masked values are ignored in OccurrenceWithinVicinity."""
        expected = np.array(
            [
                [1.0, 1.0, 1.0, 0.0, 10.0],
                [1.0, 1.0, 1.0, 1.0, 1.0],
                [0.0, 0.0, 1.0, 1.0, 1.0],
                [0.0, 0.0, 1.0, 1.0, 1.0],
                [0.0, 0.0, 0.0, 0.0, 0.0],
            ]
        )
        data = np.zeros((1, 1, 5, 5))
        data[0, 0, 0, 1] = 1.0
        data[0, 0, 2, 3] = 1.0
        data[0, 0, 0, 4] = 10.0
        mask = np.zeros((1, 1, 5, 5))
        mask[0, 0, 0, 4] = 1
        masked_data = np.ma.array(data, mask=mask)
        cube = set_up_cube()
        cube.data = masked_data
        cube = cube[0, 0, :, :]
        cube.coord('projection_y_coordinate').points = self.grid_values
        cube.coord('projection_x_coordinate').points = self.grid_values
        result = OccurrenceWithinVicinity(self.distance).maximum_within_vicinity(cube)
        self.assertIsInstance(result, Cube)
        self.assertIsInstance(result.data, np.ma.core.MaskedArray)
        self.assertArrayAlmostEqual(result.data.data, expected)
        self.assertArrayAlmostEqual(result.data.mask, mask[0, 0, :, :])


class Test_process(IrisTest):

    """Test the process method."""

    def setUp(self):
        """Set up distance."""
        self.distance = 2000
        self.coords = np.array([0.0, 2000.0, 4000.0, 6000.0])
        self.timesteps = np.array([402192.5, 402195.5], dtype = np.float32)

    def test_with_multiple_realizations_and_times(self):
        """Test for multiple realizations and times, so that multiple
        iterations will be required within the process method."""
        expected = np.array(
            [
                [
                    [
                        [0.0, 0.0, 0.0, 0.0],
                        [1.0, 1.0, 1.0, 0.0],
                        [1.0, 1.0, 1.0, 0.0],
                        [1.0, 1.0, 1.0, 0.0],
                    ],
                    [
                        [0.0, 0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0, 0.0],
                    ],
                ],
                [
                    [
                        [0.0, 0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0, 0.0],
                    ],
                    [
                        [0.0, 0.0, 1.0, 1.0],
                        [0.0, 0.0, 1.0, 1.0],
                        [0.0, 0.0, 1.0, 1.0],
                        [0.0, 0.0, 0.0, 0.0],
                    ],
                ],
            ]
        )
        data = np.zeros((2, 2, 4, 4))
        data[0, 0, 2, 1] = 1.0
        data[1, 1, 1, 3] = 1.0
        cube = set_up_variable_cube(
            np.zeros((2, 4, 4), dtype = np.float32),
            "lwe_precipitation_rate",
            "m s-1",
            "equalarea",
        )
        cube = add_coordinate(
            cube,
            self.timesteps,
            "time",
            order = [1, 0, 2, 3],
        )
        cube.data = data
        cube.coord('projection_y_coordinate').points = self.coords
        cube.coord('projection_x_coordinate').points = self.coords
        orig_shape = cube.data.copy().shape
        result = OccurrenceWithinVicinity(self.distance)(cube)
        self.assertIsInstance(result, Cube)
        self.assertEqual(result.data.shape, orig_shape)
        self.assertArrayAlmostEqual(result.data, expected)

    def test_with_multiple_realizations(self):
        """Test for multiple realizations, so that multiple
        iterations will be required within the process method."""
        expected = np.array(
            [
                [
                    [0.0, 0.0, 0.0, 0.0],
                    [1.0, 1.0, 1.0, 0.0],
                    [1.0, 1.0, 1.0, 0.0],
                    [1.0, 1.0, 1.0, 0.0],
                ],
                [
                    [0.0, 0.0, 1.0, 1.0],
                    [0.0, 0.0, 1.0, 1.0],
                    [0.0, 0.0, 1.0, 1.0],
                    [0.0, 0.0, 0.0, 0.0],
                ],
            ]
        )
        data = np.zeros((2, 4, 4), dtype = np.float32)
        data[0, 2, 1] = 1.0
        data[1, 1, 3] = 1.0
        cube = set_up_variable_cube(
            np.zeros((2, 4, 4), dtype = np.float32),
            "lwe_precipitation_rate",
            "m s-1",
            "equalarea",
        )
        cube.data = data
        cube.coord('projection_y_coordinate').points = self.coords
        cube.coord('projection_x_coordinate').points = self.coords
        result = OccurrenceWithinVicinity(self.distance)(cube)
        self.assertIsInstance(result, Cube)
        self.assertArrayAlmostEqual(result.data, expected)

    def test_with_multiple_times(self):
        """Test for multiple times, so that multiple
        iterations will be required within the process method."""
        expected = np.array(
            [
                [
                    [0.0, 0.0, 0.0, 0.0],
                    [1.0, 1.0, 1.0, 0.0],
                    [1.0, 1.0, 1.0, 0.0],
                    [1.0, 1.0, 1.0, 0.0],
                ],
                [
                    [0.0, 0.0, 1.0, 1.0],
                    [0.0, 0.0, 1.0, 1.0],
                    [0.0, 0.0, 1.0, 1.0],
                    [0.0, 0.0, 0.0, 0.0],
                ],
            ]
        )
        data = np.zeros((2, 4, 4), dtype = np.float32)
        data[ 0, 2, 1] = 1.0
        data[1, 1, 3] = 1.0
        cube = set_up_variable_cube(
            np.zeros((4, 4), dtype = np.float32),
            "lwe_precipitation_rate",
            "m s-1",
            "equalarea",
            )
        cube = add_coordinate(
            cube,
            self.timesteps,
            "time",
        )
        cube.coord('projection_y_coordinate').points = self.coords
        cube.coord('projection_x_coordinate').points = self.coords
        cube.data = data
        orig_shape = cube.data.shape
        result = OccurrenceWithinVicinity(self.distance)(cube)
        self.assertIsInstance(result, Cube)
        self.assertEqual(result.data.shape, orig_shape)
        self.assertArrayAlmostEqual(result.data, expected)

    def test_no_realization_or_time(self):
        """Test for no realizations and no times, so that the iterations
        will not require slicing cubes within the process method."""
        expected = np.array(
            [
                [0.0, 0.0, 0.0, 0.0],
                [1.0, 1.0, 1.0, 0.0],
                [1.0, 1.0, 1.0, 0.0],
                [1.0, 1.0, 1.0, 0.0],
            ]
        )
        data = np.zeros((4, 4), dtype = np.float32)
        data[2, 1] = 1.0
        cube = set_up_variable_cube(
            data,
            "lwe_precipitation_rate",
            "m s-1",
            "equalarea",
        )
        cube.coord('projection_y_coordinate').points = self.coords
        cube.coord('projection_x_coordinate').points = self.coords
        cube = iris.util.squeeze(cube)
        orig_shape = cube.data.shape
        result = OccurrenceWithinVicinity(self.distance)(cube)
        self.assertIsInstance(result, Cube)
        self.assertEqual(result.data.shape, orig_shape)
        self.assertArrayAlmostEqual(result.data, expected)


if __name__ == "__main__":
    unittest.main()
