#!/usr/bin/python3

import shutil
import yaml
import argparse
import tempfile
import os
import glob
from cookiecutter.main import cookiecutter
import subprocess

from datetime import datetime
import sys

def start_msg():
    print("This tool is designed to be used after 'charmcraft init' was initially run")

def cookie(output_dir, extra_context):
    cookiecutter(
        'aso_charm/',
        extra_context=extra_context,
        output_dir=output_dir)

def arg_parser():
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('charm_path', help='path to charm')
    return parser.parse_args()

def read_metadata_file(charm_dir):
    with open(f'{charm_dir}/metadata.yaml', 'r') as f:
        metadata = yaml.load(f, Loader=yaml.FullLoader)
    return metadata

def switch_dir():
    abspath = os.path.abspath(__file__)
    dname = os.path.dirname(abspath)
    os.chdir(dname)

def get_extra_context(charm_dir):
    metadata = read_metadata_file(charm_dir)
    charm_name = metadata['name']
    service_name = charm_name.replace('sunbeam-', '')
    service_name = service_name.replace('-operator', '')
    ctxt = {
        'service_name': service_name,
        'charm_name': charm_name}
    # XXX REMOVE
    ctxt['db_sync_command'] = 'ironic-dbsync --config-file /etc/ironic/ironic.conf create_schema'
    ctxt['ingress_port'] = 6385
    return ctxt

def sync_code(src_dir, target_dir):
    cmd = ['rsync', '-r', '-v', f'{src_dir}/', target_dir]
    subprocess.check_call(cmd)
    
def main() -> int:
    """Echo the input arguments to standard output"""
    start_msg()
    args = arg_parser()
    charm_dir = args.charm_path
    switch_dir()
    with tempfile.TemporaryDirectory() as tmpdirname:
        extra_context = get_extra_context(charm_dir)
        service_name = extra_context['service_name']
        cookie(
            tmpdirname,
            extra_context)
        src_dir = f"{tmpdirname}/{service_name}"
        shutil.copyfile(
            f'{src_dir}/src/templates/wsgi-template.conf.j2',
            f'{src_dir}/src/templates/wsgi-{service_name}-api.conf')
        sync_code(src_dir, charm_dir)
    return 0

if __name__ == '__main__':
    sys.exit(main()) 
