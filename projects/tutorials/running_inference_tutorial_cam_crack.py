from typing import Optional

from allenact.utils.viz_utils import (
    VizSuite,
    TrajectoryViz,
    ActorViz,
    AgentViewViz,
    TensorViz1D,
    TensorViz2D,
)
from allenact_plugins.robothor_plugin.robothor_viz import ThorViz


from projects.robustnav.experiments.eval.pointnav_robothor_vanilla_rgb_rdmae_ddppo_cam_crack import (
    PointNavS2SRGBVitDDPPO,)

class PointNavRoboThorRGBPPOVizExperimentConfig(PointNavS2SRGBVitDDPPO):
    """ExperimentConfig used to demonstrate how to set up visualization code.

    # Attributes

    viz_ep_ids : Scene names that will be visualized.
    viz_video_ids : Scene names that will have videos visualizations associated with them.
    """

    viz_ep_ids = [
        "FloorPlan_Val1_1_104",
        "FloorPlan_Val1_1_47",
        "FloorPlan_Val1_1_54",
        "FloorPlan_Val1_1_69",
    ]
    viz_video_ids = [["FloorPlan_Val1_1_104"], ["FloorPlan_Val1_1_47"]]

    viz: Optional[VizSuite] = None

    def get_viz(self, mode):
        if self.viz is not None:
            return self.viz

        self.viz = VizSuite(
            episode_ids=self.viz_ep_ids,
            mode=mode,
            # Basic 2D trajectory visualizer (task output source):
            base_trajectory=TrajectoryViz(
                path_to_target_location=("task_info", "target",),
            ),
            # Egocentric view visualizer (vector task source):
            egeocentric=AgentViewViz(
                max_video_length=100, episode_ids=self.viz_video_ids
            ),
            # Default action probability visualizer (actor critic output source):
            action_probs=ActorViz(figsize=(3.25, 10), fontsize=18),
            # Default taken action logprob visualizer (rollout storage source):
            taken_action_logprobs=TensorViz1D(),
            # Same episode mask visualizer (rollout storage source):
            episode_mask=TensorViz1D(rollout_source=("masks",)),
            # Default recurrent memory visualizer (rollout storage source):
            rnn_memory=TensorViz2D(),
            # Specialized 2D trajectory visualizer (task output source):
            thor_trajectory=ThorViz(
                figsize=(16, 8),
                viz_rows_cols=(448, 448),
                scenes=("FloorPlan_Val{}_{}", 1, 1, 1, 1),
            ),
        )

        return self.viz

    def machine_params(self, mode="train", **kwargs):
        res = super().machine_params(mode, **kwargs)
        if mode == "test":
            res.set_visualizer(self.get_viz(mode))

        return res