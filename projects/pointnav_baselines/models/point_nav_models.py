from typing import Tuple, Dict, Optional, Union, List, cast

import gym
import torch
import torch.nn as nn
from gym.spaces.dict import Dict as SpaceDict

from allenact.algorithms.onpolicy_sync.policy import (
    ActorCriticModel,
    LinearCriticHead,
    LinearActorHead,
    ObservationType,
    DistributionType,
)
from allenact.base_abstractions.distributions import CategoricalDistr
from allenact.base_abstractions.misc import ActorCriticOutput, Memory
from allenact.embodiedai.models.basic_models import SimpleCNN, RNNStateEncoder


class PointNavActorCriticSimpleConvRNN(ActorCriticModel[CategoricalDistr]):
    def __init__(
        self,
        action_space: gym.spaces.Discrete,
        observation_space: SpaceDict,
        rgb_uuid: Optional[str],
        depth_uuid: Optional[str],
        goal_sensor_uuid: str,
        hidden_size=512,
        embed_coordinates=False,
        coordinate_embedding_dim=8,
        coordinate_dims=2,
        num_rnn_layers=1,
        rnn_type="GRU",
    ):
        super().__init__(action_space=action_space, observation_space=observation_space)

        self.goal_sensor_uuid = goal_sensor_uuid
        self._hidden_size = hidden_size
        self.embed_coordinates = embed_coordinates
        if self.embed_coordinates:
            self.coordinate_embedding_size = coordinate_embedding_dim
        else:
            self.coordinate_embedding_size = coordinate_dims

        self.sensor_fusion = False
        if rgb_uuid is not None and depth_uuid is not None:
            self.sensor_fuser = nn.Linear(hidden_size * 2, hidden_size)
            self.sensor_fusion = True

        self.visual_encoder = SimpleCNN(
            observation_space=observation_space,
            output_size=hidden_size,
            rgb_uuid=rgb_uuid,
            depth_uuid=depth_uuid,
        )

        self.state_encoder = RNNStateEncoder(
            (0 if self.is_blind else self.recurrent_hidden_state_size)
            + self.coordinate_embedding_size,
            self._hidden_size,
            num_layers=num_rnn_layers,
            rnn_type=rnn_type,
        )

        self.actor = LinearActorHead(self._hidden_size, action_space.n)
        self.critic = LinearCriticHead(self._hidden_size)

        if self.embed_coordinates:
            self.coordinate_embedding = nn.Linear(
                coordinate_dims, coordinate_embedding_dim
            )

        self.train()

    @property
    def output_size(self):
        return self._hidden_size

    @property
    def is_blind(self):
        return self.visual_encoder.is_blind

    @property
    def num_recurrent_layers(self):
        return self.state_encoder.num_recurrent_layers

    def get_target_coordinates_encoding(self, observations):
        if self.embed_coordinates:
            return self.coordinate_embedding(
                observations[self.goal_sensor_uuid].to(torch.float32)
            )
        else:
            return observations[self.goal_sensor_uuid].to(torch.float32)

    @property
    def recurrent_hidden_state_size(self):
        return self._hidden_size

    def _recurrent_memory_specification(self):
        return dict(
            rnn=(
                (
                    ("layer", self.num_recurrent_layers),
                    ("sampler", None),
                    ("hidden", self.recurrent_hidden_state_size),
                ),
                torch.float32,
            )
        )

    def forward(  # type:ignore
        self,
        observations: ObservationType,
        memory: Memory,
        prev_actions: torch.Tensor,
        masks: torch.FloatTensor,
    ) -> Tuple[ActorCriticOutput[DistributionType], Optional[Memory]]:
        target_encoding = self.get_target_coordinates_encoding(observations)
        x: Union[torch.Tensor, List[torch.Tensor]]
        x = [target_encoding]

        # if observations["rgb"].shape[0] != 1:
        #     print("rgb", (observations["rgb"][...,0,0,:].unsqueeze(-2).unsqueeze(-2) == observations["rgb"][...,0,0,:]).float().mean())
        #     if "depth" in observations:
        #         print("depth", (observations["depth"][...,0,0,:].unsqueeze(-2).unsqueeze(-2) == observations["depth"][...,0,0,:]).float().mean())

        if not self.is_blind:
            perception_embed = self.visual_encoder(observations)
            if self.sensor_fusion:
                perception_embed = self.sensor_fuser(perception_embed)
            x = [perception_embed] + x

        x = torch.cat(x, dim=-1)
        x, rnn_hidden_states = self.state_encoder(x, memory.tensor("rnn"), masks)

        ac_output = ActorCriticOutput(
            distributions=self.actor(x), values=self.critic(x), extras={}
        )

        return ac_output, memory.set_tensor("rnn", rnn_hidden_states)


class InverseModel(nn.Module):
    def __init__(
        self, action_space: gym.spaces.Discrete, input_size: int,
    ):
        super().__init__()
        self.input_size = input_size
        self.output_size = action_space.n - 1
        self.action_predictor = nn.Linear(self.input_size, self.output_size)

    def forward(self, obs_encoding, rnn_hidden_states=None):
        curr_state = obs_encoding
        next_state = obs_encoding.roll(-1, 0)
        next_state[obs_encoding.size(0) - 1, :, :] = obs_encoding[
            obs_encoding.size(0) - 1, :, :
        ]
        action_logits = self.action_predictor(torch.cat([curr_state, next_state], 2))
        return action_logits


class RotationModel(nn.Module):
    def __init__(self, state_size: int = 1568):
        super().__init__()
        self.state_size = state_size
        self.rotation_predictor = nn.Sequential(nn.Linear(state_size, 4))

    def forward(self, state):
        rotation_logits = self.rotation_predictor(state)
        return rotation_logits


# Model for self-supervised adaptation
class ResnetTensorAuxPointNavActorCritic(ActorCriticModel[CategoricalDistr]):
    def __init__(
        self,
        action_space: gym.spaces.Discrete,
        observation_space: SpaceDict,
        goal_sensor_uuid: str,
        rgb_resnet_preprocessor_uuid: Optional[str] = None,
        depth_resnet_preprocessor_uuid: Optional[str] = None,
        hidden_size: int = 512,
        goal_dims: int = 32,
        resnet_compressor_hidden_out_dims: Tuple[int, int] = (128, 32),
        combiner_hidden_out_dims: Tuple[int, int] = (128, 32),
        aux_mode: bool = False,
        inv_mode: bool = False,
        rot_mode: bool = False,
    ):

        super().__init__(
            action_space=action_space, observation_space=observation_space,
        )

        # Auxiliary Task Arguments
        self.aux_mode = aux_mode
        self.inv_mode = inv_mode
        self.rot_mode = rot_mode

        self._hidden_size = hidden_size
        if (
            rgb_resnet_preprocessor_uuid is None
            or depth_resnet_preprocessor_uuid is None
        ):
            resnet_preprocessor_uuid = (
                rgb_resnet_preprocessor_uuid
                if rgb_resnet_preprocessor_uuid is not None
                else depth_resnet_preprocessor_uuid
            )
            self.goal_visual_encoder = ResnetTensorAuxGoalEncoder(
                self.observation_space,
                goal_sensor_uuid,
                resnet_preprocessor_uuid,
                goal_dims,
                resnet_compressor_hidden_out_dims,
                combiner_hidden_out_dims,
            )
        else:
            self.goal_visual_encoder = ResnetDualTensorGoalEncoder(  # type:ignore
                self.observation_space,
                goal_sensor_uuid,
                rgb_resnet_preprocessor_uuid,
                depth_resnet_preprocessor_uuid,
                goal_dims,
                resnet_compressor_hidden_out_dims,
                combiner_hidden_out_dims,
            )
        self.state_encoder = RNNStateEncoder(
            self.goal_visual_encoder.output_dims, self._hidden_size,
        )
        self.actor = LinearActorHead(self._hidden_size, action_space.n)
        self.critic = LinearCriticHead(self._hidden_size)

        if self.inv_mode and self.aux_mode:
            self.inverse_model = InverseModel(
                action_space, 2 * self.goal_visual_encoder.output_dims,
            )

        if self.rot_mode and self.aux_mode:
            self.rotation_model = RotationModel(self.goal_visual_encoder.output_dims)

        self.train()
        self.memory_key = "rnn"

    @property
    def recurrent_hidden_state_size(self) -> int:
        """The recurrent hidden state size of the model."""
        return self._hidden_size

    @property
    def is_blind(self) -> bool:
        """True if the model is blind (e.g. neither 'depth' or 'rgb' is an
        input observation type)."""
        return self.goal_visual_encoder.is_blind

    @property
    def num_recurrent_layers(self) -> int:
        """Number of recurrent hidden layers."""
        return self.state_encoder.num_recurrent_layers

    def _recurrent_memory_specification(self):
        return {
            self.memory_key: (
                (
                    ("layer", self.num_recurrent_layers),
                    ("sampler", None),
                    ("hidden", self.recurrent_hidden_state_size),
                ),
                torch.float32,
            )
        }

    def forward(  # type:ignore
        self,
        observations: ObservationType,
        memory: Memory,
        prev_actions: torch.Tensor,
        masks: torch.FloatTensor,
    ) -> Tuple[ActorCriticOutput[DistributionType], Optional[Memory]]:

        obs_encoding, orig_observations = self.goal_visual_encoder(
            observations
        )  # Added new goal-visual encoder to return unshaped observations

        obs_encoding, rnn_hidden_states = self.state_encoder(
            obs_encoding, memory.tensor(self.memory_key), masks
        )

        action_logits = None
        rotation_logits = None

        if self.inv_mode and self.aux_mode:
            obs_input = self.goal_visual_encoder.visual_compressor(orig_observations)
            action_logits = self.inverse_model(obs_input)

        if self.rot_mode and self.aux_mode:
            obs_input = self.goal_visual_encoder.visual_compressor(orig_observations)
            rotation_logits = self.rotation_model(obs_input)

        return (
            ActorCriticOutput(
                distributions=self.actor(obs_encoding),
                values=self.critic(obs_encoding),
                extras={
                    "pred_action_logits": action_logits,
                    "pred_rotation_logits": rotation_logits,
                    "rnn_hidden_states": rnn_hidden_states,
                },
            ),
            memory.set_tensor(self.memory_key, rnn_hidden_states),
        )



class RdmaenavTensorPointNavActorCritic(ActorCriticModel[CategoricalDistr]):
    """
    构建RDMAE-Nav整体框架
    """
    def __init__(
        self,
        action_space: gym.spaces.Discrete,
        observation_space: SpaceDict,
        goal_sensor_uuid: str,#target处理后embed.的ID
        rgb_vit_preprocessor_uuid: Optional[str] = None,#rgb处理后embed.的ID
        depth_vit_preprocessor_uuid: Optional[str] = None,#深度图处理后embed.的ID
        hidden_size: int = 512,#visual embed.的维度
        goal_dims: int = 32,#target embed.的维度
    ):

        super().__init__(
            action_space=action_space, observation_space=observation_space,
        )

        self._hidden_size = hidden_size
        if (#只处理RGB输入
            rgb_vit_preprocessor_uuid is None
            or depth_vit_preprocessor_uuid is None
        ):
            vit_preprocessor_uuid = (
                rgb_vit_preprocessor_uuid
                if rgb_vit_preprocessor_uuid is not None
                else depth_vit_preprocessor_uuid
            )
            self.goal_visual_encoder = VitTensorGoalEncoder(
                self.observation_space,
                goal_sensor_uuid,
                vit_preprocessor_uuid,
                goal_dims,
            )
        else:#RGB和depth同时输入处理，参考ResnetDualTensorGoalEncoder
            pass
        self.state_encoder = RNNStateEncoder(#policy module中的GRU
            self.goal_visual_encoder.output_dims, self._hidden_size,
        )
        self.actor = LinearActorHead(self._hidden_size, action_space.n)
        self.critic = LinearCriticHead(self._hidden_size)
        self.train()
        self.memory_key = "rnn"

    @property
    def recurrent_hidden_state_size(self) -> int:
        """The recurrent hidden state size of the model."""
        return self._hidden_size

    @property
    def is_blind(self) -> bool:
        """True if the model is blind (e.g. neither 'depth' or 'rgb' is an
        input observation type)."""
        return self.goal_visual_encoder.is_blind

    @property
    def num_recurrent_layers(self) -> int:
        """Number of recurrent hidden layers."""
        return self.state_encoder.num_recurrent_layers

    def _recurrent_memory_specification(self):
        return {
            self.memory_key: (
                (
                    ("layer", self.num_recurrent_layers),
                    ("sampler", None),
                    ("hidden", self.recurrent_hidden_state_size),
                ),
                torch.float32,
            )
        }

    def forward(  # type:ignore
        self,
        observations: ObservationType,
        memory: Memory,
        prev_actions: torch.Tensor,
        masks: torch.FloatTensor,
    ) -> Tuple[ActorCriticOutput[DistributionType], Optional[Memory]]:
        x = self.goal_visual_encoder(observations)
        x, rnn_hidden_states = self.state_encoder(
            x, memory.tensor(self.memory_key), masks
        )
        return (
            ActorCriticOutput(
                distributions=self.actor(x), values=self.critic(x), extras={}
            ),
            memory.set_tensor(self.memory_key, rnn_hidden_states),
        ) 


class ResnetTensorAuxGoalEncoder(nn.Module):
    def __init__(
        self,
        observation_spaces: SpaceDict,
        goal_sensor_uuid: str,
        resnet_preprocessor_uuid: str,
        goal_dims: int = 32,
        resnet_compressor_hidden_out_dims: Tuple[int, int] = (128, 32),
        combiner_hidden_out_dims: Tuple[int, int] = (128, 32),
    ) -> None:
        super().__init__()
        self.goal_uuid = goal_sensor_uuid
        self.resnet_uuid = resnet_preprocessor_uuid
        self.goal_dims = goal_dims
        self.resnet_hid_out_dims = resnet_compressor_hidden_out_dims
        self.combine_hid_out_dims = combiner_hidden_out_dims
        self.embed_goal = nn.Linear(2, self.goal_dims)
        self.blind = self.resnet_uuid not in observation_spaces.spaces
        if not self.blind:
            self.resnet_tensor_shape = observation_spaces.spaces[self.resnet_uuid].shape
            self.resnet_compressor = nn.Sequential(
                nn.Conv2d(self.resnet_tensor_shape[0], self.resnet_hid_out_dims[0], 1),
                nn.ReLU(),
                nn.Conv2d(*self.resnet_hid_out_dims[0:2], 1),
                nn.ReLU(),
            )
            self.target_obs_combiner = nn.Sequential(
                nn.Conv2d(
                    self.resnet_hid_out_dims[1] + self.goal_dims,
                    self.combine_hid_out_dims[0],
                    1,
                ),
                nn.ReLU(),
                nn.Conv2d(*self.combine_hid_out_dims[0:2], 1),
            )

    @property
    def is_blind(self):
        return self.blind

    @property
    def output_dims(self):
        if self.blind:
            return self.goal_dims
        else:
            return (
                self.combine_hid_out_dims[-1]
                * self.resnet_tensor_shape[1]
                * self.resnet_tensor_shape[2]
            )

    def get_object_type_encoding(
        self, observations: Dict[str, torch.FloatTensor]
    ) -> torch.FloatTensor:
        """Get the object type encoding from input batched observations."""
        return cast(
            torch.FloatTensor,
            self.embed_goal(observations[self.goal_uuid].to(torch.int64)),
        )

    def compress_resnet(self, observations):
        return self.resnet_compressor(observations[self.resnet_uuid])

    def distribute_target(self, observations):
        target_emb = self.embed_goal(observations[self.goal_uuid])
        return target_emb.view(-1, self.goal_dims, 1, 1).expand(
            -1, -1, self.resnet_tensor_shape[-2], self.resnet_tensor_shape[-1]
        )

    def adapt_input(self, observations):
        resnet = observations[self.resnet_uuid]

        use_agent = False
        nagent = 1

        if len(resnet.shape) == 6:
            use_agent = True
            nstep, nsampler, nagent = resnet.shape[:3]
        else:
            nstep, nsampler = resnet.shape[:2]

        observations[self.resnet_uuid] = resnet.view(-1, *resnet.shape[-3:])
        observations[self.goal_uuid] = observations[self.goal_uuid].view(-1, 2)

        return observations, use_agent, nstep, nsampler, nagent

    @staticmethod
    def adapt_output(x, use_agent, nstep, nsampler, nagent):
        if use_agent:
            return x.view(nstep, nsampler, nagent, -1)
        return x.view(nstep, nsampler * nagent, -1)

    def forward(self, observations):
        observations, use_agent, nstep, nsampler, nagent = self.adapt_input(
            observations
        )

        if self.blind:
            return self.embed_goal(observations[self.goal_uuid])
        embs = [
            self.compress_resnet(observations),
            self.distribute_target(observations),
        ]
        x = self.target_obs_combiner(torch.cat(embs, dim=1,))
        x = x.reshape(x.size(0), -1)  # flatten

        if use_agent:
            observations[self.resnet_uuid] = observations[self.resnet_uuid].view(
                nstep, nsampler, nagent, *observations[self.resnet_uuid].shape[-3:]
            )
        observations[self.resnet_uuid] = observations[self.resnet_uuid].view(
            nstep, nsampler * nagent, *observations[self.resnet_uuid].shape[-3:]
        )

        return self.adapt_output(x, use_agent, nstep, nsampler, nagent), observations

    def visual_compressor(self, observations, rot_resnet_uuid=None):
        if rot_resnet_uuid is not None:
            rgb_uuid = self.resnet_uuid
            self.resnet_uuid = rot_resnet_uuid
        observations, use_agent, nstep, nsampler, nagent = self.adapt_input(
            observations
        )
        x = self.compress_resnet(observations)
        x = x.view(x.size(0), -1)  # flatten

        if rot_resnet_uuid is not None:
            self.resnet_uuid = rgb_uuid

        return self.adapt_output(x, use_agent, nstep, nsampler, nagent)



class VitTensorGoalEncoder(nn.Module):
    """
    构造RDMAE-Nav的visual encoder和target encoder,供RdmaenavTensorPointNavActorCritic调用
    """
    def __init__(
        self,
        observation_spaces: SpaceDict,
        goal_sensor_uuid: str,
        vit_preprocessor_uuid: str,
        goal_dims: int = 32,
    ) -> None:
        super().__init__()
        self.goal_uuid = goal_sensor_uuid
        self.vit_uuid = vit_preprocessor_uuid
        self.goal_dims = goal_dims
        self.embed_goal = nn.Linear(2, self.goal_dims)#将2维坐标通过线性层投射到32维
        self.blind = self.vit_uuid not in observation_spaces.spaces
        if not self.blind:
            self.vit_tensor_shape = observation_spaces.spaces[self.vit_uuid].shape
            self.target_obs_combiner = nn.Sequential(
                nn.Linear(512 + self.goal_dims, 1568)#512维visual embed.和32维target embed.联合成544维joint embed.经过线性层投射为1568
            )

    @property
    def is_blind(self):
        return self.blind

    @property
    def output_dims(self):
        if self.blind:
            return self.goal_dims
        else:
            return (
                1568#544->1568
            )

    def get_object_type_encoding(
        self, observations: Dict[str, torch.FloatTensor]
    ) -> torch.FloatTensor:
        """Get the object type encoding from input batched observations."""
        return cast(
            torch.FloatTensor,
            self.embed_goal(observations[self.goal_uuid].to(torch.int64)),
        )

    def compress_vit(self, observations):
        return observations[self.vit_uuid]

    def distribute_target(self, observations):
        target_emb = self.embed_goal(observations[self.goal_uuid])
        return target_emb.view(-1, self.goal_dims)

    def adapt_input(self, observations):
        vit = observations[self.vit_uuid]

        use_agent = False
        nagent = 1

        if len(vit.shape) == 6:#此处作用不明确
            use_agent = True
            nstep, nsampler, nagent = vit.shape[:3]
        else:
            nstep, nsampler = vit.shape[:2]

        observations[self.vit_uuid] = vit.view(-1, 512)
        observations[self.goal_uuid] = observations[self.goal_uuid].view(-1, 2)

        return observations, use_agent, nstep, nsampler, nagent

    @staticmethod
    def adapt_output(x, use_agent, nstep, nsampler, nagent):
        if use_agent:
            return x.view(nstep, nsampler, nagent, -1)
        return x.view(nstep, nsampler * nagent, -1)

    def forward(self, observations):
        observations, use_agent, nstep, nsampler, nagent = self.adapt_input(
            observations
        )

        if self.blind:
            return self.embed_goal(observations[self.goal_uuid])
        embs = [
            self.compress_vit(observations),
            self.distribute_target(observations),
        ]
        x = self.target_obs_combiner(torch.cat(embs, dim=1,))
        x = x.reshape(x.size(0), -1)  # flatten

        return self.adapt_output(x, use_agent, nstep, nsampler, nagent)

class ResnetDualTensorGoalEncoder(nn.Module):
    def __init__(
        self,
        observation_spaces: SpaceDict,
        goal_sensor_uuid: str,
        rgb_resnet_preprocessor_uuid: str,
        depth_resnet_preprocessor_uuid: str,
        goal_dims: int = 32,
        resnet_compressor_hidden_out_dims: Tuple[int, int] = (128, 32),
        combiner_hidden_out_dims: Tuple[int, int] = (128, 32),
    ) -> None:
        super().__init__()
        self.goal_uuid = goal_sensor_uuid
        self.rgb_resnet_uuid = rgb_resnet_preprocessor_uuid
        self.depth_resnet_uuid = depth_resnet_preprocessor_uuid
        self.goal_dims = goal_dims
        self.resnet_hid_out_dims = resnet_compressor_hidden_out_dims
        self.combine_hid_out_dims = combiner_hidden_out_dims
        self.embed_goal = nn.Linear(2, self.goal_dims)
        self.blind = (
            self.rgb_resnet_uuid not in observation_spaces.spaces
            or self.depth_resnet_uuid not in observation_spaces.spaces
        )
        if not self.blind:
            self.resnet_tensor_shape = observation_spaces.spaces[
                self.rgb_resnet_uuid
            ].shape
            self.rgb_resnet_compressor = nn.Sequential(
                nn.Conv2d(self.resnet_tensor_shape[0], self.resnet_hid_out_dims[0], 1),
                nn.ReLU(),
                nn.Conv2d(*self.resnet_hid_out_dims[0:2], 1),
                nn.ReLU(),
            )
            self.depth_resnet_compressor = nn.Sequential(
                nn.Conv2d(self.resnet_tensor_shape[0], self.resnet_hid_out_dims[0], 1),
                nn.ReLU(),
                nn.Conv2d(*self.resnet_hid_out_dims[0:2], 1),
                nn.ReLU(),
            )
            self.rgb_target_obs_combiner = nn.Sequential(
                nn.Conv2d(
                    self.resnet_hid_out_dims[1] + self.goal_dims,
                    self.combine_hid_out_dims[0],
                    1,
                ),
                nn.ReLU(),
                nn.Conv2d(*self.combine_hid_out_dims[0:2], 1),
            )
            self.depth_target_obs_combiner = nn.Sequential(
                nn.Conv2d(
                    self.resnet_hid_out_dims[1] + self.goal_dims,
                    self.combine_hid_out_dims[0],
                    1,
                ),
                nn.ReLU(),
                nn.Conv2d(*self.combine_hid_out_dims[0:2], 1),
            )

    @property
    def is_blind(self):
        return self.blind

    @property
    def output_dims(self):
        if self.blind:
            return self.goal_dims
        else:
            return (
                2
                * self.combine_hid_out_dims[-1]
                * self.resnet_tensor_shape[1]
                * self.resnet_tensor_shape[2]
            )

    def get_object_type_encoding(
        self, observations: Dict[str, torch.FloatTensor]
    ) -> torch.FloatTensor:
        """Get the object type encoding from input batched observations."""
        return cast(
            torch.FloatTensor,
            self.embed_goal(observations[self.goal_uuid].to(torch.int64)),
        )

    def compress_rgb_resnet(self, observations):
        return self.rgb_resnet_compressor(observations[self.rgb_resnet_uuid])

    def compress_depth_resnet(self, observations):
        return self.depth_resnet_compressor(observations[self.depth_resnet_uuid])

    def distribute_target(self, observations):
        target_emb = self.embed_goal(observations[self.goal_uuid])
        return target_emb.view(-1, self.goal_dims, 1, 1).expand(
            -1, -1, self.resnet_tensor_shape[-2], self.resnet_tensor_shape[-1]
        )

    def adapt_input(self, observations):
        rgb = observations[self.rgb_resnet_uuid]
        depth = observations[self.depth_resnet_uuid]

        use_agent = False
        nagent = 1

        if len(rgb.shape) == 6:
            use_agent = True
            nstep, nsampler, nagent = rgb.shape[:3]
        else:
            nstep, nsampler = rgb.shape[:2]

        observations[self.rgb_resnet_uuid] = rgb.view(-1, *rgb.shape[-3:])
        observations[self.depth_resnet_uuid] = depth.view(-1, *depth.shape[-3:])
        observations[self.goal_uuid] = observations[self.goal_uuid].view(-1, 2)

        return observations, use_agent, nstep, nsampler, nagent

    @staticmethod
    def adapt_output(x, use_agent, nstep, nsampler, nagent):
        if use_agent:
            return x.view(nstep, nsampler, nagent, -1)
        return x.view(nstep, nsampler, -1)

    def forward(self, observations):
        observations, use_agent, nstep, nsampler, nagent = self.adapt_input(
            observations
        )

        if self.blind:
            return self.embed_goal(observations[self.goal_uuid])
        rgb_embs = [
            self.compress_rgb_resnet(observations),
            self.distribute_target(observations),
        ]
        rgb_x = self.rgb_target_obs_combiner(torch.cat(rgb_embs, dim=1,))
        depth_embs = [
            self.compress_depth_resnet(observations),
            self.distribute_target(observations),
        ]
        depth_x = self.depth_target_obs_combiner(torch.cat(depth_embs, dim=1,))
        x = torch.cat([rgb_x, depth_x], dim=1)
        x = x.reshape(x.size(0), -1)  # flatten

        return self.adapt_output(x, use_agent, nstep, nsampler, nagent)
