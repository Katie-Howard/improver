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
"""
This module defines all the "plugins" specific for ensemble calibration.

"""
import datetime
import numpy as np
from scipy import stats
from scipy.optimize import minimize
from scipy.stats import norm
import warnings

import iris
from iris.exceptions import CoordinateNotFoundError

from improver.ensemble_calibration.ensemble_calibration_utilities import (
    convert_cube_data_to_2d, check_predictor_of_mean_flag)
from improver.utilities.cube_manipulation import enforce_coordinate_ordering
from improver.utilities.temporal import (
    cycletime_to_datetime, datetime_to_cycletime, datetime_to_iris_time,
    iris_time_to_datetime)


class ContinuousRankedProbabilityScoreMinimisers(object):
    """
    Minimise the Continuous Ranked Probability Score (CRPS)

    Calculate the optimised coefficients for minimising the CRPS based on
    assuming a particular probability distribution for the phenomenon being
    minimised.

    The number of coefficients that will be optimised depend upon the initial
    guess.

    Minimisation is performed using the Nelder-Mead algorithm for 200
    iterations to limit the computational expense.
    Note that the BFGS algorithm was initially trialled but had a bug
    in comparison to comparative results generated in R.

    """

    # Maximum iterations for minimisation using Nelder-Mead.
    MAX_ITERATIONS = 200

    # The tolerated percentage change for the final iteration when
    # performing the minimisation.
    TOLERATED_PERCENTAGE_CHANGE = 5

    # An arbitrary value set if an infinite value is detected
    # as part of the minimisation.
    BAD_VALUE = np.float64(999999)

    def __init__(self):
        # Dictionary containing the minimisation functions, which will
        # be used, depending upon the distribution, which is requested.
        self.minimisation_dict = {
            "gaussian": self.normal_crps_minimiser,
            "truncated gaussian": self.truncated_normal_crps_minimiser}

    def __repr__(self):
        """Represent the configured plugin instance as a string."""
        result = ('<ContinuousRankedProbabilityScoreMinimisers: '
                  'minimisation_dict: {}>')
        print_dict = {}
        for key in self.minimisation_dict:
            print_dict.update({key: self.minimisation_dict[key].__name__})
        return result.format(print_dict)

    def crps_minimiser_wrapper(
            self, initial_guess, forecast_predictor, truth, forecast_var,
            predictor_of_mean_flag, distribution):
        """
        Function to pass a given minimisation function to the scipy minimize
        function to estimate optimised values for the coefficients.

        Args:
            initial_guess (list):
                List of optimised coefficients.
                Order of coefficients is [gamma, delta, alpha, beta].
            forecast_predictor (iris.cube.Cube):
                Cube containing the fields to be used as the predictor,
                either the ensemble mean or the ensemble realizations.
            truth (iris.cube.Cube):
                Cube containing the field, which will be used as truth.
            forecast_var (iris.cube.Cube):
                Cube containg the field containing the ensemble variance.
            predictor_of_mean_flag (str):
                String to specify the input to calculate the calibrated mean.
                Currently the ensemble mean ("mean") and the ensemble
                realizations ("realizations") are supported as the predictors.
            distribution (str):
                String used to access the appropriate minimisation function
                within self.minimisation_dict.

        Returns:
            optimised_coeffs (list):
                List of optimised coefficients.
                Order of coefficients is [gamma, delta, alpha, beta].

        """
        def calculate_percentage_change_in_last_iteration(allvecs):
            """
            Calculate the percentage change that has occurred within
            the last iteration of the minimisation. If the percentage change
            between the last iteration and the last-but-one iteration exceeds
            the threshold, a warning message is printed.

            Args:
                allvecs (list):
                    List of numpy arrays containing the optimised coefficients,
                    after each iteration.
            """
            last_iteration_percentage_change = np.absolute(
                (allvecs[-1] - allvecs[-2]) / allvecs[-2])*100
            if (np.any(last_iteration_percentage_change >
                       self.TOLERATED_PERCENTAGE_CHANGE)):
                np.set_printoptions(suppress=True)
                msg = ("\nThe final iteration resulted in a percentage change "
                       "that is greater than the accepted threshold of 5% "
                       "i.e. {}. "
                       "\nA satisfactory minimisation has not been achieved. "
                       "\nLast iteration: {}, "
                       "\nLast-but-one iteration: {}"
                       "\nAbsolute difference: {}\n").format(
                           last_iteration_percentage_change, allvecs[-1],
                           allvecs[-2], np.absolute(allvecs[-2]-allvecs[-1]))
                warnings.warn(msg)

        try:
            minimisation_function = self.minimisation_dict[distribution]
        except KeyError as err:
            msg = ("Distribution requested {} is not supported in {}"
                   "Error message is {}".format(
                       distribution, self.minimisation_dict, err))
            raise KeyError(msg)

        # Ensure predictor_of_mean_flag is valid.
        check_predictor_of_mean_flag(predictor_of_mean_flag)

        if predictor_of_mean_flag.lower() == "mean":
            forecast_predictor_data = forecast_predictor.data.flatten()
            truth_data = truth.data.flatten()
            forecast_var_data = forecast_var.data.flatten()
        elif predictor_of_mean_flag.lower() == "realizations":
            truth_data = truth.data.flatten()
            forecast_predictor = (
                enforce_coordinate_ordering(
                    forecast_predictor, "realization"))
            forecast_predictor_data = convert_cube_data_to_2d(
                forecast_predictor)
            forecast_var_data = forecast_var.data.flatten()

        initial_guess = np.array(initial_guess, dtype=np.float32)
        forecast_predictor_data = forecast_predictor_data.astype(np.float32)
        forecast_var_data = forecast_var_data.astype(np.float32)
        truth_data = truth_data.astype(np.float32)
        sqrt_pi = np.sqrt(np.pi).astype(np.float32)

        optimised_coeffs = minimize(
            minimisation_function, initial_guess,
            args=(forecast_predictor_data, truth_data,
                  forecast_var_data, sqrt_pi, predictor_of_mean_flag),
            method="Nelder-Mead",
            options={"maxiter": self.MAX_ITERATIONS, "return_all": True})
        if not optimised_coeffs.success:
            msg = ("Minimisation did not result in convergence after "
                   "{} iterations. \n{}".format(
                       self.MAX_ITERATIONS, optimised_coeffs.message))
            warnings.warn(msg)
        calculate_percentage_change_in_last_iteration(optimised_coeffs.allvecs)
        return optimised_coeffs.x.astype(np.float32)

    def normal_crps_minimiser(
            self, initial_guess, forecast_predictor, truth, forecast_var,
            sqrt_pi, predictor_of_mean_flag):
        """
        Minimisation function to calculate coefficients based on minimising the
        CRPS for a normal distribution.

        Scientific Reference:
        Gneiting, T. et al., 2005.
        Calibrated Probabilistic Forecasting Using Ensemble Model Output
        Statistics and Minimum CRPS Estimation.
        Monthly Weather Review, 133(5), pp.1098-1118.

        Args:
            initial_guess (list):
                List of optimised coefficients.
                Order of coefficients is [gamma, delta, alpha, beta].
            forecast_predictor (np.ndarray):
                Data to be used as the predictor,
                either the ensemble mean or the ensemble realizations.
            truth (np.ndarray):
                Data to be used as truth.
            forecast_var (np.ndarray):
                Ensemble variance data.
            sqrt_pi (np.ndarray):
                Square root of Pi
            predictor_of_mean_flag (str):
                String to specify the input to calculate the calibrated mean.
                Currently the ensemble mean ("mean") and the ensemble
                realizations ("realizations") are supported as the predictors.

        Returns:
            result (float):
                Minimum value for the CRPS achieved.

        """
        if predictor_of_mean_flag.lower() == "mean":
            beta = initial_guess[2:]
        elif predictor_of_mean_flag.lower() == "realizations":
            beta = np.array(
                [initial_guess[2]]+(initial_guess[3:]**2).tolist(),
                dtype=np.float32
            )

        new_col = np.ones(truth.shape, dtype=np.float32)
        all_data = np.column_stack((new_col, forecast_predictor))
        mu = np.dot(all_data, beta)
        sigma = np.sqrt(
            initial_guess[0]**2 + initial_guess[1]**2 * forecast_var)
        xz = (truth - mu) / sigma
        normal_cdf = norm.cdf(xz)
        normal_pdf = norm.pdf(xz)
        result = np.nansum(
            sigma * (xz * (2 * normal_cdf - 1) + 2 * normal_pdf - 1 / sqrt_pi))
        if not np.isfinite(np.min(mu/sigma)):
            result = self.BAD_VALUE
        return result

    def truncated_normal_crps_minimiser(
            self, initial_guess, forecast_predictor, truth, forecast_var,
            sqrt_pi, predictor_of_mean_flag):
        """
        Minimisation function to calculate coefficients based on minimising the
        CRPS for a truncated_normal distribution.

        Scientific Reference:
        Thorarinsdottir, T.L. & Gneiting, T., 2010.
        Probabilistic forecasts of wind speed: Ensemble model
        output statistics by using heteroscedastic censored regression.
        Journal of the Royal Statistical Society.
        Series A: Statistics in Society, 173(2), pp.371-388.

        Args:
            initial_guess (list):
                List of optimised coefficients.
                Order of coefficients is [gamma, delta, alpha, beta].
            forecast_predictor (np.ndarray):
                Data to be used as the predictor,
                either the ensemble mean or the ensemble realizations.
            truth (np.ndarray):
                Data to be used as truth.
            forecast_var (np.ndarray):
                Ensemble variance data.
            sqrt_pi (np.ndarray):
                Square root of Pi
            predictor_of_mean_flag (str):
                String to specify the input to calculate the calibrated mean.
                Currently the ensemble mean ("mean") and the ensemble
                realizations ("realizations") are supported as the predictors.

        Returns:
            result (float):
                Minimum value for the CRPS achieved.

        """
        if predictor_of_mean_flag.lower() == "mean":
            beta = initial_guess[2:]
        elif predictor_of_mean_flag.lower() == "realizations":
            beta = np.array(
                [initial_guess[2]]+(initial_guess[3:]**2).tolist(),
                dtype=np.float32
            )

        new_col = np.ones(truth.shape, dtype=np.float32)
        all_data = np.column_stack((new_col, forecast_predictor))
        mu = np.dot(all_data, beta)
        sigma = np.sqrt(
            initial_guess[0]**2 + initial_guess[1]**2 * forecast_var)
        xz = (truth - mu) / sigma
        normal_cdf = norm.cdf(xz)
        normal_pdf = norm.pdf(xz)
        x0 = mu / sigma
        normal_cdf_0 = norm.cdf(x0)
        normal_cdf_root_two = norm.cdf(np.sqrt(2) * x0)
        result = np.nansum(
            (sigma / normal_cdf_0**2) *
            (xz * normal_cdf_0 * (2 * normal_cdf + normal_cdf_0 - 2) +
             2 * normal_pdf * normal_cdf_0 -
             normal_cdf_root_two / sqrt_pi))
        if not np.isfinite(np.min(mu/sigma)) or (np.min(mu/sigma) < -3):
            result = self.BAD_VALUE
        return result


class EstimateCoefficientsForEnsembleCalibration(object):
    """
    Class focussing on estimating the optimised coefficients for ensemble
    calibration.
    """
    # Logical flag for whether initial guess estimates for the coefficients
    # will be estimated using linear regression i.e.
    # ESTIMATE_COEFFICIENTS_FROM_LINEAR_MODEL_FLAG = True, or whether default
    # values will be used instead i.e.
    # ESTIMATE_COEFFICIENTS_FROM_LINEAR_MODEL_FLAG = False.
    ESTIMATE_COEFFICIENTS_FROM_LINEAR_MODEL_FLAG = True

    def __init__(self, distribution, current_cycle, desired_units=None,
                 predictor_of_mean_flag="mean"):
        """
        Create an ensemble calibration plugin that, for Nonhomogeneous Gaussian
        Regression, calculates coefficients based on historical forecasts and
        applies the coefficients to the current forecast.

        Args:
            distribution (str):
                Name of distribution. Assume that the current forecast can be
                represented using this distribution.
            current_cycle (str):
                The current cycle in YYYYMMDDTHHMMZ format e.g. 20171122T0100Z.
                This is used to create a forecast_reference_time coordinate
                on the resulting EMOS coefficients cube.

        Kwargs:
            desired_units (str or cf_units.Unit):
                The unit that you would like the calibration to be undertaken
                in. The current forecast, historical forecast and truth will be
                converted as required.
            predictor_of_mean_flag (str):
                String to specify the input to calculate the calibrated mean.
                Currently the ensemble mean ("mean") and the ensemble
                realizations ("realizations") are supported as the predictors.

        """
        self.distribution = distribution
        self.current_cycle = current_cycle
        self.desired_units = desired_units
        # Ensure predictor_of_mean_flag is valid.
        check_predictor_of_mean_flag(predictor_of_mean_flag)
        self.predictor_of_mean_flag = predictor_of_mean_flag
        self.minimiser = ContinuousRankedProbabilityScoreMinimisers()
        # Setting default values for coeff_names. Beta is the final
        # coefficient name in the list, as there can potentially be
        # multiple beta coefficients if the ensemble realizations, rather
        # than the ensemble mean, are provided as the predictor.
        self.coeff_names = ["gamma", "delta", "alpha", "beta"]

        import imp
        try:
            imp.find_module('statsmodels')
        except ImportError:
            statsmodels_found = False
            if predictor_of_mean_flag.lower() == "realizations":
                msg = (
                    "The statsmodels can not be imported. "
                    "Will not be able to calculate an initial guess from "
                    "the individual ensemble realizations. "
                    "A default initial guess will be used without "
                    "estimating coefficients from a linear model.")
                warnings.warn(msg, ImportWarning)
        else:
            statsmodels_found = True
            import statsmodels.api as sm
            self.sm = sm
        self.statsmodels_found = statsmodels_found

    def __repr__(self):
        """Represent the configured plugin instance as a string."""
        result = ('<EstimateCoefficientsForEnsembleCalibration: '
                  'distribution: {}; '
                  'current_cycle: {}; '
                  'desired_units: {}; '
                  'predictor_of_mean_flag: {}; '
                  'minimiser: {}; '
                  'coeff_names: {}>')
        return result.format(
            self.distribution, self.current_cycle, self.desired_units,
            self.predictor_of_mean_flag, self.minimiser.__class__,
            self.coeff_names)

    def create_coefficients_cube(
            self, optimised_coeffs, historic_forecast):
        """Create a cube for storing the coefficients computed using EMOS.

        .. See the documentation for examples of these cubes.
        .. include:: extended_documentation/ensemble_calibration/
           ensemble_calibration/create_coefficients_cube.rst

        Args:
            optimised_coeffs (list):
                List of optimised coefficients.
                Order of coefficients is [gamma, delta, alpha, beta].
            historic_forecast (iris.cube.Cube):
                The cube containing the historic forecast.

        Returns:
            cube (iris.cube.Cube):
                Cube constructed using the coefficients provided and using
                metadata from the historic_forecast cube.  The cube contains
                a coefficient_index dimension coordinate where the points
                of the coordinate are integer values and a
                coefficient_name auxiliary coordinate where the points of
                the coordinate are e.g. gamma, delta, alpha, beta.

        """
        if self.predictor_of_mean_flag.lower() == "realizations":
            realization_coeffs = []
            for realization in historic_forecast.coord("realization").points:
                realization_coeffs.append(
                    "{}{}".format(self.coeff_names[-1], np.int32(realization)))
            coeff_names = self.coeff_names[:-1] + realization_coeffs
        else:
            coeff_names = self.coeff_names

        if len(optimised_coeffs) != len(coeff_names):
            msg = ("The number of coefficients in {} must equal the "
                   "number of coefficient names {}.".format(
                        optimised_coeffs, coeff_names))
            raise ValueError(msg)

        coefficient_index = iris.coords.DimCoord(
            np.arange(len(optimised_coeffs), dtype=np.int32),
            long_name="coefficient_index", units="1")
        coefficient_name = iris.coords.AuxCoord(
            coeff_names, long_name="coefficient_name", units="no_unit")
        dim_coords_and_dims = [(coefficient_index, 0)]
        aux_coords_and_dims = [(coefficient_name, 0)]

        # Create a forecast_reference_time coordinate.
        frt_point = cycletime_to_datetime(self.current_cycle)
        try:

            frt_coord = (
                historic_forecast.coord("forecast_reference_time").copy(
                    datetime_to_iris_time(frt_point, time_units="seconds")))
        except CoordinateNotFoundError:
            pass
        else:
            aux_coords_and_dims.append((frt_coord, None))

        # Create forecast period and time coordinates.
        try:
            fp_point = (
                np.unique(historic_forecast.coord("forecast_period").points))
            fp_coord = (
                historic_forecast.coord("forecast_period").copy(fp_point))
        except CoordinateNotFoundError:
            pass
        else:
            aux_coords_and_dims.append((fp_coord, None))
            if historic_forecast.coords("time"):
                frt_point = cycletime_to_datetime(self.current_cycle)
                # Ensure that the fp_point is determined with units of seconds.
                copy_of_fp_coord = (
                    historic_forecast.coord("forecast_period").copy())
                copy_of_fp_coord.convert_units("seconds")
                fp_point, = np.unique(copy_of_fp_coord.points)
                time_point = (
                    frt_point + datetime.timedelta(seconds=float(fp_point)))
                time_point = datetime_to_iris_time(
                    time_point,
                    time_units=str(historic_forecast.coord("time").units))
                time_coord = historic_forecast.coord("time").copy(time_point)
                aux_coords_and_dims.append((time_coord, None))

        attributes = {"diagnostic_standard_name": historic_forecast.name()}
        for attribute in historic_forecast.attributes.keys():
            if attribute.endswith("model_configuration"):
                attributes[attribute] = (
                    historic_forecast.attributes[attribute])

        cube = iris.cube.Cube(
            optimised_coeffs, long_name="emos_coefficients", units="1",
            dim_coords_and_dims=dim_coords_and_dims,
            aux_coords_and_dims=aux_coords_and_dims, attributes=attributes)
        return cube

    def compute_initial_guess(
            self, truth, forecast_predictor, predictor_of_mean_flag,
            estimate_coefficients_from_linear_model_flag,
            no_of_realizations=None):
        """
        Function to compute initial guess of the a and beta components of the
        EMOS coefficients by linear regression of the forecast predictor
        and the truth, if requested. Otherwise, default values for a and b
        will be used.

        Default values have been chosen based on Figure 8 in the
        2017 ensemble calibration report available on the Science Plugin
        Documents Confluence page.

        Args:
            truth (iris.cube.Cube):
                Cube containing the field, which will be used as truth.
            forecast_predictor (iris.cube.Cube):
                Cube containing the fields to be used as the predictor,
                either the ensemble mean or the ensemble realizations.
            predictor_of_mean_flag (str):
                String to specify the input to calculate the calibrated mean.
                Currently the ensemble mean ("mean") and the ensemble
                realizations ("realizations") are supported as the predictors.
            estimate_coefficients_from_linear_model_flag (bool):
                Flag whether coefficients should be estimated from
                the linear regression, or static estimates should be used.
            no_of_realizations (int):
                Number of realizations, if ensemble realizations are to be
                used as predictors. Default is None.

        Returns:
            initial_guess (list):
                List of coefficients to be used as initial guess.
                Order of coefficients is [gamma, delta, alpha, beta].

        """

        if (predictor_of_mean_flag.lower() == "mean" and
                not estimate_coefficients_from_linear_model_flag):
            initial_guess = [1, 1, 0, 1]
        elif (predictor_of_mean_flag.lower() == "realizations" and
              not estimate_coefficients_from_linear_model_flag):
            initial_guess = [1, 1, 0] + np.repeat(
                1, no_of_realizations).tolist()
        elif estimate_coefficients_from_linear_model_flag:
            if predictor_of_mean_flag.lower() == "mean":
                # Find all values that are not NaN.
                truth_not_nan = ~np.isnan(truth.data.flatten())
                forecast_not_nan = ~np.isnan(forecast_predictor.data.flatten())
                combined_not_nan = (
                    np.all(
                        np.row_stack([truth_not_nan, forecast_not_nan]),
                        axis=0))
                if not any(combined_not_nan):
                    gradient, intercept = ([np.nan, np.nan])
                else:
                    gradient, intercept, _, _, _ = (
                        stats.linregress(
                            forecast_predictor.data.flatten()[
                                combined_not_nan],
                            truth.data.flatten()[combined_not_nan]))
                initial_guess = [1, 1, intercept, gradient]
            elif predictor_of_mean_flag.lower() == "realizations":
                if self.statsmodels_found:
                    truth_data = truth.data.flatten()
                    forecast_predictor = (
                        enforce_coordinate_ordering(
                            forecast_predictor, "realization"))
                    forecast_data = np.array(
                        convert_cube_data_to_2d(
                            forecast_predictor, transpose=False),
                        dtype=np.float32
                    )
                    # Find all values that are not NaN.
                    truth_not_nan = ~np.isnan(truth_data)
                    forecast_not_nan = ~np.isnan(forecast_data)
                    combined_not_nan = (
                        np.all(
                            np.row_stack([truth_not_nan, forecast_not_nan]),
                            axis=0))
                    val = self.sm.add_constant(
                        forecast_data[:, combined_not_nan].T)
                    est = self.sm.OLS(truth_data[combined_not_nan], val).fit()
                    intercept = est.params[0]
                    gradient = est.params[1:]
                    initial_guess = [1, 1, intercept]+gradient.tolist()
                else:
                    initial_guess = (
                        [1, 1, 0] + np.repeat(1, no_of_realizations).tolist())
        return np.array(initial_guess, dtype=np.float32)

    def estimate_coefficients_for_ngr(self, historic_forecast, truth):
        """
        Using Nonhomogeneous Gaussian Regression/Ensemble Model Output
        Statistics, estimate the required coefficients from historical
        forecasts.

        The main contents of this method is:

        1. Metadata checks to ensure that the current forecast, historic
           forecast and truth exist in a form that can be processed.
        2. Loop through times within the concatenated current forecast cube:

           1. Extract the desired forecast period from the historic forecasts
              to match the current forecasts. Apply unit conversion to ensure
              that historic forecasts have the desired units for calibration.
           2. Extract the relevant truth to co-incide with the time within
              the historic forecasts. Apply unit conversion to ensure
              that the truth has the desired units for calibration.
           3. Calculate mean and variance.
           4. Calculate initial guess at coefficient values by performing a
              linear regression, if requested, otherwise default values are
              used.
           5. Perform minimisation.

        Args:
            historic_forecast (iris.cube.Cube):
                The cube containing the historical forecasts used
                for calibration.
            truth (iris.cube.Cube:
                The cube containing the truth used for calibration.

        Returns:
            coefficients_cube (iris.cube.Cube):
                Cube containing the coefficients estimated using EMOS.
                The cube contains a coefficient_index dimension coordinate
                and a coefficient_name auxiliary coordinate.

        """
        # Ensure predictor_of_mean_flag is valid.
        check_predictor_of_mean_flag(self.predictor_of_mean_flag)

        # Set default values for whether there are NaN values within the
        # initial guess.
        nan_in_initial_guess = False

        # Make sure inputs have the same units.
        if self.desired_units:
            historic_forecast.convert_units(self.desired_units)
            truth.convert_units(self.desired_units)

        if historic_forecast.units != truth.units:
            msg = ("The historic forecast units of {} do not match "
                   "the truth units {}. These units must match, so that "
                   "the coefficients can be estimated.")
            raise ValueError(msg)

        if self.predictor_of_mean_flag.lower() == "mean":
            no_of_realizations = None
            forecast_predictor = historic_forecast.collapsed(
                "realization", iris.analysis.MEAN)
        elif self.predictor_of_mean_flag.lower() == "realizations":
            no_of_realizations = len(
                historic_forecast.coord("realization").points)
            forecast_predictor = historic_forecast

        forecast_var = historic_forecast.collapsed(
            "realization", iris.analysis.VARIANCE)

        # Computing initial guess for EMOS coefficients
        # If no initial guess from a previous iteration, or if there
        # are NaNs in the initial guess, calculate an initial guess.
        if "initial_guess" not in locals() or nan_in_initial_guess:
            initial_guess = self.compute_initial_guess(
                truth, forecast_predictor, self.predictor_of_mean_flag,
                self.ESTIMATE_COEFFICIENTS_FROM_LINEAR_MODEL_FLAG,
                no_of_realizations=no_of_realizations)

        if np.any(np.isnan(initial_guess)):
            nan_in_initial_guess = True

        if not nan_in_initial_guess:
            # Need to access the x attribute returned by the
            # minimisation function.
            optimised_coeffs = (
                self.minimiser.crps_minimiser_wrapper(
                    initial_guess, forecast_predictor,
                    truth, forecast_var,
                    self.predictor_of_mean_flag,
                    self.distribution.lower()))
            initial_guess = optimised_coeffs
        else:
            optimised_coeffs = initial_guess

        coefficients_cube = (
            self.create_coefficients_cube(optimised_coeffs, historic_forecast))
        return coefficients_cube


class ApplyCoefficientsFromEnsembleCalibration(object):
    """
    Class to apply the optimised EMOS coefficients to future dates.

    """
    def __init__(
            self, current_forecast, coefficients_cube,
            predictor_of_mean_flag="mean"):
        """
        Create an ensemble calibration plugin that, for Nonhomogeneous Gaussian
        Regression, applies coefficients created using on historical forecasts
        and applies the coefficients to the current forecast.

        Args:
            current_forecast (iris.cube.Cube):
                The cube containing the current forecast.
            coefficients_cube (iris.cube.Cube):
                Cube containing the coefficients estimated using EMOS.
                The cube contains a coefficient_index dimension coordinate
                where the points of the coordinate are integer values and a
                coefficient_name auxiliary coordinate where the points of
                the coordinate are e.g. gamma, delta, alpha, beta.
            predictor_of_mean_flag (str):
                String to specify the input to calculate the calibrated mean.
                Currently the ensemble mean ("mean") and the ensemble
                realizations ("realizations") are supported as the predictors.

        """
        self.current_forecast = current_forecast
        self.coefficients_cube = coefficients_cube
        for coord_name in ["forecast_period", "time",
                           "forecast_reference_time"]:
            try:
                if (self.current_forecast.coord(coord_name) !=
                        self.coefficients_cube.coord(coord_name)):
                    msg = ("The {} coordinate of the current forecast cube "
                           "and coefficients cube differs. "
                           "current forecast: {}, "
                           "coefficients cube: {}").format(
                                coord_name,
                                self.current_forecast.coord(coord_name),
                                self.coefficients_cube.coord(coord_name))
                    raise ValueError(msg)
            except CoordinateNotFoundError:
                pass

        # Ensure predictor_of_mean_flag is valid.
        check_predictor_of_mean_flag(predictor_of_mean_flag)
        self.predictor_of_mean_flag = predictor_of_mean_flag

    def __repr__(self):
        """Represent the configured plugin instance as a string."""
        result = ('<ApplyCoefficientsFromEnsembleCalibration: '
                  'current_forecast: {}; '
                  'coefficients_cube: {}; '
                  'predictor_of_mean_flag: {}>')
        return result.format(
            self.current_forecast.name(), self.coefficients_cube.name(),
            self.predictor_of_mean_flag)

    def apply_params_entry(self):
        """
        Wrapping function to calculate the forecast predictor and forecast
        variance prior to applying coefficients to the current forecast.

        Returns:
            (tuple) : tuple containing:
                **calibrated_forecast_predictor** (iris.cube.Cube):
                    Cube containing the calibrated version of the
                    ensemble predictor, either the ensemble mean or
                    the ensemble realizations.
                **calibrated_forecast_variance** (iris.cube.Cube):
                    Cube containing the calibrated version of the
                    ensemble variance, either the ensemble mean or
                    the ensemble realizations.

        """
        if self.predictor_of_mean_flag.lower() == "mean":
            forecast_predictors = self.current_forecast.collapsed(
                "realization", iris.analysis.MEAN)
        elif self.predictor_of_mean_flag.lower() == "realizations":
            forecast_predictors = self.current_forecast

        forecast_vars = self.current_forecast.collapsed(
            "realization", iris.analysis.VARIANCE)

        calibrated_forecast_predictor, calibrated_forecast_var = (
            self._apply_params(forecast_predictors, forecast_vars))
        return calibrated_forecast_predictor, calibrated_forecast_var

    def _apply_params(self, forecast_predictors, forecast_vars):
        """
        Function to apply EMOS coefficients to all required dates.

        Args:
            forecast_predictors (iris.cube.Cube):
                Cube containing the forecast predictor e.g. ensemble mean
                or ensemble realizations.
            forecast_vars (iris.cube.Cube):
                Cube containing the forecast variance e.g. ensemble variance.

        Returns:
            (tuple) : tuple containing:
                **calibrated_forecast_predictor** (iris.cube.Cube):
                    Cube containing the calibrated version of the
                    ensemble predictor, either the ensemble mean or
                    the ensemble realizations.
                **calibrated_forecast_variance** (iris.cube.Cube):
                    Cube containing the calibrated version of the
                    ensemble variance, either the ensemble mean or
                    the ensemble realizations.
        """
        optimised_coeffs = (
            dict(zip(self.coefficients_cube.coord("coefficient_name").points,
                     self.coefficients_cube.data)))

        # Calculate the predicted mean based on whether the coefficients
        # were estimated using the mean as the predictor or using the
        # ensemble realizations as the predictor.
        if self.predictor_of_mean_flag.lower() == "mean":
            # Calculate predicted mean = a + b*X, where X is the
            # raw ensemble mean. In this case, b = beta.
            a_and_b = [optimised_coeffs["alpha"], optimised_coeffs["beta"]]
            forecast_predictor_flat = forecast_predictors.data.flatten()
            col_of_ones = (
                np.ones(forecast_predictor_flat.shape, dtype=np.float32))
            ones_and_mean = (
                np.column_stack((col_of_ones, forecast_predictor_flat)))
            predicted_mean = np.dot(ones_and_mean, a_and_b)
            calibrated_forecast_predictor = forecast_predictors
        elif self.predictor_of_mean_flag.lower() == "realizations":
            # Calculate predicted mean = a + b*X, where X is the
            # raw ensemble mean. In this case, b = beta^2.
            beta_values = np.array([], dtype=np.float32)
            for key in optimised_coeffs.keys():
                if key.startswith("beta"):
                    beta_values = np.append(beta_values, optimised_coeffs[key])
            a_and_b = np.append(optimised_coeffs["alpha"], beta_values**2)
            forecast_predictor_flat = (
                convert_cube_data_to_2d(forecast_predictors))
            forecast_var_flat = forecast_vars.data.flatten()
            col_of_ones = np.ones(forecast_var_flat.shape, dtype=np.float32)
            ones_and_mean = (
                np.column_stack((col_of_ones, forecast_predictor_flat)))
            predicted_mean = np.dot(ones_and_mean, a_and_b)
            # Calculate mean of ensemble realizations, as only the
            # calibrated ensemble mean will be returned.
            calibrated_forecast_predictor = (
                forecast_predictors.collapsed(
                    "realization", iris.analysis.MEAN))

        xlen = len(forecast_predictors.coord(axis="x").points)
        ylen = len(forecast_predictors.coord(axis="y").points)

        calibrated_forecast_predictor.data = (
            np.reshape(predicted_mean, (ylen, xlen)))

        calibrated_forecast_var = forecast_vars
        # Calculating the predicted variance, based on the
        # raw variance S^2, where predicted variance = c + dS^2,
        # where c = (gamma)^2 and d = (delta)^2
        calibrated_forecast_var.data = (
            optimised_coeffs["gamma"]**2 +
            optimised_coeffs["delta"]**2 * forecast_vars.data)

        return calibrated_forecast_predictor, calibrated_forecast_var


class EnsembleCalibration(object):
    """
    Plugin to wrap the core EMOS processes:
    1. Estimate optimised EMOS coefficients from training period.
    2. Apply optimised EMOS coefficients for future dates.

    """
    def __init__(self, calibration_method, distribution, desired_units=None,
                 predictor_of_mean_flag="mean"):
        """
        Create an ensemble calibration plugin that, for Nonhomogeneous Gaussian
        Regression, calculates coefficients based on historical forecasts and
        applies the coefficients to the current forecast.

        Args:
            calibration_method (str):
                The calibration method that will be applied.
                Supported methods are:

                    ensemble model output statistics
                    nonhomogeneous gaussian regression

                Currently these methods are not supported:

                    logistic regression
                    bayesian model averaging

            distribution (str):
                The distribution that will be used for calibration. This will
                be dependent upon the input phenomenon. This has to be
                supported by the minimisation functions in
                ContinuousRankedProbabilityScoreMinimisers.
        Kwargs:
            desired_units (str or cf_units.Unit):
                The unit that you would like the calibration to be undertaken
                in. The current forecast, historical forecast and truth will be
                converted as required.
            predictor_of_mean_flag (str):
                String to specify the input to calculate the calibrated mean.
                Currently the ensemble mean ("mean") and the ensemble
                realizations ("realizations") are supported as the predictors.
        """
        self.calibration_method = calibration_method
        self.distribution = distribution
        self.desired_units = desired_units
        self.predictor_of_mean_flag = predictor_of_mean_flag

    def __repr__(self):
        """Represent the configured plugin instance as a string."""
        result = ('<EnsembleCalibration: '
                  'calibration_method: {}; '
                  'distribution: {}; '
                  'desired_units: {}; '
                  'predictor_of_mean_flag: {};')
        return result.format(
            self.calibration_method, self.distribution, self.desired_units,
            self.predictor_of_mean_flag)

    def process(self, current_forecast, historic_forecast, truth):
        """
        Performs ensemble calibration through the following steps:
        1. Estimate optimised coefficients from training period.
        2. Apply optimised coefficients to current forecast.

        Args:
            current_forecast (iris.cube.Cube):
                The cube that provides the input forecast for
                the current cycle.
            historic_forecast (iris.cube.Cube):
                The cube that provides the input historic forecasts
                for calibration.
            truth (iris.cube.Cube):
                The cube that provides the input truth for
                calibration with dates matching the historic forecasts.

        Returns:
            (tuple): tuple containing:
                **calibrated_forecast_predictor** (iris.cube.Cube):
                    Cube containing the calibrated forecast predictor.
                **calibrated_forecast_variance** (iris.cube.Cube):
                    Cube containing the calibrated forecast variance.

        """
        def format_calibration_method(calibration_method):
            """Lowercase input string, and replace underscores with spaces."""
            return calibration_method.lower().replace("_", " ")

        # Ensure predictor_of_mean_flag is valid.
        check_predictor_of_mean_flag(self.predictor_of_mean_flag)

        if (format_calibration_method(self.calibration_method) in
                ["ensemble model output statistics",
                 "nonhomogeneous gaussian regression"]):
            if (format_calibration_method(self.distribution) in
                    ["gaussian", "truncated gaussian"]):
                current_cycle = datetime_to_cycletime(
                    iris_time_to_datetime(
                        current_forecast.coord("forecast_reference_time"))[0])
                ec = EstimateCoefficientsForEnsembleCalibration(
                    self.distribution, current_cycle=current_cycle,
                    desired_units=self.desired_units,
                    predictor_of_mean_flag=self.predictor_of_mean_flag)
                coefficient_cube = (
                    ec.estimate_coefficients_for_ngr(
                        historic_forecast, truth))
        else:
            msg = ("Other calibration methods are not available. "
                   "{} is not available".format(
                       format_calibration_method(self.calibration_method)))
            raise ValueError(msg)
        ac = ApplyCoefficientsFromEnsembleCalibration(
            current_forecast, coefficient_cube,
            predictor_of_mean_flag=self.predictor_of_mean_flag)
        (calibrated_forecast_predictor,
         calibrated_forecast_variance) = ac.apply_params_entry()

        # TODO: track down where np.float64 promotion takes place.
        calibrated_forecast_predictor.data = (
            calibrated_forecast_predictor.data.astype(np.float32))
        calibrated_forecast_variance.data = (
            calibrated_forecast_variance.data.astype(np.float32))

        return calibrated_forecast_predictor, calibrated_forecast_variance
