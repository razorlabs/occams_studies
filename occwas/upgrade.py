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
        dsn = "user={oid} password={opw} dbname={db}".format(**locals())
        check_call([psql, '-f', FILE_CODES, dsn], shell=True)
        check_call([psql, '-f', FILE_VARS,  dsn], shell=True)
        check_call([psql, '-f', FILE_LABFIX, dsn], shell=True)

    # Merge the database
    check_call([sys.executable, FILE_MERGE] + argv[1:], shell=True)

    # Upgrade the database
    url = str(URL(
        'postgresql', username=oid, password=opw, database=args.target))
    check_call(
        [sys.executable,
         '-m', 'alembic.config',
         '-c', FILE_ALEMBIC,
         '-x', 'db=' + url,
         'upgrade', 'head'],
        shell=True)

    # Install triggers
    check_call([sys.executable, FILE_TRIGGERS] + argv[1:], shell=True)

if __name__ == '__main__':
    main(sys.argv)
