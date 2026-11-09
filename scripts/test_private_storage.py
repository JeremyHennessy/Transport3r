"""Storage-path behavior only; no actual Windows ACL or hosting acceptance."""
import pathlib
import tempfile
import unittest
from private_storage import workspace_directory


class PrivateStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name);self.home=self.root/'home';self.repo=self.root/'repo'
        self.options={'environ':{},'home':self.home,'project_root':self.repo}

    def test_default_private_directory_is_outside_repo_on_each_platform(self):
        for platform,suffix in [('linux','.local/share'),('darwin','Library/Application Support'),('win32','AppData/Local')]:
            with self.subTest(platform=platform):
                value=workspace_directory(platform=platform,**self.options)
                self.assertEqual(value,self.home/suffix/'Transport3r/private-workspace')
                self.assertFalse(value.exists())

    def test_explicit_and_environment_paths_are_used_without_moving_files(self):
        selected=self.root/'private'
        self.assertEqual(workspace_directory(selected,**self.options),selected)
        self.assertEqual(workspace_directory(**{**self.options,'environ':{'TRANSPORT3R_PRIVATE_DATA':str(selected)}}),selected)
        self.assertFalse(selected.exists())

    def test_legacy_storage_requires_explicit_migration_decision(self):
        old=self.repo/'warehouse/private/workspace/workspace.sqlite';old.parent.mkdir(parents=True);old.write_bytes(b'unchanged')
        with self.assertRaisesRegex(ValueError,'Legacy private workspace'):workspace_directory(**self.options)
        self.assertEqual(workspace_directory(self.root/'private',**self.options),self.root/'private')
        self.assertEqual(old.read_bytes(),b'unchanged')

    def test_repository_static_relative_base_and_symlink_paths_are_rejected(self):
        for value in (self.repo,self.repo/'warehouse/private/workspace',self.root/'public/private',self.root/'dist'):
            with self.subTest(value=value),self.assertRaises(ValueError):workspace_directory(value,**self.options)
        with self.assertRaises(ValueError):workspace_directory(platform='linux',**{**self.options,'environ':{'XDG_DATA_HOME':'relative'}})
        link=self.root/'link';target=self.root/'target';target.mkdir();link.symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError):workspace_directory(link,**self.options)

if __name__=='__main__':unittest.main()
