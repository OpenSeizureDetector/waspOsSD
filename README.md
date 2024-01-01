# waspOsSD

This is the micropython app developed by user @rennard in early 2022.   
I did not manage to get it working on my PineTime, so it stalled for a while.
I am now trying to get OSD working on Pinetime and am trying this Micropython version first.
My development notes below....


## GJ Notes
   - Cloned https://github.com/wasp-os/wasp-os/ and built it for pinetime.
   - The build-pinetime folder then contained some useful binaries:
       - reloader-mcuboot.zip - flashing this installs the wasp-os bootloader, that includes integral firmware upload (dfu) support.
       - micropython.zip - once the wasp-os bootloader is running, it can be used to flash micropyton.zip to get wasp-os running.
   - I had lots of trouble trying to flash the firmware
       - NRFConnect looks like it is working, then stalls at 100% complete.
       - Gadgetbridge sometimes seems to work and other times does not detect the watch.
       - tools/wasptool has a --dfu mode, but this does not seem to work.
       - Using "tools/ota-dfu/dfu.py -z build-pinetime/micropython.zip -a f8:a1:fd:6b:de:93 --legacy" does seem to work though.
   - Running waspOsSD on the watch
      - wasptool --upload waspOsSD.py works ok
      - wasptool --console starts a python console on the watch.
      - from waspOsSD import OsdApp fails with a memory error.
      - Pre-compile the python code with:
         ../wasp-os/micropython/mpy-cross/mpy-cross -mno-unicode -march=armv7m waspOsSD.py
      - Then uplaod the pre-compiled file with wasptool --binary --upload waspOsSD.mpy
      - But still got errors when importing.  I realised I was not complying with the naming conventions [here](https://wasp-os.readthedocs.io/en/latest/appguide.html#app-naming-conventions-and-placement) so re-named to wasp_os_sd.py and the class to WaspOsSdApp
      - ...but running from wasp_os_sd import WaspOsSdApp again crashed on memory error

