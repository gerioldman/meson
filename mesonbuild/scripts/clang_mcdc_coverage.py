# Copyright 2017 The Meson development team

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

from mesonbuild import environment, mesonlib

import argparse, re, sys, os, subprocess, pathlib, stat
import json
import shutil
import xml.etree.ElementTree as et
import typing as T
import concurrent.futures

def createReportForTest(test, log_dir, regex) -> None:
    # Skip non-executable targets as those cannot have Testwell CTC++ coverage outputs
    if test["type"] != "executable":
        return
    # Clang outputs a .profraw file after test executation
    # Construct the names of these files
    executable_file_name = test["filename"][0]
    profraw_file_name = test["filename"][0] + ".profraw"
    profdata_file_name = test["filename"][0] + ".profdata"
    coverage_txt = test["filename"][0] + ".coverage.txt"
    # Check for the existence of .profraw which means coverage was enabled and the test was ran
    if not os.path.isfile(profraw_file_name):
        return
    # Generate profdata file
    if os.path.isfile(profraw_file_name):
        subprocess.run(['llvm-profdata', 'merge', '-sparse', profraw_file_name, '-o', profdata_file_name ])
    if os.path.isfile(profdata_file_name):
        cmd = ['llvm-cov', 'report', '-object', executable_file_name, f'-instr-profile={profdata_file_name}', '--show-mcdc-summary', '--summary-only']
        if regex != '':
            cmd.append(f'--ignore-filename-regex={regex}')
        output = subprocess.run(cmd, capture_output=True)
        handle = open(coverage_txt,'w')
        handle.write(output.stdout.decode('UTF-8'))
        handle.close()


def mcdc_coverage(source_root: str, subproject_root: str, build_root: str, log_dir: str, info_dir: str, regex: str) -> int:
    exitcode = 0
    # Load intro-targets.json to look for target_filename.suffix.profraw files
    tests = json.load(open(os.path.join(info_dir,'intro-targets.json')))
    merge_cmd = ['llvm-profdata', 'merge', '-sparse', '-o', f'{log_dir}/coverage.profdata']
    report_cmd = ['llvm-cov', 'report', '--show-mcdc-summary', '--summary-only', f'-instr-profile={log_dir}/coverage.profdata']
    show_cmd = ['llvm-cov', 'show', '--show-mcdc',
    '--show-branches=count', '--format', 'html', f'-instr-profile={log_dir}/coverage.profdata']
    for test in tests:
        if test["type"] != "executable":
            continue
        # Clang outputs a .profraw file after test executation
        # Construct the names of these files
        executable_file_name = test["filename"][0]
        profraw_file_name = test["filename"][0] + ".profraw"
        if not os.path.isfile(executable_file_name):
            continue
        if not os.path.isfile(profraw_file_name):
            continue
        merge_cmd.append(profraw_file_name)
        report_cmd.append('-object')
        report_cmd.append(executable_file_name)
        show_cmd.append('-object')
        show_cmd.append(executable_file_name)
    
    if regex != '':
        report_cmd.append(f'--ignore-filename-regex={regex}')
        show_cmd.append(f'--ignore-filename-regex={regex}')

    subprocess.run(merge_cmd)
    output = subprocess.run(report_cmd, capture_output=True)
    handle = open(f'{log_dir}/coverage.txt','w')
    handle.write(output.stdout.decode('UTF-8'))
    handle.close()
    output = subprocess.run(show_cmd, capture_output=True)
    handle = open(f'{log_dir}/coverage.html','wb')
    handle.write(output.stdout)
    handle.close()

    return exitcode

def run(args: T.List[str]) -> int:
    if not os.path.isfile('build.ninja'):
        print('Clang MC/DC Coverage currently only works with the Ninja backend.')
        return 1
    parser = argparse.ArgumentParser(description='Generate Clang MC/DC coverage reports')
    parser.add_argument('source_root')
    parser.add_argument('subproject_root')
    parser.add_argument('build_root')
    parser.add_argument('log_dir')
    parser.add_argument('info_dir')
    parser.add_argument('regex')
    options = parser.parse_args(args)
    return mcdc_coverage(options.source_root, options.subproject_root,
                        options.build_root, options.log_dir,
                        options.info_dir, options.regex)

if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))