# picobot_main.py — Mission: Manipulate object at end marker, return to start
# Uses same AP + web server style as your line follower main.py

import network
import socket
import json
from time import sleep, ticks_ms, ticks_diff
from machine import Pin, Timer
import picobot_motors
import picobot_arm

# ------------------------
# AP Setup (exact style as your line follower)
# ------------------------
ssid = 'picobot-prog'
password = '12345678'
led = Pin("LED", Pin.OUT)

ap = network.WLAN(network.AP_IF)
ap.config(essid=ssid, password=password)
ap.active(True)

while ap.active() == False:
    pass

print('Connection successful')
print(ap.ifconfig())
led.on()  # LED ON when AP is active & init complete

# ------------------------
# Motor driver & Arm
# ------------------------
motor_driver = picobot_motors.MotorDriver(debug=False)
arm = picobot_arm.PicoBotArm(init_servos=True)  # uses your existing arm class

# ------------------------
# Sensors: right → left
# ------------------------
sensors = [
    Pin(8, Pin.IN, Pin.PULL_UP),   # Right
    Pin(9, Pin.IN, Pin.PULL_UP),   # Right-middle
    Pin(13, Pin.IN, Pin.PULL_UP),  # Center
    Pin(14, Pin.IN, Pin.PULL_UP),  # Left-middle
    Pin(15, Pin.IN, Pin.PULL_UP)   # Left
]

# ------------------------
# Global vars (line follower)
# ------------------------
robot_running = False
line_lost = False
line_lost_time = 0
last_direction = "FORWARD"
search_intensity = 1.0  # Start with normal intensity

# Line follower defaults (unchanged)
base_speed = 30
slight_ratio = 0.9
mild_ratio = 0.75
hard_ratio = 0.6
grace_period = 800  # ms
search_ratio = 0.4

# ------------------------
# Mission State Machine
# ------------------------
# Modes: "IDLE", "OUTBOUND", "ARM_SEQ", "RETURNING", "DONE"
mission_mode = "IDLE"
mission_stage = 0
mission_stage_started = 0
mission_status_text = "Stopped"

# Mission tunables (times are ms)
# NOTE: Base servo = channel 0, Arm (elevation) = channel 1, Gripper = channel 2 (same as your UI)
# We use absolute angles (0..180); base_center + offsets for sides
base_center = 90
base_offset_deg = 45         # lateral rotation magnitude
base_first_side = "left"     # "left" or "right"

arm_transport_angle = 100    # "carry" angle (e.g., slightly up)
arm_down_angle = 70          # put-down/pick-up angle
grip_open_angle = 120        # open
grip_close_angle = 60        # closed (adjust per your gripper)

servo_settle_ms = 600        # wait time after each servo command
reverse_speed = 35           # back after manipulation
reverse_time_ms = 600        # ~10 cm (tune for your bot)
rotate_dir = "left"          # "left" or "right" 180° spin
rotate_speed = 40
rotate_time_ms = 1000        # time needed for ~180° (tune for your bot)

# Helper: compute absolute base angles for sides
def base_angle_for(side):
    if side == "left":
        return max(0, min(180, base_center - base_offset_deg))
    else:
        return max(0, min(180, base_center + base_offset_deg))

# ------------------------
# HTML/CSS/JS (mission-specific page)
# ------------------------
html_content = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PicoBot – Mission Control</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<h1>PicoBot – Mission Control</h1>

<div class="status-panel">
    <div class="section-title">Robot & Mission Status</div>
    <div class="sensor-container">
        <div class="sensor-box" id="left">L</div>
        <div class="sensor-box" id="lmid">LM</div>
        <div class="sensor-box" id="center">C</div>
        <div class="sensor-box" id="rmid">RM</div>
        <div class="sensor-box" id="right">R</div>
    </div>
    <div class="status-container">
        <div id="action">Action: -</div>
        <div id="status">Status: -</div>
        <div id="mission">Mission: -</div>
        <div id="mode">Mode: -</div>
        <div id="stage">Stage: -</div>
    </div>
</div>

<div class="control-panel">
    <div class="section-title">Mission Control</div>
    <div>
        <button class="start-btn" id="startBtn">START</button>
        <button class="stop-btn" id="stopBtn">STOP</button>
    </div>

    <div class="section-title">Line Follower Presets</div>
    <div class="param-group">
        <div class="param"><div class="label">Speed</div><input type="number" id="speed" value="30" min="0" max="100"></div>
        <div class="param"><div class="label">Slight</div><input type="number" id="slight" value="0.9" step="0.05" min="0" max="1"></div>
        <div class="param"><div class="label">Mild</div><input type="number" id="mild" value="0.75" step="0.05" min="0" max="1"></div>
        <div class="param"><div class="label">Hard</div><input type="number" id="hard" value="0.6" step="0.05" min="0" max="1"></div>
        <div class="param"><div class="label">Grace (ms)</div><input type="number" id="grace" value="800" min="0" max="5000"></div>
        <div class="param"><div class="label">Search</div><input type="number" id="search" value="0.4" step="0.05" min="0" max="1"></div>
    </div>

    <div class="section-title">Mission Presets</div>
    <div class="param-group">
        <div class="param"><div class="label">Base Center</div><input type="number" id="base_center" value="90" min="0" max="180"></div>
        <div class="param"><div class="label">Base Offset</div><input type="number" id="base_offset" value="45" min="0" max="90"></div>
        <div class="param"><div class="label">First Side</div>
            <select id="first_side">
                <option value="left">left</option>
                <option value="right">right</option>
            </select>
        </div>
        <div class="param"><div class="label">Arm Transport</div><input type="number" id="arm_transport" value="100" min="0" max="180"></div>
        <div class="param"><div class="label">Arm Down</div><input type="number" id="arm_down" value="70" min="0" max="180"></div>
        <div class="param"><div class="label">Grip Open</div><input type="number" id="grip_open" value="120" min="0" max="180"></div>
        <div class="param"><div class="label">Grip Close</div><input type="number" id="grip_close" value="60" min="0" max="180"></div>
        <div class="param"><div class="label">Servo Settle (ms)</div><input type="number" id="servo_settle" value="600" min="0" max="3000"></div>
        <div class="param"><div class="label">Reverse Speed</div><input type="number" id="reverse_speed" value="35" min="0" max="100"></div>
        <div class="param"><div class="label">Reverse Time (ms)</div><input type="number" id="reverse_time" value="600" min="0" max="5000"></div>
        <div class="param"><div class="label">Rotate Dir</div>
            <select id="rotate_dir">
                <option value="left">left</option>
                <option value="right">right</option>
            </select>
        </div>
        <div class="param"><div class="label">Rotate Speed</div><input type="number" id="rotate_speed" value="40" min="0" max="100"></div>
        <div class="param"><div class="label">Rotate Time (ms)</div><input type="number" id="rotate_time" value="1000" min="0" max="5000"></div>
    </div>

    <button class="update-btn" id="updateBtn">Update Parameters</button>
</div>

<script src="/script.js"></script>
</body>
</html>"""

css_content = """body { 
    font-family: Arial, sans-serif; 
    text-align: center; 
    margin: 0;
    padding: 10px;
    background-color: #f0f0f0;
}
.status-panel, .control-panel {
    background-color: white;
    padding: 15px;
    border-radius: 10px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    margin-bottom: 15px;
}
.param-group {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 10px;
    margin: 10px 0;
}
.param {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 130px;
}
button { 
    font-size: 1.2em; 
    padding: 10px 20px; 
    margin: 10px;
    min-width: 120px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
}
.start-btn { background-color: #4CAF50; color: white; }
.stop-btn { background-color: #f44336; color: white; }
.update-btn { background-color: #2196F3; color: white; }
input[type=number], select { 
    font-size: 1.0em; 
    width: 100px; 
    text-align: center;
    padding: 5px;
    border: 1px solid #ccc;
    border-radius: 4px;
}
.sensor-container {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    margin: 15px 0;
}
.sensor-box { 
    width: 50px; 
    height: 50px; 
    line-height: 50px; 
    margin: 5px; 
    border: 2px solid #000; 
    font-weight: bold; 
    font-size: 1.2em;
    border-radius: 8px;
}
.status-container {
    margin: 15px 0;
    font-size: 1.1em;
}
#action, #status, #mission, #mode, #stage {
    margin: 6px 0;
    font-weight: bold;
    padding: 6px;
    border-radius: 5px;
    background-color: #f8f8f8;
}"""

js_content = """function loadParams() {
    fetch("/sensors")
    .then(r => r.json())
    .then(d => {
        // Line params
        document.getElementById("speed").value = d.params.speed || 30;
        document.getElementById("slight").value = d.params.slight || 0.9;
        document.getElementById("mild").value = d.params.mild || 0.75;
        document.getElementById("hard").value = d.params.hard || 0.6;
        document.getElementById("grace").value = d.params.grace || 800;
        document.getElementById("search").value = d.params.search || 0.4;

        // Mission params
        document.getElementById("base_center").value = d.params.base_center || 90;
        document.getElementById("base_offset").value = d.params.base_offset || 45;
        document.getElementById("first_side").value = d.params.first_side || "left";
        document.getElementById("arm_transport").value = d.params.arm_transport || 100;
        document.getElementById("arm_down").value = d.params.arm_down || 70;
        document.getElementById("grip_open").value = d.params.grip_open || 120;
        document.getElementById("grip_close").value = d.params.grip_close || 60;
        document.getElementById("servo_settle").value = d.params.servo_settle || 600;
        document.getElementById("reverse_speed").value = d.params.reverse_speed || 35;
        document.getElementById("reverse_time").value = d.params.reverse_time || 600;
        document.getElementById("rotate_dir").value = d.params.rotate_dir || "left";
        document.getElementById("rotate_speed").value = d.params.rotate_speed || 40;
        document.getElementById("rotate_time").value = d.params.rotate_time || 1000;
    })
    .catch(err => console.log("Error loading params:", err));
}

function startMission() {
    const q = collectParams();
    fetch("/?action=start&" + q);
}

function stopMission() {
    fetch("/?action=stop");
}

function updateParams() {
    const q = collectParams();
    fetch("/?action=update&" + q);
}

function collectParams() {
    let p = new URLSearchParams();
    // line
    p.set("speed", document.getElementById("speed").value);
    p.set("slight", document.getElementById("slight").value);
    p.set("mild", document.getElementById("mild").value);
    p.set("hard", document.getElementById("hard").value);
    p.set("grace", document.getElementById("grace").value);
    p.set("search", document.getElementById("search").value);
    // mission
    p.set("base_center", document.getElementById("base_center").value);
    p.set("base_offset", document.getElementById("base_offset").value);
    p.set("first_side", document.getElementById("first_side").value);
    p.set("arm_transport", document.getElementById("arm_transport").value);
    p.set("arm_down", document.getElementById("arm_down").value);
    p.set("grip_open", document.getElementById("grip_open").value);
    p.set("grip_close", document.getElementById("grip_close").value);
    p.set("servo_settle", document.getElementById("servo_settle").value);
    p.set("reverse_speed", document.getElementById("reverse_speed").value);
    p.set("reverse_time", document.getElementById("reverse_time").value);
    p.set("rotate_dir", document.getElementById("rotate_dir").value);
    p.set("rotate_speed", document.getElementById("rotate_speed").value);
    p.set("rotate_time", document.getElementById("rotate_time").value);
    return p.toString();
}

function updateSensors() {
    fetch("/sensors")
    .then(response => response.json())
    .then(data => {
        // Sensors
        let vals = data.sensors;
        document.getElementById("left").style.backgroundColor = vals[4]==1?"green":"white";
        document.getElementById("lmid").style.backgroundColor = vals[3]==1?"green":"white";
        document.getElementById("center").style.backgroundColor = vals[2]==1?"green":"white";
        document.getElementById("rmid").style.backgroundColor = vals[1]==1?"green":"white";
        document.getElementById("right").style.backgroundColor = vals[0]==1?"green":"white";
        // Status text
        document.getElementById("action").innerText = "Action: " + data.action;
        document.getElementById("status").innerText = "Status: " + data.status;
        document.getElementById("mission").innerText = "Mission: " + data.mission;
        document.getElementById("mode").innerText = "Mode: " + data.mode;
        document.getElementById("stage").innerText = "Stage: " + data.stage;
    })
    .catch(err => console.log("Sensor update error:", err));
}

document.getElementById("startBtn").addEventListener("click", startMission);
document.getElementById("stopBtn").addEventListener("click", stopMission);
document.getElementById("updateBtn").addEventListener("click", updateParams);

window.addEventListener("load", function() {
    loadParams();
    setInterval(updateSensors, 200);
});"""

# ------------------------
# Decide action (unchanged logic)
# ------------------------
def decide_action(sensor_values):
    if all(v == 1 for v in sensor_values):
        return "ON JUNCTION"
    if all(v == 0 for v in sensor_values):
        return "LINE LOST"
    
    positions = [2, 1, 0, -1, -2]
    weighted_sum = 0
    active_sensors = 0
    
    for i in range(5):
        if sensor_values[i] == 1:
            weighted_sum += positions[i]
            active_sensors += 1
    
    if active_sensors > 0:
        weighted_sum = weighted_sum / active_sensors
    
    if weighted_sum > 1.2:
        return "HARD RIGHT"
    elif weighted_sum > 0.6:
        return "MILD RIGHT"
    elif weighted_sum > 0.2:
        return "SLIGHT RIGHT"
    elif weighted_sum < -1.2:
        return "HARD LEFT"
    elif weighted_sum < -0.6:
        return "MILD LEFT"
    elif weighted_sum < -0.2:
        return "SLIGHT LEFT"
    elif weighted_sum == 0 and any(v == 1 for v in sensor_values):
        return "FORWARD"
    else:
        return "SEARCHING"

# ------------------------
# Map action to motor speeds (unchanged; aggressive line loss)
# ------------------------
def set_motor_action(action):
    global last_direction, search_intensity
    
    if action == "FORWARD":
        motor_driver.TurnMotor('LeftFront', 'forward', base_speed)
        motor_driver.TurnMotor('LeftBack', 'forward', base_speed)
        motor_driver.TurnMotor('RightFront', 'forward', base_speed)
        motor_driver.TurnMotor('RightBack', 'forward', base_speed)
        search_intensity = 1.0
        
    elif action == "SLIGHT RIGHT":
        motor_driver.TurnMotor('LeftFront', 'forward', base_speed)
        motor_driver.TurnMotor('LeftBack', 'forward', base_speed)
        motor_driver.TurnMotor('RightFront', 'forward', int(base_speed * slight_ratio))
        motor_driver.TurnMotor('RightBack', 'forward', int(base_speed * slight_ratio))
        search_intensity = 1.0
        
    elif action == "MILD RIGHT":
        motor_driver.TurnMotor('LeftFront', 'forward', base_speed)
        motor_driver.TurnMotor('LeftBack', 'forward', base_speed)
        motor_driver.TurnMotor('RightFront', 'forward', int(base_speed * mild_ratio))
        motor_driver.TurnMotor('RightBack', 'forward', int(base_speed * mild_ratio))
        search_intensity = 1.0
        
    elif action == "HARD RIGHT":
        motor_driver.TurnMotor('LeftFront', 'forward', base_speed)
        motor_driver.TurnMotor('LeftBack', 'forward', base_speed)
        motor_driver.TurnMotor('RightFront', 'forward', int(base_speed * hard_ratio))
        motor_driver.TurnMotor('RightBack', 'forward', int(base_speed * hard_ratio))
        search_intensity = 1.0
        
    elif action == "SLIGHT LEFT":
        motor_driver.TurnMotor('LeftFront', 'forward', int(base_speed * slight_ratio))
        motor_driver.TurnMotor('LeftBack', 'forward', int(base_speed * slight_ratio))
        motor_driver.TurnMotor('RightFront', 'forward', base_speed)
        motor_driver.TurnMotor('RightBack', 'forward', base_speed)
        search_intensity = 1.0
        
    elif action == "MILD LEFT":
        motor_driver.TurnMotor('LeftFront', 'forward', int(base_speed * mild_ratio))
        motor_driver.TurnMotor('LeftBack', 'forward', int(base_speed * mild_ratio))
        motor_driver.TurnMotor('RightFront', 'forward', base_speed)
        motor_driver.TurnMotor('RightBack', 'forward', base_speed)
        search_intensity = 1.0
        
    elif action == "HARD LEFT":
        motor_driver.TurnMotor('LeftFront', 'forward', int(base_speed * hard_ratio))
        motor_driver.TurnMotor('LeftBack', 'forward', int(base_speed * hard_ratio))
        motor_driver.TurnMotor('RightFront', 'forward', base_speed)
        motor_driver.TurnMotor('RightBack', 'forward', base_speed)
        search_intensity = 1.0
        
    elif action == "ON JUNCTION":
        motor_driver.StopAllMotors()
        search_intensity = 1.0
        
    elif action == "LINE LOST":
        global line_lost_time, line_lost
        # Increase search intensity each time we lose the line
        search_intensity *= 1.5
        if ticks_diff(ticks_ms(), line_lost_time) < grace_period:
            if "RIGHT" in last_direction:
                turn_speed = int(base_speed * search_ratio * search_intensity)
                motor_driver.TurnMotor('LeftFront', 'forward', turn_speed)
                motor_driver.TurnMotor('LeftBack', 'forward', turn_speed)
                motor_driver.TurnMotor('RightFront', 'backward', turn_speed)
                motor_driver.TurnMotor('RightBack', 'backward', turn_speed)
            elif "LEFT" in last_direction:
                turn_speed = int(base_speed * search_ratio * search_intensity)
                motor_driver.TurnMotor('LeftFront', 'backward', turn_speed)
                motor_driver.TurnMotor('LeftBack', 'backward', turn_speed)
                motor_driver.TurnMotor('RightFront', 'forward', turn_speed)
                motor_driver.TurnMotor('RightBack', 'forward', turn_speed)
            else:
                set_motor_action(last_direction)
        else:
            motor_driver.StopAllMotors()
            search_intensity = 1.0
            
    elif action == "SEARCHING":
        if ticks_diff(ticks_ms(), line_lost_time) < grace_period:
            if "RIGHT" in last_direction:
                turn_speed = int(base_speed * search_ratio * search_intensity)
                motor_driver.TurnMotor('LeftFront', 'forward', turn_speed)
                motor_driver.TurnMotor('LeftBack', 'forward', turn_speed)
                motor_driver.TurnMotor('RightFront', 'backward', turn_speed)
                motor_driver.TurnMotor('RightBack', 'backward', turn_speed)
            elif "LEFT" in last_direction:
                turn_speed = int(base_speed * search_ratio * search_intensity)
                motor_driver.TurnMotor('LeftFront', 'backward', turn_speed)
                motor_driver.TurnMotor('LeftBack', 'backward', turn_speed)
                motor_driver.TurnMotor('RightFront', 'forward', turn_speed)
                motor_driver.TurnMotor('RightBack', 'forward', turn_speed)
            else:
                set_motor_action(last_direction)
        else:
            motor_driver.StopAllMotors()
            search_intensity = 1.0
    
    if action not in ["LINE LOST", "SEARCHING"]:
        last_direction = action

# ------------------------
# Timers
# ------------------------
line_follow_timer = Timer()
mission_timer = Timer()

def line_follow_callback(timer):
    # Run only when robot_running is True; mission_timer handles other motions
    global robot_running, line_lost, line_lost_time, mission_mode, mission_stage, mission_status_text
    
    if not robot_running:
        return
        
    vals = [s.value() for s in sensors]
    act = decide_action(vals)
    
    if act == "ON JUNCTION":
        motor_driver.StopAllMotors()
        robot_running = False
        # Transition based on mission mode
        if mission_mode == "OUTBOUND":
            mission_mode_to_arm_sequence()
        elif mission_mode == "RETURNING":
            mission_mode = "DONE"
            mission_status_text = "Mission accomplished (back at start)"
        return
        
    elif act == "LINE LOST":
        if not line_lost:
            line_lost = True
            line_lost_time = ticks_ms()
        elif ticks_diff(ticks_ms(), line_lost_time) >= grace_period:
            motor_driver.StopAllMotors()
        else:
            set_motor_action(act)
    else:
        if line_lost:
            line_lost = False
        set_motor_action(act)

def mission_mode_to_arm_sequence():
    global mission_mode, mission_stage, mission_stage_started, mission_status_text
    mission_mode = "ARM_SEQ"
    mission_stage = 0
    mission_stage_started = ticks_ms()
    mission_status_text = "Manipulating object"

def mission_callback(timer):
    # Non-blocking state machine for arm + post actions
    global mission_mode, mission_stage, mission_stage_started, mission_status_text
    if mission_mode != "ARM_SEQ":
        return
    
    now = ticks_ms()
    # Stages:
    # 0: Base -> first side
    # 1: Close gripper (pick)
    # 2: Arm -> transport (lift)
    # 3: Base -> other side
    # 4: Arm -> down
    # 5: Open gripper (place)
    # 6: Arm -> transport
    # 7: Reverse (time-based)
    # 8: Rotate 180 (time-based)
    # 9: Transition to RETURNING & resume line following
    
    if mission_stage == 0:
        # Base to first side
        target = base_angle_for(base_first_side)
        arm.control_servo(0, target)
        mission_stage_started = now
        mission_stage = 1
    
    elif mission_stage == 1:
        if ticks_diff(now, mission_stage_started) >= servo_settle_ms:
            arm.control_servo(2, grip_close_angle)  # close gripper
            mission_stage_started = now
            mission_stage = 2
    
    elif mission_stage == 2:
        if ticks_diff(now, mission_stage_started) >= servo_settle_ms:
            arm.control_servo(1, arm_transport_angle)  # lift/carry
            mission_stage_started = now
            mission_stage = 3
    
    elif mission_stage == 3:
        if ticks_diff(now, mission_stage_started) >= servo_settle_ms:
            other = "right" if base_first_side == "left" else "left"
            arm.control_servo(0, base_angle_for(other))
            mission_stage_started = now
            mission_stage = 4
    
    elif mission_stage == 4:
        if ticks_diff(now, mission_stage_started) >= servo_settle_ms:
            arm.control_servo(1, arm_down_angle)  # lower
            mission_stage_started = now
            mission_stage = 5
    
    elif mission_stage == 5:
        if ticks_diff(now, mission_stage_started) >= servo_settle_ms:
            arm.control_servo(2, grip_open_angle)  # release
            mission_stage_started = now
            mission_stage = 6
    
    elif mission_stage == 6:
        if ticks_diff(now, mission_stage_started) >= servo_settle_ms:
            arm.control_servo(1, arm_transport_angle)  # raise to transport
            mission_stage_started = now
            # Prepare to reverse
            # Start reverse immediately
            motor_driver.TurnMotor('LeftFront', 'backward', reverse_speed)
            motor_driver.TurnMotor('LeftBack', 'backward', reverse_speed)
            motor_driver.TurnMotor('RightFront', 'backward', reverse_speed)
            motor_driver.TurnMotor('RightBack', 'backward', reverse_speed)
            mission_stage = 7
    
    elif mission_stage == 7:
        if ticks_diff(now, mission_stage_started) >= reverse_time_ms:
            motor_driver.StopAllMotors()
            # Begin rotate
            if rotate_dir == "left":
                motor_driver.TurnMotor('LeftFront', 'backward', rotate_speed)
                motor_driver.TurnMotor('LeftBack', 'backward', rotate_speed)
                motor_driver.TurnMotor('RightFront', 'forward', rotate_speed)
                motor_driver.TurnMotor('RightBack', 'forward', rotate_speed)
            else:
                motor_driver.TurnMotor('LeftFront', 'forward', rotate_speed)
                motor_driver.TurnMotor('LeftBack', 'forward', rotate_speed)
                motor_driver.TurnMotor('RightFront', 'backward', rotate_speed)
                motor_driver.TurnMotor('RightBack', 'backward', rotate_speed)
            mission_stage_started = now
            mission_stage = 8
    
    elif mission_stage == 8:
        if ticks_diff(now, mission_stage_started) >= rotate_time_ms:
            motor_driver.StopAllMotors()
            # Resume line following in reverse direction
            mission_stage = 9
    
    elif mission_stage == 9:
        # Transition to RETURNING
        mission_mode = "RETURNING"
        mission_status_text = "Returning to start"
        # Resume follower
        resume_line_follow()
        # End ARM_SEQ
        # (line_follow_callback will stop at the next ON JUNCTION)
    
    # else: do nothing

def resume_line_follow():
    global robot_running, line_lost, search_intensity, last_direction
    robot_running = True
    line_lost = False
    search_intensity = 1.0
    last_direction = "FORWARD"

# ------------------------
# Start timers
# ------------------------
line_follow_timer.init(period=50, mode=Timer.PERIODIC, callback=line_follow_callback)
mission_timer.init(period=50, mode=Timer.PERIODIC, callback=mission_callback)

# ------------------------
# Web server (same style as your line follower)
# ------------------------
def open_socket(ip):
    addr = socket.getaddrinfo(ip, 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)
    return s

ap_ip = ap.ifconfig()[0]
sock = open_socket(ap_ip)
print("Server running on:", ap_ip)

while True:
    try:
        client, addr = sock.accept()
        request = client.recv(2048)
        request_str = request.decode()
        # print("Request:", request_str)

        # Serve sensors JSON
        if "GET /sensors" in request_str:
            vals = [s.value() for s in sensors]
            act = decide_action(vals) if robot_running else "-"
            
            if mission_mode == "IDLE":
                mstatus = "Stopped"
            elif mission_mode == "OUTBOUND":
                mstatus = "Going to marker"
            elif mission_mode == "ARM_SEQ":
                mstatus = "Manipulating"
            elif mission_mode == "RETURNING":
                mstatus = "Returning"
            elif mission_mode == "DONE":
                mstatus = "Done"
            else:
                mstatus = mission_status_text
            
            data = {
                'sensors': vals,
                'action': act,
                'status': "Running" if robot_running else "Stopped",
                'mission': mission_status_text,
                'mode': mission_mode,
                'stage': mission_stage,
                'params': {
                    # line follower
                    'speed': base_speed,
                    'slight': slight_ratio,
                    'mild': mild_ratio,
                    'hard': hard_ratio,
                    'grace': grace_period,
                    'search': search_ratio,
                    # mission
                    'base_center': base_center,
                    'base_offset': base_offset_deg,
                    'first_side': base_first_side,
                    'arm_transport': arm_transport_angle,
                    'arm_down': arm_down_angle,
                    'grip_open': grip_open_angle,
                    'grip_close': grip_close_angle,
                    'servo_settle': servo_settle_ms,
                    'reverse_speed': reverse_speed,
                    'reverse_time': reverse_time_ms,
                    'rotate_dir': rotate_dir,
                    'rotate_speed': rotate_speed,
                    'rotate_time': rotate_time_ms
                }
            }
            response = "HTTP/1.1 200 OK\r\n"
            response += "Content-Type: application/json\r\n"
            response += "Access-Control-Allow-Origin: *\r\n"
            response += "Connection: close\r\n\r\n"
            response += json.dumps(data)
            client.send(response.encode())

        # Handle start
        elif "GET /?action=start" in request_str:
            # Update params before start (same style as your line follower)
            if "speed=" in request_str:
                base_speed = int(request_str.split("speed=")[1].split("&")[0])
            if "slight=" in request_str:
                slight_ratio = float(request_str.split("slight=")[1].split("&")[0])
            if "mild=" in request_str:
                mild_ratio = float(request_str.split("mild=")[1].split("&")[0])
            if "hard=" in request_str:
                hard_ratio = float(request_str.split("hard=")[1].split("&")[0])
            if "grace=" in request_str:
                grace_period = int(request_str.split("grace=")[1].split("&")[0])
            if "search=" in request_str:
                search_ratio = float(request_str.split("search=")[1].split("&")[0])

            # Mission params
            if "base_center=" in request_str:
                base_center = int(request_str.split("base_center=")[1].split("&")[0])
            if "base_offset=" in request_str:
                base_offset_deg = int(request_str.split("base_offset=")[1].split("&")[0])
            if "first_side=" in request_str:
                base_first_side = request_str.split("first_side=")[1].split("&")[0]
                if base_first_side not in ("left", "right"):
                    base_first_side = "left"
            if "arm_transport=" in request_str:
                arm_transport_angle = int(request_str.split("arm_transport=")[1].split("&")[0])
            if "arm_down=" in request_str:
                arm_down_angle = int(request_str.split("arm_down=")[1].split("&")[0])
            if "grip_open=" in request_str:
                grip_open_angle = int(request_str.split("grip_open=")[1].split("&")[0])
            if "grip_close=" in request_str:
                grip_close_angle = int(request_str.split("grip_close=")[1].split("&")[0])
            if "servo_settle=" in request_str:
                servo_settle_ms = int(request_str.split("servo_settle=")[1].split("&")[0])
            if "reverse_speed=" in request_str:
                reverse_speed = int(request_str.split("reverse_speed=")[1].split("&")[0])
            if "reverse_time=" in request_str:
                reverse_time_ms = int(request_str.split("reverse_time=")[1].split("&")[0])
            if "rotate_dir=" in request_str:
                rotate_dir = request_str.split("rotate_dir=")[1].split("&")[0]
                if rotate_dir not in ("left", "right"):
                    rotate_dir = "left"
            if "rotate_speed=" in request_str:
                rotate_speed = int(request_str.split("rotate_speed=")[1].split("&")[0])
            if "rotate_time=" in request_str:
                rotate_time_ms = int(request_str.split("rotate_time=")[1].split("&")[0])

            # Init arm to transport pose before moving
            arm.control_servo(0, base_center)
            arm.control_servo(1, arm_transport_angle)
            arm.control_servo(2, grip_open_angle)

            # Start outbound line-following
            mission_mode = "OUTBOUND"
            mission_status_text = "Going to end marker"
            resume_line_follow()

            response = "HTTP/1.1 200 OK\r\n"
            response += "Content-Type: text/plain\r\n"
            response += "Access-Control-Allow-Origin: *\r\n"
            response += "Connection: close\r\n\r\n"
            response += "OK"
            client.send(response.encode())

        # Handle stop
        elif "GET /?action=stop" in request_str:
            robot_running = False
            mission_mode = "IDLE"
            mission_status_text = "Stopped by user"
            motor_driver.StopAllMotors()
            response = "HTTP/1.1 200 OK\r\n"
            response += "Content-Type: text/plain\r\n"
            response += "Access-Control-Allow-Origin: *\r\n"
            response += "Connection: close\r\n\r\n"
            response += "OK"
            client.send(response.encode())

        # Handle update (no start)
        elif "GET /?action=update" in request_str:
            # Update line params
            if "speed=" in request_str:
                base_speed = int(request_str.split("speed=")[1].split("&")[0])
            if "slight=" in request_str:
                slight_ratio = float(request_str.split("slight=")[1].split("&")[0])
            if "mild=" in request_str:
                mild_ratio = float(request_str.split("mild=")[1].split("&")[0])
            if "hard=" in request_str:
                hard_ratio = float(request_str.split("hard=")[1].split("&")[0])
            if "grace=" in request_str:
                grace_period = int(request_str.split("grace=")[1].split("&")[0])
            if "search=" in request_str:
                search_ratio = float(request_str.split("search=")[1].split("&")[0])

            # Update mission params
            if "base_center=" in request_str:
                base_center = int(request_str.split("base_center=")[1].split("&")[0])
            if "base_offset=" in request_str:
                base_offset_deg = int(request_str.split("base_offset=")[1].split("&")[0])
            if "first_side=" in request_str:
                v = request_str.split("first_side=")[1].split("&")[0]
                if v in ("left", "right"):
                    base_first_side = v
            if "arm_transport=" in request_str:
                arm_transport_angle = int(request_str.split("arm_transport=")[1].split("&")[0])
            if "arm_down=" in request_str:
                arm_down_angle = int(request_str.split("arm_down=")[1].split("&")[0])
            if "grip_open=" in request_str:
                grip_open_angle = int(request_str.split("grip_open=")[1].split("&")[0])
            if "grip_close=" in request_str:
                grip_close_angle = int(request_str.split("grip_close=")[1].split("&")[0])
            if "servo_settle=" in request_str:
                servo_settle_ms = int(request_str.split("servo_settle=")[1].split("&")[0])
            if "reverse_speed=" in request_str:
                reverse_speed = int(request_str.split("reverse_speed=")[1].split("&")[0])
            if "reverse_time=" in request_str:
                reverse_time_ms = int(request_str.split("reverse_time=")[1].split("&")[0])
            if "rotate_dir=" in request_str:
                v = request_str.split("rotate_dir=")[1].split("&")[0]
                if v in ("left", "right"):
                    rotate_dir = v
            if "rotate_speed=" in request_str:
                rotate_speed = int(request_str.split("rotate_speed=")[1].split("&")[0])
            if "rotate_time=" in request_str:
                rotate_time_ms = int(request_str.split("rotate_time=")[1].split("&")[0])

            response = "HTTP/1.1 200 OK\r\n"
            response += "Content-Type: text/plain\r\n"
            response += "Access-Control-Allow-Origin: *\r\n"
            response += "Connection: close\r\n\r\n"
            response += "OK"
            client.send(response.encode())

        # Serve CSS
        elif "GET /style.css" in request_str:
            response = "HTTP/1.1 200 OK\r\n"
            response += "Content-Type: text/css\r\n"
            response += "Access-Control-Allow-Origin: *\r\n"
            response += "Connection: close\r\n\r\n"
            response += css_content
            client.send(response.encode())

        # Serve JS
        elif "GET /script.js" in request_str:
            response = "HTTP/1.1 200 OK\r\n"
            response += "Content-Type: application/javascript\r\n"
            response += "Access-Control-Allow-Origin: *\r\n"
            response += "Connection: close\r\n\r\n"
            response += js_content
            client.send(response.encode())

        else:
            # Serve HTML
            response = "HTTP/1.1 200 OK\r\n"
            response += "Content-Type: text/html\r\n"
            response += "Access-Control-Allow-Origin: *\r\n"
            response += "Connection: close\r\n\r\n"
            response += html_content
            client.send(response.encode())

        client.close()

    except Exception as e:
        print("Error:", e)
        try:
            client.close()
        except:
            pass
