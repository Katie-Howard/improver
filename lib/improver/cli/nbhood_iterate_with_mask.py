#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# (C) British Crown Copyright 2017-2019 Met Office.
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
"""Script to run neighbourhooding processing when iterating over a coordinate
defining a series of masks."""

from improver.argparser import ArgParser
from improver.nbhood.use_nbhood import (
    ApplyNeighbourhoodProcessingWithAMask,
    CollapseMaskedNeighbourhoodCoordinate)
from improver.utilities.load import load_cube
from improver.utilities.save import save_netcdf


def main(argv=None):
    """Load in arguments for applying neighbourhood processing when using a
    mask."""
    parser = ArgParser(
        description='Apply the requested neighbourhood method via the '
                    'ApplyNeighbourhoodProcessingWithAMask plugin to a file '
                    'with one diagnostic dataset in combination with a file '
                    'containing one or more masks. The mask dataset may have '
                    'an extra dimension compared to the input diagnostic. '
                    'In this case, the user specifies the name of '
                    'the extra coordinate and this coordinate is iterated '
                    'over so each mask is applied to seperate slices over the'
                    ' input data. These intermediate masked datasets are then'
                    ' concatenated, resulting in a dataset that has been '
                    ' processed using multiple masks and has gained an extra '
                    'dimension from the masking.  There is also an option to '
                    're-mask the output dataset, so that after '
                    'neighbourhood processing, non-zero values are only '
                    'present for unmasked grid points. '
                    'There is an alternative option of collapsing the '
                    'dimension that we gain using this processing using a '
                    'weighted average.')
    parser.add_argument('coord_for_masking', metavar='COORD_FOR_MASKING',
                        help='Coordinate to iterate over when applying a mask '
                             'to the neighbourhood processing. ')
    parser.add_argument('input_filepath', metavar='INPUT_FILE',
                        help='A path to an input NetCDF file to be processed.')
    parser.add_argument('input_mask_filepath', metavar='INPUT_MASK_FILE',
                        help='A path to an input mask NetCDF file to be '
                             'used to mask the input file.')
    parser.add_argument('output_filepath', metavar='OUTPUT_FILE',
                        help='The output path for the processed NetCDF.')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--radius', metavar='RADIUS', type=float,
                       help='The radius (in m) for neighbourhood processing.')
    group.add_argument('--radii-by-lead-time',
                       metavar=('RADII_BY_LEAD_TIME', 'LEAD_TIME_IN_HOURS'),
                       nargs=2,
                       help='The radii for neighbourhood processing '
                       'and the associated lead times at which the radii are '
                       'valid. The radii are in metres whilst the lead time '
                       'has units of hours. The radii and lead times are '
                       'expected as individual comma-separated lists with '
                       'the list of radii given first followed by a list of '
                       'lead times to indicate at what lead time each radii '
                       'should be used. For example: 10000,12000,14000 1,2,3 '
                       'where a lead time of 1 hour uses a radius of 10000m, '
                       'a lead time of 2 hours uses a radius of 12000m, etc.')
    parser.add_argument('--sum_or_fraction', default="fraction",
                        choices=["sum", "fraction"],
                        help='The neighbourhood output can either be in the '
                             'form of a sum of the neighbourhood, or a '
                             'fraction calculated by dividing the sum of the '
                             'neighbourhood by the neighbourhood area. '
                             '"fraction" is the default option.')
    group2 = parser.add_mutually_exclusive_group()
    group2.add_argument('--re_mask', action='store_true',
                        help='If re_mask is set (i.e. True), the output data '
                             'following neighbourhood processing is '
                             're-masked. This re-masking removes any values '
                             'that have been generated by neighbourhood '
                             'processing at grid points that were '
                             'originally masked. '
                             'If not set, re_mask defaults to False and no '
                             're-masking is applied to the neighbourhood '
                             'processed output. Therefore, the neighbourhood '
                             'processing may result in values being present '
                             'in areas that were originally masked. This '
                             'allows the the values in adjacent bands to be'
                             'weighted together if the additional dimension'
                             'from the masking process is collapsed.')
    group2.add_argument('--collapse_dimension', action='store_true',
                        help='Collapse the dimension from the mask, by doing '
                             'a weighted mean using the weights provided. '
                             'This is only suitable when the result is is '
                             'left unmasked, so there is data to weight '
                             'between the points in coordinate we are '
                             'collapsing.')
    parser.add_argument('--weights_for_collapsing_dim', metavar='WEIGHTS',
                        default=None,
                        help='A path to an weights NetCDF file containing the '
                             'weights which are used for collapsing the '
                             'dimension gained through masking.')
    parser.add_argument('--intermediate_filepath', default=None,
                        help='If provided the result after neighbourhooding, '
                             'before collapsing the extra dimension is saved '
                             'in the given filepath.')

    args = parser.parse_args(args=argv)

    cube = load_cube(args.input_filepath)
    mask_cube = load_cube(args.input_mask_filepath)

    if args.radius:
        radius_or_radii = args.radius
        lead_times = None
    elif args.radii_by_lead_time:
        radius_or_radii = args.radii_by_lead_time[0].split(",")
        lead_times = args.radii_by_lead_time[1].split(",")

    result = ApplyNeighbourhoodProcessingWithAMask(
        args.coord_for_masking, radius_or_radii, lead_times=lead_times,
        sum_or_fraction=args.sum_or_fraction,
        re_mask=args.re_mask).process(cube, mask_cube)

    if args.intermediate_filepath is not None:
        save_netcdf(result, args.intermediate_filepath)
    # Collapse with the masking dimension.
    if args.collapse_dimension:
        weights = load_cube(args.weights_for_collapsing_dim)
        result = CollapseMaskedNeighbourhoodCoordinate(
            args.coord_for_masking, weights=weights).process(result)
    save_netcdf(result, args.output_filepath)


if __name__ == "__main__":
    main()
