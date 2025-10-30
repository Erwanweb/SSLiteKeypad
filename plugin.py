#!/usr/bin/env python3
# -*- coding: utf-8 -*-


# Author: ErwanBCN,
# Version:    0.0.1: alpha...
# Version:    1.0.1: beta...



"""
<plugin key="ZZ-SSLKEYPAD" name="RONELABS - SS Lite KEYPAD Control" author="ErwanBCN" version="1.0.2" externallink="https://ronelabs.com">
    <description>
        <h2>Security system Lite KEYPAD Control V1.0.1</h2><br/>
        Easily implement in Domoticz a Keypad In Ronelabs's SS Lite<br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Password" label="Codes or TagID (CSV List)" width="400px" required="true" default="1234"/>
        <param field="Mode1" label="SS Lite widget idx : Control, Feedback (CSV List of idx)" width="100px" required="true" default=""/>
        <param field="Mode2" label="Keypad order idxs (CSV List of idx)" width="400px" required="true" default=""/>
        <param field="Mode3" label="Keypad feedback idxs (CSV List of idx)" width="400px" required="true" default=""/>
        <param field="Mode5" label="Arming type" width="200px">
            <options>
                <option label="With Code" value="1" default="true"/>
                <option label="Without Code" value="0"/>
            </options>
        </param>
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
        self.Arming_type = 1
        self.Softrestartingtime = datetime.now()


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
        self.KP_feedback_idxs = parseCSV_to_ints(Parameters.get("Mode3", ""))

        # Arming type : 1 = With Code (défaut), 0 = Without Code
        raw_mode5 = Parameters.get("Mode5")
        self.Arming_type = 1
        try:
            if raw_mode5 is not None and str(raw_mode5).strip().lower() not in ("", "null"):
                self.Arming_type = int(raw_mode5)
        except Exception:
            self.Arming_type = 1
        Domoticz.Log(f"Arming_type = {self.Arming_type}")

        # splits SS Lite plugin parameters
        params = parseCSV_to_ints(Parameters.get("Mode1", ""))
        if len(params) == 2: # Control, Feedback
            self.SS_control_idx = CheckParam("Control", params[0], 0)
            self.SS_feedback_idx = CheckParam("Feedback", params[1], 0)
        else:
            Domoticz.Error("Error reading SS Lite widget idx (MODE 1) parameters")

        # Set domoticz heartbeat to 1 seconde
        Domoticz.Heartbeat(5)

        # Delay on plugin starting
        self.Softrestartingtime = datetime.now()
        Domoticz.Debug("SS Lite plugin is just now restarting")

    def onStop(self):
        Domoticz.Log("onStop called")
        Domoticz.Debugging(0)

    def onCommand(self, Unit, Command, Level, Color):
        Domoticz.Log("On command called")

    def onHeartbeat(self):
        Domoticz.Debug("--------------DEBUG : onHeartbeat called")

        now = datetime.now()

        if self.Softrestartingtime + timedelta(seconds=30) <= now: #Domoticz or plugin just restarting, so wait for Alarm initilization
            # refresh values and act
            self.refresh_and_act()
        else :
            Domoticz.Debug("--------------DEBUG : Plugin starting delay")


    # OTHER DEF -------------------------------------------------------------------------------------------------------

    # -------------- Main Logic --------------
    def refresh_and_act(self):

        # checking SS Feedback state
        SSCheckFeedbackAPI = DomoticzAPI("type=command&param=getdevices&rid={}".format(self.SS_feedback_idx))
        if SSCheckFeedbackAPI and "result" in SSCheckFeedbackAPI:
            for device in SSCheckFeedbackAPI["result"]:
                if "LevelInt" in device:
                    Domoticz.Debug("--------------DEBUG : device: {} - {} = {}".format(device.get("idx"), device.get("Name"), device.get("LevelInt")))
                    self.Actual_SS_Level = device["LevelInt"]

        # checking and updating if needed KP Feedback state
        KPCheckFeebackAPI = DomoticzAPI("type=command&param=getdevices&filter=light&used=true&order=Name")
        if KPCheckFeebackAPI and "result" in KPCheckFeebackAPI:
            for device in KPCheckFeebackAPI["result"]:
                idx = int(device["idx"])
                if idx in self.KP_feedback_idxs:
                    if "LevelInt" in device:
                        Domoticz.Debug("--------------DEBUG : device: {} - {} = {}".format(device.get("idx"), device.get("Name"), device.get("LevelInt")))
                        self.Actual_KP_level = device["LevelInt"]
                        # Updating KP feedback if needed
                        if self.Actual_SS_Level != self.Actual_KP_level:
                            # Boucler sur les idx de feedback et pousser le niveau SS actuel
                            for f_idx in self.KP_feedback_idxs:
                                dz_switchlevel(f_idx, self.Actual_SS_Level)

        # checking KP order
        KPCheckOrderAPI = DomoticzAPI("type=command&param=getdevices&filter=utility&used=true&order=Name")
        if KPCheckOrderAPI and "result" in KPCheckOrderAPI:
            for device in KPCheckOrderAPI["result"]:
                idx = int(device["idx"])
                if idx in self.KP_order_idxs and "Data" in device:
                    Domoticz.Debug(
                        "--------------DEBUG : device: {} - {} = {}".format(device.get("idx"), device.get("Name"),
                                                                            device.get("Data")))
                    self.Actual_KP_texte = device["Data"]

                    # 0) Pas d'ordre ? on ignore.
                    if self.Actual_KP_texte == "Waiting":
                        continue

                    # 1) Parsing robuste : "Mode,1234"
                    try:
                        mode, code_str = [x.strip() for x in self.Actual_KP_texte.split(",", 1)]
                    except Exception:
                        Domoticz.Error(f"Keypad order invalide: '{self.Actual_KP_texte}'")
                        DomoticzAPI("type=command&param=udevice&idx={}&nvalue=0&svalue=Waiting".format(idx))
                        continue

                    Domoticz.Debug(f"Keypad order mode '{mode}', code '{code_str}'.")

                    # 2) Normaliser le code en int ; -1 => invalide
                    try:
                        code_val = int(code_str)
                    except ValueError:
                        code_val = -1

                    # 3) Règles d'armement / désarmement

                    can_arm_without_code = (self.Arming_type == 0)
                    code_ok = (code_val in self.KP_codes)
                    ready_to_arm = (self.Actual_SS_Level == 10)  # On ne peut armer QUE si l'état actuel = 10 Disarmed
                    system_armed = (self.Actual_SS_Level >= 20)  # On ne peut desarmer QUE si l'état actuel = 20,30,40 Armed

                    def reset_text_field():
                        DomoticzAPI("type=command&param=udevice&idx={}&nvalue=0&svalue=Waiting".format(idx))

                    def feedback_error():
                        for f_idx in self.KP_feedback_idxs:
                            dz_switchlevel(f_idx, 50)  # petit flash/retour visuel

                    if mode == "Disarm":
                        if code_ok:
                            Domoticz.Log("Keypad Code OK pour 'Disarm'")
                            if system_armed:
                                dz_switchlevel(self.SS_control_idx, 10)  # 10 = désarmé
                            else:
                                # déjà désarmé → feedback d'erreur (optionnel) puis reset
                                feedback_error()
                            time.sleep(2)
                            reset_text_field()
                        else:
                            Domoticz.Log("--- !!! Keypad CODE ERROR (Disarm) !!!")
                            feedback_error()
                            time.sleep(2)
                            reset_text_field()

                    elif mode in ("ArmHome", "ArmNight", "ArmAllZones"):

                        if (code_ok or can_arm_without_code) and ready_to_arm:
                            # OK → on arme selon le mode
                            if mode == "ArmHome":
                                dz_switchlevel(self.SS_control_idx, 20)
                            elif mode == "ArmNight":
                                dz_switchlevel(self.SS_control_idx, 30)
                            elif mode == "ArmAllZones":
                                dz_switchlevel(self.SS_control_idx, 40)
                            reset_text_field()

                        else:
                            # Conditions non remplies → erreur
                            Domoticz.Log(f"--- ARMING ORDER ERROR ({mode}) : "
                                         f"--- CodeOK= {code_ok}, AllowNoCode= {can_arm_without_code}, ReadyToArm= {ready_to_arm}, SS Armed= {system_armed}, SS Level= {self.Actual_SS_Level}")
                            feedback_error()
                            time.sleep(2)
                            reset_text_field()

                    else:
                        Domoticz.Error(f"Mode inconnu: '{mode}'")
                        feedback_error()
                        time.sleep(2)
                        reset_text_field()

    # -------------- Write Log --------------
    def WriteLog(self, message, level="Normal"):

        if self.loglevel == "Verbose" and level == "Verbose":
            Domoticz.Log(message)
        elif level == "Normal":
            Domoticz.Log(message)


# Plugin helpers & utility functions -----------------------------------------------------------------------------------

def dz_switchlevel(idx, level):
    DomoticzAPI("type=command&param=switchlight&idx={}&switchcmd=Set Level&level={}".format(int(idx), int(level)))
    return


# Domoticz API  --------------------------------------------------------------------------------------------------------

def DomoticzAPI(APICall):
    resultJson = None
    url = f"http://127.0.0.1:8080/json.htm?{parse.quote(APICall, safe='&=%')}"

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