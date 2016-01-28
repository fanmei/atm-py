from netCDF4 import Dataset as _Dataset
import os as _os
from atmPy.data_archives.arm import _tdmasize,_tdmaapssize,_tdmahyg,_aosacsm, _noaaaos
import pandas as _pd
import pylab as _plt

arm_products = {'tdmasize':   {'module': _tdmasize},
                'tdmaapssize':{'module': _tdmaapssize},
                'tdmahyg':    {'module': _tdmahyg},
                'aosacsm':    {'module': _aosacsm},
                'noaaaos':    {'module': _noaaaos}
                }

def check_availability(folder,
                       data_product = None,
                       time_window = ('1990-01-01','2030-01-01'),
                       ignore_unknown = True,
                       verbose = False):

    fname = _os.listdir(folder)
    index = _pd.date_range('1990-01-01','2030-01-01', freq = 'D')
    df = _pd.DataFrame(index = index)

    for f in fname:
        if verbose:
            print('\n', f)

        # error handling: test for netCDF file format
        if _os.path.splitext(f)[-1] != '.cdf':
            txt = '\t %s is not a netCDF file ... skipping'%f
            if verbose:
                print(txt)
            continue

        date = _is_in_time_window(f,time_window,verbose)
        if not date:
            continue

        product_id = _is_in_product_keys(f, ignore_unknown, verbose)
        if not product_id:
            continue

        if not _is_desired_product(product_id,data_product,verbose):
            continue

        if product_id not in df.columns:
            df[product_id] = _pd.Series(1, index = [date])
        else:
            df[product_id][date] = 1

    df = df.sort(axis=1)

    for e,col in enumerate(df.columns):
        df[col].values[df[col].values == 1] = e+1


    f,a = _plt.subplots()
    for col in df.columns:
        a.plot(df.index,df[col], lw = 35, color = [0,0,1,0.3])

    a.set_ylim((0.1,df.shape[1] + 0.9))
    bla = range(1,df.shape[1]+1)
    a.yaxis.set_ticks(bla)
    a.yaxis.set_ticklabels(df.columns)

    f.autofmt_xdate()

    f.tight_layout()
    return df, a


def read_cdf(fname,
             data_product = None,
             time_window = None,
             concat = True,
             ignore_unknown = False,
             verbose = True,
             ):
    """
    Reads ARM NetCDF file(s) and returns a containers with the results.

    Parameters
    ----------
    fname: str or list of str.
        Either a file, directory, or list of files. If directory name is given
        all files in the directory will be considered.
    data_product: str.
        To see a list of allowed products look at the variable arm_products.
    time_window: tuple of str.
        e.g. ('2016-01-25 15:22:40','2016-01-29 15:00:00').
        Currently the entire day is considered, no need to use exact times.
    concat
    ignore_unknown
    verbose

    Returns
    -------

    """

    # list or single file
    if type(fname) == str:
        fname = [fname]

    if type(data_product) == str:
        data_product = [data_product]
    products = {}

    #loop thru files
    for f in fname:
        if verbose:
            print('\n', f)

        # error handling: test for netCDF file format
        if _os.path.splitext(f)[-1] != '.cdf':
            txt = '\t %s is not a netCDF file ... skipping'%f
            if verbose:
                print(txt)
            continue


        if not _is_in_time_window(f,time_window,verbose):
            continue

        product_id =  _is_in_product_keys(f, ignore_unknown, verbose)
        if not product_id:
            continue

        if not _is_desired_product(product_id,data_product,verbose):
            continue

        if product_id not in products.keys():
            products[product_id] = []


        file_obj = _Dataset(f)
        out = arm_products[product_id]['module']._parse_netCDF(file_obj)
        file_obj.close()
        products[product_id].append(out)

    if len(fname) == 1:
        return out

    else:
        if concat:
            for pf in products.keys():
                products[pf] = arm_products[pf]['module']._concat_rules(products[pf])
        return products



def _is_desired_product(product_id, data_product, verbose):
    out = True
    if data_product:
        if product_id not in data_product:
            if verbose:
                print('Not the desired data product ... skip')
            out = False
    return out


def _is_in_product_keys(f, ignore_unknown,verbose):

    fnt = _os.path.split(f)[-1].split('.')
    product_id = False
    for prod in arm_products.keys():
        if prod in fnt[0]:
            product_id = prod
            break

    if not product_id:
        txt = '\t has no ncattr named platform_id. Guess from file name failed ... skip'
        if verbose:
            print(txt)


    if product_id not in arm_products.keys():
        product_id = False
        txt = 'Platform id %s is unknown.'%product_id
        if ignore_unknown:
            if verbose:
                print(txt + '... skipping')

        else:
            raise KeyError(txt)
    return product_id

def _is_in_time_window(f,time_window, verbose):
    out = True
    if time_window:
        fnt = _os.path.split(f)[-1].split('.')
        ts = fnt[-3]
        file_start_data = _pd.to_datetime(ts)
        start_time = _pd.to_datetime(time_window[0])
        end_time = _pd.to_datetime(time_window[1])
        dt_start = file_start_data - start_time
        dt_end = file_start_data - end_time
        out = file_start_data

        if dt_start.total_seconds() < -86399:
            if verbose:
                print('outside (before) the time window ... skip')
            out = False
        elif dt_end.total_seconds() > 86399:
            if verbose:
                print('outside (after) the time window ... skip')
            out = False
    return out