#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Install Dependencies:
#   pip install requests socketIO-client
# Or
#   pip install -r requirements.txt

import thinpad
import sys
import time
import logging
import signal
import traceback
import random

def switch_and_leds(t):
    print("-- LED & Switch Test --")

    # Set 32 DIP switches 
    for i in range(32):
        t.set_dip_sw(i, 1)
    # Or set them all at once
    t.set_all_switches(dip_sw=[0]*32)
    time.sleep(1)

    for i in range(32):
        t.set_dip_sw(i, 1)
        time.sleep(0.5)

        raw = t.get_dpys() << 16 | t.get_leds()
        print(f'DPY, LED: {raw:x}')

        assert raw == (1 << (i+1)) - 1

def main():
    print("--- SDK Version:", thinpad.__version__, '---')
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('thinpad.cloud').setLevel(logging.DEBUG)
    # logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)
    # logging.getLogger('socketIO-client-2').setLevel(logging.INFO)

    if len(sys.argv) < 4:
        print('Usage:', sys.argv[0], '<username> <password> <hwtest.bit>')
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
        t.allocate_board(thinpad.BOARD_LOONG) # Choose Rev.2 or Rev.3

        # Memory Read & Write
        print('-- RAM Read after Write Test --')
        for mem in (thinpad.MEM_BASE_RAM, thinpad.MEM_EXT_RAM):
            random_bytes = bytes([random.getrandbits(8) for _ in range(0, 1024**2*4)])
            print("Writing: ")
            t.write_memory(mem, random_bytes, offset=0)
            print("Read Back: ")
            read_back = t.read_memory(mem, len(random_bytes), offset=0)
            assert read_back == random_bytes

        print("Upload Test Bitstream")
        t.upload_design(sys.argv[3])

        # Reset to start the self-test
        t.set_reset_btn(1)
        time.sleep(0.01)
        t.set_reset_btn(0)
        time.sleep(2)

        result = t.get_leds()
        print(f"result={result:x}")
        assert result >> 8 == (result & 0xff ^ 0xff)
        if result & 1:
            print("RAM error")
            return
        if result & 2:
            print('Flash error')
            return

        # UART Loopback test
        t.open_uart_port(thinpad.UART_EXT, baud=115200)
        while True:
            if random.randint(0, 99) < 50:
                print('-- UART Loopback Test --')
                t.write_uart('hello')
                r = bytes(t.read_uart(5, timeout=1))
                if len(r) != 5:
                    print(f"error: received({len(r)}):", r)
            else: 
                switch_and_leds(t)

            time.sleep(0.1 + random.random())
    except:
        traceback.print_exc()
    finally:
        print('-- Disconnect --')
        t.close()

if __name__ == '__main__':
    main()
