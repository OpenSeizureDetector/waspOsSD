from ubluepy import Service, Characteristic, UUID, Peripheral, constants
from machine import I2C
import machine
import ubluepy
import watch
import wasp
import ppg
import bma42x
import time
import struct
import math

####################################################
# TODO
# - make sure battery read is stable / read less frequently
# - make acc correct format
#
####################################################


####################################################
# Bluetooth
####################################################

connected = False
battery_write = False
accelerometer_write = False
heart_rate_write = False

event = "none"
batt_event_data = None
hr_event_data = None
acc_event_data = None
event_handle = ""
peripheral = Peripheral()
event_count = 0

# UUIDs used from https://github.com/OpenSeizureDetector/Android_Pebble_SD/blob/master/app/src/main/java/uk/org/openseizuredetector/SdDataSourceBLE.java#L85
# & https://btprodspecificationrefs.blob.core.windows.net/assigned-values/16-bit%20UUID%20Numbers%20Document.pdf


# Battery characteristic
_BATT_CHAR_UUID = UUID("0x85eb")
_BATT_CHAR = Characteristic(
    _BATT_CHAR_UUID,
    props=Characteristic.PROP_NOTIFY | Characteristic.PROP_READ,
    attrs=Characteristic.ATTR_CCCD,
)

# Accelerometer characteristic
_ACCELEROMETER_UUID = UUID("0x85ea")
_ACCELEROMETER_CHAR = Characteristic(
    _ACCELEROMETER_UUID,
    props=Characteristic.PROP_NOTIFY | Characteristic.PROP_READ,
    attrs=Characteristic.ATTR_CCCD,
)

# OSD service
_OSD_SERVICE_UUID = UUID("0x85e9")
_OSD_SERVICE = Service(_OSD_SERVICE_UUID)
_OSD_SERVICE.addCharacteristic(_BATT_CHAR)
_OSD_SERVICE.addCharacteristic(_ACCELEROMETER_CHAR)

# Heart Rate service
_HEART_RATE_UUID = UUID("0x180D")
_HEART_RATE_SERVICE = Service(_HEART_RATE_UUID)
_HEART_RATE_CHAR_UUID = UUID("0x2A37")
_HEART_RATE_CHAR = Characteristic(
    _HEART_RATE_CHAR_UUID,
    props=Characteristic.PROP_NOTIFY | Characteristic.PROP_READ,
    attrs=Characteristic.ATTR_CCCD,
)
_HEART_RATE_SERVICE.addCharacteristic(_HEART_RATE_CHAR)


class BleWaspOSProfile:
    def __init__(self):
        self.batt = watch.battery
        self.set_msg = watch.boot_msg
        self._ble = peripheral
        self._vib = watch.vibrator
        self._rtc = watch.rtc

        self._ble.addService(_HEART_RATE_SERVICE)
        self._ble.addService(_OSD_SERVICE)
        self._ble.setConnectionHandler(self.event_handler)
        self._ble.advertise_stop()
        self.advertise()

    def advertise(self):
        self._ble.advertise(
            device_name="pinetime",
        )

    def update(self):
        pass

    def event_handler(self, event_id, handle, data):
        global event, connected, event_handle, accelerometer_write, battery_write, heart_rate_write, batt_event_data, acc_event_data, hr_event_data, event_count
        event = event_id

        event_count = event_count + 1

        # Handle received is 1 less than handle set locally, presumably a 0 index issue
        handle = handle - 1

        if event_id == constants.EVT_GAP_CONNECTED:
            # stop advertising & indicate 'connected'
            connected = True

            self._ble.advertise_stop()
            self._vib.pulse()

        elif event_id == constants.EVT_GAP_DISCONNECTED:
            # stop low power timer, indicate 'disconnected', & restart advertisment
            connected = False
            accelerometer_write = False
            battery_write = False
            heart_rate_write = False

            self._vib.pulse()
            self.advertise()

        elif event_id == constants.EVT_GATTS_WRITE:
            if not connected:
                raise Exception("Invalid state, not connected")

            enable = int(data[0]) == 1

            if handle == _ACCELEROMETER_CHAR.getHandle():
                acc_event_data = data
                accelerometer_write = enable
            elif handle == _BATT_CHAR.getHandle():
                batt_event_data = data
                battery_write = enable
            elif handle == _HEART_RATE_CHAR.getHandle():
                heart_rate_write = enable
                hr_event_data = data


####################################################
# Accelerometer
####################################################

GRAVITY_EARTH = 9.80665
# Holds the total number of accel x, y and z axes sample counts to be printed
ACCEL_SAMPLE_COUNT = 100


class Accelerometer:
    def __init__(self):
        i2c = I2C(1, scl="I2C_SCL", sda="I2C_SDA")
        self._bma = bma42x.BMA42X(i2c)
        self._accel_conf = {}

        self._bma.init()

        # There is no hardware reset capability so issue a software reset
        # instead.
        self._bma.set_command_register(0xB6)
        time.sleep(0.20)

        # Upload the configuration file to enable the features of the sensor.
        self._bma.write_config_file()

        # Enable the accelerometer
        self._bma.set_accel_enable(True)

        # Accelerometer Configuration Setting
        # Output data Rate
        self._accel_conf["odr"] = bma42x.OUTPUT_DATA_RATE_100HZ

        # Gravity range of the sensor (+/- 2G, 4G, 8G, 16G)
        self._accel_conf["range"] = bma42x.ACCEL_RANGE_2G

        # Bandwidth configure number of sensor samples required to average
        # if value = 2, then 4 samples are averaged
        # averaged samples = 2^(val(accel bandwidth))
        # Note1 : More info refer datasheets
        # Note2 : A higher number of averaged samples will result in a lower noise
        # level of the signal, but since the performance power mode phase is
        # increased, the power consumption will also rise.
        self._accel_conf["bandwidth"] = bma42x.ACCEL_NORMAL_AVG4

        # Enable the filter performance mode where averaging of samples
        # will be done based on above set bandwidth and ODR.
        # There are two modes
        #  0 -> Averaging samples (Default)
        #  1 -> No averaging
        # For more info on No Averaging mode refer datasheets.
        self._accel_conf["perf_mode"] = bma42x.CIC_AVG_MODE

        # Set the accel configurations
        self._bma.set_accel_config(**self._accel_conf)

        print("Ax[m/s2], Ay[m/s2], Az[m/s2]")

    def read(self):
        (x, y, z) = self._bma.read_accel_xyz()

        # Converting lsb to meters per seconds square for 12 bit accelerometer
        # at 2G range
        x = self.lsb_to_ms2(x, 2, 12)
        y = self.lsb_to_ms2(y, 2, 12)
        z = self.lsb_to_ms2(z, 2, 12)

        return math.sqrt(x ** 2 + y ** 2 + z ** 2)

    def lsb_to_ms2(self, val, g_range, bit_width):
        """Converts raw sensor values(LSB) to meters per seconds square.

        :param val: Raw sensor value
        :param g_range: Accel Range selected (2G, 4G, 8G, 16G).
        :param bit_width: Resolution of the sensor.
        :return: Accel values in meters per second square.
        """
        half_scale = (1 << bit_width) / 2

        return GRAVITY_EARTH * val * g_range / half_scale


####################################################
# App
####################################################

SAMPLE_FREQUENCY_HZ = 100
SAMPLE_PERIOD_MS = 1000
SAMPLE_WAIT_TIME = SAMPLE_PERIOD_MS / SAMPLE_FREQUENCY_HZ


class WaspOsSdApp:
    NAME = "OSD"

    def __init__(self):
        self._enabled = False
        self._debug = True
        self._bleprofile = BleWaspOSProfile()

        self._hrdata = None
        self._hr = None

        self._accelerometer = Accelerometer()
        self._accelerometer_data = []
        self._n_samp = 0

    def enable(self):
        self._enable = True
        wasp.watch.hrs.enable()
        wasp.system.request_tick(1000 // 8)

        self._hrdata = ppg.PPG(wasp.watch.hrs.read_hrs())
        if self._debug:
            self._hrdata.enable_debug()
        self._x = 0

    def disable(self):
        self._enabled = False
        self._hrdata = None
        wasp.watch.hrs.disable()

    def foreground(self):
        self._draw()
        self.enable()
        wasp.system.request_tick(1000 / 25)  # 25hz

    def background(self):
        # TODO make it such that the user has to confirm disabling monitoring
        self.disable()

    def _draw(self):
        global event, connected, event_handle, hr_event_data, acc_event_data, event_count

        draw = wasp.watch.drawable
        draw.set_color(wasp.system.theme("bright"))
        draw.fill()

        def bool_to_short_str(value):
            return "t" if value else "f"

        if self._debug:
            draw.string(
                "connected" if connected else "not connected",
                0,
                10,
                width=240,
            )

            # hr debug
            draw.string(
                "hr: "
                + bool_to_short_str(heart_rate_write)
                + ":"
                + ("hr not found" if self._hr is None else "{}bpm".format(self._hr)),
                0,
                30,
                width=240,
            )

            # acc debug
            draw.string(
                "acc: " + bool_to_short_str(accelerometer_write), 0, 50, width=240
            )
            draw.string(str(self._accelerometer.read()), 0, 70, width=240)

            # battery debug
            self._draw_battery_debug()

    def _draw_battery_debug(self):
        global batt_event_data

        draw = wasp.watch.drawable
        battery_level = 0

        def bool_to_short_str(value):
            return "t" if value else "f"

        if not watch.battery.charging():
            battery_level = watch.battery.level()

        draw.string(
            "batt: "
            + bool_to_short_str(battery_write)
            + ":level-"
            + str(battery_level),
            0,
            90,
            width=240,
        )

    def read_accelerometer(self):
        global accelerometer_write

        data = self._accelerometer.read()
        if accelerometer_write:
            _ACCELEROMETER_CHAR.write(struct.pack("f", data))

    def _subtick(self, ticks):
        global heart_rate_write

        draw = wasp.watch.drawable
        draw.set_color(wasp.system.theme("bright"))

        self._hrdata.preprocess(wasp.watch.hrs.read_hrs())

        # TODO figure out why this takes ages to reach 240, should be 3 a second?
        if len(self._hrdata.data) >= 240:
            self._hr = self._hrdata.get_heart_rate()

            if self._hr is not None:
                self._draw()

            if self._hr is not None and heart_rate_write:
                _HEART_RATE_CHAR.write(bytearray([0, self._hr]))
            else:
                # TODO not sure
                pass

        x = self._x
        x += 2
        if x >= 240:
            x = 0
        self._x = x

    def read_battery(self):
        global battery_write

        if not battery_write:
            return

        battery_level = None
        if watch.battery.charging():
            battery_level = 0
        else:
            battery_level = watch.battery.level()

        _BATT_CHAR.write(bytearray([battery_level]))

    # Don't sleep, as app won't receive tick in sleep state
    def sleep(self):
        return False

    # Keep app receiving ticks but allow screen to turn off
    def run_in_background(self):
        return True

    # Copied from heart.py
    def tick(self, ticks):
        t = machine.Timer(id=1, period=8000000)
        t.start()

        self._subtick(1)
        while t.time() < 41666:
            pass
        self._subtick(1)
        while t.time() < 83332:
            pass
        self._subtick(1)

        self.read_accelerometer()
        self.read_battery()

        t.stop()
        del t

    @property
    def debug(self):
        return self._debug

    @debug.setter
    def debug(self, value):
        self._debug = value
        if value and self._hrdata:
            self._hrdata.enable_debug()
