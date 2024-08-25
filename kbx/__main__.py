from argparse import ArgumentParser, Namespace
import logging
from typing import Final, Any
from pyk.utils import check_file_path, check_dir_path, ensure_dir_path
from pathlib import Path

_LOGGER: Final = logging.getLogger(__name__)
_LOG_FORMAT: Final = '%(levelname)s %(asctime)s %(name)s - %(message)s'


def main() -> None:
    parser = create_argument_parser()
    args = parser.parse_args()
    logging.basicConfig(level=_loglevel(args), format=_LOG_FORMAT)

    executor_name = 'exec_' + args.command.lower().replace('-', '_')
    if executor_name not in globals():
        raise AssertionError(f'Unimplemented command: {args.command}')

    execute = globals()[executor_name]
    execute(**vars(args))


def create_argument_parser() -> ArgumentParser:
    shared_args = ArgumentParser(add_help=False)
    shared_args.add_argument('--verbose', '-v', default=False, action='store_true', help='Verbose output.')
    shared_args.add_argument('--debug', default=False, action='store_true', help='Debug output.')

    parser = ArgumentParser(prog='kbx', description='KBX command line tool')

    command_parser = parser.add_subparsers(dest='command', required=True, help='Command to execute')

    # Generate Bidirectional Transformation Definitions
    gen_subparser = command_parser.add_parser('gen',
                                                help='generate bidirectional transformation K definition files.',
                                                parents=[shared_args])
    gen_subparser.add_argument(
        'input_file',
        type=file_path,
        help='Path to unidirectional transformation K definition file.',
    )
    gen_subparser.add_argument(
        '--output_dir',
        dest='output_dir',
        type=dir_path,
        default='none',
        help='Output directory path',
        required=False,
    )

    return parser


def exec_gen(
    input_file: str,
    output_dir: str = 'none',
    **kwargs: Any,
) -> None:
    if output_dir == 'none':
        output_dir = str(Path(input_file).parent)


def _loglevel(args: Namespace) -> int:
    if args.debug:
        return logging.DEBUG

    if args.verbose:
        return logging.INFO

    return logging.WARNING


def file_path(path: str) -> Path:
    p = Path(path)
    check_file_path(p)
    return p


def dir_path(s: str) -> Path:
    path = Path(s)
    ensure_dir_path(path)
    return path


if __name__ == '__main__':
    main()
