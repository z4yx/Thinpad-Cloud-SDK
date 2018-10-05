#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Install Denpendencies:
#   pip install requests socketIO-client
# Or
#   pip install -r requirements.txt

import thinpad
import sys
import time
import logging
import signal
import traceback

def switch_and_leds(t):
    print("-- LED & Switch Test --")

    # Set 32 DIP switches 
    for i in range(32):
        t.set_dip_sw(i, 1)
    # Or set them all at once
    t.set_all_switchs(dip_sw=[1]*32)

    # Emulate reset button press
    t.set_reset_btn(1)
    time.sleep(0.01)
    t.set_reset_btn(0)
    time.sleep(0.3)

    for i in range(16):

        print('DPY, LED:')
        dpy_h, dot_h, dpy_l, dot_l = t.get_dpy_decoded()
        leds_str = map(str, reversed(t.get_led_bitmask()))
        # Print them as readable string
        print('%x%x [%s]' % (dpy_h, dpy_l, ''.join(leds_str)), end='')
        # raw value of DPY & LED
        print(' (%04x,%04x)' % (t.get_dpys(), t.get_leds()))

        # Emulate clock button press
        t.set_clock_btn(1)
        time.sleep(0.01)
        t.set_clock_btn(0)
        time.sleep(0.5)

    # Emulate reset button press
    t.set_reset_btn(1)
    time.sleep(0.01)
    t.set_reset_btn(0)
    time.sleep(0.3)
    print('After reset:\n (%04x,%04x)' % (t.get_dpys(), t.get_leds()))

def main():
    print("--- SDK Version:", thinpad.__version__, '---')
    logging.basicConfig(level=logging.INFO)
    # logging.getLogger('thinpad.cloud').setLevel(logging.DEBUG)
    # logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)
    # logging.getLogger('socketIO-client-2').setLevel(logging.INFO)

    if len(sys.argv) < 4:
        print('Usage:', sys.argv[0], '<username> <password> <thinpad_top.bit>')
        sys.exit(1)

    t = thinpad.ThinpadCloud()

    def signal_handler(sig, frame):
        print('You pressed Ctrl+C!')
        t.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:

        print("--- Login ---")
        t.login(sys.argv[1], sys.argv[2])
        t.allocate_board(thinpad.BOARD_REV2) # Choose Rev.2 or Rev.3

        # Memory Read & Write
        print('-- RAM Read after Write Test --')
        test_data = b"Test Binary\x00\x01\x02\xff\xff"
        t.write_memory(thinpad.MEM_EXT_RAM, test_data, offset=0)
        t.write_memory(thinpad.MEM_EXT_RAM, b'114514', offset=16)
        print("Read Back: ")
        print(t.read_memory(thinpad.MEM_EXT_RAM, 18, offset=4))
        # t.read_memory(thinpad.MEM_FLASH, 0x800000)
        # t.read_memory(thinpad.MEM_BASE_RAM, 0x400000)

        print("Upload Test Bitstream")
        t.upload_design(sys.argv[3])

        switch_and_leds(t)

        # UART Loopback test
        print('-- UART Loopback Test --')
        t.open_uart_port(thinpad.UART_EXT, baud=9600)
        t.write_uart('hello')
        print("received:", bytes(t.read_uart(6, timeout=1)))
    except:
        traceback.print_exc()

    print('-- Disconnect --')
    t.close()

if __name__ == '__main__':
    main()
