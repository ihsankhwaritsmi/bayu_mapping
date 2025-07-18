# PIX2RASP
- Abaikan folder `/archive`

- Install requirement package
```
pip install -r requirements.txt
```
- Lanjut gas jalankan
```
python pix2rasp_real.py
```

## SETUP NY DISINI

di file `pix2rasp_real.py` ada di line 171-175
```python
 # --- MAVLink Configuration ---
    # connection_string = "tcp:127.0.0.1:5762"
    connection_string = "/dev/ttyAMA0:57600"
```
- Pake `/dev/ttyAMA0` klo konek via UART.
- Pake `/dev/ttyACM0` klo konek via USB.
- Sesuaiin BAUDRATE-nya biasanya antara `57600` ato `115200`, tp kata abang GM kita pengennya baudrate custom ntr tanya aja ke bang GM.
- Buat setup UART, dsb harusnya udh dari kemaren jadi ga harus setup lagi
