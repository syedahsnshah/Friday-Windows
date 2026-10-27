"""Regression checks for existing-browser reuse; never opens any browser."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from core import friday_browser as bridge
from core.friday_workspace import Workspace
from core.friday_operator import run_job, collect_existing_download
from actions.browser_control import browser_control


class ExistingBrowserTests(unittest.TestCase):
    def test_multiple_browsers_ask_choice_and_saved_choice_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bridge, 'preferences_path', return_value=Path(tmp)/'choice.json'), patch.object(bridge, 'running_browsers', return_value=['chrome', 'safari']):
            with self.assertRaisesRegex(RuntimeError, 'Which existing browser'):
                bridge.select_browser()
            self.assertEqual(bridge.remember_browser('safari'), 'safari')
            self.assertEqual(bridge.select_browser(), 'safari')

    def test_no_browser_or_closed_preferred_does_not_launch(self):
        with patch.object(bridge, 'running_browsers', return_value=[]):
            with self.assertRaisesRegex(RuntimeError, 'No supported existing'):
                bridge.select_browser()
            with self.assertRaisesRegex(RuntimeError, 'will not open'):
                bridge.select_browser('chrome')

    def test_missing_window_is_checked_before_activation(self):
        with patch.object(bridge, 'running_browsers', return_value=['chrome']), patch.object(bridge, '_script', return_value='0') as script:
            with self.assertRaisesRegex(RuntimeError, 'no existing window'):
                bridge.ExistingPage('chrome')
            self.assertEqual(script.call_count, 1)
            self.assertNotIn('activate', script.call_args.args[0])

    def test_context_exit_leaves_user_browser_open(self):
        page=MagicMock()
        with patch.object(bridge,'select_browser',return_value='chrome'),patch.object(bridge,'ExistingPage',return_value=page):
            context=bridge.ExistingContext()
            context.close()
            self.assertEqual(context.pages,[page])
            page.close.assert_not_called()
            with self.assertRaisesRegex(RuntimeError,'will not create'):
                context.new_page()

    def test_existing_browser_unavailable_pauses_job_instead_of_falling_back_to_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Workspace(tmp,Path(tmp)/'outputs')
            with patch.object(store,'_enqueue'):
                job=store.submit('Create image','image')
            store.update(job['id'],status='running')
            with patch('core.friday_operator.open_existing_context',side_effect=RuntimeError('Choose existing browser')):
                self.assertFalse(run_job(store,job['id']))
            self.assertEqual(store.get(job['id'])['status'],'paused')

    def test_browser_voice_tool_never_uses_legacy_launch_registry(self):
        with patch.object(bridge,'ExistingContext') as context:
            result=browser_control({'action':'new_tab','url':'https://gemini.google.com'})
            context.assert_not_called()
            self.assertIn('preserves',result)
        with patch.object(bridge,'ExistingContext') as context:
            page=context.return_value.pages.__getitem__.return_value
            browser_control({'action':'go_to','url':'gemini.google.com'})
            page.goto.assert_called_once_with('https://gemini.google.com')
            page.close.assert_not_called()

    def test_only_one_new_matching_download_can_be_collected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);downloads=root/'Downloads';downloads.mkdir();output=root/'output';output.mkdir()
            old=downloads/'old.csv';old.write_text('old\n')
            stat=old.stat()
            job={'steps':[{'output':'csv'}],'step':0,'output':str(output),'download_baseline':{str(old):[stat.st_size,stat.st_mtime_ns]}}
            with self.assertRaises(ValueError):
                collect_existing_download(job,'latest_download',downloads)
            new=downloads/'new.csv';new.write_text('spend,revenue\n10,30\n')
            path=collect_existing_download(job,'latest_download',downloads)
            self.assertEqual(path.read_text(),new.read_text())
            self.assertTrue(new.exists())
            job['collected_downloads'] = {}
            (downloads/'another.csv').write_text('another\n')
            with self.assertRaisesRegex(ValueError,'one newly'):
                collect_existing_download(job,'latest_download',downloads)
            with self.assertRaises(ValueError):
                collect_existing_download(job,str(old),downloads)
