import errno
import logging
import subprocess
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from pi_dance.app import App, Screen
from pi_dance.charts import Note
from pi_dance.console_input import ConsoleInput, JS_EVENT
from pi_dance.display_monitor import DisplayMonitor, cec_status, tvservice_status
from pi_dance.error_logging import configure_logging
from pi_dance.gameplay import Session
from pi_dance.songs import Song
from pi_dance.input import Action, DeviceEvent
from pi_dance.joystick_input import JoystickInput
from pi_dance.main import main


class ConsoleHotplugTests(unittest.TestCase):
    def setUp(self):
        self.reader = ConsoleInput()
        self.reader._joysticks = [42]
        self.reader._input_status = []
        self.reader._button_events = []
        self.reader._next_joystick_retry = 0
        self.reader._read_keyboard_actions = Mock(return_value=[])
        self.reader._write_input_status = Mock()

    def test_unplug_closes_handle_and_reconnect_ignores_initial_start(self):
        for result in (OSError(errno.ENODEV, 'unplugged'), b''):
            with self.subTest(result=result):
                self.reader._joysticks = [42]
                with patch('pi_dance.console_input.os.read', side_effect=[result]), patch('pi_dance.console_input.os.close') as close:
                    self.assertEqual(self.reader.poll_actions(), [DeviceEvent.PAD_DISCONNECTED])
                    close.assert_called_once_with(42)
                self.assertEqual(self.reader._joysticks, [])
                packet = JS_EVENT.pack(0, 1, 0x81, 8)
                with patch.object(self.reader, '_open_joysticks', return_value=([43], [])), patch('pi_dance.console_input.os.read', return_value=packet):
                    self.assertEqual(self.reader.poll_actions(), [DeviceEvent.PAD_CONNECTED])
                self.reader._next_joystick_retry = 0

    def test_no_data_ready_keeps_pad_open(self):
        with patch('pi_dance.console_input.os.read', side_effect=BlockingIOError), patch('pi_dance.console_input.os.close') as close:
            self.assertEqual(self.reader.poll_actions(), [])
            close.assert_not_called()

    def test_desktop_hotplug_uses_instance_id_not_device_index(self):
        joystick = Mock()
        joystick.get_instance_id.return_value = 72
        with patch('pi_dance.joystick_input.pygame.joystick.get_count', return_value=0), patch('pi_dance.joystick_input.pygame.joystick.Joystick', return_value=joystick):
            reader = JoystickInput()
            self.assertIs(reader.handle_event(pygame.event.Event(pygame.JOYDEVICEADDED, device_index=0)), DeviceEvent.PAD_CONNECTED)
            self.assertIs(reader.handle_event(pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=72)), DeviceEvent.PAD_DISCONNECTED)
            self.assertEqual(reader.devices, {})
            joystick.quit.assert_called_once()


class DisplayStatusTests(unittest.TestCase):
    def test_legacy_status_and_cec_unknown_are_distinct_from_off(self):
        self.assertTrue(tvservice_status('state 0x12000a [HDMI CEA (4) RGB lim 16:9], 1280x720'))
        self.assertFalse(tvservice_status('state 0x120002 [TV is off]'))
        self.assertIsNone(tvservice_status('Error getting current display state'))
        self.assertTrue(cec_status('power status: on\n'))
        self.assertFalse(cec_status('power status: standby\n'))
        self.assertIsNone(cec_status('power status: unknown\n'))

    def test_cec_standby_overrides_forced_hdmi_and_unknown_does_not_resume(self):
        monitor = DisplayMonitor()
        monitor.status_paths = []
        monitor.tvservice = 'tvservice'
        monitor.cec_client = 'cec-client'
        hdmi = 'state 0xa [HDMI CEA (4)]'
        with patch.object(monitor, '_command', side_effect=[hdmi, 'power status: standby', hdmi, '', hdmi, 'power status: on']):
            self.assertFalse(monitor._read_status())
            self.assertFalse(monitor._read_status())
            self.assertTrue(monitor._read_status())

    def test_drm_status_and_unavailable_probe(self):
        monitor = DisplayMonitor()
        monitor.tvservice = None
        with TemporaryDirectory() as directory:
            status = Path(directory) / 'status'
            monitor.status_paths = [status]
            self.assertIsNone(monitor._read_status())
            status.write_text('connected\n')
            self.assertTrue(monitor._read_status())
            status.write_text('disconnected\n')
            self.assertFalse(monitor._read_status())

    def test_status_command_timeout_is_unknown(self):
        with patch('pi_dance.display_monitor.subprocess.run', side_effect=subprocess.TimeoutExpired('tvservice', 3)):
            self.assertEqual(DisplayMonitor._command(['tvservice', '-s']), '')

    def test_unused_desktop_hdmi_does_not_report_initial_loss(self):
        monitor = DisplayMonitor()
        monitor._stop = Mock()
        monitor._stop.is_set.side_effect = [False, False, False, True]
        with patch.object(monitor, '_read_status', side_effect=[False, True, False]):
            monitor._watch()
        self.assertEqual(monitor.poll_events(), [DeviceEvent.DISPLAY_CONNECTED, DeviceEvent.DISPLAY_DISCONNECTED])


class AppRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.app = App()

    def tearDown(self):
        self.app.close()

    def test_disconnect_pauses_and_reconnect_waits_for_start(self):
        self.app.current_screen = Screen.PLAYING
        with patch('pi_dance.app.pygame.mixer.music.pause') as pause, patch('pi_dance.app.pygame.mixer.music.unpause') as resume:
            self.app._handle_device_event(DeviceEvent.PAD_DISCONNECTED)
            self.assertIs(self.app.current_screen, Screen.PAUSED)
            pause.assert_called_once()
            self.app._handle_device_event(DeviceEvent.PAD_CONNECTED)
            resume.assert_not_called()
            self.app._handle_action(Action.START)
            resume.assert_called_once()

    def test_tv_off_blocks_resume_until_reconnected(self):
        self.app.current_screen = Screen.PLAYING
        self.app._handle_device_event(DeviceEvent.DISPLAY_DISCONNECTED)
        self.app._handle_action(Action.START)
        self.assertIs(self.app.current_screen, Screen.PAUSED)
        self.app._handle_device_event(DeviceEvent.DISPLAY_CONNECTED)
        self.assertIs(self.app.current_screen, Screen.PAUSED)
        with patch('pi_dance.app.pygame.mixer.music.unpause'):
            self.app._handle_action(Action.START)
        self.assertIs(self.app.current_screen, Screen.PLAYING)

    def test_countdown_is_frozen_until_manual_resume(self):
        self.app.current_screen = Screen.COUNTDOWN
        self.app.countdown_started_at = 0
        with patch('pi_dance.app.pygame.time.get_ticks', return_value=1000):
            self.app._handle_device_event(DeviceEvent.PAD_DISCONNECTED)
        with patch('pi_dance.app.pygame.time.get_ticks', return_value=20000):
            self.app._update()
            self.assertIs(self.app.current_screen, Screen.PAUSED)
            self.app._handle_action(Action.START)
            self.assertIs(self.app.current_screen, Screen.COUNTDOWN)
            self.assertEqual(self.app._countdown_remaining(), 2)

    def test_menu_and_result_do_not_change_on_disconnect(self):
        for screen in (Screen.SONG_LIST, Screen.DIFFICULTY, Screen.RESULT):
            self.app.current_screen = screen
            self.app._handle_device_event(DeviceEvent.PAD_DISCONNECTED)
            self.assertIs(self.app.current_screen, screen)

    def test_cancel_exit_modal_after_disconnect_stays_paused(self):
        self.app.current_screen = Screen.PLAYING
        self.app._handle_action(Action.SELECT)
        self.app._handle_device_event(DeviceEvent.PAD_DISCONNECTED)
        self.app._handle_action(Action.SELECT)
        self.assertIs(self.app.current_screen, Screen.PAUSED)

    def test_queued_start_does_not_undo_automatic_pause(self):
        self.app.current_screen = Screen.PLAYING
        self.app.display_monitor.events.put(DeviceEvent.DISPLAY_DISCONNECTED)
        with patch('pi_dance.app.pygame.event.get', return_value=[pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)]):
            self.app._handle_events()
        self.assertIs(self.app.current_screen, Screen.PAUSED)

    def test_frame_exception_returns_to_list_and_keeps_running(self):
        self.app.current_screen = Screen.PLAYING
        def run_frame():
            if self.app.current_screen is Screen.PLAYING:
                raise RuntimeError('injected failure')
            self.assertIs(self.app.current_screen, Screen.SONG_LIST)
            self.app._render()
            self.app.running = False
        with patch.object(self.app.display_monitor, 'start'), patch.object(self.app, '_run_frame', side_effect=run_frame) as frame:
            with self.assertLogs('pi_dance.app', level='ERROR') as logs:
                self.app.run()
        self.assertIn('injected failure', '\n'.join(logs.output))
        self.assertEqual(frame.call_count, 2)

    def test_repeated_failure_escapes_to_backend_restart(self):
        with patch.object(self.app.display_monitor, 'start'), patch.object(self.app, '_run_frame', side_effect=RuntimeError('broken backend')):
            with self.assertLogs('pi_dance.app', level='ERROR'), self.assertRaisesRegex(RuntimeError, 'broken backend'):
                self.app.run()

    def test_failed_framebuffer_reopen_escalates_to_restart(self):
        self.app.framebuffer = Mock()
        self.app.display_connected = False
        self.app.display_monitor.events.put(DeviceEvent.DISPLAY_CONNECTED)
        with patch('pi_dance.app.ConsoleInput') as console, patch('pi_dance.app.SETTINGS') as settings, patch.object(self.app.display_monitor, 'start'), patch.object(self.app, '_open_framebuffer_presenter', side_effect=OSError('display unavailable')):
            settings.display_backend = 'fbdev'
            console.return_value.__enter__.return_value.poll_actions.return_value = []
            with self.assertLogs('pi_dance.app', level='ERROR'), self.assertRaisesRegex(OSError, 'display unavailable'):
                self.app.run()

    def test_normal_quit_skips_broken_renderer(self):
        with patch('pi_dance.app.pygame.event.get', return_value=[pygame.event.Event(pygame.QUIT)]), patch.object(self.app, '_render', side_effect=RuntimeError('must not render')) as render:
            self.app._run_frame()
        self.assertFalse(self.app.running)
        render.assert_not_called()

    def test_explicit_quit_is_not_restarted(self):
        factory = Mock()
        with patch('pi_dance.main.configure_logging'), patch('pi_dance.main._application_types', return_value=(factory, Mock())):
            main([])
            factory.assert_called_once()
            factory.return_value.run.assert_called_once()

    def test_main_needs_no_launcher_specific_mode(self):
        factory = Mock()
        with patch('pi_dance.main.configure_logging'), \
             patch('pi_dance.main._application_types', return_value=(factory, Mock())):
            main([])
        factory.return_value.run.assert_called_once()

    def test_supervisor_restarts_at_list_and_backs_off(self):
        recovered = Mock()
        screen = Mock()
        with patch('pi_dance.main.configure_logging'), patch('pi_dance.main._application_types', return_value=(Mock(side_effect=[RuntimeError('init failed'), RuntimeError('still absent'), recovered]), screen)), patch('pi_dance.main.time.sleep') as sleep:
            with self.assertLogs('pi_dance.main', level='ERROR'):
                main([])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])
        self.assertIs(recovered.current_screen, screen.SONG_LIST)

    def test_partial_initialization_failure_closes_framebuffer(self):
        framebuffer = Mock()
        framebuffer.canvas = self.app.screen
        with patch('pi_dance.app.SETTINGS') as settings, patch.object(App, '_open_framebuffer_presenter', return_value=framebuffer), patch('pi_dance.app.Assets', side_effect=RuntimeError('asset failure')):
            settings.display_backend = 'fbdev'
            settings.display_cec = False
            with self.assertRaisesRegex(RuntimeError, 'asset failure'):
                App()
        framebuffer.close.assert_called_once()

    def test_bad_external_cover_does_not_block_song_list(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            cover = path / 'song.bmp'
            cover.write_bytes(b'incomplete upload')
            song = Song('Example', path, (255, 0, 0), path / 'song.wav', path / 'song.sm', cover, 10)
            with self.assertLogs('pi_dance.assets', level='WARNING'):
                self.app.assets.reload_covers([song], self.app.screen)
            self.assertEqual(self.app.assets.cover_for(song).get_size(), (256, 256))

    def test_disconnect_preserves_overlap_without_fabricating_lift_edge(self):
        note = Note(1.0, 'up', end_timestamp=3.0, is_lift=True)
        session = Session((note,))
        session.press('up', 1.0)
        session.clear_pressed(2.95)
        self.assertEqual(session.judgements, [])
        self.assertEqual(session.active_holds, {})
        self.assertIsNone(session.release('up', 3.0))
        session.expire(4.0)
        self.assertLessEqual(session.judgements[0].credit, 0.3)


class ErrorLoggingTests(unittest.TestCase):
    def test_traceback_is_written_and_log_size_is_bounded(self):
        logger = logging.getLogger('pi_dance')
        handlers, level, propagate = logger.handlers[:], logger.level, logger.propagate
        logger.handlers = []
        try:
            with TemporaryDirectory() as directory:
                path = Path(directory) / 'logs/errors.log'
                configure_logging(path)
                try:
                    raise ValueError('inspect this failure')
                except ValueError:
                    logger.exception('Recovery')
                contents = path.read_text()
                self.assertIn('Traceback (most recent call last)', contents)
                self.assertIn('ValueError: inspect this failure', contents)
                handler = logger.handlers[0]
                self.assertEqual(handler.backupCount, 2)
                self.assertEqual(handler.maxBytes, 1_000_000)
        finally:
            for handler in logger.handlers:
                handler.close()
            logger.handlers, logger.level, logger.propagate = handlers, level, propagate
