import numpy as np
from matplotlib.colors import LogNorm
import pylab as plt
from copy import deepcopy
from atmPy.tools import plt_tools
import pandas as pd
import warnings
import datetime
from atmPy.mie import bhmie

# TODO: Get rid of references to hagmods so we don't need them.


# TODO: Fix distrTypes so they are consistent with our understanding.
distTypes = {'log normal': ['dNdlogDp', 'dSdlogDp', 'dVdlogDp'],
             'natural': ['dNdDp', 'dSdDp', 'dVdDp'],
             'number': ['dNdlogDp', 'dNdDp'],
             'surface': ['dSdlogDp', 'dSdDp'],
             'volume': ['dVdlogDp', 'dVdDp']}


def read_distribution_csv(fname, fixGaps=True):
    headerNo = 50
    rein = open(fname, 'r')
    nol = ['distributionType', 'objectType']
    outDict = {}
    for i in range(headerNo):
        split = rein.readline().split('=')
        variable = split[0].strip()
        if split[0][0] == '#':
            break
        value = split[1].strip()
        if variable in nol:
            outDict[variable] = value
        else:
            outDict[variable] = np.array(eval(value))
        if i == headerNo - 1:
            raise TypeError('Sure this is a size distribution?')

    rein.close()
    data = pd.read_csv(fname, header=i + 1, index_col=0)
    data.index = pd.to_datetime(data.index)
    if outDict['objectType'] == 'SizeDist_TS':
        distRein = SizeDist_TS(data, outDict['bins'], outDict['distributionType'], fixGaps=fixGaps)
    elif outDict['objectType'] == 'SizeDist':
        distRein = SizeDist(data, outDict['bins'], outDict['distributionType'], fixGaps=fixGaps)
    elif outDict['objectType'] == 'SizeDist_LS':
        distRein = SizeDist_LS(data, outDict['bins'], outDict['distributionType'], fixGaps=fixGaps)
    else:
        raise TypeError('not a valid object type')
    return distRein


def get_label(distType):
    if distType == 'dNdDp':
        label = '$\mathrm{d}N\,/\,\mathrm{d}D_{P}$ (nm$^{-1}\,$cm$^{-3}$)'
    elif distType == 'dNdlogDp':
        label = '$\mathrm{d}N\,/\,\mathrm{d}log(D_{P})$ (cm$^{-3}$)'
    elif distType == 'dSdDp':
        label = '$\mathrm{d}S\,/\,\mathrm{d}D_{P}$ (nm$\,$cm$^{-3}$)'
    elif distType == 'dSdlogDp':
        label = '$\mathrm{d}S\,/\,\mathrm{d}log(D_{P})$ (nm$^2\,$cm$^{-3}$)'
    elif distType == 'dVdDp':
        label = '$\mathrm{d}V\,/\,\mathrm{d}D_{P}$ (nm$^2\,$cm$^{-3}$)'
    elif distType == 'dVdlogDp':
        label = '$\mathrm{d}V\,/\,\mathrm{d}log(D_{P})$ (nm$^3\,$cm$^{-3}$)'
    elif distType == 'calibration':
        label = '$\mathrm{d}N\,/\,\mathrm{d}Amp$ (bin$^{-1}\,$cm$^{-3}$)'
    elif distType == 'numberConcentration':
        label = 'Particle number in bin'
    else:
        raise ValueError('%s is not really an option!?!' % distType)
    return label


class SizeDist(object):
    """
    Object defining a log normal aerosol size distribution


    Attributes
    ----------
    bincenters:         NumPy array, optional
                        this is if you actually want to pass the bincenters, if False they will be calculated
    distributionType:
                        log normal: 'dNdlogDp','dSdlogDp','dVdlogDp'
                        natural: 'dNdDp','dSdDp','dVdDp'
                        number: 'dNdlogDp', 'dNdDp'
                        surface: 'dSdlogDp','dSdDp'
                        volume: 'dVdlogDp','dVdDp'
    data:   pandas dataFrame, optional
            None, will generate an empty pandas data frame with columns defined by bins
             - pandas dataFrame with
                 - column names (each name is something like this: '150-200')
                 - index is time (at some point this should be arbitrary, convertable to altitude for example?)
    unit conventions:
             - diameters: nanometers
             - flowrates: cc (otherwise, axis label need to be adjusted an caution needs to be taken when dealing is AOD)



    Notes
    ------
    * Diameters are specified in nanometers

    """

    def __init__(self, data, bins, distrType, bincenters=False, fixGaps=True):

        self.bins = bins
        if type(bincenters) == np.ndarray:
            self.bincenters = bincenters
        else:
            self.bincenters = (bins[1:] + bins[:-1]) / 2.
        self.binwidth = (bins[1:] - bins[:-1])
        self.distributionType = distrType

        if type(data).__name__ == 'NoneType':
            cols = []
            for e, i in enumerate(bins[:-1]):
                cols.append(str(i) + '-' + str(bins[e + 1]))
            self.data = pd.DataFrame(columns=cols)
        else:
            self.data = data

            if fixGaps:
                self.fillGaps()

    def fillGaps(self, scale=1.1):
        """
        Finds gaps in dataset (e.g. when instrument was shut of) and fills them with zeros.

        It adds one line of zeros to the beginning and one to the end of the gap. 
        Therefore the gap is visible as zeros instead of the interpolated values

        Parameters
        ----------
        scale:  float, optional
                This is a scale.
        """
        diff = self.data.index[1:].values - self.data.index[0:-1].values
        threshold = np.median(diff) * scale
        where = np.where(diff > threshold)[0]
        if len(where) != 0:
            warnings.warn('The dataset provided had %s gaps' % len(where))
            gap_start = self.data.index[where]
            gap_end = self.data.index[where + 1]
            for gap_s in gap_start:
                self.data.loc[gap_s + threshold] = np.zeros(self.bincenters.shape)
            for gap_e in gap_end:
                self.data.loc[gap_e - threshold] = np.zeros(self.bincenters.shape)
            self.data = self.data.sort_index()
        return

    def plot(self, showMinorTickLabels=True, removeTickLabels=["700", "900"], ax=None):
        """
        Plots and returns f,a (figure, axis).

        Arguments
        ---------
        showMinorTickLabels: bool [True], optional
            if minor tick labels are labled
        removeTickLabels: list of string ["700", "900"], optional
            list of tick labels aught to be removed (in case there are overlapping)
        ax: axis object [None], optional
            option to provide axis to plot on

        Returns
        -------
        Handles to the figure and axes of the figure.


        """
        if type(ax).__name__ == 'AxesSubplot':
            a = ax
            f = a.get_figure()
        else:
            f, a = plt.subplots()

        a.plot(self.bincenters, self.data.loc[0])
        a.set_xlabel('Particle diameter (nm)')

        label = get_label(self.distributionType)
        a.set_ylabel(label)
        a.set_xscale('log')

        return f, a

    def _normal2log(self):

        trans = (self.bincenters * np.log(10.))
        return trans

    def _2Surface(self):
        trans = 4. * np.pi * (self.bincenters / 2.) ** 2
        return trans

    def _2Volume(self):

        trans = 4. / 3. * np.pi * (self.bincenters / 2.) ** 3
        return trans

    def _convert2otherDistribution(self, distType, verbose=False):

        dist = self.copy()
        if dist.distributionType == distType:
            if verbose:
                warnings.warn(
                    'Distribution type is already %s. Output is an unchanged copy of the distribution' % distType)
            return dist

        if dist.distributionType == 'numberConcentration':
            pass
        elif distType == 'numberConcentration':
            pass
        elif dist.distributionType in distTypes['log normal']:
            if distType in distTypes['log normal']:
                if verbose:
                    print('both log normal')
            else:
                dist.data = dist.data / self._normal2log()

        elif dist.distributionType in distTypes['natural']:
            if distType in distTypes['natural']:
                if verbose:
                    print('both natural')
            else:
                dist.data = dist.data * self._normal2log()
        else:
            raise ValueError('%s is not an option' % distType)

        if dist.distributionType == 'numberConcentration':
            pass

        elif distType == 'numberConcentration':
            pass
        elif dist.distributionType in distTypes['number']:
            if distType in distTypes['number']:
                if verbose:
                    print('both number')
            else:
                if distType in distTypes['surface']:
                    dist.data *= self._2Surface()
                elif distType in distTypes['volume']:
                    dist.data *= self._2Volume()
                else:
                    raise ValueError('%s is not an option' % distType)

        elif dist.distributionType in distTypes['surface']:
            if distType in distTypes['surface']:
                if verbose:
                    print('both surface')
            else:
                if distType in distTypes['number']:
                    dist.data /= self._2Surface()
                elif distType in distTypes['volume']:
                    dist.data *= self._2Volume() / self._2Surface()
                else:
                    raise ValueError('%s is not an option' % distType)

        elif dist.distributionType in distTypes['volume']:
            if distType in distTypes['volume']:
                if verbose:
                    print('both volume')
            else:
                if distType in distTypes['number']:
                    dist.data /= self._2Volume()
                elif distType in distTypes['surface']:
                    dist.data *= self._2Surface() / self._2Volume()
                else:
                    raise ValueError('%s is not an option' % distType)
        else:
            raise ValueError('%s is not an option' % distType)

        if distType == 'numberConcentration':
            dist = dist.convert2dNdDp()
            dist.data *= self.binwidth

        elif dist.distributionType == 'numberConcentration':
            dist.data = dist.data / self.binwidth
            dist.distributionType = 'dNdDp'
            dist = dist._convert2otherDistribution(distType)

        dist.distributionType = distType
        if verbose:
            print('converted from %s to %s' % (self.distributionType, dist.distributionType))
        return dist

    def convert2dNdDp(self):
        return self._convert2otherDistribution('dNdDp')

    def convert2dNdlogDp(self):
        return self._convert2otherDistribution('dNdlogDp')

    def convert2dSdDp(self):
        return self._convert2otherDistribution('dSdDp')

    def convert2dSdlogDp(self):
        return self._convert2otherDistribution('dSdlogDp')

    def convert2dVdDp(self):
        return self._convert2otherDistribution('dVdDp')

    def convert2dVdlogDp(self):
        return self._convert2otherDistribution('dVdlogDp')

    def convert2numberconcentration(self):
        return self._convert2otherDistribution('numberConcentration')

    def copy(self):
        return deepcopy(self)

    def save_csv(self, fname):
        raus = open(fname, 'w')
        raus.write('bins = %s\n' % self.bins.tolist())
        raus.write('distributionType = %s\n' % self.distributionType)
        raus.write('objectType = %s\n' % (type(self).__name__))
        raus.write('#\n')
        raus.close()
        self.data.to_csv(fname, mode='a')
        return


class SizeDist_TS(SizeDist):
    """

    data: pandas dataFrame with
                 - column names (each name is something like this: '150-200')
                 - index is time (at some point this should be arbitrary, convertable to altitude for example?)
       unit conventions:
             - diameters: nanometers
             - flowrates: cc (otherwise, axis label need to be adjusted an caution needs to be taken when dealing is AOD)
       distributionType:  
             log normal: 'dNdlogDp','dSdlogDp','dVdlogDp'
             natural: 'dNdDp','dSdDp','dVdDp'
             number: 'dNdlogDp', 'dNdDp'
             surface: 'dSdlogDp','dSdDp'
             volume: 'dVdlogDp','dVdDp'
       bincenters: this is if you actually want to pass the bincenters, if False they will be calculated

       """

    def _getXYZ(self):
        """
        This will create three arrays, so when plotted with pcolor each pixel will represent the exact bin width
        """
        binArray = np.repeat(np.array([self.bins]), self.data.index.shape[0], axis=0)
        timeArray = np.repeat(np.array([self.data.index.values]), self.bins.shape[0], axis=0).transpose()
        ext = np.array([np.zeros(self.data.index.values.shape)]).transpose()
        Z = np.append(self.data.values, ext, axis=1)
        return timeArray, binArray, Z

    def get_timespan(self):
        return self.data.index.min(), self.data.index.max()

    # TODO: Fix plot options such as showMinorTickLabels
    def plot(self, vmax=None, vmin=None, norm='linear', showMinorTickLabels=True,
             removeTickLabels=["700", "900"], ax=None, cmap=plt_tools.get_colorMap_intensity(), colorbar=True):
        """
        plots and returns f,a,pc,cb (figure, axis, pcolormeshInstance, colorbar)
        Optional parameters:
              norm - ['log','linear']
        """
        X, Y, Z = self._getXYZ()
        if type(ax).__name__ == 'AxesSubplot':
            a = ax
            f = a.get_figure()
        else:
            f, a = plt.subplots()
            f.autofmt_xdate()

        if norm == 'log':
            norm = LogNorm()
        elif norm == 'linear':
            norm = None

        # ToDo: The following screws up log-plotting, Is that stuff neaded anywhere else?
        # if not vmax:
        # vmax = Z.max()
        # if not vmin:
        #     vmin = Z.min()

        pc = a.pcolormesh(X, Y, Z, vmin=vmin, vmax=vmax, norm=norm, cmap=cmap)
        a.set_yscale('log')
        a.set_ylim((self.bins[0], self.bins[-1]))
        a.set_xlabel('Time (UTC)')

        # TODO: Fix the spelling of calibration
        if self.distributionType == 'calibration':
            a.set_ylabel('Amplitude (digitizer bins)')
        else:
            a.set_ylabel('Diameter (nm)')
        if colorbar:
            cb = f.colorbar(pc)
            label = get_label(self.distributionType)
            cb.set_label(label)
        else:
            cb = get_label(self.distributionType)

        if self.distributionType != 'calibration':
            a.yaxis.set_major_formatter(plt.FormatStrFormatter("%i"))

            f.canvas.draw()  # this is important, otherwise the ticks (at least in case of minor ticks) are not created yet
            if showMinorTickLabels:
                a.yaxis.set_minor_formatter(plt.FormatStrFormatter("%i"))
                ticks = a.yaxis.get_minor_ticks()
                for i in ticks:
                    if i.label.get_text() in removeTickLabels:
                        i.label.set_visible(False)
        return f, a, pc, cb

    def zoom_time(self, start=None, end=None):
        """
        2014-11-24 16:02:30
        """
        dist = self.copy()
        dist.data = dist.data.truncate(before=start, after=end)
        return dist


    def average_overTime(self, window='1S'):
        dist = self.copy()
        window = window
        dist.data = dist.data.resample(window, closed='right', label='right')
        if dist.distributionType == 'calibration':
            dist.data.values[np.where(np.isnan(self.data.values))] = 0
        return dist

    def average_overAllTime(self):
        """
        averages over the entire dataFrame and returns a single sizedistribution (numpy.ndarray)
        """
        singleHist = np.zeros(self.data.shape[1])

        for i in range(self.data.shape[1]):
            line = self.data.values[:, i]
            singleHist[i] = np.average(line[~np.isnan(line)])

        data = pd.DataFrame(np.array([singleHist]), columns=self.data.columns)
        avgDist = SizeDist(data, self.bins, self.distributionType)

        return avgDist


class SizeDist_LS(SizeDist):
    """


    data: pandas dataFrame with
                 - column names (each name is something like this: '150-200')
                 - altitude (at some point this should be arbitrary, convertable to altitude for example?)
       unit conventions:
             - diameters: nanometers
             - flowrates: cc (otherwise, axis label need to be adjusted an caution needs to be taken when dealing is AOD) 
       distributionType:  
             log normal: 'dNdlogDp','dSdlogDp','dVdlogDp'
             natural: 'dNdDp','dSdDp','dVdDp'
             number: 'dNdlogDp', 'dNdDp'
             surface: 'dSdlogDp','dSdDp'
             volume: 'dVdlogDp','dVdDp'

    """

    def __init__(self, data, bins, distributionType, layerbounderies, bincenters=False, fixGaps=True):
        super(SizeDist_LS, self).__init__(data, bins, distributionType, bincenters=False, fixGaps=True)
        if type(layerbounderies).__name__ == 'NoneType':
            self.layerbounderies = np.empty((0, 2))
            self.layercenters = np.array([])
        else:
            self.layerbounderies = layerbounderies
            self.layercenters = (layerbounderies[1:] + layerbounderies[:-1]) / 2.

    def calculate_AOD(self, wavelenth=600., n=1.6):
        """
        Calculates the extinction crossection and AOD for each layer.
        plotting the layer and diameter dependent extinction coefficient gives you an idea what dominates the overall AOD.

        Parameters
        ----------
        wavelength: float, optional
                    default is 600 nm
        n:          float, optional
                    Index of refraction; default is 1.6

        Returns
        -------
        Aerosol optical depth over all layers.

        """
        sdls = self.convert2numberconcentration()

        mie = _perform_Miecalculations(np.array(sdls.bincenters / 1000.), wavelenth / 1000., n)

        AOD_layer = np.zeros((len(sdls.layercenters)))
        extCoeffPerLayer = np.zeros((len(sdls.layercenters), len(sdls.bincenters)))
        for i, lc in enumerate(sdls.layercenters):
            laydata = sdls.data.loc[lc].values
            extinction_coefficient = _get_coefficients(mie.extinction_crossection, laydata)
            layerThickness = sdls.layerbounderies[i][1] - sdls.layerbounderies[i][0]
            AOD_perBin = extinction_coefficient * layerThickness
            AOD_layer[i] = AOD_perBin.values.sum()
            extCoeffPerLayer[i] = extinction_coefficient
        out = {}
        out['AOD'] = AOD_layer.sum()
        out['AOD_layer'] = pd.DataFrame(AOD_layer, index=sdls.layercenters, columns=['AOD per Layer'])
        out['extCoeffPerLayer'] = pd.DataFrame(extCoeffPerLayer, index=sdls.layercenters, columns=sdls.data.columns)
        warnings.warn('ACTION required: what to do with gaps in the layers when clauclating the AOD?!?')
        return out


    def add_layer(self, sd, layerboundery):
        """
        Adds a sizedistribution instance to the layerseries.
        layerboundery

        Parameters
        ----------
        sd:
        layerboundary:
        """
        if len(layerboundery) != 2:
            raise ValueError('layerboundery has to be of length 2')

        sd = sd._convert2otherDistribution(self.distributionType)

        layerbounderies = np.append(self.layerbounderies, np.array([layerboundery]), axis=0)

        layerbounderiesU = np.unique(layerbounderies)

        if (np.where(layerbounderiesU == layerboundery[1])[0] - np.where(layerbounderiesU == layerboundery[0])[0])[
            0] != 1:
            raise ValueError('The new layer is overlapping with an existing layer!')
        self.layerbounderies = layerbounderies
        self.layerbounderies.sort(axis=0)
        layercenter = np.array(layerboundery).sum() / 2.
        self.layercenters = np.append(self.layercenters, layercenter)
        self.layercenters.sort()
        sd.data.index = np.array([layercenter])
        self.data = self.data.append(sd.data).sort()
        return

    def _getXYZ(self):
        """
        This will create three arrays, so when plotted with pcolor each pixel will represent the exact bin width
        """
        binArray = np.repeat(np.array([self.bins]), self.data.index.shape[0], axis=0)
        layerArray = np.repeat(np.array([self.data.index.values]), self.bins.shape[0], axis=0).transpose()
        ext = np.array([np.zeros(self.data.index.values.shape)]).transpose()
        Z = np.append(self.data.values, ext, axis=1)
        return layerArray, binArray, Z

    def plot_eachLayer(self, a=None):
        """
        Plots the distribution of each layer in one plot.

        Returns
        -------
        Handles to the figure and axes of the plot
        """
        if not a:
            f, a = plt.subplots()
        else:
            f = None
            pass
        for iv in self.data.index.values:
            a.plot(self.bincenters, self.data.loc[iv, :], label='%i' % iv)
        a.set_xlabel('Particle diameter (nm)')
        a.set_ylabel(get_label(self.distributionType))
        a.legend()
        a.semilogx()
        return f, a


    def plot(self, vmax=None, vmin=None, norm='linear', showMinorTickLabels=True,
             removeTickLabels=["700", "900"],
             plotOnTheseAxes=False):
        """ plots and returns f,a,pc,cb (figure, axis, pcolormeshInstance, colorbar)
        Optional parameters:
              norm - ['log','linear']"""
        X, Y, Z = self._getXYZ()
        f, a = plt.subplots()
        if norm == 'log':
            norm = LogNorm()
        elif norm == 'linear':
            norm = None
        pc = a.pcolormesh(Y, X, Z, vmin=vmin, vmax=vmax, norm=norm, cmap=plt_tools.get_colorMap_intensity())
        a.set_yscale('linear')
        a.set_xscale('log')
        a.set_xlim((self.bins[0], self.bins[-1]))
        a.set_ylabel('Height (m)')

        a.set_xlabel('Diameter (nm)')
        cb = f.colorbar(pc)
        label = get_label(self.distributionType)
        cb.set_label(label)

        if self.distributionType != 'calibration':
            a.xaxis.set_minor_formatter(plt.FormatStrFormatter("%i"))
            a.xaxis.set_major_formatter(plt.FormatStrFormatter("%i"))

            f.canvas.draw()  # this is important, otherwise the ticks (at least in case of minor ticks) are not created yet
            ticks = a.xaxis.get_minor_ticks()
            for i in ticks:
                if i.label.get_text() in removeTickLabels:
                    i.label.set_visible(False)
        return f, a, pc, cb

    def zoom_altitude(self, start=None, end=None):
        """'2014-11-24 16:02:30'"""
        print('need fixn')
        return False

    # dist = self.copy()
    #        dist.data = dist.data.truncate(before=start, after = end)
    #        return dist
    #


    def average_overAltitude(self, window='1S'):
        print('need fixn')
        return False

    #        window = window
    # self.data = self.data.resample(window, closed='right',label='right')
    #        if self.distributionType == 'calibration':
    #            self.data.values[np.where(np.isnan(self.data.values))] = 0
    #        return

    def average_overAllAltitudes(self):
        print('need fixn')
        return False


#        singleHist = np.zeros(self.data.shape[1])
#        for i in xrange(self.data.shape[1]):
#            line = self.data.values[:,i]
#            singleHist[i] = np.average(line[~np.isnan(line)])
#        return singleHist




def simulate_sizedistribution(diameter=[10, 2500], numberOfDiameters=100, centerOfAerosolMode=200,
                              widthOfAerosolMode=0.2, numberOfParticsInMode=1000):
    """generates a numberconcentration of an aerosol layer which has a gaussian shape when plottet in dN/log(Dp). 
    However, returned is a numberconcentrations (simply the number of particles in each bin, no normalization)
    Returns
        Number concentration (#)
        bin edges (nm)"""

    start = diameter[0]
    end = diameter[1]
    noOfD = numberOfDiameters
    centerDiameter = centerOfAerosolMode
    width = widthOfAerosolMode
    bins = np.linspace(np.log10(start), np.log10(end), noOfD)
    binwidth = bins[1:] - bins[:-1]
    bincenters = (bins[1:] + bins[:-1]) / 2.
    dNDlogDp = plt.mlab.normpdf(bincenters, np.log10(centerDiameter), width)
    extraScale = 1
    scale = 1
    while 1:
        NumberConcent = dNDlogDp * binwidth * scale * extraScale
        if scale != 1:
            break
        else:
            scale = float(numberOfParticsInMode) / NumberConcent.sum()

    binEdges = 10 ** bins
    diameterBinwidth = binEdges[1:] - binEdges[:-1]

    cols = []
    for e, i in enumerate(binEdges[:-1]):
        cols.append(str(i) + '-' + str(binEdges[e + 1]))

    data = pd.DataFrame(np.array([NumberConcent / diameterBinwidth]), columns=cols)
    return SizeDist(data, binEdges, 'dNdDp')


def simulate_sizedistribution_timeseries(diameter=[10, 2500], numberOfDiameters=100, centerOfAerosolMode=200,
                                         widthOfAerosolMode=0.2, numberOfParticsInMode=1000,
                                         startDate='2014-11-24 17:00:00',
                                         endDate='2014-11-24 18:00:00', frequency=10):
    delta = datetime.datetime.strptime(endDate, '%Y-%m-%d %H:%M:%S') - datetime.datetime.strptime(startDate,
                                                                                                  '%Y-%m-%d %H:%M:%S')
    periods = delta.total_seconds() / float(frequency)
    rng = pd.date_range(startDate, periods=periods, freq='%ss' % frequency)

    noOfOsz = 5
    ampOfOsz = 100

    oszi = np.linspace(0, noOfOsz * 2 * np.pi, periods)
    sdArray = np.zeros((periods, numberOfDiameters - 1))
    for e, i in enumerate(rng):
        sdtmp = simulate_sizedistribution(diameter=diameter,
                                          numberOfDiameters=numberOfDiameters,
                                          centerOfAerosolMode=centerOfAerosolMode + (ampOfOsz * np.sin(oszi[e])))
        sdArray[e] = sdtmp.data
    sdts = pd.DataFrame(sdArray, index=rng, columns=sdtmp.data.columns)
    return SizeDist_TS(sdts, sdtmp.bins, sdtmp.distributionType)


def simulate_sizedistribution_layerseries(diameter=[10, 2500], numberOfDiameters=100, heightlimits=[0, 6000],
                                          noOflayers=100, layerHeight=[500., 4000.], layerThickness=[100., 300.],
                                          layerDensity=[1000., 5000.], layerModecenter=[200., 800.], ):
    gaussian = lambda x, mu, sig: np.exp(-(x - mu) ** 2 / (2 * sig ** 2))

    layerbounderies = np.linspace(heightlimits[0], heightlimits[1], noOflayers + 1)
    layercenter = (layerbounderies[1:] + layerbounderies[:-1]) / 2.

    # strata = np.linspace(heightlimits[0],heightlimits[1],noOflayers+1)

    layerArray = np.zeros((noOflayers, numberOfDiameters - 1))

    for e, stra in enumerate(layercenter):
        for i, lay in enumerate(layerHeight):
            sdtmp = simulate_sizedistribution(diameter=diameter, numberOfDiameters=numberOfDiameters,
                                              widthOfAerosolMode=0.2, centerOfAerosolMode=layerModecenter[i],
                                              numberOfParticsInMode=layerDensity[i])
            layerArray[e] += sdtmp.data.values[0] * gaussian(stra, layerHeight[i], layerThickness[i])

    sdls = pd.DataFrame(layerArray, index=layercenter, columns=sdtmp.data.columns)
    return SizeDist_LS(sdls, sdtmp.bins, sdtmp.distributionType, layerbounderies)


def generate_aerosolLayer(diameter=[.01, 2.5], numberOfDiameters=30, centerOfAerosolMode=0.6,
                          widthOfAerosolMode=0.2, numberOfParticsInMode=10000, layerBoundery=[0., 10000], ):
    """Probably deprecated!?! generates a numberconcentration of an aerosol layer which has a gaussian shape when plottet in dN/log(Dp). 
    However, returned is a numberconcentrations (simply the number of particles in each bin, no normalization)
    Returns
        Number concentration (#)
        bin edges (nm)"""

    layerBoundery = np.array(layerBoundery)
    start = diameter[0]
    end = diameter[1]
    noOfD = numberOfDiameters
    centerDiameter = centerOfAerosolMode
    width = widthOfAerosolMode
    bins = np.linspace(np.log10(start), np.log10(end), noOfD)
    binwidth = bins[1:] - bins[:-1]
    bincenters = (bins[1:] + bins[:-1]) / 2.
    dNDlogDp = plt.mlab.normpdf(bincenters, np.log10(centerDiameter), width)
    extraScale = 1
    scale = 1
    while 1:
        NumberConcent = dNDlogDp * binwidth * scale * extraScale
        if scale != 1:
            break
        else:
            scale = float(numberOfParticsInMode) / NumberConcent.sum()

    binEdges = 10 ** bins
    # diameterBinCenters = (binEdges[1:] + binEdges[:-1])/2.
    diameterBinwidth = binEdges[1:] - binEdges[:-1]

    cols = []
    for e, i in enumerate(binEdges[:-1]):
        cols.append(str(i) + '-' + str(binEdges[e + 1]))

    layerBoundery = np.array([0., 10000.])
    # layerThickness = layerBoundery[1:] - layerBoundery[:-1]
    layerCenter = [5000.]
    data = pd.DataFrame(np.array([NumberConcent / diameterBinwidth]), index=layerCenter, columns=cols)
    # return data

    #     atmosAerosolNumberConcentration = pd.DataFrame()
    # atmosAerosolNumberConcentration['bin_center'] = pd.Series(diameterBinCenters)
    #     atmosAerosolNumberConcentration['bin_start'] = pd.Series(binEdges[:-1])
    #     atmosAerosolNumberConcentration['bin_end'] = pd.Series(binEdges[1:])
    #     atmosAerosolNumberConcentration['numberConcentration'] = pd.Series(NumberConcent)
    #     return atmosAerosolNumberConcentration

    return SizeDist_LS(data, binEdges, 'dNdDp', layerBoundery)


def test_generate_numberConcentration():
    """result should look identical to Atmospheric Chemistry and Physis page 422"""
    nc = generate_aerosolLayer(diameter=[0.01, 10], centerOfAerosolMode=0.8, widthOfAerosolMode=0.3,
                               numberOfDiameters=100, numberOfParticsInMode=1000, layerBoundery=[0.0, 10000])

    plt.plot(nc.bincenters, nc.data.values[0].transpose() * nc.binwidth, label='numberConc')
    plt.plot(nc.bincenters, nc.data.values[0].transpose(), label='numberDist')
    ncLN = nc.convert2dNdlogDp()
    plt.plot(ncLN.bincenters, ncLN.data.values[0].transpose(), label='LogNormal')
    plt.legend()
    plt.semilogx()


def _perform_Miecalculations(diam, wavelength, n):
    """
    Performs Mie calculations

    Parameters
    ----------
    diam:       NumPy array of floats
                Array of diameters over which to perform Mie calculations; units are um
    wavelength: float
                Wavelength of light in nm for which to perform calculations
    n:          complex
                Ensemble complex index of refraction

    Returns
        panda DataTable with the diameters as the index and the mie results in the different collumns
        total_extinction_coefficient: this takes the sum of all particles crossections of the particular diameter in a qubic
                                      meter. This is in principle the AOD of an L

    """
    noOfAngles = 100.

    diam = np.asarray(diam)

    extinction_efficiency = np.zeros(diam.shape)
    scattering_efficiency = np.zeros(diam.shape)
    absorption_efficiency = np.zeros(diam.shape)

    extinction_crossection = np.zeros(diam.shape)
    scattering_crossection = np.zeros(diam.shape)
    absorption_crossection = np.zeros(diam.shape)

    extinction_coefficient = np.zeros(diam.shape)
    scattering_coefficient = np.zeros(diam.shape)
    absorption_coefficient = np.zeros(diam.shape)

    # Function for calculating the size parameter for wavelength l and radius r
    sp = lambda r, l: 2. * np.pi * r / l

    for e, d in enumerate(diam):
        radius = d / 2.
        mie = bhmie.bhmie_hagen(sp(radius, wavelength), n, noOfAngles, diameter=d)
        values = mie.return_Values_as_dict()
        extinction_efficiency[e] = values['extinction_efficiency']
        scattering_efficiency[e] = values['scattering_efficiency']
        absorption_efficiency[e] = values['extinction_efficiency'] - values['scattering_efficiency']

        extinction_crossection[e] = values['extinction_crosssection']
        scattering_crossection[e] = values['scattering_crosssection']
        absorption_crossection[e] = values['extinction_crosssection'] - values['scattering_crosssection']

    out = pd.DataFrame(index=diam)
    out['extinction_efficiency'] = pd.Series(extinction_efficiency, index=diam)
    out['scattering_efficiency'] = pd.Series(scattering_efficiency, index=diam)
    out['absorption_efficiency'] = pd.Series(absorption_efficiency, index=diam)

    out['extinction_crossection'] = pd.Series(extinction_crossection, index=diam)
    out['scattering_crossection'] = pd.Series(scattering_crossection, index=diam)
    out['absorption_crossection'] = pd.Series(absorption_crossection, index=diam)
    return out


def _get_coefficients(crossection, cn):
    """
    Calculates the scattering coefficient

    Parameters
    ----------
    crosssection:   float
                    Units are um^2
    cn:             float
                    Particle concentration in cc^-1

    Returns
    --------
    Scattering coefficient in m^-1.  This is the percentage of light that is scattered out of the
    path when it passes through a layer with a thickness of 1 m
    """

    crossection *= 1e-12  # conversion from um^2 to m^2
    cn *= 1e6  # conversion from cm^-3 to m^-3
    coefficient = cn * crossection
    return coefficient