from pca9685 import PCA9685
from machine import I2C, Pin
import time

class PicoBotArm:
    def __init__(self, sda_pin=2, scl_pin=3, i2c_id=1, init_servos=True):
        """
        Initialise PicoBotArm: the I2C bus and the PCA9685 servo driver.
        :param init_servos: if True, all servos move to 90 degrees when the object is created.
        """
        self.sda = Pin(sda_pin)
        self.scl = Pin(scl_pin)
        self.i2c_id = i2c_id
        self.i2c = I2C(id=self.i2c_id, sda=self.sda, scl=self.scl)
        self.pca = PCA9685(i2c=self.i2c)
        self.pca.freq(50)

        # Remember the current angle of each servo
        self.current_angles = {0: 0, 1: 0, 2: 0}  # start values
        if init_servos:
            # Move the servos to the start position
            self.init_servos()  # automatic initialisation when the object is created

    def control_servo(self, channel, angle):
        """
        Set the angle of the servo on one channel.
        :param channel: PCA9685 channel (0 to 15).
        :param angle: angle in degrees (0-180).
        """
        if not 0 <= angle <= 180:
            raise ValueError("Invalid angle. Use a value between 0 and 180 degrees.")

        # Convert the angle to a PWM value.
        # At 50 Hz one period is 20 ms and the PCA9685 divides it into 4096 steps.
        min_pulse = 102  # pulse for 0 degrees (102/4096 x 20 ms = about 0.5 ms)
        max_pulse = 512  # pulse for 180 degrees (512/4096 x 20 ms = about 2.5 ms)
        pulse = int(min_pulse + (angle / 180.0) * (max_pulse - min_pulse))
        self.pca.pwm(channel, 0, pulse)

    def smooth_move_servo(self, channel, target_angle, step=1, delay=0.02):
        """
        Move the servo gradually to a new angle.
        :param channel: PCA9685 channel (0 to 15).
        :param target_angle: the angle the servo should reach.
        :param step: how many degrees to move in each step.
        :param delay: pause between the steps (in seconds).
        """
        current_angle = self.current_angles[channel]
        if current_angle < target_angle:
            for angle in range(current_angle, target_angle + 1, step):
                self.control_servo(channel, angle)
                time.sleep(delay)
        elif current_angle > target_angle:
            for angle in range(current_angle, target_angle - 1, -step):
                self.control_servo(channel, angle)
                time.sleep(delay)

        # Remember the new angle
        self.current_angles[channel] = target_angle

    def reset_servos(self):
        """
        Move all servos smoothly back to 90 degrees.
        """
        angles_to_reset = {0: 90, 1: 90, 2: 90}  # start angle for each channel
        for channel, angle in angles_to_reset.items():
            self.smooth_move_servo(channel, angle)
            self.current_angles[channel] = angle  # remember the new angle

    def init_servos(self):
        """
        Set all servos to 90 degrees at once (no smooth movement).
        """
        angles_to_reset = {0: 90, 1: 90, 2: 90}  # start angle for each channel
        for channel, angle in angles_to_reset.items():
            self.control_servo(channel, angle)
            self.current_angles[channel] = angle  # remember the new angle
