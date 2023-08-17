# Rigol DP832 powersupply control library (unofficial, Python)

This is a _currently under development_ control library for the DP832
power supply. It implements the ```PowerSupply``` base class from
the [pylabdevs](https://github.com/tspspi/pylabdevs/tree/master) base
class.

Currently only control via Ethernet is implemented in the ```DP832LAN```
class.

## Simple usage example

```
with DP832LAN("10.4.1.12", logLevel = "DEBUG") as dp:
   print(dp.idn())
   dp.setChannelEnable(True, 1)
   dp.setVoltage(23, 1)
   dp.setCurrent(1.2, 1)
   print(f"Measured voltage {dp.getVoltage(1)} and current {dp.getCurrent(1)}")
   dp.setChannelEnable(False, 1)
```
