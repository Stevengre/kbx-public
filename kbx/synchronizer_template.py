
SYNC_TEMPLATE = """#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import subprocess
import os
import sys
import hashlib
import json
from pathlib import Path
from datetime import datetime
import tempfile
from pyk.kast.formatter import Formatter
from pyk.konvert import kore_to_kast
from pyk.kore.parser import KoreParser
from pyk.kore.syntax import App, Pattern
from pyk.kast.pretty import PrettyPrinter
from pyk.kast.outer import read_kast_definition
import codecs
import re

sys.setrecursionlimit(100000)

CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
BX_DEF = "${bx_def}"
forward_k_def = os.path.join(CURRENT_DIR, 'forward', BX_DEF)
backward_k_def = os.path.join(CURRENT_DIR, 'backward', BX_DEF)
forward_kompiled = os.path.join(CURRENT_DIR, 'forward', 'llvm-kompiled')
bakcward_kompiled = os.path.join(CURRENT_DIR, 'backward', 'llvm-kompiled')
kompile_forward = ['kompile', forward_k_def, '-O3', '--gen-glr-bison-parser', '-o', forward_kompiled, '--emit-json']
kompile_backward = ['kompile', backward_k_def, '-O3', '--gen-glr-bison-parser', '-o', bakcward_kompiled, '--emit-json']
krun_forward = ['krun', '--definition', forward_kompiled, '-o', 'kore']
krun_backward = ['krun', '--definition', bakcward_kompiled, '-o', 'kore']
HASH_FILE = os.path.join(CURRENT_DIR, 'file_hashes.json')
COMPLEMENTS_DIR = os.path.join(CURRENT_DIR, 'complements')
F_IN_CELL_NAME = '${f_in_cell_name}'
F_OUT_CELL_NAME = '${f_out_cell_name}'
F_IN_DELETE = ${f_in_delete}
F_OUT_DELETE = ${f_out_delete}
TEMP_PATH = os.path.join(CURRENT_DIR, 'temp.kore')


def calculate_file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, 'rb') as file:
        buffer = file.read()
        hasher.update(buffer)
    return hasher.hexdigest()


def load_hashes() -> dict:
    if Path(HASH_FILE).exists():
        with open(HASH_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_hashes(hashes: dict) -> None:
    with open(HASH_FILE, 'w') as f:
        json.dump(hashes, f, indent=4)


def has_file_changed(path: Path) -> bool:
    stored_hashes = load_hashes()
    current_hash = calculate_file_hash(path)
    if stored_hashes.get(str(path)) != current_hash:
        stored_hashes[str(path)] = current_hash
        save_hashes(stored_hashes)
        return True
    return False


def update_complements(path: Path, complement: str) -> None:
    stored_hashes = load_hashes()
    current_hash = calculate_file_hash(path)
    prev_hash = stored_hashes.get(str(path))
    if prev_hash:
        prev_complement_path = os.path.join(COMPLEMENTS_DIR, prev_hash)
        if os.path.exists(prev_complement_path):
            os.remove(prev_complement_path)
    complement_path = os.path.join(COMPLEMENTS_DIR, current_hash)
    with open(complement_path, 'w') as f:
        f.write(complement)
    stored_hashes[str(path)] = current_hash
    save_hashes(stored_hashes)


def init(allow_proof_hints: bool):
    # read the backward_k_def
    with open(backward_k_def, 'r') as f:
        content = f.read()
        # Check if there is '?KbxGenTodo' in the content
        if '?KbxGenTodo' in content:
            print(f"Error: Please complete the transformation definition in '{backward_k_def}' with default values.")
            sys.exit(1)
    # Delete the forward_kompiled and backward_kompiled directories
    if os.path.exists(forward_kompiled):
        subprocess.run(['rm', '-rf', forward_kompiled])
    if os.path.exists(bakcward_kompiled):
        subprocess.run(['rm', '-rf', bakcward_kompiled])
    # Run the kompile command
    print("Running kompile command for the definition of forward transformation...")
    if allow_proof_hints:
        kompile_forward.append('--llvm-proof-hint-instrumentation')
        kompile_backward.append('--llvm-proof-hint-instrumentation')
    result = subprocess.run(kompile_forward, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.stderr and b"Error" in result.stderr:
        print(f"Error: {result.stderr.decode()}")
        sys.exit(1)
    print("Running kompile command for the definition of backward transformation...")
    result = subprocess.run(kompile_backward, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.stderr and b"Error" in result.stderr:
        print(f"Error: {result.stderr.decode()}")
        sys.exit(1)
    print("Initialization operation performed.")


def get_cell_by_symbol(pat: Pattern, symbol) -> Pattern | None:
    result = None

    def _get_cell_by_symbol(p: Pattern) -> Pattern:
        nonlocal result
        if isinstance(p, App) and p.symbol == symbol:
            result = p
        return p

    pat.top_down(_get_cell_by_symbol)
    return result


def remove_pattern_text(text, replaced):
    result = []
    for r in replaced:
        text = re.sub(r, '', text)
    lines = text.split('\\n')
    for line in lines:
        if line.strip():
            result.append(line)
    return '\\n'.join(result)


def trans(proof_hints, trans_type, input_path, output_path):
    input_path = os.path.abspath(input_path)
    output_path = os.path.abspath(output_path)
    kdef = read_kast_definition(os.path.join(forward_kompiled, 'compiled.json'))
    formatter = Formatter(kdef)
    if not os.path.isfile(input_path):
        print(f"Error: Input file '{input_path}' does not exist.")
        sys.exit(1)

    def _run_cmd(print_hints, cmd, path, depth=-1, is_kore=False):
        hint_cmd = []
        if print_hints:
            hint_cmd = cmd + ['--proof-hint']
        if depth >= 0:
            cmd = cmd + ['--depth', str(depth)]
            hint_cmd = hint_cmd + ['--depth', str(depth)]
        if is_kore:
            cmd = cmd + ['--term', '--parser', 'cat']
            hint_cmd = hint_cmd + ['--term', '--parser', 'cat']
        cmd = cmd + [path]
        hint_cmd = hint_cmd + [path]
        if print_hints:
            result = subprocess.run(hint_cmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.stderr:
                print(f"Error: {result.stderr.decode()}")
                sys.exit(1)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            proof_path = str(path) + '.proof' + ('' if not depth else f'.{depth}') + f'.{timestamp}'
            with open(proof_path, 'w') as f:
                f.write(str(result.stdout))
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.stderr:
            print(f"Error: {result.stderr.decode()}")
            sys.exit(1)
        return result.stdout.decode()

    def _extract_cell(kore, cell_name) -> Pattern:
        kore = KoreParser(kore).pattern()
        cell = get_cell_by_symbol(kore, f"Lbl'-LT-'{cell_name}'-GT-'")
        return cell

    def _replace_cell(origin: Pattern, replaced: Pattern, cell_name: str) -> Pattern:
        def _replace_cell_aux(p: Pattern) -> Pattern:
            nonlocal replaced
            if isinstance(p, App) and p.symbol == f"Lbl'-LT-'{cell_name}'-GT-'":
                return replaced
            return p
        return origin.top_down(_replace_cell_aux)

    def _run_create_complements(path1, cmd1, path2, cmd2, cell2):
        if not os.path.exists(COMPLEMENTS_DIR):
            os.makedirs(COMPLEMENTS_DIR)
        if not os.path.exists(path1) and not os.path.exists(path2):
            raise Exception("Error: Both input and output files do not exist.")
        if not os.path.exists(path1):
            create_result = _run_cmd(proof_hints, cmd2, path2)
            update_complements(path2, create_result)
            print("Finished creating the complement for the input file...")
            return
        if not os.path.exists(path2):
            create_result = _run_cmd(proof_hints, cmd1, path1)
            update_complements(path1, create_result)
            print("Finished creating the complement for the output file...")
            return
        create_result = _run_cmd(proof_hints, cmd1, path1)
        create_kore = KoreParser(create_result).pattern()
        path2_kore = _run_cmd(False, cmd2, path2, 0)
        path2_kore = _extract_cell(path2_kore, cell2)
        continue_kore = _replace_cell(create_kore, path2_kore, cell2)
        with open(TEMP_PATH, 'w') as f:
            continue_kore.write(f)
        continue_result = _run_cmd(proof_hints, cmd2, TEMP_PATH, -1, True)
        update_complements(path2, continue_result)
        update_complements(path1, continue_result)
        print("Finished creating the complement...")

    def _run_krun(cmd1, in_cell_name, out_cell_name, to_delete):

        def _print_result(p: Pattern):
            cell = get_cell_by_symbol(p, f"Lbl'-LT-'{out_cell_name}'-GT-'")
            cell = kore_to_kast(kdef, cell.args[0])
            final_print = formatter.format(cell)
            final_print = codecs.escape_decode(final_print)[0].decode('utf-8')
            final_print = remove_pattern_text(final_print, to_delete)
            return final_print

        if not os.path.exists(output_path):
            with open(output_path, 'w') as f:
                complement_path = os.path.join(COMPLEMENTS_DIR, load_hashes().get(input_path))
                create_kore = KoreParser(open(complement_path).read()).pattern()
                f.write(_print_result(create_kore))
        elif out_cell_name == F_IN_CELL_NAME:
            complement_path = os.path.join(COMPLEMENTS_DIR, load_hashes().get(input_path))
            put_kore = KoreParser(open(complement_path).read()).pattern()
            new_output_path = output_path + '.synchronized'
            with open(new_output_path, 'w') as f:
                f.write(_print_result(put_kore))
        else:
            create_result = _run_cmd(False, cmd1, input_path, 0)
            input_kore = _extract_cell(create_result, in_cell_name)
            complement_path = os.path.join(COMPLEMENTS_DIR, load_hashes().get(output_path))
            continue_kore = KoreParser(open(complement_path).read()).pattern()
            continue_kore = _replace_cell(continue_kore, input_kore, in_cell_name)
            with open(TEMP_PATH, 'w') as f:
                continue_kore.write(f)
            continue_result = _run_cmd(proof_hints, cmd1, TEMP_PATH, -1, True)
            update_complements(input_path, continue_result)
            new_output_path = output_path + '.synchronized'
            with open(new_output_path, 'w') as f:
                f.write(_print_result(KoreParser(continue_result).pattern()))
        print("Finished synchronization...")

    if trans_type == 'forward':
        _run_create_complements(input_path, krun_forward, output_path, krun_backward, F_OUT_CELL_NAME)
        _run_krun(krun_forward, F_IN_CELL_NAME, F_OUT_CELL_NAME, F_OUT_DELETE)
    elif trans_type == 'backward':
        _run_create_complements(output_path, krun_forward, input_path, krun_backward, F_OUT_CELL_NAME)
        _run_krun(krun_backward, F_OUT_CELL_NAME, F_IN_CELL_NAME, F_IN_DELETE)
    else:
        print(f"Error: Invalid transformation direction '{trans_type}', should be 'forward' or 'backward'.")


def main():
    parser = argparse.ArgumentParser(description='KBX Script')
    subparsers = parser.add_subparsers(dest='command')

    # Subparser for the 'init' command
    init_parser = subparsers.add_parser('init', help='Initialization operation')
    init_parser.add_argument('--allow-proof-hints', action='store_true', help='Allow proof hints to be generated')

    # Subparser for the 'trans' command
    trans_parser = subparsers.add_parser('trans', help='Transform operation')
    trans_parser.add_argument('--proof-hints', action='store_true', help='Generate proof hints')
    trans_parser.add_argument('transformation_direction', type=str,
                              help='Direction of transformation: forward or backward')
    trans_parser.add_argument('input_path', type=str, help='Path to the input file')
    trans_parser.add_argument('output_path', type=str, help='Path to the output file')

    args = parser.parse_args()

    if args.command == 'init':
        init(args.allow_proof_hints)
    elif args.command == 'trans':
        trans(args.proof_hints, args.transformation_direction, args.input_path, args.output_path)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
    
"""