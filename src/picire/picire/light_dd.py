# Copyright (c) 2016-2020 Renata Hodovan, Akos Kiss.
#
# Licensed under the BSD 3-Clause License
# <LICENSE.rst or https://opensource.org/licenses/BSD-3-Clause>.
# This file may not be copied, modified, or distributed except
# according to those terms.

import logging

from . import config_iterators
from . import config_splitters
from .abstract_dd import AbstractDD
from . import utils

logger = logging.getLogger(__name__)


class LightDD(AbstractDD):
    """
    Single process version of the Delta Debugging algorithm.
    """

    def __init__(self, test, cache=None, id_prefix=(),
                 split=config_splitters.zeller,
                 subset_first=True, subset_iterator=config_iterators.forward, complement_iterator=config_iterators.forward, **other_config):
        """
        Initialize a LightDD object.

        :param test: A callable tester object.
        :param cache: Cache object to use.
        :param id_prefix: Tuple to prepend to config IDs during tests.
        :param split: Splitter method to break a configuration up to n parts.
        :param subset_first: Boolean value denoting whether the reduce has to
            start with the subset-based approach or not.
        :param subset_iterator: Reference to a generator function that provides
            config indices in an arbitrary order.
        :param complement_iterator: Reference to a generator function that
            provides config indices in an arbitrary order.
        """
        cache = None

        AbstractDD.__init__(self, test, split, cache=cache, id_prefix=id_prefix, other_config=other_config)

        self._subset_iterator = subset_iterator
        self._complement_iterator = complement_iterator

        if subset_first:
            self._first_reduce, self._second_reduce = self._reduce_to_subset, self._reduce_to_complement
        else:
            self._first_reduce, self._second_reduce = self._reduce_to_complement, self._reduce_to_subset

    def _reduce_config(self, run, subsets, complement_offset):
        """
        Perform the reduce task in single process mode.

        :param run: The index of the current iteration.
        :param subsets: List of sets that the current configuration is split to.
        :param complement_offset: A compensation offset needed to calculate the
            index of the first unchecked complement (optimization purpose only).
        :return: Tuple: (list of subsets composing the failing config or None,
            next complement_offset).
        """
        next_subsets, complement_offset = self._first_reduce(run, subsets, complement_offset)
        if next_subsets is None:
            next_subsets, complement_offset = self._second_reduce(run, subsets, complement_offset)

        return next_subsets, complement_offset

    def _reduce_to_subset(self, run, subsets, complement_offset):
        """
        Perform a subset-based reduce task.

        :param run: The index of the current iteration.
        :param subsets: List of sets that the current configuration is split to.
        :param complement_offset: A compensation offset needed to calculate the
            index of the first unchecked complement (optimization purpose only).
        :return: Tuple: (list of subsets composing the failing config or None,
            next complement_offset).
        """
        n = len(subsets)
        for i in self._subset_iterator(n):
            if i is None:
                continue

            config_id = ('r%d' % run, 's%d' % i)
            complement = [c for si, s in enumerate(subsets) for c in s if si != i]
            subset = subsets[i]
            if (self.onepass):
                if (complement in self.delete_history):
                    continue
                else:
                    self.delete_history.append(subsets[i])
            log_to_print = utils.generate_log(subsets[i], "Try deleting(complement of)", print_idx=True, threshold=30)
            logger.info(log_to_print)

            # Get the outcome by testing it.
            outcome = self._test_config(subset, config_id)
            if outcome == self.PASS:
                # Interesting subset is found.
                log_to_print = utils.generate_log(subsets[i], "Deleted(complement of)", print_idx=True, threshold=30)
                logger.info(log_to_print)
                return [subsets[i]], 0

        return None, complement_offset

    def _reduce_to_complement(self, run, subsets, complement_offset):
        """
        Perform a complement-based reduce task.

        :param run: The index of the current iteration.
        :param subsets: List of sets that the current configuration is split to.
        :param complement_offset: A compensation offset needed to calculate the
            index of the first unchecked complement (optimization purpose only).
        :return: Tuple: (list of subsets composing the failing config or None,
            next complement_offset).
        """
        n = len(subsets)
        iterator = self._complement_iterator(n)
        for i in iterator:
            if i is None:
                continue
            i = int((i + complement_offset) % n)

            config_id = ('r%d' % run, 'c%d' % i)
            complement = [c for si, s in enumerate(subsets) for c in s if si != i]
            if (self.onepass):
                if (subsets[i] in self.delete_history):
                    continue
                else:
                    self.delete_history.append(subsets[i])
            log_to_print = utils.generate_log(subsets[i], "Try deleting", print_idx=True, threshold=30)
            logger.info(log_to_print)

            outcome = self._test_config(complement, config_id)
            if outcome == self.PASS:
                # Interesting complement is found.
                # In next run, start removing the following subset
                log_to_print = utils.generate_log(subsets[i], "Deleted", print_idx=True, threshold=30)
                logger.info(log_to_print)
                iterator.reset()
                return subsets[:i] + subsets[i + 1:], 0

        return None, complement_offset

