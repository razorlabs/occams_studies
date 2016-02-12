"""
Comprehensive upgrade from A-Z
"""

import argparse
import os
import sys
from subprocess import check_call

from sqlalchemy.engine.url import URL


HERE = os.path.abspath(os.path.dirname(__file__))

FILE_CODES = os.path.join(HERE, 'scripts', 'choice2codes.sql')
FILE_VARS = os.path.join(HERE, 'scripts', 'varnames.sql')
FILE_LABFIX = os.path.join(HERE, 'scripts', 'lab_fix.sql')
FILE_MERGE = os.path.join(HERE, 'scripts', 'mergedb.py')
FILE_TRIGGERS = os.path.join(HERE, 'triggers', 'setup.py')
FILE_ALEMBIC = os.path.join(HERE, '..', 'alembic.ini')


cli = argparse.ArgumentParser(description='Fully upgrades the database')
cli.add_argument('-U', dest='user', metavar='USER:PW')
cli.add_argument('-O', dest='owner', metavar='OWNER:PW')
cli.add_argument('--phi', metavar='DB', help='PHI database')
cli.add_argument('--fia', metavar='DB', help='FIA database')
cli.add_argument('--target', metavar='DB', help='Merged database')


def main(argv):
    args = cli.parse_args(argv[1:])

    oid, _, opw = args.owner.partition(':')

    psql = '/usr/pgsql-9.3/bin/psql'

    for db in (args.fia, args.phi):
        url = str(URL('postgresql', username=oid, database=db))
        check_call([psql, '-f', FILE_CODES, '-d', url])
        check_call([psql, '-f', FILE_VARS, '-d', url])
        check_call([psql, '-f', FILE_LABFIX, '-d', url])

    # Merge the database
    check_call([sys.executable, FILE_MERGE] + argv[1:])

    # Upgrade the database
    url = str(URL(
        'postgresql', username=oid, password=opw, database=args.target))
    check_call(
        [sys.executable,
         '-m', 'alembic.config',
         '-c', FILE_ALEMBIC,
         '-x', 'db=' + url,
         'upgrade', 'head'])

    # Install triggers
    check_call([sys.executable, FILE_TRIGGERS] + argv[1:])

if __name__ == '__main__':
    main(sys.argv)
