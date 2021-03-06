'''
.. module:: skrf.network
========================================
network (:mod:`skrf.network`)
========================================


Provides a n-port network class and associated functions.

Most of the functionality in this module is provided as methods and
properties of the :class:`Network` Class.


Network Class
===============

.. autosummary::
    :toctree: generated/

    Network

Network Representations
============================

.. autosummary::
    :toctree: generated/

    Network.s
    Network.z
    Network.y
    Network.a
    Network.t

Connecting Networks
===============================

.. autosummary::
    :toctree: generated/

    connect
    innerconnect
    cascade
    cascade_list
    de_embed
    flip


Interpolation and Concatenation Along Frequency Axis
=====================================================

.. autosummary::
    :toctree: generated/

    stitch
    overlap
    Network.resample
    Network.interpolate
    Network.interpolate_self
    Network.interpolate_from_f

Combining Networks
===================================

.. autosummary::
    :toctree: generated/

    n_oneports_2_nport
    four_oneports_2_twoport
    three_twoports_2_threeport
    n_twoports_2_nport



IO
====

.. autosummary::

    skrf.io.general.read
    skrf.io.general.write
    skrf.io.general.ntwk_2_spreadsheet
    Network.write
    Network.write_touchstone
    Network.read
    Network.write_spreadsheet

Noise
============
.. autosummary::
    :toctree: generated/

    Network.add_noise_polar
    Network.add_noise_polar_flatband
    Network.multiply_noise


Supporting Functions
======================

.. autosummary::
    :toctree: generated/

    inv
    connect_s
    innerconnect_s
    s2z
    s2y
    s2t
    s2a
    z2s
    z2y
    z2t
    z2a
    y2s
    y2z
    y2t
    t2s
    t2z
    t2y
    fix_z0_shape
    renormalize_s
    passivity
    reciprocity

Misc Functions
=====================
.. autosummary::
    :toctree: generated/

    average
    two_port_reflect
    chopinhalf
    Network.nudge
    Network.renormalize



'''
from six.moves import xrange

import os
import warnings
try:
    import cPickle as pickle    
    from cPickle import UnpicklingError
except ImportError:
    import pickle as pickle
    from pickle import UnpicklingError

from copy import deepcopy as copy
import re
from numbers import Number
from itertools import product
import numpy as npy

from numpy.linalg import inv as npy_inv

import pylab as plb
from scipy import stats,signal        # for Network.add_noise_*, and Network.windowed

from scipy.interpolate import interp1d # for Network.interpolate()
from numpy import fft
import unittest # fotr unitest.skip

from . import mathFunctions as mf
    
from . frequency import Frequency

from . plotting import *#smith, plot_rectangular, plot_smith, plot_complex_polar
from . tlineFunctions import zl_2_Gamma0
from . util import get_fid, get_extn, find_nearest_index,slice_domain
## later imports. delayed to solve circular dependencies
#from io.general import read, write
#from io import touchstone
#from io.general import network_2_spreadsheet

from .constants import ZERO

class Network(object):
    '''

    A n-port electrical network [#]_.

    For instructions on how to create Network see  :func:`__init__`.

    A n-port network may be defined by three quantities,
     * network parameter matrix (s, z, or y-matrix)
     * port characteristic impedance matrix
     * frequency information

    The :class:`Network` class stores these data structures internally
    in the form of complex :class:`numpy.ndarray`'s. These arrays are not
    interfaced directly but instead through the use of the properties:

    =====================  =============================================
    Property               Meaning
    =====================  =============================================
    :attr:`s`              scattering parameter matrix
    :attr:`z0`             characteristic impedance matrix
    :attr:`f`              frequency vector
    =====================  =============================================

    Although these docs focus on s-parameters, other equivalent network
    representations such as :attr:`z` and  :attr:`y` are
    available. Scalar projections of the complex network parameters
    are accessible through properties as well. These also return
    :class:`numpy.ndarray`'s.

    =====================  =============================================
    Property               Meaning
    =====================  =============================================
    :attr:`s_re`           real part of the s-matrix
    :attr:`s_im`           imaginary part of the s-matrix
    :attr:`s_mag`          magnitude of the s-matrix
    :attr:`s_db`           magnitude in log scale of the s-matrix
    :attr:`s_deg`          phase of the s-matrix in degrees
    :attr:`s_gd`           group delay derived from the s-matrix
    =====================  =============================================

    The following operations act on the networks s-matrix.

    =====================  =============================================
    Operator               Function
    =====================  =============================================
    \+                     element-wise addition of the s-matrix
    \-                     element-wise difference of the s-matrix
    \*                     element-wise multiplication of the s-matrix
    \/                     element-wise division of the s-matrix
    \*\*                   cascading (only for 2-ports)
    \//                    de-embedding (for 2-ports, see :attr:`inv`)
    =====================  =============================================

    Different components of the :class:`Network` can be visualized
    through various plotting methods. These methods can be used to plot
    individual elements of the s-matrix or all at once. For more info
    about plotting see the :doc:`../../tutorials/plotting` tutorial.

    =========================  =============================================
    Method                     Meaning
    =========================  =============================================
    :func:`plot_s_smith`       plot complex s-parameters on smith chart
    :func:`plot_s_re`          plot real part of s-parameters vs frequency
    :func:`plot_s_im`          plot imaginary part of s-parameters vs frequency
    :func:`plot_s_mag`         plot magnitude of s-parameters vs frequency
    :func:`plot_s_db`          plot magnitude (in dB) of s-parameters vs frequency
    :func:`plot_s_deg`         plot phase of s-parameters (in degrees) vs frequency
    :func:`plot_s_deg_unwrap`  plot phase of s-parameters (in unwrapped degrees) vs frequency
    :func:`plot_s_gd`          plot group delay of s-parameters (in s) vs frequency
    =========================  =============================================

    :class:`Network`  objects can be  created from a touchstone or pickle
    file  (see :func:`__init__`), by a
    :class:`~skrf.media.media.Media` object, or manually by assigning the
    network properties directly. :class:`Network`  objects
    can be saved to disk in the form of touchstone files with the
    :func:`write_touchstone` method.

    An exhaustive list of :class:`Network` Methods and Properties
    (Attributes) are given below

    References
    ------------
    .. [#] http://en.wikipedia.org/wiki/Two-port_network
    '''
    

    global PRIMARY_PROPERTIES
    PRIMARY_PROPERTIES = [ 's','z','y','a']

    global COMPONENT_FUNC_DICT
    COMPONENT_FUNC_DICT = {
        're'    : npy.real,
        'im'    : npy.imag,
        'mag'   : npy.abs,
        'db'    : mf.complex_2_db,
        'db10'    : mf.complex_2_db10,
        'rad'   : npy.angle,
        'deg'   : lambda x: npy.angle(x, deg=True),
        'arcl'  : lambda x: npy.angle(x) * npy.abs(x),
        'rad_unwrap'    : lambda x: mf.unwrap_rad(npy.angle(x)),
        'deg_unwrap'    : lambda x: mf.radian_2_degree(mf.unwrap_rad(\
            npy.angle(x))),
        'arcl_unwrap'   : lambda x: mf.unwrap_rad(npy.angle(x)) *\
            npy.abs(x),
        'gd' : lambda x: -1 * npy.gradient(mf.unwrap_rad(npy.angle(x)))[0],
        'vswr' : lambda x: (1+abs(x))/(1-abs(x)),
        'time' : lambda x: fft.ifftshift(fft.ifft(x, axis=0), axes=0),
        'time_db' : lambda x: mf.complex_2_db(fft.ifftshift(fft.ifft(x, axis=0),axes=0)),
        'time_mag' : lambda x: mf.complex_2_magnitude(fft.ifftshift(fft.ifft(x, axis=0),axes=0)),
        }
    # provides y-axis labels to the plotting functions
    global Y_LABEL_DICT
    Y_LABEL_DICT = {
        're'    : 'Real Part',
        'im'    : 'Imag Part',
        'mag'   : 'Magnitude',
        'abs'   : 'Magnitude',
        'db'    : 'Magnitude (dB)',
        'db10'    : 'Magnitude (dB)',
        'deg'   : 'Phase (deg)',
        'deg_unwrap'    : 'Phase (deg)',
        'rad'   : 'Phase (rad)',
        'rad_unwrap'    : 'Phase (rad)',
        'arcl'  : 'Arc Length',
        'arcl_unwrap'   : 'Arc Length',
        'gd' : 'Group Delay (s)',
        'vswr' : 'VSWR',
        'passivity' : 'Passivity',
        'reciprocity' : 'Reciprocity',
        'time': 'Time (real)',
        'time_db': 'Magnitude (dB)',
        'time_mag': 'Magnitude',
        }


    ## CONSTRUCTOR
    def __init__(self, file = None, name = None , comments = None, f_unit=None, **kwargs):
        '''
        Network constructor.

        Creates an n-port microwave network from a `file` or directly
        from data. If no file or data is given, then an empty Network
        is created.

        Parameters
        ------------

        file : str or file-object
            file to load information from. supported formats are:
             * touchstone file (.s?p)
             * pickled Network (.ntwk, .p) see :func:`write`
        name : str
            Name of this Network. if None will try to use file, if
            its a str
        comments : str
            Comments associated with the Network
        \*\*kwargs :
            key word arguments can be used to assign properties of the
            Network, such as `s`, `f` and `z0`.

        Examples
        ------------
        From a touchstone

        >>> n = rf.Network('ntwk1.s2p')

        From a pickle file

        >>> n = rf.Network('ntwk1.ntwk')

        Create a blank network, then fill in values

        >>> n = rf.Network()
        >>> freq = rf.Frequency(1,3,3,'ghz')
        >>> n.frequency, n.s, n.z0 = freq,[1,2,3], [1,2,3]

        Directly from values

        >>> n = rf.Network(f=[1,2,3],s=[1,2,3],z0=[1,2,3])

        See Also
        -----------
        read : read a network from a file
        write : write a network to a file, using pickle
        write_touchstone : write a network to a touchstone file
        '''

        # allow for old kwarg for backward compatability
        if 'touchstone_filename' in kwargs:
            file = kwargs['touchstone_filename']

        self.name = name
        self.comments = comments

        if file is not None:
            # allows user to pass filename or file obj
            # open file in 'binary' mode because we are going to try and
            # unpickle it first
            fid = get_fid(file,'rb')

            try:
                self.read(fid)
            except(UnpicklingError):
                # if unpickling doesn't work then, close fid, reopen in
                # non-binary mode and try to read it as touchstone
                fid.close()
                fid = get_fid(file)
                self.read_touchstone(fid)

            if name is None and isinstance(file,str):
                name = os.path.splitext(os.path.basename(file))[0]


        if self.frequency is not None and f_unit is not None:
            self.frequency.unit = f_unit


        # allow properties to be set through the constructor
        for attr in PRIMARY_PROPERTIES + ['frequency','z0','f']:
            if attr in kwargs:
                self.__setattr__(attr,kwargs[attr])


        #self.nports = self.number_of_ports
        ##TODO: remove this as it takes up ~70% cpu time of this init
        self.__generate_plot_functions()
        

    ## OPERATORS
    def __pow__(self,other):
        '''
        cascade this network with another network

        port 1 of this network is connected to port 0 or the other
        network
        '''
        # if they pass a number then use power operator
        if isinstance(other, Number):
            out = self.copy()
            out.s = out.s**other
            return out
        # else connect the two
        return connect(self,1,other,0)

    def __floordiv__(self,other):
        '''
        de-embeding another network[s], from this network

        See Also
        ----------
        inv : inverse s-parameters
        '''
        try:
            # if they passed 1 ntwks and a tuple of ntwks,
            # then deEmbed like A.inv*C*B.inv
            b = other[0]
            c = other[1]
            result =  copy (self)
            result.s =  (b.inv**self**c.inv).s
            #flip(de_embed( flip(de_embed(c.s,self.s)),b.s))
            return result
        except TypeError:
            pass

        if other.number_of_ports == 2:
            result = self.copy()
            result.s = (other.inv**self).s
            #de_embed(self.s,other.s)
            return result
        else:
            raise IndexError('Incorrect number of ports.')

    def __mul__(self,other):
        '''
        Element-wise complex multiplication of s-matrix
        '''
        result = self.copy()

        if isinstance(other, Network):
            self.__compatable_for_scalar_operation_test(other)
            result.s = self.s * other.s
        else:
            # other may be an array or a number
            result.s = self.s * npy.array(other).reshape(-1,self.nports,self.nports)

        return result

    def __rmul__(self,other):
        '''
        Element-wise complex multiplication of s-matrix
        '''

        result = self.copy()

        if isinstance(other, Network):
            self.__compatable_for_scalar_operation_test(other)
            result.s = self.s * other.s
        else:
            # other may be an array or a number
            result.s = self.s * npy.array(other).reshape(-1,self.nports,self.nports)

        return result

    def __add__(self,other):
        '''
        Element-wise complex addition of s-matrix
        '''
        result = self.copy()

        if isinstance(other, Network):
            self.__compatable_for_scalar_operation_test(other)
            result.s = self.s + other.s
        else:
            # other may be an array or a number
            result.s = self.s + npy.array(other).reshape(-1,self.nports,self.nports)

        return result

    def __radd__(self,other):
        '''
        Element-wise complex addition of s-matrix
        '''
        result = self.copy()

        if isinstance(other, Network):
            self.__compatable_for_scalar_operation_test(other)
            result.s = self.s + other.s
        else:
            # other may be an array or a number
            result.s = self.s + npy.array(other).reshape(-1,self.nports,self.nports)

        return result


    def __sub__(self,other):
        '''
        Element-wise complex subtraction of s-matrix
        '''
        result = self.copy()

        if isinstance(other, Network):
            self.__compatable_for_scalar_operation_test(other)
            result.s = self.s - other.s
        else:
            # other may be an array or a number
            result.s = self.s - npy.array(other).reshape(-1,self.nports,self.nports)

        return result

    def __rsub__(self,other):
        '''
        Element-wise complex subtraction of s-matrix
        '''
        result = self.copy()

        if isinstance(other, Network):
            self.__compatable_for_scalar_operation_test(other)
            result.s = other.s - self.s
        else:
            # other may be an array or a number
            result.s = npy.array(other).reshape(-1,self.nports,self.nports) - self.s

        return result
    
    def __truediv__(self,other):
        return self.__div__(other)

    def __div__(self,other):
        '''
        Element-wise complex multiplication of s-matrix
        '''
        result = self.copy()

        if isinstance(other, Network):
            self.__compatable_for_scalar_operation_test(other)
            result.s = self.s / other.s
        else:
            # other may be an array or a number
            result.s = self.s / npy.array(other).reshape(-1,self.nports,self.nports)

        return result


    def __eq__(self,other):
        if other is None:
            return False
        if npy.all(npy.abs(self.s - other.s) < ZERO):
            return True
        else:
            return False

    def __ne__(self,other):
        return (not self.__eq__(other))

    def __getitem__(self,key):
        '''
        Slices a Network object based on an index, or human readable string

        Parameters
        -----------
        key : str, or slice
            if slice; like [2-10] then it is interpreted as the index of
            the frequency.
            if str, then should be like '50.1-75.5ghz', or just '50'.
            If the frequency unit is omited then self.frequency.unit is
            used.

        Examples
        -----------
        >>> from skrf.data import ring_slot
        >>> a = ring_slot['80-90ghz']
        >>> a.plot_s_db()
        '''
        a = self.z0# HACK: to force getter for z0 to re-shape it
        sliced_frequency = self.frequency[key]
        return self.interpolate(sliced_frequency)


    def __str__(self):
        '''
        '''
        f = self.frequency
        if self.name is None:
            name = ''
        else:
            name = self.name

        if len(npy.shape(self.z0)) == 0:
            z0 = str(self.z0)
        else:
            z0 = str(self.z0[0,:])

        output = '%i-Port Network: \'%s\',  %s, z0=%s' % (self.number_of_ports, name, str(f), z0)

        return output

    def __repr__(self):
        return self.__str__()

    def __len__(self):
        '''
        length of frequency axis
        '''
        return len(self.s)



    ## INTERNAL CODE GENERATION METHODS
    def __compatable_for_scalar_operation_test(self, other):
        '''
        tests to make sure other network's s-matrix is of same shape
        '''
        if other.frequency  != self.frequency:
            raise IndexError('Networks must have same frequency. See `Network.interpolate`')

        if other.s.shape != self.s.shape:
            raise IndexError('Networks must have same number of ports.')

    def __generate_secondary_properties(self):
        '''
        creates numerous `secondary properties` which are various
        different scalar projects of the primary properties. the primary
        properties are s,z, and y.
        '''
        for prop_name in PRIMARY_PROPERTIES:
            for func_name in COMPONENT_FUNC_DICT:
                func = COMPONENT_FUNC_DICT[func_name]
                if 'gd' in func_name: # scaling of gradient by frequency
                    def fget(self, f=func, p = prop_name):
                        return f(getattr(self,p)) / (2 * npy.pi * self.frequency.step)
                else:
                    def fget(self, f=func, p = prop_name):
                        return f(getattr(self,p))
                doc = '''
                The %s component of the %s-matrix


                See Also
                ----------
                %s
                '''%(func_name, prop_name, prop_name)

                setattr(self.__class__,'%s_%s'%(prop_name, func_name),\
                    property(fget, doc = doc))

    def __generate_plot_functions(self):
        '''
        '''
        for prop_name in PRIMARY_PROPERTIES:

            def plot_prop_polar(self,
                m=None, n=None, ax=None,
                show_legend=True ,prop_name=prop_name,*args, **kwargs):

                # create index lists, if not provided by user
                if m is None:
                    M = range(self.number_of_ports)
                else:
                    M = [m]
                if n is None:
                    N = range(self.number_of_ports)
                else:
                    N = [n]

                if 'label'  not in kwargs.keys():
                    gen_label = True
                else:
                    gen_label = False


                was_interactive = plb.isinteractive
                if was_interactive:
                    plb.interactive(False)

                for m in M:
                    for n in N:
                        # set the legend label for this trace to the networks
                        # name if it exists, and they didnt pass a name key in
                        # the kwargs
                        if gen_label:
                            if self.name is None:
                                if plb.rcParams['text.usetex']:
                                    label_string = '$%s_{%i%i}$'%\
                                    (prop_name[0].upper(),m+1,n+1)
                                else:
                                    label_string = '%s%i%i'%\
                                    (prop_name[0].upper(),m+1,n+1)
                            else:
                                if plb.rcParams['text.usetex']:
                                    label_string = self.name+', $%s_{%i%i}$'%\
                                    (prop_name[0].upper(),m+1,n+1)
                                else:
                                    label_string = self.name+', %s%i%i'%\
                                    (prop_name[0].upper(),m+1,n+1)
                            kwargs['label'] = label_string

                        # plot the desired attribute vs frequency
                        plot_complex_polar(
                            z = getattr(self,prop_name)[:,m,n],
                             show_legend = show_legend, ax = ax,
                            *args, **kwargs)

                if was_interactive:
                    plb.interactive(True)
                    plb.draw()
                    plb.show()

            plot_prop_polar.__doc__ = '''
    plot the Network attribute :attr:`%s` vs frequency.

    Parameters
    -----------
    m : int, optional
        first index of s-parameter matrix, if None will use all
    n : int, optional
        secon index of the s-parameter matrix, if None will use all
    ax : :class:`matplotlib.Axes` object, optional
        An existing Axes object to plot on
    show_legend : Boolean
        draw legend or not
    attribute : string
        Network attribute to plot
    y_label : string, optional
        the y-axis label

    \*args,\\**kwargs : arguments, keyword arguments
        passed to :func:`matplotlib.plot`

    Notes
    -------
    This function is dynamically generated upon Network
    initialization. This is accomplished by calling
    :func:`plot_vs_frequency_generic`

    Examples
    ------------
    >>> myntwk.plot_%s(m=1,n=0,color='r')
    '''%(prop_name,prop_name)

            setattr(self.__class__,'plot_%s_polar'%(prop_name), \
                plot_prop_polar)

            def plot_prop_rect(self,
                m=None, n=None, ax=None,
                show_legend=True,prop_name=prop_name,*args, **kwargs):

                # create index lists, if not provided by user
                if m is None:
                    M = range(self.number_of_ports)
                else:
                    M = [m]
                if n is None:
                    N = range(self.number_of_ports)
                else:
                    N = [n]

                if 'label'  not in kwargs.keys():
                    gen_label = True
                else:
                    gen_label = False


                #was_interactive = plb.isinteractive
                #if was_interactive:
                #    plb.interactive(False)

                for m in M:
                    for n in N:
                        # set the legend label for this trace to the networks
                        # name if it exists, and they didnt pass a name key in
                        # the kwargs
                        if gen_label:
                            if self.name is None:
                                if plb.rcParams['text.usetex']:
                                    label_string = '$%s_{%i%i}$'%\
                                    (prop_name[0].upper(),m+1,n+1)
                                else:
                                    label_string = '%s%i%i'%\
                                    (prop_name[0].upper(),m+1,n+1)
                            else:
                                if plb.rcParams['text.usetex']:
                                    label_string = self.name+', $%s_{%i%i}$'%\
                                    (prop_name[0].upper(),m+1,n+1)
                                else:
                                    label_string = self.name+', %s%i%i'%\
                                    (prop_name[0].upper(),m+1,n+1)
                            kwargs['label'] = label_string

                        # plot the desired attribute vs frequency
                        plot_complex_rectangular(
                            z = getattr(self,prop_name)[:,m,n],
                             show_legend = show_legend, ax = ax,
                            *args, **kwargs)

                #if was_interactive:
                #    plb.interactive(True)
                #    plb.draw()
                #    plb.show()

            plot_prop_rect.__doc__ = '''
    plot the Network attribute :attr:`%s` vs frequency.

    Parameters
    -----------
    m : int, optional
        first index of s-parameter matrix, if None will use all
    n : int, optional
        secon index of the s-parameter matrix, if None will use all
    ax : :class:`matplotlib.Axes` object, optional
        An existing Axes object to plot on
    show_legend : Boolean
        draw legend or not
    attribute : string
        Network attribute to plot
    y_label : string, optional
        the y-axis label

    \*args,\\**kwargs : arguments, keyword arguments
        passed to :func:`matplotlib.plot`

    Notes
    -------
    This function is dynamically generated upon Network
    initialization. This is accomplished by calling
    :func:`plot_vs_frequency_generic`

    Examples
    ------------
    >>> myntwk.plot_%s(m=1,n=0,color='r')
    '''%(prop_name,prop_name)

            setattr(self.__class__,'plot_%s_complex'%(prop_name), \
                plot_prop_rect)


            for func_name in COMPONENT_FUNC_DICT:
                attribute = '%s_%s'%(prop_name, func_name)
                y_label = Y_LABEL_DICT[func_name]

                def plot_func(self,  m=None, n=None, ax=None,
                    show_legend=True,attribute=attribute,
                    y_label=y_label,*args, **kwargs):

                    # create index lists, if not provided by user
                    if m is None:
                        M = range(self.number_of_ports)
                    else:
                        M = [m]
                    if n is None:
                        N = range(self.number_of_ports)
                    else:
                        N = [n]

                    if 'label'  not in kwargs.keys():
                        gen_label = True
                    else:
                        gen_label = False

                    #TODO: turn off interactive plotting for performance
                    # this didnt work because it required a show()
                    # to be called, which in turn, disrupted testCases
                    #
                    #was_interactive = plb.isinteractive
                    #if was_interactive:
                    #    plb.interactive(False)

                    for m in M:
                        for n in N:
                            # set the legend label for this trace to the networks
                            # name if it exists, and they didnt pass a name key in
                            # the kwargs
                            if gen_label:
                                if self.name is None:
                                    if plb.rcParams['text.usetex']:
                                        label_string = '$%s_{%i%i}$'%\
                                        (attribute[0].upper(),m+1,n+1)
                                    else:
                                        label_string = '%s%i%i'%\
                                        (attribute[0].upper(),m+1,n+1)
                                else:
                                    if plb.rcParams['text.usetex']:
                                        label_string = self.name+', $%s_{%i%i}$'%\
                                        (attribute[0].upper(),m+1,n+1)
                                    else:
                                        label_string = self.name+', %s%i%i'%\
                                        (attribute[0].upper(),m+1,n+1)
                                kwargs['label'] = label_string

                            # plot the desired attribute vs frequency
                            if 'time' in attribute:
                                xlabel = 'Time (ns)'
                                x = self.frequency.t_ns

                            else:
                                xlabel = 'Frequency (%s)'%self.frequency.unit
                                x = self.frequency.f_scaled

                            plot_rectangular(
                                    x = x,
                                    y = getattr(self,attribute)[:,m,n],
                                    x_label = xlabel,
                                    y_label = y_label,
                                    show_legend = show_legend, ax = ax,
                                    *args, **kwargs)


                    #if was_interactive:
                    #    plb.interactive(True)
                    #    plb.draw()
                    #    #plb.show()

                plot_func.__doc__ = '''
        plot the Network attribute :attr:`%s` vs frequency.

        Parameters
        -----------
        m : int, optional
            first index of s-parameter matrix, if None will use all
        n : int, optional
            secon index of the s-parameter matrix, if None will use all
        ax : :class:`matplotlib.Axes` object, optional
            An existing Axes object to plot on
        show_legend : Boolean
            draw legend or not
        attribute : string
            Network attribute to plot
        y_label : string, optional
            the y-axis label

        \*args,\\**kwargs : arguments, keyword arguments
            passed to :func:`matplotlib.plot`

        Notes
        -------
        This function is dynamically generated upon Network
        initialization. This is accomplished by calling
        :func:`plot_vs_frequency_generic`

        Examples
        ------------
        >>> myntwk.plot_%s(m=1,n=0,color='r')
        '''%(attribute,attribute)

                setattr(self.__class__,'plot_%s'%(attribute), \
                    plot_func)

    def __generate_subnetworks(self):
        '''
        generates all one-port sub-networks
        '''
        for m in range(self.number_of_ports):
            for n in range(self.number_of_ports):
                def fget(self,m=m,n=n):
                    ntwk = self.copy()
                    ntwk.s = self.s[:,m,n]
                    ntwk.z0 = self.z0[:,m]
                    return ntwk
                doc = '''
                one-port sub-network.
                '''
                setattr(self.__class__,'s%i%i'%(m+1,n+1),\
                    property(fget,doc=doc))

    def plot_s_db_time(self,*args,**kwargs):
        return self.windowed().plot_s_time_db(*args,**kwargs)

    ## PRIMARY PROPERTIES
    @property
    def s(self):
        '''
        Scattering parameter matrix.

        The s-matrix[#]_ is a 3-dimensional :class:`numpy.ndarray` which has shape
        `fxnxn`, where `f` is frequency axis and `n` is number of ports.
        Note that indexing starts at 0, so s11 can be accessed by
        taking the slice s[:,0,0].


        Returns
        ---------
        s : complex :class:`numpy.ndarray` of shape `fxnxn`
                the scattering parameter matrix.

        See Also
        ------------
        s
        y
        z
        t
        a

        References
        ------------
        .. [#] http://en.wikipedia.org/wiki/Scattering_parameters
        '''
        return self._s

    @s.setter
    def s(self, s):
        '''
        the input s-matrix should be of shape fxnxn,
        where f is frequency axis and n is number of ports
        '''
        s_shape= npy.shape(s)
        if len(s_shape) <3:
            if len(s_shape) == 2:
                # reshape to kx1x1, this simplifies indexing in function
                s = npy.reshape(s,(-1,s_shape[0],s_shape[0]))
            else:
                s = npy.reshape(s,(-1,1,1))

        self._s = npy.array(s,dtype=complex)
        self.__generate_secondary_properties()
        self.__generate_subnetworks()

    @property
    def y(self):
        '''
        Admittance parameter matrix.

        The y-matrix [#]_ is a 3-dimensional :class:`numpy.ndarray` which has shape
        `fxnxn`, where `f` is frequency axis and `n` is number of ports.
        Note that indexing starts at 0, so y11 can be accessed by
        taking the slice `y[:,0,0]`.


        Returns
        ---------
        y : complex :class:`numpy.ndarray` of shape `fxnxn`
                the admittance parameter matrix.

        See Also
        ------------
        s
        y
        z
        t
        a

        References
        ------------
        .. [#] http://en.wikipedia.org/wiki/Admittance_parameters
        '''
        return s2y(self._s, self.z0)

    @y.setter
    def y(self, value):
        self._s = y2s(value, self.z0)

    @property
    def z(self):
        '''
        Impedance parameter matrix.

        The z-matrix  [#]_ is a 3-dimensional :class:`numpy.ndarray` which has shape
        `fxnxn`, where `f` is frequency axis and `n` is number of ports.
        Note that indexing starts at 0, so z11 can be accessed by
        taking the slice `z[:,0,0]`.


        Returns
        ---------
        z : complex :class:`numpy.ndarray` of shape `fxnxn`
                the Impedance parameter matrix.

        See Also
        ------------
        s
        y
        z
        t
        a

        References
        ------------
        .. [#] http://en.wikipedia.org/wiki/impedance_parameters
        '''
        return s2z(self._s, self.z0)

    @z.setter
    def z(self, value):
        self._s = z2s(value, self.z0)

    @property
    def t(self):
        '''
        Scattering transfer parameters

        The t-matrix [#]_ is a 3-dimensional :class:`numpy.ndarray`
        which has shape `fx2x2`, where `f` is frequency axis.
        Note that indexing starts at 0, so t11 can be accessed by
        taking the slice `t[:,0,0]`.

        The t-matrix, also known as the wave cascading matrix, is
        only defined for a 2-port Network.

        Returns
        --------
        t : complex numpy.ndarry of shape `fx2x2`
                t-parameters, aka scattering transfer parameters


        See Also
        ------------
        s
        y
        z
        t
        a

        References
        -----------
        .. [#] http://en.wikipedia.org/wiki/Scattering_parameters#Scattering_transfer_parameters
        '''
        return s2t(self.s)

    @property
    def sa(self):
        '''
        Active scattering parameter matrix.

        Active scattering parameters are simply inverted s-parameters,
        defined as a = 1/s. Useful in analysis of active networks.
        The a-matrix is a 3-dimensional :class:`numpy.ndarray` which has shape
        `fxnxn`, where `f` is frequency axis and `n` is number of ports.
        Note that indexing starts at 0, so a11 can be accessed by
        taking the slice a[:,0,0].


        Returns
        ---------
        a : complex :class:`numpy.ndarray` of shape `fxnxn`
                the active scattering parameter matrix.

        See Also
        ------------
        s
        y
        z
        t
        a
        '''
        return 1/self.s

    @sa.setter
    def sa(self, value):
        raise (NotImplementedError)

    @property
    def a(self):
        '''
        abcd parameter matrix. Used to cascade two-ports

        The abcd-matrix  [#]_ is a 3-dimensional :class:`numpy.ndarray` which has shape
        `fxnxn`, where `f` is frequency axis and `n` is number of ports.
        Note that indexing starts at 0, so abcd11 can be accessed by
        taking the slice `abcd[:,0,0]`.


        Returns
        ---------
        abcd : complex :class:`numpy.ndarray` of shape `fxnxn`
                the Impedance parameter matrix.

        See Also
        ------------
        s
        y
        z
        t
        a
        abcd

        References
        ------------
        .. [#] http://en.wikipedia.org/wiki/impedance_parameters
        '''
        return s2a(self.s, self.z0)
    @a.setter
    def a(self, value):
        raise (NotImplementedError)

    @property
    def z0(self):
        '''
        Characteristic impedance[s] of the network ports.

        This property stores the  characteristic impedance of each port
        of the network. Because it is possible that each port has
        a different characteristic impedance each varying with
        frequency, `z0` is stored internally as a `fxn` array.

        However because  `z0` is frequently simple (like 50ohm), it can
        be set with just number as well.

        Returns
        --------
        z0 : :class:`numpy.ndarray` of shape fxn
                characteristic impedance for network

        '''
        # i hate this function
        # it was written this way because id like to allow the user to
        # set the z0 before the s-parameters are set. However, in this
        # case we dont know how to re-shape the z0 to fxn. to solve this
        # i attempt to do the re-shaping when z0 is accessed, not when
        # it is set. this is what makes this function confusing.
        
        try:
            if len(npy.shape(self._z0)) ==0:
                try:
                    #try and re-shape z0 to match s
                    self._z0=self._z0*npy.ones(self.s.shape[:-1])
                except(AttributeError):
                    print ('Warning: Network has improper \'z0\' shape.')
                    #they have yet to set s .

            elif len(npy.shape(self._z0)) ==1:
                try:
                    if len(self._z0) == self.frequency.npoints:
                        # this z0 is frequency dependent but not port dependent
                        self._z0 = \
                                npy.repeat(npy.reshape(self._z0,(-1,1)),self.number_of_ports,1)

                    elif len(self._z0) == self.number_of_ports:
                        # this z0 is port dependent but not frequency dependent
                        self._z0 = self._z0*npy.ones(\
                                (self.frequency.npoints,self.number_of_ports))

                    else:
                        raise(IndexError('z0 has bad shape'))

                except(AttributeError):
                    # there is no self.frequency, or self.number_of_ports
                    raise(AttributeError('Error: I cant reshape z0 through inspection. you must provide correctly shaped z0, or s-matrix first.'))

            return self._z0

        except(AttributeError):
            #print('Warning: z0 is undefined. Defaulting to 50.')
            self.z0=50
            return self.z0 #this is not an error, its a recursive call

    @z0.setter
    def z0(self, z0):
        '''z0=npy.array(z0)
        if len(z0.shape) < 2:
                try:
                        #try and re-shape z0 to match s
                        z0=z0*npy.ones(self.s.shape[:-1])
                except(AttributeError):
                        print ('Warning: you should store a Network\'s \'s\' matrix before its \'z0\'')
                        #they have yet to set s .
                        pass
        '''
        self._z0 = npy.array(z0,dtype=complex)

    @property
    def frequency(self):
        '''
        frequency information for the network.

        This property is a :class:`~skrf.frequency.Frequency` object.
        It holds the frequency vector, as well frequency unit, and
        provides other properties related to frequency information, such
        as start, stop, etc.

        Returns
        --------
        frequency :  :class:`~skrf.frequency.Frequency` object
                frequency information for the network.


        See Also
        ---------
        f : property holding frequency vector in Hz
        change_frequency : updates frequency property, and
            interpolates s-parameters if needed
        interpolate : interpolate function based on new frequency
            info
        '''
        try:
            return self._frequency
        except (AttributeError):
            self._frequency = Frequency(0,0,0)
            return self._frequency

    @frequency.setter
    def frequency(self, new_frequency):
        '''
        takes a Frequency object, see  frequency.py
        '''
        if isinstance(new_frequency, Frequency):
            self._frequency = new_frequency.copy()
        else:
            try:
                self._frequency = Frequency.from_f(new_frequency)
            except (TypeError):
                raise TypeError('Could not convert argument to a frequency vector')



    @property
    def inv(self):
        '''
        a :class:`Network` object with 'inverse' s-parameters.

        This is used for de-embedding. It is defined so that the inverse
        of a Network cascaded with itself is unity.

        Returns
        ---------
        inv : a :class:`Network` object
                a :class:`Network` object with 'inverse' s-parameters.

        See Also
        ----------
                inv : function which implements the inverse s-matrix
        '''
        if self.number_of_ports <2:
            raise(TypeError('One-Port Networks dont have inverses'))
        out = self.copy()
        out.s = inv(self.s)
        return out

    @property
    def f(self):
        '''
        the frequency vector for the network, in Hz.

        Returns
        --------
        f : :class:`numpy.ndarray`
                frequency vector in Hz

        See Also
        ---------
                frequency : frequency property that holds all frequency
                        information
        '''
        return self.frequency.f

    @f.setter
    def f(self,f):
        tmpUnit= self.frequency.unit
        self.frequency = Frequency.from_f(f, unit=tmpUnit)


    ## SECONDARY PROPERTIES
    @property
    def number_of_ports(self):
        '''
        the number of ports the network has.

        Returns
        --------
        number_of_ports : number
                the number of ports the network has.

        '''
        try:
            return self.s.shape[1]
        except (AttributeError):
            return 0

    @property
    def nports(self):
        '''
        the number of ports the network has.

        Returns
        --------
        number_of_ports : number
                the number of ports the network has.

        '''
        return self.number_of_ports

    @property
    def port_tuples(self):
        '''
        Returns a list of tuples, for each port index pair

        A convenience function for the common task fo iterating over
        all s-parameters index pairs

        This just calls:
        `[(y,x) for x in range(self.nports) for y in range(self.nports)]`
        '''
        return [(y,x) for x in range(self.nports) for y in range(self.nports)]

    @property
    def passivity(self):
        '''
        passivity metric for a multi-port network.

        This returns a matrix who's diagonals are equal to the total
        power received at all ports, normalized to the power at a single
        excitement port.

        mathematically, this is a test for unitary-ness of the
        s-parameter matrix [#]_.

        for two port this is

        .. math::

                ( |S_{11}|^2 + |S_{21}|^2 \, , \, |S_{22}|^2+|S_{12}|^2)

        in general it is

        .. math::

                S^H \\cdot S

        where :math:`H` is conjugate transpose of S, and :math:`\\cdot`
        is dot product.

        Returns
        ---------
        passivity : :class:`numpy.ndarray` of shape fxnxn

        References
        ------------
        .. [#] http://en.wikipedia.org/wiki/Scattering_parameters#Lossless_networks
        '''
        return passivity(self.s)

    @property
    def reciprocity(self):
        '''
        reciprocity metric for a multi-port network.

        This returns the difference between the s-parameter matrix
        and its transpose.

        for two port this is

        .. math::

                S - S^T



        where :math:`T` is transpose of S

        Returns
        ---------
        reciprocity : :class:`numpy.ndarray` of shape fxnxn


        '''
        return reciprocity(self.s)

    @property
    def reciprocity2(self):
        '''
        Reciprocity metric #2

        .. math::

                abs(1 - S/S^T )

        for the two port case, this evaluates to the distance of the
        determinant of the wave-cascading matrix from unity.

        '''
        return abs(1-self.s/self.s.swapaxes(1,2))

    ## NETWORK CLASIFIERs
    def is_reciprocal(self):
        '''
        test for reciprocity
        '''
        raise(NotImplementedError)

    def is_symmetric(self):
        '''
        test for symmetry
        '''
        raise(NotImplementedError)

    def is_passive(self):
        '''
        test for passivity
        '''
        raise(NotImplementedError)

    def is_lossless(self):
        '''
        test for losslessness
        '''
        raise(NotImplementedError)




    ## specific ploting functions
    def plot_passivity(self, port = None,label_prefix=None,  *args, **kwargs):
        '''
        Plot dB(diag(passivity metric)) vs frequency
        
        Notes
        -------
        This plot does not completely capture the passivity metric, which 
        is a test for `unitary-ness` of the s-matrix. However, it may
        be  used to display a measure of power disapated in a network. 

        See Also
        -----------
        passivity
        '''
        name = '' if self.name is None else self.name

        if port is None:
            ports = range(self.nports)
        else:
            ports = [port]
        for k in ports:
            if label_prefix==None:
                label = name +', port %i'%(k+1)
            else:
                label = label_prefix+', port %i'%(k+1)
            self.frequency.plot(mf.complex_2_db(self.passivity[:,k,k]),
                                label=label,
                                *args, **kwargs)

        plb.legend()
        plb.draw()

    def plot_reciprocity(self, db= False, *args, **kwargs):
        '''
        Plot reciprocity metric

        See Also
        -----------
        reciprocity
        '''
        for m in range(self.nports):
            for n in range(self.nports):
                if m>n:
                    if 'label'  not in kwargs.keys():
                        kwargs['label'] = 'ports %i%i'%(m,n)
                    y = self.reciprocity[:,m,n].flatten()
                    if db:
                        y = mf.complex_2_db(y)
                    self.frequency.plot(y,*args, **kwargs)

        plb.legend()
        plb.draw()

    def plot_reciprocity2(self, db= False, *args, **kwargs):
        '''
        Plot reciprocity metric #2

        this is distance of the determinant of the wave-cascading matrix
        from unity.

        .. math::

                abs(1 - S/S^T )



        See Also
        -----------
        reciprocity
        '''
        for m in range(self.nports):
            for n in range(self.nports):
                if m>n:
                    if 'label'  not in kwargs.keys():
                        kwargs['label'] = 'ports %i%i'%(m,n)
                    y = self.reciprocity2[:,m,n].flatten()
                    if db:
                        y = mf.complex_2_db(y)
                    self.frequency.plot(y,*args, **kwargs)

        plb.legend()
        plb.draw()
    ## CLASS METHODS
    def copy(self):
        '''
        Returns a copy of this Network

        Needed to allow pass-by-value for a Network instead of
        pass-by-reference
        '''
        ntwk = Network(s = self.s,
                       frequency = self.frequency.copy(),
                       z0 = self.z0,
                       )
        
        ntwk.name = self.name
        return ntwk

    def copy_from(self,other):
        '''
        Copies the contents of another Network into self

        Uses copy, so that the data is passed-by-value, not reference

        Parameters
        -----------
        other : Network
            the network to copy the contents of

        Examples
        -----------
        >>> a = rf.N()
        >>> b = rf.N('my_file.s2p')
        >>> a.copy_from (b)
        '''
        for attr in ['_s','frequency','_z0','name' ]:
            self.__setattr__(attr,copy(other.__getattribute__(attr)))


    # touchstone file IO
    def read_touchstone(self, filename):
        '''
        loads values from a touchstone file.

        The work of this function is done through the
        :class:`~skrf.io.touchstone` class.

        Parameters
        ----------
        filename : str or file-object
            touchstone file name.


        Notes
        ------
        only the scattering parameters format is supported at the
        moment



        '''
        from .io import touchstone
        touchstoneFile = touchstone.Touchstone(filename)

        if touchstoneFile.get_format().split()[1] != 's':
            raise NotImplementedError('only s-parameters supported for now.')

        self.comments = touchstoneFile.get_comments()

        # set z0 before s so that y and z can be computed
        self.z0 = complex(touchstoneFile.resistance)
        f, self.s = touchstoneFile.get_sparameter_arrays() # note: freq in Hz
        self.frequency = Frequency.from_f(f, unit='hz')
        self.frequency.unit = touchstoneFile.frequency_unit

        if self.name is None:
            try:
                self.name = os.path.basename( os.path.splitext(filename)[0])
                # this may not work if filename is a file object
            except(AttributeError):
                # in case they pass a file-object instead of file name,
                # get the name from the touchstone file
                try:
                    self.name = os.path.basename( os.path.splitext(touchstoneFile.filename)[0])
                except():
                    print('warning: couldnt inspect network name')
                    self.name=''
                pass
        #TODO: add Network property `comments` which is read from
        # touchstone file.

    def write_touchstone(self, filename=None, dir = None,
                         write_z0=False,skrf_comment=True):
        '''
        Write a contents of the :class:`Network` to a touchstone file.


        Parameters
        ----------
        filename : a string, optional
            touchstone filename, without extension. if 'None', then
            will use the network's :attr:`name`.
        dir : string, optional
            the directory to save the file in.
        write_z0 : boolean
            write impedance information into touchstone as comments,
            like Ansoft HFSS does
        skrf_comment : bool, optional
            write `created by skrf` comment


        Notes
        -------
        format supported at the moment is,
                HZ S RI

        The functionality of this function should take place in the
        :class:`~skrf.touchstone.touchstone` class.


        '''
        # according to Touchstone 2.0 spec
        # [no tab, max. 4 coeffs per line, etc.]

        if filename is None:
            if self.name is not None:
                filename= self.name
            else:
                raise ValueError('No filename given. Network must have a name, or you must provide a filename')


        if get_extn(filename) is None:
            filename = filename +'.s%ip'%self.number_of_ports

        if dir is not None:
            filename =  os.path.join(dir, filename)

        with open(filename,"w") as outputFile:
            # Add '!' Touchstone comment delimiters to the start of every line
            # in self.comments
            commented_header = ''
            if self.comments:
                for comment_line in self.comments.split('\n'):
                    commented_header += '!{}\n'.format(comment_line)
            if skrf_comment:
                commented_header +='!Created with skrf (http://scikit-rf.org).\n'

            outputFile.write(commented_header)

            # write header file.
            # the '#'  line is NOT a comment it is essential and it must be
            # exactly this format, to work
            # [HZ/KHZ/MHZ/GHZ] [S/Y/Z/G/H] [MA/DB/RI] [R n]

            outputFile.write('# ' + self.frequency.unit + ' S RI R ' + str(abs(self.z0[0,0])) +" \n")

            if self.number_of_ports == 1 :
                # write comment line for users (optional)
                outputFile.write('!freq ReS11 ImS11\n')
                # write out data
                for f in range(len(self.f)):
                    outputFile.write(str(self.frequency.f_scaled[f])+' '\
                        + str(npy.real(self.s[f,0,0])) + ' '\
                        + str(npy.imag(self.s[f,0,0])) +'\n')
                    # write out the z0 following hfss's convention if desired
                    if write_z0:
                        outputFile.write('! Port Impedance ' )
                        for n in range(self.number_of_ports):
                            outputFile.write('%.14f %.14f '%(self.z0[f,n].real, self.z0[f,n].imag))
                        outputFile.write('\n')

            elif self.number_of_ports == 2 :
                # 2-port is a special case with
                # - single line, and
                # - S21,S12 in reverse order: legacy ?

                # write comment line for users (optional)
                outputFile.write('!freq ReS11 ImS11 ReS21 ImS21 ReS12 ImS12 ReS22 ImS22\n')
                # write out data
                for f in range(len(self.f)):
                    outputFile.write(str(self.frequency.f_scaled[f])+' '\
                        + str(npy.real(self.s[f,0,0])) + ' '\
                        + str(npy.imag(self.s[f,0,0])) + ' '\
                        + str(npy.real(self.s[f,1,0])) + ' '\
                        + str(npy.imag(self.s[f,1,0])) + ' '\
                        + str(npy.real(self.s[f,0,1])) + ' '\
                        + str(npy.imag(self.s[f,0,1])) + ' '\
                        + str(npy.real(self.s[f,1,1])) + ' '\
                        + str(npy.imag(self.s[f,1,1])) +'\n')
                    # write out the z0 following hfss's convention if desired
                    if write_z0:
                        outputFile.write('! Port Impedance' )
                        for n in range(2):
                            outputFile.write(' %.14f %.14f'%(self.z0[f,n].real, self.z0[f,n].imag))
                        outputFile.write('\n')

            elif self.number_of_ports == 3 :
                # 3-port is written over 3 lines / matrix order

                # write comment line for users (optional)
                outputFile.write ('!freq')
                for m in range(1,4):
                    for n in range(1,4):
                        outputFile.write(" ReS{m}{n}  ImS{m}{n}".format(m=m, n=n))
                    outputFile.write('\n!')
                outputFile.write('\n')
                # write out data
                for f in range(len(self.f)):
                    outputFile.write(str(self.frequency.f_scaled[f]))
                    for m in range(3):
                        for n in range(3):
                            outputFile.write( ' ' + str(npy.real(self.s[f,m,n])) + ' '\
                             + str(npy.imag(self.s[f,m,n])))
                        outputFile.write('\n')
                    # write out the z0 following hfss's convention if desired
                    if write_z0:
                        outputFile.write('! Port Impedance' )
                        for n in range(3):
                            outputFile.write(' %.14f %.14f'%(self.z0[f,n].real, self.z0[f,n].imag))
                        outputFile.write('\n')

            elif self.number_of_ports >= 4 :
                # general n-port
                # - matrix is written line by line
                # - 4 complex numbers / 8 real numbers max. for a single line
                # - continuation lines (anything except first) go with indent
                #   this is not part of the spec, but many tools handle it this way
                #   -> allows to parse without knowledge of number of ports

                # write comment line for users (optional)
                outputFile.write ('!freq')
                for m in range(1,1+self.number_of_ports):
                    for n in range(1,1+self.number_of_ports):
                        if (n > 0 and (n%4) == 0 ) :
                            outputFile.write('\n!')
                            outputFile.write(" ReS{m}{n}  ImS{m}{n}".format(m=m, n=n))
                    outputFile.write('\n!')
                outputFile.write('\n')
                # write out data
                for f in range(len(self.f)):
                    outputFile.write(str(self.frequency.f_scaled[f]))
                    for m in range(self.number_of_ports):
                        for n in range(self.number_of_ports):
                            if (n > 0 and (n%4) == 0 ) :
                                outputFile.write('\n')
                            outputFile.write( ' ' + str(npy.real(self.s[f,m,n])) + ' '\
                             + str(npy.imag(self.s[f,m,n])))
                        outputFile.write('\n')

                    # write out the z0 following hfss's convention if desired
                    if write_z0:
                        outputFile.write('! Port Impedance' )
                        for n in range(self.number_of_ports):
                            outputFile.write(' %.14f %.14f'%(self.z0[f,n].real, self.z0[f,n].imag))
                        outputFile.write('\n')


    def write(self, file=None, *args, **kwargs):
        '''
        Write the Network to disk using the :mod:`pickle` module.

        The resultant file can be read either by using the Networks
        constructor, :func:`__init__` , the read method :func:`read`, or
        the general read function :func:`skrf.io.general.read`


        Parameters
        -----------
        file : str or file-object
            filename or a file-object. If left as None then the
            filename will be set to Network.name, if its not None.
            If both are None, ValueError is raised.
        \*args, \*\*kwargs :
            passed through to :func:`~skrf.io.general.write`

        Notes
        ------
        If the self.name is not None and file is  can left as None
        and the resultant file will have the `.ntwk` extension appended
        to the filename.

        Examples
        ---------
        >>> n = rf.N(f=[1,2,3],s=[1,1,1],z0=50, name = 'open')
        >>> n.write()
        >>> n2 = rf.read('open.ntwk')

        See Also
        ---------
        skrf.io.general.write : write any skrf object
        skrf.io.general.read : read any skrf object
        '''
        # this import is delayed until here because of a circular depency
        from io.general import write

        if file is None:
            if self.name is None:
                 raise (ValueError('No filename given. You must provide a filename, or set the name attribute'))
            file = self.name

        write(file,self,*args, **kwargs)

    def read(self, *args, **kwargs):
        '''
        Read a Network from a 'ntwk' file

        A ntwk file is written with :func:`write`. It is just a pickled
        file.

        Parameters
        -------------
        \*args, \*\*kwargs : args and kwargs
            passed to :func:`skrf.io.general.write`

        Notes
        ------
        This function calls :func:`skrf.io.general.read`.

        Examples
        -----------
        >>> rf.read('myfile.ntwk')
        >>> rf.read('myfile.p')

        See Also
        ----------
        write
        skrf.io.general.write
        skrf.io.general.read
        '''
        from .io.general import read
        self.copy_from(read(*args, **kwargs))

    def write_spreadsheet(self, *args, **kwargs):
        '''
        Write contents of network to a spreadsheet, for your boss to use.

        See Also
        ---------
        skrf.io.general.network_2_spreadsheet
        '''
        from .io.general import network_2_spreadsheet
        network_2_spreadsheet(self, *args, **kwargs)

    def to_dataframe(self, *args, **kwargs):
        '''
        Convert attributes of a Network to a pandas DataFrame

        See Also
        ---------
        skrf.io.general.network_2_dataframe
        '''
        from .io.general import network_2_dataframe
        return network_2_dataframe(self, *args, **kwargs)

    # interpolation
    def interpolate(self, new_frequency,**kwargs):
        '''
        Return an interpolated network, from a new :class:'~skrf.frequency.Frequency'.

        Interpolate the networks s-parameters linearly in real and
        imaginary components. Other interpolation types can be used
        by passing appropriate `\*\*kwargs`. This function `returns` an
        interpolated Network. Alternatively :func:`~Network.interpolate_self`
        will interpolate self.


        Parameters
        -----------
        new_frequency : :class:`~skrf.frequency.Frequency`
            frequency information to interpolate
        **kwargs : keyword arguments
            passed to :func:`scipy.interpolate.interp1d` initializer.

        Returns
        ----------
        result : :class:`Network`
                an interpolated Network

        Notes
        --------
        See  :func:`scipy.interpolate.interpolate.interp1d` for useful
        kwargs. For example
            **kind** : str or int
                Specifies the kind of interpolation as a string ('linear',
                'nearest', 'zero', 'slinear', 'quadratic, 'cubic') or
                as an integer specifying the order of the spline
                interpolator to use.

        See Also
        ----------
        resample
        interpolate_self
        interpolate_from_f

        Examples
        -----------
        .. ipython::

            @suppress
            In [21]: import skrf as rf

            In [21]: n = rf.data.ring_slot

            In [21]: n

            In [21]: new_freq = rf.Frequency(75,110,501,'ghz')

            In [21]: n.interpolate(new_freq, kind = 'cubic')

        '''
        # create interpolation objects
        interpolation_s_re = \
            interp1d(self.frequency.f,self.s_re,axis=0,**kwargs)
        interpolation_s_im = \
            interp1d(self.frequency.f,self.s_im,axis=0,**kwargs)
        interpolation_z0_re = \
            interp1d(self.frequency.f,self.z0.real,axis=0,**kwargs)
        interpolation_z0_im = \
            interp1d(self.frequency.f,self.z0.imag,axis=0,**kwargs)

        # make new network and fill with interpolated s, and z0
        result = self.copy()
        result.frequency = new_frequency
        result.s = interpolation_s_re(new_frequency.f) +\
            1j*interpolation_s_im(new_frequency.f)
        result.z0 = interpolation_z0_re(new_frequency.f) +\
            1j*interpolation_z0_im(new_frequency.f)

        return result

    def interpolate_self_npoints(self, npoints, **kwargs):
        '''

        Interpolate network based on a new number of frequency points


        Parameters
        -----------
        npoints : int
                number of frequency points
        **kwargs : keyword arguments
                passed to :func:`scipy.interpolate.interp1d` initializer.

        See Also
        ---------
        interpolate_self : same functionality but takes a Frequency
                object
        interpolate : same functionality but takes a Frequency
                object and returns a new Network, instead of updating
                itself.

        Notes
        -------
        The function :func:`~Network.resample` is an alias for
        :func:`~Network.interpolate_self_npoints`.

        Examples
        -----------
        .. ipython::

            @suppress
            In [21]: import skrf as rf

            In [21]: n = rf.data.ring_slot

            In [21]: n

            In [21]: n.resample(501) # resample is an alias

            In [21]: n

        '''
        new_frequency = self.frequency.copy()
        new_frequency.npoints = npoints
        self.interpolate_self(new_frequency, **kwargs)

    ##convenience
    resample = interpolate_self_npoints

    def interpolate_self(self, new_frequency, **kwargs):
        '''
        Interpolates s-parameters given a new

        :class:'~skrf.frequency.Frequency' object.

        See :func:`~Network.interpolate` for more information.

        Parameters
        -----------
        new_frequency : :class:`~skrf.frequency.Frequency`
                frequency information to interpolate at
        **kwargs : keyword arguments
                passed to :func:`scipy.interpolate.interp1d` initializer.

        See Also
        ----------
        resample
        interpolate
        interpolate_from_f
        '''
        ntwk = self.interpolate(new_frequency, **kwargs)
        self.frequency, self.s,self.z0 = ntwk.frequency, ntwk.s,ntwk.z0

    def interpolate_from_f(self, f, interp_kwargs={}, **kwargs):
        '''
        Interpolates s-parameters from a frequency vector.

        Given a frequency vector, and optionally a `unit` (see \*\*kwargs)
        , interpolate the networks s-parameters linearly in real and
        imaginary components.

        See :func:`~Network.interpolate` for more information.




        Parameters
        -----------
        new_frequency : :class:`~skrf.frequency.Frequency`
            frequency information to interpolate at
        interp_kwargs :
            dictionary of kwargs to be passed through to
            :func:`scipy.interpolate.interpolate.interp1d`
        \*\*kwargs :
            passed to :func:`scipy.interpolate.interp1d` initializer.

        Notes
        ---------
        This creates a new :class:`~skrf.frequency.Frequency`, object
        using the method :func:`~skrf.frequency.Frequency.from_f`, and then calls
        :func:`~Network.interpolate_self`.

        See Also
        ----------
        resample
        interpolate
        interpolate_self


        '''
        freq = Frequency.from_f(f,**kwargs)
        self.interpolate_self(freq, **interp_kwargs)

    def crop(self, f_start, f_stop):
        '''
        Crop Network based on start and stop frequencies.

        No interpolation is done.


        Parameters
        -----------
        f_start : number
            start frequency of crop range, in units of self.frequency.unit
        f_stop : number
            stop frequency of crop range, in units of self.frequency.unit


        '''
        if f_start < self.frequency.f_scaled.min():
            raise ValueError('`f_start` is out of range.')
        elif f_stop > self.frequency.f_scaled.max():
            raise ValueError('`f_stop` is out of range.')

        start_idx = find_nearest_index(self.frequency.f_scaled,f_start)
        stop_idx = find_nearest_index(self.frequency.f_scaled,f_stop)

        ntwk = self[start_idx:stop_idx+1]
        self.frequency, self.s,self.z0 = ntwk.frequency, ntwk.s,ntwk.z0

    def cropped(self, f_start, f_stop):
        '''
        returns a cropped network, leaves self alone.

        See Also
        ---------
        crop
        '''
        out = self.copy()
        out.crop(f_start = f_start, f_stop = f_stop)
        return out

    def flip(self):
        '''
        swaps the ports of a two port Network
        '''
        if self.number_of_ports == 2:
            self.renumber( [0,1], [1,0] )
        else:
            raise ValueError('you can only flip two-port Networks')

    def flipped(self):
        '''
        returns a flipped network, leaves self alone.

        See Also
        ---------
        flip
        '''
        out = self.copy()
        out.flip()
        return out

    def renormalize(self, z_new, powerwave=False):
        '''
        Renormalize s-parameter matrix given a new port impedances


        Parameters
        ---------------
        z_new : complex array of shape FxN, F, N or a  scalar
            new port impedances

        powerwave : bool
            if true this calls :func:`renormalize_s_pw`, which assumes
            a powerwave formulation. Otherwise it calls
            :func:`renormalize_s` which implements the default psuedowave
            formuation. If z_new or self.z0 is complex, then these
            produce different results.

        See Also
        ----------
        renormalize_s
        renormalize_s_pw
        fix_z0_shape
        '''
        if powerwave:
            self.s = renormalize_s_pw(self.s, self.z0, z_new)
        else:
            self.s = renormalize_s(self.s, self.z0, z_new)
        self.z0 = fix_z0_shape(z_new,self.frequency.npoints, self.nports)

    def renumber(self, from_ports, to_ports):
        '''
        renumbers  ports of a  Network

        Parameters
        -----------
        from_ports : list-like
        to_ports: list-like

        Examples
        ---------
        To flip the ports of a 2-port network 'foo':
        >>> foo.renumber( [0,1], [1,0] )

        To rotate the ports of a 3-port network 'bar' so that port 0 becomes port 1:
        >>> bar.renumber( [0,1,2], [1,2,0] )

        To swap the first and last ports of a network 'duck':
        >>> duck.renumber( [0,-1], [-1,0] )
        '''
        from_ports = npy.array(from_ports)
        to_ports = npy.array(to_ports)
        if len(npy.unique(from_ports)) != len(from_ports):
            raise ValueError('an index can appear at most once in from_ports or to_ports')
        if any(npy.unique(from_ports) != npy.unique(to_ports)):
            raise ValueError('from_ports and to_ports must have the same set of indices')

        self.s[:,to_ports,:] = self.s[:,from_ports,:]  # renumber rows
        self.s[:,:,to_ports] = self.s[:,:,from_ports]  # renumber columns
        self.z0[:,to_ports] = self.z0[:,from_ports]

    def windowed(self, window=('kaiser',6),  normalize = True):
        '''
        Return a windowed version of s-matrix. Used in time-domain analysis.

        When using time domain through :attr:`s_time_db`,
        or similar properies, the spectrum is usually windowed,
        before the IFFT is taken. This is done to
        compensate for the band-pass nature of a spectrum [1]_ .

        This function calls :func:`scipy.signal.get_window` which gives
        more details about the windowing.

        Parameters
        -----------
        window : string, float, or tuple
            The type of window to create. See :func:`scipy.signal.get_window`
            for details.
        normalize : bool
            Normalize the window to preserve power. ie
            sum(ntwk.s,axis=0) == sum(ntwk.windowed().s,axis=0)

        Examples
        -----------
        >>> ntwk = rf.Network('myfile.s2p')
        >>> ntwk_w = ntwk.windowed()
        >>> ntwk_w.plot_s_time_db()

        References
        -------------
        .. [1] Agilent Time Domain Analysis Using a Network Analyzer Application Note 1287-12

        '''
        window = signal.get_window(window, len(self))
        window =window.reshape(-1,1,1) * npy.ones((len(self),
                                                   self.nports,
                                                   self.nports))
        windowed = self * window
        if normalize:
            # normalize the s-parameters to account for power lost in windowing
            windowed.s = windowed.s * npy.sum(self.s_mag,axis=0)/\
                npy.sum(windowed.s_mag,axis=0)

        return windowed

    def time_gate(self, t_start, t_stop, window = ('kaiser',6)):
        '''
        Time-gate s-parameters

        See Warning!

        Parameters
        ------------
        t_start : number
            start of time gate, (s)
        t_stop : number
            stop of time gate (s)

        Returns
        --------
        ntwk : Network
            copy of self with time-gated s-parameters

        .. warning::
            This is not fully tested, and doesnt appear to be preserve power
            correctly


        '''
        gated = self.copy()

        t_2_f = lambda x:fft.fft(x, axis=0)

        t = self.frequency.t
        t_start_idx = find_nearest_index(t,t_start)
        t_stop_idx = find_nearest_index(t,t_stop)

        window_width = abs(t_stop_idx-t_start_idx)
        window = signal.get_window(window, window_width)

        padded_window = npy.r_[npy.zeros(t_start_idx),
                               window,
                               npy.zeros(len(t)-t_stop_idx)]
        padded_window = padded_window.reshape(-1,1,1) *\
                        npy.ones((len(gated), gated.nports, gated.nports))
        window_in_f = t_2_f(padded_window)
    
        #window_in_freq = window_in_freq.reshape(-1,1,1) * \
        #                npy.ones((len(self), self.nports, self.nports))

        '''
        for m,n in self.port_tuples:
            x = signal.convolve(self.s[:,m,n], window_in_f, mode='same')
            gated.s[:,m,n] = fft.ifftshift(x)

        #normalize output
        gated.s = gated.s  * npy.sum(self.s_mag,axis=0)/\
                npy.sum(gated.s_mag,axis=0)

        '''
        s_time_windowed = gated.s_time*padded_window
        gated.s = t_2_f(s_time_windowed)
        return gated

    # plotting
    def plot_s_smith(self,m=None, n=None,r=1,ax = None, show_legend=True,\
            chart_type='z', draw_labels=False, label_axes=False, *args,**kwargs):
        '''
        plots the scattering parameter on a smith chart

        plots indices `m`, `n`, where `m` and `n` can be integers or
        lists of integers.


        Parameters
        -----------
        m : int, optional
                first index
        n : int, optional
                second index
        ax : matplotlib.Axes object, optional
                axes to plot on. in case you want to update an existing
                plot.
        show_legend : boolean, optional
                to turn legend show legend of not, optional
        chart_type : ['z','y']
            draw impedance or addmitance contours
        draw_labels : Boolean
            annotate chart with impedance values
        label_axes : Boolean
            Label axis with titles `Real` and `Imaginary`
        border : Boolean
            draw rectangular border around image with ticks

        \*args : arguments, optional
                passed to the matplotlib.plot command
        \*\*kwargs : keyword arguments, optional
                passed to the matplotlib.plot command


        See Also
        --------
        plot_vs_frequency_generic - generic plotting function
        smith -  draws a smith chart

        Examples
        ---------
        >>> myntwk.plot_s_smith()
        >>> myntwk.plot_s_smith(m=0,n=1,color='b', marker='x')
        '''
        # TODO: prevent this from re-drawing smith chart if one alread
        # exists on current set of axes

        # get current axis if user doesnt supply and axis
        if ax is None:
            ax = plb.gca()


        if m is None:
            M = range(self.number_of_ports)
        else:
            M = [m]
        if n is None:
            N = range(self.number_of_ports)
        else:
            N = [n]

        if 'label'  not in kwargs.keys():
            generate_label=True
        else:
            generate_label=False

        for m in M:
            for n in N:
                # set the legend label for this trace to the networks name if it
                # exists, and they didnt pass a name key in the kwargs
                if generate_label:
                    if self.name is None:
                        if plb.rcParams['text.usetex']:
                            label_string = '$S_{'+repr(m+1) + repr(n+1)+'}$'
                        else:
                            label_string = 'S'+repr(m+1) + repr(n+1)
                    else:
                        if plb.rcParams['text.usetex']:
                            label_string = self.name+', $S_{'+repr(m+1) + \
                                    repr(n+1)+'}$'
                        else:
                            label_string = self.name+', S'+repr(m+1) + repr(n+1)

                    kwargs['label'] = label_string

                # plot the desired attribute vs frequency
                if len (ax.patches) == 0:
                    smith(ax=ax, smithR = r, chart_type=chart_type, draw_labels=draw_labels)
                ax.plot(self.s[:,m,n].real,  self.s[:,m,n].imag, *args,**kwargs)

        #draw legend
        if show_legend:
            ax.legend()
        ax.axis(npy.array([-1.1,1.1,-1.1,1.1])*r)

        if label_axes:
            ax.set_xlabel('Real')
            ax.set_ylabel('Imaginary')


    def plot_it_all(self,*args, **kwargs):
        '''
        Plots dB, deg, smith, and complex in subplots

        Plots the magnitude in dB in subplot 1, the phase in degrees in
        subplot 2, a smith chart in subplot 3, and a complex plot in
        subplot 4.

        Parameters
        -----------
        \*args : arguments, optional
                passed to the matplotlib.plot command
        \*\*kwargs : keyword arguments, optional
                passed to the matplotlib.plot command

        See Also
        --------
        plot_s_db - plot magnitude (in dB) of s-parameters vs frequency
        plot_s_deg - plot phase of s-parameters (in degrees) vs frequency
        plot_s_smith - plot complex s-parameters on smith chart
        plot_s_complex - plot complex s-parameters in the complex plane

        Examples
        ---------
        >>> from skrf.data import ring_slot
        >>> ring_slot.plot_it_all()
        '''
        plb.subplot(221)
        getattr(self,'plot_s_db')(*args, **kwargs)
        plb.subplot(222)
        getattr(self,'plot_s_deg')(*args, **kwargs)
        plb.subplot(223)
        getattr(self,'plot_s_smith')(*args, **kwargs)
        plb.subplot(224)
        getattr(self,'plot_s_complex')(*args, **kwargs)

    # noise
    def add_noise_polar(self,mag_dev, phase_dev,**kwargs):
        '''
        adds a complex zero-mean gaussian white-noise.

        adds a complex zero-mean gaussian white-noise of a given
        standard deviation for magnitude and phase

        Parameters
        ------------
        mag_dev : number
                standard deviation of magnitude
        phase_dev : number
                standard deviation of phase [in degrees]

        '''

        phase_rv= stats.norm(loc=0, scale=phase_dev).rvs(size = self.s.shape)
        mag_rv = stats.norm(loc=0, scale=mag_dev).rvs(size = self.s.shape)

        phase = (self.s_deg+phase_rv)
        mag = self.s_mag + mag_rv
        self.s = mag* npy.exp(1j*npy.pi/180.*phase)

    def add_noise_polar_flatband(self,mag_dev, phase_dev,**kwargs):
        '''
        adds a flatband complex zero-mean gaussian white-noise signal of
        given standard deviations for magnitude and phase

        Parameters
        ------------
        mag_dev : number
                standard deviation of magnitude
        phase_dev : number
                standard deviation of phase [in degrees]

        '''
        phase_rv= stats.norm(loc=0, scale=phase_dev).rvs(size = self.s[0].shape)
        mag_rv = stats.norm(loc=0, scale=mag_dev).rvs(size = self.s[0].shape)

        phase = (self.s_deg+phase_rv)
        mag = self.s_mag + mag_rv
        self.s = mag* npy.exp(1j*npy.pi/180.*phase)

    def multiply_noise(self,mag_dev, phase_dev, **kwargs):
        '''
        multiplys a complex bivariate gaussian white-noise signal
        of given standard deviations for magnitude and phase.
        magnitude mean is 1, phase mean is 0

        takes:
                mag_dev: standard deviation of magnitude
                phase_dev: standard deviation of phase [in degrees]
                n_ports: number of ports. defualt to 1
        returns:
                nothing
        '''
        phase_rv = stats.norm(loc=0, scale=phase_dev).rvs(\
                size = self.s.shape)
        mag_rv = stats.norm(loc=1, scale=mag_dev).rvs(\
                size = self.s.shape)
        self.s = mag_rv*npy.exp(1j*npy.pi/180.*phase_rv)*self.s

    def nudge(self, amount=1e-12):
        '''
        Perturb s-parameters by small amount.

        This is useful to work-around numerical bugs.

        Notes
        -----------
        This function is
            self.s = self.s + 1e-12

        Parameters
        ------------
        amount : number,
                amount to add to s parameters

        '''
        self.s = self.s + amount

    # other
    def func_on_parameter(self, func, attr= 's',*args, **kwargs):
        '''
        Applies a function parameter matrix, one frequency slice at a time

        This is useful for functions that can only operate on 2d arrays,
        like numpy.linalg.inv. This loops over f and calls
        `func(ntwkA.s[f,:,:], *args, **kwargs)`

        Parameters
        ------------

        func : func
            function to apply to s-parameters, on a single-freqency slice.
            (ie func(ntwkA.s[0,:,:], *args, **kwargs)
        \*args, \*\*kwargs :
            passed to the func


        Examples
        -----------
        >>> from numpy.linalg import inv
        >>> ntwk.func_on_parameter(inv)
        '''
        ntwkB= self.copy()
        p = self.__getattribute__(attr)
        ntwkB.s = npy.r_[[func(p[k,:,:],*args,**kwargs) \
            for k in range(len(p))]]
        return ntwkB

    def nonreciprocity(self,m,n, normalize = False):
        '''
        Normalized non-reciprocity metric.

        This is a port-by-port measure of how non-reciprocal a n-port
        network is. It is defined by,

        .. math::

            (S_{mn} - S_{nm}) / \\sqrt ( S_{mn} S_{nm} )




        '''
        forward = self.__getattribute__('s%i%i'%(m,n))
        reverse = self.__getattribute__('s%i%i'%(n,m))
        if normalize:
            denom = forward*reverse
            denom.s = npy.sqrt(denom.s)
            return (forward-reverse)/denom
        else:
            return (forward-reverse)

## Functions operating on Network[s]
def connect(ntwkA, k, ntwkB, l, num=1):
    '''
    connect two n-port networks together.

    specifically, connect ports `k` thru `k+num-1` on `ntwkA` to ports
    `l` thru `l+num-1` on `ntwkB`. The resultant network has
    (ntwkA.nports+ntwkB.nports-2*num) ports. The port indices ('k','l')
    start from 0. Port impedances **are** taken into account.

    Parameters
    -----------
    ntwkA : :class:`Network`
            network 'A'
    k : int
            starting port index on `ntwkA` ( port indices start from 0 )
    ntwkB : :class:`Network`
            network 'B'
    l : int
            starting port index on `ntwkB`
    num : int
            number of consecutive ports to connect (default 1)


    Returns
    ---------
    ntwkC : :class:`Network`
            new network of rank (ntwkA.nports + ntwkB.nports - 2*num)


    See Also
    -----------
            connect_s : actual  S-parameter connection algorithm.
            innerconnect_s : actual S-parameter connection algorithm.

    Notes
    -------
            the effect of mis-matched port impedances is handled by inserting
            a 2-port 'mismatch' network between the two connected ports.
            This mismatch Network is calculated with the
            :func:`impedance_mismatch` function.

    Examples
    ---------
    To implement a *cascade* of two networks

    >>> ntwkA = rf.Network('ntwkA.s2p')
    >>> ntwkB = rf.Network('ntwkB.s2p')
    >>> ntwkC = rf.connect(ntwkA, 1, ntwkB,0)

    '''
    # some checking
    check_frequency_equal(ntwkA,ntwkB)

    if (k+num-1> ntwkA.nports-1):
        raise IndexError('Port `k` out of range')
    if (l+num-1> ntwkB.nports-1):
        raise IndexError('Port `l` out of range')

    # create output Network, from copy of input
    ntwkC = ntwkA.copy()

    # if networks' z0's are not identical, then connect a impedance
    # mismatch, which takes into account the effect of differing port
    # impedances.
    #import pdb;pdb.set_trace()
    if assert_z0_at_ports_equal(ntwkA,k,ntwkB,l) == False:
        ntwkC.s = connect_s(
            ntwkA.s, k,
            impedance_mismatch(ntwkA.z0[:,k], ntwkB.z0[:,l]), 0)
        # the connect_s() put the mismatch's output port at the end of
        #   ntwkC's ports.  Fix the new port's impedance, then insert it
        #   at position k where it belongs.
        ntwkC.z0[:,k:] = npy.hstack((ntwkC.z0[:,k+1:], ntwkB.z0[:,[l]]))
        ntwkC.renumber(from_ports= [ntwkC.nports-1] + list(range(k, ntwkC.nports-1)),
                       to_ports=list(range(k, ntwkC.nports)))

    # call s-matrix connection function
    ntwkC.s = connect_s(ntwkC.s,k,ntwkB.s,l)

    # combine z0 arrays and remove ports which were `connected`
    ntwkC.z0 = npy.hstack(
        (npy.delete(ntwkA.z0, range(k,k+1), 1), npy.delete(ntwkB.z0, range(l,l+1), 1)))

    # if we're connecting more than one port, call innerconnect recursively
    # untill all connections are made to finish the job
    if num>1:
        ntwkC = innerconnect(ntwkC, k, ntwkA.nports-1+l, num-1)

    # if ntwkB is a 2port, then keep port indices where you expect.
    if ntwkB.nports == 2 and ntwkA.nports>2:
        from_ports = list(range(ntwkC.nports))
        to_ports = list(range(ntwkC.nports))
        to_ports.pop(k);
        to_ports.append(k)

        ntwkC.renumber(from_ports=from_ports,
                       to_ports=to_ports)

    return ntwkC

def connect_fast(ntwkA, k, ntwkB, l):
    '''
    Connect two n-port networks together (using C-implementation)

    Specifically, connect ports `k` on `ntwkA` to ports
    `l` thru  on `ntwkB`. The resultant network has
    (ntwkA.nports+ntwkB.nports-2) ports. The port indices ('k','l')
    start from 0. Port impedances **are** taken into account.

    Parameters
    -----------
    ntwkA : :class:`Network`
            network 'A'
    k : int
            starting port index on `ntwkA` ( port indices start from 0 )
    ntwkB : :class:`Network`
            network 'B'
    l : int
            starting port index on `ntwkB`


    Returns
    ---------
    ntwkC : :class:`Network`
            new network of rank (ntwkA.nports + ntwkB.nports - 2)


    See Also
    -----------
        :mod:`skrf.src`

    Notes
    -------
            the effect of mis-matched port impedances is handled by inserting
            a 2-port 'mismatch' network between the two connected ports.
            This mismatch Network is calculated with the
            :func:`impedance_mismatch` function.

    Examples
    ---------
    To implement a *cascade* of two networks

    >>> ntwkA = rf.Network('ntwkA.s2p')
    >>> ntwkB = rf.Network('ntwkB.s2p')
    >>> ntwkC = rf.connect(ntwkA, 1, ntwkB,0)

    '''
    num = 1
    from src import connect_s_fast

    # some checking
    check_frequency_equal(ntwkA,ntwkB)

    # create output Network, from copy of input
    ntwkC = ntwkA.copy()

    # if networks' z0's are not identical, then connect a impedance
    # mismatch, which takes into account the effect of differing port
    # impedances.

    if assert_z0_at_ports_equal(ntwkA,k,ntwkB,l) == False:
        ntwkC.s = connect_s(
            ntwkA.s, k,
            impedance_mismatch(ntwkA.z0[:,k], ntwkB.z0[:,l]), 0)
        # the connect_s() put the mismatch's output port at the end of
        #   ntwkC's ports.  Fix the new port's impedance, then insert it
        #   at position k where it belongs.
        ntwkC.z0[:,k:] = npy.hstack((ntwkC.z0[:,k+1:], ntwkB.z0[:,[l]]))
        ntwkC.renumber(from_ports= [ntwkC.nports-1] + range(k, ntwkC.nports-1),
                       to_ports=range(k, ntwkC.nports))

    # call s-matrix connection function
    ntwkC.s = connect_s_fast(ntwkC.s,k,ntwkB.s,l)

    # combine z0 arrays and remove ports which were `connected`
    ntwkC.z0 = npy.hstack(
        (npy.delete(ntwkA.z0, range(k,k+num), 1), npy.delete(ntwkB.z0, range(l,l+num), 1)))


    return ntwkC

def innerconnect(ntwkA, k, l, num=1):
    '''
    connect ports of a single n-port network.

    this results in a (n-2)-port network. remember port indices start
    from 0.

    Parameters
    -----------
    ntwkA : :class:`Network`
        network 'A'
    k,l : int
        starting port indices on ntwkA ( port indices start from 0 )
    num : int
        number of consecutive ports to connect

    Returns
    ---------
    ntwkC : :class:`Network`
        new network of rank (ntwkA.nports - 2*num)

    See Also
    -----------
        connect_s : actual  S-parameter connection algorithm.
        innerconnect_s : actual S-parameter connection algorithm.

    Notes
    -------
        a 2-port 'mismatch' network is inserted between the connected ports
        if their impedances are not equal.

    Examples
    ---------
    To connect ports '0' and port '1' on ntwkA

    >>> ntwkA = rf.Network('ntwkA.s3p')
    >>> ntwkC = rf.innerconnect(ntwkA, 0,1)

    '''
    
    if (k+num-1> ntwkA.nports-1):
        raise IndexError('Port `k` out of range')
    if (l+num-1> ntwkA.nports-1):
        raise IndexError('Port `l` out of range')
        
        
    # create output Network, from copy of input
    ntwkC = ntwkA.copy()

    
    if not (ntwkA.z0[:,k] == ntwkA.z0[:,l]).all():
        # connect a impedance mismatch, which will takes into account the
        # effect of differing port impedances
        mismatch = impedance_mismatch(ntwkA.z0[:,k], ntwkA.z0[:,l])
        ntwkC.s = connect_s( ntwkA.s,k, mismatch, 0)
        #print 'mismatch %i-%i'%(k,l)
        # the connect_s() put the mismatch's output port at the end of
        #   ntwkC's ports.  Fix the new port's impedance, then insert it
        #   at position k where it belongs.
        ntwkC.z0[:,k:] = npy.hstack((ntwkC.z0[:,k+1:], ntwkC.z0[:,[l]]))
        ntwkC.renumber(from_ports= [ntwkC.nports-1] + list(range(k, ntwkC.nports-1)),
                       to_ports=list(range(k, ntwkC.nports)))

    # call s-matrix connection function
    ntwkC.s = innerconnect_s(ntwkC.s,k,l)

    # update the characteristic impedance matrix
    ntwkC.z0 = npy.delete(ntwkC.z0, list(range(k,k+1)) + list(range(l,l+1)),1)

    # recur if we're connecting more than one port
    if num>1:
        ntwkC = innerconnect(ntwkC, k, l-1, num-1)

    return ntwkC

def cascade(ntwkA,ntwkB):
    '''
    Cascade two 2-port Networks together

    Connects port 1 of `ntwkA` to port 0 of `ntwkB`. This calls
    `connect(ntwkA,1, ntwkB,0)`, which is a more general function.

    Parameters
    -----------
    ntwkA : :class:`Network`
            network `ntwkA`
    ntwkB : Network
            network `ntwkB`

    Returns
    --------
    C : Network
            the resultant network of ntwkA cascaded with ntwkB

    See Also
    ---------
    connect : connects two Networks together at arbitrary ports.
    '''
    return connect(ntwkA,1, ntwkB,0)

def cascade_list(l):
    '''
    cascade a list of 2-port networks
    
    all networks must have same frequency
    
    Parameters
    --------------
    l : list-like
        (ordered) list of networks 
    
    Returns
    ----------
    out : 2-port Network
        the results of casacading all networks in the list `l`
        
    '''
    return reduce(cascade, l)

def de_embed(ntwkA,ntwkB):
    '''
    De-embed `ntwkA` from `ntwkB`.

    This calls `ntwkA.inv ** ntwkB`. The syntax of cascading an inverse
    is more explicit, it is recomended that it be used instead of this
    function.

    Parameters
    -----------
    ntwkA : :class:`Network`
            network `ntwkA`
    ntwkB : :class:`Network`
            network `ntwkB`

    Returns
    --------
    C : Network
            the resultant network of ntwkB de-embeded from ntwkA

    See Also
    ---------
    connect : connects two Networks together at arbitrary ports.

    '''
    return ntwkA.inv ** ntwkB

def stitch(ntwkA, ntwkB, **kwargs):
    '''
    Stitches ntwkA and ntwkB together.

    Concatenates two networks' data. Given two networks that cover
    different frequency bands this can be used to combine their data
    into a single network.

    Parameters
    ------------
    ntwkA, ntwkB : :class:`Network` objects
        Networks to stitch together

    \*\*kwargs : keyword args
        passed to :class:`Network` constructor, for output network

    Returns
    ---------
    ntwkC : :class:`Network`
        result of stitching the networks `ntwkA` and `ntwkB` together

    Examples
    ----------
    >>> from skrf.data import wr2p2_line, wr1p5_line
    >>> rf.stitch(wr2p2_line, wr1p5_line)
    2-Port Network: 'wr2p2,line',  330-750 GHz, 402 pts, z0=[ 50.+0.j  50.+0.j]
    '''

    A,B = ntwkA, ntwkB
    C = Network(
        frequency = Frequency.from_f(npy.r_[A.f[:],B.f[:]], unit='hz'),
        s = npy.r_[A.s,B.s],
        z0 = npy.r_[A.z0, B.z0],
        name = A.name,
        **kwargs
        )
    C.frequency.unit = A.frequency.unit
    return C

def overlap(ntwkA, ntwkB):
    '''
    Returns the overlapping parts of two Networks, interpolating if needed.

    If frequency vectors for each ntwk dont perfectly overlap, then
    ntwkB is interpolated so that the resultant networks have identical
    frequencies.

    Parameters
    ------------
    ntwkA : :class:`Network`
        a ntwk which overlaps `ntwkB`. (the `dominant` network)
    ntwkB : :class:`Network`
        a ntwk which overlaps `ntwkA`.

    Returns
    -----------
    ntwkA_new : :class:`Network`
        part of `ntwkA` that overlapped `ntwkB`
    ntwkB_new : :class:`Network`
        part of `ntwkB` that overlapped `ntwkA`, possibly interpolated


    See Also
    ------------

    :func:`skrf.frequency.overlap_freq`

    '''

    new_freq = ntwkA.frequency.overlap(ntwkB.frequency)
    return ntwkA.interpolate(new_freq),ntwkB.interpolate(new_freq)


def average(list_of_networks, polar = False):
    '''
    Calculates the average network from a list of Networks.

    This is complex average of the s-parameters for a  list of Networks.


    Parameters
    -----------
    list_of_networks : list of :class:`Network` objects
        the list of networks to average

    Returns
    ---------
    ntwk : :class:`Network`
            the resultant averaged Network

    Notes
    ------
    This same function can be accomplished with properties of a
    :class:`~skrf.networkset.NetworkSet` class.

    Examples
    ---------

    >>> ntwk_list = [rf.Network('myntwk.s1p'), rf.Network('myntwk2.s1p')]
    >>> mean_ntwk = rf.average(ntwk_list)
    '''
    out_ntwk = list_of_networks[0].copy()

    if polar:
        # average the mag/phase components individually
        raise NotImplementedError
    else:
        # average the re/im components individually
        for a_ntwk in list_of_networks[1:]:
            out_ntwk += a_ntwk

        out_ntwk.s = out_ntwk.s/(len(list_of_networks))

    return out_ntwk

def one_port_2_two_port(ntwk):
    '''
    calculates the two-port network given a symmetric, reciprocal and
    lossless one-port network.

    takes:
            ntwk: a symmetric, reciprocal and lossless one-port network.
    returns:
            ntwk: the resultant two-port Network
    '''
    result = ntwk.copy()
    result.s = npy.zeros((result.frequency.npoints,2,2), dtype=complex)
    s11 = ntwk.s[:,0,0]
    result.s[:,0,0] = s11
    result.s[:,1,1] = s11
    ## HACK: TODO: verify this mathematically
    result.s[:,0,1] = npy.sqrt(1- npy.abs(s11)**2)*\
            npy.exp(1j*(npy.angle(s11)+npy.pi/2.*(npy.angle(s11)<0) -npy.pi/2*(npy.angle(s11)>0)))
    result.s[:,1,0] = result.s[:,0,1]
    return result

def chopinhalf(ntwk, *args, **kwargs):
        '''
        Chops a sandwich of identical,recicprocal 2-ports in half.

        Given two identical, reciprocal 2-ports measured in series,
        this returns one.


        Notes
        --------
        In other words, given

        .. math::

            B = A\\cdot\\cdotA

        Return A, where A port2 is connected to A port1. The result may
        be found through signal flow graph analysis and is,

        .. math::

            a_{11} = \frac{b_{11}}{1+b_{12}}

            a_{22} = \frac{b_{22}}{1+b_{12}}

            a_{12}^2 = b_{21}(1-\frac{b_{11}b_{22}}{(1+b_{12})^2}

        Parameters
        ------------
        ntwk : :class:`Network`
            a 2-port  that is equal to two identical two-ports in cascade


        '''
        if ntwk.nports != 2:
            raise ValueError('Only valid on 2ports')

        b11,b22,b12 = ntwk.s11,ntwk.s22,ntwk.s12
        kwargs['name'] = kwargs.get('name', ntwk.name)

        a11 = b11/(1+b12)
        a22 = b22/(1+b12)
        a21 = b12*(1-b11*b22/(1+b12)**2) # this is a21^2 here
        a21.s = mf.sqrt_phase_unwrap(a21.s)
        A = n_oneports_2_nport([a11,a21,a21,a22], *args, **kwargs)

        return A



## Building composit networks from sub-networks
def n_oneports_2_nport(ntwk_list, *args, **kwargs):
    '''
    Builds a N-port Network from list of N one-ports

    Parameters
    -----------
    ntwk_list : list of :class:`Network` objects
        must follow left-right, top-bottom order, ie, s11,s12,s21,s22
    \*args, \*\*kwargs :
        passed to :func:`Network.__init__` for the N-port

    Returns
    ----------
    nport : n-port :class:`Network`
        result
    '''
    nports = int(npy.sqrt(len(ntwk_list)))

    s_out = npy.concatenate(
        [npy.concatenate(
            [ntwk_list[(k+(l*nports))].s for k in range(nports)],2)\
                for l in range(nports)],1)


    z0 = npy.concatenate(
        [ntwk_list[k].z0 for k in range(0,nports**2,nports+1)],1)
    frequency = ntwk_list[0].frequency
    return Network(s=s_out, z0=z0, frequency=frequency, *args, **kwargs)


def n_twoports_2_nport(ntwk_list,nports, offby=1, **kwargs):
    '''
    Builds a N-port Network from list of two-ports

    By default all entries of result.s are filled with 0's, in case  you
    dont fully specify the entire s-matrix of the resultant ntwk.

    Parameters
    -----------
    ntwk_list : list of :class:`Network` objects
        the names must contain the port index, ie 'p12' or 'p43'
    offby : int
        starting value for s-parameters idecies. ie  a value of `1`,
        assumes that a s21 = ntwk.s[:,1,0]

    \*args, \*\*kwargs :
        passed to :func:`Network.__init__` for the N-port

    Returns
    ----------
    nport : n-port :class:`Network`
        result
    '''

    frequency = ntwk_list[0].frequency
    nport = Network(frequency = frequency ,
                    s=npy.zeros(shape=(frequency.npoints,nports,nports)),
                    **kwargs)

    for subntwk in ntwk_list:
        for m,n in nport.port_tuples:
            if m!=n and m>n:
                if '%i%i'%(m+offby,n+offby) in subntwk.name:
                    pass
                elif '%i%i'%(n+offby,m+offby)  in subntwk.name:
                    subntwk = subntwk.flipped()
                else:
                    continue

                for mn,jk in zip(product((m,n), repeat=2),product((0,1), repeat=2)):
                    m,n,j,k = mn[0],mn[1],jk[0],jk[1]
                    nport.s[:,m,n] = subntwk.s[:,j,k]
                    nport.z0[:,m] = subntwk.z0[:,j]
    return nport

def four_oneports_2_twoport(s11,s12,s21,s22, *args, **kwargs):
    '''
    Builds a 2-port Network from list of four 1-ports

    Parameters
    -----------
    s11 : one-port :class:`Network`
        s11
    s12 : one-port :class:`Network`
        s12
    s21 : one-port :class:`Network`
        s21
    s22 : one-port :class:`Network`
        s22
    \*args, \*\*kwargs :
        passed to :func:`Network.__init__` for the twoport

    Returns
    ----------
    twoport : two-port :class:`Network`
        result

    See Also
    -----------
    n_oneports_2_nport
    three_twoports_2_threeport
    '''
    return n_oneports_2_nport([s11,s12,s21,s22], *args, **kwargs)

def three_twoports_2_threeport(ntwk_triplet, auto_order = True,  *args,
                               **kwargs):
    '''
    Creates 3-port from  three 2-port Networks

    This function provides a convenient way to build a 3-port Network
    from a set of 2-port measurements. Which may occur when measuring
    a three port device on a 2-port VNA.

    Notes
    ---------
    if `auto_order` is False,  ntwk_triplet must be of port orderings:
         [p12, p13, p23]

    else if `auto_order`is True, then the  3 Networks in ntwk_triplet must
    contain port identification in their names.
    For example, their names may be like `me12`, `me13`, `me23`

    Parameters
    --------------
    ntwk_triplet : list of 2-port Network objects
        list of three 2-ports. see notes about order.

    auto_order : bool
        if True attempt to inspect port orderings from Network names.
        Names must be like 'p12', 'p23', etc
    contains : str
        only files containing this string will be loaded.
    \*args,\*\*kwargs :
        passed to :func:`Network.__init__` for resultant network

    Returns
    ------------
    threeport : 3-port Network

    See Also
    -----------
    n_oneports_2_nport

    Examples
    -----------
    >>> rf.three_twoports_2_threeport(rf.read_all('.').values())
    '''
    raise DeprecationWarning('Use n_twoports_2_nport instead')
    if auto_order:
        p12,p13,p23 = None,None,None
        s11,s12,s13,s21,s22,s23,s31,s32,s33 = None,None,None,None,None,None,None,None,None

        for k in ntwk_triplet:
            if '12' in k.name:
                p12 = k
            elif '13' in k.name:
                p13 = k
            elif '23' in k.name:
                p23 = k
            elif '21' in k.name:
                p12 = k.flipped()
            elif '31' in k.name:
                p31 = k.flipped()
            elif '32' in k.name:
                p23 = k.flipped()
    else:
        p12,p13,p23 = ntwk_triplet
        p21= p12.flipped()
        p31= p13.flipped()
        p32= p23.flipped()

    if p12 != None:
        s11 = p12.s11
        s12 = p12.s12
        s21 = p12.s21
        s22 = p12.s22

    if p13 != None:
        s11 = p13.s11
        s13 = p13.s12
        s31 = p13.s21
        s33 = p13.s22

    if p23 != None:
        s22 = p23.s11
        s23 = p23.s12
        s32 = p23.s21
        s33 = p23.s22

    ntwk_list = [s11,s12,s13,s21,s22,s23,s31,s32,s33]

    for k in range(len(ntwk_list)):
        if ntwk_list[k] == None:
            frequency = ntwk_triplet[0].frequency
            s = npy.zeros((len(ntwk_triplet[0]),1,1))
            ntwk_list[k] = Network(s=s, frequency=frequency)

    threeport = n_oneports_2_nport( ntwk_list, *args, **kwargs)
    return threeport




## Functions operating on s-parameter matrices
def connect_s(A,k,B,l):
    '''
    connect two n-port networks' s-matricies together.

    specifically, connect port `k` on network `A` to port `l` on network
    `B`. The resultant network has nports = (A.rank + B.rank-2). This
    function operates on, and returns s-matricies. The function
    :func:`connect` operates on :class:`Network` types.

    Parameters
    -----------
    A : :class:`numpy.ndarray`
            S-parameter matrix of `A`, shape is fxnxn
    k : int
            port index on `A` (port indices start from 0)
    B : :class:`numpy.ndarray`
            S-parameter matrix of `B`, shape is fxnxn
    l : int
            port index on `B`

    Returns
    -------
    C : :class:`numpy.ndarray`
        new S-parameter matrix


    Notes
    -------
    internally, this function creates a larger composite network
    and calls the  :func:`innerconnect_s` function. see that function for more
    details about the implementation

    See Also
    --------
        connect : operates on :class:`Network` types
        innerconnect_s : function which implements the connection
            connection algorithm


    '''

    if k > A.shape[-1]-1 or l > B.shape[-1] - 1:
        raise(ValueError('port indices are out of range'))

    nf = A.shape[0]     # num frequency points
    nA = A.shape[1]     # num ports on A
    nB = B.shape[1]     # num ports on B
    nC = nA + nB        # num ports on C

    #create composite matrix, appending each sub-matrix diagonally
    C = npy.zeros((nf, nC, nC), dtype='complex')
    C[:, :nA, :nA] = A.copy()
    C[:, nA:, nA:] = B.copy()

    # call innerconnect_s() on composit matrix C
    return innerconnect_s(C, k, nA + l)

def innerconnect_s(A, k, l):
    '''
    connect two ports of a single n-port network's s-matrix.

    Specifically, connect port `k`  to port `l` on `A`. This results in
    a (n-2)-port network.  This     function operates on, and returns
    s-matrices. The function :func:`innerconnect` operates on
    :class:`Network` types.

    Parameters
    -----------
    A : :class:`numpy.ndarray`
        S-parameter matrix of `A`, shape is fxnxn
    k : int
        port index on `A` (port indices start from 0)
    l : int
        port index on `A`

    Returns
    -------
    C : :class:`numpy.ndarray`
            new S-parameter matrix

    Notes
    -----
    The algorithm used to calculate the resultant network is called a
    'sub-network growth',  can be found in [#]_. The original paper
    describing the  algorithm is given in [#]_.

    References
    ----------
    .. [#] Compton, R.C.; , "Perspectives in microwave circuit analysis," Circuits and Systems, 1989., Proceedings of the 32nd Midwest Symposium on , vol., no., pp.716-718 vol.2, 14-16 Aug 1989. URL: http://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=101955&isnumber=3167

    .. [#] Filipsson, Gunnar; , "A New General Computer Algorithm for S-Matrix Calculation of Interconnected Multiports," Microwave Conference, 1981. 11th European , vol., no., pp.700-704, 7-11 Sept. 1981. URL: http://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=4131699&isnumber=4131585


    '''

    if k > A.shape[-1] - 1 or l > A.shape[-1] - 1:
        raise(ValueError('port indices are out of range'))

    nA = A.shape[1]  # num of ports on input s-matrix
    # create an empty s-matrix, to store the result
    C = npy.zeros(shape=A.shape, dtype='complex')

    # loop through ports and calulates resultant s-parameters
    for i in range(nA):
        for j in range(nA):
            C[:,i,j] = \
                A[:,i,j] + \
                ( A[:,k,j] * A[:,i,l] * (1 - A[:,l,k]) + \
                A[:,l,j] * A[:,i,k] * (1 - A[:,k,l]) +\
                A[:,k,j] * A[:,l,l] * A[:,i,k] + \
                A[:,l,j] * A[:,k,k] * A[:,i,l])/\
                ((1 - A[:,k,l]) * (1 - A[:,l,k]) - A[:,k,k] * A[:,l,l])

    # remove ports that were `connected`
    C = npy.delete(C, (k,l), 1)
    C = npy.delete(C, (k,l), 2)

    return C




## network parameter conversion
def s2z(s,z0=50):
    '''
    Convert scattering parameters [1]_ to impedance parameters [2]_


    .. math::
        z = \\sqrt {z_0} \\cdot (I + s) (I - s)^{-1} \\cdot \\sqrt{z_0}

    Parameters
    ------------
    s : complex array-like
        scattering parameters
    z0 : complex array-like or number
        port impedances.

    Returns
    ---------
    z : complex array-like
        impedance parameters



    References
    ----------
    .. [1] http://en.wikipedia.org/wiki/S-parameters
    .. [2] http://en.wikipedia.org/wiki/impedance_parameters

    '''
    nfreqs, nports, nports = s.shape
    z0 = fix_z0_shape(z0, nfreqs, nports)

    z = npy.zeros(s.shape, dtype='complex')
    I = npy.mat(npy.identity(s.shape[1]))
    s = s.copy() # to prevent the original array from being altered
    s[s==1.] = 1. + 1e-12 # solve numerical singularity
    s[s==-1.] = -1. + 1e-12 # solve numerical singularity
    for fidx in xrange(s.shape[0]):
        sqrtz0 = npy.mat(npy.sqrt(npy.diagflat(z0[fidx])))
        z[fidx] = sqrtz0 * (I-s[fidx])**-1 * (I+s[fidx]) * sqrtz0
    return z

def s2y(s,z0=50):
    '''
    convert scattering parameters [#]_ to admittance parameters [#]_


    .. math::
        y = \\sqrt {y_0} \\cdot (I - s)(I + s)^{-1} \\cdot \\sqrt{y_0}

    Parameters
    ------------
    s : complex array-like
        scattering parameters
    z0 : complex array-like or number
        port impedances

    Returns
    ---------
    y : complex array-like
        admittance parameters

    See Also
    ----------
    s2z
    s2y
    s2t
    z2s
    z2y
    z2t
    y2s
    y2z
    y2z
    t2s
    t2z
    t2y
    Network.s
    Network.y
    Network.z
    Network.t

    References
    ----------
    .. [#] http://en.wikipedia.org/wiki/S-parameters
    .. [#] http://en.wikipedia.org/wiki/Admittance_parameters
    '''

    nfreqs, nports, nports = s.shape
    z0 = fix_z0_shape(z0, nfreqs, nports)
    y = npy.zeros(s.shape, dtype='complex')
    I = npy.mat(npy.identity(s.shape[1]))
    s = s.copy() # to prevent the original array from being altered
    s[s==-1.] = -1. + 1e-12 # solve numerical singularity
    s[s==1.] = 1. + 1e-12 # solve numerical singularity
    for fidx in xrange(s.shape[0]):
        sqrty0 = npy.mat(npy.sqrt(npy.diagflat(1.0/z0[fidx])))
        y[fidx] = sqrty0*(I-s[fidx])*(I+s[fidx])**-1*sqrty0
    return y

def s2t(s):
    '''
    Converts scattering parameters [#]_ to scattering transfer parameters [#]_ .

    transfer parameters are also refered to as
    'wave cascading matrix', this function only operates on 2-port
    networks.

    Parameters
    -----------
    s : :class:`numpy.ndarray` (shape fx2x2)
        scattering parameter matrix

    Returns
    -------
    t : numpy.ndarray
        scattering transfer parameters (aka wave cascading matrix)

    See Also
    ---------
    inv : calculates inverse s-parameters

    s2z
    s2y
    s2t
    z2s
    z2y
    z2t
    y2s
    y2z
    y2z
    t2s
    t2z
    t2y
    Network.s
    Network.y
    Network.z
    Network.t

    References
    -----------
    .. [#] http://en.wikipedia.org/wiki/S-parameters
    .. [#] http://en.wikipedia.org/wiki/Scattering_transfer_parameters#Scattering_transfer_parameters
    '''
    #TODO: check rank(s) ==2

    t = npy.array([
        [-1*(s[:,0,0]*s[:,1,1]- s[:,1,0]*s[:,0,1])/s[:,1,0],
            -s[:,1,1]/s[:,1,0]],
        [s[:,0,0]/s[:,1,0],
            1./s[:,1,0] ]
        ]).transpose()
    return t


def z2s(z, z0=50):
    '''
    convert impedance parameters [1]_ to scattering parameters [2]_

    .. math::
        s = (\\sqrt{y_0} \\cdot z \\cdot \\sqrt{y_0} - I)(\\sqrt{y_0} \\cdot z \\cdot\\sqrt{y_0} + I)^{-1}

    Parameters
    ------------
    z : complex array-like
        impedance parameters
    z0 : complex array-like or number
        port impedances

    Returns
    ---------
    s : complex array-like
        scattering parameters



    References
    ----------
    .. [1] http://en.wikipedia.org/wiki/impedance_parameters
    .. [2] http://en.wikipedia.org/wiki/S-parameters
    '''
    nfreqs, nports, nports = z.shape
    z0 = fix_z0_shape(z0, nfreqs, nports)
    s = npy.zeros(z.shape, dtype='complex')
    I = npy.mat(npy.identity(z.shape[1]))
    for fidx in xrange(z.shape[0]):
        sqrty0 = npy.mat(npy.sqrt(npy.diagflat(1.0/z0[fidx])))
        s[fidx] = (sqrty0*z[fidx]*sqrty0 - I) * (sqrty0*z[fidx]*sqrty0 + I)**-1
    return s

def z2y(z):
    '''
    convert impedance parameters [#]_ to admittance parameters [#]_


    .. math::
        y = z^{-1}

    Parameters
    ------------
    z : complex array-like
        impedance parameters

    Returns
    ---------
    y : complex array-like
        admittance parameters

    See Also
    ----------
    s2z
    s2y
    s2t
    z2s
    z2y
    z2t
    y2s
    y2z
    y2z
    t2s
    t2z
    t2y
    Network.s
    Network.y
    Network.z
    Network.t

    References
    ----------
    .. [#] http://en.wikipedia.org/wiki/impedance_parameters
    .. [#] http://en.wikipedia.org/wiki/Admittance_parameters
    '''
    return npy.array([npy.mat(z[f,:,:])**-1 for f in xrange(z.shape[0])])

def z2t(z):
    '''
    Not Implemented yet

    convert impedance parameters [#]_ to scattering transfer parameters [#]_


    Parameters
    ------------
    z : complex array-like or number
        impedance parameters

    Returns
    ---------
    s : complex array-like or number
        scattering parameters

    See Also
    ----------
    s2z
    s2y
    s2t
    z2s
    z2y
    z2t
    y2s
    y2z
    y2z
    t2s
    t2z
    t2y
    Network.s
    Network.y
    Network.z
    Network.t


    References
    ----------
    .. [#] http://en.wikipedia.org/wiki/impedance_parameters
    .. [#] http://en.wikipedia.org/wiki/Scattering_transfer_parameters#Scattering_transfer_parameters
    '''
    raise (NotImplementedError)

def z2a(z):
    '''
    Converts impedance parameters to abcd  parameters [#]_ .

   
    Parameters
    -----------
    z : :class:`numpy.ndarray` (shape fx2x2)
        impedance parameter matrix

    Returns
    -------
    abcd : numpy.ndarray
        scattering transfer parameters (aka wave cascading matrix)

    See Also
    ---------
    inv : calculates inverse s-parameters

    s2z
    s2y
    s2t
    z2s
    z2y
    z2t
    y2s
    y2z
    y2z
    t2s
    t2z
    t2y
    Network.s
    Network.y
    Network.z
    Network.t

    References
    -----------
    .. [#] https://en.wikipedia.org/wiki/Two-port_network
    '''
    abcd = npy.array([
        [z[:,0,0]/z[:,1,0],
            1./z[:,1,0]],
        [(z[:,0,0]*z[:,1,1]- z[:,1,0]*z[:,0,1])/z[:,1,0],
            z[:,1,1]/z[:,1,0]],
        ]).transpose()
    return abcd

def s2a(s,z0):
    '''
    Converts scattering parameters to abcd  parameters [#]_ .

   
    Parameters
    -----------
    s : :class:`numpy.ndarray` (shape fx2x2)
        impedance parameter matrix
        
    z0: number or, :class:`numpy.ndarray` (shape fx2)
        port impedance

    Returns
    -------
    abcd : numpy.ndarray
        scattering transfer parameters (aka wave cascading matrix)
    '''
    return z2a(s2z(s,z0))
    
def y2s(y, z0=50):
    '''
    convert admittance parameters [#]_ to scattering parameters [#]_


    .. math::
        s = (I - \\sqrt{z_0} \\cdot y \\cdot \\sqrt{z_0})(I + \\sqrt{z_0} \\cdot y \\cdot \\sqrt{z_0})^{-1}

    Parameters
    ------------
    y : complex array-like
        admittance parameters

    z0 : complex array-like or number
        port impedances

    Returns
    ---------
    s : complex array-like or number
        scattering parameters

    See Also
    ----------
    s2z
    s2y
    s2t
    z2s
    z2y
    z2t
    y2s
    y2z
    y2z
    t2s
    t2z
    t2y
    Network.s
    Network.y
    Network.z
    Network.t


    References
    ----------
    .. [#] http://en.wikipedia.org/wiki/Admittance_parameters
    .. [#] http://en.wikipedia.org/wiki/S-parameters
    '''
    nfreqs, nports, nports = y.shape
    z0 = fix_z0_shape(z0, nfreqs, nports)
    s = npy.zeros(y.shape, dtype='complex')
    I = npy.mat(npy.identity(s.shape[1]))
    for fidx in xrange(s.shape[0]):
        sqrtz0 = npy.mat(npy.sqrt(npy.diagflat(z0[fidx])))
        s[fidx] = (I - sqrtz0*y[fidx]*sqrtz0) * (I + sqrtz0*y[fidx]*sqrtz0)**-1
    return s

def y2z(y):
    '''
    convert admittance parameters [#]_ to impedance parameters [#]_


    .. math::
        z = y^{-1}

    Parameters
    ------------
    y : complex array-like
        admittance parameters

    Returns
    ---------
    z : complex array-like
        impedance parameters

    See Also
    ----------
    s2z
    s2y
    s2t
    z2s
    z2y
    z2t
    y2s
    y2z
    y2z
    t2s
    t2z
    t2y
    Network.s
    Network.y
    Network.z
    Network.t

    References
    ----------
    .. [#] http://en.wikipedia.org/wiki/Admittance_parameters
    .. [#] http://en.wikipedia.org/wiki/impedance_parameters
    '''
    return npy.array([npy.mat(y[f,:,:])**-1 for f in xrange(y.shape[0])])

def y2t(y):
    '''
    Not Implemented Yet

    convert admittance parameters [#]_ to scattering-transfer parameters [#]_


    Parameters
    ------------
    y : complex array-like or number
        impedance parameters

    Returns
    ---------
    t : complex array-like or number
        scattering parameters

    See Also
    ----------
    s2z
    s2y
    s2t
    z2s
    z2y
    z2t
    y2s
    y2z
    y2z
    t2s
    t2z
    t2y
    Network.s
    Network.y
    Network.z
    Network.t

    References
    ----------
    .. [#] http://en.wikipedia.org/wiki/Admittance_parameters
    .. [#] http://en.wikipedia.org/wiki/Scattering_transfer_parameters#Scattering_transfer_parameters
    '''
    raise (NotImplementedError)

def t2s(t):
    '''
    converts scattering transfer parameters [#]_ to scattering parameters [#]_

    transfer parameters are also referred to as
    'wave cascading matrix', this function only operates on 2-port
    networks. this function only operates on 2-port scattering
    parameters.

    Parameters
    -----------
    t : :class:`numpy.ndarray` (shape fx2x2)
            scattering transfer parameters

    Returns
    -------
    s : :class:`numpy.ndarray`
            scattering parameter matrix.

    See Also
    ---------
    inv : calculates inverse s-parameters
    s2z
    s2y
    s2t
    z2s
    z2y
    z2t
    y2s
    y2z
    y2z
    t2s
    t2z
    t2y
    Network.s
    Network.y
    Network.z
    Network.t

    References
    -----------
    .. [#] http://en.wikipedia.org/wiki/Scattering_transfer_parameters#Scattering_transfer_parameters
    .. [#] http://en.wikipedia.org/wiki/S-parameters
    '''
    #TODO: check rank(s) ==2
    s = npy.array([
        [t[:,0,1]/t[:,1,1],
             1/t[:,1,1]],
        [(t[:,0,0]*t[:,1,1]- t[:,1,0]*t[:,0,1])/t[:,1,1],
            -1*t[:,1,0]/t[:,1,1] ]
        ]).transpose()
    return s

def t2z(t):
    '''
    Not Implemented  Yet

    Convert scattering transfer parameters [#]_ to impedance parameters [#]_



    Parameters
    ------------
    t : complex array-like or number
        impedance parameters

    Returns
    ---------
    z : complex array-like or number
        scattering parameters

    See Also
    ----------
    s2z
    s2y
    s2t
    z2s
    z2y
    z2t
    y2s
    y2z
    y2z
    t2s
    t2z
    t2y
    Network.s
    Network.y
    Network.z
    Network.t

    References
    ----------
    .. [#] http://en.wikipedia.org/wiki/Scattering_transfer_parameters#Scattering_transfer_parameters
    .. [#] http://en.wikipedia.org/wiki/impedance_parameters
    '''
    raise (NotImplementedError)

def t2y(t):
    '''
    Not Implemented Yet

    Convert scattering transfer parameters to admittance parameters [#]_




    Parameters
    ------------
    t : complex array-like or number
        t-parameters

    Returns
    ---------
    y : complex array-like or number
        admittance parameters

    See Also
    ----------
    s2z
    s2y
    s2t
    z2s
    z2y
    z2t
    y2s
    y2z
    y2z
    t2s
    t2z
    t2y
    Network.s
    Network.y
    Network.z
    Network.t

    References
    ----------
    .. [#] http://en.wikipedia.org/wiki/Scattering_transfer_parameters#Scattering_transfer_parameters

    '''
    raise (NotImplementedError)

## these methods are used in the secondary properties
def passivity(s):
    '''
    Passivity metric for a multi-port network.

    A metric which is proportional to the amount of power lost in a 
    multiport network, depending on the excitation port. Specifically, 
    this returns a matrix who's diagonals are equal to the total
    power received at all ports, normalized to the power at a single
    excitement port.

    mathmatically, this is a test for unitary-ness of the
    s-parameter matrix [#]_.

    for two port this is

    .. math::

            \sqrt( |S_{11}|^2 + |S_{21}|^2 \, , \, |S_{22}|^2+|S_{12}|^2)

    in general it is

    .. math::

            \\sqrt( S^H \\cdot S)

    where :math:`H` is conjugate transpose of S, and :math:`\\cdot`
    is dot product.
    
    Notes
    ---------
    The total amount of power disipated in a network depends on the 
    port matches. For example, given a matched attenuator, this metric 
    will yield the attenuation value. However, if the attenuator is 
    cascaded with a mismatch, the power disipated will not be equivalent
    to the attenuator value, nor equal for each excitation port.

    Returns
    ---------
    passivity : :class:`numpy.ndarray` of shape fxnxn

    References
    ------------
    .. [#] http://en.wikipedia.org/wiki/Scattering_parameters#Lossless_networks
    '''
    if s.shape[-1] == 1:
        raise (ValueError('Doesn\'t exist for one ports'))

    pas_mat = s.copy()
    for f in range(len(s)):
        pas_mat[f,:,:] = npy.sqrt(npy.dot(s[f,:,:].conj().T, s[f,:,:]))

    return pas_mat

def reciprocity(s):
        '''
        Reciprocity metric for a multi-port network.

        This returns the magnitude of the difference between the
        s-parameter matrix and its transpose.

        for two port this is

        .. math::

                | S - S^T |



        where :math:`T` is transpose of S

        Returns
        ---------
        reciprocity : :class:`numpy.ndarray` of shape fxnxn
        '''
        if s.shape[-1] == 1:
            raise (ValueError('Doesn\'t exist for one ports'))

        rec_mat = s.copy()
        for f in range(len(s)):
            rec_mat[f,:,:] = abs(s[f,:,:]- s[f,:,:].T)

        return rec_mat


## renormalize
def renormalize_s(s, z_old, z_new):
    '''
    Renormalize a s-parameter matrix given old and new port impedances

    In the Parameters descriptions, F,N,N = shape(s).

    Notes
    ------
    This re-normalization assumes psuedo-wave formulation. The
    function :func:`renormalize_s_pw` implementes the power-wave
    formulation. However, the two implementation are only different
    for complex characteristic impedances.
    See the [1]_ and [2]_ for more details.

    Parameters
    ---------------
    s : complex array of shape FxNxN
        s-parameter matrix

    z_old : complex array of shape FxN, F, N or a  scalar
        old (original) port impedances

    z_new : complex array of shape FxN, F, N or a  scalar
        new port impedances


    Notes
    ------
    The impedance renormalization. This just calls ::

        z2s(s2z(s,z0 = z_old), z0 = z_new)

    However, you can see ref [1]_ or [2]_ for some theoretical background.



    See Also
    --------
    renormalize_s_pw : renormalize using power wave formulation
    Network.renormalize : method of Network  to renormalize s
    fix_z0_shape
    ssz
    z2s

    References
    -------------
    .. [1] R. B. Marks and D. F. Williams, "A general waveguide circuit theory," Journal of Research of the National Institute of Standards and Technology, vol. 97, no. 5, pp. 533-561, 1992.


    .. [2] http://www.anritsu.com/en-gb/downloads/application-notes/application-note/dwl1334.aspx

    Examples
    ------------
    >>> s = zeros(shape=(101,2,2))
    >>> renormalize_s(s, 50,25)


    '''
    # thats a heck of a one-liner!
    return z2s(s2z(s, z0=z_old), z0=z_new)

def renormalize_s_pw(s, z_old, z_new):
    '''
    Renormalize a s-parameter matrix given old and new port impedances
    by the power wave renormalization

    In the Parameters descriptions, F,N,N = shape(s).

    Parameters
    ---------------
    s : complex array of shape FxNxN
        s-parameter matrix

    z_old : complex array of shape FxN, F, N or a  scalar
        old (original) port impedances

    z_new : complex array of shape FxN, F, N or a  scalar
        new port impedances


    Notes
    ------
    This re-normalization assumes psuedo-wave formulation. The
    function :func:`renormalize_s_pw` implementes the power-wave
    formulation. However, the two implementation are only different
    for complex characteristic impedances.
    See the [1]_ and [2]_ for more details.



    References
    -------------
    .. [1] http://www.anritsu.com/en-gb/downloads/application-notes/application-note/dwl1334.aspx
        power-wave Eq 10,11,12 in page 10

    See Also
    ----------
    renormalize_s : renormalize using psuedo wave formulation
    Network.renormalize : method of Network  to renormalize s
    fix_z0_shape
    fix_z0_shape
    ssz
    z2s

    Examples
    ------------
    >>> z_old = 50.+0.j # original reference impedance
    >>> z_new = 50.+50.j # new reference impedance to change to
    >>> load = rf.wr10.load(0.+0.j, nports=1, z0=z_old)
    >>> s = load.s
    >>> renormalize_s_powerwave(s, z_old, z_new)
    '''

    nfreqs, nports, nports = s.shape
    A = fix_z0_shape(z_old, nfreqs, nports)
    B = fix_z0_shape(z_new, nfreqs, nports)

    S_pw = npy.zeros(s.shape, dtype='complex')
    I = npy.mat(npy.identity(s.shape[1]))
    s = s.copy() # to prevent the original array from being altered
    s[s==1.] = 1. + 1e-12 # solve numerical singularity
    s[s==-1.] = -1. + 1e-12 # solve numerical singularity
    # make sure real part of impedance is not zero
    A[A.real==0] = 1e-12 + 1.j*A.imag[A.real<=0]
    B[B.real==0] = 1e-12 + 1.j*B.imag[B.real<=0]

    for fidx in xrange(s.shape[0]):
        A_ii = A[fidx]
        B_ii = B[fidx]

        # Eq. 11, Eq. 12
        Q_ii = npy.sqrt(npy.absolute(B_ii.real/A_ii.real)) * (A_ii + A_ii.conj()) / (B_ii.conj() + A_ii) # Eq(11)
        G_ii = (B_ii - A_ii) / (B_ii + A_ii.conj()) # Eq(12)

        Q = npy.mat(npy.diagflat(Q_ii))
        G = npy.mat(npy.diagflat(G_ii))
        S = s[fidx]

        # Eq. 10
        S_pw[fidx] = Q**-1 * (S - G.conj().T) * (I - G*S)**-1 * Q.conj().T
    return S_pw


def fix_z0_shape( z0, nfreqs, nports):
    '''
    Make a port impedance of correct shape for a given network's matrix

    This attempts to broadcast z0 to satisy
        npy.shape(z0) == (nfreqs,nports)

    Parameters
    --------------
    z0 : number, array-like
        z0 can be:
        * a number (same at all ports and frequencies)
        * an array-like of length == number ports.
        * an array-like of length == number frequency points.
        * the correct shape ==(nfreqs,nports)

    nfreqs : int
        number of frequency points
    nportrs : int
        number of ports

    Returns
    ----------
    z0 : array of shape ==(nfreqs,nports)
        z0  with the right shape for a nport Network

    Examples
    ----------
    For a two-port network with 201 frequency points, possible uses may
    be

    >>> z0 = rf.fix_z0_shape(50 , 201,2)
    >>> z0 = rf.fix_z0_shape([50,25] , 201,2)
    >>> z0 = rf.fix_z0_shape(range(201) , 201,2)


    '''



    if npy.shape(z0) == (nfreqs, nports):
        # z0 is of correct shape. super duper.return it quick.
        return z0.copy()

    elif npy.isscalar(z0):
        # z0 is a single number
        return npy.array(nfreqs*[nports * [z0]])

    elif len(z0)  == nports:
        # assume z0 is a list of impedances for each port,
        # but constant with frequency
        return npy.array(nfreqs*[z0])

    elif len(z0) == nfreqs:
        # assume z0 is a list of impedances for each frequency,
        # but constant with respect to ports
        return npy.array(nports * [z0]).T

    else:
        raise IndexError('z0 is not an acceptable shape')


## cascading assistance functions
def inv(s):
    '''
    Calculates 'inverse' s-parameter matrix, used for de-embedding

    This is not literally the inverse of the s-parameter matrix. Instead, it
    is defined such that the inverse of the s-matrix cascaded
    with itself is unity.

    .. math::

            inv(s) = t2s({s2t(s)}^{-1})

    where :math:`x^{-1}` is the matrix inverse. In words, this
    is the inverse of the scattering transfer parameters matrix
    transformed into a scattering parameters matrix.

    Parameters
    -----------
    s : :class:`numpy.ndarray` (shape fx2x2)
            scattering parameter matrix.

    Returns
    -------
    s' : :class:`numpy.ndarray`
            inverse scattering parameter matrix.

    See Also
    ---------
    t2s : converts scattering transfer parameters to scattering parameters
    s2t : converts scattering parameters to scattering transfer parameters


    '''
    # this idea is from lihan
    i = s2t(s)
    for f in range(len(i)):
        i[f,:,:] = npy.linalg.inv(i[f,:,:])   # could also be written as
                                              #   npy.mat(i[f,:,:])**-1  -- Trey
    i = t2s(i)
    return i

def flip(a):
    '''
    invert the ports of a networks s-matrix, 'flipping' it over

    Parameters
    -----------
    a : :class:`numpy.ndarray`
            scattering parameter matrix. shape should be should be 2x2, or
            fx2x2

    Returns
    -------
    a' : :class:`numpy.ndarray`
            flipped scattering parameter matrix, ie interchange of port 0
            and port 1

    Note
    -----
                    only works for 2-ports at the moment
    '''
    c = a.copy()

    if len (a.shape) > 2 :
        for f in range(a.shape[0]):
            c[f,:,:] = flip(a[f,:,:])
    elif a.shape == (2,2):
        c[0,0] = a[1,1]
        c[1,1] = a[0,0]
        c[0,1] = a[1,0]
        c[1,0] = a[0,1]
    else:
        raise IndexError('matrices should be 2x2, or kx2x2')
    return c



## COMMON CHECKS (raise exceptions)
def check_frequency_equal(ntwkA, ntwkB):
    '''
    checks if two Networks have same frequency
    '''
    if assert_frequency_equal(ntwkA,ntwkB) == False:
        raise IndexError('Networks dont have matching frequency. See `Network.interpolate`')

def check_z0_equal(ntwkA,ntwkB):
    '''
    checks if two Networks have same port impedances
    '''
    #note you should check frequency equal before you call this
    if assert_z0_equal(ntwkA,ntwkB) == False:
        raise ValueError('Networks dont have matching z0.')

def check_nports_equal(ntwkA,ntwkB):
    '''
    checks if two Networks have same number of ports
    '''
    if assert_nports_equal(ntwkA,ntwkB) == False:
        raise ValueError('Networks dont have matching number of ports.')

## TESTs (return [usually boolean] values)
def assert_frequency_equal(ntwkA, ntwkB):
    '''
    '''
    return (ntwkA.frequency  == ntwkB.frequency)

def assert_z0_equal(ntwkA,ntwkB):
    '''
    '''
    return (ntwkA.z0 == ntwkB.z0).all()

def assert_z0_at_ports_equal(ntwkA,k,ntwkB,l):
    '''
    '''
    return (ntwkA.z0[:,k] == ntwkB.z0[:,l]).all()

def assert_nports_equal(ntwkA,ntwkB):
    '''
    '''
    return (ntwkA.number_of_ports == ntwkB.number_of_ports)




## Other
# dont belong here, but i needed them quickly
# this is needed for port impedance mismatches
def impedance_mismatch(z1, z2):
    '''
    creates a two-port s-matrix for a impedance mis-match

    Parameters
    -----------
    z1 : number or array-like
            complex impedance of port 1
    z2 : number or array-like
            complex impedance of port 2

    Returns
    ---------
    s' : 2-port s-matrix for the impedance mis-match
    '''
    gamma = zl_2_Gamma0(z1,z2)
    result = npy.zeros(shape=(len(gamma),2,2), dtype='complex')

    result[:,0,0] = gamma
    result[:,1,1] = -gamma
    result[:,1,0] = (1+gamma)*npy.sqrt(1.0*z1/z2)
    result[:,0,1] = (1-gamma)*npy.sqrt(1.0*z2/z1)
    return result

def two_port_reflect(ntwk1, ntwk2=None):
    '''
    Generates a two-port reflective two-port, from two one-ports.


    Parameters
    ----------
    ntwk1 : one-port Network object
            network seen from port 1
    ntwk2 : one-port Network object, or None
            network seen from port 2. if None then will use ntwk1. 

    Returns
    -------
    result : Network object
            two-port reflective network

    Notes
    -------
        The resultant Network is copied from `ntwk1`, so its various
    properties(name, frequency, etc) are inherited from that Network.

    Examples
    ---------
    >>> short,open = rf.Network('short.s1p', rf.Network('open.s1p')
    >>> rf.two_port_reflect(short,open)
    '''
    result = ntwk1.copy()
    if ntwk2 is None:
        ntwk2 =ntwk1
    s11 = ntwk1.s[:,0,0]
    s22 = ntwk2.s[:,0,0]
    s21 = npy.zeros(ntwk1.frequency.npoints, dtype=complex)
    result.s = npy.array(\
            [[s11,  s21],\
            [ s21,  s22]]).\
            transpose().reshape(-1,2,2)
    result.z0 = npy.hstack([ntwk1.z0, ntwk2.z0])
    try:
        result.name = ntwk1.name+'-'+ntwk2.name
    except(TypeError):
        pass
    return result

