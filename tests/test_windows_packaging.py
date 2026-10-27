"""Portable checks for release data boundaries and writable-state upgrades."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

payload=load('windows_payload_test',ROOT/'packaging/windows/payload.py')
launcher=load('windows_launcher_test',ROOT/'packaging/windows/launcher.py')

class WindowsPackagingTests(unittest.TestCase):
    def make_project(self,root):
        for name in payload.TOP:
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('release content')
        for name,text in [('core/runtime_paths.py','value = 1'),('config/api_keys.json','PRIVATE_KEY'),
                          ('memory/long_term.json','PRIVATE_MEMORY'),('config/whatsapp_web/token.json','PRIVATE_SESSION'),
                          ('config/friday.ico','icon'),('dashboard/static/index.html','<p>dashboard</p>'),
                          ('memory/wake/vosk-model-small-en-us-0.15/am/final.mdl','wake model'),
                          ('memory/wake/vosk-model-small-en-us-0.15/conf/model.conf','model config')]:
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)

    def test_payload_excludes_private_state_and_includes_assets(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'source';self.make_project(root)
            dest=Path(d)/'payload';manifest=payload.stage_payload(root,dest)
            self.assertNotIn('config/api_keys.json',manifest['files'])
            self.assertNotIn('memory/long_term.json',manifest['files'])
            self.assertFalse((dest/'config/whatsapp_web').exists())
            self.assertIn('config/friday.ico',manifest['files'])
            self.assertIn('memory/wake/vosk-model-small-en-us-0.15/am/final.mdl',manifest['files'])

    def test_upgrade_preserves_customer_keys_and_memory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'source';self.make_project(root);dest=Path(d)/'payload'
            payload.stage_payload(root,dest);app=launcher.prepare(dest,Path(d)/'state')
            key=app/'config/api_keys.json';key.write_text('{"customer":"own-key"}')
            memory=app/'memory/long_term.json';memory.write_text('{"customer":"own-memory"}')
            (root/'ui.py').write_text('updated UI');payload.stage_payload(root,dest)
            launcher.prepare(dest,Path(d)/'state')
            self.assertEqual((app/'ui.py').read_text(),'updated UI')
            self.assertEqual(json.loads(key.read_text()),{'customer':'own-key'})
            self.assertEqual(json.loads(memory.read_text()),{'customer':'own-memory'})

    def test_rejects_payload_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'source';self.make_project(root);dest=Path(d)/'payload'
            payload.stage_payload(root,dest);(dest/'ui.py').write_text('unexpected modification')
            with self.assertRaisesRegex(ValueError,'verification'):launcher.prepare(dest,Path(d)/'state')

    def test_rejects_manifest_escape(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('../outside','/outside','C:/outside','folder\\outside'):
                with self.assertRaises(ValueError):launcher.safe_target(Path(d),name)

    def test_rejects_symlink_target(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'state';root.mkdir();elsewhere=Path(d)/'other';elsewhere.mkdir()
            try:(root/'config').symlink_to(elsewhere,target_is_directory=True)
            except OSError:self.skipTest('Creating symlinks is unavailable')
            with self.assertRaises(ValueError):launcher.safe_target(root,'config/example.py')

    def test_runtime_root_is_writable_launcher_location_when_frozen(self):
        from core.runtime_paths import application_root
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'FRIDAY_RUNTIME_DIR':d}), patch.object(sys,'frozen',True,create=True):
            self.assertEqual(application_root(),Path(d).resolve())
            config=load('test_release_config',ROOT/'memory/config_manager.py')
            config.save_api_keys('customer-provided-example')
            self.assertEqual(config.CONFIG_FILE.parent.parent,Path(d).resolve())
            self.assertEqual(config.get_gemini_key(),'customer-provided-example')

    def test_source_root_is_unchanged_without_launcher_override(self):
        from core.runtime_paths import application_root
        with patch.dict(os.environ,{},clear=True),patch.object(sys,'frozen',False,create=True):
            self.assertEqual(application_root(),ROOT)

    def test_installer_identity_matches_current_release(self):
        text=(ROOT/'packaging/windows/setup_installer.iss').read_text()
        self.assertIn(f'#define MyAppVersion "{payload.VERSION}"',text)
        self.assertIn(f'#define MyAppPublisher "{payload.PUBLISHER}"',text)
        self.assertNotIn('us commerce',text.lower())
        self.assertIn('PrivilegesRequired=lowest',text)
        self.assertIn('DefaultDirName={localappdata}',text)

if __name__=='__main__':unittest.main()
