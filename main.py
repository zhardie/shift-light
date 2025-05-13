from machine import Pin, I2C
import ssd1306
import usocket as socket
import time
import json
import struct
from neopixel import NeoPixel
import uasyncio as asyncio

import simulation
import wifi

from fonts import digits

i2c = I2C(0, scl=Pin(1), sda=Pin(2))
display = ssd1306.SSD1306_I2C(128, 64, i2c)

num_pixels = 24
flash_max_cycles = 50

# Load config
conf = {}
with open('config.json', 'r') as f:
    conf = json.load(f)

np = NeoPixel(Pin(3), num_pixels)

connected = wifi.connect_wifi(ssid=conf['wifi_ssid'], password=conf['wifi_password'], max_retries=10, display=display)
display.fill(0)
display.show()

# Test data
test_data = simulation.generate_simple_rpm_simulation()


gear_map = {
    0: 'N',
    1: '1',
    2: '2',
    3: '3',
    4: '4',
    5: '5',
    6: '6',
    7: '7',
    8: '8',
    9: '9',
    -1: 'R'
}

def set_color_all(r, g, b, brightness=conf['led_ring_brightness']):
    """
    Set all pixels to the same color
    """
    # Apply brightness
    r = int(r * brightness)
    g = int(g * brightness)
    b = int(b * brightness)
    
    for i in range(num_pixels):
        np[i] = (r, g, b)
    np.write()

def display_gear(bitmap):
    """
    Displays a bitmap digit scaled to fill the entire 128x64 display.
    
    Args:
        bitmap: A 2D list representing the digit (should be 16x8)
    """
    # Clear the display
    display.fill(0)
    
    # Get dimensions of the bitmap
    height = len(bitmap)
    width = len(bitmap[0])
    
    # Calculate scaling factor (should be 8 for 16x8 bitmap on 128x64 display)
    scale_x = display.width // width
    scale_y = display.height // height
    
    # Draw each pixel of the bitmap, scaled up
    for y in range(height):
        for x in range(width):
            if bitmap[y][x] == 1:
                # Draw a square of scale_x x scale_y pixels
                for dy in range(scale_y):
                    for dx in range(scale_x):
                        display.pixel(x * scale_x + dx, y * scale_y + dy, 1)
    
    # Update the display
    display.show()

def decode_dirt_rally(data):
    if len(data) >= 152:  # Ensure enough data for gear and rpm (148 + 4)
        gear_float = struct.unpack_from('f', data, offset=132)[0]
        rpm_float = struct.unpack_from('f', data, offset=148)[0]
        gear = int(gear_float)
        rpm = int(rpm_float * 10)
        return gear, rpm
    else:
        return None, None

async def sim_task(gauge):
    """Collect data from simulator and update gauge"""
    port = 20777
    sock = None
    
    # Idle state tracking
    last_data_time = time.time()
    idle_timeout = 5  # Seconds before showing idle animation
    is_idle_mode = False
    
    try:
        # Create socket once outside the loop
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((conf['sim_ip'], port))
        sock.setblocking(False)
        print(f"Listening for telemetry on port {port}")
        
        last_gear = None
        
        while True:
            try:
                data_received = False
                
                # Try to receive data
                try:
                    data = sock.recv(512)
                    # Process the received data
                    #telemetry = json.loads(data)
                    
                    dirt_data = struct.unpack('64f', data[0:256])
                    
                    gear = int(dirt_data[33])
                    rpm = int(dirt_data[37])*10
                    
                    #rpm = telemetry.get('rpm', 0)
                    #gear = telemetry.get('gear', 1)
                    if rpm > gauge.max_rpm:
                        gauge.max_rpm = rpm
                    
                    # Data received, update last data time
                    last_data_time = time.time()
                    data_received = True
                    
                    # We were in idle mode but just received data
                    if is_idle_mode:
                        is_idle_mode = False
                        print("Telemetry received - exiting idle mode")
                    
                    # Calculate normalized rpm (0.0 to 1.0)
                    rpm_normalized = rpm / gauge.max_rpm
                    
                    # Store the RPM level but only update display if not at redline
                    gauge.level = rpm_normalized
                    if rpm_normalized < conf['led_redline_flash_above']:
                        gauge.set_gauge_level(rpm_normalized)
                    
                    # Update gear display only when gear changes
                    gear_str = str(gear) if isinstance(gear, int) else gear
                    if gear_str in digits.digits and gear != last_gear:
                        display_gear(digits.digits[gear_str])
                        last_gear = gear
                        
                except OSError:
                    # No data available yet
                    pass
                
                # Check if we should switch to idle mode
                current_time = time.time()
                if not data_received and not is_idle_mode and (current_time - last_data_time) > idle_timeout:
                    # Switch to idle mode
                    is_idle_mode = True
                    gauge.max_rpm = 3000
                    print("No telemetry received for 5 seconds - entering idle mode")
                    display.fill(0)
                    display.show()
                    
                    # Create and run the idle animation asynchronously
                    if conf['allow_idle_animations']:
                        asyncio.create_task(run_idle_animation(gauge))
                    else:
                        set_color_all(0, 0, 0)
                
                # Short delay before next iteration
                await asyncio.sleep_ms(10)
                
            except Exception as e:
                print(f"Error processing data: {e}")
                await asyncio.sleep(1)
    except Exception as e:
        print(f"Socket error: {e}")
    finally:
        if sock:
            sock.close()

async def run_idle_animation(gauge):
    """Run the idle animation until telemetry data is received again"""
    # Set a flag to indicate we're in idle mode
    gauge.in_idle_mode = True
    
    # Use a cyan color for the idle animation
    r, g, b = 0, 150, 150
    
    try:
        # Run the idle animation until we're no longer in idle mode
        while getattr(gauge, 'in_idle_mode', True):
            # Breathe in
            for i in range(0, 101, 5):
                if not getattr(gauge, 'in_idle_mode', True):
                    break
                    
                intensity = i / 100.0
                set_color_all(r * intensity, g * intensity, b * intensity, conf['led_ring_brightness'] * 0.5)
                await asyncio.sleep_ms(50)
                
            # Breathe out
            for i in range(100, -1, -5):
                if not getattr(gauge, 'in_idle_mode', True):
                    break
                    
                intensity = i / 100.0
                set_color_all(r * intensity, g * intensity, b * intensity, conf['led_ring_brightness'] * 0.5)
                await asyncio.sleep_ms(50)
    finally:
        # Reset the flag when we exit the idle animation
        gauge.in_idle_mode = False

class Gauge():
    def __init__(self):
        self.max_rpm = 3000
        self.level = 0
        self.flashed = False
        self.flash_cycles = 0
        self.increasing = True
        self.in_idle_mode = False  # Add this line
        
    def set_gauge_level(self, level):
        # Exit idle mode if we're updating the gauge
        self.in_idle_mode = False
        
        self.flashed = False
        level = max(0, min(1.0, level))  # Clamp between 0 and 1
        self.level = level
        lit_pixels = int(num_pixels * level)

        r, g, b = (0, 0, 0)

        # Determine base colors based on level
        if level < conf['led_green_breakpoint']:
            r, g, b = 0, 255, 0  # Green
        elif level < conf['led_yellow_breakpoint']:
            r, g, b = 255, 255, 0  # Yellow
        else:
            r, g, b = 255, 0, 0  # Red
        
        # Apply brightness
        r = int(r * conf['led_ring_brightness'])
        g = int(g * conf['led_ring_brightness'])
        b = int(b * conf['led_ring_brightness'])
        
        # Clear all pixels
        for i in range(num_pixels):
            if i < lit_pixels:
                np[i] = (r, g, b)
            else:
                np[i] = (0, 0, 0)
        np.write()
    
    def set_flash(self):
        for i in range(num_pixels):
            np[i] = (0, 0, 0)
        np.write()

    async def check_redline(self):
        while True:
            # Skip redline checking if we're in idle mode
            if not self.in_idle_mode:
                current_level = self.level  # Store current level

                if current_level >= conf['led_redline_flash_above']:  # If at or above redline
                    # Flash pattern - alternate between off and on
                    if self.flash_cycles % 2 == 0:  # Even cycles = LED off
                        # Store current LEDs state before turning off
                        current_pixels = []
                        for i in range(num_pixels):
                            current_pixels.append(np[i])
                        
                        # Turn off all LEDs
                        for i in range(num_pixels):
                            np[i] = (0, 0, 0)
                        np.write()
                    else:  # Odd cycles = LEDs on (bright red)
                        # Set all active LEDs to bright red
                        lit_pixels = int(num_pixels * current_level)
                        r = int(255 * conf['led_ring_brightness'])
                        g = 0
                        b = 0
                        
                        for i in range(num_pixels):
                            if i < lit_pixels:
                                np[i] = (r, g, b)
                            else:
                                np[i] = (0, 0, 0)
                        np.write()
                    
                    self.flash_cycles += 1
                    if self.flash_cycles >= flash_max_cycles:
                        self.flash_cycles = 0
                        
                # If not above redline, reset flash counter but don't change LEDs
                # (sim_task will handle normal gauge display)
                else:
                    self.flash_cycles = 0
            
            # Short delay for flashing effect (adjust as needed)
            await asyncio.sleep_ms(100)  # Flash frequency = 10 Hz

    def gauge_sweep(self, times=2):
        interval_ms = 20/1000 # 100 ms
        for t in range(0, times, 1):
            for level in range(0, 101, 4):
                self.set_gauge_level(level/100.0)
                time.sleep(interval_ms)
            for level in range(101, 0, -4):
                self.set_gauge_level(level/100.0)
                time.sleep(interval_ms)

    def gear_range(self):
        for d in '123456NR':
            display_gear(digits.digits[d])
            time.sleep(50/1000)

async def main():
    gauge = Gauge()
    gauge.gauge_sweep(1)

    # Check for new Schema here and download if new one available

    sim_task_handle = asyncio.create_task(sim_task(gauge))
    redline_task = asyncio.create_task(gauge.check_redline())

    while True: # main loop
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
