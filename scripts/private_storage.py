"""Resolve private local storage outside Git, without silently moving old records."""
import argparse
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def workspace_directory(explicit=None, *, environ=None, platform=None, home=None, project_root=ROOT):
    env = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = pathlib.Path.home() if home is None else pathlib.Path(home)
    chosen = explicit or env.get('TRANSPORT3R_PRIVATE_DATA')
    legacy = pathlib.Path(project_root) / 'warehouse' / 'private' / 'workspace' / 'workspace.sqlite'
    if chosen is None and legacy.exists():
        raise ValueError('Legacy private workspace exists inside the repository. Stop the old service, back up '
                         'and migrate its complete private directory to a reviewed location outside Git, then '
                         'supply --data or TRANSPORT3R_PRIVATE_DATA. No records have been moved or deleted.')
    if chosen is None:
        if platform == 'win32':
            base = pathlib.Path(env.get('LOCALAPPDATA') or home / 'AppData' / 'Local')
        elif platform == 'darwin':
            base = home / 'Library' / 'Application Support'
        else:
            base = pathlib.Path(env.get('XDG_DATA_HOME') or home / '.local' / 'share')
        if not base.is_absolute():
            raise ValueError('Private data base must be an absolute directory')
        chosen = base / 'Transport3r' / 'private-workspace'
    raw = pathlib.Path(chosen).expanduser()
    if raw.is_symlink():
        raise ValueError('Private workspace directory must not be a symlink')
    value = raw.resolve()
    root = pathlib.Path(project_root).resolve()
    if value == root or root in value.parents or any(p.lower() in ('public', 'dist') for p in value.parts):
        raise ValueError('Private workspace storage must be outside the repository and public static paths')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?')
    try:
        print(workspace_directory(parser.parse_args().directory))
    except ValueError as error:
        parser.error(str(error))
