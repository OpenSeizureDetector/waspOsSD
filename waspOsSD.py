# Initial go at some OpenSeizureDetector features for wasp-os
# Licence:  GPL3
# Copyright (C) 2021, Graham Jones

#Based on micropython ble_teperature.py example

import wasp


import random
import struct
import time
import machine
import ubluepy

from micropython import const


def updateChars(self, timer_id):
    print("global.updateChars")



class OsdApp():
    NAME = "OSD"

    def __init__(self, msg="Hello World!"):
        self.msg = msg

        self.timer = machine.RTCounter(1, period=50, mode=machine.RTCounter.PERIODIC, callback=updateChars)

        self.notif_enabled = False
        self.uuid_env_sense = ubluepy.UUID("0x181A")  # Environmental Sensing service
        self.uuid_temp = ubluepy.UUID("0x2A6E")  # Temperature characteristic
        self.service = ubluepy.Service(self.uuid_env_sense)


        temp_props = ubluepy.Characteristic.PROP_NOTIFY | \
                     ubluepy.Characteristic.PROP_READ
        temp_attrs = ubluepy.Characteristic.ATTR_CCCD
        self.char_temp = ubluepy.Characteristic(self.uuid_temp,
                                        props=temp_props,
                                        attrs=temp_attrs)

        self.service.addCharacteristic(self.char_temp)

        self.periph = ubluepy.Peripheral()
        self.periph.addService(self.service)
        self.periph.setConnectionHandler(self.event_handler)
        #print("OsdApp.__init__(): stopping advertisment...")
        #self.periph.advertise_stop()
        print("OsdApp.__init__(): starting advertisement...")
        self.periph.advertise(
            device_name="micr_temp",
            services=[self.service])


    def event_handler(self,id, handle, data):
        if id == ubluepy.constants.EVT_GAP_CONNECTED:
            print("CONNETED")

        elif id == ubluepy.constants.EVT_GAP_DISCONNECTED:
            # stop low power timer
            self.timer.stop()
            print("Disconnected")
            # restart advertisment
            #self.periph.advertise_stop()
            self.periph.advertise(device_name="micr_temp",
                                  services=[self.serv_env_sense])

        elif id == ubluepy.constants.EVT_GATTS_WRITE:
            # write to this Characteristic is to CCCD
            if int(data[0]) == 1:
                print("Enabling Notifications")
                self.notif_enabled = True
                # start low power timer
                self.timer.start()
            else:
                print("Disabling Notifications")
                self.notif_enabled = False
                # stop low power timer
                self.timer.stop()


        


    def updateChars(self, timer_id):
        if self.notif_enabled:
            # measure chip temperature
            temp = Temp.read()
            temp = temp * 100
            self.char_temp.write(bytearray([temp & 0xFF, temp >> 8]))



        
    def foreground(self):
        self._draw()
        t = 25
        i = 0

        while True:
            # Write every second, notify every 10 seconds.
            i = (i + 1) % 10
            self.set_temperature(t, notify=i == 0, indicate=False)
            # Random walk the temperature.
            t += random.uniform(-0.5, 0.5)
            time.sleep_ms(1000)


        

    def _draw(self):
        draw = wasp.watch.drawable
        draw.fill()
        draw.string(self.msg, 0, 108, width=240)
