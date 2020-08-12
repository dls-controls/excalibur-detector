"""
interface_wrapper.py - EXCALIBUR high level API for the ODIN server.

Alan Greer, DLS
"""
import sys
import traceback
import logging
import json
from datetime import datetime
import time
import threading
is_py2 = sys.version[0] == '2'
if is_py2:
    import Queue as queue
else:
    import queue as queue
    unicode = str

from excalibur.detector import ExcaliburDetector, ExcaliburDetectorError
from excalibur.detector_sim import ExcaliburSimulator
from excalibur.calibration_files import DetectorCalibration
from excalibur.definitions import ExcaliburDefinitions
from excalibur.efuse_id_parser import ExcaliburEfuseIDParser
from excalibur.fem import ExcaliburFem
from odin.adapters.parameter_tree import ParameterAccessor, ParameterTree
from enum import Enum
from collections import OrderedDict



class ExcaliburParameter(OrderedDict):
    def __init__(self, param, value,
                 fem=ExcaliburDefinitions.ALL_FEMS, chip=ExcaliburDefinitions.ALL_CHIPS):
        super(ExcaliburParameter, self).__init__()
        self['param'] = param
        self['value'] = value
        self['fem'] = fem
        self['chip'] = chip

    def get(self):
        return self.param, self.value, self.fem, self.chip


class ExcaliburReadParameter(OrderedDict):
    def __init__(self, param, fem=ExcaliburDefinitions.ALL_FEMS, chip=ExcaliburDefinitions.ALL_CHIPS):
        super(ExcaliburReadParameter, self).__init__()
        self['param'] = param
        self['fem'] = fem
        self['chip'] = chip

    def get(self):
        return self.param, self.fem, self.chip


class HLExcaliburDetector(ExcaliburDetector):
    """Wraps the detector class to provide a high level interface.

    """
    test_mode = False

    STATE_IDLE = 0
    STATE_ACQUIRE = 1
    STATE_CALIBRATING = 2

    CALIBRATION_AREAS = [
        'dac',
        'discl',
        'disch',
        'mask',
        'thresh'
        ]

    POWERCARD_PARAMS = [['fe_lv_enable',
                         'fe_hv_enable',
                         'pwr_p5va_vmon'],
                        ['pwr_p5vb_vmon',
                         'pwr_p5v_fem00_imon',
                         'pwr_p5v_fem01_imon'],
                        ['pwr_p5v_fem02_imon',
                         'pwr_p5v_fem03_imon',
                         'pwr_p5v_fem04_imon'],
                        ['pwr_p5v_fem05_imon',
                         'pwr_p48v_vmon',
                         'pwr_p48v_imon'],
                        ['pwr_p5vsup_vmon',
                         'pwr_p5vsup_imon',
                         'pwr_humidity_mon'],
                        ['pwr_air_temp_mon',
                         'pwr_coolant_temp_mon',
                         'pwr_coolant_flow_mon'],
                        ['pwr_p3v3_imon',
                         'pwr_p1v8_imonA',
                         'pwr_bias_imon'],
                        ['pwr_p3v3_vmon',
                         'pwr_p1v8_vmon',
                         'pwr_bias_vmon'],
                        ['pwr_p1v8_imonB',
                         'pwr_p1v8_vmonB',
                         'pwr_coolant_temp_status'],
                        ['pwr_humidity_status',
                         'pwr_coolant_flow_status',
                         'pwr_air_temp_status',
                         'pwr_fan_fault']
                        ]

    EFUSE_PARAMS = [
        'efuseid_c0',
        'efuseid_c1',
        'efuseid_c2',
        'efuseid_c3',
        'efuseid_c4',
        'efuseid_c5',
        'efuseid_c6',
        'efuseid_c7',
        'efuse_match'
        ]

    FEM_PARAMS = [
        'fem_local_temp',
        'fem_remote_temp',
        'moly_temp',
        'moly_humidity'
        ]

    SUPPLY_PARAMS = [
        'supply_p1v5_avdd1',
        'supply_p1v5_avdd2',
        'supply_p1v5_avdd3',
        'supply_p1v5_avdd4',
        'supply_p1v5_vdd1',
        'supply_p2v5_dvdd1'
        ]

    STR_STATUS = 'status'
    STR_STATUS_SENSOR = 'sensor'
    STR_STATUS_SENSOR_WIDTH = 'width'
    STR_STATUS_SENSOR_HEIGHT = 'height'
    STR_STATUS_SENSOR_BYTES = 'bytes'
    STR_STATUS_MANUFACTURER = 'manufacturer'
    STR_STATUS_MODEL = 'model'
    STR_STATUS_ERROR = 'error'
    STR_STATUS_STATE = 'state'
    STR_STATUS_FEM_STATE = 'fem_state'
    STR_STATUS_FEM_FRAMES = 'fem_frames'
    STR_STATUS_FRAMES_ACQUIRED = 'frames_acquired'
    STR_STATUS_FRAME_RATE = 'frame_rate'
    STR_STATUS_ACQUISITION_COMPLETE = 'acquisition_complete'
    STR_STATUS_LV_ENABLED = 'lv_enabled'
    STR_STATUS_CALIBRATING = 'calibrating'
    STR_STATUS_CALIBRATION = 'calibration'
    STR_STATUS_POWERCARD = 'powercard'
    STR_STATUS_POWERCARD_HV_ENABLED = 'hv_enabled'
    STR_STATUS_EFUSE = 'efuse'
    STR_STATUS_FEM = 'fems'
    STR_STATUS_SUPPLY = 'supply'

    STR_CONFIG = 'config'
    STR_CONFIG_NUM_IMAGES = 'num_images'
    STR_CONFIG_EXPOSURE_TIME = 'exposure_time'
    STR_CONFIG_NUM_TEST_PULSES = 'num_test_pulses'
    STR_CONFIG_SCAN_DAC_NUM = 'scan_dac_num'
    STR_CONFIG_SCAN_DAC_START = 'scan_dac_start'
    STR_CONFIG_SCAN_DAC_STOP = 'scan_dac_stop'
    STR_CONFIG_SCAN_DAC_STEP = 'scan_dac_step'
    STR_CONFIG_TEST_PULSE_ENABLE = 'test_pulse_enable'
    STR_CONFIG_IMAGE_MODE = 'image_mode'
    STR_CONFIG_OPERATION_MODE = 'operation_mode'
    STR_CONFIG_LFSR_BYPASS = 'lfsr_bypass'
    STR_CONFIG_READ_WRITE_MODE = 'read_write_mode'
    STR_CONFIG_DISC_CSM_SPM = 'disc_csm_spm'
    STR_CONFIG_EQUALIZATION_MODE = 'equalization_mode'
    STR_CONFIG_TRIGGER_MODE = 'trigger_mode'
    STR_CONFIG_TRIGGER_POLARITY = 'trigger_polarity'
    STR_CONFIG_CSM_SPM_MODE = 'csm_spm_mode'
    STR_CONFIG_COLOUR_MODE = 'colour_mode'
    STR_CONFIG_GAIN_MODE = 'gain_mode'
    STR_CONFIG_COUNTER_SELECT = 'counter_select'
    STR_CONFIG_COUNTER_DEPTH = 'counter_depth'
    STR_CONFIG_CAL_FILE_ROOT = 'cal_file_root'
    STR_CONFIG_ENERGY_THRESHOLD = 'energy_threshold'
    STR_CONFIG_UDP_FILE = 'udp_file'
    STR_CONFIG_HV_BIAS = 'hv_bias'
    STR_CONFIG_LV_ENABLE = 'lv_enable'
    STR_CONFIG_HV_ENABLE = 'hv_enable'
    STR_CONFIG_TEST_DAC_FILE = 'test_dac_file'
    STR_CONFIG_TEST_MASK_FILE = 'test_mask_file'

    def __init__(self, fem_connections, simulated=False):
        self._simulated = simulated
        if self._simulated:
            ExcaliburFem.use_stub_api = True
            self._simulator = ExcaliburSimulator(fem_connections)
        else:
            self._simulator = None

        super(HLExcaliburDetector, self).__init__(fem_connections)

        self._fems = range(1, len(fem_connections)+1)
        logging.debug("Fem conection IDs: %s", self._fems)

        self._default_status = []
        for fem in self._fems:
            self._default_status.append(None)

        # Initialise sensor dimensions
        self._sensor_width = ExcaliburDefinitions.X_PIXELS_PER_CHIP * ExcaliburDefinitions.X_CHIPS_PER_FEM
        self._sensor_height = ExcaliburDefinitions.Y_PIXELS_PER_CHIP * ExcaliburDefinitions.Y_CHIPS_PER_FEM * len(self._fems)
        self._sensor_bytes = 0

        # Initialise state
        self._state = HLExcaliburDetector.STATE_IDLE

        # Initialise error message
        self._error = ''

        # Initialise acquisition status
        self._fem_state = None
        self._fem_frames = 0
        self._frames_acquired = None
        self._frame_rate = None
        self._acquisition_complete = None

        # Initialise hv and lv enabled status
        self._lv_enabled = 0

        # Create the calibration object and associated status dict
        self._calibrating = 0
        self._calibration_bitmask = [0] * len(self._fems)
        self._cb = DetectorCalibration()
        self._calibration_status = {}
        for cb in self.CALIBRATION_AREAS:
            self._calibration_status[cb] = [0] * len(self._fems)

        # Create the Excalibur parameters
        self._num_images = 1
        self._exposure_time = 1.0
        self._num_test_pulses = 0
        self._scan_dac_num = 0
        self._scan_dac_start = 0
        self._scan_dac_stop = 0
        self._scan_dac_step = 0
        self._test_pulse_enable = ExcaliburDefinitions.FEM_TEST_PULSE_NAMES[0]
        self._image_mode = ExcaliburDefinitions.FEM_IMAGEMODE_NAMES[0]
        self._operation_mode = ExcaliburDefinitions.FEM_OPERATION_MODE_NAMES[0]
        self._lfsr_bypass = ExcaliburDefinitions.FEM_LFSR_BYPASS_MODE_NAMES[0]
        self._read_write_mode = ExcaliburDefinitions.FEM_READOUT_MODE_NAMES[0]
        self._disc_csm_spm = ExcaliburDefinitions.FEM_DISCCSMSPM_NAMES[0]
        self._equalization_mode = ExcaliburDefinitions.FEM_EQUALIZATION_MODE_NAMES[0]
        self._trigger_mode = ExcaliburDefinitions.FEM_TRIGMODE_NAMES[0]
        self._trigger_polarity = ExcaliburDefinitions.FEM_TRIGPOLARITY_NAMES[1]
        self._csm_spm_mode = ExcaliburDefinitions.FEM_CSMSPM_MODE_NAMES[0]
        self._colour_mode = ExcaliburDefinitions.FEM_COLOUR_MODE_NAMES[0]
        self._gain_mode = ExcaliburDefinitions.FEM_GAIN_MODE_NAMES[0]
        self._counter_select = 0
        self._counter_depth = '12'
        self._cal_file_root = ''
        self._energy_threshold = 0.0
        self._udp_file = ''
        self._hv_bias = 0.0
        self._lv_enable = 0
        self._hv_enable = 0
        self._test_dac_file = ''
        self._test_mask_file = ''

        # Initialise the powercard
        self._powercard_status = None
        powercard_tree = self.init_powercard()

        # Initialise the efuse structure
        self._efuse_status = None
        efuse_tree = self.init_efuse_ids()

        # Initialise the supply structure
        self._supply_status = None
        supply_tree = self.init_supply()

        # Initialise the fem structure
        self._fem_status = None
        fem_tree = self.init_fems()

        # Initialise the parameter tree from the general status, powercard status and efuse status
        tree = {
            'api': (lambda: 0.1, {
                # Meta data here
            }),
            self.STR_STATUS: {
                self.STR_STATUS_SENSOR: {
                    self.STR_STATUS_SENSOR_WIDTH: (self.get_sensor_width, {
                        # Meta data here
                    }),
                    self.STR_STATUS_SENSOR_HEIGHT: (self.get_sensor_height, {
                        # Meta data here
                    }),
                    self.STR_STATUS_SENSOR_BYTES: (self.get_sensor_bytes, {
                        # Meta data here
                    })
                },
                self.STR_STATUS_MANUFACTURER: (lambda: 'DLS/STFC', {
                    # Meta data here
                }),
                self.STR_STATUS_MODEL: (lambda: 'Odin [Excalibur2]', {
                    # Meta data here
                }),
                self.STR_STATUS_ERROR: (self.get_error, {
                    # Meta data here
                }),
                self.STR_STATUS_STATE: (self.get_state, {
                    # Meta data here
                }),
                self.STR_STATUS_FEM_STATE: (self.get_fem_state, {
                    # Meta data here
                }),
                self.STR_STATUS_FEM_FRAMES: (self.get_fem_frames, {
                    # Meta data here
                }),
                self.STR_STATUS_FRAMES_ACQUIRED: (self.get_frames_acquired, {
                    # Meta data here
                }),
                self.STR_STATUS_FRAME_RATE: (self.get_frame_rate, {
                    # Meta data here
                }),
                self.STR_STATUS_ACQUISITION_COMPLETE: (self.get_acquisition_complete, {
                    # Meta data here
                }),
                self.STR_STATUS_LV_ENABLED: (self.get_lv_enabled, {
                    # Meta data here
                }),
                self.STR_STATUS_CALIBRATING: (self.get_calibrating_status, {
                    # Meta data here
                }),
                self.STR_STATUS_CALIBRATION: (self.get_calibration_bitmask, {
                    # Meta data here
                }),
                self.STR_STATUS_POWERCARD: powercard_tree,
                self.STR_STATUS_EFUSE: efuse_tree,
                self.STR_STATUS_SUPPLY: supply_tree,
                self.STR_STATUS_FEM: fem_tree
            },
            self.STR_CONFIG: {
                self.STR_CONFIG_NUM_IMAGES: (self.get_num_images, self.set_num_images, {
                    # Meta data here
                }),
                self.STR_CONFIG_EXPOSURE_TIME: (self.get_exposure_time, self.set_exposure_time, {
                    # Meta data here
                }),
                self.STR_CONFIG_NUM_TEST_PULSES: (self.get_num_test_pulses, self.set_num_test_pulses, {
                    # Meta data here
                }),
                self.STR_CONFIG_SCAN_DAC_NUM: (self.get_scan_dac_num, self.set_scan_dac_num, {
                    # Meta data here
                }),
                self.STR_CONFIG_SCAN_DAC_START: (self.get_scan_dac_start, self.set_scan_dac_start, {
                    # Meta data here
                }),
                self.STR_CONFIG_SCAN_DAC_STOP: (self.get_scan_dac_stop, self.set_scan_dac_stop, {
                    # Meta data here
                }),
                self.STR_CONFIG_SCAN_DAC_STEP: (self.get_scan_dac_step, self.set_scan_dac_step, {
                    # Meta data here
                }),
                self.STR_CONFIG_TEST_PULSE_ENABLE: (self.get_test_pulse_enable, self.set_test_pulse_enable, {
                    'allowed_values': ExcaliburDefinitions.FEM_TEST_PULSE_NAMES
                }),
                self.STR_CONFIG_IMAGE_MODE: (self.get_image_mode, self.set_image_mode, {
                    'allowed_values': ExcaliburDefinitions.FEM_IMAGEMODE_NAMES
                }),
                self.STR_CONFIG_OPERATION_MODE: (self.get_operation_mode, self.set_operation_mode, {
                    'allowed_values': ExcaliburDefinitions.FEM_OPERATION_MODE_NAMES
                }),
                self.STR_CONFIG_LFSR_BYPASS: (self.get_lfsr_bypass, self.set_lfsr_bypass, {
                    'allowed_values': ExcaliburDefinitions.FEM_LFSR_BYPASS_MODE_NAMES
                }),
                self.STR_CONFIG_READ_WRITE_MODE: (self.get_read_write_mode, self.set_read_write_mode, {
                    'allowed_values': ExcaliburDefinitions.FEM_READOUT_MODE_NAMES
                }),
                self.STR_CONFIG_DISC_CSM_SPM: (self.get_disc_csm_spm, self.set_disc_csm_spm, {
                    'allowed_values': ExcaliburDefinitions.FEM_DISCCSMSPM_NAMES
                }),
                self.STR_CONFIG_EQUALIZATION_MODE: (self.get_equalization_mode, self.set_equalization_mode, {
                    'allowed_values': ExcaliburDefinitions.FEM_EQUALIZATION_MODE_NAMES
                }),
                self.STR_CONFIG_TRIGGER_MODE: (self.get_trigger_mode, self.set_trigger_mode, {
                    'allowed_values': ExcaliburDefinitions.FEM_TRIGMODE_NAMES
                }),
                self.STR_CONFIG_TRIGGER_POLARITY: (self.get_trigger_polarity, self.set_trigger_polarity, {
                    'allowed_values': ExcaliburDefinitions.FEM_TRIGPOLARITY_NAMES
                }),
                self.STR_CONFIG_CSM_SPM_MODE: (self.get_csm_spm_mode, self.set_csm_spm_mode, {
                    'allowed_values': ExcaliburDefinitions.FEM_CSMSPM_MODE_NAMES
                }),
                self.STR_CONFIG_COLOUR_MODE: (self.get_colour_mode, self.set_colour_mode, {
                    'allowed_values': ExcaliburDefinitions.FEM_COLOUR_MODE_NAMES
                }),
                self.STR_CONFIG_GAIN_MODE: (self.get_gain_mode, self.set_gain_mode, {
                    'allowed_values': ExcaliburDefinitions.FEM_GAIN_MODE_NAMES
                }),
                self.STR_CONFIG_COUNTER_SELECT: (self.get_counter_select, self.set_counter_select, {
                    # Meta data here
                }),
                self.STR_CONFIG_COUNTER_DEPTH: (self.get_counter_depth, self.set_counter_depth, {
                    'allowed_values': ['1', '6', '12', '24']
                }),
                self.STR_CONFIG_CAL_FILE_ROOT: (self.get_cal_file_root, self.set_cal_file_root, {
                    # Meta data here
                }),
                self.STR_CONFIG_ENERGY_THRESHOLD: (self.get_energy_threshold, self.set_energy_threshold, {
                    # Meta data here
                }),
                self.STR_CONFIG_UDP_FILE: (self.get_udp_file, self.set_udp_file, {
                    # Meta data here
                }),
                self.STR_CONFIG_HV_BIAS: (self.get_hv_bias, self.set_hv_bias, {
                    # Meta data here
                }),
                self.STR_CONFIG_LV_ENABLE: (self.get_lv_enable, self.set_lv_enable, {
                    # Meta data here
                }),
                self.STR_CONFIG_HV_ENABLE: (self.get_hv_enable, self.set_hv_enable, {
                    # Meta data here
                }),
                self.STR_CONFIG_TEST_DAC_FILE: (self.get_test_dac_file, self.set_test_dac_file, {
                    # Meta data here
                }),
                self.STR_CONFIG_TEST_MASK_FILE: (self.get_test_mask_file, self.set_test_dac_file, {
                    # Meta data here
                })
            }
        }

        self._tree_status = ParameterTree(tree)

        logging.debug("Excalibur parameter tree: %s", self._tree_status.tree)

        self._executing_updates = True
        self._read_efuse_ids = False
        self._acquiring = False
        self._frames_acquired = 0
        self._hw_frames_acquired = 0
        self._acq_frame_count = 0
        self._acq_exposure = 0.0
        self._acq_start_time = datetime.now()
        self._acq_timeout = 0.0
        self._comms_lock = threading.RLock()
        self._param_lock = threading.RLock()
        self._fast_update_time = datetime.now()
        self._medium_update_time = datetime.now()
        self._slow_update_time = datetime.now()
        self._startup_time = datetime.now()
        self._frame_start_count = 0
        self._frame_count_time = None
        self._calibration_required = True
        self._moly_humidity_counter = 0

        # Temporary 24 bit mode setup
        # TODO: Remove this once 24 bit mode has been implemented within the firmware
        self._24bit_mode = False
        self._24bit_acquiring = False
        self._24bit_params = None
        #self._counter_select = 0
        self._acquisition_loops = 0
        # End of 24 bit mode

        if self.test_mode is False:
            # Perform a slow read
            self.slow_read()
            self._lv_toggle_required = False
            with self._param_lock:
                if self._lv_enabled == 0:
                    # We have started up with the lv not enabled so toggle in case of detector power cycle
                    self._lv_toggle_required = True
            self._status_thread = threading.Thread(target=self.status_loop)
            self._status_thread.start()
            # Create the command handling thread
            self._command_lock = threading.Lock()
            self._command_queue = queue.Queue()
            self._command_thread = threading.Thread(target=self.command_loop)
            self._command_thread.start()
            self.init_hardware_values()

    def get_num_images(self):
        return self._num_images

    def set_num_images(self, value):
        self._num_images = value

    def get_exposure_time(self):
        return self._exposure_time

    def set_exposure_time(self, value):
        self._exposure_time = value

    def get_num_test_pulses(self):
        return self._num_test_pulses

    def set_num_test_pulses(self, value):
        self._num_test_pulses = value

    def get_scan_dac_num(self):
        return self._scan_dac_num

    def set_scan_dac_num(self, value):
        self._scan_dac_num = value

    def get_scan_dac_start(self):
        return self._scan_dac_start

    def set_scan_dac_start(self, value):
        self._scan_dac_start = value

    def get_scan_dac_stop(self):
        return self._scan_dac_stop

    def set_scan_dac_stop(self, value):
        self._scan_dac_stop = value

    def get_scan_dac_step(self):
        return self._scan_dac_step

    def set_scan_dac_step(self, value):
        self._scan_dac_step = value

    def get_test_pulse_enable(self):
        return self._test_pulse_enable

    def set_test_pulse_enable(self, value):
        self._test_pulse_enable = value

    def get_image_mode(self):
        return self._image_mode

    def set_image_mode(self, value):
        self._image_mode = value

    def get_operation_mode(self):
        return self._operation_mode

    def set_operation_mode(self, value):
        self._operation_mode = value
    
    def get_lfsr_bypass(self):
        return self._lfsr_bypass

    def set_lfsr_bypass(self, value):
        self._lfsr_bypass = value
    
    def get_read_write_mode(self):
        return self._read_write_mode

    def set_read_write_mode(self, value):
        self._read_write_mode = value

    def get_disc_csm_spm(self):
        return self._disc_csm_spm

    def set_disc_csm_spm(self, value):
        self._disc_csm_spm = value

    def get_equalization_mode(self):
        return self._equalization_mode

    def set_equalization_mode(self, value):
        self._equalization_mode = value

    def get_trigger_mode(self):
        return self._equalization_mode

    def set_trigger_mode(self, value):
        self._trigger_mode = value

    def get_trigger_polarity(self):
        return self._trigger_polarity

    def set_trigger_polarity(self, value):
        self._trigger_polarity = value

    def get_csm_spm_mode(self):
        return self._csm_spm_mode

    def set_csm_spm_mode(self, value):
        self._csm_spm_mode = value
        self.update_calibration('set_csm_spm_mode', value)
    
    def get_colour_mode(self):
        return self._colour_mode

    def set_colour_mode(self, value):
        self._colour_mode = value

    def get_gain_mode(self):
        return self._gain_mode

    def set_gain_mode(self, value):
        self._gain_mode = value
        self.hl_set_gain_mode()

    def get_counter_select(self):
        return self._counter_select

    def set_counter_select(self, value):
        self._counter_select = value

    def get_counter_depth(self):
        return self._counter_depth

    def set_counter_depth(self, value):
        self._counter_depth = value

    def get_cal_file_root(self):
        return self._cal_file_root

    def set_cal_file_root(self, value):
        self._cal_file_root = value
        self.update_calibration('set_cal_file_root', value)

    def get_energy_threshold(self):
        return self._energy_threshold

    def set_energy_threshold(self, value):
        self._energy_threshold = value
        self.update_calibration('set_energy_threshold', value)

    def get_udp_file(self):
        return self._udp_file

    def set_udp_file(self, value):
        self._udp_file = value

    def get_hv_bias(self):
        return self._hv_bias

    def set_hv_bias(self, value):
        self._hv_bias = value
        self.hl_hv_bias_set('set_hv_bias', value)

    def get_lv_enable(self):
        return self._lv_enable

    def set_lv_enable(self, value):
        self._lv_enable = value
        self.hl_lv_enable('set_lv_enable', value)

    def get_hv_enable(self):
        return self._hv_enable

    def set_hv_enable(self, value):
        self._hv_enable = value
        self.hl_hv_enable('set_hv_enable', value)

    def get_test_dac_file(self):
        return self._test_dac_file

    def set_test_dac_file(self, value):
        self._test_dac_file = value

    def get_test_mask_file(self):
        return self._test_mask_file

    def set_test_mask_file(self, value):
        self._test_mask_file = value

    def get_calibrating_status(self):
        return self._calibrating

    def get_calibration_bitmask(self):
        return self._calibration_bitmask

    def get_powercard_status(self, param):
        return self._powercard_status[param]

    def get_efuse_id_status(self, efuse):
        return self._efuse_status[efuse]

    def get_supply_status(self, param):
        return self._supply_status[param]

    def get_fem_status(self, param):
        return self._fem_status[param]

    def get_lv_enabled(self):
        return self._lv_enabled

    def get_sensor_width(self):
        return self._sensor_width

    def get_sensor_height(self):
        return self._sensor_height

    def get_sensor_bytes(self):
        return self._sensor_bytes

    def get_state(self):
        return self._state

    def get_error(self):
        return self._error

    def get_fem_state(self):
        return self._fem_state

    def get_fem_frames(self):
        return self._fem_frames

    def get_frames_acquired(self):
        return self._frames_acquired

    def get_frame_rate(self):
        return self._frame_rate

    def get_acquisition_complete(self):
        return self._acquisition_complete

    def init_powercard(self):
        # First, initialise the powercard status dict from the POWERCARD_PARAMS
        self._powercard_status = {}
        powercard_dict = {}

        for param_block in self.POWERCARD_PARAMS:
            for param in param_block:
                self._powercard_status[param] = [None]
                powercard_dict[param] = (lambda p=param:self.get_powercard_status(p), {
                        # Meta data here
                    })
        # Add the hv_enabled flag
        self._powercard_status[self.STR_STATUS_POWERCARD_HV_ENABLED] = 0
        powercard_dict[self.STR_STATUS_POWERCARD_HV_ENABLED] = (lambda p=self.STR_STATUS_POWERCARD_HV_ENABLED:self.get_powercard_status(p), {
            # Meta data here
        })

        # Initialise the powercard parameter tree
        powercard_tree = ParameterTree(powercard_dict)
        return powercard_tree

    def init_efuse_ids(self):
        # Initialise the efuse status dict from the EFUSE_PARAMS
        self._efuse_status = {}
        efuse_dict = {}

        for efuse in self.EFUSE_PARAMS:
            self._efuse_status[efuse] = [0] * len(self._fems)
            efuse_dict[efuse] = (lambda p=efuse:self.get_efuse_id_status(p), {
                        # Meta data here
                    })

        # Initialise the efuse parameter tree
        efuse_tree = ParameterTree(efuse_dict)
        return efuse_tree

    def init_supply(self):
        # First, initialise the supply status dict from the SUPPLY_PARAMS
        self._supply_status = {}
        supply_dict = {}

        for param in self.SUPPLY_PARAMS:
            self._supply_status[param] = [None]
            supply_dict[param] = (lambda p=param:self.get_supply_status(p), {
                    # Meta data here
                })

        # Initialise the powercard parameter tree
        supply_tree = ParameterTree(supply_dict)
        return supply_tree

    def init_fems(self):
        # First, initialise the fem status dict from the FEM_PARAMS
        self._fem_status = {}
        fem_dict = {}

        for param in self.FEM_PARAMS:
            self._fem_status[param] = [None]
            fem_dict[param] = (lambda p=param:self.get_fem_status(p), {
                    # Meta data here
                })

        # Initialise the powercard parameter tree
        fem_tree = ParameterTree(fem_dict)
        return fem_tree

    def init_hardware_values(self):
        self.hl_set_gain_mode()

    def hl_set_gain_mode(self):
        with self._comms_lock:
            # Initialise the detector parameters
            write_params = []
            logging.info('  Setting ASIC gain mode to {} '.format(self._gain_mode))
            write_params.append(ExcaliburParameter('mpx3_gainmode', [[ExcaliburDefinitions.FEM_GAIN_MODE_NAMES.index(self._gain_mode)]]))
            self.hl_write_params(write_params)
            self.update_calibration('mpx3_gainmode', self._gain_mode)

    def hl_load_udp_config(self, name, filename):
        logging.info("Loading UDP configuration [{}] from file {}".format(name, filename))

        try:
            with open(filename) as config_file:
                udp_config = json.load(config_file)
        except IOError as io_error:
            logging.error("Failed to open UDP configuration file: {}".format(io_error))
            self.set_error("Failed to open UDP configuration file: {}".format(io_error))
            return
        except ValueError as value_error:
            logging.error("Failed to parse UDP json config: {}".format(value_error))
            self.set_error("Failed to parse UDP json config: {}".format(value_error))
            return

        source_data_addr = []
        source_data_mac = []
        source_data_port = []
        dest_data_port_offset = []

        for idx, fem in enumerate(udp_config['fems']):
            source_data_addr.append(fem['ipaddr'])
            source_data_mac.append(fem['mac'])
            source_data_port.append(fem['port'])
            dest_data_port_offset.append(fem['dest_port_offset']
                                         )
            logging.debug(
                'FEM  {idx:d} | '
                'ip: {ipaddr:16s} mac: {mac:s} port: {port:5d} offset: {dest_port_offset:d}'.format(
                    idx=idx, **fem)
            )
        udp_params = []
        num_fems = len(self._fems)
        # Append per-FEM UDP source parameters, truncating to number of FEMs present in system
        udp_params.append(ExcaliburParameter(
            'source_data_addr', [[addr] for addr in source_data_addr[:num_fems]],
        ))
        udp_params.append(ExcaliburParameter(
            'source_data_mac', [[mac] for mac in source_data_mac[:num_fems]],
        ))
        udp_params.append(ExcaliburParameter(
            'source_data_port', [[port] for port in source_data_port[:num_fems]]
        ))
        udp_params.append(ExcaliburParameter(
            'dest_data_port_offset',
            [[offset] for offset in dest_data_port_offset[:num_fems]]
        ))

        # These configurations need to be nested once each each for [Detector[FEM[Chip]]]
        if 'all_fems' in udp_config['nodes'].keys():
            # We need to duplicate the same configuration to all FEMs
            dest_data_addr = [[[]]]
            dest_data_mac = [[[]]]
            dest_data_port = [[[]]]
            for dest_idx, dest in enumerate(udp_config['nodes']['all_fems']):
                dest_data_addr[0][0].append(dest['ipaddr'])
                dest_data_mac[0][0].append(dest['mac'])
                dest_data_port[0][0].append(int(dest['port']))

                logging.debug(
                    'Node {node:d} | '
                    'ip: {ipaddr:16s} mac: {mac:s} port: {port:5d}'.format(
                        node=dest_idx, **dest)
                )
        else:
            fems = [fem['name'] for fem in udp_config['fems']]
            if all(fem in udp_config['nodes'].keys() for fem in fems):
                # Each FEM needs a different configuration
                dest_data_addr = [[[]] for _ in self._fems]
                dest_data_mac = [[[]] for _ in self._fems]
                dest_data_port = [[[]] for _ in self._fems]
                for fem_idx, fem_key in enumerate(fems):
                    for dest_idx, dest in enumerate(udp_config['nodes'][fem_key]):
                        dest_data_addr[fem_idx][0].append(dest['ipaddr'])
                        dest_data_mac[fem_idx][0].append(dest['mac'])
                        dest_data_port[fem_idx][0].append(int(dest['port']))

                        logging.debug(
                            'FEM {fem:d} Node {node:d} | '
                            'ip: {ipaddr:16s} mac: {mac:s} port: {port:5d}'.format(
                                fem=fem_idx, node=dest_idx, **dest)
                        )
            else:
                message = "Failed to parse UDP json config." \
                          "Node config must contain a config for each entry in fems or " \
                          "one config with the key 'all_fems'.\n" \
                          "Fems: {}\n" \
                          "Node Config Keys: {}".format(fems, udp_config['nodes'].keys())
                logging.error(message)
                self.set_error(message)
                return

        # Append the UDP destination parameters, noting [[[ ]]] indexing as they are common for
        # all FEMs and chips - there must be a better way to do this
        udp_params.append(ExcaliburParameter(
            'dest_data_addr', dest_data_addr
        ))
        udp_params.append(ExcaliburParameter(
            'dest_data_mac', dest_data_mac
        ))
        udp_params.append(ExcaliburParameter(
            'dest_data_port', dest_data_port
        ))

        farm_mode_enable = udp_config['farm_mode']['enable']
        farm_mode_num_dests = udp_config['farm_mode']['num_dests']

        # Append the farm mode configuration parameters
        udp_params.append(ExcaliburParameter('farm_mode_enable', [[farm_mode_enable]]))
        udp_params.append(ExcaliburParameter('farm_mode_num_dests', [[farm_mode_num_dests]]))

        # Write all the parameters to system
        logging.info('Writing UDP configuration parameters to system')
        complete, msg = self.hl_write_params(udp_params)
        if complete:
            logging.info('UDP configuration complete')
        else:
            logging.error('UDP configuration failed')

    def shutdown(self):
        self._executing_updates = False
        self.queue_command(None)

    def set_calibration_status(self, fem, status, area=None):
        if area is not None:
            self._calibration_status[area][fem-1] = status
        else:
            for area in self.CALIBRATION_AREAS:
                self._calibration_status[area][fem - 1] = status

        logging.debug("Calibration: %s", self._calibration_status)
        bit = 0
        calibration_bitmask = 0
        for area in self.CALIBRATION_AREAS:
            calibration_bitmask += (self._calibration_status[area][fem - 1] << bit)
            bit += 1
        if calibration_bitmask == 0x1F:
            calibration_bitmask += (1 << bit)

        self._calibration_bitmask[fem-1] = calibration_bitmask

    def hl_manual_dac_calibration(self, filename):
        logging.debug("Manual DAC calibration requested: %s", filename)
        for fem in self._fems:
            self.set_calibration_status(fem, 0, 'dac')
        self._cb.manual_dac_calibration(self._fems, filename)
        self.download_dac_calibration()
        logging.debug("Calibration Status: %s", self._calibration_bitmask)

    def hl_test_mask_calibration(self, filename):
        logging.debug("Test mask file requested: %s", filename)
        for fem in self._fems:
            self.set_calibration_status(fem, 0, 'mask')
        self._cb.manual_mask_calibration(self._fems, filename)
        self.download_test_masks()
        logging.debug("Calibration Status: %s", self._calibration_bitmask)

    def update_calibration(self, name, value):
        logging.debug("Update calibration requested due to %s updated to %s", name, value)
        if (datetime.now() - self._startup_time).total_seconds() < 10.0:
            # update_calibration requested too early so flag for an update as soon as possible
            self._calibration_required = True
            logging.debug("Too early in initialisation to calibrate, queued...")
        else:
            lv_enabled = 0
            with self._param_lock:
                lv_enabled = self._lv_enabled
            if lv_enabled == 1:
                try:
                    self._calibrating = 1
                    self._state = HLExcaliburDetector.STATE_CALIBRATING
                    logging.info("Calibrating now...")
                    # Reset all calibration status values prior to loading a new calibration
                    for fem in self._fems:
                        self.set_calibration_status(fem, 0)
                    if self._cal_file_root != '':
                        self._cb.set_file_root(self._cal_file_root)
                        self._cb.set_csm_spm_mode(ExcaliburDefinitions.FEM_CSMSPM_MODE_NAMES.index(self._csm_spm_mode))
                        self._cb.set_gain_mode(ExcaliburDefinitions.FEM_GAIN_MODE_NAMES.index(self._gain_mode))
                        self._cb.set_energy_threshold(self._energy_threshold)
                        self._cb.load_calibration_files(self._fems)
                        self.download_dac_calibration()
                        self.download_pixel_calibration()
                    else:
                        logging.info("No calibration root supplied")
                    self._calibrating = 0
                    self._state = HLExcaliburDetector.STATE_IDLE
                except Exception as ex:
                    # If any exception occurs during calibration reset the status item
                    self._calibrating = 0
                    self._state = HLExcaliburDetector.STATE_IDLE
                    # Set the error message
                    self.set_error(str(ex))
            else:
                logging.info("Not updating calibration as LV is not enabled")

    def get_chip_ids(self, fem_id):
        # Return either the default chip IDs or reversed chip IDs depending on the FEM
        # ID.  TODO: 
        chip_ids = ExcaliburDefinitions.FEM_DEFAULT_CHIP_IDS
        if fem_id & 1 != 1:
            chip_ids = reversed(chip_ids)
        return chip_ids

    def download_dac_calibration(self):
        dac_params = []

        for (dac_name, dac_param) in self._cb.get_dac(1).dac_api_params():
            logging.debug("%s  %s", dac_name, dac_param)
            dac_vals = []
            for fem in self._fems:
                logging.info("Downloading {} to FEM # {}".format(dac_name, fem))
                #fem_vals = [self._cb.get_dac(fem).dacs(fem, chip_id)[dac_name] for chip_id in self.get_chip_ids(fem)]
                fem_vals = [self._cb.get_dac(fem).dacs(fem, chip_id)[dac_name] for chip_id in ExcaliburDefinitions.FEM_DEFAULT_CHIP_IDS]
                dac_vals.append(fem_vals)

            dac_params.append(ExcaliburParameter(dac_param, dac_vals,
                                                 fem=self._fems, chip=ExcaliburDefinitions.FEM_DEFAULT_CHIP_IDS))

        dac_params.append(ExcaliburParameter('mpx3_dacsense', [[0]],
                                             fem=self._fems, chip=ExcaliburDefinitions.FEM_DEFAULT_CHIP_IDS))

        # Write all the parameters to system
        logging.debug('Writing DAC configuration parameters to system {}'.format(str(dac_params)))
        with self._comms_lock:
            self.hl_write_params(dac_params)
            time.sleep(1.0)
            # Now send the command to load the DAC configuration
            self.hl_do_command('load_dacconfig')

        for fem in self._fems:
            self.set_calibration_status(fem, 1, 'dac')
            self.set_calibration_status(fem, 1, 'thresh')

    def download_pixel_masks(self):
        pixel_params = []
        mpx3_pixel_masks = []
        logging.debug("Generating mpx3_pixel_mask...")
        for fem in self._fems:
            chip_ids = self.get_chip_ids(fem)
            fem_vals = [self._cb.get_mask(fem)[chip-1].pixels for chip in chip_ids]
            mpx3_pixel_masks.append(fem_vals)
        pixel_params.append(ExcaliburParameter('mpx3_pixel_mask', mpx3_pixel_masks,
                                               fem=self._fems, chip=ExcaliburDefinitions.FEM_DEFAULT_CHIP_IDS))

        # Write all the parameters to system
        with self._comms_lock:
            self.hl_write_params(pixel_params)
            time.sleep(1.0)
            # Send the command to load the pixel configuration
            self.hl_do_command('load_pixelconfig')

        for fem in self._fems:
            self.set_calibration_status(fem, 1, 'mask')

    def download_test_masks(self):
        chip_ids = ExcaliburDefinitions.FEM_DEFAULT_CHIP_IDS
        pixel_params = []
        mpx3_pixel_masks = []
        mpx3_pixel_mask = [0] * ExcaliburDefinitions.FEM_PIXELS_PER_CHIP
        mpx3_pixel_discl = [0] * ExcaliburDefinitions.FEM_PIXELS_PER_CHIP
        mpx3_pixel_disch = [0] * ExcaliburDefinitions.FEM_PIXELS_PER_CHIP
        logging.debug("Generating mpx3_pixel_test...")
        for fem in self._fems:
            fem_vals = [self._cb.get_mask(fem)[chip-1].pixels for chip in chip_ids]
            mpx3_pixel_masks.append(fem_vals)
        pixel_params.append(ExcaliburParameter('mpx3_pixel_mask', [[mpx3_pixel_mask]],
                                               fem=self._fems, chip=chip_ids))
        pixel_params.append(ExcaliburParameter('mpx3_pixel_discl', [[mpx3_pixel_discl]],
                                               fem=self._fems, chip=chip_ids))
        pixel_params.append(ExcaliburParameter('mpx3_pixel_disch', [[mpx3_pixel_disch]],
                                               fem=self._fems, chip=chip_ids))
        pixel_params.append(ExcaliburParameter('mpx3_pixel_test', mpx3_pixel_masks,
                                               fem=self._fems, chip=chip_ids))

        # Write all the parameters to system
        with self._comms_lock:
            self.hl_write_params(pixel_params)
            time.sleep(1.0)

            # Send the command to load the pixel configuration
            self.hl_do_command('load_pixelconfig')

        for fem in self._fems:
            self.set_calibration_status(fem, 1, 'mask')

    def download_pixel_calibration(self):
        #chip_ids = ExcaliburDefinitions.FEM_DEFAULT_CHIP_IDS
        pixel_params = []
        mpx3_pixel_masks = []
        # Write all the parameters to system
        logging.debug("Writing pixel parameters to hardware...")

        logging.debug("Generating mpx3_pixel_mask...")
        for fem in self._fems:
            chip_ids = self.get_chip_ids(1)
            fem_vals = [self._cb.get_mask(fem)[chip-1].pixels for chip in chip_ids]
            mpx3_pixel_masks.append(fem_vals)
        pixel_params.append(ExcaliburParameter('mpx3_pixel_mask', mpx3_pixel_masks,
                                               fem=self._fems, chip=ExcaliburDefinitions.FEM_DEFAULT_CHIP_IDS))

        with self._comms_lock:
            self.hl_write_params(pixel_params)

            time.sleep(1.0)

            # Send the command to load the pixel configuration
            logging.debug("Sending the load_pixelconfig command...")
            self.hl_do_command('load_pixelconfig')

        for fem in self._fems:
            self.set_calibration_status(fem, 1, 'mask')

        pixel_params = []
        mpx3_pixel_discl = []
        logging.debug("Generating mpx3_pixel_discl...")
        for fem in self._fems:
            chip_ids = self.get_chip_ids(1)
            fem_vals = [self._cb.get_discL(fem)[chip-1].pixels for chip in chip_ids]
            mpx3_pixel_discl.append(fem_vals)
        pixel_params.append(ExcaliburParameter('mpx3_pixel_discl', mpx3_pixel_discl,
                                               fem=self._fems, chip=ExcaliburDefinitions.FEM_DEFAULT_CHIP_IDS))

        with self._comms_lock:
            self.hl_write_params(pixel_params)

            time.sleep(1.0)

            # Send the command to load the pixel configuration
            logging.debug("Sending the load_pixelconfig command...")
            self.hl_do_command('load_pixelconfig')

        for fem in self._fems:
            self.set_calibration_status(fem, 1, 'discl')

        pixel_params = []
        mpx3_pixel_disch = []
        logging.debug("Generating mpx3_pixel_disch...")
        for fem in self._fems:
            chip_ids = self.get_chip_ids(1)
            fem_vals = [self._cb.get_discH(fem)[chip - 1].pixels for chip in chip_ids]
            mpx3_pixel_disch.append(fem_vals)
        pixel_params.append(ExcaliburParameter('mpx3_pixel_disch', mpx3_pixel_disch,
                                               fem=self._fems, chip=ExcaliburDefinitions.FEM_DEFAULT_CHIP_IDS))

        with self._comms_lock:
            self.hl_write_params(pixel_params)
        
            time.sleep(1.0)

            # Send the command to load the pixel configuration
            logging.debug("Sending the load_pixelconfig command...")
            self.hl_do_command('load_pixelconfig')

        for fem in self._fems:
            self.set_calibration_status(fem, 1, 'disch')

    def status_loop(self):
        # Status loop has two polling rates, fast and slow
        # Fast poll is currently set to 0.2 s
        # Slow poll is currently set to 5.0 s
        if self._lv_toggle_required:
            # Short pause to ensure the power card ID has been set from the low level detector
            time.sleep(1.0)
            # We only ever toggle the lv once if required
            self._lv_toggle_required = False
            # Perform the toggling of the command bit for lv
            self.hl_toggle_lv()

        while self._executing_updates:
            if (datetime.now() - self._startup_time).total_seconds() > 10.0:
                if self._calibration_required:
                    try:
                        self._calibration_required = False
                        self.update_calibration(self.STR_STATUS_LV_ENABLED, '1')
                    except:
                        pass
            if (datetime.now() - self._slow_update_time).seconds > 10.0:
                self._slow_update_time = datetime.now()
                self.slow_read()
            if (datetime.now() - self._medium_update_time).seconds > 10.0:
                self._medium_update_time = datetime.now()
                self.power_card_read()
            if (datetime.now() - self._fast_update_time).microseconds > 100000:
                self._fast_update_time = datetime.now()
                self.fast_read()
            time.sleep(0.1)

    def queue_command(self, command):
        self._command_queue.put(command, block=False)

    def command_loop(self):
        running = True
        while running:
            try:
                command = self._command_queue.get()
                if command:
                    with self._command_lock:
                        self.execute_command(command)
                else:
                    running = False
            except Exception as e:
                type_, value_, traceback_ = sys.exc_info()
                ex = traceback.format_exception(type_, value_, traceback_)
                logging.error(e)
                self.set_error("Unhandled exception: {} => {}".format(str(e), str(ex)))

    def execute_command(self, command):
        path = command['path']
        data = command['data']
        if isinstance(data, unicode):
            data = data.encode("utf-8")
        try:
            try:
                self._tree_status.set(path, data)
            except Exception as e:
                if path == 'command/initialise':
                    # Initialise the FEMs
                    logging.debug('Initialise has been called')
                    self.hl_initialise()
                elif path == 'command/force_calibrate':
                    self.update_calibration('reload', 'manual')
                elif path == 'command/configure_dac':
                    # Configure the DAC
                    dac_file = self._test_dac_file
                    logging.debug('Manual DAC calibration has been called with file: %s', dac_file)
                    self.hl_manual_dac_calibration(dac_file)
                elif path == 'command/configure_mask':
                    # Apply a test maks
                    mask_file = self._test_mask_file
                    logging.debug('Manual mask file download has been called with file: %s', mask_file)
                    self.hl_test_mask_calibration(mask_file)
                elif path == 'command/24bit_acquire':
                    # Perform a 24 bit acquisition loop
                    self.hl_do_24bit_acquisition()
                else:
                    super(HLExcaliburDetector, self).set(path, data)
        except Exception as ex:
            self.set_error(str(ex))
            raise ExcaliburDetectorError(str(ex))

    def get(self, path):
        with self._param_lock:
            if path == 'command/initialise':
                response = {'value': 1}
            elif path == 'command/force_calibrate':
                response = {'value': 1}
            elif path == 'command/configure_dac':
                response = {'value': 1}
            elif path == 'command/configure_mask':
                response = {'value': 1}
            else:
                try:
                    logging.debug("Searching for '%s': %s", path, self._tree_status.get(path, True))
                    param = path.split('/')[-1]
                    response = self._tree_status.get(path, True)[param]
                    logging.debug("Sending response: %s", response)
                except:
                    response = super(HLExcaliburDetector, self).get(path)

            return response

    def set(self, path, data):
        self.clear_error()
        try:
            if path == 'command/start_acquisition':
                # Starting an acquisition!
                logging.debug('Start acquisition has been called')
                self.hl_arm_detector()
                self.do_acquisition()
            elif path == 'command/stop_acquisition':
                # Starting an acquisition!
                logging.debug('Abort acquisition has been called')
                self.hl_stop_acquisition()
            else:
                self.queue_command({'path': path, 'data': data})
        except Exception as ex:
            self.set_error(str(ex))
            raise ExcaliburDetectorError(str(ex))

    def set_error(self, err):
        # Record the error message into the status
        logging.error(err)
        self._error = err

    def clear_error(self):
        # Record the error message into the status
        self._error = ""

    def fast_read(self):
        status = {}
        with self._param_lock:
            bit_depth = self._counter_depth
            bps = 1
            if bit_depth == '12':
                bps = 2
            elif bit_depth == '24':
                bps = 4
            self._sensor_bytes = self._sensor_width * self._sensor_height * bps

        frame_rate = 0.0
        if not self._24bit_mode:
            with self._comms_lock:
                acq_completion_state_mask = 0x40000000
                # Connect to the hardware
                if not self.connected:
                    self.connect({'state': True})

                fem_params = ['frames_acquired', 'control_state']

                read_params = ExcaliburReadParameter(fem_params)
                cmd_ok, err_msg, vals = self.hl_read_params(read_params)
                logging.debug("Raw fast read status: %s", vals)
                # Calculate the minimum number of frames from the fems, as this will be the actual complete frame count
                frames_acquired = min(vals[self.STR_STATUS_FRAMES_ACQUIRED])
                self._hw_frames_acquired = frames_acquired
                #acq_completed = all(
                #    [((state & acq_completion_state_mask) == acq_completion_state_mask) for state in vals['control_state']]
                #)
                if self._acquiring:
                    # Record the frames acquired
                    self._frames_acquired = frames_acquired
                    # We are acquiring so check to see if we have the correct number of frames
                    if frames_acquired == self._acq_frame_count:
                        self._acquiring = False
                        # Acquisition has finished so we must send the stop command
                        logging.debug("stop_acquisition called at end of a complete acquisition")
                        self.hl_stop_acquisition()
                    elif frames_acquired > self._acq_frame_count:
                        # There has been an error in the acquisition, we should never have too many frames
                        self._acquiring = False
                        # Acquisition has finished so we must send the stop command
                        logging.debug("stop_acquisition called at end of a complete acquisition")
                        self.hl_stop_acquisition()
                    else:
                        if frames_acquired > 0:
                            if self._frame_count_time is None:
                                self._frame_start_count = frames_acquired
                                self._frame_count_time = datetime.now()
                            # Check to see if we have timed out
                            delta_us = (datetime.now() - self._frame_count_time).microseconds
                            delta_s = (datetime.now() - self._frame_count_time).seconds
                            frame_rate = float(frames_acquired-self._frame_start_count) / (float(delta_s) + (float(delta_us) / 1000000.0))
                        else:
                            self._frame_start_count = 0
                            self._frame_count_time = None
                            frame_rate = 0.0

                        # We can only time out if we are not waiting for triggers
                        if ExcaliburDefinitions.FEM_TRIGMODE_NAMES.index(self._trigger_mode) == ExcaliburDefinitions.FEM_TRIGMODE_INTERNAL:
                            delta_t = (datetime.now() - self._acq_start_time).seconds
                            # Work out the worst case for number of expected frames (assuming 25% plus 5 second startup)
                            delta_t -= 5.0
                            if delta_t > 0.0:
                                expected_frames = int(delta_t / (self._acq_exposure * 1.25))
                                logging.debug("We would have expected %d frames by now", expected_frames)
                                if expected_frames > frames_acquired:
                                    #self._acquiring = False
                                    # Acquisition has finished so we must send the stop command
                                    #self.set_error("stop_acquisition called due to a timeout")
                                    logging.debug("stop_acquisition called due to a timeout")
                                    #self.hl_stop_acquisition()

                init_state = []
                for fem_state in self.get('status/fem')['fem']:
                    init_state.append(fem_state['state'])

                status = {self.STR_STATUS_FEM_STATE: init_state,
                          self.STR_STATUS_FRAMES_ACQUIRED: self._frames_acquired,
                          self.STR_STATUS_FEM_FRAMES: vals[self.STR_STATUS_FRAMES_ACQUIRED],
                          self.STR_STATUS_FRAME_RATE: frame_rate,
                          self.STR_STATUS_ACQUISITION_COMPLETE: (not self._acquiring)}
            with self._param_lock:
                self._fem_state = status[self.STR_STATUS_FEM_STATE]
                self._fem_frames = status[self.STR_STATUS_FEM_FRAMES]
                self._frame_rate = status[self.STR_STATUS_FRAME_RATE]
                self._acquisition_complete = status[self.STR_STATUS_ACQUISITION_COMPLETE]
            logging.debug("Fast update status: %s", status)

    def power_card_read(self):
        for powercard_params in self.POWERCARD_PARAMS:
            with self._comms_lock:
                # Do not perform a slow read if an acquisition is taking place
                if not self._acquiring:
                    # Connect to the hardware
                    if not self.connected:
                        self.connect({'state': True})

                    fe_params = powercard_params
                    read_params = ExcaliburReadParameter(fe_params, fem=self.powercard_fem_idx+1)
                    cmd_ok, err_msg, status = self.hl_read_params(read_params)
                    if cmd_ok:
                        with self._param_lock:
                            for param in powercard_params:
                                if param in status:
                                    val = status[param]
                                    if isinstance(val, list):
                                        self._powercard_status[param] = val[0]
                                    else:
                                        self._powercard_status[param] = val
        
        with self._param_lock:
            # Check for the current HV enabled state
            hv_enabled = 0
            # Greater than hv_bias means the HV is enabled
            if self._powercard_status['pwr_bias_vmon'] > self._hv_bias - 5.0:
                hv_enabled = 1
            self._powercard_status[self.STR_STATUS_POWERCARD_HV_ENABLED] = hv_enabled
            logging.debug("Power card update status: %s", self._powercard_status)

    def slow_read(self):
        status = {}
        with self._comms_lock:
            # Do not perform a slow read if an acquisition is taking place
            if not self._acquiring:
                # Connect to the hardware
                if not self.connected:
                    self.connect({'state': True})

                fem_params = self.FEM_PARAMS
                supply_params = self.SUPPLY_PARAMS

                fe_params = fem_params + supply_params + ['mpx3_dac_out']

                read_params = ExcaliburReadParameter(fe_params)
                cmd_ok, err_msg, status = self.hl_read_params(read_params)
                if cmd_ok:
                    with self._param_lock:
                        logging.debug("Slow read params: {}".format(status))
                        lv_enabled = 1
                        for param in fe_params:
                            if param in status:
                                val = []
                                if param in supply_params:
                                    for item in status[param]:
                                        if item != 1:
                                            val.append(0)
                                        else:
                                            val.append(1)
                                    self._supply_status[param] = val
                                else:
                                    if param == 'moly_temp' or param == 'moly_humidity':
                                        for item in status[param]:
                                            if item < 0.0:
                                                val.append(None)
                                                lv_enabled = 0
                                            else:
                                                val.append(item)
                                    else:
                                        val = status[param]
                                    self._fem_status[param] = val
                        # Catch when the lv has been enabled and attempt to re-send calibration
                        # Also do not return the humidity right away as it has a settling time
                        if self._lv_enabled == 0 and lv_enabled == 1:
                            self._calibration_required = True
                            self._moly_humidity_counter = 3
                        if self._moly_humidity_counter > 0:
                            self._fem_status['moly_humidity'] = self._default_status
                            self._moly_humidity_counter -= 1
                        self._lv_enabled = lv_enabled

                else:
                    with self._param_lock:
                        for param in fe_params:
                            if param in supply_params:
                                self._supply_status[param] = self._default_status
                            if param in fem_params:
                                self._fem_status[param] = self._default_status
                        if self._lv_enable == 1:
                            logging.error("Lost LV enabled.  Check for safety trip indicator")
                            self.hl_toggle_lv()
                        self._lv_enabled = 0

                if not self._read_efuse_ids:
                    # Only read the efuse IDs if the LV is enabled
                    if self._lv_enabled == 1:
                        response_status, efuse_dict = self.hl_efuseid_read()
                        self._efuse_status.update(efuse_dict)
                        logging.debug("EFUSE return status: %s", response_status)
                        if response_status == 0:
                            self._read_efuse_ids = True

    def hl_arm_detector(self):
        # Perform all of the actions required to get the detector ready for an acquisition
        with self._comms_lock:
            self.clear_error()

            # Start by downloading the UDP configuration
            self.hl_load_udp_config('arming', self._udp_file)

    def hl_do_dac_scan(self):

        logging.info("Executing DAC scan ...")

        # Build a list of parameters to be written toset up the DAC scan
        scan_params = []

        scan_dac = self._scan_dac_num
        logging.info('  Setting scan DAC to {}'.format(scan_dac))
        scan_params.append(ExcaliburParameter('dac_scan_dac', [[scan_dac]]))

        scan_start = self._scan_dac_start
        logging.info('  Setting scan start value to {}'.format(scan_start))
        scan_params.append(ExcaliburParameter('dac_scan_start', [[scan_start]]))

        scan_stop = self._scan_dac_stop
        logging.info('  Setting scan stop value to {}'.format(scan_stop))
        scan_params.append(ExcaliburParameter('dac_scan_stop', [[scan_stop]]))

        scan_step = self._scan_dac_step
        logging.info('  Setting scan step size to {}'.format(scan_step))
        scan_params.append(ExcaliburParameter('dac_scan_step', [[scan_step]]))

        # Record the acquisition exposure time
        self._acq_exposure = self._exposure_time

        acquisition_time = int(self._exposure_time * 1000.0)
        logging.info('  Setting acquisition time to {} ms'.format(acquisition_time))
        scan_params.append(ExcaliburParameter('acquisition_time', [[acquisition_time]]))


        readout_mode = ExcaliburDefinitions.FEM_READOUT_MODE_SEQUENTIAL
        logging.info('  Setting ASIC readout mode to {}'.format(
            ExcaliburDefinitions.readout_mode_name(readout_mode)
        ))
        scan_params.append(ExcaliburParameter('mpx3_readwritemode', [[readout_mode]]))

        colour_mode = ExcaliburDefinitions.FEM_COLOUR_MODE_NAMES.index(self._colour_mode)
        logging.info('  Setting ASIC colour mode to {} '.format(self._colour_mode))
        scan_params.append(ExcaliburParameter('mpx3_colourmode', [[colour_mode]]))

        csmspm_mode = ExcaliburDefinitions.FEM_CSMSPM_MODE_NAMES.index(self._csm_spm_mode)
        logging.info('  Setting ASIC pixel mode to {} '.format(self._csm_spm_mode))
        scan_params.append(ExcaliburParameter('mpx3_csmspmmode', [[csmspm_mode]]))

        disc_csm_spm = ExcaliburDefinitions.FEM_DISCCSMSPM_NAMES.index(self._disc_csm_spm)
        logging.info('  Setting ASIC discriminator output mode to {} '.format(self._disc_csm_spm))
        scan_params.append(ExcaliburParameter('mpx3_disccsmspm', [[disc_csm_spm]]))

        equalization_mode = ExcaliburDefinitions.FEM_EQUALIZATION_MODE_NAMES.index(self._equalization_mode)
        logging.info('  Setting ASIC equalization mode to {} '.format(self._equalization_mode))
        scan_params.append(ExcaliburParameter('mpx3_equalizationmode', [[equalization_mode]]))

        gain_mode = ExcaliburDefinitions.FEM_GAIN_MODE_NAMES.index(self._gain_mode)
        logging.info('  Setting ASIC gain mode to {} '.format(self._gain_mode))
        scan_params.append(ExcaliburParameter('mpx3_gainmode', [[gain_mode]]))

        counter_select = self._counter_select
        logging.info('  Setting ASIC counter select to {} '.format(counter_select))
        scan_params.append(ExcaliburParameter('mpx3_counterselect', [[counter_select]]))

        counter_depth = self._counter_depth
        logging.info('  Setting ASIC counter depth to {} bits'.format(counter_depth))
        scan_params.append(ExcaliburParameter('mpx3_counterdepth',
                                               [[ExcaliburDefinitions.FEM_COUNTER_DEPTH_MAP[counter_depth]]]))

        operation_mode = ExcaliburDefinitions.FEM_OPERATION_MODE_DACSCAN
        logging.info('  Setting operation mode to {}'.format(
            ExcaliburDefinitions.operation_mode_name(operation_mode)
        ))
        scan_params.append(ExcaliburParameter('mpx3_operationmode', [[operation_mode]]))

        lfsr_bypass_mode = ExcaliburDefinitions.FEM_LFSR_BYPASS_MODE_DISABLED
        logging.info('  Setting LFSR bypass mode to {}'.format(
            ExcaliburDefinitions.lfsr_bypass_mode_name(lfsr_bypass_mode)
        ))
        scan_params.append(ExcaliburParameter('mpx3_lfsrbypass', [[lfsr_bypass_mode]]))

        logging.info('  Disabling local data receiver thread')
        scan_params.append(ExcaliburParameter('datareceiver_enable', [[0]]))

        # Write all the parameters to system
        logging.info('Writing configuration parameters to system {}'.format(str(scan_params)))
        self.hl_write_params(scan_params)

        self._frame_start_count = 0
        self._frame_count_time = None

        # Send start acquisition command
        logging.info('Sending start acquisition command')
        self.hl_start_acquisition()
        logging.info('Start acquisition completed')

    def do_acquisition(self):
        with self._comms_lock:
            self.clear_error()
            if self._hw_frames_acquired > 0:
                # Counters have not cleared yet, send a stop acquisition before restarting
                self.hl_stop_acquisition()

            # Set the acquiring flag
            self._acquiring = True
            self._acq_start_time = datetime.now()
            self._acquisition_complete = not self._acquiring
            # Resolve the acquisition operating mode appropriately, handling burst and matrix read if necessary
            operation_mode = ExcaliburDefinitions.FEM_OPERATION_MODE_NAMES.index(self._operation_mode)

            # Check if the operational mode is DAC scan.
            if operation_mode == ExcaliburDefinitions.FEM_OPERATION_MODE_DACSCAN:
                logging.debug('DAC scan requested so entering DAC scan mode')
                self.hl_do_dac_scan()
                return

            num_frames = self._num_images
            image_mode = self._image_mode
            logging.info('  Image mode set to {}'.format(image_mode))
            # Check for single image mode
            if image_mode == ExcaliburDefinitions.FEM_IMAGEMODE_NAMES[0]:
                # Single image mode requested, set num frames to 1
                logging.info('  Single image mode, setting number of frames to 1')
                num_frames = 1
            logging.info('  Setting number of frames to {}'.format(num_frames))



            # Temporary 24 bit mode setup
            # TODO: Remove this once 24 bit mode has been implemented within the firmware
            # 24-bit reads are a special case, so set things up appropriately in this mode
            logging.info("config/counter_depth value: {}".format(self._counter_depth))
            if int(self._counter_depth) == 24:
                self._24bit_mode = True

                # Force counter select to C1, C0 is read manually afterwards
                self._counter_select = 1

                # For acquisitions with > 1 frame, run multiple acquisition loops instea
                self._acquisition_loops = num_frames
                num_frames = 1
                logging.info("Configuring 24-bit acquisition with {} 1-frame loops".format(self._acquisition_loops))

                # In 24-bit mode, force a reset of the UDP frame counter before first acquisition loop
                logging.info('Resetting UDP frame counter for 24 bit mode')
                cmd_ok, err_msg = self.hl_do_command('reset_udp_counter')
                logging.info("Command returned [{}] => {}".format(cmd_ok, err_msg))
                if not cmd_ok:
                    logging.error("UDP counter reset failed: {}".format(err_msg))
                    return
            else:
                self._24bit_mode = False
            # End of 24 bit mode

            # Build a list of parameters to be written to the system to set up acquisition
            write_params = []

            tp_count = self._num_test_pulses
            logging.info('  Setting test pulse count to {}'.format(tp_count))
            write_params.append(ExcaliburParameter('mpx3_numtestpulses', [[tp_count]]))
            tp_enable = ExcaliburDefinitions.FEM_TEST_PULSE_NAMES.index(self._test_pulse_enable)
            logging.info('  Setting test pulse enable to {}'.format(self._test_pulse_enable))
            write_params.append(ExcaliburParameter('testpulse_enable', [[tp_enable]]))

            write_params.append(ExcaliburParameter('num_frames_to_acquire', [[num_frames]]))

            # Record the number of frames for this acquisition
            self._acq_frame_count = num_frames

            # Record the acquisition exposure time
            self._acq_exposure = self._exposure_time

            acquisition_time = int(self._exposure_time * 1000.0)
            logging.info('  Setting acquisition time to {} ms'.format(acquisition_time))
            write_params.append(ExcaliburParameter('acquisition_time', [[acquisition_time]]))

            trigger_mode = ExcaliburDefinitions.FEM_TRIGMODE_NAMES.index(self._trigger_mode)
            logging.info('  Setting trigger mode to {}'.format(self._trigger_mode))
            write_params.append(ExcaliburParameter('mpx3_externaltrigger', [[trigger_mode]]))

            trigger_polarity = ExcaliburDefinitions.FEM_TRIGPOLARITY_NAMES.index(self._trigger_polarity)
            logging.info('  Setting trigger polarity to {}'.format(self._trigger_polarity))
            write_params.append(ExcaliburParameter('mpx3_triggerpolarity', [[trigger_polarity]]))

            read_write_mode = ExcaliburDefinitions.FEM_READOUT_MODE_NAMES.index(self._read_write_mode)
            logging.info('  Setting ASIC readout mode to {}'.format(self._read_write_mode))
            write_params.append(ExcaliburParameter('mpx3_readwritemode', [[read_write_mode]]))

            colour_mode = ExcaliburDefinitions.FEM_COLOUR_MODE_NAMES.index(self._colour_mode)
            logging.info('  Setting ASIC colour mode to {} '.format(self._colour_mode))
            write_params.append(ExcaliburParameter('mpx3_colourmode', [[colour_mode]]))

            csmspm_mode = ExcaliburDefinitions.FEM_CSMSPM_MODE_NAMES.index(self._csm_spm_mode)
            logging.info('  Setting ASIC pixel mode to {} '.format(self._csm_spm_mode))
            write_params.append(ExcaliburParameter('mpx3_csmspmmode', [[csmspm_mode]]))

            equalization_mode = ExcaliburDefinitions.FEM_EQUALIZATION_MODE_NAMES.index(self._equalization_mode)
            logging.info('  Setting ASIC equalization mode to {} '.format(self._equalization_mode))
            write_params.append(ExcaliburParameter('mpx3_equalizationmode', [[equalization_mode]]))

            gain_mode = ExcaliburDefinitions.FEM_GAIN_MODE_NAMES.index(self._gain_mode)
            logging.info('  Setting ASIC gain mode to {} '.format(self._gain_mode))
            write_params.append(ExcaliburParameter('mpx3_gainmode', [[gain_mode]]))

            counter_select = self._counter_select
            logging.info('  Setting ASIC counter select to {} '.format(counter_select))
            write_params.append(ExcaliburParameter('mpx3_counterselect', [[counter_select]]))

            counter_depth = self._counter_depth
            logging.info('  Setting ASIC counter depth to {} bits'.format(counter_depth))
            write_params.append(ExcaliburParameter('mpx3_counterdepth',
                                                   [[ExcaliburDefinitions.FEM_COUNTER_DEPTH_MAP[counter_depth]]]))

            disc_csm_spm = ExcaliburDefinitions.FEM_DISCCSMSPM_NAMES.index(self._disc_csm_spm)
            int_counter_depth = ExcaliburDefinitions.FEM_COUNTER_DEPTH_MAP[counter_depth]
            csm_spm_value = ExcaliburDefinitions.DISC_SPM_CSM_TABLE[int_counter_depth][csmspm_mode][disc_csm_spm][read_write_mode][counter_select]
            logging.info('  Setting ASIC discriminator output mode to {} '.format(csm_spm_value))
            write_params.append(ExcaliburParameter('mpx3_disccsmspm', [[csm_spm_value]]))

            logging.info('  Setting operation mode to {}'.format(self._operation_mode))
            write_params.append(ExcaliburParameter('mpx3_operationmode', [[operation_mode]]))

            lfsr_bypass = ExcaliburDefinitions.FEM_LFSR_BYPASS_MODE_NAMES.index(self._lfsr_bypass)
            logging.info('  Setting LFSR bypass mode to {}'.format(self._lfsr_bypass))
            write_params.append(ExcaliburParameter('mpx3_lfsrbypass', [[lfsr_bypass]]))

            logging.info('  Disabling local data receiver thread')
            write_params.append(ExcaliburParameter('datareceiver_enable', [[0]]))

            if self._24bit_mode:
                self._24bit_params = write_params
                # Create and queue the command object
                cmd = {
                    'path': 'command/24bit_acquire',
                    'data': {}
                }
                self.queue_command(cmd)

            else:
                # Write all the parameters to system
                logging.info('Writing configuration parameters to system {}'.format(str(write_params)))
                self.hl_write_params(write_params)

                self._frame_start_count = 0
                self._frame_count_time = None

                # Send start acquisition command
                logging.info('Sending start acquisition command')
                self.hl_start_acquisition()
                logging.info('Start acquisition completed')

    def hl_do_24bit_acquisition(self):
        logging.info('24 bit mode acquisition loop entered...')
        for acq_loop in range(self._acquisition_loops):

            self._frame_start_count = 0
            self._frame_count_time = None

            logging.info(
                'Executing acquisition loop {} of {}...'.format(acq_loop + 1, self._acquisition_loops)
            )

            # Write all the parameters to system
            logging.info('Writing configuration parameters to system')
            self.hl_write_params(self._24bit_params)

            # Send start acquisition command
            logging.info('Sending part 1 start acquisition command')
            self.hl_start_acquisition()

            logging.info("Waiting for part 1 acquisition to complete")
            self.wait_for_24bit_acquisition_completion(0x40000000)
            logging.info("Part 1 acquisition has completed")

            self.do_c0_matrix_read()
            logging.info('Acquisition of 24 bit frame completed')

        # Holding the standard acquiring flag true until all loops have completed
        self._acquiring = False
        # Reset 24bit mode flag so that fast read can read
        self._24bit_mode = False
        logging.info("Completed {} acquisition loops".format(self._acquisition_loops))

    def do_c0_matrix_read(self):
        logging.info('Performing a C0 matrix read for 24 bit mode')

        c0_read_params = []
        c0_read_params.append(ExcaliburParameter(
            'mpx3_operationmode', [[ExcaliburDefinitions.FEM_OPERATION_MODE_MAXTRIXREAD]]
        ))
        # Reset counter select back to C0
        self._counter_select = 0

        c0_read_params.append(ExcaliburParameter('mpx3_counterselect', [[0]]))
        c0_read_params.append(ExcaliburParameter('num_frames_to_acquire', [[1]]))
        c0_read_params.append(ExcaliburParameter('mpx3_lfsrbypass', [[0]]))

        logging.info("Sending configuration parameters for C0 matrix read")
        self.hl_write_params(c0_read_params)

        logging.info("Sending part 2 start acquisition command")
        self.hl_start_acquisition()

        logging.info("Waiting for part 2 acquisition to complete")
        self.wait_for_24bit_acquisition_completion(0x1f)
        logging.info("Part 2 acquisition has completed")


    def wait_for_24bit_acquisition_completion(self, acq_completion_state_mask):
        fem_params = ['frames_acquired', 'control_state']
        while True:
            read_params = ExcaliburReadParameter(fem_params)
            cmd_ok, err_msg, vals = self.hl_read_params(read_params)

            acq_completed = all(
                [((state & acq_completion_state_mask) == acq_completion_state_mask) for state in vals['control_state']]
            )
            if acq_completed:
                break

        self.hl_stop_acquisition()

    def hl_initialise(self):
        logging.info("Initialising front end...")
        for fem in self._fems:
            self.set_calibration_status(fem, 0)
        logging.info("Sending a fe_vdd_enable param set to 1")
        params = []
        params.append(ExcaliburParameter('fe_vdd_enable', [[1]], fem=self.powercard_fem_idx+1))
        self.hl_write_params(params)
        logging.info("Sending the fe_init command")
        self.hl_do_command('fe_init')
        logging.info("Sending a stop acquisition")
        return self.hl_stop_acquisition()

    def hl_toggle_lv(self):
        logging.info("Toggling lv_enable 1,0")
        for fem in self._fems:
            self.set_calibration_status(fem, 0)
        if self.powercard_fem_idx < 0:
            self.set_error("Unable to toggle LV enable as server reports no power card")
            return
        params = [ExcaliburParameter('fe_lv_enable', [[1]], fem=self.powercard_fem_idx+1)]
        self.hl_write_params(params)
        params = [ExcaliburParameter('fe_lv_enable', [[0]], fem=self.powercard_fem_idx+1)]
        self.hl_write_params(params)

    def hl_lv_enable(self, name, lv_enable):
        logging.info("Setting lv_enable to %d", lv_enable)
        for fem in self._fems:
            self.set_calibration_status(fem, 0)
        if self.powercard_fem_idx < 0:
            self.set_error("Unable to set LV enable [] as server reports no power card".format(name))
            return
        params = []
        params.append(ExcaliburParameter('fe_lv_enable', [[lv_enable]], fem=self.powercard_fem_idx+1))
        self.hl_write_params(params)
        if lv_enable == 1:
            self.hl_initialise()

    def hl_hv_enable(self, name, hv_enable):
        logging.info("Setting hv_enable to %d", hv_enable)
        if self.powercard_fem_idx < 0:
            self.set_error("Unable to set HV enable [] as server reports no power card".format(name))
            return
        params = []
        params.append(ExcaliburParameter('fe_hv_enable', [[hv_enable]], fem=self.powercard_fem_idx+1))
        self.hl_write_params(params)

    def hl_hv_bias_set(self, name, value):
        if self.powercard_fem_idx < 0:
            self.set_error("Unable to set HV bias [] as server reports no power card".format(name))
            return
        params = []
        params.append(ExcaliburParameter('fe_hv_bias', [[float(value)]], fem=self.powercard_fem_idx+1))
        self.hl_write_params(params)

    def hl_start_acquisition(self):
        with self._comms_lock:
            self.do_command('start_acquisition', None)
            return self.wait_for_write_completion()

    def hl_stop_acquisition(self):
        with self._comms_lock:
            self._acquiring = False
            self.do_command('stop_acquisition', None)
            return self.wait_for_write_completion()

    def hl_do_command(self, command):
        logging.debug("Do command: {}".format(command))
        with self._comms_lock:
            if self._simulator is not None:
                self._simulator.do_command(command)
                return (True, '')
            self.do_command(command, None)
            return self.wait_for_write_completion()

    def hl_write_params(self, params):
        logging.debug("Writing params: {}".format(params))
        with self._comms_lock:
            try:
                if self._simulator is not None:
                    self._simulator.write_fe_params(params)
                    return (True, '')
                self.write_fe_param(params)
                return self.wait_for_write_completion()
            except:
                self.set_error("Failed to write params: {}".format(params))
                return (False, '')


    def hl_read_params(self, params):
        values = None
        with self._comms_lock:
            if self._simulator is not None:
                return (True, '', self._simulator.read_fe_params(params))
            self.read_fe_param(params)
            cmd_ok, err_msg = self.wait_for_read_completion()
            if cmd_ok:
                values = super(HLExcaliburDetector, self).get('command')['command']['fe_param_read']['value']
            return (cmd_ok, err_msg, values)

    def hl_efuseid_read(self):
        response_status = 0
        efuse_dict = {'efuseid_c0':  [],
                      'efuseid_c1':  [],
                      'efuseid_c2':  [],
                      'efuseid_c3':  [],
                      'efuseid_c4':  [],
                      'efuseid_c5':  [],
                      'efuseid_c6':  [],
                      'efuseid_c7':  [],
                      'efuse_match': []}
        if self._cal_file_root != '':
            try:
                # First read out the efuse values from the files
                recorded_efuses = {}
                for fem in self._fems:
                    efid_parser = ExcaliburEfuseIDParser()
                    filename = self._cal_file_root + '/fem' + str(fem) + '/efuseIDs'
                    efid_parser.parse_file(filename)
                    recorded_efuses[fem] = efid_parser.efuse_ids
                logging.debug("EfuseIDs read from file: %s", recorded_efuses)
                fe_params = ['efuseid']
                read_params = ExcaliburReadParameter(fe_params)
                self.read_fe_param(read_params)

                while True:
                    time.sleep(0.1)
                    if not self.command_pending():
                        if self._get('command_succeeded'):
                            logging.info("Command has succeeded")
                            status = super(HLExcaliburDetector, self).get('command')['command']['fe_param_read']['value']
                            fem = 1
                            for efuse in status['efuseid']:
                                id_match = 1
                                efuse_dict['efuseid_c0'].append(efuse[0])
                                if recorded_efuses[fem][1] != efuse[0]:
                                    id_match = 0
                                efuse_dict['efuseid_c1'].append(efuse[1])
                                if recorded_efuses[fem][2] != efuse[1]:
                                    id_match = 0
                                efuse_dict['efuseid_c2'].append(efuse[2])
                                if recorded_efuses[fem][3] != efuse[2]:
                                    id_match = 0
                                efuse_dict['efuseid_c3'].append(efuse[3])
                                if recorded_efuses[fem][4] != efuse[3]:
                                    id_match = 0
                                efuse_dict['efuseid_c4'].append(efuse[4])
                                if recorded_efuses[fem][5] != efuse[4]:
                                    id_match = 0
                                efuse_dict['efuseid_c5'].append(efuse[5])
                                if recorded_efuses[fem][6] != efuse[5]:
                                    id_match = 0
                                efuse_dict['efuseid_c6'].append(efuse[6])
                                if recorded_efuses[fem][7] != efuse[6]:
                                    id_match = 0
                                efuse_dict['efuseid_c7'].append(efuse[7])
                                if recorded_efuses[fem][8] != efuse[7]:
                                    id_match = 0
                                efuse_dict['efuse_match'].append(id_match)
                                fem += 1
                        break
            except:
                # Unable to get the efuse IDs so set the dict up with None vales
                response_status = -1
                for efuse_name in efuse_dict:
                    efuse_dict[efuse_name].append(None)
        else:
            response_status = -1
            logging.debug("No EFUSE ID root directory supplied")
        
        logging.debug("EFUSE: %s", efuse_dict)
        return response_status, efuse_dict

    def get_fem_error_state(self):
        fem_state = self.get('status/fem')['fem']
        logging.debug("%s", fem_state)
        for (idx, state) in enumerate(fem_state):
            yield (idx, state['id'], state['error_code'], state['error_msg'])

    def wait_for_write_completion(self):
        return self.wait_for_completion('write_fe_param')

    def wait_for_read_completion(self):
        return self.wait_for_completion('read_fe_param')

    def wait_for_completion(self, wait_type):
        succeeded = False
        err_msg = ''
        try:
            while True:
                time.sleep(0.1)
                if not self.get('status/command_pending')['command_pending']:
                    succeeded = self.get('status/command_succeeded')['command_succeeded']
                    if succeeded:
                        pass
                    else:
                        logging.error('Command {} failed on following FEMS:'.format(wait_type))
                        fem_error_count = 0
                        for (idx, fem_id, error_code, error_msg) in self.get_fem_error_state():
                            if error_code != 0:
                                logging.error(
                                    '  FEM idx {} id {} : {} : {}'.format(idx, fem_id, error_code, error_msg))
                                fem_error_count += 1
                        err_msg = 'Command {} failed on {} FEMs'.format(wait_type, fem_error_count)
                    break

        except ExcaliburDetectorError as e:
            err_msg = str(e)

        if not succeeded:
            self.set_error(err_msg)

        return succeeded, err_msg
