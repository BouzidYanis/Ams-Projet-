# -*- coding: utf-8 -*-
import qi
import time
import wave
import sys
import numpy as np
import subprocess

IP_WINDOWS = "10.255.255.254"
IP_WSL = "10.40.0.9"

IP_ROBOT = "192.168.13.230"
PORT_ROBOT = "9559"


def setup_tunnels(robot_ip, wsl_ip, port_robot=9559, port_wsl_relay=9560):
    """
    Sets up bidirectional tunnels between WSL and Pepper via Windows.
    Tunnel 1 (Outbound): Windows:9560 -> Pepper:9559
    Tunnel 2 (Inbound):  Windows:9559 -> WSL:9559
    """
  
    # We combine both commands into one PowerShell call to minimize UAC popups
    commands = [
        # Tunnel 1: Outbound (Commands from WSL to Robot)
        "netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport={0} connectaddress={1} connectport={2}".format(
            port_wsl_relay, robot_ip, port_robot),
        
        # Tunnel 2: Inbound (Audio from Robot back to WSL)
        "netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport={0} connectaddress={1} connectport={2}".format(
            port_robot, wsl_ip, port_robot)
    ]
    
    # Join commands with a semicolon for PowerShell
    full_command = "; ".join(commands)
    
    ps_cmd = (
        "Start-Process powershell -Verb RunAs -ArgumentList "
        "'-Command \"{0}\"'"
    ).format(full_command)
    
    try:
        subprocess.check_call(["powershell.exe", "-Command", ps_cmd])
        print("[TUNNEL] Success: Bidirectional bridge established.")
        print("  - Outbound: Windows:{} -> Pepper:{}".format(port_wsl_relay, robot_ip))
        print("  - Inbound:  Windows:{} -> WSL:{}".format(port_robot, wsl_ip))
        time.sleep(2) # Give Windows a moment to apply the rules
    except Exception as e:
        print("[TUNNEL] Error setting up tunnels: {}. Ensure you are Admin.".format(e))

class SoundReceiver(object):
    """ 
    This class MUST be a 'new-style' object for qi registration.
    The method name 'processRemote' is hardcoded in the Pepper NAOqi framework.
    """
    def __init__(self, robot_instance):
        self.robot = robot_instance

    def processRemote(self, nbOfChannels, nbrSamples, timeStamp, buffer):
        """ Callback from Pepper's ALAudioDevice """
        self.robot._on_audio_data(buffer)

class PepperRobot:
    def __init__(self, robot_ip="192.168.13.230", win_gateway = IP_WINDOWS, wsl_ip=IP_WSL):
        # 1. Establish the bidirectional network bridge
        # Tunnel A: Windows:9560 -> Pepper:9559 (Commands)
        # Tunnel B: Windows:9559 -> WSL:9559 (Audio Return)
        setup_tunnels(robot_ip, wsl_ip)
        
        # 2. IP & Port Definitions
        self.win_gateway = win_gateway
        self.wsl_ip = wsl_ip                 # Your WSL instance IP
        self.port = 9560                     # We connect to the command relay port
        
        # 3. Attributes from previous version
        self.session = qi.Session()
        self.module_name = "SoundReceiverModule"
        self.audio_buffer = []
        self.is_recording = False

        try:
            # 4. IMPORTANT: Prepare the 'Return Address' for Audio
            # 1. Listen on all interfaces inside WSL so the tunnel can hit it
            self.session.listen("tcp://0.0.0.0:9559")

            # 2. Tell Pepper your "public" name is the Windows Gateway
            # This forces Pepper to use the Tunnel (Windows:9559) for callbacks
            self.session.setServiceDirectoryEndpoints(["tcp://{}:9559".format(self.win_gateway)])
            
            # 5. Connect to Pepper via the Windows Outbound Tunnel
            #self.session.connect("tcp://{}:{}".format(self.win_gateway, self.port))
            self.session.connect("tcp://127.0.0.1:9560")

            # 6. Initialize Services
            self.tts = self.session.service("ALAnimatedSpeech")
            self.audio_device = self.session.service("ALAudioDevice")

            # 7. Register the Audio Collector (The "Ear")
            self.collector = SoundReceiver(self)
            self.service_id = self.session.registerService(self.module_name, self.collector)

            print("[SUCCESS] Connected to Pepper via Double-Tunnel.")
            print("         Listening for Audio on {}:9559".format(self.wsl_ip))
            
        except Exception as e:
            print("[ERROR] Connection failed: {}".format(e))
            sys.exit(1)

    def _on_audio_data(self, data):
        """ Efficiently collect raw bytes """
        if self.is_recording:
            # Pepper sends 16-bit PCM data as a buffer
            self.audio_buffer.append(data)

    def say(self, text):
        print("[ROBOT] Saying: {}".format(text))
        self.tts.say(text)

    def record_to_pc(self, duration=5, filename="input.wav"):
        try:
            print("[AUDIO] Recording for {}s...".format(duration))
            self.audio_buffer = []
            self.is_recording = True

            # Configuration: 16000Hz, 3 (Front Mic), 0 (Interleaved)
            # 16kHz is preferred for Whisper/ASR
            self.audio_device.setClientPreferences(self.module_name, 16000, 3, 0)
            self.audio_device.subscribe(self.module_name)

            time.sleep(duration)

            self.audio_device.unsubscribe(self.module_name)
            self.is_recording = False

            # Save to WAV
            raw_data = b"".join(self.audio_buffer)
            if not raw_data:
                print("[ERROR] No audio data received! Check your network/firewall.")
                return None

            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2) # 16-bit
                wf.setframerate(16000)
                wf.writeframes(raw_data)
            
            print("[SUCCESS] Saved to {}".format(filename))
            return filename
        except Exception as e:
            print("[ERROR] Recording failed: {}".format(e))
            self.is_recording = False
            return None

    def shutdown(self):
        print("[SHUTDOWN] Cleaning up...")
        try:
            self.audio_device.unsubscribe(self.module_name)
        except: pass
        
        if hasattr(self, 'service_id'):
            self.session.unregisterService(self.service_id)
        
        if self.session.isConnected():
            self.session.close()

if __name__ == "__main__":
    # Note: Passed IP_WINDOWS as the second argument for the gateway
    robot = PepperRobot(IP_ROBOT, IP_WINDOWS, IP_WSL)
    
    try:
        if robot.session.isConnected():
            print("[SUCCESS] Bridge Active: WSL <-> Windows <-> Pepper")
            
            robot.say("Connection established. Recording now.")
            audio_file = robot.record_to_pc(duration=5, filename="capture.wav")
            
            if audio_file:
                import os
                if os.path.getsize(audio_file) > 1000: # Ensure more than just a header
                    print("[RECORDING SUCCESS] Saved {} bytes to {}".format(os.path.getsize(audio_file), audio_file))
                else:
                    print("[ERROR] File empty. Check Windows Firewall for Port 9559.")
        else:
            print("[ERROR] Failed to connect to Pepper.")

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        robot.shutdown()