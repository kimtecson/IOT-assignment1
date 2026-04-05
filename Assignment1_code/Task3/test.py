from sense_hat import SenseHat
import time

sense = SenseHat()

while True:
    # Get raw acceleration data
    accel = sense.get_accelerometer_raw()
    x = accel['x']
    y = accel['y']
    z = accel['z']

    # Round to 1 decimal place to ignore minor vibrations
    x = round(x, 1)
    y = round(y, 1)
    z = round(z, 1)

    # Check for alignment
    if z == 1:
        print("Flat (Aligned)")
    elif z == -1:
        print("Upside Down")
    else:
        print(f"Tilted: X={x}, Y={y}, Z={z}")

    time.sleep(0.5)
