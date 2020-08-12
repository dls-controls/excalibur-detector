import logging


class ExcaliburSimulator(object):
    """EXCALIBUR detector simulator class.

    This class provides some simple simulated values that allows control application
    development without a real detector.  This only provides some basic simulation of
    control parameters and status items.
    """
    DEFAULT_PARAMETERS = {
        'mpx3_gainmode':0,
        'fe_lv_enable':0,
        'fe_hv_enable':0,
        'pwr_p5va_vmon':5.0,
        'pwr_p5vb_vmon':5.0,
        'pwr_p5v_fem00_imon':0.2,
        'pwr_p5v_fem01_imon':0.2,
        'pwr_p5v_fem02_imon':0.2,
        'pwr_p5v_fem03_imon':0.2,
        'pwr_p5v_fem04_imon':0.2,
        'pwr_p5v_fem05_imon':0.2,
        'pwr_p48v_vmon':48.0,
        'pwr_p48v_imon':0.2,
        'pwr_p5vsup_vmon':5.0,
        'pwr_p5vsup_imon':0.1,
        'pwr_humidity_mon':0.2,
        'pwr_air_temp_mon':0.2,
        'pwr_coolant_temp_mon':0.2,
        'pwr_coolant_flow_mon':200.0,
        'pwr_p3v3_imon':0.2,
        'pwr_p1v8_imonA':0.2,
        'pwr_bias_imon':0.2,
        'pwr_p3v3_vmon':3.3,
        'pwr_p1v8_vmon':1.8,
        'pwr_bias_vmon':120.0,
        'pwr_p1v8_imonB':0.2,
        'pwr_p1v8_vmonB':0.2,
        'pwr_coolant_temp_status':1,
        'pwr_humidity_status':1,
        'pwr_coolant_flow_status':1,
        'pwr_air_temp_status':1,
        'pwr_fan_fault':0,
        'fem_local_temp':34.0,
        'fem_remote_temp':33.0,
        'moly_temp':35.0,
        'moly_humidity':20.0,
        'supply_p1v5_avdd1':1,
        'supply_p1v5_avdd2':1,
        'supply_p1v5_avdd3':1,
        'supply_p1v5_avdd4':1,
        'supply_p1v5_vdd1':1,
        'supply_p2v5_dvdd1':1,
        'mpx3_dac_out':1,
        'frames_acquired':0,
        'control_state':0x40000000,
        'dac_scan_dac': 0,
        'dac_scan_start': 0,
        'dac_scan_stop': 0,
        'dac_scan_step': 0
    }

    def __init__(self, fem_connections):
        """Initialise the ExcaliburSimulator object.

        :param fem_connections: list of (address, port) FEM connections to make
        """
        self._fems = range(1, len(fem_connections)+1)
        self.num_fems = len(fem_connections)

        # Create the parameter structure that will be interacted with
        self._params = {}
        for param in self.DEFAULT_PARAMETERS:
            default_param = {}
            for fem_id in self._fems:
                default_param[fem_id] = self.DEFAULT_PARAMETERS[param]
            self._params[param] = default_param
        
    def write_fe_params(self, params):
        if not isinstance(params, list):
            params = [params]
        for param in params:
            logging.debug('SIM: Writing parameter {}'.format(param))
            # Get the parameter list and the fem list
            param_names = param['param']
            value = param['value'][0][0]
            fem = param['fem']
            if not isinstance(param_names, list):
                param_names = [param_names]
            for param_name in param_names:
                logging.debug('SIM: Setting parameter {} to {}'.format(param_name, value))
                fem_list = [fem]
                if fem == 0:
                    fem_list = self._fems
                for fem_id in fem_list:
                    self._params[param_name][fem_id] = value

    def read_fe_params(self, params):
        reply = {}
        if not isinstance(params, list):
            params = [params]
        for param in params:
            logging.debug('SIM: Reading parameter {}'.format(param))
            param_names = param['param']
            fem = param['fem']
            if not isinstance(param_names, list):
                param_names = [param_names]
            for param_name in param_names:
                fem_list = [fem]
                if fem == 0:
                    fem_list = self._fems
                reply[param_name] = []
                for fem_id in fem_list:
                    reply[param_name].append(self._params[param_name][fem_id])
        #logging.info("SIM: Parameter Read block {}".format(reply))
        return reply

    def do_command(self, command):
        logging.info("Simulator: command received [{}]".format(command))

