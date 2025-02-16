"""Tests for preprocessing functions.

"""
import pytest

import numpy as np

import alchemlyb
from alchemlyb.parsing import gmx
from alchemlyb.preprocessing import (slicing, statistical_inefficiency,
                                     equilibrium_detection,
                                     decorrelate_u_nk, decorrelate_dhdl)
from alchemlyb.parsing.gmx import extract_u_nk, extract_dHdl
from alchemtest.gmx import load_benzene, load_ABFE

import alchemtest.gmx


def gmx_benzene_dHdl():
    dataset = alchemtest.gmx.load_benzene()
    return gmx.extract_dHdl(dataset['data']['Coulomb'][0], T=300)


@pytest.fixture()
def gmx_ABFE():
    dataset = alchemtest.gmx.load_ABFE()
    return gmx.extract_u_nk(dataset['data']['complex'][0], T=300)

@pytest.fixture()
def gmx_ABFE_dhdl():
    dataset = alchemtest.gmx.load_ABFE()
    return gmx.extract_dHdl(dataset['data']['complex'][0], T=300)

@pytest.fixture()
def gmx_ABFE_u_nk():
    dataset = alchemtest.gmx.load_ABFE()
    return gmx.extract_u_nk(dataset['data']['complex'][-1], T=300)

@pytest.fixture()
def gmx_benzene_u_nk_fixture():
    dataset = alchemtest.gmx.load_benzene()
    return gmx.extract_u_nk(dataset['data']['Coulomb'][0], T=300)


def gmx_benzene_u_nk():
    dataset = alchemtest.gmx.load_benzene()
    return gmx.extract_u_nk(dataset['data']['Coulomb'][0], T=300)


def gmx_benzene_dHdl_full():
    dataset = alchemtest.gmx.load_benzene()
    return alchemlyb.concat([gmx.extract_dHdl(i, T=300) for i in dataset['data']['Coulomb']])


def gmx_benzene_u_nk_full():
    dataset = alchemtest.gmx.load_benzene()
    return alchemlyb.concat([gmx.extract_u_nk(i, T=300) for i in dataset['data']['Coulomb']])

class TestSlicing:
    """Test slicing functionality.

    """
    def slicer(self, *args, **kwargs):
        return slicing(*args, **kwargs)

    @pytest.mark.parametrize(('data', 'size'), [(gmx_benzene_dHdl(), 661),
                                                (gmx_benzene_u_nk(), 661)])
    def test_basic_slicing(self, data, size):
        assert len(self.slicer(data, lower=1000, upper=34000, step=5)) == size

    @pytest.mark.parametrize('data', [gmx_benzene_dHdl(),
                                      gmx_benzene_u_nk()])
    def test_disordered_exception(self, data):
        """Test that a shuffled DataFrame yields a KeyError.

        """
        indices = np.arange(len(data))
        np.random.shuffle(indices)

        df = data.iloc[indices]

        with pytest.raises(KeyError):
            self.slicer(df, lower=200)

    @pytest.mark.parametrize('data', [gmx_benzene_dHdl_full(),
                                      gmx_benzene_u_nk_full()])
    def test_duplicated_exception(self, data):
        """Test that a DataFrame with duplicate times yields a KeyError.

        """
        with pytest.raises(KeyError):
            self.slicer(data.sort_index(0), lower=200)

    def test_subsample_bounds_and_step(self, gmx_ABFE):
        """Make sure that slicing the series also works
        """
        subsample = statistical_inefficiency(gmx_ABFE,
                                             gmx_ABFE.sum(axis=1),
                                             lower=100,
                                             upper=400,
                                             step=2)
        assert len(subsample) == 76

    def test_multiindex_duplicated(self, gmx_ABFE):
        subsample = statistical_inefficiency(gmx_ABFE,
                                             gmx_ABFE.sum(axis=1))
        assert len(subsample) == 501

    def test_sort_off(self, gmx_ABFE):
        unsorted = alchemlyb.concat([gmx_ABFE[-500:], gmx_ABFE[:500]])
        with pytest.raises(KeyError):
            statistical_inefficiency(unsorted,
                                     unsorted.sum(axis=1),
                                     sort=False)

    def test_sort_on(self, gmx_ABFE):
        unsorted = alchemlyb.concat([gmx_ABFE[-500:], gmx_ABFE[:500]])
        subsample = statistical_inefficiency(unsorted,
                                             unsorted.sum(axis=1),
                                             sort=True)
        assert subsample.reset_index(0)['time'].is_monotonic_increasing

    def test_sort_on_noseries(self, gmx_ABFE):
        unsorted = alchemlyb.concat([gmx_ABFE[-500:], gmx_ABFE[:500]])
        subsample = statistical_inefficiency(unsorted,
                                             None,
                                             sort=True)
        assert subsample.reset_index(0)['time'].is_monotonic_increasing

    def test_duplication_off(self, gmx_ABFE):
        duplicated = alchemlyb.concat([gmx_ABFE, gmx_ABFE])
        with pytest.raises(KeyError):
            statistical_inefficiency(duplicated,
                                     duplicated.sum(axis=1),
                                     drop_duplicates=False)

    def test_duplication_on_dataframe(self, gmx_ABFE):
        duplicated = alchemlyb.concat([gmx_ABFE, gmx_ABFE])
        subsample = statistical_inefficiency(duplicated,
                                             duplicated.sum(axis=1),
                                             drop_duplicates=True)
        assert len(subsample) < 1000

    def test_duplication_on_dataframe_noseries(self, gmx_ABFE):
        duplicated = alchemlyb.concat([gmx_ABFE, gmx_ABFE])
        subsample = statistical_inefficiency(duplicated,
                                             None,
                                             drop_duplicates=True)
        assert len(subsample) == 1001

    def test_duplication_on_series(self, gmx_ABFE):
        duplicated = alchemlyb.concat([gmx_ABFE, gmx_ABFE])
        subsample = statistical_inefficiency(duplicated.sum(axis=1),
                                             duplicated.sum(axis=1),
                                             drop_duplicates=True)
        assert len(subsample) < 1000

    def test_duplication_on_series_noseries(self, gmx_ABFE):
        duplicated = alchemlyb.concat([gmx_ABFE, gmx_ABFE])
        subsample = statistical_inefficiency(duplicated.sum(axis=1),
                                             None,
                                             drop_duplicates=True)
        assert len(subsample) == 1001

class CorrelatedPreprocessors:

    @pytest.mark.parametrize(('data', 'size'), [(gmx_benzene_dHdl(), 4001),
                                                (gmx_benzene_u_nk(), 4001)])
    def test_subsampling(self, data, size):
        """Basic test for execution; resulting size of dataset sensitive to
        machine and depends on algorithm.
        """
        assert len(self.slicer(data, series=data.iloc[:, 0])) <= size

    @pytest.mark.parametrize('data', [gmx_benzene_dHdl(),
                                      gmx_benzene_u_nk()])
    def test_no_series(self, data):
        """Check that we get the same result as simple slicing with no Series.

        """
        df_sub = self.slicer(data, lower=200, upper=5000, step=2)
        df_sliced = slicing(data, lower=200, upper=5000, step=2)

        assert np.all((df_sub == df_sliced))


class TestStatisticalInefficiency(TestSlicing, CorrelatedPreprocessors):

    def slicer(self, *args, **kwargs):
        return statistical_inefficiency(*args, **kwargs)

    @pytest.mark.parametrize(('conservative', 'data', 'size'),
                             [
                                 (True, gmx_benzene_dHdl(), 2001),  # 0.00:  g = 1.0559445620585415
                                 (True, gmx_benzene_u_nk(), 2001),  # 'fep': g = 1.0560203916559594
                                 (False, gmx_benzene_dHdl(), 3789),
                                 (False, gmx_benzene_u_nk(), 3571),
                             ])
    def test_conservative(self, data, size, conservative):
        sliced = self.slicer(data, series=data.iloc[:, 0], conservative=conservative)
        # results can vary slightly with different machines
        # so possibly do
        # delta = 10
        # assert size - delta < len(sliced) < size + delta
        assert len(sliced) == size

    @pytest.mark.parametrize('series', [
        gmx_benzene_dHdl()['fep'][:20],   # wrong length
        gmx_benzene_dHdl()['fep'][::-1],  # wrong time stamps (reversed)
        ])
    def test_raise_ValueError_for_mismatched_data(self, series):
        data = gmx_benzene_dHdl()
        with pytest.raises(ValueError):
            self.slicer(data, series=series)


class TestEquilibriumDetection(TestSlicing, CorrelatedPreprocessors):

    def slicer(self, *args, **kwargs):
        return equilibrium_detection(*args, **kwargs)

class Test_Units():
    '''Test the preprocessing module.'''
    @staticmethod
    @pytest.fixture(scope='class')
    def dhdl():
        dataset = load_benzene()
        dhdl = extract_dHdl(dataset['data']['Coulomb'][0], 310)
        return dhdl

    def test_slicing(self, dhdl):
        '''Test if extract_u_nk assign the attr correctly'''
        dataset = load_benzene()
        u_nk = extract_u_nk(dataset['data']['Coulomb'][0], 310)
        new_u_nk = slicing(u_nk)
        assert new_u_nk.attrs['temperature'] == 310
        assert new_u_nk.attrs['energy_unit'] == 'kT'

    def test_statistical_inefficiency(self, dhdl):
        '''Test if extract_u_nk assign the attr correctly'''
        dataset = load_benzene()
        dhdl = extract_dHdl(dataset['data']['Coulomb'][0], 310)
        new_dhdl = statistical_inefficiency(dhdl)
        assert new_dhdl.attrs['temperature'] == 310
        assert new_dhdl.attrs['energy_unit'] == 'kT'

    def test_equilibrium_detection(self, dhdl):
        '''Test if extract_u_nk assign the attr correctly'''
        dataset = load_benzene()
        dhdl = extract_dHdl(dataset['data']['Coulomb'][0], 310)
        new_dhdl = equilibrium_detection(dhdl)
        assert new_dhdl.attrs['temperature'] == 310
        assert new_dhdl.attrs['energy_unit'] == 'kT'

@pytest.mark.parametrize(('method', 'size'), [('dhdl', 2001),
                                              ('dhdl_all', 2001),
                                              ('dE', 2001)])
def test_decorrelate_u_nk_single_l(gmx_benzene_u_nk_fixture, method, size):
    assert len(decorrelate_u_nk(gmx_benzene_u_nk_fixture, method=method,
                                drop_duplicates=True,
                                sort=True)) == size

@pytest.mark.parametrize(('method', 'size'), [('dhdl', 501),
                                              ('dhdl_all', 1001),
                                              ('dE', 334)])
def test_decorrelate_u_nk_multiple_l(gmx_ABFE_u_nk, method, size):
    assert len(decorrelate_u_nk(gmx_ABFE_u_nk, method=method,)) == size

def test_decorrelate_dhdl_single_l(gmx_benzene_u_nk_fixture):
    assert len(decorrelate_dhdl(gmx_benzene_u_nk_fixture, drop_duplicates=True,
                                sort=True)) == 2001

def test_decorrelate_dhdl_multiple_l(gmx_ABFE_dhdl):
    assert len(decorrelate_dhdl(gmx_ABFE_dhdl,)) == 501

def test_raise_non_uk(gmx_ABFE_dhdl):
    with pytest.raises(ValueError):
        decorrelate_u_nk(gmx_ABFE_dhdl, )
