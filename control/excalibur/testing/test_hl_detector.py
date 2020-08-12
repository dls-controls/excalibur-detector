"""
Test cases for the ExcaliburDetector class of the ODIN server EXCALIBUR plugin

Tim Nicholls, STFC Application Engineering Group
"""

from nose.tools import *
import logging
from mock import Mock

from excalibur.hl_detector import HLExcaliburDetector, ExcaliburParameter
from excalibur.fem import ExcaliburFem


class TestExcaliburDetector():

    @classmethod
    def setup_class(cls):
        ExcaliburFem.use_stub_api = True
        HLExcaliburDetector.test_mode = True
        cls.detector_fems = [
            ('192.168.0.1', 6969, '10.0.2.1'),
            ('192.168.0.2', 6969, '10.0.2.1'),
            ('192.168.0.3', 6969, '10.0.2.1')
        ]

        cls.detector = HLExcaliburDetector(cls.detector_fems)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

    def test_detector_simple_init(self):
        assert_equal(len(self.detector.fems), len(self.detector_fems))

    def test_wait_for_read_completion(self):
        # Mock out the low level calls for get
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        assert_equal((True, ''), self.detector.wait_for_read_completion())
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': False})
        self.detector.get_fem_error_state = Mock(return_value=[(1, 0, 1, 'Test Error')])
        assert_equal((False, 'Command read_fe_param failed on 1 FEMs'), self.detector.wait_for_read_completion())

    def test_wait_for_completion(self):
        # Mock out the low level calls for get
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        assert_equal((True, ''), self.detector.wait_for_completion('testing'))
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': False})
        self.detector.get_fem_error_state = Mock(return_value=[(1, 0, 1, 'Test Error')])
        assert_equal((False, 'Command write_fe_param failed on 1 FEMs'), self.detector.wait_for_completion('write_fe_param'))

    def test_set_calibration_status(self):
        self.detector.set_calibration_status(1, 1, 'dac')
        assert_equal(self.detector._calibration_bitmask[0], 1)
        self.detector.set_calibration_status(2, 1)
        assert_equal(self.detector._calibration_bitmask[1], 63)

    def test_execute_command(self):
        hl_initialise = self.detector.hl_initialise
        self.detector.hl_initialise = Mock()
        self.detector.execute_command({'path': 'command/initialise', 'data': None})
        self.detector.hl_initialise.assert_called()
        self.detector.hl_initialise = hl_initialise
        self.detector.update_calibration = Mock()
        self.detector.execute_command({'path': 'command/force_calibrate', 'data': None})
        self.detector.update_calibration.assert_called()
        self.detector.hl_manual_dac_calibration = Mock()
        self.detector.execute_command({'path': 'command/configure_dac', 'data': None})
        self.detector.hl_manual_dac_calibration.assert_called()
        self.detector.hl_test_mask_calibration = Mock()
        self.detector.execute_command({'path': 'command/configure_mask', 'data': None})
        self.detector.hl_test_mask_calibration.assert_called()

    def test_init_hardware(self):
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        self.detector.write_fe_param = Mock()
        self.detector.init_hardware_values()
        self.detector.write_fe_param.assert_called_with([ExcaliburParameter(param='mpx3_gainmode', value=[[0]], fem=0, chip=0)])

    def test_hl_start_acquisition(self):
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        self.detector.do_command = Mock()
        self.detector.write_fe_param = Mock()
        self.detector.hl_start_acquisition()
        self.detector.do_command.assert_called_with('start_acquisition', None)

    def test_hl_stop_acquisition(self):
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        self.detector.do_command = Mock()
        self.detector.write_fe_param = Mock()
        self.detector.hl_stop_acquisition()
        self.detector.do_command.assert_called_with('stop_acquisition', None)

    def test_hl_do_command(self):
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        self.detector.do_command = Mock()
        self.detector.write_fe_param = Mock()
        self.detector.hl_do_command('test_command')
        self.detector.do_command.assert_called_with('test_command', None)

    def test_hl_write_params(self):
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        self.detector.write_fe_param = Mock()
        self.detector.hl_write_params(['test_params'])
        self.detector.write_fe_param.assert_called_with(['test_params'])

    def test_hl_hv_bias_set(self):
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        self.detector.write_fe_param = Mock()
        self.detector.powercard_fem_idx = 0
        self.detector.hl_hv_bias_set('test_bias', 119.8)
        self.detector.write_fe_param.assert_called_with([ExcaliburParameter(param='fe_hv_bias', value=[[119.8]], fem=1, chip=0)])

    def test_hl_hv_enable(self):
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        self.detector.write_fe_param = Mock()
        self.detector.powercard_fem_idx = 0
        self.detector.hl_hv_enable('test_hv_enable', 1)
        self.detector.write_fe_param.assert_called_with([ExcaliburParameter(param='fe_hv_enable', value=[[1]], fem=1, chip=0)])

    def test_hl_lv_enable(self):
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        self.detector.write_fe_param = Mock()
        self.detector.powercard_fem_idx = 0
        self.detector.hl_lv_enable('test_lv_enable', 0)
        self.detector.write_fe_param.assert_called_with([ExcaliburParameter(param='fe_lv_enable', value=[[0]], fem=1, chip=0)])

    def test_hl_lv_toggle(self):
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        self.detector.write_fe_param = Mock()
        self.detector.powercard_fem_idx = 0
        self.detector.hl_toggle_lv()
        self.detector.write_fe_param.assert_called_with([ExcaliburParameter(param='fe_lv_enable', value=[[0]], fem=1, chip=0)])

    def test_hl_initialise(self):
        self.detector.get = Mock(return_value={'command_pending': False, 'command_succeeded': True})
        self.detector.powercard_fem_idx = 0
        self.detector.do_command = Mock()
        self.detector.write_fe_param = Mock()
        self.detector.hl_initialise()
        self.detector.write_fe_param.assert_called_with([ExcaliburParameter(param='fe_vdd_enable', value=[[1]], fem=1, chip=0)])
        self.detector.do_command.assert_called_with('stop_acquisition', None)

