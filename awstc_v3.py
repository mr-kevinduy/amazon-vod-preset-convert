import os
import argparse
import datetime
import time
import json
import os
import sys
import shutil
import boto3
from botocore.config import Config

# log_path = "/var/log/awstc/"
# if not os.path.exists(log_path):
#     os.makedirs(log_path)

# log_file = log_path + "awstc.log"

COLOR_HEADER = '\033[95m'
COLOR_ENDC = '\033[0m'
COLOR_BOLD = '\033[1m'
COLOR_UNDERLINE = '\033[4m'
COLOR_BLUE = '\033[94m'
COLOR_CYAN = '\033[96m'
COLOR_GREEN = '\033[92m'
COLOR_WARNING = '\033[93m'
COLOR_FAIL = '\033[91m'

def log_info(msg = ''):
    print(f"{COLOR_BLUE}{msg}{COLOR_ENDC}")

def log_error(msg = ''):
    print(f"{COLOR_FAIL}{msg}{COLOR_ENDC}")

def log_warning(msg = ''):
    print(f"{COLOR_WARNING}{msg}{COLOR_ENDC}")

def log_success(msg = ''):
    print(f"{COLOR_GREEN}{msg}{COLOR_ENDC}")

parser = argparse.ArgumentParser(prog='awstc', description='ETS to AWS Elemental MediaConvert preset converter', add_help=True)
parser.add_argument('-i', '--input', dest='input', type=str, default=None, help='Input config file')
parser.add_argument('-o', '--output', action='store', dest='output', help='Output preset to files. default: output')
parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + '0.0.1')

args = parser.parse_args()

# if (args.region==None or args.preset_id==None or args.preset_output_type==None):
if args.input==None:
    parser.print_help()
    exit()

if args.output != None:
    _output = args.output
else:
    _output = "output"

def read_json_file(file_path):
    if file_path != None:
        if '.json' in file_path:
            try:
                return json.load(open(file_path))
            except ValueError as e:
                log_error('File invalid json: %s' % e)
                exit()

    log_error("File json is must required.")
    exit()

def remove_end_slash(s):
    if s.endswith('/'):
        s = s[:-1]
    return s

def output_dir(path):
    path = remove_end_slash(path) + "/"

    if not os.path.exists(path):
        os.makedirs(path)

    return path

def output_path(filename, subpath):
    if filename is None:
        if subpath != None:
            return output_dir(str(_output) + "/" + str(subpath))
        else:
            return output_dir(str(_output) + "/")

    if subpath != None:
        return output_dir(str(_output) + "/" + str(subpath)) + str(filename)

    return output_dir(str(_output)) + str(filename)

def validation_region(r):
    while True:
        region = r.lower()
        if (region == 'us-east-1') or (region == 'us-west-1') or (region == 'us-west-2') or (region == 'eu-west-1') or (region == 'ap-southeast-1') or (region == 'ap-southeast-2') or (region == 'ap-south-1') or (region == 'ap-northeast-1'):
            return region
        else:
            log_error("Unsupported region selected..exiting")
            exit()

def validate_container(preset_payload, unsupported):
    if  (('Preset' not in preset_payload) or ('Container' not in preset_payload['Preset']) or json.dumps(preset_payload['Preset']['Container']) in unsupported):
        log_error('Unsupported Container found in preset, please try another preset')
        exit()
    else:
        supported_container = json.dumps(preset_payload['Preset']['Container'])
        return supported_container

def validate_video(preset_payload, unsupported):
    if 'Preset' in preset_payload and 'Video' in preset_payload['Preset']:
        if  json.dumps(preset_payload['Preset']['Video']['Codec']) in unsupported:
            log_error('Unsupported Video codec found in preset, please try anohter preset')
            exit()
        else:
            supported_video = json.dumps(preset_payload['Preset']['Video']['Codec'])
            return supported_video
    else:
        supported_video = 'none'
        return supported_video

def validate_audio(preset_payload, unsupported):
    if 'Preset' in preset_payload and 'Audio' in preset_payload['Preset']:
        if  json.dumps(preset_payload['Preset']['Audio']['Codec']) in unsupported:
            log_error('Unsupported Video condec found in preset, please try anohter preset')
            exit()
        else:
            supported_audio = json.dumps(preset_payload['Preset']['Audio']['Codec'])
            return supported_audio
    else:
        supported_audio = 'none'
        return supported_audio

def validate_output(output_type, output_types):
    if output_type.lower() in output_types:
        return output_type
    else:
        log_error("Output group type must be file, apple, dash, or smooth")
        exit()

def validate_input(input_config):
    if input_config != None:
        if '.json' in input_config:
            try:
                # return json.loads(text)
                inputjson = json.load(open(input_config))
                inputdump = json.dumps(inputjson)

                if 'region' not in inputdump:
                    log_error('Invalid, "region" input is must required.')
                    exit()

                if 'pipeline_id' not in inputdump:
                    log_error('Invalid, "pipeline_id" input is must required.')
                    exit()

                if 'presets' not in inputdump:
                    log_error('Invalid, "presets" input is must required.')
                    exit()

                return inputjson
            except ValueError as e:
                log_error('Invalid, input file invalid json: %s' % e)
                exit()

    log_error("Invalid, input file is must required.")
    exit()

def validate_input_presets(presets):
    if presets is None:
        log_error("Invalid, input presets is required.")
        exit()

    if not presets:
        log_error("Invalid, input presets is must not empty.")
        exit()

    name_list = [item['name'] for item in presets if 'name' in item]
    thumbnail_name_list = [item['thumbnail_name'] for item in presets if 'thumbnail_name' in item]
    full_list = name_list + thumbnail_name_list

    if len(full_list) != len(set(full_list)):
        log_error("Invalid, input preset name and thumbnail_name is must not duplicate.")
        exit()

    for preset in presets:
        presetdump = json.dumps(preset)

        if 'preset_id' not in presetdump:
            log_error("Invalid, input presets:preset_id is required.")
            exit()

        if 'output_type' not in presetdump:
            log_error("Invalid, input presets:output_type is required.")
            exit()

        if ('name' in presetdump) and (len(preset['name']) > 40):
            log_error("Invalid, input preset name require <= 40 characters.")
            exit()

        if ('thumbnail_name' in presetdump) and (len(preset['thumbnail_name']) > 40):
            log_error("Invalid, input preset thumbnail_name require <= 40 characters.")
            exit()

    return presets

def get_pipeline(pipeline_id):
    while True:
        try:
            payload_pipeline = _elastictranscoder_client.read_pipeline(Id=pipeline_id.lower())
            return pipeline_id.lower(), payload_pipeline
        except Exception as e:
            print(e)
            exit()

def get_preset(preset_id):
    while True:
        try:
            payload_preset = _elastictranscoder_client.read_preset(Id=preset_id.lower())
            return preset_id.lower(), payload_preset
        except Exception as e:
            print(e)
            exit()

def get_mediaconvert_preset(preset_name):
    while True:
        try:
            response = _mediaconvert_client.get_preset(Name=preset_name)
            return preset_name, response
        except Exception as e:
            return None, None

def create_mediaconvert_preset(preset_category, preset_description, preset_name, preset_configs):
    while True:
        try:
            response = _mediaconvert_client.create_preset(
                Category=preset_category,
                Description=preset_description,
                Name=preset_name,
                Settings=preset_configs)
            return preset_name, response
        except Exception as e:
        # except _mediaconvert_client.exceptions.BadRequestException as e:
            # print(e.response)
            print(e)
            exit()

def update_mediaconvert_preset(preset_category, preset_description, preset_name, preset_configs):
    while True:
        try:
            response = _mediaconvert_client.update_preset(
                Category=preset_category,
                Description=preset_description,
                Name=preset_name,
                Settings=preset_configs)
            return preset_name, response
        except Exception as e:
            print(e)
            exit()

def delete_mediaconvert_preset(preset_name):
    while True:
        try:
           response = _mediaconvert_client.delete_preset(Name=preset_name)
           return preset_name, response
        except Exception as e:
            print(e)
            exit()

def convert_audio(preset_payload, preset_audio):
    audiodump = json.dumps(preset_payload['Preset']['Audio'])
    preset_channel_num = json.dumps(preset_payload['Preset']['Audio']['Channels'])

    if preset_channel_num == '"auto"':
        preset_channel_num = '"2"'
    else:
        preset_channel_num = json.dumps(preset_payload['Preset']['Audio']['Channels'])

    ets_audio_bitrate = int(json.dumps(preset_payload['Preset']['Audio']['BitRate']).strip('"'))
    ets_audio_sample = json.dumps(preset_payload['Preset']['Audio']['SampleRate']).strip('"')

    if ets_audio_sample == "auto":
        ets_audio_sample = 48
    else:
        ets_audio_sample = int(json.dumps(preset_payload['Preset']['Audio']['SampleRate']).strip('"'))

    ###Translate Audio Profile###
    ###AAC Type
    if preset_audio == '"AAC"':
        etsaudioprofile = json.dumps(preset_payload['Preset']['Audio']['CodecOptions']['Profile'])
        aac_range=[64,84,96,112,128,192,224,256,288,320,384,448,512,576]

        if etsaudioprofile == '"AAC-LC"':
            audio_profile = 'LC'
        elif etsaudioprofile == '"HE-AAC"':
            audio_profile = 'HEV1'
        elif etsaudioprofile ==  '"HE-AACV2"':
            audio_profile = 'HEV2'
        else:
            audio_profile = 'LC'
            # print("Warning: No matching profile found, changing to lc \n")

        if preset_channel_num == '"2"':
            audio_coding = "CODING_MODE_2_0"
        elif preset_channel_num == '"1"':
            audio_coding = "CODING_MODE_1_0"
        else:
            audio_coding = "CODING_MODE_2_0"

        emf_bitrate = str(min(aac_range, key=lambda x:abs(x-ets_audio_bitrate)))
        emf_bitrate = int(emf_bitrate) * 1000
        emf_sample = preset_payload['Preset']['Audio']['SampleRate']
        AudioSettings = {}
        AudioSettings = {
            "LanguageCodeControl": "FOLLOW_INPUT",
            "AudioTypeControl": "FOLLOW_INPUT",
            "AudioSourceName": "Audio Selector 1",
            'CodecSettings': {
                'Codec': 'AAC',
                'AacSettings': {
                    'AudioDescriptionBroadcasterMix': "NORMAL",
                    'Bitrate': emf_bitrate,
                    'CodecProfile': audio_profile,
                    'CodingMode': audio_coding,
                    'RawFormat': "NONE",
                    'Specification': "MPEG4",
                    'RateControlMode': 'CBR',
                }
            }
        }

        if emf_sample != 'auto':
            AudioSettings['CodecSettings']['AacSettings'].update({"SampleRate": int(emf_sample)})
        else:
            warning = "Auto in setting Sample Rate not supported...defaulting to  48kHz\n"
            AudioSettings['CodecSettings']['AacSettings'].update({"SampleRate": int(48000)})

    ###PCM/WAV Type
    elif preset_audio == '"wav"' or preset_audio == '"pcm"':
        wav_sample=[8,16,22.05,24,32,44.1,48,88.2,96,192]

        emf_sample = str(min(wav_sample, key=lambda x:abs(x-ets_audio_sample)))
        emf_sample = int(emf_sample) * 1000
        ets_bitdepth=[16,24]
        emf_bitdepth=str(min(ets_bitdepth, key=lambda x:abs(x-int(json.dumps(preset_payload['Preset']['Audio']['CodecOptions']['BitDepth']).strip('"')))))

        if json.dumps(preset_payload['Preset']['Audio']['Channels']) == '"auto"' or json.dumps(preset_payload['Preset']['Audio']['Channels'])== '"0"':
            warning = "0 and auto channels not supported...defaulting to 2\n"
            emf_channels = "2"
        else:
            emf_channels = json.dumps(preset_payload['Preset']['Audio']['Channels']).strip('"')

        AudioSettings = {}
        AudioSettings = {
            "LanguageCodeControl": "FOLLOW_INPUT",
            "AudioTypeControl": "FOLLOW_INPUT",
            "AudioSourceName": "Audio Selector 1",
            'CodecSettings':{
                'Codec': 'WAV',
                'WavSettings': {
                    'BitDepth': int(emf_bitdepth),
                    'Channels': int(emf_channels),
                }
            }
        }

        if emf_sample != 'auto':
            AudioSettings['CodecSettings']['WavSettings'].update({"SampleRate": int(emf_sample)})
        else:
            warning = "Auto in setting Sample Rate not supported...defaulting to 44.1kHz\n"
            AudioSettings['CodecSettings']['WavSettings'].update({"SampleRate": int(44100)})

    ###Type MP2
    elif preset_audio == '"mp2"':
        mp2_range = [32,48,56,64,80,96,112,128,160,192,224,256,320,384]
        mp2_sample_range =[32,44.1,48]

        emf_bitrate = min(mp2_range, key=lambda x:abs(x-ets_audio_bitrate))
        emf_sample = min(mp2_sample_range, key=lambda x:abs(x-ets_audio_sample))
        emf_bitrate = str(min(mp2_range, key=lambda x:abs(x-ets_audio_bitrate)))
        emf_bitrate = int(emf_bitrate) * 1000
        emf_sample = emf_sample * 1000
        AudioSettings = {}

        if json.dumps(preset_payload['Preset']['Audio']['Channels']) == '"auto"' or json.dumps(preset_payload['Preset']['Audio']['Channels'])== '"0"':
            log_warning("Warning = 0 and auto channels not supported...defaulting to 2\n")
            emf_channels = "2"
        else:
            emf_channels = json.dumps(preset_payload['Preset']['Audio']['Channels']).strip('"')
            AudioSettings = {
                "LanguageCodeControl": "FOLLOW_INPUT",
                "AudioTypeControl": "FOLLOW_INPUT",
                "AudioSourceName": "Audio Selector 1",
                'CodecSettings':{
                    'Codec': 'MP2',
                    'Mp2Settings': {
                        'Bitrate': int(emf_bitrate),
                        'Channels': int(emf_channels),
                    }
                }
            }

        if emf_sample != 'auto':
            AudioSettings['CodecSettings']['Mp2Settings'].update({"SampleRate": int(emf_sample)})
        else:
            warning = "Auto in setting Sample Rate not supported...defaulting to 48000kHz\n"
            AudioSettings['CodecSettings']['Mp2Settings'].update({"SampleRate": int(48000)})

    AudioDescription = {}
    AudioDesc1 = {}
    AudioDesc1 = {
        "LanguageCodeControl": "FOLLOW_INPUT",
        "InputTypeControl": "FOLLOW_INPUT",
        "AudioSourceName": "Audio Selector 1",
    }

    AudioExtra = json.dumps(AudioDesc1, indent=4,sort_keys=True)
    AudioDescription ={
        "AudioDescriptions":[]
    }

    AudioDescription['AudioDescriptions'].insert(0, AudioSettings)

    return AudioDescription

def convert_video(preset_payload, preset_video):
    # Checks for Profile for h264 - not putting into fill h264 if due to if ets support h265 in future will be easier to migrate
    videodump = json.dumps(preset_payload['Preset']['Video'])
    if 'Profile' in videodump and preset_video != '"mpeg2"':
        emf_codec_profile = preset_payload['Preset']['Video']['CodecOptions']['Profile'].upper()
        emf_codec_level = preset_payload['Preset']['Video']['CodecOptions']['Level']

        cavlc_profile =  ["HIGH","HIGH_10BIT","HIGH_422","HIGH_422_10BIT","MAIN","BASELINE"]
        if emf_codec_profile in cavlc_profile :
            emf_entropy_encoding = "CAVLC"
        else:
            emf_entropy_encoding = "CABAC"

        ##Logic for Level 1b that isn't supported in AWS Elemental MediaConvert
        if emf_codec_level == '"1b"':
            emf_codec_level = '"AUTO"'
            log_warning("WARNING: 1b not supported in AWS Elemental MediaConvert, defaulting to auto, please change to 1 or 1.1 based off bitrate and resolution \n")
        else:
            emf_codec_level = preset_payload['Preset']['Video']['CodecOptions']['Level']
    if emf_codec_level == '1':
        emf_codec_level = 'LEVEL_1'
    elif emf_codec_level == '1.1':
        emf_codec_level = 'LEVEL_1_1'
    elif emf_codec_level == '1.2':
        emf_codec_level = 'LEVEL_1_2'
    elif emf_codec_level == '1.3':
        emf_codec_level = 'LEVEL_1_3'
    elif emf_codec_level == '2':
        emf_codec_level = 'LEVEL_2'
    elif emf_codec_level == '2.1':
        emf_codec_level = 'LEVEL_2_1'
    elif emf_codec_level == '2.2':
        emf_codec_level = 'LEVEL_2_2'
    elif emf_codec_level == '3':
        emf_codec_level = 'LEVEL_3'
    elif emf_codec_level == '3.1':
        emf_codec_level = 'LEVEL_3_1'
    elif emf_codec_level == '3.2':
        emf_codec_level = 'LEVEL_3_2'
    elif emf_codec_level == '4':
        emf_codec_level = 'LEVEL_4'
    elif emf_codec_level == '4.1':
        emf_codec_level = 'LEVEL_4_1'
    else:
        emf_codec_level = "AUTO"
        log_warning("WARNING: Item not found defaulting to auto, please change based off bitrate and resolution \n")

    if (preset_payload['Preset']['Video']['MaxWidth'] == 'auto') or (preset_payload['Preset']['Video']['MaxHeight'] == 'auto'):
        emf_codec_level = "AUTO"
        log_warning("WARNING: Since resolution != defined setting Profile Level to AUTO")

    ## Interlace Mode Logic
    if preset_payload['Preset']['Video']['CodecOptions']['InterlacedMode'] == 'Progressive':
        emf_interlace_mode = 'PROGRESSIVE'
    elif preset_payload['Preset']['Video']['CodecOptions']['InterlacedMode'] == 'TopFirst':
        emf_interlace_mode = 'TOP_FIELD'
    elif preset_payload['Preset']['Video']['CodecOptions']['InterlacedMode'] == 'BottomFirst':
        emf_interlace_mode = 'BOTTOM_FIELD'
    elif preset_payload['Preset']['Video']['CodecOptions']['InterlacedMode'] == 'Auto':
        emf_interlace_mode = 'PROGRESSIVE'
        log_warning("WARNING: Auto interlaced mode not supported in MediaConvert, setting to progressive")
    else:
        emf_interlace_mode = 'PROGRESSIVE'

    ###Strech output###
    if preset_payload['Preset']['Video']['SizingPolicy'] == '"Stretch"':
        emf_stretch = "STRETCH_TO_OUTPUT"
    else:
        emf_stretch = "DEFAULT"

    ###ColorsSpace Conversion Precessor
    if preset_payload['Preset']['Video']['CodecOptions']['ColorSpaceConversionMode'] == "None":
        emf_enable_color = False
    elif preset_payload['Preset']['Video']['CodecOptions']['ColorSpaceConversionMode'] == "Bt601ToBt709":
        emf_enable_color = True
        emf_color_space_conversion =  'FORCE_709'
    elif preset_payload['Preset']['Video']['CodecOptions']['ColorSpaceConversionMode'] == "Bt709ToBt601":
        emf_enable_color = True
        emf_color_space_conversion = 'FORCE_601'
    else:
        emf_enable_color = False
        log_warning("WARNING: Auto in ColorSpaceConversion != supported in EMF setting ColorSpace on input to Auto and disabling color correction\n")

    if preset_video == '"H.264"':
        xSettings = 'H264Settings'

        emf_video_bitrate = preset_payload['Preset']['Video']['BitRate']
        emf_video_width = preset_payload['Preset']['Video']['MaxWidth']

        if emf_video_bitrate == "113" and emf_video_width == "320" and emf_codec_level != 'LEVEL_1_3':
            emf_codec_level = 'LEVEL_1_3'

        VideoSettings = {}
        VideoSettings = {
            'Codec': 'H_264',
            'H264Settings': {
                'AdaptiveQuantization': 'HIGH',
                'HrdBufferInitialFillPercentage': 90,
                'CodecLevel': emf_codec_level,
                'CodecProfile': emf_codec_profile,
                'FlickerAdaptiveQuantization': "ENABLED",
                'EntropyEncoding': emf_entropy_encoding,
                'GopBReference': "DISABLED",
                'GopClosedCadence': 1,
                'NumberBFramesBetweenReferenceFrames': 0,
                'GopSize': int(preset_payload['Preset']['Video']['KeyframesMaxDist']),
                'GopSizeUnits': 'FRAMES',
                'InterlaceMode': emf_interlace_mode,
                'FramerateConversionAlgorithm': "DUPLICATE_DROP",
                'MinIInterval': 0,
                'NumberReferenceFrames': int(preset_payload['Preset']['Video']['CodecOptions']['MaxReferenceFrames']),
                'QualityTuningLevel': "SINGLE_PASS",
                'RepeatPps': "DISABLED",
                'Syntax': "DEFAULT",
                'SceneChangeDetect': "ENABLED",
                'UnregisteredSeiTimecode': "DISABLED",
                'Slices': 1,
                'FlickerAdaptiveQuantization': "DISABLED",
                'SlowPal': "DISABLED",
                'Softness': 0,
                'SpatialAdaptiveQuantization': "ENABLED",
                'Telecine': 'NONE',
                'TemporalAdaptiveQuantization': "ENABLED"
            },
        }
    elif preset_video == '"mpeg2"':
        xSettings = 'Mpeg2Settings'
        VideoSettings = {}
        VideoSettings = {
            'Codec': 'MPEG2',
            'Mpeg2Settings': {
                'CodecLevel': 'AUTO',
                'CodecProfile': 'MAIN',
                'GopClosedCadence': 1,
                'NumberBFramesBetweenReferenceFrames': 2,
                'GopSize': int(preset_payload['Preset']['Video']['KeyframesMaxDist']),
                'GopSizeUnits': 'FRAMES',
                'InterlaceMode': emf_interlace_mode,
                'FramerateConversionAlgorithm': "DUPLICATE_DROP",
                'MinIInterval': 0,
                'QualityTuningLevel': "SINGLE_PASS",
                'SceneChangeDetect': "ENABLED",
                'SlowPal': "DISABLED",
                'Softness': 0,
                'SpatialAdaptiveQuantization': "ENABLED",
                'Telecine': 'NONE',
                'TemporalAdaptiveQuantization': "ENABLED"
            }
        }

    VideoDescription = {}
    VideoDescription = {
        "VideoDescription": {
            "TimecodeInsertion": "DISABLED" ,
            "AntiAlias": "ENABLED",
            "Sharpness": 100,
            "AfdSignaling": "NONE",
            "RespondToAfd": "NONE",
            "ColorMetadata": "INSERT",
            "ScalingBehavior": emf_stretch,
            "CodecSettings": {}
        }
    }

    if emf_enable_color:
        VideoPreProcessors ={}
        VideoPreProcessors = {
            'VideoPreprocessors': {
                'ColorCorrector': {
                    'Brightness': 50,
                    'ColorSpaceConversion': emf_color_space_conversion,
                    'Contrast': 50,
                    'Hue': 0,
                    'Saturation': 0
                }
            }
        }

        VideoDescription['VideoDescription'].update(VideoPreProcessors)

    ##Handle Auto Resolution
    if preset_payload['Preset']['Video']['MaxWidth'] != 'auto':
        VideoDescription['VideoDescription'].update({"Width" : int(preset_payload['Preset']['Video']['MaxWidth'])})

    if preset_payload['Preset']['Video']['MaxHeight'] != 'auto':
        VideoDescription['VideoDescription'].update({"Height" : int(preset_payload['Preset']['Video']['MaxHeight'])})

    ########################################
    #                                      #
    #         All Codec Type Items         #
    #                                      #
    ########################################

    ###ETS FrameRate auto to EMF FrameRate Follow
    if preset_payload['Preset']['Video']['FrameRate'] == 'auto':
        emf_codec_framerate = "Follow"
        emf_framerate = "INITIALIZE_FROM_SOURCE"
        VideoSettings[xSettings].update({'FramerateControl': emf_framerate})
    else:
        emf_codec_framerate = preset_payload['Preset']['Video']['FrameRate']
        emf_framerate = "SPECIFIED"
        VideoSettings[xSettings].update({'FramerateControl': emf_framerate})

        ###Logic for FrameRate Fraction
        if float(emf_codec_framerate).is_integer() :
            VideoSettings[xSettings].update({'FramerateDenominator': 1})
            VideoSettings[xSettings].update({'FramerateNumerator': int(emf_codec_framerate)})
        else:
            VideoSettings[xSettings].update({'FramerateDenominator': 1001})
            if emf_codec_framerate == "29.97":
                emf_codec_framerate = 30000
            elif emf_codec_framerate == "23.97":
                emf_codec_framerate = 24000

        VideoSettings[xSettings].update({'FramerateNumerator': emf_codec_framerate})

    ###Logic for PAR
    if preset_payload['Preset']['Video']['DisplayAspectRatio'] == "auto":
        emf_codec_par = "Follow"
        emf_par = "INITIALIZE_FROM_SOURCE"
        VideoSettings[xSettings].update({'ParControl': emf_par})

    elif preset_payload['Preset']['Video']['DisplayAspectRatio'] == "1:1":
        emf_codec_par_num = 1
        emf_codec_par_dem = 1
        VideoSettings[xSettings].update({'ParNumerator': emf_codec_par_num})
        VideoSettings[xSettings].update({'ParDenominator': emf_codec_par_dem})
        emf_par = "SPECIFIED"
        VideoSettings[xSettings].update({'ParControl': emf_par})

    elif preset_payload['Preset']['Video']['DisplayAspectRatio'] == "4:3":
        par_num = 4
        emf_codec_par_dem = 3
        VideoSettings[xSettings].update({'ParNumerator': emf_codec_par_num})
        VideoSettings[xSettings].update({'ParDenominator': emf_codec_par_dem})
        emf_par = "SPECIFIED"
        VideoSettings[xSettings].update({'ParControl': emf_par})

    elif preset_payload['Preset']['Video']['DisplayAspectRatio'] == "3:2":
        par_num = 3
        emf_codec_par_dem = 2
        VideoSettings[xSettings].update({'ParNumerator': emf_codec_par_num})
        VideoSettings[xSettings].update({'ParDenominator': emf_codec_par_dem})
        emf_par = "SPECIFIED"
        VideoSettings[xSettings].update({'ParControl': emf_par})

    elif preset_payload['Preset']['Video']['DisplayAspectRatio'] == "16:9":
        emf_codec_par_num = 40
        emf_codec_par_dem = 30
        VideoSettings[xSettings].update({'ParNumerator': emf_codec_par_num})
        VideoSettings[xSettings].update({'ParDenominator': emf_codec_par_dem})
        emf_par = "SPECIFIED"
        VideoSettings[xSettings].update({'ParControl': emf_par})

    ###Rate Control Modes/BitRate/Buffer
    if 'MaxBitrate' in videodump:
        if int(preset_payload['Preset']['Video']['MaxBitRate']) > 0:
            emf_control_mode = 'VBR'
            VideoSettings[xSettings].update({'RateControlMode': emf_control_mode})
            emf_max_bitrate = int(preset_payload['Preset']['Video']['MaxBitRate'])
            VideoSettings[xSettings].update({'MaxBitrate': emf_max_bitrate})

            if preset_payload['Preset']['Video']['Bitrate'] == '"auto"':
                log_warning("WARNING: auto not a supported bitrate parameter in EMF setting to default to 5M")
                emf_bitrate = 5000000
                VideoSettings[xSettings].update({'Bitrate': emf_bitrate})
            else:
                emf_bitrate = int(preset_payload['Preset']['Video']['BitRate'])
                VideoSettings[xSettings].update({'Bitrate': emf_bitrate})
                emf_max_bitrate = int(preset_payload['Preset']['Video']['MaxBitRate'])
                VideoSettings[xSettings].update({'MaxBitrate': emf_max_bitrate})
    else:
        emf_control_mode = 'CBR'
        if preset_payload['Preset']['Video']['BitRate'] != 'auto':
            VideoSettings[xSettings].update({'RateControlMode': emf_control_mode})
            emf_bitrate_temp = int(preset_payload['Preset']['Video']['BitRate'])
            ##convert kilobits to bits
            emf_bitrate = emf_bitrate_temp * 1000

            if emf_bitrate < 1000:
                log_warning("WARNING: Bitrate must be greater than 1000, increase to 1000\n")
                emf_bitrate = 1000
        else:
            emf_bitrate = 5000000
            VideoSettings[xSettings].update({'RateControlMode': emf_control_mode})

        VideoSettings[xSettings].update({'Bitrate': emf_bitrate})

    VideoDescription['VideoDescription'].update({'CodecSettings': VideoSettings})

    return VideoDescription

def convert_container(Mediaconvert_AudioDescription, MediaConvert_VideoDescription, preset_container, MediaConvert_OutputGroup, preset_video, preset_audio):
    if MediaConvert_VideoDescription == 'none' and ((MediaConvert_OutputGroup != 'dash' and preset_container != '"mp4"') or (MediaConvert_OutputGroup == 'dash' and preset_container != '"fmp4"')):
        log_error("Audio only is supported in MP4 or dash fmp4 containers\n")
        exit()

    if MediaConvert_OutputGroup == 'apple' and preset_container == '"ts"':
        OutputGroupSettings = {}
        OutputGroupSettings = {
            "Settings": {
                "ContainerSettings": {
                    "Container": "M3U8",
                    "M3u8Settings": {
                        "AudioFramesPerPes": 2,
                        "PcrControl": "PCR_EVERY_PES_PACKET",
                        "PmtPid": 480,
                        "Scte35Source": "NONE",
                        "ProgramNumber": 1,
                        "PatInterval": 100,
                        "PmtInterval": 100,
                        "TimedMetadata": "NONE",
                        "VideoPid": 481,
                        "AudioPids": [482,483,484,485,486,487,488,489,490,491,492]
                    }
                }
            }
        }

        if MediaConvert_VideoDescription != 'none':
            OutputGroupSettings['Settings'].update(MediaConvert_VideoDescription)
        if Mediaconvert_AudioDescription != 'none':
            OutputGroupSettings['Settings'].update(Mediaconvert_AudioDescription)

        return OutputGroupSettings
    elif MediaConvert_OutputGroup == 'apple' and preset_container == '"mp4"':
        log_error("This tool only supports converting Non-CMAF HLS presets")
        exit()
    elif MediaConvert_OutputGroup == 'apple' and preset_container != '"ts"':
        log_error("ETS Preset must be in a ts container")
        exit()

    if MediaConvert_OutputGroup == 'dash' and preset_video == '"H.264"' and preset_container == '"fmp4"':
        OutputGroupSettings = {}
        OutputGroupSettings = {
            "Settings": {
                "ContainerSettings": {
                    "Container": "MPD"
                }
            }
        }

        if MediaConvert_VideoDescription != 'none':
            OutputGroupSettings['Settings'].update(MediaConvert_VideoDescription)
        if Mediaconvert_AudioDescription != 'none':
            OutputGroupSettings['Settings'].update(Mediaconvert_AudioDescription)
        return OutputGroupSettings
    if MediaConvert_VideoDescription == 'none' and Mediaconvert_AudioDescription != 'none' and MediaConvert_OutputGroup == 'dash' and preset_video == 'none' and preset_container == '"fmp4"':
        OutputGroupSettings = {}
        OutputGroupSettings = {
            "Settings": {
                "ContainerSettings": {
                    "Container": "MPD"
                }
            }
        }

        OutputGroupSettings['Settings'].update(Mediaconvert_AudioDescription)

        return OutputGroupSettings
    elif MediaConvert_OutputGroup == 'dash' and preset_container != '"fmp4"':
        log_error("ETS Preset must have container set to fmp4 for DASH conversion")
        exit()

    if MediaConvert_OutputGroup == 'smooth' and preset_video == '"H.264"' and preset_container == '"fmp4"':
        OutputGroupSettings = {}
        OutputGroupSettings = {
            "Settings": {
                "ContainerSettings": {
                    "Container": "ISMV"
                }
            }
        }

        if MediaConvert_VideoDescription != 'none':
            OutputGroupSettings['Settings'].update(MediaConvert_VideoDescription)
        if Mediaconvert_AudioDescription != 'none':
            OutputGroupSettings['Settings'].update(Mediaconvert_AudioDescription)
        return OutputGroupSettings
    elif MediaConvert_OutputGroup == 'smooth' and preset_container != '"fmp4"':
        print("ETS Preset must have contianer set to fmp4 for smooth conversion")
        exit()

    if MediaConvert_OutputGroup == 'file':
        if preset_container == '"ts"' or preset_container == '"mpg"':
            OutputGroupSettings = {}
            OutputGroupSettings = {
                "Settings": {
                    "ContainerSettings": {
                        "Container": "M2TS",
                        "M2tsSettings": {
                            "AudioBufferModel": "ATSC",
                            "EsRateInPes": "EXCLUDE",
                            "PatInterval": 100,
                            "Scte35Source": "NONE",
                            "VideoPid": 481,
                            "PmtInterval": 100,
                            "SegmentationStyle": "MAINTAIN_CADENCE",
                            "PmtPid": 480,
                            "Bitrate": 0,
                            "AudioPids": [482, 483,484,485, 486,487, 488, 489, 490,491, 492],
                            "PrivateMetadataPid": 503,
                            "DvbSubPids": [460,461,462,463,464,465,466,467,468,469,470,471,472,473,474,475, 476,477,478,479],
                            "RateMode": "CBR",
                            "AudioFramesPerPes": 2,
                            "PcrControl": "PCR_EVERY_PES_PACKET",
                            "SegmentationMarkers": "NONE",
                            "EbpAudioInterval": "VIDEO_INTERVAL",
                            "ProgramNumber": 1,
                            "BufferModel": "MULTIPLEX",
                            "DvbTeletextPid": 499,
                            "EbpPlacement": "VIDEO_AND_AUDIO_PIDS",
                            "NullPacketBitrate": 0
                        }
                    }
                }
            }

            if MediaConvert_VideoDescription != 'none':
                OutputGroupSettings['Settings'].update(MediaConvert_VideoDescription)

                if Mediaconvert_AudioDescription != 'none':
                    OutputGroupSettings['Settings'].update(Mediaconvert_AudioDescription)

                return OutputGroupSettings

            elif preset_container == '"mp4"':
                OutputGroupSettings = {}
                OutputGroupSettings = {
                        "Settings": {
                            "ContainerSettings": {
                                "Container": "MP4",
                                "Mp4Settings": {
                                "CslgAtom": "INCLUDE" ,
                                "FreeSpaceBox": "EXCLUDE",
                                "MoovPlacement": "PROGRESSIVE_DOWNLOAD"
                            }
                        }
                    }
                }

                if MediaConvert_VideoDescription != 'none':
                    OutputGroupSettings['Settings'].update(MediaConvert_VideoDescription)

                    if Mediaconvert_AudioDescription != 'none':
                        OutputGroupSettings['Settings'].update(Mediaconvert_AudioDescription)

                    return OutputGroupSettings

            elif preset_container == '"mxf"':
                OutputGroupSettings = {}
                OutputGroupSettings = {
                    "Settings":{
                        "ContainerSettings": {
                            "Container": "MXF"
                        }
                    }
                }

                if MediaConvert_VideoDescription != 'none':
                    OutputGroupSettings['Settings'].update(MediaConvert_VideoDescription)
                if Mediaconvert_AudioDescription != 'none':
                    OutputGroupSettings['Settings'].update(Mediaconvert_AudioDescription)

                return OutputGroupSettings
        else:
            print("Unknown Error Hit...exiting")
            exit()


        #if preset_container == 'pcm':

        #else:
        #    print("Unknown Error Hit exiting")
        #    exit()

def convert_thumbnails(preset_payload, preset):
    MediaConvert_Preset_Thumbnail = {
        "Name": preset['preset_id'] + '_thumbnails',
        "Description": preset_payload['Preset']['Description'] + ' Thumbnails - clone from preset_id: ' + preset['preset_id'],
        "Settings": {
            "VideoDescription": {
                "ScalingBehavior": "DEFAULT",
                "TimecodeInsertion": "DISABLED",
                "AntiAlias": "ENABLED",
                "Sharpness": 50,
                "CodecSettings": {
                    "Codec": "FRAME_CAPTURE",
                    "FrameCaptureSettings": {
                        "FramerateNumerator": 1,
                        "FramerateDenominator": int(preset_payload['Preset']['Thumbnails']['Interval']),
                        "MaxCaptures": 10000000,
                        "Quality": 80
                    }
                },
                "AfdSignaling": "NONE",
                "DropFrameTimecode": "ENABLED",
                "RespondToAfd": "NONE",
                "ColorMetadata": "INSERT"
            },
            "ContainerSettings": {"Container": "RAW"}
        }
    }

    presetdump = json.dumps(preset)
    # thumbnail_preset_name = preset_payload['Preset']['Name'] + 'Thumbnails'
    if 'thumbnail_name' in presetdump:
        MediaConvert_Preset_Thumbnail['Name'] = preset['thumbnail_name']
    elif (len(preset_payload['Preset']['Name']) > 40):
        preset_name = preset_payload['Preset']['Name']
        MediaConvert_Preset_Name = preset_name[:40]
        MediaConvert_Preset_Thumbnail['Name'] = mediaconvert_PresetName
        log_error("WARNING: Warning name is greater than 40 characters, truncating... \n")
    else:
        MediaConvert_Preset_Thumbnail['Name'] = preset_payload['Preset']['Name']

    ##Handle Auto Resolution
    if preset_payload['Preset']['Video']['MaxWidth'] !=  'auto':
        MediaConvert_Preset_Thumbnail['Settings']['VideoDescription'].update({"Width" : int(preset_payload['Preset']['Thumbnails']['MaxWidth'])})

    if preset_payload['Preset']['Video']['MaxHeight'] !=  'auto':
        MediaConvert_Preset_Thumbnail['Settings']['VideoDescription'].update({"Height" : int(preset_payload['Preset']['Thumbnails']['MaxHeight'])})

    return MediaConvert_Preset_Thumbnail

def export_pipeline():
    pipeline_id, pipeline_payload = get_pipeline(_input['pipeline_id'])

    output_pipeline_path = output_path("pipeline-"+pipeline_id+".json", "elastictranscoder")
    log_info('Export ElasticTranscoder pipeline(' + pipeline_id + ') config...')
    file = open(output_pipeline_path, "w")
    file.write(json.dumps(pipeline_payload, indent=4, sort_keys=False))
    file.close()
    log_success('---> Exported at: ' + output_pipeline_path)
    print(' \n')

def create_mediaconvert_presets(o_dir):
    output_dir = output_path(None, o_dir)

    if not os.path.exists(output_dir):
        log_error('Directory: "' + output_dir + '" is not found.')
        exit()

    yes = {'yes','y', ''}
    no = {'no','n'}

    preset_files = [file_path for file_path in os.listdir(output_dir) if file_path.endswith('.json')]
    for preset_file in preset_files:
        preset = read_json_file(output_dir + preset_file)

        # Check preset
        preset_name, preset_payload = get_mediaconvert_preset(preset['Name'])

        if preset_name is None:
            # Create preset
            log_info("Creating MediaConvert preset name: " + preset['Name'] + "(" + output_dir + preset_file + ")")
            create_mediaconvert_preset('', preset['Description'], preset['Name'], preset['Settings'])
            log_success("---> Created: " + preset['Name'] + " \n")
        else:
            # Update preset : yes/no?
            log_info('MediaConvert preset with name "' + preset_name + '" was exists. Do you want update it? fill yes or no (Default: yes):')
            choice = input().lower()
            if choice in yes:
               update_mediaconvert_preset('', preset['Description'], preset['Name'], preset['Settings'])
               log_success("---> Updated: " + preset_name + " \n")
            elif choice in no:
               continue
            else:
               sys.stdout.write("Please respond with 'yes' or 'no'")

def convert_presets(presets, output_dir, mc_output_dir):
    for preset in presets:
        convert_preset(preset, output_dir, mc_output_dir)

    create_mediaconvert_presets(mc_output_dir)

def convert_preset(preset, output_dir, mc_output_dir):
    # Define the support list.
    output_types=['file','apple','dash','smooth']
    unsupport_containers = ['"webm"','"mp3"','"ogg"','"flac"','"flv"','"gif"']
    unsupport_video_codecs = ['"vp8"','"vp9"','"gif"']
    unsupport_audio_codecs = ['"vorbis"','"flac"','"wav"']

    presetdump = json.dumps(preset)
    preset_id, preset_payload = get_preset(preset['preset_id'])
    preset_container = validate_container(preset_payload, unsupport_containers)
    preset_video = validate_video(preset_payload, unsupport_video_codecs)
    preset_audio = validate_audio(preset_payload, unsupport_audio_codecs)

    # Export preset
    file = open(output_path(preset_id+".json", output_dir), "w")
    file.write(json.dumps(preset_payload, indent=4, sort_keys=False))
    file.close()

    # MediaConvert::Preset:OutputGroup
    MediaConvert_Preset_OutputGroup = validate_output(preset['output_type'], output_types)

    # MediaConvert::Preset:Settings:VideoDescription
    if preset_video != 'none':
        MediaConvert_Preset_VideoDescription = convert_video(preset_payload, preset_video)

        if 'thumbnail_name' in presetdump and preset['thumbnail_name'] != None:
            MediaConvert_Preset_Thumbnails = convert_thumbnails(preset_payload, preset)
    else:
        MediaConvert_Preset_VideoDescription = 'none'

    # MediaConvert::Preset:Settings:AudioDesciption
    if preset_audio != 'none':
        MediaConvert_Preset_AudioDesciption = convert_audio(preset_payload, preset_audio)
    elif 'audio_preset_id' in presetdump and (preset['audio_preset_id'] != None):
        audio_preset_id, audio_preset_payload = get_preset(preset['audio_preset_id'])
        addition_preset_audio = validate_audio(audio_preset_payload, unsupport_audio_codecs)
        MediaConvert_Preset_AudioDesciption = convert_audio(audio_preset_payload, addition_preset_audio)

        # Export preset
        file = open(output_path(audio_preset_id+".json", output_dir), "w")
        file.write(json.dumps(audio_preset_payload, indent=4, sort_keys=False))
        file.close()
    else:
        MediaConvert_Preset_AudioDesciption = 'none'

    # MediaConvert::Preset:Settings
    MediaConvert_Preset_Container = convert_container(
        MediaConvert_Preset_AudioDesciption,
        MediaConvert_Preset_VideoDescription,
        preset_container,
        MediaConvert_Preset_OutputGroup,
        preset_video,
        preset_audio)

    MediaConvert_Preset = {
        "Name": "",
        "Description": "",
        "Settings": {}
    }

    # MediaConvert::Preset:Settings Description
    if preset_payload['Preset']['Description'] == None:
        ts = time.time()
        MediaConvert_Description = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H-%M-%S')
        MediaConvert_Preset['Description'] = MediaConvert_Description
    elif 'audio_preset_id' in presetdump and (preset['audio_preset_id'] != None):
        MediaConvert_Preset['Description'] = preset_payload['Preset']['Description'] + " - clone from preset_id: " + preset_id + " audio_preset_id: " + audio_preset_id
    else:
        MediaConvert_Preset['Description'] = preset_payload['Preset']['Description'] + " - clone from preset_id: " + preset_id

    # MediaConvert::Preset:Settings Name
    if 'name' in presetdump:
        MediaConvert_Preset['Name'] = preset['name']
    elif (len(preset_payload['Preset']['Name']) > 40):
        preset_name = preset_payload['Preset']['Name']
        MediaConvert_PresetName = preset_name[:40]
        MediaConvert_Preset['Name'] = MediaConvert_PresetName
        log_error("WARNING: Warning name is greater than 40 characters, truncating... \n")
    else:
        MediaConvert_Preset['Name'] = preset_payload['Preset']['Name']

    MediaConvert_Preset['Settings'] = MediaConvert_Preset_Container['Settings']

    # print(json.dumps(MediaConvert_Preset, indent=4, sort_keys=True))
    # print('==================SAVING FILES=========================')
    log_info('Convert ElasticTranscoder preset(' + preset_id + ') to MediaConvert preset...')
    output_mediaconvert_preset_path = output_path(MediaConvert_Preset['Name'] + ".json", mc_output_dir)
    file = open(output_mediaconvert_preset_path, "w")
    file.write(json.dumps(MediaConvert_Preset, indent=4, sort_keys=False))
    file.close()
    log_success('---> Converted save to: ' + output_mediaconvert_preset_path)
    print(' \n')

    # print('====================THUMBNAILS=====================')
    # print('==================SAVING FILES=========================')
    if preset_video != 'none' and 'thumbnail_name' in presetdump and preset['thumbnail_name'] != None:
        log_info('Convert ElasticTranscoder THUMBNAILS preset(' + preset_id + ') to MediaConvert THUMBNAILS preset...')
        # print(json.dumps(MediaConvert_Preset_Thumbnails, indent=4, sort_keys=False))
        output_mediaconvert_preset_thumbnail_path = output_path(MediaConvert_Preset_Thumbnails['Name'] + "_Thumbnail.json", mc_output_dir)
        file = open(output_mediaconvert_preset_thumbnail_path, "w")
        file.write(json.dumps(MediaConvert_Preset_Thumbnails, indent=4, sort_keys=False))
        file.close()
        log_success('---> Converted save to: ' + output_mediaconvert_preset_thumbnail_path)
        print(' \n')

# Main
_input = validate_input(args.input)
_region = validation_region(_input['region'])
_presets = validate_input_presets(_input['presets'])
_pipeline_id = _input['pipeline_id']
# _current_path = os.path.abspath(os.getcwd())
_output_etc_dir = "elastictranscoder"
_output_mc_dir = "mediaconvert"
_output_etcp_dir = _output_etc_dir + "/presets"
_output_mcp_dir = _output_mc_dir + "/presets"

# Clear output
_output_path = remove_end_slash(_output) + "/"
if os.path.exists(_output_path):
    shutil.rmtree(_output_path, ignore_errors=True)

# Proccess
aws_config = Config(
    region_name = _region,
)

_elastictranscoder_client = boto3.client('elastictranscoder', config=aws_config)
_mediaconvert_client = boto3.client('mediaconvert', config=aws_config)

export_pipeline()
convert_presets(_presets, _output_etcp_dir, _output_mcp_dir)
# generate_lambda_env()
