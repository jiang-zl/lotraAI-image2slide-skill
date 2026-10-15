"""Stdlib-only entry into the unchanged offline companion preparer."""
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--skill', type=Path, required=True)
p.add_argument('--project', type=Path, required=True)
p.add_argument('--companion', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
base_facts = {'isolated': bool(sys.flags.isolated), 'user_site_disabled': bool(sys.flags.no_user_site),
              'pillow_preinstalled': importlib.util.find_spec('PIL') is not None}
sys.path.insert(0, str(a.skill.resolve() / 'scripts'))
from core.runtime_bootstrap import prepare
from core.common import write_json

def normal_windows(path):
    text = str(path)
    if text.startswith('\\\\?\\UNC\\'):
        return Path('\\\\' + text[8:])
    return Path(text[4:]) if text.startswith('\\\\?\\') else Path(text)


def extended_windows(path):
    text = str(path)
    if text.startswith('\\\\?\\'):
        return text
    return '\\\\?\\UNC\\' + text[2:] if text.startswith('\\\\') else '\\\\?\\' + text


project, companion = a.project, a.companion
original_popen = subprocess.Popen
if os.name == 'nt':
    # Windows extended paths deliberately do not resolve "..". Pip uses such
    # wheel RECORD paths for Scripts entries, so installation needs normal
    # spelling. Actual numeric/OCR workers need extended spelling for deep
    # native-DLL paths. Adapt only this exact owned runtime's process argv.
    project, companion = normal_windows(project), normal_windows(companion)
    key = 'windows-' + platform.machine().lower() + '-cp312'
    companion_hash = hashlib.sha256((companion / 'Manifest.json').read_bytes()).hexdigest()
    runtime_exe = project / ('.lotraAI-build/toolchain/runtime-v1.14.0-' + key + '-' + companion_hash[:12] + '/Scripts/python.exe')
    def runtime_popen(argv, *args, **kwargs):
        if isinstance(argv, (list, tuple)) and argv and str(normal_windows(argv[0])).casefold() == str(runtime_exe).casefold():
            argv = list(argv)
            pip_install = '--require-hashes' in argv and '--no-index' in argv
            argv[0] = str(runtime_exe) if pip_install else extended_windows(runtime_exe)
        return original_popen(argv, *args, **kwargs)
    subprocess.Popen = runtime_popen
    base_facts['command_path_adapter'] = 'owned-runtime: normal pip paths; extended native-worker paths'

try:
    result = prepare(project, companion)
    result['bootstrap_base'] = base_facts
    write_json(a.out, result)
    print(json.dumps({'status': result['status'], 'bootstrap_base': base_facts}))
except Exception as error:
    write_json(a.out, {'status': 'FAIL', 'reason': str(error), 'bootstrap_base': base_facts})
    print(json.dumps({'status': 'FAIL', 'reason': str(error)}, ensure_ascii=True))
    raise SystemExit(1)
finally:
    subprocess.Popen = original_popen
