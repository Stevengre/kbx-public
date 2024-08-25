import glob
import shutil
import time
import os
from pathlib import Path
import subprocess
import json
import contextlib
import io
from pyk.kast.inner import KToken
import re

from kbx.generator import BXGenerator

os.chdir(os.path.dirname(os.path.abspath(__file__)))

F2P_PATH = Path("evaluation/families2persons/families-to-persons.k")
F2P_WORKSPACE = Path("evaluation/families2persons/families-to-persons-kbx-workspace")
F2P_FORWARD = F2P_WORKSPACE / "forward" / "families-to-persons.k"
F2P_BACKWARD = F2P_WORKSPACE / "backward" / "families-to-persons.k"
F2P_KBX = F2P_WORKSPACE / "kbx.py"
F2P_F = F2P_WORKSPACE / '..' / 'example.family'
F2P_P = F2P_WORKSPACE / '..' / 'example.person'
F2P_CMD = ['python', F2P_KBX]
H2U_PATH = Path("evaluation/hcsp2uml/hcsp-to-sequence.k")
H2U_WORKSPACE = Path("evaluation/hcsp2uml/hcsp-to-sequence-kbx-workspace")
H2U_FORWARD = H2U_WORKSPACE / "forward" / "hcsp-to-sequence.k"
H2U_BACKWARD = H2U_WORKSPACE / "backward" / "hcsp-to-sequence.k"
H2U_KBX = H2U_WORKSPACE / "kbx.py"
H2U_H = H2U_WORKSPACE / '..' / 'example.hcsp'
H2U_H_100 = H2U_WORKSPACE / '..' / 'example-100.hcsp'
H2U_H_1000 = H2U_WORKSPACE / '..' / 'example-1000.hcsp'
H2U_S = H2U_WORKSPACE / '..' / 'example.plantuml'
H2U_CMD = ['python', H2U_KBX]

def suppress_prints(func, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)


class Timer:
    message = ""

    def __init__(self, message="Execution time:"):
        self.message = message

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, *args):
        self.end_time = time.time()
        self.execution_time = (self.end_time - self.start_time) * 1000
        print(f"{self.message}: {self.execution_time:.3f} ms")


def count_lines(path: Path, language="Python") -> int:
    result = subprocess.run(['cloc', f"--force-lang={language}", '--json', path], capture_output=True, text=True)
    if result.returncode != 0:
        IOError(f"Error: {result.stderr}")
    data = json.loads(result.stdout)
    return data['SUM']['code']


def count_words(path: Path) -> int:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with path.open() as file:
        content = file.read()
        words = re.findall(r'\b\w+\b', content)
        return len(words)


def run_cmd(cmd, message=""):
    with Timer(message):
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise IOError(f"Error: {result.stderr}")
    return result.stdout


def clear_evaluation_folder():
    root_dir = Path("evaluation")
    file_patterns = ["*.synchronized", "*.creation", "*.proof*", "*.with_hint"]
    for pattern in file_patterns:
        for filepath in glob.glob(os.path.join(root_dir, "**", pattern), recursive=True):
            try:
                os.remove(filepath)
                print(f"Deleted file: {filepath}")
            except OSError as e:
                print(f"Error deleting file {filepath}: {e}")

    folder_patterns = ["proof", "families-to-persons-kbx-workspace", "hcsp-to-sequence-kbx-workspace"]
    # folder_patterns = ["proof"]
    for folder_name in folder_patterns:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            if folder_name in dirnames:
                folder_path = os.path.join(dirpath, folder_name)
                try:
                    shutil.rmtree(folder_path)
                    print(f"Deleted folder: {folder_path}")
                except OSError as e:
                    print(f"Error deleting folder {folder_path}: {e}")


if __name__ == '__main__':
    clear_evaluation_folder()
    print('------ Families & Persons ------')
    print(f"Families & Persons -> Lines of Code: {count_lines(F2P_PATH, 'C')}")
    print(f"Families & Persons -> Number of Words: {count_words(F2P_PATH)}")
    print("Families & Persons -> Generating BX Workspace ...")
    default_value = {}  # {'?KbxGenTodo0': "\"Smith\""}
    generator = BXGenerator(F2P_PATH,
                            'k',
                            KToken('.Famlies', 'Families'),
                            ['.Families', r',\s*\.FamilyMembers', '.FamilyMembers', r',\s*\ ~> .K'],
                            'person',
                            'Persons',
                            [r',\s*\.Persons'],
                            default_value)
    with Timer("Families & Persons -> Generation Time"):
        suppress_prints(generator.generate)
    print(f"Families & Persons -> Number of Words for Generated Definitions: {count_words(F2P_FORWARD) + count_words(F2P_BACKWARD)}")
    print(f"Families & Persons -> Initialising BX Workspace ...")
    # for faster initialisation, remove '-O3' '--gen-glr-bison-parser' from F2P_KBX
    with open(F2P_KBX, 'r+') as f:
        content = f.read()
        content = content.replace("'-O3', '--gen-glr-bison-parser', ", '')
        f.seek(0)
        f.write(content)
        f.truncate()
    run_cmd(F2P_CMD + ['init'], "Families & Persons -> Initialisation Time")
    print(f"Families & Persons -> Synchronizing & Verifying example.family and example.person BX ...")
    run_cmd(F2P_CMD + ['trans', 'forward', F2P_F, F2P_P], "Families & Persons -> Forward Synchronisation Time")
    print(f"Families & Persons -> Forward Synchronization Result: example.person.synchronized")
    run_cmd(F2P_CMD + ['trans', 'backward', F2P_P, F2P_F], "Families & Persons -> Backward Synchronisation Time")
    print(f"Families & Persons -> Backward Synchronization Result: example.family.synchronized")
    print("------ HCSP & PlantUML ------")
    print(f"HCSP & PlantUML -> Lines of Code: {count_lines(H2U_PATH, 'C')}")
    print(f"HCSP & PlantUML -> Number of Words: {count_words(H2U_PATH)}")
    print("HCSP & PlantUML -> Generating BX Workspace ...")
    default_value = {'?KbxGenTodo0': '#token("placeholdervar","Id")',
                     '?KbxGenTodo1': "0",
                     '?KbxGenTodo2': '#token("placeholdervar","Id")',
                     '?KbxGenTodo3': "0",
                     '?KbxGenTodo4': '#token("placeholder","Id")',
                     '?KbxGenTodo5': '#token("placeHolderHybrid","Hybrid")',
                     '?KbxGenTodo6': '#token("placeHolderHybrid","Hybrid")',
                     }
    generator = BXGenerator(H2U_PATH,
                            'csp-program',
                            KToken('.CSP', 'CSP'),
                            [r'\$\.CSPCommunicationInterrupts', r';\s*\.CSPProcess', r',\s*\.ContinuousAssignments', '.CSP'],
                            'uml-sequence',
                            'SequenceStatements',
                            [r'\.SequenceStatements'],
                            default_value)
    with Timer("HCSP & PlantUML -> Generation Time"):
        suppress_prints(generator.generate)

    print(f"HCSP & PlantUML -> Number of Words for Forward Definition: {count_words(H2U_FORWARD)}")
    print(f"HCSP & PlantUML -> Number of Words for Backward Definition: {count_words(H2U_BACKWARD)}")
    print(f"HCSP & PlantUML -> Number of Words for Generated Definitions: {count_words(H2U_FORWARD) + count_words(H2U_BACKWARD)}")
    print(f"HCSP & PlantUML -> Initialising BX Workspace ...")
    # for faster initialisation, remove '-O3' '--gen-glr-bison-parser' from H2U_KBX
    with open(H2U_KBX, 'r+') as f:
        content = f.read()
        content = content.replace("'-O3', '--gen-glr-bison-parser', ", '')
        f.seek(0)
        f.write(content)
        f.truncate()
    run_cmd(H2U_CMD + ['init', '--allow-proof-hints'], "HCSP & PlantUML -> Initialisation Time")
    print(f"HCSP & PlantUML -> Synchronizing & Verifying example.hcsp and example.plantuml BX ...")
    run_cmd(H2U_CMD + ['trans', 'forward', H2U_H, str(H2U_S) + '.creation'], "HCSP & PlantUML -> Forward Creation Time")
    print(f"HCSP & PlantUML -> Forward Creation Result: example.plantuml.creation")
    run_cmd(H2U_CMD + ['trans', 'forward', H2U_H, str(H2U_S) + '.creation.with_hint', '--proof-hints'], "HCSP & PlantUML -> Forward Creation Time with Proof Hints")
    print(f"HCSP & PlantUML -> Forward Creation Result with Proof Hints: example.hcsp.proof & example.plantuml.creation.with_hint")
    run_cmd(H2U_CMD + ['trans', 'forward', H2U_H_100, str(H2U_S) + '.100.creation'], "HCSP & PlantUML -> Forward Creation Time -- 100 Lines of Code")
    print(f"HCSP & PlantUML -> Forward Creation Result: example.plantuml.100.creation")
    run_cmd(H2U_CMD + ['trans', 'forward', H2U_H_1000, str(H2U_S) + '.1000.creation'], "HCSP & PlantUML -> Forward Creation Time -- 1000 Lines of Code")
    print(f"HCSP & PlantUML -> Forward Creation Result: example.plantuml.1000.creation")
    run_cmd(H2U_CMD + ['trans', 'backward', H2U_S, str(H2U_H) + '.creation'], "HCSP & PlantUML -> Backward Creation Time")
    print(f"HCSP & PlantUML -> Backward Creation Result: example.hcsp.creation")
    run_cmd(H2U_CMD + ['trans', 'forward', H2U_H, H2U_S], "HCSP & PlantUML -> Forward Synchronization Time")
    print(f"HCSP & PlantUML -> Forward Synchronization Result: example.plantuml.synchronized")
    run_cmd(H2U_CMD + ['trans', 'backward', H2U_S, H2U_H], "HCSP & PlantUML -> Backward Synchronization Time")
    print(f"HCSP & PlantUML -> Backward Synchronization Result: example.hcsp.synchronized")





