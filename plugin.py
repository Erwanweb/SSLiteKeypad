#!/usr/bin/env python3
# -*- coding: utf-8 -*-


# Author: ErwanBCN,
# Version:    0.0.1: alpha...
# Version:    1.0.1: beta...



"""
<plugin key="ZZ-SSLKEYPAD" name="RONELABS - SS Lite KEYPAD Control" author="ErwanBCN" version="1.0.2" externallink="https://ronelabs.com">
    <description>
        <h2>Security system Lite KEYPAD Control V1.0.1</h2><br/>
        Easily implement in Domoticz a VMC DF Inteliggent Control<br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Password" label="Codes (CSV List)" width="400px" required="true" default="1234"/>
        <param field="Mode1" label="SS Lite widget : Control, Feedback (CSV List of idx)" width="400px" required="true" default=""/>
        <param field="Mode2" label="Keypad order idx" width="400px" required="true" default=""/>
        <param field="Mode3" label="Keypad feedback idx" width="400px" required="true" default=""/>
        <param field="Mode6" label="Logging Level" width="200px">
            <options>
                <option label="Normal" value="Normal"  default="true"/>
                <option label="Verbose" value="Verbose"/>
                <option label="Debug - Python Only" value="2"/>
                <option label="Debug - Basic" value="62"/>
                <option label="Debug - Basic+Messages" value="126"/>
                <option label="Debug - Connections Only" value="16"/>
                <option label="Debug - Connections+Queue" value="144"/>
                <option label="Debug - All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""
# ----------------------------- Imports -----------------------------
import json
import urllib
import urllib.parse as parse
import urllib.request as request
from datetime import datetime, timedelta
import time
import math
import Domoticz

try:
    from Domoticz import Devices, Parameters
except ImportError:
# Permet d'éviter des erreurs à l'analyse statique
    pass

# ----------------------------- Plugin -----------------------------

class deviceparam:

    def __init__(self, unit, nvalue, svalue):
        self.unit = unit
        self.nvalue = nvalue
        self.svalue = svalue

class BasePlugin:
    def __init__(self):
        self.debug = False
        self.loglevel = "Normal"

        now = datetime.now() # Time helper

        self.SS_control_idx = 0
        self.SS_feedback_idx = 0
        self.KP_codes = []
        self.KP_order_idxs = []
        self.KP_feedback_idxs = []
        self.Actual_SS_Level = 0
        self.Actual_KP_level = 0
        self.Actual_KP_texte = False
        self.Previous_KP_texte = False


    # -------------- Life cycle --------------

    def onStart(self):
        Domoticz.Log("onStart called")
        # setup the appropriate logging level
        try:
            debuglevel = int(Parameters["Mode6"])
        except ValueError:
            debuglevel = 0
            self.loglevel = Parameters["Mode6"]
        if debuglevel != 0:
            self.debug = True
            Domoticz.Debugging(debuglevel)
            DumpConfigToLog()
            self.loglevel = "Verbose"
        else:
            self.debug = False
            Domoticz.Debugging(0)

        # Paramètres du Keypad
        self.KP_codes = parseCSV_to_ints(Parameters.get("Password", ""))
        self.KP_order_idxs = parseCSV_to_ints(Parameters.get("Mode2", ""))
        self.KP_feedback_idxs = parseCSV_to_floats(Parameters.get("Mode3", ""))

        # splits SS Lite plugin parameters
        #params = parseCSV(Parameters["Mode1"])
        params = parseCSV_to_ints(Parameters.get("Mode1", ""))
        if len(params) == 2: # Control, Armed, Int.Detect., Alarm, Log
            self.SS_control_idx = CheckParam("Control", params[0], 0)
            self.SS_feedback_idx = CheckParam("Feedback", params[1], 0)
        else:
            Domoticz.Error("Error reading SS Lite (MODE 1) parameters")

        # Set domoticz heartbeat to 1 seconde
        Domoticz.Heartbeat(1)

        # Lecture initiale + maj état
        self.refresh_and_act()

    def onStop(self):
        Domoticz.Log("onStop called")
        Domoticz.Debugging(0)

    def onCommand(self, Unit, Command, Level, Color):
        Domoticz.Log("On command called")

    def onHeartbeat(self):
        Domoticz.Debug("--------------DEBUG : onHeartbeat called")

        #now = datetime.now()

        # refresh values and act
        self.refresh_and_act()


    # OTHER DEF -------------------------------------------------------------------------------------------------------

    # -------------- Main Logic --------------
    def refresh_and_act(self):

        #checking SS Feeback state
        SSCheckFeebackAPI = DomoticzAPI("type=command&param=getdevices&rid={}".format(self.SS_control_idx))
        if SSCheckFeebackAPI and SSCheckFeebackAPI("result"):
            for device in SSCheckFeebackAPI["result"]:
                if "LevelInt" in device:
                    Domoticz.Debug("device: {}-{} = {}".format(device.get("idx"), device.get("Name"), device.get("LevelInt")))
                    actualSSlevel = device["LevelInt"]
                    self.Actual_SS_Level = actualSSlevel

        # checking and updating if needed KP Feeback state
        KPCheckFeebackAPI = DomoticzAPI("type=command&param=getdevices&filter=light&used=true&order=Name")
        if KPCheckFeebackAPI and KPCheckFeebackAPI("result"):
            for device in KPCheckFeebackAPI["result"]:
                idx = int(device["idx"])
                if idx in self.KP_feedback_idxs :
                    if "LevelInt" in device:
                        Domoticz.Debug("device: {}-{} = {}".format(device.get("idx"), device.get("Name"),device.get("LevelInt")))
                        actualKPlevel = device["LevelInt"]
                        self.Actual_KP_level = actualKPlevel
                        # Updating KP feeback if needed
                        if not self.Actual_SS_Level == self.Actual_KP_level:
                            DomoticzAPI("command&param=switchlight&idx={}&switchcmd=Set%20Level&level={}".format(self.KP_feeback_idxs, self.Actual_SS_Level))



        # checking KP order - Feedback Levels : 0= Not Ready |10= Disarmed |20= ArmAllZone (Total) |30= ArmNight (Night) |40= ArmHome (Perimetral) |50=InvalidCode/NotReady(flash3x) |60=Not Ready(neverstop) |70= ExitDelay |80= EntryDelay |90= InAlarm
        """KPCheckControlAPI = DomoticzAPI("type=command&param=getdevices&rid={}".format(self.KP_order_idxs))
        if KPCheckControlAPI and KPCheckControlAPI("result"):
            for device in KPCheckControlAPI["result"]:
                if "Data" in device:
                    Domoticz.Debug("device: {}-{} = {}".format(device.get("idx"), device.get("Name"),device.get("Data")))
                    self.Actual_KP_texte = device["Data"]
                    if not self.Actual_KP_texte == "Waiting"
                        texte = self.Actual_KP_texte
                        mode, code = texte.split(",")
                        if code in self.KP_codes :
                            Domoticz.Log(f"Keypad Code OK pour mode '{mode}'.")
                            if not self.Actual_SS_Level == 0:
                            if mode == "Disarm" :
                                if not self.Actual_SS_Level =< 10 :
                                    DomoticzAPI("command&param=switchlight&idx={}&switchcmd=Set%20Level&level=10".format(self.SS_control_idx))
                                    DomoticzAPI("command&param=switchlight&idx={}&switchcmd=Set%20Level&level=10".format(self.KP_feedback_idxs))
                            else : # System Not ready
                                DomoticzAPI("command&param=switchlight&idx={}&switchcmd=Set%20Level&level=50".format(self.KP_feedback_idxs))
                                time.sleep(2)
                                DomoticzAPI("command&param=udevice&idx=IDX&nvalue=0&svalue=Waiting{}".format(self.KP_order_idxs))

                        else : # BAD CODE
                            Domoticz.Log(f"Keypad CODE ERROR.")
                            DomoticzAPI("command&param=switchlight&idx={}&switchcmd=Set%20Level&level=50".format(self.KP_feedback_idxs))
                            DomoticzAPI("command&param=udevice&idx=IDX&nvalue=0&svalue=Waiting{}".format(self.KP_order_idxs))
"""

    # -------------- get_device_by_idx --------------
    """def get_device_by_idx(self, idx):
        res = DomoticzAPI(f"type=devices&rid={idx}")
        if res and 'result' in res and len(res['result']) > 0:
            return res['result'][0]
        Domoticz.Error(f"Device idx {idx} introuvable")
        return None"""

    # -------------- Write Log --------------
    def WriteLog(self, message, level="Normal"):

        if self.loglevel == "Verbose" and level == "Verbose":
            Domoticz.Log(message)
        elif level == "Normal":
            Domoticz.Log(message)


# Plugin helpers & utility functions -----------------------------------------------------------------------------------

# Domoticz API  --------------------------------------------------------------------------------------------------------

def DomoticzAPI(APICall):
    resultJson = None
    url = f"http://127.0.0.1:8080/json.htm?{parse.quote(APICall, safe='&=')}"

    try:
        Domoticz.Debug(f"Domoticz API request: {url}")
        req = request.Request(url)
        response = request.urlopen(req)

        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson.get("status") == "ERR":
                Domoticz.Error(f"Domoticz API returned an error: status = {resultJson.get('status')}")
                resultJson = None
        else:
            Domoticz.Error(f"Domoticz API: HTTP error = {response.status}")

    except urllib.error.HTTPError as e:
        Domoticz.Error(f"HTTP error calling '{url}': {e}")
    except urllib.error.URLError as e:
        Domoticz.Error(f"URL error calling '{url}': {e}")
    except json.JSONDecodeError as e:
        Domoticz.Error(f"JSON decoding error: {e}")
    except Exception as e:
        Domoticz.Error(f"Error calling '{url}': {e}")

    return resultJson

# CSV and param Helpers ------------------------------------------------------------------------------------------------
def parseCSV_to_ints(s):
    return [int(x.strip()) for x in s.split(',') if x.strip().isdigit()]

def parseCSV_to_floats(s):
    out = []
    for x in s.split(','):
        try:
            out.append(float(x.strip()))
        except Exception:
            pass
    return out

def CheckParam(name, value, default):
    try:
        param = int(value)
    except ValueError:
        param = default
        Domoticz.Error("Parameter '{}' has an invalid value of '{}' ! defaut of '{}' is instead used.".format(name, value, default))
    return param

# Generic helper functions ---------------------------------------------------------------------------------------------

def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return

# Glue - Plugin functions ----------------------------------------------------------------------------------------------

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onCommand(Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Color)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

# End--------------------------------------------------------------- ---------------------------------------------------