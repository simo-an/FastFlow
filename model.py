import numpy as np
import os
import torch
import torch.nn.functional as F
from torch import nn
from torchvision.models import alexnet
from torchsummary import summary

import config as c
from freia_funcs import permute_layer, glow_coupling_layer, F_fully_connected, ReversibleGraphNet, OutputNode, \
    InputNode, Node


WEIGHT_DIR = './weights'
MODEL_DIR = './models'

def subnet_conv(c_in, c_out, kernel_size):
    return nn.Sequential(nn.Conv2d(c_in, c.subnet_conv_dim,   kernel_size=(kernel_size,kernel_size), padding='same'),
                         nn.ReLU(),
                         nn.Conv2d(c.subnet_conv_dim,  c_out, kernel_size=(kernel_size,kernel_size), padding='same'))


def nf_head(input_dim=c.n_feat):
    nodes = list()
    nodes.append(InputNode(input_dim, name='input'))
    for k in range(c.n_coupling_blocks):
        nodes.append(Node([nodes[-1].out0], permute_layer, {'seed': k}, name=F'permute_{k}'))
        nodes.append(Node([nodes[-1].out0], glow_coupling_layer,
                          {'clamp': c.clamp_alpha, 'F_class': F_fully_connected,
                           'F_args': {'internal_size': c.fc_internal, 'dropout': c.dropout}},
                          name=F'fc_{k}'))
    nodes.append(OutputNode([nodes[-1].out0], name='output'))
    coder = ReversibleGraphNet(nodes)
    return coder

def nf_fast_flow(input_dim):
    nodes = list()
    nodes.append(InputNode(input_dim, name='input'))
    for k in range(c.n_coupling_blocks):
        nodes.append(Node([nodes[-1].out0], permute_layer, {'seed': k}, name=F'permute_{k}')) # non va bene, deve permutare solo i channels
        nodes.append(Node([nodes[-1].out0], glow_coupling_layer,
                          {'clamp': c.clamp_alpha, 'F_class': subnet_conv,
                           'F_args': {'c_in': 96, 'c_out': 96, 'kernel_size': 1}},
                          name=F'conv_{k}'))
    nodes.append(OutputNode([nodes[-1].out0], name='output'))
    coder = ReversibleGraphNet(nodes)
    return coder


class FastFlow(nn.Module):
    def __init__(self):
        super(FastFlow, self).__init__()
        #self.feature_extractor = alexnet(pretrained=True)
        self.feature_extractor = torch.hub.load('facebookresearch/deit:main', 'deit_base_distilled_patch16_224', pretrained=True)
        self.feature_extractor = torch.nn.Sequential(*(list(self.feature_extractor.children())[:-2])) # I remove the last two layers

        print(summary(self.feature_extractor, (3,224,224)))
        #self.feature_extractor = torch.load('./pretrained/M48_448.pth') #sbagliato, carica solo i pesi, non il modello
        #self.feature_extractor.eval() # to deactivate the dropout layers
        self.nf = nf_fast_flow((96,196,768))

    def forward(self, x):
        y_cat = list()

        '''
        for s in range(c.n_scales):
            x_scaled = F.interpolate(x, size=c.img_size[0] // (2 ** s)) if s > 0 else x
            #feat_s = self.feature_extractor.features(x_scaled)
            feat_s = self.feature_extractor(x_scaled)
            y_cat.append(torch.mean(feat_s, dim=(2, 3)))
        '''
        feat_s = self.feature_extractor(x)
        #y_cat.append(feat_s)
        #y = torch.cat(y_cat, dim=3)
        print(feat_s)
        z = self.nf(feat_s)
        return z



def save_model(model, filename):
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)
    torch.save(model, os.path.join(MODEL_DIR, filename))


def load_model(filename):
    path = os.path.join(MODEL_DIR, filename)
    model = torch.load(path)
    return model


def save_weights(model, filename):
    if not os.path.exists(WEIGHT_DIR):
        os.makedirs(WEIGHT_DIR)
    torch.save(model.state_dict(), os.path.join(WEIGHT_DIR, filename))


def load_weights(model, filename):
    path = os.path.join(WEIGHT_DIR, filename)
    model.load_state_dict(torch.load(path))
    return model