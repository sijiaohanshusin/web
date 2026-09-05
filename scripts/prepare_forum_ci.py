"""Provision a fresh loopback-only NodeBB/PostgreSQL CI fixture, never production."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / '.shots' / 'forum-runtime'
OUT = ROOT / '.shots' / 'forum-evidence'
NODEBB_COMMIT = '607f737bdcb0d894f09829870ff006f2f325b226'


def main():
    if os.environ.get('HEUESTA_FORUM_AUDIT') != '1' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Fresh disposable GitHub runner required; no production or shared host setup')
    if APP.exists():
        raise RuntimeError('Refusing to overwrite an existing forum checkout')
    if any(os.environ.get(key) for key in ('GMAIL_APP_PASSWORD', 'GMAIL_OAUTH_CLIENT_SECRET', 'NODEBB_DB_PASSWORD')):
        raise RuntimeError('Production/mail credentials must not be supplied')
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ | {'NODE_ENV': 'production', 'NODEBB_APP_DIR': str(APP),
                        'NODEBB_JWT_SECRET': 'dev-sso-secret-not-for-production'}

    def run(args, cwd=ROOT):
        subprocess.run(args, cwd=cwd, env=env, check=True)

    run(['git', 'clone', '--depth', '1', '--branch', 'v4.14.0', 'https://github.com/NodeBB/NodeBB.git', str(APP)])
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=APP, text=True).strip()
    assert commit == NODEBB_COMMIT
    shutil.copyfile(APP / 'install/package.json', APP / 'package.json')
    run(['npm', 'install', '--omit=dev', '--no-audit', '--no-fund'], APP)
    run(['npm', 'install', '--omit=dev', '--no-audit', '--no-fund',
         'nodebb-plugin-session-sharing@7.2.3', 'nodebb-theme-harmony@3.0.15'], APP)
    for package in (ROOT / 'ops/forum/plugins/nodebb-plugin-heuesta-mailbox', ROOT / 'scripts/forum_fixture'):
        packed = subprocess.check_output(['npm', 'pack', '--json', '--pack-destination', str(OUT)], cwd=package, text=True)
        filename = json.loads(packed)[0]['filename']
        run(['npm', 'install', '--omit=dev', '--no-audit', '--no-fund', str(OUT / filename)], APP)
    password = secrets.token_urlsafe(30)
    config = {
        'url': 'http://127.0.0.1:4567', 'secret': secrets.token_hex(32), 'database': 'postgres',
        'postgres:host': '127.0.0.1', 'postgres:port': 5432, 'postgres:username': 'heuesta_forum_ci',
        'postgres:password': 'disposable-forum-ci-only', 'postgres:database': 'heuesta_forum_ci', 'postgres:ssl': False,
        'admin:username': 'audit-admin', 'admin:password': password, 'admin:password:confirm': password,
        'admin:email': 'admin@example.invalid',
    }
    # Setup can print credentials. Its log is deliberately excluded from CI artifacts.
    with (OUT / 'setup.private.log').open('w') as log:
        result = subprocess.run(['node', 'nodebb', 'setup', json.dumps(config), '--skip-build'], cwd=APP, env=env,
                                stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError('Disposable NodeBB setup failed; credential-bearing command/log withheld')
    for script in ('localize.js', 'groups-v2.js'):
        run(['node', str(ROOT / 'ops/forum' / script)], APP)
    shutil.copyfile(ROOT / 'scripts/forum_fixture/configure.cjs', APP / 'heuesta-audit.cjs')
    run(['node', 'heuesta-audit.cjs'], APP)
    for plugin in ('nodebb-plugin-session-sharing', 'nodebb-plugin-heuesta-mailbox', 'nodebb-plugin-heuesta-ci-fixture'):
        run(['node', 'nodebb', 'activate', plugin], APP)
    run(['node', 'nodebb', 'build'], APP)
    print('Isolated forum prepared; no production settings or mail credentials used.')


if __name__ == '__main__':
    main()
