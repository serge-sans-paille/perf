from __future__ import print_function
import argparse
import collections
import os.path
import sys

import statistics

import perf.text_runner


def create_parser():
    parser = argparse.ArgumentParser(description='Display benchmark results.',
                                     prog='-m perf')
    subparsers = parser.add_subparsers(dest='action')


    def input_filenames(cmd):
        cmd.add_argument('-b', '--name',
                         help='only display the benchmark called NAME')
        cmd.add_argument('filenames', metavar='file.json',
                         type=str, nargs='+',
                         help='Benchmark file')

    # show
    cmd = subparsers.add_parser('show')
    cmd.add_argument('-q', '--quiet', action="store_true",
                     help='enable quiet mode')
    cmd.add_argument('-v', '--verbose', action="store_true",
                     help='enable verbose mode')
    cmd.add_argument('-m', '--metadata', dest='metadata',
                     action="store_true",
                     help="Show metadata.")
    cmd.add_argument('-g', '--hist', action="store_true",
                     help='display an histogram of samples')
    cmd.add_argument('-t', '--stats', action="store_true",
                     help='display statistics (min, max, ...)')
    input_filenames(cmd)

    # hist
    cmd = subparsers.add_parser('hist')
    cmd.add_argument('--extend', action="store_true",
                     help="Extend the histogram to fit the terminal")
    cmd.add_argument('-n', '--bins', type=int, default=None,
                     help='Number of histogram bars (default: 25, or less '
                          'depeding on the terminal size)')
    input_filenames(cmd)

    # compare, compare_to
    for command in ('compare', 'compare_to'):
        cmd = subparsers.add_parser(command)
        cmd.add_argument('-v', '--verbose', action="store_true",
                         help='enable verbose mode')
        cmd.add_argument('-m', '--metadata', dest='metadata',
                         action="store_true",
                         help="Show metadata.")
        cmd.add_argument('ref_filename', type=str,
                             help='Reference JSON file')
        cmd.add_argument('changed_filenames', metavar="changed_filename",
                             type=str, nargs='+',
                             help='Changed JSON file')

    # stats
    cmd = subparsers.add_parser('stats')
    input_filenames(cmd)

    # metadata
    subparsers.add_parser('metadata')

    # timeit
    cmd = subparsers.add_parser('timeit')
    timeit_runner = perf.text_runner.TextRunner(name='timeit', _argparser=cmd)
    cmd.add_argument('-s', '--setup', action='append', default=[],
                     help='setup statements')
    cmd.add_argument('stmt', nargs='+',
                     help='executed statements')

    # convert
    cmd = subparsers.add_parser('convert')
    cmd.add_argument('input_filename',
                     help='Filename of the input benchmark suite')
    cmd.add_argument('-o', '--output', metavar='OUTPUT_FILENAME',
                     dest='output_filename',
                     help='Filename where the output benchmark suite '
                          'is written',
                     required=True)
    cmd.add_argument('--include-benchmark', metavar='NAME',
                     help='Only keep benchmark called NAME')
    cmd.add_argument('--exclude-benchmark', metavar='NAME',
                     help='Remove the benchmark called NAMED')
    cmd.add_argument('--include-runs',
                     help='Only keep benchmark runs RUNS')
    cmd.add_argument('--exclude-runs',
                     help='Remove specified benchmark runs')
    cmd.add_argument('--remove-outliers', action='store_true',
                     help='Remove outlier runs')

    return parser, timeit_runner


def load_result(filename, default_name=None):
    result = perf.Benchmark.load(filename)

    if not result.name and filename != "-":
        name = filename
        if name.lower().endswith('.json'):
            name = name[:-5]
        if name:
            result.name = name
    if not result.name and default_name:
        result.name = default_name

    return result


def _result_sort_key(result):
    return (result.median(), result.name or '')


def _common_metadata(metadatas):
    if not metadatas:
        return dict()

    metadata = dict(metadatas[0])
    for run_metadata in metadatas[1:]:
        for key in set(metadata) - set(run_metadata):
            del metadata[key]
        for key in set(run_metadata) & set(metadata):
            if run_metadata[key] != metadata[key]:
                del metadata[key]
    return metadata


def _display_common_metadata(metadatas):
    if len(metadatas) < 2:
        return

    for metadata in metadatas:
        # don't display name as metadata, it's already displayed
        metadata.pop('name', None)

    common_metadata = _common_metadata(metadatas)
    if common_metadata:
        perf.text_runner._display_metadata(common_metadata,
                               header='Common metadata:')
        print()

    for key in common_metadata:
        for metadata in metadatas:
            metadata.pop(key, None)


def compare_results(args, benchmarks, sort_benchmarks):
    if sort_benchmarks:
        benchmarks.sort(key=_result_sort_key)

    ref_result = benchmarks[0]

    if sort_benchmarks:
        print("Reference (best): %s" % ref_result.name)
    else:
        print("Reference: %s" % ref_result.name)
        for index, result in enumerate(benchmarks[1:], 1):
            if index > 1:
                prefix = 'Changed #%s' % index
            else:
                prefix = 'Changed'
            print("%s: %s" % (prefix, result.name))
    print()

    if args.metadata:
        metadatas = [dict(benchmark.metadata) for benchmark in benchmarks]
        _display_common_metadata(metadatas)

        for result, metadata in zip(benchmarks, metadatas):
            perf.text_runner._display_metadata(metadata,
                                   header='%s metadata:' % result.name)
            print()

    # Compute medians
    ref_samples = ref_result.get_samples()
    ref_avg = ref_result.median()
    last_index = len(benchmarks) - 1
    for index, changed_result in enumerate(benchmarks[1:], 1):
        changed_samples = changed_result.get_samples()
        changed_avg = changed_result.median()
        text = ("Median +- std dev: [%s] %s -> [%s] %s"
                % (ref_result.name, ref_result.format(),
                   changed_result.name, changed_result.format()))

        # avoid division by zero
        if changed_avg == ref_avg:
            text = "%s: no change" % text
        elif changed_avg < ref_avg:
            text = "%s: %.1fx faster" % (text, ref_avg /  changed_avg)
        else:
            text= "%s: %.1fx slower" % (text, changed_avg / ref_avg)
        print(text)

        # significant?
        significant, t_score = perf.is_significant(ref_samples, changed_samples)
        if significant:
            print("Significant (t=%.2f)" % t_score)
        else:
            print("Not significant!")

        if index != last_index:
            print()


def cmd_metadata():
    from perf import metadata as perf_metadata
    metadata = {}
    perf_metadata.collect_metadata(metadata)
    perf.text_runner._display_metadata(metadata)


DataItem = collections.namedtuple('DataItem', 'benchmark title is_last')


class Benchmarks:
    def __init__(self):
        self.suites = []

    def load_benchmark_suites(self, filenames):
        for filename in filenames:
            suite = perf.BenchmarkSuite.load(filename)
            self.suites.append(suite)

    # FIXME: move this method to BenchmarkSuite?
    def include_benchmark(self, name):
        for suite in self.suites:
            if name not in suite:
                fatal_missing_benchmark(suite, name)
            for key in list(suite):
                if key != name:
                    del suite[key]

    def __len__(self):
        return sum(len(suite) for suite in self.suites)

    def __iter__(self):
        filenames = {os.path.basename(suite.filename) for suite in self.suites}
        if len(filenames) == len(self.suites):
            format_filename = os.path.basename
        else:
            # FIXME: try harder: try to get differente names by keeping only
            # the parent directory?
            format_filename = lambda filename: filename

        show_name = (len(self) > 1)
        show_filename = (len(self.suites) > 1)

        for suite_index, suite in enumerate(self.suites):
            filename = format_filename(suite.filename)
            last_suite = (suite_index == (len(self.suites) - 1))

            benchmarks = suite.get_benchmarks()
            for bench_index, benchmark in enumerate(benchmarks):
                if show_name:
                    title = benchmark.name
                    if show_filename:
                        title = "%s:%s" % (filename, title)
                else:
                    title = None
                last_benchmark = (bench_index == (len(benchmarks) - 1))
                is_last = (last_suite and last_benchmark)

                yield DataItem(benchmark, title, is_last)


def display_title(title):
    print(title)
    print("=" * len(title))
    print()


def load_benchmarks(args):
    data = Benchmarks()
    data.load_benchmark_suites(args.filenames)
    if args.name:
        data.include_benchmark(args.name)
    return data


def cmd_show(args):
    data = load_benchmarks(args)

    many_benchmarks = (len(data) > 1)

    if args.metadata:
        metadatas = [dict(item.benchmark.metadata) for item in data]
        _display_common_metadata(metadatas)

    if args.metadata or args.hist or args.stats or args.verbose:
        for index, item in enumerate(data):
            if item.title:
                display_title(item.title)

            if args.metadata:
                metadata = metadatas[index]
                perf.text_runner._display_metadata(metadata)
                print()

            perf.text_runner._display_benchmark(item.benchmark,
                                                hist=args.hist,
                                                stats=args.stats,
                                                runs=bool(args.verbose),
                                                check_unstable=not args.quiet)
            if not item.is_last:
                print()
    else:
        # simple output: one line
        for item in data:
            if item.title:
                prefix = '%s: ' % item.title
            else:
                prefix = ''

            if not args.quiet:
                warnings = perf.text_runner._warn_if_bench_unstable(item.benchmark)
                for line in warnings:
                    print(prefix + line)

            print("%s%s" % (prefix, item.benchmark))


def cmd_timeit(args, timeit_runner):
    import perf._timeit
    timeit_runner.args = args
    timeit_runner._process_args()
    perf._timeit.main(timeit_runner)


def cmd_stats(args):
    data = load_benchmarks(args)

    for item in data:
        if item.title:
            display_title(item.title)
        perf.text_runner._display_stats(item.benchmark)
        if not item.is_last:
            print()


def cmd_compare(args):
    ref_result = load_result(args.ref_filename, '<file#1>')
    results = [ref_result]
    for index, filename in enumerate(args.changed_filenames, 2):
        result = load_result(filename, '<file#%s>' % index)
        results.append(result)
    compare_results(args, results, args.action == 'compare')


def cmd_hist(args):
    data = load_benchmarks(args)
    benchmarks = [item.benchmark for item in data]

    perf.text_runner._display_histogram(benchmarks, bins=args.bins,
                                        extend=args.extend)


def fatal_missing_benchmark(suite, name):
    print("ERROR: The benchmark suite %s doesn't contain "
          "a benchmark called %r"
          % (suite.filename, name))
    sys.exit(1)


def cmd_convert(args):
    suite = perf.BenchmarkSuite.load(args.input_filename)

    if args.include_benchmark:
        remove = set(suite)
        name = args.include_benchmark
        try:
            remove.remove(name)
        except KeyError:
            fatal_missing_benchmark(suite, name)
        for name in remove:
            del suite[name]

    elif args.exclude_benchmark:
        name = args.exclude_benchmark
        try:
            del suite[name]
        except KeyError:
            fatal_missing_benchmark(suite, name)

    if args.include_runs or args.exclude_runs:
        if args.include_runs:
            runs = args.include_runs
            include = True
        else:
            runs = args.exclude_runs
            include = False
        try:
            only_runs = perf._parse_run_list(runs)
        except ValueError as exc:
            print("ERROR: %s (runs: %r)" % (exc, runs))
            sys.exit(1)
        for benchmark in suite.values():
            if include:
                old_runs = benchmark._runs
                max_index = len(old_runs) - 1
                runs = []
                for index in only_runs:
                    if index <= max_index:
                        runs.append(old_runs[index])
            else:
                runs = benchmark._runs
                max_index = len(runs) - 1
                for index in reversed(only_runs):
                    if index <= max_index:
                        del runs[index]
            if not runs:
                print("ERROR: Benchmark %r has no more run" % benchmark.name)
                sys.exit(1)
            benchmark._runs = runs

    if args.remove_outliers:
        for benchmark in suite.values():
            warmups = benchmark.warmups
            raw_samples = benchmark._get_raw_samples()

            median = statistics.median(raw_samples)
            min_sample = median * 0.95
            max_sample = median * 1.05

            new_runs = []
            for run in benchmark._runs:
                if all(min_sample <= sample <= max_sample
                       for sample in run[warmups:]):
                    new_runs.append(run)
            if not new_runs:
                print("ERROR: Benchmark %r has no more run after removing "
                      "outliers" % benchmark.name)
                sys.exit(1)
            benchmark._runs[:] = new_runs

    suite.dump(args.output_filename)


def main():
    parser, timeit_runner = create_parser()
    args = parser.parse_args()
    action = args.action
    if action == 'show':
        cmd_show(args)
    elif action in ('compare', 'compare_to'):
        cmd_compare(args)
    elif action == 'hist':
        cmd_hist(args)
    elif action == 'stats':
        cmd_stats(args)
    elif action == 'metadata':
        cmd_metadata()
    elif action == 'timeit':
        cmd_timeit(args, timeit_runner)
    elif action == 'convert':
        cmd_convert(args)
    else:
        parser.print_usage()
        sys.exit(1)


main()
