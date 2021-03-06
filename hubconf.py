dependencies = ["torch", "requests"]

import requests
import torch
from pathlib import Path

from bunch import Bunch

from models.fatchord_version import WaveRNN
from models.tacotron import Tacotron
from utils.text.symbols import symbols
from utils.text import text_to_sequence

ROOT = Path(__file__).parent

hp = Bunch(
    # Settings for all models
    sample_rate = 22050,
    n_fft = 2048,
    fft_bins = 2048 // 2 + 1,
    num_mels = 80,
    hop_length = 275,                    # 12.5ms - in line with Tacotron 2 paper,
    win_length = 1100,                   # 50ms - same reason as above
    fmin = 40,
    min_level_db = -100,
    ref_level_db = 20,
    bits = 9,                            # bit depth of signal
    mu_law = True,                       # Recommended to suppress noise if using raw bits in hp.voc_mode below
    peak_norm = False,                   # Normalise to the peak of each wav file

    # Model Hparams
    voc_mode = 'MOL',                    # either 'RAW' (softmax on raw bits) or 'MOL' (sample from mixture of logistics)
    voc_upsample_factors = (5, 5, 11),   # NB - this needs to correctly factorise hop_length
    voc_rnn_dims = 512,
    voc_fc_dims = 512,
    voc_compute_dims = 128,
    voc_res_out_dims = 128,
    voc_res_blocks = 10,

    # Training
    voc_batch_size = 32,
    voc_lr = 1e-4,
    voc_checkpoint_every = 25_000,
    voc_gen_at_checkpoint = 5,      # number of samples to generate at each checkpoint
    voc_total_steps = 1_000_000,         # Total number of training steps
    voc_test_samples = 50,               # How many unseen samples to put aside for testing
    voc_pad = 2,                         # this will pad the input so that the resnet can 'see' wider than input length
    voc_seq_len = 275 * 5,        # must be a multiple of hop_length
    voc_clip_grad_norm = 4,              # set to None if no gradient clipping needed

    # Generating / Synthesizing
    voc_gen_batched = True,              # very fast (realtime+) single utterance batched generation
    voc_target = 11_000,                 # target number of samples to be generated in each batch entry
    voc_overlap = 550,                   # number of samples for crossfading between batches

    # Model Hparams
    tts_embed_dims = 256,                # embedding dimension for the graphemes/phoneme inputs
    tts_encoder_dims = 128,
    tts_decoder_dims = 256,
    tts_postnet_dims = 128,
    tts_encoder_K = 16,
    tts_lstm_dims = 512,
    tts_postnet_K = 8,
    tts_num_highways = 4,
    tts_dropout = 0.5,
    tts_cleaner_names = ['english_cleaners'],
    tts_stop_threshold = -3.4,           # Value below which audio generation ends.
                                        # For example, for a range of [-4, 4], this
                                        # will terminate the sequence at the first
                                        # frame that has all values < -3.4

# Training

    tts_schedule = [(7,  1e-3,  10_000,  32),   # progressive training schedule
                    (5,  1e-4, 100_000,  32),   # (r, lr, step, batch_size)
                    (2,  1e-4, 180_000,  16),
                    (2,  1e-4, 350_000,  8)],

    tts_max_mel_len = 1250,              # if you have a couple of extremely long spectrograms you might want to use this
    tts_bin_lengths = True,             # bins the spectrogram lengths before sampling in data loader - speeds up training)
)

def hparams():
    return hp

def text_to_sequence_converter():
    return text_to_sequence

def fetch_and_load_state_dict(model_name: str):
    WEIGHT_PATH = ROOT / "pretrained" / model_name / "latest_weights.pyt"
    data = requests.get(
        f"https://github.com/keitakurita/WaveRNN_Manual/raw/master/pretrained/{model_name}/latest_weights.pyt"
    )
    with WEIGHT_PATH.open("wb") as f:
        f.write(data.content)
    state_dict = torch.load(WEIGHT_PATH)
    return state_dict

def wave_rnn(pretrained=True, **kwargs):
    model = WaveRNN(rnn_dims=hp.voc_rnn_dims,
                    fc_dims=hp.voc_fc_dims,
                    bits=hp.bits,
                    pad=hp.voc_pad,
                    upsample_factors=hp.voc_upsample_factors,
                    feat_dims=hp.num_mels,
                    compute_dims=hp.voc_compute_dims,
                    res_out_dims=hp.voc_res_out_dims,
                    res_blocks=hp.voc_res_blocks,
                    hop_length=hp.hop_length,
                    sample_rate=hp.sample_rate,
                    mode=hp.voc_mode)
    if pretrained:
        state_dict = fetch_and_load_state_dict("wavernn")
        model.load_state_dict(state_dict)
    return model


def tacotron(pretrained=True, **kwargs):
    model = Tacotron(embed_dims=hp.tts_embed_dims,
                     num_chars=len(symbols),
                     encoder_dims=hp.tts_encoder_dims,
                     decoder_dims=hp.tts_decoder_dims,
                     n_mels=hp.num_mels,
                     fft_bins=hp.num_mels,
                     postnet_dims=hp.tts_postnet_dims,
                     encoder_K=hp.tts_encoder_K,
                     lstm_dims=hp.tts_lstm_dims,
                     postnet_K=hp.tts_postnet_K,
                     num_highways=hp.tts_num_highways,
                     dropout=hp.tts_dropout,
                     stop_threshold=hp.tts_stop_threshold)
    if pretrained:
        state_dict = fetch_and_load_state_dict("tacotron")
        state_dict["decoder.r"] = state_dict.pop("r")
        state_dict["stop_threshold"] = torch.tensor(hp.tts_stop_threshold, dtype=torch.float32)
        model.load_state_dict(state_dict)
    return model
