# Fieldline OPM Client

## Installation

We recommend using the [Anaconda](https://www.anaconda.com/) package
library for system-independent installation.

### Optional step
If you want to manage the dependencies in a virtual environment, do
the following:

    conda create -n opm_virtual_env python=3.8
    conda activate opm_virtual_env

Once you have Python installed through Anaconda, do the following:

    pip install git+https://github.com/juangpc/fieldline-opm-client.git#egg=fieldline_client -r https://raw.githubusercontent.com/juangpc/fieldline-opm-client/main/requirements.txt

## Dependencies

- Python (>=3.8)
- appdirs==1.4.3
- ifaddr==0.1.6
- netifaces==0.10.9
- numpy==1.18.2
- protobuf==3.11.3
- six==1.14.0
- zeroconf==0.24.5
- fieldline_api (bundled)

# FieldLine API README

## Prerequisits:
- Python 3.8 needs to be installed - due to an issue in the shared memory library that was fixed
- Download api-example.zip and fieldline_api_XXX.whl

1) Download and extract api-example.zip
2) cd api-example
3) python3.8 -m venv venv
4) . venv/bin/activate
5) pip install -r requirements-api.txt
6) pip install <path to downloaded API whl file>
7) python main.py

# Release Notes
- 0.0.13 - add SENSOR_READY state
- 0.0.12 - fix wrong file include
- 0.0.11 - Add sensor status call
- 0.0.10 - Few API cleanup items
- 0.0.2 - add start_adc and stop_adc calls
- 0.0.1 - initial release
