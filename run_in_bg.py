import subprocess
from time import strftime
from datetime import date
timestamp = date.today().strftime("%A_") + strftime("%H:%M:%S")

subprocess.run("nohup python /home/daniel_nlp/Lung-Cancer-Risk-Prediction/main.py > out_" + timestamp + ".log 2>&1 &", shell=True)
