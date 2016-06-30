############################################################################################
#
# 	File:		etc.py
#	Author:		Anna Zovaro
#	Email:		anna.zovaro@anu.edu.au
#
#	Description:
#	An exposure time calculator (ETC) for a telescope-detector system in the near-infrared.
#	The detector is assumed to be housed in a cryostat. 
#	
#	The returned SNR is per pixel (for now).
#	
#	The user specifies the exposure time, the surface brightness (in Vega or AB magnitudes)
#	and the imaging band (J, H or K).
#
#	TO DO:
#	- double check: do we need Tr_win for the telescope thermal emission calcs?
#
###########################################################################################
from apdsim import *

#########################################################################################################
def exposureTimeCalc(
		band,
		t_exp = 1,
		surfaceBrightness = 19,
		magnitudeSystem = 'AB',
		worstCaseSpider = False
	):

	wavelength_eff = telescope.filter_bands_m[band][0]
	bandwidth = telescope.filter_bands_m[band][1]
	wavelength_min = telescope.filter_bands_m[band][2]
	wavelength_max = telescope.filter_bands_m[band][3]

	E_photon = constants.h * constants.c / wavelength_eff
	# Vega band magnitudes calculated using data from https://www.astro.umd.edu/~ssm/ASTR620/mags.html
	# Note: the bandwidths used to calculate these numbers DO NOT correspond to those in our system but are
	# slightly different. Hence there is some inaccuracy involved in using Vega magnitudes as the input.
	Vega_magnitudes = {
		'J' : 49.46953099,
		'H' : 49.95637318,
		'K' : 50.47441871
	}

	""" Telescope-detector system properties """
	# Calculate the plate scale.
	plate_scale_as = telescope.plate_scale_as_m * detector.l_px_m
	plate_scale_rad = plate_scale_as / 3600 * np.pi / 180
	Omega_px_rad = plate_scale_rad * plate_scale_rad
	T_sky = 273

	#########################################################################################################
	# Noise terms in the SNR calculation
	#########################################################################################################
	
	""" Signal photon flux """
	# Given the surface brightness and angular extent of the image, calculate the source electrons/s/pixel.
	Sigma_source_e = getPhotonFlux(surfaceBrightness = surfaceBrightness, 
		wavelength_eff = wavelength_eff, 
		bandwidth = bandwidth, 
		plate_scale_as = plate_scale_as, 
		A_tel = telescope.A_collecting, 
		tau = telescope.tau * cryo.Tr_win,
		qe = detector.qe,
		gain_av = detector.gain_av,
		magnitudeSystem = 'AB'
	)

	""" Cryostat photon flux """
	Sigma_cryo = getCryostatTE(plotIt=False)

	""" Telescope thermal background photon flux """
	Sigma_tel = getTelescopeTE(plotIt=False, worstCaseSpider=worstCaseSpider)[band]

	""" Sky thermal background photon flux """
	Sigma_sky_thermal = getSkyTE(plotIt=False)[band]

	""" Empirical sky background flux """
	Sigma_sky_emp = getPhotonFlux(surfaceBrightness = telescope.sky_brightness[band], 
		wavelength_eff = wavelength_eff, 
		bandwidth = bandwidth, 
		plate_scale_as = plate_scale_as, 
		A_tel = telescope.A_collecting, 
		tau = telescope.tau * cryo.Tr_win,
		qe = detector.qe,
		gain_av = detector.gain_av,
		magnitudeSystem = 'AB'
	)

	""" Total sky background """
	if band == 'K':
		# In the K band, thermal emission from the sky is dominated by the telescope and sky thermal emission
		Sigma_sky = Sigma_sky_thermal + Sigma_tel
	else:
		# In the J and H bands, OH emission dominates; hence empirical sky brightness values are used instead.
		Sigma_sky = Sigma_sky_emp

	""" Dark current """
	Sigma_dark = detector.dark_current

	#########################################################################################################
	# Calculating the SNR
	#########################################################################################################
	N_source = Sigma_source_e * t_exp
	N_dark = Sigma_dark * t_exp
	N_cryo = Sigma_cryo * t_exp
	N_sky = Sigma_sky * t_exp
	N_tel = Sigma_tel * t_exp
	N_sky_emp = Sigma_sky_emp * t_exp
	N_sky_thermal = Sigma_sky_thermal * t_exp
	N_RN = detector.read_noise * detector.read_noise

	SNR = N_source / np.sqrt(N_source + N_dark + N_cryo + N_sky + N_RN)

	#########################################################################################################

	etc_output = {
		# Input parameters
		't_exp' : t_exp,
		'band' : band,
		'surfaceBrightness' : surfaceBrightness,
		'magnitudeSystem' : magnitudeSystem,
		# Noise standard deviations
		# Poisson distribution, so the nosie scales as the square root of the total number of photons
		'sigma_source' : np.sqrt(N_source),
		'sigma_dark' : np.sqrt(N_dark),
		'sigma_cryo' : np.sqrt(N_cryo),
		'sigma_sky' : np.sqrt(N_sky),
		'sigma_sky_emp' : np.sqrt(N_sky_emp),
		'sigma_tel' : np.sqrt(N_tel),
		'sigma_sky_thermal' : np.sqrt(N_sky_thermal),
		'sigma_RN' : detector.read_noise,
		# Total electron counts
		'N_source' : N_source,
		'N_dark' : N_dark,
		'N_cryo' : N_cryo,
		'N_sky_emp' : N_sky_emp,
		'N_sky_thermal' : N_sky_thermal,
		'N_sky' : N_sky,
		'N_tel' : N_tel,
		'N_RN' : N_RN,
		# SNR
		'SNR' : SNR
	}

	return etc_output

#########################################################################################################
def getPhotonFlux(surfaceBrightness, wavelength_eff, bandwidth, plate_scale_as, A_tel, 
	tau = 1.,
	qe = 1.,
	gain_av = 1.,
	magnitudeSystem = 'AB',
	):
	" Return the electron count per pixel per second from a source with a given surface brightness imaged through a system with collecting area A_tel, throughput tau, quantum efficiency qe, avalanche gain gain_av and plate scale plate_scale_as"

	E_photon = constants.h * constants.c / wavelength_eff
	# Vega band magnitudes calculated using data from https://www.astro.umd.edu/~ssm/ASTR620/mags.html
	Vega_magnitudes = {
		'J' : 49.46953099,
		'H' : 49.95637318,
		'K' : 50.47441871
	}

	" Signal photon flux "
	# Given the surface brightness, calculate the source electrons/s/pixel.
	m = surfaceBrightness	
	if magnitudeSystem == 'AB':
		F_nu_cgs = np.power(10, - (48.6 + m) / 2.5) 						# ergs/s/cm^2/arcsec^2/Hz		
	elif magnitudeSystem == 'Vega':
		F_nu_cgs = np.power(10, - (Vega_magnitudes[band] + m) / 2.5) 		# ergs/s/cm^2/arcsec^2/Hz
	else:
		print('Magnitude must be specified either in AB or Vega magnitudes!')

	F_lambda_cgs = F_nu_cgs * constants.c / np.power(wavelength_eff, 2)	# ergs/s/cm^2/arcsec^2/m
	F_lambda = F_lambda_cgs * 1e-7 * 1e4								# J/s/m^2/arcsec^2/m
	F_total_phot = F_lambda * bandwidth	/ E_photon						# photons/s/m^2/arcsec^2
	Sigma_source_phot = F_total_phot * np.power(plate_scale_as,2) * A_tel	# photons/s/px
	Sigma_source_e = Sigma_source_phot * tau * qe * gain_av 			# electrons/s/px

	return Sigma_source_e

#########################################################################################################
def getCryostatTE(plotIt=True):
	T_cryo = np.linspace(80, 200, 1000)
	I_cryo = np.zeros(len(T_cryo))
	I_cryo_h = np.zeros(len(T_cryo))

	# For finding the crossover point
	minVal = np.inf	
	minVal_min = np.inf

	for k in range(T_cryo.size):
		I_cryo[k] = thermalEmissionIntensity(
			T = T_cryo[k],
			A = detector.A_px_m2,
			wavelength_min = 0.0,
			wavelength_max = detector.wavelength_cutoff,
			Omega = cryo.Omega,
			eps = cryo.eps_wall,
			eta = detector.gain_av * detector.qe
			)
		I_cryo_h[k] = thermalEmissionIntensity(
			T = T_cryo[k],
			A = detector.A_px_m2,
			wavelength_min = 0.0,
			wavelength_max = detector.wavelength_cutoff_h,
			Omega = cryo.Omega,
			eps = cryo.eps_wall,
			eta = detector.gain_av * detector.qe
			)
		# Find the crossing point
		if abs(I_cryo[k] - detector.dark_current) < minVal:
			minVal = abs(I_cryo[k] - detector.dark_current)
			idx = k
		# Absolute worst-case
		if abs(I_cryo_h[k] - detector.dark_current*0.1) < minVal_min:
			minVal_min = abs(I_cryo_h[k] - detector.dark_current*0.1)
			idx_min = k

	if plotIt:
		D = np.ones(len(T_cryo))*detector.dark_current
		wavelengths = np.linspace(0.80, 2.5, 1000)*1e-6

		# Plotting
		plt.figure(figsize=(figsize*1.25,figsize))
		plt.rc('text', usetex=True)
		plt.plot(T_cryo, I_cryo, 'r', label='Cryostat thermal emission, $\lambda_c = %.1f \mu$m' % (detector.wavelength_cutoff*1e6))
		plt.plot(T_cryo, I_cryo_h, 'r--', label='Cryostat thermal emission, $\lambda_c = %.1f \mu$m' % (detector.wavelength_cutoff_h*1e6))
		plt.plot(T_cryo, D, 'g', label=r'Dark current')
		plt.plot(T_cryo, D*0.1, 'g--', label=r'Dark current (10\%)')
		plt.plot([T_cryo[idx],T_cryo[idx]], [0, np.max(I_cryo_h)], 'k', label='$T_c = %.3f$ K' % (T_cryo[idx]))
		plt.plot([T_cryo[idx_min],T_cryo[idx_min]], [0, np.max(I_cryo_h)], 'k--', label='$T_c = %.3f$ K (worst-case)' % T_cryo[idx_min])
		plt.yscale('log')
		plt.axis('tight')
		plt.legend(loc='lower right')
		plt.xlabel(r'Temperature (K)')
		plt.ylabel(r'Count ($e^{-}$ s$^{-1}$ pixel$^{-1}$)')
		plt.title('Estimated count from cryostat thermal emission')
	
	return I_cryo[idx]

#########################################################################################################

def getSkyTE(T_sky=273, plotIt=True):
	" Sky thermal background photon flux in the J, H and K bands "
	I_sky = {
		'J' : 0.0,
		'H' : 0.0,
		'K' : 0.0
	}
	
	plate_scale_as_px = telescope.plate_scale_as_m * detector.l_px_m
	plate_scale_rad_px = plate_scale_as_px / 3600 * np.pi / 180
	Omega_px_rad = plate_scale_rad_px * plate_scale_rad_px

	# Atmospheric properties	
	fname = 'cptrans_zm_23_10.dat'
	this_dir, this_filename = os.path.split(__file__)
	DATA_PATH = os.path.join(this_dir, 'skytransdata', fname)
	# f = open(fname,'r')
	f = open(DATA_PATH, 'r')

	wavelengths_sky = [];
	Tr_sky = [];
	for line in f:
		cols = line.split()
		wavelengths_sky.append(float(cols[0]))
		Tr_sky.append(float(cols[1]))
	Tr_sky = np.asarray(Tr_sky)
	wavelengths_sky = np.asarray(wavelengths_sky) * 1e-6
	eps_sky = lambda wavelength: np.interp(wavelength, wavelengths_sky, 1 - Tr_sky)
	f.close()

	for key in I_sky:
		wavelength_min = telescope.filter_bands_m[key][2]
		wavelength_max = telescope.filter_bands_m[key][3]
		I_sky[key] = thermalEmissionIntensity(
			T = T_sky, 
			wavelength_min = wavelength_min, 
			wavelength_max = wavelength_max, 
			Omega = Omega_px_rad, 
			A = telescope.A_collecting, 
			eps = eps_sky
			)
		# Multiply by the gain, QE and telescope transmission to get units of electrons/s/px.
		I_sky[key] = detector.gain_av * detector.qe * telescope.tau * cryo.Tr_win * I_sky[key]

	if plotIt:
		D = np.ones(1000)*detector.dark_current
		wavelengths = np.linspace(0.80, 2.5, 1000)*1e-6

		# Plotting
		plt.figure(figsize=(figsize,figsize))
		plt.plot(wavelengths*1e6, D, 'g--', label=r'Dark current')
		# Imager mode
		for key in I_sky:
			plt.errorbar(telescope.filter_bands_m[key][0]*1e6, I_sky[key], 0, telescope.filter_bands_m[key][1]/2*1e6, fmt='o')
			plt.text(telescope.filter_bands_m[key][0]*1e6, I_sky[key]*5, key)

		plt.yscale('log')
		plt.axis('tight')
		plt.ylim(ymax=100*I_sky['K'],ymin=1e-5)
		plt.legend(loc='lower right')
		plt.xlabel(r'$\lambda$ ($\mu$m)')
		plt.ylabel(r'Count ($e^{-}$ s$^{-1}$ pixel$^{-1}$)')
		plt.title(r'Estimated count from sky thermal emission')
		plt.show()

	return I_sky

#########################################################################################################

def getTelescopeTE(T_sky=273, plotIt=True, worstCaseSpider=False):
	I_tel = {
		'J' : 0.0,
		'H' : 0.0,
		'K' : 0.0
	}
	
	# plate_scale_as_px = telescope.plate_scale_as_mm * detector.l_px
	plate_scale_as_px = telescope.plate_scale_as_m * detector.l_px_m
	plate_scale_rad_px = plate_scale_as_px / 3600 * np.pi / 180
	Omega_px_rad = plate_scale_rad_px * plate_scale_rad_px

	for key in I_tel:
		wavelength_min = telescope.filter_bands_m[key][2]
		wavelength_max = telescope.filter_bands_m[key][3]
		
		I_M1 = thermalEmissionIntensity(T = telescope.T, wavelength_min = wavelength_min, wavelength_max = wavelength_max, Omega = Omega_px_rad, A = telescope.A_M1_total, eps = telescope.eps_M1_eff)
		I_M2 = thermalEmissionIntensity(T = telescope.T, wavelength_min = wavelength_min, wavelength_max = wavelength_max, Omega = Omega_px_rad, A = telescope.A_M2_total_eff, eps = telescope.eps_M2_eff)
		I_M3 = thermalEmissionIntensity(T = telescope.T, wavelength_min = wavelength_min, wavelength_max = wavelength_max, Omega = Omega_px_rad, A = telescope.A_M1_total, eps = telescope.eps_M1_eff)
		
		# Spider (acting as a grey body at both the sky temperature and telescope temperature)
		if worstCaseSpider == False:
			# BEST CASE: assume the spider has a fresh aluminium coating - so 9.1% emissive at sky temp and 90.1% emissive at telescope temp
			I_spider = \
				thermalEmissionIntensity(T = telescope.T, 	wavelength_min = wavelength_min, wavelength_max = wavelength_max, Omega = Omega_px_rad, A = telescope.A_M1_total, eps = telescope.eps_spider_eff)\
			  + thermalEmissionIntensity(T = T_sky, 		wavelength_min = wavelength_min, wavelength_max = wavelength_max, Omega = Omega_px_rad, A = telescope.A_M1_total, eps = 1 - telescope.eps_spider_eff)
		else:
			# WORST CASE: assume the spider is 100% emissive at telescope temperature (i.e. not reflective at all)
			I_spider = \
				thermalEmissionIntensity(T = telescope.T, 	wavelength_min = wavelength_min, wavelength_max = wavelength_max, Omega = Omega_px_rad, A = telescope.A_M1_total, eps = 1.0)\
		
		# Cryostat window (acting as a grey body)
		I_window = thermalEmissionIntensity(T = cryo.T, wavelength_min = wavelength_min, wavelength_max = wavelength_max, Omega = Omega_px_rad, A = telescope.A_M1_total, eps = cryo.eps_win)

		# Multiply by the gain and QE to get units of electrons/s/px.
		# We don't multiply by the transmission because the mirrors themselves are emitting.
		I_tel[key] = detector.gain_av * detector.qe * cryo.Tr_win * (I_M1 + I_M2 + I_M3 + I_spider) + detector.gain_av * detector.qe * I_window

	if plotIt:
		D = np.ones(1000)*detector.dark_current
		wavelengths = np.linspace(0.80, 2.5, 1000)*1e-6

		# Plotting
		plt.figure(figsize=(figsize,figsize))
		plt.plot(wavelengths*1e6, D, 'g--', label=r'Dark current')

		for key in telescope.filter_bands_m:
			plt.errorbar(telescope.filter_bands_m[key][0]*1e6, I_tel[key], 0, telescope.filter_bands_m[key][1]/2*1e6, fmt='o')
			plt.text(telescope.filter_bands_m[key][0]*1e6, I_tel[key]*5, key)

		plt.yscale('log')
		plt.axis('tight')
		plt.ylim(ymax=100*I_tel['K'],ymin=1e-5)
		plt.legend(loc='lower right')
		plt.xlabel(r'$\lambda$ ($\mu$m)')
		plt.ylabel(r'Count ($e^{-}$ s$^{-1}$ pixel$^{-1}$)')
		plt.title(r'Estimated count from telescope thermal emission')
		plt.show()

	return I_tel

########################################################################################
def plotBackgroundNoiseSources():
	" Plot the empirical sky brightness, thermal sky emission, thermal telescope emission and dark current as a function of wavelength "
	counts = {
		'H' : 0,
		'J' : 0,
		'K' : 0
	}
	counts['H'] = exposureTimeCalc(band='H', t_exp=1)
	counts['J'] = exposureTimeCalc(band='J', t_exp=1)
	counts['K'] = exposureTimeCalc(band='K', t_exp=1)
	N_tel_worstcase = getTelescopeTE(worstCaseSpider=True, plotIt=False)
	D = np.ones(1000)*detector.dark_current
	wavelengths = np.linspace(1.0, 2.5, 1000)*1e-6

	# Plotting
	plt.figure(figsize=(figsize,figsize))
	plt.plot(wavelengths*1e6, D, 'g--', label=r'Dark current')
	plotColors = {
		'H' : 'orangered',
		'J' : 'darkorange',
		'K' : 'darkred'
	}
	for key in counts:
		if key == 'J':
			plt.errorbar(telescope.filter_bands_m[key][0]*1e6, counts[key]['N_sky_emp'], 0, telescope.filter_bands_m[key][1]/2*1e6, fmt='o', ecolor=plotColors[key], mfc=plotColors[key], label='Empirical sky background')
			plt.errorbar(telescope.filter_bands_m[key][0]*1e6, counts[key]['N_sky_thermal'], 0, telescope.filter_bands_m[key][1]/2*1e6, fmt='^', ecolor=plotColors[key], mfc=plotColors[key], label='Thermal sky background')
			plt.errorbar(telescope.filter_bands_m[key][0]*1e6, counts[key]['N_tel'], 0, telescope.filter_bands_m[key][1]/2*1e6, fmt='*', ecolor=plotColors[key], mfc=plotColors[key], label='Thermal telescope background')
			# eb=plt.errorbar(telescope.filter_bands_m[key][0]*1e6, N_tel_worstcase[key], 0, telescope.filter_bands_m[key][1]/2*1e6, fmt='*', ecolor=plotColors[key], mfc=plotColors[key], label='Thermal telescope background (worst-case)')
			# eb[-1][0].set_linestyle('--')
		else:
			plt.errorbar(telescope.filter_bands_m[key][0]*1e6, counts[key]['N_sky_emp'], 0, telescope.filter_bands_m[key][1]/2*1e6, fmt='o', ecolor=plotColors[key], mfc=plotColors[key])
			plt.errorbar(telescope.filter_bands_m[key][0]*1e6, counts[key]['N_sky_thermal'], 0, telescope.filter_bands_m[key][1]/2*1e6, fmt='^', ecolor=plotColors[key], mfc=plotColors[key])
			plt.errorbar(telescope.filter_bands_m[key][0]*1e6, counts[key]['N_tel'], 0, telescope.filter_bands_m[key][1]/2*1e6, fmt='*', ecolor=plotColors[key], mfc=plotColors[key])
			# eb=plt.errorbar(telescope.filter_bands_m[key][0]*1e6, N_tel_worstcase[key], 0, telescope.filter_bands_m[key][1]/2*1e6, fmt='*', ecolor=plotColors[key], mfc=plotColors[key])
			# eb[-1][0].set_linestyle('--')

		plt.text(telescope.filter_bands_m[key][0]*1e6, counts[key]['N_sky_emp']*5, key)

	plt.yscale('log')
	plt.axis('tight')
	plt.ylim(ymax=100*counts['K']['N_tel'],ymin=1e-5)
	plt.legend(loc='lower right')
	plt.xlabel(r'$\lambda$ ($\mu$m)')
	plt.ylabel(r'Count ($e^{-}$ s$^{-1}$ pixel$^{-1}$)')
	plt.title(r'Expected background noise levels')
	plt.show()

########################################################################################
def thermalEmissionIntensity(		
	T,					# Emission source temperature
	wavelength_min,		# Integrand interval lower limit
	wavelength_max,		# Integrand interval upper limit
	Omega,				# Solid angle subtended by source on pupil
	A,					# Collecting area of pupil
	eps = 1.0,			# Emissivity of source
	eta = 1.0			# Efficiency of system
	):

	"""
		Given a blackbody with emissivity eps and temperature T, find the total irradiance over an interval 
		[wavelength_min, wavelength_max] incident upon a pupil/emitter system with etendue A * Omega and 
		efficiency eta. 

		I is in units of photons per second (per area A) if eta does not include the QE.
		I is in units of electrons per second (per area A) if eta does include the QE.
	"""

	# Planck function
	B = lambda wavelength, T: 2 * constants.h * np.power(constants.c,2) / np.power(wavelength,5) * 1 / (np.exp(constants.h * constants.c / (wavelength * constants.Boltzmann * T)) - 1)
	
	# Integrand
	integrand = lambda wavelength, Omega, eta, A, T, eps: Omega * A * eta * B(wavelength, T) * wavelength / (constants.h * constants.c) * eps
	
	# Integrating to find the total irradiance incident upon the pupil
	if hasattr(eps, '__call__'):
		# if the emissivity is a function of wavelength
		integrand_prime = lambda wavelength, Omega, eta, A, T: integrand(wavelength, Omega, eta, A, T, eps(wavelength))
		I = integrate.quad(integrand_prime, wavelength_min, wavelength_max, args=(Omega, eta, A, T))[0]
	else:	
		# if the emissivity is scalar
		I = integrate.quad(integrand, wavelength_min, wavelength_max, args=(Omega, eta, A, T, eps))[0]

	return I