from __future__ import division, print_function, absolute_import

__version__ = '0.7.7'

# Clocks
try:
    # Python 3.3+ (PEP 418)
    from time import monotonic as monotonic_clock, perf_counter
except ImportError:
    import sys
    import time

    monotonic_clock = time.time
    if sys.platform == "win32":
        perf_counter = time.clock
    else:
        perf_counter = time.time

    del sys, time
__all__ = ['monotonic_clock', 'perf_counter']


from perf._utils import is_significant, python_implementation, python_has_jit  # noqa
__all__.extend(('is_significant', 'python_implementation', 'python_has_jit'))

from perf._bench import Run, Benchmark, BenchmarkSuite, add_runs  # noqa
__all__.extend(('Run', 'Benchmark', 'BenchmarkSuite', 'add_runs'))
