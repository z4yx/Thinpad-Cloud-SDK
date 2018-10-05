#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Install Denpendencies:
#   pip install requests socketIO-client websocket-client

import requests
from socketIO_client import SocketIO
import threading
import time
import logging
import queue

class BackgroundThread(threading.Thread):
    def __init__(self, socketIO, logger):
        super(BackgroundThread, self).__init__()
        self.socketIO = socketIO
        self.logger = logger

    def run(self):
        try:
            self.socketIO.wait()
        except Exception as e:
            self.logger.debug('socketIO.wait(): '+str(e))
            return

class ThinpadCloud:

    DPY_DECODE = {
        0x7e: 0, 0x12: 1, 0xbc: 2, 0xb6: 3, 0xd2: 4, 0xe6: 5, 0xee: 6,
        0x32: 7, 0xfe: 8, 0xf2: 9, 0xf6: 9, 0xfa: 0xa, 0xce: 0xb, 0x6c: 0xc,
        0x9e: 0xd, 0xec: 0xe, 0xe8: 0xf,
    }

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.base_uri = 'http://thinpad.dynv6.net:8080/thinpad'
        self.sess = requests.Session()
        self.socketIO = None
        self.socketIOLogin = False
        self.ioThread = None
        self.token = ''
        self.led_switch_status = {
            'leds': [],
            'nums': [],
            'dip_switches': [0]*32, 
            'micro_switches': [0]*2,
            'touch_switches': [0]*4
        }
        self.uart_recv_queue = queue.Queue()
        self.flash_status_queue = queue.Queue()

    def __del__(self):
        self.logout()
        # super().__del__()

    def _setup_handler(self):

        def on_connect():
            self.logger.debug('[connect]')
            self.socketIO.emit('login', self.token)

        def on_disconnect():
            self.logger.debug('[disconnect]')

        def on_reconnect():
            self.logger.debug('[reconnect]')

        def on_failure(*args):
            self.logger.error('on_failure: ' + repr(args))
            # raise SystemError('System Failure: ' + repr(args))
            self.socketIO.disconnect()
            self.socketIOLogin = False
            self.socketIO = None

        def on_login_success(*args):
            self.socketIOLogin = True

        def on_LED_SWITCH_STATUS(args):
            # self.logger.debug("on_LED_SWITCH_STATUS: " + repr(args))
            self.led_switch_status['leds'] = args['leds']
            self.led_switch_status['nums'] = args['nums']
        
        def on_TTL_DATA_FROMFPGA(data):
            # self.logger.debug("on_TTL_DATA_FROMFPGA: " + repr(data))
            data = data['TTL_serial_data']
            for i in data:
                self.uart_recv_queue.put_nowait(i)
        
        def on_FLASH_PROGRESS(progress):
            self.flash_status_queue.put((0, progress))

        def on_FLASH_RAM_WRITE_RESULT(obj):
            self.logger.debug('FLASH_RAM_WRITE_RESULT '+repr(obj))
            self.flash_status_queue.put((1, obj['success']))

        self.socketIO.on('connect', on_connect)
        self.socketIO.on('disconnect', on_disconnect)
        self.socketIO.on('reconnect', on_reconnect)
        self.socketIO.on('login_fail', on_failure)
        self.socketIO.on('login_success', on_login_success)
        self.socketIO.on('unexpect', on_failure)
        self.socketIO.on('LED_SWITCH_STATUS', on_LED_SWITCH_STATUS)
        self.socketIO.on('TTL_DATA_FROMFPGA', on_TTL_DATA_FROMFPGA)
        self.socketIO.on('FLASH_PROGRESS', on_FLASH_PROGRESS)
        self.socketIO.on('FLASH_RAM_WRITE_RESULT', on_FLASH_RAM_WRITE_RESULT)

    def _socketio_connect(self):

        self.socketIO = SocketIO(self.base_uri, transports=['websocket'])
        self._setup_handler()
        self.ioThread = BackgroundThread(self.socketIO, self.logger)
        self.ioThread.start()

    def _socketio_disconnect(self):
        if self.socketIO is not None:
            self.socketIO.disconnect()
            self.ioThread.join()
            self.socketIO = None
            self.socketIOLogin = False

    def _socketio_send(self, topic, data):
        if self.socketIOLogin:
            self.socketIO.emit(topic, data)
            return True
        return False

    def close(self):
        self._socketio_disconnect()

    # def wait(self):
    #     if self.socketIO is not None:
    #         self.ioThread.join()

    def login(self, user, password):
        r = self.sess.post(self.base_uri+'/signin', timeout=3,
                           data={'username': user, 'password': password})
        self.logger.debug('/signin: %d', r.status_code)
        r.raise_for_status()
        return True

    def logout(self):
        r = self.sess.get(self.base_uri+'/logout', timeout=3)
        self.logger.debug('/logout: %d', r.status_code)
        r.raise_for_status()
        return True

    def allocate_board(self, capability):
        self._socketio_disconnect()
        payload = {'thinpad': capability, 'ident': '', 'require_new': 1}
        r = self.sess.post(self.base_uri+'/upload', files={'placeholder': None},
                            data=payload, allow_redirects=True)
        self.logger.debug('/upload: %d', r.status_code)
        r.raise_for_status()
        if r.url.endswith('/work'):
            self.token = r.headers.get('X-SocketIO-Token')
            self.logger.debug('token: %s', self.token)
            self._socketio_connect()
            while not self.socketIOLogin:
                time.sleep(0.05)
                if self.socketIO is None:
                    raise ConnectionError('Broken socket.io connection')
            return True
        elif r.url.endswith('/signin'):
            raise SystemError('Not Logged in')
        else:
            self.logger.error("redirected to "+r.url)
        return False

    def upload_design(self, filename):
        with open(filename, 'rb') as fd:
            r = self.sess.post(self.base_uri+'/upload', timeout=80,
                            files={'bitstream': fd},
                            allow_redirects=False)
        self.logger.debug('/upload: %d', r.status_code)
        r.raise_for_status()
        if r.status_code == 302:
            self.logger.error("redirected to "+r.headers['location'])
            return False
        return True

    @staticmethod
    def _bitmask2num(bitmask):
        result = 0
        for i in bitmask[::-1]:
            result = result << 1 | i
        return result

    @classmethod
    def _decode_dpy(cls, raw):
        dot = False
        if raw & 1:
            raw ^= 1
            dot = True
        return (-1 if raw not in cls.DPY_DECODE else cls.DPY_DECODE[raw]), dot

    def get_led_bitmask(self):
        return self.led_switch_status['leds']
    
    def get_leds(self):
        return self._bitmask2num(self.led_switch_status['leds'])

    def get_dpy_bitmask(self):
        return self.led_switch_status['nums']

    def get_dpys(self):
        return self._bitmask2num(self.led_switch_status['nums'])

    def get_dpy_decoded(self):
        raw = self.get_dpys()
        return self._decode_dpy(raw>>8) + self._decode_dpy(raw&0xff)

    def set_all_switchs(self, dip_sw=None, touch_btn=None, clock_btn=None, reset_btn=None):
        if dip_sw is not None and len(dip_sw)==32:
            self.led_switch_status['dip_switches'] = dip_sw
        if touch_btn is not None and len(touch_btn) == 4:
            self.led_switch_status['touch_switches'] = touch_btn
        if clock_btn is not None:
            assert 0 <= clock_btn <= 1
            self.led_switch_status['micro_switches'][0] = clock_btn
        if reset_btn is not None:
            assert 0 <= reset_btn <= 1
            self.led_switch_status['micro_switches'][1] = reset_btn

        return self._socketio_send('sendSwitches', self.led_switch_status)

    def set_clock_btn(self, singal_value):
        return self.set_all_switchs(clock_btn=singal_value)

    def set_reset_btn(self, singal_value):
        return self.set_all_switchs(reset_btn=singal_value)

    def set_dip_sw(self, index=0, singal_value=0):
        self.led_switch_status['dip_switches'][index] = singal_value
        return self.set_all_switchs()

    def set_touch_btn(self, index=0, singal_value=0):
        self.led_switch_status['touch_switches'][index] = singal_value
        return self.set_all_switchs()

    def open_uart_port(self, port, baud=115200, parity='NONE', databits=8, stopbits=1):
        assert parity in ['NONE','ODD','EVEN']
        assert databits in [6, 7, 8]
        assert stopbits in [1, 2]
        ret = self._socketio_send('openTTL', {'port_index': str(port)})
        if not ret:
            return ret
        return self._socketio_send('setTTL', {
            'index': str(port),
            'baudrate': str(baud),
            'checkbit': str(parity),
            'datalen': str(databits),
            'stopbit': str(stopbits)
        })

    def close_uart_port(self):
        return self._socketio_send('closeTTL', {})

    def read_uart(self, size=1, timeout=-1):
        blocking = timeout != 0
        if timeout < 0:  # Infinity
            timeout = None
        ret = []
        try:
            while size > 0:
                ret.append(self.uart_recv_queue.get(blocking, timeout))
                size -= 1
        except Exception:
            pass
        return ret
    
    def flush_uart(self):
        try:
            while not self.uart_recv_queue.empty():
                self.uart_recv_queue.get_nowait()
        except Exception:
            pass

    def write_uart(self, data):
        if type(data) is bytes:
            sending = list(data)
        elif type(data) is str:
            sending = list(data.encode('utf-8'))
        elif type(data) is list:
            for i in data:
                if i < 0 or i > 255:
                    raise ValueError('number out of range')
            sending = data
        else:
            raise TypeError('type of "data" should be bytes, str, or list of number')
        return self._socketio_send('sendTTL', sending)

    def read_memory(self, memory, size=0x1000, offset=0):
        if offset % 2 != 0 or size % 2 != 0:
            raise ValueError("size & offset should by multiple of 2")
        r = self.sess.post(self.base_uri+'/flash_ram',
                           files={'placeholder': 'null'},
                           data={'op': 'read_mem', 'offset': '%x' % (offset), 'size': '%x' % (size), 'type': memory})
        self.logger.debug('/flash_ram: %d', r.status_code)
        r.raise_for_status()
        try:
            attachment = r.headers['Content-Disposition']
            self.logger.debug(attachment)
        except KeyError:
            self.logger.warn("read_memory failed: "+r.text)
            return None
        return r.content

    def write_memory(self, memory, data, offset=0):
        if type(data) is not bytes:
            raise TypeError('type of "data" should be bytes')
        size = len(data)
        if offset % 2 != 0 or size % 2 != 0:
            raise ValueError("size & offset should be multiple of 2")

        r = self.sess.post(self.base_uri+'/flash_ram',
                           files={'datafile': ('file1.bin', data)},
                           data={'op': 'write_mem', 'offset': '%x' % (offset), 'type': memory})
        self.logger.debug('/flash_ram: %d', r.status_code)
        r.raise_for_status()
        if r.text != 'ack':
            return False
        while True:
            t, p = self.flash_status_queue.get()
            if t == 0:
                self.logger.info("Progress %d%%"%(p))
            elif t == 1:
                return p
