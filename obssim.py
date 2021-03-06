################################################################################
#
# 	File:		obssim.py
#	Author:		Anna Zovaro
#	Email:		anna.zovaro@anu.edu.au
#
#	Description:
#	A module for simulating imaging of objects using a given telescope and detector system.
#
#	Copyright (C) 2016 Anna Zovaro
#
################################################################################
#
#	This file is part of linguinesim.
#
#	linguinesim is free software: you can redistribute it and/or modify
#	it under the terms of the GNU General Public License as published by
#	the Free Software Foundation, either version 3 of the License, or
#	(at your option) any later version.
#
#	linguinesim is distributed in the hope that it will be useful,
#	but WITHOUT ANY WARRANTY; without even the implied warranty of
#	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	GNU General Public License for more details.
#
#	You should have received a copy of the GNU General Public License
#	along with linguinesim.  If not, see <http://www.gnu.org/licenses/>.
#
################################################################################
from __future__ import division, print_function 
import miscutils as mu
import numpy as np
import ipdb
import os
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm 
from matplotlib import rc
from matplotlib.cbook import is_numlike
rc('image', interpolation='none', cmap = 'binary_r')

import scipy.integrate
import scipy.special
import scipy.ndimage.interpolation
from scipy.signal import convolve2d

# Image processing library
import PIL
from PIL import Image
try:
	from PIL.Image import LANCZOS as RESAMPLE_FILTER
except:
	from PIL.Image import BILINEAR as RESAMPLE_FILTER

# linguine modules 
from linguineglobals import *
import etc, etcutils, fftwconvolve, imutils

################################################################################
def add_tt(image, 
	sigma_tt_px=None, 
	tt_idxs=None):

	if not plt.is_numlike(sigma_tt_px) and not plt.is_numlike(tt_idxs):
		print("ERROR: either sigma_tt_px OR tt_idxs must be specified!")
		raise UserWarning
	
	# Adding a randomised tip/tilt to the image
	if plt.is_numlike(sigma_tt_px):
		# If no vector of tip/tilt values is specified, then we use random numbers.
		shift_height = np.random.randn() * sigma_tt_px
		shift_width = np.random.randn() * sigma_tt_px
		tt_idxs = [shift_height, shift_width]
	else:
		# Otherwise we take them from the input vector.
		shift_height = tt_idxs[0]
		shift_width = tt_idxs[1]
	
	image_tt = scipy.ndimage.interpolation.shift(image, (shift_height, shift_width))

	return image_tt, tt_idxs

################################################################################
def strehl(psf, psf_dl):
	""" Calculate the Strehl ratio of an aberrated input PSF given the diffraction-limited PSF. """
	return np.amax(psf) / np.amax(psf_dl)

################################################################################
def field_star(psf, band, mag, optical_system, star_coords_as, final_sz, plate_scale_as_px,
	gain = 1,
	magnitude_system = 'AB',
	plotit = False
	):
	"""
		Returns an image of a star in a field with a specified position offset
		(specified w.r.t. the centre of the image).

		The returned image IS NOT gain-multiplied by default. Be careful!
	"""
	# Scale up to the correct magnitude
	star = psf * etcutils.surface_brightness_to_count_rate(
		mu = mag, 
		A_tel = optical_system.telescope.A_collecting_m2, 
		tau = optical_system.telescope.tau,
		qe = optical_system.detector.qe,
		gain = gain,
		magnitude_system = magnitude_system,
		band = band)

	# Pad the sides appropriately.
	star_coords_px = [int(x/plate_scale_as_px) for x in star_coords_as]
	pad_ud, pad_lr = ( int((x - y) // 2) for x, y in zip(final_sz, psf.shape) )
	star_padded = np.pad(
		array = star, 
		pad_width = (
			(pad_ud + star_coords_px[0], pad_ud - star_coords_px[0]), 
			(pad_lr + star_coords_px[1], pad_lr - star_coords_px[1])
			),
		mode='constant')

	if plotit:
		mu.newfigure(1,2)
		plt.suptitle("Field star image")
		mu.astroimshow(
			im = psf, 
			plate_scale_as_px = plate_scale_as_px, 
			title="PSF", 
			subplot=121)
		mu.astroimshow(
			im = star_padded, 
			plate_scale_as_px = plate_scale_as_px, 
			title='Moved to coordinates ({:.2f}",{:.2f}")'.format(
				star_coords_as[0], 
				star_coords_as[1]), 
			subplot=122)
		mu.show_plot()

	return star_padded

################################################################################
def convolve_psf(image, psf, 
	padFactor=1,
	plotit=False):
	"""
		 Convolve an input PSF with an input image. 
	"""

	# Padding the source image.
	height, width = image.shape
	pad_ud = height // padFactor // 2
	pad_lr = width // padFactor // 2
	
	# If the image dimensions are odd, need to ad an extra row/column of zeros.
	image_padded = np.pad(
		image, 
		((pad_ud,pad_ud + height % 2),
		(pad_lr,pad_lr + width % 2)), 
		mode='constant')
	conv_height = 2 * pad_ud + height + (height % 2)
	conv_width = 2 * pad_lr + width + (width % 2)

	# Convolving the kernel with the image.
	image_conv = np.ndarray((conv_height, conv_width))
	image_conv_cropped = np.ndarray((height, width))

	image_padded = np.pad(image, ((pad_ud,pad_ud + height % 2),(pad_lr,pad_lr + width % 2)), mode='constant')
	
	image_conv = fftwconvolve.fftconvolve(image_padded, psf, mode='same')

	image_conv_cropped = image_conv[pad_ud : height + pad_ud, pad_lr : width + pad_lr]		

	if plotit:
		mu.newfigure(2,2)
		plt.suptitle('Seeing-limiting image')
		plt.subplot(2,2,1)
		plt.imshow(image)
		mu.colorbar()
		plt.title('Input image')
		plt.subplot(2,2,2)
		plt.imshow(psf)
		mu.colorbar()
		plt.title('Kernel')
		plt.subplot(2,2,3)
		plt.imshow(image_conv)
		mu.colorbar()
		plt.title('Convolved image (padded)')
		plt.subplot(2,2,4)
		plt.imshow(image_conv_cropped)
		mu.colorbar()
		plt.title('Convolved image (original size)')
		mu.show_plot()

	return image_conv_cropped

################################################################################
def noise_frames_from_etc(N, height_px, width_px, 
	gain=1,
	band=None,
	t_exp=None,
	etc_input=None):
	""" 
	Generate a series of N noise frames with dimensions (height_px, width_px) based on the output of exposure_time_calc() (in etc.py). 

	A previous ETC output returned by exposure_time_calc() can be supplied, or can be generated if band and t_exp are specified. 

	The output is returned in the form of a dictionary allowing the sky, dark current, cryostat and read noise contributions to be accessed separately. The frame generated by summing each of these components is also generated. 

	Important note: we do NOT create master frames here to aviod confusion. The purpose of this routine is to return individual noise frames that can be added to images. However the master frames must not be created from the same frames that are added to images as this is not realistic. 

	"""
	print ("Generating noise frames...")

	# The output is stored in a dictionary with each entry containing the noise frames.
	noise_frames_dict = {
		'sky' : np.zeros((N, height_px, width_px), dtype=int),	# Note: the sky includes the emission from the telescope.
		'dark' : np.zeros((N, height_px, width_px), dtype=int),
		'cryo' : np.zeros((N, height_px, width_px), dtype=int),
		'RN' : np.zeros((N, height_px, width_px), dtype=int),
		'total' : np.zeros((N, height_px, width_px), dtype=int),
		'gain-multiplied' : np.zeros((N, height_px, width_px), dtype=int),
		'unity gain' : np.zeros((N, height_px, width_px), dtype=int),
		'post-gain' : np.zeros((N, height_px, width_px), dtype=int)
	}

	# Getting noise parameters from the ETC.
	if not etc_input:
		if not optical_system:
			print("ERROR: if no ETC input is specified, then you must pass an instance of an opticalSystem!")
			raise UserWarning
		else:
			# If no ETC input is given then we generate a new one.
			if plt.is_numlike(t_exp) and band:
				etc_output = etc.exposure_time_calc(optical_system = optical_system, band = band, t_exp = t_exp)
			else:
				print("ERROR: if no ETC input is specified, then to calculate the noise levels you must also specify t_exp and the imaging band!")
				raise UserWarning

	else:
		# Otherwise, we just return whatever was entered.
		etc_output = etc_input

	# Adding noise to each image and multiplying by the detector gain where appropriate.
	noise_frames_dict['sky'] = noise_frames(height_px, width_px, etc_output['unity gain']['N_sky'], N_frames = N) * gain
	noise_frames_dict['dark'] = noise_frames(height_px, width_px, etc_output['unity gain']['N_dark'], N_frames = N) * gain
	noise_frames_dict['cryo'] = noise_frames(height_px, width_px, etc_output['unity gain']['N_cryo'], N_frames = N) * gain
	noise_frames_dict['RN'] = noise_frames(height_px, width_px, etc_output['unity gain']['N_RN'], N_frames = N)
	
	noise_frames_dict['total'] = noise_frames_dict['sky'] + noise_frames_dict['cryo'] + noise_frames_dict['RN'] + noise_frames_dict['dark']
	noise_frames_dict['gain-multiplied'] = noise_frames_dict['sky'] + noise_frames_dict['cryo'] + noise_frames_dict['dark']
	noise_frames_dict['unity gain'] = noise_frames_dict['gain-multiplied'] / gain
	noise_frames_dict['post-gain'] = noise_frames_dict['RN']

	return noise_frames_dict, etc_output

################################################################################
def noise_frames(height_px, width_px, lam,
	N_frames = 1):
	""" Generate an array of integers drawn from a Poisson distribution with an expected value lam in each entry. """
	if N_frames == 1:
		return np.random.poisson(lam=lam, 
			size=(height_px, width_px)).astype(int)
	else:
		return np.random.poisson(lam=lam, 
			size=(N_frames, height_px, width_px)).astype(int)

################################################################################
def dark_sky_master_frames(N, height_px, width_px,
	band=None,
	t_exp=None,
	etc_input=None):
	""" 
		Generate dark and sky master frames to be used to subtract the dark and/or sky background level in an image. 

		The individual noise frames used to generate the master frames are NOT returned here; this is deliberate as it prevents one from generating the master frames from the same frames that are added to the image.

	"""
	noise_frames_dict = noise_frames_from_etc(
		N=N, 
		height_px=height_px, 
		width_px=width_px, 
		band=band, 
		t_exp=t_exp, 
		etc_input=etc_input)[0]

	# Generating the master dark and sky frames.
	master_dark = median_combine(noise_frames_dict['total'] - noise_frames_dict['sky'])
	master_dark_and_sky = median_combine(noise_frames_dict['total'])

	return master_dark_and_sky, master_dark

################################################################################
def median_combine(images):
	""" Median-combine the input images. """
	# TODO: implement robust median (sigma clipping?)
	return np.median(images, axis=0)

################################################################################
def airy_disc(wavelength_m, f_ratio, l_px_m, 
	detector_size_px=None,
	trapz_oversampling=8,	# Oversampling used in the trapezoidal rule approximation.
	coords=None,
	P_0=1,
	plotit=False):
	"""
		Returns the PSF of an optical system with a circular aperture given the f ratio, pixel and detector size at a given wavelength_m.

		If desired, an offset (measured from the top left corner of the detector) can be specified in vector coords = (x, y).

		The PSF is normalised such that the sum of every pixel in the PSF (extended to infinity) is equal to P_0 (unity by default), where P_0 is the total energy incident upon the telescope aperture. 

		P_0 represents the *ideal* total energy in the airy disc (that is, the total energy incident upon the telescope aperture), whilst P_sum measures the actual total energy in the image (i.e. the pixel values). 
	"""

	# Output image size 
	detector_height_px, detector_width_px = detector_size_px[0:2]

	# Intensity map grid size
	# Oversampled image size
	oversampled_height_px = detector_height_px * trapz_oversampling
	oversampled_width_px = detector_width_px * trapz_oversampling
	# Coordinates of the centre of the Airy disc in the intensity map grid
	if coords == None:
		x_offset = oversampled_height_px/2
		y_offset = oversampled_width_px/2
	else:
		x_offset = coords[0] * trapz_oversampling
		y_offset = coords[1] * trapz_oversampling
	dx = oversampled_height_px/2 - x_offset
	dy = oversampled_width_px/2 - y_offset
	# Intensity map grid indices (in metres)
	x = np.arange(-oversampled_height_px//2, +oversampled_height_px//2 + oversampled_height_px%2 + 1, 1) + dx
	y = np.arange(-oversampled_width_px//2, +oversampled_width_px//2 + oversampled_width_px%2 + 1, 1) + dy
	x *= l_px_m / trapz_oversampling
	y *= l_px_m / trapz_oversampling
	Y, X = np.meshgrid(y, x)

	# Central intensity (W m^-2)
	I_0 = P_0 * np.pi / 4 / wavelength_m / wavelength_m / f_ratio / f_ratio

	# Calculating the Airy disc
	r = lambda x, y: np.pi / wavelength_m / f_ratio * np.sqrt(np.power(x,2) + np.power(y,2))
	I_fun = lambda x, y : np.power((2 * scipy.special.jv(1, r(x,y)) / r(x,y)), 2) * I_0 
	I = I_fun(X,Y)
	# I = np.swapaxes(I,0,1)
	nan_idx = np.where(np.isnan(I))
	if nan_idx[0].shape != (0,):
		I[nan_idx[0][0],nan_idx[1][0]] = I_0 # removing the NaN in the centre of the image if necessary

	""" Converting intensity values to count values in each pixel """
	# Approximation using top-hat intensity profile in each pixel
	count_approx = I * l_px_m**2 / trapz_oversampling**2
	count_approx = count_approx.astype(np.float64)

	# Approximation using trapezoidal rule
	count_cumtrapz = np.zeros((detector_height_px,detector_width_px))
	cumsum = 0
	for j in range(detector_width_px):
		for k in range(detector_height_px):
			px_grid = I[trapz_oversampling*k:trapz_oversampling*k+trapz_oversampling+1,trapz_oversampling*j:trapz_oversampling*j+trapz_oversampling+1]
			res1 = scipy.integrate.cumtrapz(px_grid, dx = l_px_m/trapz_oversampling, axis = 0, initial = 0)
			res2 = scipy.integrate.cumtrapz(res1[-1,:], dx = l_px_m/trapz_oversampling, initial = 0)
			count_cumtrapz[k,j] = res2[-1]
	# Total energy in image
	P_sum = sum(count_cumtrapz.flatten())
	count_cumtrapz /= P_sum

	if plotit:
		mu.newfigure(1,2)
		plt.subplot(1,2,1)
		plt.imshow(I, norm=LogNorm())
		mu.colorbar()
		plt.title('Intensity (oversampled by a factor of %d)' % trapz_oversampling)
		plt.subplot(1,2,2)
		plt.imshow(count_cumtrapz, norm=LogNorm())
		mu.colorbar()
		plt.title('Count (via trapezoidal rule)')
		mu.show_plot()

	return count_cumtrapz, I, P_0, P_sum, I_0

################################################################################
def psf_airy_disk_kernel(wavelength_m, 
	l_px_m=None, 
	f_ratio=None,
	N_OS=None, 
	T_OS=8,
	detector_size_px=None,
	trunc_sigma=10.25,	# 10.25 corresponds to the 10th Airy ring		
	plotit=False):
	"""
		Returns an Airy disc PSF corresponding to an optical system with a given f ratio, pixel size and detector size at a specified wavelength_m.

		If the detector size is not specified, then the PSF is truncated at a radius of 8 * sigma, where sigma corresponds to the HWHM (to speed up convolutions made using this kernel)

		There are 3 ways to constrain the plate scale of the output PSF. One of either the f ratio, the pixel width or the Nyquist sampling factor (where a larger number ==> finer sampling) must be left unspecified, and will be constrained by the other two parameters.
	"""	

	# Now, we have to calculate what the EFFECTIVE f ratio needs to be to achieve the desired Nyquist oversampling in the returned PSF.
	if not f_ratio:
		f_ratio = 2 * N_OS / wavelength_m * np.deg2rad(206265 / 3600) * l_px_m
	elif not N_OS:
		N_OS = wavelength_m * f_ratio / 2 / np.deg2rad(206265 / 3600) / l_px_m
		ipdb.set_trace()	
	elif not l_px_m:
		l_px_m = wavelength_m * f_ratio / 2 / np.deg2rad(206265 / 3600) / N_OS	

	if not detector_size_px:
		psf_size = int(np.round(trunc_sigma * N_OS * 4))
		detector_size_px = (psf_size,psf_size)	

	# In the inputs to this function, do we need to specify the oversampling factor AND the f ratio and/or pixel widths?
	kernel = airy_disc(wavelength_m=wavelength_m, f_ratio=f_ratio, l_px_m=l_px_m, detector_size_px=detector_size_px, trapz_oversampling=T_OS, plotit=plotit)[0]	

	return kernel

###################################################################################
def get_diffraction_limited_image(image_truth, l_px_m, f_ratio, wavelength_m, 
	f_ratio_in=None, wavelength_in_m=None, # f-ratio and imaging wavelength of the input image (if it has N_os > 1)
	N_OS_psf=4,
	detector_size_px=None,
	plotit=False):
	""" Convolve the PSF of a given telescope at a given wavelength with image_truth to simulate diffraction-limited imaging. 
	It is assumed that the truth image has the appropriate plate scale of, but may be larger than, the detector. 
	If the detector size is not given, then it is assumed that the input image and detector have the same dimensions. 

	The flow should really be like this:
		1. Generate the PSF with N_OS = 4, say.
		2. Rescale the image to achieve the same plate scale.
		3. Convolve.
		4. Resample back down to the original plate scale.

	"""
	print("Diffraction-limiting truth image(s)...")
	image_truth, N, height, width = imutils.get_image_size(image_truth)

	# If the input image is already sampled by N_os > 1, then the PSF that we convolve with the image needs to add in quadrature with the PSF that has already been convolved with the image to get to the scaling we want.
	if f_ratio_in != None and wavelength_in_m != None:
		# Then we need to add the PSFs in quadrature.
		f_ratio_out = f_ratio
		wavelength_out_m = wavelength_m

		efl = 1
		D_in = efl / f_ratio_in
		D_out = efl / f_ratio_out
		FWHM_in = wavelength_in_m / D_in
		FWHM_out = wavelength_out_m / D_out
		FWHM_prime = np.sqrt(FWHM_out**2 - FWHM_in**2)

		wavelength_prime_m = wavelength_in_m
		D_prime = wavelength_prime_m / FWHM_prime
		f_ratio_prime = efl / D_prime

		f_ratio = f_ratio_prime
		wavelength_m = wavelength_prime_m

	# Because we specify the PSF in terms of Nyquist sampling, we need to express N_OS in terms of the f ratio and wavelength of the input image.
	N_OS_input = wavelength_m * f_ratio / 2 / l_px_m / (np.deg2rad(206265 / 3600))

	# Calculating the PSF
	psf = psf_airy_disk_kernel(wavelength_m=wavelength_m, N_OS=N_OS_psf, l_px_m=l_px_m)
	# TODO need to check that the PSF is not larger than image_truth_large

	# Convolving the PSF and the truth image to obtain the simulated diffraction-limited image
	# image_difflim = np.ndarray((N, height, width))
	for k in range(N):
		# Resample the image up to the appropriate plate scale.
		image_truth_large = resizeImagesToDetector(image_truth[k], 1/N_OS_input, 1/N_OS_psf)
		# Convolve with the PSF.
		image_difflim_large = fftwconvolve.fftconvolve(image_truth_large, psf, mode='same')
		# Resize the image to its original plate scale.
		if k == 0:
			im = resizeImagesToDetector(image_difflim_large, 1/N_OS_psf, 1/N_OS_input)
			image_difflim = np.ndarray((N, im.shape[0], im.shape[1]))
			image_difflim[0] = im
		else:
			image_difflim[k] = resizeImagesToDetector(image_difflim_large, 1/N_OS_psf, 1/N_OS_input)


	if plotit:
		mu.newfigure(1,3)
		plt.subplot(1,3,1)
		plt.imshow(psf)
		mu.colorbar()
		plt.title('Diffraction-limited PSF of telescope')
		plt.subplot(1,3,2)
		plt.imshow(image_truth[0])
		mu.colorbar()
		plt.title('Truth image')
		plt.subplot(1,3,3)
		plt.imshow(image_difflim[0])
		mu.colorbar()
		plt.title('Diffraction-limited image')
		plt.suptitle('Diffraction-limiting image')
		mu.show_plot()

	return np.squeeze(image_difflim)

################################################################################
def get_seeing_limited_image(images, seeing_diameter_as, 
	plate_scale_as=1,
	padFactor=1,
	plotit=False):
	"""
		 Convolve a Gaussian PSF with an input image to simulate seeing with a FWHM of seeing_diameter_as. 
	"""
	print("Seeing-limiting image(s)",end="")

	images, N, height, width = get_image_size(images)

	# Padding the source image.
	pad_ud = height // padFactor // 2
	pad_lr = width // padFactor // 2
	
	# If the image dimensions are odd, need to ad an extra row/column of zeros.
	image_padded = np.pad(images[0], ((pad_ud,pad_ud + height % 2),(pad_lr,pad_lr + width % 2)), mode='constant')
	# conv_height = image_padded.shape[0]
	# conv_width = image_padded.shape[1]
	conv_height = 2 * pad_ud + height + (height % 2)
	conv_width = 2 * pad_lr + width + (width % 2)

	# Generate a Gaussian kernel.
	kernel = np.zeros((conv_height, conv_width))
	y_as = np.arange(-conv_width//2, +conv_width//2 + conv_width%2, 1) * plate_scale_as
	x_as = np.arange(-conv_height//2, +conv_height//2 + conv_height%2, 1) * plate_scale_as
	X, Y = np.meshgrid(x_as, y_as)
	sigma = seeing_diameter_as / (2 * np.sqrt(2 * np.log(2)))
	kernel = np.exp(-(np.power(X, 2) + np.power(Y, 2)) / (2 * np.power(sigma,2)))
	kernel /= sum(kernel.flatten())
	kernel = np.pad(kernel, ((pad_ud, pad_ud + height % 2), (pad_lr, pad_lr + width % 2)), mode='constant')

	# Convolving the kernel with the image.
	image_seeing_limited = np.ndarray((N, conv_height, conv_width))
	image_seeing_limited_cropped = np.ndarray((N, height, width))

	for k in range(N):
		print('.',end="")
		image_padded = np.pad(images[k], ((pad_ud,pad_ud + height % 2),(pad_lr,pad_lr + width % 2)), mode='constant')
		image_seeing_limited[k] = fftwconvolve.fftconvolve(image_padded, kernel, mode='same')
		image_seeing_limited_cropped[k] = image_seeing_limited[k,pad_ud : height + pad_ud, pad_lr : width + pad_lr]		

	if plotit:
		mu.newfigure(2,2)
		plt.suptitle('Seeing-limiting image')
		plt.subplot(2,2,1)
		plt.imshow(images[0])
		mu.colorbar()
		plt.title('Input image')
		plt.subplot(2,2,2)
		plt.imshow(kernel, extent=axes_kernel)
		mu.colorbar()
		plt.title('Kernel')
		plt.subplot(2,2,3)
		plt.imshow(image_seeing_limited[0])
		mu.colorbar()
		plt.title('Convolved image')
		plt.subplot(2,2,4)
		plt.imshow(image_seeing_limited_cropped[0])
		mu.colorbar()
		plt.title('Cropped, convolved image')
		mu.show_plot()

	return np.squeeze(image_seeing_limited_cropped)

