'''
picobot.py

PicoBot class: drives the four mecanum wheels and gives access to the arm.
'''
import time
from picobot_motors import MotorDriver
from picobot_arm import PicoBotArm

class PicoBot:
    def __init__(self):
        self.m = MotorDriver()
        time.sleep(1)
        print("PicoBot initialized")
        # MotorDriver.TurnMotor(motor, direction, speed):
        #   motor:     'LeftFront', 'LeftBack', 'RightFront', 'RightBack'
        #   direction: 'forward', 'backward'
        #   speed:     0-100 (%)

        # Create the arm object (the servos move to 90 degrees)
        self.arm = PicoBotArm()

    def stop_all_motors(self):
        self.m.StopAllMotors()

    def goForward(self, speed = 50):
        # Default speed is 50 (%)
        self.m.TurnMotor('LeftFront', 'forward', speed)
        self.m.TurnMotor('LeftBack','forward', speed)
        self.m.TurnMotor('RightFront', 'forward', speed)
        self.m.TurnMotor('RightBack', 'forward', speed)

    def goBackward(self, speed = 50):
        self.m.TurnMotor('LeftFront', 'backward', speed)
        self.m.TurnMotor('LeftBack','backward', speed)
        self.m.TurnMotor('RightFront', 'backward', speed)
        self.m.TurnMotor('RightBack', 'backward', speed)

    # Old misspelled name, kept so that older programs still work
    goBackwad = goBackward

    def moveRight(self, speed = 50):
        # Sideways to the right (mecanum "strafe")
        self.m.TurnMotor('LeftFront', 'forward', speed)
        self.m.TurnMotor('LeftBack','backward', speed)
        self.m.TurnMotor('RightFront', 'backward', speed)
        self.m.TurnMotor('RightBack', 'forward', speed)

    def moveLeft(self, speed = 50):
        # Sideways to the left (mecanum "strafe")
        self.m.TurnMotor('LeftFront', 'backward', speed)
        self.m.TurnMotor('LeftBack','forward', speed)
        self.m.TurnMotor('RightFront', 'forward', speed)
        self.m.TurnMotor('RightBack', 'backward', speed)

    # Old names (same movement as moveLeft / moveRight), kept so that older programs still work
    starf_left = moveLeft
    starf_right = moveRight

    def moveRightForward(self, speed = 50):
        # Diagonal: forward and to the right
        self.m.TurnMotor('LeftFront','forward', speed)
        self.m.TurnMotor('RightBack', 'forward', speed)

    def moveRightBackward(self, speed = 50):
        # Diagonal: backward and to the right
        self.m.TurnMotor('LeftBack', 'backward', speed)
        self.m.TurnMotor('RightFront', 'backward', speed)

    def moveLeftForward(self, speed = 50):
        # Diagonal: forward and to the left
        self.m.TurnMotor('LeftBack','forward', speed)
        self.m.TurnMotor('RightFront', 'forward', speed)

    def moveLeftBackward(self, speed = 50):
        # Diagonal: backward and to the left
        self.m.TurnMotor('LeftFront', 'backward', speed)
        self.m.TurnMotor('RightBack', 'backward', speed)

    def rotateRight(self, speed = 50):
        # Turn on the spot, clockwise
        self.m.TurnMotor('LeftFront', 'forward', speed)
        self.m.TurnMotor('LeftBack','forward', speed)
        self.m.TurnMotor('RightFront', 'backward', speed)
        self.m.TurnMotor('RightBack', 'backward', speed)

    def rotateLeft(self, speed = 50):
        # Turn on the spot, counter-clockwise
        self.m.TurnMotor('LeftFront', 'backward', speed)
        self.m.TurnMotor('LeftBack','backward', speed)
        self.m.TurnMotor('RightFront', 'forward', speed)
        self.m.TurnMotor('RightBack', 'forward', speed)

    def stopRobot(self, delay_ms = 10):
        # Stop all motors, then wait delay_ms milliseconds
        self.m.StopAllMotors()
        time.sleep_ms(delay_ms)

    def hardStop(self):
        # Stop all motors immediately
        self.m.StopAllMotors()
