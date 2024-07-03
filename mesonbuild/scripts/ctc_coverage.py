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

def createReportForTarget(ctcpost, target, log_dir) -> None:
    # Skip non-executable targets as those cannot have Testwell CTC++ coverage outputs
    if target["type"] != "executable":
        return
    # CTC++ coverage tool outputs a .sym file during compilation and a .dat during test executation
    # Construct the names of these files
    dat_file_name = target["filename"][0] + ".dat"
    sym_file_name = target["filename"][0] + ".sym"
    # Check for the existence of .sym which means coverage was enabled
    if not os.path.isfile(sym_file_name):
        return
    # Create subfolder for storing results identical to the one used in the build
    result_dir = os.path.join(log_dir, 'coverage_per_target', target["name"])
    if os.path.isdir(result_dir):
        print(f'WARNING: identical names used for targets: {target["name"]}, result won\'t be generated.')
        return
    else:
        os.mkdir(result_dir)
    
    txt_file_name = os.path.join(result_dir,'coverage.txt')
    xml_file_name = os.path.join(result_dir,'coverage.xml')
    # Create XML and TXT reports
    # .dat might not be created if the instrumented code was not called at all (0% coverage)
    if os.path.isfile(dat_file_name):
        subprocess.run( [ctcpost, sym_file_name, dat_file_name, '-x', xml_file_name,'-p',txt_file_name],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.STDOUT)
    else:
        subprocess.run( [ctcpost, sym_file_name,'-x', xml_file_name,'-p',txt_file_name],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.STDOUT)        
    # Read XML report for printing result to screen
    xml_root = et.parse(xml_file_name)
    multicondition_percentage = xml_root.getroot().find('overall_summary').find('ter')
    statement_percentage = xml_root.getroot().find('overall_summary').find('statement_ter')
    # Print report for executable
    print('{:<80} {:>10}% {:>5}%'.format(target["name"],statement_percentage.text,multicondition_percentage.text))
    # ctc2html is a Perl script so some work-around was needed
    ctchome = os.getenv('CTCHOME')
    subprocess.run(['perl',os.path.join(ctchome,'ctc2html.pl'),'-nsb','-i',txt_file_name,'-o',os.path.join(result_dir,'CTCHTML')],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT)


def ctc_coverage(source_root: str, subproject_root: str, build_root: str, log_dir: str, info_dir: str) -> int:
    outfiles = []
    exitcode = 0

    ctc, ctc_version, ctc_path = environment.find_ctc_coverage_tools()
    if ctc is None:
        exitcode = 1
    else:
        print(f'\nFound Testwell CTC++ version {ctc_version}')
        # Load intro-targets.json to look for target_filename.suffix.(sym|dat) files
        targets = json.load(open(os.path.join(info_dir,'intro-targets.json')))
        if ctc_version[0] == '9':
            # Delete previous results if they exist
            if os.path.isdir(os.path.join(log_dir,'coverage_per_target')):
                shutil.rmtree(os.path.join(log_dir,'coverage_per_target'),ignore_errors=False)

            # Create directory
            os.mkdir(os.path.join(log_dir, 'coverage_per_target'))
            # Print new line
            print()
            print('{:<80} {:>11} {:>6}'.format('Test name','Statement','MC/DC'))

            # Create the individual reports parallel
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [executor.submit(createReportForTarget, 'ctcpost', target, log_dir) for target in targets]
                results = [future.result() for future in concurrent.futures.as_completed(futures)]
            xml_files = []
            for target in targets:
                if os.path.isfile(os.path.join(log_dir, 'coverage_per_target', target["name"], 'coverage.xml')):
                    xml_files.append(os.path.join(log_dir, 'coverage_per_target', target["name"], 'coverage.xml'))

            optionfile_path = os.path.join(log_dir,'coverage.rsp')
            optionfile = open(optionfile_path, mode='w')
            optionfile.write( ' '.join(xml_files))
            optionfile.close()

            subprocess.run( ['ctcxmlmerge' ,f'@{optionfile_path}', '-p', os.path.join(log_dir,'coverage.txt'),'-x',os.path.join(log_dir,'coverage.xml')])
            os.remove(optionfile_path)
            ctchome = os.getenv('CTCHOME')
            subprocess.run(['perl',os.path.join(ctchome,'ctc2html.pl'),'-nsb','-i',os.path.join(log_dir,'coverage.txt'),'-o',os.path.join(log_dir,'coverage')])
        if ctc_version[0] == '1' and ctc_version[1] == '0':
            sym_files = []
            dat_files = []
            for target in targets:
                dat_file_name = target["filename"][0] + ".dat"
                sym_file_name = target["filename"][0] + ".sym"
                if os.path.isfile(sym_file_name):
                    sym_files.append(sym_file_name)
                if os.path.isfile(dat_file_name):
                    dat_files.append(dat_file_name)

            optionfile_path = os.path.join(log_dir,'coverage.rsp')
            optionfile = open(optionfile_path, mode='w')
            optionfile.write( ' '.join(sym_files + dat_files + ['-measures','mcdc,m,c,d,s,f','-nsb','-o',os.path.join(log_dir,'coverage')]))
            optionfile.close()
            subprocess.run( ['ctcreport' ,f'@{optionfile_path}'], capture_output=True)
            optionfile = open(optionfile_path, mode='w')
            optionfile.write( ' '.join(sym_files + dat_files + ['-measures','mcdc,m,c,d,s,f','-nsb','-o',os.path.join(log_dir,'coverage.xml'),'-template','example_xml']))
            optionfile.close()
            subprocess.run( ['ctcreport' ,f'@{optionfile_path}'], capture_output=True)
            optionfile = open(optionfile_path, mode='w')
            optionfile.write( ' '.join(sym_files + dat_files + ['-measures','mcdc,m,c,d,s,f','-nsb','-o',os.path.join(log_dir,'coverage.csv'),'-template','example_csv']))
            optionfile.close()
            subprocess.run( ['ctcreport' ,f'@{optionfile_path}'], capture_output=True)
            optionfile = open(optionfile_path, mode='w')
            optionfile.write( ' '.join(sym_files + dat_files + ['-measures','mcdc,m,c,d,s,f','-nsb','-o',os.path.join(log_dir,'coverage.md'),'-template','example_markdown']))
            optionfile.close()
            subprocess.run( ['ctcreport' ,f'@{optionfile_path}'], capture_output=True)
    return exitcode

def run(args: T.List[str]) -> int:
    if not os.path.isfile('build.ninja'):
        print('Testwell CTC++ Coverage currently only works with the Ninja backend.')
        return 1
    parser = argparse.ArgumentParser(description='Generate CTC++ coverage reports')
    parser.add_argument('source_root')
    parser.add_argument('subproject_root')
    parser.add_argument('build_root')
    parser.add_argument('log_dir')
    parser.add_argument('info_dir')
    options = parser.parse_args(args)
    return ctc_coverage(options.source_root, options.subproject_root,
                        options.build_root, options.log_dir,
                        options.info_dir)

if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))