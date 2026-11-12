import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launch
import server


class LaunchTests(unittest.TestCase):
    def test_other_workspace_is_never_restarted(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(launch,'request',return_value=dict(appId='frame-workbench',home=temp,pid=999)):
            with self.assertRaisesRegex(RuntimeError,'其他工作区'):
                launch.health()

    def test_existing_server_is_reused(self):
        health=dict(pid=123)
        with patch.object(launch,'launcher_lock',return_value=contextlib.nullcontext()),patch.object(launch,'health',return_value=health),patch.object(launch,'start_service') as start,patch.object(launch,'stop_service') as stop:
            self.assertEqual(launch.operate('start',False),health)
            start.assert_not_called();stop.assert_not_called()

    def test_all_busy_states_block_restart(self):
        for key in ('busy','scanning','aiBusy'):
            with self.subTest(key=key),patch.object(launch,'request',return_value={key:True}) as request:
                with self.assertRaisesRegex(RuntimeError,'已取消重启'):
                    launch.stop_service()
                request.assert_called_once_with('/api/state')

    def test_shutdown_rejection_prevents_relaunch(self):
        with patch.object(launch,'launcher_lock',return_value=contextlib.nullcontext()),patch.object(launch,'health',return_value=dict(pid=123)),patch.object(launch,'check_dependencies'),patch.object(launch,'request',side_effect=[{},RuntimeError('当前任务仍在运行')]),patch.object(launch,'start_service') as start:
            with self.assertRaisesRegex(RuntimeError,'仍在运行'):
                launch.operate('restart',False)
            start.assert_not_called()

    def test_restart_uses_shutdown_api_and_waits_for_port_release(self):
        with patch.object(launch,'request',side_effect=[{},dict(ok=True)]) as request,patch.object(launch,'port_open',side_effect=[True,False]),patch.object(launch.time,'sleep') as sleep:
            launch.stop_service()
            self.assertEqual(request.call_args_list[-1].args,('/api/shutdown',{}))
            sleep.assert_called_once()

    def test_restart_starts_when_already_stopped(self):
        with patch.object(launch,'launcher_lock',return_value=contextlib.nullcontext()),patch.object(launch,'health',return_value=None),patch.object(launch,'check_dependencies'),patch.object(launch,'stop_service') as stop,patch.object(launch,'start_service',return_value=dict(pid=456)) as start:
            self.assertEqual(launch.operate('restart',False)['pid'],456)
            start.assert_called_once();stop.assert_not_called()

    def test_server_rejects_new_work_after_shutdown_accepted(self):
        with patch.object(server,'SHUTTING_DOWN',True):
            with self.assertRaisesRegex(ValueError,'正在退出'):
                server.dispatch('/api/scan',dict(project='unused.aep'))
