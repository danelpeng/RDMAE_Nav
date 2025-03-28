# Regularized Denoising Masked Visual Pretraining for Robust Embodied PointGoal Navigation



## Overall

![](https://github.com/dniwsac/RDMAE_Nav/blob/master/assets/rdmae.png)



![](https://github.com/dniwsac/RDMAE_Nav/blob/master/assets/overall.png)



## Installation

NVIDIA GeForce RTX 3060, python3.6, torch1.10.2+cu113

1. First install [Anaconda](https://docs.anaconda.com/anaconda/install/linux/)

2. Use conda environment

   ```
   conda env create --file robustnav.yml --name <ENV-NAME>
   
   e.g. conda env create --file robustnav.yml --name rdmaenav
   ```

3. Activate the conda environment

   ```
   conda activate <ENV-NAME>
   ```



## Train

### Setting

Specify the path of the pretrained visual module in "allenact/embodiedai/preprocessors/vit.py "

```
e.g. 
pretrain_path = "/home/pengjie/projects/RDMAE_Nav/checkpoints/rdmae.pth"
```

### Begin

Run the following command to train a navigation agent

```
bash train.sh
```

### Description

```
python main.py \
    -o storage/robothor-pointnav-rgb-rdmae-ddppo \
    -exp pointnav_robothor_vanilla_rgb_rdmae_ddppo \
    -b projects/robustnav/experiments/train \
    -s 12345 \
    -et rnav_pointnav_vanilla_rgb_rdmae_ddppo_clean
    
#Parameters Description
-o: 	Model and log storage location
-exp:  	Experimental configuration, together with -b to form the task file and path
-b: 	Task folder path
-s: 	Random seed
-et: 	The name of the folder where the tensorboard is saved
```



## Test

### Setting

The pretraining model consists of two parts：visual module and policy module

1. Specify the path of the pretrained visual module in "allenact/embodiedai/preprocessors/vit.py "

   ```
   e.g. 
   pretrain_path = "/home/pengjie/projects/RDMAE_Nav/checkpoints/rdmae.pth"
   ```

2. Specify the path of the pretrained policy module in "test.sh"

   ```
   e.g.
   agent=/home/pengjie/projects/RDMAE_Nav/checkpoints/rdmae_nav.pt
   ```

### Begin

Run the following command to train a navigation agent

```
bash test.sh
```

### Description

Tests for clean and visual corruptions. Results are saved in "storage/robothor-pointnav-rgb-rdmae-ddppo-eval".



## Pretrain Visualization
![](https://github.com/dniwsac/RDMAE_Nav/blob/master/assets/viz.png)


## Visualization

### Setting

Specify the episodes to be visualized in projects/tutorials/running_inference_tutorial.py, running_inference_tutorial_fov.py, and running_inference_tutorial_cam_crack.py.

```
viz_ep_ids: 	Specify the episodes to be visualized in the top-down trajectory
viz_video_ids： Specify the episodes to be visualized for egocentric navigation
```

### Begin

```
bash viz.sh
```

## Description

The visualization results are saved in the tensorboard file in "storage/robothor-pointnav-rgb-rdmae-ddppo-eval"

**egocentric navigation**

![](https://github.com/dniwsac/RDMAE_Nav/blob/master/assets/video_example.gif)

**top-down trajectory**

![](https://github.com/dniwsac/RDMAE_Nav/blob/master/assets/scene_viz.png)

![](https://github.com/dniwsac/RDMAE_Nav/blob/master/assets/coor_viz.png)



## Caution

This project requires internet connection to render the UI interface when running, so **internet connection is required** during training/testing and can be disconnected after training/testing starts.



## Acknowledgement

This project has heavily referenced code from [robustnav](https://github.com/allenai/robustnav), thanks!



## Others

This project was completed by [Daniel Peng](https://github.com/danelpeng).







