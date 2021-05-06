import os
import sys

this_dir = os.path.dirname(os.path.realpath(__file__))

sys.path.insert(0, this_dir)
sys.path.insert(1, this_dir + os.path.sep + "pycore")
