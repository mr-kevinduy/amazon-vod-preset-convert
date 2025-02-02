# Requirements

- Python 3.8.x
- AWS CLI

# Pre-check & Usage

```sh
# Verify Python is Installed. Please make sure that the Python version is a variation of **3.8.x**.
python –version
pip –version

# Verify AWS CLI is Installed and configurated. If haven't installed, following url for install it. https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html
aws --version
aws configure list

# Make sure the awstc_v3.py is located on your machine, and then make awstc_v3.py executable using the following chmod command:
chmod +x awstc_v3.py

# Install python packages
pip install boto3

# Run
python awstc_v3.py -i ./input_test.json
python awstc_v3.py -i ./input_stag.json
python awstc_v3.py -i ./input_prod.json
```
