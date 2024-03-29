"""
adapter.py - EXCALIBUR API adapter for the ODIN server.

Tim Nicholls, STFC Application Engineering Group
"""

import logging
import re
from tornado.escape import json_decode
from odin.adapters.adapter import ApiAdapter, ApiAdapterResponse, request_types, response_types

from excalibur_detector.control.detector import ExcaliburDetector, ExcaliburDetectorError
from excalibur_detector.control.hl_detector import HLExcaliburDetector


def require_valid_detector(func):
    """Decorator method for request handler methods to check that adapter has valid detector."""
    def wrapper(_self, path, request):
        if _self.detector is None:
            return ApiAdapterResponse(
                'Invalid detector configuration', status_code=500
            )
        return func(_self, path, request)
    return wrapper


class ExcaliburAdapter(ApiAdapter):
    """ExcaliburAdapter class.

    This class provides the adapter interface between the ODIN server and the EXCALIBUR detector
    system, transforming the REST-like API HTTP verbs into the appropriate EXCALIBUR detector
    control actions
    """
    use_raw_detector = False

    def __init__(self, **kwargs):
        """Initialise the ExcaliburAdapter object.

        :param kwargs: keyword arguments passed to ApiAdapter as options.
        """
        # Initialise the ApiAdapter base class to store adapter options
        super(ExcaliburAdapter, self).__init__(**kwargs)

        # Compile the regular expression used to resolve paths into actions and resources
        self.path_regexp = re.compile('(.*?)/(.*)')

        # Determine if the raw (low-level) or high-level detector class is to be used
        use_raw = bool(self.options.get('raw_detector', ExcaliburAdapter.use_raw_detector))

        # Parse the FEM connection information out of the adapter options and initialise the
        # detector object
        self.detector = None
        if 'detector_fems' in self.options:
            fems = [tuple(fem.strip().split(':')) for fem in self.options['detector_fems'].split(',')]
            try:
                if use_raw:
                    self.detector = ExcaliburDetector(fems)
                else:
                    simulated = False
                    if 'simulated' in self.options:
                        try:
                            if self.options['simulated'] == 'True':
                                simulated = True
                                logging.info("Excalibur detector has been set to simulation mode")
                        except Exception as e:
                            logging.error('Failed to parse simulated flag from options: {}'.format(e))
                    self.detector = HLExcaliburDetector(fems, simulated)
                logging.debug('ExcaliburAdapter loaded with {} detector'.format(
                    'raw' if use_raw else 'high-level'
                ))

                if 'powercard_fem_idx' in self.options:
                    try:
                        powercard_fem_idx = int(self.options['powercard_fem_idx'])
                    except ValueError as e:
                        logging.error('Failed to parse powercard FEM index from options: %s', e)
                    else:
                        logging.debug('Setting power card FEM index to %d',
                            int(self.options['powercard_fem_idx'])
                        )
                        self.detector.set_powercard_fem_idx(powercard_fem_idx)

                if 'chip_enable_mask' in self.options:
                    try:
                        chip_enable_mask = [
                            int(mask, 0) for mask in self.options['chip_enable_mask'].split(',')
                        ]
                    except ValueError as e:
                        logging.error("Failed to parse chip enable mask from options: %s", e)
                    else:
                        logging.debug("Setting chip enable mask for FEMS: %s",
                            ', '.join([hex(mask) for mask in chip_enable_mask])
                        )
                        self.detector.set_chip_enable_mask(chip_enable_mask)

                if 'fem_timeout_ms' in self.options:
                    try:
                        fem_timeout_ms = int(self.options['fem_timeout_ms'])
                    except ValueError as e:
                        logging.error("Failed to parse FEM timeout from options: %s", e)
                    else:
                        logging.debug("Setting FEM timeout to %d ms", fem_timeout_ms)
                        self.detector.set_fem_timeout(fem_timeout_ms)

                if not use_raw:
                    self.detector.init()

            except ExcaliburDetectorError as e:
                logging.error('ExcaliburAdapter failed to initialise detector: %s', e)
        else:
            logging.warning('No detector FEM option specified in configuration')

    @request_types('application/json')
    @response_types('application/json', default='application/json')
    @require_valid_detector
    def get(self, path, request):
        """Handle an HTTP GET request.

        This method is the implementation of the HTTP GET handler for ExcaliburAdapter.

        :param path: URI path of the GET request
        :param request: Tornado HTTP request object
        :return: ApiAdapterResponse object to be returned to the client
        """
        try:
            response = self.detector.get(path)
            status_code = 200
        except ExcaliburDetectorError as e:
            response = {'error': str(e)}
            logging.error(e)
            status_code = 400

        return ApiAdapterResponse(response, status_code=status_code)

    @request_types('application/json')
    @response_types('application/json', default='application/json')
    @require_valid_detector
    def put(self, path, request):
        """Handle an HTTP PUT request.

        This method is the implementation of the HTTP PUT handler for ExcaliburAdapter/

        :param path: URI path of the PUT request
        :param request: Tornado HTTP request object
        :return: ApiAdapterResponse object to be returned to the client
        """
        logging.debug("%s", path)
        logging.debug("%s", request.body)
        try:
            data = json_decode(request.body)
            self.detector.set(path, data)
            response = self.detector.get(path)
            status_code = 200
        except ExcaliburDetectorError as e:
            response = {'error': str(e)}
            status_code = 400
            logging.error(e)
        except (TypeError, ValueError) as e:
            response = {'error': 'Failed to decode PUT request body: {}'.format(str(e))}
            logging.error(e)
            status_code = 400

        return ApiAdapterResponse(response, status_code=status_code)

    @request_types('application/json')
    @response_types('application/json', default='application/json')
    @require_valid_detector
    def delete(self, path, request):
        """Handle an HTTP DELETE request.

        This method is the implementation of the HTTP DELETE verb for ExcaliburAdapter.

        :param path: URI path of the DELETE request
        :param request: Tornado HTTP request object
        :return: ApiAdapterResponse object to be returned to the client
        """
        response = {'response': '{}: DELETE on path {}'.format(self.name, path)}
        status_code = 200

        logging.debug(response)

        return ApiAdapterResponse(response, status_code=status_code)

    def cleanup(self):
        if self.detector:
            self.detector.shutdown()
