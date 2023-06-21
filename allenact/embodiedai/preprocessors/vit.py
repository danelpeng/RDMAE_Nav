from turtle import forward
from typing import List, Callable, Optional, Any, cast, Dict

import gym
import numpy as np
import torch
from torch import nn as nn
from torchvision import models

from allenact.base_abstractions.preprocessor import Preprocessor
from allenact.utils.misc_utils import prepare_locals_for_super

import allenact.embodiedai.preprocessors.base_vit as vit

_MODEL_FUNC = {
    "vitt": vit.vit_t16,
    "vits": vit.vit_s16,
    "vitb": vit.vit_b16,
    "vitl": vit.vit_l16,
}

class VitEmbedder(nn.Module):
    def __init__(
        self,
        freeze = True,#冻结权重
        emb_dim = 512#visual embed.的维度
    ):
        super(VitEmbedder, self).__init__()
        model_func = _MODEL_FUNC["vits"]#选择模型，需要与预训练模型一致
        img_size = 224
        #预训练模型路径
        pretrain_path = "/home/pengjie/projects/RDMAE_Nav/checkpoints/rdmae.pth"
        self.backbone , gap_dim = model_func(pretrain_path, img_size=img_size)
        if freeze:
            self.backbone.freeze()
        self.freeze = freeze
        self.projector = nn.Linear(gap_dim, emb_dim)
    
    @torch.no_grad()
    def forward(self, x):
        feat = self.backbone.extract_feat(x)
        return self.projector(self.backbone.forward_norm(feat)), feat
    
    def forward_feat(self, feat):
        return self.projector(self.backbone.forward_norm(feat))

class VitPreprocessor(Preprocessor):
    """Preprocess RGB image using a Pretrained RDMAE-ViT model."""

    def __init__(
        self,
        input_uuids: List[str],
        output_uuid: str,
        input_height: int,
        input_width: int,
        output_dims: int,
        pool: bool,
        device: Optional[torch.device] = None,
        device_ids: Optional[List[torch.device]] = None,
        **kwargs: Any
    ):
        def f(x, k):
            assert k in x, "{} must be set in VitPreprocessor".format(k)
            return x[k]

        def optf(x, k, default):
            return x[k] if k in x else default

        self.input_height = input_height
        self.input_width = input_width
        self.output_dims = output_dims
        self.pool = pool

        self.device = torch.device("cpu") if device is None else device
        self.device_ids = device_ids or cast(
            List[torch.device], list(range(torch.cuda.device_count()))
        )

        self._vit: Optional[VitEmbedder] = None

        low = -np.inf
        high = np.inf
        shape = (self.output_dims, )

        assert (
            len(input_uuids) == 1
        ), "vit preprocessor can only consume one observation type"

        observation_space = gym.spaces.Box(low=low, high=high, shape=shape)

        super().__init__(**prepare_locals_for_super(locals()))

    @property
    def vit(self) -> VitEmbedder:
        if self._vit is None:
            self._vit = VitEmbedder()
        return self._vit

    def to(self, device: torch.device) -> "VitPreprocessor":
        self._vit = self.vit.to(device)
        self.device = device
        return self

    def process(self, obs: Dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        x = obs[self.input_uuids[0]].to(self.device).permute(0, 3, 1, 2)  # bhwc -> bchw
        # If the input is depth, repeat it across all 3 channels
        if x.shape[1] == 1:
            x = x.repeat(1, 3, 1, 1)
        obs_emb, obs_feat = self.vit(x.to(self.device))
        return obs_emb